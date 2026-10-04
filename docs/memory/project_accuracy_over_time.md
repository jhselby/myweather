---
name: project_accuracy_over_time
description: "Standing measurement tool built 2026-07-16. Per-day MAE/RMSE/bias/Brier trajectory chart on the debug page — Raw / L2 / L3 / Prod, rolling 7-day means, ship-date annotations, sparkline grid + detail chart. Persistent history grows indefinitely past the pair log's 30-day retention."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9f628bfb-c69d-4f01-8ea8-d87eb0bb20d7
---

## What it is

`analysis/mae_over_time.py` + accuracy-over-time chart section on the debug page (inside `#sec-accuracy` since v0.6.353j). Fills the gap between per-tick MAE tables (current window only) and the 2-window anomaly detector (discrete alarms, no trajectory). Surfaces gradual drift and lets you visually verify a ship moved the needle.

## Data flow

1. Script aggregates `forecast_error_log.jsonl` per (obs_day × field × layer × metric). All four layers: Raw (L1), L2, L3, Prod (L4). Metrics: MAE, RMSE, signed bias, Brier.
2. Publishes `mae_over_time.json` to GCS via `weather_collector.gcs_io.upload_json`.
3. Auto-picked-up by daily digest via `analysis/*.py` glob.
4. Frontend fetches from GCS with cache-busting, renders sparkline grid (scan-all) + detail chart (drill-down).

## Persistent history model (v0.6.353h)

Pair log is capped at 30 days by `weather_collector/processors/decay_fit.py::RETENTION_DAYS`. A re-aggregate-from-scratch view would max out there. Script maintains an accumulating history:

1. Fetch prior `mae_over_time.json` from GCS.
2. Recompute per-day rollup from current pair log.
3. Merge: overwrite last `MERGE_REFRESH_DAYS=3` days (recent still accumulating); preserve older days (pair-log rows may have been pruned since prior recording).

**Why 3-day refresh window:** today's day is still growing; the last few days may see late-arriving pair rows. 3 days is generous but not so long that stale-pruned data creeps in.

## Storage math (per "always be mindful of data volume" — codified 07-16)

Each (day × field × layer) cell ≈ 90 bytes JSON. 13 fields × 4 layers = 52 cells/day → ~5 KB/day → ~1.8 MB/year. Trivial at years of scale. Storage knobs at top of script: `MIN_N_PER_DAY = 200` (drop noise-thin cells), `MERGE_REFRESH_DAYS = 3`.

## Frontend structure (inside `#sec-accuracy`)

`<details open id="sec-mae-over-time">` contains:
1. Field + Metric dropdowns
2. Detail chart (280px) — one field, all four layers + rolling 7-day means (Raw + Prod only) + ship-date annotations
3. Sparkline grid — 13 mini-charts (~190×80 each), Raw + Prod rolling means only, click to focus detail chart

Both react to metric selector. Selecting `pp` auto-flips metric to Brier.

## Ship-date annotations (SHIP_EVENTS map in frontend JS)

Per-field {date, label} pairs for events with visible expected impact. Currently populated:
- `ws` 2026-07-06: L3 skip-table firing (the big visible move after 4-day silent dormancy)
- `sr` 2026-07-06: Lsr correction firing after bug fixes
- `t` 2026-07-13: Lt retired
- `pa` 2026-07-13: τ 28→42
- `pp` 2026-07-04: pp dropped from L3
- `cm` 2026-07-04: HRRR cm anomaly onset (data event, not ship — labeled to explain the mid-window Prod spike)

**Dormant ships (ENABLED=False) deliberately NOT annotated** — they don't move Production, so annotating would suggest impact that isn't there. **When a gate flips live, add the corresponding annotation** — e.g., tomorrow's Lc flip should add `{date: "2026-07-17", label: "Lc flip"}` entries for cc/cl/cm/ch.

## Rolling-mean methodology (v0.6.353i)

Chose rolling 7-day mean over linear regression: no functional assumption, obviously "smoothed" so reader won't mistake for a fitted line. Only overlaid on Raw and Prod (not L2/L3) to avoid 8-line noise — the reader watches Raw ↔ Prod for drift. Rendered thicker (4px) with 0.35 alpha so daily line stays visually dominant. Kicks in once ≥4 non-null points in the trailing 7-day window.

**Why complementary to ship annotations:** if a ship's effect is sustained, the rolling mean bends within a week. If it reverts, the mean stays flat. Visual test for "did this ship do real work."

## Files

- `analysis/mae_over_time.py` — the aggregator
- `analysis/output/mae_over_time.json` — local mirror (gitignored)
- `https://data.wymancove.com/mae_over_time.json` — GCS published copy consumed by frontend
- `corrections_debug.html` inside `#sec-accuracy` → `#sec-mae-over-time` — the UI

## Related

[[project_stage4_audit_metric_limitation]] (companion drift-detection tool with a very different failure mode — see the silent-15-day-multi-axis bug narrative), [[feedback_verify_writers_for_read_paths]] (the pattern that would have caught the Stage 4 stratify bug earlier), [[feedback_debug_page_canon]] (Rule 5 — annotations need updating when live ships happen).
