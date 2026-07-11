# How Vigil's Agents Work — Architecture & Design Decisions

> The interview-ready walkthrough: **what** each agent is, **how** they work
> together, and **why** it's built this way. Every claim here matches the code —
> that's a project guardrail, not a hope. Decisions cite `docs/MASTER_PLAN.md`
> (D#) where the full reasons canvas lives.

## 0. The honest one-liner

**"A routed multi-agent workflow: 2 tool-using agents, an LLM router, 4 focused
analyst steps, a strategy step, and an optional critic — orchestrated
framework-free with deterministic guardrails."**

Note what this *doesn't* say: it doesn't call all 8 components "autonomous
agents." By the standard definition (a model **in a loop with tools**), only the
scouts qualify. Knowing — and naming — the difference between an agent and a
workflow step is the point (D3). Production guidance is unanimous that fixed
steps inside a routed workflow beat "agents everywhere" for reliability.

## 1. What an agent IS here (`agent_core.py`)

Not a prompt — a component with a declared anatomy, one dataclass instance each:

| Part | Meaning | In code |
|---|---|---|
| **Model** | right-sized LLM: Haiku to fetch/judge, Sonnet to reason (D4) | `Agent.model` |
| **Instructions** | role, rules, **JSON output contract** | `prompts/<name>.txt` |
| **Tools** | functions it may CALL to observe the world | `Agent.tools` |
| **Memory** | the context scope it's allowed to read | `Agent.memory` |
| **Guardrails** | token budget, temperature, retry, iteration cap | `max_tokens`, … |

`Agent.run()` executes one agent. Tool-using agents run the canonical loop —
**reason → call tool → observe → repeat** (capped at 5; degrades to a plain
completion if the provider lacks function-calling). Every LLM call retries
transient failures (3×, exponential backoff); auth errors fail fast.

## 2. The roster

| Component | Kind | Model | Tools |
|---|---|---|---|
| Orchestrator | LLM router | Sonnet | — (routes 1 of 7 intents; deterministic keyword backstop when it fails) |
| **Signal Harvester** | **agent** | Haiku | market pulse, sectors, headlines, **search/read the user's docs** |
| Narrative Intel | analyst step | Sonnet | — |
| Macro Watchdog | analyst step | Sonnet | — |
| Competitive Intel | analyst step | Sonnet | — |
| Risk Synthesizer | analyst step | Sonnet | — (outputs the scored JSON briefing) |
| Strategy Commander | analyst step | Sonnet | — |
| **Market Oracle** | **agent** | Haiku | stock data, market pulse |
| Risk Evaluator | critic (opt-in) | Haiku | — (evaluator-optimizer, `VIGIL_ENABLE_EVALUATOR`) |
| Doc Distiller | utility | Haiku | — (powers `/ingest`) |

**Why only scouts get tools:** tools belong where an agent must *observe the
world*. Analysts reason over what the scouts found — giving everyone tools is
theater, not architecture.

## 3. The five orchestration patterns (all real, all locatable)

1. **Routing** — Orchestrator classifies into 7 intents; each activates a
   different subset (an investment question wakes 2 agents, not 6). A
   deterministic keyword backstop routes when the LLM router fails ("hard-code
   what you can": code is more reliable than inference).
2. **Parallelization** — Narrative + Macro + Competitive share one input and run
   simultaneously (`ThreadPoolExecutor`).
3. **Prompt chaining with gates** — Signal → analysts → Synthesizer → Strategy.
   Because errors compound across chained steps (95%/step ≈ 77% over 5), each
   wave's output passes a **validation gate**: degenerate output is replaced with
   an explicit data-gap note so downstream steps never reason over garbage.
4. **Orchestrator-workers** — the router leads; specialists work.
5. **Evaluator-optimizer** — the critic grades the synthesis against a rubric
   (scored? grounded? complete? honest?) and can trigger exactly one revision.
   Off by default: it costs a round trip, and that's the user's trade to make.

## 4. Memory — four layers, all explicit

- **Working**: the (action, observation) pairs inside a tool loop, and
  `specialist_outputs` flowing between waves.
- **Session**: profile + conversation history, persisted by the CLI, fed back
  into every run. The engine itself stays a pure function.
- **Episodic**: `score_history` — the risk trend over time (`/trend` sparkline,
  deltas on the welcome line, `vigil monitor` thresholds).
- **Knowledge base**: the user's own documents. `workspace/docs/` is searchable
  and readable **by the agents as tools**; `/ingest` distills docs into
  `workspace/wiki/` notes that join every run's context. Distillation is honest
  about being an index: summaries are lossy, so originals stay readable — the
  wiki note points at the source, never replaces it (D9).

## 5. Guardrails — deterministic before model judgment

- **Structured seams**: agents answer in JSON contracts; parsing is JSON-first
  with legacy regex fallback; malformed fields degrade individually (D5).
- **Injection defense**: all external text (headlines, doc contents, stock
  names) is flattened, capped, and wrapped in an `EXTERNAL_DATA` envelope marked
  "data, not instructions." Doc access is path-traversal-safe. Tools are
  read-only by design — the blast radius of a bad run is a wrong analysis, never
  a changed system.
- **No fabrication**: a missing ticker, an empty workspace, a dead API — every
  path returns an honest "not available" instead of an invented number. This is
  tested, not aspirational.
- **Failure isolation**: one agent's error becomes a labeled placeholder; the
  briefing continues with a gap instead of sinking.

## 6. Observability & evaluation — the demo/production divide

- **Traces**: every run writes JSONL (`traces/run-*.jsonl`) — per step: model,
  latency, token usage, tool calls with args, full output. Any briefing is
  replayable; `token_usage` and `trace_path` ride in every result; the CLI
  footer prints cost-per-run.
- **Tests**: 84 offline pytest tests — unit (tools, parsing, retry, gates),
  integration (full pipeline with scripted LLM), adversarial (malicious
  headlines, path traversal, garbage JSON, injection-shaped queries), and
  console session tests.
- **Golden evals**: 15 scenarios covering all 7 intents + adversarial cases;
  deterministic structural checks plus an **LLM-as-judge** scoring faithfulness,
  completeness, and sufficiency; cost and latency per scenario
  (`evals/run_evals.py`).

## 7. Why framework-free (the deliberate one)

No LangChain, no LangGraph (D2). The strongest practitioner evidence says simple,
composable patterns beat complex frameworks, and reliability comes from
architecture — modular design, state management, deterministic guardrails — not
from framework machinery. Here, every mechanism in sections 1–6 is plain Python
you can read in an afternoon: the loop is ~60 lines, the router is a function,
the gates are `if` statements. That legibility *is* the feature.

## 8. One engine, two front-ends

`run_pipeline()` is a pure function; persistence belongs to callers.
- **Console** (`vigil`): wizard-built profile, live agent-wave view (statuses
  stream from the engine's listener), `/brief`, `/trend`, `/ingest`, `/export`,
  and a cron-able `vigil monitor` with exit-code alerting.
- **MCP** (`vigil-mcp`): `risk_briefing` and `market_verdict` exposed to Claude
  Desktop/Cursor — an AI can wield the whole workflow as two tools.

Adding an agent = a prompt file + a registry entry (+ tools if it observes the
world). Adding a front-end = another caller of the same pure function.
