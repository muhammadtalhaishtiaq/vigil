"""
session_manager.py — Vigil Session & Profile Management
=========================================================
Pure-Python session store. No Streamlit dependency.
Sessions are keyed by session_id (UUID string) in an in-memory dict.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

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

_CONTEXT_PHRASES = {
    "our", "we", "us", "my company", "our company", "our business", "our risk",
    "our sector", "our market", "our competitors", "our funding", "our decisions",
    "my risk",
}

# ---------------------------------------------------------------------------
# In-memory session store: {session_id: {session_data}}
# ---------------------------------------------------------------------------
_SESSIONS: dict[str, dict] = {}


def _make_session_defaults() -> dict:
    return {
        "vigil_profile": None,
        "vigil_conversation": [],
        "vigil_auto_loaded": False,
        "vigil_last_risk_score": None,
        "vigil_last_agents_used": [],
        "vigil_last_top_risks": [],
        "vigil_last_score_breakdown": {},
        "vigil_last_top_actions": [],
        "vigil_last_verdict": None,
        "vigil_last_risk_tier": None,
        "agent_statuses": {a: "idle" for a in _ALL_AGENTS},
        "agent_elapsed": {a: None for a in _ALL_AGENTS},
    }


def _get_session(session_id: str) -> dict:
    """Get or create session data for a given session_id."""
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = _make_session_defaults()
    return _SESSIONS[session_id]


def create_session() -> str:
    """Create a new session and return its ID."""
    session_id = str(uuid.uuid4())
    _get_session(session_id)
    logger.info("New session created: %s", session_id)
    return session_id


# ============================================================================
# SECTION 1 — PROFILE MANAGEMENT
# ============================================================================

def _calculate_completeness(profile: dict) -> int:
    score = 0
    for field, pts in _REQUIRED_PROFILE_FIELDS.items():
        val = profile.get(field)
        if val and str(val).strip():
            score += pts
    for field, pts in _OPTIONAL_PROFILE_FIELDS.items():
        val = profile.get(field)
        if isinstance(val, (list, dict)):
            if val:
                score += pts
        elif val and str(val).strip():
            score += pts
    return min(score, 100)


def save_profile(session_id: str, profile: dict) -> None:
    """Persist a company profile to the session store."""
    sess = _get_session(session_id)
    enriched = dict(profile)
    # Normalize: accept both 'company_name' and 'name'
    if "company_name" in enriched and "name" not in enriched:
        enriched["name"] = enriched["company_name"]
    enriched["profile_completeness"] = _calculate_completeness(enriched)
    sess["vigil_profile"] = enriched
    logger.info(
        "Profile saved for session %s — company: %s | completeness: %d%%",
        session_id, enriched.get("name", "unnamed"), enriched["profile_completeness"],
    )


def load_profile(session_id: str) -> Optional[dict]:
    """Retrieve the current company profile from session store."""
    return _get_session(session_id).get("vigil_profile")


def get_profile_context_string(session_id: str) -> str:
    """Format the stored company profile as text for LLM prompts."""
    profile = load_profile(session_id)
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


def has_sufficient_profile(session_id: str) -> bool:
    """Return True if profile completeness >= 60."""
    profile = load_profile(session_id)
    if not profile:
        return False
    return profile.get("profile_completeness", 0) >= 60


# ============================================================================
# SECTION 2 — CONVERSATION MEMORY
# ============================================================================

def init_conversation(session_id: str) -> None:
    """Initialise session state (creates if not exists)."""
    _get_session(session_id)
    logger.debug("Session initialised: %s", session_id)


def add_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> None:
    """Append a message to the conversation history."""
    if metadata is None:
        metadata = {}
    sess = _get_session(session_id)

    message: dict = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents_used": metadata.get("agents_used", []),
        "risk_score": metadata.get("risk_score", None),
        "intent_type": metadata.get("intent_type", ""),
    }
    sess["vigil_conversation"].append(message)

    if role == "vigil":
        if metadata.get("risk_score") is not None:
            sess["vigil_last_risk_score"] = metadata["risk_score"]
        if metadata.get("agents_used"):
            sess["vigil_last_agents_used"] = metadata["agents_used"]
        if metadata.get("top_risks"):
            sess["vigil_last_top_risks"] = metadata["top_risks"]
        if metadata.get("top_actions"):
            sess["vigil_last_top_actions"] = metadata["top_actions"]
        if metadata.get("verdict") is not None:
            sess["vigil_last_verdict"] = metadata["verdict"]
        if metadata.get("risk_tier") is not None:
            sess["vigil_last_risk_tier"] = metadata["risk_tier"]

    logger.debug("Message added — role: %s | intent: %s", role, message.get("intent_type", ""))


def get_conversation_history(session_id: str) -> list:
    return _get_session(session_id).get("vigil_conversation", [])


def get_conversation_context_string(session_id: str, last_n: int = 6) -> str:
    history = get_conversation_history(session_id)
    if not history:
        return ""
    recent = history[-last_n:]
    exchange_count = max(1, last_n // 2)
    lines = [f"[CONVERSATION HISTORY — LAST {exchange_count} EXCHANGES]"]
    for msg in recent:
        role_label = "User" if msg["role"] == "user" else "Vigil"
        content = msg.get("content", "")
        if msg["role"] == "vigil" and len(content) > 200:
            content = content[:200].rstrip() + "…"
        lines.append(f"{role_label}: {content}")
    lines.append("[END HISTORY]")
    return "\n".join(lines)


def get_full_context_for_agent(session_id: str) -> str:
    parts: list[str] = []
    profile_ctx = get_profile_context_string(session_id)
    if profile_ctx:
        parts.append(profile_ctx)
    history_ctx = get_conversation_context_string(session_id, last_n=6)
    if history_ctx:
        parts.append(history_ctx)
    return "\n\n".join(parts)


# ============================================================================
# SECTION 3 — AUTO-LOAD LOGIC
# ============================================================================

def should_auto_load(session_id: str) -> bool:
    sess = _get_session(session_id)
    return (
        has_sufficient_profile(session_id)
        and not sess.get("vigil_auto_loaded", True)
        and len(get_conversation_history(session_id)) == 0
    )


def mark_auto_loaded(session_id: str) -> None:
    _get_session(session_id)["vigil_auto_loaded"] = True
    logger.info("Auto-load marked for session %s", session_id)


def get_auto_load_prompt(session_id: str) -> str:
    profile = load_profile(session_id)
    if not profile:
        return ""

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
        risk_focus = f"Focus on {risk_areas_raw[0]} and {risk_areas_raw[1]} as primary exposures."
    elif isinstance(risk_areas_raw, str) and risk_areas_raw.strip():
        risk_focus = f"Focus on {risk_areas_raw.strip()} as the primary exposure."
    else:
        risk_focus = "Identify and analyse the top risk exposures for this business profile."

    return (
        f"Give me a complete risk intelligence briefing for {company_name}. "
        f"We are a {stage} {sector} company based in {country} with {arr} ARR "
        f"and {runway} runway. Our most pressing decisions: {decisions}. {risk_focus}"
    )


# ============================================================================
# SECTION 4 — QUERY CONTEXT ENHANCEMENT
# ============================================================================

def enhance_query_with_context(session_id: str, user_message: str) -> str:
    lower = user_message.lower()
    has_context_phrase = any(phrase in lower for phrase in _CONTEXT_PHRASES)
    profile = load_profile(session_id)

    if has_context_phrase and profile:
        profile_ctx = get_profile_context_string(session_id)
        if profile_ctx:
            return f"{profile_ctx}\n\nUSER QUERY: {user_message}"
    elif has_context_phrase and get_conversation_history(session_id):
        recent_ctx = get_conversation_context_string(session_id, last_n=4)
        if recent_ctx:
            return f"{recent_ctx}\n\nUSER QUERY: {user_message}"
    return user_message


# ============================================================================
# SECTION 5 — AGENT STATUS
# ============================================================================

def update_agent_status(
    session_id: str,
    agent_name: str,
    status: str,
    elapsed: Optional[float] = None,
) -> None:
    valid_statuses = {"idle", "queued", "running", "complete", "error"}
    if status not in valid_statuses:
        logger.warning("Invalid status '%s' for agent '%s'", status, agent_name)
        return
    sess = _get_session(session_id)
    sess["agent_statuses"][agent_name] = status
    if elapsed is not None:
        sess["agent_elapsed"][agent_name] = round(elapsed, 2)


def get_agent_statuses(session_id: str) -> dict:
    sess = _get_session(session_id)
    return {
        "statuses": dict(sess["agent_statuses"]),
        "elapsed": dict(sess["agent_elapsed"]),
    }


def get_session_summary(session_id: str) -> dict:
    """Return a summary of the current session state for the frontend."""
    sess = _get_session(session_id)
    return {
        "session_id": session_id,
        "has_profile": sess["vigil_profile"] is not None,
        "profile_completeness": (sess["vigil_profile"] or {}).get("profile_completeness", 0),
        "company_name": (sess["vigil_profile"] or {}).get("name", ""),
        "conversation_length": len(sess["vigil_conversation"]),
        "last_risk_score": sess["vigil_last_risk_score"],
        "last_risk_tier": sess["vigil_last_risk_tier"],
        "last_verdict": sess["vigil_last_verdict"],
        "last_top_risks": sess["vigil_last_top_risks"],
        "last_top_actions": sess["vigil_last_top_actions"],
        "last_score_breakdown": sess["vigil_last_score_breakdown"],
        "agent_statuses": dict(sess["agent_statuses"]),
        "agent_elapsed": dict(sess["agent_elapsed"]),
    }
