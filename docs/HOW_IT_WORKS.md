# How It Works

MyWeather is a hyperlocal weather app built for a specific location: Wyman Cove in Marblehead, Massachusetts. Every number you see has been processed through a pipeline designed to answer one question: what is the weather actually doing here, right now?

The system runs in two places. A Python collector on Google Cloud Functions fires every ten minutes, pulls from ten external sources, runs every value through three layers of correction, and writes a single JSON payload to a public Google Cloud Storage bucket. A vanilla-JS progressive web app at wymancove.com reads that payload from GitHub Pages and renders it. The two halves share no infrastructure — they connect through a public URL and nothing else.

---

## Data Sources

Ten external sources feed in every ten minutes.

**Open-Meteo** is the model backbone — HRRR for the next 48 hours and GFS for days 3 through 7. These are the same numerical weather prediction models professional forecasters use. They're excellent at large-scale patterns but their grid cells are kilometers wide, too coarse to resolve the microclimate at the water's edge.

**Pirate Weather** provides the only reliable minutely precipitation forecast (the next hour, by the minute), plus solar radiation, lightning probability, and atmospheric instability (CAPE) that Open-Meteo doesn't expose.

**Weather Underground** provides observations from up to 29 personal weather stations within 1.5 miles of the cove. These are hobbyist sensors — quality varies wildly. The system measures and corrects for each station's individual drift (see Calibration, below).

**Up to nine Tempest stations** within 1.5 miles contribute higher-quality observations. Tempest's sensor architecture is more consistent than typical WU stations and generally has lower drift.

**KBVY** (Beverly Municipal Airport), 6.3 miles northwest, provides certified ASOS observations — the same instrument-grade sensors used by the FAA and the National Weather Service. KBVY is the wind floor and a calibration anchor for the local station network.

**KBOS** (Logan Airport) contributes pressure observations. Logan's barometers are among the most reliable in the region.

**NWS gridpoints** at BOX/76,97 provide additional forecast detail (cloud, mixing height, fire weather) and active weather alerts.

**NOAA's Gulf of Maine Operational Forecast System (GoMOFS)** provides water temperature from a grid point in Salem Channel, about 1.5 miles from the dock. Far more accurate for local water temperature than the NDBC buoy 16 miles offshore.

**NOAA CO-OPS** (station 8442645, Salem) provides tide harmonic predictions used for the tides card and water-level overlays.

**eBird** provides bird observations from a 5 km radius, looking back 48 hours, refreshed every 10 minutes.

**Google Gemini 2.5 Flash** generates the briefing headline and subheadline once every 30 minutes. Groq (Llama 3.3 70B) is the fallback when Gemini fails.

---

## The Four Correction Layers

Every numeric forecast you see in the app — temperature, humidity, wind, dew point, gust, precipitation probability — has been through up to four layers of work. Understanding all four makes everything else easier to read.

**Layer 1 — Raw model (HRRR / GFS).**
The starting point. The Open-Meteo HRRR model gives a 48-hour forecast on a multi-kilometer grid; GFS extends days 3–7. Neither knows anything about Wyman Cove specifically. Every other layer is correcting what these two get wrong locally.

**Layer 2 — Station observations correct the model (current hour, all forecast hours).**
The 38 local stations contribute to a weighted average based on distance (closer matters more, inverse-square) and elevation (similar height to the cove's 30 ft matters more than rooftop sensors). The difference between this corrected local consensus and the raw model gives a single bias value per field. A Kalman gain (0.40 / 0.65 / 0.90 depending on how many stations agree, and by how much) decides how much of that bias to actually apply: 90% when 33 stations agree within 1 °F, less when the network is noisy. The result is `corrected_temperature`, `corrected_humidity`, etc. — the same flat correction is added to every forecast hour out to 48h. Wind is a special case under Layer 2: averaging 38 stations is meaningless because wind varies too much over short distances, so the system takes the maximum gust observed by any local station and blends it into the next 24 hours of the model on a linear decay (100% observed at hour 0, model-only by hour 24). Same concept — trust local observations over the model — just a different aggregation method for a different physical quantity.

**Layer 3 — Adaptive station calibration (runs upstream of Layer 2 to make station data trustworthy).**
Layer 2 only works if the station data itself is reliable, and personal weather stations drift. A sensor on a south-facing rooftop reads warm in summer. One in a shaded garden runs cold. Layer 3 tracks each station's chronic offset over a 48-hour rolling window using a leave-one-out technique: every run, each station's reading is compared against the weighted consensus of all its neighbors. A station that consistently reads 2.7 °F warmer than everyone else gets that offset subtracted before it contributes to the Layer 2 correction. This runs separately for day and night, since a sensor shaded in the afternoon may be accurate at midnight. Layer 3 runs *before* Layer 2 in execution order, but it's a distinct concept worth naming separately — Layer 2 is "how do we use stations to correct the model," Layer 3 is "how do we know which station readings to trust."

**Layer 4 — Lead-time decay correction (forecast hours 0–47).**
The newest layer. Layers 2 and 3 correct for "the model is biased right now"; Layer 4 corrects for "the model's bias changes the further out you forecast." The system measures its own past forecast errors by snapshot-versus-observation comparison, fits a recency-weighted mean error per (field, lead-hour) bin (exponential decay, τ=14 days), and subtracts that residual from every forecast hour. At lead 0 the correction is near zero (Layers 2 and 3 have already done their work); at lead 36h the correction can be 5–15 mph on gust, 12% on humidity, 1–2 °F on temperature.

The four layers don't fight each other. Layer 1 is raw input; Layer 3 calibrates the data Layer 2 will consume; Layer 2 anchors the current hour to local truth; Layer 4 removes systematic lead-time error from everything downstream. Each is measured against post-prior-layer values, so the stack doesn't double-count.

---

## The Decay-Curve Pipeline (Layer 4 in detail)

Layer 4 is built from four pieces that run inside the collector. None of them are visible to the user directly, but they're worth understanding because they're the part of the system that gets *better over time*.

**Piece 1 — Logger.** Every 10-minute tick, the collector saves a snapshot of the corrected 48-hour forecast to `forecast_log.json` in GCS. The snapshot has the post-Layer-1 / post-Layer-2 values — temperature, dew point, humidity, wind, gust, and precipitation probability — for each of the next 48 hours. A 14-day rolling window of these snapshots is kept (~600 snapshots at steady state).

**Piece 2 — Joiner.** Every tick, the collector also pairs every recent observation against every snapshot whose forecast covered that hour. One row per (observation × snapshot × field) triple, with the forecast value, the observed value, the lead time, and the error (forecast − observed). The rows are appended to `forecast_error_log.jsonl` via GCS compose (server-side stitch, constant cost regardless of file size). At steady state this file is ~1.3 GB containing about 7.5 million pairs across 30 days.

**Piece 3 — Fitter.** Once a day, at 3:07 AM Eastern, the collector reads the full pair log, groups by (field, lead-hour), and computes a **recency-weighted** mean error per bin. Each pair contributes a weight of `exp(-age_days / 14)` — fresh pairs full weight, week-old pairs half-weight, three-week-old pairs about 12%. This lets the fit track seasonal transitions (spring→summer, fall onset) and recover faster when upstream data quality changes. The result is `decay_corrections.json` — a small lookup table of 6 fields × 48 lead-hour bins. Same pass also prunes the pair log to the 30-day window and rewrites it as a single non-composed blob.

**Piece 4 — Apply.** Every tick, after the main payload is built, the collector reads `decay_corrections.json` and subtracts each lead's mean error from the corresponding hour of the corrected forecast arrays. Per-field sanity caps (5 °F for temp, 10 mph for wind, etc.) prevent any pathological future fit from blowing up the user-facing forecast. If the corrections file is missing or older than 7 days, Apply quietly skips — the payload falls back cleanly to Layers 1 and 2 only.

You can see all of this — the fitted curves, the live forecast with and without decay, and the per-station bias offsets on a map — at `wymancove.com/corrections_debug.html`.

---

## Temperature

Layer 1 (HRRR raw) → Layer 2 (Kalman-blended station-network bias, calibrated by Layer 3) → Layer 4 (lead-time decay correction). The current-hour display reads `corrected_temperature[0]`. Forecast hours read the rest of the array. Daily high and low are not the model's forecast — they're computed from a hybrid of observed and forecast: each tick logs the corrected local temperature, and the daily high is the max of all observed temperatures so far today plus the corrected forecast temperatures for the remaining hours. As the day progresses, observations replace forecast values, so the high and low end the day reflecting what actually happened.

## Humidity and Dew Point

Same pipeline as temperature: Layer 2 station-network correction (separately tracked humidity bias, with Layer 3 station calibration upstream), then Layer 4 lead-time correction. Marine air is consistently more humid than model grids suggest — the Layer 2 correction regularly adds 4–6% RH. Dew point is computed from the corrected temperature and corrected humidity via the Magnus formula, and gets its own independent Layer 4 correction on top.

## Wind and Gusts

Current observed wind is the maximum of all fresh local readings (WU stations < 20 min old, Tempest < 20 min old, KBVY METAR, and the model as a floor). A sanity cap fires if the chosen value is more than 2.5× the WU network aggregate, which usually means a single bad sensor is spiking. Wind direction prefers the highest-gust *waterfront* Tempest station, falling back to whatever the max-gust source reports.

For the 48-hour forecast: Layer 2 wind blend (24-hour linear blend from observed toward model) → Layer 4 (lead-time decay correction). At hour 0 the displayed wind is essentially the observation. By hour 24 the blend has faded out and only the model + decay correction remain.

## Wind Impact Score

A 20 mph south wind is barely felt at the dock — Marblehead and local terrain block it almost completely. The same speed from the north or northwest, with open harbor exposure, is a completely different experience. The wind impact score multiplies wind speed by a directional exposure factor between 0 and 1, drawn from a 16-direction lookup table tuned for Wyman Cove. The 7-day forecast text uses this score to decide between "windy at the cove" and "calm at the cove despite regional gusts."

## Feels Like

Uses the Steadman Australian Apparent Temperature formula, which combines temperature, humidity, and wind speed. On days with direct sunlight, a solar radiation term is added. The card on the Weather tab shows the shade value as primary and the full-sun value as secondary when they differ by more than 5 °F. All inputs are corrected values; recalculated for every hour of the 48-hour forecast.

## Wet Bulb Temperature

The lowest temperature achievable by evaporative cooling, calculated from corrected temperature and corrected humidity via Stull's psychrometric equation. More relevant than heat index for assessing humid-heat stress, and more honest than feels-like for outdoor athletic limits.

## Pressure

Weighted station average with per-station bias correction, falling back to KBOS (Logan) if station data isn't available, and to the model as a last resort. Pressure doesn't vary much over 1.5 miles — the correction is mostly about sensor calibration. A separate pressure-trend analyzer classifies the 3-hour trend into an alarm level (steady / falling / rapidly falling) that drives the storm-warning indicators.

## Fog, Sea Breeze, Thunderstorm

Three independent detectors run every tick and feed the "Watch For" rows on the Briefing tab. Fog metrics produce a current risk plus an 18-hour probability array with a dissipation hour. The sea-breeze detector looks for the land-water temperature differential, wind direction, and synoptic-pattern signatures that produce a sea breeze, with hard vetoes when wind is wrong-direction or too strong. The thunderstorm detector combines CAPE (from Pirate Weather), lightning observations, and the model's instability fields.

## Daily High and Low

Today's high and low are a hybrid: max of all observed corrected temperatures logged this 24-hour day, combined with the corrected forecast for the remaining hours. Yesterday's high, peak gust, and total precipitation come from the rolling observation log. Tomorrow's high and low are forecast-only.

## Water Temperature

From NOAA's Gulf of Maine Operational Forecast System — a dedicated ocean circulation model with a grid point in Salem Channel (ny=401, nx=103), 1.5 miles from the dock. The model runs four times a day with 72-hour forecasts. Significantly more accurate than buoy 44013 sixteen miles offshore, which runs 2–5 °F colder than local inshore water in summer due to upwelling and distance.

## Tides

Harmonic predictions from NOAA station 8442645 (Salem) — high/low times and heights plus an interpolated curve for the Day Plan and Dock Day cards. The tides card shows today, tomorrow, and the day after, with a 72-hour graph annotated for the next event.

## Dock Day Score

Predicts swim-float quality for accessible tide windows in the next three days. Each candidate window (when the tide is above the threshold for the float to be reachable) gets scored on a combination of temperature, wind exposure relative to dock face direction (315°), precipitation probability, and tide depth. Wind from the sheltered land directions scores higher than equivalent wind from the open-harbor directions.

## Hair Day Score

Predicts hair manageability for the next three days. The primary driver is absolute humidity (the actual water vapor content of the air, calculated from dew point), which doesn't change when temperature changes — making it a more stable frizz-risk predictor than relative humidity. Four hair-type profiles (Straight, Wavy, Curly, Coily) have different scoring curves, different wind thresholds, and different weightings between humidity, precipitation, and wind. Morning hours weight 3× more than afternoon hours because what your hair looks like at 8 AM is what matters.

## Birds

Bird observations from eBird within 5 km of the cove, refreshed every 10 minutes, looking back 48 hours. Notable/rare species flagged by eBird's regional filters are highlighted. Observations are grouped by location with public hotspot links (eBird) and private locations (Apple Maps), sorted nearest-first.

## 7-Day Forecast Text

A narrative forecast generated entirely in the collector — no AI involved. Merges HRRR (days 1–2) with GFS (days 3–7), producing NWS-style period descriptions with exposure-aware wind sentences. When wind is coming from a sheltered direction, the text says so explicitly instead of just reporting the speed.

## AI Briefing

Once every 30 minutes, the collector sends a structured summary of current and forecast conditions to Gemini 2.5 Flash and asks for a headline plus one-sentence subheadline. Gemini receives corrected values, the wind impact label rather than raw speed, the briefing from the previous run as context (so it can note forecast shifts), and explicit rules to use plain language and avoid redundancy between headline and subheadline. If Gemini fails for any reason, Groq's Llama 3.3 70B is the fallback. The active model is stamped on every cached briefing and surfaced in the Sources card.

---

## Calibration

The local station network learns from itself, but a closed-loop self-calibration has a blind spot: if every station drifts in the same direction (say, all of them read warm during a marine heatwave), the system can't detect it because each sensor still looks correct relative to its neighbors.

**Per-station chronic offsets.** Every tick, each station's reading is compared against the leave-one-out weighted consensus of all its peers, separately for day (7 AM–7 PM ET) and night (7 PM–7 AM ET). A 48-hour rolling history is kept in `station_history.json` in GCS. Once a station has at least 6 readings, its chronic offset is subtracted before that station contributes to the consensus. This catches the south-facing-rooftop bias, the shaded-garden bias, the thermal-mass-of-concrete bias.

**KBVY as outside reference.** Beverly Airport, 6.3 miles away, sits outside the network and uses different instruments. The difference between the local corrected temperature and KBVY is logged every 10 minutes. A sudden change in that gap is an early warning that something in the local network has shifted in a way the leave-one-out couldn't catch.

**The decay-curve fit.** Layer 4 fits forecast errors at every lead hour. If the model develops a new systematic bias at, say, lead 36h, the next daily Fitter run will see it in the data and the next collector tick will subtract it. The system corrects itself without anyone touching the code.

---

## Where to look

- **Live app:** [wymancove.com](https://wymancove.com)
- **Raw data:** [data.wymancove.com/weather_data.json](https://data.wymancove.com/weather_data.json)
- **Corrections debug page:** [wymancove.com/corrections_debug.html](https://wymancove.com/corrections_debug.html) — fitted decay curves, live forecast with vs without decay correction, and a per-station bias map
- **Code:** [github.com/jhselby/myweather](https://github.com/jhselby/myweather)
- **Detailed pipeline spec:** [docs/DATA_PIPELINE.md](DATA_PIPELINE.md) — full technical reference with code locations
- **Changelog:** [docs/CHANGELOG.md](CHANGELOG.md)
