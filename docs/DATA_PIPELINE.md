# MyWeather Data Pipeline Reference
**Version:** 4.82  
**Last Updated:** April 24, 2026  
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
8. [Birds (eBird)](#birds-ebird)
9. [Hair Day Scoring](#hair-day-scoring)
10. [Data Flow Summary](#data-flow-summary)

---

## TEMPERATURE

### Current Hour Calculation

**Location:** `weather_collector/processors/hyperlocal.py` lines 48-123

**Method:** Distance and elevation weighted bias correction

**Formula:**
```python
# For each WU station within 1.5 miles:
bias_at_station = station_temp - model_temp
dist_weight = 1.0 / (station_dist ** 2)                    # Inverse square law
elev_weight = exp(-|station_elev - 30ft| / 30)            # Exponential decay
combined_weight = dist_weight × elev_weight

# Weighted average of all biases:
weighted_bias = Σ(bias_at_station × combined_weight) / Σ(combined_weight)

# Apply to model:
corrected_temp = model_temp + weighted_bias
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
- `weighted_bias` - Calculated bias correction (°F)
- `corrected_temp` - Model + weighted bias (°F)
- `stations_used` - Number of stations contributing to calculation
- `stations_total` - Total WU stations available
- `confidence` - "High", "Moderate", or "Low"
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

**Location:** `weather_collector/processors/hyperlocal.py` lines 135-141

**Method:** Direct replacement with WU multi-station average

**Formula:**
```python
corrected_humidity = wu_avg_humidity  # Simple replacement
bias_humidity = wu_avg_humidity - model_humidity
```

**Data Stored (in `weather_data["hyperlocal"]`):**
- `model_humidity` - Raw GFS/HRRR model humidity (%)
- `wu_humidity` - WU multi-station average (%)
- `bias_humidity` - Difference (%)
- `corrected_humidity` - Same as wu_humidity (%)

**Note:** Unlike temperature, humidity uses simple replacement, not weighted bias correction

---

### Forecast Hours (1-48) Handling

**Backend:** NO correction to main hourly arrays  
**Storage:** `weather_data["hourly"]["humidity"]` contains raw HRRR model data

**Frontend Application:** NO direct correction  
**Exception:** Humidity bias IS used for corrected wet bulb calculation (see Wet Bulb section)

**Location of bias application:** `weather_collector/processors/precip_surface.py` lines 139-147
```python
# Applied only for wet bulb calculation, not stored in main humidity array
corrected_hourly_humidity = hourly_humidity[i] + humidity_bias
corrected_wet_bulb = calculate_wet_bulb(hourly_temp[i], corrected_hourly_humidity)
```

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

**Location:** `weather_collector/processors/hyperlocal.py` lines 125-133

**Method:** Preference hierarchy (WU → KBOS → Model)

**Formula:**
```python
corrected_pressure_in = wu_pressure_in OR kbos_pressure_in OR model_pressure_in
```

**Data Stored (in `weather_data["hyperlocal"]`):**
- `model_pressure_in` - GFS/HRRR model pressure (inHg)
- `wu_pressure_in` - WU multi-station average (inHg) [if available]
- `kbos_pressure_in` - KBOS observation (inHg) [if available]
- `corrected_pressure_in` - Best available value (inHg)

**Note:** This is selection, not bias correction - picks best source

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

**Location:** `weather_collector/collector.py` lines 79-106

**Method:** MAX selection across all stations

**Process:**
1. Collect wind candidates from KBVY and all WU stations
2. Select station with HIGHEST gust reading
3. Use that station's sustained wind speed

**Code:**
```python
# Build candidates list
wind_candidates = []
if kbvy_data and kbvy_data.get("wind_gust_kt"):
    wind_candidates.append({
        "source": "KBVY",
        "gust": kbvy_data["wind_gust_kt"] * 1.15078,  # kt to mph
        "speed": kbvy_data["wind_speed_kt"] * 1.15078,
        "direction": kbvy_data.get("wind_dir")
    })

for wu_station in wu_stations:
    if wu_station.get("wind_gust_mph"):
        wind_candidates.append({
            "source": f"WU_{station_id}",
            "gust": wu_station["wind_gust_mph"],
            "speed": wu_station.get("wind_speed_mph", 0),
            "direction": wu_station.get("wind_direction")
        })

# Select station with max gust
max_wind = max(wind_candidates, key=lambda x: x['gust'])

# Store in current (overwrites model values)
weather_data["current"]["wind_speed"] = max(max_wind['speed'], model_wind_speed)
weather_data["current"]["wind_gusts"] = max_wind['gust']
weather_data["current"]["wind_direction"] = max_wind['direction']
```

**Rationale:** Exposed coastal location - trust highest observed wind

**Data Stored:**
- Values stored directly in `weather_data["current"]` (NOT in hyperlocal)
- `current["wind_speed"]` - Observed sustained wind (mph)
- `current["wind_gusts"]` - Observed gust (mph)
- `current["wind_direction"]` - Wind direction (degrees)
- `current["condition_source"]` - e.g., "KBVY observed" or "WU_STATION123 observed"

**Hyperlocal Data (for reference only):**
- **Location:** `weather_collector/processors/hyperlocal.py` line 150
- `model_wind_speed` - Raw model value
- `wu_wind_speed` - WU average (if available)
- `corrected_wind_speed` - Currently just copies model_wind_speed (placeholder)
- **NOTE:** This is a BUG - hyperlocal doesn't use the max-selected wind from collector

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

**Bug/Constraint:** Lines 192-195
```python
# Gusts must be >= sustained wind
if corrected_gust < corrected_wind_speed:
    corrected_gust = corrected_wind_speed
```
**Problem:** `corrected_wind_speed` is just model copy (not the max-selected observed), so this constraint may use wrong value

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

**Also calculated (for reference):**
- **Location:** `weather_collector/processors/wet_bulb.py` lines 39-69
- `weather_data["current"]["wet_bulb"]` - From raw model temp + humidity
- `weather_data["hourly"]["wet_bulb"]` - From raw model temps + humidity (all hours)

---

### Forecast Hours (1-48) Handling

**Backend:** YES - humidity bias applied, temp NOT corrected  
**Location:** `weather_collector/processors/precip_surface.py` lines 139-147

**Formula:**
```python
# For each forecast hour:
hourly_temp = hourly["temperature"][i]  # RAW MODEL (no temp correction)
hourly_humidity = hourly["humidity"][i] # RAW MODEL
humidity_bias = hyp.bias_humidity       # From current hour

# Apply humidity correction only:
corrected_humidity = hourly_humidity + humidity_bias
corrected_humidity = clamp(0, 100, corrected_humidity)

# Calculate wet bulb from raw temp + corrected humidity:
corrected_wet_bulb = calculate_wet_bulb(hourly_temp, corrected_humidity)
```

**Storage:** `weather_data["hourly"]["corrected_wet_bulb"]`

**Note:** This is a PARTIAL correction:
- ✅ Uses corrected humidity (bias applied)
- ❌ Uses raw model temperature (no bias applied)
- This differs from current hour which uses BOTH corrected temp and humidity

**Why temperature not corrected in forecast:**
- Temperature bias is applied in FRONTEND (js/app-main.js), not backend
- Wet bulb is calculated in BACKEND, so it can't access frontend temp corrections
- Only humidity bias is available in backend for correction

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

### Current Hour Calculation

**Location:** `js/app-main.js` lines 3194-3212, 3302-3318

**Method:** Calculate in frontend from corrected inputs

**Formula:**
```javascript
const T = hyp.corrected_temp
const windSpeed = hyp.corrected_wind_speed ?? cur.wind_speed
const RH = hyp.corrected_humidity

// Default: no adjustment
let feelsLike = T

// Wind chill (if T ≤ 50°F and wind > 3 mph)
if (T <= 50 && windSpeed > 3) {
    feelsLike = 35.74 + (0.6215 × T) 
              - (35.75 × windSpeed^0.16) 
              + (0.4275 × T × windSpeed^0.16)
}

// Heat index (if T ≥ 80°F and humidity available)
else if (T >= 80 && RH != null) {
    feelsLike = -42.379 
              + (2.04901523 × T) 
              + (10.14333127 × RH) 
              - (0.22475541 × T × RH)
              - (0.00683783 × T²) 
              - (0.05481717 × RH²) 
              + (0.00122874 × T² × RH)
              + (0.00085282 × T × RH²) 
              - (0.00000199 × T² × RH²)
}
```

**Inputs:**
- ✅ Temperature: `hyp.corrected_temp` (corrected)
- ⚠️ Wind speed: `hyp.corrected_wind_speed` (currently just model copy, not max-selected)
- ✅ Humidity: `hyp.corrected_humidity` (corrected)

**Storage:** NOT stored in data - calculated on-demand in frontend

**For comparison:**
- Model feels like: `cur.apparent_temperature` (from GFS/HRRR, uses raw model inputs)

---

### Forecast Hours (1-48) Handling

**Backend:** Model provides apparent_temperature in hourly data  
**Frontend:** NO correction applied to forecast feels-like

**Storage:** `weather_data["hourly"]["apparent_temperature"]` - raw model values only

**Note:** Unlike temperature which gets bias applied in frontend, feels-like forecast is NOT corrected

---

### Frontend Display Usage

**Right Now Card:**
- **Element:** `#feelsLike`, `#feelsLikeCollapsed`
- **Code:** `js/app-main.js` lines 3214-3216
- **Value:** Calculated from corrected temp + corrected wind + corrected humidity

**Smart Corrections Table:**
- **Elements:** `#scModelFeelsLike`, `#scCorrectedFeelsLike`
- **Code:** `js/app-main.js` lines 3298-3321
- **Values:**
  - Model: `cur.apparent_temperature` (raw model)
  - Corrected: Calculated from corrected inputs (same formula as Right Now)

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
│          HYPERLOCAL PROCESSOR (hyperlocal.py)                │
├─────────────────────────────────────────────────────────────┤
│ Creates weather_data["hyperlocal"] with:                     │
│                                                              │
│ TEMPERATURE:                                                 │
│  • Weighted bias from WU stations                           │
│  • corrected_temp = model + weighted_bias                   │
│                                                              │
│ HUMIDITY:                                                    │
│  • corrected_humidity = WU average (replacement)            │
│  • bias_humidity = WU - model                               │
│                                                              │
│ PRESSURE:                                                    │
│  • corrected_pressure = WU OR KBOS OR model (priority)      │
│                                                              │
│ WIND GUSTS (parallel to collector's max-select):            │
│  • Weighted average from WU stations                        │
│  • corrected_wind_gusts = model + weighted_bias             │
│                                                              │
│ WIND SPEED:                                                  │
│  • corrected_wind_speed = model (PLACEHOLDER - no actual    │
│    correction, should use max-selected from collector)      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│       WET BULB PROCESSOR (wet_bulb.py)                       │
├─────────────────────────────────────────────────────────────┤
│ Creates weather_data["current"]["wet_bulb"]:                 │
│  • From RAW model temp + humidity                           │
│                                                              │
│ Creates weather_data["hourly"]["wet_bulb"]:                  │
│  • From RAW model temps + humidity (all hours)              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│    SURFACE PRECIP PROCESSOR (precip_surface.py)             │
├─────────────────────────────────────────────────────────────┤
│ Creates weather_data["derived"]["corrected_wet_bulb"]:       │
│  • From CORRECTED temp + CORRECTED humidity                 │
│                                                              │
│ Creates weather_data["hourly"]["corrected_wet_bulb"]:        │
│  • From RAW temp + CORRECTED humidity (humidity bias only)  │
│  • NOTE: Temp not corrected in forecast (bias applied in    │
│    frontend, not available here)                            │
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
│  • Wind speed: hyp.corrected_wind_speed (placeholder)       │
│  • Wind gusts: hyp.corrected_wind_gusts (weighted avg)      │
│  • Feels like: CALCULATE from corrected inputs              │
│  • Wet bulb: der.corrected_wet_bulb                         │
│                                                              │
│ 48-HOUR FORECAST DISPLAY:                                    │
│  • Temperature: hourly.temperature + hyp.weighted_bias      │
│    (bias applied here in frontend)                          │
│  • Wind speed: hourly.wind_speed (already blended)          │
│  • Wind gusts: hourly.wind_gusts (already blended)          │
│  • Wet bulb: hourly.corrected_wet_bulb (partial correction) │
│  • Feels like: hourly.apparent_temperature (NO correction)  │
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
- **Backend (current hour):** Max-selects from model + KBVY + WU stations (independently for gusts and sustained)
- **Backend (forecast):** Blends max-selected observed into hourly arrays with 24h linear decay
- **Hyperlocal:** Stores model vs corrected for Smart Corrections display
- **Frontend:** Displays pre-blended forecast values directly
- **Rationale:** User lives in most exposed/windiest location, so max across all sources is a floor, not a ceiling

### Wind Speed and Gust Architecture (v4.30)
- **Collector:** Max-selects from model + KBVY + WU stations independently for both sustained and gusts
- **Collector:** Saves original model values as model_wind_speed and model_wind_gusts before override
- **Hyperlocal:** Passes through collector max-selected values, calculates bias (corrected - model)
- **Frontend:** Displays max-selected values with model comparison in Smart Corrections table
- **Result:** Both sustained and gusts always use highest available reading across all sources

### Partial Correction: Wet Bulb Forecast
- **Uses:** Corrected humidity (bias applied in backend)
- **Doesn't use:** Corrected temperature (bias applied in frontend, not available)
- **Result:** Forecast wet bulb is only partially corrected

### No Correction: Feels-Like Forecast
- **Current hour:** Fully corrected (temp, wind, humidity)
- **Forecast hours:** No correction (uses raw model apparent_temperature)
- **Could improve:** Apply temp bias + humidity bias to calculate corrected forecast feels-like

---

## CORRECTION STATUS MATRIX

| Variable | Current Hour | Forecast (1-48h) | Method | Decay |
|----------|-------------|------------------|--------|-------|
| **Temperature** | ✅ Corrected | ✅ Bias applied (frontend) | Weighted bias | None (flat) |
| **Humidity** | ✅ Corrected | ❌ Raw model | Replacement | N/A |
| **Pressure** | ✅ Best source | ❌ Raw model | Selection | N/A |
| **Wind Speed** | ✅ Max-selected (model+KBVY+WU) | ✅ Blended (backend) | Independent max-select | 24h linear |
| **Wind Gusts** | ✅ Max-selected (model+KBVY+WU) | ✅ Blended (backend) | Independent max-select | 24h linear |
| **Wet Bulb** | ✅ Fully corrected | ⚠️ Partial (humidity only) | Calculated | N/A |
| **Feels Like** | ✅ Fully corrected | ❌ Raw model | Calculated | N/A |

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

### Improvement #3: Wet Bulb Forecast Full Correction
**Current:** Uses raw temp + corrected humidity
**Potential:** Apply temp bias in wet bulb calculation
**Challenge:** Temp bias currently applied in frontend, wet bulb calculated in backend
**Solutions:**
  - Option A: Move temp bias application to backend
  - Option B: Recalculate wet bulb in frontend with both biases
**Complexity:** Medium-High

### Improvement #4: Feels-Like Forecast Correction
**Current:** Uses raw model apparent_temperature
**Potential:** Calculate corrected feels-like for forecast hours
**Method:** Apply temp + humidity biases, use blended wind
**Complexity:** Low - just extend current calculation to forecast hours

---

## VERSION HISTORY

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
