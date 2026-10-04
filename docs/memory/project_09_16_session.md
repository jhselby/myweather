---
name: project-09-16-session
description: "09-16 Wed morning session — 4 ships (v0.6.635-638): h τ=7 in decay_fit, wg_residual_persistence ENABLED=True (long-frozen at False since 07-14), NBM stale-skip removal, stack health trajectory multi-window trend selector. Frontal detector clarified as persistent HOLD not regression. Walkforward L3L4 streak reset explained (new 1 skip cell proposal)."
metadata: 
  node_type: memory
  type: project
  originSessionId: e57e2209-ff1a-48b3-9cda-1b804929f7ad
  modified: 2026-09-16T17:06:48.486Z
---

## Ships (4, deployed 2026-09-16 ~12:06 UTC; commits c09426a1 + 870c29ba)

- **v0.6.635** — `decay_fit.py:151` added `TAU_DAYS_BY_FIELD["h"] = 7`. `decay_tau_tuning.py` 3/3 confirmation streak; h held-out MAE +6.9% vs global τ=14. Affects fitter recency-weighting `w = exp(-age/τ_h)`. Lands next daily fitter tick (03:X7 UTC). **dp deliberately excluded** despite +7.6% gain — dp is derived (Magnus from t,h) and not in L3_FIELDS/L4_FIELDS/L2_TAU_FIELDS, so a dp override would only affect analytics (same inert-config pattern as the pp entry). Per [[project_dp_is_derived_no_dp_work]].

- **v0.6.636** — `wg_residual_persistence.py` ENABLED flipped True (was False since v0.6.351 on 2026-07-14, 2 months past the 07-27 earliest-flip target). Stage 1 PROMOTE fresh today: +17.83% test MAE, 3/5 regime WIN, halves both positive. Stage 2 curated table has 16 SHIP cells; `_residual_persistence_walker` confirms 13 cells cleared the 7-day gate (all ⊂ Stage 2 SHIP set). Live tick verified 12:07 UTC: `wg_residual_persistence.enabled: true`, `fires_by_band: {0-5:0, 6-11:6, 12-23:12, 24-47:24}`, `skips_by_band: {0-5:5, ...}` — correctly skipping 0-5h band, firing on long-lead. Real corrections landing (~−10 mph on 24h in `pre_frontal` regime; matches Stage 2 pre_frontal 24-47 SHIP verdict of −17.86% lift).

- **v0.6.637** — `skip_table_nbm_curated.json` — removed `["ne_flow", 6, 12]` from `l3_nbm.wg`. Two-window audit passed: 14d n=157 lift +7.67%, 50d n=418 lift +6.91%. Both windows positive → correction was helping and skip was blocking it. History entry appended.

- **v0.6.638** — `corrections_debug.html` — Stack health trajectory trend line replaced with multi-window selector (7d/30d/90d/180d/365d checkboxes; default 30d only; selection persists in `localStorage["debug.stackHealth.trendWindows"]`). Motivating diagnosis: the pre-change single trend fit OLS through ALL plotted days on top of a 7d rolling mean — for a shop shipping 1-3 changes/day, that's an archive summary, not a live signal. Each window now regresses the last N days of the smoothed daily median (per-obs-day cross-field median of `(1 − prod_MAE / raw_MAE_90d_ref) × 100`) and reports `pp/week` in the legend. `computeTrendline(agg, windowDays)` now takes optional windowDays; legacy full-series callsite (line 9621, main aggregate chart) unaffected. Min-points guard 8 → 4 so 7d can produce a slope.

## Root causes / non-ship diagnostics

- **Walkforward L3L4 streak reset (48/7 → 1/7)** — investigated as potential v0.6.625 normalizer bug per [[project_09_15_session]] clock-watch. **Working correctly.** Digest history shows 09-11 through 09-14 all had `[entangled: 0], 0 skip cell(s) proposed`. 09-15 had `[entangled: 1], 0 skip cell(s)`. 09-16 has `[entangled: 0], **1 skip cell(s) proposed**`. The v0.6.625 normalizer strips `[entangled:N]` but preserves skip-cell count — so the skip-cell count changing legitimately restarts the streak. New proposal: add `("frontal", 24, 48)` to `SKIP_TABLE[("wg","l3")]` on the HRRR side. Day 1/7 clock started.

- **Frontal detector HOLD** — NOT a today-regression. Persistent HOLD every day since v0.6.619 introduced the health check on 09-14. The 09-14 memory's expectation ("verdict auto-flips HOLD→CLEAN") was optimism that never materialized. Two distinct problems: (a) coverage gap (sim 14 events at 4°F threshold vs runtime logs 5 — likely 60-min same-type dedup swallowing repeats), (b) 'cold' branch never fires because the conjunction `dp_drop≥4 AND wd_to∈{N,NE,NW} AND pressure_rising` hasn't happened in 14d — plausibly seasonal (mid-Sept, still summer synoptics). Investigation needed, not a same-session ship. v0.6.621 diagnostic `print(..., flush=True)` is live; miss data recoverable via `gcloud functions logs read myweather-collector --region=us-east1 --limit=200 --gen2 | grep frontal`.

- **h FRESH FIRE still hot** — 7d +9.8%, 3d +18.1%. Still on the v0.6.620 shadow trajectory per [[project_09_15_session]]. Expected roll-off 09-17 as pre-v0.6.620 pairs fall out of 3d window. τ=7 ship (v0.6.635) will also compress the fitter's memory for h, adding to the healing.

## Clock-watches for 09-17 digest

- **wg residual persistence live check (day 1/7).** Watch production wg MAE vs L2 baseline. Any halves-flip demotions in any of the 16 SHIP cells → concern.
- **h FRESH FIRE HEALING.** 3d should drop as pre-v0.6.620 pairs age out AND as τ=7 kicks in on next fitter tick. If still hot, dig for a second cause.
- **NBM stale-skip audit for l3_nbm.wg.ne_flow.6-11h.** Post-removal, watch that the audit no longer flags it (it shouldn't) and that live-runtime MAE for wg/ne_flow/6-11h improves.
- **h τ=7 signature.** After next daily fitter tick, expect h/production τ-suspect (0-5h -43.7% / 24-47h +12.0%) to shift toward the short-lead pain and long-lead relief.
- **Walkforward L3L4 frontal 24-47h skip proposal.** Day 2/7 tomorrow. Watch for stability or a new proposal-shape flip.
- **Frontal detector.** Joe pulls Cloud Run logs for miss-diagnosis; classifier gate loosening (drop pressure_rising requirement? widen wd_to?) is potential fix territory.
- **Stack health trajectory (v0.6.638).** New multi-window selector live. Watch: 7d slope should be the most responsive to today's ships; 30d/90d should start moving over the week if v0.6.635-637 land as expected; 180d/365d are backdrop context, shouldn't move meaningfully in a day.

## Blocking / paused

- Frontal detector investigation open (log-analysis-shaped, not a same-session ship).
- All other clock-watches from [[project_09_15_session]] resolved today (streak: not-a-bug, nbm_skip_add filter: empty as expected, stagnant_high walker: THIN as predicted).

Related: [[project_09_15_session]] · [[project_wg_residual_persistence]] · [[project_dp_is_derived_no_dp_work]] · [[project_frontal_detector_health_09_14]].
