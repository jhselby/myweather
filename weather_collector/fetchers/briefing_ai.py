"""
Briefing headline generator using Google Gemini API (free tier).
Generates an editorial headline and subheadline from weather data.
Falls back gracefully if the API is unavailable.
"""

import json
import os
import requests

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

SYSTEM_PROMPT = """You are the briefing voice for a hyperlocal weather station at Wyman Cove, Marblehead MA — a coastal New England harbor.

Your tone is like a seasoned local neighbor: observant, direct, helpful. Not a weather channel, not a lifestyle blog. You notice things — when the fog is about to burn off, when the wind will make the dock unpleasant, when it's one of those rare perfect days.

You receive all of today's weather data. Your job is to pick what actually matters and ignore the rest. On a quiet day, say very little. On a busy day, name the one or two things worth knowing.

Rules:
- HEADLINE: Under 12 words. One breath. Lead with the weather story, not activities.
- SUBHEADLINE: 1-2 sentences. What rounds out the picture. Specific times, temps, wind if relevant. Skip anything unremarkable.
- Don't mention everything. Skip calm wind, normal humidity, boring sunsets.
- Never start with greetings or "Today will be."
- Be specific when it matters (times, speeds, amounts) but impressionistic when that's more useful.
- Respond in JSON only, no markdown fences: {"headline": "...", "subheadline": "..."}"""


def _build_weather_summary(weather_data):
    """Extract the key fields Gemini needs to write the briefing."""
    cur = weather_data.get("current", {})
    hyp = weather_data.get("hyperlocal", {})
    daily = weather_data.get("daily", {})
    der = weather_data.get("derived", {})
    sb = weather_data.get("sea_breeze", {})
    alerts = weather_data.get("alerts", [])
    hourly = weather_data.get("hourly", {})

    # Current conditions
    temp = round(hyp.get("corrected_temp") or cur.get("temperature") or 0)
    humidity = round(hyp.get("corrected_humidity") or cur.get("humidity") or 0)
    wind_speed = round(hyp.get("corrected_wind_speed") or cur.get("wind_speed") or 0)
    wind_gusts = round(hyp.get("corrected_wind_gusts") or cur.get("wind_gusts") or 0)
    sky = cur.get("condition_override") or cur.get("weather_description") or "Unknown"

    # Daily
    high = daily.get("temperature_max", [None])[0]
    low = daily.get("temperature_min", [None])[0]
    if high is not None:
        bias = hyp.get("weighted_bias", 0)
        high = round(high + bias)
        low = round(low + bias) if low is not None else None

    # Wind direction
    wind_dir_deg = cur.get("wind_direction")
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    wind_dir = dirs[round((wind_dir_deg or 0) / 22.5) % 16] if wind_dir_deg is not None else ""

    # Fog
    fog_prob = der.get("fog_probability", 0)
    fog_label = der.get("fog_label", "No risk")

    # Sea breeze
    sb_active = sb.get("active", False)
    sb_reason = sb.get("reason", "")

    # Rain next 48h
    precip_arr = hourly.get("precipitation", [])
    rain_total_mm = sum(precip_arr[:48]) if precip_arr else 0
    rain_inches = round(rain_total_mm / 25.4, 1)

    # Precipitation probability scan
    pop_arr = hourly.get("precipitation_probability", [])
    time_arr = hourly.get("times", [])
    rain_start = None
    for i, p in enumerate(pop_arr[:48]):
        if p and p >= 40 and time_arr and i < len(time_arr):
            rain_start = time_arr[i]
            break

    # Alerts
    alert_strs = []
    for a in alerts[:3]:  # max 3
        event = a.get("event", "")
        if event:
            alert_strs.append(event)

    # Sunset quality (if available)
    sunset_data = weather_data.get("sunset_directional", [])
    sunset_note = ""
    if sunset_data and len(sunset_data) > 0:
        today_sunset = sunset_data[0]
        if isinstance(today_sunset, dict):
            score = today_sunset.get("score")
            label = today_sunset.get("label")
            if score and label:
                sunset_note = f"{label} ({score}/100)"

    lines = [
        f"Current: {temp}°F, {sky}",
        f"High: {high}°F, Low: {low}°F",
        f"Wind: {wind_speed} mph {wind_dir}" + (f", gusts {wind_gusts}" if wind_gusts > wind_speed + 5 else ""),
        f"Humidity: {humidity}%",
        f"Fog: {fog_label} ({fog_prob}%)",
        f"Sea breeze: {'Active — ' + sb_reason if sb_active else 'Inactive'}",
        f"Rain next 48h: {rain_inches}\"" + (f", starts around {rain_start}" if rain_start else ""),
        f"Alerts: {', '.join(alert_strs) if alert_strs else 'None'}",
    ]
    if sunset_note:
        lines.append(f"Sunset quality: {sunset_note}")

    return "\n".join(lines)


def generate_briefing(weather_data):
    """
    Call Gemini to generate a briefing headline and subheadline.
    Returns dict with 'headline' and 'subheadline' keys, or None on failure.
    """
    summary = _build_weather_summary(weather_data)

    # Inject current time so Gemini writes forward-looking content
    from datetime import datetime
    import pytz
    eastern = pytz.timezone("America/New_York")
    now = datetime.now(eastern)
    time_str = now.strftime("%I:%M %p").lstrip("0")
    day_str = now.strftime("%A, %B %d")

    time_context = (
        f"\nCurrent time: {time_str} on {day_str}.\n"
        f"CRITICAL: Only write about what's AHEAD — not what already happened. "
        f"If it's afternoon, don't mention morning. If it's evening, focus on tonight and tomorrow. "
        f"Never reference times that have already passed today."
    )

    payload = {
        "contents": [{
            "parts": [{"text": f"{SYSTEM_PROMPT}\n\nWeather data for right now:\n{summary}{time_context}"}]
        }],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 200,
        }
    }

    try:
        resp = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=10
        )
        resp.raise_for_status()

        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        # Strip markdown fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        result = json.loads(text)

        headline = result.get("headline", "").strip()
        subheadline = result.get("subheadline", "").strip()

        if headline:
            print(f"  ✓ Briefing: {headline}")
            return {"headline": headline, "subheadline": subheadline}
        else:
            print("  ⚠ Briefing: empty headline from Gemini")
            return None

    except requests.exceptions.Timeout:
        print("  ⚠ Briefing: Gemini timeout (10s)")
        return None
    except requests.exceptions.RequestException as e:
        print(f"  ⚠ Briefing: Gemini API error: {e}")
        return None
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"  ⚠ Briefing: Failed to parse Gemini response: {e}")
        return None
