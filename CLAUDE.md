# CLAUDE.md — Vigil

Multi-agent financial risk intelligence platform. 8 specialized Claude agents run in
orchestrated waves **inside a single FastAPI process**, turning live market data
(yfinance + NewsAPI) into a scored (0–100), tiered risk briefing personalized to a
company profile.

**Current mission:** portfolio-grade revamp. The plan of record is
`docs/REVAMP_PLAN.md` — read it before making changes, execute it line by line, and
tick checkboxes as work lands. Its "Decisions & Reasons" section explains *why*; do
not relitigate settled decisions without the user.

## Architecture (post-revamp, single process)

- `main.py` — FastAPI app: serves HTML pages, session APIs, calls the engine directly.
- `agent_pipeline.py` — the engine. `run_pipeline(message, profile, history)` routes
  one of 7 intents to agent waves (Wave 2 runs 3 agents in parallel via ThreadPoolExecutor).
  Framework-free: no Streamlit, no LangGraph, no HTTP between agents.
- `data_layer.py` — live market data (yfinance, NewsAPI), 60s cache, degrades gracefully.
- `session_store.py` — JSON file persistence (`sessions.json`, gitignored).
- `prompts/*.txt` — one system prompt per agent. Prompt changes = product changes; keep
  output-format sections intact (the parser depends on them).
- `static/` + `vigil-*.html` — vanilla JS/CSS frontend (no build step).

## Run

```bash
pip install -r requirements.txt
cp .env.example .env   # add keys
uvicorn main:app --port 3000
```

Env: `AIML_API_KEY` (or `LLM_API_KEY` + `LLM_BASE_URL` for any OpenAI-compatible
endpoint), `NEWSAPI_KEY`, optional `VIGIL_MODEL` (overrides all agent models).

## Rules

- **One process.** Never reintroduce agent microservices, inter-agent HTTP, or a second
  frontend. New agents = a prompt file + a routing entry in `agent_pipeline.py`.
- **The engine stays framework-free.** `agent_pipeline.py` must import neither Streamlit
  nor FastAPI; it takes plain dicts and returns a plain dict. Persistence belongs to the
  caller (`main.py`).
- **Secrets via env only.** Never hardcode keys, never commit `.env` or `sessions.json`.
- Python 3.12, type hints on public functions, module-level docstrings match the
  existing style. Frontend stays dependency-free vanilla JS.

## Guardrails (non-negotiable — this project's history is the reason)

1. **No fabricated data, ever.** No hardcoded risk scores, fake briefings, "demo mode"
   fallbacks, or invented statistics anywhere in code or UI. If real analysis is
   unavailable, say so in the response ("no analysis yet — run a briefing").
   The hackathon version shipped fake payloads; we removed them. Never bring them back.
2. **README claims must match the code.** Model names, parallelism, timing, agent
   counts — verify by reading the code before writing the claim.
3. **Every LLM-generated number shown to users must be labeled as analysis, not fact.**
   Vigil gives perspective, not certified financial advice — keep disclaimers intact.
4. **Don't break the 90-second reviewer test:** repo must always install and boot with
   the documented commands, even with no API keys (graceful degradation).
5. Destructive ops (deleting files, force pushes, rewriting `main`) — branch first,
   confirm with the user.

## Verification

Use the `verify-vigil` skill (`.claude/skills/verify-vigil/`) before declaring any
change done. Minimum bar: `python -m py_compile` on touched files, app boots, affected
endpoint exercised, no-keys degradation still graceful.
