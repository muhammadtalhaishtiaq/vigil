"""Run traces: lifecycle, usage totals, tool-call records, disabled mode."""

import os

import agent_core
import tracing
from tests.conftest import make_response, make_tool_call


def _run_traced_oracle(mock_llm, monkeypatch):
    """One traced oracle run: tool call turn, then final answer, with usage."""
    stub = agent_core.Tool(
        name="get_stock_data", description="stub",
        fn=lambda ticker: f"data {ticker}",
        schema={"type": "object", "properties": {"ticker": {"type": "string"}}},
    )
    monkeypatch.setattr(agent_core.AGENTS["market_oracle"], "tools", [stub])

    state = {"turn": 0}

    def create(**kw):
        state["turn"] += 1
        if state["turn"] == 1 and "tools" in kw:
            return make_response(
                tool_calls=[make_tool_call("c1", "get_stock_data", '{"ticker":"TSLA"}')],
                prompt_tokens=200, completion_tokens=30,
            )
        return make_response(content="Verdict text.", prompt_tokens=150, completion_tokens=80)

    mock_llm(create)
    tracing.recorder.start_run("should I buy TSLA?", profile_company="Acme")
    out = agent_core.AGENTS["market_oracle"].run("should I buy TSLA?")
    info = tracing.recorder.end_run(
        {"intent_type": "INVESTMENT_QUERY", "risk_score": None, "total_time": 1.0}
    )
    return out, info


def test_trace_file_and_usage_totals(mock_llm, monkeypatch):
    out, info = _run_traced_oracle(mock_llm, monkeypatch)
    assert out == "Verdict text."
    assert info["path"] and os.path.exists(info["path"])
    assert info["usage"] == {"prompt": 350, "completion": 110}

    events = tracing.load_trace(info["path"])
    assert [e["event"] for e in events] == ["run_start", "agent_step", "run_end"]

    step = events[1]
    assert step["agent"] == "market_oracle"
    assert step["usage"] == {"prompt": 350, "completion": 110}
    assert step["tool_calls"] == [
        {"name": "get_stock_data", "args": '{"ticker":"TSLA"}',
         "result_chars": 9, "result": "data TSLA"}
    ]
    assert step["output"] == "Verdict text."
    assert events[2]["total_usage"] == {"prompt": 350, "completion": 110}


def test_disabled_mode_writes_nothing(mock_llm, monkeypatch):
    monkeypatch.setenv("VIGIL_TRACE", "0")

    mock_llm(lambda **kw: make_response(content="ok"))
    tracing.recorder.start_run("x")
    agent_core.AGENTS["narrative_intel"].run("q")
    info = tracing.recorder.end_run({})
    assert info["path"] is None


def test_error_steps_are_traced(mock_llm, monkeypatch):
    def create(**kw):
        raise RuntimeError("simulated outage")

    mock_llm(create)
    tracing.recorder.start_run("q")
    agent_core.AGENTS["macro_watchdog"].run("q")
    info = tracing.recorder.end_run({"intent_type": "MACRO_FOCUS"})

    events = tracing.load_trace(info["path"])
    step = next(e for e in events if e["event"] == "agent_step")
    assert step["status"] == "error"
    assert "simulated outage" in step["output"]


def test_record_without_active_run_is_noop():
    tracing.recorder.record({"event": "agent_step", "agent": "x"})  # must not raise
    assert tracing.recorder.end_run({})["path"] is None
