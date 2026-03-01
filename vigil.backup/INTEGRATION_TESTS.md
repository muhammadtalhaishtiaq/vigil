# Vigil — Integration Tests

> 9 test scenarios covering end-to-end wiring.
> Run these manually before each production deployment.

---

## Setup

```bash
# Start the app
streamlit run app.py

# Open: http://localhost:8501  (or your deployed URL)
# Enable terminal logs to see INFO/DEBUG output:
# LOG_LEVEL=DEBUG streamlit run app.py
```

---

## Test Scenarios

### TEST 1 — Auto-load fires exactly once on fresh session

**Precondition:** Complete company profile saved (completeness ≥ 70%)

**Steps:**
1. Open the dashboard in a new incognito/private browser tab
2. Observe the chat thread

**Expected behavior:**
- A single auto-briefing fires and populates the chat
- Risk/action strip appears after briefing completes
- Verdict bar shows risk score (not "--")

**Anti-patterns to watch for:**
- Two briefings firing (loop)
- Briefing firing but history showing duplicate messages

- [ ] Auto-briefing fires exactly **once** on first load
- [ ] Verdict bar score populates (not "--")
- [ ] Risk strip shows ≥ 1 risk chip
- [ ] No duplicate briefing messages in chat

---

### TEST 2 — Profile context injected into Orchestrator

**Precondition:** Company profile has name, sector, country, and ≥ 1 regulation

**Steps:**
1. Open terminal running the app
2. Set log level to INFO if not already
3. Submit any query (e.g., "What's our risk level?")
4. Check terminal output

**Expected log line:**
```
STEP 1 complete — profile_used: True | full_context: XXXX chars | ...
```

- [ ] Log shows `profile_used: True`
- [ ] `full_context` char count is > 200 (profile injected)
- [ ] Response references the company name or sector

---

### TEST 3 — Generic mode activates without profile

**Precondition:** No company profile, or profile completeness < 30%

**Steps:**
1. Clear/skip profile setup
2. Submit any query (e.g., "market check")
3. Check terminal for DEBUG log

**Expected log:**
```
No profile active — pipeline will run in GENERIC market-analysis mode
```

**Expected response:**
- References real market conditions
- Does NOT contain `[Company Name]` or other blank placeholders

- [ ] DEBUG log present: "GENERIC market-analysis mode"
- [ ] Response contains real market data (VIX, sectors, or specific asset)
- [ ] No placeholder text like `[Company]` or `[Sector]` in response

---

### TEST 4 — Agent header animates during pipeline execution

**Precondition:** Any query that triggers ≥ 3 agents

**Steps:**
1. Submit "full briefing" query
2. Watch the header agent nodes during processing (~10-30s)

**Expected behavior:**
- Nodes transition from idle (gray dot) → active (green pulsing dot) → done (green static)
- Orchestrator lights up first, then specialists in sequence

- [ ] At least 3 header nodes animate during execution
- [ ] All nodes show "done" state after pipeline completes
- [ ] Header does not flicker or disappear mid-pipeline

---

### TEST 5 — Risk strip persists after investment query

**Precondition:** A full briefing has been run (risk strip populated)

**Steps:**
1. Run a full briefing → confirm strip shows 3 risk chips
2. Ask an investment question: "Should I buy NASDAQ stocks?"
3. Wait for Oracle response
4. Observe the risk strip

**Expected behavior:**
- Oracle tab populates with BUY/WAIT/CAUTION/AVOID verdict
- **Risk strip still shows the original risks from the briefing** (not cleared)
- Log shows: `Strip persistence skipped for intent 'INVESTMENT_QUERY'`

- [ ] Risk strip unchanged after INVESTMENT_QUERY
- [ ] Oracle tab shows verdict card
- [ ] Log: `Strip persistence skipped for intent 'INVESTMENT_QUERY'`

---

### TEST 6 — Generic mode produces real market intelligence

**Precondition:** No company profile set

**Steps:**
1. Submit: "Give me a market overview for the week"
2. Read the response

**Expected behavior:**
- Response discusses current market conditions (sectors, VIX, macro)
- No "As [Company Name]..." or "Your [sector]..." templates
- Response is actionable for a general investor/reader

- [ ] Response references real assets or indices (NASDAQ, VIX, S&P, etc.)
- [ ] No company-specific placeholder text
- [ ] Response length is substantial (>100 words)

---

### TEST 7 — Investment keywords route to INVESTMENT_QUERY

**Steps (run each):**

| Input | Expected Intent | Expected Tab |
|-------|----------------|-------------|
| "Should I buy AAPL right now?" | `INVESTMENT_QUERY` | Oracle populates |
| "Is gold a good safe haven?" | `INVESTMENT_QUERY` | Oracle populates |
| "NVDA outlook this quarter" | `INVESTMENT_QUERY` | Oracle populates |
| "Give me a full risk briefing" | `FULL_BRIEFING` | All tabs populate |
| "What's the macro situation?" | `MACRO_FOCUS` | Risk tab updates |

**Check via:**
1. Terminal logs showing `Investment keyword detected → INVESTMENT_QUERY routing hint injected`
2. Correct tab activating after response

- [ ] "buy AAPL" → `INVESTMENT_QUERY` → Oracle tab
- [ ] "gold safe haven" → `INVESTMENT_QUERY` → Oracle tab
- [ ] "full risk briefing" → `FULL_BRIEFING` → Risk + Actions tabs
- [ ] "macro situation" → `MACRO_FOCUS` → Risk tab (NOT Oracle)

---

### TEST 8 — Quick-prompt chips fill the chat input

**Steps:**
1. Click any chip in the verdict bar (e.g., "MiCA →")
2. Observe the chat text input field

**Expected behavior:**
- Text input fills with chip text (minus the "→")
- Input field gains focus
- User can press Enter to submit

**Also test:**
- Sector heatmap cell click → input fills with "Analyze risk for [Sector] sector"
- Oracle tab example chips → input fills with investment question

- [ ] Verdict bar chips fill chat input
- [ ] Sector heatmap clicks fill chat input
- [ ] Oracle tab chips fill chat input
- [ ] Input gains focus after fill

---

### TEST 9 — Profile save redirect does not trigger duplicate briefing

**Precondition:** A briefing has already been run in the current session

**Steps:**
1. Run a briefing (chat has messages)
2. Navigate to Profile page (`Set up profile →` or directly)
3. Make any edit (e.g., change a word in company description)
4. Click **Save**
5. Observe redirect to dashboard
6. Wait 5 seconds

**Expected behavior:**
- Profile saves and redirects correctly
- **No new briefing fires** (history already exists)
- Chat thread shows previous messages unchanged

**Anti-pattern to watch for:**
- A new "Auto-brief" message appearing after profile save redirect

- [ ] Profile saves successfully
- [ ] Redirect to dashboard occurs
- [ ] No new auto-briefing fires
- [ ] Previous chat history preserved

---

## Regression Smoke Test

Run after all 9 tests pass:

| Scenario | Command / Action | Expected | ✓ |
|----------|-----------------|----------|---|
| Fresh load, no profile | New incognito tab | Generic welcome, no auto-brief | ☐ |
| Fresh load, complete profile | New incognito tab | Single auto-brief fires | ☐ |
| "full briefing" | Type + submit | All 8 agents in header, strip updates | ☐ |
| "Should I buy gold?" | Type + submit | Oracle tab, strip unchanged | ☐ |
| "ECB rate scenario" | Type + submit | SCENARIO intent, strip updates | ☐ |
| Profile chip click | Click verdict bar chip | Input fills, submit works | ☐ |
| Profile save → redirect | Edit profile, save | No duplicate briefing | ☐ |
| Health check | `python health_check.py` | All 3/3 PASS | ☐ |

---

## Known Edge Cases

| Scenario | Current Behavior | Notes |
|----------|-----------------|-------|
| AIML API timeout (>30s) | Agent returns empty string, pipeline continues | Graceful degradation |
| NewsAPI rate limit | Fallback headlines used, `data_quality: MINIMAL` | User sees "No headlines" |
| yfinance rate limit | Sector data empty, sectors panel hides | Auto-retry on next 60s cache cycle |
| Very short message ("ok") | Routes to `MARKET_PULSE` | Correct fallback behavior |
| Message with no keywords | Orchestrator defaults to `FULL_BRIEFING` | Safe default |

---

*Generated for VIGIL · Complete AI Agent Hackathon · lablab.ai · 2026*
