---
name: verify-vigil
description: >
  Verify Vigil actually works after a change: compile check, boot the FastAPI app,
  exercise the affected endpoints, and confirm graceful no-keys degradation. Use
  before marking any task complete or committing a nontrivial change.
---

# Verify Vigil

## 1. Static checks (always)

```bash
python3 -m py_compile main.py agent_pipeline.py data_layer.py session_store.py
python3 -c "import agent_pipeline"   # must succeed without streamlit installed
grep -n "streamlit\|session_manager" agent_pipeline.py   # expect no hits
```

## 2. Boot (always)

```bash
uvicorn main:app --port 3000  # run in background, then:
curl -s http://localhost:3000/health
```

Expected: JSON with `"status": "healthy"`. Boot must succeed **even with no API keys**.

## 3. Endpoint smoke (pick what the change touched)

```bash
curl -s http://localhost:3000/                       # landing HTML
curl -s http://localhost:3000/dashboard              # dashboard HTML
curl -s http://localhost:3000/api/market/pulse       # live data (yfinance, no key)
curl -s http://localhost:3000/api/intelligence/analyze
curl -s -X POST http://localhost:3000/api/chat -H 'Content-Type: application/json' \
     -d '{"message": "quick market check"}'
```

## 4. Interpret results honestly

- **No keys set:** chat should return an honest degraded response (agent unavailable
  placeholders), never a fake briefing. Market pulse should still return live yfinance
  data. `/api/intelligence/analyze` without a prior briefing must return a
  "no analysis yet" state, not numbers.
- **Keys set (user-provided):** a chat message must produce a real briefing and update
  the risk strip (`/api/session/dashboard` reflects new score/tier).
- Any hardcoded score/text in a response = guardrail violation — stop and fix.

## 5. Cleanup

Kill the uvicorn process you started. Never leave servers running past verification.
