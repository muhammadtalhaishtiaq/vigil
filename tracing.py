"""
tracing.py — Replayable run traces for the Vigil engine
=======================================================
Observability per the production-agent playbook: every pipeline run writes a
JSONL trace — one line per event — so any briefing can be replayed and debugged
("why did the agent say that?") instead of guessed at from log lines.

Events:
    run_start   {query, profile_company, ts}
    agent_step  {agent, model, status, elapsed, usage{prompt,completion},
                 tool_calls[{name, args, result_chars}], input_chars,
                 output, ts}
    run_end     {intent_type, risk_score, total_time, total_usage, ts}

Storage: one file per run under VIGIL_TRACE_DIR (default ./traces/, gitignored).
Disable entirely with VIGIL_TRACE=0. Tracing must never break a run: every
write is wrapped; failure degrades to "no trace," not to a crashed pipeline.

Thread-safe: Wave 2 runs agents in parallel threads; events append under a lock.
"""

from __future__ import annotations

import os
import json
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("vigil.trace")

_OUTPUT_CAP = 20_000  # chars of agent output kept per step — enough to replay


def _enabled() -> bool:
    return os.getenv("VIGIL_TRACE", "1") != "0"


def _trace_dir() -> Path:
    # cwd, not module dir: identical behavior from a repo checkout and an install
    return Path(os.getenv("VIGIL_TRACE_DIR", Path.cwd() / "traces"))


class TraceRecorder:
    """Collects events for one pipeline run and writes them as JSONL."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._run_id: Optional[str] = None
        self._path: Optional[Path] = None

    # -- lifecycle ---------------------------------------------------------
    def start_run(self, query: str, profile_company: str = "") -> None:
        if not _enabled():
            return
        with self._lock:
            self._run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
            self._path = _trace_dir() / f"run-{self._run_id}.jsonl"
            self._events = [{
                "event": "run_start",
                "query": query[:2000],
                "profile_company": profile_company,
                "ts": time.time(),
            }]

    def record(self, event: dict) -> None:
        """Append one event (thread-safe). No-op when no run is active."""
        if not _enabled():
            return
        with self._lock:
            if self._run_id is None:
                return
            event.setdefault("ts", time.time())
            self._events.append(event)

    def end_run(self, summary: dict) -> dict:
        """
        Close the run and write the JSONL file.

        Returns {"path": str|None, "usage": {"prompt": int, "completion": int}} —
        usage is totalled from the recorded agent steps.
        """
        empty = {"path": None, "usage": {"prompt": 0, "completion": 0}}
        if not _enabled():
            return empty
        with self._lock:
            if self._run_id is None:
                return empty
            totals = {"prompt": 0, "completion": 0}
            for ev in self._events:
                u = ev.get("usage") or {}
                totals["prompt"] += int(u.get("prompt") or 0)
                totals["completion"] += int(u.get("completion") or 0)
            self._events.append({
                "event": "run_end", **summary, "total_usage": totals, "ts": time.time(),
            })
            path, events = self._path, self._events
            self._run_id, self._path, self._events = None, None, []
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                for ev in events:
                    f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
            return {"path": str(path), "usage": totals}
        except Exception as exc:  # tracing never breaks a run
            logger.warning("trace write failed (%s) — run continues untraced", str(exc)[:80])
            return {"path": None, "usage": totals}


# Module-level recorder shared by the engine (one run at a time per process).
recorder = TraceRecorder()


def agent_step_listener(event: dict) -> None:
    """Adapter: receives agent_core trace events and records them."""
    ev = dict(event)
    ev["event"] = "agent_step"
    if isinstance(ev.get("output"), str):
        ev["output"] = ev["output"][:_OUTPUT_CAP]
    recorder.record(ev)


def load_trace(path: str) -> list[dict]:
    """Read a trace file back as a list of events (for replay/eval tooling)."""
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events
