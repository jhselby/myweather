---
name: run-time-keyed-walkforward
description: "Any Stage 0/1 test that uses 'recent observed' as a feature (recent-N-day bias, prev residual, current disagreement, streak of recent errors) MUST be keyed by run_time — split features vs scoring by forecast-issue time, not obs-time. If both come from overlapping obs windows, you're measuring auto-correlation and it will die under honest walkforward."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 88021b04-0fee-492f-9d9b-c7a25f4a38db
  modified: 2026-08-17T22:52:42.570Z
---

# The rule

If a proposed specialist/gate/router uses **any feature drawn from recent observations** — recent-N-day bias, prev-window residual, current live disagreement between models, streak-of-recent-errors, EMA/Kalman shift trackers — the Stage 0/1 test MUST:

1. **Key features by run_time (forecast issue time)**, not obs_time. Feature values available at time T come from obs strictly *before* T (typically T − forecast horizon − buffer).
2. **Key scoring by obs_time > T**. The truth window must sit strictly after the feature window.
3. **Match production causality**: whatever the collector will actually know at forecast-stamp time is the only signal allowed. If the runtime path can't see obs from hour H, the test can't either.

If the test just aggregates by obs_time and computes "does recent bias predict this-hour error", the answer is almost always yes — because both series overlap in the same weather regime. That "signal" is auto-correlation of the underlying process, not skill.

# Why

**2026-08-17 session — 5 same-day CLOSED MISS closures, all from this failure class:**

- **[[project_lc_ema_kalman_fallback]]** — Stage 0 "HIT" for cl using EMA of recent bias. Honest run-time-keyed sim (features from obs strictly before run_time, score on obs after) showed EMA hurts cl at every N. Original Stage 0 was aggregating both sides by obs_time.
- **[[project_cl_h_predictor]]** — Stage 0 real (h_fc disagreement cells 1.59× MAE). But "disagreement" was measured on the same forecast the score used. Stage 1 halves catastrophically failed: Half A −35% / Half B +34%. Signal was regime-boundary contamination, not causal.
- **[[project_lc_gate_rule_direct_mae]]** — Stage 0/1 leaked because the decision window (recent MAE) and the scoring window (this obs) overlapped. Honest walk showed zero different decisions from current rule.
- Plus 2 more prior closures in the same session.

**The failure mode:** aggregate the pair log by (regime, band), notice a nice pattern, ship. The pattern was there because obs at time T is correlated with obs at T-6h, T-12h, T-24h in the same weather system — not because knowing T-24h helps *predict* T. Prod-time causality strips this.

# How to apply

**Before running any Stage 0/1 script:**

- Ask: does this feature come from an obs window? If yes, apply causality gate.
- Write the test so the feature aggregation uses `run_time` as the anchor and reads only obs with `obs_time < run_time - buffer`. Scoring reads obs with `obs_time > run_time + lead_h_test`.
- If that structure can't be built from the pair log, note that limitation loudly in the report — do not treat the obs-time aggregate as evidence.

**Before shipping:**

- Halves stability must be run on run-time-keyed data. Halves on obs-time-keyed data is not a defense — both halves share the same auto-correlation.
- A Stage 0 HIT that cannot be reproduced under run-time-keying is not a real signal. Close it same-day, don't build Stage 1.

**Red-flag features (assume auto-correlation until proven otherwise):**
- "recent 3-day bias", "recent 24h residual", "prev N obs streak"
- "current live disagreement between fc1 and fc2" (both fc1 and fc2 were issued at the same run_time; their disagreement at T is a function of the same underlying atmospheric state you're scoring)
- "just-observed value" as feature (e.g. persistence hybrid) — the observation is causally in the past, but if the walker uses `obs_time` bins it can leak the same period's obs into both sides.

**Safe features (causally available at run_time):**
- forecast values from independent models at the same run_time
- fields from earlier runs (T-24h issued forecast for current T obs)
- climatology + regime prior
- bias tables *frozen* at time of run_time, refit only on obs strictly before run_time

# Sibling context

- The recent-bias gates that DID work ([[project_lc_regime_conditional]], [[project_chp_cell_skip_to_dynamic_gate]]) survive because they gate on `recent_3d_bias vs historical_fit` where the historical fit was frozen weeks earlier — the "recent" side is production-available at run_time, and it modulates a table that was fit on strictly-past data.
- [[feedback_check_contamination_before_acting]] — different failure mode (contaminated post-ship watch), same underlying skill: always check *what time period each signal was drawn from* before treating it as evidence.
- [[feedback_measure_before_concluding]] · [[feedback_measure_against_live_stack_baseline]] — general priors this specializes.

# The trap that keeps working

The trap is comfortable because obs-time aggregation is what the pair log makes easiest. `grep field=X | group_by obs_day | compute delta` reads cleanly and produces plausible-looking regime tables. It takes deliberate work to add the `run_time < obs_time - lead` filter. That deliberate work is the whole test.
