"""ch persistence gate — regime × lead_band conditioned bypass of L4 for ch.

Follow-on to [[project-ch-persistence-gap]] + Stage 2 preview
(analysis/h_ch_persistence_blend_stage2.py). ch (cloud_cover_high) loses
to naive persistence in 8 of 9 regimes; only `frontal` benefits from L4.
This gate replaces the L4-corrected ch value with persistence-of-obs
(flat carry of the joined ch obs at forecast issue time) in cells where
Stage 2 verified persistence wins on both halves + full 30d window.

Cells with verdict=SHIP (22 cells at ship) or MARGIN (both halves
negative, magnitude below 3% floor) use persistence at runtime.
Cells with verdict=SKIP (8 cells at ship — sw_flow-heavy long-lead,
plus scattered halves-flip cells) fall back to L4.
`frontal` regime always uses L4 by design (only regime where L4 beats
persistence).

Runtime persistence source:
  Preferred: cloud_l2_meta.fields_applied[cloud_cover_high].obs_mean
             (pure KBOS+KBVY blended obs, pre-Kalman-shrinkage).
  Fallback:  hourly[0].cloud_cover_high (Kalman-blended value; deviates
             from pure obs only when K < 1).
  If neither is available, the gate is a no-op this tick.

Placement: runs AFTER Lc so persistence overwrites both L4 and Lc
outputs where the gate fires. Lc's saturation-unbias was fit against
L4, not persistence — applying it on top of persistence would
re-introduce bias.

When ENABLED=False the module still stamps telemetry (what would be
overwritten) so the 7-day live-layer change gate can watch it. Flip
ENABLED=True only after gate agreement across 7 daily reads. See
[[feedback_whitelist_promotion_gate]] and [[feedback_regime_gate_first]].
"""
import json
import logging
from pathlib import Path


ENABLED = True  # Flipped 2026-07-19 v0.6.358 after 7-day gate cleared + refreshed-window rerun confirmed SHIP: 27 SHIP cells, halves A -17.84% / B -37.61%, regime_gate FULL -29.53%. Stage 2 preview shipped 2026-07-12.

FIELD = "ch"
HOURLY_KEY = "cloud_cover_high"

_LEAD_BANDS = [
    ("0-5",   1,  5),
    ("6-11",  6, 11),
    ("12-23", 12, 23),
    ("24-47", 24, 47),
]

# v0.6.401 diurnal gate. 08-10 investigation of the 12-23h + 24-47h chp
# regression on the debug-page scoreboard traced the bias to daytime
# valid-times in nw_flow (chp_bias +20.51 at 12-23h nw_flow day, n=78)
# and pre_frontal (chp_bias +4.25 at 24-47h day, n=91). Nighttime cells
# in the same regimes remain strong wins (-6 to -26% vs raw). Physical
# story: chp persists residual overnight clouds into daytime valid times;
# in post-frontal cold advection (nw_flow) or pre-frontal warm sector
# (pre_frontal) the clouds burn off by midday and persistence over-forecasts.
# hourly.times[i] is America/New_York local; 10-18 local ≈ 6am-2pm EDT,
# solidly inside sun-up hours for August. See
# project_ch_chp_midlead_band_watch_08_10.
_DIURNAL_SKIP_REGIMES = frozenset({"nw_flow", "pre_frontal"})
_DIURNAL_SKIP_HOUR_START = 10  # inclusive, America/New_York local
_DIURNAL_SKIP_HOUR_END = 18    # exclusive

# v0.6.405 emergency (regime, lead_band) demote. 08-13 investigation of
# widening Prod-vs-L6 MAE gap on ch (+3.4→+12.7 over 8 days) traced to
# chp firing on mid/long-lead cells where the vs_l6 tool says chp
# materially loses to L6. Source: h_ch_persistence_blend_stage2_vs_l6.txt
# "9 live cell(s) flip → SKIP under L6 baseline". Fitter regenerates the
# curated JSON daily so a JSON verdict edit would be transient; encoded
# here in the processor to survive. Reversibility: remove any entry to
# re-enable that cell. Prior watches
# [[project_ch_chp_regression_watch_08_07]] and
# [[project_ch_chp_midlead_band_watch_08_10]] closed clean 08-09/08-10,
# but the gap started widening after those closes — this is a NEW
# regression class in the same mid/long-lead bands.
_CELL_SKIP = frozenset({
    ("calm",        "12-23"),  # vs_l6 Δ +34.26%
    ("calm",        "24-47"),  # vs_l6 Δ +34.89%
    ("nw_flow",     "12-23"),  # vs_l6 Δ +22.42% (overlaps diurnal skip 10-18 local)
    ("pre_frontal", "12-23"),  # vs_l6 Δ +27.83% (overlaps diurnal skip 10-18 local)
    ("pre_frontal", "24-47"),  # 08-14 add: vs_l6 Δ +101.59% (biggest current chp loser to L6; nighttime targets outside the diurnal skip window)
    ("se_flow",     "24-47"),  # vs_l6 Δ -0.16% (parity — precautionary)
    ("sea_breeze",  "12-23"),  # vs_l6 Δ  +9.71%
    ("sea_breeze",  "24-47"),  # vs_l6 Δ  -1.84% (parity — precautionary)
    ("sw_flow",     "12-23"),  # vs_l6 Δ +22.80%
    ("sw_flow",     "24-47"),  # vs_l6 Δ +30.69%
})


def _valid_hour_local(times, i):
    """Extract local-time hour from hourly.times[i]. Returns None on failure."""
    if i >= len(times):
        return None
    t = times[i]
    if not isinstance(t, str) or len(t) < 13:
        return None
    try:
        return int(t[11:13])
    except ValueError:
        return None


def _diurnal_skip(regime, valid_hour):
    """True when the diurnal gate suppresses chp fire at this (regime, hour)."""
    if regime not in _DIURNAL_SKIP_REGIMES:
        return False
    if valid_hour is None:
        return False
    return _DIURNAL_SKIP_HOUR_START <= valid_hour < _DIURNAL_SKIP_HOUR_END

_TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / "ch_persistence_gate_curated.json"
_TABLE_CACHE = None


def _load_table():
    """Load and cache the Stage 2 preview table. Missing / malformed →
    empty table (gate is a no-op)."""
    global _TABLE_CACHE
    if _TABLE_CACHE is not None:
        return _TABLE_CACHE
    try:
        _TABLE_CACHE = json.loads(_TABLE_PATH.read_text())
    except FileNotFoundError:
        logging.warning(f"  ⚠  ch persistence gate table missing at {_TABLE_PATH}; gate will not fire")
        _TABLE_CACHE = {"cells": {}}
    except Exception as e:
        logging.warning(f"  ⚠  ch persistence gate table load failed: {e}")
        _TABLE_CACHE = {"cells": {}}
    return _TABLE_CACHE


def _lead_band(lead_h):
    for name, lo, hi in _LEAD_BANDS:
        if lo <= lead_h <= hi:
            return name
    return None


def _cell_fires(cells, regime, band):
    """True if (regime, band) is SHIP or MARGIN (both halves improving).
    `frontal` always falls to L4 regardless of table content.
    `_CELL_SKIP` cells are demoted regardless of table verdict."""
    if regime == "frontal":
        return False
    if (regime, band) in _CELL_SKIP:
        return False
    cell = cells.get(regime, {}).get(band)
    if not cell:
        return False
    verdict = cell.get("verdict")
    return verdict in ("SHIP", "MARGIN")


def _persistence_source(weather_data):
    """Return (value, source_label) for the persistence-of-obs at
    forecast issue time. None if no source is available this tick."""
    hourly = weather_data.get("hourly") or {}

    meta = hourly.get("cloud_l2_meta") or {}
    for entry in (meta.get("fields_applied") or []):
        if entry.get("field") == HOURLY_KEY:
            v = entry.get("obs_mean")
            if v is not None:
                return float(v), "cloud_l2_meta.obs_mean"

    arr = hourly.get(HOURLY_KEY)
    if isinstance(arr, list) and arr and arr[0] is not None:
        return float(arr[0]), "hourly[0].cloud_cover_high (Kalman-blended)"

    return None, None


def describe_applicability():
    """Applicability descriptor for the ch persistence gate."""
    table = _load_table()
    cells = table.get("cells", {})
    if ENABLED:
        fires_when = ("ENABLED — replaces L4/Lc ch value with persistence-of-obs when (regime, lead_band) is SHIP or MARGIN. "
                      "frontal + SKIP cells fall back to L4. "
                      f"v0.6.401 diurnal gate: chp OFF for valid hours {_DIURNAL_SKIP_HOUR_START}-{_DIURNAL_SKIP_HOUR_END} local "
                      f"in {sorted(_DIURNAL_SKIP_REGIMES)} (morning residual clouds burn off; persistence over-forecasts).")
        state_prefix = "ENABLED True"
    else:
        fires_when = "OFF — ENABLED False. Telemetry stamped for 7-day watch; no ch values modified."
        state_prefix = "ENABLED False"

    ship_cells, skip_cells, thin_cells, margin_cells = [], [], [], []
    for regime, bandmap in cells.items():
        for band, cell in bandmap.items():
            v = cell.get("verdict")
            key = f"{regime}/{band}"
            if v == "SHIP":
                ship_cells.append(key)
            elif v == "MARGIN":
                margin_cells.append(key)
            elif v == "SKIP":
                skip_cells.append(key)
            elif v == "THIN":
                thin_cells.append(key)
    current_state = (
        f"{state_prefix}. Cells — SHIP: {len(ship_cells)}, MARGIN: {len(margin_cells)}, "
        f"SKIP: {len(skip_cells)} (fall back to L4), THIN: {len(thin_cells)}. "
        f"frontal always L4 by design. "
        f"v0.6.405 emergency demote: {len(_CELL_SKIP)} (regime, band) cells forced to L4 "
        f"regardless of curated verdict (h_ch_persistence_blend_stage2_vs_l6 damage)."
    )

    return [{
        "layer_id": "ch_persistence_gate",
        "name": "ch persistence gate (regime × lead_band bypass of L4)",
        "category": "specialist",
        "fields": [{
            "field": FIELD,
            "fires_when": fires_when,
            "gated_by": "ENABLED + SHIP/MARGIN verdict per (regime, lead_band); frontal always falls to L4",
            "current_state": current_state,
        }],
    }]


def stamp_ch_persistence_gate(weather_data):
    """Stamp `weather_data["ch_persistence_gate"]` telemetry per lead.
    When ENABLED=True, overwrite hourly.cloud_cover_high on cells that
    fire; preserve the pre-gate array as
    hourly["cloud_cover_high_post_lc"] for snapshot attribution."""
    hourly = weather_data.get("hourly") or {}
    arr = hourly.get(HOURLY_KEY)
    if not isinstance(arr, list) or not arr:
        weather_data["ch_persistence_gate"] = {
            "enabled": ENABLED,
            "status": "no_hourly_array",
        }
        return

    table = _load_table()
    cells = table.get("cells", {})

    regime = ((weather_data.get("derived") or {}).get("state") or {}).get("regime_synoptic") or "unknown"

    persist_val, persist_src = _persistence_source(weather_data)

    times = hourly.get("times") or []

    n_leads = len(arr)
    per_lead_would_apply = [None] * n_leads
    per_lead_bands = [None] * n_leads
    per_lead_fires = [False] * n_leads
    fires_by_band = {name: 0 for name, _, _ in _LEAD_BANDS}
    skips_by_band = {name: 0 for name, _, _ in _LEAD_BANDS}
    diurnal_skips_by_band = {name: 0 for name, _, _ in _LEAD_BANDS}

    for i in range(n_leads):
        band = _lead_band(i)
        per_lead_bands[i] = band
        if band is None or persist_val is None:
            continue
        # v0.6.401: diurnal gate — suppress chp fire during daytime valid
        # hours in regimes where morning residual clouds burn off by midday.
        if _diurnal_skip(regime, _valid_hour_local(times, i)):
            skips_by_band[band] += 1
            diurnal_skips_by_band[band] += 1
            continue
        if _cell_fires(cells, regime, band):
            per_lead_would_apply[i] = round(persist_val, 3)
            per_lead_fires[i] = True
            fires_by_band[band] += 1
        else:
            skips_by_band[band] += 1

    # v0.6.382p: unconditional shadow-array write for template consistency
    # with wdp/clp. ENABLED=True so no behavior change today (shadow == live);
    # keeps any future re-verify or clone-of-template honest.
    shadow_arr = list(arr)
    if persist_val is not None:
        for i, fires in enumerate(per_lead_fires):
            if fires and shadow_arr[i] is not None:
                shadow_arr[i] = max(0.0, min(100.0, persist_val))
    hourly[HOURLY_KEY + "_shadow_chp"] = shadow_arr

    if ENABLED and persist_val is not None:
        post_lc_key = f"{HOURLY_KEY}_post_lc"
        if post_lc_key not in hourly:
            hourly[post_lc_key] = list(arr)
        hourly[HOURLY_KEY] = shadow_arr

    weather_data["ch_persistence_gate"] = {
        "enabled": ENABLED,
        "regime": regime,
        "persistence_value": (round(persist_val, 3) if persist_val is not None else None),
        "persistence_source": persist_src,
        "fires_by_band": fires_by_band,
        "skips_by_band": skips_by_band,
        "diurnal_skips_by_band": diurnal_skips_by_band,
        "per_lead_would_apply": per_lead_would_apply,
        "table_generated_at": table.get("generated_at"),
    }

    try:
        from . import gate_firing_log
        total_fires = sum(fires_by_band.values())
        total_skips = sum(skips_by_band.values())
        gate_firing_log.record_firing(
            operator="ch_persistence_gate",
            regime=regime,
            by_field={FIELD: {
                "fires": total_fires if ENABLED else 0,
                "skips": total_skips if ENABLED else total_fires + total_skips,
            }},
            leads=n_leads,
        )
    except Exception as e:
        try:
            logging.warning(f"  ⚠  gate_firing record (ch_persistence_gate) failed: {e}")
        except Exception:
            pass
