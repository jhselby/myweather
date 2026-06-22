# Third-Party Licenses & Attributions

MyWeather is a hobby project and not for commercial use. This page credits every third-party library, API, and data source the app relies on, and includes the attribution language requested by sources whose terms of service ask for it.

## Client-Side Libraries

### SunCalc 1.9.0
- **Author:** Vladimir Agafonkin
- **License:** BSD-2-Clause
- **URL:** https://github.com/mourner/suncalc
- **Use:** Sun and moon position, sunrise/sunset/twilight calculations.

### Leaflet 1.9.4
- **Author:** Volodymyr Agafonkin
- **License:** BSD-2-Clause
- **URL:** https://github.com/Leaflet/Leaflet
- **Use:** Radar tab map rendering.

### Chart.js 4.4.4
- **Author:** Chart.js Contributors
- **License:** MIT
- **URL:** https://github.com/chartjs/Chart.js
- **Use:** Forecast charts (temperature, wind, precipitation), corrections debug page.

### VSOP87 (truncated series)
- **License:** Public domain algorithm; truncated implementation reproduced in `js/almanac.js`.
- **Use:** Client-side planetary positions for the Solar System card. Truncated series gives roughly 1° accuracy — fine for "where is Jupiter tonight" visualization.

## Map Tiles

### CartoDB Dark Matter basemap
- **Provider:** Carto (https://carto.com)
- **Underlying data:** © OpenStreetMap contributors
- **License:** Tiles free for non-commercial use; attribution required.
- **Required attribution:** "© OpenStreetMap contributors © CARTO"
- **Use:** Radar tab basemap.

### IEM NEXRAD radar tiles
- **Provider:** Iowa Environmental Mesonet (https://mesonet.agron.iastate.edu)
- **Data source:** NOAA NEXRAD base reflectivity composite
- **License:** NOAA data is public domain; IEM provides the tile service.
- **Preferred credit:** "Radar via Iowa Environmental Mesonet / NOAA NEXRAD"
- **Use:** Radar overlay (5-minute archive composites).

## Weather Data APIs

### Open-Meteo (HRRR + GFS + ECMWF)
- **Provider:** https://open-meteo.com
- **License:** CC-BY-4.0
- **Required attribution:** "Weather data by Open-Meteo.com"
- **Use:** Primary forecast model (HRRR 48h hourly + GFS 7-day + ECMWF 10-day daily), cloud-layer splits for sunset quality.

### Pirate Weather
- **Provider:** https://pirateweather.net
- **License:** Paid API key (subscription).
- **Attribution:** Not required for paid tier.
- **Use:** Next-60-minute precipitation (minutely), CAPE for the thunderstorm detector, solar radiation cross-reference.

### NOAA / National Weather Service
- **Provider:** https://www.weather.gov, https://api.weather.gov
- **License:** Public domain (NOAA / US Federal).
- **Use:** Gridpoint forecasts (BOX/76,97), active alerts.

### NOAA AviationWeather.gov (METAR)
- **Provider:** https://aviationweather.gov
- **License:** Public domain.
- **Use:** KBOS Boston Logan and KBVY Beverly METAR observations — temperature, wind, pressure, cloud cover, cloud layer altitudes.

### NOAA NDBC (Buoy 44013)
- **Provider:** https://www.ndbc.noaa.gov
- **License:** Public domain.
- **Use:** Boston Buoy (16 mi ENE) water temperature, wave height, offshore wind as a fallback reference.

### NOAA CO-OPS (Tides)
- **Provider:** https://api.tidesandcurrents.noaa.gov
- **License:** Public domain.
- **Use:** Salem Harbor tide predictions (station 8442645) for the Dock Day Score and tide-aware analysis.

### NOAA GoMOFS (Gulf of Maine Operational Forecast)
- **Provider:** https://nomads.ncep.noaa.gov
- **License:** Public domain.
- **Use:** Salem Channel water temperature near-surface (regulargrid ny=401, nx=103, depth=0m).

### Weather Underground
- **Provider:** https://www.wunderground.com
- **License:** Personal Weather Station data accessed via WU API with key.
- **Attribution:** "Powered by Weather Underground" (per WU TOS).
- **Use:** The 41-station personal weather station mesonet that feeds the L2 Kalman blend.

### WeatherFlow Tempest (public stations)
- **Provider:** https://tempestwx.com
- **License:** Public station data accessed via the tempestwx.com web API.
- **Attribution:** "Includes WeatherFlow Tempest public station data" (courtesy).
- **Use:** 20 nearby Tempest stations for the mesonet — lightning detection (close-strike distance + count), solar radiation, wind lull, wet bulb.

## Other Data Sources

### eBird (Cornell Lab of Ornithology)
- **Provider:** https://ebird.org
- **License:** Free for non-commercial use; attribution required.
- **Required attribution:** "Bird observations via eBird (Cornell Lab of Ornithology)"
- **Use:** Recent and notable bird sightings near Marblehead on the Birds card.

## AI Services

### Groq
- **Provider:** https://groq.com
- **License:** Free tier API.
- **Attribution:** Not required.
- **Use:** Briefing headline generation waterfall: `openai/gpt-oss-120b` → `llama-3.3-70b-versatile`.

### Google Gemini
- **Provider:** https://ai.google.dev
- **License:** Free tier API.
- **Attribution:** Not required.
- **Use:** Currently disabled (`GEMINI_ENABLED = False`). Was the briefing source until v0.6.133 when free-tier quota proved too tight for our 10-min tick cadence.

## MyWeather Itself

This codebase is private and not licensed for redistribution. The repository at https://github.com/jhselby/myweather is mirrored for backup and Cloud Function deploy via GitHub Pages, not as an invitation to fork.
