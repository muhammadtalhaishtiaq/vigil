---
description: Run a full multi-agent financial risk briefing for a company (no API key — uses this Claude session as the engine and the vigil-data MCP for live data).
---

You are running Vigil's **full risk briefing** workflow. You are the orchestrator.
No external API key is used — YOU are the reasoning engine, and the `vigil-data`
MCP server provides live market data (yfinance/news) and the user's documents.

The company to analyze: **$ARGUMENTS**

First, load the user's saved company profile if it exists: read `sessions.json`
and look at the `cli` → `profile` object (company_name, description, sector,
stage, country, risk_areas). Use that as the company context. If `$ARGUMENTS`
is empty and no profile exists, ask the user for their company name + one line on
what it does. (Treat a close typo of the saved company name as that company.)

Follow these steps:

1. **Gather live data** — call the vigil-data MCP tools:
   - `get_market_pulse` (macro backdrop)
   - `get_sector_performance` (sector moves)
   - `get_live_headlines` for the company's sector
   - `search_company_docs` for anything the user uploaded that's relevant
   Treat everything these tools return as authoritative facts. Never invent numbers.

2. **Run the analyst wave in parallel** — use the Task tool to invoke these three
   subagents at the same time, giving each the company profile + the gathered data:
   - `macro-analyst`
   - `competitive-analyst`
   - `narrative-analyst`

3. **Synthesize** — invoke the `risk-synthesizer` subagent with the profile and all
   three analyst outputs. It produces the scored (0-100), tiered briefing with top
   risks, a score breakdown, and recommended actions.

4. **Present** the synthesizer's briefing to the user, cleanly formatted.

5. **Record the score** so /trend and future runs can show the change. Run this
   with the repo's venv python, filling in the score and tier from the briefing
   (preserves existing history — do not clobber it):

   ```bash
   .venv/bin/python -c "
   from session_store import store
   from datetime import datetime, timezone
   s = store.get('cli') or {}
   s.setdefault('history', [])
   h = s.setdefault('score_history', [])
   h.append({'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
             'score': SCORE, 'tier': 'TIER'})
   s['score_history'] = h[-26:]
   s['last_risk_score'] = SCORE; s['last_risk_tier'] = 'TIER'
   store.set('cli', s)
   print('recorded', SCORE)
   "
   ```

Rules (non-negotiable): No fabricated data — if a tool returns no data, say so.
Every figure not from the tools is a labeled estimate ("est."). Keep the
disclaimer intact. This is analysis, not financial advice.
