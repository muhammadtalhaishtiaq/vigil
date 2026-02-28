# Vigil — Integration Checklist
> 9-point end-to-end wiring pass · Complete AI Agent Hackathon

---

## How to use this checklist
1. Start the app: `streamlit run vigil/app.py`
2. Work through each numbered item top-to-bottom.
3. Tick the checkbox once you have **manually verified** the behaviour.
4. Red items are blocking (demo will break). Orange items are UX polish.

---

## Pre-flight

- [ ] `.env` contains `AIML_API_KEY`, `NEWS_API_KEY` (or graceful fallback confirmed)
- [ ] `pip install -r requirements.txt` completes without errors
- [ ] `streamlit run vigil/app.py` reaches the dashboard without Python exceptions

---

## Fix 1 — Auto-load fires only on a fresh session  *(blocking)*
**What was wrong:** `should_auto_load()` returned `True` even when the user had already been chatting, causing duplicate briefings after every page reload post-profile-save.

**Fix applied:** Guard now also checks `not get_conversation_history()`.

**Manual test:**
1. Open dashboard with a complete profile → confirm auto-briefing fires once.
2. Ask a follow-up question → press Enter → page reruns → **confirm no second briefing**.
3. Open a fresh tab → confirm single briefing only.

- [ ] Auto-briefing fires exactly once on first load with a complete profile
- [ ] No duplicate briefing after user input + page rerun

---

## Fix 2 — Profile context logged at pipeline start  *(debug / traceability)*
**What was wrong:** No way to confirm during a run whether the company profile was actually injected into the Orchestrator prompt.

**Fix applied:** `logger.info()` after STEP 1 logs `profile_used`, `full_context` char count, `enhanced_msg` char count, and `data_quality`.

**Manual test:**
1. Set terminal log level to INFO (`export LOG_LEVEL=INFO` or check Streamlit logs).
2. Submit a query with a complete profile loaded.
3. Confirm a log line like: `STEP 1 complete — profile_used: True | full_context: XXXX chars`.

- [ ] Log line appears with `profile_used: True` when profile is complete
- [ ] Log line appears with `profile_used: False` in generic mode

---

## Fix 3 — "No profile" debug message  *(debug / traceability)*
**What was wrong:** Silent failure when pipeline ran without a profile — no way to trace generic-mode activation.

**Fix applied:** `logger.debug("No profile active — pipeline will run in GENERIC market-analysis mode")`.

**Manual test:**
1. Clear / skip company profile setup.
2. Submit any query.
3. Confirm DEBUG log: `No profile active — pipeline will run in GENERIC market-analysis mode`.

- [ ] Debug log present when no profile is loaded

---

## Fix 4 — Agent flow header updates in real time  *(UX / demo wow)*
**What was wrong:** Agent nodes in the header (idle → running → complete) only changed state after the entire pipeline completed, defeating the live-status purpose.

**Fix applied:**
- `app.py`: Header rendered inside `st.empty()` slot; `_refresh_header()` callback stored in `st.session_state["_vigil_header_cb"]`.
- `agent_pipeline.py`: `update_agent_status()` calls the callback after every state transition.

**Manual test:**
1. Submit a full-briefing query.
2. Watch the header row during processing — dots should animate: `queued → running → complete` per agent.
3. Orchestrator node should pulse green first, then Signal Harvester, etc.

- [ ] Header nodes animate progressively during pipeline execution
- [ ] All nodes show `complete` (green) after pipeline finishes

---

## Fix 5 — Risk strip only updates on full-risk-analysis intents  *(data integrity)*
**What was wrong:** Asking a simple investment question (`"Should I buy AAPL?"`) overwrote `vigil_last_top_risks` / `vigil_last_top_actions` with empty lists from the Oracle path, clearing a valid prior briefing from the strip.

**Fix applied:** `_STRIP_UPDATE_INTENTS = {FULL_BRIEFING, MACRO_FOCUS, COMPETITIVE_FOCUS, DECISION_SUPPORT, SCENARIO}`. STEP 5 only persists strip state for these intents.

**Manual test:**
1. Run a full briefing → confirm Risk/Action strip populates with 3 items each.
2. Ask an investment question (`"Is gold a buy?"`).
3. Confirm the strip **still shows the original risks/actions** (not cleared).

- [ ] Strip persists after an INVESTMENT_QUERY follows a FULL_BRIEFING
- [ ] Strip updates correctly when a new FULL_BRIEFING is run

---

## Fix 6 — Generic mode instruction injected when no profile  *(AI quality)*
**What was wrong:** Without a profile, the Orchestrator received no indication it should default to general market analysis, sometimes producing corporate-specific templates with blank fields.

**Fix applied:** `orchestrator_input` gets appended: `[MODE: GENERIC — No company profile loaded. Provide general market intelligence…]`

**Manual test:**
1. Use dashboard without a profile.
2. Ask: `"Give me a market overview"`.
3. Confirm the response discusses broad market conditions, not placeholders like `[Company Name]`.

- [ ] Generic responses reference real market data rather than blank company fields
- [ ] Personalized responses (with profile) still reference the company by name

---

## Fix 7 — Investment keyword → INVESTMENT_QUERY routing hint  *(intent routing)*
**What was wrong:** Queries like `"Should I buy NVDA?"` were sometimes classified as `FULL_BRIEFING`, activating 7 agents instead of the lean Oracle path (3 agents).

**Fix applied:** `_inv_kw` regex detects buy/sell/ticker/crypto/stock keywords in the raw user message and appends a routing hint to `orchestrator_input`.

**Manual test:**
1. Ask: `"Is it a good time to buy Tesla stock?"` — confirm intent routes to `INVESTMENT_QUERY` (check Streamlit logs or Oracle tab activates).
2. Ask: `"Give me a full risk briefing"` — confirm intent stays `FULL_BRIEFING`.

- [ ] `"Should I buy AAPL?"` → `INVESTMENT_QUERY` → Oracle tab populates
- [ ] `"Full briefing"` → `FULL_BRIEFING` → all 7 agents activate
- [ ] Investment routing does not break non-investment queries

---

## Fix 8 — `vigilFillInput()` JS chip → text box fill  *(UX)*
**What was wrong:** `querySelectorAll('input[type="text"]')` sometimes targeted hidden/stale inputs in Streamlit's virtual DOM, leaving the visible chat input unfilled.

**Fix applied:** Primary selector now targets `[data-testid="stTextInput"] input`; falls back to last visible text input; dispatches both `input` and `change` events for React compatibility.

**Manual test:**
1. Click any chip button in the verdict bar (e.g., `"MiCA →"`).
2. Confirm the chat text input field is filled with the chip text.
3. Click a sector heatmap cell — confirm `"Analyze risk for Technology sector"` fills the input.

- [ ] Verdict bar chips fill the chat input correctly
- [ ] Sector heatmap cell clicks fill the chat input correctly
- [ ] Oracle tab example chips fill the chat input correctly

---

## Fix 9 — Auto-load doesn't re-fire after profile page save  *(blocking)*
**What was wrong:** `pages/profile.py` calls `st.switch_page("app.py")` after saving. On the redirected load, `should_auto_load()` returned `True` again (session was new), firing a second briefing even though the user just navigated back.

**Fix applied:** Same as Fix 1 guard — `not get_conversation_history()` prevents a re-trigger if the redirect carries over any prior state.

**Manual test:**
1. Start fresh → go to Profile page → fill and save.
2. Observe redirect to dashboard → one auto-briefing fires.
3. Navigate back to Profile → make a small edit → save again.
4. Confirm **no second auto-briefing** fires on return (history already exists).

- [ ] Profile save → dashboard redirect → exactly one briefing
- [ ] Second profile edit → save → no duplicate briefing

---

## Regression smoke test (run after all fixes verified)

| Scenario | Expected | Pass? |
|----------|----------|-------|
| Fresh session, no profile | Generic welcome + no auto-brief | ☐ |
| Fresh session, complete profile | Single auto-brief fires | ☐ |
| `"full briefing"` query | 7 agents activate, strip updates | ☐ |
| `"Should I buy gold?"` query | Oracle tab populates, strip unchanged | ☐ |
| `"ECB rate scenario"` query | `SCENARIO` intent, strip updates | ☐ |
| Profile chip click | Input fills, form submits on Enter | ☐ |
| Profile save → redirect | Single briefing, no loop | ☐ |

---

*Generated by Vigil integration pass · 2026-02-26*
