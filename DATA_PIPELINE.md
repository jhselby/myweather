
### v0.5.34 - Precip type surface temp override fix
- `forecast_text.py` `_build_precip_narrative()`: surface temp override now uses keyword matching (`frozen_keywords = ["snow", "mixed", "ice", "freezing", "sleet"]`) instead of exact string matching
- Above 40°F surface temp: all frozen precip types forced to "Rain"
- 35-40°F: snow/ice/sleet forced to "Mixed" (marginal zone)
- Below 34°F: rain forced to "Mixed"
- Root cause: `col_precip_type_850mb` returns "Mixed" at altitude even when wet bulb is 45°F+ at surface; old override only caught "snow"/"heavy snow" exact matches
