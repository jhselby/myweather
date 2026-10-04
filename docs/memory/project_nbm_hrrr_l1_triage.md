---
name: nbm-hrrr-l1-triage
description: 2026-08-18 triage — NBM/HRRR beat Open-Meteo L1 on wg/sr/wd/t at 14-day scale. dp/cl/cm/ch correction stacks vindicated. L1 per-field router is the recovery.
metadata: 
  node_type: memory
  type: project
  originSessionId: 1ca38152-581f-428c-be01-d4c986490eb5
  modified: 2026-08-18T17:39:32.374Z
---

# NBM/HRRR vs current stack — 2026-08-18 triage

Session opened after v0.6.431 shipped NWS-gridpoint stamping. Backfilled NBM
and HRRR from S3 to run head-to-head instead of waiting 72h for organic
accumulation. Findings force a rethink of L1 for most fields.

## Data

- **NBM 14-day** cache: 2160 (run,lead) rows. `scratchpad/nbm_cache_wide.jsonl`
  (3 days, 12 fields) + `nbm_cache_narrow14.jsonl` (12 days prior, 4 fields).
  Nearest 2.5km cell: 42.5136N, −70.884W (1.6km NW of Wyman Cove).
- **HRRR 3-day** cache: `hrrr_cache.jsonl` (t/dp/ws/wd/wg/sr, Aug 15-17).
  14-day HRRR backfill launched 08-18; when done combine and re-run.
- Pair-log `run_time` is **America/New_York local**, not UTC. Convert before
  joining NBM (which is UTC). First-pass 4h offset made `t` look catastrophic;
  UTC-corrected in `enrich_pair_log*.py`.
- `pp` in pair log is Probability of Precipitation (0-100), not amount.
  NBM APCP mm/hr is not comparable — needs separate POP extract.

## Findings (14-day scale, halves-stable, vs current PRODUCTION)

| Field | Winner | Δ vs Prod | Verdict |
|---|---|---|---|
| **sr** | NBM (also HRRR won at 3d) | +20% (NBM), +32% (HRRR at 3d) | **PROMOTE** — swap L1 |
| **wg** | NBM | +16% | **PROMOTE** — swap L1 |
| **wd** | NBM | +11% | **PROMOTE** — swap L1 |
| ws | NBM | +3.5% (only +1.2% on earlier 12d) | HOLD — 3-day looked +14%, regime-flattered |
| t | HRRR (3-day only) | +14% (3d), 14d pending | HOLD until 14-day HRRR completes |
| dp | Prod | — (correction stack wins) | **KEEP** — dp chain is real signal |
| cl, cm, ch | Prod | -13% to -161% | **KEEP** — cloud-layer stacks vindicated |
| cc | HOLD | +21% but halves +59/-19 — one regime | Watch, don't touch |
| pa, pp | HOLD | marginal | Watch |

## Per-lead pattern (from 3-way 3-day)

- **At lead 1h**: production wins for t/dp/ws/wd/wg. Station-blend + short-lead
  correction has real value that no external model matches.
- **At lead ≥3h**: external models (NBM or HRRR) beat production.
- Implication: don't nuke the cascade. Replace L1 seed for the wrong fields,
  keep short-lead correction as-is.

## Recovery plan (draft — DO NOT ship without 14-day HRRR)

1. Confirm HRRR 14-day t/dp/sr numbers hold (backfill in flight 08-18).
2. Per-field L1 router in `weather_collector/processors/` — routes each field
   to its best source: HRRR for t/sr, NBM for ws/wd/wg. Leaves dp/cl/cm/ch on
   Open-Meteo current path.
3. Refit L2-L6 cascade against new-L1 residuals. Some layers may lose signal
   entirely (were cancelling OM bias, no real skill). Some may survive.
4. Re-run per-field prod evaluation. Prod-vs-NBM shrinks once cascade is
   refit against NBM.

## Caveats worth flagging before ANY ship

- Grid cell is 1.6km NW of Wyman Cove — verify not inland at Beverly city
  center for cloud numbers.
- NBM `GUST:10m` is instantaneous; our stack's `gust_mph` obs is Tempest
  rolling max. Verify timebase alignment for wg before shipping.
- HRRR wind is derived from UGRD/VGRD at 10m instant; NBM's WIND:10m is the
  blend's central estimate. Not identical semantics.
- cl/cm are assigned from NBM message ORDER (1st `TCDC:reserved`=low,
  2nd=mid). If NBM convention is reversed, labels swap. Since both KILL,
  verdict doesn't change.

## Files (scratchpad)

- `nbm_extract.py` / `nbm_extract_wide.py` — S3 range-fetch + cfgrib decode
- `nbm_backfill.py` / `nbm_backfill_wide.py` / `nbm_backfill_narrow14.py`
- `hrrr_extract.py` / `hrrr_backfill.py` / `hrrr_backfill_prior12.py`
- `enrich_pair_log.py` / `enrich_pair_log_wide.py` / `enrich_3way.py`
- `run_benchmark.py` / `run_benchmark_wide.py` / `run_benchmark_3way.py`
  / `run_benchmark_14d.py`

## What shipped 08-18 (v0.6.432)

- `weather_collector/processors/l1_router.py` — new. At leads ≥6h, replaces
  `hourly.corrected_temperature` / `wind_speed` / `wind_direction` with
  NWS-gridpoint (NBM-derived) values. Preserves pre-router array +
  per-hour source labels. Fall-through to cascade if NWS missing.
- `weather_collector/collector.py` — call site added right before
  `append_forecast_snapshot`.
- Version bumped to v0.6.432 (index.html + build.py auto-updated
  version.json + sw.js).
- Changelog entry added at top of `docs/CHANGELOG.md`.
- **NOT SHIPPED tonight**: wg, sr, dp router (need NBM grib ingester
  on the Cloud Function — phase 2). Cloud stack (cc/cl/cm/ch) NOT
  touched — production wins those.
- **Rollback**: `_ROUTER_ENABLED = False` in `l1_router.py`, redeploy.

## Definitive 14-day scoreboard (from `router_scoreboard.py`)

```
field    L1     L3     L6     L12    L18    L24
t        Prod   HRRR   NBM    NBM    NBM    NBM
dp       Prod   Prod   NBM    NBM    NBM    NBM
ws       Prod   NBM    NBM    NBM    NBM    NBM
wd       Prod   Prod   NBM    NBM    NBM    NBM
wg       Prod   NBM    NBM    NBM    NBM    NBM   ← phase 2
sr       HRRR   NBM    NBM    NBM    HRRR   NBM   ← phase 2
```

## Directive for next session

1. Verify shipped router is behaving on live pair log after 24-48h — pull
   pair-log rows, check `error_l4` at lead ≥6h for t/ws/wd approaches
   `error_nws`.
2. If shadow numbers hold: plan phase 2 (NBM grib ingester as a separate
   scheduled Cloud Function that writes point extracts to GCS every hour;
   collector reads them for wg and sr).
3. Investigation-survival triage (see above): cloud/pressure/short-lead
   work stands. Long-lead t/ws/wd correction fits become moot for the
   user-facing forecast, though Fitter will still emit coefficients.
