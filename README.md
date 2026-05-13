# Wyman Cove Weather

A hyperlocal weather PWA for Wyman Cove, Marblehead MA (42.5014, -70.8750). The app combines data from ~10 sources into a single dashboard tuned for one specific location — correcting for coastal microclimate, elevation, wind exposure, and harbor orientation.

## Architecture

The system has two independent pieces:

```
┌─────────────────────────────────────────────────────────┐
│                   Google Cloud (us-east1)                │
│                                                         │
│  Cloud Scheduler ──(every 10 min)──▶ Cloud Run Service  │
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

The collector is a Python package (`weather_collector/`) deployed as a Google Cloud Run service. Cloud Scheduler triggers it via HTTP POST every 10 minutes. A single run takes ~30–40 seconds.

### Entry point

`main.py` imports and exposes `run()` from `weather_collector/collector.py`. Cloud Run calls this on each trigger.

### Data sources

Fetchers live in `weather_collector/fetchers/`:

| Fetcher | Source | What it provides |
|---|---|---|
| `pirate_weather.py` | Pirate Weather API | Minutely precip, current solar irradiance, CAPE |
| `open_meteo.py` | Open-Meteo API | HRRR 48h + ECMWF 10-day forecasts, directional cloud sampling |
| `wu_scraper_realtime.py` | Weather Underground API | 29 personal weather station readings for hyperlocal corrections |
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

`hyperlocal.py` (temperature/humidity corrections from WU + Tempest station network), `station_bias.py` (per-station Kalman bias tracking), `wind_risk.py`, `fog.py`, `frost.py`, `sunset_directional.py`, `sea_breeze.py`, `pressure.py`, `wet_bulb.py`, `precip_surface.py`, `precip_850mb.py`, `trough.py`, `forecast_text.py`

### Output

The collector assembles everything into a single `weather_data.json` (~375 KB) and uploads it to the `myweather-data` GCS bucket. A `frost_log.json` is also maintained in the same bucket as a running log.

### Environment variables

The collector reads API keys from environment variables (set in the Cloud Run service configuration):

- `PIRATE_WEATHER_API_KEY`
- `WU_API_KEY`
- `EBIRD_API_KEY`
- `GEMINI_API_KEY`
- `GOOGLE_CLOUD_PROJECT`

These are **not** in the source code. They are set at deploy time.

## PWA

The frontend is a single-page app served by GitHub Pages. Rendering logic is split across `index.html` and ~20 JS modules in `js/` (app-main.js, briefing.js, wind.js, forecast.js, etc.). Styles are in `styles/`.

On load and every 10 minutes, the PWA fetches `weather_data.json` from:

```
https://storage.googleapis.com/myweather-data/weather_data.json
```

It also re-fetches when the app resumes from background.

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

This runs `gcloud functions deploy --gen2`, which deploys to Cloud Run. After deploying, trigger a manual run to verify:

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

The collector is not designed to run locally. It depends on Google Cloud credentials for GCS access. All development and testing happens through deploy → trigger → check logs.

The PWA can be previewed locally by opening `index.html` in a browser. It will fetch live data from GCS.
