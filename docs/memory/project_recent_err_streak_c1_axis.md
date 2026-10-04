---
name: project-recent-err-streak-c1-axis
description: Stage 1 PROMOTE 08-10 — past-3h |err| streak orthogonal to c1 axes on 4 of 5 cells. Stage 2 buildout parked (needs new live signal source in collector).
metadata: 
  node_type: memory
  type: project
  originSessionId: a5abe271-d453-4134-96ba-9a1fb2cf3347
  modified: 2026-08-11T00:48:45.239Z
---

# Recent-|err|-streak as c1 axis — parked at Stage 1 PROMOTE

## Verdict (2026-08-10)

`analysis/h_recent_err_streak_c1_stage1.py` (commit `7001ca9`). Tests past-3h hourly-mean |err| stratification vs the c1 incumbents (transition, pt) plus cross-run spread (itself PROMOTE from [[project_cross_run_spread_c1_axis]]).

**PROMOTE 4/5 cells** — orthogonal to all three conditioning axes on:
- t/4-12  (n_test=1629)
- t/13-36 (n_test=4344, cleanest — full matrix, ratios 1.92–3.73)
- wd/4-12 (n_test=1629)
- wg/4-12 (n_test=1629)

**wd/13-36** CONFOUNDED on spread — signal collapses to ratio 0.97 in spread_Q2. Cross-run spread already covers that cell. Drop from Stage 2 scope.

**Weak-evidence caveats**: t/4-12 spread verdict rests only on Q5 (all other spread quintiles THIN); wg/4-12 spread axis is entirely THIN. Real strength is against transition + pt for those two.

## Why Stage 2 is parked

Streak is a **live signal** — needs `mean(|err|)` over the past 3h per (field, band) at collector run time. Existing c1 axes (`spread_q::pt_label::trans::c1f::hsf`) are all state-based (computable from `weather_data.json` at forecast time). Streak isn't in that universe; the collector doesn't compute it today.

Stage 2 buildout scope (~3-4h careful work):

1. **Live signal source (new).** Two paths:
   - Tail-read `forecast_error_log.jsonl` each collector run to compute past-3h |err| per (field, band).
   - Add a rolling |err| stash to `weather_data.json` written by the pair-log builder.
   No preference yet — decide when we start.
2. **Measurement side** (`analysis/c1_confidence_calibration_v2.py`): compute per-row pt3 |err| from pair log, bin per-cell, add `streak_q` as a 6th key dimension in `by_axes`. Only for the 4 PROMOTE cells.
3. **Band mismatch to resolve.** v2 uses 0-5h / 6-11h / 12-23h / 24-47h; streak found HIT cells on 4-12h / 13-36h. Best current mapping:
   - t/4-12 → v2's 6-11h
   - t/13-36 → v2's 12-23h
   - wd/4-12 → v2's 6-11h
   - wg/4-12 → v2's 6-11h
   Must confirm halves stability on the v2 band boundaries before wiring (a re-fit of Stage 1 on 6-11h and 12-23h is the safer path — 5 cells collapse to 3 cells but on the exact bands the live layer uses).
4. **Lookup** (`weather_collector/processors/confidence_layer.py`): compose `streak_q` into the axis_key for those 3 cells only; fall back to the 5-tuple key elsewhere.
5. **Curator** (`analysis/c1_curate_confidence_table_v2.py`): SHIP/SKIP the new streak-conditioned cells.

## Cheaper next step (Option C) if we want to derisk before the live buildout

Do the measurement side alone first (item 2 + item 3 re-fit). If the by_axes MAE numbers on the v2 bands don't show meaningful separation, skip the live buildout entirely. ~1h, no live code touched.

## Related

- [[project_cross_run_spread_c1_axis]] — the sibling PROMOTE, also blocked on Stage 2
- [[project_08_10_confidence_axes_sweep]] — the sweep that produced this candidate
- [[project_c1_pivot_to_confidence]] — parent architecture
- [[feedback_orthogonality_gate]] · [[feedback_measure_against_live_stack_baseline]]
