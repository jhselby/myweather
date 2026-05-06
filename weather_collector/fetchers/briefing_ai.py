"""
Briefing headline generator using Google Gemini API (free tier).
Generates an editorial headline and subheadline from weather data.
Falls back gracefully if the API is unavailable.
"""
import re

import json
import os
import requests

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

SYSTEM_PROMPT = """You are the briefing voice for a hyperlocal weather station at Wyman Cove — on the Salem Harbor side of Marblehead's peninsula, with open water to the north and northwest.

Site exposure by wind direction (0=no shelter, 1=fully exposed):
N to NNE (0°–25°): 1.0 — open harbor, max exposure
NE (25°–45°): 0.7 — partial terrain blocking
E to ESE (45°–100°): 0.25 — heavy terrain blocking
SE to S (100°–200°): 0.08 — maximum shelter (Marblehead peninsula)
SSW to WSW (200°–260°): 0.10 — heavy terrain blocking
W (260°–290°): 0.40 — moderate, harbor opens beyond
WNW to NW (290°–320°): 0.75 — harbor opening, high exposure
NW to N (320°–360°): 1.0 — open harbor, max exposure

Tone: seasoned local neighbor — observant, direct, helpful. Not a weather channel. Pick what matters, ignore the rest. On a quiet day, say little.

Rules:
- HEADLINE: Under 12 words. One breath. Lead with the weather story.
- SUBHEADLINE: 1-2 sentences. Specific times, temps, wind if relevant. Skip anything unremarkable.
- Don't mention everything. Only what's worth knowing right now.
- Never start with greetings or "Today will be."
- Use the temperature ranges provided — never invent specific degree numbers. The only exact temperature is the current reading.
- Wind Impact score already accounts for the cove's terrain exposure — it is the authoritative, hyperlocal wind measure, more accurate than raw forecast speed. Use it to set the tone. Mention the contrast with regional forecast only when it adds useful context. Never mention numerical impact scores — only use the impact label (Calm, Moderate, etc.).
- Only mention precipitation if POP data is included. If no precip data is included, conditions are dry — do not mention rain.
- Only mention fog or sea breeze if included in the data.
- Ignore any alerts containing "TEST" — those are NWS transmission tests.
- Respond in JSON only, no markdown fences: {"headline": "...", "subheadline": "..."}"""



def _temp_range(t):
    """Convert exact temp to a natural range so Gemini can't hallucinate specifics."""
    if t is None:
        return "unknown"
    t = round(t)
    decade = (t // 10) * 10
    pos = t % 10
    labels = {20: "20s", 30: "30s", 40: "40s", 50: "50s", 60: "60s", 70: "70s", 80: "80s", 90: "90s"}
    decade_str = labels.get(decade, f"{decade}s")
    if pos <= 1:
        return f"around {decade}"
    elif pos <= 3:
        return f"low {decade_str}"
    elif pos <= 6:
        return f"mid {decade_str}"
    elif pos <= 8:
        return f"upper {decade_str}"
    else:
        return f"near {decade + 10}"


def _redact_secrets(value):
    s = str(value)
    s = re.sub(r'([?&]key=)[^&\s]+', r'\1REDACTED', s)
    s = re.sub(r'(AIza[0-9A-Za-z\-_]{20,})', 'REDACTED', s)
    s = re.sub(r"((?:x-goog-api-key|api[_-]?key)[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+", r"\1REDACTED", s, flags=re.IGNORECASE)
    return s

def _build_weather_summary(weather_data):
    """Extract only what Gemini needs — minimal tokens, no conflicting data."""
    cur = weather_data.get("current", {})
    hyp = weather_data.get("hyperlocal", {})
    daily = weather_data.get("daily", {})
    der = weather_data.get("derived", {})
    sb = weather_data.get("sea_breeze", {})
    alerts = weather_data.get("alerts", [])
    hourly = weather_data.get("hourly", {})

    # Current conditions
    temp = round(hyp.get("corrected_temp") or cur.get("temperature") or 0)
    sky = cur.get("condition_override") or cur.get("weather_description") or "Unknown"

    # Highs/lows as ranges
    high = der.get("today_high") or (daily.get("temperature_max", [None]) or [None])[0]
    low = der.get("today_low") or (daily.get("temperature_min", [None]) or [None])[0]
    tomorrow_high = der.get("tomorrow_high")
    tomorrow_low = der.get("tomorrow_low")

    # Wind — corrected values + impact
    wind_speed = round(hyp.get("corrected_wind_speed") or cur.get("wind_speed") or 0)
    wind_gusts = round(hyp.get("corrected_wind_gusts") or cur.get("wind_gusts") or 0)
    wind_dir_deg = cur.get("wind_direction")
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    wind_dir = dirs[round((wind_dir_deg or 0) / 22.5) % 16] if wind_dir_deg is not None else ""

    from weather_collector.processors.wind_risk import get_exposure_factor, worry_score, worry_level
    _ef = get_exposure_factor(int(wind_dir_deg) % 360) if wind_dir_deg is not None else 1.0
    _sus_score = worry_score(wind_speed, _ef)
    _gst_score = worry_score(wind_gusts, _ef)
    _combined = _sus_score if wind_speed < 15 else _gst_score
    wind_impact = round(_combined, 1)
    wind_impact_label = worry_level(round(_combined))

    # Precip — only include if POP >= 20% somewhere in next 48h
    pop_arr = hourly.get("precipitation_probability", [])
    time_arr = hourly.get("times", [])
    max_pop = max((p or 0) for p in pop_arr[:48]) if pop_arr else 0
    precip_line = ""
    if max_pop >= 20:
        precip_arr = hourly.get("precipitation", [])
        rain_inches = round(sum(precip_arr[:48]) / 25.4, 1) if precip_arr else 0
        rain_start = None
        for i, p in enumerate(pop_arr[:48]):
            if p and p >= 30 and i < len(time_arr):
                rain_start = time_arr[i]
                break
        precip_line = f"Precip: max {max_pop}% POP, {rain_inches}\" total"
        if rain_start:
            precip_line += f", starts around {rain_start}"

    # Fog — only include if risk > 0
    fog_prob = der.get("fog_probability", 0)
    fog_line = ""
    if fog_prob > 0:
        fog_line = f"Fog: {der.get('fog_label', 'Possible')} ({fog_prob}%)"

    # Sea breeze — only include if active
    sb_line = ""
    if sb.get("active"):
        sb_line = f"Sea breeze: Active — {sb.get('reason', '')}"

    # Alerts — filter TEST
    alerts = [a for a in alerts if 'TEST' not in (a.get('headline', '') + ' ' + a.get('description', '')).upper()]
    alert_line = ""
    if alerts:
        alert_line = f"Alerts: {', '.join(a.get('event', '') for a in alerts[:3])}"

    lines = [
        f"Current: {temp}°F, {sky}",
        f"Today high: {_temp_range(high)}, low: {_temp_range(low)}",
        f"Tomorrow high: {_temp_range(tomorrow_high)}, low: {_temp_range(tomorrow_low)}",
        f"Wind: {wind_speed} mph {wind_dir}" + (f", gusts {wind_gusts}" if wind_gusts > wind_speed + 5 else "") + f" | Local impact: {wind_impact_label}",
    ]
    if precip_line:
        lines.append(precip_line)
    if fog_line:
        lines.append(fog_line)
    if sb_line:
        lines.append(sb_line)
    if alert_line:
        lines.append(alert_line)

    return "\n".join(lines)


# Cache: last successful headline stored in GCS
_BRIEFING_CACHE_PATH = "briefing_cache.json"
_BRIEFING_INTERVAL_MINUTES = 30


def _load_cached_briefing():
    """Load last successful briefing from GCS."""
    try:
        from google.cloud import storage as gcs
        client = gcs.Client()
        bucket = client.bucket("myweather-data")
        blob = bucket.blob(_BRIEFING_CACHE_PATH)
        if blob.exists():
            data = json.loads(blob.download_as_text())
            print(f"  ✓ Briefing cache loaded: {data.get('headline', '?')[:50]}")
            return data
    except Exception as e:
        print(f"  ⚠ Briefing cache load failed: {_redact_secrets(e)}")
    return None


def _save_cached_briefing(briefing):
    """Save successful briefing to GCS."""
    try:
        from google.cloud import storage as gcs
        from datetime import datetime
        import pytz
        client = gcs.Client()
        bucket = client.bucket("myweather-data")
        blob = bucket.blob(_BRIEFING_CACHE_PATH)
        briefing["cached_at"] = datetime.now(pytz.timezone("America/New_York")).isoformat()
        blob.upload_from_string(json.dumps(briefing), content_type="application/json")
        print(f"  ✓ Briefing cache saved")
    except Exception as e:
        print(f"  ⚠ Briefing cache save failed: {_redact_secrets(e)}")


def _should_call_gemini():
    """Only call Gemini every 30 minutes to stay under free tier quota."""
    try:
        from google.cloud import storage as gcs
        from datetime import datetime
        import pytz
        client = gcs.Client()
        bucket = client.bucket("myweather-data")
        blob = bucket.blob(_BRIEFING_CACHE_PATH)
        if blob.exists():
            data = json.loads(blob.download_as_text())
            cached_at = data.get("cached_at")
            if cached_at:
                eastern = pytz.timezone("America/New_York")
                cached_time = datetime.fromisoformat(cached_at)
                now = datetime.now(eastern)
                age_min = (now - cached_time).total_seconds() / 60
                if age_min < _BRIEFING_INTERVAL_MINUTES:
                    print(f"  ⏭ Briefing: cached {age_min:.0f}m ago, skipping Gemini (interval: {_BRIEFING_INTERVAL_MINUTES}m)")
                    return False, data
    except Exception as e:
        print(f"  ⚠ Briefing interval check failed: {_redact_secrets(e)}")
    return True, None


def generate_briefing(weather_data):
    """
    Call Gemini to generate a briefing headline and subheadline.
    - Only calls Gemini every 30 minutes (free tier quota management)
    - Retries once on 429
    - Falls back to cached headline on failure
    Returns dict with 'headline' and 'subheadline' keys, or None on failure.
    """
    import time

    # Check if we should call Gemini or use cache
    should_call, cached = _should_call_gemini()
    if not should_call and cached:
        return {"headline": cached.get("headline", ""), "subheadline": cached.get("subheadline", ""), "cached_at": cached.get("cached_at", "")}

    summary = _build_weather_summary(weather_data)

    # Guard: if current temp fell through to 0 (GFS failure + no hyperlocal), skip
    cur_temp = weather_data.get("hyperlocal", {}).get("corrected_temp") or weather_data.get("current", {}).get("temperature")
    if cur_temp is None or cur_temp == 0:
        daily_high = weather_data.get("derived", {}).get("today_high") or (weather_data.get("daily", {}).get("temperature_max", [None]) or [None])[0]
        if daily_high is not None and daily_high > 20:
            print("  ⚠ Briefing: current temp is missing/zero (likely GFS failure), using cache")
            cached = _load_cached_briefing()
            if cached and cached.get("headline"):
                return {"headline": cached["headline"], "subheadline": cached.get("subheadline", ""), "cached_at": cached.get("cached_at", "")}
            return None

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

    # Try up to 2 times (initial + 1 retry on 429)
    for attempt in range(2):
        try:
            resp = requests.post(
                GEMINI_URL,
                params={"key": GEMINI_API_KEY},
                json=payload,
                timeout=20
            )
            if resp.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                print("  ⚠ Briefing: 429 rate limited, retrying in 3s...")
                time.sleep(3)
                continue
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
                cached_at = datetime.now(eastern).isoformat()
                briefing = {"headline": headline, "subheadline": subheadline, "cached_at": cached_at}
                _save_cached_briefing(briefing)
                return briefing
            else:
                print("  ⚠ Briefing: empty headline from Gemini")
                break

        except requests.exceptions.Timeout:
            if attempt == 0:
                print("  ⚠ Briefing: timeout, retrying in 2s...")
                time.sleep(2)
                continue
            print("  ⚠ Briefing: Gemini timeout after retry")
            break
        except requests.exceptions.RequestException as e:
            print(f"  ⚠ Briefing: Gemini API error: {_redact_secrets(e)}")
            break
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"  ⚠ Briefing: Failed to parse Gemini response: {_redact_secrets(e)}")
            break

    # All attempts failed — fall back to cached headline
    cached = _load_cached_briefing()
    if cached and cached.get("headline"):
        print(f"  ↩ Briefing: using cached headline")
        return {"headline": cached["headline"], "subheadline": cached.get("subheadline", ""), "cached_at": cached.get("cached_at", "")}

    return None
