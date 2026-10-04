---
name: project-08-10-confidence-axes-sweep
description: 08-10 session — smoke tested ~20 novel confidence axis ideas; 4 promoted to Stage 0 HIT and 1 to Stage 1 PROMOTE. Full punchlist here.
metadata: 
  node_type: memory
  type: project
  originSessionId: 795b3253-14c7-40c1-bfc6-2279cd08d765
  modified: 2026-08-11T00:14:35.705Z
---

# 08-10 confidence-axes sweep

Session goal: use remaining weekly session time to smoke-test angles not covered in `analysis/`. ~20 ideas across 4 rounds, three cleared Stage 0 held-out gate, one cleared Stage 1 orthogonality. Landed as individual `h_*_stage0.py` / `_stage1.py` scripts — all auto-picked-up by `run_digest.sh`.

## Landed hypotheses & verdicts

| script | verdict | notes |
|---|---|---|
| `h_run_bias_carryover_t_stage0.py` | NO HIT (-5.6%) | Smoke was in-sample; held-out killed. Kept for re-fire. |
| `h_run_bias_carryover_pa_stage0.py` | NO HIT (-13.2%) | Same story. Kept for re-fire. |
| `h_cross_run_spread_stage0.py` | HIT (8 fields) | wd 7.30x, t 3.59x, wg 2.57x, dp 2.54x, h 2.38x, pr 2.64x, ws 1.89x, cl 238x. |
| `h_windspeed_t_confidence_stage0.py` | HIT | observed ws bin -> \|t_err\| ratio 1.92x monotone. |
| `h_cross_run_spread_c1_stage1.py` | **PROMOTE** | ortho to BOTH transition + pt on 7/7 tested fields. |
| `h_forecast_magnitude_confidence_stage0.py` | HIT (wg only) | wg 2.23x. t near-miss 1.82x, dp thin. |
| `h_depression_cloud_confidence_stage0.py` | HIT (2 fields) | cl 3.06x, ch 2.77x; cc/cm missed monotone. |
| `h_recent_err_streak_stage0.py` | HIT (5 cells) | t/4-12 4.18x, t/13-36 3.59x, wd/4-12 2.67x, wd/13-36 2.50x, wg/4-12 2.03x. |

## Standing stack of Stage 0 hits ready for Stage 1

1. **Cross-run spread** — already at Stage 1 PROMOTE. See [[project_cross_run_spread_c1_axis]]. Blocked on ortho vs cluster_spread_q.
2. **Windspeed -> t** — Stage 1 ortho check against pt + cluster_spread_q.
3. **Forecast-magnitude wg** — Stage 1 ortho vs pt (high-wind forecasts often follow big pt swings).
4. **Depression -> cl/ch** — Stage 1 ortho vs cluster_spread_q (both moisture-adjacent).
5. **Recent-3h \|err\| streak** — Stage 1 ortho vs cross-run spread (both difficulty proxies).

**Why:** c1 currently has 5 axes (transition, cluster_spread_q, pt, precip_fc, hsf_group). This sweep queued 5 new axis candidates. Most likely to survive Stage 1: cross-run spread (already validated), recent-streak (independent temporal signal). Depression and windspeed will fight cluster_spread_q.

**How to apply:** Do NOT bulk-promote. Each Stage 1 tests exactly one candidate at a time, on the current live c1 axes. Ship narrow — [[feedback_orthogonality_gate]] applies. If two candidates test ortho, next check is orthogonality between THEM before both ship.

## Findings that died at Stage 0

- **Same-sign streak (bias direction persistence)** — 95%+ apparent rates are adjacent-row autocorrelation. Not signal.
- **Inter-source sigma \|cloud err\|** — WEAK (spread=4.0 across sigma bins).
- **Diurnal transition penalty** — DEAD. Midday |t_err| exceeds sunrise/sunset.
- **Run-level bias carryover (t, pa)** — smoke's in-sample "signed yield" of 22.9% / 14% did not survive OOS OLS.
- **Analysis-time transition -> tail err** — only pa 1.68x survived, likely axis-overlap.
- **state_obs regime freshness** — DEAD.
- **Cyclic 24h lag autocorrelation** — WEAK/DEAD (also had a computational bug).
- **Cross-field \|err\| coherence** — Real correlations reduce to derived-field families (dp-h 0.74 is trivially h=f(t,dp)). t vs cc r=0.03 — genuinely independent. **Useful negative finding: validates per-field confidence gates.**
- **|forecast dt| -> \|err\|** — Big for bounded fields (bounded-field zero-heavy artifacts); weak (1.07-1.44) for unbounded.
- **Precip-fc regime -> other-field err** — dp/h/cc BETTER when wet fc (0.64-0.71x). Interesting but reversed direction, modest effect. Not promoted.

## Related
[[project_cross_run_spread_c1_axis]] · [[project_c1_pivot_to_confidence]] · [[feedback_orthogonality_gate]] · [[feedback_measure_against_live_stack_baseline]] · [[project_metric_provenance_v0391]]
