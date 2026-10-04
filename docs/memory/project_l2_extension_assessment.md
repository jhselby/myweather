---
name: project-l2-extension-assessment
description: 2026-06-08 verdict on extending L2 station-network bias + lead-decay to pass-through fields. Closed except for sr (date-gated against L5 decision).
metadata: 
  node_type: memory
  type: project
  originSessionId: 43ac5ed4-a539-4e44-be37-7cbc5fe435f9
---

## What was assessed (2026-06-08 session)

Question: extend L2 lead-decay (v0.6.44) beyond t/h/dp/pr to the remaining 8 fields that currently pass through L2 untouched.

## Mechanic recap (so future-me doesn't have to re-derive it)

L2 lead-decay only works on fields that already have an **additive L2 bias term** (i.e., `forecast_l2 != forecast_l1`). The fit reads `applied_bias = f_l2 − f_l1` from the pair log and grid-searches τ in `bias × exp(-lead/τ)`. If `applied_bias = 0` for every pair, the fit is degenerate — every τ scores identically.

## Field-by-field verdict

- **t / h / pr**: shipped in v0.6.44–v0.6.45. Done.
- **dp**: inherits via Magnus from corrected t + h. No work needed.
- **ws / wg**: ran fit on 2026-06-08, τ=∞ for both. The hardcoded 0→24h linear ramp in the wind path already decays `applied_bias` to zero by lead 24h, so the exponential fit has nothing left to multiply. Current wind path is fine; **no further work**.
- **sr**: 20/20 Tempest stations report `solar_radiation_wm2`. Network qualifies. Estimated build cost ~1–2 sessions (new `solar_bias.py` Kalman tracker, daylight gate, hook into `hyperlocal.py` and `corrected_hourly.py`, then 2–3 wks for pairs to accumulate, then re-run τ fit). **BUT**: R2 state-stratified flagged Solar × flow regime as the #1 opportunity (~120 W/m² spread). That's a regime-conditional signal, not a stable-bias signal. L5 regime correction is the better tool for the same problem.
- **pa**: WU + Tempest rain gauges exist, but octant signed-mean aggregation breaks for precip (intermittent + spatially patchy). ~3–5 sessions of design work, uncertain payoff. Defer indefinitely.
- **cc / cl / cm / ch**: no station network has the right sensor (PWS lack ceilometers; KBVY ASOS is a single station). Not buildable.
- **pp**: probability, not measurable per-station. Wrong model for L2 anyway; handled in L3 via Brier-score path.

## Open decision

**sr L2 vs sr L5** is the only live question. Decision is date-gated to ~2026-06-22, when post-v0.6.44 data lets us re-confirm whether the ~120 W/m² Solar × regime spread held. If spread ≥ ~100 W/m²: green-light L5 (existing plan), skip sr L2. If spread < ~50 W/m²: L5 payoff too small, reconsider sr L2.

**Why:** the 120 W/m² spread was measured on the pre-v0.6.44 pipeline. The L2 lead-decay shipped between then and now may have absorbed some of it. Don't build either path against a stale number.

**How to apply:** until 2026-06-22, do not start work on L5 *or* sr L2. After re-running R2 with fresh data, pick the winning path.

Related: [[project-todo]], [[project-correction-stack]], [[project-state-metadata]], [[project-layer34-watch]].
