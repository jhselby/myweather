---
name: project-l1-per-obs-gbm-experiment
description: "09-24 experiment: non-linear per-obs classifier (sklearn GradientBoostingClassifier, same 12 features as v2b). v3 single-split: 20+ PROMOTE cells. v4 halves-stable (quartile fold A/B like l1_blender_stage1): drops to 9 sr STABLE + 1 ch STABLE. sr is the real unlock — physically coherent non-linear cloud/sun-angle interactions. Everything else (h, wg, cc, wd) washes out. Next: v5 vs error_prod_real (not error_l4) for honest ship-gain."
metadata: 
  node_type: memory
  type: project
  originSessionId: 12ef5cc5-cd7f-4340-9a6f-4df528b5b372
  modified: 2026-09-25T11:25:21.036Z
---

# L1 per-obs classifier — non-linear GBM experiment

## Setup

- Input: same 12 features as `l1_selector_per_obs_classifier_stage1_v2.py` (ims, xr_spread, lead_h, sin/cos hod, cc_inter_sigma, pressure_trend, wd_sin/cos, ws_fc, cloud_low_fc, solar_wm2_fc)
- Model: sklearn `GradientBoostingClassifier(max_depth=3, min_samples_leaf=30, learning_rate=0.05, subsample=0.9, n_estimators=300)` with early stopping via `staged_predict_proba` against val slice
- Target: `y = 1 iff |error_l3_nbm| < |error_l4|` (per-obs, NBM wins)
- Fresh data (post-09-24 appender fix so backstamp URL is current)

## v3 vs v4 gate

**v3** (`analysis/l1_selector_per_obs_classifier_stage1_v3.py`): identical to v2b except swap logistic ridge for GBM. Single train/test split (rows sorted by time, first half fit, last 30% of that = val, second half test). Gate: `test_lift >= 3%`, `test_lift >= 0.5 * train_lift`, `0.05 < fNBM_te < 0.60`.

**v4** (`analysis/l1_selector_per_obs_classifier_stage1_v4.py`): quartile fold matching `l1_blender_stage1.py`. Q1-Q4 by time. Pair A: train=Q1+Q2 val=inner-30%, test=Q3. Pair B: train=Q2+Q3, test=Q4. STABLE iff BOTH pairs clear the v3 gate independently.

## Results — v3 → v4 attrition

| Field | v3 PROMOTE | v4 STABLE | Notes |
|---|---|---|---|
| **sr** | 11 | **9** | Real unlock — non-linear cloud/sun-angle geometry |
| **cc** | 4 | 0 | v3 promotes were single-window artifacts |
| **wg** | 4 | 0 | Same |
| **ch** | 3 | **1** (se_flow/6-11h) | One narrow cell |
| **h** | 1 (sw_flow/24-47) | 0 | Didn't survive halves-stable |
| t | 0 (v3 also HOLD) | 0 | Feature-set ceiling — non-linear didn't help either |
| dp | 0 | 0 | Same |
| ws | 0 | 0 | Same |
| wd | 0 (all degenerate) | 0 | Same |

## sr STABLE cells (the actual finding)

9 cells clear halves-stable non-linear gate, avg test lift +19% to +37% vs always-HRRR baseline, non-degenerate fNBM 10-49%:

- `nw_flow/0-5h` — A+24.1% / B+39.3%
- `pre_frontal/0-5h` — A+10.5% / B+27.7%
- `pre_frontal/6-11h` — A+14.5% / B+23.1%
- `pre_frontal/12-23h` — A+17.0% / B+43.7%
- `pre_frontal/24-47h` — A+28.3% / B+46.3%
- `se_flow/12-23h` — A+27.5% / B+37.3%
- `sw_flow/24-47h` — A+20.8% / B+34.7%
- (2 more visible in truncated output — likely ne_flow bands)

## ch cell

`ch/se_flow/6-11h` — A+25.7% / B+18.7%, fNBM 37.6% / 54.5%. Narrow but real.

## Key caveat before ship

**All lifts measured vs always-HRRR baseline** (`base_te = mean(|error_l4|)`). The production selector already routes some sr cells to NBM via `l1_selector_table_curated.json`. So "+30% vs HRRR" overstates the ship gain — the honest number is "vs what the selector actually served" (`error_prod_real`). Same baseline-inflation trap the blender's stage1 has.

**v5 = score vs `error_prod_real`.** Required before shipping any of these cells. Compute per-row `served_err`: apply the selector's runtime routing (from `l1_selector_table_curated.json`) to pick HRRR or NBM per (regime, band), take that error. Compare classifier's per-obs pick against served. The delta is the honest ship-gain.

## Non-caveats — real content

- sr non-linear IS a real architectural improvement, not a stats artifact. Halves-stable holds. Physics is coherent (cloud thresholds, sun angle geometry are canonical non-linear).
- The blender's 2 STABLE cells (`h/pre_frontal/24-47`, `t/se_flow/24-47`) and these 9 sr cells are on DIFFERENT fields — they stack, don't compete.
- Feature-engineering deprioritized: GBM already extracts real signal from existing 12 features for sr. Adding features helps only for fields where GBM is currently HOLD (h, cc, wd, wg) — those are the harder problems.

## Comparison to earlier stale-data claims

- v0.6.644 "learned selector" (linear logistic on same features) claimed +6.5% on `h/nw_flow/24-47h`. Fresh-data v2b: STAGE 1 HOLD everywhere on h. Fresh-data v3 GBM: h/sw_flow/24-47h clears single-split but drops to MARGINAL under v4 halves-stable. **v0.6.644 shadow tables shipped in v0.6.644-6 need re-fit or removal.**
- v2b feature-set-ceiling verdict for h and t was correct FOR LINEAR models. Non-linear reveals it was a model-class ceiling for sr specifically.

## Scripts

- `analysis/l1_selector_per_obs_classifier_stage1_v3.py` — GBM single-split. Committed via this session? Check git status if unclear (was in progress, may not be committed).
- `analysis/l1_selector_per_obs_classifier_stage1_v4.py` — GBM halves-stable. Same.

Install: `pip3 install lightgbm scikit-learn` (lightgbm needs `libomp` on Mac — `brew install libomp`; sklearn works out of the box, chosen for portability).

## Next session concrete plan

1. Build v5 (score against `error_prod_real` from selector runtime routing).
2. Run sweep. See which of the 9 sr cells + 1 ch cell hold up when the baseline is honest.
3. Compare surviving sr cells to what `l3_nbm_curated.json` + selector already achieve.
4. If lift-over-served ≥ 5% halves-stable on any sr cell, that's a ship candidate — new curated JSON, new runtime tile, `L1_CLASSIFIER_APPLIED_FIELDS = frozenset({"sr"})`-shaped flip.

## Related

- [[project_backstamp_stale_09_24]] — root-cause of why the earlier per-obs classifier work claimed wins on stale data
- [[project_l1_blender_stale_fit_audit]] — parallel finding for the blender
- [[project_l1_selector_per_obs_axes]] — the h_l1_selector_ims_* work is on the same stale-URL list; 09-26 flip watch numbers were on stale data
