# ⚡ VIGIL-your terminal's financial-risk copilot

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![Runs in Claude Code — no API key](https://img.shields.io/badge/Claude%20Code-no%20API%20key-8A63D2?style=flat)](#3--in-claude-code--no-api-key)
[![MCP server](https://img.shields.io/badge/MCP-server-purple?style=flat)](#2--from-claude-desktop--cursor-mcp)
[![Tests](https://img.shields.io/badge/tests-86%20passing-green?style=flat)](tests/)
[![MIT License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

**Describe your company once. Drop your documents in a folder. Then ask anything —
"how exposed are we to the new EU rules?" — and watch specialized agents pull live
market data *and your own docs* to build a scored, tiered risk briefing about
*your* situation.** All local: your machine, nothing to sign up for — and it can
run entirely inside Claude Code with **no API key at all**.

Born at a lablab.ai hackathon (Top-10 finalist), then rebuilt twice: from nine
microservices to one honest process, and from a web app to a terminal + MCP tool
built to production-agent standards — tests, evals, traces, guardrails.

## What it actually is (the honest architecture)

A **routed multi-agent workflow**: 2 tool-using agents (Signal Harvester, Market
Oracle), an LLM router (Orchestrator), 4 focused analyst steps, a strategy step,
and an optional critic (evaluator-optimizer) — orchestrated **framework-free**
(no LangChain) with deterministic guardrails. Why no framework? The evidence says
simple, composable patterns beat frameworks — and here you can read every mechanism.
Full walkthrough: [docs/AGENT_ARCHITECTURE.md](docs/AGENT_ARCHITECTURE.md).

```
 you ──► Orchestrator (routes by intent; answers chat/simple Qs itself)
              │
              ▼
      Signal Harvester ──► calls tools: market pulse · sectors · headlines
              │                         + YOUR docs (search/read)
              ▼
   Narrative │ Macro │ Competitive     (3 analysts, in parallel)
              ▼
      Risk Synthesizer ──► score 0-100 + tier   [◄─ optional critic pass]
              ▼
     Strategy Commander ──► prioritized actions
```

## Three ways to run it

| | How | API key? |
|---|---|---|
| **1. CLI** | `vigil` — interactive console | needs a key |
| **2. MCP** | plug into Claude Desktop / Cursor | needs a key |
| **3. Claude Code project** | `clone → claude → /brief` | **no key** ✨ |

Pick #3 to just try it. #1 and #2 are for headless / cron / power use.

---

### 3 · In Claude Code — no API key

The zero-friction path: **Claude Code itself is the reasoning engine**, and a
keyless data server feeds it live market data. No AIML/OpenAI/Anthropic key.

```bash
git clone https://github.com/muhammadtalhaishtiaq/vigil.git && cd vigil
python3 -m venv .venv && .venv/bin/pip install -e .
claude                      # approve the "vigil-data" MCP server when asked
```

Then, inside Claude Code:

```
/setup             # a short chat that saves your company profile
/brief             # full multi-agent risk briefing (score, risks, actions)
/verdict tesla     # quick BUY/WAIT/CAUTION/AVOID on one asset
/trend             # your risk score over time
```

Optional: `export NEWSAPI_KEY=...` for live headlines (free tier). Everything else
is keyless — market data comes from yfinance.

---

### 1 · The CLI

```bash
pipx install git+https://github.com/muhammadtalhaishtiaq/vigil.git
# or clone for development:  git clone … && cd vigil && pip install -e ".[dev]"

export AIML_API_KEY=...     # or LLM_API_KEY + LLM_BASE_URL for any OpenAI-compatible endpoint
export NEWSAPI_KEY=...      # optional: live headlines (free tier: newsapi.org)

vigil                       # interactive console
```

First run: a 30-second wizard saves your company profile locally. Then just talk
— the router answers greetings and quick questions instantly, and only spins up
the full analyst wave when a question actually needs it:

```
vigil> how exposed are we to the new EU payment rules?
vigil> /brief         # full briefing — watch the agent wave live
vigil> /trend         # your risk score over time (sparkline)
vigil> /agents        # who does what, which model, which tools
vigil> /export        # write the last briefing to workspace/reports/
```

**Ground it in your own documents:** drop `.md`/`.txt`/`.csv` files (financials,
plans, contracts) into `workspace/docs/`, then:

```
vigil> /ingest        # distills them into workspace/wiki/ (uses your configured LLM)
```

From then on every briefing reads your knowledge base, and agents can search or
read the originals mid-analysis (`search_company_docs` / `read_company_doc`).
Everything under `workspace/` is gitignored — your data never leaves your machine
except to the LLM provider you chose.

**Scheduled monitoring** (cron-able one-shot, exit code 2 on a risk jump):

```bash
# weekdays at 08:00 — writes a report and alerts on ≥10-point moves
0 8 * * 1-5  cd ~/vigil && vigil monitor --threshold 10 || notify-send "Vigil: risk moved"
```

One-shots for scripting: `vigil ask "..."` · `vigil verdict "should I buy TSLA?"`
· `vigil brief`.

### 2 · From Claude Desktop / Cursor (MCP)

```jsonc
// claude_desktop_config.json
{ "mcpServers": { "vigil": {
    "command": "vigil-mcp",
    "env": { "AIML_API_KEY": "your-key" }
} } }
```

Two tools appear: `risk_briefing(company, description, …)` and
`market_verdict(question)` — same engine as the console.

## Built like a production agent (not a demo)

- **Structured outputs** — JSON contracts at every LLM/code seam, regex only as fallback
- **Observability** — every run writes a replayable JSONL trace (`traces/`) with
  per-agent tokens, latency, and tool calls; the CLI footer shows cost per run
- **Evaluation** — 86 offline tests + a golden dataset with an LLM-as-judge
  harness (`python evals/run_evals.py`)
- **Guardrails** — deterministic routing backstop, inter-wave validation gates,
  retry with backoff, prompt-injection envelope on all external text, read-only
  tools, path-traversal-safe doc access
- **Honesty** — no fabricated data anywhere; missing data is reported as missing;
  every number is labeled analysis, not fact

Plan of record and every decision's reason: [docs/MASTER_PLAN.md](docs/MASTER_PLAN.md).

## Development

```bash
pytest                          # 86 tests, all offline (no keys needed)
python evals/run_evals.py       # golden evals (needs a live key)
```

New agent = a prompt file in `prompts/` + a registry entry in `agent_core.py`
(+ tools if it needs to observe the world). The engine (`agent_pipeline.py`) is a
pure function: `(message, profile, history) → result dict`.

## Disclaimer

Vigil produces **model-generated analysis, not certified financial advice**.
It labels its output accordingly — always verify independently before acting.

MIT licensed. Built by [Muhammad Talha Ishtiaq](https://github.com/muhammadtalhaishtiaq).
