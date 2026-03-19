# Weather App Changelog

## Recent Updates (March 10-19, 2026)

### Data Collection & Processing
- **Added wet bulb temperature calculation** - Calculates wet bulb temp for every hour in forecast to improve precipitation type classification (snow/mixed/rain thresholds: ≤32°F/32-35°F/>35°F)
- **Added 850mb temperature extraction** - Classic forecaster's tool for rain/snow discrimination; surfaces when PoP ≥ 20%
- **Added 850mb precip type classification** - Classifies precip as snow/mixed/rain based on 850mb temp thresholds (≤0°C/0-3°C/>3°C)
- **Added sea breeze detection** - Detects sea breeze probability based on land-water temperature differential, wind conditions, and time of day; displays percentage, temp delta, wind direction/speed
- **Added pressure tendency tracking** - 3-hour pressure change detection with fallback chain: KBOS observed → buoy 44013 → model forecast
- **Added fog risk calculation** - Combines dewpoint depression, cloud cover, wind, and visibility data to estimate fog probability
- **Fixed frost tracker** - Restored season-to-date freeze counters (freeze_days, hard_freeze_days, severe_days) with historical backfill from Open-Meteo; added frost_log.json to git workflow
- **Added ASOS condition overrides** - Uses KBOS/KBVY observed conditions to override model forecast when observations show fog/mist/drizzle/freezing conditions
- **Improved Weather Underground PWS selection** - Added realtime validation: filters out stale stations (>2h old), validates temperature sanity (≥-40°F, ≤130°F), prioritizes Marblehead stations, sorts by distance

### UI Improvements
- **Redesigned wind impact display** - Removed redundant "Level" row; renamed "Current" to "Current Impact" (score + severity on one line); renamed "Impact Score" to "Peak Impact (next Xh)" with dynamic time window
- **Added wind impact scores to 48-hour wind chart** - Dual-axis overlay showing sustained (purple) and gust (red) impact scores alongside raw wind forecast; added color-coded impact zones (Calm/Breezy/Notable/Strong/Severe/Extreme)
- **Added wind speed color legend** - Visual guide showing color coding for different wind speeds
- **Fixed sea breeze text wrapping** - Shortened display to icon + percentage + temp delta + compass direction + wind speed to prevent overflow on iPhone
- **Fixed charts to start at current hour** - Both temperature/precip and wind charts now begin at the current hour rather than midnight for better relevance
- **Added compass direction conversion** - Sea breeze module now converts degrees to 16-point compass (N, NNE, NE, etc.)
- **Fixed dewpoint display bug** - Corrected stray `<` character from double `<<div` typo and missing space between spans
- **Fixed feels-like temperature** - Changed from non-existent `cur.feels_like` to `cur.apparent_temperature`
- **Added wet bulb temp display row** - Conditional display (shown when PoP ≥ 20%) with tooltip explaining significance for precip type
- **Added 850mb precip type display row** - Conditional display showing snow/mixed/rain classification when PoP ≥ 20%

### Wind Exposure & Scoring
- **Rebuilt wind exposure table using terrain analysis** - Maximum exposure (1.00) from 320-25° (open harbor to north); heavy blocking from 45-260° due to terrain rising 18-57 ft around property bowl; replaces initial estimated values with contour-map-derived factors
- **Fixed wind impact card data source** - Cards now look at forward-looking windows (e.g., "next 12h") instead of incorrectly using past data
- **Fixed wind worry score calculation** - Now starts peak calculations from current hour index rather than including historical data

### Data Sources & API Integration
- **Improved NWS alerts** - Fixed key mismatch (`nws_alerts` → `alerts`); transformed raw API response to simplified structure with proper URLs (event/headline/description/severity/onset/expires/url fields)
- **Fixed wind chart 2H pressure trend** - Corrected frontend reference from `pressure_trend_hpa_2h` to `pressure_trend_hpa_3h` to match actual data field

### Code Structure & Workflow
- **Refactored to modular architecture** - Migrated from single `collector.py` to organized `weather_collector/` package with separate modules for fetchers, processors, and config
- **Added GitHub Actions concurrency guard** - Prevents simultaneous workflow runs from causing merge conflicts on `weather_data.json`
- **Improved git workflow** - Added `frost_log.json` to automated commits; documented correct sequence for handling Actions-committed data files

### Version History
- v2.78 - Latest (wet bulb + 850mb precip type + sea breeze wrapping fix)
- v2.72 - Terrain-based wind exposure table
- v2.70 - Wind impact chart redesign with dual-axis scores
- v2.69 - Wind impact scores, NWS alert fixes, chart timing fixes
- v2.67-2.68 - Bug fixes and enhancements

---

## Pending / Next Steps
See TODO.md for planned improvements including:
- Additional atmospheric data (CAPE, freezing level, precipitable water, cloud base height)
- Wave period data
- Wind gust forecast
- Fog dissipation timing
- Freezing rain risk score
- Documentation of Impact Score and Dock Days methodology
