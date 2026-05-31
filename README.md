# Wyman Cove Weather

A hyperlocal weather PWA for Wyman Cove, Marblehead MA (42.5014, -70.8750). The app combines data from ~10 sources into a single dashboard tuned for one specific location — correcting for coastal microclimate, elevation, wind exposure, and harbor orientation.

## Architecture

The system has two independent pieces:

```
┌─────────────────────────────────────────────────────────┐
│                   Google Cloud (us-east1)                │
│                                                         │
│  Cloud Scheduler ──(every 10 min)──▶ Cloud Functions (Gen 2)  │
│                                      myweather-collector│
│                                           │             │
│                                           ▼             │
│                                    GCS Bucket           │
│                                    myweather-data/      │
│                                    weather_data.json    │
│                                    frost_log.json       │
└─────────────────────────────────────────────────────────┘
                                         │
                                    public fetch
                                         │
┌─────────────────────────────────────────────────────────┐
│                   GitHub Pages                          │
│                                                         │
│  PWA (index.html + js/ + styles/)                       │
│  fetches from:                                          │
│  storage.googleapis.com/myweather-data/weather_data.json│
└─────────────────────────────────────────────────────────┘
```

**The collector and the PWA share no infrastructure.** The collector writes JSON to a GCS bucket. The PWA reads it. They connect through a public URL and nothing else.

## Collector

The collector is a Python package (`weather_collector/`) deployed as a Google Cloud Function (Gen 2, which runs on Cloud Run under the hood). Cloud Scheduler triggers it via HTTP POST every 10 minutes, on the `:07` mark of each ten-minute slot (`:07`, `:17`, `:27`, etc.). A single run takes ~30–40 seconds.

### Entry point

`main.py` imports and exposes `run()` from `weather_collector/collector.py`. The Cloud Function runtime calls this on each trigger.

### Data sources

Fetchers live in `weather_collector/fetchers/`:

| Fetcher | Source | What it provides |
|---|---|---|
| `pirate_weather.py` | Pirate Weather API | Minutely precip, current solar irradiance, CAPE |
| `open_meteo.py` | Open-Meteo API | HRRR 48h + GFS 7-day forecasts, directional cloud sampling |
| `wu_scraper_realtime.py` | Weather Underground API | Up to 29 personal weather station readings for hyperlocal corrections |
| `tempest.py` | WeatherFlow Tempest API | Up to 9 Tempest stations within 1.5mi; lightning, solar, wind lull, wet bulb |
| `pws.py` | NWS/KBOS/KBVY/buoy | Nearby official station observations |
| `nws.py` | NWS API | Alerts + gridpoint forecast data (BOX/76,97) |
| `noaa.py` | NOAA CO-OPS | Tide predictions and water temperature |
| `tides.py` | NOAA tides | Detailed tide data for station 8442645 |
| `salem_water.py` | Salem Water dept | Salem Sound water temperature |
| `ebird.py` | eBird API | Recent/notable bird sightings within 5 km |
| `briefing_ai.py` | Google Gemini API | AI-generated briefing headline and subheadline |

### Processors

Processors live in `weather_collector/processors/` and compute derived scores from raw fetcher data:

- **Correction pipeline:** `hyperlocal.py` (Layer 1 — temperature/humidity weighted-average corrections from WU + Tempest), `station_bias.py` (per-station Kalman bias tracking, 48h rolling window), `wind_blend.py` (Layer 2 — 24h linear blend of observed wind into the forecast), `corrected_hourly.py` (assembles the bias-corrected hourly arrays the frontend reads)
- **Decay pipeline (Layer 3):** `forecast_snapshot.py` (logs the corrected 48h forecast every tick, 14-day rolling), `forecast_error_log.py` (pairs every observation against every snapshot that predicted its hour, appends to GCS via compose), `decay_fit.py` (daily fit of mean error per `(field, lead_h)` bin), `decay_apply.py` (subtracts the fitted residual from the live forecast)
- **Derived scores + detectors:** `wind_risk.py`, `fog.py`, `fog_metrics.py`, `frost.py`, `sunset_directional.py`, `sea_breeze.py`, `pressure.py`, `wet_bulb.py`, `precip_surface.py`, `precip_850mb.py`, `trough.py`, `thunderstorm.py`, `daily_extremes.py`, `current_derived.py`, `forecast_text.py`
- **Helpers:** `normalize.py`, `hourly_7day.py`, `hourly_trim.py`

### Output

The collector assembles everything into a single `weather_data.json` (~400 KB) and uploads it to the `myweather-data` GCS bucket. Several auxiliary files in the same bucket support the correction pipelines:

- `frost_log.json` — rolling frost-event log
- `station_history.json` — 48h rolling per-station bias history (Layer 1)
- `obs_temp_log.json` — 24h rolling observation log
- `forecast_log.json` — 48h corrected forecast snapshots, 14-day rolling (Layer 3, Piece 1)
- `forecast_error_log.jsonl` — matched forecast-vs-observed pairs, 30-day rolling (Layer 3, Piece 2)
- `forecast_error_state.json` — Joiner watermark
- `decay_corrections.json` — fitted decay lookup table, rewritten daily (Layer 3, Piece 3)

### Environment variables

The collector reads API keys from environment variables (set in the Cloud Function (Gen 2) configuration):

- `PIRATE_WEATHER_API_KEY`
- `WU_API_KEY`
- `EBIRD_API_KEY`
- `GEMINI_API_KEY`
- `GOOGLE_CLOUD_PROJECT`

These are **not** in the source code. They are set at deploy time.

## PWA

The frontend is a single-page app served by GitHub Pages at [wymancove.com](https://wymancove.com). Rendering logic is split across `index.html` and ~30 JS modules in `js/` (`app-main.js` is the entry point + data loader; each card/concern lives in its own file — `right_now.js`, `briefing.js`, `wind.js`, `corrections.js`, `alarms.js`, `alerts.js`, `theme.js`, `format.js`, `version_check.js`, `pull_refresh.js`, etc.). Styles are in `styles/`. Vanilla JS, no framework.

On load and every 10 minutes, the PWA fetches `weather_data.json` from:

```
https://data.wymancove.com/weather_data.json
```

(Cloudflare CDN in front of the GCS bucket; the raw GCS URL `https://storage.googleapis.com/myweather-data/weather_data.json` also works.)

It also re-fetches when the app resumes from background.

### Debug page

A separate page at [wymancove.com/corrections_debug.html](https://wymancove.com/corrections_debug.html) renders three views of the correction pipelines: the fitted decay curves (Layer 3 output), the live forecast with vs without decay correction, and a per-station bias map showing every WU/Tempest station as a circle colored by its current chronic offset. Not linked from the PWA — debug-only.

### Build step

Before committing frontend changes, run:

```bash
python3 build.py
```

This hashes local JS/CSS files for cache busting.

## Deployment

### Collector (Python → Google Cloud)

```bash
make deploy-collector
```

This runs `gcloud functions deploy --gen2`. After deploying, trigger a manual run to verify:

```bash
make run-collector
```

Check logs:

```bash
make logs
```

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
