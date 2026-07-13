# Contributing to Vigil

Vigil is a **terminal + MCP** multi-agent financial-risk copilot — framework-free,
built to production-agent standards. Contributions welcome; keep the bar high.

Read first: [docs/MASTER_PLAN.md](docs/MASTER_PLAN.md) (vision, decisions & reasons,
task plan) and [docs/AGENT_ARCHITECTURE.md](docs/AGENT_ARCHITECTURE.md) (how the
agents work). The `CLAUDE.md` rules apply to humans too.

## Setup

```bash
git clone https://github.com/muhammadtalhaishtiaq/vigil.git && cd vigil
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# keys (env only — never commit them)
export AIML_API_KEY=...        # or LLM_API_KEY + LLM_BASE_URL
export NEWSAPI_KEY=...         # optional (live headlines)

vigil            # run the console
pytest           # run the test suite (84 tests, offline, no keys needed)
```

## Project layout

| File | What |
|---|---|
| `agent_core.py` | The `Agent` dataclass, the component registry, the tool-calling loop |
| `agent_pipeline.py` | Orchestration: routing, waves, gates, parsing — a pure function |
| `tools.py` | Capabilities agents call (market data + user docs) |
| `tracing.py` | Per-run JSONL traces (tokens, latency, tool calls) |
| `vigil_cli.py` / `vigil_mcp.py` | The two front-ends |
| `prompts/*.txt` | One instruction file per component; output sections are JSON contracts |
| `tests/` · `evals/` | Offline test suite · golden dataset + LLM-as-judge harness |

## How to add an agent or component

1. Write `prompts/<name>.txt` — role, rules, and a **JSON output contract** if it
   produces structured fields.
2. Add an `Agent(...)` entry to the registry in `agent_core.py` (right-size the
   model; give it tools only if it must observe the world).
3. Route to it in `agent_pipeline.py` (an intent branch or a wave).
4. Add tests in `tests/`; add a golden scenario in `evals/golden.json` if it
   changes user-visible output.

## The bar (non-negotiable — see CLAUDE.md guardrails)

- **No fabricated data.** No hardcoded scores, fake briefings, or invented
  statistics anywhere in code or prompts. Missing data is reported as missing.
- **Docs match code.** If you change behavior, update the claim (README, CLAUDE.md,
  AGENT_ARCHITECTURE.md). Verify by reading the code before writing the claim.
- **Framework-free.** No web framework, no LangChain/LangGraph. The engine stays a
  pure function; persistence lives in the front-ends.
- **Secrets via env only.** Never commit `.env`, `sessions.json`, `traces/`, or
  `workspace/` contents.
- **Every user-facing number is labeled analysis, not fact**, with the disclaimer intact.

## Before you open a PR

```bash
pytest                              # must be green
python -m py_compile *.py           # must compile
vigil --help                        # CLI still boots
```

- [ ] Tests pass; new behavior has tests
- [ ] Docs/claims updated to match the change (README, CLAUDE.md, AGENT_ARCHITECTURE.md)
- [ ] `AGENTS.md` roster updated if you added/renamed a component
- [ ] No secrets, no fabricated data, no reintroduced web/agent frameworks

Run the `verify-vigil` skill (or its steps) as a final gate. Thanks for contributing!
