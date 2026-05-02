
## v0.5.34 - 2026-05-02
- Fixed: 850mb precip type override now catches all frozen/mixed types (snow, mixed, ice, freezing, sleet) when surface temp > 40°F — was only catching exact "snow" and "heavy snow", letting "Mixed" pass through and producing bogus "mixed rain and snow" forecasts in May
