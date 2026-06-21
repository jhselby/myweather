"""
L2 cloud blend: Kalman-gated blend of KBOS+KBVY METAR sky obs against
HRRR hourly[0] cloud_cover.

Why this lives here (not in build_hyperlocal_data):
  build_hyperlocal_data runs BEFORE trim_hourly_to_current_hour, and its
  "model" reference is current.cloud_cover — which is sourced from a
  separate fetch_current_gfs() call (GFS, not HRRR). Computing an
  obs-vs-model bias against GFS and adding it to HRRR hourly[] would
  produce nonsense (today: GFS=83, HRRR=8 — wildly different baselines).
  Running this AFTER trim lets us read hourly[0] (HRRR L1, the correction
  stack's true baseline) directly.

Logic mirrors the temperature/humidity Kalman blend in hyperlocal.py:
  obs_mean = mean(KBOS_cc, KBVY_cc)
  bias    = obs_mean - hourly[0].cloud_cover     (where model = HRRR L1)
  K       = _kalman_gain_cloud(n_sources, bias_std)
  new_cc  = hourly[0].cloud_cover + K * bias       (in [0,100])

Same Kalman gain function (_kalman_gain_cloud in hyperlocal.py) handles
validation: low K when sources disagree (likely real spatial gradient),
high K when sources agree (treat as authoritative). Falls back to the
HRRR L1 value when neither METAR is available or when the gain is zero.

L/M/H splits get the same K applied with their own obs means.

Runs after trim_hourly_to_current_hour so hourly[0] is the current hour;
runs before apply_decay_corrections so L3/L4 (when cc enters those
whitelists) operate on the L2-corrected baseline.
"""
import logging
import statistics

from .hyperlocal import _kalman_gain_cloud


def _mean(vals):
    if not vals:
        return None
    return sum(vals) / len(vals)


def _collect(metar_data, key):
    """Return [(label, value), ...] for valid METAR entries."""
    out = []
    if metar_data and metar_data.get(key) is not None:
        out.append(metar_data[key])
    return out


def blend_metar_cloud_into_hourly(weather_data, kbos_data, kbvy_data):
    """Apply L2 cloud Kalman blend to hourly[0]. Mutates weather_data in
    place. Stamps weather_data["hourly"]["cloud_l2_meta"] with provenance
    for the debug page."""
    hourly = weather_data.get("hourly") or {}
    if not hourly.get("times"):
        return

    # Collect METAR cloud values per field
    fields = [
        ("cloud_cover",       "cloud_cover_pct"),
        ("cloud_cover_low",   "cloud_low_pct"),
        ("cloud_cover_mid",   "cloud_mid_pct"),
        ("cloud_cover_high",  "cloud_high_pct"),
    ]

    # Compute K from the total cloud_cover sources — splits inherit the
    # same K. This keeps the corrected total + splits self-consistent.
    cc_sources = _collect(kbos_data, "cloud_cover_pct") + _collect(kbvy_data, "cloud_cover_pct")
    if not cc_sources:
        return

    cc_obs_mean = _mean(cc_sources)
    cc_bias_std = statistics.stdev(cc_sources) if len(cc_sources) > 1 else 0.0
    K = _kalman_gain_cloud(len(cc_sources), cc_bias_std)
    if K == 0.0:
        return

    # Preserve raw HRRR cloud arrays BEFORE we mutate any of them. The
    # backtest framework and any "what would the raw model alone predict"
    # reads `hourly["raw_cloud_cover*"]` as the L1 truth. apply_decay's
    # later raw-preservation block (decay_apply.py:267-275) runs AFTER
    # this mutation; if we don't preserve here, raw_cloud_cover[0] will
    # be the L2-blended value, not the raw HRRR L1.
    for hourly_key, _ in fields:
        raw_key = "raw_" + hourly_key
        if hourly_key in hourly and raw_key not in hourly:
            hourly[raw_key] = list(hourly[hourly_key])

    applied = []
    for hourly_key, metar_key in fields:
        obs_vals = _collect(kbos_data, metar_key) + _collect(kbvy_data, metar_key)
        if not obs_vals:
            continue
        obs_mean = _mean(obs_vals)
        arr = hourly.get(hourly_key)
        if not isinstance(arr, list) or not arr or arr[0] is None:
            continue
        raw = arr[0]
        bias = obs_mean - raw
        new_val = raw + K * bias
        new_val = max(0, min(100, round(new_val)))
        arr[0] = new_val
        applied.append({
            "field":    hourly_key,
            "raw_hrrr": raw,
            "obs_mean": round(obs_mean, 1),
            "bias":     round(bias, 1),
            "new":      new_val,
        })

    if not applied:
        return

    n_sources = (1 if kbos_data and kbos_data.get("cloud_cover_pct") is not None else 0) + \
                (1 if kbvy_data and kbvy_data.get("cloud_cover_pct") is not None else 0)
    src_label = "KBOS+KBVY" if n_sources == 2 else (
        "KBOS only" if kbos_data and kbos_data.get("cloud_cover_pct") is not None
        else "KBVY only"
    )
    hourly["cloud_l2_meta"] = {
        "source":         src_label,
        "n_sources":      n_sources,
        "kalman_gain":    round(K, 2),
        "bias_std_cc":    round(cc_bias_std, 1),
        "obs_mean_cc":    round(cc_obs_mean, 1),
        "hour":           hourly["times"][0],
        "fields_applied": applied,
    }
    cc = next((a for a in applied if a["field"] == "cloud_cover"), None)
    if cc:
        logging.info(
            f"  ✓ L2 cloud blend: cloud_cover {cc['raw_hrrr']}→{cc['new']} "
            f"(obs={cc['obs_mean']}, K={K:.2f}, σ={cc_bias_std:.1f}, "
            f"src={src_label})"
        )
