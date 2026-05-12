"""
Per-station bias tracking for hyperlocal temperature correction.
Tracks each station's chronic offset from the local consensus using
a leave-one-out approach over a 48-hour rolling window.
"""
import json
import math
from datetime import datetime, timezone, timedelta
from ..config import ELEVATION_FT

GCS_PATH = "station_history.json"
WINDOW_HOURS = 48
MIN_READINGS = 6  # require 1 hour of data before applying corrections


def _sid(station):
    return station.get('station_id') or station.get('station_name')


def _weight(station):
    dist = station.get('distance_mi')
    elev = station.get('elevation_ft')
    if dist is None or elev is None or dist == 0 or dist > 1.5:
        return None
    return (1.0 / dist ** 2) * math.exp(-abs(elev - ELEVATION_FT) / 30.0)


def _build_station_list(wu_data, tempest_data):
    stations = list(wu_data.get("stations", [])) if wu_data else []
    if tempest_data:
        for tb in tempest_data.get("stations", []):
            if tb.get("valid") and tb.get("temperature_f") and tb.get("distance_mi") and tb.get("elevation_ft") is not None:
                stations.append(tb)
    return stations


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
    Compute each station's leave-one-out delta from the local consensus
    and append to history. Trims entries older than WINDOW_HOURS.
    Uses raw (uncorrected) temps so history reflects true sensor behavior.
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

    total_w = sum(w for _, w, _ in eligible)
    total_wt = sum(w * t for _, w, t in eligible)

    for station, w, temp in eligible:
        sid = _sid(station)
        if not sid:
            continue
        denom = total_w - w
        if denom <= 0:
            continue
        consensus = (total_wt - w * temp) / denom
        delta = round(temp - consensus, 3)

        if sid not in history:
            history[sid] = []
        history[sid].append({"ts": ts, "delta": delta})
        history[sid] = [r for r in history[sid] if r["ts"] >= cutoff]

    return history


def compute_offsets(history):
    """
    Return {station_id: chronic_offset} for stations with >= MIN_READINGS.
    Positive offset means station reads warm; negative means reads cold.
    """
    offsets = {}
    for sid, readings in history.items():
        if len(readings) >= MIN_READINGS:
            offsets[sid] = round(sum(r["delta"] for r in readings) / len(readings), 3)
    return offsets
