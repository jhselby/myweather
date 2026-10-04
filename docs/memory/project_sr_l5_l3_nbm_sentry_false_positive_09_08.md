---
name: project-sr-l5-l3-nbm-sentry-false-positive-09-08
description: "09-08 late-evening — sentry HOT on sr.l5_nbm and WATCH on sr.l3_nbm are ramp-up artifacts, not regressions. sr was added to L3_NBM on 09-04 (v0.6.549); sentry's 7d sustained window (day 4-10 ago) has only n=324 pre-ramp rows vs n_fresh=2635. Suppress until 09-14."
metadata: 
  node_type: memory
  type: project
  originSessionId: f4f9924e-0098-4fb2-bee7-03e379adcce9
  modified: 2026-09-08T21:48:11.817Z
---

# sr.l5_nbm HOT / sr.l3_nbm WATCH — false positives from recent add (2026-09-08)

**Sentry output (refreshed 09-08 evening):**
- sr.l3_nbm WATCH: n_sustained=324, n_fresh=2635, mae_sustained=48.14, mae_fresh=55.64, marginal_degradation_pp=+9.32, layer_help_pct 23.74 → 14.42.
- sr.l5_nbm HOT ★: same n and MAE numbers, marginal_available=False, verdict from fallback mae_pct_change=+15.6%.

**Why bogus.** sr added to L3_NBM_FIELDS on 09-04 v0.6.549. Sentry sustained window = days 4-10 ago = ~08-29 → 09-05. Most of that predates the ship. n_sustained=324 is the small ramp-up tail; n_fresh=2635 is the full post-ship population. Comparing them isn't a fresh-vs-sustained regression check — it's tiny-sample-vs-steady-state.

**Confirmed by own pair-log dump last 24h:** sr.l3_nbm mae=53.22 vs sr.raw_nbm mae=63.16 (−10 MAE, huge help). sr.l5_nbm output identical to sr.l3_nbm in every window (l5 correction is 0 for sr → passes through). Layer is helping, not hurting.

**How to apply:** ignore these two verdicts through 09-14 (when sustained window fully post-dates 09-04). Do not ship a sr layer change on this signal.

**Design gap this exposes.** KILLED_LAYERS in `analysis/nbm_regression_sentry.py:77` suppresses recently-KILLED layers during the decay window. There's no symmetric mechanism for recently-ADDED layers, which produce the same false-positive shape. Small ship candidate: extend registry to `ADDED_LAYERS = {(field, layer): "YYYY-MM-DD"}` and suppress verdicts until sustained_start > added_date. Would auto-catch sr.l3_nbm/sr.l5_nbm today and any future add.

Related: [[project_09_08_evening_session]] · [[feedback_fossil_windows]] · [[feedback_nbm_regression_sentry_semantics]] · [[project_09_04_session]] (the v0.6.549 sr add).
