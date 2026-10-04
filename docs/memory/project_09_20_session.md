---
name: project-09-20-session
description: "09-20 Sun — 0 ships, per-obs classifier for t explored + parked. xr_q Stage 0 confirmed dead-end on HRRR-dominant fields; linear logistic on 8 features can't crack t at 34K rows."
metadata: 
  node_type: memory
  type: project
  originSessionId: ea23724d-936e-4dce-9950-f73f42a59c8e
  modified: 2026-09-20T12:19:14.712Z
---

# 09-20 Sunday session — L1 selector per-obs classifier: explored, parked

## Ships
None.

## Digest triage
- τ-suspect fresh-fire h/production day 4/7 (expected, v0.6.635 τ=7 ship). Watch through 09-23.
- NBM skip-ADDs walkforward: wd ne_flow 12-23h + se_flow 24-47h CONFIRMED both windows, waiting on 7-day streak.
- L4 add wg: 3/7 gated (didn't advance today).
- L3 drop wg: 1/7 fresh.
- ims Stage 1 gate re-check: sea_breeze/24-47h test +4.32% clears MAE but "weak" halves-stability (guard 0.44× < 0.5×). Same read as 09-19. No flip planned; run through the week.
- New Stage 0 promotes (backlog): l2_lead_decay_fit pr τ=4h +2.9%; h_diurnal_l2_tau_stage0 wg/dp/sr HOD-strong.
- walkforward_lc_regime_ship_stability READY 7d/16 SHIP — target already live (auto-refits), health-check pass only.
- Simpson-guard shadow flipped sign: pooled +4.9% guard-helps vs -14.2% on 09-13. Regime shift near equinox. Data point.

## Big arc — per-obs classifier for HRRR-dominant fields

**Question:** the 09-19 finding said sr/t/ws HOLD on ims Stage 0. Working hypothesis: sr/t/ws need a different per-obs axis (xr_q, cross-run spread). Tested today.

**Finding 1 — xr_q Stage 0 on sr:** blocked by [[project_sr_unit_mismatch]]. NBM sr mae 300-450 W/m² in every quartile of every cell (nonsense units). HRRR mae 0.4-307. shadow_lift ≡ 0 uniformly. Can't test the axis while NBM sr is broken at pair-log level.

**Finding 2 — xr_q Stage 0 on t:** HOLD, and same 0 shadow_lift pattern. NBM t mae 3.1-6.8 °F vs HRRR mae 0.6-3.3 across every cell. **HRRR wins cell-avg in every quartile of every cell** → shadow_lift ≡ 0 by construction. Per-obs oracle gap is 10-30% MAE, H_win% varies 49-92pp across quartiles (real signal there), but no quartile-bin picker can extract it because the losing model never wins cell-avg at the quartile grain.

**Finding 3 — structural rule:** [[feedback_stage0_shadow_lift_gate_hrrr_dominant]] saved. Stage 0 shadow-lift gate is dead for sr/t/ws regardless of axis. Only per-obs continuous classifiers (Stage 1 v2) can extract per-obs signal on HRRR-dominant fields.

**Finding 4 — per-obs classifier on t (Stage 1 v2 prototype):** built `analysis/l1_selector_per_obs_classifier_stage1.py` — L2 logistic regression per (regime, band) with 8 features [ims, xr_spread, lead_h, sin/cos(hour), cc_disagree, cc_inter_sigma, pressure_trend], nested train (fit 70% / val 30% for θ*), tested on held-out half.
- First pass L2=0.5, θ* on train: massive overfit (train +5-22%, test all negative).
- Second pass L2=3.0, θ* on val slice: overfit mostly gone. Test lifts collapsed to ±3% band. **Best cell pre_frontal/6-11h: test +2.17%, train +0.18%, capture +10.0%, fNBM 7.3%** — real generalization (test > train) but sub-gate.
- All 21 cells fail +3% test lift gate. Most degenerate (fNBM<5%) or still overfit on the big cells (nw_flow/24-47h: train +15%, test -13% despite L2=3.0).

**Diagnosis, honest:** the per-obs oracle gap on t is real (30.7% on sea_breeze/24-47h) but 8-feature linear model + 250-1000 train rows/cell + this feature set can't reach it. Structural gaps: (a) features probably miss the physics driving per-obs disagreement (solar zenith, snow cover, temperature advection sign, boundary-layer inversion, station-specific biases), (b) data volume thin for 8 params on a per-cell fit.

## Parked — bigger builds needed
- Richer features: add solar zenith, hour × regime interaction, forecast wind direction (proxy for advection sign), obs-hour lagged temp trend.
- Non-linear model: gradient boosting decision trees (need sklearn install) or hand-rolled shallow tree ensemble.
- Longer window: 34K row pair-log gives 250-1000 rows/cell. Extended backstamp replay would triple this.
- Field ordering: t was chosen for biggest oracle gap. ws untested but similar geometry expected.

**pre_frontal/6-11h watch cell:** the only cell showing real generalization signal (small +2.17% test). If accumulating data lifts this above +3% halves-stable, it becomes the first per-obs classifier ship.

## How to apply
Don't propose new axes on sr/t/ws for Stage 0 gates — the gate is structurally blind ([[feedback_stage0_shadow_lift_gate_hrrr_dominant]]). Any resumed work here is Stage 1 v2 (per-obs classifier), not axis-hunting. First step of that resumed work: better feature engineering, not more model complexity.
