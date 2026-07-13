---
description: Show your company's risk score over time — the trend from past briefings. No agents, no API key.
---

You are showing Vigil's **risk trend**. No agents run — just read and present saved
history.

Read `sessions.json` and look at `cli` → `score_history` (a list of
`{date, score, tier}` entries saved by past /brief runs).

- If it's empty or missing: tell the user there are no briefings yet — run
  **/brief** first to establish a baseline.
- Otherwise present it clearly: list the entries oldest→newest, show the latest
  score/tier, and call out the change from the previous entry (e.g. "61/100 —
  down from 68 on 2026-07-03"). A tiny inline sparkline of the scores is a nice
  touch if you can.

Keep it short. This is a status readout, not an analysis.
