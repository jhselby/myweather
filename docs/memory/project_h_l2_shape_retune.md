---
name: h-l2-shape-retune
description: "v0.6.390g (2026-07-31) shipped H_SOFT_RAMP_FLOOR: 0.4→0.1, H_SOFT_RAMP_END: 24→10 in corrected_hourly.py after h L2 station_bias flipped from helping to hurting on 07-25. Grid sweep (h_l2_shape_sweep.py) found 7d best {0,8} and 14d best {0.4,12} disagree — middle path {0.1,10} beats old shape on both. 7-day watch CLOSED CLEAN 2026-08-07 (sentry green all bands, pair-log ΔMAE -28.3%). Retune held."
metadata: 
  node_type: memory
  type: project
  originSessionId: 434af779-9797-4cea-bd88-1e0939ffeef0
  modified: 2026-08-07T10:27:30.385Z
---

# h L2 shape re-tune (v0.6.390g, 2026-07-31)

## The mechanism (foundational context)

**h's L2 correction:** `corrected_humidity[lead] = raw_h[lead] + humid_bias × soft_ramp(lead)`
- `humid_bias` = `K_h × (station_consensus - HRRR_model)`, single scalar per tick from `hyperlocal.py`
- `soft_ramp(lead)` = piecewise-linear via `H_SOFT_RAMP_FLOOR`, `H_SOFT_RAMP_END` in `corrected_hourly.py`
- Same bias scalar applied to every future hour, tapered by lead

**Not tunable via decay_tau_tuning.py.** That's for L4. h's L2 is a distinct calibration.

**dp inheritance:** `corrected_dew_point = magnus_dew_point_f(corrected_temperature, corrected_humidity)`. dp has NO independent bias correction. dp damage = downstream of t and h corrections.

**h and dp are NOT on L3_FIELDS or L4_FIELDS whitelists.** L2 IS production for both. Confirmed empirically in `h_h_dp_layer_walk.py` — L3 marginal = 0.0% every day, L4 marginal ≤5%.

## The problem

Layer-shape sentry (after v0.6.390e fix restored it) surfaced h/production τ-suspect ★ signature: helps 0-5h (−16.6%) but hurts 6-11h (+14.8%), 12-23h (+11.0%), 24-47h (+8.8%).

Layer walk showed h's L2-vs-L1 marginal was consistently helping (−5% to −25%) through mid-July, then **flipped POSITIVE (+6% to +36%) starting exactly 2026-07-25.** Same shape for dp (via Magnus inheritance).

Diagnosis: soft_ramp shape (floor=0.4, end=24) shipped v0.6.218 was calibrated on 2026-06-22 data. Regime shifted around 07-25 to one where less-aggressive correction wins. Old shape kept applying 40% of a noisy bias out to lead 47; new regime made that noise injection instead of signal.

Same class of failure as [[project_lc_regime_conditional]] — static bias-learning against a moving target.

## What shipped

**Constants in `weather_collector/processors/corrected_hourly.py`:**
- `H_SOFT_RAMP_FLOOR: 0.4 → 0.1`
- `H_SOFT_RAMP_END: 24 → 10`

Ramp is now: 1.0 at lead 0 → 0.1 at lead 10 → held at 0.1 through lead 47.

## Why the middle path

`h_l2_shape_sweep.py` grid across floor ∈ {0.0..0.4} × end ∈ {6..24}, halves-verified top-5:
- **7d window (07-24 → 07-31, "new regime only") best:** floor=0.0, end=8 → +3.18% vs raw
- **14d window (07-17 → 07-31, includes old regime) best:** floor=0.4, end=12 → +7.26% vs raw
- **Grids INVERT between windows.** Because 07-17 → 07-24 was the old regime where L2 was working strongly

Middle path {floor=0.1, end=10} beats old shape on BOTH windows: +2.8% vs raw on 7d, +6.0% vs raw on 14d. Trades ~1pp in each direction to avoid betting on either regime persisting/reverting.

## Status: WATCH CLOSED CLEAN 2026-08-07

Layer-shape sentry green at all bands, pair-log h ΔMAE −28.3% on close day. Retune held. Reversibility path preserved below.

## Watch triggers (original, kept for history)

1. **h L2-vs-L1 marginal in daily digest must stay negative for ≥5 of next 7 days.** Compute from `mae_over_time.json` — `series.h.l2.mae` per day vs `series.h.l1.mae` per day.
2. **Layer-shape sentry ★ τ-suspect signature on h must fade.** Currently +14.8% at 6-11h, +11.0% at 12-23h. Should compress toward 0 as the new shape works through the trailing window.
3. **dp inherits via Magnus** — should track h. If dp doesn't recover with h, the shape isn't the whole answer.

If h marginal stays positive after 5 days, re-sweep with fresh 7d and re-tune constants. Reversible one-line edit.

## Related workstreams parked

**Shadow whitelist tuner has been recommending "add h to L4" since June** across 12 daily Fitter cycles (2026-06-17 → 06-30 nearly every cycle, then quiet, then 07-27 + 07-28 again). We've never adopted it. That's a SEPARATE workstream — adding L4 decay-fit for h on top of L2 station_bias, would capture per-lead bias structure L2 doesn't. Deferred until L2 shape watch settles.

**dp:** never shadow-recommended for L3/L4 in 45 Fitter cycles. Genuinely L2-only-forever per the data.

## Reversibility

Two-constant revert in `corrected_hourly.py`. If new shape hurts, back to floor=0.4/end=24 (or wherever the fresh sweep points). 30-second edit.

## Related

- [[project_07_31_session]] — full investigation arc
- [[feedback_pair_log_error_field]] — trap I hit while investigating (`error` vs `error_l1`)
- [[project_lc_regime_conditional]] — sibling regime-shift failure (cl on 07-30)
- [[project_cc_is_blend_of_clchcm]] — dp inherits from t+h, same as cc inherits from cl/cm/ch
