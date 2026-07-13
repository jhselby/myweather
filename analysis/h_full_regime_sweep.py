"""Full regime-gate halves-check sweep — comprehensive edition.

Framework built through the 2026-07-11 session (see [[project-regime-gate-sweep-07-11]]
and [[feedback-regime-gate-first]]): the split-halves stability check is the
standard pre-ship gate for regime-gated decisions.

This script applies it comprehensively:
  For every (field, layer_transition, regime, lead_band):
    - Compute MAE for prev-layer vs curr-layer, split into two 15-day halves
    - Classify:
        ★ STABLE WIN  — both halves show curr-layer beats prev by ≥3%
        ★ STABLE LOSE — both halves show curr-layer worse than prev by ≥3%
        flipped/mixed — one half wins, other doesn't → not actionable
        thin          — n<300 in either half → not enough data

  Then flag:
    ADD_CANDIDATE  — field NOT currently in the layer's applied set,
                     but a STABLE WIN cell exists → regime-gated add candidate
    SKIP_CANDIDATE — field IS currently in the layer's applied set,
                     but a STABLE LOSE cell exists → skip-cell candidate

Output: tiered list of actionable cells sorted by |Δ%| × n (impact).

Windows: recent 15d + prior 15d (well-stamped period).
"""
import os, sys, json, math
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "output", "h_full_regime_sweep_summary.txt")

WIN_A_LO, WIN_A_HI = "2026-06-26T00:00", "2026-07-11T00:00"
WIN_B_LO, WIN_B_HI = "2026-06-11T00:00", "2026-06-26T00:00"

# Current state per project_correction_stack + project_todo
L2_APPLIED = {"t", "dp", "h", "ws", "wg", "cc", "cl", "cm", "ch"}  # additive/direct/blend
L3_APPLIED = {"ws", "wg", "ch", "cm"}
L4_APPLIED = {"cc", "ch"}
L5_APPLIED = {"sr"}
L6_APPLIED = set()  # Lt dormant

# Layer transitions to test: (layer_prev, layer_curr, applied_set)
# We check what layer_curr does vs layer_prev
TRANSITIONS = [
    ("l1", "l2", L2_APPLIED),
    ("l2", "l3", L3_APPLIED),
    ("l3", "l4", L4_APPLIED),
    ("l4", "l5", L5_APPLIED),
]

STABLE_THRESHOLD = 3.0  # both halves must show ≥3% delta in the same direction
MIN_N = 300

FIELDS_ALL = ["t","dp","h","pr","ws","wg","cc","cl","cm","ch","sr","pp","pa"]


def band_of(lead):
    if lead <= 5: return "0-5h"
    if lead <= 11: return "6-11h"
    if lead <= 23: return "12-23h"
    return "24-47h"


def compute():
    path = cached_path(URL)
    # buckets[(field, layer_prev, layer_curr, regime, band, win)] = {n, ae_prev, ae_curr}
    buckets = defaultdict(lambda: {"n": 0, "ae_p": 0.0, "ae_c": 0.0})
    n_rows = 0
    print("Scanning pair log...", file=sys.stderr)
    with open(path, "rb") as fh:
        for raw in fh:
            n_rows += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            fld = r.get("field")
            if fld not in FIELDS_ALL:
                continue
            rt = r.get("run_time", "")
            if WIN_A_LO <= rt < WIN_A_HI:
                win = "A"
            elif WIN_B_LO <= rt < WIN_B_HI:
                win = "B"
            else:
                continue
            lead = r.get("lead_h")
            if lead is None:
                continue
            try:
                lead = int(lead)
            except Exception:
                continue
            if lead <= 0 or lead > 47:
                continue
            band = band_of(lead)
            regime = (r.get("state_fc") or {}).get("regime_synoptic")
            if not regime:
                continue
            for lp, lc, _ in TRANSITIONS:
                ep = r.get(f"error_{lp}")
                ec = r.get(f"error_{lc}")
                if ep is None or ec is None:
                    continue
                # Only score if the two layers differ (otherwise no transition happened)
                if abs(float(ep) - float(ec)) < 1e-9:
                    # No layer transition for this row — but that's normal (the correction
                    # didn't fire for this field). Still bucket it — will show up as flat.
                    pass
                b = buckets[(fld, lp, lc, regime, band, win)]
                b["n"] += 1
                b["ae_p"] += abs(float(ep))
                b["ae_c"] += abs(float(ec))
    print(f"    scanned {n_rows:,} rows", file=sys.stderr)
    return buckets


def stats(bkt):
    n = bkt["n"]
    if not n:
        return None
    mp = bkt["ae_p"] / n
    mc = bkt["ae_c"] / n
    if mp == 0:
        return None
    delta = (mp - mc) / mp * 100  # positive = curr helps
    return {"n": n, "mae_p": mp, "mae_c": mc, "delta": delta}


def emit(buckets):
    lines = []
    lines.append("=" * 100)
    lines.append("FULL REGIME-GATE HALVES-CHECK SWEEP")
    lines.append("=" * 100)
    lines.append("")
    lines.append("For every (field, layer, regime, lead_band) with n≥300 in both halves,")
    lines.append("classify as STABLE WIN (curr helps both halves ≥3%), STABLE LOSE (curr hurts both ≥3%),")
    lines.append("flipped (one half wins, other doesn't), or flat (< 3% both halves).")
    lines.append("")

    skip_candidates = []
    add_candidates = []
    for (fld, lp, lc, regime, band, _), _ in list(buckets.items()):
        # Aggregate over win — do it once per cell
        pass
    # Collect unique (field, layer_prev, layer_curr, regime, band) keys — freeze
    # the iteration set to avoid RuntimeError from defaultdict on lookups.
    unique_keys = set()
    for (fld, lp, lc, regime, band, _win) in list(buckets.keys()):
        unique_keys.add((fld, lp, lc, regime, band))
    for key in unique_keys:
        fld, lp, lc, regime, band = key
        # Use dict.get to avoid inserting into defaultdict on missing halves
        a_raw = buckets.get((fld, lp, lc, regime, band, "A"))
        b_raw = buckets.get((fld, lp, lc, regime, band, "B"))
        a = stats(a_raw) if a_raw else None
        b = stats(b_raw) if b_raw else None
        if not a or not b or a["n"] < MIN_N or b["n"] < MIN_N:
            continue
        # Which applied-set determines LOSE-vs-ADD?
        applied_set = next((tr[2] for tr in TRANSITIONS if tr[0] == lp and tr[1] == lc), set())
        currently_on = fld in applied_set

        a_win = a["delta"] >= STABLE_THRESHOLD
        b_win = b["delta"] >= STABLE_THRESHOLD
        a_lose = a["delta"] <= -STABLE_THRESHOLD
        b_lose = b["delta"] <= -STABLE_THRESHOLD

        # Impact score = |mean delta| * mean n
        impact = abs((a["delta"] + b["delta"]) / 2) * (a["n"] + b["n"]) / 2

        if a_lose and b_lose and currently_on:
            skip_candidates.append({
                "field": fld, "layer": lc, "regime": regime, "band": band,
                "delta_a": a["delta"], "delta_b": b["delta"],
                "n_a": a["n"], "n_b": b["n"],
                "impact": impact,
            })
        elif a_win and b_win and (not currently_on):
            add_candidates.append({
                "field": fld, "layer": lc, "regime": regime, "band": band,
                "delta_a": a["delta"], "delta_b": b["delta"],
                "n_a": a["n"], "n_b": b["n"],
                "impact": impact,
            })

    # Sort by impact
    skip_candidates.sort(key=lambda x: -x["impact"])
    add_candidates.sort(key=lambda x: -x["impact"])

    lines.append("=" * 100)
    lines.append(f"SKIP CANDIDATES — layer currently ON for field but LOSES in cell (both halves ≥{STABLE_THRESHOLD}%)")
    lines.append(f"Count: {len(skip_candidates)}. Ranked by impact = |mean Δ| × mean n.")
    lines.append("=" * 100)
    if skip_candidates:
        hdr = f"{'field':<6}{'layer':<7}{'regime':<14}{'band':<8}{'A_n':>7}{'A_Δ%':>8}{'B_n':>7}{'B_Δ%':>8}{'impact':>10}"
        lines.append(hdr)
        lines.append("-" * len(hdr))
        for c in skip_candidates:
            lines.append(f"{c['field']:<6}{c['layer']:<7}{c['regime']:<14}{c['band']:<8}"
                         f"{c['n_a']:>7,}{c['delta_a']:>+8.1f}{c['n_b']:>7,}{c['delta_b']:>+8.1f}"
                         f"{c['impact']:>10.0f}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("=" * 100)
    lines.append(f"ADD CANDIDATES — layer currently OFF for field but WINS in cell (both halves ≥{STABLE_THRESHOLD}%)")
    lines.append(f"Count: {len(add_candidates)}. Ranked by impact.")
    lines.append("=" * 100)
    if add_candidates:
        hdr = f"{'field':<6}{'layer':<7}{'regime':<14}{'band':<8}{'A_n':>7}{'A_Δ%':>8}{'B_n':>7}{'B_Δ%':>8}{'impact':>10}"
        lines.append(hdr)
        lines.append("-" * len(hdr))
        for c in add_candidates:
            lines.append(f"{c['field']:<6}{c['layer']:<7}{c['regime']:<14}{c['band']:<8}"
                         f"{c['n_a']:>7,}{c['delta_a']:>+8.1f}{c['n_b']:>7,}{c['delta_b']:>+8.1f}"
                         f"{c['impact']:>10.0f}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Roll up: how many (field, layer) pairs have any actionable cells?
    lines.append("=" * 100)
    lines.append("ROLLUP by (field, layer)")
    lines.append("=" * 100)
    per_fl = defaultdict(lambda: {"skip": 0, "add": 0, "skip_impact": 0.0, "add_impact": 0.0})
    for c in skip_candidates:
        per_fl[(c["field"], c["layer"])]["skip"] += 1
        per_fl[(c["field"], c["layer"])]["skip_impact"] += c["impact"]
    for c in add_candidates:
        per_fl[(c["field"], c["layer"])]["add"] += 1
        per_fl[(c["field"], c["layer"])]["add_impact"] += c["impact"]
    for (fld, lyr), v in sorted(per_fl.items(), key=lambda x: -(x[1]["skip_impact"]+x[1]["add_impact"])):
        lines.append(f"  {fld} {lyr}:  {v['skip']} SKIP cells (impact {v['skip_impact']:.0f})   "
                     f"{v['add']} ADD cells (impact {v['add_impact']:.0f})")

    lines.append("")
    lines.append(f"Verdict: {len(skip_candidates)} SKIP candidates, {len(add_candidates)} ADD candidates cleared halves check.")

    return "\n".join(lines), add_candidates


def _emit_add_candidates_json(add_candidates):
    """Emit the ADD candidates as a curated JSON so the daily digest can
    walk the SHIP-cell list as a 7-day live-layer-change-gate streak
    claim (analogous to c1h/c1d/pre_frontal). Wired 2026-07-13 v0.6.331
    after h/l4/calm/12-23h found on 07-12 + 07-13 (day 2/7). When the
    ADD candidate set stays stable for 7 consecutive daily digest reads,
    the finding is ready for a live-layer change ship — actual code
    change on ship day is: (a) add field to L4_FIELDS, (b) add narrow
    whitelist entry to decay_apply.py.

    Cell key encoding: `<field>.<layer>.<regime>` at the field level,
    band at the band level. This lets _claim_marginal_ship_cells consume
    it with no code change (returns [[field.layer.regime, band], ...]).
    """
    from datetime import datetime as _dt, timezone as _tz
    OUT_JSON = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "weather_collector", "data",
        "h_l4_add_candidates.json"
    ))
    cells = {}
    for c in add_candidates:
        # Only h/l4 fields tracked here — this axis is a live-layer gate
        # for the L4 whitelist, not a generic ADD tracker. Broadening
        # scope would need per-field-per-layer gates registered in
        # build_executive_summary._NARROW_PROMOTE_GATES; skipped for now.
        if c["field"] != "h" or c["layer"] != "l4":
            continue
        key = f"{c['field']}.{c['layer']}.{c['regime']}"
        cells.setdefault(key, {})[c["band"]] = {
            "status": "SHIP",
            "delta_a_pct": round(c["delta_a"], 2),
            "delta_b_pct": round(c["delta_b"], 2),
            "n_a": c["n_a"],
            "n_b": c["n_b"],
            "impact": round(c["impact"], 0),
        }
    payload = {
        "generated_at": _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "h_full_regime_sweep.py",
        "scope": "h/l4 ADD candidates only — one live-layer change gate per (field, layer) axis",
        "cells": cells,
    }
    try:
        os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
        with open(OUT_JSON, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"→ wrote {OUT_JSON}  ({sum(len(b) for b in cells.values())} h/l4 ADD cells)")
    except Exception as e:
        print(f"⚠ ADD candidates JSON write failed: {e}")


def main():
    buckets = compute()
    text, add_candidates = emit(buckets)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    _emit_add_candidates_json(add_candidates)


if __name__ == "__main__":
    main()
