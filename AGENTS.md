# ⚡ Vigil — Agent Documentation

> All 8 agents, their routing logic, system prompt descriptions, intent types, and activation matrix.

---

## Agent Overview

Vigil uses 8 specialized AI agents running in-process (`agent_pipeline.py`) — Claude
models by default, via any OpenAI-compatible endpoint (AIML API out of the box).
The **Orchestrator** receives every query and routes it to the appropriate specialist agents.

```
┌─────────────┐
│ Orchestrator│ ← Always first. Classifies intent, routes specialists, synthesizes final response.
└──────┬──────┘
       ├── FULL_BRIEFING       → Agents 2,3,4,5,6,7  (3+4+5 run in parallel)
       ├── MACRO_FOCUS         → Agents 2,4,6,7
       ├── COMPETITIVE_FOCUS   → Agents 2,5,6,7
       ├── DECISION_SUPPORT    → Agents 2,4,6,7
       ├── SCENARIO            → Agents 2,4,6,7
       ├── INVESTMENT_QUERY    → Agents 2,8
       └── MARKET_PULSE        → Agents 2,3,6 (brief mode)
```

---

## Agent Activation Matrix

| Agent | FULL_BRIEFING | MACRO_FOCUS | COMPETITIVE_FOCUS | DECISION_SUPPORT | SCENARIO | INVESTMENT_QUERY | MARKET_PULSE |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1. Orchestrator | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 2. Signal Harvester | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 3. Narrative Intel | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 4. Macro Watchdog | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| 5. Competitive Intel | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| 6. Risk Synthesizer | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ (brief) |
| 7. Strategy Commander | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| 8. Market Oracle | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |

**Strip persistence** (risk/action strip on dashboard) only updates for:
`FULL_BRIEFING`, `MACRO_FOCUS`, `COMPETITIVE_FOCUS`, `DECISION_SUPPORT`, `SCENARIO`

**Oracle tab** only activates for: `INVESTMENT_QUERY`

---

## Agent 1 — Orchestrator

**Model:** `claude-sonnet-4-6` (default — override all agents with `VIGIL_MODEL`)
**File:** `vigil/prompts/orchestrator.txt`

### Role
The Orchestrator is the entry point for every user query. It has three responsibilities:
1. **Classify** the query into one of 7 intent types
2. **Synthesize** the initial analysis from all specialist outputs
3. **Produce** the final user-facing response and structured fields (score, tier, verdict, risks, actions)

### System Prompt Description
The Orchestrator prompt defines:
- The 7 intent types with routing examples
- Output format: structured `KEY: value` lines (`INTENT_TYPE:`, `RISK_SCORE:`, `RISK_TIER:`, `VERDICT:`, risk/action blocks) parsed by `parse_orchestrator_response()`
- Instructions to synthesize specialist outputs into a coherent final answer
- Tone: direct, data-grounded, Bloomberg-terminal style

### Inputs
- Full company profile context (if available)
- User message (enhanced with conversation history)
- Live market data summary (NewsAPI + yfinance)
- `[MODE: GENERIC]` hint when no profile
- `[ROUTING HINT: INVESTMENT_QUERY]` when investment keywords detected

### Outputs
Structured text parsed by `parse_orchestrator_response()` (`agent_pipeline.py`):
```text
INTENT_TYPE: FULL_BRIEFING
RISK_SCORE: <0-100>
RISK_TIER: GREEN|YELLOW|ORANGE|RED|DARK_RED
VERDICT: <one-line verdict>
TOP RISKS / NEXT MOVES blocks (NAME/PROBABILITY/SEVERITY/DETAIL, TITLE/OWNER/DEADLINE/URGENCY)
```

### Intent Classification Rules
| Intent | Trigger Keywords / Patterns |
|--------|---------------------------|
| `FULL_BRIEFING` | "full briefing", "risk briefing", "complete analysis", "everything" |
| `MACRO_FOCUS` | "macro", "Fed", "ECB", "interest rates", "inflation", "GDP" |
| `COMPETITIVE_FOCUS` | "competitors", "competitive", "landscape", "market share" |
| `DECISION_SUPPORT` | "should I", "decision", "hiring", "delay", "expand", "raise" |
| `SCENARIO` | "scenario", "what if", "if ECB", "stress test" |
| `INVESTMENT_QUERY` | "buy", "sell", "invest", stock tickers, "NASDAQ", "gold" |
| `MARKET_PULSE` | "quick check", "market now", "pulse", "brief" |

---

## Agent 2 — Signal Harvester

**Model:** `claude-haiku-4-5-20251001` (fast, cost-efficient)
**File:** `vigil/prompts/signal_harvester.txt`

### Role
Collects, organizes, and interprets live market signals. Always activated (every intent). The fastest agent — runs concurrently with others.

### System Prompt Description
Instructs the agent to parse live market data and return structured signals:
- Current market regime (RISK-ON / RISK-OFF / TRANSITIONING)
- VIX level and interpretation
- Sector rotation signals
- Key price movements relevant to the query

### Inputs
- Live data from `data_layer.get_all_live_data()` (prices, VIX, sectors, headlines)
- User query context

### Outputs
- Market regime classification
- VIX reading + interpretation
- Top sector movers (7-day)
- Signal summary for downstream agents

---

## Agent 3 — Narrative Intel

**Model:** `claude-sonnet-4-6`
**File:** `vigil/prompts/narrative_intel.txt`

### Role
Reads the market narrative — news sentiment, hidden signals, emerging risks not yet in price. Acts as an "early warning" system.

### System Prompt Description
Analyzes financial headlines for:
- Sentiment shifts (positive / negative / neutral per source)
- Hidden signals: what's being discussed before it moves markets
- Regulatory language changes
- Geopolitical risk mentions relevant to the user's sector

### Activated For
`FULL_BRIEFING`, `MARKET_PULSE`

### Idle For
`MACRO_FOCUS`, `COMPETITIVE_FOCUS`, `DECISION_SUPPORT`, `SCENARIO`, `INVESTMENT_QUERY`

---

## Agent 4 — Macro Watchdog

**Model:** `claude-sonnet-4-6`
**File:** `vigil/prompts/macro_watchdog.txt`

### Role
Translates macro-economic conditions into specific business impact for the user's company profile.

### System Prompt Description
Analyzes:
- Central bank policy signals and their sector implications
- Currency / FX risk relevant to the company's geography
- Inflation and rate environment impact on fundraising stage
- Macro-driven regulatory pressure (DORA, MiCA, Basel IV)

### Activated For
`FULL_BRIEFING`, `MACRO_FOCUS`, `DECISION_SUPPORT`, `SCENARIO`

---

## Agent 5 — Competitive Intel

**Model:** `claude-sonnet-4-6`
**File:** `vigil/prompts/competitive_intel.txt`

### Role
Tracks competitive landscape shifts, funding rounds, product launches, and strategic pivots by competitors.

### System Prompt Description
Uses news signals to identify:
- Recent competitor funding events
- Market entry / exit signals
- Product positioning changes
- Industry consolidation moves

### Activated For
`FULL_BRIEFING`, `COMPETITIVE_FOCUS`

---

## Agent 6 — Risk Synthesizer

**Model:** `claude-sonnet-4-6` (structured output required)
**File:** `vigil/prompts/risk_synthesizer.txt`

### Role
Aggregates all specialist outputs into a single composite risk score (0–100), tier classification, and top 3 ranked risks with action triggers.

### System Prompt Description
Produces structured `KEY: value` output parsed by the pipeline:
```text
RISK_SCORE: <0-100>          (composite: Macro×0.35 + Market×0.25 + Narrative×0.20 + Competitive×0.20)
RISK_TIER: GREEN|YELLOW|ORANGE|RED|DARK_RED
VERDICT: <one line>
SCORE_BREAKDOWN: MACRO/MARKET/NARRATIVE/COMPETITIVE sub-scores
TOP RISKS: NAME | PROBABILITY | SEVERITY + DETAIL lines
```

### Risk Tier Scale
| Score | Tier | Color | Meaning |
|-------|------|-------|---------|
| 0–25 | GREEN ✅ | `#00e676` | Low risk, stable environment |
| 26–50 | YELLOW ⚠️ | `#ffd740` | Elevated watch, monitor closely |
| 51–70 | ORANGE 🟠 | `#ff9100` | High risk, action required |
| 71–85 | RED 🔴 | `#ff5252` | Critical risk, immediate action |
| 86–100 | DARK_RED ⬛ | `#b71c1c` | Extreme risk, crisis mode |

### Activated For
`FULL_BRIEFING`, `MACRO_FOCUS`, `COMPETITIVE_FOCUS`, `DECISION_SUPPORT`, `SCENARIO`, `MARKET_PULSE` (brief mode)

**Note:** Risk Synthesizer outputs persist to the dashboard strip only for these intents (not `INVESTMENT_QUERY` or `MARKET_PULSE`).

---

## Agent 7 — Strategy Commander

**Model:** `claude-sonnet-4-6`
**File:** `vigil/prompts/strategy_commander.txt`

### Role
Translates risk synthesis into a prioritized, time-bound action playbook specific to the company's decision context.

### System Prompt Description
Generates a playbook with:
- 3 priority actions ranked by urgency × impact
- Owner assignments (CEO / CFO / Legal / Product)
- Deadlines (this week / this month / this quarter)
- Decision trees for key choices (raise now vs. delay, expand vs. hold)

### Outputs
Full playbook text (displayed in the "📋 Playbook" tab) + structured top_actions for the strip.

### Activated For
`FULL_BRIEFING`, `MACRO_FOCUS`, `COMPETITIVE_FOCUS`, `DECISION_SUPPORT`, `SCENARIO`

---

## Agent 8 — Market Oracle

**Model:** `claude-haiku-4-5-20251001`
**File:** `vigil/prompts/market_oracle.txt`

### Role
Investment verdict engine. Takes any investment question and delivers a structured BUY / WAIT / CAUTION / AVOID verdict with full reasoning.

### System Prompt Description
Produces:
```
## THE BULL CASE
[3 bullet points supporting the investment]

## THE BEAR CASE
[3 bullet points against the investment]

## HISTORICAL PARALLEL
[One past market situation as analogy]

## VIGIL'S TAKE
[1-2 sentence decisive verdict]

**Verdict:** WAIT / BUY SIGNAL / CAUTION / AVOID
```

### Activated For
`INVESTMENT_QUERY`

**Note:** Oracle tab on the dashboard only populates when last intent is `INVESTMENT_QUERY`.

---

## Routing Logic (agent_pipeline.py)

Routing is an if/elif chain on the Orchestrator's classified intent inside
`run_pipeline()` — the actual activation sets are:

```text
INVESTMENT_QUERY  → signal_harvester, market_oracle
MARKET_PULSE      → signal_harvester, narrative_intel, risk_synthesizer (brief mode)
MACRO_FOCUS       → signal_harvester, macro_watchdog, risk_synthesizer, strategy_commander
DECISION_SUPPORT  → signal_harvester, macro_watchdog, risk_synthesizer, strategy_commander
SCENARIO          → signal_harvester, macro_watchdog, risk_synthesizer, strategy_commander
COMPETITIVE_FOCUS → signal_harvester, competitive_intel, risk_synthesizer, strategy_commander
FULL_BRIEFING     → signal_harvester → (narrative ∥ macro ∥ competitive, parallel)
                    → risk_synthesizer → strategy_commander
```

Strip persistence only updates for:
```python
_STRIP_UPDATE_INTENTS = frozenset({
    "FULL_BRIEFING", "MACRO_FOCUS", "COMPETITIVE_FOCUS", "DECISION_SUPPORT", "SCENARIO"
})
```
