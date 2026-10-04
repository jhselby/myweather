---
name: cl-h-predictor
description: "CLOSED MISS 2026-08-17 same-day. Stage 0 found HRRR's h_fc is a real structural predictor of cl residual variance (disagreement cells 1.59× MAE of agreement cells). Stage 1 walkforward: routing rule (persistence-of-obs fallback at lead≥12h AND disagreement, N=6h) squeaked to +2.5% overall on 14d held-out, but halves catastrophically failed — Half A −35%, Half B +34%. Third cl-correction architecture to fail this session (after EMA/Kalman and Lc-rolling-window). h_predictor signal on cm/ch has univariate spread but neutral disagreement ratio — signal explained by baseline difficulty, not routable structure."
metadata: 
  node_type: memory
  type: project
  originSessionId: 32832742-5efb-4b02-a23b-3cd645f9da4d
  modified: 2026-08-17T12:59:05.217Z
---

# cl h-predictor router — CLOSED MISS

**Status:** [closed: 2026-08-17 same-day, MISS]. Stage 0 HIT that survived leakage scrutiny — but Stage 1 halves-stability showed the win was averaging noise, not signal. cl remains resistant to correction under yet another architecture.

## Stage 0 (`analysis/h_cl_h_predictor_stage0.py`)

Multi-field join on (run_time, obs_time, lead_h) between cl and h pair-log rows. For each cl row, look up HRRR's raw h forecast_l1 at the same forecast point. Stratify cl residual variance by h_fc.

Univariate cl MAE by h_fc bin:

| h_fc | n | cl MAE |
|---|---|---|
| 0-40% | 2031 | 9.97 |
| 40-60% | 8022 | 10.91 |
| 60-75% | 8709 | 13.75 |
| 75-85% | 5925 | 16.61 |
| 85-92% | 4473 | 20.57 |
| 92-100% | 4702 | 21.46 |

2.15× spread — real univariate signal.

Bivariate `(cl_fc bin × h_fc bin)`: agreement cells (both wet or both dry) MAE = 12.77, disagreement cells (cl says wet + h says dry, or vice versa) MAE = 20.29. **Ratio 1.59×.** The most striking cell: `(cl_fc=95-100 predicted, h_fc=60-75 predicted)` MAE = 83 — HRRR predicts full overcast but only medium humidity, which is internally inconsistent and dramatically wrong.

Verdict: STAGE 0 HIT. Signal is physical (clouds require near-saturation) and structural (specific bin combinations show the pattern).

## Stage 1 (`analysis/h_cl_h_predictor_stage1.py`)

Honest walkforward: split last 14 days as held-out. Routing rule tests:

| routing scheme | N=6 overall Δ | N=12 | N=24 |
|---|---|---|---|
| always-persist | −22.0% | −34.8% | −34.5% |
| disagreement-only | −0.7% | −6.8% | −6.6% |
| long-lead-only (lead ≥ 12h) | −19.0% | −29.6% | −27.4% |
| **long-lead + disagreement** | **+2.5%** | −2.5% | −2.5% |

Only one cell of the grid cleared the 2.0% SHIP floor. Halves-stability on the winner:

| window | n | overall Δ | disagreement-only Δ |
|---|---|---|---|
| Full 14d | 15,382 | **+2.5%** | +5.3% |
| Half A (2026-08-03 → 08-10) | 7,365 | **−35.5%** | −85.2% |
| Half B (2026-08-10 → 08-17) | 8,017 | **+34.3%** | +67.3% |

Complete failure of halves-stability. The +2.5% was averaging noise.

## Why it failed

The routing rule fires when the (cl_fc, h_fc) cell is a "disagreement" and lead ≥ 12h. At those points it swaps HRRR's raw cl for a 6-hour lookback mean of cl obs. In Half A, cl obs during the lookback windows systematically differed from cl during the scoring window — so the persistence fallback dragged forecasts away from truth. In Half B, the pattern flipped and persistence was closer.

Same fundamental cl-instability story as [[project_lc_ema_kalman_fallback]]. Any correction method that assumes "recent state predicts near-future state" for cl fails because cl's underlying process is too regime-driven for local temporal smoothing.

## Signal on other fields (cheap check)

Ran the same Stage 0 on cm/ch/cc:

- **cm**: univariate spread 3.37× (bigger than cl) BUT disagreement ratio 0.99× (neutral). High-h rows just have higher MAE across the board — no routable structure.
- **ch**: same — spread 2.45×, disagreement 0.95×.
- **cc**: spread 1.61×, disagreement 1.54× — real routing signal, comparable to cl. **But cc ships via Ccd** (derived from cl_l6/cm_l6/ch_l6 after Lc), so the router would be moot in production.

Only cl has the routable disagreement structure, and cl doesn't monetize it.

## Pattern across the session

Three cl-correction architectures tested today, all failed:

1. **Lc rolling-window sweep** (existing `h_lc_rolling_window`): no window recovers cl on 14d hold-out. Diagnosed as fit-target instability.
2. **Lc EMA/Kalman fallback** ([[project_lc_ema_kalman_fallback]]): Stage 0 "HIT" was leakage; honest run-time-keyed simulation hurts cl at every N.
3. **h-predictor persistence router** (this workstream): Stage 0 real, Stage 1 halves-unstable.

cl's underlying process is too regime-driven for local temporal smoothing OR raw-forecast-bias correction. Correction architectures that DO work for cc/cm/ch (fixed-window Lc, presumably Ccd-adjacent) don't work for cl.

## Remaining Stage 0 ideas from the closed EMA memo

Not yet tested:
- **fc-trajectory** — multi-run consistency of cl_fc for the same valid_time across recent HRRR runs. If HRRR keeps agreeing with itself, trust it more.
- **LCL height** — derived from t + h + pressure. More precise cloud-formation predictor than h alone.
- **Satellite low-cloud** — external observation of low-cloud presence (needs a new data source).
- **Reviving clp with a new gate** — clp exists as SHADOW but Stage 3 walker FAILS min-J 0.167.

Given today's 3-for-3 failure rate, my prior on any of these succeeding is low. cl may genuinely be beyond shift-table-family correction for the KBVY/HRRR combination we're working with. The `_FIELD_SKIP` from 07-30 is looking more and more like the correct answer rather than a bandage.

## Related

- [[project_lc_ema_kalman_fallback]] — same-session closed workstream, meta-lessons on simulation leakage.
- [[project_lc_regime_conditional]] — regime-conditional Lc also HURTS cl (walkforward).
- [[project_lc_cl_unskip_investigation]] — original un-skip investigation; can close as "no correction architecture works."
- [[project_plan_pipeline_to_good]] item 3 — update to reflect all three fallback architectures closed.
- [[feedback_hypothesis_promotion_pipeline]] — Stage 1 halves-stability caught the false HIT; pipeline discipline holding.

## Meta-observation

Two commits today (v0.6.425, v0.6.426) advanced our knowledge by ruling out approaches, not by shipping. Both are valid progress under the hypothesis-promotion-pipeline discipline. When cl comes up again, we can point at these closed workstreams instead of re-running the same investigations.
