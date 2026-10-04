---
name: 08-21-evening-handoff
description: "08-21 session close — NBM cascade structurally complete (v0.6.450-455), selector data plumbing fixed, debug page swept. Next: F3 full NBM audit per project_nbm_structural_completion_plan."
metadata: 
  node_type: memory
  type: project
  originSessionId: 59e82d06-cdfb-4ebe-9ff9-4ea3ac9e7b83
  modified: 2026-08-21T16:33:37.964Z
---

# 08-21 evening handoff — NBM cascade shipped end-to-end; next session starts with NBM audit

**READ THIS FIRST — this is the entry point for the next session.**

## Session shipped (all deployed, all verified in prod)

Six versions in one long session (v0.6.450-455), all committed at 8cdacfe and pushed to origin/main.

- **v0.6.450** — cc l3_nbm clamp fix. Percent fields `[0,100]`, sr `≥0` in `forecast_snapshot._round_for`.
- **v0.6.451** — L4_NBM shadow-live. Diurnal hour-of-day residual for cc/ch. Cascade after L3_NBM.
- **v0.6.452** — L5_NBM shadow-live. Regime × hour_of_day solar bias for sr. Skips L4_NBM by design.
- **v0.6.453** — L6_NBM shape-only scaffold, t-only, `ENABLED=False` mirroring HRRR L6.
- **v0.6.454** — chp_nbm specialist. Reuses HRRR ch_persistence_gate primitives; overwrites ch_l4_nbm on gate-fired cells. Mid-session `weather_data` reference bug caused a 30-min snapshot outage (12:57-13:35 UTC); fix wraps arg as `{"hourly": hourly}`.
- **v0.6.455** — debug page F1-F12 punch list. Chart layer registry, per-field pipeline table, current-state, L1 card, Recent activity, 3 new fit-status tiles, SHIP_EVENTS, v0.6.432 router card RETIRED banner.

## Data-plumbing fix (matters most)

**Bug found and fixed:** `analysis/nbm_backstamp.py`'s synthetic historical rows lived only in `~/.cache/myweather_nbm_backstamp/forecast_error_log_backstamped.jsonl` — never published anywhere. Today's daily digest ran `l1_selector_fit` against the live pair log alone (2 days of L3_NBM stamps → n=6-186 per cell → nothing cleared MIN_N=200 → selector picked HRRR everywhere → chooser lift went to -29% on 7d, -61% on 24h).

**Fix:**
1. Uploaded backstamped file to `gs://myweather-data/forecast_error_log_backstamped.jsonl` (432 MB, stable URL, never overwritten).
2. New `pair_log_paths()` helper in `analysis/_cache.py` returns `[cached_path(LIVE), cached_path(BACKSTAMP)]`.
3. Updated `l1_selector_fit.py`, `l3_nbm_fit.py`, `l4_nbm_fit.py`, `l5_nbm_recompute_biases_hourly.py` to stream both.
4. Re-fit: **selector picks 9 cells for NBM** (cc all leads, dp 6-47h, wg 12-47h), router-scope ship-gate lift **+53.3% on n=75,023**. Verified 12:17 UTC tick in prod: cc 45/0, dp 39/6, wg 33/12.

**Auto-sunsets:** backstamped rows age out of the 30-day window naturally over the next ~28 days; live pair log alone will suffice after that. No maintenance needed.

**Why:** [[feedback-machine-only-fixes-invalid]] — a fix that only works on Joe's machine is not a valid fix.

## Scoreboard status

Chooser lift on the debug page will remain deeply negative (7d -29%, 24h -61%) until pair-log rows with new `selector_source=nbm` accumulate. 24h window fully turns over in ~24h; 7d takes a week. Selector picks in the snapshot log are already correct — only the *windowed metric* lags.

## What's next — the plan-of-record

See [[nbm-structural-completion-plan]] for full detail. Summary:

Before NBM shipped, the project was in **pure tuning mode** — HRRR cascade structurally complete, iterating on gates / cells / walkforwards. NBM broke that by introducing a second cascade without HRRR's monitoring scaffolding. To return to pure tuning, ~3-4 focused sessions:

**Session 1 (next): F3 — full NBM audit.** Walk the pipeline end-to-end, catch anything missed. Grounds the rest.
**Session 2: F1 (per-NBM-layer regression sentry) + F2 (NBM walkforward validator).** Restores earn-your-way + regression-alert loops for NBM.
**Session 3: F4 (gate-firing telemetry) + F5 (skip-table gate for NBM).** Same file surface.
**Session 4: F6 (PWA writeback trace).** Confirm the selector's `entry[f]` flows to `hourly[array_name]`.
**Later: F7 (applicability map entries), F8 (per-field caps + staleness gates).**

## Debug page state

- Debug page swept, retired all "cascade still to build" language, added 3 new fit-status tiles for L4/L5/L6 NBM, per-field pipeline table updated for t/cc/ch/sr.
- v0.6.432 L1 router card marked RETIRED with banner (superseded by L1 selector since 2026-08-19).
- Chart LAYER_STYLE + FIELD_LAYERS know about l4_nbm/l5_nbm/l6_nbm/chp_nbm/wdp_nbm (all dashed to mark NBM cascade).
- SHIP_EVENTS annotations added for today's ships across 6 fields.

## Files touched

**New:**
- `weather_collector/processors/l4_nbm.py`, `l5_nbm.py`, `l6_nbm.py`
- `analysis/l4_nbm_fit.py`, `l5_nbm_recompute_biases_hourly.py`, `l6_nbm_fit.py`
- `weather_collector/data/l4_nbm_curated.json`, `lsr_nbm_bias_table_curated.json`, `l6_nbm_cove_curated.json`

**Modified:**
- `analysis/_cache.py` (new `pair_log_paths()` helper)
- `analysis/l1_selector_fit.py`, `l3_nbm_fit.py`, `l4_nbm_fit.py`, `l5_nbm_recompute_biases_hourly.py` (stream both live + backstamp)
- `weather_collector/processors/forecast_snapshot.py` (L4/L5/L6/chp_nbm apply blocks; selector substitution walks l6>l5>l4>l3)
- `weather_collector/processors/forecast_error_log.py` (layer list gains l4_nbm, l5_nbm)
- `index.html` (version pill)
- `docs/CHANGELOG.md` (six new entries)
- `corrections_debug.html` (F1-F12 sweep)
- `weather_collector/data/l1_selector_table_curated.json`, `l3_nbm_curated.json` (refits with backstamp)

**NOT committed** (auto-regenerated by daily digest): 26 other curated JSONs and 7 `.cache_*_history.json` files.

## GCS state

- Uploaded: `gs://myweather-data/forecast_error_log_backstamped.jsonl` (432 MB, stable, never overwritten).

## Digest highlights from morning run (before today's ships)

- 163/163 pass, no ships fire, no regressions.
- New WATCH: **cm layer-shape at 0-5h (+13.4%) and 6-11h (+15.3%)**. cm hurts short-lead, L3-shipped for long-lead. Log as τ-suspect; don't touch yet.

## Related memory
- [[nbm-structural-completion-plan]] — the plan of record for next 3-4 sessions.
- [[nbm-parallel-pipeline-plan]] — the plan that shipped this session (superseded but kept for context).
- [[08-21-morning-handoff]] — mid-session state before L6/chp/audit work.
- [[feedback-answer-direct-first]] — why the next-session handoff leads with the plan, not the menu.
- [[feedback-machine-only-fixes-invalid]] — why the backstamp fix went to GCS, not the local cron.
