"""
Shadow whitelist tuner — what would the auto-tuner have chosen?

Reads the latest Fitter output (`time_series_diagnostic.json`), applies
the same per-lead-band threshold logic the human audit uses, and logs
what whitelist sets it WOULD recommend for L3_FIELDS and L4_FIELDS.

Does NOT modify production. The log accumulates over months so we can
later evaluate: how often does the shadow's recommendation match the
manually-chosen production whitelist? If it tracks for 3+ months with
high agreement, automating the decision becomes safer to consider.

Threshold mirrors the R0 audit table:
  - A field is recommended ON for L3 if L3 beats L2 by ≥3% in any lead
    band AND L3's bias is no worse than L2's (closer to zero).
  - Same logic for L4 vs L3.

Logged per Fitter cycle to `shadow_whitelist_log.json`. Append-only,
60-day retention. Entries deduped: if recommendation hasn't changed
since last logged entry, skip (keeps the log compact).
"""
from datetime import datetime, timedelta

import pytz

from ..gcs_io import load_json, upload_json


LOG_PATH = "shadow_whitelist_log.json"
RETENTION_DAYS = 60
TZ = pytz.timezone("America/New_York")
SUSPECT_MARGIN = 0.03  # 3% — same as the human audit's threshold

# Fields that can be L3/L4-corrected via the per-(field,lead) decay path.
# Mirrors decay_apply.TARGET_ARRAY keys.
FIELDS = ["t", "dp", "h", "ws", "wg", "pp", "pr", "cc", "sr", "pa", "cl", "cm", "ch"]
LEAD_BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]


def _avg(arr, lo=1, hi=48):
    if not isinstance(arr, list):
        return None
    vals = [x for x in arr[lo:hi] if x is not None]
    return sum(vals) / len(vals) if vals else None


def _band_avgs(arr):
    """Per-band average of an array indexed by lead hour."""
    return {label: _avg(arr, lo, hi) for label, lo, hi in LEAD_BANDS}


def _recommend(upper_mae, lower_mae, upper_bias, lower_bias):
    """Should `upper` layer be enabled vs `lower`?
    Returns True if upper beats lower by ≥ SUSPECT_MARGIN in any band
    AND upper's bias is no worse (in absolute value) than lower's.
    """
    if not upper_mae or not lower_mae:
        return False
    # MAE: any band wins by ≥3%
    any_band_win = False
    for band in LEAD_BANDS:
        u = upper_mae.get(band[0])
        l = lower_mae.get(band[0])
        if u is None or l is None or l <= 0:
            continue
        if (l - u) / l >= SUSPECT_MARGIN:
            any_band_win = True
            break
    if not any_band_win:
        return False
    # Bias: overall (lead 1-47) absolute value didn't get worse
    if upper_bias is None or lower_bias is None:
        # Bias data missing for one side — fall back to MAE-only decision
        return True
    return abs(upper_bias) <= abs(lower_bias) + 0.05  # 0.05 slop


def compute_recommendation(ts_diag):
    """Given a time_series_diagnostic.json doc, return recommended whitelist sets."""
    mae_by_lead = ts_diag.get("per_layer_mae_by_lead") or {}
    bias_by_lead = ts_diag.get("per_layer_bias_by_lead") or {}

    rec_l3 = set()
    rec_l4 = set()
    per_field = {}

    for f in FIELDS:
        m = mae_by_lead.get(f, {})
        b = bias_by_lead.get(f, {})
        l1_bands = _band_avgs(m.get("l1"))
        l2_bands = _band_avgs(m.get("l2"))
        l3_bands = _band_avgs(m.get("l3"))
        l4_bands = _band_avgs(m.get("l4"))
        b2 = _avg(b.get("l2"))
        b3 = _avg(b.get("l3"))
        b4 = _avg(b.get("l4"))

        l3_ok = _recommend(l3_bands, l2_bands, b3, b2)
        # v0.6.110: cascade constraint removed. The original logic gated L4
        # consideration on L3 being recommended ("only consider L4 if L3 is
        # in"). But L4 is fit on error_l3, which equals error_l2 by
        # construction when L3 is off — so L4 ON without L3 is architecturally
        # valid (L4 fits on the L2 residual). Removing the gate lets the
        # shadow see "bad L3, good L4" cases for fields where the diurnal
        # signal is real but the per-lead bias signal isn't.
        l4_ok = _recommend(l4_bands, l3_bands, b4, b3)
        if l3_ok:
            rec_l3.add(f)
        if l4_ok:
            rec_l4.add(f)
        per_field[f] = {"l3": l3_ok, "l4": l4_ok}

    return rec_l3, rec_l4, per_field


def log_shadow_recommendation(ts_diag, current_l3_fields, current_l4_fields,
                              conditional_audits=None):
    """Compute the shadow recommendation and append to the log if it
    differs from the most recent entry (dedup on identical recommendations).

    Called by the Fitter after writing time_series_diagnostic.json.

    `conditional_audits` (optional, v0.6.110+): dict mapping conditional-layer
    name (e.g., "r5", "l5") to a verdict dict shaped like:
        {
            "verdict": "SHIP" | "HOLD" | "insufficient_data",
            "enabled": bool,        # current production ENABLED state
            "mae_baseline": float,
            "mae_with_layer": float,
            "improvement_pct": float,
            "n_pairs": int,
            "best_variant": "...",  # optional, for layers with multiple application strategies
        }
    These extend the existing per-field L3/L4 whitelist recommendation pattern
    to cover layers that don't fit the per-field-whitelist model (R5 = single
    on/off for one location; L5 = regime-conditional). Same shadow pattern,
    different decision rule per layer. Future R6/L6/etc. can be added the
    same way without further changes to this signature.
    """
    rec_l3, rec_l4, _per_field = compute_recommendation(ts_diag)
    fitted_at = ts_diag.get("fitted_at")
    if not fitted_at:
        return

    now_local = datetime.now(TZ)
    cutoff = (now_local - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")

    cur_l3_sorted = sorted(current_l3_fields)
    cur_l4_sorted = sorted(current_l4_fields)
    rec_l3_sorted = sorted(rec_l3)
    rec_l4_sorted = sorted(rec_l4)

    entry = {
        "fitted_at": fitted_at,
        "current_l3": cur_l3_sorted,
        "current_l4": cur_l4_sorted,
        "shadow_l3": rec_l3_sorted,
        "shadow_l4": rec_l4_sorted,
        "would_change_l3": cur_l3_sorted != rec_l3_sorted,
        "would_change_l4": cur_l4_sorted != rec_l4_sorted,
    }
    if conditional_audits:
        entry["conditional_audits"] = conditional_audits

    log = load_json(LOG_PATH, default={"entries": []})
    entries = [e for e in log.get("entries", []) if e.get("fitted_at", "") >= cutoff]
    last_evaluated_at = fitted_at
    # Dedup: skip appending if the last entry has the same shadow rec AND the
    # same conditional audit verdicts (a flip from HOLD to SHIP on R5/L5 is
    # meaningful and should produce a new entry even if L3/L4 are unchanged).
    # On a dedup-skip we still bump the last entry's held_cycles + the log's
    # last_evaluated_at so consumers can see "tuner ran, rec stable" rather
    # than misreading the unchanged file mtime as "tuner stalled".
    if entries:
        last = entries[-1]
        same_whitelists = (last.get("shadow_l3") == entry["shadow_l3"]
                           and last.get("shadow_l4") == entry["shadow_l4"]
                           and last.get("current_l3") == entry["current_l3"]
                           and last.get("current_l4") == entry["current_l4"])
        same_conditionals = _same_conditional_verdicts(
            last.get("conditional_audits"), entry.get("conditional_audits"))
        if same_whitelists and same_conditionals:
            last["held_cycles"] = int(last.get("held_cycles", 1)) + 1
            last["last_seen_at"] = fitted_at
            upload_json({"entries": entries, "last_evaluated_at": last_evaluated_at},
                        LOG_PATH, LOG_PATH)
            return
    entry["held_cycles"] = 1
    entry["last_seen_at"] = fitted_at
    entries.append(entry)
    upload_json({"entries": entries, "last_evaluated_at": last_evaluated_at},
                LOG_PATH, LOG_PATH)


def _same_conditional_verdicts(prev, curr):
    """Two entries' conditional-audit verdicts are 'same' if every layer key
    has the same `verdict` and `enabled` value. Numeric MAE values can drift
    slightly between cycles without that being a meaningful change."""
    prev = prev or {}
    curr = curr or {}
    if set(prev.keys()) != set(curr.keys()):
        return False
    for k in prev:
        if (prev[k].get("verdict") != curr[k].get("verdict")
            or prev[k].get("enabled") != curr[k].get("enabled")):
            return False
    return True
