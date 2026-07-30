"""Ccd — cc from-derivation (specialist).

Replace the Pirate-fed cc forecast with a derived cc computed from the
Lc-corrected cl/cm/ch. Two candidate formulas: max-overlap
(`cc = max(cl, cm, ch)`) and random-overlap (`cc = 1 - (1-cl)(1-cm)(1-ch)`).
h_cc_derivation.py 2026-07-30 held-out test on 123,050 joined (cc, cl, cm,
ch) quads shows max-overlap wins pooled MAE by +8.5% vs current
production cc, +5.8% halves-averaged. Random-overlap +5.1% pooled.
Wins in 6 of 9 real regimes; loses in se_flow (−6.5%) and marginal in
unknown/calm.

Runs LAST in the cloud pipeline — after Lc, after chp/clp. Reads the
final `hourly.cloud_cover_low / _mid / _high` arrays (post-Lc for cm/ch,
raw for cl since cl is currently in `_FIELD_SKIP`) and overwrites
`hourly.cloud_cover`.

Design notes:
  * Domain-scoped specialist: only touches cc.
  * Skip regimes (`SKIP_REGIMES`) fall back to the Pirate cc value —
    those are regimes where the h_cc_derivation held-out test shows
    Pirate wins vs derivation.
  * Preserves the pre-derivation Pirate value as
    `hourly.cloud_cover_pirate_raw` so the forecast snapshot can
    attribute cc-derived vs cc-pirate cleanly.
  * When ENABLED=False, still stamps telemetry (what would have been
    written) so the 7-day live-layer change gate can watch it.
  * When ENABLED=True, mutates hourly.cloud_cover in place.

Ship discipline:
  ENABLED=False first (2026-07-30 v0.6.389j), 7-day gate on SHIP-set
  stability + halves-verified pooled positive per regime, then flip.
"""
import json
import logging
from pathlib import Path


ENABLED = False  # v0.6.389j 2026-07-30 — Stage 3 wire ENABLED=False.
                 # Flip earliest 2026-08-06 after 7-day gate + halves-clean
                 # on daily h_cc_derivation re-runs.

# Regimes where h_cc_derivation held-out test showed Pirate cc + Lc wins vs
# derivation. Fall back to Pirate cc in these regimes.
#   se_flow: derived max-overlap loses -6.50% vs prod (n=22,803, real signal)
#   unknown: derived random loses -6.35%, max marginal +2.47% (n=1,608)
# Both are logged as SKIP even though max-unknown is technically flat — the
# unknown regime tag itself is a hedge, so being conservative on it costs
# little.
SKIP_REGIMES = frozenset({"se_flow", "unknown"})

# Formula choice — h_cc_derivation shows max-overlap wins on this dataset
# (+8.5% pooled vs +5.1% random). Physical justification: KBOS/KBVY METAR
# reports total sky cover as the coverage of the highest layer that
# reaches broken/overcast, which correlates more with max than with
# random-independent union.
FORMULA = "max"  # "max" | "random"


def _clip(v):
    return max(0.0, min(100.0, v))


def _derive_max(cl, cm, ch):
    return _clip(max(cl, cm, ch))


def _derive_random(cl, cm, ch):
    a = 1.0 - cl / 100.0
    b = 1.0 - cm / 100.0
    c = 1.0 - ch / 100.0
    return _clip(100.0 * (1.0 - a * b * c))


def _derive(cl, cm, ch):
    return _derive_max(cl, cm, ch) if FORMULA == "max" else _derive_random(cl, cm, ch)


def describe_applicability():
    """Applicability descriptor for Ccd. Field-scoped to cc."""
    state_prefix = "ENABLED True" if ENABLED else "ENABLED False"
    fires_when = (
        f"{'ENABLED' if ENABLED else 'OFF'} — replaces hourly.cloud_cover with "
        f"derived-{FORMULA}(cl_l6, cm_l6, ch_l6) for regimes NOT in SKIP_REGIMES. "
        f"SKIP: {sorted(SKIP_REGIMES)}."
    )
    return [{
        "layer_id": "Ccd",
        "name": "cc from-derivation (max/random overlap)",
        "category": "specialist",
        "fields": [{
            "field": "cc",
            "fires_when": fires_when,
            "gated_by": "ENABLED + regime NOT in SKIP_REGIMES",
            "current_state": (
                f"{state_prefix}. Formula: {FORMULA}. "
                f"Skip regimes: {sorted(SKIP_REGIMES)}. "
                f"Held-out lift +8.5% pooled MAE vs current cc (h_cc_derivation, 2026-07-30)."
            ),
        }],
    }]


def stamp_cc_from_derivation(weather_data):
    """Compute derived cc per lead and stamp telemetry. When ENABLED, mutate
    hourly.cloud_cover in place; preserve pre-derivation as
    hourly.cloud_cover_pirate_raw for attribution.

    When ENABLED=False, still stamp telemetry showing what WOULD have been
    written — this feeds the 7-day live-layer change gate.
    """
    hourly = weather_data.get("hourly") or {}
    cc_arr = hourly.get("cloud_cover")
    cl_arr = hourly.get("cloud_cover_low")
    cm_arr = hourly.get("cloud_cover_mid")
    ch_arr = hourly.get("cloud_cover_high")
    regime = ((weather_data.get("derived") or {}).get("state") or {}).get("regime_synoptic")

    per_lead = {
        "enabled": ENABLED,
        "formula": FORMULA,
        "regime_at_apply": regime,
        "skip_regimes": sorted(list(SKIP_REGIMES)),
        "gate_skip_regime": regime in SKIP_REGIMES,
        "derived": None,
        "would_fire": False,
        "n_leads": 0,
    }

    if not cc_arr or not cl_arr or not cm_arr or not ch_arr:
        weather_data["cc_from_derivation"] = per_lead
        return
    if regime in SKIP_REGIMES:
        # No-op tick; log for gate accounting only.
        weather_data["cc_from_derivation"] = per_lead
        _log_firing(0, 48, ENABLED, regime, gate_skip=True)
        return

    n = min(len(cc_arr), len(cl_arr), len(cm_arr), len(ch_arr))
    derived = [None] * n
    fires = 0
    for i in range(n):
        cl_v = cl_arr[i]
        cm_v = cm_arr[i]
        ch_v = ch_arr[i]
        cc_v = cc_arr[i]
        if cl_v is None or cm_v is None or ch_v is None or cc_v is None:
            derived[i] = cc_v
            continue
        d = _derive(float(cl_v), float(cm_v), float(ch_v))
        derived[i] = d
        # Fire counts a lead if derivation would produce a materially
        # different value than the Pirate cc — |Δ| > 0.5pp.
        if abs(d - float(cc_v)) > 0.5:
            fires += 1

    per_lead["derived"] = [round(x, 2) if x is not None else None for x in derived]
    per_lead["would_fire"] = fires > 0
    per_lead["cells_fired"] = fires
    per_lead["n_leads"] = n

    if ENABLED:
        # Preserve pre-derivation Pirate array for attribution.
        if "cloud_cover_pirate_raw" not in hourly:
            hourly["cloud_cover_pirate_raw"] = list(cc_arr)
        # Mutate in place with rounded ints (matches the Pirate feed's shape).
        hourly["cloud_cover"] = [
            round(d) if d is not None else cc_arr[i]
            for i, d in enumerate(derived)
        ]

    weather_data["cc_from_derivation"] = per_lead
    _log_firing(fires, n, ENABLED, regime, gate_skip=False)


def _log_firing(fires, n_leads, enabled, regime, gate_skip):
    """Record firing to gate_firing_log for the 7-day gate accounting."""
    try:
        from . import gate_firing_log
        from ..utils import redact_secrets as _redact
        by_field = {
            "cc": {
                "fires": fires if enabled else 0,
                "skips": (0 if enabled else fires) + (n_leads if gate_skip else 0),
            }
        }
        gate_firing_log.record_firing(
            operator="Ccd", regime=regime,
            by_field=by_field, leads=n_leads,
        )
    except Exception as e:
        try:
            logging.warning(f"  ⚠  gate_firing record (Ccd) failed: {_redact(e)}")
        except Exception:
            pass
