# Contributing to Vigil

Thank you for your interest in contributing to Vigil! This guide covers how to run locally, add a new agent, modify routing, and follow the code style.

---

## Running Locally

### Prerequisites
- Python 3.10+
- Two API keys: `AIML_API_KEY` (aimlapi.com) and `NEWSAPI_KEY` (newsapi.org)

### Setup

```bash
# 1. Clone
git clone https://github.com/<your-username>/vigil.git
cd vigil

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure keys
cp .env.example .env
# Edit .env with your keys

# 5. Run health check first
python health_check.py

# 6. Run the app
streamlit run app.py
```

App runs at `http://localhost:8501`.

### Project Layout
```
vigil/
├── app.py              ← Main dashboard entry point
├── agent_pipeline.py   ← Add/modify agents here
├── session_manager.py  ← Profile + conversation state
├── data_layer.py       ← Live data (NewsAPI + yfinance)
├── pages/
│   └── profile.py      ← Company profile form
└── prompts/            ← System prompts for each agent
    └── *.txt
```

---

## Adding a New Agent

### Step 1 — Create the system prompt
```bash
# Create prompt file
touch vigil/prompts/my_new_agent.txt
```

Write a system prompt that clearly defines:
- The agent's role and expertise domain
- Expected input format
- Expected output format (plain text or JSON)
- Output length constraints

### Step 2 — Register in `_MODEL_MAP`
In `agent_pipeline.py`, add your agent to the model map:

```python
_MODEL_MAP: dict[str, str] = {
    ...
    "my_new_agent": "claude-sonnet-4-6",  # Choose appropriate model
}
```

### Step 3 — Add to routing table
In the `INTENT_ROUTING` dict, add your agent to the relevant intents:

```python
INTENT_ROUTING = {
    "FULL_BRIEFING": [
        ...,
        "my_new_agent",   # Fires for full briefings
    ],
    "MY_NEW_INTENT": [    # Or create a new intent
        "signal_harvester",
        "my_new_agent",
    ],
}
```

### Step 4 — Update the Orchestrator prompt
In `prompts/orchestrator.txt`, add your new intent to the classification section so the Orchestrator knows when to route to it.

### Step 5 — Update `_ALL_AGENTS`
The `_ALL_AGENTS` list must include your new agent for the header pipeline display:

```python
_ALL_AGENTS: list[str] = list(_MODEL_MAP.keys())
# New agent auto-appears in the header flow visualization
```

### Step 6 — Handle outputs (optional)
If your agent produces structured data, parse it in `run_pipeline()` STEP 4 and persist to `st.session_state` in STEP 5. Add a new tab in `_render_analysis_tabs()` in `app.py` if needed.

---

## Modifying Intent Routing

### Adding a new intent type

1. **In `agent_pipeline.py`:**
   ```python
   INTENT_ROUTING["MY_NEW_INTENT"] = ["signal_harvester", "my_agent"]
   ```

2. **In `prompts/orchestrator.txt`:** Add classification examples for the new intent.

3. **In `_STRIP_UPDATE_INTENTS`** (if it produces risk data):
   ```python
   _STRIP_UPDATE_INTENTS: frozenset[str] = frozenset({
       ...,
       "MY_NEW_INTENT",  # Add only if it produces top_risks/top_actions
   })
   ```

4. **In `session_manager.py` `enhance_query_with_context()`:** If the new intent needs special context injection, add a branch there.

### Changing which agents fire for an existing intent
Simply edit the list in `INTENT_ROUTING`. The pipeline will automatically dispatch to listed agents in parallel.

### Changing the investment keyword detection
In `agent_pipeline.py`, find the `_inv_kw` regex and add/remove keywords:
```python
_inv_kw = re.compile(
    r"\b(buy|sell|invest|...|YOUR_NEW_KEYWORD)\b",
    re.IGNORECASE,
)
```

---

## Code Style

### Python
- **Formatter:** `black` with default settings (line length 88)
- **Type hints:** All function signatures must have type hints
- **Docstrings:** One-line for simple functions, multi-line for pipeline steps
- **Error handling:** Wrap all external API calls in `try/except`; log errors, never crash the pipeline

```python
# Good
def run_agent(agent_name: str, prompt: str, context: str) -> str:
    """Call a single agent and return its text output."""
    try:
        ...
    except Exception as exc:
        logger.error("Agent %s failed: %s", agent_name, exc)
        return ""  # graceful fallback

# Bad — no type hints, no error handling
def run_agent(agent_name, prompt, context):
    return client.chat.completions.create(...)
```

### Streamlit / HTML
- All UI strings must use `unsafe_allow_html=True` with the design system CSS classes
- Never hardcode colors — use `var(--green)`, `var(--text2)`, etc.
- New UI sections should follow the existing `fade-up` animation pattern

### Commit Messages
Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add sentiment agent for social media signals
fix: resolve pipeline crash when AIML API times out
docs: update AGENTS.md with Market Oracle output format
refactor: extract _build_context() from run_pipeline()
```

### Branch Naming
```
feature/new-agent-name
bugfix/pipeline-timeout
hotfix/api-key-resolution
```

---

## Pull Request Checklist

- [ ] `python health_check.py` passes (all 3/3)
- [ ] `streamlit run app.py` starts without errors
- [ ] Agent count in docs/comments is still 8 (never 7)
- [ ] New agents added to `_MODEL_MAP` and `INTENT_ROUTING`
- [ ] `_STRIP_UPDATE_INTENTS` updated if new intent produces risk data
- [ ] AGENTS.md updated for new agents
- [ ] No API keys committed (check `.gitignore`)
- [ ] Type hints added to new functions

---

## Questions?

Open a GitHub Issue or reach out via the lablab.ai hackathon submission thread.
