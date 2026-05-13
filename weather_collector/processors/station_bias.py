"""
Per-station bias tracking for hyperlocal corrections.
Tracks each station's chronic offset from the local consensus using
a leave-one-out approach over a 48-hour rolling window.
Covers temperature, humidity, and pressure.
"""
import json
import math
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from ..config import ELEVATION_FT

_EASTERN = ZoneInfo("America/New_York")


def _is_daytime(ts_utc_iso):
    dt = datetime.fromisoformat(ts_utc_iso).replace(tzinfo=timezone.utc)
    return 7 <= dt.astimezone(_EASTERN).hour < 19

GCS_PATH = "station_history.json"
WINDOW_HOURS = 48
MIN_READINGS = 6  # require 1 hour of data before applying corrections

MB_TO_INHG = 1.0 / 33.8639


def _sid(station):
    sid = station.get('station_id') or station.get('station_name')
    return str(sid) if sid is not None else None


def _weight(station):
    dist = station.get('distance_mi')
    elev = station.get('elevation_ft')
    if dist is None or elev is None or dist == 0 or dist > 1.5:
        return None
    return (1.0 / dist ** 2) * math.exp(-abs(elev - ELEVATION_FT) / 30.0)


def _humidity(station):
    return station.get('humidity_pct') or station.get('relative_humidity')


def _pressure_in(station):
    p = station.get('pressure_in')
    if p is not None:
        return p
    p_mb = station.get('sea_level_pressure_mb')
    return round(p_mb * MB_TO_INHG, 3) if p_mb is not None else None


def _build_station_list(wu_data, tempest_data):
    stations = list(wu_data.get("stations", [])) if wu_data else []
    if tempest_data:
        for tb in tempest_data.get("stations", []):
            if tb.get("valid") and tb.get("temperature_f") and tb.get("distance_mi") and tb.get("elevation_ft") is not None:
                stations.append(tb)
    return stations


def _leave_one_out(eligible, value_fn):
    """
    Given eligible = [(station, weight, value), ...],
    return {sid: leave_one_out_delta} for each station.
    value_fn extracts the metric value from a station dict.
    """
    vals = [(s, w, value_fn(s)) for s, w, _ in eligible]
    vals = [(s, w, v) for s, w, v in vals if v is not None]
    if len(vals) < 2:
        return {}

    total_w = sum(w for _, w, _ in vals)
    total_wv = sum(w * v for _, w, v in vals)
    result = {}
    for station, w, val in vals:
        sid = _sid(station)
        if not sid:
            continue
        denom = total_w - w
        if denom <= 0:
            continue
        consensus = (total_wv - w * val) / denom
        result[sid] = round(val - consensus, 3)
    return result


def load_history(gcs_client, bucket_name):
    try:
        blob = gcs_client.bucket(bucket_name).blob(GCS_PATH)
        if blob.exists():
            return json.loads(blob.download_as_text())
        print("  ℹ  No station_history.json yet (first run)")
    except Exception as e:
        print(f"  ⚠  Could not load station history: {e}")
    return {}


def save_history(history, gcs_client, bucket_name):
    try:
        blob = gcs_client.bucket(bucket_name).blob(GCS_PATH)
        blob.upload_from_string(json.dumps(history), content_type="application/json")
        print(f"  ✓ Saved station history ({len(history)} stations)")
    except Exception as e:
        print(f"  ⚠  Could not save station history: {e}")


def update_history(history, wu_data, tempest_data):
    """
    Compute each station's leave-one-out delta for temp, humidity, and pressure,
    then append to history. Trims entries older than WINDOW_HOURS.
    Uses raw (uncorrected) values so history reflects true sensor behavior.
    """
    ts = datetime.now(timezone.utc).isoformat()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)).isoformat()

    stations = _build_station_list(wu_data, tempest_data)

    eligible = []
    for s in stations:
        w = _weight(s)
        temp = s.get('temperature_f')
        if w is not None and temp is not None:
            eligible.append((s, w, temp))

    if len(eligible) < 2:
        return history

    temp_deltas = _leave_one_out(eligible, lambda s: s.get('temperature_f'))
    humidity_deltas = _leave_one_out(eligible, _humidity)
    pressure_deltas = _leave_one_out(eligible, _pressure_in)

    is_day = _is_daytime(ts)
    all_sids = set(temp_deltas) | set(humidity_deltas) | set(pressure_deltas)
    for sid in all_sids:
        entry = {"ts": ts}
        if sid in temp_deltas:
            entry["delta"] = temp_deltas[sid]
            if is_day:
                entry["delta_d"] = temp_deltas[sid]
            else:
                entry["delta_n"] = temp_deltas[sid]
        if sid in humidity_deltas:
            entry["h_delta"] = humidity_deltas[sid]
        if sid in pressure_deltas:
            entry["p_delta"] = pressure_deltas[sid]

        if sid not in history:
            history[sid] = []
        history[sid].append(entry)
        history[sid] = [r for r in history[sid] if r["ts"] >= cutoff]

    return history


def compute_offsets(history):
    """
    Return structured offsets dict:
    {
        "temp":     {station_id: chronic_offset, ...},
        "humidity": {station_id: chronic_offset, ...},
        "pressure": {station_id: chronic_offset, ...},
    }
    Only includes stations with >= MIN_READINGS for each metric.
    """
    temp_off, temp_day_off, temp_night_off = {}, {}, {}
    humidity_off, pressure_off = {}, {}

    for sid, readings in history.items():
        t_vals = [r["delta"] for r in readings if "delta" in r]
        if len(t_vals) >= MIN_READINGS:
            temp_off[sid] = round(sum(t_vals) / len(t_vals), 3)

        d_vals = [r["delta_d"] for r in readings if "delta_d" in r]
        if len(d_vals) >= MIN_READINGS:
            temp_day_off[sid] = round(sum(d_vals) / len(d_vals), 3)

        n_vals = [r["delta_n"] for r in readings if "delta_n" in r]
        if len(n_vals) >= MIN_READINGS:
            temp_night_off[sid] = round(sum(n_vals) / len(n_vals), 3)

        h_vals = [r["h_delta"] for r in readings if "h_delta" in r]
        if len(h_vals) >= MIN_READINGS:
            humidity_off[sid] = round(sum(h_vals) / len(h_vals), 3)

        p_vals = [r["p_delta"] for r in readings if "p_delta" in r]
        if len(p_vals) >= MIN_READINGS:
            pressure_off[sid] = round(sum(p_vals) / len(p_vals), 4)

    return {"temp": temp_off, "temp_day": temp_day_off, "temp_night": temp_night_off,
            "humidity": humidity_off, "pressure": pressure_off}
