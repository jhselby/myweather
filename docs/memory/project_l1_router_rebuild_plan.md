---
name: l1-router-rebuild-plan
description: "2026-08-18 session plan — rebuild v0.6.432 as a proper pre-cascade L1 router (universal, per (field, lead-band), argmin over raw sources, cascade runs on top)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 1ca38152-581f-428c-be01-d4c986490eb5
  modified: 2026-08-18T19:05:54.835Z
---

# L1 router rebuild — session plan for fresh session

## What v0.6.432 got wrong

Shipped 2026-08-18 as an L1 router but is actually a **post-cascade override**:
- Cascade runs against Open-Meteo across the whole horizon.
- At the very end, for t/ws/wd at leads ≥6h, cascade output is thrown away and replaced with NWS-gridpoint (NBM) values.
- Pair log's `l1` slot still holds Open-Meteo. Two definitions of "L1" coexist (raw = Open-Meteo, user-facing = router-picked). Debug page becomes incoherent.
- Router covers only 3 fields (t/ws/wd) and only at ≥6h, not universally per (field, lead-band).

## What we're rebuilding it as (Joe's actual mental model)

**A universal pre-cascade seed router.** Every field. Every lead-band. Every tick.

- Router runs **BEFORE** `snapshot_raw_baseline` in `collector.py`.
- For every (field, lead-band) cell, router picks the raw source (hrrr | nbm) whose recent MAE against observations was lowest. Argmin, no defaults.
- Router mutates `hourly[<field>][i]` at every hour with the picked source's value.
- Cascade (L2/L3/L4/wdp/cove/Lc) runs against router-picked L1 unchanged.
- Users see cascade output = router-picked L1 + cascade lift.
- Pair log's `l1` slot IS the router's pick. Debug page's "raw" curves show router-picked values. One consistent semantics.

## Sources at runtime

- **HRRR** = Open-Meteo delivery (what we currently call "L1"). Available live for every field.
- **NBM** = point extracts from NBM CO grib archive. Needs a new hourly ingester (see below). Available for: t, dp, ws, wd, wg, sr, cc, cl, cm, ch, pa.

Neither is default. Router picks per cell.

Fields NBM doesn't expose (h, pr as of the CO subset): router table trivially has HRRR at every band (single-candidate cells, still going through the router).

## Design decisions locked in

- **Granularity**: per (field, lead-band). Bands = {0-2h, 3-5h, 6-11h, 12-23h, 24-47h}. Per-lead-hour is too many parameters to estimate reliably from live data.
- **Fit rule**: argmin of recent 14-day rolling MAE per (field, band, source). No thresholds, no gates. Just pick the winner. Halves-stability check for diagnostics, not gating.
- **Config**: `weather_collector/data/l1_router_table.json`. Refit nightly (analysis script emits new table). Router loads it fresh every tick.

## Cascade concern (documented, not fixed tonight)

Cascade layers were fit against Open-Meteo residuals. Applied to NBM at routed hours, some layers (L2 Kalman) will over-correct slightly — magnitude too large for NBM's cleaner residuals. Not directionally wrong. Estimated ~10-20% over-correction at routed hours. Ship and monitor; per-source K tuning is a follow-up if net production regresses vs. NBM raw at routed hours.

## Ship order (fresh session)

### 1. NBM point-extract service (~1-2h)
- New scheduled Cloud Function OR embedded in the existing publisher CF (already runs hourly).
- Fetches latest NBM CO grib (`s3://noaa-nbm-grib2-pds/blend.YYYYMMDD/HH/core/blend.tHHz.core.fFFF.co.grib2`) for leads 1-47.
- Extracts point values at Wyman Cove (42.5014, -70.875) for all fields NBM emits.
- Writes `nbm_point_extract.json` to GCS with structure:
  ```json
  {
    "generated_at": "2026-08-18T18:00:00Z",
    "run": "2026-08-18T17:00:00Z",
    "hourly": {
      "times": ["2026-08-18T18:00", ...],
      "t": [72.3, 71.8, ...],
      "dp": [...],
      "ws": [...],
      "wd": [...],
      "wg": [...],
      "sr": [...],
      "cc": [...],
      "cl": [...],
      "cm": [...],
      "ch": [...],
      "pa": [...]
    }
  }
  ```
- Source code: adapt `scratchpad/nbm_extract_wide.py` (~120 lines, already validated on 3 days of data during 08-18 backfill).

### 2. Router module rewrite (~1h)
- Rip out v0.6.432 `l1_router.py`.
- New `weather_collector/processors/l1_router.py`:
  - Loads `l1_router_table.json`.
  - Loads NBM extract from GCS (via existing fetcher pattern).
  - For each hour, for each field, computes lead_h, picks source from table, if `nbm`, replaces `hourly[<field>][i]` with NBM value from extract.
  - Stamps `hourly[<field>_router_pick][i]` per hour for debug visibility.
  - Shadow-writes `hourly[<field>_hrrr_shadow][i]` = original Open-Meteo value at every hour (so we don't lose HRRR historically).

### 3. Collector wire (~30min)
- Move router call from post-cascade (current v0.6.432 location) to before `snapshot_raw_baseline` (line 145).
- Ensure `raw_integrity._RAW_FIELDS` snapshots the router-picked values as `raw_*`.
- Add `temperature` / `dew_point_f` / `wind_direction` to `_RAW_FIELDS` if not there (currently missing per 08-18 investigation).

### 4. Rip out v0.6.432 legacy plumbing (~30min)
- `forecast_snapshot.py`: remove `l1r` layer slot from t/ws/wd, remove `l1r` from `_derive_applied_layer` walk order.
- `forecast_error_log.py`: remove `l1r` from per-layer emit loops (both branches).
- `decay_fit.py`: remove `l1r` from `per_layer_mae_by_lead` aggregation loops.
- `analysis/mae_over_time.py`: remove `l1r` from `PERMISSIVE_LAYER_KEYS`.
- `corrections_debug.html`: remove `l1r` from `LAYER_STYLE`, `FIELD_LAYERS` (t/ws/wd), `SHIP_EVENTS` 08-18 annotation. Remove the router state tile that read `<field>_pre_router` (arrays won't exist under new architecture).
- `js/obschart.js`: revert `maeAt()` to only read `l4` — no `l1r` preference (l1r doesn't exist under new arch).

### 5. Debug page consistency sweep (~1h)
- L1 section: raw curves now show router-picked values by construction; no need for "post-router" caveats. Update descriptor text.
- Applicability map L1 row group: rewrite for the universal architecture. Every field row = "picks per cell per band from router table." Add link to `l1_router_table.json` shape.
- Live per-hour router state tile: rebuild to read new `hourly[<field>_router_pick][i]` array. Show per-hour source label for every field, not just t/ws/wd.
- SHIP_EVENTS annotation: keep 08-18 but relabel "L1 router (universal HRRR/NBM per cell)".
- Nav breadcrumb, Sources tab, Recent Activity entry, changelog entry — all reflect universal-per-cell semantics.

### 6. Fit script (~30min)
- `analysis/h_router_fit.py`:
  - Loads pair log.
  - For each (field, lead-band), computes MAE for `hrrr` (from `forecast_l1`) and `nbm` (from `forecast_nws` + historical enrichment) over last 14 days.
  - Argmin per cell → source name.
  - Writes `weather_collector/data/l1_router_table.json`.
  - Emits diagnostics (per-cell MAE per source, margin, halves stability, n).
- Runs nightly via publisher CF or added to Fitter cron.

## Data available for fit script (already in hand)

- `scratchpad/nbm_cache_wide.jsonl` — 3 days × 12 fields NBM point extracts
- `scratchpad/nbm_cache_narrow14.jsonl` — 12 days × ws/wd/wg/sr NBM point extracts
- `scratchpad/hrrr_cache.jsonl` — 14 days × 6 fields HRRR-direct point extracts
- Pair log has `forecast_nws` stamped live since v0.6.431 (2026-08-18 morning) — accumulating

## Version + versioning

- Fresh session ships as **v0.6.434**. Supersedes and rolls back v0.6.432/v0.6.433 semantics.
- Rollback for v0.6.434: `_ROUTER_ENABLED = False` in new `l1_router.py` — falls through to Open-Meteo for every field at every hour, equivalent to pre-router behavior.

## Pre-flight checks before fresh session starts

1. Read this file first.
2. Read `project_nbm_hrrr_l1_triage.md` — has the 14-day scoreboard.
3. Verify current v0.6.432 is still live in production (`git log`, `gsutil cat gs://myweather-data/weather_data.json | python3 -c "import json, sys; d=json.load(sys.stdin); print(d.get('hourly',{}).get('corrected_temperature_router_source',[])[:6])"` — should show `['prod','prod','prod','prod','prod','prod']` at t=0 to t=5).
4. Confirm scratchpad caches are still present.

## What NOT to do in fresh session

- Do not re-derive the router design. It's above.
- Do not ship without the NBM extract CF first — router without NBM data is degenerate.
- Do not skip the v0.6.432 legacy plumbing rip-out (item 4). Leaving `l1r` as a dead layer name in the snapshot dict poisons future readers.
- Do not gate the router by fixed lead thresholds ("≥6h → NBM"). The router picks per cell from data, not from hand rules.

## Success criteria for v0.6.434 ship

- Pair log's `l1` slot for any routed row matches the router's picked source's value (not Open-Meteo).
- Debug page's L1 raw curves show router-picked values per hour, no "pre-router" concept.
- `hourly[<field>_router_pick][i]` present for every field, every hour.
- `l1_router_table.json` in GCS, refit nightly, per (field, band) source pick.
- No `l1r` references anywhere in code, snapshot, or frontend.
