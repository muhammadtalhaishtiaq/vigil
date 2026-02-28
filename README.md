# ⚡ VIGIL — Autonomous Financial Risk Intelligence

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Streamlit-FF4B4B?style=flat&logo=streamlit)](https://nm285lam.run.complete.dev)
[![Built on Complete.dev](https://img.shields.io/badge/Built%20on-Complete.dev-00e676?style=flat)](https://complete.dev)
[![lablab.ai Hackathon](https://img.shields.io/badge/lablab.ai-Complete%20AI%20Agent%20Hackathon-blue?style=flat)](https://lablab.ai)
[![MIT License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

---

## What is Vigil?

Vigil is an autonomous multi-agent financial risk intelligence platform that runs 8 specialized AI agents in parallel to deliver a complete risk briefing in under 90 seconds. It connects live market data (NewsAPI + yfinance) with an 8-agent Claude-powered pipeline to produce scored, tiered, actionable intelligence — personalized to your company profile. Built entirely on Complete.dev for the Complete AI Agent Hackathon on lablab.ai.

---

## Two Use Cases

### 🏢 For Founders & Executives
Set up a company profile once (sector, stage, regulations, decisions). Every query triggers a full risk briefing calibrated to your business — MiCA compliance windows, competitive shifts, macro headwinds, and a prioritized action playbook.

### 💹 For Investors & Anyone
No setup required. Ask Market Oracle any investment question in plain English: *"Should I buy NASDAQ stocks right now?"* Get a clear **BUY / WAIT / CAUTION / AVOID** verdict with bull case, bear case, historical parallel, and Vigil's take.

---

## Architecture

```
                         ┌────────────────────────────────┐
  User Query ───────────►│        ORCHESTRATOR             │
                         │  Intent classification + route  │
                         └─────────────┬──────────────────┘
                                       │
          ┌────────────────────────────┼─────────────────────────────┐
          │                            │                             │
          │ FULL_BRIEFING              │ INVESTMENT_QUERY            │ MARKET_PULSE
          │ MACRO_FOCUS                │                             │
          │ COMPETITIVE_FOCUS          │                             │
          │ DECISION_SUPPORT           │                             │
          │ SCENARIO                   │                             │
          ▼                            ▼                             ▼
  ┌───────────────────┐      ┌─────────────────────┐      ┌──────────────────┐
  │ Signal Harvester  │      │  Signal Harvester   │      │ Signal Harvester │
  │ Narrative Intel   │      │  (prices + VIX)     │      │ (brief pulse)    │
  │ Macro Watchdog    │      │                     │      └──────────────────┘
  │ Competitive Intel │      │  Market Oracle      │
  │ Risk Synthesizer  │      │  BUY / WAIT /       │
  │ Strategy Cmdr     │      │  CAUTION / AVOID    │
  │ Market Oracle     │      └─────────────────────┘
  └────────┬──────────┘
           │
           ▼
  Risk Score 0–100 · Tier (Green/Yellow/Orange/Red/Black)
  Top 3 Risks · 3 Priority Actions · Strategy Playbook
  Verdict sentence · Specialist outputs for analysis tabs
```

**8 Agents · 7 Routing Intents · 2 Primary Paths**

| Intent | Agents Activated | Use Case |
|--------|-----------------|----------|
| `FULL_BRIEFING` | All 8 | "Give me a complete risk briefing" |
| `MACRO_FOCUS` | Orchestrator, Signal, Macro, Risk | "What's the macro outlook?" |
| `COMPETITIVE_FOCUS` | Orchestrator, Signal, Competitive, Risk | "Competitive landscape?" |
| `DECISION_SUPPORT` | Orchestrator, Signal, Macro, Strategy, Risk | "Should I delay Series A?" |
| `SCENARIO` | Orchestrator, Macro, Narrative, Risk, Strategy | "ECB rate hike scenario" |
| `INVESTMENT_QUERY` | Orchestrator, Signal, Oracle | "Should I buy gold?" |
| `MARKET_PULSE` | Orchestrator, Signal | "Quick market check" |

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/vigil.git
cd vigil

# 2. Set environment variables
cp .env.example .env
# Edit .env with your AIML_API_KEY and NEWSAPI_KEY

# 3. Install and run
pip install -r requirements.txt
streamlit run app.py
```

App opens at **http://localhost:8501**

---

## Environment Variables

| Variable | Required | Where to get it |
|----------|----------|-----------------|
| `AIML_API_KEY` | ✅ Yes | [aimlapi.com](https://aimlapi.com) — free tier available |
| `NEWSAPI_KEY` | ✅ Yes | [newsapi.org/register](https://newsapi.org/register) — free tier: 100 req/day |
| `NEWSAPI_KEY` yfinance | ❌ No key needed | Uses Yahoo Finance public feeds automatically |

For Streamlit Cloud deployment, add both keys via **Settings → Secrets** (not `.env`).

---

## The 8 Agents

| # | Agent | Role | Input | Output | Active for |
|---|-------|------|-------|--------|------------|
| 1 | **Orchestrator** | Master router + synthesizer | User query + full context | Intent type + initial synthesis | All intents |
| 2 | **Signal Harvester** | Live market data collector | Live prices, VIX, sector data | Structured market signals | All intents |
| 3 | **Narrative Intel** | Hidden signal detector | News headlines + sentiment | Early warning signals from narrative | FULL_BRIEFING, SCENARIO |
| 4 | **Macro Watchdog** | Macro environment analyst | Macro indicators + sector data | Business impact of macro trends | FULL_BRIEFING, MACRO_FOCUS, DECISION_SUPPORT, SCENARIO |
| 5 | **Competitive Intel** | Competitive landscape tracker | Market data + headlines | Competitor positioning & shifts | FULL_BRIEFING, COMPETITIVE_FOCUS |
| 6 | **Risk Synthesizer** | Risk scorer & prioritizer | All specialist outputs | 0–100 score, tier, top 3 risks, 3 actions | FULL_BRIEFING + briefing intents |
| 7 | **Strategy Commander** | Action playbook generator | Risk synthesis + profile | Prioritized 3-action playbook | FULL_BRIEFING, DECISION_SUPPORT |
| 8 | **Market Oracle** | Investment verdict engine | Live market data + query | BUY/WAIT/CAUTION/AVOID + bull/bear/take | INVESTMENT_QUERY, FULL_BRIEFING |

**Idle for `INVESTMENT_QUERY`:** Narrative Intel, Macro Watchdog, Competitive Intel, Risk Synthesizer, Strategy Commander

**Idle for `MARKET_PULSE`:** Narrative Intel, Macro Watchdog, Competitive Intel, Risk Synthesizer, Strategy Commander, Market Oracle

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | Streamlit 1.35+ | Multi-page dashboard |
| UI Design | Pure CSS (DM Mono + Cabinet Grotesk) | Bloomberg-meets-Vercel dark theme |
| AI Agents | AIML API (OpenAI-compatible) | Claude claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001 |
| Market Data | yfinance | Real-time prices, VIX, sector ETFs |
| News | NewsAPI.org | Live financial headlines + sentiment |
| State | Streamlit session_state | Profile, conversation, agent statuses |
| Config | python-dotenv + st.secrets | Local `.env` + Streamlit Cloud secrets |
| Deployment | Streamlit Cloud | Zero-infra public deployment |

---

## Project Structure

```
vigil/
├── app.py                      # Main dashboard (Streamlit multi-page root)
├── agent_pipeline.py           # 8-agent orchestration engine
├── session_manager.py          # Profile CRUD + conversation state
├── data_layer.py               # Live data (NewsAPI + yfinance, 60s cache)
│
├── pages/
│   └── profile.py              # Company profile setup (4-section form)
│
├── prompts/                    # System prompt templates for all 8 agents
│   ├── orchestrator.txt
│   ├── signal_harvester.txt
│   ├── narrative_intel.txt
│   ├── macro_watchdog.txt
│   ├── competitive_intel.txt
│   ├── risk_synthesizer.txt
│   ├── strategy_commander.txt
│   └── market_oracle.txt
│
├── .streamlit/
│   ├── config.toml             # Dark theme + server config
│   └── secrets.toml.example    # Secret keys template
│
├── vigil-landing.html          # Standalone marketing landing page
│
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable template
├── .gitignore                  # Git ignore (secrets, __pycache__, logs)
├── health_check.py             # Pre-deploy API connectivity check
│
├── README.md                   # This file
├── LICENSE                     # MIT License
├── AGENTS.md                   # All 8 agents documented
├── CONTRIBUTING.md             # Contribution guide
├── INTEGRATION_CHECKLIST.md    # 9-point integration test checklist
├── INTEGRATION_TESTS.md        # Extended test scenarios
└── STREAMLIT_DEPLOY.md         # Step-by-step cloud deployment guide
```

---

## Running the Health Check

Before deploying, verify all external API connections:

```bash
python health_check.py
# Expected output:
# ✓ PASS  NewsAPI    — HTTP 200 · N results
# ✓ PASS  yfinance   — ^VIX = XX.XX
# ✓ PASS  AIML API   — response: 'OK'
# All 3/3 checks passed — safe to deploy ✓
```

---

## License

MIT — see [LICENSE](LICENSE). Free to use, modify, and distribute with attribution.

Built for the **Complete AI Agent Hackathon** on [lablab.ai](https://lablab.ai) · February 2026.
