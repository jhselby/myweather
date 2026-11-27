"""URMA-truth bias-then-blend for t (v0.8.0 rebuild branch). Stamps `t_urmab`; SERVED since v0.7.114. Also stamps the SHADOW `t_stnoff` (v0.7.153).

For t at leads 6-47h: per source (HRRR L1, NBM raw, ECMWF raw) subtract its trailing bias against
URMA (independent truth, not built from our forecast), then blend with weights fit on those
bias-corrected errors. Written by analysis/urma_blend_table_fit.py into
weather_collector/data/urma_blend_shadow_curated.json (refit daily by myweather-refitter once
registered). Walk-forward on 67 days: +11.4% (6-11h), +17.7% (12-23h), +16.6% (24-47h) vs served on
URMA truth, both halves positive; holdout (9 days) intervals still span zero, so this stamps
`t_urmab` for the pair log and changes NOTHING served. Pair log emits forecast_urmab / error_urmab.

Ship tiers (fixed 11-12): forward shadow days only; >= 5 of 7 days beating served with a positive
median, 6-47h only, auto-revert tripwire, then analysis/ship_rule.py at >= 14 holdout days.
Reversal: ENABLED = False (stamps nothing) or serving off. Serving is gated by SERVE and by the
runtime doc urma_blend_serve.json {"serve": bool} (gs://myweather-data/runtime_tables/, bundled copy
in data/), so a revert needs no deploy: gsutil cp a {"serve": false} doc. When served, the old served
t is kept as `t_pre_urmab` (pair log error_pre_urmab) so analysis/urma_shadow_score.py keeps scoring
the blend against what users would have seen without it.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

ENABLED = True
TABLE_NAME = "urma_blend_shadow_curated.json"
TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / TABLE_NAME
SERVE = True
SERVE_TABLE = "urma_blend_serve.json"
SERVE_PATH = Path(__file__).resolve().parent.parent / "data" / SERVE_TABLE
STALE_DAYS = 4
BANDS = (("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48))
WG_BANDS = (("0-5", 0, 6),) + BANDS   # v0.7.125 wg / v0.7.126 ws: the wind shadows also cover 0-5h


def validate_table(doc):
    """None when usable, else the reason. fields.t is required; fields.ws (v0.7.123) is optional."""
    try:
        fields = doc["fields"]
        cells = fields["t"]["bands"]
    except (KeyError, TypeError):
        return "missing fields.t.bands"
    if not cells:
        return "no bands"
    off = (fields.get("t_off") or {}).get("by_hour")
    if off is not None:
        if not isinstance(off, dict) or any(not (isinstance(v, (int, float)) and abs(v) <= 6) for v in off.values()):
            return "t_off.by_hour must map hour -> |offset| <= 6"
    for f in ("t", "ws", "wg", "dp"):
        if f not in fields:
            continue
        for b, c in (fields[f].get("bands") or {}).items():
            w, bias = c.get("w"), c.get("bias")
            if not (isinstance(w, list) and len(w) == 3 and isinstance(bias, list) and len(bias) == 3):
                return f"{f} band {b}: w/bias must be length-3 lists"
            if abs(sum(w) - 1.0) > 0.01 or min(w) < -1e-9:
                return f"{f} band {b}: weights not on the simplex"
            if any(abs(x) > 15 for x in bias):
                return f"{f} band {b}: |bias| > 15"
    return None


def _band(lead_h, bands=BANDS):
    return next((b for b, lo, hi in bands if lo <= lead_h < hi), None)


def _fresh(doc):
    try:
        t = datetime.strptime(doc["fitted_at"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    except (KeyError, ValueError, TypeError):
        return False
    return (datetime.now(timezone.utc) - t).days <= STALE_DAYS


def stamp(entry, lead_h):
    """Stamp entry['t_urmab'] at 6-47h, and the shadows entry['ws_urmab'] (6-47h, v0.7.123) and
    entry['wg_urmab'] (0-47h, v0.7.125; HRRR/NBM only, ECMWF weight 0) and
    entry['dp_urmab'] (6-47h, v0.7.135; weights only, bias 0) when the inputs and a fresh
    table exist. Only t is ever served; the pair log scores the others as forecast_urmab."""
    if not ENABLED or _band(lead_h, WG_BANDS) is None:
        return
    try:
        from .. import runtime_tables
        doc = runtime_tables.get(TABLE_NAME, TABLE_PATH, validate_table)
    except Exception as e:  # noqa: BLE001
        logging.warning(f"  ⚠  urma_blend_shadow: table load failed ({e})")
        return
    if not doc or not _fresh(doc):
        return
    for f, floor, bands in (("t", None, BANDS), ("ws", 0.0, WG_BANDS), ("wg", 0.0, WG_BANDS), ("dp", None, BANDS)):
        band = _band(lead_h, bands)
        cell = ((doc["fields"].get(f) or {}).get("bands") or {}).get(band) if band else None
        if not cell:
            continue
        w, bias = cell["w"], cell["bias"]
        xs = (entry.get(f"{f}_l1"), entry.get(f"{f}_raw_nbm"), entry.get(f"{f}_ecmwf"))
        if any(x is None and wi > 0 for x, wi in zip(xs, w)):
            continue
        v = sum(wi * (float(x) - bi) for wi, x, bi in zip(w, xs, bias) if wi > 0)
        entry[f"{f}_urmab"] = round(v if floor is None else max(floor, v), 1)
        if f == "t":
            _stamp_stnoff(entry, doc, entry["t_urmab"])


def _stamp_stnoff(entry, doc, t_urmab):
    """v0.7.153 SHADOW t_stnoff = t_urmab + trailing (Mesonet stations - URMA) mean for the valid hour of day
    (analysis/t_night_offset_wf.py: +12..20% vs t_urmab on stations, 12 holdout days). Never served. Hours with
    no offset (fewer than 7 fit days) get nothing."""
    try:
        off = ((doc["fields"].get("t_off") or {}).get("by_hour") or {}).get(str(int(entry["v"][11:13])))
    except (KeyError, TypeError, ValueError):
        return
    if off is not None:
        entry["t_stnoff"] = round(t_urmab + float(off), 1)


def _valid_serve(doc):
    if not (isinstance(doc, dict) and isinstance(doc.get("serve"), bool)):
        return "serve must be a bool"
    if "serve_dp" in doc and not isinstance(doc["serve_dp"], bool):
        return "serve_dp must be a bool"
    if "serve_ch" in doc and not isinstance(doc["serve_ch"], bool):
        return "serve_ch must be a bool"
    if "serve_ws" in doc and not isinstance(doc["serve_ws"], bool):
        return "serve_ws must be a bool"
    return None


def serving():
    """True when t_urmab replaces served t. Fails closed (False) if the switch doc cannot be read."""
    if not (ENABLED and SERVE):
        return False
    try:
        from .. import runtime_tables
        doc = runtime_tables.get(SERVE_TABLE, SERVE_PATH, _valid_serve)
    except Exception as e:  # noqa: BLE001
        logging.warning(f"  ⚠  urma_blend_shadow: serve switch unreadable ({e}); not serving")
        return False
    return bool(doc and doc.get("serve"))


def apply(entry):
    """Serve t_urmab in place of t. Keeps the replaced value as t_pre_urmab. True when it fired."""
    tu, told = entry.get("t_urmab"), entry.get("t")
    if tu is None or told is None or not serving():
        return False
    entry["t_pre_urmab"] = told
    entry["t_preempted_source_shadow"] = entry.get("t_selector_source")
    entry["t"] = tu
    entry["t_applied"] = "urmab"
    entry["t_selector_source"] = "urmab"
    return True


# v0.7.140: dew point blend (dp_urmab) served for dew point ONLY, 6-23h. Served humidity stays the humidity
# blend: building it from (t, dp) lost 10-17% to the served humidity in the walk-forward
# (analysis/urma_dp_h_coupling.py), so the entry is flagged `dp_urmab_independent` and
# decay_apply.recompute_derived_moisture_arrays leaves corrected_humidity alone for those hours.
# Kill switch: {"serve_dp": false} in urma_blend_serve.json (default false; flip without a deploy).
SERVE_DP_BANDS = ("6-11", "12-23")


def serving_dp():
    """True when dp_urmab replaces served dp. Fails closed (False)."""
    if not ENABLED:
        return False
    try:
        from .. import runtime_tables
        doc = runtime_tables.get(SERVE_TABLE, SERVE_PATH, _valid_serve)
    except Exception as e:  # noqa: BLE001
        logging.warning(f"  ⚠  urma_blend_shadow: serve switch unreadable ({e}); not serving dp")
        return False
    return bool(doc and doc.get("serve_dp") is True)


def apply_dp(entry, lead_h):
    """Serve dp_urmab in place of dp at 6-23h. Keeps the replaced value as dp_pre_dpurmab. True when it fired."""
    du, dold = entry.get("dp_urmab"), entry.get("dp")
    if du is None or dold is None or _band(lead_h, BANDS) not in SERVE_DP_BANDS or not serving_dp():
        return False
    entry["dp_pre_dpurmab"] = dold
    entry.setdefault("dp_pre_urmab", dold)
    entry["dp"] = du
    entry["dp_applied"] = "urmab"
    entry["dp_selector_source"] = "urmab"
    entry["dp_urmab_independent"] = True
    return True


# v0.7.154: high cloud served as raw HRRR (ch_l1) at 6-23h. On satellite truth (GOES-19 ACHAC cloud-top height at the Cove,
# analysis/goes_cloud_layers.py; the airport ceilometer cannot see above 12,000 ft) raw HRRR beat served ch by +37.7% [+15.4, +57.1]
# over 22 holdout days, both halves positive (7 km cutoff +34.8, 8 km +28.3). Nothing is fitted: ch_l1 was already logged.
# Served cc does not read ch (cc = NBM selector pick), so cc is unchanged. Kill switch: {"serve_ch": false} in urma_blend_serve.json
# (default false when the key is absent). The replaced value is kept as ch_pre_hrrr.
SERVE_CH_BANDS = ("6-11", "12-23")


def serving_ch():
    """True when raw HRRR ch replaces served ch at 6-23h. Fails closed (False)."""
    if not ENABLED:
        return False
    try:
        from .. import runtime_tables
        doc = runtime_tables.get(SERVE_TABLE, SERVE_PATH, _valid_serve)
    except Exception as e:  # noqa: BLE001
        logging.warning(f"  ⚠  urma_blend_shadow: serve switch unreadable ({e}); not serving ch")
        return False
    return bool(doc and doc.get("serve_ch") is True)


def apply_ch(entry, lead_h):
    """Serve ch_l1 (raw HRRR high cloud) in place of ch at 6-23h. Keeps the replaced value as ch_pre_hrrr. True when it fired."""
    hr, old = entry.get("ch_l1"), entry.get("ch")
    if hr is None or old is None or _band(lead_h, BANDS) not in SERVE_CH_BANDS or not serving_ch():
        return False
    entry["ch_pre_hrrr"] = old
    entry["ch"] = hr
    entry["ch_applied"] = "hrrr_sat"
    entry["ch_selector_source"] = "hrrr"
    return True


# v0.7.169: wind speed served as raw NBM at 6-23h. The served ws was a terminal blend (HRRR/NBM/ECMWF) fit on the
# model-blended `observed`, whose sheltered anemometers read low and pulled weight toward ECMWF (5.9 mph low in the
# 11-26 Wind Advisory). On URMA 10 m wind (analysis/urma_blend_wf_ws.py, 24 holdout days) raw NBM beat served
# +4.2% [+0.4, +9.2] at 6-11h and +5.2% [+1.0, +10.9] at 12-23h; 24-47h +4.1% [-0.6, +10.6] does not pass and
# 0-5h keeps the station nowcast. URMA is a fair open-air truth by direction (analysis/wind_shelter_by_direction.py:
# KBOS / URMA flat across sectors). Nothing is fitted. Applied tag raw_nbm, so the pair log's error_raw_nbm is
# the served error; the replaced value is kept as ws_pre_urmab (pair log error_pre_urmab).
# Kill switch: {"serve_ws": false} in urma_blend_serve.json (default false when the key is absent).
SERVE_WS_BANDS = ("6-11", "12-23")


def serving_ws():
    """True when raw NBM ws replaces served ws at 6-23h. Fails closed (False)."""
    if not ENABLED:
        return False
    try:
        from .. import runtime_tables
        doc = runtime_tables.get(SERVE_TABLE, SERVE_PATH, _valid_serve)
    except Exception as e:  # noqa: BLE001
        logging.warning(f"  ⚠  urma_blend_shadow: serve switch unreadable ({e}); not serving ws")
        return False
    return bool(doc and doc.get("serve_ws") is True)


def apply_ws(entry, lead_h):
    """Serve ws_raw_nbm in place of ws at 6-23h. Keeps the replaced value as ws_pre_urmab. True when it fired."""
    nb, old = entry.get("ws_raw_nbm"), entry.get("ws")
    if nb is None or old is None or _band(lead_h, BANDS) not in SERVE_WS_BANDS or not serving_ws():
        return False
    entry["ws_pre_urmab"] = old
    entry["ws_preempted_source_shadow"] = entry.get("ws_selector_source")
    entry["ws"] = nb
    entry["ws_applied"] = "raw_nbm"
    entry["ws_selector_source"] = "nbm"
    return True
