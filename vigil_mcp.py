"""
vigil_mcp.py — Vigil as an MCP server
=====================================
Exposes Vigil's multi-agent engine to any MCP client (Claude Desktop, Cursor,
etc.) as two tools:

    • risk_briefing(...)   — run the full 6-agent wave and return a scored,
                             tiered risk briefing for a company.
    • market_verdict(...)  — ask the Market Oracle a plain-English investment
                             question and get a BUY/WAIT/CAUTION/AVOID verdict.

It is a thin adapter: it builds a profile/question, calls `run_pipeline()` from
the same framework-free engine the CLI uses, and formats the result. No agent
logic lives here — one engine, many front-ends.

Run it:  python vigil_mcp.py       (stdio transport; point your MCP client here)

Note on latency: a full risk_briefing chains several LLM calls and can take a
minute or more depending on your provider. `market_verdict` is the fast path
(a single tool-using Haiku agent).

Guardrail: every number here is model-generated *analysis*, not certified
financial advice — the disclaimers below are intentional and must stay.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from agent_pipeline import run_pipeline
import tools  # noqa: F401 — importing attaches the scout agents' data tools

mcp = FastMCP("vigil")

_DISCLAIMER = (
    "— Vigil analysis, not financial advice. Model-generated perspective based "
    "on live market data; verify independently before acting."
)


def _format_briefing(result: dict) -> str:
    """Render a run_pipeline() result as a readable risk briefing."""
    score = result.get("risk_score")
    tier = result.get("risk_tier")
    verdict = result.get("verdict")

    lines: list[str] = []
    head = "VIGIL RISK BRIEFING"
    if score is not None:
        head += f" — risk {score}/100"
        if tier:
            head += f" ({tier})"
    lines.append(head)
    if verdict:
        lines.append(f"Verdict: {verdict}")

    brief = result.get("executive_brief")
    if brief:
        lines.append(f"\n{brief}")

    top_risks = result.get("top_risks") or []
    if top_risks:
        lines.append("\nTOP RISKS:")
        for r in top_risks[:5]:
            name = r.get("name") or r.get("risk") or "Risk"
            prob = r.get("probability")
            detail = r.get("detail") or ""
            lines.append(f"  • {name}" + (f" (~{prob})" if prob else "") + (f" — {detail}" if detail else ""))

    top_actions = result.get("top_actions") or []
    if top_actions:
        lines.append("\nRECOMMENDED ACTIONS:")
        for a in top_actions[:5]:
            title = a.get("title") or a.get("action") or "Action"
            deadline = a.get("deadline")
            lines.append(f"  • {title}" + (f" (by {deadline})" if deadline else ""))

    # Fall back to the fullest available narrative if structured fields are thin.
    if score is None and not brief:
        lines.append(result.get("primary_response") or "No analysis produced.")

    agents = result.get("agents_activated") or []
    took = result.get("total_time_seconds")
    meta = f"\n[{len(agents)} agents · {took}s]" if took is not None else ""
    return "\n".join(lines) + meta + f"\n{_DISCLAIMER}"


@mcp.tool()
def risk_briefing(
    company_name: str,
    description: str,
    sector: str = "",
    stage: str = "",
    country: str = "",
    key_concerns: str = "",
) -> str:
    """
    Produce a full, scored financial-risk briefing for a company by running
    Vigil's multi-agent pipeline (signal harvesting → narrative/macro/competitive
    analysis → risk synthesis → strategy).

    Args:
        company_name: The company's name.
        description:  What the company does (one or two sentences).
        sector:       Industry/sector, e.g. "Fintech" (optional but improves focus).
        stage:        Funding/maturity stage, e.g. "Series B" (optional).
        country:      Primary market/HQ country (optional).
        key_concerns: Anything specific to weigh, e.g. "FX exposure, new EU rules".

    Returns a briefing with a 0–100 risk score, tier, top risks, and actions.
    This is the slow path — it runs several agents.
    """
    profile = {
        "company_name": company_name,
        "description": description,
        "sector": sector,
        "stage": stage,
        "country": country,
        "risk_areas": key_concerns,
    }
    result = run_pipeline(
        f"Give me a full financial risk briefing for {company_name}.",
        profile=profile,
    )
    return _format_briefing(result)


@mcp.tool()
def market_verdict(question: str) -> str:
    """
    Ask Vigil's Market Oracle a plain-English investment question and get a
    BUY / WAIT / CAUTION / AVOID verdict with a bull case, bear case, and a
    historical parallel. The Oracle fetches live price/fundamentals for the
    asset in question via its tools before answering.

    Args:
        question: e.g. "Should I buy Tesla right now?" or "Is gold a good hedge?"

    Returns the Oracle's verdict. This is the fast path (a single agent).
    """
    result = run_pipeline(question)
    verdict = result.get("oracle_output") or result.get("primary_response")
    if not verdict:
        return "No verdict produced — try naming a specific asset or ticker."
    return f"{verdict}\n{_DISCLAIMER}"


def main() -> None:
    """Entry point for the `vigil-mcp` console script (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
