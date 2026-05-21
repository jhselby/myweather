# MyWeather Data Pipeline Reference
**Version:** 0.5.170
**Last Updated:** May 21, 2026  
**Purpose:** Complete technical specification of all data corrections and transformations

---

## Table of Contents
1. [Temperature](#temperature)
2. [Humidity](#humidity)
3. [Pressure](#pressure)
4. [Wind Speed](#wind-speed)
5. [Wind Gusts](#wind-gusts)
6. [Wet Bulb Temperature](#wet-bulb-temperature)
7. [Feels Like / Apparent Temperature](#feels-like--apparent-temperature)
8. [Water Temperature](#water-temperature)
9. [Birds (eBird)](#birds-ebird)
10. [Hair Day Scoring](#hair-day-scoring)
11. [Forecast Text Generation](#forecast-text-generation)
12. [Data Flow Summary](#data-flow-summary)

---

## TEMPERATURE

### Current Hour Calculation

**Location:** `weather_collector/processors/hyperlocal.py`

**Station sources:** 29 WU stations + up to 9 Tempest stations, all within 1.5 miles

**Method:** Distance/elevation weighted bias correction with adaptive per-station offsets (diurnal split), Kalman gain blend

**Formula:**
```python
# Per-station adaptive offset — diurnal split (from station_bias.py, 48h rolling history):
# Uses temp_day offset during 7am-7pm ET, temp_night offset otherwise.
# Falls back to combined offset if split doesn't yet have >= MIN_READINGS.
corrected_station_temp = station_temp - chronic_offset[station_id]

# Bias against model:
bias_at_station = corrected_station_temp - model_temp
dist_weight = 1.0 / (station_dist ** 2)                    # Inverse square law
elev_weight = exp(-|station_elev - 30ft| / 30)            # Exponential decay
combined_weight = dist_weight × elev_weight

# Weighted average of all biases:
weighted_bias = Σ(bias_at_station × combined_weight) / Σ(combined_weight)

# Kalman gain — how much to trust stations vs. model:
K = 0.90  if stations_used >= 5 and bias_std < 1.0°F   # High confidence
K = 0.65  if stations_used >= 3 and bias_std < 2.0°F   # Moderate confidence
K = 0.40  otherwise                                      # Low confidence / few stations

# Apply to model (model contributes when K < 1):
corrected_temp = model_temp + K × weighted_bias
```

**Requirements:**
- Minimum 3 stations with valid data
- Stations must be within 1.5 miles
- Stations must have temperature, distance, and elevation data

**Confidence Calculation:**
```python
bias_std = standard_deviation(all_station_biases)
if bias_std < 1.0°F:    confidence = "High"
elif bias_std < 2.0°F:  confidence = "Moderate"
else:                   confidence = "Low"
```

**Data Stored (in `weather_data["hyperlocal"]`):**
- `model_temp` - Raw GFS/HRRR model temperature (°F)
- `weighted_bias` - Calculated bias correction (°F, before K scaling)
- `kalman_gain` - K value applied (0.40 / 0.65 / 0.90)
- `corrected_temp` - model_temp + K × weighted_bias (°F)
- `stations_used` - Number of stations with valid data in this run
- `stations_total` - All attempted stations (29 WU + 9 Tempest = 38)
- `confidence` - "High", "Moderate", or "Low"
- `bias_std` - Standard deviation of per-station biases (°F)
- `station_offsets` - Chronic offsets applied this run (from station_bias.py), if any
- `wu_avg_temp` - Simple WU multi-station average (for reference only)

**Fallback (if WU unavailable):**
- Uses PWS (Personal Weather Station) data
- Stores as `pws_temp`, `simple_bias`, `corrected_temp`

**Example Calculation:**
```
Model temp: 32.9°F
Station A (0.3mi, 28ft): 33.2°F → bias = +0.3°F, weight = 11.1 × 0.945 = 10.49
Station B (0.8mi, 35ft): 33.0°F → bias = +0.1°F, weight = 1.56 × 0.863 = 1.35
Station C (1.2mi, 20ft): 33.5°F → bias = +0.6°F, weight = 0.69 × 0.741 = 0.51

weighted_bias = (0.3×10.49 + 0.1×1.35 + 0.6×0.51) / (10.49 + 1.35 + 0.51)
              = 3.29 / 12.35 = +0.27°F

corrected_temp = 32.9 + 0.27 = 33.2°F
```

---

### Forecast Hours (1-48) Handling

**Backend:** NO correction applied to hourly arrays  
**Location:** `weather_collector/collector.py` line 113  
**Storage:** `weather_data["hourly"]["temperature"]` contains raw HRRR model data

**Frontend Application:** YES - flat bias applied  
**Location:** `js/app-main.js` lines 3787, 3807  
**Formula:**
```javascript
const bias = hyp.weighted_bias ?? 0;
corrected_forecast_temp = hourly.temperature[i] + bias
```

**Decay:** NONE - Same bias applied to all 48 hours

**Example:**
```
Current hour: bias = +0.27°F
Hour 1:  Model 31°F → Display 31.27°F
Hour 6:  Model 29°F → Display 29.27°F
Hour 24: Model 35°F → Display 35.27°F
Hour 48: Model 38°F → Display 38.27°F
```

---

### Frontend Display Usage

**Right Now Card:**
- **Element:** `#currentTemp`, `#currentTempCollapsed`
- **Code:** `js/app-main.js` lines 3185-3187
- **Value:** `hyp.corrected_temp ?? cur.temperature`
- **Fallback chain:** Corrected → Model

**48-Hour Temperature Chart:**
- **Element:** Temperature line in combined chart
- **Code:** `js/app-main.js` line 3787
- **Value:** `hourly.temperature.map(t => t + bias)` for 48 hours
- **Note:** Bias applied in frontend, not in data

**Smart Corrections Table:**
- **Elements:** `#scModelTemp`, `#scBiasTemp`, `#scCorrectedTemp`
- **Code:** `js/app-main.js` lines 3248-3253
- **Values:**
  - Model: `hyp.model_temp`
  - Bias: `hyp.weighted_bias ?? hyp.bias_temp`
  - Corrected: `hyp.corrected_temp`

---

## HUMIDITY

### Current Hour Calculation

**Location:** `weather_collector/processors/hyperlocal.py`

**Method:** Distance/elevation weighted average across all stations with adaptive per-station bias correction (same weights as temperature)

**Formula:**
```python
# Per-station adaptive offset (from station_bias.py, once >= 6 readings):
corrected_station_humidity = station_humidity - chronic_h_offset[station_id]

# Distance/elevation weighted average:
corrected_humidity = Σ(corrected_station_humidity × weight) / Σ(weight)
bias_humidity = corrected_humidity - model_humidity
```

**Data Stored (in `weather_data["hyperlocal"]`):**
- `model_humidity` - Raw GFS/HRRR model humidity (%)
- `corrected_humidity` - Weighted station average with bias correction (%)
- `bias_humidity` - corrected - model (%)

**Note:** Per-station chronic offsets kick in after ≥ 6 readings (~1 hour). Before that, raw station values are used.

---

### Forecast Hours (1-48) Handling

**Backend:** `corrected_humidity` array built in `collector.py` immediately after `build_hyperlocal_data`  
**Storage:** `weather_data["hourly"]["corrected_humidity"]` contains bias-corrected values; raw `weather_data["hourly"]["humidity"]` preserved as fallback

**Frontend Application:** YES — all display paths prefer corrected array  
**Pattern:** `hourly.corrected_humidity || hourly.humidity` used in app-main.js (line 1658) and `hyp.corrected_humidity ?? cur.humidity` for current hour

---

### Frontend Display Usage

**Right Now Card:** Not displayed separately (only used for dewpoint/wet bulb)

**Smart Corrections Table:**
- **Elements:** `#scModelHumidity`, `#scBiasHumidity`, `#scCorrectedHumidity`
- **Code:** `js/app-main.js` lines 3255-3260
- **Values:**
  - Model: `hyp.model_humidity`
  - Bias: `hyp.bias_humidity`
  - Corrected: `hyp.corrected_humidity`

---

## PRESSURE

### Current Hour Calculation

**Location:** `weather_collector/processors/hyperlocal.py`

**Method:** Distance/elevation weighted average across all stations with adaptive per-station bias correction. Falls back to KBOS or model if no station pressure data available.

**Formula:**
```python
# Per-station adaptive offset (from station_bias.py, once >= 6 readings):
corrected_station_pressure = station_pressure_in - chronic_p_offset[station_id]

# Distance/elevation weighted average:
corrected_pressure_in = Σ(corrected_station_pressure × weight) / Σ(weight)

# Fallback hierarchy if no station pressure data:
corrected_pressure_in = kbos_pressure_in OR model_pressure_in
```

**Data Stored (in `weather_data["hyperlocal"]`):**
- `model_pressure_in` - GFS/HRRR model pressure (inHg)
- `kbos_pressure_in` - KBOS observation (inHg) [if available]
- `corrected_pressure_in` - Weighted station average, or fallback (inHg)

**Note:** Per-station chronic offsets kick in after ≥ 6 readings (~1 hour).

---

### Forecast Hours (1-48) Handling

**Backend:** NO correction applied  
**Frontend:** NO correction applied  
**Storage:** `weather_data["hourly"]["pressure"]` contains raw HRRR model data

**Rationale:** Pressure varies spatially; KBOS/WU observations may not apply to forecast locations

---

### Frontend Display Usage

**Smart Corrections Table:**
- **Elements:** `#scModelPressure`, `#scBiasPressure`, `#scCorrectedPressure`
- **Code:** `js/app-main.js` lines 3262-3272
- **Values:**
  - Model: `hyp.model_pressure_in`
  - Bias: `corrected_pressure_in - model_pressure_in` (calculated, not stored)
  - Corrected: `hyp.corrected_pressure_in`

---

## WIND SPEED

### Current Hour Calculation

**Location:** `weather_collector/collector.py` lines ~230-317

**Method:** MAX selection across all stations; direction sourced from waterfront Tempest

**Process:**
1. Collect wind candidates from model, KBVY, WU stations (age-filtered), and Tempest stations (age-filtered)
2. Select station with HIGHEST gust for `wind_gusts`
3. Select station with HIGHEST sustained for `wind_speed` (independent from gust)
4. Direction: prefer highest-gust fresh waterfront Tempest station; fall back to max-gust source

**Code:**
```python
# Save model values before override
weather_data["current"]["model_wind_speed"] = weather_data["current"].get("wind_speed", 0)
weather_data["current"]["model_wind_gusts"] = weather_data["current"].get("wind_gusts", 0)

wind_candidates = []

# Model always included as a floor
wind_candidates.append({"source": "model", "gust": ..., "speed": ..., "waterfront": False})

# KBVY — METARs always fresh, no age filter needed
if kbvy_data and kbvy_data.get("wind_gust_kt"):
    wind_candidates.append({
        "source": "KBVY",
        "gust": kbvy_data["wind_gust_kt"] * 1.15078,
        "speed": kbvy_data["wind_speed_kt"] * 1.15078,
        "waterfront": False,
    })

# WU stations — skip if observation > 20 min old
for station in wu_data["stations"]:
    if not station.get("wind_gust_mph"):
        continue
    if timestamp_age_minutes(station["timestamp"]) > 20:
        continue
    wind_candidates.append({
        "source": f"WU_{station_id}",
        "gust": station["wind_gust_mph"],
        "speed": station.get("wind_speed_mph", 0),
        "waterfront": station.get("waterfront", False),  # no WU stations are waterfront
    })

# Tempest stations — skip if observation > 20 min old
for tb in tempest_data["stations"]:
    if not tb.get("valid") or not tb.get("wind_gust_mph"):
        continue
    if tb.get("age_minutes", 0) > 20:
        continue
    wind_candidates.append({
        "source": f"Tempest_{tb['station_name']}",
        "gust": tb["wind_gust_mph"],
        "speed": tb.get("wind_avg_mph", 0),
        "waterfront": tb.get("waterfront", False),  # True for Willow Rd, Driftwood Rd, Neptune Rd
    })

# Select independently
max_gust_entry = max(wind_candidates, key=lambda x: x['gust'])
max_speed_entry = max(wind_candidates, key=lambda x: x['speed'])
weather_data["current"]["wind_gusts"] = max_gust_entry['gust']
weather_data["current"]["wind_speed"] = max_speed_entry['speed']

# Direction from best fresh waterfront Tempest; fall back to max-gust source
waterfront_tempest = [c for c in wind_candidates if c["waterfront"] and c["source"].startswith("Tempest_") and c["direction"] is not None]
dir_source = max(waterfront_tempest, key=lambda x: x['gust']) if waterfront_tempest else max_gust_entry
weather_data["current"]["wind_direction"] = float(dir_source['direction'])
weather_data["current"]["condition_source"] = f"{max_gust_entry['source']} observed"
```

**Waterfront Tempest stations:** Willow Rd (204883), Driftwood Rd (85260), Neptune Rd (192019) — flagged in `TEMPEST_STATIONS` in `tempest.py`. These sit on the harbor and provide the most accurate wind direction for Wyman Cove.

**Rationale:** Exposed coastal location — trust highest observed wind. Direction from waterfront station because inland stations underreport due to terrain shielding.

**Data Stored:**
- Values stored directly in `weather_data["current"]` (NOT in hyperlocal)
- `current["wind_speed"]` - Observed sustained wind (mph)
- `current["wind_gusts"]` - Observed gust (mph)
- `current["wind_direction"]` - Wind direction (degrees)
- `current["condition_source"]` - e.g., "KBVY observed" or "WU_STATION123 observed"

**Hyperlocal Data (for reference only):**
- **Location:** `weather_collector/processors/hyperlocal.py` lines 166-178
- `model_wind_speed` - Raw model value (saved before max-selection)
- `wu_wind_speed` - WU average (if available)
- `corrected_wind_speed` - Max-selected value from collector (reads `current["wind_speed"]` which has already been overwritten by max-selection)
- `bias_wind_speed` - corrected - model (for Smart Corrections display)

---

### Forecast Hours (1-48) Handling

**Backend:** YES - 24-hour linear decay blend applied  
**Location:** `weather_collector/collector.py` lines 136-164

**Formula:**
```python
# Get observed wind from current hour (already max-selected)
observed_speed = weather_data["current"]["wind_speed"]

# Find current hour index in hourly array
current_idx = hourly["times"].index(current_hour_iso)

# Blend for next 24 hours
for i in range(current_idx, current_idx + 24):
    hours_ahead = i - current_idx
    blend_weight = max(0, 1 - (hours_ahead / 24))
    
    model_speed = hourly["wind_speed"][i]
    hourly["wind_speed"][i] = (observed_speed × blend_weight) + (model_speed × (1 - blend_weight))
```

**Blend Weight Schedule:**
- Hour 0:  100% observed, 0% model
- Hour 6:  75% observed, 25% model
- Hour 12: 50% observed, 50% model
- Hour 18: 25% observed, 75% model
- Hour 24: 0% observed, 100% model
- Hour 25+: 100% model (no blend)

**Example:**
```
Observed: 12 mph
Model forecast: [10, 11, 9, 8, 7, 6, ...remaining hours]

After blend:
Hour 0:  12.0 × 1.00 + 10 × 0.00 = 12.0 mph
Hour 6:  12.0 × 0.75 + 9  × 0.25 = 11.3 mph
Hour 12: 12.0 × 0.50 + 7  × 0.50 = 9.5 mph
Hour 24: 12.0 × 0.00 + 6  × 1.00 = 6.0 mph
Hour 25+: Raw model (no observed influence)
```

**Storage:** Values are MODIFIED IN PLACE in `weather_data["hourly"]["wind_speed"]`

---

### Frontend Display Usage

**Right Now Card - Wind Impact:**
- **Element:** `#windImpactNow`
- **Code:** `js/app-main.js` lines 3416-3427
- **Value:** `hyp.corrected_wind_speed ?? cur.wind_speed`
- **Used for:** Display AND impact score calculation
- **Note:** Falls back to hyperlocal corrected (which is just model copy) or current

**48-Hour Wind Chart:**
- **Element:** Sustained wind bars
- **Code:** `js/app-main.js` line 3801
- **Value:** `hourly.wind_speed` (already blended in backend)
- **Note:** Chart displays backend-blended values directly

**Impact Score Calculation:**
- **Code:** `js/app-main.js` line 3421
- **Formula:** `worryScore(hyp.corrected_wind_speed ?? cur.wind_speed, exposure)`
- **Exposure:** Directional exposure factor from lookup table

---

## WIND GUSTS

### Current Hour Calculation

**Two parallel systems exist - this is confusing:**

#### System 1: Collector Max Selection (Used by Frontend)
**Location:** `weather_collector/collector.py` lines 98-102  
**Method:** MAX gust across all stations (same as sustained wind)  
**Storage:** `weather_data["current"]["wind_gusts"]`  
**This is what actually gets used**

#### System 2: Hyperlocal Weighted Average (Calculated but Less Used)
**Location:** `weather_collector/processors/hyperlocal.py` lines 152-195  
**Method:** Distance and elevation weighted average (same weights as temperature)

**Formula:**
```python
# For each WU station with gust data:
dist_weight = 1.0 / (station_dist ** 2)
elev_weight = exp(-|station_elev - 30ft| / 30)
combined_weight = dist_weight × elev_weight

# Weighted average:
wu_avg_gust = Σ(station_gust × combined_weight) / Σ(combined_weight)
bias_gust = wu_avg_gust - model_gust
corrected_gust = model_gust + bias_gust  # Same as wu_avg_gust
```

**Requirements:**
- Minimum 3 stations with gust data
- Stations within 1.5 miles

**Constraint:** Gusts enforced >= sustained wind
```python
if corrected_gust < corrected_wind_speed:
    corrected_gust = corrected_wind_speed
```
`corrected_wind_speed` is the max-selected observed value (not a model copy), so this constraint is valid.

**Data Stored (in `weather_data["hyperlocal"]`):**
- `model_wind_gusts` - Raw model value
- `wu_wind_gusts` - Weighted average of WU stations
- `bias_wind_gusts` - wu_avg - model
- `corrected_wind_gusts` - model + bias (enforced >= sustained)

---

### Forecast Hours (1-48) Handling

**Backend:** YES - 24-hour linear decay blend applied  
**Location:** `weather_collector/collector.py` lines 153-159  
**Uses:** Max-selected observed gust from System 1 (NOT hyperlocal weighted average)

**Formula:**
```python
# Get observed gust from current hour (max-selected)
observed_gust = weather_data["current"]["wind_gusts"]

# Blend for next 24 hours (same as sustained wind)
for i in range(current_idx, current_idx + 24):
    hours_ahead = i - current_idx
    blend_weight = max(0, 1 - (hours_ahead / 24))
    
    model_gust = hourly["wind_gusts"][i]
    hourly["wind_gusts"][i] = (observed_gust × blend_weight) + (model_gust × (1 - blend_weight))
```

**Same decay as sustained wind** - see Wind Speed section for schedule

**Storage:** Values MODIFIED IN PLACE in `weather_data["hourly"]["wind_gusts"]`

---

### Frontend Display Usage

**Right Now Card - Gust Impact:**
- **Element:** `#gustImpactNow`
- **Code:** `js/app-main.js` lines 3433-3445
- **Value:** `hyp.corrected_wind_gusts ?? cur.wind_gusts`
- **Used for:** Display AND impact score calculation
- **Note:** Uses hyperlocal weighted average if available, falls back to max-selected

**48-Hour Wind Chart:**
- **Element:** Gust line
- **Code:** `js/app-main.js` line 3802
- **Value:** `hourly.wind_gusts` (already blended in backend)
- **Note:** Chart displays backend-blended values (which used max-selected, not hyperlocal)

**Smart Corrections Table:**
- **Elements:** `#scModelGusts`, `#scBiasGusts`, `#scCorrectedGusts`
- **Code:** `js/app-main.js` lines 3274-3279
- **Values:**
  - Model: `hyp.model_wind_gusts`
  - Bias: `hyp.bias_wind_gusts`
  - Corrected: `hyp.corrected_wind_gusts` (from hyperlocal weighted average)

---

## WET BULB TEMPERATURE

### Current Hour Calculation

**Location:** `weather_collector/processors/precip_surface.py` lines 107-116

**Method:** Calculate from corrected temperature and corrected humidity

**Formula (Stull's psychrometric equation):**
```python
# Using corrected values:
corrected_temp_f = hyp.corrected_temp
corrected_humidity_pct = hyp.corrected_humidity

# Convert to Celsius
t = (corrected_temp_f - 32) × 5/9
rh = corrected_humidity_pct

# Stull's formula
tw = (t × atan(0.151977 × (rh + 8.313659)^0.5)
      + atan(t + rh)
      - atan(rh - 1.676331)
      + 0.00391838 × rh^1.5 × atan(0.023101 × rh)
      - 4.686035)

# Convert back to Fahrenheit
corrected_wet_bulb_f = tw × 9/5 + 32
```

**Data Stored:**
- `weather_data["derived"]["corrected_wet_bulb"]` - Current hour only (°F)
- Uses corrected temp + corrected humidity inputs

**Also calculated:**
- **Location:** `weather_collector/processors/wet_bulb.py`
- `weather_data["current"]["wet_bulb"]` - From hyperlocal corrected temp + corrected humidity
- `weather_data["hourly"]["wet_bulb"]` - From corrected_temperature + corrected_humidity arrays (all hours)

---

### Forecast Hours (1-48) Handling

**Backend:** YES - fully corrected (both temp and humidity)  
**Location:** `weather_collector/processors/precip_surface.py`

**Formula:**
```python
# Use bias-corrected arrays (built earlier in collector.py):
hourly_temps = hourly["corrected_temperature"]   # Bias-corrected temp array
hourly_humidity = hourly["corrected_humidity"]   # Bias-corrected humidity array

# Calculate corrected wet bulb directly:
corrected_wet_bulb = calculate_wet_bulb(temp, humidity)
```

**Storage:** `weather_data["hourly"]["corrected_wet_bulb"]`

**Correction status:**
- ✅ Uses corrected temperature (corrected_temperature array, v0.5.71)
- ✅ Uses corrected humidity (corrected_humidity array, v0.5.71)
- Consistent with current hour correction

**Daily High/Low (Corrected):**

**Location:** `weather_collector/collector.py` (after `build_hyperlocal_data`)

**Method:** Separate HRRR fetch with `past_hours=24` + `forecast_hours=48` provides full calendar day coverage. Hyperlocal bias applied to all hourly temps, then max/min computed per day.

```
corrected_hourly_temp = hrrr_hourly_temp + weighted_bias
today_high = max(corrected temps for today date)
today_low  = min(corrected temps for today date)
```

**Output:** `derived.today_high`, `derived.today_low`, `derived.tomorrow_high`, `derived.tomorrow_low`

**Frontend:** All display paths (briefing card, 10-day collapsed preview, detailed forecast) read directly from `derived`. No bias recomputation in JS.

**Observed Temperature Log:**

**Location:** `weather_collector/collector.py` → `_update_obs_temp_log()`

**Method:** Each collector run (every 10 min) logs `hyperlocal.corrected_temp` with an Eastern-time hour stamp to `obs_temp_log.json`. One entry per hour, deduped. Keeps today + yesterday only.

**Hybrid daily high/low:** `derived.today_high/low` = max/min of (observed corrected temps for past hours) + (corrected forecast temps for remaining hours). As the day progresses, observations replace forecast data, converging on the true observed high/low by end of day.

**Fetch parallelization:** Open-Meteo calls run sequentially (rate-limit sensitive). All other fetchers (NWS, WU, buoy, tides, KBOS, KBVY, eBird, Pirate Weather, GoMOFS water temp) run in parallel via `concurrent.futures.ThreadPoolExecutor`.

**Why corrected arrays are used for wet bulb:**
- `corrected_temperature` and `corrected_humidity` are built in `collector.py` immediately after `build_hyperlocal_data` runs
- Both wet_bulb.py and precip_surface.py run after those arrays exist, so they can use them directly
- The frontend still applies bias to the raw `temperature` array for chart display, but the backend now has fully corrected values for derived calculations

---

### Frontend Display Usage

**48-Hour Temperature Chart:**
- **Element:** Wet bulb line
- **Code:** `js/app-main.js` line 3789
- **Value:** `hourly.corrected_wet_bulb ?? hourly.wet_bulb`
- **Fallback:** Corrected (partial) → Raw model

**Smart Corrections Table:**
- **Elements:** `#scModelWetBulb`, `#scCorrectedWetBulb`
- **Values:**
  - Model: `cur.wet_bulb` (from raw temp + humidity)
  - Corrected: `der.corrected_wet_bulb` (from corrected temp + corrected humidity)

---

## FEELS LIKE / APPARENT TEMPERATURE

### Two parallel systems (v0.5.147+)

**System 1: NWS Heat Index (shade)**
- **Condition:** T ≥ 80°F AND RH ≥ 40%
- **Formula:** Rothfusz polynomial (NOAA standard)
- **Inputs:** hyp.corrected_temp, hyp.corrected_humidity
- **Storage:** `derived.heat_index` (°F)
- **Display:** Primary value on card front ("In shade") and briefing tab Heat Index row

**System 2: Steadman Australian Apparent Temperature (full sun)**
- **Location:** weather_collector/collector.py lines ~495-520 (current), ~393-415 (hourly)
- **Shade formula (no direct sun):** AT = Ta + 0.33×e − 0.70×ws − 4.00
- **Radiation formula (direct sun):** AT = Ta + 0.348×e − 0.70×ws + 0.70×Q/(ws+10) − 4.25; Q = solar_wm2 × 0.17
- Where: Ta = corrected temp (°C), e = vapour pressure (hPa), ws = corrected wind (m/s)
- **Solar source priority:**
  1. Pirate Weather `current_solar` — point forecast, updated each run
  2. Average of valid Tempest station readings (`solar_radiation_wm2`)
  3. Open-Meteo `hourly.direct_radiation` — modeled, hourly resolution
- **Storage:** `derived.corrected_feels_like` (°F, current); `hourly.corrected_apparent_temperature` (48h array)
- **Display:** Secondary value ("☀ Full sun: X°F") when full sun exceeds heat index by >5°F

### Card Front Display Logic
```
heatIndex = der.heat_index ?? der.corrected_feels_like ?? apparent_temperature
fullSunFL = der.corrected_feels_like
if fullSunFL > heatIndex + 5: show "☀ Full sun: X°F" below primary value
```

### Briefing Tab Heat Index Row
- Shown when feelsLike > temp, temp ≥ 80°F, diff ≥ 5°F
- Uses `der.heat_index` directly (Kalman-corrected inputs; avoids 1°F discrepancy from re-computing with uncorrected `s.temp`)
- Value string: "98° in shade · 109° in full sun" when full sun exceeds shade by >3°F

### Feels Like Chart (feelslike.js)
Three lines computed from hourly arrays:
- **In shade:** `calcFullSunAT(temp, humidity, wind, 0)` — AT formula, solar=0
- **☀ Full sun:** `calcFullSunAT(temp, humidity, wind, direct_radiation)` — AT formula with solar
- **Air Temp:** raw `corrected_temperature`
- Note: `hourly.corrected_apparent_temperature` (Open-Meteo apparent temp) is NOT used for the chart because it already bakes in radiation effects, causing the two feels-like lines to overlap.

---


## BIRDS (eBIRD)

### Data Source

**Fetcher:** `weather_collector/fetchers/ebird.py`

**API Endpoints:**
- `/v2/data/obs/geo/recent` — all recent species (one obs per species)
- `/v2/data/obs/geo/recent/notable` — rarities per eBird regional filters

**Parameters:**
- Radius: 5 km from home (LAT/LON in config.py)
- Lookback: 2 days (~48 hours)
- API key: `EBIRD_API_KEY` env var (Cloud Function), hardcoded fallback for local dev

### Per-Observation Schema

| Field | Type | Description |
|-------|------|-------------|
| code | string | eBird species code (e.g., "coohaw") |
| name | string | Common name |
| sci_name | string | Scientific name |
| count | int/null | Number observed (null = "X" in eBird) |
| last_seen | string | "YYYY-MM-DD HH:MM" |
| location | string | Location name (hotspot or personal) |
| loc_id | string | eBird location ID (e.g., "L5289631") |
| loc_private | bool | True = personal location, False = public hotspot |
| lat | float | Observation latitude |
| lng | float | Observation longitude |
| distance_km | float | Haversine distance from home |
| notable | bool | True if in notable/rarity list |

### Frontend Rendering

**Location:** `js/app-main.js` function `renderBirds()`

Collapsed tile: top notable species or species count. Expanded: grouped by location, sorted nearest first. Species links go to eBird. Public hotspot names link to eBird map view. Private location names link to Apple Maps via maps: URI. External links set `window.__externalLinkOpen` to prevent visibilitychange card collapse on return.

---

## HAIR DAY SCORING

### Overview

Predicts hair manageability for 3 days. Four hair type profiles with different scoring curves. Selection persisted to localStorage key `hairType`, default `curly`.

**Location:** `js/app-main.js` function `renderHairDay()`

### Hair Type Profiles

| Profile | AH Sweet Spot | Wind Threshold | Weights (AH/Precip/Wind) | Primary Risk |
|---------|--------------|----------------|--------------------------|-------------|
| Straight | 4-5 g/m3 | 28 mph gust | 55/30/15 | Limpness in humidity, static in dry |
| Wavy | 4-5 g/m3 | 22 mph gust | 60/25/15 | Frizz and puffiness |
| Curly | 4-5 g/m3 | 20 mph gust | 70/20/10 | Frizz and volume expansion |
| Coily | 6-7 g/m3 | 18 mph gust | 75/15/10 | Dryness, shrinkage, breakage |

### Scoring Components

**AH (primary):** From dew point via Magnus approximation. Each type has different curve. **Precip (secondary):** Based on probability, type, intensity. **Wind (tertiary):** Based on when wind crosses threshold during 6am-8pm. **RH penalty:** Multiplicative: >90%=0.65x, >80%=0.80x, >70%=0.92x.

**Composite:** `round((ahScore * w_ah + precipScore * w_precip + windScore * w_wind) * rhPenalty)`

### Hour Weighting

Morning-biased: 6-10am weight 3.0, 10am-2pm weight 1.0, 2-8pm weight 0.5, outside 0.

### Score Labels

88-100: Great hair day. 74-87: Good hair day. 58-73: Manageable. 40-57: Frizz risk. 25-39: Bad hair day. 0-24: Stay inside.

---

## WATER TEMPERATURE

### Source Priority
1. **GoMOFS** (primary) — NOAA Gulf of Maine Operational Forecast System
2. **Buoy 44013** (fallback) — NDBC offshore buoy, 16mi ENE

### GoMOFS Details
- **Endpoint:** `https://opendap.co-ops.nos.noaa.gov/thredds/dodsC/NOAA/GOMOFS/MODELS/YYYY/MM/DD/`
- **File pattern:** `gomofs.tHHz.YYYYMMDD.regulargrid.nNNN.nc`
- **Grid point:** ny=401, nx=103 (42.53N, -70.86W) — Salem Channel, ~1.5mi from dock
- **Variable:** `temp[time][Depth][ny][nx]`, Depth index 0 = surface
- **Resolution:** ~700m horizontal grid
- **Cycles:** 4/day (00z, 06z, 12z, 18z), 72h forecast each
- **Fill value:** -99999.0 = land mask (point confirmed as water)
- **Output key:** `weather_data["salem_water_temp_f"]` (°F)

### URL Construction
Fetcher tries most recent cycle first, walks back through n000→n003→n006→n009→n012 forecast offsets until a non-404 file is found. Falls back to previous day 18z if needed.

### Buoy 44013 Fallback
- Scraped from `https://www.ndbc.noaa.gov/station_page.php?station=44013`
- Returns surface water temp in °F
- Systematically 2-5°F colder than Salem Sound in summer

### Frontend
- `data.salem_water_temp_f` used in ocean card front (waterTempCollapsed), expanded view (buoyWaterTemp), and beach day scoring (waterTempRaw)
- Falls back to `data.buoy_44013.water_temp_f` if GoMOFS key absent

---

## DATA FLOW SUMMARY

### Current Hour Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA SOURCES (APIs)                       │
├─────────────────────────────────────────────────────────────┤
│ • Open-Meteo (GFS/HRRR) - Model data                       │
│ • Weather Underground - Multi-station observations          │
│ • KBOS (Logan Airport) - Official observations              │
│ • KBVY (Beverly Airport) - ASOS observations               │
│ • Personal Weather Station - Hyperlocal observations        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              COLLECTOR (collector.py)                        │
├─────────────────────────────────────────────────────────────┤
│ 1. Fetch all sources                                         │
│ 2. Build weather_data["current"] from model                 │
│ 3. Build weather_data["hourly"] from model (raw arrays)     │
│ 4. MAX-SELECT wind from all stations                        │
│    → Overwrites current["wind_speed"]                       │
│    → Overwrites current["wind_gusts"]                       │
│ 5. BLEND wind into hourly arrays (24h decay)                │
│    → Modifies hourly["wind_speed"] IN PLACE                 │
│    → Modifies hourly["wind_gusts"] IN PLACE                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│       STATION BIAS PROCESSOR (station_bias.py)               │
├─────────────────────────────────────────────────────────────┤
│ Loads station_history.json from GCS (48h rolling window)     │
│ compute_offsets() → chronic offset per station per metric    │
│                                                              │
│  • ≥ 6 readings required before offset applied              │
│  • Leave-one-out: each station vs. consensus of all others  │
│  • Covers temp, humidity, pressure independently            │
│  • Offsets passed to hyperlocal.py as station_offsets dict  │
│  • After hyperlocal runs, update_history() appends new      │
│    leave-one-out deltas and saves to GCS                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│          HYPERLOCAL PROCESSOR (hyperlocal.py)                │
├─────────────────────────────────────────────────────────────┤
│ Creates weather_data["hyperlocal"] with:                     │
│                                                              │
│ TEMPERATURE:                                                 │
│  • Per-station offsets applied before bias calculation      │
│  • weighted_bias = distance/elevation weighted avg of biases │
│  • K (Kalman gain) = 0.90/0.65/0.40 based on confidence    │
│  • corrected_temp = model + K × weighted_bias               │
│                                                              │
│ HUMIDITY:                                                    │
│  • Per-station offsets applied                              │
│  • corrected_humidity = weighted station average            │
│  • bias_humidity = corrected - model                        │
│                                                              │
│ PRESSURE:                                                    │
│  • Per-station offsets applied                              │
│  • corrected_pressure = weighted station average            │
│  • Fallback: KBOS OR model                                  │
│                                                              │
│ WIND GUSTS (parallel to collector's max-select):            │
│  • Weighted average from WU stations                        │
│  • corrected_wind_gusts = model + weighted_bias             │
│                                                              │
│ WIND SPEED:                                                  │
│  • corrected_wind_speed = max-selected (reads current[      │
│    "wind_speed"] which collector already overwrote)         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│       WET BULB PROCESSOR (wet_bulb.py)                       │
├─────────────────────────────────────────────────────────────┤
│ Creates weather_data["current"]["wet_bulb"]:                 │
│  • From hyperlocal corrected_temp + corrected_humidity      │
│                                                              │
│ Creates weather_data["hourly"]["wet_bulb"]:                  │
│  • From corrected_temperature + corrected_humidity arrays   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│    SURFACE PRECIP PROCESSOR (precip_surface.py)             │
├─────────────────────────────────────────────────────────────┤
│ Creates weather_data["derived"]["corrected_wet_bulb"]:       │
│  • From CORRECTED temp + CORRECTED humidity                 │
│                                                              │
│ Creates weather_data["hourly"]["corrected_wet_bulb"]:        │
│  • From corrected_temperature + corrected_humidity arrays   │
│  • Fully corrected (both temp and humidity, v0.5.71)        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                 WRITE weather_data.json                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              FRONTEND (app-main.js)                          │
├─────────────────────────────────────────────────────────────┤
│ Load weather_data.json                                       │
│                                                              │
│ CURRENT HOUR DISPLAY:                                        │
│  • Temperature: hyp.corrected_temp                          │
│  • Humidity: hyp.corrected_humidity                         │
│  • Pressure: hyp.corrected_pressure_in                      │
│  • Wind speed: hyp.corrected_wind_speed (max-selected)      │
│  • Wind gusts: hyp.corrected_wind_gusts (weighted avg)      │
│  • Feels like: CALCULATE from corrected inputs              │
│  • Wet bulb: der.corrected_wet_bulb                         │
│                                                              │
│ 48-HOUR FORECAST DISPLAY:                                    │
│  • Temperature: hourly.temperature + hyp.weighted_bias      │
│    (bias applied here in frontend)                          │
│  • Wind speed: hourly.wind_speed (already blended)          │
│  • Wind gusts: hourly.wind_gusts (already blended)          │
│  • Wet bulb: hourly.corrected_wet_bulb (fully corrected)    │
│  • Feels like chart: calcFullSunAT(hourly, solar=0/actual)  │
│    (corrected_apparent_temperature not used — bakes in solar)│
└─────────────────────────────────────────────────────────────┘
```

---

## KEY ARCHITECTURAL NOTES


### API Key Management (v4.81)
- All API keys (WU, Pirate Weather, eBird) read from Cloud Function environment variables
- Hardcoded fallback values remain in source for local development
- Keys set via `--set-env-vars` in `make deploy-collector`
- Repo is public (`jhselby/myweather`) — env vars prevent key exposure in production

### Temperature Correction Architecture
- **Backend:** Calculates bias, stores in hyperlocal, does NOT modify hourly arrays
- **Frontend:** Applies bias to 48-hour forecast when displaying
- **Reason:** Allows flexibility - can change decay strategy without re-running collector

### Wind Correction Architecture
- **Backend (current hour):** Max-selects from model + KBVY + WU (age-filtered) + Tempest (age-filtered, waterfront-flagged)
- **Backend (forecast):** Blends max-selected observed into hourly arrays with 24h linear decay
- **Hyperlocal:** Stores model vs corrected for Smart Corrections display
- **Frontend:** Displays pre-blended forecast values directly
- **Direction:** Waterfront Tempest stations (Willow Rd, Driftwood Rd, Neptune Rd) preferred for direction; these sit on harbor and are most accurate for Wyman Cove
- **Rationale:** User lives in most exposed/windiest location, so max across all sources is a floor, not a ceiling

### Wind Speed and Gust Architecture (v0.5.119)
- **Collector:** Max-selects from model + KBVY + WU + Tempest independently for both sustained and gusts
- **Collector:** WU candidates excluded if observation > 20 min old; Tempest candidates excluded if `age_minutes > 20`
- **Collector:** Saves original model values as `model_wind_speed` and `model_wind_gusts` before override
- **Collector:** `waterfront` flag on each candidate — currently True only for three Tempest stations on Wyman Cove harbor
- **Hyperlocal:** Passes through collector max-selected values, calculates bias (corrected - model)
- **Frontend:** Displays max-selected values with model comparison in Smart Corrections table
- **Result:** Both sustained and gusts always use highest available reading across all fresh sources

### Full Correction: Wet Bulb Forecast (v0.5.71)
- **Uses:** corrected_temperature array (temp bias pre-applied in backend)
- **Uses:** corrected_humidity array (humidity bias pre-applied in backend)
- **Result:** Forecast wet bulb fully corrected, consistent with current hour

### Full Correction: Feels-Like Forecast
- **Current hour:** Fully corrected (temp, wind, humidity via Steadman radiation formula)
- **Forecast hours:** Fully corrected via hourly.corrected_apparent_temperature (computed in collector since v0.5.43)

---

## CORRECTION STATUS MATRIX

| Variable | Current Hour | Forecast (1-48h) | Method | Decay |
|----------|-------------|------------------|--------|-------|
| **Temperature** | ✅ Corrected | ✅ Bias applied (frontend) | Weighted bias | None (flat) |
| **Humidity** | ✅ Corrected | ✅ corrected_humidity array used by frontend | Replacement | N/A |
| **Pressure** | ✅ Best source | ❌ Raw model | Selection | N/A |
| **Wind Speed** | ✅ Max-selected (model+KBVY+WU+Tempest, age-filtered) | ✅ Blended (backend) | Independent max-select | 24h linear |
| **Wind Gusts** | ✅ Max-selected (model+KBVY+WU+Tempest, age-filtered) | ✅ Blended (backend) | Independent max-select | 24h linear |
| **Wet Bulb** | ✅ Fully corrected | ✅ Fully corrected (v0.5.71) | Calculated | N/A |
| **Feels Like (shade)** | ✅ NWS heat index from corrected inputs | ✅ AT formula solar=0 from corrected hourly | Calculated | N/A |
| **Feels Like (full sun)** | ✅ AT formula with corrected inputs + solar | ✅ AT formula with hourly direct_radiation | Calculated | N/A |

**Legend:**
- ✅ Fully corrected
- ⚠️ Partially corrected or has issues
- ❌ No correction applied

---

## BUGS AND IMPROVEMENTS NEEDED

### Bug #1: Wind Speed Current Hour — RESOLVED (v4.29)
**Original concern:** `hyp.corrected_wind_speed` appeared to be a model copy
**Actual behavior:** Collector max-selects wind (KBVY, WU, model) and writes to `weather_data["current"]["wind_speed"]` BEFORE `build_hyperlocal_data` runs. So `current.get("wind_speed")` already returns the corrected value.
**Fix:** Variable renamed from `model_w` to `observed_w`, comment updated to clarify.
**Status:** Not a bug — execution order was correct all along.

### Bug #2: Wind Gust Constraint — RESOLVED (v4.29)
**Original concern:** Constraint compared against model copy
**Actual behavior:** Same as Bug #1 — `corrected_wind_speed` was already max-selected.
**Status:** Constraint works as intended.

### Improvement #1: Temperature Forecast Decay
**Current:** Flat bias for all 48 hours
**Potential:** Time-decaying bias (similar to wind's 24h decay)
**Rationale:** Bias relevance decreases over time, especially across diurnal cycles
**Complexity:** Medium - requires choosing decay window (6h? 12h? 24h?)

### Improvement #2: Humidity Forecast Correction
**Current:** Only used for wet bulb calculation, not applied to main humidity arrays
**Potential:** Apply humidity bias to forecast (like temperature)
**Impact:** Would improve dewpoint, wet bulb, feels-like forecasts
**Complexity:** Low - just apply bias in frontend like temperature

### Improvement #3: Wet Bulb Forecast Full Correction — RESOLVED (v0.5.71)
**Fix:** Both wet_bulb.py and precip_surface.py now read corrected_temperature and corrected_humidity arrays instead of raw model arrays. corrected_temperature is built in collector.py immediately after build_hyperlocal_data, so it's available to all downstream processors.

### Improvement #4: Feels-Like Forecast Correction — RESOLVED (v0.5.43)
**Fix:** collector.py computes corrected_apparent_temperature for all 48h using corrected_temperature, corrected_humidity, and blended wind. Frontend reads hourly.corrected_apparent_temperature directly.

---

## VERSION HISTORY

**v0.5.169–v0.5.170 (May 21, 2026):**
- Yesterday context in briefing prompt: `obs_temp_log.json` now records hourly `precip_in` and `gust_mph` alongside temp; collector derives `derived.yesterday_high`, `derived.yesterday_precip_in`, `derived.yesterday_peak_gust`; all three passed to Gemini/Groq as a single "Yesterday:" line with no rules attached
- Groq model upgraded from `llama-3.1-8b-instant` to `llama-3.3-70b-versatile` for better prompt rule compliance
- Settings alert dot: critical-only trigger (GFS, HRRR, WU, Pirate Weather, NWS Alerts); supplementary sources (KBVY, KBOS, eBird, buoy, tides) fail silently
- Source error display: raw exception strings parsed to short readable labels in sources.js

**v0.5.159–v0.5.168 (May 20, 2026):**
- Groq fallback: `llama-3.1-8b-instant` via Groq API (OpenAI-compatible); fires when Gemini raises any exception; `"model": "gemini"/"groq"` tagged on every briefing save and cached return; Sources card shows active/standby with age for the active model
- No-redundancy prompt rule: headline and subheadline must carry different information
- Briefing stale indicator: "headline from Xh ago" shown below headline when briefing >90 min old
- Corrections card: bias display fixed — shows actual applied delta (`corrected_temp − model_temp`) not raw `weighted_bias` (which is pre-Kalman and overstates the correction)
- Wind briefing row: "Light winds at the cove (9 mph NW, gusts 23)" format
- Terminology: mph spacing, capitalization normalized across js/briefing.js, js/wind.js, js/sources.js, index.html

**v0.5.145–v0.5.149 (May 19, 2026):**
- Pirate Weather cloud cover fallback: collector extracts 48h cloud cover from PW; injected into hourly block when Open-Meteo HRRR is down or cloud_cover array is empty
- Gemini briefing: switched to `gemini-2.5-flash` (gemini-2.5-flash-lite invalid); maxOutputTokens 200→2048 (thinking model); in-memory backoff on failure prevents retry storm
- Dual feels-like display: NWS heat index (shade, Rothfusz) added to `derived.heat_index`; card front shows heat index as primary + "☀ Full sun" secondary when gap >5°F; briefing tab uses `der.heat_index` directly for consistency
- Feels Like chart: 3 lines (In shade = AT formula solar=0, Full sun = AT formula with direct_radiation, Air Temp); `hourly.corrected_apparent_temperature` not used (it bakes in radiation, causing lines to overlap); legend updated to match
- Briefing Heat Index row: "98° in shade · 109° in full sun" format when full sun exceeds shade by >3°F

**v0.5.119–v0.5.121 (May 13, 2026):**
- Wind blend expanded to include Tempest stations alongside model, KBVY, and WU
- Age filtering added: WU candidates excluded if observation > 20 min old; Tempest excluded if `age_minutes > 20`
- `waterfront` flag added to all wind candidates; Willow Rd (204883), Driftwood Rd (85260), Neptune Rd (192019) marked True
- Wind direction now sourced from the highest-gust fresh waterfront Tempest station when available; falls back to max-gust source
- Gust and sustained speed max-selected independently (gust source and speed source may differ)
- WU `print()` calls converted to `logging` for structured Cloud Function log output
- Schema version check added to frontend: shows "App update required" if `schema_version` in data doesn't match expected
- Hard vetoes added to sea breeze detector: wrong direction or excessive wind speed vetoes `active=True` regardless of overall score
- Advection fog bug fixed: early return on spread > 5°F was preventing advection fog from ever firing; restructured to always compute both fog types and take the max
- Sea breeze threshold tightened: `temp_diff < 5°F → score 0` (was: `< 3°F → 20, < 5°F → 40`)
- Alert priority fixed in briefing: Extreme/Severe NWS alerts now surface above `rain_now`
- "Watch For" hierarchy: fog rows at 50–69% and sea breeze rows dim at 55% opacity
- Briefing dateline: data age shown right-aligned ("3m ago")
- Settings accordions: opening one panel now collapses its siblings
- `Hyperlocal` tab renamed to `Lifestyle`
- Test suite added: `tests/test_processors.py` with 17 tests for fog, wet bulb, and sea breeze processors

**v0.5.105 (May 13, 2026):**
- Diurnal split on temperature bias correction: station_bias.py now tags each temp delta as `delta_d` (7am–7pm ET) or `delta_n` (7pm–7am ET) alongside the combined `delta`. compute_offsets() returns `temp_day` and `temp_night` in addition to `temp`. hyperlocal.py applies the split offset when ≥ MIN_READINGS available for the current period, falls back to combined. Captures sensors whose warm/cold bias varies across the day (e.g. shading, thermal mass).
- KBVY temp logged as external calibration anchor: `kbvy_temp_f` and `kbvy_local_delta` (corrected_temp − KBVY) added to hyperlocal output every run. Builds empirical distribution of the local marine/elevation offset for future network-level drift detection.

**v0.5.86–v0.5.104 (May 13, 2026):**
- Tempest stations expanded from 3 to 9 within ~1.5mi of Wyman Cove (Willow Rd, Driftwood Rd, Neptune Rd, Baldwin Rd, Maple St, Forest Ave, Lincoln Ave, Willard Ln, ColleeninMHD)
- WU station list trimmed from 36 to 29: removed 7 confirmed out-of-range stations (KMAMARBL1, KMASALEM91, KMAMARBL8, KMAMARBL64, KMAMARBL85, KMAMARBL113, KMAMARBL118)
- Station denominator: `stations_total` now counts all attempted stations (29 WU + 9 Tempest = 38), not just responders
- Adaptive bias correction (station_bias.py): new module tracking per-station chronic offsets for temp, humidity, and pressure using leave-one-out consensus over a 48h rolling window in GCS (station_history.json). MIN_READINGS=6 before offset applied.
- hyperlocal.py: single-pass per-station loop applies temp, humidity, and pressure offsets simultaneously; old standalone humidity/pressure blocks removed
- Kalman gain blend: corrected_temp = model + K × weighted_bias where K = 0.90/0.65/0.40 based on stations_used and bias_std. Model contributes meaningfully when stations disagree. `kalman_gain` field added to hyperlocal output.
- Tempest stations shown in Settings → Sources card
- Version update detection: build.py writes version.json; frontend polls every 5 min and lights up refresh button dot if new version available
- v0.5.104: fixed version dot always showing (DOM timing — appVersion element not yet parsed when script executed; fixed with setTimeout(0) and lazy read)

**v0.5.76–v0.5.85 (May 9, 2026):**
- Gemini briefing: fallback to gemini-1.5-flash-8b on 429; both models configurable via env vars
- Gemini briefing: in-memory guard prevents burst calls on GCS failure (safe due to max-instances=1)
- Gemini briefing: previous headline fed as context; prompt instructs model to note forecast shifts
- Wet bulb, precip_surface.py: both now use corrected_temperature and corrected_humidity arrays throughout (v0.5.71 fix; documented here retroactively)
- Wind direction fallback: if GFS fails and no candidate station has direction, falls back to KBVY wind_dir

**v4.82 (April 24, 2026):**
- Hair Day hair-type selector: 4 profiles (Straight, Wavy, Curly, Coily) with tuned scoring curves
- Birds card: clickable location links (eBird hotspot map for public, Apple Maps for private)
- Birds card: sort by distance, added loc_id/loc_private/lat/lng to collector schema
- External link fix: visibilitychange handler skips card collapse on return from external links
- API keys migrated to Cloud Function env vars
- HTML validator added to build.py
- Wind Impact card moved to Weather tab
- Hyperlocal tab reordered, Sunset Score renamed to Sunset

**v4.11 (April 4, 2026):**
- Wind corrections applied throughout frontend
- 48-hour wind chart uses corrected values (already blended in backend)
- Smart Corrections table displays all correction data
- This documentation created

**Previous versions:**
- Temperature weighted bias system implemented
- Wind blend (24h decay) implemented
- Wet bulb correction (partial) implemented
- Humidity and pressure corrections implemented

---

## USAGE NOTES

**For Data Work:**
Paste this document + session handoff when working on corrections, biases, or data pipeline.

**For UI Work:**
This document not needed - UI just displays values from weather_data.json.

**For Debugging:**
Check this document first to understand where data comes from and what corrections apply.

**When Adding New Corrections:**
1. Update relevant section with formulas, line numbers, storage locations
2. Add to Correction Status Matrix
3. Update Data Flow Summary diagram if architecture changes
4. Bump version number and document in Version History

---

**END OF DOCUMENT**


---

## AI Briefing (Gemini)

**Purpose:** Generate a concise, human-readable daily briefing (headline + subheadline) using corrected and derived weather data.

### Inputs (Collector → Gemini)

- Current (corrected where available):
  - Temperature (corrected_temp)
  - Humidity (corrected_humidity)
  - Wind speed (corrected_wind_speed)
  - Wind gusts (corrected_wind_gusts)
  - Wind direction
- Daily:
  - High temperature (derived.today_high preferred, fallback to model daily)
  - Low temperature (model fallback)
- Derived:
  - Wind impact label only (Calm, Breezy, etc.) — numeric score intentionally excluded to prevent Gemini from echoing raw numbers
  - Fog probability + label
  - Sea breeze state + reasoning
- Forecast:
  - Rain timing (next 48h, probability ≥40 percent)
  - Total precipitation (mm → inches)
- Alerts (NWS)
- Sunset score (if available)
- Yesterday's observed high (from `obs_temp_log.json`; always present after first full day)
- Yesterday's precip total in inches (from `obs_temp_log.json`; present once log has been running ≥1 day; omitted if trace/zero)
- Yesterday's peak gust in mph (from `obs_temp_log.json`; omitted if < 20 mph)

### Key Rules

- Corrected data is source of truth
- Wind Impact score is the authoritative hyperlocal measure — accounts for terrain exposure; Gemini uses the label to set tone, not raw speed
- Gemini decides when contrast between local impact and regional forecast is worth mentioning (not forced)
- No invented geography or causal landmark claims
- Avoid vague coastal phrasing ("off the water", "onshore")
- Headline and subheadline must not repeat the same information — if the headline names a trend, the subheadline must add something new

### Output

{ "headline": "...", "subheadline": "..." }

- Headline: ≤12 words
- Subheadline: 1–2 sentences

### Model Configuration

- **Primary:** `gemini-2.5-flash` (default, configurable via `GEMINI_MODEL` env var; `gemini-2.5-flash-lite` was invalid/503)
- **Fallback:** Groq API (`llama-3.3-70b-versatile`) when Gemini raises any exception; OpenAI-compatible endpoint (`https://api.groq.com/openai/v1/chat/completions`); key via `GROQ_API_KEY` Secret Manager; same system prompt as Gemini
- **maxOutputTokens:** 2048 for Gemini (thinking model); 256 for Groq
- **Retry storm guard:** `_last_gemini_call_time` set on failure; prevents every 10-min run from retrying Gemini after an error; same guard covers Groq path
- **Model tagging:** every briefing save includes `"model": "gemini"` or `"model": "groq"`; cached returns preserve the tag; Sources card reads `data.briefing.model` to show active/standby state

### Previous Briefing Context

- Before calling Gemini, `_load_cached_briefing()` reads the current `briefing_cache.json` from GCS
- Previous headline is injected into the prompt as `prev_context`
- System prompt rule: if forecast has shifted meaningfully (timing, rain/snow line, temperature trend), note the change briefly in the subheadline

### Caching

- Cached in GCS (`briefing_cache.json`)
- Refresh interval: 30 minutes
- In-memory guard (`_last_gemini_call_time`): checked before GCS read, prevents burst calls when GCS fails; safe because Cloud Function runs max-instances=1
- Fallback: cached → template


---

## Forecast Text Generation

**Source:** `weather_collector/processors/forecast_text.py`
**Output:** `weather_data["forecast_text"]` — array of period objects

### Structure
- **Days 1-7:** 14 day/night periods from merged HRRR (48h) + GFS (168h) hourly data
- **Days 8-10:** Simple daily summaries from ECMWF daily data

### Period Fields (Days 1-7)
- `period_name` — "Today", "Tonight", "Saturday", "Saturday Night", etc.
- `date` — ISO date string
- `is_daytime` — boolean
- `text` — NWS-style narrative with exposure-aware wind sentences
- `temperature` — high (day) or low (night), rounded
- `wind_speed`, `wind_direction`, `wind_full` — raw wind data
- `wind_worry_score` — site-adjusted wind impact (speed × exposure^1.5)
- `wind_worry_label` — Calm / Light winds / Breezy / Windy / Very windy
- `wind_exposure_factor` — 0.0–1.0 directional terrain exposure from WIND_EXPOSURE_TABLE

### Wind Narrative Logic
Uses worry_score + exposure_factor to generate contextual wind sentences:
- **Windy/Breezy label:** "Windy at the cove, [dir] gusts to X mph."
- **High raw wind + low exposure (< 0.5):** "Calm at the cove despite [dir] gusts to X mph."
- **Normal conditions:** Standard NWS-style wind sentence
- Gust threshold for "despite" narrative: ≥ 25 mph or sustained > 12 mph

### Period Fields (Days 8-10)
- `period_name`, `date`, `temperature`, `low_temp`
- `is_simple_daily` — true
- `text` — includes sky condition (from ECMWF weather_code), temp, precip, gusts

### Data Source Priority
- HRRR preferred for periods within 48h coverage (2h tolerance)
- GFS used for periods beyond HRRR range
- NWS gridpoint temps override model temps when available
- `derived.today_high/low` and `derived.tomorrow_high/low` override computed temps for days 0-1
