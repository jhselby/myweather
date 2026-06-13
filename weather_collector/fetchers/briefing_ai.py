"""
Briefing headline generator using Google Gemini API (free tier).
Generates an editorial headline and subheadline from weather data.
Falls back gracefully if the API is unavailable.
"""
from ..utils import redact_secrets

import json
import logging
import os
import time
from datetime import datetime

import pytz
import requests

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

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
- Wind Impact score already accounts for the cove's terrain exposure — it is the authoritative, hyperlocal wind measure, more accurate than raw forecast speed. Use it to set the tone, and use the numerical score (provided alongside the label) to judge how strongly to lean on wind in the headline. Mention the contrast with regional forecast only when it adds useful context. Never write out the numerical impact score in your output — only use the impact label (Calm, Moderate, etc.) in the text.
- Only mention precipitation if POP data is included. If no precip data is included, conditions are dry — do not mention rain.
- Precip intensity words must match the data line. If the summary says "light," do not write "heavy," "downpour," "torrential," "deluge," "soaking," or "severe." Only use "torrential" or "deluge" when the data line explicitly says "torrential." Only use "heavy" or "downpour" when the data line says "heavy" or "torrential." When in doubt, use the exact word from the data line.
- Only mention fog or sea breeze if included in the data.
- Ignore any alerts containing "TEST" — those are NWS transmission tests.
- If a previous briefing is provided and the forecast has shifted meaningfully (timing, rain/snow line, temperature trend), note the change briefly in the subheadline (e.g., "rain timing pushed back two hours" or "snow line crept east since this morning"). If nothing significant changed, say nothing about the prior forecast — do not write phrases like "no change since last update" or "consistent with the prior forecast."
- The headline and subheadline must not repeat the same information. If the headline says "cooler Thursday," the subheadline must add something new — don't restate it.
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
    try:
        wind_dir_deg = float(wind_dir_deg) if wind_dir_deg is not None else None
    except (ValueError, TypeError):
        wind_dir_deg = None
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    wind_dir = dirs[round((wind_dir_deg or 0) / 22.5) % 16] if wind_dir_deg is not None else ""

    from weather_collector.processors.wind_risk import get_exposure_factor, worry_score, worry_level
    _ef = get_exposure_factor(int(wind_dir_deg) % 360) if wind_dir_deg is not None else 1.0
    _sus_score = worry_score(wind_speed, _ef)
    _gst_score = worry_score(wind_gusts, _ef)
    _combined = _sus_score if wind_speed < 15 else _gst_score
    wind_impact = round(_combined, 1)
    wind_impact_label = worry_level(round(_combined))

    # Sky/cloud cover (added v0.6.28) — gives Gemini the missing "sunny vs
    # overcast" context. Uses the Layer-4-corrected hourly cloud_cover array.
    cloud_arr = hourly.get("cloud_cover", [])
    cloud_now = round(cloud_arr[0]) if cloud_arr and cloud_arr[0] is not None else None
    cloud_24h = [v for v in cloud_arr[:24] if v is not None]
    cloud_min_24 = round(min(cloud_24h)) if cloud_24h else None
    cloud_max_24 = round(max(cloud_24h)) if cloud_24h else None
    sky_line = ""
    if cloud_now is not None:
        if cloud_min_24 is not None and cloud_max_24 is not None and abs(cloud_max_24 - cloud_min_24) >= 25:
            sky_line = f"Sky: {cloud_now}% cloud now, ranges {cloud_min_24}-{cloud_max_24}% next 24h"
        else:
            sky_line = f"Sky: {cloud_now}% cloud (steady through next 24h)"

    # Pressure trend (added v0.6.28) — surfaces "front incoming" signals to
    # Gemini. Use the raw 3h trend in hPa from `derived`, not just the binary
    # alarm flag, so Gemini can mention modest rises/falls too.
    p_trend = der.get("pressure_trend_hpa_3h")
    pressure_line = ""
    if p_trend is not None:
        if p_trend <= -3.0:
            pressure_line = f"Pressure: {p_trend:+.1f} hPa/3h — FALLING FAST (storm signal — front likely incoming)"
        elif p_trend <= -1.5:
            pressure_line = f"Pressure: {p_trend:+.1f} hPa/3h — falling (weather change possible)"
        elif p_trend >= 3.0:
            pressure_line = f"Pressure: {p_trend:+.1f} hPa/3h — rising fast (clearing/high pressure building)"
        elif p_trend >= 1.5:
            pressure_line = f"Pressure: {p_trend:+.1f} hPa/3h — rising (improving)"
        # else: steady, don't clutter the prompt

    # Precip — only include if POP >= 20% somewhere in next 48h
    pop_arr = hourly.get("precipitation_probability", [])
    time_arr = hourly.get("times", [])
    max_pop = max((p or 0) for p in pop_arr[:48]) if pop_arr else 0
    precip_line = ""
    if max_pop < 20:
        precip_line = "No significant rain expected next 48h — do NOT mention rain"
    elif max_pop >= 20:
        precip_arr = hourly.get("precipitation", [])
        # hourly.precipitation is in INCHES — OM_UNITS in config.py requests
        # precipitation_unit="inch" on every Open-Meteo call. The /25.4 that
        # used to be here (and the one v0.6.54 added to peak_intensity) was
        # wrong: it divided inches by 25.4, under-reporting rain 25×.
        rain_inches = round(sum(precip_arr[:48]), 1) if precip_arr else 0
        rain_start = None
        for i, p in enumerate(pop_arr[:48]):
            if p and p >= 30 and i < len(time_arr):
                rain_start = time_arr[i]
                break
        # Already in in/hr — the thresholds below apply directly.
        peak_intensity = max((p or 0) for p in precip_arr[:48]) if precip_arr else 0
        intensity_label = (
            "torrential" if peak_intensity >= 1.0 else
            "heavy"      if peak_intensity >= 0.30 else
            "moderate"   if peak_intensity >= 0.10 else
            "light"      if peak_intensity >= 0.01 else
            "drizzle"
        )
        intensity_str = f" · peak {intensity_label} ({peak_intensity:.2f}\"/hr)" if peak_intensity >= 0.01 else ""
        precip_line = f"Precip: max {max_pop}% POP, {rain_inches}\" total{intensity_str}"
        if rain_start:
            from datetime import datetime
            import pytz
            try:
                eastern = pytz.timezone("America/New_York")
                now_et = datetime.now(eastern)
                rain_dt = datetime.fromisoformat(rain_start).replace(tzinfo=eastern) if rain_start[-1] != "Z" else datetime.fromisoformat(rain_start.replace("Z", "+00:00")).astimezone(eastern)
                delta_hours = (rain_dt - now_et).total_seconds() / 3600
                hour = rain_dt.hour
                if hour < 6:
                    time_of_day = "early morning"
                elif hour < 12:
                    time_of_day = "morning"
                elif hour < 17:
                    time_of_day = "afternoon"
                elif hour < 21:
                    time_of_day = "evening"
                else:
                    time_of_day = "tonight"
                day_name = rain_dt.strftime("%A")
                hours_away = round(delta_hours)
                if delta_hours < 6:
                    rain_label = f"within the next few hours (~{hours_away}h from now)"
                elif rain_dt.date() == now_et.date():
                    rain_label = f"this {time_of_day} (~{hours_away}h from now)"
                elif (rain_dt.date() - now_et.date()).days == 1:
                    rain_label = f"tomorrow {time_of_day} (~{hours_away}h from now)"
                else:
                    rain_label = f"{day_name} {time_of_day} (~{hours_away}h from now)"
                precip_line += f", starts around {rain_label} — NOT sooner"
            except Exception:
                precip_line += f", starts around {rain_start}"

    # Fog — only include if risk > 0
    fog_prob = der.get("fog_probability", 0)
    fog_line = ""
    if fog_prob > 0:
        fog_line = f"Fog: {der.get('fog_label', 'Possible')} ({fog_prob}%)"

    # Sea breeze — only include if active. Verbose form (not the compact
    # frontend-card "reason" string) because Gemini misreads "Δ+22°F" as a
    # temperature change applied by the breeze (v0.6.61 incident) instead of
    # the land–water gradient that drives it. Naming the values explicitly
    # removes the ambiguity at source.
    sb_line = ""
    if sb.get("active"):
        land_t = hyp.get("corrected_temp") or cur.get("temperature")
        water_t = (weather_data.get("buoy_44013") or {}).get("water_temp_f")
        sb_wind_mph = round(cur.get("wind_speed") or 0)
        if land_t is not None and water_t is not None:
            gap = land_t - water_t
            sb_line = (
                f"Sea breeze: Active — onshore flow off the harbor. "
                f"Land {land_t:.1f}°F, water {water_t:.1f}°F "
                f"(land–water gap of {gap:.1f}°F drives the breeze — "
                f"this gradient is NOT a temperature change). "
                f"Wind {sb_wind_mph} mph from {wind_dir}."
            )
        else:
            sb_line = f"Sea breeze: Active — onshore flow off the harbor, wind {sb_wind_mph} mph from {wind_dir}."

    # Alerts — filter TEST + empty events
    alerts = [a for a in alerts if 'TEST' not in (a.get('headline', '') + ' ' + a.get('description', '')).upper()]
    alert_events = [a.get('event', '').strip() for a in alerts[:3]]
    alert_events = [e for e in alert_events if e]
    alert_line = f"Alerts: {', '.join(alert_events)}" if alert_events else ""

    yesterday_high = der.get("yesterday_high")
    yesterday_precip = der.get("yesterday_precip_in")
    yesterday_gust = der.get("yesterday_peak_gust")

    yesterday_parts = []
    if yesterday_high is not None:
        yesterday_parts.append(f"high {_temp_range(yesterday_high)}")
    if yesterday_precip is not None and yesterday_precip >= 0.01:
        yesterday_parts.append(f"{yesterday_precip}\" rain")
    if yesterday_gust is not None and yesterday_gust >= 20:
        yesterday_parts.append(f"gusts to {round(yesterday_gust)} mph")

    lines = [
        f"Current: {temp}°F, {sky}",
        f"Yesterday: {', '.join(yesterday_parts)}" if yesterday_parts else None,
        f"Today high: {_temp_range(high)}, low: {_temp_range(low)}",
        f"Tomorrow high: {_temp_range(tomorrow_high)}, low: {_temp_range(tomorrow_low)}",
        f"Wind: {wind_speed} mph {wind_dir}" + (f", gusts {wind_gusts}" if wind_gusts > wind_speed + 5 else "") + f" | Local impact: {wind_impact_label} (score {wind_impact}/10, for your internal judgment only)",
    ]
    if sky_line:
        lines.append(sky_line)
    if pressure_line:
        lines.append(pressure_line)
    if precip_line:
        lines.append(precip_line)
    if fog_line:
        lines.append(fog_line)
    if sb_line:
        lines.append(sb_line)

    # Frontal-passage attribution. If a front passed within the last 12 hours,
    # tell Gemini so the briefing can name the cause of the weather change
    # rather than just listing the new numbers.
    frontal = weather_data.get("frontal") or {}
    frontal_state = frontal.get("state")
    frontal_event = frontal.get("event") or {}
    if frontal_state in ("active", "recent") and frontal_event:
        ftype_label = {
            "cold":       "cold front",
            "warm":       "warm front",
            "sea_breeze": "sea-breeze front",
        }.get(frontal_event.get("type"), "front")
        dp_drop = frontal_event.get("dp_drop_f")
        wd_from_oct = frontal_event.get("wd_from_oct")
        wd_to_oct = frontal_event.get("wd_to_oct")
        ev_ts = frontal_event.get("ts")
        when_phrase = "currently passing" if frontal_state == "active" else f"passed at {ev_ts[-5:]}"
        bits = []
        if dp_drop is not None and abs(dp_drop) >= 1:
            verb = "dropped" if dp_drop > 0 else "rose"
            bits.append(f"dewpoint {verb} {abs(dp_drop):.0f}°F")
        if wd_from_oct and wd_to_oct:
            bits.append(f"wind shifted {wd_from_oct}→{wd_to_oct}")
        detail = "; ".join(bits) if bits else "transition in progress"
        lines.append(
            f"Frontal context: a {ftype_label} {when_phrase} ({detail}). "
            f"This is the cause of the recent change in conditions — "
            f"feel free to name it as such in the briefing."
        )

    # Thunderstorm. Risk gating keys off the *peak* CAPE label (next 12h),
    # not the current value — current CAPE at 8am is uselessly low almost
    # every summer day, which used to mask the textbook NE pulse setups.
    ts = der.get("thunderstorm", {})
    ts_severity = ts.get("severity", "clear")
    risk_label = ts.get("cape_peak_label") or ts.get("cape_label", "")
    risk_word = {"Extreme": "extreme", "High": "high", "Moderate": "moderate"}.get(risk_label, "low")
    if ts_severity in ("active", "severe"):
        min_dist = ts.get("min_distance_km")
        dist_str = f", closest {min_dist} km" if isinstance(min_dist, (int, float)) and min_dist > 0 else ""
        lines.append(f"{'Severe thunderstorm' if ts_severity == 'severe' else 'Thunderstorm'} in progress — {ts.get('lightning_count', 0)} strikes in past hour{dist_str}")
    elif ts_severity == "watch" and risk_label not in ("", "Weak", "Low", "Unknown"):
        lines.append(f"Thunderstorm risk: {risk_word} — do NOT overstate this, mention only briefly if relevant")

    pwat = der.get("precip_water_mm")
    if pwat is not None and ts_severity in ("active", "watch") and pwat >= 25:
        pwat_label = "very high" if pwat >= 35 else "high"
        lines.append(f"Precipitable water: {pwat}mm ({pwat_label}) — heavy rainfall rates likely with any storm")

    if alert_line:
        lines.append(alert_line)

    return "\n".join(l for l in lines if l is not None)


# Cache: last successful headline stored in GCS
_BRIEFING_CACHE_PATH = "briefing_cache.json"
_BRIEFING_INTERVAL_MINUTES = 30
# In-memory guard: persists across invocations on the same instance (max-instances=1)
_last_gemini_call_time = None


def _load_cached_briefing():
    """Load last successful briefing from GCS."""
    try:
        from google.cloud import storage as gcs
        client = gcs.Client()
        bucket = client.bucket("myweather-data")
        blob = bucket.blob(_BRIEFING_CACHE_PATH)
        if blob.exists():
            data = json.loads(blob.download_as_text())
            logging.info(f"  ✓ Briefing cache loaded: {data.get('headline', '?')[:50]}")
            return data
    except Exception as e:
        logging.error(f"  ⚠ Briefing cache load failed: {redact_secrets(e)}")
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
        logging.info(f"  ✓ Briefing cache saved")
    except Exception as e:
        logging.error(f"  ⚠ Briefing cache save failed: {redact_secrets(e)}")


def _validate_headline(briefing, summary, weather_data):
    """Sanity-check an LLM-generated headline against the structured weather
    data we fed into the prompt. Catches obvious contradictions (rain when no
    rain, clear when overcast, 'torrential' when actually light, etc.) before
    they reach the user. Conservative — only rejects clear contradictions,
    not borderline calls.

    Returns (is_valid: bool, reason: str). Caller falls through to the next
    headline source on False.
    """
    headline = briefing.get("headline", "").lower()
    sub = briefing.get("subheadline", "").lower()
    combined = f"{headline} {sub}"

    # 1. Precip contradiction — prompt is told "no rain" but headline mentions it.
    rain_words = ("rain", "shower", "drizzle", "downpour", "torrential",
                  "deluge", "soaker", "thunderstorm", "thundershower", "snow")
    if "No significant rain expected" in summary:
        for w in rain_words:
            if w in combined:
                return False, f"mentions {w!r} but forecast shows no significant rain"

    # 2. Sky contradiction vs current cloud cover (only flag the obvious ones).
    cloud_arr = weather_data.get("hourly", {}).get("cloud_cover", [])
    cloud_now = cloud_arr[0] if cloud_arr and cloud_arr[0] is not None else None
    if cloud_now is not None:
        if cloud_now >= 75 and ("clear" in combined or "sunny" in combined):
            return False, f"says clear/sunny but cloud cover is {cloud_now}%"
        if cloud_now <= 20 and ("cloudy" in combined or "overcast" in combined):
            return False, f"says cloudy/overcast but cloud cover is {cloud_now}%"

    # 3. Intensity word vs actual intensity label in the prompt.
    if "torrential" in combined and "torrential" not in summary:
        return False, "says 'torrential' but data doesn't label it that"
    if "deluge" in combined and "torrential" not in summary:
        return False, "says 'deluge' but data doesn't label it that"

    return True, "ok"


def _templated_briefing(weather_data):
    """Last-resort deterministic headline built from structured data. Used when
    Gemini, Groq, and the GCS cache have all failed (or all produced
    contradictions). Boring but never wrong."""
    cur = weather_data.get("current", {})
    hyp = weather_data.get("hyperlocal", {})
    der = weather_data.get("derived", {})
    sky = cur.get("weather_description") or "Conditions"
    temp = round(hyp.get("corrected_temp") or cur.get("temperature") or 0)
    high = der.get("today_high")
    high_str = f", high {_temp_range(high)}" if high is not None else ""
    return {
        "headline": f"{sky} at the cove",
        "subheadline": f"Currently {temp}°F{high_str}.",
        "model": "templated",
    }


def _should_call_gemini():
    """Only call Gemini every 30 minutes to stay under free tier quota."""
    from datetime import datetime
    import pytz
    eastern = pytz.timezone("America/New_York")
    now = datetime.now(eastern)

    # In-memory fast path — survives GCS failures; reliable with max-instances=1
    if _last_gemini_call_time is not None:
        age_min = (now - _last_gemini_call_time).total_seconds() / 60
        if age_min < _BRIEFING_INTERVAL_MINUTES:
            logging.info(f"  ⏭ Briefing: in-memory guard {age_min:.0f}m, skipping Gemini")
            return False, None

    try:
        from google.cloud import storage as gcs
        client = gcs.Client()
        bucket = client.bucket("myweather-data")
        blob = bucket.blob(_BRIEFING_CACHE_PATH)
        if blob.exists():
            data = json.loads(blob.download_as_text())
            cached_at = data.get("cached_at")
            if cached_at:
                cached_time = datetime.fromisoformat(cached_at)
                age_min = (now - cached_time).total_seconds() / 60
                if age_min < _BRIEFING_INTERVAL_MINUTES:
                    logging.info(f"  ⏭ Briefing: cached {age_min:.0f}m ago, skipping Gemini (interval: {_BRIEFING_INTERVAL_MINUTES}m)")
                    return False, data
    except Exception as e:
        logging.error(f"  ⚠ Briefing interval check failed: {redact_secrets(e)}")
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

    global _last_gemini_call_time

    # Check if we should call Gemini or use cache
    should_call, cached = _should_call_gemini()
    if not should_call:
        if cached is None:
            cached = _load_cached_briefing()
        if cached and cached.get("headline"):
            return {"headline": cached.get("headline", ""), "subheadline": cached.get("subheadline", ""), "cached_at": cached.get("cached_at", ""), "model": cached.get("model", "gemini")}

    summary = _build_weather_summary(weather_data)
    prev_briefing = _load_cached_briefing()
    prev_headline = prev_briefing.get("headline", "").strip() if prev_briefing else ""

    # Guard: if current temp fell through to 0 (GFS failure + no hyperlocal), skip
    cur_temp = weather_data.get("hyperlocal", {}).get("corrected_temp") or weather_data.get("current", {}).get("temperature")
    if cur_temp is None or cur_temp == 0:
        daily_high = weather_data.get("derived", {}).get("today_high") or (weather_data.get("daily", {}).get("temperature_max", [None]) or [None])[0]
        if daily_high is not None and daily_high > 20:
            logging.error("  ⚠ Briefing: current temp is missing/zero (likely GFS failure), using cache")
            cached = _load_cached_briefing()
            if cached and cached.get("headline"):
                return {"headline": cached["headline"], "subheadline": cached.get("subheadline", ""), "cached_at": cached.get("cached_at", ""), "model": cached.get("model", "gemini")}
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

    prev_context = f'\nPrevious briefing (30 min ago): "{prev_headline}"' if prev_headline else ""

    payload = {
        "contents": [{
            "parts": [{"text": f"{SYSTEM_PROMPT}\n\nWeather data for right now:\n{summary}{time_context}{prev_context}"}]
        }],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 2048,
        }
    }

    # Try Gemini first, with a single 5s retry on any transient 5xx or 429.
    # Capacity errors clear quickly; saves a fallback hop to Groq for most of them.
    gemini_ok = False
    try:
        resp = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=20
        )
        if resp.status_code == 429 or (500 <= resp.status_code < 600):
            logging.info(f"  ↻ Briefing: Gemini {resp.status_code}, retrying in 5s…")
            time.sleep(5)
            resp = requests.post(
                GEMINI_URL,
                params={"key": GEMINI_API_KEY},
                json=payload,
                timeout=20
            )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        result = json.loads(text.strip())
        headline = result.get("headline", "").strip()
        subheadline = result.get("subheadline", "").strip()
        if headline:
            cached_at = datetime.now(eastern).isoformat()
            briefing = {"headline": headline, "subheadline": subheadline, "cached_at": cached_at, "model": "gemini"}
            valid, reason = _validate_headline(briefing, summary, weather_data)
            if valid:
                logging.info(f"  ✓ Briefing (Gemini): {headline}")
                _save_cached_briefing(briefing)
                _last_gemini_call_time = datetime.now(eastern)
                return briefing
            else:
                logging.warning(f"  ⊘ Briefing (Gemini) REJECTED ({reason}): {headline!r} — falling through")
    except Exception as e:
        # Capture HTTP status + body excerpt to diagnose Cloud Function-side failures
        # (key + payload were verified working locally; failure is environment-specific).
        status = getattr(getattr(e, "response", None), "status_code", "n/a")
        body = getattr(getattr(e, "response", None), "text", "") or ""
        logging.warning(f"  ⚠ Briefing: Gemini failed ({type(e).__name__} status={status}), trying Groq... body[:300]={body[:300]!r}")

    # Groq fallback (OpenAI-compatible)
    if GROQ_API_KEY:
        try:
            groq_payload = {
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Weather data for right now:\n{summary}{time_context}{prev_context}"},
                ],
                "temperature": 0.5,
                "max_tokens": 256,
            }
            resp = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json=groq_payload,
                timeout=15
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            result = json.loads(text.strip())
            headline = result.get("headline", "").strip()
            subheadline = result.get("subheadline", "").strip()
            if headline:
                cached_at = datetime.now(eastern).isoformat()
                briefing = {"headline": headline, "subheadline": subheadline, "cached_at": cached_at, "model": "groq"}
                valid, reason = _validate_headline(briefing, summary, weather_data)
                if valid:
                    logging.info(f"  ✓ Briefing (Groq): {headline}")
                    # Intentionally NOT updating _last_gemini_call_time (let Gemini
                    # be retried on the next collector run) and NOT saving Groq to
                    # the cache (the cache is reserved for last-good Gemini, which
                    # is higher quality than a fresh Groq fallback).
                    return briefing
                else:
                    logging.warning(f"  ⊘ Briefing (Groq) REJECTED ({reason}): {headline!r} — falling through")
        except Exception as e:
            logging.error(f"  ⚠ Briefing: Groq failed ({type(e).__name__}: {redact_secrets(e)})")

    # All live LLM attempts failed (or both rejected by the validator).
    # Set the throttle so we don't hammer Gemini in the next 30 min, then walk
    # the safe-fallback chain: last-good cached Gemini → deterministic template.
    from datetime import datetime
    import pytz
    _last_gemini_call_time = datetime.now(pytz.timezone("America/New_York"))

    cached = _load_cached_briefing()
    if cached and cached.get("headline"):
        # Re-validate cached against current data — old cached headline might
        # contradict today's conditions (e.g. cached during yesterday's rain).
        valid, reason = _validate_headline(cached, summary, weather_data)
        if valid:
            logging.info(f"  ↩ Briefing: using cached headline")
            return {"headline": cached["headline"], "subheadline": cached.get("subheadline", ""), "cached_at": cached.get("cached_at", ""), "model": cached.get("model", "gemini")}
        else:
            logging.warning(f"  ⊘ Briefing cached headline REJECTED ({reason}) — using template")

    logging.info(f"  ⚙ Briefing: using deterministic template")
    templated = _templated_briefing(weather_data)
    templated["cached_at"] = datetime.now(pytz.timezone("America/New_York")).isoformat()
    return templated


def apply_briefing_to_weather_data(weather_data):
    """Run generate_briefing(), store the result on weather_data['briefing'],
    record the source status (with cached_at age in minutes) on
    weather_data['sources']['gemini'], and log the elapsed time. Handles the
    failure path by setting an empty briefing placeholder + error status.
    Mutates weather_data in place; returns nothing."""
    t0 = time.time()
    try:
        briefing = generate_briefing(weather_data)
    except Exception as e:
        logging.error(f"  ⚠ Briefing generation failed: {e}")
        briefing = None
    elapsed = time.time() - t0

    if briefing:
        weather_data["briefing"] = briefing
        # Age of the cached_at timestamp (minutes from now in Eastern time)
        gemini_age = 0
        if briefing.get("cached_at"):
            try:
                cached = datetime.fromisoformat(briefing["cached_at"])
                gemini_age = round((datetime.now(pytz.timezone("America/New_York")) - cached).total_seconds() / 60, 1)
            except Exception:
                pass
        weather_data["sources"]["gemini"] = {"status": "ok", "age_minutes": gemini_age}
    else:
        weather_data.setdefault("briefing", {"headline": "", "subheadline": ""})
        weather_data["sources"]["gemini"] = {"status": "error", "age_minutes": 0}

    logging.info(f"  ⏱  Briefing AI: {elapsed:.1f}s")
