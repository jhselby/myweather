---
name: correction-stack-architecture
description: Current correction stack per field (verified 2026-08-09 audit chunk 4). 4-layer core + specialists. L3/L4 whitelists have narrowed dramatically — 8 fields now run L1+L2+specialists only.
metadata: 
  node_type: memory
  type: project
  originSessionId: 8936b8c9-2577-4ecc-9d6b-6658da634b60
  modified: 2026-08-09T14:16:54.685Z
---

## Layer model

1. **L1 — Raw model** (HRRR 0-48h, GFS 3-7d via `hourly_7day`)
2. **L2 — Mesonet corrections** — 81-station network → per-station Kalman → octant-balanced aggregation. Sub-shapes: t/pr exp decay, h soft_ramp (K 1.0→0.4 over 24h), wind octant-max→median, cl hourly[0] blend at lead 0.
3. **L3 — Decay correction** (`decay_apply.py:78` — `L3_FIELDS = {"wg", "ch", "cm"}`) — per-(field, lead_h) recency-weighted mean error subtracted. Brier-only path for pp (`L3_BRIER_FIELDS = {"pp"}`).
4. **L4 — Diurnal correction** (`decay_apply.py:79` — `L4_FIELDS = {"ch", "cc"}`) — per-hour-of-day mean-zero residual.

Both whitelists severely narrowed since June: ws dropped 08-08 v0.6.397; pp dropped 07-04 v0.6.304; t/dp/h/pr/cl/sr/pa all stripped over July.

**L5, L6:** overloaded terms. L5 = solar-regime (Lsr). L6 = per-field regime overlays (cove t retired; Lc for clouds live).

## 14 correction fields — current state (2026-08-09)

| Field | L1 | L2 | L3 | L4 | Specialists |
|-------|----|----|----|----|-------------|
| t     | ✓  | ✓ exp τ=4h | — | — | L6 cove RETIRED (07-01) |
| dp    | derived | derived | — | — | dpbp LIVE (08-04); dprp shadow |
| h     | ✓  | ✓ soft_ramp | — | — | — |
| ws    | ✓  | ✓ wind blend | dropped 08-08 | — | wsbp HELD (calm n=0) |
| wg    | ✓  | ✓ wind blend | ✓ | — | wgrp shadow |
| wd    | ✓  | pre-gate carry (see [[project_wd_applied_layer_stamp_fix]]) | — | — | wdp LIVE (07-27) |
| pp    | ✓  | — | Brier-only | — | ppbp Stage 0 PROMOTE (frontal) |
| pr    | ✓  | ✓ octant | — | — | pr L2 regime-gate shadow |
| cc    | ✓  | — | — | ✓ | Lc LIVE but `_FIELD_SKIP`; Ccd derivation LIVE (07-30); MLC DORMANT |
| cl    | ✓  | ✓ hourly[0] lead 0 | — | — | Lc `_FIELD_SKIP`; clp Stage 3 shadow — READY FOR FLIP DECISION |
| cm    | ✓  | — | ✓ | — | Lc LIVE |
| ch    | ✓  | — | ✓ | ✓ | Lc LIVE; chp LIVE (07-19) |
| sr    | ✓  | — | — | — | Lsr LIVE (06-28); Lsb LIVE (08-05) |
| pa    | ✓  | — | — | — | — |

## `_FIELD_SKIP` (Lc bypass)

`cloud_saturation_correction.py:61` — `_FIELD_SKIP = frozenset({"cc", "cl"})`. Lc is LIVE globally but is bypassed for cc (Ccd owns composition) and cl (07-30 shift-table broke cl per [[project_lc_regime_conditional]]).

Sanity check at `analysis/runlog/build_executive_summary.py:770` flags prod_real divergence from raw for FIELD_SKIP fields (cc exempt). Verified clean 08-09: cl -1.4%.

## Data flow (per tick)

1. Collector fetch (WU, Tempest, KBVY, KBOS, NOAA, Pirate)
2. `hyperlocal.py::build_hyperlocal_data` — L2 aggregation
3. `corrected_hourly.py::add_corrected_hourly_arrays` — L2 apply
4. `decay_apply.py::apply_decay_corrections` — L3 + L4 (whitelist-gated) + wd sin/cos
5. Specialists apply in order (see `collector.py`): Lc → chp → clp → wdp → dpbp → Lsr/Lsb → Ccd
6. `forecast_snapshot.py` — capture all layers per hour (top-level = L2 per Fitter contract, [[feedback_top_level_forecast_is_l2]])
7. `forecast_error_log.py` — pair-log append with per-layer errors + applied_layer stamp
8. Fitter (`decay_fit.py`) every 6h EDT — writes `decay_corrections.json`

## Key GCS files
`weather_data.json`, `forecast_log.json`, `forecast_error_log.jsonl` (~1.1M pairs, 30d retention), `decay_corrections.json`, `mae_over_time.json` (canonical for debug page).

## Constants
- `LEAD_BINS = 48`, `DIURNAL_BINS = 24`
- `TAU_DAYS = 14`, `RETENTION_DAYS = 30`
- Caps: t/dp 5°F, h 20%, ws 10mph, wg 15mph, pp 25%, pr 0.30 inHg, cc 40%, sr 300 W/m², pa 0.20 in/hr, cl/cm/ch 40%, wd sin/cos 0.30
