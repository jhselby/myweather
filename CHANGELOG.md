# Weather App Changelog
## v4.1 • March 31, 2026
* Tab reorganization: Hyperlocal moved to second position (Weather → Hyperlocal → Almanac → Overhead → Sources)
* Renamed "Hyperlocal Corrections" tab to "Hyperlocal", card to "Smart Corrections"
* Renamed "Wyman Cove Detailed Forecast" to "Detailed Forecast"
* Renamed "48-Hour Temperature & Precipitation" to "48-Hour Temperature, Precipitation & Sky"
* Moved Sunset Quality Forecast and Dock Day Score cards from Almanac to Hyperlocal tab
* Added new Fog Risk card to Hyperlocal tab with calculation breakdown (dew point spread + humidity + wind)
* Right Now card: Added Sunset Score and Dock Day Score with today's values
* Right Now card: Consolidated Wind/Sustained Impact and Gusts/Gust Impact into two combined rows
* Right Now card: 6 hyperlocal fields now tappable/clickable, linking directly to detailed cards in Hyperlocal tab
* Wind Impact/Gust Impact format: Score and severity level shown first, followed by direction and speed
* Chart hover improvements: Wind chart direction moved to second line, Temp/Precip/Sky chart reorganized (Temp/POP/Type line 1, Sky data line 2)
* Fix: Precipitation type now matches bar colors at all POP levels (removed 5% threshold), shows "None" only when POP = 0%
* Fix: Radar initialization on page load when card state remembered as open
* Fix: Fog Risk card now populates correctly (moved render call to proper section)
* Navigation: Tappable hyperlocal links use smooth scroll and auto-open target cards
* CSS: Added hyperlocal-link styling with hover effects and chevron indicators


## v4.0 • March 31, 2026
* MAJOR: Comprehensive hyperlocal correction system - all derived values now use corrected data
* Corrected wet bulb calculation from corrected temp + humidity (current + 48h forecast)
* Hybrid precipitation type classification using corrected wet bulb + 850mb temp (catches freezing rain)
* Corrected feels like calculation (wind chill + heat index from corrected values)
* Corrected dew point calculation from corrected temp + humidity
* Today's high/low now calculated from corrected hourly temps (not model daily values)
* Wind gust corrections blended into 48h forecast (100% at current hour, declining to 0% at hour 24)
* Tab reorganization: removed Wind and Radar tabs, created Hyperlocal Corrections tab
* Hyperlocal Corrections tab card order: main correction tables first, then wind impacts, sea breeze
* Renamed "Smart Correction" card to "Hyperlocal Corrections" - removed duplicate confidence from title
* Removed redundant Conditions & Diagnostics card
* Updated all tooltips to reflect corrected methodology
* Chart now uses corrected wet bulb for precipitation type coloring
* Right Now card field reorder: wind metrics grouped together (sustained + impact, gusts + impact)

## v3.18 • March 30, 2026
* Fix plane icon rotation: corrected for eastward-pointing default orientation
* Aircraft now point in correct direction based on track heading


## v3.17 • March 29, 2026
* Flight tracker route validation: trajectory analyzer flags stale/incorrect routes from adsbdb cache
* Route validation uses position (cross-track distance) and heading alignment checks
* Near-airport exemption (<100nm) prevents false positives during departure/arrival
* FlightAware verification link added to all commercial flight routes
* Private aircraft detection: GA/private flights show "Private — no route data" in large bold text
* Selected aircraft highlighting: clicked plane turns magenta, previous selection returns to altitude color
* Alert visibility fix: weather alerts now hidden on Almanac/Overhead/Sources tabs
* Single alert display: removed redundant summary bar when only one alert active
* UI cleanup: removed duplicate refresh button from overhead controls

## v3.16 • March 28, 2026
* Beefed up airplane data popup with distance, vertical rate, and bearing
* Reformatted airplane info: "Airline • Flight#" format, added full city names to routes
* Fixed light mode contrast issues across multiple sections
* Fixed wind chart legend wrapping and increased route text size

## v3.14 • March 26, 2026
* Fix missing tail hours in wind/temp charts by using Open-Meteo seamless model blending
* Ensures full 48-hour forecast display without data dropoff at end of timeframe

## v3.13 • March 26, 2026
* Add Overhead tab - live aircraft tracker showing planes visible from property
* Mapbox-based map with lazy initialization (loads only when tab opened)
* Manual refresh button, zoom level 12 for ~15mi radius view
* Safari-compatible plane markers (text variant ✈︎)
* Fix Today card alignment issues
* Scope fixes for tab initialization

## v3.12 • March 26, 2026
* Add sky condition bars to 48-hour temperature/precipitation chart
* Shows clear/partly/mostly/overcast cloud layers as stacked bars
* Fix wind data dropoff at end of forecast window
* Trim past hours from chart display (now shows current hour forward)

## v3.11 • March 26, 2026
* Fix horizontal page drift on mobile when touching/sliding across chart
* Add touch-action CSS to prevent unwanted page scroll during chart interaction
* Mobile UX improvement for chart data bar interaction

## v3.10 • March 26, 2026
* Consolidate temp/precip chart data bar into single responsive line
* Shows: Temp | POP | Cloud % | Clear % | Type in one formatted line
* Data bar appears on click, updates on hover, closes with X button
* Replaces previous 3-column grid layout

## v3.5 • March 21, 2026
* Wind forecast improvements: max(KBVY, WU) for current conditions
* Extract wind gusts from KBVY METAR (Aviation Weather API)
* Blend observed wind into hourly forecast (24hr decay curve)
* Lower wind impact thresholds for waterfront exposure (10/16 vs 12/20)
* Fixes underreported gusts in impact cards, graphs, and forecast text

## v3.4 • March 21, 2026
* Fix NWS temperature fallback IndexError in forecast generator
* Prevents crashes when NWS data is incomplete

## v3.3 • March 21, 2026
* Wind chart redesign: axis swap (time horizontal, speed vertical)
* Wind chart: labeled worry zones with gradient color fills
* Wind chart: legend shows current + peak worry levels with time labels
* Wind chart: switched from stacked bar to grouped bar layout
* Fix: duplicate "Calm" label in worryLevel function

## v3.2 • March 21, 2026
* Add morning/afternoon cloud split for accurate sky narratives
* Fix fog handling: precipitation now primary, fog as modifier
* Fix precipitation probability thresholds (90%+ drops qualifiers)
* Fix RIGHT NOW card to show smart-corrected temperature
* Fix 10-day forecast missing temperature data
* Fix multiple JS errors in forecast rendering

## v3.1 • March 21, 2026
* NWS NBM gridpoint integration (replaced GFS surface data)
* Fix precipitation likelihood qualifiers (added "likely", "chance of", "slight chance of")
* Fix surface temperature validation for precipitation type
* NWS temperatures and weather conditions now override GFS/HRRR
* Prevents physically impossible forecasts (heavy snow at 40°F)
* Add 850mb precipitation type classifier (Rain/Mixed/Snow/Heavy snow)
* Wet bulb temperature display in Conditions card (shown when PoP ≥ 20%)
* 850mb precip type only calculated when PoP ≥ 20%

## v2.72–v2.77 • March 16–18, 2026
* Sea breeze detector with detailed analysis card and likelihood scoring
* Terrain-based wind exposure table from contour map analysis
* Wind impact cards restructured with forward-looking peak windows (12/24/36/48h)
* Current impact scores added to wind cards
* Trough signal processor for 850mb height tendency
* ASOS condition override and fog risk calculation
* Dewpoint depression display and meteorological seasons

## v2.70–v2.71 • March 16, 2026
* 48-hour wind chart: swapped axes, color gradient zones, forward-looking impact scores
* Fix wind exposure table using actual fetch measurements

## v2.66–v2.69 • March 15, 2026
* Major refactor: split monolithic collector.py into modular package (fetchers/, processors/)
* Separate processors for fog, frost, hyperlocal, pressure, sea breeze, trough, wet bulb, wind risk
* Buoy wind data added; KBOS/KBVY migrated to new Aviation Weather API
* NWS alerts simplified format with proper URLs
* 48-hour charts now start from current hour instead of midnight
* Feels-like temp fixed to use apparent_temperature

## v2.5 • February 23, 2026
* Smart hyperlocal correction: distance + elevation weighted bias
* Quality filtering: reject stale data (>30 min) and outliers (>2σ)
* Station diagnostics: used/total count, effective radius, confidence level
* Model correction instead of replacement (respects grid precision)

## v2.2 • February 21, 2026
* Light / dark / system theme toggle
* Pressure unit switching (hPa / inHg)
* Today almanac card (day of year, season countdown, daylight change)
* Solar System Now — honest "above horizon" wording, clearer tile contrast
* Wind impact pill wrapping fix on mobile
* Light mode: comprehensive inline color overrides throughout
* Version + changelog moved to settings

## v2.0 • February 2026
* 10-day forecast with NWS integration and day selection
* Mobile responsive layout (1-column stacking, horizontal scroll)
* Gust & sustained wind impact cards with time windows
* Frost & freeze tracker with season stats
* Dock Day Score with tide-window scoring
* Sunset Quality forecast card
* RainViewer radar with nowcast frames
* Settings panel (gear icon)

## v1.0 • Late 2025
* Initial build: multi-model weather, tides, buoy, NWS alerts
* Multi-tab layout (Weather / Wind / Almanac / Radar / Sources)
* KBOS / KBVY / PWS observed conditions
