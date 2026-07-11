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

import re
import json
import time
import logging
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# The agent runtime + registry live in agent_core (the "what an agent is").
# This module owns only the orchestration (the "how they work together").
from agent_core import (
    AGENTS,
    RISK_EVALUATOR,
    ALL_AGENTS as _ALL_AGENTS,
    AGENT_STATUSES,
    AGENT_ELAPSED,
    set_status_listener,
    update_agent_status,
    load_prompt as _load_prompt,
    invalidate_prompt_cache,
    get_client as _get_client,
    _get_secret,
)

# Importing tools attaches the scouts' data tools to the registry (see tools.py).
import tools  # noqa: F401,E402

# Observability: every agent step is recorded to a replayable JSONL trace.
import tracing  # noqa: E402
from agent_core import set_trace_listener  # noqa: E402

set_trace_listener(tracing.agent_step_listener)

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


# Agent runtime (models, LLM client, status, prompts) now lives in agent_core.
# `AGENTS`, `_ALL_AGENTS`, `_get_client`, `_get_secret`, `_load_prompt`, and the
# status functions are imported at the top of this module.

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
# FUNCTION: run_agent  (thin shim → the Agent registry in agent_core)
# ---------------------------------------------------------------------------

def run_agent(
    agent_name: str,
    system_prompt: str,  # noqa: ARG001 — kept for call-site compatibility; the
                         # Agent owns its instructions, so this arg is ignored.
    user_content: str,
    max_tokens: int = 2000,
) -> str:
    """
    Run one agent by name via the `AGENTS` registry in agent_core.

    Each agent already owns its own instructions/model/guardrails (see
    `agent_core.Agent`), so this shim just looks it up and executes. The
    `system_prompt` argument is retained so existing call sites keep working;
    it is intentionally ignored (the registry is the single source of truth).

    Returns the agent's text response, or a safe labelled placeholder on error.
    """
    agent = AGENTS.get(agent_name)
    if agent is None:
        logger.error("Unknown agent '%s' — no registry entry", agent_name)
        return f"[{agent_name.upper().replace('_', ' ')} UNAVAILABLE — not registered]"
    return agent.run(user_content, max_tokens=max_tokens)


# ---------------------------------------------------------------------------
# FUNCTION: parse_orchestrator_response
# ---------------------------------------------------------------------------

def extract_json_block(text: str) -> Optional[dict]:
    """
    Find and parse the first JSON object in an LLM response.

    Handles the ways models actually emit JSON: bare, inside ```json fences,
    or preceded/followed by prose. Returns None if nothing parseable is found —
    never raises. This is the structured seam between LLM output and code.
    """
    if not text:
        return None
    # Prefer a fenced block if present
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    candidates = [fence.group(1)] if fence else []
    # Fall back to the outermost brace span
    start = text.find("{")
    if start != -1:
        candidates.append(text[start : text.rfind("}") + 1])
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _clamp_score(value) -> Optional[int]:
    """Coerce a score-ish value to an int in [0, 100], or None."""
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return None


def _map_structured_response(obj: dict) -> dict:
    """
    Map a JSON contract object (Orchestrator or Risk Synthesizer) onto the
    canonical result dict. Field-by-field defensive: a malformed field degrades
    to its default instead of poisoning the rest.
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

    intent = obj.get("intent_type")
    if isinstance(intent, str) and re.fullmatch(r"[A-Z_]{4,30}", intent.strip()):
        result["intent_type"] = intent.strip()

    agents = obj.get("agents_needed") or obj.get("agents_to_activate")
    if isinstance(agents, list):
        result["agents_to_activate"] = [str(a).strip() for a in agents if str(a).strip()]

    result["risk_score"] = _clamp_score(obj.get("risk_score"))
    tier = obj.get("risk_tier")
    if isinstance(tier, str) and tier.strip():
        result["risk_tier"] = tier.strip().upper()

    for key in ("verdict", "executive_brief", "market_pulse_summary"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            result[key] = val.strip()

    risks = obj.get("top_risks")
    if isinstance(risks, list):
        for r in risks[:3]:
            if not isinstance(r, dict):
                continue
            name = str(r.get("name") or "").strip()
            if not name:
                continue
            result["top_risks"].append({
                "name": name,
                "probability": _clamp_score(r.get("probability")) or 50,
                "severity": str(r.get("severity") or "MEDIUM").strip().upper(),
                "detail": str(r.get("detail") or "").strip()[:300],
                "action_if_ignored": str(r.get("action_if_ignored") or "").strip(),
                "timeline": str(r.get("timeline") or "").strip(),
                "owner": str(r.get("owner") or "Leadership").strip(),
            })

    actions = obj.get("top_actions")
    if isinstance(actions, list):
        for a in actions[:3]:
            if not isinstance(a, dict):
                continue
            title = str(a.get("title") or "").strip()
            if not title:
                continue
            result["top_actions"].append({
                "title": title[:60],
                "detail": str(a.get("detail") or "").strip()[:300],
                "deadline": str(a.get("deadline") or "").strip(),
                "owner": str(a.get("owner") or "Leadership").strip(),
                "urgency": str(a.get("urgency") or "HIGH").strip().upper(),
            })

    breakdown = obj.get("score_breakdown")
    if isinstance(breakdown, dict):
        bd = {}
        for key in ("macro", "market", "narrative", "competitive"):
            score = _clamp_score(breakdown.get(key) or breakdown.get(key.upper()))
            if score is not None:
                bd[key] = score
        result["score_breakdown"] = bd

    oracle = obj.get("oracle_verdict")
    if isinstance(oracle, str) and oracle.strip().upper() in ("BUY", "WAIT", "CAUTION", "AVOID"):
        result["oracle_verdict"] = oracle.strip().upper()

    return result


def parse_orchestrator_response(response: str) -> dict:
    """
    Extract structured fields from an agent response.

    JSON-first: agents are instructed to answer with a JSON contract
    (see prompts/orchestrator.txt, prompts/risk_synthesizer.txt); when a valid
    JSON object is found it is mapped defensively onto the result dict. If no
    JSON parses — an older prompt, a chatty model, a truncated reply — the
    legacy markdown/regex path below still extracts what it can, so a format
    slip degrades quality instead of breaking the pipeline.

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

    # ── JSON-FIRST PATH (the structured contract) ────────────────────────────
    json_obj = extract_json_block(response)
    if json_obj is not None:
        mapped = _map_structured_response(json_obj)
        # Only trust the JSON path if it produced at least one meaningful field;
        # otherwise fall through to the legacy regex extraction.
        if any([mapped["intent_type"], mapped["risk_score"] is not None,
                mapped["verdict"], mapped["top_risks"], mapped["executive_brief"]]):
            return mapped

    # ── LEGACY MARKDOWN/REGEX PATH (fallback) ────────────────────────────────
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
                            "owner": "",         # don't invent an owner
                            "deadline": "",      # don't invent a deadline
                            "urgency": "",
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

    # No default intent here: an unclassified response stays None so the
    # pipeline's deterministic fallback (keyword routing → FULL_BRIEFING)
    # can make the routing decision instead of a silent parser default.
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


def _build_signal_input(business_context: str) -> str:
    """
    Assemble the Signal Harvester input.

    No market data is stuffed in here anymore — the Signal Harvester is a
    tool-using agent and pulls its own live data (macro pulse, sectors,
    headlines) via its tools. We just give it the business context and tell it
    to gather what's relevant.
    """
    return json.dumps(
        {
            "business_context": business_context,
            "instruction": (
                "Call your tools to gather the live market data relevant to this "
                "business context (macro pulse, sector performance, headlines), "
                "then produce the Signal Harvest Report."
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


# (Live market data is no longer pre-formatted for prompt injection — scout
# agents fetch it through their tools. See tools.py.)


def _wiki_context(max_chars: int = 6000) -> str:
    """
    Load the distilled knowledge notes from workspace/wiki/ (built by /ingest).

    These notes ground every run in the user's own documents. They are an INDEX:
    agents can still read the originals via the docs tools — per the wiki's
    lossy-summarization warning, summaries never replace sources. Empty string
    when no notes exist (the feature is fully optional).
    """
    try:
        from tools import workspace_dir
        wiki = workspace_dir("wiki")
        if not wiki.is_dir():
            return ""
        parts: list[str] = []
        total = 0
        for path in sorted(wiki.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                continue
            text = text[:1500]
            parts.append(f"--- {path.name} ---\n{text}")
            total += len(text)
            if total > max_chars:
                break
        if not parts:
            return ""
        return (
            "[COMPANY KNOWLEDGE BASE — distilled from the user's own documents "
            "via /ingest. Company facts here come from the user; verify market "
            "claims against live tools.]\n" + "\n\n".join(parts)
        )
    except Exception as exc:
        logger.warning("wiki context unavailable: %s", str(exc)[:80])
        return ""


def _gate_upstream(agent_name: str, output: str) -> str:
    """
    Inter-step error correction: validate one wave's output before it feeds the
    next (errors compound across chained steps — catch them at the seam, not at
    the end).

    A failed or degenerate output (unavailable placeholder, near-empty text) is
    replaced with an explicit, honest note so downstream agents analyze from
    the remaining context and say what's missing — instead of reasoning over
    garbage as if it were data.
    """
    text = (output or "").strip()
    is_placeholder = text.startswith("[") and "UNAVAILABLE" in text
    if text and not is_placeholder and len(text) >= 80:
        return output
    logger.warning(
        "gate: %s output unusable (%d chars%s) — downstream agents get an "
        "explicit data-gap note", agent_name, len(text),
        ", placeholder" if is_placeholder else "",
    )
    return (
        f"[{agent_name.upper().replace('_', ' ')} DATA UNAVAILABLE for this run. "
        "Analyze from the business context you have. State explicitly which "
        "market data is missing. Do NOT invent market figures.]"
    )


def _render_synthesis_text(parsed: dict) -> str:
    """
    Render the Risk Synthesizer's structured output as readable text.

    The synthesizer answers in JSON (its contract); this deterministic renderer
    is what humans see in the playbook. Presentation belongs to code, not to
    the model.
    """
    lines: list[str] = []
    score = parsed.get("risk_score")
    tier = parsed.get("risk_tier") or ""
    if score is not None:
        lines.append(f"RISK SCORE: {score}/100" + (f" ({tier})" if tier else ""))
    if parsed.get("verdict"):
        lines.append(f"VERDICT: {parsed['verdict']}")

    risks = parsed.get("top_risks") or []
    if risks:
        lines.append("\nTOP RISKS:")
        for i, r in enumerate(risks, 1):
            head = f"{i}. {r.get('name', 'Risk')}"
            probability = r.get("probability")
            if probability is not None:
                head += f" — probability {probability}%"
            if r.get("severity"):
                head += f", severity {r['severity']}"
            lines.append(head)
            for key, label in [("detail", "   "), ("action_if_ignored", "   If ignored: "),
                               ("timeline", "   Timeline: "), ("owner", "   Owner: ")]:
                if r.get(key):
                    lines.append(f"{label}{r[key]}")

    breakdown = parsed.get("score_breakdown") or {}
    if breakdown:
        parts = " | ".join(f"{k}: {v}" for k, v in breakdown.items())
        lines.append(f"\nSCORE BREAKDOWN: {parts}")

    return "\n".join(lines) or "(no structured synthesis available)"


def _evaluate_and_refine(synth_out: str, synth_input: str) -> str:
    """
    Optional evaluator-optimizer pass (Anthropic's 5th pattern).

    A cheap, near-deterministic critic (the Risk Evaluator) grades the Risk
    Synthesizer's briefing against a rubric. On a REVISE verdict, the synthesizer
    runs once more with the critic's feedback and that improved briefing is used.

    Gated by the VIGIL_ENABLE_EVALUATOR env var: it costs one (or two) extra LLM
    round trips, so it is off by default and turned on when quality matters more
    than latency. Never raises — any failure falls back to the original briefing.
    """
    if not _get_secret("VIGIL_ENABLE_EVALUATOR"):
        return synth_out

    try:
        verdict_text = RISK_EVALUATOR.run(
            f"UPSTREAM SIGNALS + CONTEXT:\n{synth_input}\n\n"
            f"RISK SYNTHESIZER BRIEFING TO GRADE:\n{synth_out}"
        )
        # JSON contract first; legacy EVAL_VERDICT format as fallback.
        eval_obj = extract_json_block(verdict_text) or {}
        verdict = str(eval_obj.get("verdict") or "").strip().upper()
        feedback = str(eval_obj.get("feedback") or "").strip()
        if verdict not in ("PASS", "REVISE"):
            m = re.search(r"EVAL_VERDICT[:\s\"]+(PASS|REVISE)", verdict_text, re.IGNORECASE)
            verdict = m.group(1).upper() if m else "PASS"
            fb = re.search(r"EVAL_FEEDBACK[:\s]+(.+)", verdict_text, re.IGNORECASE | re.DOTALL)
            feedback = (fb.group(1).strip() if fb else verdict_text.strip())

        if verdict != "REVISE":
            logger.info("Evaluator verdict: PASS — keeping original synthesis")
            return synth_out

        feedback = feedback[:1200]
        logger.info("Evaluator verdict: REVISE — re-running synthesizer with feedback")
        return run_agent(
            "risk_synthesizer",
            _load_prompt("risk_synthesizer"),
            f"{synth_input}\n\n[EVALUATOR FEEDBACK — revise your briefing to fix "
            f"these specific issues, keeping the same output format:]\n{feedback}",
            max_tokens=2000,
        )
    except Exception as exc:
        logger.error("Evaluator pass failed (%s) — using original synthesis", str(exc)[:80])
        return synth_out


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
    vigil_trace_company = (profile or {}).get("company_name") or (profile or {}).get("name") or ""
    tracing.recorder.start_run(user_message, profile_company=str(vigil_trace_company))

    # ── STEP 1: PREPARE ──────────────────────────────────────────────────────
    profile_was_used = has_sufficient_profile(profile)
    wiki_ctx = _wiki_context()
    full_context = "\n\n".join(
        part for part in [
            get_profile_context_string(profile) if profile_was_used else "",
            wiki_ctx,
            _history_context_string(history),
        ] if part
    )
    enhanced_message = user_message

    # No blanket market pre-fetch: the scout agents (Signal Harvester, Market
    # Oracle) pull the live data they need via their tools. This removes a slow
    # sequential yfinance sweep from every request and only fetches what the
    # query actually calls for.

    logger.info(
        "STEP 1 complete — profile_used: %s | full_context: %d chars | enhanced_msg: %d chars",
        profile_was_used,
        len(full_context),
        len(enhanced_message),
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
    # Deterministic routing backstop ("hard-code what you can"): when the
    # Orchestrator fails to classify — error, prose-only reply, parse miss —
    # a message that plainly matches investment keywords routes to the Oracle
    # by code, not by hoping the LLM obeyed the hint.
    _fallback_intent = "INVESTMENT_QUERY" if _inv_kw.search(user_message) else "FULL_BRIEFING"
    intent_type: str = parsed_orch.get("intent_type") or _fallback_intent
    logger.info("Pipeline routing → intent: %s", intent_type)

    # ── STEP 3: ROUTE TO SPECIALISTS ─────────────────────────────────────────
    specialist_outputs: dict[str, str] = {}
    agents_activated: list[str] = ["orchestrator"]
    business_context = _build_business_context(profile, user_message)
    if wiki_ctx:
        business_context += "\n\n" + wiki_ctx

    # ── INTENT: INVESTMENT_QUERY (2 agents) ──────────────────────────────────
    if intent_type == "INVESTMENT_QUERY":
        _set_agents_queued(["signal_harvester", "market_oracle"])
        _set_agents_idle(["narrative_intel", "macro_watchdog", "competitive_intel",
                          "risk_synthesizer", "strategy_commander"])

        signal_out = run_agent(
            "signal_harvester",
            _load_prompt("signal_harvester"),
            _build_signal_input(business_context),
            max_tokens=2000,
        )
        signal_out = _gate_upstream("signal_harvester", signal_out)
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
            _build_signal_input(business_context),
            max_tokens=2000,
        )
        signal_out = _gate_upstream("signal_harvester", signal_out)
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
            _build_signal_input(business_context),
            max_tokens=2000,
        )
        signal_out = _gate_upstream("signal_harvester", signal_out)
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
            _build_signal_input(business_context),
            max_tokens=2000,
        )
        signal_out = _gate_upstream("signal_harvester", signal_out)
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
            _build_signal_input(business_context),
            max_tokens=2500,
        )
        signal_out = _gate_upstream("signal_harvester", signal_out)
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
        # Pattern 5 — evaluator-optimizer: a critic grades the briefing and can
        # trigger one revision. Gated by VIGIL_ENABLE_EVALUATOR (off by default,
        # since it adds a round trip — a deliberate latency/quality trade-off).
        synth_out = _evaluate_and_refine(synth_out, synth_input)
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

    # Compile full_playbook from all specialist outputs (excluding market_oracle).
    # JSON-contract agents (risk_synthesizer) get their structured output rendered
    # to readable text — users never see raw JSON.
    playbook_parts = []
    for agent_key in [
        "signal_harvester", "narrative_intel", "macro_watchdog",
        "competitive_intel", "risk_synthesizer", "strategy_commander",
    ]:
        if agent_key in specialist_outputs:
            section_title = agent_key.upper().replace("_", " ")
            section_body = specialist_outputs[agent_key]
            if agent_key == "risk_synthesizer" and synth_parsed.get("risk_score") is not None:
                section_body = _render_synthesis_text(synth_parsed)
            playbook_parts.append(
                f"{'━' * 60}\n{section_title}\n{'━' * 60}\n"
                f"{section_body}"
            )

    full_playbook = "\n\n".join(playbook_parts) or None

    # Determine primary display response. The Orchestrator answers in JSON now,
    # so prefer its parsed narrative fields; raw text is the fallback for the
    # legacy/degraded path only.
    orch_narrative = "\n\n".join(
        part for part in [
            parsed_orch.get("executive_brief") or "",
            f"Verdict: {parsed_orch['verdict']}" if parsed_orch.get("verdict") else "",
        ] if part
    )
    primary_response = (
        orch_narrative
        or (orchestrator_response if not extract_json_block(orchestrator_response or "") else "")
        or full_playbook
        or "Analysis unavailable."
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

    # Persistence is the caller's responsibility (see the CLI/MCP front-ends) —
    # the engine stays a pure function: (message, profile, history) → result dict.
    # STRIP_UPDATE_INTENTS tells callers which intents represent a full risk
    # re-assessment; Oracle/pulse runs preserve previous state.
    result["updates_risk_strip"] = intent_type in _STRIP_UPDATE_INTENTS

    # Close the observability trace and surface it in the result.
    trace_info = tracing.recorder.end_run({
        "intent_type": intent_type,
        "risk_score": final_risk_score,
        "total_time": total_time,
    })
    result["trace_path"] = trace_info["path"]
    result["token_usage"] = trace_info["usage"]

    logger.info(
        "Pipeline complete — intent: %s | agents: %d | risk_score: %s | time: %.2fs | tokens: %d+%d",
        intent_type,
        len(agents_activated),
        final_risk_score,
        total_time,
        trace_info["usage"]["prompt"],
        trace_info["usage"]["completion"],
    )

    return result
