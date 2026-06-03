"""
Joiner: appends matched-pair rows to forecast_error_log.jsonl via GCS compose.

Each tick:
- Reads state file to find the last obs_time already processed
- Walks every new obs entry past last_processed (since v0.6.4 — was previously
  gated on "completed hour bucket" which held back current-hour obs for up to
  60 min; pairs are per-obs and don't need the hour to be fully sampled)
- For each new obs, generates pairs against every snapshot that predicted its hour
- Uploads the new pairs as a tiny temp .jsonl object
- Composes main + temp → main (server-side, constant cost regardless of main size)
- Deletes the temp object
- Updates the state file

Format: JSONL (one JSON object per line) so concatenation via GCS compose
yields a still-valid file. Pruning to RETENTION_DAYS and flattening of the
composite component count both happen in the daily Fitter pass (Piece 3).

Runs every 10 min from collector.main() because obs only retains 24h — if we
ran less often, pairs would fall out of the obs window before being matched.
"""
import json
import logging
from datetime import datetime

import pytz

from ..gcs_io import BUCKET, get_client, load_json, upload_json
from ..utils import redact_secrets


MAIN_PATH = "forecast_error_log.jsonl"
TEMP_PREFIX = "forecast_error_log_temp_"
STATE_PATH = "forecast_error_state.json"
FORECAST_LOG_PATH = "forecast_log.json"
OBS_LOG_PATH = "obs_temp_log.json"
TZ = pytz.timezone("America/New_York")

# Forecast-snapshot short keys → obs-log field names.
# 'pp' is handled separately (observed = hourly rain occurrence on 0/100 scale).
FIELD_MAP = {
    "t":  "temp",
    "ws": "wind_mph",
    "wg": "gust_mph",
    "h":  "humidity",
    "dp": "dew_point_f",
    "pr": "pressure_in",
    "cc": "cloud_cover",
    "sr": "solar_wm2",
    "pa": "precip_amount_in",
    "cl": "cloud_low",
    "cm": "cloud_mid",
    "ch": "cloud_high",
    "wd": "wind_dir",  # circular field — Fitter handles via sin/cos components, see _circular_diff
}

import math

def _circular_diff_deg(forecast_deg, observed_deg):
    """Signed angular difference in [-180, 180] (forecast − observed, wrap-aware).
    Example: forecast=5, observed=355 → +10 (not −350).
    """
    d = (forecast_deg - observed_deg + 180) % 360 - 180
    return d


def _parse(stamp):
    """Local-naive ISO minute string → naive datetime."""
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M")


def _pairs_for_obs(obs_entry, obs_hour_iso, snapshots):
    """All matched-pair rows for one obs entry across every covering snapshot."""
    pairs = []
    obs_time = obs_entry["time"]
    v_hour = _parse(obs_hour_iso).replace(minute=0, second=0, microsecond=0)

    for snap in snapshots:
        run = snap.get("run")
        if not run:
            continue
        try:
            run_dt = _parse(run)
        except (ValueError, TypeError):
            continue
        # Quick reject: snapshot's first forecast hour is the run hour, so any
        # snapshot whose run is *after* the obs's hour can't predict that hour.
        run_hour = run_dt.replace(minute=0, second=0, microsecond=0)
        if run_hour > v_hour:
            continue
        target_hour = None
        for h in snap.get("hours", []):
            if h.get("v") == obs_hour_iso:
                target_hour = h
                break
        if target_hour is None:
            continue
        lead_h = int(round((v_hour - run_hour).total_seconds() / 3600))

        # v0.6.29 conditional-state metadata. Same value for every pair from
        # this (snapshot, obs) join. Forecast-side state pulls from the
        # snapshot's target_hour (which has the L2 values via legacy top-level
        # keys) + snapshot-level fields. Observed-side state pulls from the
        # obs_entry. The Fitter doesn't aggregate by these yet — they're
        # logged for downstream stratification analyses (Research section).
        state_fc = {}
        for key, src in (("wind_speed","ws"), ("wind_dir","wd"),
                          ("solar_wm2","sr"), ("cloud_cover","cc"),
                          ("cloud_low","cl"), ("cloud_mid","cm"),
                          ("cloud_high","ch"), ("pressure_in","pr"),
                          ("precip_in","pa")):
            v = target_hour.get(src)
            if v is not None:
                state_fc[key] = v
        pt = snap.get("pressure_trend_hpa_3h")
        if pt is not None:
            state_fc["pressure_trend_hpa_3h"] = pt
        state_obs = {}
        for key, src in (("wind_speed","wind_mph"), ("wind_dir","wind_dir"),
                          ("solar_wm2","solar_wm2"), ("cloud_cover","cloud_cover"),
                          ("cloud_low","cloud_low"), ("cloud_mid","cloud_mid"),
                          ("cloud_high","cloud_high"), ("pressure_in","pressure_in"),
                          ("precip_in","precip_amount_in"), ("humidity","humidity"),
                          ("temp","temp")):
            v = obs_entry.get(src)
            if v is not None:
                state_obs[key] = v

        for short, long in FIELD_MAP.items():
            if short not in target_hour or target_hour[short] is None:
                continue
            observed = obs_entry.get(long)
            if observed is None:
                continue
            forecast = float(target_hour[short])
            obs_f = float(observed)
            # Wind direction is circular: error is angular difference, and the
            # Fitter aggregates sin/cos components separately to avoid wrap-around
            # pathologies in the mean.
            if short == "wd":
                err = _circular_diff_deg(forecast, obs_f)
                f_rad = math.radians(forecast); o_rad = math.radians(obs_f)
                pair = {
                    "obs_time": obs_time,
                    "run_time": run,
                    "valid_time": obs_hour_iso,
                    "lead_h": lead_h,
                    "field": short,
                    "forecast": round(forecast, 3),
                    "observed": round(obs_f, 3),
                    "error": round(err, 3),         # angular Δ in [-180, 180], for display
                    "error_sin": round(math.sin(f_rad) - math.sin(o_rad), 5),
                    "error_cos": round(math.cos(f_rad) - math.cos(o_rad), 5),
                }
                if state_fc:  pair["state_fc"]  = state_fc
                if state_obs: pair["state_obs"] = state_obs
                pairs.append(pair)
                continue
            pair = {
                "obs_time": obs_time,
                "run_time": run,
                "valid_time": obs_hour_iso,
                "lead_h": lead_h,
                "field": short,
                "forecast": round(forecast, 3),
                "observed": round(obs_f, 3),
                "error": round(forecast - obs_f, 3),
            }
            # v0.6.25: per-layer forecast values + errors when the snapshot
            # captured them (post-deploy snapshots only). Pre-v0.6.25 snapshots
            # only have the top-level short keys, no _lN suffixes — those pairs
            # carry no per-layer detail and quietly contribute only to the L4
            # accuracy stats. For wind direction (wd) the per-layer error uses
            # circular angular diff instead of linear subtract.
            for lyr in ("l1", "l2", "l3", "l4"):
                v = target_hour.get(f"{short}_{lyr}")
                if v is not None:
                    pair[f"forecast_{lyr}"] = round(float(v), 3)
                    if short == "wd":
                        pair[f"error_{lyr}"] = round(_circular_diff_deg(float(v), obs_f), 3)
                    else:
                        pair[f"error_{lyr}"] = round(float(v) - obs_f, 3)
            if state_fc:  pair["state_fc"]  = state_fc
            if state_obs: pair["state_obs"] = state_obs
            pairs.append(pair)
        # POP: forecast probability vs binary observed rain occurrence
        # on the same 0-100 scale.
        if "pp" in target_hour and target_hour["pp"] is not None:
            precip = obs_entry.get("precip_in")
            if precip is not None:
                forecast = float(target_hour["pp"])
                observed_pp = 100.0 if precip > 0 else 0.0
                pairs.append({
                    "obs_time": obs_time,
                    "run_time": run,
                    "valid_time": obs_hour_iso,
                    "lead_h": lead_h,
                    "field": "pp",
                    "forecast": round(forecast, 3),
                    "observed": observed_pp,
                    "error": round(forecast - observed_pp, 3),
                })
    return pairs


def _generate_new_pairs(forecast_log, obs_log, last_processed):
    """Pure function — given inputs, return (new_pairs, latest_obs_time_processed).

    Emits pairs for every obs entry strictly past last_processed, regardless
    of which hour bucket they fall in. Pairs are per-obs, not per-hour-bucket,
    so emitting immediately at the next tick produces identical pair content
    to waiting for the obs's hour to complete. Pre-v0.6.4 held back obs from
    the current in-progress hour as a state-machine simplification.
    """
    snapshots = forecast_log.get("snapshots", [])
    obs_entries = obs_log.get("entries", [])
    if not snapshots or not obs_entries:
        return [], last_processed

    new_pairs = []
    latest = last_processed
    for e in obs_entries:
        t = e.get("time")
        if not t or len(t) < 13:
            continue
        if t <= last_processed:
            continue
        hour_key = t[:13] + ":00"
        new_pairs.extend(_pairs_for_obs(e, hour_key, snapshots))
        if t > latest:
            latest = t
    return new_pairs, latest


def update_forecast_error_log():
    """Joiner entry point — call every 10 min from collector.main().

    Append-only via GCS compose. Constant per-tick cost regardless of how
    big the main file has grown.
    """
    state = load_json(STATE_PATH, default={"last_processed": ""})
    forecast_log = load_json(FORECAST_LOG_PATH, default={"snapshots": []})
    obs_log = load_json(OBS_LOG_PATH, default={"entries": []})

    last_processed = state.get("last_processed", "")
    new_pairs, latest = _generate_new_pairs(forecast_log, obs_log, last_processed)

    if not new_pairs:
        # If we advanced the watermark with no eligible obs (rare), persist it
        # so we don't keep re-scanning the same window.
        if latest != last_processed:
            upload_json({"last_processed": latest}, STATE_PATH, "forecast_error_state.json")
        return

    client = get_client()
    bucket = client.bucket(BUCKET)
    main_blob = bucket.blob(MAIN_PATH)
    temp_name = f"{TEMP_PREFIX}{latest.replace(':', '-')}.jsonl"
    temp_blob = bucket.blob(temp_name)

    jsonl_text = "".join(json.dumps(p) + "\n" for p in new_pairs)

    try:
        temp_blob.upload_from_string(jsonl_text, content_type="application/x-ndjson")
        if main_blob.exists():
            # Server-side stitch: main + temp → main. Cost is O(1) regardless
            # of how big main has grown. Component count of main grows by 1.
            main_blob.compose([main_blob, temp_blob])
            temp_blob.delete()
        else:
            # First run — promote temp to main, no compose needed.
            bucket.copy_blob(temp_blob, bucket, MAIN_PATH)
            temp_blob.delete()
        upload_json({"last_processed": latest}, STATE_PATH, "forecast_error_state.json")
        logging.info(f"  ✓ Appended {len(new_pairs):,} forecast-error pairs (through {latest})")
    except Exception as e:
        logging.error(f"  ✗ Forecast error log append failed: {redact_secrets(e)}")
        # Clean up temp if it got uploaded but compose failed
        try:
            if temp_blob.exists():
                temp_blob.delete()
        except Exception:
            pass
        raise
