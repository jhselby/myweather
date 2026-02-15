# Wyman Cove Weather Station

Hyperlocal weather monitoring for Marblehead waterfront using 100% FOSS data sources. Updates automatically every 15 minutes via GitHub Actions.

## Live Site

View at: `https://yourusername.github.io/myweather/`

## Data Sources

All free, open, and require no API keys:
- **Open-Meteo** - 10-day forecast with hourly resolution
- **Castle Hill PWS** (KMAMARBL63) - Hyperlocal current conditions
- **NOAA Tides** - Salem station (8442668)
- **NWS Alerts** - Active weather warnings

## Features

- **Current Conditions** - Temperature, feels-like, wind, pressure, humidity
- **Hyperlocal Comparison** - Castle Hill PWS vs. Open-Meteo model
- **Active Alerts** - NWS warnings prominently displayed
- **10-Day Forecast** - Daily high/low, conditions, precipitation
- **48-Hour Charts** - Temperature, precipitation, wind speed/gusts
- **Tides** - Next 4 high/low predictions
- **Sun/Moon** - Sunrise/sunset, daylight duration

## How It Works

GitHub Actions runs `collector.py` every 15 minutes:
1. Fetches data from all sources
2. Generates `weather_data.json`
3. Commits and pushes to repo
4. GitHub Pages serves updated `index.html` + JSON

Zero infrastructure needed - 100% automated on GitHub.

## Setup (Already Done)

This repo is configured and running. GitHub Actions handles everything automatically.

To modify update frequency, edit `.github/workflows/update-weather.yml` and change the cron schedule.

## Customization

### Change Location
Edit `collector.py`:
```python
LAT, LON = 42.5014, -70.8750  # Your coordinates
LOCATION_NAME = "Your Location Name"
```

### Change Update Frequency
Edit `.github/workflows/update-weather.yml`:
```yaml
schedule:
  - cron: '*/15 * * * *'  # Every 15 minutes
```

## Future Enhancements

- Add your own PWS for truly hyperlocal Wyman Cove data
- NOAA Marine buoy data (offshore conditions)
- EPA AirNow (air quality)
- Historical data tracking

## License

MIT License

## Data Credits

- Open-Meteo (https://open-meteo.com) - CC BY 4.0
- NOAA (https://tidesandcurrents.noaa.gov) - Public Domain
- NWS (https://api.weather.gov) - Public Domain
- Weather Underground PWS Network - Public observations
# myweather
16 Indianhead Circle, Marblehead, MA 01945
