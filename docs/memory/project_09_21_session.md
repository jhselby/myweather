---
name: project-09-21-session
description: "09-21 Mon — 7 commits, 4 collector deploys. Frontal detector 2 bugs (v0.6.643). Per-obs classifier v2b → curated cell → wire scaffold → feature plumbing → shadow telemetry (v0.6.644-646). Data leak caught + cc_combine walker loosened + chp finding anchored."
metadata: 
  node_type: memory
  type: project
  originSessionId: d9396da2-0b4a-4ad5-880f-066560d5a914
  modified: 2026-09-22T11:40:54.656Z
---

# 09-21 Monday session — per-obs classifier infrastructure end-to-end

## The strategic arc

Owner-level question surfaced early: the daily digest triage is a gravity well; we ship 1-2 cells while the memory itself says the per-obs oracle gap is 37-45% of MAE on h/dp/t/sr. Current chooser captures 8-20%. **Real headroom is 15-20% MAE — order of magnitude above what daily cell tuning yields.** 6 weeks of C1 axes never fed the picker; per-obs is the direction.

Today's work stood up the infrastructure to attack that gap.

## Ships

**v0.6.643 collector (frontal detector, 2 bugs).** See [[project_frontal_detector_health_09_14]] context.
1. `_classify_type` cold branch dropped `pressure_rising` requirement — trough sits AT frontal passage, bounce is lagging, requiring all three signals produced 4/5 recent events labeled "unknown".
2. `_window_entries` cutoff truncated to minute — was using `now_local` with seconds, silently dropped earliest obs when collector ran mid-minute; explained 3/6 missed wd+pressure passages runtime kept missing.

**v0.6.644 collector (learned classifier wire scaffold).** First non-crude-threshold picker rule.
- `l1_selector.py`: loads `l1_learned_selector_curated.json` at import → `_LEARNED_CELLS` dict. New `_learned_predict/override`. `pick_source(..., features=None)` signature extended. Precedence: HRRR PBL morning-overshoot → **learned per-obs** (new) → ims per-obs (v0.6.640) → regime → band pool → HRRR fall-through.
- Curator `analysis/l1_learned_selector_curate.py`: reads Stage 1 v2b outputs, filters to promote cells, emits runtime JSON.
- Fitter `analysis/l1_selector_per_obs_classifier_stage1_v2.py`: 12-feature L2 logistic. Cell: `h/nw_flow/24-47h`. Test +6.50% MAE lift on 879 rows, capture **19.9%** of oracle gap.

**v0.6.645 collector (feature plumbing).** Closed the loop.
- `forecast_snapshot.py::_build_learned_features(field, i, ims, valid_hour_local, hourly, derived, cross_run_spread, times)`: assembles the 12-feature dict per (field, lead) matching FEATURE_NAMES exactly.
- `append_forecast_snapshot(..., cross_run_spread=None)` signature; collector.py passes `weather_data.get("cross_run_spread")`.

**v0.6.646 collector (shadow telemetry).**
- `_learned_predict` split from `_learned_override`: predict always computes when cell + features present, override guards on flag.
- Public `learned_predict(field, regime, band, features)` entrypoint.
- `forecast_snapshot` stamps `entry[f"{f}_learned_pick_shadow"]` and `entry[f"{f}_learned_prob_shadow"]` **regardless of shadow flag** → pair log picks them up → retro can score classifier vs actual pool pick row-by-row without depending on flag state.

**Analysis-only commits** (no deploy):
- `analysis/h_cc_combine_walker`: loosened rule from "unanimous R over 7 days ≥1% margin" to "≥5/7 R days AND 0 M days AND ≥1% margin on R days" — physics-choice semantics, not regression-correction. 1 cell cleared today: `pre_frontal/0-5h` (PRRPRRR). Runtime gate `CC_COMBINE_GATE_ENABLED` remains False; 2-day out-of-sample stability watch before flip.
- `analysis/_residual_persistence_walker`: verdict now introspects processor file for `ENABLED = (True|False)` and emits LIVE / STAGE 3 READY (shadow) / STAGE 3 READY (unwritten) per actual state. Fixes stale digest noise where wg (live since v0.6.635), h and dp all showed identical "ready to write processor" text.
- `analysis/l1_selector_per_obs_classifier_stage1_v2.py`: 12-feature L2 logistic, replaces Saturday's parked 8-feature v1. Data-leak caught: `cc_disagree = |state_fc.cloud_cover - state_obs.cloud_cover|` used `state_obs` which is post-hoc. See [[feedback_state_fc_vs_state_obs]] — any live picker feature that reads `state_obs.*` is leakage. Initial run had t/ne_flow/12-23h promote at test +6.08% capture 23.2%; when leak removed, t collapsed to HOLD (the entire lift was the leak), h held at +6.50% capture 19.9%. Would have shipped fake improvement.

## Key findings

**chp is net +7.79% worse than L6 over 66 days post-Lc (all 22 live cells, 23,820 rows).** 79.4% of ch predictions in live chp cells are actively degraded by chp. Pattern: 0-5h wins clean (persistence natural short-lead advantage), 6-11h mostly loses, 12-23h systematically loses, 24-47h worst (pre_frontal/24-47 +37.1%, calm/24-47 +16.1%). Ship candidate: narrow chp to 0-5h only, drop all cells at 6h+. Day 1/7 watch; earliest ship 2026-09-28. Digest's 10-day tool inflates the numbers 3-5× vs 66-day view — don't act on that view alone. See [[project_chp_narrow_to_0_5h_watch]] for full anchor.

**cc_combine walker gate was over-strict for physics-choice questions.** Unanimity rule (R on ALL 7 days ≥1% vs max) never fired. Loosened rule fires exactly 1 cell (pre_frontal/0-5h) with the discipline still intact: 0 M days required. See [[feedback_gate_semantics_physics_vs_regression]] worth writing.

**Data leakage rule now with a live example.** `cc_disagree` used post-hoc obs. Left uncaught it would have shipped a t/ne_flow/12-23h "+6.08% capture 23.2%" that would have flopped in production. **Rule:** any classifier feature that reads `state_obs.*` in the fitter fails leak-check. Add to [[feedback_state_fc_vs_state_obs]].

## Shadow-evidence velocity — real observation

With only 1 curated cell `(h, nw_flow, 24-47)`, shadow stamps only land when `state_fc_by_lead` puts nw_flow into leads 24-47. 3 post-deploy snapshots through 18:27 UTC: **zero stamps** because none of those ticks had nw_flow forecast at 24-47h band. Estimated stamp rate: ~50-150 rows per week. Adds a second reason to expand cells (beyond MAE gain): faster shadow accumulation.

## Where the wire stands end-of-day

Full path live in production:
```
collector.py
 → weather_data (with cross_run_spread, derived, hourly)
 → forecast_snapshot.append_forecast_snapshot(hourly, ..., cross_run_spread)
 → per (field, i) loop:
     _feats = _build_learned_features(f, i, ims, valid_hour_local, hourly, derived, cross_run_spread, times)
     learned_pick, learned_prob = learned_predict(f, regime, band, _feats)  # shadow telemetry — always runs
     if learned_pick is not None:
         entry[f+"_learned_pick_shadow"] = learned_pick
         entry[f+"_learned_prob_shadow"] = round(learned_prob, 4)
     source = pick_source(f, i, regime, hour_local, ims, _feats)             # picks — guarded
         → _learned_override(...) → returns None when LEARNED_SELECTOR_SHADOW_ENABLED = False
         → falls through to ims override, regime override, band pool
```

Flag flip readiness: pair log accumulates `{f}_learned_pick_shadow` + `{f}_learned_prob_shadow` for retro. Once 7 days of fresh data has enough matched rows (~50-150), retro tool can compute counterfactual MAE = `|forecast_l4-obs|` if pick=hrrr else `|forecast_l3_nbm-obs|` and compare to actual selector source's MAE per row. If lift ≥ +3% on held-out fresh data, flip flag.

## Immediate next steps (fresh session pickup)

1. **Extend classifier to remaining fields** (`dp`, `sr`, `wg`, `ws`, `wd`, `cc`, `ch`). Run `analysis/l1_selector_per_obs_classifier_stage1_v2.py <FIELD>` for each. Watch for promote cells. Re-run curator `analysis/l1_learned_selector_curate.py` — add each field to `FIELDS = ("t", "h", ...)`. Each honest new cell = more MAE gain + faster shadow evidence velocity.
2. **Retro tool** to score shadow evidence: `analysis/l1_learned_selector_shadow_retro.py`. Reads pair log, joins on `{f}_learned_pick_shadow`, computes counterfactual MAE, reports fresh-window lift. Should run in daily digest once meaningful sample accumulates.
3. **09-22 or 09-23 gate check for cc_combine walker.** If pre_frontal/0-5h stays cleared and ne_flow/12-23h gains one more R day, both cells could be promoted to runtime by enabling `CC_COMBINE_GATE_ENABLED = True`.
4. **chp narrow-to-0-5h watch.** Day 2/7 tomorrow. Rerun the 66-day analysis, compare to today's anchor in [[project_chp_narrow_to_0_5h_watch]].
5. **09-26 ims Stage 1 formal gate.** From [[project_l1_selector_per_obs_axes]]. Fresh data check.
6. **09-27 wd L3_NBM skip-ADD earliest ship** (if the proposal set stays stable — Saturday's set reset today because 2 FRESH added / 1 STALE dropped).
7. **09-28 chp narrow-to-0-5h earliest ship.**

## How to apply

**Rule 1 — data-leak discipline for any per-obs classifier work.** Any feature that reads `state_obs.*` in the fitter is leak; the fitter learns a pattern the runtime can't reproduce. See [[feedback_state_fc_vs_state_obs]] and the today example (cc_disagree removed).

**Rule 2 — no more crude-threshold rules for new per-obs cells.** The learned-classifier wire is live. Any new per-obs signal goes through Stage 1 v2b (leak-safe features, held-out halves, non-degenerate NBM fraction gate) and lands in `l1_learned_selector_curated.json` via the curator. Don't hand-code new threshold rules in `_IMS_SELECTOR_CELLS` unless there's a specific reason the learned pipeline can't fit the shape.

**Rule 3 — shadow before flip, retro first.** Never flip `LEARNED_SELECTOR_SHADOW_ENABLED = True` without a retro pass showing held-out fresh-window MAE lift ≥+3% on ≥100 shadowed rows over ≥5 distinct days. Repeats the [[feedback_fresh_per_day_recompute]] discipline for learned models.
