---
name: feedback-same-day-close-via-pair-log
description: "When a watch says \"re-check tomorrow\" or \"wait one day\", check the pair log FIRST — often the answer is already there. Cheap check, saves 24h and stochastic-signal noise."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b8058893-d7b5-4544-a4d3-9f9dee94eef7
  modified: 2026-08-10T14:23:34.055Z
---

# Rule

When about to log a watch for "re-check tomorrow morning" on a signal, first ask: **is the data needed to resolve it already in the pair log or shadow log?** If yes, resolve today.

## Why

08-10 opened two watches — `project_ch_chp_midlead_band_watch_08_10` and `project_pr_l2_regime_flip_investigation_08_10` — both scoped to "re-check 08-11 h_chp_midlead_regression" and "read shadow-wire pair-log on 08-11". Both were actually resolvable same-day:

- **ch watch**: needed 48h of pair-log rows grouped by regime × valid-hour × band. Already in `forecast_error_log.jsonl`. Ran a 40-line script, got the finding (daytime nw_flow + pre_frontal), shipped the diurnal-gate fix same day.
- **pr watch**: needed to see if the retro's WIN cells reproduced under live τ=8h vs τ=12h. Already in the retro's own output (which uses whatever τ the writer stamps — currently τ=8h). Verified same-day, shipped the regime-gated apply.

Waiting one day would have added noise (a single stochastic day's data at n<1000 can swing verdicts by ±10-20%) and cost 24h of user-visible degradation.

## How to apply

Before writing a "re-check tomorrow" watch memory, run this check:

1. What data do I need to resolve this? (pair log rows / shadow output / regime cross-cut / etc.)
2. Is that data already accumulated on disk? Grep the cache dir + `analysis/output/`.
3. If yes → resolve today. Only defer if the answer genuinely requires accumulating fresh observations.

The exception is truly-forward-looking signals: watches waiting for a specific weather event to recur (frontal passage, calm regime, cool-season NE-flow), or 7-day gate-agreement counts. Those legitimately need calendar time.

## Where waiting IS right

- 7-day live-layer change gate (per [[feedback_whitelist_promotion_gate]])
- Watches waiting for weather event accumulation (dpbp gate on pre_frontal, wsbp calm-only, chp mid-lead recovery)
- Post-ship 14-day watch windows

Where waiting is WRONG:
- Signal was flagged today and the underlying pair-log data is already sufficient to resolve it.

Related: [[feedback_digest_triage_discipline]], [[project_ch_chp_midlead_band_watch_08_10]], [[project_pr_l2_regime_flip_investigation_08_10]].
