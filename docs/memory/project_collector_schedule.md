---
name: Collector Schedule
description: When and how often the Cloud Function collector runs, and why
type: project
originSessionId: f4a8ab7f-e55c-4320-b889-991cbc97cec9
---
Collector runs every 10 minutes on the 7s (`:07`, `:17`, `:27`, `:37`, `:47`, `:57`).

**Why:** Moved to the 7s to avoid 429 rate-limit errors from Open-Meteo, which likely hammers at the top/bottom of the hour.

**How to apply:** When suggesting `make run-collector` or advising Joe to wait for the next scheduled run, the next fire is on the next :X7 mark, not :X0.

## Fitter — twice daily, not daily

The Fitter (`decay_fit.py::fit_decay_corrections`) runs **twice per day, at 03:07 AND 15:07 local**. This is corrected against the `decay_fit.py` docstring's claim of "once per day" (2026-07-09 — I said "03:X7" and Joe corrected me).

**Why it matters:** any Fitter-gated verification (new preflight, new gate history writer, new verdict output) fires twice a day. If a change goes live at 08:11, the first real Fitter tick is 15:07 the same day — ~7 hours out, not next morning. Similarly for L5 / Lc gate accumulators, the daily-count math needs to acknowledge 2 fitter-updates per calendar day.

**How to apply:** whenever advising when a Fitter-side change will first exercise, compute against the next 03:07 OR 15:07 (whichever is sooner), not just the next 03:07.
