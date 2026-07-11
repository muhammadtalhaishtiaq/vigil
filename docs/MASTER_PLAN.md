# VIGIL — Master Plan (the single living document)

> **The one document.** Vision, use cases, every decision with its reason, and the
> ordered task plan — all back-linked (UC# ↔ D# ↔ T#). Add/update here; never fork
> planning into other files. Supersedes: REVAMP_PLAN.md, WIKI_AUDIT.md's plan
> section, CONSOLE_PLAN.md. Standards source: the agent-development wiki
> (`~/Documents/Me/vaults/agent-development/wiki`).

---

## 1. Vision

**Vigil is a multi-agent financial-risk copilot that lives in your terminal and
knows your company.** Describe your company once, optionally drop your documents in
a folder, and every question — "how exposed are we to the new EU rules?" — is
answered by specialized agents pulling **live market data + your own docs**,
reasoning **about your situation**, visibly, on your machine, with your keys.

Open source. Terminal + MCP only (no web app, no accounts — nothing to trust but
your own computer). Built framework-free to the production standards of the
agent-development wiki, and honest about every claim.

**The honest architecture line (use verbatim everywhere):** "A routed multi-agent
workflow: 2 tool-using agents (Signal Harvester, Market Oracle), an LLM router
(Orchestrator), 4 focused analyst steps, a strategy step, and an optional critic
(evaluator-optimizer) — orchestrated framework-free with deterministic guardrails."

## 2. Audiences (priority order)

1. **A1 — Founder/operator (non-dev):** installs in one line, answers a wizard,
   asks questions in plain language.
2. **A2 — Developers:** read/extend the architecture; add agents/tools/domains.
3. **A3 — AI-tool users:** plug the MCP server into Claude Desktop/Cursor.
4. **A4 — Interviewers/recruiters:** watch the demo, read the architecture story.

## 3. Use cases

| # | Use case | Flow | Serves |
|---|---|---|---|
| UC1 | Weekly risk check-in | `vigil` → `/brief` → score + trend delta + actions | A1 |
| UC2 | Quick investment verdict | `vigil verdict "buy TSLA?"` or in-console | A1 |
| UC3 | What-if scenarios | "what if rates rise 100bps?" (SCENARIO intent) | A1 |
| UC4 | **Grounded-in-my-docs analysis** | drop docs in `workspace/` → `/ingest` → answers cite user's own material | A1 |
| UC5 | Scheduled monitoring | cron runs `vigil monitor` → report file + nonzero exit on risk jump | A1 |
| UC6 | Exportable reports | `/export` → markdown report in `workspace/reports/` | A1 |
| UC7 | Interview demo | `/agents` roster → `/brief` live wave view → `/trend` | A4 |
| UC8 | MCP tools from Claude/Cursor | one-paste config → `risk_briefing`, `market_verdict` | A3 |
| UC9 | Build-your-own on the architecture | read AGENT_ARCHITECTURE.md → add an agent = prompt + registry entry (+ tools) | A2 |

## 4. Decisions & Reasons canvas

Every decision links to the use cases it serves, the wiki principle behind it, and
the tasks that implement it. **Don't relitigate without the user.**

| # | Decision | Why (reason) | Wiki principle | Serves | Tasks |
|---|---|---|---|---|---|
| D1 | Terminal + MCP only; no web app | Local execution with user's own keys removes the auth/data-trust barrier that killed the web version; terminal makes agent latency feel like visible work | Start small, constrained scope | UC1–UC8 | done |
| D2 | Framework-free engine | Simple composable patterns beat frameworks; everything debuggable; `pip install` and read | Chrono/Anthropic: simplest that works | UC9 | done |
| D3 | 2 true agents + routed workflow steps (honest naming) | Only scouts need to observe the world; analysts reason over scout output. Saying "8 agents" where 6 are steps violates honesty and weakens the interview story | Agents-vs-workflow distinction; hard-code what you can | UC7, UC9 | T3 |
| D4 | Model routing: Haiku scouts/critic, Sonnet analysts | Pay for reasoning, not fetching; cost/latency are first-class | Fit-for-purpose beats most-powerful | all | done |
| D5 | Structured JSON contracts at every LLM/code seam | The seam where LLM output meets code must be typed; regex is a fallback, not the path | Structured outputs principle | all | done |
| D6 | Traces + tests + golden evals before features | Can't improve or trust what you can't measure; evaluation is the demo/production divide | The wiki's strongest consensus | UC7, UC9 | done, T1 |
| D7 | Deterministic guardrails: routing backstop, gates, retry, injection envelope | Don't rely on model judgment for safety-critical steps; errors compound across chained steps | Guardrails ch.; error-compounding math | all | done, T1 |
| D8 | **`workspace/` folder + docs as a TOOL** | User docs are the highest-value grounding; "long-term memory is almost always implemented as another tool" — same pattern as market data, so it's consistent and testable | Memory/context engineering | UC4 | T4 |
| D9 | **`/ingest` → distilled wiki notes (NOT a "knowledge graph")** | LLM-built index of user docs using *their* key; originals stay readable via the tool because summaries are lossy. Calling it a knowledge graph in v1 would be a false claim | Lossy-summarization warning; honesty rule | UC4 | T5 |
| D10 | **`vigil monitor` one-shot + cron recipe (no daemon)** | The OS already has a scheduler; a daemon is deployment burden and failure surface. One-shot + exit code = composable, testable | Treat agents like software | UC5 | T6 |
| D11 | Risk-trend memory in session | A score means little without its history; "61, down from 68" is the product's stickiest feature | Episodic memory | UC1, UC5, UC7 | T2 |
| D12 | **Distribution: pyproject entry point; pipx/uvx from git; PyPI later** | One-line install for anyone without PyPI release maintenance; publishing is cheap to add once stable | Start small; design for impermanence | A1–A4 | T7 |
| D13 | Reports as markdown files in `workspace/reports/` | Terminal-native, diffable, greppable, zero deps; PDF is polish not substance | Simplicity | UC6 | T6 |
| D14 | Keep `.claude/` workflows polished (career-ops pattern) | Contributors opening the repo in a coding agent get guided verify/audit workflows — cheap, open-source-friendly | Agent Ops | A2 | T7 |
| D15 | Evaluator critic stays opt-in | Quality-vs-latency is a user trade-off, not ours to force | Evaluator-optimizer pattern | UC1 | done |
| D16 | Every LLM number labeled analysis + disclaimer | Financial domain; trust through honesty is the product's moat | Guardrails; EU-AI-Act spirit | all | done |

## 5. What "DONE (v1)" means

A stranger can, without help:
1. Install with one command (pipx/uvx from git) → `vigil` works. (T7)
2. Run `vigil`: wizard → profile saved; optionally drop docs in `workspace/docs/`
   and run `/ingest`. (done + T4/T5)
3. Ask anything; watch the agent wave; answers grounded in live data **and their
   docs**, with sources visible. (T4)
4. See trend (`/trend`), export a report (`/export`), cron `vigil monitor`. (T2/T6)
5. Paste one MCP snippet → use Vigil from Claude Desktop. (done)
6. Devs: 46+ tests green, `run_evals.py` passes live, architecture doc matches code. (T1, T8, T3)
7. Repo public with honest README; leaked key revoked; honesty audit clean. (T9, user)

## 6. Task plan (ordered — tick as landed)

**Already done (verified):** engine (agents/tools/loop/retry/gates/hygiene),
JSON contracts, tracing+tokens, 46 tests, eval harness, MCP server, interactive
console w/ wizard + live wave view, web app removed.

- [x] **T1 — Phase B tests** (D6, D7): retry, gates, sanitize/envelope, `_run_footer`. Suite green. ✅ 2026-07-11
- [x] **T2 — Risk-trend memory** (D11 → UC1): `score_history` (last 26), delta on welcome + after runs, `/trend` sparkline. Tested. ✅ 2026-07-11
- [x] **T3 — Honest reframing** (D3): README rewritten (product story, one-line install, MCP snippet, workspace, cron recipe), CLAUDE.md rewritten (terminal+MCP reality, continuity section), AGENT_ARCHITECTURE.md rewritten. ✅ 2026-07-11
- [x] **T4 — Workspace + docs tool** (D8 → UC4): `workspace/{docs,wiki,reports}/`, `search_company_docs`/`read_company_doc` (md/txt/csv, traversal-safe, enveloped), attached to signal_harvester. Tested. ✅ 2026-07-11
- [x] **T5 — `/ingest` wiki notes** (D9 → UC4): DOC_DISTILLER agent + console command; notes → `_wiki_context()` joins orchestrator + specialist context. Tested. ✅ 2026-07-11
- [x] **T6 — Monitor + export** (D10, D13 → UC5, UC6): `vigil monitor` (exit 2 on jump ≥ threshold), `/export`, reports in `workspace/reports/`. Tested. ✅ 2026-07-11
- [x] **T7 — Distribution** (D12, D14): `pyproject.toml`, `vigil` + `vigil-mcp` entry points, prompts ship in wheel, cwd-based paths; verified from outside the repo. ✅ 2026-07-11
- [~] **T8 — USER GATE: live test** (D6): LARGELY DONE (2026-07-11, live AIML key).
      ✅ `vigil verdict` end-to-end (real TSLA data, tool-calling works on AIML).
      ✅ full `/brief` — all 6 waves, Wave-2 parallelism confirmed via trace,
         both JSON contracts (orchestrator + synthesizer) held on live provider.
      ✅ eval harness runs live; **it caught two real issues, both addressed:**
         (a) HARNESS FIX (done): judge was penalizing real tool-fetched numbers
             from its own stale memory → now fed the run's tool outputs as ground
             truth (traces enriched with tool `result`); invest-ticker 2→3, judge
             confirms "faithfully uses all ground-truth data".
         (b) VIGIL FIX (partial): tool-less analysts state forward-looking
             specifics (compliance costs, probabilities, "smart money" theses) as
             fact. Prompts strengthened (hedge labels, LOW/MED/HIGH, examples) —
             improved framing but faithfulness not yet at target. **OPEN:**
             prompt-hedging convergence is an iterative tuning task; do it against
             a defined eval bar, not a blind live-token loop. Tracked as T8b.
- [ ] **T8b — Faithfulness convergence** (D16 → guardrail #3): iterate the 3
      analyst + oracle + synthesizer prompts against `run_evals.py` until median
      judge faithfulness ≥ the agreed bar. Needs the eval-bar sign-off (§7). Each
      iteration costs a live run — batch deliberately.
- [~] **T9 — Ship**: ✅ verify-vigil pass · ✅ honesty-auditor pass (6 findings
      fixed: CONTRIBUTING/AGENTS rewritten, "8 agents"→"8 components", invented
      action deadline removed, fear/greed UNKNOWN) · ✅ honest 6-commit series on
      `revamp/single-process` (2026-07-11). **OPEN (USER GATE):** push + PR to
      main — user's approval. Then LinkedIn blurb from the honest line.

## 7. Standing user actions
- ⚠️ **REVOKE the leaked AIML key** (git history is public) — still pending!
- ✅ **Eval bar set (2026-07-11): median LLM-judge faithfulness ≥ 4/5.** This is
  the target for T8b (analyst faithfulness convergence, deferred post-ship per
  user decision "ship now, converge later").

## 8. Roadmap — v2 / v3 (directional; re-planned after v1 feedback)

Rule (wiki): complexity is **earned with evidence**, not ambition. Each version
ships only if the previous one proved the demand.

**v2 — earned intelligence** (needs v1's foundation to exist)
- **PDF ingestion** — real financial docs are PDFs; needs the T4/T5 pipeline first
- **Analyst tools** — competitive_intel pulls rivals' stock data; narrative_intel
  pulls company-specific headlines (4–5 true agents, each justified)
- **True knowledge structure** — entity extraction + cross-doc links over the
  wiki notes: the "knowledge graph" earned honestly (D9)
- **Multiple profiles + compare** — "Acme vs. rival" side-by-side briefings
- **Evals v2** — golden set grown from real usage; judge calibrated vs human
  review; metrics-driven gate for prompt changes (change prompt → eval must pass)
- **PyPI publish + GitHub Actions CI** (tests + mocked evals on every PR)
- Demo GIF / short screencast for README

**v3 — the ecosystem** (only if v1/v2 prove demand)
- **More senses** — SEC/EDGAR filings, earnings calendars, FX/rates feeds as tools
- **Watch mode with notifications** — `vigil monitor` pushes via user's channels
  (email/Slack webhook), still cron-driven, still no daemon
- **MCP resources** — expose traces/reports/trend to MCP clients, not just tools
- **A2A readiness** — Vigil as a specialist agent other agents delegate to
- **Domain packs** — the config-defined "bring your own domain" layer (legal risk,
  supply-chain risk…) — the "agent OS" ambition, earned last, not first
- Homebrew/binaries · `.codex`/`.gemini` folders if the community asks

## 9. Later / explicitly not planned
- Web app or hosted SaaS (D1 — the whole point is local trust)
- Fabricated demo data of any kind (guardrail #1, forever)
