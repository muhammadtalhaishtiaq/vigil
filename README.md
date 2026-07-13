# ⚡ VIGIL — your terminal's financial-risk copilot

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![MCP server](https://img.shields.io/badge/MCP-server-purple?style=flat)](#use-it-from-claude-desktop--cursor-mcp)
[![Tests](https://img.shields.io/badge/tests-84%20passing-green?style=flat)](tests/)
[![MIT License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

**Describe your company once. Drop your documents in a folder. Then ask anything —
"how exposed are we to the new EU rules?" — and watch specialized agents pull live
market data *and your own docs* to build a scored, tiered risk briefing about
*your* situation.** All local: your machine, your keys, nothing to sign up for.

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
 you ──► Orchestrator (routes 1 of 7 intents)
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

## Install (one line)

```bash
pipx install git+https://github.com/muhammadtalhaishtiaq/vigil.git
# or:  uvx --from git+https://github.com/muhammadtalhaishtiaq/vigil.git vigil
```

Or clone for development:

```bash
git clone https://github.com/muhammadtalhaishtiaq/vigil.git && cd vigil
pip install -e ".[dev]"
```

**Keys** (env vars — never committed):

```bash
export AIML_API_KEY=...     # or LLM_API_KEY + LLM_BASE_URL for any OpenAI-compatible endpoint
export NEWSAPI_KEY=...      # optional: live headlines (free tier: newsapi.org)
```

No keys? It still boots and degrades honestly — agents report what they couldn't
fetch instead of inventing it. That's a design rule, not an accident.

## Use it

```bash
vigil                 # interactive console (the main door)
```

First run: a 30-second wizard saves your company profile locally. Then just talk:

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
vigil> /ingest        # distills them into workspace/wiki/ using YOUR llm key
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

## Use it from Claude Desktop / Cursor (MCP)

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
- **Evaluation** — 84 offline tests + a golden dataset with an LLM-as-judge
  harness (`python evals/run_evals.py`)
- **Guardrails** — deterministic routing backstop, inter-wave validation gates,
  retry with backoff, prompt-injection envelope on all external text, read-only
  tools, path-traversal-safe doc access
- **Honesty** — no fabricated data anywhere; missing data is reported as missing;
  every number is labeled analysis, not fact

Plan of record and every decision's reason: [docs/MASTER_PLAN.md](docs/MASTER_PLAN.md).

## Development

```bash
pytest                          # 84 tests, all offline (no keys needed)
python evals/run_evals.py       # golden evals (needs a live key)
```

New agent = a prompt file in `prompts/` + a registry entry in `agent_core.py`
(+ tools if it needs to observe the world). The engine (`agent_pipeline.py`) is a
pure function: `(message, profile, history) → result dict`.

## Disclaimer

Vigil produces **model-generated analysis, not certified financial advice**.
It labels its output accordingly — always verify independently before acting.

MIT licensed. Built by [Muhammad Talha Ishtiaq](https://github.com/muhammadtalhaishtiaq).
