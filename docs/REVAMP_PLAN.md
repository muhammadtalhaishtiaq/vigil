# VIGIL Revamp — Analysis & Execution Plan

> **Purpose of this document:** the single source of truth for turning Vigil from a
> hackathon build into a portfolio-grade project (GitHub / LinkedIn / job-profile
> highlight). We execute this plan **line by line** and check items off as they land.
>
> **Branch:** `revamp/single-process` · **Started:** 2026-07-03

---

## 1. Goal & Framing

**Goal:** minimal work, maximum credibility. Vigil must pass the "90-second reviewer
test" — a recruiter or engineer opens the repo and:

1. The README tells an honest, impressive story (multi-agent orchestration, real data).
2. The app runs with **one command** and **one API key**.
3. The code structure is clean — no duplicates, no dead code, no fake data.

**Positioning (the one-liner for GitHub/LinkedIn):**
> *Vigil — a multi-agent financial risk intelligence platform. 8 specialized Claude
> agents, orchestrated in parallel waves in a single process, turn live market data
> (yfinance + NewsAPI) into a scored, tiered risk briefing for any company profile.*

**Parked (explicitly out of scope for this revamp):**
- Hosted SaaS / auth / payments — revisit after portfolio version ships
- MCP server distribution — Phase 7 stretch goal, only after core is verified
- Grounded-citations engine ("no invented numbers") — the v2 product bet
- Stitch redesign — current dashboard is kept; Stitch screens saved as design refs

---

## 2. Audit Findings (what was wrong)

| # | Finding | Severity | Fix phase |
|---|---------|----------|-----------|
| 1 | 9-process architecture (8 FastAPI microservices + gateway) for what are 8 prompts | Critical — kills "plug and play" | P1–P2 |
| 2 | Triple code duplication: `agents/`, root-level agent folders, `vigil.backup/` | Critical — repo looks abandoned | P0 ✅ |
| 3 | README claims "Claude-powered, 8 agents in parallel"; microservices ran `gpt-4o` sequentially | Critical — honesty gap | P2, P4 |
| 4 | `/api/intelligence/analyze` + `/api/scores/breakdown` return **hardcoded fake risk data** (score 72, MiCA, "Thu Feb 27") | Critical — fake product | P2 |
| 5 | `main.py` "DEMO MODE" returns canned fake briefings on pipeline failure | Critical — fake product | P2 |
| 6 | `sessions.json` (real user session data) committed to git | High — privacy | P0 ✅ |
| 7 | Two frontends (Streamlit v1 + FastAPI v2) both in repo | High — confusion | P0 ✅ |
| 8 | Port chaos: agent code says 3003–3009, docs say 3022–3030, main.py defaults 3001 | Medium | P2 (moot after collapse) |
| 9 | `requirements.txt` still Streamlit-era; doesn't install what `main.py` needs | High — repo doesn't run | P3 |
| 10 | Hardcoded fallback `SECRET_KEY`, CORS `*` with credentials | Medium | P2 |
| 11 | NewsAPI free tier = 100 req/day single point of failure | Known limitation — document it | P4 |

**Key asset discovered:** `agent_pipeline.py` (Streamlit-era) already implements the
full 8-agent pipeline **in-process** with genuine `ThreadPoolExecutor` parallelism and
Claude models via AIML API. The revamp reuses it as the engine instead of rebuilding.

---

## 3. Target Architecture

### Before (hackathon)
```
Browser → FastAPI gateway (main.py, port 3029)
             │ HTTP
             ▼
          vigil-orchestrator (port 3030, LangGraph, gpt-4o)
             │ HTTP × 7, sequential
             ▼
          7 agent microservices (ports 3022–3028, gpt-4o)
```

### After (revamp)
```
Browser → FastAPI app (main.py, ONE process, ONE port)
             │ direct function call (threadpool)
             ▼
          agent_pipeline.run_pipeline(message, profile, history)
             ├─ Orchestrator (intent routing, 7 intents)
             ├─ Wave 1: Signal Harvester (live data framing)
             ├─ Wave 2: Narrative ∥ Macro ∥ Competitive  ← PARALLEL (real)
             ├─ Wave 3: Risk Synthesizer (score 0–100 + tier)
             └─ Wave 4: Strategy Commander / Market Oracle
          data_layer.py (yfinance + NewsAPI, 60s cache)
          session_store.py (JSON persistence, gitignored)
```

- **Models:** Claude (sonnet/haiku) via any OpenAI-compatible endpoint.
  Env-configurable: `LLM_BASE_URL`, `LLM_API_KEY` (fallback `AIML_API_KEY`), `VIGIL_MODEL` override.
- **Agent status streaming:** pipeline exposes `set_status_listener()`; the
  WebSocket `/ws` broadcasts statuses to the dashboard agent-flow UI.
- **Run:** `uvicorn main:app --port 3000` — that's it.

---

## 4. Execution Plan (follow line by line)

### Phase 0 — Repo hygiene ✅ DONE
- [x] Create branch `revamp/single-process`
- [x] Delete `vigil.backup/` (full duplicate of old app)
- [x] Delete root-level duplicate agent folders (8×: `signal-harvester/` … `vigil-orchestrator/`)
- [x] Delete `agents/` microservices (replaced by in-process engine)
- [x] Delete Streamlit v1: `app.py`, `pages/`, `session_manager.py`, `STREAMLIT_DEPLOY.md`
- [x] Delete `sessions.json` from git + add to `.gitignore`
- [x] Delete stale files: `take_screenshots.js`, `package.json`, `package-lock.json`,
      `VIGIL_AGENT_REGISTRATION.md`, `INTEGRATION_TESTS.md`, `INTEGRATION_CHECKLIST.md`, `run_e2e_tests.py`

### Phase 1 — Engine: decouple `agent_pipeline.py` from Streamlit ✅ DONE
- [x] Remove `import streamlit` and `import session_manager`
- [x] Secrets from env only (`_get_secret`)
- [x] Provider-agnostic LLM client (`LLM_BASE_URL` / `LLM_API_KEY` / `VIGIL_MODEL` override)
- [x] Module-level agent status registry + `set_status_listener()` (replaces `st.session_state`)
- [x] Pure-function profile/history context builders (ported from old `session_manager`)
- [x] `run_pipeline(user_message, profile=None, history=None)` signature
- [x] Remove STEP 5 `st.session_state` writes + `session_manager.add_message`
      (persistence becomes the caller's job)
- [x] `python -c "import agent_pipeline"` passes with no Streamlit installed

### Phase 2 — Gateway: `main.py` single-process rewiring ✅ DONE
- [x] Delete `ORCHESTRATOR_URL` + all HTTP orchestrator calls
- [x] `/api/chat` + `/api/chat/message` → call `run_pipeline()` via `asyncio.to_thread`,
      passing session profile + last 10 conversation turns
- [x] Map pipeline result → session fields (`last_risk_score`, `last_risk_tier`,
      `last_verdict`, `last_top_risks`, `last_top_actions`, `last_playbook`, `score_breakdown`)
- [x] **Delete DEMO MODE fake-briefing block** and `_infer_agents_from_message` theater
- [x] `/api/intelligence/analyze`: serve the session's **real** last analysis
      (or honest `run_briefing_first` state) — delete hardcoded MiCA payload
- [x] `/api/scores/breakdown`: serve real `score_breakdown` from last pipeline run —
      delete hardcoded scores
- [x] Wire pipeline status listener → session `agent_statuses` → existing `/ws` broadcast
- [x] `/health`: report engine mode `in-process`, API-key presence, data-layer reachability
- [x] Remove hardcoded `SECRET_KEY` fallback (generate ephemeral if unset); tighten CORS

### Phase 3 — Dependencies & config ✅ DONE
- [x] Rewrite `requirements.txt`: fastapi, uvicorn, itsdangerous, requests, yfinance,
      openai, python-dotenv, pandas (drop streamlit, langchain, langgraph, plotly)
- [x] Rewrite `.env.example`: `AIML_API_KEY` (or `LLM_API_KEY`+`LLM_BASE_URL`),
      `NEWSAPI_KEY`, `PORT`, optional `VIGIL_MODEL`
- [x] Update `health_check.py` if it references removed pieces

### Phase 3.5 — Project config for AI-assisted development ✅ DONE
- [x] Root `CLAUDE.md` — architecture, run commands, rules, guardrails
- [x] `.claude/settings.json` — safe permission allowlist, deny `.env`/`sessions.json` reads
- [x] `.claude/agents/honesty-auditor.md` — pre-ship audit agent (fake data, claim/code drift)
- [x] `.claude/skills/verify-vigil/SKILL.md` — end-to-end verification recipe

### Phase 4 — Story: README & docs ✅ DONE
- [x] Rewrite `README.md`: honest architecture diagram (waves, real parallelism),
      one-command quickstart, env table, screenshots, agent table, known limitations
      (NewsAPI free tier, LLM-generated analysis disclaimer)
- [x] Update `AGENTS.md` to match in-process architecture
- [x] Keep `CONTRIBUTING.md`, `LICENSE`; screenshots stay
- [x] Copy Stitch design explorations into `docs/design/` (they currently live in
      `../nexoux/stitch_design/` — wrong repo)

### Phase 5 — Verify (acceptance criteria) 🔄 (keys-required test pending)
- [x] Fresh venv: `pip install -r requirements.txt` succeeds
- [x] `uvicorn main:app` boots with **no keys** → pages load, APIs degrade gracefully
- [ ] With keys: chat message → real pipeline → briefing + risk strip update end-to-end
- [x] `grep` proves: no `streamlit` import, no fake data blocks, no orchestrator URLs
- [ ] Commit history on branch is clean and reviewable

### Phase 5.5 — Pre-ship honesty audit ✅ DONE (2026-07-04)
- [x] honesty-auditor agent run — 13 findings; all code/docs findings fixed:
      market-pulse key mismatch, client-side fake Oracle verdict, hardcoded HTML
      numbers, landing mock relabeled "simulated", heuristics labeled, AGENTS.md
      routing/format/tier corrections, honest parse-failure fallback
- [x] Stale runtime `sessions.json` deleted (gitignored)
- [ ] ⚠️ **CRITICAL (user action): live AIML API key exists in git HISTORY**
      (`STREAMLIT_DEPLOY.md` in commits 534b6cd→HEAD, already public on GitHub).
      → REVOKE the key at aimlapi.com immediately; optionally scrub history
      with `git filter-repo` before/after merging.

### Phase 6 — Ship
- [ ] Final commit + push branch, open PR to `main` (user approves merge)
- [ ] LinkedIn/portfolio blurb draft (project description + what it demonstrates)

### Phase 7 — Stretch (only after 0–6 verified)
- [ ] `vigil_mcp.py` — MCP server exposing `risk_briefing` / `market_verdict` tools
- [ ] Demo GIF for README

---

## 5. Decisions & Reasons (the "why" record)

Every settled decision, with its reason. Future sessions: don't relitigate these
without the user — this section exists so the *why* survives context loss.

| Decision | Reason |
|---|---|
| **Reframe as portfolio project, park the SaaS** | User's goal changed to GitHub/LinkedIn/job-profile highlight. Portfolio is judged on README + one-command run + clean code, not revenue features. Auth/payments/hosting are wasted effort until that bar is passed. |
| **Collapse 9 processes → 1** | The 8 microservices were prompt-wrappers; HTTP between them added deploy pain, port chaos, and sequential latency but zero capability. Single process = `pip install` + one command, which is the whole "plug and play" promise. |
| **Reuse `agent_pipeline.py` as the engine, delete `agents/`** | It already implements all 7 intents with real ThreadPoolExecutor parallelism and Claude models — deleting it and keeping the microservices would mean rebuilding worse. Minimal-work principle: keep the best existing implementation. |
| **Delete Streamlit v1 entirely** | Two frontends made the repo unreadable and the requirements file wrong. FastAPI v2 is what the dashboard JS targets. Old code stays recoverable in git history — no backup folders. |
| **Remove ALL fake data (demo mode, hardcoded intelligence/scores)** | Fake analysis is the #1 credibility killer for a *risk intelligence* project; any reviewer who greps the code finds it. Honest "no analysis yet" beats impressive fake numbers, always. |
| **Provider-agnostic LLM client (env-configurable), Claude by default** | Fixes the "says Claude, runs gpt-4o" honesty gap while making the project usable by anyone with any OpenAI-compatible key — that's what makes it adoptable. |
| **Persistence moved out of the engine (caller owns it)** | Engine as a pure function (`message, profile, history → result`) is testable, reusable by a future MCP server/CLI, and framework-proof. UI state coupling is what made the Streamlit version unportable. |
| **Keep current dashboard, don't build the Stitch redesign** | Stitch screens contain demo theater (agent toggles, fake word clouds, a nonexistent Legal Agent). Rebuilding UI before the engine is honest = polishing the wrong layer. Screens kept as design references only. |
| **MCP server is a stretch goal (Phase 7), not core** | Highest-value distribution idea, but it depends on a verified single-process engine. Sequencing it after verification keeps "minimal work" true. |
| **`.claude/` project config (CLAUDE.md, guardrails, auditor agent, verify skill)** | Makes the rules and the plan machine-readable for every future session — guardrails (no fake data, claims match code) are enforced at development time, not just remembered. |

---

## 6. Risks / Notes

- **No API keys available during dev** → verification without keys covers boot +
  graceful degradation; full-pipeline test needs the user's AIML/NewsAPI keys.
- **Status-listener is process-global** → concurrent chats from two sessions could
  cross-talk agent status displays. Acceptable for portfolio scope; noted in code.
- **Everything deleted is recoverable** — all removals are commits on a branch;
  `main` is untouched until the PR is merged.
