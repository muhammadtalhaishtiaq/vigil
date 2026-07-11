"""The agent loop: tool calling, iteration cap, graceful degradation, status events."""

import agent_core
from tests.conftest import make_response, make_tool_call

import pytest


@pytest.fixture
def oracle(monkeypatch):
    """market_oracle with one stub tool; tool list restored after the test."""
    calls = []

    def fake_fetch(ticker):
        calls.append(ticker)
        return f"STUBDATA for {ticker}: price 100"

    stub = agent_core.Tool(
        name="get_stock_data", description="stub", fn=fake_fetch,
        schema={"type": "object", "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"]},
    )
    agent = agent_core.AGENTS["market_oracle"]
    monkeypatch.setattr(agent, "tools", [stub])
    return agent, calls


def test_tool_loop_reason_act_observe_answer(mock_llm, oracle):
    agent, calls = oracle
    state = {"turn": 0}

    def create(**kw):
        state["turn"] += 1
        assert "tools" in kw, "tool-using agent must advertise its tools"
        if state["turn"] == 1:
            return make_response(
                tool_calls=[make_tool_call("c1", "get_stock_data", '{"ticker":"TSLA"}')]
            )
        return make_response(content="Verdict: HOLD — based on STUBDATA.")

    mock_llm(create)
    events = []
    agent_core.set_status_listener(lambda n, s, e: events.append((n, s)))

    out = agent.run("Should I buy TSLA?", max_tokens=200)

    assert calls == ["TSLA"], "tool was not executed exactly once"
    assert "HOLD" in out
    assert ("market_oracle", "running") in events
    assert ("market_oracle", "complete") in events


def test_iteration_cap_forces_final_answer(mock_llm, oracle):
    agent, calls = oracle
    state = {"turn": 0}

    def create(**kw):
        state["turn"] += 1
        if "tools" in kw:  # keep asking for tools forever
            return make_response(
                tool_calls=[make_tool_call(f"c{state['turn']}", "get_stock_data",
                                           '{"ticker":"TSLA"}')]
            )
        return make_response(content="Forced final answer.")

    mock_llm(create)
    out = agent.run("loop forever please")
    assert out == "Forced final answer."
    assert len(calls) == agent_core._MAX_TOOL_ITERS, "cap not enforced"


def test_provider_without_function_calling_degrades(mock_llm, oracle):
    agent, calls = oracle

    def create(**kw):
        if "tools" in kw:
            raise RuntimeError("tools parameter not supported")
        return make_response(content="Plain answer without tools.")

    mock_llm(create)
    out = agent.run("Should I buy TSLA?")
    assert out == "Plain answer without tools."
    assert calls == []


def test_unknown_tool_call_is_reported_not_crashed(mock_llm, oracle):
    agent, _ = oracle
    state = {"turn": 0}

    def create(**kw):
        state["turn"] += 1
        if state["turn"] == 1:
            return make_response(
                tool_calls=[make_tool_call("c1", "not_a_real_tool", "{}")]
            )
        return make_response(content="done")

    mock_llm(create)
    assert agent.run("x") == "done"


def test_llm_failure_returns_safe_placeholder(mock_llm):
    def create(**kw):
        raise RuntimeError("simulated 500")

    mock_llm(create)
    events = []
    agent_core.set_status_listener(lambda n, s, e: events.append((n, s)))
    out = agent_core.AGENTS["risk_synthesizer"].run("anything")
    assert "UNAVAILABLE" in out
    assert ("risk_synthesizer", "error") in events


def test_toolless_agent_makes_single_plain_call(mock_llm):
    seen = []

    def create(**kw):
        seen.append(kw)
        return make_response(content="analysis")

    mock_llm(create)
    out = agent_core.AGENTS["narrative_intel"].run("context here")
    assert out == "analysis"
    assert len(seen) == 1
    assert "tools" not in seen[0], "toolless agents must not send a tools param"


def test_vigil_model_env_overrides_all_agents(mock_llm, monkeypatch):
    monkeypatch.setenv("VIGIL_MODEL", "override-model-x")
    seen = {}

    def create(**kw):
        seen["model"] = kw["model"]
        return make_response(content="ok")

    mock_llm(create)
    agent_core.AGENTS["macro_watchdog"].run("q")
    assert seen["model"] == "override-model-x"
