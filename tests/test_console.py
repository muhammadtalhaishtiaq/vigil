"""Interactive console: wizard → persist → question with profile → relaunch memory."""

import io
import json

import pytest

import agent_core
import session_store
import vigil_cli


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """Point the session store at a temp file and start empty."""
    path = tmp_path / "sessions.json"
    monkeypatch.setattr(session_store, "SESSIONS_FILE", path)
    monkeypatch.setattr(session_store.store, "sessions", {})
    return path


@pytest.fixture
def scripted_pipeline(monkeypatch):
    """Replace run_pipeline with a recorder that also drives status events."""
    calls = []

    def fake_run_pipeline(query, profile=None, history=None):
        calls.append({
            "query": query,
            "profile_company": (profile or {}).get("company_name"),
            "history_len": len(history or []),
        })
        for a in ("orchestrator", "signal_harvester", "risk_synthesizer"):
            agent_core.update_agent_status(a, "running")
            agent_core.update_agent_status(a, "complete", 0.1)
        return {
            "risk_score": 61, "risk_tier": "ORANGE",
            "verdict": "FX is the live risk",
            "executive_brief": "Euro exposure is the main concern this quarter.",
            "top_risks": [{"name": "FX volatility", "detail": "EUR revenue"}],
            "top_actions": [{"title": "Hedge EUR", "deadline": "Q3"}],
            "agents_activated": ["orchestrator", "signal_harvester", "risk_synthesizer"],
            "total_time_seconds": 1.2, "primary_response": "x",
        }

    monkeypatch.setattr(vigil_cli, "run_pipeline", fake_run_pipeline)
    return calls


def _run_console(monkeypatch, lines):
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(lines) + "\n"))
    return vigil_cli.interactive()


def test_wizard_persist_ask_and_relaunch(isolated_store, scripted_pipeline, monkeypatch):
    # First launch: wizard (2 required + 1 optional, skip 6), show, ask, exit.
    rc = _run_console(monkeypatch, [
        "Y",                      # set up profile now?
        "Acme Fintech",           # company_name (required)
        "cross-border payments",  # description (required)
        "Fintech",                # sector
        "", "", "", "", "", "",   # skip optional fields
        "/profile show",
        "how exposed are we to EU regulation?",
        "/history",
        "/exit",
    ])
    assert rc == 0

    # The question ran WITH the freshly saved profile
    assert scripted_pipeline[0]["profile_company"] == "Acme Fintech"

    saved = json.loads(isolated_store.read_text())["cli"]
    assert saved["profile"]["company_name"] == "Acme Fintech"
    assert saved["profile"]["sector"] == "Fintech"
    assert len(saved["history"]) == 2          # user turn + assistant turn
    assert saved["last_risk_score"] == 61

    # Second launch: profile remembered, history fed back into the pipeline.
    rc = _run_console(monkeypatch, ["what changed since yesterday?", "/exit"])
    assert rc == 0
    assert scripted_pipeline[1]["profile_company"] == "Acme Fintech"
    assert scripted_pipeline[1]["history_len"] == 2


def test_brief_requires_profile(isolated_store, scripted_pipeline, monkeypatch):
    rc = _run_console(monkeypatch, [
        "n",          # decline wizard
        "/brief",     # must warn, not run
        "/exit",
    ])
    assert rc == 0
    assert scripted_pipeline == [], "/brief must not run without a profile"


def test_unknown_command_is_handled(isolated_store, scripted_pipeline, monkeypatch):
    rc = _run_console(monkeypatch, ["n", "/bogus", "/exit"])
    assert rc == 0
    assert scripted_pipeline == []


def test_risk_trend_history_and_sparkline(isolated_store, monkeypatch, capsys):
    scores = iter([68, 61])

    def fake_run_pipeline(query, profile=None, history=None):
        s = next(scores)
        return {
            "risk_score": s, "risk_tier": "ORANGE", "verdict": f"risk {s}",
            "executive_brief": "brief", "top_risks": [], "top_actions": [],
            "agents_activated": ["orchestrator"], "total_time_seconds": 1.0,
            "primary_response": "x",
        }

    monkeypatch.setattr(vigil_cli, "run_pipeline", fake_run_pipeline)
    rc = _run_console(monkeypatch, [
        "Y", "Acme", "payments", "", "", "", "", "", "", "",  # wizard
        "brief me", "brief me again", "/trend", "/exit",
    ])
    assert rc == 0
    out = capsys.readouterr().out

    saved = json.loads(isolated_store.read_text())["cli"]
    assert [e["score"] for e in saved["score_history"]] == [68, 61]
    assert "down from 68" in out          # delta printed on the second run
    assert "Risk trend" in out            # /trend panel rendered
    assert any(ch in out for ch in "▁▂▃▄▅▆▇█")

    # Third launch: welcome line carries the delta
    monkeypatch.setattr(vigil_cli, "run_pipeline", lambda *a, **k: {})
    _run_console(monkeypatch, ["/exit"])
    out2 = capsys.readouterr().out
    assert "61/100" in out2 and "down from 68" in out2
