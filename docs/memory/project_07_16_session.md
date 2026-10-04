---
name: project_07_16_session
description: "**20-ship marathon Thursday (v0.6.352b → v0.6.353l).** MLC diagnosis closed 'seasonal-not-HRRR'; new accuracy-over-time chart infrastructure (sparklines + detail + persistent history + ship annotations); Rule 5 automation shipped; sr sea_breeze Lsr refit Stage 1 PROMOTE (+43.7%); Stage 4 refined view promoted to primary; silent 15-day multi-axis stratification bug found + fixed; Safari reload-with-hash 3-layer bug fixed; Lc flip prep for tomorrow."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9f628bfb-c69d-4f01-8ea8-d87eb0bb20d7
---

## Ship arc

v0.6.352b → v0.6.353l across the day. Two clean threads: (a) closing out today's diagnostic questions, (b) building measurement infrastructure. Both surfaced real bugs while in progress.

## MLC collapse diagnosed (v0.6.352b)

07-13 read said "COLLAPSE at 07-07, separate event from cm HRRR anomaly." Today's fresh per-obs-day recompute (`analysis/marine_layer_collapse_diagnostic.py`) proved: real break was **06-30**, not 07-07. The 07-07 date was the growing cumulative window of the Fitter's watch series finally reflecting the older shift. Split at 07-04: in-bin Δ = −48.6 vs out-of-bin Δ = −5.0 (9.8× ratio) → stratum-local, pre-HRRR. Companion cl signal weakens same week. Diagnosis: **likely seasonal marine-layer weakening; will NOT re-arm when cm HRRR anomaly clears.** Full detail: [[project_mlc_diagnosis]]. Reusable lesson: [[feedback_fresh_per_day_recompute]] — cumulative fitter watch series lag the real break; recompute per-obs-day before hypothesising causation.

## Accuracy-over-time chart infrastructure (v0.6.353 → v0.6.353j → v0.6.353l)

New standing measurement tool that fills the gap between per-tick MAE tables and 2-window anomaly detector. See [[project_accuracy_over_time]] for the standing reference.

## Rule 5 automation (v0.6.353b)

`scripts/check_stale_refs.py` + `make check-stale` codifies the transition-invalidation sweep discipline. Grep-checks the debug page for stale predictive-tense refs (day counters `(MM-DD)`, `as of MM-DD`, `HOLD until MM-DD`, `earliest ship/flip MM-DD`), exits 1 on any > 2 days old. Historical mentions deliberately left alone. Directly addresses today's own v0.6.352c failure. Extended [[feedback_debug_page_canon]] with the automation note.

## sr sea_breeze Lsr refit Stage 1 PROMOTE (v0.6.353c)

Held-out MAE 137.93 → 77.64 (+43.71%). Halves check A→B +26.55% / B→A +38.58%, both confirm. Overall fit bias +67.60 matches 07-11 confound diagnostic direction (+83.6). Caveats: 3 test days, high underlying variance between halves. Next: Stage 2 = full per (regime × hour) cross-cut across all regimes + multi-week stability check. Memory [[project_sr_unit_mismatch]] updated with the Stage 1 outcome.

## Stage 4 audit — refined view promoted to primary + silent 15-day multi-axis bug fixed (v0.6.353e / v0.6.353f)

**v0.6.353e:** `c1_stage4_audit.py` now prints refined view FIRST (labeled PRIMARY), legacy view second (labeled `[legacy — not authoritative]`). Closes with a pinned `Verdict:` line carrying refined recommendation so digest exec summary picks it up. JSON gains top-level `primary` field. Memory [[project_stage4_audit_metric_limitation]] updated with the codified-in-script note.

**v0.6.353f:** the promotion immediately exposed a **silent 15-day bug**: multi-axis reporting 1013 cells all n=0 (INSUFFICIENT). Root cause: on 07-01 v0.6.272, `c1_confidence_calibration_v2.py` extended the axis_key format from 4-part (`sq::pt::slot::c1f`) to 5-part (`sq::pt::slot::c1f::hsf`) when C1e (hours-since-front) shipped. `c1_stage4_audit.py::stratify()` kept building 4-part keys. Every ship-cell lookup missed. Fix: added `_load_frontal_passages()` and `_hsf_group()` mirroring the calibration script. First real read: 195 PASS / 139 WATCH / 320 FAIL / 143 INSUFFICIENT / +216 excluded → NOT READY (genuine signal, not infrastructure failure).

**The learning:** the split legacy-vs-refined view had been masking infrastructure failure. Legacy single-axis stayed working, so no metric reported total failure. Elevating refined to primary exposed the "1013 INSUFFICIENT" symptom which led to the fix. **Never assume a metric is honest just because it's numeric — check that its accumulator is actually accumulating.** See [[feedback_verify_writers_for_read_paths]] — this is a real-world instance where the pattern was needed.

## Safari reload-with-hash bug (v0.6.353l)

Three-layer bug that only manifested on localhost Safari, not live Chrome. Symptom: Cmd-R with `#sec-research` in URL made R&D scroll into view AND expand all its subsections AND flash the header. Diagnosis: (1) Safari's default scroll-to-hash on reload (Chrome uses scroll restoration), (2) our `openSectionByHash`'s aggressive "expand every inner `<details>`" on any hash target, (3) CSS `:target` matching R&D and firing the `.research-heading` flash animation. Fixes: `history.scrollRestoration = "manual"`; `{expandAllInner: false}` opt on load-time `openSectionByHash` call; strip URL hash via `history.replaceState` on reload only (`performance.navigation type === "reload"`) before any DOM parses. Preserves hash behavior for fresh navigation.

## Lc flip plan for 07-17

Full prep saved to [[project_lc_flip_plan]] — exact preconditions, one-line flip in `cloud_saturation_correction.py:29`, deploy sequence, and Rule 5 sweep list. Delete after flip lands.

## Ships closed today

- MLC as ship candidate — closed, hold indefinitely, redesign candidate for autumn data
- sr sea_breeze Lsr refit — Stage 1 PROMOTE, into Stage 2 pipeline
- Stage 4 refined view promotion — TODO item closed
- Rule 5 discipline codification — moved from process rule to automated check
- `make analyze` + `_combined.txt` — dead code removed

## Session cost & meta

Joe corrected my scope twice (v0.6.352c partial sweep → v0.6.352d full sweep; my confused explanations of the Safari bug → simpler "3 stacked bugs" framing). Both self-inflicted; the Rule 5 automation should reduce the former. The latter is a communication lesson: when diagnosing multi-layer bugs, keep the layer-by-layer breakdown visible and don't declare victory until all layers are fixed.
