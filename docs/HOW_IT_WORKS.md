# How It Works

MyWeather is a hyperlocal weather app built for a specific location: Wyman Cove in Marblehead, Massachusetts. Every number you see has been processed through a pipeline designed to answer one question: what is the weather actually doing here, right now?

The system runs in two places. A Python collector on Google Cloud Functions fires every ten minutes, pulls from ten external sources, runs every value through four layers of correction, and writes a single JSON payload to a public Google Cloud Storage bucket. A vanilla-JS progressive web app at wymancove.com reads that payload from GitHub Pages and renders it. The two halves share no infrastructure — they connect through a public URL and nothing else.

---

## Data Sources

Ten external sources feed in every ten minutes.

**Open-Meteo** is the model backbone — HRRR for the next 48 hours and GFS for days 3 through 7. These are the same numerical weather prediction models professional forecasters use. They're excellent at large-scale patterns but their grid cells are kilometers wide, too coarse to resolve the microclimate at the water's edge.

**Pirate Weather** provides the only reliable minutely precipitation forecast (the next hour, by the minute), plus solar radiation, lightning probability, and atmospheric instability (CAPE) that Open-Meteo doesn't expose.

**Weather Underground** provides observations from up to 60 personal weather stations within 2.5 miles of the cove. These are hobbyist sensors — quality varies wildly. The system measures and corrects for each station's individual drift (see Calibration, below).

**Up to 26 Tempest stations** within 2.5 miles contribute higher-quality observations. Tempest's sensor architecture is more consistent than typical WU stations and generally has lower drift.

**KBVY** (Beverly Municipal Airport), 6.3 miles northwest, provides certified ASOS observations — the same instrument-grade sensors used by the FAA and the National Weather Service. KBVY is the wind floor and a calibration anchor.

**KBOS** (Logan Airport) contributes pressure and sky-condition observations. Logan's barometers are among the most reliable in the region, and its METAR sky-condition codes feed the cloud-cover correction.

**NWS gridpoints** at BOX/76,97 provide additional forecast detail (cloud, mixing height, fire weather) and active weather alerts.

**NOAA's Gulf of Maine Operational Forecast System (GoMOFS)** provides water temperature from a grid point in Salem Channel, about 1.5 miles from the dock. Far more accurate for local water temperature than the NDBC buoy 16 miles offshore.

**NOAA CO-OPS** (station 8442645, Salem) provides tide harmonic predictions used for the tides card and water-level overlays.

**eBird** provides bird observations from a 5 km radius, looking back 48 hours, refreshed every 10 minutes.

**Google Gemini 2.5 Flash** generates the briefing headline and subheadline once every 30 minutes. Groq (Llama 3.3 70B) is the fallback when Gemini fails.

---

## The Four Correction Layers

Every numeric forecast you see in the app — temperature, dew point, humidity, wind speed, wind gust, precipitation probability, pressure, cloud cover — has been through up to four layers of work. Understanding all four makes everything else easier to read.

**Layer 1 — Raw model (HRRR / GFS).**
The starting point. The Open-Meteo HRRR model gives a 48-hour forecast on a multi-kilometer grid; GFS extends days 3–7. Neither knows anything about Wyman Cove specifically. Every other layer is correcting what these two get wrong locally.

**Layer 2 — Mesonet corrections (local station network).**
The 81-station local network's collective read on what the raw model is missing. Four internal sub-steps. (a) Collect: pull readings from the WU and Tempest stations within 2.5 miles. (b) Per-station calibration: subtract each station's own chronic offset (a Kalman tracker maintains a 48h rolling estimate of how warm/cold/wet each individual station systematically reads vs. its neighbors). (c) Octant-balanced aggregation: group the stations by compass octant (N/NE/E/SE/S/SW/W/NW), compute a distance²×elevation-weighted bias within each octant, then average across non-empty octants — so a dense Marblehead-side cluster of 12 stations doesn't outvote a sparse Salem-side octant of 2. Before each octant's mean, MAD-based outlier trimming drops any single station that's > ~4°F from the octant median (busted-sensor defense). (d) Network confidence: a Kalman gain K (0.4 / 0.65 / 0.9) decides how much of the resulting network bias to actually apply to the forecast, based on how tightly the octants agree. K=0.9 means trust the network strongly (octants are within 0.4°F); K=0.4 means trust the model and barely nudge it. The result is `corrected_temperature`, `corrected_humidity`, `corrected_pressure_in`, etc. — the same flat correction added to every forecast hour out to 48h.

Wind is a special case under this layer: averaging stations is meaningless because wind varies too much over short distances, so the system takes the per-octant maximum gust and then the median across octants. A single sensor's gust spike won't move the forecast; a regional event seen in multiple directions will. The selected value is blended into the next 24 hours of the model on a linear decay (100% observed at hour 0, model-only by hour 24). Cloud cover and precipitation probability have no per-station bias (stations don't measure them) — they pass through Layer 2 unchanged.

**Layer 3 — Lead-time decay correction (forecast hours 0–47).**
Layer 2 corrects for "the model is biased right now"; Layer 3 corrects for "the model's bias changes the further out you forecast." The system measures its own past forecast errors via snapshot-versus-observation comparison, fits a recency-weighted mean error per (field, lead-hour) bin (exponential decay, τ=14 days), and subtracts that residual from every forecast hour. At lead 0 the correction is near zero (Layer 2 has already done its work); at lead 36h the correction can be 5–15 mph on gust, 12% on humidity, 1–2 °F on temperature. Fitted four times daily (every 6h) on a rolling 30-day window of pairs.

**Layer 4 — Diurnal correction (hour-of-day).**
Some biases follow the clock, not the lead time: marine air gets more humid every afternoon as the sea breeze kicks in, temperature consistently under-predicts in the late afternoon, etc. Layer 4 fits a per-(field, hour-of-day) mean residual error from the same pair log, normalized to be mean-zero across 24 bins so it doesn't double-count Layer 3's overall mean. The correction at lead-hour N depends on what local clock time that hour will be when it arrives.

The four layers don't fight each other. Layer 1 is raw input; Layer 2 anchors to the local mesonet; Layer 3 removes systematic lead-time error; Layer 4 captures the diurnal residual that Layer 3 averages over. Each is measured against post-prior-layer values, so the stack doesn't double-count.

---

## The Decay Pipeline (Layers 3 & 4 in detail)

Layers 3 and 4 share an infrastructure of four pieces that run inside the collector. None are visible to the user directly, but they're the part of the system that gets *better over time*.

**Piece 1 — Snapshot logger.** Every 10-minute tick, the collector saves a snapshot of the corrected 48-hour forecast to `forecast_log.json` in GCS. Since v0.6.25, snapshots also capture the forecast at each layer (raw, +mesonet, +decay, +final) per hour — enabling per-layer accuracy measurement on the diagnostic page. A 14-day rolling window is kept (~600 snapshots at steady state).

**Piece 2 — Joiner.** Every tick, the collector pairs every recent observation against every snapshot whose forecast covered that hour. One row per (observation × snapshot × field) triple, with the forecast value, the observed value, the lead time, and the error (forecast − observed). Per-layer error fields too (since v0.6.25). Rows are appended to `forecast_error_log.jsonl` via GCS compose (server-side stitch, constant cost regardless of file size). At steady state this file is ~1.3 GB containing about 7.5 million pairs across 30 days.

**Piece 3 — Fitter.** Every 6 hours (03:07, 09:07, 15:07, 21:07 EDT), the collector reads the full pair log and computes three things: (a) Layer-3 per-(field, lead-hour) recency-weighted mean error; (b) Layer-4 per-(field, hour-of-day) mean error, mean-zero normalized; (c) per-layer MAE-by-lead grids for the accuracy diagnostic page. Each pair contributes a weight of `exp(-age_days / 14)` — fresh pairs full weight, week-old pairs half-weight. The Fitter also prunes the pair log to a 30-day window.

**Piece 4 — Apply.** Every tick, after the main payload is built, the collector reads the correction tables and subtracts each lead's mean error from the corresponding hour of the corrected forecast arrays. Per-field sanity caps (5 °F for temp, 10 mph for wind, etc.) prevent any pathological fit from blowing up the user-facing forecast. If a corrections file is missing or older than 7 days, Apply skips that layer — the payload falls back cleanly.

You can see all of this — the fitted curves, the per-station bias map, the live forecast with vs without each correction layer, the octant coverage rose, and the per-layer MAE chart that measures whether each correction earns its keep — at `wymancove.com/corrections_debug.html`.

---

## Temperature

Layer 1 (HRRR raw) → Layer 2 (octant-balanced mesonet bias, K-scaled) → Layer 3 (lead-time decay) → Layer 4 (diurnal). The current-hour display reads `hyperlocal.corrected_temp` (live station consensus, better than a model-derived value for "now"). Forecast hours read `corrected_temperature[]` (post all four layers). Daily high and low are not the model's forecast — they're computed from a hybrid of observed and forecast: each tick logs the corrected local temperature, and the daily high is the max of all observed temperatures so far today plus the corrected forecast temperatures for the remaining hours. As the day progresses, observations replace forecast values, so the high and low end the day reflecting what actually happened.

## Humidity and Dew Point

Same four layers as temperature: Layer 2 octant-balanced mesonet correction (separately tracked humidity bias), then Layer 3 lead-time decay, then Layer 4 diurnal. Marine air is consistently more humid than model grids suggest — the Layer 2 correction regularly adds 4–6% RH. Dew point is computed from the corrected temperature and corrected humidity via the Magnus formula, and gets its own independent Layer 3/4 corrections on top.

## Wind and Gusts

Current observed wind is selected via Layer 2's octant-aware logic: per-octant max gust across all fresh sources (WU < 20 min old, Tempest < 20 min old, KBVY METAR, model floor), then median across octants. A sanity cap fires if the chosen value is more than 2.5× the WU network aggregate, which usually means a single bad sensor is spiking. Wind direction prefers the highest-gust *waterfront* Tempest station, falling back to whatever the max-gust source reports.

For the 48-hour forecast: Layer 2 wind blend (24-hour linear blend from observed toward model) → Layer 3 (lead-time decay) → Layer 4 (diurnal). At hour 0 the displayed wind is essentially the observation. By hour 24 the blend has faded out and only the model + Layer 3/4 corrections remain. Wind has no per-station bias under Layer 2 — per-station wind biases are too noisy to track meaningfully.

## Wind Impact Score

A 20 mph south wind is barely felt at the dock — Marblehead and local terrain block it almost completely. The same speed from the north or northwest, with open harbor exposure, is a completely different experience. The wind impact score multiplies wind speed by a directional exposure factor between 0 and 1, drawn from a 16-direction lookup table tuned for Wyman Cove. The 7-day forecast text uses this score to decide between "windy at the cove" and "calm at the cove despite regional gusts."

## Feels Like

Uses the Steadman Australian Apparent Temperature formula, which combines temperature, humidity, and wind speed. On days with direct sunlight, a solar radiation term is added. The card on the Weather tab shows the shade value as primary and the full-sun value as secondary when they differ by more than 5 °F. All inputs are corrected values; recalculated for every hour of the 48-hour forecast.

## Wet Bulb Temperature

The lowest temperature achievable by evaporative cooling, calculated from corrected temperature and corrected humidity via Stull's psychrometric equation. More relevant than heat index for assessing humid-heat stress, and more honest than feels-like for outdoor athletic limits.

## Pressure

Weighted station average with octant balancing and per-station bias correction (same Layer 2 treatment as temp/humidity), falling back to KBOS (Logan) if station data isn't available. Pressure doesn't vary much over 2.5 miles — the correction is mostly about sensor calibration and ends up tiny (~0.02 inHg typically). Layer 3 (lead-time decay) and Layer 4 (diurnal) also apply to forecast pressure, though the model is already quite accurate so the corrections are small. A separate pressure-trend analyzer classifies the 3-hour trend into an alarm level (steady / falling / rapidly falling) that drives the storm-warning indicators.

## Cloud Cover

Forecast cloud cover (Layer 1) gets Layer 3 (decay) and Layer 4 (diurnal) corrections, calibrated against KBOS METAR sky-condition observations (SKC/CLR=0%, FEW=12%, SCT=38%, BKN=75%, OVC=100%, taking the highest layer per NWS convention). KBOS is ~15 miles south but coastal — adequate for synoptic cloud patterns but blind to local marine-layer dynamics specific to the Marblehead peninsula. No Layer 2 (stations don't measure cloud cover directly).

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

**Outlier defense.** Within each compass octant, MAD-based (median absolute deviation) outlier detection drops any station whose reading is more than ~3.5×MAD from the octant median before computing that octant's contribution to the network bias. MAD instead of standard deviation, because std is inflated by the very outlier we want to catch — a +5°F busted sensor near a 0.5°F median pushes std past its own deviation and protects itself; MAD is unaffected.

**Geographic balance.** Stations cluster where people live. Without correction, the dense Marblehead-side cluster would dominate the network bias, ignoring the genuinely-different microclimate on the Salem side. Octant balancing weights every compass sector equally regardless of how many stations are in it — a 12-station Marblehead octant contributes the same as a 2-station Salem octant.

**KBVY as outside reference.** Beverly Airport, 6.3 miles away, sits outside the network and uses different instruments. The difference between the local corrected temperature and KBVY is logged every 10 minutes. A sudden change in that gap is an early warning that something in the local network has shifted in a way the leave-one-out couldn't catch.

**The decay-curve and diurnal fits.** Layers 3 and 4 fit forecast errors at every lead hour and hour of day. If the model develops a new systematic bias, the next Fitter run will see it in the data and the next collector tick will subtract it. The system corrects itself without anyone touching the code.

---

## Where to look

- **Live app:** [wymancove.com](https://wymancove.com)
- **Raw data:** [data.wymancove.com/weather_data.json](https://data.wymancove.com/weather_data.json)
- **Forecast pipeline (live diagnostics):** [wymancove.com/corrections_debug.html](https://wymancove.com/corrections_debug.html) — per-field accuracy chart, layer-by-layer drill-down, per-station bias map, octant coverage rose, fitted decay + diurnal curves
- **Code:** [github.com/jhselby/myweather](https://github.com/jhselby/myweather)
- **Detailed pipeline spec:** [docs/DATA_PIPELINE.md](DATA_PIPELINE.md) — full technical reference with code locations
- **Changelog:** [docs/CHANGELOG.md](CHANGELOG.md)
