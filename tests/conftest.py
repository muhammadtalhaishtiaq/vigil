"""
Shared fixtures for the Vigil test suite.

Every test runs offline: LLM calls are mocked at the OpenAI-client boundary and
data-layer functions are monkeypatched. No API keys, no network.
"""

from __future__ import annotations

import types

import pytest

import agent_core


def make_response(content=None, tool_calls=None, prompt_tokens=100, completion_tokens=50):
    """Build a fake OpenAI-compatible chat completion response."""
    msg = types.SimpleNamespace(content=content, tool_calls=tool_calls)
    usage = types.SimpleNamespace(
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
    )
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)], usage=usage)


def make_tool_call(call_id: str, name: str, arguments: str):
    """Build a fake tool_call entry as the OpenAI SDK shapes it."""
    return types.SimpleNamespace(
        id=call_id,
        type="function",
        function=types.SimpleNamespace(name=name, arguments=arguments),
    )


def make_client(create_fn):
    """Wrap a create(**kwargs) function into a fake OpenAI client."""
    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create_fn))
    )


@pytest.fixture
def mock_llm(monkeypatch):
    """
    Patch the shared LLM client. Usage:

        def test_x(mock_llm):
            mock_llm(lambda **kw: make_response(content="hi"))
    """
    def _install(create_fn):
        client = make_client(create_fn)
        monkeypatch.setattr(agent_core, "get_client", lambda: client)
        return client
    return _install


@pytest.fixture(autouse=True)
def isolate_state(tmp_path, monkeypatch):
    """Keep traces and status listeners from leaking between tests."""
    monkeypatch.setenv("VIGIL_TRACE_DIR", str(tmp_path / "traces"))
    monkeypatch.delenv("VIGIL_ENABLE_EVALUATOR", raising=False)
    monkeypatch.delenv("VIGIL_MODEL", raising=False)
    monkeypatch.setattr(agent_core, "_BACKOFF_BASE_S", 0.0)  # no real sleeps
    yield
    agent_core.set_status_listener(None)
