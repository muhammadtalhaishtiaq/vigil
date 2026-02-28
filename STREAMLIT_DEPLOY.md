# VIGIL — Streamlit Cloud Deployment Checklist

> Complete these steps in order. Estimated time: ~10 minutes.

---

## 0 · Pre-flight (local machine)

```bash
# From inside the vigil/ directory
pip install -r requirements.txt
python health_check.py          # must print "All 3/3 checks passed"
streamlit run app.py            # smoke-test locally on http://localhost:8501
```

- [ ] `health_check.py` prints **All 3/3 checks passed**
- [ ] App loads locally without Python errors in the terminal

---

## 1 · Push to GitHub

```bash
# From repo root (the folder that contains vigil/)
git init                         # if not already a git repo
git add .
git commit -m "feat: vigil initial deploy"
git remote add origin https://github.com/<YOUR_USERNAME>/<REPO_NAME>.git
git push -u origin main
```

> **Important:** make sure `.streamlit/secrets.toml` is in `.gitignore`
> (only `secrets.toml.example` should be committed — never the real one).

- [ ] Repo pushed to GitHub
- [ ] `.streamlit/secrets.toml` is **NOT** in the commit

---

## 2 · Create the Streamlit Cloud App

1. Go to **https://share.streamlit.io** → sign in with GitHub
2. Click **"New app"**
3. Fill in the form:
   - **Repository:** `<YOUR_USERNAME>/<REPO_NAME>`
   - **Branch:** `main`
   - **Main file path:** `vigil/app.py`  ← critical
4. Click **"Advanced settings"** (do NOT deploy yet)

- [ ] Form filled, main file set to `vigil/app.py`

---

## 3 · Add Secrets

Still in "Advanced settings" (or after deploy via **Settings → Secrets**):

Paste the following into the Secrets text area:

```toml
AIML_API_KEY = "0a9f32b207494176a81f13b011128df0"
NEWSAPI_KEY  = "f5d0c89e9d3143c594ed757572d8f788"
```

- [ ] `AIML_API_KEY` added
- [ ] `NEWSAPI_KEY` added

---

## 4 · Deploy

Click **"Deploy!"** and wait for the build log to complete (~2–4 minutes for first build).
Watch for any `ModuleNotFoundError` — if seen, check `requirements.txt`.

- [ ] Build completes without errors
- [ ] Green "Your app is live" banner shown

---

## 5 · Test 5 Critical Flows

Open the live URL and verify each flow:

| # | Test | Expected | ✓ |
|---|------|----------|---|
| 1 | Load dashboard (no profile) | Generic welcome message, live news visible | ☐ |
| 2 | Set up company profile → Save | Redirects to dashboard, profile pill appears in header | ☐ |
| 3 | Auto-briefing fires once | Single briefing on first load after profile save | ☐ |
| 4 | Type `"Is gold a buy?"` → submit | Oracle tab populates with BUY/WAIT/CAUTION/AVOID verdict | ☐ |
| 5 | Type `"full briefing"` → submit | All 8 agent nodes animate, risk strip updates | ☐ |

---

## 6 · Share URL

Copy the Streamlit Cloud URL (format: `https://<appname>.streamlit.app`).

- [ ] URL accessible publicly (no login required)
- [ ] Submit to hackathon demo form

---

## Troubleshooting Quick Reference

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: openai` | Check `requirements.txt` has `openai>=1.30.0` |
| `AIML_API_KEY not set` | Re-check Secrets panel; ensure no leading spaces |
| `NEWSAPI_KEY not set` | Same as above |
| `yfinance` 404 / empty data | Yahoo Finance rate-limit; retry in 60s |
| App crashes on load | Check Streamlit logs → `Manage app → Logs` |
| Profile not saving | Confirm `st.session_state` flow; no database needed |

---

*Generated for VIGIL · Complete AI Agent Hackathon · lablab.ai · 2026-02-26*
