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


ENABLED = True   # v0.6.390 2026-07-30 — flipped early. Rerun of
                 # h_cc_derivation against the post-cl-field-kill regime
                 # reconfirmed +8.48% pooled MAE vs current prod, halves
                 # +11.4% / +5.8% (both positive), 6/10 regimes win.
                 # Verdict PROMOTE. Retires cc's Lc surface entirely; cc
                 # is now a derived field, not an independent one.

# Dynamic per-(regime × lead-band) combine gate. When True, per-cell formula
# from cc_combine_gate.json overrides the module-level FORMULA default.
# See [[project_cc_combine_walker]]. Ship-ahead pattern — same as chp v0.6.421
# and Lc v0.6.410 → v0.6.413. Flip only after walker clears >= 1 cell.
CC_COMBINE_GATE_ENABLED = False

# Regimes where h_cc_derivation held-out test showed Pirate cc + Lc wins vs
# derivation. Fall back to Pirate cc in these regimes.
#   se_flow: derived max-overlap loses -6.50% vs prod (n=22,803, real signal)
#   unknown: derived random loses -6.35%, max marginal +2.47% (n=1,608)
# Both are logged as SKIP even though max-unknown is technically flat — the
# unknown regime tag itself is a hedge, so being conservative on it costs
# little.
SKIP_REGIMES = frozenset({"se_flow", "unknown"})

# Saturation guard — when raw cc says the sky is already filled, Ccd's
# max(l6_cl, l6_cm, l6_ch) systematically undershoots because cm/ch's Lc
# corrections drag their l6 well below 100 (cm bin 80-95 Lc premium is
# +82%, ch is +268%). Investigation 2026-08-04 on last-24h pair log:
# obs-cc bin 95-100 across pre_frontal/se_flow/sea_breeze/sw_flow, n=235,
# raw MAE ~2 vs Ccd MAE ~30 (+1000%+). Corrections can only hurt when
# raw already agrees with obs. Skip derivation on those leads and keep
# raw cc.
SAT_THRESHOLD = 90.0

# Formula choice — h_cc_derivation shows max-overlap wins on this dataset
# (+8.5% pooled vs +5.1% random). Physical justification: KBOS/KBVY METAR
# reports total sky cover as the coverage of the highest layer that
# reaches broken/overcast, which correlates more with max than with
# random-independent union.
FORMULA = "max"  # "max" | "random"

_LEAD_BANDS = (("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48))

_COMBINE_GATE_PATH = Path(__file__).resolve().parent.parent / "data" / "cc_combine_gate.json"
_COMBINE_GATE_CACHE = None


def _clip(v):
    return max(0.0, min(100.0, v))


def _derive_max(cl, cm, ch):
    return _clip(max(cl, cm, ch))


def _derive_random(cl, cm, ch):
    a = 1.0 - cl / 100.0
    b = 1.0 - cm / 100.0
    c = 1.0 - ch / 100.0
    return _clip(100.0 * (1.0 - a * b * c))


def _derive_with(formula, cl, cm, ch):
    if formula == "random":
        return _derive_random(cl, cm, ch)
    return _derive_max(cl, cm, ch)


def _derive(cl, cm, ch):
    return _derive_with(FORMULA, cl, cm, ch)


def _band_of(lead_h):
    for name, lo, hi in _LEAD_BANDS:
        if lo <= lead_h < hi:
            return name
    return None


def _load_combine_gate():
    """Load and cache the dynamic per-cell combine gate. Missing / malformed →
    empty gate (nothing overridden). Never raises."""
    global _COMBINE_GATE_CACHE
    if _COMBINE_GATE_CACHE is not None:
        return _COMBINE_GATE_CACHE
    try:
        _COMBINE_GATE_CACHE = json.loads(_COMBINE_GATE_PATH.read_text())
    except FileNotFoundError:
        logging.warning(f"  ⚠  cc combine gate missing at {_COMBINE_GATE_PATH}; gate is a no-op")
        _COMBINE_GATE_CACHE = {"per_cell": {}}
    except Exception as e:
        logging.warning(f"  ⚠  cc combine gate load failed: {e}")
        _COMBINE_GATE_CACHE = {"per_cell": {}}
    return _COMBINE_GATE_CACHE


def _gate_formula_for(gate, regime, band):
    """Runtime contract: only when CC_COMBINE_GATE_ENABLED. Returns a formula
    string ('max' | 'random' | 'prod') or None to defer to FORMULA default."""
    if not CC_COMBINE_GATE_ENABLED:
        return None
    if regime is None or band is None:
        return None
    cell = ((gate.get("per_cell") or {}).get(regime) or {}).get(band)
    if not cell or not cell.get("cleared"):
        return None
    return cell.get("formula")


def describe_applicability():
    """Applicability descriptor for Ccd. Field-scoped to cc."""
    state_prefix = "ENABLED True" if ENABLED else "ENABLED False"
    gate_note = (
        f" · combine gate {'ENABLED' if CC_COMBINE_GATE_ENABLED else 'OFF'} "
        f"(per-cell formula override when cleared, else FORMULA default)"
    )
    fires_when = (
        f"{'ENABLED' if ENABLED else 'OFF'} — replaces hourly.cloud_cover with "
        f"derived-{FORMULA}(cl_l6, cm_l6, ch_l6) for regimes NOT in SKIP_REGIMES "
        f"and leads where raw cc < {SAT_THRESHOLD:.0f}. "
        f"SKIP: {sorted(SKIP_REGIMES)}. Saturation guard: raw cc ≥ {SAT_THRESHOLD:.0f} keeps raw."
        f"{gate_note}"
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

    gate = _load_combine_gate() if CC_COMBINE_GATE_ENABLED else {"per_cell": {}}

    per_lead = {
        "enabled": ENABLED,
        "formula": FORMULA,
        "combine_gate_enabled": CC_COMBINE_GATE_ENABLED,
        "regime_at_apply": regime,
        "skip_regimes": sorted(list(SKIP_REGIMES)),
        "gate_skip_regime": regime in SKIP_REGIMES,
        "derived": None,
        "would_fire": False,
        "n_leads": 0,
        "formula_by_band": {},
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
    sat_holds = 0
    gate_passthrough = 0
    formula_counts = {}
    for i in range(n):
        cl_v = cl_arr[i]
        cm_v = cm_arr[i]
        ch_v = ch_arr[i]
        cc_v = cc_arr[i]
        if cl_v is None or cm_v is None or ch_v is None or cc_v is None:
            derived[i] = cc_v
            continue
        if float(cc_v) >= SAT_THRESHOLD:
            derived[i] = cc_v
            sat_holds += 1
            continue
        # Per-lead formula: gate override if enabled+cleared, else module default.
        band = _band_of(i)
        gate_formula = _gate_formula_for(gate, regime, band)
        formula_for_lead = gate_formula or FORMULA
        formula_counts[formula_for_lead] = formula_counts.get(formula_for_lead, 0) + 1
        if formula_for_lead == "prod":
            # Gate says Pirate cc wins this cell — passthrough.
            derived[i] = cc_v
            gate_passthrough += 1
            continue
        d = _derive_with(formula_for_lead, float(cl_v), float(cm_v), float(ch_v))
        derived[i] = d
        # Fire counts a lead if derivation would produce a materially
        # different value than the Pirate cc — |Δ| > 0.5pp.
        if abs(d - float(cc_v)) > 0.5:
            fires += 1

    per_lead["derived"] = [round(x, 2) if x is not None else None for x in derived]
    per_lead["would_fire"] = fires > 0
    per_lead["cells_fired"] = fires
    per_lead["sat_holds"] = sat_holds
    per_lead["sat_threshold"] = SAT_THRESHOLD
    per_lead["gate_passthrough"] = gate_passthrough
    per_lead["formula_by_band"] = formula_counts
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
