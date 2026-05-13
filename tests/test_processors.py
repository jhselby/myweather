"""
Tests for weather_collector processors.
Run with: python3 -m pytest tests/ -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weather_collector.processors.fog import calculate_fog_risk
from weather_collector.processors.wet_bulb import calculate_wet_bulb
from weather_collector.processors.sea_breeze import detect_sea_breeze


# ── Fog ──────────────────────────────────────────────────────────────────────

class TestFogRisk:

    def test_no_risk_large_spread(self):
        # 20°F spread, no coastal conditions → no fog
        result = calculate_fog_risk(70, 50, 60, 5)
        assert result["fog_label"] == "No risk"
        assert result["fog_probability"] == 0

    def test_radiation_fog_likely(self):
        # Near-saturated, calm winds → likely
        result = calculate_fog_risk(55, 53, 95, 2)
        assert result["fog_probability"] >= 70
        assert result["fog_label"] == "Likely"
        assert result["fog_type"] == "radiation"

    def test_radiation_fog_dispersed_by_wind(self):
        # Near-saturated but strong wind → lower probability
        calm = calculate_fog_risk(55, 53, 95, 2)
        windy = calculate_fog_risk(55, 53, 95, 15)
        assert windy["fog_probability"] < calm["fog_probability"]

    def test_advection_fog_fires_with_large_spread(self):
        # 70°F air, 50°F water, SE wind, humid — advection fog should fire
        # even though spread (70-60=10°F) would normally rule out radiation fog
        result = calculate_fog_risk(
            temperature_f=70, dew_point_f=60, humidity_pct=85,
            wind_speed_mph=8, wind_direction=150, water_temp_f=50
        )
        assert result["fog_type"] == "advection"
        assert result["fog_probability"] > 0
        assert result["fog_label"] != "No risk"

    def test_advection_fog_requires_onshore_wind(self):
        # Same conditions but offshore wind (270° W) → no advection fog
        onshore = calculate_fog_risk(70, 60, 85, 8, wind_direction=150, water_temp_f=50)
        offshore = calculate_fog_risk(70, 60, 85, 8, wind_direction=270, water_temp_f=50)
        assert onshore["fog_probability"] > offshore["fog_probability"]

    def test_advection_fog_requires_warm_air_over_cold_water(self):
        # Air cooler than water → no advection fog
        result = calculate_fog_risk(
            temperature_f=50, dew_point_f=45, humidity_pct=85,
            wind_speed_mph=8, wind_direction=150, water_temp_f=60
        )
        assert result["fog_type"] == "radiation"

    def test_returns_none_on_missing_inputs(self):
        assert calculate_fog_risk(None, 50, 80, 5) is None
        assert calculate_fog_risk(70, None, 80, 5) is None


# ── Wet Bulb ─────────────────────────────────────────────────────────────────

class TestWetBulb:

    def test_wet_bulb_below_dry_bulb(self):
        # Wet bulb is always ≤ dry bulb
        wb = calculate_wet_bulb(70, 50)
        assert wb < 70

    def test_wet_bulb_equals_dry_bulb_at_100pct(self):
        # At 100% RH wet bulb = dry bulb
        wb = calculate_wet_bulb(60, 100)
        assert abs(wb - 60) < 1.0

    def test_snow_threshold(self):
        # 28°F, 90% RH → wet bulb well below freezing → snow
        wb = calculate_wet_bulb(28, 90)
        assert wb <= 32

    def test_rain_threshold(self):
        # 50°F, 80% RH → wet bulb above freezing → rain
        wb = calculate_wet_bulb(50, 80)
        assert wb > 32

    def test_returns_none_on_missing_inputs(self):
        assert calculate_wet_bulb(None, 80) is None
        assert calculate_wet_bulb(70, None) is None


# ── Sea Breeze ────────────────────────────────────────────────────────────────

class TestSeaBreeze:

    def _make_data(self, land_temp, water_temp, wind_speed, wind_dir, hour=14):
        """Build a minimal weather_data dict for sea breeze detection."""
        import unittest.mock as mock
        import pytz
        from datetime import datetime

        data = {
            "current": {
                "temperature": land_temp,
                "wind_speed": wind_speed,
                "wind_direction": wind_dir,
            },
            "buoy_44013": {"water_temp_f": water_temp},
            "hyperlocal": {"corrected_temp": land_temp},
        }
        return data

    def test_active_sea_breeze(self):
        # Strong differential, onshore wind, midday → active
        data = self._make_data(land_temp=80, water_temp=60, wind_speed=8, wind_dir=165)
        detect_sea_breeze(data)
        assert data["sea_breeze"]["active"] is True
        assert data["sea_breeze"]["likelihood"] >= 60

    def test_no_sea_breeze_small_differential(self):
        # Under 5°F differential → score 0 for temp, should not be active
        data = self._make_data(land_temp=64, water_temp=62, wind_speed=8, wind_dir=165)
        detect_sea_breeze(data)
        assert data["sea_breeze"]["active"] is False

    def test_no_sea_breeze_wrong_direction(self):
        # Good differential but offshore wind → not active
        data = self._make_data(land_temp=80, water_temp=60, wind_speed=8, wind_dir=315)
        detect_sea_breeze(data)
        assert data["sea_breeze"]["active"] is False

    def test_no_sea_breeze_too_windy(self):
        # Good differential and direction but wind too strong
        data = self._make_data(land_temp=80, water_temp=60, wind_speed=20, wind_dir=165)
        detect_sea_breeze(data)
        assert data["sea_breeze"]["active"] is False

    def test_insufficient_data(self):
        # Missing water temp → insufficient data, no crash
        data = {
            "current": {"temperature": 75, "wind_speed": 8, "wind_direction": 165},
            "buoy_44013": {},
            "hyperlocal": {},
        }
        detect_sea_breeze(data)
        assert data["sea_breeze"]["active"] is False
        assert "Insufficient" in data["sea_breeze"]["reason"]
