## v4.56 • 2026-04-19
* **Tab active state fix**
  * Weather tab no longer incorrectly highlighted when on another tab after refresh
  * Active tab correctly restored from localStorage on page load
  * Removed hardcoded active class from weather tab HTML

## v4.55 • 2026-04-19
* **Ocean tile layout fix**
  * Labels left-aligned, values right-aligned using table layout
  * Wind value no longer wraps to multiple lines

## v4.54 • 2026-04-19
* **Tap outside to close card**
  * Transparent full-screen backdrop captures taps outside expanded cards
  * Consistent with X button behavior, no visual dimming

## v4.53 • 2026-04-19
* **Next Hour precip drawer — honest timing**
  * First tick now shows actual data fetch time (e.g. "10:23am") instead of "now"
  * Summary text adjusted for data staleness — "starting in ~26 min" reflects minutes from now, not from fetch time
  * Rain already-started edge case handled correctly

## v4.52 • 2026-04-19
* **Infrastructure: GCS migration**
  * Collector moved from GitHub Actions to Google Cloud Functions + Cloud Scheduler
  * weather_data.json and frost_log.json now served from GCS bucket (myweather-data)
  * Eliminates force-push conflicts caused by GitHub Actions writing data to repo
  * PWA fetch URL updated to GCS public URL

## v4.51 • 2026-04-18
* **Feels Like card redesign**
  * 48-hour Chart.js line chart with day-labeled x-axis (matches wind/sky pattern)
  * Hover/swipe data bar showing time, feels-like type, and air temp
  * Removed static rows — chart is the UI
* **Bug fixes**
  * Fog emoji (🌫️) replaced with 🌥️ — was rendering as square on all platforms

## v4.50 • 2026-04-18
* **Pirate Weather Integration**
  * Added minutely precip fetcher (61-point, 1-min resolution)
  * Solar irradiance and CAPE stored in weather_data.json
  * Conditional 🌧️ badge in header — appears only when precip expected in next hour
  * Tap badge to open Next Hour drawer with 60-bar minutely chart and plain-language summary
  * Swipe-down or ✕ to dismiss; pulsing blue dot matches alert badge pattern
  * Removed debug console.log noise from collapsed radar map init

## v4.48 • 2026-04-18
- Fix blank card bug on resume: close any open expanded card before refreshing data on visibility change

## v4.47 • 2026-04-17
* **Scoring Display**
  * Dock Day and Sunset Score tile fronts now show score as xx/100
  * Dock Day expanded card inner tiles use opaque white background in light mode for readability
* **Dock Day Scoring**
  * Raised label thresholds to better reflect actual conditions (Great 80+, Good 65+, Marginal 45+, Poor 25+)

## v4.46 • 2026-04-17
* **Feels Like Card**
  * New Hyperlocal card showing current apparent temperature with context-aware label (Wind Chill / Heat Index / Feels Like)
  * Blue tint for wind chill, orange for heat index, neutral otherwise
  * Hourly chart for today showing feels-like vs air temp (dashed)
  * Shows coldest/peak value for today, plus air temp, humidity, and wind inputs
  * "Feels like" on Right Now card is now tappable — navigates directly to Feels Like card

## v4.45 • 2026-04-17
* **Auto-Refresh on Resume**
  * Page now reloads weather data automatically when reopened from background or home screen
* **Expanded Card Backgrounds**
  * Dynamic tile colors (temp, wind, dock day, sunset, sea breeze) now render at full intensity when card is expanded (were washed out at low opacity)
* **Emoji Removal** (continued)
  * Removed remaining emoji from dock day collapsed tile

## v4.44 • 2026-04-17
* **Dock Day Score Refinements**
  * Score now displayed as 1-100 (was 0-1 fraction)
  * Tightened temp curve: below 50°F scores 0 (was 45°F), comfortable range shifted to 65-80°F
  * Raised label thresholds: Great day 80+, Good day 65+, Marginal 45+, Poor 25+

## v4.43 • 2026-04-17
* **Emoji Removal**
  * Removed all decorative and status emojis throughout the app
  * Dock Day Score, Sunset Quality, Sea Breeze, storm flags, and sources status now use color-coded text labels only
  * Frost log severity labels replaced with text (Hard freeze / Frost / Cool)
  * Season, NWS, and settings panel emojis removed
  * 10-day weather condition icons retained (functional)
  * Sun card and overhead tab symbols retained
* **Detail Forecast Tile**
  * Collapsed preview now clamps to 4 lines with ellipsis

## v4.42 • 2026-04-16
* **Wind Impact Unification**
  * Added combined Wind Impact score using threshold logic: sustained wind when below 15 mph, gust impact when sustained wind is 15 mph or higher
  * Weather page now uses a single Wind Impact score across the tile, chart, and Right Now card
  * Hyperlocal sustained and gust impact cards merged into one Wind Impact card with combined headline and separate sustained/gust breakdown
* **Wind Chart Cleanup**
  * Wind data bar condensed to a single-line format
  * X-axis simplified to 6-hour ticks with day labels at midnight
* **Wind Severity Styling**
  * Weather wind tile impact bar now reflects severity color
  * Expanded wind card tint now matches the combined wind impact severity scale
* **Bug Fixes**
  * Fixed combined peak wind impact logic using incorrect units
  * Fixed missing combinedWindImpact function reference
  * Fixed null element errors in fillWorryCard
  * Fixed breakdown rows so sustained and gust scores reflect peak impact over the selected 12/24/36/48h window
## v4.41 • 2026-04-15
* **Sky & Precip Chart Redesign**
  * Sky conditions now painted as per-column background gradients instead of stacked bars
  * Clear days show warm yellow columns, overcast days cool gray, nights deep blue-black
  * Cloud darkening weighted by layer height — low clouds darken most, high cirrus barely affects brightness
  * Precip bars now show only precipitation probability, colored by type (rain/snow/freezing rain/mixed)
  * X-axis simplified to 6-hour ticks; midnight shows day name (Thu, Fri) instead of 12am
  * Y-axis labels embedded in tick suffixes (54°, 50%) instead of rotated axis titles
  * Data bar condensed: short date format, no emojis, shows dominant sky condition (64% sun vs 80% clouds)
* **Radar Modal Polish**
  * Tight single-row header: title + timestamp + play + close in one bar
  * Map toggle button removed
  * CartoDB light/dark vector tiles replace satellite imagery
  * Dark mode automatically switches tile style via MutationObserver
* **Bug Fixes**
  * Fixed fog detail card never called on data load
  * Fixed fog detail ReferenceError (hyp declared after use)
  
## v4.40 • 2026-04-14
* **Planets Tile**
  * "None visible tonight" → "None visible now" (reflects current time, not night forecast)
  * "Visible tonight" label hidden when no planets are currently visible
  * "None visible now" sized to match "Visible now" label for visual consistency

## v4.39 • 2026-04-14
* **Tides Card Redesign**
  * Expanded view replaced with 3-column calendar layout (Today / Tomorrow / next day)
  * High tides highlighted in blue, low tides muted — clear visual hierarchy
  * Next tide marked with ▶ and blue highlight border
  * Tide chart axis labels and grid now theme-aware (dark and light mode)
  * Collector now fetches 3 days / 12 events (was 2 days / 8 events)

## v4.38 • 2026-04-14
* **Corrected Values Audit — Use Corrections Everywhere**
  * Fog detail breakdown now uses corrected temp, humidity, and calculated dew point (Magnus formula)
  * Dew point display and depression spread calculated from corrected temp + humidity
  * Gust impact scores use corrected wind gusts everywhere (was using raw model)
  * Sustained wind scores use corrected wind speed in collapsed wind tile
  * Wind tile collapsed preview shows corrected wind speed and gusts
  * Pressure display uses corrected pressure (hyp.corrected_pressure_in) in Right Now and Wind tile
  * Sea breeze detail land temp shows corrected temperature
  * Dock day hourly temp scoring applies weighted bias to raw hourly temps

* **Alert Modal**
  * Swipe-down to dismiss (touch and mouse drag)
  * Close (✕) button removed — use swipe or tap scrim to dismiss

## v4.37 • 2026-04-14
* **Forecast Temperature Corrections**
  * Today and tomorrow high/low in expanded 10-day card now use corrected hourly temperatures
  * Detailed forecast period header temperature corrected for today and tomorrow
  * Forecast narrative text ("high near X") uses hyperlocal bias-corrected temperature for today and tomorrow

## v4.36 • 2026-04-14
* **10-Day Forecast**
  * Today and tomorrow high/low now use corrected hourly temperatures (bias-adjusted) instead of raw NWS model values

## v4.35 • 2026-04-14
* **UI / Native App Polish**
  * Header now fixed with frosted glass effect matching footer (backdrop blur, same opacity)
  * Storm mode banner removed from header — storm alerts consolidated into alert badge modal
  * Alert modal renamed "Active Alerts" — shows storm flags + NWS alerts in one place
  * Alert badge now activates for storm conditions (2+ flags) as well as NWS alerts
  * Settings icon replaced with standard gear (was brightness/sun icon)
  * Swipe-down to dismiss settings drawer (desktop mouse drag also supported)
  * Settings close (✕) button removed — use swipe or tap scrim to dismiss

* **Settings Cleanup**
  * Pressure unit toggle removed — hardcoded to inHg (standard US consumer default)

* **Tooltips Removed**
  * All data-tip tooltips removed from Weather, Almanac, Hyperlocal, and Overhead tabs

* **Sources / Data Display**
  * 📡 emoji added to Data Sources section in settings
  * Offline stations now display "---" instead of "undefined°F, undefinedmph"

* **Corrections Card**
  * Confidence level removed — station spread displayed instead
  * Bullet separator removed from station count line

## v4.34 • 2026-04-12
* **Card Beautification Pass**
  * Gradient backgrounds now persist into expanded card state (all tabs)
  * Expanded cards show clean title row matching tile label style (no emoji, uppercase)
  * Close button and title share header row — content starts immediately below
  * Removed tooltip dotted underline from hero temperature display

* **Right Now Card**
  * Centered hero area (temp, feels like, condition)
  * Lighter font weights (300 temp, 400 feels-like)
  * Refined row dividers (0.5px) and muted labels

* **10-Day Forecast**
  * Low temperature muted (40% opacity) for visual hierarchy

* **Detailed Forecast**
  * Converted from 2-column grid to inline layout (period + temp, wind, narrative)

* **Dock Day & Sunset Cards**
  * Light mode score colors darkened for readability against gradient backgrounds
  * Dock Day: dark green/gold/red score labels in light mode
  * Sunset: Poor/Fair/Good labels now readable on light backgrounds

* **Corrections Card**
  * Corrected values changed from cyan to dark blue, black override in light mode

* **Sun Card**
  * Hidden large emoji in expanded state

## v4.33 • 2026-04-12
* **Sources moved to Settings Modal**
  * Data Sources and Status now accessible from settings gear icon
  * Collapsible section showing all live data sources and station details

## v4.32 • 2026-04-12
* **Station Network Expansion**
  * Expanded from 15 to 36 WU stations (30 responding, 13 within 1 mile)
  * Removed KMAMARBL17 (consistently failing)
  * Added 22 new stations discovered via API scan
  * Collector run time: 9.1s (only 1s slower than 15 stations)

* **Humidity Display Fix**
  * Current humidity now uses corrected value from hyperlocal

## v4.31 • 2026-04-11
* **Tide Animation Fix**
  * Tide water level now replays correctly when switching to Almanac tab
  * Animation starts from previous tide height (high or low) and animates to current level
  * Fixed stale animation when tab was hidden during initial data load

## v4.29 • 2026-04-11
* **Swipe Navigation**
  * Swipe left/right to page through tabs (Weather, Hyperlocal, Almanac, Overhead)
  * Slide animation on swipe (60px travel, 0.35s ease-out)
  * Ignores vertical scrolls, expanded cards, and map/scrubber interactions

 • 2026-04-11
* **Uniform Tile Heights**
  * Added grid-auto-rows: 192px for consistent tile sizing across all tabs
  * All col-6 tiles now identical height regardless of content
  * Added overflow: hidden on col-6 cards to clip overflowing content

* **Content Scaling for Smaller Tiles**
  * Hyperlocal: Gust/Wind impact numbers 4rem to 3rem, Sea Breeze/Fog 3.5rem to 2.8rem
  * Almanac: Sun status 28px to 18px, Moon 28px to 22px, date/tide/planet text 20px to 16px
  * Ocean card font 20px to 15px with tighter padding
  * Sun/Frost/Dock/Sunset emoji sizes reduced proportionally

* **Wind Tile Fix**
  * Compass SVG shrunk 160px to 120px, padding-bottom 40px to 8px

## v4.27 • 2026-04-11
* **iOS-Style Bottom Tab Bar**
  * Fixed-position bottom nav with 4 tabs: Weather, Hyperlocal, Almanac, Overhead
  * Frosted glass background, active tab label turns blue
  * Constrained to max-width 980px on desktop

* **Header Redesign**
  * Simplified to Wyman Cove title with Marblehead map icon
  * Three SVG icon buttons: alert badge, refresh, settings
  * Transparent/borderless header

* **Settings Modal Sheet**
  * iOS-style slide-up modal replaces inline settings
  * Contains theme toggle, pressure units, version, changelog, data pipeline

* **Alert System Overhaul**
  * Alert badge with pulsing red dot replaces inline alert bar
  * Tapping badge opens alert modal sheet

* **Marblehead Map Icon**
  * CartoDB map tile of Marblehead peninsula as app icon
  * Water tinted blue, red dot marks Wyman Cove

* **Sun Arc Fix**
  * Sun position dot tracks time progress through day
  * Uses actual altitude for y-axis

* **Wind Arrow Improvements**
  * Longer arrow, brighter blue with glow effect
  * Organic wobble animation with prime-number durations

* **Spacing and Animation**
  * Tightened container/header padding and grid gap
  * Animation restart on tab switch

## v4.26 • 2026-04-11
* **Moon Phase Rendering**
  * Replaced emoji moon with canvas-rendered moon phase (scanline algorithm)
  * Canvas moon in collapsed tile (60px) and expanded card (80px)
  * Northern hemisphere view: waxing lit on right, waning lit on left
  * Removed emoji from Right Now card moon phase labels

* **Tile Visual Consistency**
  * **Moon tile**: Canvas moon graphic offset to upper right (matching Sky & Precip pattern)
  * **Sun tile**: Replaced flat SVG with radial gradient sun graphic in upper right
  * **Sun tile**: Separated sun arc/position dot from sun graphic, kept arc centered
  * **Sun tile**: Arc stroke color updated for dark mode visibility
  * **Sun/Moon tiles**: Text sizing matched to Sky & Precip (28px primary, 15px secondary)

* **Bug Fixes**
  * **Ocean tile**: Fixed collapsed wind display (was reading nonexistent wind_speed_kt, now uses wind_mph)
  * **CSS**: Scoped global canvas sizing rule to exclude moon canvases (canvas:not(.moon-canvas))

## v4.25 • 2026-04-10
* **UI/UX Improvements
  * **Tide tile**: Added "NOW: Coming in/Going out, X.X ft" indicator in water showing current tide height and direction
  * **Tide tile**: Added 0 ft reference line at 14.3% for visual orientation
  * **Tide tile**: Increased minimum water height from 5% to 12% ensuring text always visible
  * **Tide tile**: Changed "High/Low Tide" label to "Next: High/Low Tide" for clarity

* Visual Polish
  * **Fog Risk backgrounds**: Replaced linear gradients with layered radial fog clouds (2-4 layers based on risk)
  * **Wind Impact backgrounds**: Updated calm/light colors from green to blue (matches temp-cool)
  * **Wind Impact backgrounds**: Enhanced strong wind color to orange-red (255,140,60)
  * **Sea Breeze backgrounds**: Smoother color progression, brighter teal for likely (80,220,230)
  * **Sunset Quality backgrounds**: Increased contrast - spectacular now 255,100,50 at 30%/20%
  * **Dock Day backgrounds**: Changed scale from green→red to blue→red (great = 96,165,250)

* Performance
  * **NWS Forecast fetcher**: Disabled (was unused - card hidden in UI, using custom forecasts instead)
  * Saves ~1-2 seconds on every 15-minute collector run

* Data Sources
  * Removed NWS Forecast from sources list (fetcher disabled)

## v4.24 • 2026-04-07
* **Hyperlocal & Almanac tile redesign - 14 collapsed previews redesigned** - New centered layouts with clean 20px regular-weight text matching Detailed Forecast aesthetic
* **Corrections tile** - Shows station count and confidence level as simple teaser ("13 stations • Moderate")
* **Wind Impact tiles (Gust & Sustained)** - Large centered score number, label, and wind data with color-coded gradients (green calm → red severe)
* **Sea Breeze tile** - Large percentage with label and time, teal gradient based on likelihood
* **Sunset Score tile** - Shows next sunset (today or tomorrow after civil dusk) with day label, weather icon, and score with gradient
* **Dock Day tile** - Day label, emoji, and condition label with score-based gradient
* **Fog Risk tile** - Large percentage and risk label with fog overlay gradient (increases with risk level)
* **Today Almanac tile** - Date, day, and sunrise/sunset times with daylight duration
* **Tides tile** - Animated water fill showing current tide height, fills/drains from last tide event on page load, gentle wave slosh animation, overlaid next tide info
* **Ocean/Buoy tile** - 3-row mini table (Water temp, Waves, Wind) in 20px text
* **Sun tile** - Arc with moving dot showing sun position based on altitude, altitude display, next event (sunrise/sunset)
* **Moon tile** - Dynamic phase emoji, phase name, illumination percentage
* **Planets tile** - Realistic SVG planets (simple spheres with radial gradients, Saturn with rings) replacing Unicode symbols, shows visible planet icons/names or "None visible tonight"
* **Frost tile** - Snowflake emoji, days since frost, last year comparison
* Fixed collapsed radar map rendering bug - Map now properly resizes when switching to Weather tab (no longer requires manual refresh)
* All Hyperlocal/Almanac tiles use consistent 20px font-weight 400 style
* All tiles have subtle background gradients matching their data state (fog levels, wind impact, sea breeze likelihood, sunset quality, dock conditions)

## v4.23 • 2026-04-07
* **Radar tile dark mode optimization** - Replaced dynamic Leaflet map with static Mapbox background image for better performance and consistent rendering
* Fixed radar tile dark mode appearance - now properly darkened to match theme while maintaining land/sea contrast
* Fixed radar tile title positioning and border visibility in dark mode
* Eliminated Leaflet tile loading race conditions and theme detection issues

## v4.22 • 2026-04-07
* **Weather page tile redesign - all 6 collapsed previews redesigned** - New collapsible tile/modal architecture with distinctive card-collapsed-preview designs
* **Right Now tile** - Centered layout with large temperature (68px), thermometer graphic with animated mercury level, "Feels like" below
* **Sky & Precip tile** - Sky visualization, sky condition text, precipitation and cloud percentage
* **Wind tile** - Centered compass rose background (80×80px at 0.3 opacity), large sustained speed with small "mph" to right, gusts below, compass arrow shows wind direction, impact bar at bottom
* **10-Day tile** - Large high/low temperatures centered with "High / Low today" label
* **Detailed Forecast tile** - First sentence from current NWS forecast period with "..." to invite expansion
* **Radar tile** - Animated Leaflet map showing MA coastline with CartoDB Positron light base map, subtle green radar aesthetics (range rings at 15/30/60/90 miles, rotating sweep line, pulsing center dot at Marblehead), zoom level 10, fills entire tile edge-to-edge
* All collapsed previews now have consistent "TITLE" labels in upper-left, positioned absolutely at top:0/left:0
* Tiles fill entire card area with no white background showing (matching Right Now and Sky & Precip colored backgrounds)


## v4.23 • 2026-04-07
* **Radar tile dark mode optimization** - Replaced dynamic Leaflet map with static Mapbox background image for better performance and consistent rendering
* Fixed radar tile dark mode appearance - now properly darkened to match theme while maintaining land/sea contrast  
* Fixed radar tile title positioning and border visibility in dark mode
* Eliminated Leaflet tile loading race conditions and theme detection issues


## v4.21 • 2026-04-05
* Alert toggle positioning fixed - Changed justify-content from flex-start to space-between for better chevron alignment

## v4.20 • 2026-04-05
* **Right Now card navigation improved** - Clicking links from Right Now card (Wind Impact, Sea Breeze, Fog Risk, etc.) now switches to Hyperlocal tab to open the target card, then returns to Weather tab with Right Now card still open when closed
* Right Now card sunset score now reads directly from rendered sunset card instead of relying on global variable

## v4.19 • 2026-04-05
* **Right Now card sunset score fixed** - Now reads from rendered sunset card instead of global variable that wasn't being set for overcast/clear-sky conditions

## v4.18 • 2026-04-04
* **Warmup optimization** - Warmup call now uses single attempt (no retry) to reduce total collection time by ~60 seconds
* Warmup still establishes connection for Day 0 even if it times out

## v4.17 • 2026-04-04
* **Sunset Day 0 warmup improved** - Added dummy Day 6 fetch to establish API connection before Day 0 data collection
* This warms the connection without risking Day 0 data if warmup times out

## v4.16 • 2026-04-04
* **Sunset data collection reliability improved** - Added retry logic with 10-second backoff for timeout failures, plus increased API timeout from 30s to 60s
* **Sunset score now works with partial data** - If some distance measurements fail, estimates missing values from available data instead of showing "No data"
* API requests that timeout are automatically retried once after 10 seconds before failing

## v4.15 • 2026-04-04
* **Sunset data collection reliability** - Added warmup API call to establish connection before fetching directional cloud data (later replaced by retry logic in v4.16)

## v4.14 • 2026-04-04
* **Smart Corrections table unified** - Removed distinction between "Metric" and "Derived" sections
* **Added Bias column for derived values** - Dew point, wet bulb, feels like, and precip type now show calculated bias
* Precip type bias shows "Changed" when correction differs from model, "--" when same

## v4.13 • 2026-04-04
* **Wet bulb forecast accuracy** - 48-hour wet bulb now calculated with BOTH corrected temperature and corrected humidity (previously only humidity was corrected)
* Added calculateWetBulb() function to frontend for accurate psychrometric calculations using Stull's formula
* Tested and validated build.py cache-busting system

## v4.12 • 2026-04-04
* **Automated cache-busting build system** - Added build.py script to generate content hashes for JS/CSS files
* **DATA_PIPELINE.md reference document** - Comprehensive documentation of all data sources, processors, and correction algorithms
* Added Data Pipeline Reference section to settings panel for easy access to technical documentation

## v4.11 • 2026-04-03
* **Wind corrections** - Improved sustained wind and gust correction algorithms
* **48-hour chart data bars improved** - Better visualization of precipitation and cloud data
* **Header cleanup** - Streamlined header layout and styling

## v4.9 • 2026-04-03
* **Fixed hyperlocal navigation from Right Now card** - Clicking hyperlocal links (Sunset, Dock, Wind Impact, etc.) now properly navigates without leaving page unresponsive
* **Fixed card interaction** - Restored guard preventing cards from closing when clicking content inside expanded cards (only X button closes)

## v4.8 • 2026-04-03
* **Eliminated duplicate calculations in Right Now card** - Sunset and Dock scores now read from their respective cards instead of recalculating
* **All impact scores now use unified 1-100 scale** for consistency
  * Wind Impact: 1-100 (previously unbounded)
  * Gust Impact: 1-100 (previously unbounded)
  * Sunset Quality: 1-100 (previously 0.00-1.00 decimal)
  * Dock Day Score: 1-100 (previously 0.00-1.00 decimal)
* All scores display as whole numbers without decimals

## v4.7 • 2026-04-03
* **CRITICAL**: Chart temperature line now uses corrected HRRR data (model + hyperlocal bias) instead of raw model temperatures
* **CRITICAL**: Precip type coloring on chart now uses corrected temperatures for freezing rain detection
* **CRITICAL**: Today's high/low calculated from corrected hourly temps instead of timing-out ECMWF daily endpoint
* **CRITICAL**: Gust floor bug - corrected gusts can no longer be less than corrected sustained wind speed
* Sunrise/sunset times now display in 12-hour format (e.g., "6:22 AM" instead of "06:22")
* All tiles now start closed on page load (localStorage no longer restores previous state)
* Only one tile can be open at a time (opening a tile closes all others)

# Weather App Changelog
## v4.6 • April 2, 2026
* Collapsible tile system - all cards now col-6 tiles that expand to modal overlays
  * 20+ cards converted: Weather (7), Hyperlocal (7), Almanac (7)
  * Tiles show preview data when collapsed (current conditions, scores, next events)
  * Click tile to expand to full-screen modal with close button (X)
  * State persists in localStorage across sessions
* Preview data improvements:
  * Right Now: Temperature + Feels Like
  * Sky & Precip: Condition emoji + POP/clouds/clear breakdown
  * Wind: Current sustained + gust impact scores with speed/direction
  * Tides: Next tide (High/Low) with 12-hour time + height
  * Sun: Next event (Sunrise/Sunset) with 12-hour time
  * Sea Breeze, Sunset Quality, Dock Day: Current scores + status
  * Ocean, Fog, Frost, Moon, Planets: Current data
* 10-Day Forecast: Days no longer clickable (removed detail view expansion)
* Time format: All tide and sun times now display in 12-hour format with AM/PM
* Tile design: Uniform 140px height, centered titles + data, compact spacing
* Fixed: Duplicate `const today` declaration in renderTides
* Fixed: UTC vs local date bug for tide "next event" calculation
* Renamed: "CORRECTIONS" → "OBSERVATION-BASED CORRECTIONS"
* Code: toggleCard(), initCollapsibleCards(), modal-backdrop CSS

## v4.5 • April 2, 2026
* Prototype: Collapsible tile system (single card proof-of-concept)
  * Converted one card to col-6 tile that expands to modal overlay
  * Implemented toggleCard() function and modal backdrop
  * localStorage persistence for open/closed state
  * Foundation for v4.6 full rollout

## v4.4 • April 1, 2026 - NEXRAD Radar Upgrade**
*  Switched radar source from RainViewer to IEM NEXRAD WMS
  * 5-minute update intervals (vs RainViewer's 10-minute)
  * 24 frames = 2 hours of radar history
  * Higher quality NOAA NEXRAD base reflectivity composite
* Fixed animation smoothness: crossfade between frames
  * Old radar layer stays visible until new frame fully loads
  * Tracks tile loading state to prevent blank gaps during playback
  * No more choppy transitions or disappearing radar data
* Updated Sources page: "IEM NEXRAD" attribution
* Code locations:
  * Radar implementation: `js/app-main.js` lines ~2315-2520
  * WMS endpoint: `https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0r-t.cgi`
  * Layer: `nexrad-n0r-wmst` (time-enabled)

## v4.3 • April 1, 2026
* UI consistency improvements: standardized card collapse patterns
* Radar card: moved controls (timestamp, play/pause, map toggle) inside card body
* Wind Impact cards: moved time window pills (12h/24h/36h/48h) inside card body
* All collapsible cards now have clean titles when collapsed, controls visible only when expanded
* Flight tracker: selected aircraft now reverts to altitude-based color when detail panel closes
* Fixed bug where clicked planes stayed highlighted (red) after closing details

## v4.2 • March 31, 2026
* Chart sky colors redesigned for visual accuracy
* Clear sky: yellow (sun) during day, dark blue/black at night, subtle orange at dawn/dusk
* Cloud bars: weighted blend of low/mid/high cloud layers
  * High clouds: light gray (wispy)
  * Mid clouds: medium gray
  * Low clouds: dark gray (blocking)
  * Night clouds: blue-tinted gray
* Legend updated to reflect new color scheme

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

## v4.12 • April 4, 2026
* Added DATA_PIPELINE.md technical reference documentation
* Moved CHANGELOG.md to docs/ folder
* Added Data Pipeline Reference section to header
* Created build.py automated cache-busting system
* Moved wu_scraper_realtime.py to weather_collector/fetchers/
* Updated .gitignore with cache file exclusions
* Fixed wu.py to import scraper as module instead of subprocess

## v4.21 - UI fixes
- Fixed chart data bar text alignment (date and data now properly aligned)
- Fixed alert Show/Hide toggle positioning (now consistently on far right)

## v4.21 - UI fixes
- Fixed chart data bar text alignment (date and data now properly aligned)
- Fixed alert Show/Hide toggle positioning (now consistently on far right)


## v4.57 • 2026-04-19
* **Hair Day Card (Hyperlocal tab)**
  * New col-6 card scoring current hair conditions 0–100
  * Five weighted factors: humidity (40%), dew point spread (25%), wind (15%), rain chance (10%), UV index (10%)
  * Uses hyperlocal-corrected temp/humidity where available
  * Collapsed preview shows emoji, label, and score
  * Labels: Great hair day / Good hair day / Manageable / Frizz risk / Bad hair day / Stay inside

## v4.57 • 2026-04-19
* **Hair Day Card (Hyperlocal tab)**
  * 3-day horizontal layout matching Sunset/Dock Day style
  * Today uses hyperlocal-corrected values; Tomorrow and Day After use daytime hourly averages (7am–8pm)
  * Scored 0–100: humidity (40%), dew point spread (25%), wind (20%), rain chance (15%)
  * Each column shows date, emoji, score label, score/100, progress bar, and 4 data rows
  * Collapsed preview shows today's emoji, score label, and score

## v4.58 • 2026-04-19
* **UX polish (roadmap easy wins)**
  * Frost Log: explicit empty state when no frost events recorded this season
  * Collapsed tiles: hover lift + cursor affordance to signal interactivity
  * Escape key closes any expanded card modal

## v4.60 • 2026-04-19
* **Sunset headline sentence**
  * Plain-English summary above day grid ("Good sunset tonight — clear horizon, low humidity")
  * Matches headline pattern from Hair Day, Dock Day, Sea Breeze, Fog cards
