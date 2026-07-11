"""Tool formatters and registry wiring — data layer mocked, no network."""

import tools
import agent_core


def test_stock_tool_formats_valid_data(monkeypatch):
    monkeypatch.setattr(tools, "get_stock_data", lambda t: {
        "ticker": t.upper(), "name": "Apple Inc.", "current_price": 313.39,
        "currency": "USD", "pct_7d": 8.3, "pct_30d": 1.97, "pct_1yr": 49.86,
        "pe_ratio": 37.94, "market_cap": 4602870628352,
        "week_52_high": 317.4, "week_52_low": 201.5,
        "analyst_target": 315.57, "volume": 38466049,
        "valid": True, "error": None,
    })
    out = tools._fmt_stock("aapl")
    assert "Apple Inc. (AAPL)" in out
    assert "313.39 USD" in out
    assert "8.3%" in out


def test_stock_tool_honest_on_unknown_ticker(monkeypatch):
    monkeypatch.setattr(tools, "get_stock_data", lambda t: {
        "ticker": t.upper(), "valid": False, "error": "Ticker not found",
    })
    out = tools._fmt_stock("NOTREAL")
    assert "No market data found" in out
    assert "313" not in out  # no fabricated numbers, ever


def test_headlines_tool_honest_when_empty(monkeypatch):
    monkeypatch.setattr(tools, "get_live_headlines", lambda s="finance": [])
    out = tools._fmt_headlines("fintech")
    assert "No live headlines" in out


def test_sectors_tool_formats_rows(monkeypatch):
    monkeypatch.setattr(tools, "get_sector_performance", lambda: {
        "Technology": {"ticker": "XLK", "pct_7d": 2.1, "pct_1d": 0.3,
                       "color": "dark_green", "signal": "STRONGLY BULLISH"},
    })
    out = tools._fmt_sectors()
    assert "Technology (XLK): 7d 2.1%" in out


def test_scouts_have_tools_analysts_do_not():
    scout_tools = {
        "signal_harvester": {"get_market_pulse", "get_sector_performance",
                             "get_live_headlines", "search_company_docs",
                             "read_company_doc"},
        "market_oracle": {"get_stock_data", "get_market_pulse"},
    }
    for name, expected in scout_tools.items():
        assert {t.name for t in agent_core.AGENTS[name].tools} == expected

    for name in ("orchestrator", "narrative_intel", "macro_watchdog",
                 "competitive_intel", "risk_synthesizer", "strategy_commander"):
        assert agent_core.AGENTS[name].tools == [], f"{name} should be toolless"


def test_tool_openai_schema_shape():
    schema = tools.TOOL_STOCK_DATA.as_openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "get_stock_data"
    assert "ticker" in schema["function"]["parameters"]["properties"]


def test_registry_has_exactly_eight_agents():
    assert len(agent_core.AGENTS) == 8
    assert "risk_evaluator" not in agent_core.AGENTS, \
        "the critic must stay out of the 8-agent briefing registry"
