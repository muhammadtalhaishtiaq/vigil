"""
vigil_data_mcp.py — Vigil's data tools as a KEYLESS MCP server
==============================================================
This is the foundation of "Path 3": run Vigil inside Claude Code (or any MCP
client) with **no API key**. It exposes only the deterministic data tools —
live market data and the user's own documents — none of which call an LLM.

The reasoning (routing, analysis, scoring, the risk briefing) is done by the MCP
*client's* model — e.g. Claude Code itself — using the `.claude/` agents and
commands. So the intelligence is the user's existing Claude session; this server
just hands it real facts. No AIML/OpenAI/Anthropic key required to run it.

Tools exposed:
    get_stock_data(ticker)         live price / fundamentals for one ticker
    get_market_pulse()             VIX, S&P, yields, gold, USD, regime, fear/greed
    get_sector_performance()       7-day moves across major sectors
    get_live_headlines(sector)     recent headlines with sentiment (needs NEWSAPI_KEY
                                   only for news; everything else is keyless)
    search_company_docs(query)     search the user's workspace/docs
    read_company_doc(name)         read one workspace document

Run it:  python vigil_data_mcp.py     (stdio transport)
Or register in Claude Code:  claude mcp add vigil-data -- vigil-data-mcp

Guardrail: every tool returns live data or an honest "no data" — never fabricated
numbers. External text comes wrapped in a data-only envelope (see tools.py).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import tools

mcp = FastMCP("vigil-data")


@mcp.tool()
def get_stock_data(ticker: str) -> str:
    """Live price, %-change, P/E, 52-week range, and analyst target for one ticker
    (e.g. AAPL, TSLA, BTC-USD, QQQ). Returns an honest 'no data' for unknown symbols."""
    return tools._fmt_stock(ticker)


@mcp.tool()
def get_market_pulse() -> str:
    """The current macro backdrop: VIX, S&P 500 trend, 10Y yield and curve, gold,
    USD index, market regime, and a fear/greed reading."""
    return tools._fmt_pulse()


@mcp.tool()
def get_sector_performance() -> str:
    """7-day performance and a directional signal for the major market sectors
    (tech, healthcare, financials, energy, etc.)."""
    return tools._fmt_sectors()


@mcp.tool()
def get_live_headlines(sector: str = "finance") -> str:
    """Recent financial news headlines with sentiment labels for a sector/topic.
    (Needs NEWSAPI_KEY for news; returns an honest empty note if unset.)"""
    return tools._fmt_headlines(sector)


@mcp.tool()
def search_company_docs(query: str) -> str:
    """Search the user's own company documents (in their workspace) for a topic —
    their financials, plans, contracts. Their numbers beat general market data."""
    return tools._fmt_doc_search(query)


@mcp.tool()
def read_company_doc(name: str) -> str:
    """Read one of the user's company documents in full, by filename."""
    return tools._fmt_doc_read(name)


def main() -> None:
    """Entry point for the `vigil-data-mcp` console script (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
