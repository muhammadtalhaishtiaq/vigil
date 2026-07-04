"""
main.py — Vigil FastAPI App (single process)
Serves the HTML frontend, manages sessions, and runs the 8-agent
intelligence engine (agent_pipeline.py) in-process — no microservices.
"""
import os
import uuid
import secrets
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

from agent_pipeline import run_pipeline, set_status_listener
from data_layer import (
    get_all_live_data,
    get_market_pulse as fetch_market_pulse,
    get_sector_performance as fetch_sector_performance,
    get_live_headlines as fetch_live_headlines
)
from session_store import store as SESSION_STORE

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
)
logger = logging.getLogger("vigil-main")

# FastAPI app
app = FastAPI(
    title="Vigil Risk Intelligence Platform",
    version="2.0.0",
    description="Autonomous financial risk intelligence powered by 8 AI agents"
)

# Middleware — frontend is served same-origin, so no CORS needed.
# SECRET_KEY signs the session cookie; without one set, an ephemeral key is
# generated (sessions reset on restart — fine for local/demo use).
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY") or secrets.token_hex(32)
)

# Mount static files (CSS, JS, images, etc.)
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
    logger.info(f"Static files mounted from: {static_path}")
else:
    logger.warning(f"Static directory not found at {static_path}")

# Session store with file persistence
SESSIONS = SESSION_STORE.sessions

# Active WebSocket connections
active_connections: Dict[str, WebSocket] = {}

# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

def _ensure_session_defaults(session: dict) -> dict:
    """Ensure required session keys exist for backward compatibility."""
    session.setdefault("profile", None)
    session.setdefault("conversation", [])
    session.setdefault("dashboard_cache", {})
    session.setdefault("updated_at", datetime.utcnow().isoformat())
    session.setdefault("last_risk_score", None)
    session.setdefault("last_risk_tier", None)
    session.setdefault("last_verdict", None)
    session.setdefault("last_top_risks", [])
    session.setdefault("last_top_actions", [])
    session.setdefault("last_score_breakdown", {})
    session.setdefault("last_playbook", None)
    session.setdefault("last_oracle_output", None)
    session.setdefault("agent_statuses", {
        "orchestrator": "idle",
        "signal_harvester": "idle",
        "narrative_intel": "idle",
        "macro_watchdog": "idle",
        "competitive_intel": "idle",
        "risk_synthesizer": "idle",
        "strategy_commander": "idle",
        "market_oracle": "idle",
    })
    return session


def _cache_dashboard_block(session: dict, key: str, data: dict | list):
    """Store dashboard API payloads in session for refresh persistence."""
    cache = session.setdefault("dashboard_cache", {})
    cache[key] = data
    cache["updated_at"] = datetime.utcnow().isoformat()
    session["updated_at"] = cache["updated_at"]
    SESSION_STORE.save()


def _append_conversation(session: dict, entry: dict, max_items: int = 200):
    """Append chat message to session history with a safe cap."""
    conv = session.setdefault("conversation", [])
    conv.append(entry)
    if len(conv) > max_items:
        del conv[:-max_items]
    session["updated_at"] = datetime.utcnow().isoformat()
    SESSION_STORE.save()


def _has_user_profile(session: dict) -> bool:
    """Hard rule: company data must be user-provided."""
    profile = session.get("profile") or {}
    if not isinstance(profile, dict):
        return False
    return bool(str(profile.get("company_name", "")).strip())


def _normalize_profile(profile: Optional[dict]) -> dict:
    """Normalize profile keys for downstream consumers."""
    if not isinstance(profile, dict):
        return {}
    normalized = dict(profile)
    if not normalized.get("industry") and normalized.get("sector"):
        normalized["industry"] = normalized.get("sector")
    if not normalized.get("location") and normalized.get("country"):
        normalized["location"] = normalized.get("country")
    if not normalized.get("employees") and normalized.get("team_size"):
        normalized["employees"] = normalized.get("team_size")
    if not normalized.get("arr_range") and normalized.get("arr"):
        normalized["arr_range"] = normalized.get("arr")
    if not normalized.get("funding_stage") and normalized.get("stage"):
        normalized["funding_stage"] = normalized.get("stage")
    return normalized


def _extract_clean_verdict(raw_message: str) -> str:
    """
    Extract clean verdict/answer from raw agent output.
    Removes ALL agent metadata and formatting.
    """
    if not raw_message:
        return "No response generated."
    
    # Step 1: Remove everything before "THE VERDICT" or "THE HONEST ANSWER"
    if "THE VERDICT" in raw_message:
        raw_message = raw_message.split("THE VERDICT", 1)[1]
    elif "THE HONEST ANSWER" in raw_message:
        raw_message = raw_message.split("THE HONEST ANSWER", 1)[1]
    
    # Step 2: Remove everything after "WHAT THE MARKET IS SAYING" or similar sections
    end_markers = ["WHAT THE MARKET IS SAYING", "WHAT SMART MONEY IS DOING", 
                   "THE BEAR CASE", "THE BULL CASE", "CRITICAL BRIEF", 
                   "TOP 3 RISKS", "YOUR NEXT 3 MOVES", "MARKET PULSE", 
                   "GO DEEPER", "This is market intelligence"]
    
    for marker in end_markers:
        if marker in raw_message:
            raw_message = raw_message.split(marker)[0]
            break
    
    # Step 3: Clean line by line
    lines = raw_message.split("\n")
    clean_lines = []
    
    for line in lines:
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
        
        # Skip lines with metadata markers
        skip_markers = [
            "—", "##", "**", "*Vigil", "UTC", "Agents activated",
            "MARKET ORACLE", "Question:", "Verdict:", "CAUTION", "⚠️",
            "Powered by", "Analysis by", "###", "TIER", "ORANGE", "RED"
        ]
        
        if any(marker in line for marker in skip_markers):
            continue
        
        # Skip lines that are just symbols
        if all(c in "—#*⚠️🔴🟠🟡🟢⚡" for c in line.replace(" ", "")):
            continue
        
        # Remove remaining formatting
        line = line.replace("**", "").replace("*", "").replace("—", "")
        line = line.replace("⚠️", "").replace("🔴", "").replace("🟠", "")
        line = line.strip()
        
        if line and len(line) > 10:  # Must have meaningful content
            clean_lines.append(line)
    
    # Step 4: Join and limit length
    clean_text = " ".join(clean_lines)
    
    # Step 5: Extract first 2-3 sentences (up to 400 chars)
    sentences = []
    current = ""
    
    for char in clean_text:
        current += char
        if char in ".!?" and len(current) > 50:
            sentences.append(current.strip())
            current = ""
            if len(sentences) >= 3:
                break
    
    if current:
        sentences.append(current.strip())
    
    result = " ".join(sentences[:3])
    
    # Fallback if nothing extracted
    if not result or len(result) < 20:
        # Try to find any paragraph between markers
        parts = raw_message.split(".")
        for part in parts:
            if len(part.strip()) > 50 and not any(m in part for m in skip_markers):
                result = part.strip() + "."
                break
    
    return result if result else (
        "Couldn't extract a summary from this analysis — open the full playbook for the complete output."
    )

def init_session(session_id: str) -> dict:
    """Initialize a new session with default values (like st.session_state)"""
    SESSIONS[session_id] = {
        "session_id": session_id,
        "created_at": datetime.utcnow().isoformat(),
        "profile": None,
        "conversation": [],
        "dashboard_cache": {},
        "last_risk_score": None,
        "last_risk_tier": None,
        "last_verdict": None,
        "last_top_risks": [],
        "last_top_actions": [],
        "last_playbook": None,
        "last_oracle_output": None,
        "agent_statuses": {
            "orchestrator": "idle",
            "signal_harvester": "idle",
            "narrative_intel": "idle",
            "macro_watchdog": "idle",
            "competitive_intel": "idle",
            "risk_synthesizer": "idle",
            "strategy_commander": "idle",
            "market_oracle": "idle",
        },
        "theme": "dark",
        "auto_loaded": False,
        "completed_actions": [],
        "updated_at": datetime.utcnow().isoformat(),
    }
    SESSION_STORE.save()
    logger.info(f"Session initialized: {session_id}")
    return SESSIONS[session_id]


def get_session(request: Request) -> dict:
    """Get or create session for request"""
    session_id = request.session.get("session_id")
    
    if not session_id or session_id not in SESSIONS:
        session_id = str(uuid.uuid4())
        request.session["session_id"] = session_id
        return init_session(session_id)
    
    return _ensure_session_defaults(SESSIONS[session_id])


async def broadcast_status(session_id: str):
    """Send agent status updates via WebSocket if connected"""
    if session_id in active_connections and session_id in SESSIONS:
        try:
            ws = active_connections[session_id]
            await ws.send_json({
                "type": "agent_status",
                "data": SESSIONS[session_id]["agent_statuses"]
            })
        except Exception as e:
            logger.error(f"WebSocket broadcast error: {e}")


# ============================================================================
# HTML PAGE SERVING
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_landing():
    """Serve landing page"""
    html_path = Path(__file__).parent / "vigil-landing.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Landing page not found")
    return FileResponse(html_path)


@app.get("/profile", response_class=HTMLResponse)
async def serve_profile():
    """Serve profile setup page"""
    html_path = Path(__file__).parent / "vigil-profile.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Profile page not found")
    return FileResponse(html_path)


@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve main dashboard"""
    html_path = Path(__file__).parent / "vigil-dashboard-v3.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(html_path)


# ============================================================================
# SESSION API ENDPOINTS
# ============================================================================

@app.post("/api/session/init")
async def session_init(request: Request):
    """Initialize session (called on page load)"""
    session = get_session(request)
    return {
        "status": "ok",
        "session_id": session["session_id"],
        "has_profile": bool(session.get("profile")),
        "conversation_count": len(session.get("conversation", [])),
        "updated_at": session.get("updated_at")
    }


@app.get("/api/session/data")
async def get_session_data(request: Request):
    """Get all session data (like st.session_state)"""
    session = get_session(request)
    return session


@app.get("/api/session/dashboard")
async def get_dashboard_session_state(request: Request):
    """Get persisted dashboard snapshot for refresh restore."""
    session = get_session(request)
    return {
        "profile": session.get("profile"),
        "dashboard_cache": session.get("dashboard_cache", {}),
        "updated_at": session.get("updated_at")
    }


@app.get("/api/chat/history")
async def get_chat_history(request: Request):
    """Get conversation history for current session."""
    session = get_session(request)
    return {
        "conversation": session.get("conversation", []),
        "count": len(session.get("conversation", [])),
        "updated_at": session.get("updated_at")
    }


@app.post("/api/session/update")
async def update_session_data(request: Request, data: dict):
    """Update session data"""
    session = get_session(request)
    session.update(data)
    return {"status": "ok"}


@app.post("/api/session/reset")
async def reset_session_data(request: Request):
    """Reset current session state to empty defaults."""
    old_session_id = request.session.get("session_id")
    if old_session_id:
        SESSION_STORE.delete(old_session_id)

    new_session_id = str(uuid.uuid4())
    request.session["session_id"] = new_session_id
    session = init_session(new_session_id)

    return {
        "status": "reset",
        "old_session_id": old_session_id,
        "session_id": session["session_id"]
    }


# ============================================================================
# PROFILE API
# ============================================================================

@app.post("/api/profile/save")
async def save_profile(request: Request, profile: dict):
    """Save company profile"""
    session = get_session(request)
    normalized = _normalize_profile(profile)
    session["profile"] = normalized
    session["auto_loaded"] = False  # Reset auto-load flag
    _cache_dashboard_block(session, "profile", normalized)
    SESSION_STORE.save()  # Explicit save for critical data
    logger.info(f"Profile saved for session {session['session_id']}: {normalized.get('company_name', 'Unknown')}")
    return {
        "status": "saved",
        "completeness": _calculate_profile_completeness(normalized)
    }


@app.get("/api/profile/load")
async def load_profile(request: Request):
    """Load saved profile - returns current profile or empty profile"""
    session = get_session(request)
    
    profile = session.get("profile") or {}

    # Migrate legacy auto-seeded dummy profile out of session
    if (
        profile.get("company_name") == "AlfaTrader AI"
        and profile.get("description") == "AI-powered algorithmic trading platform"
    ):
        profile = {}
        session["profile"] = None

    payload = {
        "company_name": profile.get("company_name", ""),
        "website": profile.get("website", ""),
        "description": profile.get("description", ""),
        "sector": profile.get("sector", ""),
        "sub_sector": profile.get("sub_sector", ""),
        "primary_market": profile.get("primary_market", ""),
        "country": profile.get("country", ""),
        "operating_countries": profile.get("operating_countries", ""),
        "arr": profile.get("arr", ""),
        "stage": profile.get("stage", ""),
        "runway": profile.get("runway", ""),
        "team_size": profile.get("team_size", ""),
        "currency": profile.get("currency", ""),
        "risk_areas": profile.get("risk_areas", []),
        "regulations": profile.get("regulations", []),
        "risk_tolerance": profile.get("risk_tolerance", ""),
        "current_decisions": profile.get("current_decisions", ""),
        "comp_threat": profile.get("comp_threat", ""),
        "constraint": profile.get("constraint", ""),
        "completeness": _calculate_profile_completeness(profile) if profile else 0
    }

    if not payload["company_name"]:
        session["dashboard_cache"] = {}

    _cache_dashboard_block(session, "profile", payload)

    return payload


@app.get("/api/intelligence/analyze")
async def analyze_intelligence(request: Request):
    """Analyze risk intelligence for current profile"""
    session = get_session(request)

    if not _has_user_profile(session):
        payload = {
            "requires_profile": True,
            "risk_score": None,
            "tier": "PROFILE_REQUIRED",
            "direction": "—",
            "summary_text": "Add company profile first to run intelligence.",
            "risks": [],
            "actions": []
        }
        _cache_dashboard_block(session, "intelligence", payload)
        return payload

    # Serve the REAL last pipeline analysis — never fabricated numbers.
    if session.get("last_risk_score") is None:
        payload = {
            "requires_briefing": True,
            "risk_score": None,
            "tier": "NO_ANALYSIS",
            "direction": "—",
            "summary_text": "No analysis yet — ask Vigil for a risk briefing in the chat to generate live intelligence.",
            "risks": [],
            "actions": [],
            "oracle_output": session.get("last_oracle_output")
        }
        _cache_dashboard_block(session, "intelligence", payload)
        return payload

    payload = {
        "risk_score": session.get("last_risk_score"),
        "tier": session.get("last_risk_tier") or "—",
        "direction": "—",
        "summary_text": session.get("last_verdict")
                        or "Latest briefing available in chat.",
        "risks": [_risk_to_ui(r) for r in (session.get("last_top_risks") or [])[:3]],
        "actions": [_action_to_ui(a) for a in (session.get("last_top_actions") or [])[:3]],
        "oracle_output": session.get("last_oracle_output")
    }
    _cache_dashboard_block(session, "intelligence", payload)

    return payload


def _risk_to_ui(risk: dict) -> dict:
    """Map an engine risk dict to the dashboard's display shape."""
    return {
        "name": risk.get("name", "Unnamed risk"),
        "probability": risk.get("probability", 50),
        "severity": risk.get("severity", "MEDIUM"),
        "horizon": risk.get("timeline") or risk.get("horizon") or "—",
        "detail": risk.get("detail", "")
    }


def _action_to_ui(action: dict) -> dict:
    """Map an engine action dict to the dashboard's display shape."""
    return {
        "name": action.get("title") or action.get("name", "Unnamed action"),
        "owner": action.get("owner", "Leadership"),
        "deadline": action.get("deadline", "—"),
        "priority": action.get("urgency") or action.get("priority", "HIGH"),
        "detail": action.get("detail", "")
    }


@app.get("/api/scores/breakdown")
async def get_scores_breakdown(request: Request):
    """Get risk score breakdown by category"""
    session = get_session(request)

    if not _has_user_profile(session):
        payload = {
            "requires_profile": True,
            "macro": {"score": 0, "label": "Macro", "status": "not_available"},
            "narrative": {"score": 0, "label": "Narrative", "status": "not_available"},
            "market": {"score": 0, "label": "Market", "status": "not_available"},
            "competitive": {"score": 0, "label": "Competitive", "status": "not_available"}
        }
        _cache_dashboard_block(session, "scores", payload)
        return payload

    # Serve the REAL breakdown parsed from the last Risk Synthesizer run.
    breakdown = session.get("last_score_breakdown") or {}
    if not breakdown:
        payload = {
            "requires_briefing": True,
            "macro": {"score": 0, "label": "Macro", "status": "not_available"},
            "narrative": {"score": 0, "label": "Narrative", "status": "not_available"},
            "market": {"score": 0, "label": "Market", "status": "not_available"},
            "competitive": {"score": 0, "label": "Competitive", "status": "not_available"}
        }
        _cache_dashboard_block(session, "scores", payload)
        return payload

    def _band(score: int) -> str:
        if score >= 75:
            return "high_risk"
        if score >= 50:
            return "medium_risk"
        return "low_risk"

    payload = {
        key: {
            "score": breakdown.get(key, 0),
            "label": key.capitalize(),
            "status": _band(breakdown.get(key, 0)) if key in breakdown else "not_available"
        }
        for key in ("macro", "narrative", "market", "competitive")
    }
    _cache_dashboard_block(session, "scores", payload)
    return payload


@app.get("/api/market/pulse")
async def get_market_pulse_api(request: Request):
    """Get LIVE market indicators from data_layer"""
    session = get_session(request)

    def _fmt(value, spec: str) -> str:
        """Format a numeric value, or an honest em-dash when data is missing."""
        return format(value, spec) if value is not None else "—"

    try:
        pulse = fetch_market_pulse()
        vix = pulse.get("vix", {})
        spx = pulse.get("spx", {})
        tnx = pulse.get("treasury_10y", {})
        gold = pulse.get("gold", {})

        payload = {
            "vix": {
                "value": vix.get("value"),
                "label": "VIX",
                "status": (vix.get("level") or "neutral").lower(),
                "formatted": _fmt(vix.get("value"), ".1f")
            },
            "yield_10y": {
                "value": tnx.get("yield_pct"),
                "label": "10Y Yield",
                "status": (tnx.get("signal") or "neutral").lower(),
                "formatted": _fmt(tnx.get("yield_pct"), ".2f") + ("%" if tnx.get("yield_pct") is not None else "")
            },
            "sp500_7d": {
                "value": spx.get("pct_7d"),
                "label": "S&P 7D",
                "status": (spx.get("trend") or "flat").lower(),
                "formatted": _fmt(spx.get("pct_7d"), "+.1f") + ("%" if spx.get("pct_7d") is not None else "")
            },
            "gold_7d": {
                "value": gold.get("pct_7d"),
                "label": "Gold 7D",
                "status": (gold.get("signal") or "flat").lower(),
                "formatted": _fmt(gold.get("pct_7d"), "+.1f") + ("%" if gold.get("pct_7d") is not None else "")
            },
            "market_regime": pulse.get("market_regime")
        }
        _cache_dashboard_block(session, "pulse", payload)
        return payload
    except Exception as e:
        logger.error(f"Error fetching market pulse: {e}")
        # Return fallback data on error
        payload = {
            "vix": {"value": None, "label": "VIX", "status": "neutral", "formatted": "—"},
            "yield_10y": {"value": None, "label": "10Y Yield", "status": "neutral", "formatted": "—"},
            "sp500_7d": {"value": None, "label": "S&P 7D", "status": "neutral", "formatted": "—"},
            "gold_7d": {"value": None, "label": "Gold 7D", "status": "neutral", "formatted": "—"}
        }
        _cache_dashboard_block(session, "pulse", payload)
        return payload


@app.get("/api/sectors/performance")
async def get_sectors_performance_api(request: Request):
    """Get LIVE sector performance from data_layer"""
    session = get_session(request)
    try:
        sectors_data = fetch_sector_performance()
        
        # Map full sector names to dashboard short names
        sector_map = {
            "Technology": "TECH",
            "Healthcare": "HEALTH",
            "Financial Services": "FINANCE",
            "Consumer Discretionary": "CONSUMER",
            "Energy": "ENERGY",
            "Real Estate": "REAL EST",
            "Industrials": "INDUSTRIALS"
        }
        
        sectors = []
        for full_name, short_name in sector_map.items():
            data = sectors_data.get(full_name, {})
            pct_7d = data.get("pct_7d", 0)
            signal = data.get("signal", "FLAT").lower()
            
            sectors.append({
                "name": short_name,
                "change_7d": pct_7d if pct_7d is not None else 0,
                "status": signal
            })
        
        payload = {"sectors": sectors}
        _cache_dashboard_block(session, "sectors", payload)
        return payload
    except Exception as e:
        logger.error(f"Error fetching sector performance: {e}")
        payload = {"sectors": [], "error": "LIVE_SECTORS_UNAVAILABLE"}
        _cache_dashboard_block(session, "sectors", payload)
        return payload


@app.get("/api/feed/intelligence")
async def get_feed_intelligence_api(request: Request):
    """Get LIVE news feed from data_layer"""
    try:
        session = get_session(request)
        if not _has_user_profile(session):
            payload = {"requires_profile": True, "feed": []}
            _cache_dashboard_block(session, "feed", payload)
            return payload

        profile = session.get("profile") or {}
        
        # Use profile industry for targeted news, or default to 'finance'
        industry = profile.get("industry", "finance")
        if not isinstance(industry, str) or not industry.strip():
            industry = "finance"
        sector = industry.strip().lower()
        
        headlines = fetch_live_headlines(sector=sector)
        
        # Map data_layer format to dashboard format
        feed = [
            {
                "source": h.get("source", "Unknown"),
                "headline": h.get("title", "No headline"),
                "sentiment": h.get("sentiment", "neutral"),
                "timestamp": h.get("publishedAt", datetime.utcnow().isoformat()),
                "url": h.get("url", "")
            }
            for h in headlines[:10]  # Top 10 headlines
        ]
        
        payload = {"feed": feed}
        _cache_dashboard_block(session, "feed", payload)
        return payload
    except Exception as e:
        logger.error(f"Error fetching intelligence feed: {e}")
        payload = {"feed": [], "error": "LIVE_NEWS_UNAVAILABLE"}
        _cache_dashboard_block(session, "feed", payload)
        return payload


@app.post("/api/chat/message")
async def chat_message(request: Request, data: dict):
    """
    Direct chat message endpoint (distinct from /api/chat)
    Delegate to orchestrator-backed chat for real agent behavior
    """
    return await chat_endpoint(request, data)


def _calculate_profile_completeness(profile: Optional[dict]) -> int:
    """Calculate profile completeness percentage"""
    if not profile:
        return 0
    
    required_fields = ["company_name", "description", "sector"]
    optional_fields = ["website", "sub_sector", "primary_market", "country", "arr_range", "funding_stage"]
    
    score = 0
    # Required fields: 20 points each (60 total)
    for field in required_fields:
        if profile.get(field):
            score += 20
    
    # Optional fields: 5 points each (40 total)
    for field in optional_fields:
        if profile.get(field):
            score += 5
    
    return min(score, 100)


# ============================================================================
# LIVE DATA API
# ============================================================================

@app.get("/api/live-data")
async def get_live_data():
    """Get live market data (wraps data_layer)"""
    try:
        data = get_all_live_data()
        return data
    except Exception as e:
        logger.error(f"Error fetching live data: {e}")
        return {
            "headlines": [],
            "sectors": {},
            "pulse": {},
            "data_quality": "MINIMAL",
            "error": str(e)
        }


# ============================================================================
# CHAT/ANALYSIS API
# ============================================================================

# Pipeline statuses → dashboard status vocabulary
_STATUS_MAP = {"queued": "queued", "running": "active", "complete": "done",
               "error": "error", "idle": "idle"}


@app.post("/api/chat")
async def chat_endpoint(request: Request, data: dict):
    """
    Main analysis endpoint — runs the 8-agent pipeline in-process.
    The engine routes intents to agent waves and returns a structured result.
    """
    session = get_session(request)
    message = data.get("message", "")

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    logger.info(f"Chat request from session {session['session_id']}: {message[:50]}...")

    # History BEFORE this message (engine context), then persist the user turn
    history = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in session.get("conversation", [])[-10:]
    ]
    _append_conversation(session, {
        "role": "user",
        "content": message,
        "timestamp": datetime.utcnow().isoformat()
    })

    profile = _normalize_profile(session.get("profile") or {})

    # Stream engine agent statuses into the session; /ws polls and broadcasts.
    # Note: the listener is process-global — concurrent chats from different
    # sessions may briefly cross-talk status displays (portfolio-scope tradeoff).
    def _on_status(agent_name: str, status: str, elapsed=None):
        session["agent_statuses"][agent_name] = _STATUS_MAP.get(status, status)

    set_status_listener(_on_status)
    try:
        result = await asyncio.to_thread(
            run_pipeline, message, profile or None, history
        )
    except Exception as e:
        session["agent_statuses"]["orchestrator"] = "error"
        await broadcast_status(session["session_id"])
        logger.error(f"Pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis pipeline failed: {e}")
    finally:
        set_status_listener(None)

    await broadcast_status(session["session_id"])

    # Persist structured outputs to the session (engine owns no state)
    _update_session_from_result(session, result)

    intent = result.get("intent_type", "")
    if intent == "INVESTMENT_QUERY" and result.get("oracle_output"):
        raw_message = result["oracle_output"]
    else:
        raw_message = result.get("primary_response", "")

    # Honest degradation: if the LLM was unreachable the engine returns
    # "[AGENT UNAVAILABLE …]" placeholders — say so plainly, never fake analysis.
    if "UNAVAILABLE" in raw_message[:120]:
        status = "degraded"
        clean_message = (
            "Vigil's analysis agents are unavailable right now — check that your "
            "LLM API key (AIML_API_KEY or LLM_API_KEY in .env) is set and valid. "
            "Live market data remains active."
        )
    else:
        status = "success"
        clean_message = _extract_clean_verdict(raw_message)

    agents_used = [
        a.replace("_", " ").title() for a in result.get("agents_activated", [])
    ]

    _append_conversation(session, {
        "role": "assistant",
        "content": clean_message,
        "timestamp": datetime.utcnow().isoformat(),
        "intent": intent,
        "agents_used": agents_used
    })

    logger.info(f"Analysis complete for session {session['session_id']}")

    return {
        "status": status,
        "message": clean_message,
        "intent": intent,
        "agents_used": agents_used,
        "risk_score": result.get("risk_score"),
        "risk_tier": result.get("risk_tier"),
        "execution_time": result.get("total_time_seconds", 0)
    }


def _update_session_from_result(session: dict, result: dict):
    """Persist pipeline outputs to the session — the engine owns no state."""
    # Risk-strip fields update only for full-risk-analysis intents
    # (Oracle/pulse runs preserve the previous strip state).
    if result.get("updates_risk_strip"):
        if result.get("risk_score") is not None:
            session["last_risk_score"] = result["risk_score"]
        if result.get("risk_tier"):
            session["last_risk_tier"] = result["risk_tier"]
        if result.get("verdict"):
            session["last_verdict"] = result["verdict"]
        if result.get("top_risks"):
            session["last_top_risks"] = result["top_risks"]
        if result.get("top_actions"):
            session["last_top_actions"] = result["top_actions"]
        if result.get("score_breakdown"):
            session["last_score_breakdown"] = result["score_breakdown"]
        if result.get("full_playbook"):
            session["last_playbook"] = result["full_playbook"]

    if result.get("oracle_output"):
        session["last_oracle_output"] = result["oracle_output"]

    session["updated_at"] = datetime.utcnow().isoformat()
    SESSION_STORE.save()


# ============================================================================
# WEBSOCKET FOR REAL-TIME UPDATES
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time agent status updates"""
    await websocket.accept()
    
    # Get session ID from query params
    query_params = websocket.query_params
    session_id = query_params.get("session_id")
    
    if not session_id or session_id not in SESSIONS:
        await websocket.close(code=1008, reason="Invalid session")
        return
    
    active_connections[session_id] = websocket
    logger.info(f"WebSocket connected for session {session_id}")
    
    try:
        while True:
            # Send current agent statuses every 500ms
            if session_id in SESSIONS:
                await websocket.send_json({
                    "type": "agent_status",
                    "data": SESSIONS[session_id]["agent_statuses"]
                })
            await asyncio.sleep(0.5)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
        if session_id in active_connections:
            del active_connections[session_id]
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if session_id in active_connections:
            del active_connections[session_id]


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    llm_key_set = bool(
        os.getenv("LLM_API_KEY") or os.getenv("AIML_API_KEY") or os.getenv("OPENAI_API_KEY")
    )
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "engine": "in-process",
        "llm_key_configured": llm_key_set,
        "newsapi_key_configured": bool(os.getenv("NEWSAPI_KEY")),
        "sessions": len(SESSIONS),
        "active_connections": len(active_connections)
    }


# ============================================================================
# STARTUP
# ============================================================================

@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("Vigil starting — single-process, 8-agent engine in-process")
    logger.info(f"Sessions loaded: {len(SESSIONS)}")
    
    # Cleanup old sessions (>7 days)
    SESSION_STORE.cleanup_old_sessions(max_age_days=7)
    
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Save sessions on graceful shutdown"""
    logger.info("Saving sessions before shutdown...")
    SESSION_STORE.save()
    logger.info("✅ Sessions saved")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
