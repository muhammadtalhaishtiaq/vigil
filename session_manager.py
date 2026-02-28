"""
session_manager.py — Vigil Session & Profile Management
=========================================================
Handles all Streamlit session_state operations:
  - Company profile storage, scoring, and context injection
  - Conversation history management within a browser session
  - Auto-load logic (first-visit welcome briefing trigger)
  - Query context enhancement for agent calls

All state lives exclusively in st.session_state — no database, no files.
Every public function is safe to call before st.session_state is fully
initialised (init_conversation() should be called at app startup).
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

import streamlit as st

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [session_manager] %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# All 8 Vigil agent names (used to initialise agent status dicts)
_ALL_AGENTS: list[str] = [
    "orchestrator",
    "signal_harvester",
    "narrative_intel",
    "macro_watchdog",
    "competitive_intel",
    "risk_synthesizer",
    "strategy_commander",
    "market_oracle",
]

# Profile fields and their point values for completeness scoring
_REQUIRED_PROFILE_FIELDS: dict[str, int] = {
    "name": 15,
    "description": 15,
    "sector": 15,
    "country": 15,
}

_OPTIONAL_PROFILE_FIELDS: dict[str, int] = {
    "sub_sector": 5,
    "arr": 5,
    "stage": 5,
    "runway": 5,
    "funding": 5,
    "current_decisions": 5,
    "risk_areas": 5,
    "regulations": 5,
    "headcount": 5,
    "business_model": 5,
}

# Phrases that signal the user wants context-aware responses
_CONTEXT_PHRASES: set[str] = {
    "my company",
    "our business",
    "our company",
    "we are",
    "we're",
    "our sector",
    "our stage",
    "my situation",
    "my business",
    "our situation",
    "based on what we discussed",
    "using my data",
    "using our data",
    "given our profile",
    "for us",
    "for our",
    "in our case",
    "our arr",
    "our runway",
    "our risk",
    "my risk",
}

# ============================================================================
# SECTION 1 — PROFILE MANAGEMENT
# ============================================================================


def _calculate_completeness(profile: dict) -> int:
    """
    Compute a 0-100 completeness score for a company profile.

    Required fields contribute 15 pts each (4 fields = 60 pts max).
    Optional fields contribute 5 pts each (up to 10 fields = 50 pts max).
    Total is capped at 100.

    A field counts as present if its value is truthy and non-empty.
    """
    score = 0

    for field, pts in _REQUIRED_PROFILE_FIELDS.items():
        val = profile.get(field)
        if val and str(val).strip():
            score += pts

    for field, pts in _OPTIONAL_PROFILE_FIELDS.items():
        val = profile.get(field)
        # Lists/dicts count if non-empty; strings count if non-blank
        if isinstance(val, (list, dict)):
            if val:
                score += pts
        elif val and str(val).strip():
            score += pts

    return min(score, 100)


def save_profile(profile: dict) -> None:
    """
    Persist a company profile to session state and attach its completeness score.

    Args:
        profile: Dict containing any subset of the recognised profile fields.
                 Unknown keys are preserved without scoring.

    Side effects:
        - Sets st.session_state["vigil_profile"]
        - Attaches "profile_completeness" (int 0-100) to the stored dict
    """
    enriched = dict(profile)
    enriched["profile_completeness"] = _calculate_completeness(profile)
    st.session_state["vigil_profile"] = enriched
    logger.info(
        "Profile saved — company: %s | completeness: %d%%",
        profile.get("name", "unnamed"),
        enriched["profile_completeness"],
    )


def load_profile() -> Optional[dict]:
    """
    Retrieve the current company profile from session state.

    Returns:
        The profile dict (including ``profile_completeness`` key),
        or ``None`` if no profile has been saved yet.
    """
    return st.session_state.get("vigil_profile", None)


def get_profile_context_string() -> str:
    """
    Format the stored company profile as a clean text block suitable
    for prepending to LLM agent prompts.

    Returns:
        A formatted multi-line string when a profile exists,
        or an empty string when no profile is set.

    Example output::

        [COMPANY PROFILE — VIGIL CONTEXT]
        Company: Acme Corp | Sector: SaaS / DevTools
        Location: USA | ARR: $2M | Stage: Series A | Runway: 18 months
        WHAT THEY DO: Developer tooling platform for CI/CD automation.
        CURRENT DECISIONS: Expand into EU market, hire 10 engineers
        KEY RISK EXPOSURES: Interest rates, USD/EUR FX, talent market
        ACTIVE REGULATIONS: GDPR, SOC2
        [END PROFILE]
    """
    profile = load_profile()
    if not profile:
        return ""

    def _fmt(key: str, fallback: str = "Not specified") -> str:
        val = profile.get(key)
        if isinstance(val, list):
            return ", ".join(str(v) for v in val) if val else fallback
        return str(val).strip() if val and str(val).strip() else fallback

    lines = [
        "[COMPANY PROFILE — VIGIL CONTEXT]",
        f"Company: {_fmt('name')} | Sector: {_fmt('sector')}"
        + (f" / {_fmt('sub_sector')}" if profile.get("sub_sector") else ""),
        f"Location: {_fmt('country')} | ARR: {_fmt('arr')} "
        f"| Stage: {_fmt('stage')} | Runway: {_fmt('runway')}",
        f"WHAT THEY DO: {_fmt('description')}",
        f"CURRENT DECISIONS: {_fmt('current_decisions')}",
        f"KEY RISK EXPOSURES: {_fmt('risk_areas')}",
        f"ACTIVE REGULATIONS: {_fmt('regulations')}",
        "[END PROFILE]",
    ]
    return "\n".join(lines)


def has_sufficient_profile() -> bool:
    """
    Return ``True`` if the stored profile has a completeness score >= 60.

    A score of 60 guarantees all four required fields are present (60 pts),
    which is the minimum for the Orchestrator to produce tailored analysis.
    """
    profile = load_profile()
    if not profile:
        return False
    return profile.get("profile_completeness", 0) >= 60


# ============================================================================
# SECTION 2 — CONVERSATION MEMORY
# ============================================================================


def init_conversation() -> None:
    """
    Initialise all Vigil-related session state keys on first load.

    Safe to call on every Streamlit rerun — existing keys are never
    overwritten, so state persists across reruns within the same session.

    Keys initialised:
        vigil_conversation      list[dict]  — full message history
        vigil_session_id        str         — UUID for this browser session
        vigil_auto_loaded       bool        — welcome briefing fired flag
        vigil_last_risk_score   int|None    — latest composite risk score
        vigil_last_agents_used  list[str]   — agents fired in last query
        vigil_last_top_risks    list[dict]  — top 3 risks (for strip display)
        vigil_last_top_actions  list[dict]  — top 3 actions (for strip display)
        vigil_last_verdict      str|None    — one-line verdict (for verdict bar)
        vigil_last_risk_tier    str|None    — tier label e.g. "RED 🔴"
        agent_statuses          dict        — per-agent status: idle/running/done/error
        agent_elapsed           dict        — per-agent elapsed seconds or None
    """
    defaults: dict = {
        "vigil_conversation": [],
        "vigil_session_id": str(uuid.uuid4()),
        "vigil_auto_loaded": False,
        "vigil_last_risk_score": None,
        "vigil_last_agents_used": [],
        "vigil_last_top_risks": [],
        "vigil_last_score_breakdown": {},
        "vigil_last_top_actions": [],
        "vigil_last_verdict": None,
        "vigil_last_risk_tier": None,
        "agent_statuses": {agent: "idle" for agent in _ALL_AGENTS},
        "agent_elapsed": {agent: None for agent in _ALL_AGENTS},
    }
    for key, default_val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_val

    logger.debug("Session state initialised — session_id: %s", st.session_state["vigil_session_id"])


def add_message(
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> None:
    """
    Append a message to the conversation history.

    Args:
        role:     "user" or "vigil"
        content:  Full message text
        metadata: Optional dict with any of:
                    agents_used  (list[str])
                    risk_score   (int|None)
                    intent_type  (str)
                    top_risks    (list[dict])
                    top_actions  (list[dict])
                    verdict      (str|None)
                    risk_tier    (str|None)

    Side effects:
        - Appends structured message to st.session_state["vigil_conversation"]
        - If role=="vigil" and metadata includes risk/verdict fields,
          updates the latest pinned dashboard values in session state.
    """
    if metadata is None:
        metadata = {}

    message: dict = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents_used": metadata.get("agents_used", []),
        "risk_score": metadata.get("risk_score", None),
        "intent_type": metadata.get("intent_type", ""),
    }

    # Ensure list exists (defensive — init_conversation may not have been called)
    if "vigil_conversation" not in st.session_state:
        st.session_state["vigil_conversation"] = []

    st.session_state["vigil_conversation"].append(message)

    # Update pinned dashboard state whenever Vigil responds with risk data
    if role == "vigil":
        if metadata.get("risk_score") is not None:
            st.session_state["vigil_last_risk_score"] = metadata["risk_score"]
        if metadata.get("agents_used"):
            st.session_state["vigil_last_agents_used"] = metadata["agents_used"]
        if metadata.get("top_risks"):
            st.session_state["vigil_last_top_risks"] = metadata["top_risks"]
        if metadata.get("top_actions"):
            st.session_state["vigil_last_top_actions"] = metadata["top_actions"]
        if metadata.get("verdict") is not None:
            st.session_state["vigil_last_verdict"] = metadata["verdict"]
        if metadata.get("risk_tier") is not None:
            st.session_state["vigil_last_risk_tier"] = metadata["risk_tier"]

    logger.debug("Message added — role: %s | intent: %s", role, message.get("intent_type", ""))


def get_conversation_history() -> list:
    """
    Return the full conversation history for the current session.

    Returns:
        List of message dicts (may be empty on first load).
    """
    return st.session_state.get("vigil_conversation", [])


def get_conversation_context_string(last_n: int = 6) -> str:
    """
    Format the last N conversation exchanges as a text block for
    injection into agent prompts.

    Each Vigil response is truncated to 200 characters to keep the
    context block concise without losing intent signals.

    Args:
        last_n: Number of recent messages (user + vigil pairs) to include.
                Default is 6 (3 full exchanges).

    Returns:
        Formatted multi-line string, or empty string if no history.

    Example output::

        [CONVERSATION HISTORY — LAST 3 EXCHANGES]
        User: What is our exposure to rising interest rates?
        Vigil: Your SaaS business faces a 23% increase in CAC due to...
        User: What should we do about pricing?
        Vigil: Recommend a 12-15% price increase on annual contracts by...
        [END HISTORY]
    """
    history = get_conversation_history()
    if not history:
        return ""

    recent = history[-last_n:]
    exchange_count = max(1, last_n // 2)
    lines = [f"[CONVERSATION HISTORY — LAST {exchange_count} EXCHANGES]"]

    for msg in recent:
        role_label = "User" if msg["role"] == "user" else "Vigil"
        content = msg.get("content", "")
        # Truncate Vigil responses to keep context block concise
        if msg["role"] == "vigil" and len(content) > 200:
            content = content[:200].rstrip() + "…"
        lines.append(f"{role_label}: {content}")

    lines.append("[END HISTORY]")
    return "\n".join(lines)


def get_full_context_for_agent() -> str:
    """
    Combine company profile context and conversation history into a
    single string prepended to every Orchestrator call.

    Returns:
        Combined context string. Empty sections are omitted gracefully.
        Returns empty string if neither profile nor history exists.
    """
    parts: list[str] = []

    profile_ctx = get_profile_context_string()
    if profile_ctx:
        parts.append(profile_ctx)

    history_ctx = get_conversation_context_string(last_n=6)
    if history_ctx:
        parts.append(history_ctx)

    return "\n\n".join(parts)


# ============================================================================
# SECTION 3 — AUTO-LOAD LOGIC
# ============================================================================


def should_auto_load() -> bool:
    """
    Determine whether to automatically trigger a welcome risk briefing.

    Returns ``True`` only when ALL three conditions hold:
        1. The company profile has completeness >= 60 (sufficient context)
        2. The auto-load welcome briefing has not yet fired this session
        3. The conversation history is empty (this is the user's first message)

    This prevents re-triggering on every rerun and avoids auto-loading
    mid-conversation after a page refresh.
    """
    return (
        has_sufficient_profile()
        and not st.session_state.get("vigil_auto_loaded", True)
        and len(get_conversation_history()) == 0
    )


def mark_auto_loaded() -> None:
    """
    Mark the welcome briefing as having fired for this session.

    Must be called immediately after dispatching the auto-load prompt
    to prevent repeated triggers on Streamlit reruns.
    """
    st.session_state["vigil_auto_loaded"] = True
    logger.info("Auto-load marked as fired for session %s", st.session_state.get("vigil_session_id", "unknown"))


def get_auto_load_prompt(profile: dict) -> str:
    """
    Generate the automatic first-visit risk briefing query from a profile.

    The prompt is structured to trigger FULL_BRIEFING intent in the
    Orchestrator, ensuring all specialist agents are activated.

    Args:
        profile: The company profile dict (from load_profile()).

    Returns:
        A fully-formed natural language query string pre-loaded with
        company context to kick off the welcome briefing pipeline.
    """
    def _get(key: str, fallback: str = "unspecified") -> str:
        val = profile.get(key)
        if isinstance(val, list):
            return ", ".join(str(v) for v in val) if val else fallback
        return str(val).strip() if val and str(val).strip() else fallback

    company_name = _get("name")
    stage = _get("stage")
    sector = _get("sector")
    country = _get("country")
    arr = _get("arr")
    runway = _get("runway")
    decisions = _get("current_decisions")

    risk_areas_raw = profile.get("risk_areas")
    if isinstance(risk_areas_raw, list) and len(risk_areas_raw) >= 2:
        primary_risk = str(risk_areas_raw[0])
        secondary_risk = str(risk_areas_raw[1])
        risk_focus = f"Focus on {primary_risk} and {secondary_risk} as primary exposures."
    elif isinstance(risk_areas_raw, str) and risk_areas_raw.strip():
        risk_focus = f"Focus on {risk_areas_raw.strip()} as the primary exposure."
    else:
        risk_focus = "Identify and analyse the top risk exposures for this business profile."

    prompt = (
        f"Give me a complete risk intelligence briefing for {company_name}. "
        f"We are a {stage} {sector} company based in {country} with {arr} ARR "
        f"and {runway} runway. "
        f"Our most pressing decisions: {decisions}. "
        f"{risk_focus}"
    )

    logger.info("Auto-load prompt generated for company: %s", company_name)
    return prompt


# ============================================================================
# SECTION 4 — QUERY CONTEXT ENHANCEMENT
# ============================================================================


def enhance_query_with_context(user_message: str) -> str:
    """
    Enrich a user query with company profile or conversation context
    when context-dependent phrases are detected.

    Detection logic (case-insensitive):
        - Checks for any phrase from _CONTEXT_PHRASES in the message.

    Branch logic:
        A. Context phrase + profile exists → prepend full profile block
        B. Context phrase + no profile → append instruction to infer from history
        C. No context phrase → return message unchanged

    Args:
        user_message: The raw user input string.

    Returns:
        Enhanced message string ready for Orchestrator dispatch.
    """
    lowered = user_message.lower()
    has_context_phrase = any(phrase in lowered for phrase in _CONTEXT_PHRASES)

    if not has_context_phrase:
        # Branch C — no enhancement needed
        return user_message

    profile = load_profile()

    if profile and has_sufficient_profile():
        # Branch A — inject full profile context ahead of the query
        profile_block = get_profile_context_string()
        enhanced = (
            f"{profile_block}\n\n"
            f"USER QUERY (answer in context of the company profile above):\n"
            f"{user_message}"
        )
        logger.debug("Query enhanced with profile context (%d chars)", len(enhanced))
        return enhanced

    else:
        # Branch B — no profile; instruct agent to infer from conversation history
        history_note = (
            "\n\n[NOTE: The user is referring to their company/situation but "
            "no company profile has been saved. Infer business context from "
            "the conversation history above. If insufficient context exists, "
            "ask ONE clarifying question before proceeding with analysis.]"
        )
        enhanced = user_message + history_note
        logger.debug("Query enhanced with no-profile inference note")
        return enhanced
