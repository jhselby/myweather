---
name: cm-stage4-degradation
description: "2026-07-11: Stage 4 refined view flipped from 27/1/2 (07-10) to 26/0/9 (07-11) after a single-day window roll. 8 of 9 refined FAILs are cm × every band × both difficulty keys, all post-mixture-check (real drift, not weather-mixture). cm calib MAE 9-15 → recent MAE 25-33 (2-3× degradation). cl/24-47h newly joined cl/12-23h as FAIL. Legacy C1 axis ship BLOCKED; the '2-SKIPs → 96%' plan died."
metadata: 
  node_type: memory
  type: project
  originSessionId: 2bd018ca-98b4-4343-badc-7b405cae24be
---

## What happened

Saturday 2026-07-11 07:xx digest. The plan going into today was to ship legacy C1 axis with 2 manual SKIPs (ws/24-47h + cl/12-23h) → 27/28 refined PASS = 96.4% → READY. Yesterday's refined view was **27 PASS / 1 WATCH / 2 FAIL**.

Today's refined view: **26 PASS / 0 WATCH / 9 FAIL / 7 SKIP (metric-artifact)**. Pass rate 74.3% — under the 75% READY threshold. Would need to SKIP 7 cells instead of 2; can't.

## The FAIL pattern

8 of 9 refined FAILs are **cm × every band × both difficulty keys**:

```
cm/12-23h [transition]  +211.8%   9.0 → 27.9
cm/0-5h   [stable]      +200.2%   9.7 → 29.1
cm/6-11h  [transition]  +155.1%   9.8 → 25.0
cm/6-11h  [stable]      +136.6%  14.1 → 33.4
cm/24-47h [transition]  +126.1%  13.7 → 31.1
cm/24-47h [stable]      +121.8%  14.2 → 31.4
cm/12-23h [stable]      +110.1%  15.2 → 31.9
cm/0-5h   [transition]   +78.6%  11.6 → 20.7
cl/24-47h [stable]       +38.9%  20.1 → 28.0   ← new WATCH → FAIL vs 07-10
```

Every cm band × difficulty is ~2× worse in recent window vs calib. cl/24-47h newly joined cl/12-23h as failing (cl is destabilizing across bands too).

**Refined = post-mixture-check.** The mixture check tests whether drift is contained within one forecast-value bin (real degradation) or spread across changing bin populations (weather-mixture confound). All 9 FAILs came through as DEGRADED per the mixture check → not weather-mixture drift; real calibrated-band-width drift.

## Corroborating signals

- `c1_calibration_audit` (Stage 3 gate) → HOLD, 64.86% pass < 75%. Recommendation: re-curate.
- `c1h_curate` shows cm bands with +98% to +125% premium widening this week — genuine confidence-band drift on cm.
- Windows rolled one day (calib 06-26 → 06-27, recent 07-10 → 07-11). Yesterday's 27/1/2 verdict was thin — one dropped calib day + one added recent day flipped several PASS/WATCH → FAIL.

## Why (diagnosed 2026-07-11 by joining pair log to Stage 4 windows)

**Not a MyWeather pipeline bug — HRRR itself shifted this week.** Distribution comparison of cm forecasts + obs in the two Stage 4 windows:

| metric | calib (06-27→07-04) | recent (07-04→07-11) |
|---|---:|---:|
| mean cm forecast | 16.1% | **46.6%** |
| mean cm obs | 14.7% | 25.3% |
| signed bias (fc-obs) | +1.4% | **+21.3%** |
| MAE | 15.2 | 33.0 |
| RMSE | 28.8 | 47.3 |
| b0 [0-25%] fc count | 36,383 | 19,938 (−45%) |
| b3 [75-100%] fc count | 5,814 | **17,056 (+193%)** |

HRRR started forecasting mid-cloud much more aggressively AND being wronger when it did. Recent MAE within b3 bin is +50% vs calib MAE within b3 (per mixture check output) — so it's both a bin-population shift AND per-bin quality degradation.

**Regime + lead diffuse:**
- Every regime shows a +5 to +40 bias jump (ne_flow biggest at +38.75, with regime population also up +168%).
- Every lead band shows +20 to +23 bias jump (lead-uniform → not decay/τ).
- Not concentrated in one slice → structural HRRR-side change, not weather-composition amplifying a known bias.

## Candidate causes

- **(a) HRRR model change** this week (upstream update, boundary condition change). Persists.
- **(b) Persistent atmospheric setup** early July — stable marine air over New England, hazy summer conditions where HRRR mid-cloud parameterization runs hot. Transient.

Cannot distinguish with one week of data.

## Actions

**Immediate (07-11): DONE**
- Legacy C1 axis ship BLOCKED. Do not ship.
- Do NOT re-curate now — would bake potentially-transient anomaly week into bands.
- Do NOT SKIP the cm cells to force a ship — would bake ~2× MAE into ENABLED bands.
- Do NOT chase as a MyWeather pipeline bug — it's boundary-condition drift, not our code.

**Next audit window (07-18):**
- Re-run Stage 4. Two-week test:
  - If cm cells recover to PASS → cause (b) transient weather → do nothing, calibrated bands are still correct for typical weeks.
  - If cm cells hold FAIL → cause (a) structural HRRR shift → re-curate C1 bands (`c1_confidence_calibration.py` + `c1_curate_confidence_table.py`) + investigate HRRR side.

**Escape hatch still viable:**
- C1h + C1d standalone (curated-only, ENABLED=False) — narrow-promote gates at 2/7, earliest ship 07-16 if streaks hold. Distinct from legacy axis path.

## Meta-lesson for Stage 4 methodology

The mixture check verdict was DEGRADED (correct in one sense — per-bin MAE really did degrade), but the label doesn't capture the full picture: **within-bin MAE degraded AND bin populations shifted massively at the same time.** When HRRR moves its forecast distribution AND its bias inside the new distribution AT THE SAME TIME, the two effects compound and the mixture check treats them as one signal. Consider adding a companion diagnostic: "did the forecast-value distribution shift materially?" as a separate PASS/FAIL alongside the drift verdict. If both fail together, that's a structural upstream change to flag, not a per-band recalibration signal.

## Cross-refs

Related: [[project-c1-pivot-to-confidence]], [[project-stage4-audit]], [[project-stage4-audit-metric-limitation]], [[feedback-dont-invent-numbers]], [[feedback-co-owner-posture]], [[project-todo]].
