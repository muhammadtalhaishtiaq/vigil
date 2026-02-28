"""
storage.py — File-based Session Persistence for Vigil
=======================================================
Stores each session as a JSON file under SESSIONS_DIR.
Sessions are keyed by UUID (the same vigil_session_id used in session_manager).

Usage:
    from storage import persist_session, restore_session, session_exists

Design decisions:
  - Atomic writes: write to .tmp then rename to prevent corrupt files.
  - Sessions older than SESSION_TTL_DAYS are silently ignored (stale GC).
  - Only vigil-owned keys are persisted (profile, conversation, flags, scores).
"""

import os
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "sessions")
SESSION_TTL_DAYS = 30  # sessions older than this are ignored

# Keys we persist (everything else in st.session_state is ephemeral UI noise)
_PERSIST_KEYS = [
    "vigil_session_id",
    "vigil_profile",
    "vigil_conversation",
    "vigil_auto_loaded",
    "vigil_last_risk_score",
    "vigil_last_agents_used",
    "vigil_last_top_risks",
    "vigil_last_score_breakdown",
    "vigil_last_top_actions",
    "vigil_last_verdict",
    "vigil_last_risk_tier",
    "agent_statuses",
    "agent_elapsed",
    "vigil_specialist_outputs",
]

os.makedirs(SESSIONS_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def persist_session(session_id: str, state: dict) -> None:
    """
    Write a subset of session state to disk as JSON.

    Uses a tmp-then-rename pattern to prevent partial writes.

    Args:
        session_id: UUID string used as the filename stem.
        state:      Dict (typically from st.session_state) to persist.
                    Only keys in _PERSIST_KEYS are written.
    """
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    tmp_path = path + ".tmp"

    payload = {k: state[k] for k in _PERSIST_KEYS if k in state}
    payload["_persisted_at"] = time.time()

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, default=str, ensure_ascii=False)
        os.replace(tmp_path, path)
        logger.debug("Session persisted: %s (%d keys)", session_id, len(payload))
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to persist session %s: %s", session_id, exc)


def restore_session(session_id: str) -> Optional[dict]:
    """
    Load session data from disk.

    Returns None when:
        - File doesn't exist
        - File is unreadable / corrupt JSON
        - Session is older than SESSION_TTL_DAYS

    Args:
        session_id: UUID string to look up.

    Returns:
        Dict of persisted state keys, or None.
    """
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        return None

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read session file %s: %s", path, exc)
        return None

    # TTL check
    persisted_at = data.get("_persisted_at", 0)
    age_days = (time.time() - persisted_at) / 86400
    if age_days > SESSION_TTL_DAYS:
        logger.info("Session %s expired (%.1f days old) — starting fresh", session_id, age_days)
        return None

    logger.info("Session restored: %s (%.1f days old, %d msgs)",
                session_id, age_days,
                len(data.get("vigil_conversation", [])))
    return data


def session_exists(session_id: str) -> bool:
    """Return True if a (non-expired) session file exists for session_id."""
    if not session_id:
        return False
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        age_days = (time.time() - data.get("_persisted_at", 0)) / 86400
        return age_days <= SESSION_TTL_DAYS
    except Exception:  # noqa: BLE001
        return False


def delete_session(session_id: str) -> None:
    """Remove a session file from disk (e.g. on explicit logout)."""
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    try:
        os.remove(path)
        logger.info("Session deleted: %s", session_id)
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to delete session %s: %s", session_id, exc)
