"""Evaluator-optimizer: gating, PASS/REVISE handling, JSON + legacy formats."""

import json

import agent_core
import agent_pipeline as ap

ORIGINAL = '{"risk_score": 50}'
REVISED = '{"risk_score": 62}'


def test_flag_off_is_a_passthrough(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(
        agent_core.RISK_EVALUATOR, "run",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or "x",
    )
    assert ap._evaluate_and_refine(ORIGINAL, "ctx") == ORIGINAL
    assert called["n"] == 0, "evaluator must not run when the flag is off"


def test_json_pass_keeps_original(monkeypatch):
    monkeypatch.setenv("VIGIL_ENABLE_EVALUATOR", "1")
    monkeypatch.setattr(
        agent_core.RISK_EVALUATOR, "run",
        lambda *a, **k: json.dumps({"verdict": "PASS", "quality_score": 88,
                                    "feedback": "solid"}),
    )
    assert ap._evaluate_and_refine(ORIGINAL, "ctx") == ORIGINAL


def test_json_revise_reruns_synthesizer_with_feedback(monkeypatch):
    monkeypatch.setenv("VIGIL_ENABLE_EVALUATOR", "1")
    monkeypatch.setattr(
        agent_core.RISK_EVALUATOR, "run",
        lambda *a, **k: json.dumps({"verdict": "REVISE", "quality_score": 40,
                                    "feedback": "No score; cite FX figures."}),
    )
    captured = {}

    def fake_run_agent(name, prompt, content, max_tokens=2000):
        captured["name"] = name
        captured["content"] = content
        return REVISED

    monkeypatch.setattr(ap, "run_agent", fake_run_agent)
    out = ap._evaluate_and_refine(ORIGINAL, "ctx-with-signals")
    assert out == REVISED
    assert captured["name"] == "risk_synthesizer"
    assert "EVALUATOR FEEDBACK" in captured["content"]
    assert "cite FX figures" in captured["content"]


def test_legacy_eval_format_still_understood(monkeypatch):
    monkeypatch.setenv("VIGIL_ENABLE_EVALUATOR", "1")
    monkeypatch.setattr(
        agent_core.RISK_EVALUATOR, "run",
        lambda *a, **k: "EVAL_VERDICT: REVISE\nEVAL_FEEDBACK: add a tier",
    )
    monkeypatch.setattr(ap, "run_agent", lambda *a, **k: REVISED)
    assert ap._evaluate_and_refine(ORIGINAL, "ctx") == REVISED


def test_evaluator_crash_falls_back_to_original(monkeypatch):
    monkeypatch.setenv("VIGIL_ENABLE_EVALUATOR", "1")

    def boom(*a, **k):
        raise RuntimeError("evaluator exploded")

    monkeypatch.setattr(agent_core.RISK_EVALUATOR, "run", boom)
    assert ap._evaluate_and_refine(ORIGINAL, "ctx") == ORIGINAL


def test_garbage_evaluator_output_defaults_to_pass(monkeypatch):
    monkeypatch.setenv("VIGIL_ENABLE_EVALUATOR", "1")
    monkeypatch.setattr(
        agent_core.RISK_EVALUATOR, "run", lambda *a, **k: "utter nonsense"
    )
    assert ap._evaluate_and_refine(ORIGINAL, "ctx") == ORIGINAL
