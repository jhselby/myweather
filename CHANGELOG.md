
## v0.5.34 - 2026-05-02
- Fixed: 850mb precip type override now catches all frozen/mixed types (snow, mixed, ice, freezing, sleet) when surface temp > 40°F — was only catching exact "snow" and "heavy snow", letting "Mixed" pass through and producing bogus "mixed rain and snow" forecasts in May

## v0.5.35 - 2026-05-02
- Fixed: precip_surface.py dead code - classify_surface_precip_type never returned rain (missing else branch)
- Fixed: forecast_text.py now uses surface_precip_type (wet bulb based) instead of col_precip_type_850mb as primary precip classifier
- Fixed: 7-day GFS data now gets wet bulb and surface precip type processing (was only getting 850mb)
- Fixed: Days 8-10 simple forecasts now use temp-based precip type instead of hardcoded rain

## v0.5.37 - 2026-05-02
- Fixed: sea_breeze.py now uses corrected hyperlocal temp for land/water differential
- Added: advection fog detection (warm air over cold water with onshore wind) - primary coastal fog type
- fog.py now returns fog_type (radiation vs advection)
