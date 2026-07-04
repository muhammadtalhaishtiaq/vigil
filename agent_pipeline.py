"""
agent_pipeline.py — Vigil Intelligence Engine
===============================================
Orchestrates all 8 Vigil agents through intent-based routing.

Flow:
  run_pipeline(user_message, profile, history)
    → STEP 1: assemble full context (profile + history + live data)
    → STEP 2: Orchestrator (intent classification + initial synthesis)
    → STEP 3: specialist agents dispatched per intent routing table
              (FULL_BRIEFING Wave 2 runs 3 agents in parallel)
    → STEP 4: structured result dict returned — caller owns persistence

Framework-free engine: no Streamlit, no FastAPI, no HTTP between agents.
LLM access via any OpenAI-compatible endpoint (default: AIML API).
"""

import os
import re
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from data_layer import get_all_live_data

# Load .env for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [agent_pipeline] %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Secret resolution (env / .env)
# ---------------------------------------------------------------------------
def _get_secret(key: str, default: str = "") -> str:
    """Read a secret from the environment (.env is loaded above)."""
    return os.getenv(key, default)

# ---------------------------------------------------------------------------
# LLM client (OpenAI-compatible, lazy singleton)
#
# Provider-agnostic: any OpenAI-compatible endpoint works.
#   LLM_BASE_URL — default https://api.aimlapi.com/v1
#   LLM_API_KEY  — falls back to AIML_API_KEY, then OPENAI_API_KEY
# ---------------------------------------------------------------------------
_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """Lazily initialise and return the OpenAI-compatible LLM client."""
    global _client
    if _client is None:
        api_key = (
            _get_secret("LLM_API_KEY")
            or _get_secret("AIML_API_KEY")
            or _get_secret("OPENAI_API_KEY")
        )
        if not api_key:
            logger.warning("No LLM API key set (LLM_API_KEY / AIML_API_KEY) — agent calls will fail")
        _client = OpenAI(
            api_key=api_key,
            base_url=_get_secret("LLM_BASE_URL", "https://api.aimlapi.com/v1"),
        )
    return _client


# ---------------------------------------------------------------------------
# Agent model routing table
# ---------------------------------------------------------------------------
_MODEL_MAP: dict[str, str] = {
    "orchestrator":       "claude-sonnet-4-6",        # was opus — sonnet is 3-5x faster
    "signal_harvester":   "claude-haiku-4-5-20251001",
    "narrative_intel":    "claude-sonnet-4-6",
    "macro_watchdog":     "claude-sonnet-4-6",
    "competitive_intel":  "claude-sonnet-4-6",
    "risk_synthesizer":   "claude-sonnet-4-6",        # was opus — sonnet sufficient
    "strategy_commander": "claude-sonnet-4-6",
    "market_oracle":      "claude-haiku-4-5-20251001",
}


def _model_for(agent_name: str) -> str:
    """Resolve the model for an agent. VIGIL_MODEL env var overrides all agents."""
    override = _get_secret("VIGIL_MODEL")
    if override:
        return override
    return _MODEL_MAP.get(agent_name, "claude-sonnet-4-6")

# All 8 agent names in pipeline order
_ALL_AGENTS: list[str] = list(_MODEL_MAP.keys())

# Intents that produce full risk analysis → update the dashboard strip
# INVESTMENT_QUERY and MARKET_PULSE use Oracle / brief-mode → skip strip update
_STRIP_UPDATE_INTENTS: frozenset[str] = frozenset({
    "FULL_BRIEFING",
    "MACRO_FOCUS",
    "COMPETITIVE_FOCUS",
    "DECISION_SUPPORT",
    "SCENARIO",
})

# ---------------------------------------------------------------------------
# System prompt loader
# ---------------------------------------------------------------------------
_PROMPTS_DIR = Path(__file__).parent / "prompts"
_prompt_cache: dict[str, str] = {}


def _load_prompt(agent_name: str) -> str:
    """
    Load the system prompt for an agent from /prompts/{agent_name}.txt.
    Caches the result in memory after first read.

    Returns empty string if the file is missing — agent will run with
    no system prompt rather than crashing the pipeline.
    """
    if agent_name in _prompt_cache:
        return _prompt_cache[agent_name]

    prompt_file = _PROMPTS_DIR / f"{agent_name}.txt"
    try:
        content = prompt_file.read_text(encoding="utf-8").strip()
        _prompt_cache[agent_name] = content
        logger.debug("Prompt loaded for %s (%d chars)", agent_name, len(content))
        return content
    except FileNotFoundError:
        logger.warning("Prompt file not found: %s (agent will run without system prompt)", prompt_file)
        _prompt_cache[agent_name] = ""
        return ""
    except Exception as exc:
        logger.error("Failed to load prompt for %s: %s", agent_name, exc)
        _prompt_cache[agent_name] = ""
        return ""


def invalidate_prompt_cache() -> None:
    """Force reload of all prompt files on next agent call (useful during development)."""
    _prompt_cache.clear()


# ---------------------------------------------------------------------------
# FUNCTION: update_agent_status
# ---------------------------------------------------------------------------

_VALID_STATUSES = {"idle", "queued", "running", "complete", "error"}

# Module-level status registry — the UI layer reads these (or subscribes via
# set_status_listener) to render the agent flow visualisation.
AGENT_STATUSES: dict[str, str] = {a: "idle" for a in _ALL_AGENTS}
AGENT_ELAPSED: dict[str, Optional[float]] = {a: None for a in _ALL_AGENTS}

_status_listener = None


def set_status_listener(callback) -> None:
    """Register a callable(agent_name, status, elapsed) invoked on every status change."""
    global _status_listener
    _status_listener = callback


def update_agent_status(
    agent_name: str,
    status: str,
    elapsed: Optional[float] = None,
) -> None:
    """
    Update the per-agent status and elapsed time.

    Args:
        agent_name: One of the 8 Vigil agent identifiers.
        status:     One of "idle" | "queued" | "running" | "complete" | "error"
        elapsed:    Seconds the agent took to complete (optional).
    """
    if status not in _VALID_STATUSES:
        logger.warning("Invalid status '%s' for agent '%s' — ignored", status, agent_name)
        return

    AGENT_STATUSES[agent_name] = status
    if elapsed is not None:
        AGENT_ELAPSED[agent_name] = round(elapsed, 2)

    logger.debug(
        "Agent status: %s → %s%s",
        agent_name, status,
        f" ({elapsed:.2f}s)" if elapsed is not None else "",
    )

    if callable(_status_listener):
        try:
            _status_listener(agent_name, status, elapsed)
        except Exception:
            pass  # Never crash the pipeline over a UI notification failure


# ---------------------------------------------------------------------------
# FUNCTION: run_agent
# ---------------------------------------------------------------------------

def run_agent(
    agent_name: str,
    system_prompt: str,
    user_content: str,
    max_tokens: int = 2000,
) -> str:
    """
    Execute a single agent call via the AIML API.

    Updates agent_statuses: idle → running → complete | error
    Logs elapsed time per agent.

    Args:
        agent_name:    Agent identifier (used for model lookup and status updates).
        system_prompt: The agent's system prompt (loaded from /prompts/).
        user_content:  The assembled user-side input for this agent.
        max_tokens:    Maximum response length.

    Returns:
        The agent's text response, or a safe error placeholder string.
    """
    update_agent_status(agent_name, "running")
    start_ts = time.perf_counter()

    try:
        client = _get_client()
        model = _model_for(agent_name)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_content})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.35,
        )

        elapsed = time.perf_counter() - start_ts
        update_agent_status(agent_name, "complete", elapsed)

        content = (response.choices[0].message.content or "").strip()
        logger.info(
            "✓ %s completed in %.2fs | model: %s | output: %d chars",
            agent_name, elapsed, model, len(content),
        )
        return content

    except Exception as exc:
        elapsed = time.perf_counter() - start_ts
        update_agent_status(agent_name, "error", elapsed)
        logger.error(
            "✗ %s failed after %.2fs: %s",
            agent_name, elapsed, str(exc)[:120],
        )
        return (
            f"[{agent_name.upper().replace('_', ' ')} UNAVAILABLE — "
            f"analysis for this section could not be completed. Error: {str(exc)[:80]}]"
        )


# ---------------------------------------------------------------------------
# FUNCTION: parse_orchestrator_response
# ---------------------------------------------------------------------------

def parse_orchestrator_response(response: str) -> dict:
    """
    Extract structured fields from a Vigil-formatted markdown response.

    Used on both the Orchestrator output and the Risk Synthesizer output.
    Every field extraction is wrapped independently — one parse failure
    never cascades to other fields. All unresolvable fields return None/[].

    Returns:
        dict with keys:
            intent_type          str | None
            agents_to_activate   list[str]
            risk_score           int | None    (0–100)
            risk_tier            str | None
            verdict              str | None
            top_risks            list[dict]    (name, probability, detail, action_if_ignored)
            top_actions          list[dict]    (title, deadline, owner, urgency, detail)
            executive_brief      str | None
            full_playbook        str | None
            market_pulse_summary str | None
    """
    result: dict = {
        "intent_type": None,
        "agents_to_activate": [],
        "risk_score": None,
        "risk_tier": None,
        "verdict": None,
        "top_risks": [],
        "top_actions": [],
        "executive_brief": None,
        "full_playbook": None,
        "market_pulse_summary": None,
        "score_breakdown": {},
        "oracle_verdict": None,
    }

    if not response or not response.strip():
        return result

    # ── INTENT TYPE ──────────────────────────────────────────────────────────
    try:
        # New format: INTENT_TYPE: FULL_BRIEFING
        intent_match = re.search(r"INTENT[_\s]TYPE[:\s]+([A-Z_]{4,30})", response)
        if not intent_match:
            intent_match = re.search(r"\bINTENT[:\s]+([A-Z_]{4,30})", response)
        if intent_match:
            result["intent_type"] = intent_match.group(1).strip()
    except Exception:
        pass

    # ── AGENTS ACTIVATED (from header: "Agents activated: signal, macro...") ─
    try:
        agents_match = re.search(
            r"AGENTS[_\s]NEEDED[:\s]+([^\n]+)|[Aa]gents?\s+activated[:\s*]+([^\n\*]+)", response
        )
        if agents_match:
            raw = agents_match.group(1) or agents_match.group(2) or ""
            raw = re.sub(r"[\[\]\*\|]", "", raw)
            parsed_agents = [a.strip() for a in re.split(r"[,;]", raw) if a.strip()]
            result["agents_to_activate"] = parsed_agents
    except Exception:
        pass

    # ── INFER INTENT FROM AGENTS LIST (fallback) ─────────────────────────────
    if not result["intent_type"] and result["agents_to_activate"]:
        try:
            agents_lower = " ".join(result["agents_to_activate"]).lower()
            if "market_oracle" in agents_lower or "market oracle" in agents_lower:
                result["intent_type"] = "INVESTMENT_QUERY"
            elif len(result["agents_to_activate"]) >= 6:
                result["intent_type"] = "FULL_BRIEFING"
            elif "macro" in agents_lower:
                result["intent_type"] = "MACRO_FOCUS"
            elif "competitive" in agents_lower:
                result["intent_type"] = "COMPETITIVE_FOCUS"
            elif "narrative" in agents_lower:
                result["intent_type"] = "MARKET_PULSE"
        except Exception:
            pass

    # ── RISK SCORE ────────────────────────────────────────────────────────────
    try:
        # New format: RISK_SCORE: 72
        score_match = re.search(r"RISK[_\s]SCORE[:\s]+(\d{1,3})", response, re.IGNORECASE)
        if not score_match:
            score_match = re.search(
                r"(?:COMPOSITE\s+)?RISK\s+SCORE[:\s\*]*(\d{1,3})\s*/\s*100",
                response, re.IGNORECASE,
            )
        if score_match:
            score = int(score_match.group(1))
            result["risk_score"] = max(0, min(100, score))
    except Exception:
        pass

    # ── RISK TIER ─────────────────────────────────────────────────────────────
    try:
        # New format: RISK_TIER: ORANGE
        tier_match = re.search(r"RISK[_\s]TIER[:\s]+(GREEN|YELLOW|ORANGE|RED|DARK_RED)", response, re.IGNORECASE)
        if not tier_match:
            tier_match = re.search(
                r"TIER[:\s\|\*]+([A-Z]+(?:\s+[A-Z]+)?(?:\s*[🟢✅⚠️🟠🔴⬛])?)",
                response, re.IGNORECASE,
            )
        if tier_match:
            result["risk_tier"] = tier_match.group(1).strip()
    except Exception:
        pass

    # ── VERDICT ───────────────────────────────────────────────────────────────
    try:
        # New format: VERDICT: [text]
        verdict_match = re.search(r"^VERDICT[:\s]+(.+)$", response, re.MULTILINE | re.IGNORECASE)
        if not verdict_match:
            # Old format: THE VERDICT heading
            verdict_match = re.search(
                r"THE\s+VERDICT\s*\n+>\s*[\"']?(.+?)[\"']?\s*(?:\n\n|\*\*RISK|\*\*TIME|---|\Z)",
                response, re.DOTALL | re.IGNORECASE,
            )
        if verdict_match:
            result["verdict"] = verdict_match.group(1).strip()
        else:
            # Fallback: look for a quoted verdict line
            fallback_match = re.search(r'>\s*["\']?([^"\'\n]{20,200})["\']?', response)
            if fallback_match:
                result["verdict"] = fallback_match.group(1).strip()
    except Exception:
        pass

    # ── EXECUTIVE BRIEF ───────────────────────────────────────────────────────
    try:
        brief_match = re.search(
            r"EXECUTIVE[_\s]BRIEF[:\s]+(.+?)(?:\n\n|\Z)",
            response, re.IGNORECASE | re.DOTALL,
        )
        if not brief_match:
            brief_match = re.search(
                r"EXECUTIVE\s+BRIEF\s*\n+([\s\S]+?)(?:\n---|\n###|\n\*\*\*|\Z)",
                response, re.IGNORECASE,
            )
        if brief_match:
            result["executive_brief"] = brief_match.group(1).strip()
    except Exception:
        pass

    # ── SCORE BREAKDOWN ───────────────────────────────────────────────────────
    try:
        breakdown_match = re.search(
            r"SCORE[_\s]BREAKDOWN[:\s]*\n([\s\S]+?)(?:\n\n|\nSIGNAL|\Z)",
            response, re.IGNORECASE,
        )
        if breakdown_match:
            bd_text = breakdown_match.group(1)
            bd = {}
            for field, key in [("MACRO", "macro"), ("MARKET", "market"),
                                ("NARRATIVE", "narrative"), ("COMPETITIVE", "competitive")]:
                m = re.search(rf"{field}[:\s]+(\d{{1,3}})", bd_text, re.IGNORECASE)
                if m:
                    bd[key] = max(0, min(100, int(m.group(1))))
            if bd:
                result["score_breakdown"] = bd
    except Exception:
        pass

    # ── ORACLE VERDICT ────────────────────────────────────────────────────────
    try:
        oracle_match = re.search(r"ORACLE[_\s]VERDICT[:\s]+(BUY|WAIT|CAUTION|AVOID)", response, re.IGNORECASE)
        if oracle_match:
            result["oracle_verdict"] = oracle_match.group(1).upper()
    except Exception:
        pass

    # ── TOP 3 RISKS (new format: NAME: | PROBABILITY: | SEVERITY:) ────────────
    try:
        # New structured format from risk_synthesizer.txt
        top_risks_new = re.findall(
            r"NAME:\s*(.+?)\s*\|\s*PROBABILITY:\s*(\d+)\s*\|\s*SEVERITY:\s*([A-Z]+)\s*\n"
            r"\s*DETAIL:\s*(.+?)(?:\n\s*ACTION_IF_IGNORED:\s*(.+?))?(?:\n\s*TIMELINE:\s*(.+?))?(?:\n\s*OWNER:\s*(.+?))?(?=\n\d+\.|$)",
            response, re.DOTALL,
        )
        if top_risks_new:
            for m in top_risks_new[:3]:
                result["top_risks"].append({
                    "name": m[0].strip(),
                    "probability": int(m[1]) if m[1] else 50,
                    "severity": m[2].strip() if m[2] else "MEDIUM",
                    "detail": m[3].strip()[:300] if m[3] else "",
                    "action_if_ignored": m[4].strip() if m[4] else "",
                    "timeline": m[5].strip() if m[5] else "",
                    "owner": m[6].strip() if m[6] else "Leadership",
                })
    except Exception:
        pass

    # ── TOP 3 RISKS (old format fallback) ─────────────────────────────────────
    if not result["top_risks"]:
        try:
            risks_section = re.search(
                r"TOP[_\s]RISKS?[:\s]*\n+([\s\S]+?)(?:\nTOP[_\s]ACTIONS|\nSCORE[_\s]BREAKDOWN|\n###|\n---|\n✅|\n🟢|\Z)",
                response, re.IGNORECASE,
            )
            if risks_section:
                risks_text = risks_section.group(1)
                risk_items = re.findall(
                    r"\d+\.\s+\*\*(.+?)\*\*\s*[—\-–]+\s*(.+?)\s*[—\-–]+\s*Probability:\s*([\d]+%?)",
                    risks_text,
                )
                if not risk_items:
                    risk_items_simple = re.findall(
                        r"\d+\.\s+\*\*(.+?)\*\*[^\n]*\n.*?([^\n]{10,120})",
                        risks_text,
                    )
                    for name, detail in risk_items_simple[:3]:
                        result["top_risks"].append({
                            "name": name.strip(),
                            "probability": 50,
                            "detail": detail.strip(),
                            "action_if_ignored": "",
                        })
                else:
                    for name, detail, prob in risk_items[:3]:
                        result["top_risks"].append({
                            "name": name.strip(),
                            "probability": int(re.sub(r"[^0-9]", "", prob)) if prob else 50,
                            "detail": detail.strip(),
                            "action_if_ignored": "",
                        })
        except Exception:
            pass

    # ── TOP 3 ACTIONS (new format: TITLE: / DETAIL: / DEADLINE: / OWNER:) ─────
    try:
        # New structured format from strategy_commander.txt
        top_actions_new = re.findall(
            r"TITLE:\s*(.+?)\s*\n\s*DETAIL:\s*(.+?)\s*\n\s*DEADLINE:\s*(.+?)\s*\n\s*OWNER:\s*(.+?)\s*\n\s*EST_TIME:\s*(.+?)\s*\n\s*URGENCY:\s*([A-Z]+)",
            response, re.DOTALL,
        )
        if top_actions_new:
            for m in top_actions_new[:3]:
                result["top_actions"].append({
                    "title": m[0].strip()[:60],
                    "detail": m[1].strip()[:300],
                    "deadline": m[2].strip(),
                    "owner": m[3].strip(),
                    "est_time": m[4].strip(),
                    "urgency": m[5].strip(),
                })
    except Exception:
        pass

    # ── TOP 3 ACTIONS / NEXT MOVES (old format fallback) ─────────────────────
    if not result["top_actions"]:
        try:
            actions_section = re.search(
                r"(?:YOUR\s+NEXT\s+3\s+MOVES|NEXT\s+3\s+MOVES|TOP[_\s]3\s+ACTIONS?|IMMEDIATE\s+ACTIONS?)\s*\n+([\s\S]+?)(?:\n###|\n---|\n📅|\n📊|\n💰|\nFINANCIAL_STANCE|\Z)",
                response, re.IGNORECASE,
            )
            if actions_section:
                actions_text = actions_section.group(1)
                action_items = re.findall(
                    r"\d+\.\s+\*\*(.+?)\*\*\s*→\s*Owner:\s*([^|\n]+?)\s*\|\s*Deadline:\s*([^\n|]+)",
                    actions_text,
                )
                if not action_items:
                    action_items_simple = re.findall(
                        r"\d+\.\s+\*\*(.+?)\*\*[^\n]*\n?\s*→?\s*([^\n]{10,120})",
                        actions_text,
                    )
                    for title, detail in action_items_simple[:3]:
                        result["top_actions"].append({
                            "title": title.strip(),
                            "owner": "Leadership",
                            "deadline": "This week",
                            "urgency": "HIGH",
                            "detail": detail.strip(),
                        })
                else:
                    for title, owner, deadline in action_items[:3]:
                        result["top_actions"].append({
                            "title": title.strip(),
                            "owner": owner.strip(),
                            "deadline": deadline.strip(),
                            "urgency": "HIGH",
                            "detail": "",
                        })
        except Exception:
            pass

    # ── MARKET PULSE SUMMARY ──────────────────────────────────────────────────
    try:
        pulse_match = re.search(
            r"MARKET\s+PULSE\s*\n+([\s\S]+?)(?:\n---|\n###|\n💬|\n\*\Z|\Z)",
            response, re.IGNORECASE,
        )
        if pulse_match:
            result["market_pulse_summary"] = pulse_match.group(1).strip()
    except Exception:
        pass

    # ── DEFAULT INTENT ────────────────────────────────────────────────────────
    if not result["intent_type"]:
        result["intent_type"] = "FULL_BRIEFING"

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _set_agents_queued(agents: list[str]) -> None:
    """Mark a list of agents as queued (about to run)."""
    for agent in agents:
        update_agent_status(agent, "queued")


def _set_agents_idle(agents: list[str]) -> None:
    """Mark a list of agents as idle (not activated for this query)."""
    for agent in agents:
        update_agent_status(agent, "idle")


def _reset_pipeline_statuses() -> None:
    """Reset all agents to idle at the start of each pipeline run."""
    for agent in _ALL_AGENTS:
        update_agent_status(agent, "idle")


def _profile_field(profile: dict, *keys: str, fallback: str = "Not specified") -> str:
    """Return the first non-empty profile value among keys (list values joined)."""
    for key in keys:
        val = profile.get(key)
        if isinstance(val, list) and val:
            return ", ".join(str(v) for v in val)
        if val and str(val).strip():
            return str(val).strip()
    return fallback


def has_sufficient_profile(profile: Optional[dict]) -> bool:
    """A profile is usable when it names the company and states what it does."""
    if not isinstance(profile, dict):
        return False
    name = _profile_field(profile, "company_name", "name", fallback="")
    desc = _profile_field(profile, "description", fallback="")
    return bool(name and desc)


def get_profile_context_string(profile: Optional[dict]) -> str:
    """
    Format a company profile as a clean text block suitable for
    prepending to LLM agent prompts. Empty string when no profile.
    """
    if not isinstance(profile, dict) or not profile:
        return ""

    f = lambda *keys: _profile_field(profile, *keys)
    lines = [
        "[COMPANY PROFILE — VIGIL CONTEXT]",
        f"Company: {f('company_name', 'name')} | Sector: {f('sector', 'industry')}"
        + (f" / {f('sub_sector')}" if profile.get("sub_sector") else ""),
        f"Location: {f('country', 'location')} | ARR: {f('arr', 'arr_range')} "
        f"| Stage: {f('stage', 'funding_stage')} | Runway: {f('runway')}",
        f"WHAT THEY DO: {f('description')}",
        f"CURRENT DECISIONS: {f('current_decisions')}",
        f"KEY RISK EXPOSURES: {f('risk_areas')}",
        f"ACTIVE REGULATIONS: {f('regulations')}",
        "[END PROFILE]",
    ]
    return "\n".join(lines)


def _history_context_string(history: Optional[list], last_n: int = 6) -> str:
    """Format recent conversation turns for agent context (empty if no history)."""
    if not history:
        return ""
    lines = ["[RECENT CONVERSATION]"]
    for msg in history[-last_n:]:
        role = str(msg.get("role", "user")).upper()
        content = str(msg.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content[:500]}")
    lines.append("[END CONVERSATION]")
    return "\n".join(lines) if len(lines) > 2 else ""


def _build_business_context(
    profile: Optional[dict],
    user_message: str,
) -> str:
    """
    Return the best available business context string for specialist inputs.
    Prefers the formatted profile block; falls back to the raw user message.
    """
    if has_sufficient_profile(profile):
        return get_profile_context_string(profile)
    return f"USER QUERY (infer business context from this message):\n{user_message}"


def _build_signal_input(business_context: str, live_data_text: str) -> str:
    """Assemble the Signal Harvester input payload."""
    return json.dumps(
        {
            "business_context": business_context,
            "live_market_data": live_data_text,
            "instruction": (
                "Generate a comprehensive Signal Harvest Report based on "
                "the business context and live market data above."
            ),
        },
        indent=2,
    )


def _build_synthesis_input(
    business_context: str,
    signal_output: str,
    narrative_output: str = "",
    macro_output: str = "",
    competitive_output: str = "",
) -> str:
    """Assemble the Risk Synthesizer input from all available upstream outputs."""
    parts = [
        f"BUSINESS CONTEXT:\n{business_context}",
        f"SIGNAL HARVESTER OUTPUT:\n{signal_output}",
    ]
    if narrative_output:
        parts.append(f"NARRATIVE INTEL OUTPUT:\n{narrative_output}")
    if macro_output:
        parts.append(f"MACRO WATCHDOG OUTPUT:\n{macro_output}")
    if competitive_output:
        parts.append(f"COMPETITIVE INTEL OUTPUT:\n{competitive_output}")
    return "\n\n".join(parts)


def _format_live_data_as_text(live_data: dict) -> str:
    """
    Convert the get_all_live_data() payload into a compact text block
    suitable for LLM context injection (avoids raw JSON verbosity).
    """
    lines = ["[LIVE MARKET DATA — VIGIL DATA LAYER]"]

    pulse = live_data.get("pulse", {})
    vix_d = pulse.get("vix", {})
    spx_d = pulse.get("spx", {})
    tnx_d = pulse.get("treasury_10y", {})
    fg_d = pulse.get("fear_greed", {})

    lines.append(
        f"VIX: {vix_d.get('value', 'N/A')} ({vix_d.get('level', 'N/A')}) | "
        f"S&P500 7d: {spx_d.get('pct_7d', 'N/A')}% ({spx_d.get('trend', 'N/A')}) | "
        f"10Y Yield: {tnx_d.get('yield_pct', 'N/A')}% ({tnx_d.get('yield_curve', 'N/A')}) | "
        f"Regime: {pulse.get('market_regime', 'N/A')} | "
        f"Fear/Greed: {fg_d.get('score', 'N/A')}/100 ({fg_d.get('label', 'N/A')})"
    )

    sectors = live_data.get("sectors", {})
    if sectors:
        sector_parts = []
        for name, data in sectors.items():
            pct = data.get("pct_7d")
            pct_str = f"{pct:+.1f}%" if pct is not None else "N/A"
            sector_parts.append(f"{name}: {pct_str}")
        lines.append("SECTORS (7d): " + " | ".join(sector_parts))

    headlines = live_data.get("headlines", [])
    if headlines:
        lines.append("TOP HEADLINES:")
        for i, h in enumerate(headlines[:5], 1):
            sentiment = h.get("sentiment", "neutral").upper()
            title = h.get("title", "")
            source = h.get("source", "")
            lines.append(f"  {i}. [{sentiment}] {title} — {source}")

    lines.append(
        f"Data quality: {live_data.get('data_quality', 'UNKNOWN')} | "
        f"Fetched: {live_data.get('fetched_at', 'N/A')}"
    )
    lines.append("[END LIVE DATA]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MAIN FUNCTION: run_pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    user_message: str,
    profile: Optional[dict] = None,
    history: Optional[list] = None,
) -> dict:
    """
    Execute the full Vigil intelligence pipeline for a user message.

    STEP 1 — PREPARE:    assemble full context + live data
    STEP 2 — ORCHESTRATOR: classify intent + initial synthesis
    STEP 3 — ROUTE:       dispatch specialist agents per intent
    STEP 4 — BUILD RESULT: merge all outputs into structured dict

    Args:
        user_message: Raw natural language input from the user.
        profile:      Company profile dict (optional — generic mode without it).
        history:      Recent conversation as [{"role", "content"}, ...] (optional).

    Returns:
        Structured result dict with all pipeline outputs and metadata.
        The caller owns persistence (session store, conversation history).
    """
    pipeline_start = time.perf_counter()
    _reset_pipeline_statuses()

    # ── STEP 1: PREPARE ──────────────────────────────────────────────────────
    profile_was_used = has_sufficient_profile(profile)
    full_context = "\n\n".join(
        part for part in [
            get_profile_context_string(profile) if profile_was_used else "",
            _history_context_string(history),
        ] if part
    )
    enhanced_message = user_message

    live_data: dict = {}
    live_data_text = ""
    try:
        live_data = get_all_live_data()
        live_data_text = _format_live_data_as_text(live_data)
    except Exception as exc:
        logger.error("Live data fetch failed: %s — pipeline continues without it", exc)

    # Fix 2&3 — Context verification logging
    logger.info(
        "STEP 1 complete — profile_used: %s | full_context: %d chars | "
        "enhanced_msg: %d chars | live_data_quality: %s",
        profile_was_used,
        len(full_context),
        len(enhanced_message),
        live_data.get("data_quality", "UNKNOWN"),
    )
    if not profile_was_used:
        logger.debug("No profile active — pipeline will run in GENERIC market-analysis mode")
    else:
        logger.debug(
            "Profile context injected — company: %s",
            (profile or {}).get("name", "unknown"),
        )

    orchestrator_input = "\n\n".join(
        part for part in [
            full_context,
            f"USER REQUEST:\n{enhanced_message}",
            live_data_text,
        ] if part.strip()
    )

    # Fix 6 — Generic mode instruction when no profile is set
    if not profile_was_used:
        orchestrator_input += (
            "\n\n[MODE: GENERIC — No company profile is loaded. "
            "Provide general market intelligence, macro analysis, and investment insights. "
            "Do not assume any specific business context.]"
        )

    # Fix 7 — Investment keyword routing hint so Orchestrator routes INVESTMENT_QUERY
    _inv_kw = re.compile(
        r"\b(buy|sell|invest(ing|ment)?|ticker|stock|etf|crypto|bitcoin|ethereum|"
        r"nasdaq|s&p|gold|oil|should i|worth it|opportunity|trade|portfolio|"
        r"price target|outlook for|aapl|tsla|nvda|msft|amzn|goog|apple|nvidia|"
        r"amazon|google|short|long|rally|dip|bullish|bearish)\b",
        re.IGNORECASE,
    )
    if _inv_kw.search(user_message):
        orchestrator_input += (
            "\n\n[ROUTING HINT: The user message contains investment/market query keywords. "
            "Strongly consider routing this as INVESTMENT_QUERY to activate the Market Oracle.]"
        )
        logger.debug("Investment keyword detected → INVESTMENT_QUERY routing hint injected")

    # ── STEP 2: ORCHESTRATOR ─────────────────────────────────────────────────
    update_agent_status("orchestrator", "queued")
    orchestrator_prompt = _load_prompt("orchestrator")
    orchestrator_response = run_agent(
        "orchestrator",
        orchestrator_prompt,
        orchestrator_input,
        max_tokens=1500,  # only needs intent classification + brief
    )

    parsed_orch = parse_orchestrator_response(orchestrator_response)
    intent_type: str = parsed_orch.get("intent_type") or "FULL_BRIEFING"
    logger.info("Pipeline routing → intent: %s", intent_type)

    # ── STEP 3: ROUTE TO SPECIALISTS ─────────────────────────────────────────
    specialist_outputs: dict[str, str] = {}
    agents_activated: list[str] = ["orchestrator"]
    business_context = _build_business_context(profile, user_message)

    # ── INTENT: INVESTMENT_QUERY (2 agents) ──────────────────────────────────
    if intent_type == "INVESTMENT_QUERY":
        _set_agents_queued(["signal_harvester", "market_oracle"])
        _set_agents_idle(["narrative_intel", "macro_watchdog", "competitive_intel",
                          "risk_synthesizer", "strategy_commander"])

        signal_out = run_agent(
            "signal_harvester",
            _load_prompt("signal_harvester"),
            _build_signal_input(business_context, live_data_text),
            max_tokens=2000,
        )
        specialist_outputs["signal_harvester"] = signal_out
        agents_activated.append("signal_harvester")

        oracle_out = run_agent(
            "market_oracle",
            _load_prompt("market_oracle"),
            json.dumps({
                "user_question": user_message,
                "signal_harvester_data": signal_out[:2500],
            }, indent=2),
            max_tokens=2500,
        )
        specialist_outputs["market_oracle"] = oracle_out
        agents_activated.append("market_oracle")

    # ── INTENT: MACRO_FOCUS | DECISION_SUPPORT | SCENARIO (4 agents) ─────────
    elif intent_type in ("MACRO_FOCUS", "DECISION_SUPPORT", "SCENARIO"):
        _set_agents_queued(["signal_harvester", "macro_watchdog",
                            "risk_synthesizer", "strategy_commander"])
        _set_agents_idle(["narrative_intel", "competitive_intel", "market_oracle"])

        signal_out = run_agent(
            "signal_harvester",
            _load_prompt("signal_harvester"),
            _build_signal_input(business_context, live_data_text),
            max_tokens=2000,
        )
        specialist_outputs["signal_harvester"] = signal_out
        agents_activated.append("signal_harvester")

        macro_input = f"{business_context}\n\nSIGNAL HARVESTER OUTPUT:\n{signal_out}"
        if intent_type == "SCENARIO":
            macro_input += f"\n\n[SCENARIO BEING ANALYZED]: {user_message}"

        macro_out = run_agent(
            "macro_watchdog",
            _load_prompt("macro_watchdog"),
            macro_input,
            max_tokens=2500,
        )
        specialist_outputs["macro_watchdog"] = macro_out
        agents_activated.append("macro_watchdog")

        synth_input = _build_synthesis_input(
            business_context, signal_out, macro_output=macro_out
        )
        synth_out = run_agent(
            "risk_synthesizer",
            _load_prompt("risk_synthesizer"),
            synth_input,
            max_tokens=2500,
        )
        specialist_outputs["risk_synthesizer"] = synth_out
        agents_activated.append("risk_synthesizer")

        strat_input = f"{business_context}\n\nRISK SYNTHESIZER OUTPUT:\n{synth_out}"
        if intent_type == "DECISION_SUPPORT":
            strat_input += f"\n\n[SPECIFIC DECISION TO SUPPORT]: {user_message}"

        strat_out = run_agent(
            "strategy_commander",
            _load_prompt("strategy_commander"),
            strat_input,
            max_tokens=2000,
        )
        specialist_outputs["strategy_commander"] = strat_out
        agents_activated.append("strategy_commander")

    # ── INTENT: COMPETITIVE_FOCUS (4 agents) ─────────────────────────────────
    elif intent_type == "COMPETITIVE_FOCUS":
        _set_agents_queued(["signal_harvester", "competitive_intel",
                            "risk_synthesizer", "strategy_commander"])
        _set_agents_idle(["narrative_intel", "macro_watchdog", "market_oracle"])

        signal_out = run_agent(
            "signal_harvester",
            _load_prompt("signal_harvester"),
            _build_signal_input(business_context, live_data_text),
            max_tokens=2000,
        )
        specialist_outputs["signal_harvester"] = signal_out
        agents_activated.append("signal_harvester")

        comp_out = run_agent(
            "competitive_intel",
            _load_prompt("competitive_intel"),
            f"{business_context}\n\nSIGNAL HARVESTER OUTPUT:\n{signal_out}",
            max_tokens=2500,
        )
        specialist_outputs["competitive_intel"] = comp_out
        agents_activated.append("competitive_intel")

        synth_input = _build_synthesis_input(
            business_context, signal_out, competitive_output=comp_out
        )
        synth_out = run_agent(
            "risk_synthesizer",
            _load_prompt("risk_synthesizer"),
            synth_input,
            max_tokens=2500,
        )
        specialist_outputs["risk_synthesizer"] = synth_out
        agents_activated.append("risk_synthesizer")

        strat_out = run_agent(
            "strategy_commander",
            _load_prompt("strategy_commander"),
            f"{business_context}\n\nRISK SYNTHESIZER OUTPUT:\n{synth_out}",
            max_tokens=2000,
        )
        specialist_outputs["strategy_commander"] = strat_out
        agents_activated.append("strategy_commander")

    # ── INTENT: MARKET_PULSE (3 agents) ──────────────────────────────────────
    elif intent_type == "MARKET_PULSE":
        _set_agents_queued(["signal_harvester", "narrative_intel", "risk_synthesizer"])
        _set_agents_idle(["macro_watchdog", "competitive_intel",
                          "strategy_commander", "market_oracle"])

        signal_out = run_agent(
            "signal_harvester",
            _load_prompt("signal_harvester"),
            _build_signal_input(business_context, live_data_text),
            max_tokens=2000,
        )
        specialist_outputs["signal_harvester"] = signal_out
        agents_activated.append("signal_harvester")

        narrative_out = run_agent(
            "narrative_intel",
            _load_prompt("narrative_intel"),
            f"{business_context}\n\nSIGNAL HARVESTER OUTPUT:\n{signal_out}",
            max_tokens=2000,
        )
        specialist_outputs["narrative_intel"] = narrative_out
        agents_activated.append("narrative_intel")

        # Risk Synthesizer in brief mode — condensed output only
        brief_prompt = _load_prompt("risk_synthesizer")
        if brief_prompt:
            brief_prompt += (
                "\n\n[MODE: BRIEF — Produce only: verdict, composite score, "
                "top 2 risks, market regime summary. Max 400 words.]"
            )
        synth_input = _build_synthesis_input(
            business_context, signal_out, narrative_output=narrative_out
        )
        synth_out = run_agent(
            "risk_synthesizer",
            brief_prompt,
            synth_input,
            max_tokens=1200,
        )
        specialist_outputs["risk_synthesizer"] = synth_out
        agents_activated.append("risk_synthesizer")

    # ── INTENT: FULL_BRIEFING (all 7 specialists — default) ──────────────────
    else:
        # Wave 0 — queue all
        _set_agents_queued([
            "signal_harvester", "narrative_intel", "macro_watchdog",
            "competitive_intel", "risk_synthesizer", "strategy_commander",
        ])
        _set_agents_idle(["market_oracle"])

        # Wave 1 — Signal Harvester
        signal_out = run_agent(
            "signal_harvester",
            _load_prompt("signal_harvester"),
            _build_signal_input(business_context, live_data_text),
            max_tokens=2500,
        )
        specialist_outputs["signal_harvester"] = signal_out
        agents_activated.append("signal_harvester")

        # Wave 2 — Narrative + Macro + Competitive (PARALLEL — all share same input)
        wave2_tasks = {
            "narrative_intel":  (
                _load_prompt("narrative_intel"),
                f"{business_context}\n\nSIGNAL HARVESTER OUTPUT:\n{signal_out}",
                2000,
            ),
            "macro_watchdog": (
                _load_prompt("macro_watchdog"),
                f"{business_context}\n\nSIGNAL HARVESTER OUTPUT:\n{signal_out}",
                2000,
            ),
            "competitive_intel": (
                _load_prompt("competitive_intel"),
                f"{business_context}\n\nSIGNAL HARVESTER OUTPUT:\n{signal_out}",
                2000,
            ),
        }
        wave2_results: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(run_agent, name, prompt, content, tokens): name
                for name, (prompt, content, tokens) in wave2_tasks.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    wave2_results[name] = future.result()
                except Exception as exc:
                    logger.error("Wave 2 agent %s failed: %s", name, exc)
                    wave2_results[name] = f"[{name.upper()} UNAVAILABLE]"
        narrative_out  = wave2_results.get("narrative_intel", "")
        macro_out      = wave2_results.get("macro_watchdog", "")
        comp_out       = wave2_results.get("competitive_intel", "")
        for name in ("narrative_intel", "macro_watchdog", "competitive_intel"):
            specialist_outputs[name] = wave2_results[name]
            agents_activated.append(name)

        # Wave 3 — Risk Synthesizer (all 4 upstream outputs)
        synth_input = _build_synthesis_input(
            business_context,
            signal_out,
            narrative_output=narrative_out,
            macro_output=macro_out,
            competitive_output=comp_out,
        )
        synth_out = run_agent(
            "risk_synthesizer",
            _load_prompt("risk_synthesizer"),
            synth_input,
            max_tokens=2000,
        )
        specialist_outputs["risk_synthesizer"] = synth_out
        agents_activated.append("risk_synthesizer")

        # Wave 4 — Strategy Commander
        strat_out = run_agent(
            "strategy_commander",
            _load_prompt("strategy_commander"),
            f"{business_context}\n\nRISK SYNTHESIZER OUTPUT:\n{synth_out}",
            max_tokens=2000,
        )
        specialist_outputs["strategy_commander"] = strat_out
        agents_activated.append("strategy_commander")

    # ── STEP 4: BUILD RESULT ─────────────────────────────────────────────────
    total_time = round(time.perf_counter() - pipeline_start, 2)

    # Re-parse Risk Synthesizer output for authoritative structured fields
    synth_parsed: dict = {}
    if "risk_synthesizer" in specialist_outputs:
        synth_parsed = parse_orchestrator_response(
            specialist_outputs["risk_synthesizer"]
        )

    # Prefer Risk Synthesizer structured data; fall back to Orchestrator parse
    final_risk_score = synth_parsed.get("risk_score") or parsed_orch.get("risk_score")
    final_risk_tier  = synth_parsed.get("risk_tier")  or parsed_orch.get("risk_tier")
    final_verdict    = synth_parsed.get("verdict")    or parsed_orch.get("verdict")
    final_top_risks  = synth_parsed.get("top_risks")  or parsed_orch.get("top_risks") or []
    final_top_actions = (
        synth_parsed.get("top_actions") or
        parsed_orch.get("top_actions") or []
    )

    # Compile full_playbook from all specialist outputs (excluding market_oracle)
    playbook_parts = []
    for agent_key in [
        "signal_harvester", "narrative_intel", "macro_watchdog",
        "competitive_intel", "risk_synthesizer", "strategy_commander",
    ]:
        if agent_key in specialist_outputs:
            section_title = agent_key.upper().replace("_", " ")
            playbook_parts.append(
                f"{'━' * 60}\n{section_title}\n{'━' * 60}\n"
                f"{specialist_outputs[agent_key]}"
            )

    full_playbook = "\n\n".join(playbook_parts) or None

    # Determine primary display response
    primary_response = (
        orchestrator_response if orchestrator_response
        else (full_playbook or "Analysis unavailable.")
    )

    result: dict = {
        "intent_type":      intent_type,
        "agents_activated": agents_activated,
        "risk_score":       final_risk_score,
        "risk_tier":        final_risk_tier,
        "verdict":          final_verdict,
        "top_risks":        final_top_risks,
        "top_actions":      final_top_actions,
        "score_breakdown":  synth_parsed.get("score_breakdown") or {},
        "executive_brief":  parsed_orch.get("executive_brief"),
        "full_playbook":    full_playbook,
        "oracle_output":    specialist_outputs.get("market_oracle"),
        "market_pulse":     (
            specialist_outputs.get("signal_harvester") or
            parsed_orch.get("market_pulse_summary")
        ),
        "total_time_seconds": total_time,
        "profile_was_used":   profile_was_used,
        # Raw outputs for UI rendering (full response chain)
        "raw_orchestrator":    orchestrator_response,
        "specialist_outputs":  specialist_outputs,
        "primary_response":    primary_response,
    }

    # Persistence is the caller's responsibility (see main.py) — the engine
    # stays a pure function: (message, profile, history) → result dict.
    # STRIP_UPDATE_INTENTS tells callers which intents should repaint the
    # dashboard risk strip; Oracle/pulse runs preserve previous state.
    result["updates_risk_strip"] = intent_type in _STRIP_UPDATE_INTENTS

    logger.info(
        "Pipeline complete — intent: %s | agents: %d | risk_score: %s | time: %.2fs",
        intent_type,
        len(agents_activated),
        final_risk_score,
        total_time,
    )

    return result
