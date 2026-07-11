---
name: verify-vigil
description: Verify Vigil actually works after a change — compile, boot the CLI + MCP, run the offline test suite, and confirm graceful no-keys degradation. Use before marking any task complete or committing a nontrivial change.
---

# Verify Vigil

Vigil is a **terminal + MCP** app (no web server). Verify against that reality.

## 1. Static checks (always)

```bash
cd "$(git rev-parse --show-toplevel)"
.venv/bin/python -m py_compile agent_core.py agent_pipeline.py tools.py \
    tracing.py vigil_cli.py vigil_mcp.py data_layer.py session_store.py
.venv/bin/python -c "import agent_pipeline, vigil_cli, vigil_mcp"   # imports clean
grep -rn "streamlit\|fastapi\|uvicorn\|langchain\|langgraph" *.py   # expect NO hits
```

## 2. Test suite (always — this is the primary gate)

```bash
.venv/bin/python -m pytest -q          # all tests must pass, offline, no keys
```

## 3. Boot the front-ends (always)

```bash
.venv/bin/vigil --help                 # CLI entry point works
.venv/bin/python -c "import asyncio, vigil_mcp; \
  print('MCP tools:', len(asyncio.run(vigil_mcp.mcp.list_tools())))"   # expect 2
```

## 4. No-keys graceful degradation (always)

```bash
# With NO LLM key, an agent call must return a labelled placeholder, never fake data:
env -i PATH="$PATH" HOME="$HOME" .venv/bin/python -c "
import agent_core
out = agent_core.AGENTS['narrative_intel'].run('test')
assert 'UNAVAILABLE' in out, out
print('degrades honestly')
"
# yfinance tools need no key and should still return real data or an honest 'no data':
.venv/bin/python -c "import tools; print(tools.TOOL_MARKET_PULSE.fn()[:60])"
```

## 5. Exercise what the change touched (pick relevant)

- Engine/parsing change → `pytest tests/test_pipeline.py tests/test_parsing.py`
- Tools/workspace change → `pytest tests/test_tools.py tests/test_workspace.py`
- Console change → `pytest tests/test_console.py tests/test_reports.py`
- With a live key (optional, costs tokens): `.venv/bin/vigil verdict "buy TSLA?"`
  and/or `.venv/bin/python evals/run_evals.py --only market-pulse`

## 6. Interpret honestly

- **No keys:** agent calls return `UNAVAILABLE` placeholders, never a fabricated
  briefing. yfinance tools still return live data or an honest "no data".
- **Any hardcoded score/briefing/statistic in a code path = guardrail violation** —
  stop and fix. Missing data must be reported as missing.
- Every user-facing number stays labelled analysis, with the disclaimer intact.

No servers to clean up — nothing is left running.
