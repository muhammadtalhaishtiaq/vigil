"""The eval harness itself: golden file integrity, structural checks, runner."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "evals"))
import run_evals  # noqa: E402

GOLDEN = json.loads((Path(__file__).parent.parent / "evals" / "golden.json").read_text())


def test_golden_file_is_well_formed():
    assert len(GOLDEN["scenarios"]) >= 15
    ids = [s["id"] for s in GOLDEN["scenarios"]]
    assert len(ids) == len(set(ids)), "duplicate scenario ids"
    for sc in GOLDEN["scenarios"]:
        assert sc["query"].strip()
        if sc.get("profile"):
            assert sc["profile"] in GOLDEN["profiles"]
    # Every routed intent is covered
    intents = {s["expect"].get("intent") for s in GOLDEN["scenarios"] if s.get("expect")}
    for intent in ("FULL_BRIEFING", "INVESTMENT_QUERY", "MACRO_FOCUS",
                   "COMPETITIVE_FOCUS", "DECISION_SUPPORT", "SCENARIO", "MARKET_PULSE"):
        assert intent in intents, f"no scenario covers {intent}"


def test_structural_checks():
    expect = {"intent": "FULL_BRIEFING", "risk_score": True, "top_risks": 3,
              "agents_include": ["risk_synthesizer"], "agents_exclude": ["market_oracle"]}
    good = {"intent_type": "FULL_BRIEFING", "risk_score": 60,
            "top_risks": [{}, {}, {}],
            "agents_activated": ["orchestrator", "risk_synthesizer"]}
    assert run_evals.check_structure(expect, good) == []

    bad = {"intent_type": "MARKET_PULSE", "risk_score": None, "top_risks": [{}],
           "agents_activated": ["market_oracle"]}
    failures = run_evals.check_structure(expect, bad)
    assert len(failures) == 5  # intent, score, risks, include, exclude


def test_response_view_prefers_structured_fields():
    view = run_evals.response_view({
        "risk_score": 61, "risk_tier": "ORANGE", "verdict": "v",
        "top_risks": [{"name": "FX", "detail": "d"}],
        "primary_response": "should not appear",
    })
    assert "Risk 61/100" in view and "FX" in view
    assert "should not appear" not in view


def test_runner_end_to_end_with_mocked_pipeline(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(run_evals, "REPORTS", tmp_path)
    monkeypatch.setattr(run_evals, "run_pipeline", lambda q, profile=None: {
        "intent_type": "INVESTMENT_QUERY", "risk_score": None, "top_risks": [],
        "oracle_output": "WAIT — overextended.", "agents_activated":
            ["orchestrator", "signal_harvester", "market_oracle"],
        "token_usage": {"prompt": 1000, "completion": 300},
        "trace_path": None, "profile_was_used": False,
        "primary_response": "x", "top_actions": [],
    })
    rc = run_evals.main(["--only", "invest-ticker", "--no-judge"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Structural: 1/1 passed" in out
    reports = list(tmp_path.glob("eval-*.json"))
    assert len(reports) == 1
    row = json.loads(reports[0].read_text())[0]
    assert row["id"] == "invest-ticker"
    assert row["structural_failures"] == []


def test_runner_reports_structural_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(run_evals, "REPORTS", tmp_path)
    monkeypatch.setattr(run_evals, "run_pipeline", lambda q, profile=None: {
        "intent_type": "FULL_BRIEFING",  # wrong for invest-ticker
        "risk_score": None, "top_risks": [], "oracle_output": None,
        "agents_activated": [], "token_usage": {}, "trace_path": None,
        "profile_was_used": False, "primary_response": "x", "top_actions": [],
    })
    rc = run_evals.main(["--only", "invest-ticker", "--no-judge"])
    assert rc == 1
    assert "STRUCT FAIL" in capsys.readouterr().out
