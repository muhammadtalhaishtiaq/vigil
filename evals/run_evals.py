#!/usr/bin/env python3
"""
run_evals.py — Vigil's evaluation harness (golden dataset + LLM-as-judge)
=========================================================================
Runs the golden scenarios through the real pipeline and answers the question
the test suite can't: **is the output actually good?**

Two layers, per the production-agent playbook:

1. **Structural checks (deterministic, free).** Intent routing correct, risk
   score present when expected, exactly 3 risks, right agents activated, no
   fabricated data on unknown tickers.
2. **LLM-as-judge (model-scored).** A cheap judge model grades each response
   1–5 on faithfulness (grounded in the run's own data), completeness, and
   sufficiency — plus any scenario-specific judge_note.

Cost and latency are recorded per scenario — "cost per successful task" is a
first-class metric.

Usage (requires a live LLM key; this is the live-key test plan):
    python evals/run_evals.py                 # all scenarios
    python evals/run_evals.py --only invest-ticker adversarial-injection
    python evals/run_evals.py --limit 3       # first N scenarios
    python evals/run_evals.py --no-judge      # structural checks only

Reports: printed table + evals/reports/eval-<timestamp>.json
"""

from __future__ import annotations

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))  # repo root

from agent_pipeline import run_pipeline, extract_json_block  # noqa: E402
from agent_core import get_client  # noqa: E402

GOLDEN = Path(__file__).parent / "golden.json"
REPORTS = Path(__file__).parent / "reports"

JUDGE_MODEL = "claude-haiku-4-5-20251001"

JUDGE_PROMPT = """You are grading one response from Vigil, a financial-risk analysis system.

USER QUERY:
{query}

{judge_note}
GROUND-TRUTH DATA THE SYSTEM FETCHED FROM ITS LIVE TOOLS (yfinance / news APIs):
This is the real market data Vigil retrieved for this run. Treat it as authoritative.
{tool_data}

SYSTEM RESPONSE (what the user would see):
{response}

Grade 1-5 on each criterion (5 = excellent):
- faithfulness: Market figures (prices, P/E, VIX, yields, % moves) are faithful if they
  match the GROUND-TRUTH DATA above — do NOT penalize them for differing from your own
  training knowledge; the live feed is authoritative and more current than you.
  DO penalize forward-looking specifics that appear nowhere in the ground-truth data and
  are stated as hard fact without hedging (e.g. "compliance will cost €400K", "65%
  probability of X") — those are invented. Honest "data unavailable" is faithful.
- completeness: Addresses every part of the query.
- sufficiency: Appropriately scoped — no hallucinated extras, no critical omissions,
  concrete rather than vague. Estimates are fine if clearly framed as estimates.

Respond with ONE JSON object only:
{{"faithfulness": 4, "completeness": 4, "sufficiency": 3, "comment": "one sentence"}}"""


# ---------------------------------------------------------------------------
# Structural checks (deterministic)
# ---------------------------------------------------------------------------
def check_structure(expect: dict, result: dict) -> list[str]:
    """Return a list of failure strings (empty = all structural checks pass)."""
    failures = []
    if "intent" in expect and result.get("intent_type") != expect["intent"]:
        failures.append(f"intent={result.get('intent_type')} (wanted {expect['intent']})")
    if expect.get("risk_score") and result.get("risk_score") is None:
        failures.append("risk_score missing")
    if "top_risks" in expect and len(result.get("top_risks") or []) != expect["top_risks"]:
        failures.append(f"top_risks={len(result.get('top_risks') or [])} (wanted {expect['top_risks']})")
    if expect.get("oracle_output") and not result.get("oracle_output"):
        failures.append("oracle_output missing")
    activated = set(result.get("agents_activated") or [])
    for agent in expect.get("agents_include", []):
        if agent not in activated:
            failures.append(f"{agent} not activated")
    for agent in expect.get("agents_exclude", []):
        if agent in activated:
            failures.append(f"{agent} should not have activated")
    if "profile_was_used" in expect and result.get("profile_was_used") != expect["profile_was_used"]:
        failures.append(f"profile_was_used={result.get('profile_was_used')}")
    return failures


# ---------------------------------------------------------------------------
# LLM-as-judge
# ---------------------------------------------------------------------------
def tool_ground_truth(trace_path: str | None) -> str:
    """
    Collect the raw tool observations from a run's trace — the live data the
    judge must treat as authoritative. Empty when no tools ran or no trace.
    """
    if not trace_path:
        return "(no tool data — the system did not fetch live data for this run)"
    try:
        from tracing import load_trace
        chunks = []
        for ev in load_trace(trace_path):
            for tc in ev.get("tool_calls", []) if ev.get("event") == "agent_step" else []:
                if tc.get("result"):
                    chunks.append(f"[{tc['name']}({tc.get('args', '')})]\n{tc['result']}")
        return "\n\n".join(chunks) if chunks else "(no tool data fetched this run)"
    except Exception as exc:
        return f"(tool data unavailable: {str(exc)[:80]})"


def judge(query: str, response_text: str, tool_data: str = "", judge_note: str = "") -> dict:
    """Score one response. Returns {faithfulness, completeness, sufficiency, comment}."""
    note = f"SCENARIO-SPECIFIC GUIDANCE: {judge_note}\n" if judge_note else ""
    prompt = JUDGE_PROMPT.format(query=query, judge_note=note,
                                 tool_data=(tool_data or "(none)")[:6000],
                                 response=response_text[:8000])
    resp = get_client().chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.0,
    )
    obj = extract_json_block(resp.choices[0].message.content or "") or {}
    return {
        "faithfulness": obj.get("faithfulness"),
        "completeness": obj.get("completeness"),
        "sufficiency": obj.get("sufficiency"),
        "comment": str(obj.get("comment") or "")[:200],
    }


def response_view(result: dict) -> str:
    """Assemble what a user actually sees from a pipeline result."""
    parts = []
    if result.get("risk_score") is not None:
        parts.append(f"Risk {result['risk_score']}/100 ({result.get('risk_tier')})")
    for key in ("verdict", "executive_brief", "oracle_output"):
        if result.get(key):
            parts.append(str(result[key]))
    for r in (result.get("top_risks") or [])[:3]:
        parts.append(f"Risk: {r.get('name')} — {r.get('detail')}")
    for a in (result.get("top_actions") or [])[:3]:
        parts.append(f"Action: {a.get('title')}")
    if not parts:
        parts.append(str(result.get("primary_response") or ""))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run Vigil's golden evals")
    parser.add_argument("--only", nargs="*", help="scenario ids to run")
    parser.add_argument("--limit", type=int, help="run first N scenarios")
    parser.add_argument("--no-judge", action="store_true", help="skip LLM judge")
    args = parser.parse_args(argv)

    golden = json.loads(GOLDEN.read_text())
    profiles = golden["profiles"]
    scenarios = golden["scenarios"]
    if args.only:
        scenarios = [s for s in scenarios if s["id"] in set(args.only)]
    if args.limit:
        scenarios = scenarios[: args.limit]
    if not scenarios:
        print("no scenarios selected"); return 1

    rows = []
    for sc in scenarios:
        profile = profiles.get(sc["profile"]) if sc.get("profile") else None
        print(f"▶ {sc['id']} … ", end="", flush=True)
        t0 = time.perf_counter()
        try:
            result = run_pipeline(sc["query"], profile=profile)
        except Exception as exc:
            rows.append({"id": sc["id"], "error": str(exc)[:200]})
            print(f"ERROR {str(exc)[:80]}")
            continue
        latency = round(time.perf_counter() - t0, 1)

        failures = check_structure(sc.get("expect", {}), result)
        usage = result.get("token_usage") or {}
        row = {
            "id": sc["id"],
            "structural_failures": failures,
            "latency_s": latency,
            "tokens": usage,
            "trace": result.get("trace_path"),
        }
        if not args.no_judge:
            try:
                row["judge"] = judge(
                    sc["query"], response_view(result),
                    tool_data=tool_ground_truth(result.get("trace_path")),
                    judge_note=sc.get("judge_note", ""),
                )
            except Exception as exc:
                row["judge"] = {"error": str(exc)[:120]}
        rows.append(row)
        status = "ok" if not failures else f"STRUCT FAIL: {failures}"
        print(f"{status} ({latency}s)")

    # ── Report ───────────────────────────────────────────────────────────────
    REPORTS.mkdir(exist_ok=True)
    report_path = REPORTS / f"eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    report_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    struct_pass = sum(1 for r in rows if not r.get("structural_failures") and "error" not in r)
    print(f"\n{'='*60}")
    print(f"Structural: {struct_pass}/{len(rows)} passed")
    judged = [r["judge"] for r in rows
              if isinstance(r.get("judge"), dict) and r["judge"].get("faithfulness")]
    if judged:
        for crit in ("faithfulness", "completeness", "sufficiency"):
            scores = [j[crit] for j in judged if isinstance(j.get(crit), (int, float))]
            if scores:
                print(f"{crit:>13}: median {sorted(scores)[len(scores)//2]}  "
                      f"min {min(scores)}  (n={len(scores)})")
    total_tokens = sum((r.get("tokens") or {}).get("prompt", 0) +
                       (r.get("tokens") or {}).get("completion", 0) for r in rows)
    print(f"total tokens: {total_tokens:,} | report: {report_path}")
    return 0 if struct_pass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
