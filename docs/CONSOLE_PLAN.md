# Vigil Console — Product Plan & Wireframes

> Plan of record for the terminal product. Approved by user before implementation
> continues. The engine (8 agents, tools, MCP) is built; this defines the **human
> experience** on top of it.

## 1. What Vigil is (the pitch)

**A financial-risk copilot that lives in your terminal and knows your company.**
You describe your company once. From then on, every question — "how exposed are we
to the new EU rules?", "should I delay the US expansion?" — is answered by 8
specialized agents pulling **live market data** and reasoning **about your
situation**, not generically. You literally watch them work.

What's unique (the interview answer):
1. **Personalized, not generic** — a persistent company profile drives every analysis.
2. **Grounded, not hallucinated** — scout agents *call tools* for live prices/news;
   no fabricated numbers, honest degradation.
3. **Visible orchestration** — the live agent-wave view shows routing, parallelism,
   and per-agent timing as it happens.
4. **Two front-ends, one engine** — humans get the console; AI clients (Claude
   Desktop/Cursor) get the same engine via MCP.

## 2. Who uses it, and how (use cases)

| # | User | Flow | Time |
|---|---|---|---|
| UC1 | Founder, weekly check-in | `vigil` → `/brief` → read score/risks/actions → ask follow-ups (history-aware) | ~1–2 min |
| UC2 | Anyone, quick verdict | `vigil verdict "should I buy TSLA?"` — Oracle + live data, one shot | ~15–30 s |
| UC3 | Operator, what-if | `vigil` → "what happens to us if the Fed cuts rates?" (SCENARIO intent) | ~1 min |
| UC4 | The user, demoing in an interview | `/agents` roster → `/brief` → watch the wave; `docs/AGENT_ARCHITECTURE.md` is the talk track | ~3 min |
| UC5 | AI-tool user | Add `vigil_mcp.py` to Claude Desktop → "run a risk briefing on Acme" | one-time setup |

## 3. Command surface

**Main door:** `vigil` (no args) → interactive console. Profile + conversation
history persist across launches (`sessions.json`, local, gitignored).

In-console commands:

| Command | Does |
|---|---|
| `/profile` | setup/edit wizard (9 fields, 2 required, Enter skips) |
| `/profile show` | view saved profile |
| `/brief` | full risk briefing for your company (all waves) |
| `/agents` | the roster — who does what, which model, which tools |
| `/history` | recent conversation |
| `/clear` | clear history |
| `/help`, `/exit` | obvious |
| *anything else* | a question → routed by the Orchestrator with profile + history |

**Scripting one-shots:** `vigil brief`, `vigil ask "…"`, `vigil verdict "…"` —
same engine, no REPL (usable in cron/CI/demos).

## 4. Wireframes

### W1 — First launch (onboarding)
```
$ vigil
╭──────────────────────────────────────────────────────────────╮
│  VIGIL — multi-agent financial risk intelligence             │
│  8 agents · live market data · analysis for YOUR company     │
╰──────────────────────────────────────────────────────────────╯

No company profile yet. Vigil's whole point is analysis for
YOUR company — let's set that up (30 seconds, stays on your machine).

Set up your profile now? [Y/n] y

╭─ Profile setup ──────────────────────────────────────────────╮
│ Enter keeps current value · '-' clears · * required          │
╰──────────────────────────────────────────────────────────────╯
Company name *:                Acme Fintech
What does the company do *:    cross-border payments for SMBs
Sector:                        Fintech
Stage:                         Series A
Primary market / HQ country:   Germany
Revenue or ARR range:          $1–5M
Runway:                        14 months
Decisions on the table:        hiring in EU, US expansion
Known risk exposures:          FX, EU regulation

✓ Profile saved locally. Try /brief — or just ask a question.
vigil> _
```

### W2 — Returning user
```
$ vigil
╭──────────────────────────────────────────────────────────────╮
│  VIGIL                                                       │
╰──────────────────────────────────────────────────────────────╯
Welcome back — Acme Fintech · last risk score 61/100 (ELEVATED)
/help for commands, or just ask.

vigil> how exposed are we to the new EU payment rules?
```

### W3 — Live agent wave (while a question runs)
```
╭─ Vigil — analyzing ──────────────────────────────────────────╮
│ ●  orchestrator       complete  2.1s  routed → MACRO_FOCUS   │
│ ◑  signal_harvester   running    …    pulling live data      │
│      ↳ called get_market_pulse · get_live_headlines          │
│ ◔  macro_watchdog     queued          rates, FX, policy      │
│ ◔  risk_synthesizer   queued          scores the risk        │
│ ○  narrative_intel    idle                                   │
│ ○  competitive_intel  idle                                   │
│ ○  strategy_commander idle                                   │
│ ○  market_oracle      idle                                   │
╰──────────────────────────────────────────────────────────────╯
```
The `↳ called …` line is **new**: the engine will emit tool-call events so the
view shows *which live data* each scout fetched. (Small addition to
`agent_core` status events.)

### W4 — Briefing result
```
╭─ Verdict ────────────────────────────────────────────────────╮
│ Risk 61/100 (ELEVATED) — FX and PSD3 are the live risks      │
╰──────────────────────────────────────────────────────────────╯
╭─ Executive brief ────────────────────────────────────────────╮
│ Euro exposure and the incoming PSD3 rules are the two        │
│ material risks for Acme this quarter. …                      │
╰──────────────────────────────────────────────────────────────╯
Top risks
  • FX volatility — 40% of revenue in EUR
  • PSD3 compliance — new licensing burden

Recommended actions
  • Hedge EUR exposure (by Q3)
  • Start a PSD3 gap analysis

4 agents · 48s · Vigil analysis, not financial advice.
vigil> and if the euro drops another 5%?          ← follow-up uses history
```

### W5 — `/agents` (the demo screen)
```
╭─ The 8 agents ───────────────────────────────────────────────╮
│ agent               model   tools                 role       │
│ orchestrator        sonnet  —                     routes …   │
│ signal_harvester    haiku   pulse,sectors,news    scout …    │
│ narrative_intel     sonnet  —                     media …    │
│ macro_watchdog      sonnet  —                     rates …    │
│ competitive_intel   sonnet  —                     rivals …   │
│ risk_synthesizer    sonnet  —                     scores …   │
│ strategy_commander  sonnet  —                     actions …  │
│ market_oracle       haiku   stock,pulse           verdicts … │
╰──────────────────────────────────────────────────────────────╯
```

### W6 — MCP (the AI front-end)
```jsonc
// claude_desktop_config.json
{ "mcpServers": { "vigil": {
    "command": "python", "args": ["/path/to/vigil_mcp.py"],
    "env": { "AIML_API_KEY": "…" } } } }
```
Then in Claude Desktop: *"Run a risk briefing on Acme Fintech, a German
cross-border payments startup"* → Claude calls Vigil's `risk_briefing` tool.

## 5. State & persistence

- `sessions.json` (local, gitignored, `VIGIL_DATA_DIR`-relocatable):
  `profile` (the 9 fields) · `history` (last 40 turns, fed back into the
  pipeline) · `last_risk_score/tier` (shown on welcome).
- No accounts, no server, no data leaves the machine except LLM/data API calls.

## 6. Build plan (after approval)

1. **Console per these wireframes** — mostly built; add tool-call events
   (engine emits, wave view renders the `↳ called …` line).
2. **Verify offline** — scripted console session with mocked pipeline
   (wizard → persist → relaunch → history fed back).
3. **Live test with the user's key** — `verdict` first (fast path proves LLM +
   tool-calling), then a full `/brief`.
4. **README rewrite** around the console + MCP story; update REVAMP_PLAN;
   commit + PR.

## 7. Open questions (user to decide)

- Keep the one-shot subcommands (`brief/ask/verdict`)? (Recommend yes — free, scriptable.)
- Multiple profiles (e.g. compare two companies) — v2, not now?
- Demo GIF for the README once live test passes?
