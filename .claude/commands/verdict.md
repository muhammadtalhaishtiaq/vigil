---
description: Quick investment verdict (BUY/WAIT/CAUTION/AVOID) on a single asset — no API key. Uses this Claude session + the vigil-data MCP for live prices.
---

You are running Vigil's **investment verdict** — the fast path. No external API
key is used: YOU are the reasoning engine, and the `vigil-data` MCP provides live
data.

The question / asset: **$ARGUMENTS**
(If empty, ask the user which asset or ticker they're considering.)

Steps:

1. **Identify the ticker** from the question (e.g. "Tesla" → TSLA, "bitcoin" →
   BTC-USD, "gold" → GC=F). If unsure, ask.

2. **Gather live data** — call the vigil-data MCP tools:
   - `get_stock_data` for the ticker (price, %-change, P/E, 52-week range, target)
   - `get_market_pulse` for the macro backdrop
   Treat what they return as authoritative. If the ticker returns no data, tell the
   user it couldn't be found — do NOT invent a price.

3. **Get the verdict** — invoke the `market-oracle` subagent with the user's
   question plus the gathered data. It returns a BUY/WAIT/CAUTION/AVOID verdict
   with a bull case, bear case, and historical parallel.

4. **Present** the verdict cleanly.

Rules: No fabricated data. Every figure not from the tools is a labeled estimate.
Keep the disclaimer intact. Analysis, not financial advice.
