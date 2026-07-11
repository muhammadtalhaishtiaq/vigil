# Vigil vs. the Agent-Development Wiki — Brutal Audit

> Audit of Vigil (2026-07-10) against `~/Documents/Me/vaults/agent-development/wiki`
> (Google whitepaper, Chrono, MLflow, Dataiku, Nir Diamant synthesis). No mercy,
> no marketing. Verdicts: ✅ meets the bar · ⚠️ partial · ❌ missing.

## Scorecard

| Wiki concept | Verdict | Evidence |
|---|---|---|
| Agent = model in a loop with tools | ⚠️ | Only 2 of 8 "agents" (Signal Harvester, Market Oracle) run the real think→act→observe loop. The other 6 are single focused LLM calls — workflow steps, not agents, by the wiki's definition. |
| Right-sized models, routing | ✅ / ⚠️ | Haiku scouts + Sonnet analysts matches "don't crack a nut with a sledgehammer" — but the choice was never *tested on our task*. It's vibes, not measurement. |
| Deterministic beats LLM where knowable | ✅ | Framework-free engine, hard-coded wave sequencing, keyword routing fallback, `/brief` bypasses classification. Matches Chrono/MLflow exactly. |
| Tools, function calling, MCP | ✅ | Real tool loop (capped), OpenAI function schemas, MCP server, read-only tool surface. |
| Structured outputs at the LLM/code seam | ❌ | Regex over markdown. The wiki calls typed outputs "the seam where LLM reasoning hands off to deterministic code." Known deferral — now overdue. |
| Working + session memory | ✅ | (Action, observation) pairs in the loop; profile+history persisted. |
| Long-term memory / episodic | ❌ | No memory of past briefings. The product's most valuable memory — *risk trend over time* ("you were 61, now 58") — doesn't exist. |
| Error compounding awareness | ❌ | FULL_BRIEFING = 5 sequential LLM steps ≈ 77% success at 95%/step, per Chrono's math — and we have **no inter-step validation**. Garbage from the Harvester flows straight into 4 downstream agents. |
| Retry with backoff | ❌ | One transient 429/timeout → whole section reports UNAVAILABLE. Wiki: 3 attempts with backoff is table stakes. |
| Graceful degradation | ✅ | Genuinely good: per-agent safe-fail, honest tool errors, no-keys boot, no fabrication. |
| Guardrails: action classification | ✅ (by luck) | All tools are read-only — the "safe" class. True but **undocumented as a design guarantee**. |
| Guardrails: confidence thresholds | ⚠️ | Oracle outputs VERDICT_CONFIDENCE but nothing *acts* on it. No agent ever says "I'm not sure — clarify." |
| Guardrails: input filtering | ❌ | **Live news headlines enter agent context unfiltered — an indirect prompt-injection vector.** A malicious headline is instructions smuggled into the context. Blast radius is "wrong analysis" (read-only system), but the wiki says validate both boundaries. |
| Rate/cost limits | ⚠️ | Per-run cost is architecturally bounded (fixed waves, max_tokens, tool cap = good). But **zero token/cost tracking** — we can't even report cost per briefing. |
| Logging → tracing | ❌ | `logger.info` lines only. No structured, replayable trace (prompt, output, tokens, timing per step). Debugging a bad briefing is guesswork — the exact failure MLflow names. |
| **Evaluation** | ❌❌ | **The biggest violation.** No test suite in the repo (my verifications were uncommitted scratchpad scripts). No golden dataset. No LLM-as-judge eval. No adversarial tests. No metrics (task completion, faithfulness, cost/task). We cannot answer "is a briefing good?" or safely change a prompt. The wiki's strongest consensus, and we fail it outright. |
| Eval probes in-workflow | ⚠️ | The Risk Evaluator critic *is* one in-workflow probe (matches MLflow/NIST pattern) — but it's off by default and it's the only one. |
| Generator–critic pattern | ✅ | Evaluator-optimizer implemented, gated, tested (mocked). |
| CI/CD, environments | ❌ | No CI. Nothing runs tests on change (there are no tests to run). |
| Least privilege / secrets | ✅ / ⚠️ | Env-only keys, read-only tools. ⚠️ The leaked key in git history is STILL unrevoked (user action, pending since 07-04). |
| Define success criteria before building | ❌ | Never done. "Good briefing" has no measurable definition. |
| Start small, low-risk, augment humans | ✅ | Read-only advisory scope, disclaimers, human reads everything. Genuinely compliant. |
| Honest claims (our own guardrail #2) | ⚠️ | "8 agents" oversells by the wiki's definition. Honest framing: **a routed multi-agent workflow — 2 tool-using agents, an LLM router, 5 focused specialist steps, 1 critic.** That's *more* impressive to a serious interviewer, not less. |

## What we got right (keep, and say out loud)

Framework-free simple-composable architecture (Chrono + Google's synthesis is
exactly our design); model routing by task class; deterministic control flow with
LLM reserved for ambiguity; MCP adopted early; read-only tool surface as a safety
property; graceful degradation everywhere; constrained low-risk first use case.

## The brutal summary

Vigil is an honest, well-architected **prototype** with production *instincts*
(degradation, secrets, scope) but **no measurement layer at all**. The wiki's
single loudest lesson — from every source — is that evaluation and observability
are what separate a demo from a system. We built the agent loop, the tools, the
patterns, and the front-ends, and skipped the part that tells us whether any of
it is good. That is the exact "impressive demo as warning sign" MLflow describes.

## The firm plan

**Phase A — Measurement first (the wiki's core demand)**
1. **Structured outputs** — JSON contract per agent (kill the regex). The seam
   fix that everything else builds on.
2. **Run traces** — structured JSONL per pipeline run: per step, the input,
   model, output, tokens, latency. Replayable; feeds evals; shown by `/trace`.
3. **Test suite in the repo** (pytest, committed): unit (tools, parsers,
   routing), integration (mocked pipeline), adversarial (malicious headline,
   garbage ticker, empty profile), the promoted scratchpad tests.
4. **Golden dataset + LLM-as-judge eval** — ~15 scenarios with expected
   properties; judge scores faithfulness/completeness/sufficiency; cost & latency
   reported per scenario. This also *is* the live-key test plan.

**Phase B — Reliability hardening**
5. Retry with exponential backoff (3×) on transient LLM/tool failures.
6. Inter-step validation gates between waves (cheap deterministic checks;
   degrade to a smaller flow instead of propagating garbage).
7. Input hygiene: external data (headlines) wrapped in delimited data-only
   blocks, length-capped, with explicit "data, not instructions" framing.
8. Token/cost capture per run → result dict, trace, CLI footer
   ("$0.04 · 21k tokens").

**Phase C — Product & honesty**
9. Risk-trend memory: store each briefing's score/date per profile; show the
   delta ("58, down from 61 on Jul 2").
10. Reframe all docs to the honest architecture description (workflow + 2 true
    agents + router + critic) — stronger interview story, zero asterisks.
11. Console per the approved CONSOLE_PLAN wireframes → live key test → README.

**Standing items**: revoke the leaked AIML key (user, still pending!);
success criteria to define with user: e.g. "eval suite ≥ 4/5 median judge score,
briefing < 90s, cost < $0.10/briefing."
