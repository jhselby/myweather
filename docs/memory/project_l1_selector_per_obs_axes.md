---
name: project-l1-selector-per-obs-axes
description: "L1 selector picks per (field, regime, lead_band) only — no per-obs features. C1 axes (ims, xr_q, cluster_spread, state_fc/obs) all terminate at C1 confidence bands instead of feeding the picker. Stage 0 on ims for h PROMOTED 2 cells (+6% / +4% shadow lift). Real per-obs gap 20-40% MAE across most cells."
metadata: 
  node_type: memory
  type: project
  originSessionId: d4ff154d-a9eb-435b-9633-2ee0e8fabca3
  modified: 2026-09-19T17:54:23.625Z
---

# L1 selector — per-obs axis wire (2026-09-19 finding)

## Diagnosis
Live L1 selector signature: `pick_source(field, lead_h, regime, hour_local)`. That's it. No cross_run_spread, cluster_spread, inter_model_spread, state_fc/obs disagreement — none of the C1 axes feed the picker. All flow into `confidence_layer.py` to widen bands, never into `l1_selector.py` to pick winners.

Result: chooser value-captured stuck at:
- dp/7d: 8% (oracle gain +0.87 MAE = 41% of raw)
- t/7d: 8% (+0.57 = 40%)
- sr/7d: 19% (+16.3 = 37%)
- h/7d: 20% (+2.18 = 45%)

**Wrong-ceiling story I told earlier: "dp/t are structurally capped at 2%" — that was HRRR-vs-NBM cell-average spread, not the per-obs oracle gap.** Real oracle gap on dp/t/sr/h is 37-45% of MAE. Massive per-obs winner-flip inside each cell that the coarse picker can't see.

## Stage 0 finding (`analysis/h_l1_selector_ims_stage0.py`)
Field=h only. Split each (regime, band) into ims quartiles by `|forecast_l1 - forecast_raw_nbm|`. Compute H_win_rate per quartile and shadow-MAE if picker chose per-quartile winner.

**2 cells PROMOTE (halves-stable + shadow MAE lift ≥ 3%):**
- h / sea_breeze / 24-47h: Q1..Q4 H-win 45/34/57/75%, shadow lift +6.39%
- h / sw_flow / 24-47h: Q1..Q4 H-win 56/53/43/71%, shadow lift +3.95%

**~10 more cells: halves-stable win-rate spread of 14-48pp** but sub-gate on shadow lift because HRRR still wins each quartile's cell average individually. A per-obs continuous classifier (not quartile-bucketed pick) would extract this. Examples: pre_frontal/12-23h (23pp), nw_flow/12-23h (48pp), sw_flow/12-23h (35pp).

**Per-obs gap is 20-40% MAE across nearly every cell** — the ceiling for a per-obs classifier is huge on h.

## Ship shape (if it clears the pipeline)
L1 selector signature grows a per-obs axis. First implementation:
```
pick_source(field, lead_h, regime, hour_local, ims=None, xr_q=None, ...) -> "hrrr" | "nbm" | "nws"
```
Curated table keyed on (field, regime, band, ims_quintile) instead of (field, regime, band). Same 4-stage promotion pipeline as C1 axes, terminating at L1 instead of C1.

## Stage 1 done — 09-19
Single-threshold ims on held-out halves: only `h/sea_breeze/24-47h` generalized cleanly (train +9.86% / test +4.32%, 11.1% of per-obs gap; overfit guard 0.44× < 0.5× strict). Multi-axis voting via bin-picks collapses to always-min by construction — voter minimizes cell-avg = always-min. Only per-obs classifiers (or fine sub-partitioning) can beat that.

## Shipped v0.6.640 (shadow)
`l1_selector.py` — new `_ims_override(field, regime, band, ims)` + expanded `pick_source(..., ims=None)` signature. `_IMS_SELECTOR_CELLS` currently holds one entry: `("h","sea_breeze","24-47"): (13.0, "H_high")`. `forecast_snapshot.py` computes `ims = |{f}_l1 - {f}_raw_nbm|` per row and passes it through.

`IMS_SELECTOR_SHADOW_ENABLED = False` — branch inert, picks identical to v0.6.639. Flip to True after 7-day pair-log accumulates and retro confirms +4.32% held-out lift replicates on fresh data. Blast radius when flipped: ~30-50 obs/day (one cell, one regime, one lead band).

## Stage 0 field sweep (09-19)
Parameterized `h_l1_selector_ims_stage0.py` (accepts FIELD as argv[1]). Ran on 9 fields:

| Field | Verdict | PROMOTE cells | Top shadow lifts |
|---|---|---|---|
| **ch** | PROMOTE | 3 | **+14.3%**, +8.2%, +13.8% |
| **wg** | PROMOTE | 7 | +8.3%, +5.9%, +5.3%, +4.1%, +3.1%, +3.1% |
| **cc** | PROMOTE | 3 | +8.7%, +7.9%, +4.9% |
| **wd** | PROMOTE | 2 | +7.3%, +6.1% |
| **h**  | PROMOTE | 2 | +6.4%, +4.0% |
| **dp** | PROMOTE | 1 | +6.2% |
| t | HOLD | 0 | (sub-gate spreads exist, no halves-stable + shadow lift) |
| sr | HOLD | 0 | 40-97pp sub-gate spreads but halves fail — likely wants a different axis (cross-run spread not inter-model) |
| ws | HOLD | 0 | narrow spreads |

**ch has the biggest ims picking payoff** — 3 cells at +8-14% shadow lift. ch is at 63% VC 7d / 90% 24h — real headroom.

**sr HOLD is diagnostic**: signal exists (huge spreads) but not halves-stable on ims quartile-splits. Solar radiation likely responds to day-to-day cloud regime changes better captured by cross_run_spread than inter-model spread. Try that axis for sr in the next survey.

## Next steps
1. **09-26 gate check**: re-run `h_l1_selector_ims_stage1.py` on fresh pair-log data. Strict gate: test ≥ 3%, train ≥ 3%, test ≥ 0.5× train. If clear → flip `IMS_SELECTOR_SHADOW_ENABLED = True`.
2. **Stage 1 sweep after gate flip**: extend Stage 1 to the other 17 promote cells (ch/wg/cc/wd/dp). Same threshold approach. Add cleared cells to `_IMS_SELECTOR_CELLS` batch by batch.
3. **Second per-obs axis for sr + t + ws**: build a Stage 0 for cross_run_spread (xr_q) and state_fc/obs disagreement. Different axis per field is the working hypothesis.
4. **Per-obs classifier** (Stage 1 v2): if simple threshold rules don't scale, replace with a logistic-on-continuous-features fit per cell. Higher ceiling than binning.

## Why: 6 weeks of selector work + C1 axes existed but never crossed the wall
Every C1 axis built since v0.6.401 (ims Stage 2 PROMOTE 09-12, xr_q live since v0.6.401g, cluster_spread wired, state_fc/obs on backlog) feeds `confidence_layer.py`. `l1_selector.py` still uses only the coarsest features. The C1 → L1 bridge was the missing wire. Joe surfaced this frustration 09-19 after 6 weeks of stuck VC on dp/t/sr/h.

**How to apply:** before proposing more L1 selector fixes on weak fields (dp/t/sr/h), check whether the fix would actually add per-obs signal or just re-arrange the coarse bucket. If the latter, it's diminishing returns; the real lever is Stage 1 → wiring C1 axes into the selector.

## Why: 6 weeks of selector work + C1 axes existed but never crossed the wall
Every C1 axis built since v0.6.401 (ims Stage 2 PROMOTE 09-12, xr_q live since v0.6.401g, cluster_spread wired, state_fc/obs on backlog) feeds `confidence_layer.py`. `l1_selector.py` still uses only the coarsest features. The C1 → L1 bridge was the missing wire. Joe surfaced this frustration 09-19 after 6 weeks of stuck VC on dp/t/sr/h.

**How to apply:** before proposing more L1 selector fixes on weak fields (dp/t/sr/h), check whether the fix would actually add per-obs signal or just re-arrange the coarse bucket. If the latter, it's diminishing returns; the real lever is Stage 1 → wiring C1 axes into the selector.
