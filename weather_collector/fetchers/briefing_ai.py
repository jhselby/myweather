"""
Briefing headline generator using Google Gemini API (free tier).
Generates an editorial headline and subheadline from weather data.
Falls back gracefully if the API is unavailable.
"""

import json
import os
import requests

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
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
- Use corrected values and derived values as the source of truth when they are provided. Do not recompute your own temperatures or reinterpret the numbers.
- Ignore any alerts that contain "TEST" in the headline or description. These are NWS transmission tests, not real alerts. Never mention test alerts in the headline or subheadline.
- Wind tone must follow the provided wind impact score first, with gusts only as supporting detail.
- If wind impact is calm or light, describe wind as light, gentle, or a breeze. Do not describe it as sharp, strong, choppy, restless, or disruptive unless the impact data supports that.
- Example: if wind impact is 2 (Calm) but raw wind is 15 mph with 21 mph gusts, the headline should treat it as calm or light air — the impact score accounts for local exposure and is more accurate than raw speed for this location. Raw speed and gusts may be mentioned as context but must not set the tone.
- Local flavor is welcome, but only when physically correct. Do not invent causal claims about local geography or landmarks unless they are explicitly supported by the input data.
- Avoid vague coastal phrasing like "off the water" or "onshore." Prefer explicit wind direction (e.g., northeast breeze) unless a directional relationship is clearly defined.
- If next rain is known within the next few days, do not say "no rain in sight"; instead say when rain returns.
- Do not use absolute phrasing like "rain stays away until" or "no rain until" if there is any earlier non-zero rain chance.
- If early rain chances are minor, describe conditions as mostly dry or as a slight chance before steadier rain arrives.
- If near-term precipitation chance is non-zero, avoid describing conditions as completely dry.
- Use the provided temperature values exactly as given. Never estimate, round differently, or invent temperatures not in the data.
- Respond in JSON only, no markdown fences: {"headline": "...", "subheadline": "..."}"""



def _redact_secrets(value):
    s = str(value)
    s = re.sub(r'([?&]key=)[^&\s]+', r'\1REDACTED', s)
    s = re.sub(r'(AIza[0-9A-Za-z\-_]{20,})', 'REDACTED', s)
    s = re.sub(r"((?:x-goog-api-key|api[_-]?key)[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+", r"\1REDACTED", s, flags=re.IGNORECASE)
    return s

def _build_weather_summary(weather_data):
    """Extract the key fields Gemini needs to write the briefing."""
    cur = weather_data.get("current", {})
    hyp = weather_data.get("hyperlocal", {})
    daily = weather_data.get("daily", {})
    der = weather_data.get("derived", {})
    sb = weather_data.get("sea_breeze", {})
    alerts = weather_data.get("alerts", [])
    hourly = weather_data.get("hourly", {})
    pirate = weather_data.get("pirate_weather", {})

    # Current conditions
    temp = round(hyp.get("corrected_temp") or cur.get("temperature") or 0)
    humidity = round(hyp.get("corrected_humidity") or cur.get("humidity") or 0)
    wind_speed = round(hyp.get("corrected_wind_speed") or cur.get("wind_speed") or 0)
    wind_gusts = round(hyp.get("corrected_wind_gusts") or cur.get("wind_gusts") or 0)
    sky = cur.get("condition_override") or cur.get("weather_description") or "Unknown"

    # Daily / derived source-of-truth values
    high = der.get("today_high")
    if high is None:
        high = daily.get("temperature_max", [None])[0]
    high = round(high) if high is not None else None

    # Use corrected low from derived, fallback to daily
    low = der.get("today_low") or daily.get("temperature_min", [None])[0]
    low = round(low) if low is not None else None

    # Tomorrow high/low
    tomorrow_high = der.get("tomorrow_high")
    tomorrow_high = round(tomorrow_high) if tomorrow_high is not None else None
    tomorrow_low = der.get("tomorrow_low")
    tomorrow_low = round(tomorrow_low) if tomorrow_low is not None else None

    # Wind direction
    wind_dir_deg = cur.get("wind_direction")
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    wind_dir = dirs[round((wind_dir_deg or 0) / 22.5) % 16] if wind_dir_deg is not None else ""

    # Fog
    fog_prob = der.get("fog_probability", 0)
    fog_label = der.get("fog_label", "No risk")

    # Wind impact — replicate frontend combinedWindImpact logic
    # sustained < 15mph → use sustained worry; otherwise use gust worry
    # worry_score = speed * exposure_factor^1.5
    _wind_dir = cur.get("wind_direction")
    _hyp = weather_data.get("hyperlocal", {})
    _sus = _hyp.get("corrected_wind_speed") or cur.get("wind_speed") or 0
    _gst = _hyp.get("corrected_wind_gusts") or cur.get("wind_gusts") or 0
    # Exposure factor from wind_risk processor
    from weather_collector.processors.wind_risk import get_exposure_factor, worry_score, worry_level
    _ef = get_exposure_factor(int(_wind_dir) % 360) if _wind_dir is not None else 1.0
    _sus_score = worry_score(_sus, _ef)
    _gst_score = worry_score(_gst, _ef)
    _combined = _sus_score if _sus < 15 else _gst_score
    wind_impact = round(_combined, 1)
    wind_impact_label = worry_level(round(_combined))

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
    rain_start_idx = None
    for i, p in enumerate(pop_arr[:48]):
        if p and p >= 40 and time_arr and i < len(time_arr):
            rain_start = time_arr[i]
            rain_start_idx = i
            break

    # Minor rain chances before the main rain event
    minor_rain_before_main = False
    minor_rain_max_pop_before_main = 0
    scan_end = rain_start_idx if rain_start_idx is not None else min(len(pop_arr), 24)
    for p in pop_arr[:scan_end]:
        if p is None:
            continue
        if p > 0:
            minor_rain_before_main = True
        if p > minor_rain_max_pop_before_main:
            minor_rain_max_pop_before_main = p

    # Pirate Weather near-term precip signal
    pirate_next_hour_pop = pirate.get("precip_probability")

    # Alerts
    # Filter out TEST alerts before sending to Gemini
    alerts = [a for a in alerts if 'TEST' not in (a.get('headline', '') + ' ' + a.get('description', '')).upper() 
              and 'THIS_MESSAGE_IS_FOR_TEST_PURPOSES_ONLY' not in a.get('description', '')]
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
        f"Today high: {high}°F, Low: {low}°F",
        f"Tomorrow high: {tomorrow_high}°F, Low: {tomorrow_low}°F",
        f"Wind impact: {wind_impact if wind_impact is not None else 'Unknown'}" + (f" ({wind_impact_label})" if wind_impact_label else "") + " — THIS IS THE AUTHORITATIVE WIND MEASURE",
        f"Raw model wind: {wind_speed} mph {wind_dir}" + (f", gusts {wind_gusts}" if wind_gusts > wind_speed + 5 else "") + " (use for context only, not tone)",
        f"Humidity: {humidity}%",
        f"Fog: {fog_label} ({fog_prob}%)",
        f"Sea breeze: {'Active — ' + sb_reason if sb_active else 'Inactive'}",
        f"Rain next 48h: {rain_inches}\"" + (f", starts around {rain_start}" if rain_start else ""),
        f"Minor rain chance before main rain: {'yes' if minor_rain_before_main else 'no'}" + (f", max {minor_rain_max_pop_before_main}%" if minor_rain_before_main else ""),
        f"Next-hour precip chance (Pirate): {pirate_next_hour_pop}%" if pirate_next_hour_pop is not None else "",
        f"Alerts: {', '.join(alert_strs) if alert_strs else 'None'}",
    ]
    if sunset_note:
        lines.append(f"Sunset quality: {sunset_note}")

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
        return {"headline": cached["headline"], "subheadline": cached.get("subheadline", "")}

    return None
