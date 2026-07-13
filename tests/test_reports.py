"""/export and `vigil monitor`: reports, thresholds, exit codes."""

import json

import pytest

import session_store
import tools
import vigil_cli


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated store + workspace."""
    monkeypatch.setattr(session_store, "SESSIONS_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(session_store.store, "sessions", {})
    monkeypatch.setenv("VIGIL_WORKSPACE", str(tmp_path / "ws"))
    return tmp_path


def _scored_result(score):
    return {
        "risk_score": score, "risk_tier": "ORANGE", "verdict": f"risk {score}",
        "executive_brief": "the brief", "top_risks":
            [{"name": "FX", "probability": 70, "detail": "EUR exposure"}],
        "top_actions": [{"title": "Hedge EUR", "deadline": "Q3"}],
        "agents_activated": ["a", "b"], "total_time_seconds": 3.2,
        "primary_response": "x",
    }


def _seed_session(profile=True, briefing=True, history=()):
    data = {"profile": {"company_name": "Acme", "description": "payments"}
            if profile else {}, "history": [], "score_history": list(history)}
    if briefing:
        data["last_briefing"] = vigil_cli._briefing_snapshot(_scored_result(61))
    session_store.store.set("cli", data)


class TestExport:
    def test_export_writes_markdown_report(self, env, capsys):
        _seed_session(history=[{"date": "2026-07-01", "score": 68, "tier": "RED"}])
        session = vigil_cli._load_session()
        vigil_cli._cmd_export(session)
        out = capsys.readouterr().out
        assert "report written" in out

        reports = list(tools.workspace_dir("reports").glob("briefing-*.md"))
        assert len(reports) == 1
        body = reports[0].read_text()
        assert "# Vigil risk report — Acme" in body
        assert "61/100" in body and "Hedge EUR" in body
        assert "not financial advice" in body

    def test_export_without_briefing_warns(self, env, capsys):
        _seed_session(briefing=False)
        vigil_cli._cmd_export(vigil_cli._load_session())
        assert "Nothing to export" in capsys.readouterr().out


class TestMonitor:
    class Args:
        threshold = 10

    def test_first_run_exits_2_and_writes_report(self, env, monkeypatch):
        _seed_session(briefing=False)
        monkeypatch.setattr(vigil_cli, "run_pipeline",
                            lambda *a, **k: _scored_result(61))
        with pytest.raises(SystemExit) as e:
            vigil_cli.cmd_monitor(self.Args())
        assert e.value.code == 2  # first run counts as a change
        assert list(tools.workspace_dir("reports").glob("monitor-*.md"))
        saved = session_store.store.get("cli")
        assert saved["score_history"][-1]["score"] == 61

    def test_small_change_exits_0(self, env, monkeypatch):
        _seed_session(history=[{"date": "2026-07-01", "score": 65, "tier": "ORANGE"}])
        monkeypatch.setattr(vigil_cli, "run_pipeline",
                            lambda *a, **k: _scored_result(61))
        with pytest.raises(SystemExit) as e:
            vigil_cli.cmd_monitor(self.Args())
        assert e.value.code == 0  # Δ4 < 10

    def test_jump_exits_2(self, env, monkeypatch):
        _seed_session(history=[{"date": "2026-07-01", "score": 40, "tier": "YELLOW"}])
        monkeypatch.setattr(vigil_cli, "run_pipeline",
                            lambda *a, **k: _scored_result(61))
        with pytest.raises(SystemExit) as e:
            vigil_cli.cmd_monitor(self.Args())
        assert e.value.code == 2  # Δ21 >= 10

    def test_no_profile_exits_1(self, env, monkeypatch):
        _seed_session(profile=False, briefing=False)
        with pytest.raises(SystemExit) as e:
            vigil_cli.cmd_monitor(self.Args())
        assert e.value.code == 1

    def test_no_score_exits_1(self, env, monkeypatch):
        _seed_session()
        monkeypatch.setattr(vigil_cli, "run_pipeline",
                            lambda *a, **k: {"risk_score": None})
        with pytest.raises(SystemExit) as e:
            vigil_cli.cmd_monitor(self.Args())
        assert e.value.code == 1
