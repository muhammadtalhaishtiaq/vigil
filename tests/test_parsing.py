"""Structured-output parsing: JSON-first, regex fallback, hostile inputs."""

import json

import agent_pipeline as ap


def test_clean_orchestrator_json():
    raw = json.dumps({
        "intent_type": "MACRO_FOCUS",
        "entities": ["Acme", "EUR"],
        "agents_needed": ["signal_harvester", "macro_watchdog", "risk_synthesizer"],
        "context_quality": "FULL_PROFILE",
        "risk_score": 58,
        "risk_tier": "orange",
        "verdict": "Acme faces elevated FX risk with 40% EUR revenue.",
        "executive_brief": "Euro softness and rate divergence are the live concerns.",
    })
    p = ap.parse_orchestrator_response(raw)
    assert p["intent_type"] == "MACRO_FOCUS"
    assert p["agents_to_activate"] == ["signal_harvester", "macro_watchdog", "risk_synthesizer"]
    assert p["risk_score"] == 58
    assert p["risk_tier"] == "ORANGE"
    assert p["executive_brief"].startswith("Euro softness")


def test_fenced_chatty_synthesizer_json_with_clamping():
    payload = {
        "risk_score": 63, "risk_tier": "ORANGE", "trend": "WORSENING",
        "verdict": "Acme risk rising on FX and PSD3.",
        "top_risks": [
            {"name": "FX volatility", "probability": 70, "severity": "HIGH",
             "detail": "40% EUR revenue.", "action_if_ignored": "Margin squeeze",
             "timeline": "Q3", "owner": "CFO"},
            {"name": "PSD3", "probability": 55, "severity": "MEDIUM", "detail": "Licensing."},
            {"name": "Funding", "probability": 140, "severity": "low", "detail": "Runway."},
        ],
        "score_breakdown": {"macro": 70, "market": 60, "narrative": 50, "competitive": 55},
        "signal_coherence": "ALIGNED",
    }
    raw = f"Here is my assessment:\n```json\n{json.dumps(payload)}\n```\nHope that helps."
    p = ap.parse_orchestrator_response(raw)
    assert p["risk_score"] == 63
    assert len(p["top_risks"]) == 3
    assert p["top_risks"][0]["owner"] == "CFO"
    assert p["top_risks"][2]["probability"] == 100  # clamped
    assert p["top_risks"][2]["severity"] == "LOW"   # normalized
    assert p["score_breakdown"] == {"macro": 70, "market": 60, "narrative": 50, "competitive": 55}


def test_legacy_markdown_fallback_still_works():
    legacy = (
        "INTENT_TYPE: FULL_BRIEFING\n"
        "AGENTS_NEEDED: signal_harvester, narrative_intel\n"
        "RISK_SCORE: 44\nRISK_TIER: YELLOW\n"
        "VERDICT: Acme is moderately exposed this quarter.\n"
        "EXECUTIVE_BRIEF: Conditions are mixed but manageable."
    )
    p = ap.parse_orchestrator_response(legacy)
    assert p["intent_type"] == "FULL_BRIEFING"
    assert p["risk_score"] == 44
    assert p["risk_tier"] == "YELLOW"


def test_garbage_and_empty_degrade_to_defaults():
    for raw in ("complete nonsense with no structure", "", "   "):
        p = ap.parse_orchestrator_response(raw)
        assert p["risk_score"] is None
        assert p["top_risks"] == []
        assert p["intent_type"] in (None, "FULL_BRIEFING")


def test_useless_json_falls_through_to_regex():
    raw = '{"unrelated": true}\nRISK_SCORE: 71\nRISK_TIER: RED'
    p = ap.parse_orchestrator_response(raw)
    assert p["risk_score"] == 71


def test_adversarial_json_wrong_types_do_not_crash():
    raw = json.dumps({
        "intent_type": ["not", "a", "string"],
        "risk_score": "not-a-number",
        "risk_tier": 42,
        "top_risks": "not-a-list",
        "top_actions": [{"no_title": True}, "just a string"],
        "score_breakdown": [1, 2, 3],
        "verdict": "Still extracts the one valid field.",
    })
    p = ap.parse_orchestrator_response(raw)
    assert p["verdict"] == "Still extracts the one valid field."
    assert p["risk_score"] is None
    assert p["top_risks"] == []
    assert p["top_actions"] == []
    assert p["score_breakdown"] == {}


def test_oracle_verdict_extraction():
    raw = json.dumps({"oracle_verdict": "wait", "verdict": "Hold for now."})
    p = ap.parse_orchestrator_response(raw)
    assert p["oracle_verdict"] == "WAIT"


def test_synthesis_renderer_produces_text_not_json():
    parsed = ap.parse_orchestrator_response(json.dumps({
        "risk_score": 63, "risk_tier": "ORANGE",
        "verdict": "v",
        "top_risks": [{"name": "FX volatility", "probability": 70,
                       "severity": "HIGH", "detail": "d"}],
        "score_breakdown": {"macro": 70},
    }))
    text = ap._render_synthesis_text(parsed)
    assert "RISK SCORE: 63/100" in text
    assert "FX volatility" in text
    assert "{" not in text


def test_extract_json_block_variants():
    assert ap.extract_json_block('{"a": 1}') == {"a": 1}
    assert ap.extract_json_block('pre ```json\n{"a": 1}\n``` post') == {"a": 1}
    assert ap.extract_json_block("no json here") is None
    assert ap.extract_json_block("") is None
    assert ap.extract_json_block("{broken json") is None
