"""
main.py — Vigil FastAPI Application v2.1
=========================================
Background job queue eliminates 524 timeouts.
Pipeline runs in a thread; client polls /api/job/{id} every 2s.

Routes:
  GET  /                      → vigil-landing.html
  GET  /dashboard             → vigil-dashboard.html
  GET  /profile               → vigil-profile.html
  GET  /api/session           → create or validate session
  POST /api/profile           → save company profile
  GET  /api/profile           → load company profile
  POST /api/analyze           → enqueue pipeline job → returns {job_id}
  GET  /api/job/{job_id}      → poll job status + agent states + result
  GET  /api/session/summary   → session state (risks, scores, agent statuses)
  GET  /api/live-data         → live market data
  GET  /api/health            → health check
"""

import os
import uuid
import logging
import asyncio
import threading
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from fastapi import FastAPI, Cookie, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv

load_dotenv()

import session_manager
from data_layer import get_all_live_data

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
)
logger = logging.getLogger("vigil.main")

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
app = FastAPI(title="Vigil — Risk Intelligence", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ---------------------------------------------------------------------------
# Background Job Queue
# job_id → {status, session_id, result, error, started_at}
# ---------------------------------------------------------------------------
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _run_pipeline_job(job_id: str, session_id: str, message: str) -> None:
    """Background thread: runs the full agent pipeline and stores result in _JOBS."""
    import agent_pipeline
    try:
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "running"

        result = agent_pipeline.run_pipeline(session_id, message)

        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "done"
            _JOBS[job_id]["result"] = {
                "ok":                 True,
                "intent_type":        result.get("intent_type"),
                "agents_activated":   result.get("agents_activated", []),
                "risk_score":         result.get("risk_score"),
                "risk_tier":          result.get("risk_tier"),
                "verdict":            result.get("verdict"),
                "top_risks":          result.get("top_risks", []),
                "top_actions":        result.get("top_actions", []),
                "score_breakdown":    result.get("score_breakdown", {}),
                "executive_brief":    result.get("executive_brief"),
                "full_playbook":      result.get("full_playbook"),
                "oracle_output":      result.get("oracle_output"),
                "market_pulse":       result.get("market_pulse"),
                "primary_response":   result.get("primary_response"),
                "total_time_seconds": result.get("total_time_seconds"),
                "profile_was_used":   result.get("profile_was_used"),
            }
    except Exception as e:
        logger.error("Job %s failed: %s", job_id, e, exc_info=True)
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "error"
            _JOBS[job_id]["error"] = str(e)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ProfilePayload(BaseModel):
    session_id: str
    profile: dict


class AnalyzePayload(BaseModel):
    session_id: str
    message: str
    profile: Optional[dict] = None


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------
def _serve_html(filename: str) -> HTMLResponse:
    html_path = BASE_DIR / filename
    if not html_path.exists():
        return HTMLResponse(f"<h1>File not found: {filename}</h1>", status_code=404)
    content = html_path.read_text(encoding="utf-8")
    content = (content
        .replace('href="vigil-landing.html"',  'href="/"')
        .replace('href="vigil-dashboard.html"', 'href="/dashboard"')
        .replace('href="vigil-profile.html"',   'href="/profile"')
        .replace("location.href='vigil-dashboard.html'", "location.href='/dashboard'")
        .replace("location.href='vigil-profile.html'",   "location.href='/profile'")
        .replace('window.location.href=\'vigil-dashboard.html\'', "window.location.href='/dashboard'")
        .replace('window.location.href="vigil-dashboard.html"',   "window.location.href='/dashboard'")
    )
    return HTMLResponse(content=content)


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def landing():
    return _serve_html("vigil-landing.html")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return _serve_html("vigil-dashboard.html")


@app.get("/profile", response_class=HTMLResponse)
async def profile_page():
    return _serve_html("vigil-profile.html")


# ---------------------------------------------------------------------------
# Session API
# ---------------------------------------------------------------------------
@app.get("/api/session")
async def get_session(vigil_sid: Optional[str] = Cookie(default=None)):
    if vigil_sid and vigil_sid in session_manager._SESSIONS:
        summary = session_manager.get_session_summary(vigil_sid)
        return JSONResponse({"session_id": vigil_sid, **summary})
    new_sid = session_manager.create_session()
    response = JSONResponse({"session_id": new_sid, "has_profile": False, "profile_completeness": 0})
    response.set_cookie("vigil_sid", new_sid, max_age=86400 * 30, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# Profile API
# ---------------------------------------------------------------------------
@app.post("/api/profile")
async def save_profile(payload: ProfilePayload):
    try:
        session_manager.save_profile(payload.session_id, payload.profile)
        profile = session_manager.load_profile(payload.session_id)
        return JSONResponse({
            "ok": True,
            "completeness":    profile.get("profile_completeness", 0),
            "company_name":    profile.get("name", ""),
            "auto_load_prompt": session_manager.get_auto_load_prompt(payload.session_id)
                if session_manager.has_sufficient_profile(payload.session_id) else None,
        })
    except Exception as e:
        logger.error("Profile save failed: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/profile")
async def load_profile(session_id: str):
    profile = session_manager.load_profile(session_id)
    if not profile:
        return JSONResponse({"ok": False, "profile": None})
    return JSONResponse({"ok": True, "profile": profile})


# ---------------------------------------------------------------------------
# Analyze API — enqueues job, returns job_id immediately (fixes 524 timeout)
# ---------------------------------------------------------------------------
@app.post("/api/analyze")
async def analyze(payload: AnalyzePayload):
    """
    Enqueue an analysis job. Returns {job_id} immediately.
    Client polls GET /api/job/{job_id} for status + result.
    """
    try:
        session_manager.init_conversation(payload.session_id)
        if payload.profile:
            session_manager.save_profile(payload.session_id, payload.profile)

        job_id = str(uuid.uuid4())
        with _JOBS_LOCK:
            _JOBS[job_id] = {
                "status":     "queued",
                "session_id": payload.session_id,
                "result":     None,
                "error":      None,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }

        # Start pipeline in background thread
        t = threading.Thread(
            target=_run_pipeline_job,
            args=(job_id, payload.session_id, payload.message),
            daemon=True,
        )
        t.start()

        return JSONResponse({"ok": True, "job_id": job_id, "status": "queued"})
    except Exception as e:
        logger.error("Analyze enqueue failed: %s", e, exc_info=True)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Job Status API — poll this every 2s to get progress + final result
# ---------------------------------------------------------------------------
@app.get("/api/job/{job_id}")
async def job_status(job_id: str):
    """
    Poll for job status. Returns:
      {status: 'queued'|'running'|'done'|'error', agent_statuses, result}
    """
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)

    if not job:
        return JSONResponse({"ok": False, "error": "Job not found"}, status_code=404)

    session_id = job["session_id"]

    # Get live agent statuses from session
    agent_info = session_manager.get_agent_statuses(session_id)

    response: dict = {
        "ok":             True,
        "job_id":         job_id,
        "status":         job["status"],
        "agent_statuses": agent_info["statuses"],
        "agent_elapsed":  agent_info["elapsed"],
        "started_at":     job.get("started_at"),
    }

    if job["status"] == "done" and job["result"]:
        response["result"] = job["result"]
        # Clean up job after delivering result (keep for 5 min for retries)
    elif job["status"] == "error":
        response["error"] = job.get("error", "Unknown error")

    return JSONResponse(response)


# ---------------------------------------------------------------------------
# Session Summary API
# ---------------------------------------------------------------------------
@app.get("/api/session/summary")
async def session_summary(session_id: str):
    try:
        summary = session_manager.get_session_summary(session_id)
        return JSONResponse({"ok": True, **summary})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Live Data API
# ---------------------------------------------------------------------------
@app.get("/api/live-data")
async def live_data(sector: str = "finance"):
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, get_all_live_data, sector)
        return JSONResponse({"ok": True, "data": data})
    except Exception as e:
        logger.error("Live data fetch failed: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return JSONResponse({
        "status":          "ok",
        "service":         "vigil",
        "version":         "2.1.0",
        "active_sessions": len(session_manager._SESSIONS),
        "active_jobs":     len([j for j in _JOBS.values() if j["status"] in ("queued","running")]),
    })


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info("Starting Vigil FastAPI v2.1 on port %d", port)
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
