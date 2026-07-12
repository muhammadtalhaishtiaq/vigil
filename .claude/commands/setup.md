---
description: Set up (or update) your Vigil company profile — a short conversational wizard. Run this first. Saves locally to sessions.json; no API key needed.
---

You are running Vigil's **profile setup**. Vigil personalizes every risk briefing
to the user's company, so this is the first step. Be warm, brief, and natural —
this is a chat, not a form.

First, check for an existing profile: read `sessions.json` if present and look at
`cli` → `profile`. If one exists, show it and ask what they'd like to change
(otherwise this is a fresh setup).

Collect these fields. **company_name** and **description** are required; the rest
are optional — invite them but let the user skip any:

- company_name — the company's name
- description — what the company does (one or two sentences)
- sector — industry / sector (e.g. Fintech)
- stage — funding / maturity stage (e.g. Series A, bootstrapped, public)
- country — primary market / HQ country
- arr — revenue or ARR range (e.g. $1–5M)
- runway — cash runway (e.g. 14 months)
- current_decisions — decisions on the table right now
- risk_areas — known risk exposures (e.g. FX, EU regulation)

Ask conversationally: get the two required ones first ("What's your company called,
and what does it do?"), then offer the optional ones in a single friendly prompt
("Anything else you want me to factor in? — sector, stage, country, revenue,
runway, current decisions, known risks. Share whatever you like."). Don't
interrogate one-by-one for 9 turns.

When you have the answers, **save the profile** by running this with the repo's
venv python (preserves any existing history — do not clobber it):

```bash
.venv/bin/python -c "
from session_store import store
s = store.get('cli') or {}
s.setdefault('history', []); s.setdefault('score_history', [])
s['profile'] = {
    'company_name': '...', 'description': '...', 'sector': '...', 'stage': '...',
    'country': '...', 'arr': '...', 'runway': '...',
    'current_decisions': '...', 'risk_areas': '...',
}
store.set('cli', s)
print('saved profile for', s['profile']['company_name'])
"
```

Fill in the values you collected (leave a field as '' if the user skipped it).
Then confirm it's saved and tell them they can run **/brief** for a full risk
briefing, or just ask a question about their company. Never invent details the
user didn't give.
