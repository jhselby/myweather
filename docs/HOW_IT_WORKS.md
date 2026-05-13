# How It Works

MyWeather is a hyperlocal weather app built for a specific location: Wyman Cove in Marblehead, Massachusetts. Every number you see has been processed through a pipeline designed to answer one question: what is the weather actually doing here, right now?

---

## Data Sources

The app draws from eight external sources simultaneously, every ten minutes:

**Open-Meteo** provides the model backbone — HRRR for the next 48 hours and GFS for days 3 through 10. These are the same numerical weather prediction models used by professional forecasters. They're good at large-scale patterns but run on grids too coarse to resolve local coastal microclimate effects.

**Weather Underground** provides observations from 29 personal weather stations within 1.5 miles of Wyman Cove, plus wind data from stations slightly farther out. These are hobbyist sensors — quality varies.

**Nine Tempest stations** also within 1.5 miles contribute higher-quality observations. Tempest uses a different sensor architecture than typical WU stations and generally has lower drift.

**KBVY (Beverly Municipal Airport)**, 6.3 miles northwest, provides certified ASOS observations — the same instrument-grade sensors used by the FAA and National Weather Service. Used primarily for wind and as a calibration reference.

**KBOS (Logan Airport)** contributes pressure observations. Logan's barometers are among the most reliable in the region.

**Pirate Weather** provides the only reliable minutely precipitation forecast (next hour, by the minute), plus solar radiation, lightning probability, and atmospheric instability data that Open-Meteo doesn't expose.

**NOAA's Gulf of Maine Operational Forecast System (GoMOFS)** provides water temperature from a grid point in Salem Channel, approximately 1.5 miles from the dock — far more accurate than a buoy 16 miles offshore.

**eBird** provides bird observation data from a 5km radius, updated every 10 minutes.

---

## Temperature

The model's temperature for this grid cell is a starting point, not an answer. The HRRR grid cell that covers Wyman Cove spans several kilometers — the model has no knowledge of the specific microclimate at the water's edge.

The correction works in three layers.

**Station weighting.** Each of the 38 local stations contributes to a weighted average based on two factors: distance (closer stations matter more, following an inverse-square relationship) and elevation (stations at similar height to Wyman Cove's 30 feet are more representative than rooftop sensors). The weighted average of what all stations are reading gives a "bias" — the difference between what the model predicts and what the local area is actually experiencing.

**Self-calibration.** Personal weather stations drift. A sensor on a south-facing rooftop will read warm in summer. One in a shaded garden runs cold. The app tracks each station's chronic offset over a 48-hour rolling window using a leave-one-out technique: every run, each station's reading is compared against the weighted consensus of all its neighbors. A station that consistently reads 2.7°F warmer than everyone else gets that offset subtracted before it contributes to the correction. This runs separately for day and night, since a sensor shaded in the afternoon may be accurate at midnight.

**Confidence blending.** When 33 stations all agree within 1°F of each other, the station-based correction is applied at 90% weight — the model contributes only 10%. When stations are noisier or fewer are reporting, the model gets more weight back (up to 60%). This is the same principle used in the NWS Real-Time Mesoscale Analysis: blend observations with the model in proportion to how much you trust each.

For the 48-hour forecast, the current bias is applied flat across all hours.

---

## Humidity

Handled the same way as temperature: a distance/elevation weighted average across all stations, with per-station chronic offsets applied first. The model's humidity is frequently wrong for coastal locations — marine air is consistently more humid than model grids suggest, and the correction regularly adds 4–6% relative humidity to the model value.

---

## Pressure

Weighted station average with per-station bias correction, falling back to Logan Airport (KBOS) if station data isn't available, and to the model as a last resort. Pressure doesn't vary much over 1.5 miles, so the correction here is mostly about sensor calibration rather than spatial interpolation.

---

## Wind

Wind is handled differently from temperature and humidity. A weighted average of wind speeds across 38 stations is meaningless — wind varies too much over short distances depending on terrain, buildings, and fetch. A sensor behind a house reads differently from one on a roof, which reads differently from one at the water's edge.

The approach for current conditions is maximum selection: take the highest gust observed by any station (including KBVY), and use that as the floor. At an exposed coastal site, the highest reading is the most representative one for what you'd experience outside. The model value is never allowed to be higher than the observed maximum.

For the 48-hour forecast, the current observed wind is blended into the model forecast with a linear decay over 24 hours. At the current hour, the display shows 100% observed. Six hours from now, 75% observed. Twelve hours, 50/50. By hour 24, the model takes over completely. This ensures the near-term forecast is grounded in what's actually happening rather than what the model expected hours ago.

---

## Wind Impact Score

Raw wind speed doesn't tell the whole story at Wyman Cove. A 20 mph south wind is barely felt at the dock — Marblehead and local terrain block it almost completely. The same speed from the north or northwest, with open harbor exposure, is a completely different experience.

The wind impact score adjusts for directional exposure using a lookup table that maps wind direction to a terrain exposure factor between 0 and 1. The impact score is the product of wind speed and a power of the exposure factor. A strong wind from a sheltered direction scores low. A moderate wind from the exposed southeast scores high. The 10-day forecast text uses this score to decide whether to say "windy at the cove" or "calm at the cove despite regional gusts."

---

## Feels Like

Uses the Steadman Australian Apparent Temperature formula, which combines temperature, humidity, and wind speed. On days with direct sunlight, a solar radiation term is added — this accounts for the fact that full sun in calm conditions feels warmer than the thermometer suggests. The formula uses corrected values for all inputs, and is fully recalculated for every hour of the 48-hour forecast.

---

## Wet Bulb Temperature

The wet bulb temperature — the lowest temperature achievable by evaporative cooling — is calculated from corrected temperature and corrected humidity using Stull's psychrometric equation. It's more relevant than heat index for assessing heat stress in humid conditions, and more honest than "feels like" for understanding outdoor athletic limits. Calculated for the current hour and all 48 forecast hours.

---

## Daily High and Low

The daily high and low are not taken directly from the model's forecast. Instead, they're computed from a hybrid of observed and forecast temperatures. Each time the collector runs, it logs the corrected local temperature with an hourly timestamp. The daily high is the maximum of all observed corrected temperatures so far today, plus the corrected forecast temperatures for the remaining hours. As the day progresses, observations replace forecast values, so by evening the high and low reflect what actually happened rather than what was predicted.

---

## Water Temperature

Comes from NOAA's Gulf of Maine Operational Forecast System — a dedicated ocean circulation model with a grid point in Salem Channel, 1.5 miles from the dock. This is significantly more accurate than the NDBC buoy 16 miles offshore, which runs 2–5°F colder than local inshore water in summer due to upwelling and distance. The GoMOFS model runs four times a day and produces 72-hour forecasts.

---

## Hair Day Score

Predicts hair manageability for three days. The primary driver is absolute humidity — the actual water vapor content of the air, calculated from dew point. Unlike relative humidity, absolute humidity doesn't change when temperature changes, making it a more stable predictor of frizz risk. Four hair type profiles (Straight, Wavy, Curly, Coily) have different scoring curves, different wind thresholds, and different weightings between humidity, precipitation, and wind. Morning hours are weighted three times more heavily than afternoon, on the logic that how your hair looks at 8am is what matters. A high relative humidity penalty multiplies the score down when air is already near saturation regardless of absolute moisture content.

---

## Birds

Bird observations from eBird within 5km of the cove, updated every 10 minutes, looking back 48 hours. Notable/rare species flagged by eBird's regional filters are highlighted. Observations are grouped by location, sorted nearest first. Counts come directly from eBird observer reports and may be exact numbers or an "X" where the observer didn't count.

---

## 10-Day Forecast Text

The narrative forecast is generated entirely in the collector — no AI involved for the text itself. It merges HRRR data (days 1–2) with GFS data (days 3–7) and ECMWF daily summaries (days 8–10), generating NWS-style period descriptions with exposure-aware wind sentences. When wind is coming from a sheltered direction, the text says so explicitly rather than just reporting the speed.

---

## AI Briefing (Gemini)

Once every 30 minutes, the collector sends a structured summary of current and forecast conditions to Google's Gemini model and asks for a headline and one-sentence subheadline. Gemini receives corrected values — not raw model output — and the wind impact label rather than raw speed, so its tone reflects what the weather feels like at the specific location rather than what the regional forecast says. The previous headline is fed as context so Gemini can note when the forecast has shifted since the last briefing.

---

## KBVY as a Calibration Anchor

The leave-one-out self-calibration is a closed loop — stations learn from each other. If the entire local network drifts warm together over a summer, the system won't detect it because every station looks correct relative to its neighbors. Beverly Airport, 6.3 miles away, provides an outside reference. The difference between the local corrected temperature and KBVY is logged every 10 minutes. Over time, this builds a picture of the normal marine and elevation offset between the airport and the cove. A sudden change in that gap is an early warning that something in the local network has shifted.
