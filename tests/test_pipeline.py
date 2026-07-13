"""Integration: run_pipeline end-to-end with a mocked LLM (no keys, no network)."""

import json

import agent_pipeline as ap
from tests.conftest import make_response

PROFILE = {
    "company_name": "Acme Fintech",
    "description": "cross-border payments for SMBs",
    "sector": "Fintech",
    "country": "Germany",
}

ORCH_FULL = json.dumps({
    "intent_type": "FULL_BRIEFING",
    "agents_needed": ["signal_harvester", "narrative_intel", "macro_watchdog",
                      "competitive_intel", "risk_synthesizer", "strategy_commander"],
    "context_quality": "FULL_PROFILE",
    "risk_score": 55, "risk_tier": "ORANGE",
    "verdict": "Acme faces elevated but manageable risk.",
    "executive_brief": "FX exposure and PSD3 are the live concerns this quarter.",
})

SYNTH = json.dumps({
    "risk_score": 61, "risk_tier": "ORANGE", "trend": "STABLE",
    "verdict": "Acme risk 61/100 driven by FX and PSD3.",
    "top_risks": [
        {"name": "FX volatility", "probability": 70, "severity": "HIGH",
         "detail": "40% EUR revenue.", "owner": "CFO"},
        {"name": "PSD3", "probability": 55, "severity": "MEDIUM", "detail": "Licensing."},
        {"name": "Funding", "probability": 40, "severity": "LOW", "detail": "Runway."},
    ],
    "score_breakdown": {"macro": 65, "market": 60, "narrative": 55, "competitive": 60},
    "signal_coherence": "ALIGNED",
})

ORCH_INVEST = json.dumps({
    "intent_type": "INVESTMENT_QUERY",
    "agents_needed": ["signal_harvester", "market_oracle"],
    "context_quality": "GENERIC",
    "risk_score": None, "risk_tier": None,
    "verdict": "Routing to the Market Oracle.",
    "executive_brief": "Investment question about TSLA.",
})


def _scripted_llm(mock_llm, script_by_system):
    """
    Route mocked completions by the agent's system prompt content.
    `script_by_system` maps a distinctive prompt substring -> response text.
    """
    def create(**kw):
        system = next(
            (m["content"] for m in kw["messages"] if m["role"] == "system"), ""
        )
        for needle, reply in script_by_system.items():
            if needle in system:
                return make_response(content=reply)
        return make_response(content="generic specialist analysis text")
    mock_llm(create)


def test_full_briefing_end_to_end(mock_llm):
    _scripted_llm(mock_llm, {
        "Orchestrator": ORCH_FULL,
        "Risk Synthesizer": SYNTH,
    })
    result = ap.run_pipeline("give me a full briefing", profile=PROFILE)

    assert result["intent_type"] == "FULL_BRIEFING"
    # Synthesizer is authoritative over the orchestrator's initial read
    assert result["risk_score"] == 61
    assert result["risk_tier"] == "ORANGE"
    assert len(result["top_risks"]) == 3
    assert result["score_breakdown"]["macro"] == 65
    assert set(result["agents_activated"]) >= {
        "signal_harvester", "narrative_intel", "macro_watchdog",
        "competitive_intel", "risk_synthesizer", "strategy_commander",
    }
    assert result["updates_risk_strip"] is True
    # Structured seam: no raw JSON leaks into what users see
    assert "{" not in result["primary_response"]
    assert "risk_synthesizer" in result["full_playbook"].lower() or \
           "RISK SYNTHESIZER" in result["full_playbook"]
    assert "{" not in result["full_playbook"].split("RISK SYNTHESIZER")[1].split("━")[0] \
        if "RISK SYNTHESIZER" in result["full_playbook"] else True
    # Observability fields present
    assert "token_usage" in result
    assert result["profile_was_used"] is True


def test_investment_query_routes_to_oracle_only(mock_llm):
    _scripted_llm(mock_llm, {
        "Orchestrator": ORCH_INVEST,
        "Market Oracle": "ORACLE_VERDICT: WAIT\nONE_LINE: Wait for a dip.",
    })
    result = ap.run_pipeline("should I buy TSLA?")

    assert result["intent_type"] == "INVESTMENT_QUERY"
    # Only the scouts run — none of the four analysts should activate
    assert set(result["agents_activated"]) - {"orchestrator"} == \
        {"signal_harvester", "market_oracle"}
    assert result["oracle_output"] is not None
    assert result["updates_risk_strip"] is False


def test_orchestrator_failure_still_produces_a_run(mock_llm):
    """A dead orchestrator degrades to the default FULL_BRIEFING route."""
    def create(**kw):
        system = next(
            (m["content"] for m in kw["messages"] if m["role"] == "system"), ""
        )
        if "Orchestrator" in system:
            raise RuntimeError("orchestrator down")
        return make_response(content="specialist text")

    mock_llm(create)
    result = ap.run_pipeline("hello", profile=PROFILE)
    assert result["intent_type"] == "FULL_BRIEFING"
    assert result["primary_response"]  # something useful, not a crash


def test_empty_profile_runs_generic_mode(mock_llm):
    _scripted_llm(mock_llm, {"Orchestrator": ORCH_FULL, "Risk Synthesizer": SYNTH})
    result = ap.run_pipeline("brief me", profile={})
    assert result["profile_was_used"] is False


def test_conversation_answers_directly_no_agents(mock_llm):
    """A meta/greeting query must NOT run the analyst wave — router replies itself."""
    ran = []

    def create(**kw):
        system = next((m["content"] for m in kw["messages"] if m["role"] == "system"), "")
        if "Orchestrator" in system:
            return make_response(content=json.dumps({
                "intent_type": "CONVERSATION",
                "reply": "Vigil is your financial-risk copilot — ask about your "
                         "company's risk, an investment, or type /help.",
            }))
        ran.append(system[:20])  # any specialist call is a failure here
        return make_response(content="should not run")

    mock_llm(create)
    result = ap.run_pipeline("what can you do?")

    assert result["intent_type"] == "CONVERSATION"
    assert ran == [], "no specialist agents should run for CONVERSATION"
    assert result["agents_activated"] == ["orchestrator"]
    assert "financial-risk copilot" in result["primary_response"]
    assert result["risk_score"] is None
    assert result["updates_risk_strip"] is False


def test_direct_qa_runs_only_the_concierge(mock_llm, monkeypatch):
    """A simple data question routes to the single concierge, not the full wave."""
    calls = {"orchestrator": 0, "concierge": 0, "other": 0}

    def create(**kw):
        system = next((m["content"] for m in kw["messages"] if m["role"] == "system"), "")
        if "Orchestrator" in system:
            calls["orchestrator"] += 1
            return make_response(content=json.dumps({"intent_type": "DIRECT_QA"}))
        if "Concierge" in system:
            calls["concierge"] += 1
            return make_response(content="Your runway is 14 months per your profile.")
        calls["other"] += 1
        return make_response(content="should not run")

    mock_llm(create)
    result = ap.run_pipeline("what's my runway?", profile=PROFILE)

    assert result["intent_type"] == "DIRECT_QA"
    assert calls["concierge"] == 1
    assert calls["other"] == 0, "no analyst agents should run for DIRECT_QA"
    assert "concierge" in result["agents_activated"]
    assert "14 months" in result["primary_response"]
    assert result["updates_risk_strip"] is False


def test_keyword_hint_routes_investment_without_orchestrator_json(mock_llm):
    """Deterministic keyword routing backs up the LLM router (hard-code what you can)."""
    _scripted_llm(mock_llm, {
        "Orchestrator": "I think you should consider many factors...",  # useless
        "Market Oracle": "ORACLE_VERDICT: CAUTION",
    })
    result = ap.run_pipeline("should I buy bitcoin now?")
    assert result["intent_type"] == "INVESTMENT_QUERY"
