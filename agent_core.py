"""
agent_core.py — The anatomy of a Vigil agent
=============================================
This module answers one question precisely: **what *is* an agent?**

In 2026 practice an "agent" is not a prompt. It is a small component with a
fixed anatomy (Anthropic, *Building Effective Agents*):

    ┌────────────────────────────────────────────────────────────┐
    │  AGENT                                                      │
    │    • model         — the LLM, right-sized to the job        │
    │    • instructions  — system prompt: role, goal, format      │
    │    • tools         — functions it may CALL to act/observe   │
    │    • memory        — what context it is allowed to read     │
    │    • output        — the contract it must return            │
    │    • guardrails    — temperature, token budget, safe-fail   │
    └────────────────────────────────────────────────────────────┘

Every Vigil component is one `Agent` instance in the `AGENTS` registry below —
though only 2 of the 8 are true agents (the tool-using scouts); the rest are an
LLM router and workflow steps (see D3 in docs/MASTER_PLAN.md). "How is each one
built?" has a literal, readable answer: scroll down.

Design choice — *no framework*. Anthropic's own finding is that "the most
successful implementations use simple, composable patterns rather than complex
frameworks." So an agent here is a plain dataclass that can run itself; the
orchestration between agents lives in `agent_pipeline.py`.

Framework-free: this module imports neither FastAPI nor any agent framework.
LLM access is via any OpenAI-compatible endpoint (default: AIML API).
"""

from __future__ import annotations

import os
import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Optional

from openai import OpenAI

# Load .env for local development (no-op if python-dotenv isn't installed)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("vigil.agent_core")


# ===========================================================================
# 1. SECRETS + LLM CLIENT  (provider-agnostic, lazy singleton)
# ===========================================================================
def _get_secret(key: str, default: str = "") -> str:
    """Read a secret from the environment (.env is loaded above)."""
    return os.getenv(key, default)


_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    """
    Lazily build the OpenAI-compatible LLM client shared by every agent.

    Provider-agnostic — point it anywhere OpenAI-compatible:
        LLM_BASE_URL — default https://api.aimlapi.com/v1
        LLM_API_KEY  — falls back to AIML_API_KEY, then OPENAI_API_KEY
    """
    global _client
    if _client is None:
        api_key = (
            _get_secret("LLM_API_KEY")
            or _get_secret("AIML_API_KEY")
            or _get_secret("OPENAI_API_KEY")
        )
        if not api_key:
            logger.warning(
                "No LLM API key set (LLM_API_KEY / AIML_API_KEY) — agent calls will fail"
            )
        _client = OpenAI(
            api_key=api_key,
            base_url=_get_secret("LLM_BASE_URL", "https://api.aimlapi.com/v1"),
        )
    return _client


# ===========================================================================
# 2. LIVE STATUS REGISTRY  (the "watch the agents work" feed)
# ===========================================================================
# Every state change fires the registered listener. The old web app piped this
# to a websocket; the coming CLI pipes the *same* events into a live terminal
# panel. Orchestration code only has to call `update_agent_status(...)`.
_VALID_STATUSES = {"idle", "queued", "running", "complete", "error"}

AGENT_STATUSES: dict[str, str] = {}
AGENT_ELAPSED: dict[str, Optional[float]] = {}

_status_listener: Optional[Callable[[str, str, Optional[float]], None]] = None
_trace_listener: Optional[Callable[[dict], None]] = None


def set_status_listener(callback: Callable[[str, str, Optional[float]], None]) -> None:
    """Register a callable(agent_name, status, elapsed) invoked on every change."""
    global _status_listener
    _status_listener = callback


def set_trace_listener(callback: Callable[[dict], None]) -> None:
    """
    Register a callable(event_dict) invoked once per completed agent step with
    the full observability record: model, timing, token usage, tool calls, and
    output. The trace module (trace.py) is the standard consumer.
    """
    global _trace_listener
    _trace_listener = callback


def _emit_trace(event: dict) -> None:
    if callable(_trace_listener):
        try:
            _trace_listener(event)
        except Exception:
            pass  # observability failures never break the run


def _usage_of(resp) -> dict:
    """Extract token usage from an OpenAI-compatible response (zeros if absent)."""
    u = getattr(resp, "usage", None)
    return {
        "prompt": getattr(u, "prompt_tokens", 0) or 0,
        "completion": getattr(u, "completion_tokens", 0) or 0,
    }


def update_agent_status(
    agent_name: str,
    status: str,
    elapsed: Optional[float] = None,
) -> None:
    """Update one agent's status/elapsed and notify any listener. Never raises."""
    if status not in _VALID_STATUSES:
        logger.warning("Invalid status '%s' for agent '%s' — ignored", status, agent_name)
        return

    AGENT_STATUSES[agent_name] = status
    if elapsed is not None:
        AGENT_ELAPSED[agent_name] = round(elapsed, 2)

    if callable(_status_listener):
        try:
            _status_listener(agent_name, status, elapsed)
        except Exception:
            pass  # a UI notification failure must never crash the pipeline


# ===========================================================================
# 3. INSTRUCTIONS  (system prompts loaded from /prompts/<name>.txt)
# ===========================================================================
_PROMPTS_DIR = Path(__file__).parent / "prompts"
_prompt_cache: dict[str, str] = {}


def load_prompt(agent_name: str) -> str:
    """
    Load an agent's instructions from /prompts/{agent_name}.txt (cached).

    Missing file → empty string (the agent runs without a system prompt rather
    than crashing the pipeline). Prompt changes are product changes.
    """
    if agent_name in _prompt_cache:
        return _prompt_cache[agent_name]

    prompt_file = _PROMPTS_DIR / f"{agent_name}.txt"
    try:
        content = prompt_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.warning("Prompt file not found: %s (agent runs without instructions)", prompt_file)
        content = ""
    except Exception as exc:
        logger.error("Failed to load prompt for %s: %s", agent_name, exc)
        content = ""

    _prompt_cache[agent_name] = content
    return content


def invalidate_prompt_cache() -> None:
    """Force a reload of all prompt files on next call (useful during dev)."""
    _prompt_cache.clear()


# ===========================================================================
# 4. TOOL  (scaffold — populated in step 2)
# ===========================================================================
@dataclass(frozen=True)
class Tool:
    """
    A capability an agent may CALL — the thing that separates a real agent from
    a prompt chain. `fn` runs the action (fetch data, hit an API) and returns a
    string; `schema` is the JSON-Schema of its parameters, which the model reads
    when deciding whether and how to call it.

    Concrete tools live in `tools.py` (they wrap `data_layer.py`) and are the
    same definitions the MCP server exposes to external clients.
    """
    name: str
    description: str
    fn: Callable[..., str]
    schema: dict = field(default_factory=dict)

    def as_openai_schema(self) -> dict:
        """Render this tool in the OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema or {"type": "object", "properties": {}},
            },
        }


# ===========================================================================
# 5. AGENT  (the anatomy, made runnable)
# ===========================================================================
# Safety cap: how many think→call-tool→observe rounds one agent may take.
_MAX_TOOL_ITERS = 5

# Retry policy for transient LLM failures: 3 attempts, exponential backoff.
# Bounded on purpose — infinite retries are runaway cost, not resilience.
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_S = 1.0

_TRANSIENT_MARKERS = (
    "429", "rate limit", "ratelimit", "timeout", "timed out", "overloaded",
    "connection", "temporarily", "503", "502", "500", "server error",
)


def _is_transient(exc: Exception) -> bool:
    """Heuristic: worth retrying? Auth/validation errors are not."""
    text = f"{type(exc).__name__} {exc}".lower()
    if "401" in text or "unauthorized" in text or "invalid api key" in text:
        return False
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _create_with_retry(**kwargs):
    """
    One chat.completions.create call with up to _MAX_ATTEMPTS on transient
    failures (rate limits, timeouts, 5xx). Non-transient errors raise
    immediately — retrying a bad API key three times just wastes time.
    """
    last_exc: Exception = RuntimeError("unreachable")
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return get_client().chat.completions.create(**kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt == _MAX_ATTEMPTS or not _is_transient(exc):
                raise
            delay = _BACKOFF_BASE_S * (2 ** (attempt - 1))
            logger.warning(
                "transient LLM error (attempt %d/%d, retrying in %.1fs): %s",
                attempt, _MAX_ATTEMPTS, delay, str(exc)[:100],
            )
            time.sleep(delay)
    raise last_exc


@dataclass
class Agent:
    """
    One Vigil agent. Reading these fields tells you exactly what it is made of.

    Fields (the anatomy):
        name         stable identifier; also the /prompts/<name>.txt filename
        role         one-line human description (documentation, not sent to LLM)
        model        the LLM, right-sized: Haiku for fast scouts, Sonnet to reason
        memory       what context this agent is allowed to read (a label, so the
                     information flow is auditable — e.g. "profile + live data"
                     vs "upstream agent outputs")
        tools        Tools it may CALL. Scouts have them (they observe the world);
                     analysts have none (they reason over what scouts found).
        max_tokens   output budget (a cost/latency guardrail)
        temperature  sampling; lower = more deterministic
    """
    name: str
    role: str
    model: str
    memory: str
    tools: list[Tool] = field(default_factory=list)
    max_tokens: int = 2000
    temperature: float = 0.35

    @property
    def instructions(self) -> str:
        """The agent's system prompt (loaded lazily from its prompt file)."""
        return load_prompt(self.name)

    def resolved_model(self) -> str:
        """Model to actually use — VIGIL_MODEL env var overrides every agent."""
        return _get_secret("VIGIL_MODEL") or self.model

    def run(self, user_content: str, max_tokens: Optional[int] = None) -> str:
        """
        Execute this agent and return its text output.

        Toolless agents make one LLM call. Tool-using agents run the canonical
        agent loop: the model reasons, may request tool calls, we execute them
        and feed the observations back, and repeat until it returns a final
        answer (capped at `_MAX_TOOL_ITERS`).

        Emits status transitions (running → complete | error) so any listener
        can render the live agent flow. Never raises: on failure it returns a
        labelled placeholder so one agent's error can't sink the whole briefing.
        """
        update_agent_status(self.name, "running")
        start = time.perf_counter()
        model = self.resolved_model()
        messages: list[dict] = []
        if self.instructions:
            messages.append({"role": "system", "content": self.instructions})
        messages.append({"role": "user", "content": user_content})

        usage = {"prompt": 0, "completion": 0}
        tool_call_log: list[dict] = []
        try:
            content = (
                self._run_tool_loop(model, messages, max_tokens, usage, tool_call_log)
                if self.tools
                else self._complete(model, messages, max_tokens, usage)
            )
            elapsed = time.perf_counter() - start
            update_agent_status(self.name, "complete", elapsed)
            logger.info(
                "✓ %s completed in %.2fs | model: %s | output: %d chars | tokens: %d+%d",
                self.name, elapsed, model, len(content),
                usage["prompt"], usage["completion"],
            )
            _emit_trace({
                "agent": self.name, "model": model, "status": "complete",
                "elapsed": round(elapsed, 2), "usage": dict(usage),
                "tool_calls": tool_call_log,
                "input_chars": len(user_content), "output": content,
            })
            return content
        except Exception as exc:
            elapsed = time.perf_counter() - start
            update_agent_status(self.name, "error", elapsed)
            logger.error("✗ %s failed after %.2fs: %s", self.name, elapsed, str(exc)[:120])
            _emit_trace({
                "agent": self.name, "model": model, "status": "error",
                "elapsed": round(elapsed, 2), "usage": dict(usage),
                "tool_calls": tool_call_log,
                "input_chars": len(user_content), "output": str(exc)[:500],
            })
            return (
                f"[{self.name.upper().replace('_', ' ')} UNAVAILABLE — "
                f"analysis for this section could not be completed. Error: {str(exc)[:80]}]"
            )

    # -- internals -----------------------------------------------------------
    def _complete(self, model: str, messages: list[dict],
                  max_tokens: Optional[int], usage: dict) -> str:
        """One plain completion (no tools). Accumulates token usage in place."""
        resp = _create_with_retry(
            model=model,
            messages=messages,
            max_tokens=max_tokens or self.max_tokens,
            temperature=self.temperature,
        )
        step = _usage_of(resp)
        usage["prompt"] += step["prompt"]
        usage["completion"] += step["completion"]
        return (resp.choices[0].message.content or "").strip()

    def _run_tool_loop(self, model: str, messages: list[dict], max_tokens: Optional[int],
                       usage: dict, tool_call_log: list[dict]) -> str:
        """
        The agent loop: reason → (optionally) call tools → observe → repeat.

        Accumulates token usage and a record of every tool call (for the trace).
        Degrades gracefully: if the provider rejects the `tools` parameter
        (not every endpoint supports function-calling), we fall back to a plain
        completion so the agent still produces an answer.
        """
        schemas = [t.as_openai_schema() for t in self.tools]
        by_name = {t.name: t for t in self.tools}

        for _ in range(_MAX_TOOL_ITERS):
            try:
                resp = _create_with_retry(
                    model=model,
                    messages=messages,
                    tools=schemas,
                    tool_choice="auto",
                    max_tokens=max_tokens or self.max_tokens,
                    temperature=self.temperature,
                )
            except Exception as exc:
                logger.warning(
                    "tool-calling unavailable for %s (%s) — plain completion",
                    self.name, str(exc)[:80],
                )
                return self._complete(model, messages, max_tokens, usage)

            step = _usage_of(resp)
            usage["prompt"] += step["prompt"]
            usage["completion"] += step["completion"]

            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                return (msg.content or "").strip()

            # Record the assistant's tool-call turn, then execute each call.
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                result = self._invoke_tool(by_name, tc.function.name, tc.function.arguments)
                tool_call_log.append({
                    "name": tc.function.name,
                    "args": (tc.function.arguments or "")[:500],
                    "result_chars": len(result),
                    "result": result[:1500],  # the raw observation (for traces + eval grounding)
                })
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        # Hit the iteration cap — force a final answer from what we've gathered.
        logger.warning("%s hit tool-iteration cap (%d)", self.name, _MAX_TOOL_ITERS)
        return self._complete(model, messages, max_tokens, usage)

    def _invoke_tool(self, by_name: dict, name: str, raw_args: str) -> str:
        """Execute one tool call and return its result as text. Never raises."""
        tool = by_name.get(name)
        if tool is None:
            return f"[tool '{name}' is not available to this agent]"
        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            args = {}
        try:
            logger.info("→ %s calling tool %s(%s)", self.name, name, args)
            return str(tool.fn(**args))
        except Exception as exc:
            logger.error("tool %s failed: %s", name, exc)
            return f"[tool '{name}' error: {str(exc)[:80]}]"


# ===========================================================================
# 6. THE REGISTRY  — Vigil's 8 components, declared in one place
# ===========================================================================
# Honest framing (D3): of these 8, only 2 are true agents (the tool-using scouts
# signal_harvester + market_oracle); the rest are an LLM router (orchestrator),
# 4 analyst steps, and a strategy step. Each entry is a model + role + memory
# scope + tools. The orchestration that connects them lives in agent_pipeline.py
# via the five patterns: routing, parallelization, prompt-chaining,
# orchestrator-worker, and evaluator-optimizer.

_SONNET = "claude-sonnet-4-6"
_HAIKU = "claude-haiku-4-5-20251001"

AGENTS: dict[str, Agent] = {
    "orchestrator": Agent(
        name="orchestrator",
        role="Lead agent — classifies the query's intent and delegates to specialists (routing + orchestrator-worker).",
        model=_SONNET,
        memory="user query + profile + conversation history",
        max_tokens=1500,
    ),
    "signal_harvester": Agent(
        name="signal_harvester",
        role="Data scout — gathers the raw market/news signals the analysts reason over.",
        model=_HAIKU,  # fast + cheap: scouting, not deep reasoning
        memory="profile + live market/news data",
        max_tokens=2500,
    ),
    "narrative_intel": Agent(
        name="narrative_intel",
        role="Narrative analyst — reads the media/sentiment story around the company.",
        model=_SONNET,
        memory="profile + Signal Harvester output",
    ),
    "macro_watchdog": Agent(
        name="macro_watchdog",
        role="Macro analyst — rates, FX, and policy exposure.",
        model=_SONNET,
        memory="profile + Signal Harvester output",
    ),
    "competitive_intel": Agent(
        name="competitive_intel",
        role="Competitive analyst — rivals, moat, and market-position risk.",
        model=_SONNET,
        memory="profile + Signal Harvester output",
    ),
    "risk_synthesizer": Agent(
        name="risk_synthesizer",
        role="Risk synthesizer — fuses all upstream analysis into one scored (0–100), tiered briefing.",
        model=_SONNET,
        memory="profile + all specialist outputs",
    ),
    "strategy_commander": Agent(
        name="strategy_commander",
        role="Strategy commander — turns the risk picture into a prioritized action playbook.",
        model=_SONNET,
        memory="profile + Risk Synthesizer output",
    ),
    "market_oracle": Agent(
        name="market_oracle",
        role="Market oracle — fast, focused verdict on a single ticker/question.",
        model=_HAIKU,  # fast path: single-shot verdict
        memory="profile + live data for one ticker",
    ),
}

# The Risk Evaluator is a *critic*, deliberately kept OUT of the 8-component briefing
# registry: it doesn't author analysis, it grades it. It powers the optional
# evaluator-optimizer pattern (gated by VIGIL_ENABLE_EVALUATOR) and is not part
# of the live briefing flow — hence a standalone Agent, not an AGENTS entry.
RISK_EVALUATOR = Agent(
    name="risk_evaluator",
    role="Critic — grades the Risk Synthesizer's briefing against a rubric and "
         "can trigger one revision (the evaluator-optimizer pattern).",
    model=_HAIKU,  # cheap+fast: judging is lighter than authoring
    memory="Risk Synthesizer output + the upstream signals",
    max_tokens=600,
    temperature=0.1,  # a critic should be near-deterministic
)

# The Document Distiller is a utility agent (also outside the briefing registry):
# /ingest runs it once per workspace doc to build the wiki notes that ground
# future briefings. Extraction, not judgment — hence Haiku at low temperature.
DOC_DISTILLER = Agent(
    name="doc_distiller",
    role="Librarian — distills one user document into a compact knowledge note "
         "(index, not replacement; originals stay readable via tools).",
    model=_HAIKU,
    memory="one workspace document",
    max_tokens=800,
    temperature=0.1,
)

# All 8 component names, in pipeline order (kept for status seeding / iteration).
ALL_AGENTS: list[str] = list(AGENTS.keys())

# Seed the status registry now that we know the agent set.
AGENT_STATUSES.update({a: "idle" for a in ALL_AGENTS})
AGENT_ELAPSED.update({a: None for a in ALL_AGENTS})

# NOTE: tools are attached to the scout agents by `tools.py` (imported by the
# entry points). agent_core deliberately does NOT import tools — that keeps this
# module dependency-light and avoids a circular import.
