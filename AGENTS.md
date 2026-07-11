# Vigil — Agents & Components

> The full walkthrough (anatomy, patterns, memory, guardrails) lives in
> **[docs/AGENT_ARCHITECTURE.md](docs/AGENT_ARCHITECTURE.md)**. This is the quick roster.

**Honest framing:** Vigil is a *routed multi-agent workflow* — **2 tool-using
agents**, an LLM router, 4 analyst steps, a strategy step, and an optional critic.
Only the scouts are "agents" by the strict definition (a model in a loop with
tools); the rest are focused workflow steps. Naming them precisely is the point.

| Component | Kind | Model | Tools | Job |
|---|---|---|---|---|
| Orchestrator | LLM router | Sonnet | — | Classifies 1 of 7 intents, routes to specialists |
| **Signal Harvester** | **agent** | Haiku | market pulse, sectors, headlines, user-doc search/read | Gathers the raw signals |
| Narrative Intel | analyst step | Sonnet | — | Media/sentiment story |
| Macro Watchdog | analyst step | Sonnet | — | Rates, FX, policy exposure |
| Competitive Intel | analyst step | Sonnet | — | Rivals, moat, positioning |
| Risk Synthesizer | analyst step | Sonnet | — | Fuses everything → scored (0–100) tiered JSON briefing |
| Strategy Commander | analyst step | Sonnet | — | Prioritized action playbook |
| **Market Oracle** | **agent** | Haiku | stock data, market pulse | Fast BUY/WAIT/CAUTION/AVOID verdict |
| Risk Evaluator | critic (opt-in) | Haiku | — | Grades the synthesis; can trigger one revision |
| Doc Distiller | utility | Haiku | — | `/ingest`: distills user docs into the knowledge base |

**The 7 intents** the Orchestrator routes to: `FULL_BRIEFING`, `INVESTMENT_QUERY`,
`MACRO_FOCUS`, `COMPETITIVE_FOCUS`, `MARKET_PULSE`, `DECISION_SUPPORT`, `SCENARIO`
— each activates a different subset (an investment question wakes 2 components,
not 6), with a deterministic keyword backstop when the LLM router fails.

Each component is one declarative `Agent` in the registry in `agent_core.py`.
Add one = a prompt file in `prompts/` + a registry entry (+ tools if it must
observe the world). The orchestration that connects them is in `agent_pipeline.py`.
Prompt output-format sections are JSON contracts the parser depends on, so prompt
changes are product changes.
