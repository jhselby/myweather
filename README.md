# Wyman Cove Weather

A hyperlocal weather PWA for Wyman Cove, Marblehead MA (42.5014, -70.8750). The app combines data from ~12 sources into a single dashboard tuned for one specific location — correcting for coastal microclimate, elevation, wind exposure, and harbor orientation.

## Architecture

Five Google Cloud Functions, one GCS bucket, one static site. They share nothing but files in `gs://myweather-data/`.

```
                 Google Cloud (us-east1)
  ┌──────────────────────────────────────────────────────────┐
  │  myweather-nbm-ingest  (hourly) ──▶ nbm_point_extract.json │
  │  myweather-collector   (every 10 min, :07 marks)           │
  │       reads APIs + NBM extract + tables                    │
  │       writes weather_data.json, forecast log, pair log     │
  │  myweather-refitter    (04:30 ET) ──▶ runtime_tables/      │
  │  myweather-publisher   (hourly)   ──▶ mae_over_time.json,  │
  │                                       backstamped pair log │
  │  myweather-nbm-backfill (one-shot) ──▶ nbm_backfill/       │
  │                                                            │
  │                 GCS bucket myweather-data/                 │
  └──────────────────────────────────────────────────────────┘
                              │ public fetch
  ┌──────────────────────────────────────────────────────────┐
  │  GitHub Pages: PWA (index.html + js/ + styles/)            │
  │  + corrections_debug.html                                  │
  └──────────────────────────────────────────────────────────┘
```

The loop: the collector serves a corrected forecast every 10 minutes, saves every forecast it makes, and pairs each new observation against every earlier forecast for that hour (the pair log). The pair log refits the tables the collector reads: the in-collector Fitter twice a day, and the Refitter every morning.

| Function | Schedule | Writes | Deploy |
|---|---|---|---|
| `myweather-collector` | every 10 min | `weather_data.json`, `forecast_log.json`, `forecast_error_log.jsonl`, station/obs logs; Fitter tables at 03:07 and 15:07 | `make deploy-collector` |
| `myweather-nbm-ingest` | hourly | `nbm_point_extract.json` (NBM at the cove, leads 1–47) | `make deploy-nbm-ingester` |
| `myweather-refitter` | 04:30 ET | `runtime_tables/` (10 self-refit tables, `history/`, `_status.json`) | `make deploy-refitter` |
| `myweather-publisher` | hourly | `forecast_error_log_backstamped.jsonl`, `mae_over_time.json` and other debug-page rollups | `make deploy-publisher` |
| `myweather-nbm-backfill` | by hand | `nbm_backfill/` | `make deploy-nbm-backfill` |

The repo copies of the 10 refitter tables (`weather_collector/data/*_curated.json`) are fallbacks; the collector uses the `runtime_tables/` copies. The Mac digest (`analysis/runlog/run_digest.sh`) still rewrites the repo copies, which is why `git status` usually shows them modified. Ship-decision tables (skip tables, selector IMS cells, static-blend cells) are bundled with the deploy and change only when you ship.

## Collector

The collector is a Python package (`weather_collector/`) deployed as a Google Cloud Function (Gen 2). Cloud Scheduler triggers it every 10 minutes on the `:07` mark of each slot. `main.py` exposes `run()` from `weather_collector/collector.py`.

### Data sources

Fetchers live in `weather_collector/fetchers/` and run in parallel via `fetch_all.py`:

| Fetcher | Source | What it provides |
|---|---|---|
| `open_meteo.py` | Open-Meteo API | HRRR 48h + GFS 7-day forecasts, directional cloud sampling |
| `nbm_point.py` | `nbm_point_extract.json` (from the ingester) | NBM forecast at the cove, leads 1–47 |
| `pirate_weather.py` | Pirate Weather API | Minutely precip, current solar irradiance, CAPE |
| `wu_scraper_realtime.py` | Weather Underground API | 41 personal weather stations for the L2 station network |
| `tempest.py` | WeatherFlow Tempest API | 19 Tempest stations; lightning, solar, wind lull, wet bulb |
| `pws.py` | NWS/KBOS/KBVY/buoy | Official station observations and METAR sky cover |
| `nws.py` | NWS API | Alerts + gridpoint forecast data (BOX/76,97) |
| `noaa.py`, `tides.py` | NOAA CO-OPS | Tide predictions and water temperature (station 8442645) |
| `salem_water.py` | GoMOFS | Salem Channel water temperature |
| `ebird.py` | eBird API | Recent/notable bird sightings within 5 km |
| `briefing_ai.py` | Groq API | Briefing headline: `gpt-oss-120b`, fallback `llama-3.3-70b-versatile`, then a template. Gemini code remains but is disabled (`GEMINI_ENABLED = False`). |

### Correction stack

Two cascades run side by side, then a selector picks one per field, regime and lead band.

- **HRRR side:** L1 raw → L2 live-observation corrections (`hyperlocal.py` + `station_bias.py` station network with 48h Kalman bias, `wind_blend.py` 4h wind fade-in, `cloud_obs_blend.py` METAR cloud at hour 0, applied forward by `corrected_hourly.py`) → L3 per-lead error table and L4 hour-of-day table (`decay_apply.py`, `wg` and `ch` only, with a regime × band skip table) → specialists (Lsr, Lsb, Lc, Ccd, chp, wgrp, dpbp, wdp live; others shadow or off).
- **NBM side:** raw NBM → L2_nbm (same observations, anchored to NBM) → L3_nbm (`wg`, `ch`, `sr`, `wd`, with its own skip table) → L4_nbm (`ch`) → wdp_nbm.
- **Selector** (`l1_selector.py`, called from `forecast_snapshot.py`): first rule with an answer wins — HRRR morning-overshoot rule, learned GBM (sr, 2 cells), inter-model spread rule (ch + one h cell), by-regime walker, pooled per-band table, default HRRR. An L1 static blend (h, 2 cells) overrides the pick. The chosen values are written back into the arrays the app reads.
- **Regimes** come from `regime_classifier.py` (11 labels) and are stamped by `state_stamp.py`.
- `cl`, `cm`, `pr`, `pp`, `pa` are HRRR-only; NBM doesn't provide them.

The live state of every module is reported by its `describe_applicability()` and rendered on the debug page's applicability map.

### Learning loop

- `forecast_snapshot.py` logs every layer of every forecast each tick (`forecast_log.json`, 14 days).
- `forecast_error_log.py` (the joiner) pairs each observation with every snapshot that forecast its hour and appends rows to `forecast_error_log.jsonl` (30 days). Rows carry per-layer errors, `applied_layer`, `selector_source`/`selector_mechanism`, shadow stamps and regime stamps.
- `decay_fit.py` (the Fitter) rewrites the L3/L4 tables at 03:07 and 15:07.
- `myweather-refitter` refits the selector tables, NBM L3/L4 tables, learned GBM and other self-refit tables daily.

### Derived products

`wind_risk.py`, `fog.py`, `fog_metrics.py`, `frost.py`, `sunset_directional.py`, `sea_breeze.py`, `pressure.py`, `wet_bulb.py`, `precip_surface.py`, `precip_850mb.py`, `trough.py`, `thunderstorm.py`, `frontal_detection.py`, `daily_extremes.py`, `current_derived.py`, `forecast_text.py`. Helpers: `normalize.py`, `hourly_7day.py`, `hourly_trim.py`, `current_from_hourly.py`; `weather_collector/stale_cache.py` fills failed sources from the previous payload.

### Output

The collector writes `weather_data.json` to the `myweather-data` bucket. Other files in the bucket:

| File | Written by | Holds |
|---|---|---|
| `nbm_point_extract.json` | NBM ingester | Latest NBM cycle at the cove |
| `forecast_log.json` | collector | Every snapshot with every layer, 14 days |
| `forecast_error_log.jsonl` | collector (joiner) | The pair log, 30 days |
| `forecast_error_log_backstamped.jsonl` | publisher | Pair log with NBM layers recomputed for older rows |
| `decay_corrections.json`, `diurnal_corrections.json` | Fitter | L3 and L4 tables |
| `runtime_tables/` | Refitter | 10 self-refit tables, `history/`, `state/`, `_status.json` |
| `station_history.json` | collector | 48h per-station bias history for the Kalman filter |
| `obs_temp_log.json` | collector | 24h of observed conditions |
| `mae_over_time.json` | publisher | Debug page accuracy series (raw, prod, prod_real) |
| `frost_log.json` and other small state files | collector | Rolling state for individual modules |

### Environment variables

Set in the Cloud Function configuration, never in source: `PIRATE_WEATHER_API_KEY`, `WU_API_KEY`, `EBIRD_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY` (still read at import), `GOOGLE_CLOUD_PROJECT`.

## PWA

The frontend is a single-page app served by GitHub Pages at [wymancove.com](https://wymancove.com). Rendering logic is split across `index.html` and ~30 JS modules in `js/` (`app-main.js` is the entry point + data loader; each card/concern lives in its own file — `right_now.js`, `briefing.js`, `wind.js`, `corrections.js`, `alarms.js`, `alerts.js`, `theme.js`, `format.js`, `version_check.js`, `pull_refresh.js`, etc.). Styles are in `styles/`. Vanilla JS, no framework.

On load and every 10 minutes, the PWA fetches `weather_data.json` from:

```
https://data.wymancove.com/weather_data.json
```

(Cloudflare CDN in front of the GCS bucket; the raw GCS URL `https://storage.googleapis.com/myweather-data/weather_data.json` also works.)

It also re-fetches when the app resumes from background.

### Debug page

A separate page at [wymancove.com/corrections_debug.html](https://wymancove.com/corrections_debug.html) renders the correction pipelines: the applicability map (what each module covers and whether it fires), one section per layer (L1 with the selector, L2 station network, L3, L4, Lsr, Lc), accuracy series from `mae_over_time.json`, and research and archive sections. Not linked from the PWA — debug-only.

### Build step

Before committing frontend changes, run:

```bash
python3 build.py
```

This hashes local JS/CSS files for cache busting.

## Deployment

### Cloud Functions (Python → Google Cloud)

```bash
make deploy-collector
make deploy-nbm-ingester
make deploy-refitter
make deploy-publisher
```

Each runs `gcloud functions deploy --gen2`. Check logs with `make logs` (collector), `make logs-refitter`, `make logs-publisher`, `make logs-nbm-ingester`. If both collector and frontend change, deploy the collector first, verify the data in GCS, then push the frontend.

### PWA (HTML/JS/CSS → GitHub Pages)

```bash
python3 build.py
git add -A
git commit -m "description of change"
git push
```

**Never stage `weather_data.json` or `frost_log.json`** — these are collector outputs, not source files. They should not be in git.

## Local development

The collector is normally exercised through deploy → trigger → check logs, since most of it depends on Google Cloud credentials for GCS access. For one-offs there is `make run-local`, which sources `.env` and invokes `weather_collector.collector.run` directly — useful for triggering, say, a manual Fitter pass off-schedule.

The PWA can be previewed locally by opening `index.html` in a browser. It fetches live data from `data.wymancove.com` either way.

## Analysis

`analysis/` contains standalone scripts that touch no production code. `analysis/tide_hypothesis.py` downloads `forecast_log.json` plus NOAA tide harmonic predictions, synthesizes forecast-vs-observed pairs by treating each snapshot's `lead_h=0` entry as the observation for its run hour, bins errors by M2 tide phase, and tests whether forecast bias correlates with tide. Run with `python3 analysis/tide_hypothesis.py`. Output is PNGs in `analysis/output/` (not committed).
