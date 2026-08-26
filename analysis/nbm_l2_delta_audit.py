#!/usr/bin/env python3
"""L2_NBM soundness audit — raw_nbm → l2_nbm lift by field × lead (v0.6.492, 2026-08-26).

Purpose: L2_NBM is not fit natively. It's reconstructed at snapshot time as
  l2_nbm = raw_nbm + (l2_hrrr − raw_hrrr)
i.e. the HRRR-side Kalman-scaled additive bias delta is applied to the NBM
raw under the assumption that the true Wyman Cove bias is independent of
which model generated the raw. That's a big assumption underpinning every
NBM cascade layer downstream.

This script quantifies whether the assumption holds by field × lead band:
  MAE(l2_nbm) vs MAE(raw_nbm) → lift %.

  Positive lift = the HRRR-delta transfer helps (assumption vindicated for
                  that cell).
  Near-zero    = neutral (delta washes out — assumption not violated but
                  not adding value).
  Negative     = the delta actively hurts (assumption broken for that cell
                  — the true NBM-vs-truth bias is not the HRRR-vs-truth
                  bias in this regime/lead).

For each cell we also emit n, MAE(raw_nbm), MAE(l2_nbm), signed bias(raw_nbm),
signed bias(l2_nbm) so a bias-flip (sign change from raw to l2) can be
spotted — that's the strongest evidence the delta is anti-adaptive.

Windows: 30 days back from now, split into halves for stability check.

Run:
    python3 analysis/nbm_l2_delta_audit.py

Output:
    analysis/output/nbm_l2_delta_audit.txt
    analysis/output/nbm_l2_delta_audit.json
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import pair_log_paths  # noqa: E402

OUT_TXT = os.path.join(SCRIPT_DIR, "output", "nbm_l2_delta_audit.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "nbm_l2_delta_audit.json")

# NBM emits 9 fields — cl/cm/pp/pa/pr are HRRR-only forever.
NBM_SCOPE = ("t", "dp", "ws", "wd", "wg", "sr", "cc", "ch", "h")

WINDOW_DAYS = 30
MIN_N_CELL = 50
LEAD_BANDS = [("0-5h", 0, 5), ("6-11h", 6, 11), ("12-23h", 12, 23), ("24-47h", 24, 47)]


def _band_for(lead_h):
    if lead_h is None:
        return None
    lh = int(lead_h)
    for label, lo, hi in LEAD_BANDS:
        if lo <= lh <= hi:
            return label
    return None


def _wd_abs_err(err):
    """wd errors are stored as signed degrees. Wrap to [-180, 180] and take abs."""
    e = float(err)
    while e > 180:
        e -= 360
    while e < -180:
        e += 360
    return abs(e)


def _accumulate(pair_log_path, window_start_iso, midpoint_iso):
    # (field, band) -> {sum_abs_raw, sum_abs_l2, sum_sig_raw, sum_sig_l2, n}
    # split by half for stability
    cells = defaultdict(lambda: {
        "n": 0,
        "abs_raw": 0.0, "abs_l2": 0.0,
        "sig_raw": 0.0, "sig_l2": 0.0,
        "n_a": 0, "abs_raw_a": 0.0, "abs_l2_a": 0.0,
        "n_b": 0, "abs_raw_b": 0.0, "abs_l2_b": 0.0,
    })
    with open(pair_log_path) as fin:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            field = row.get("field")
            if field not in NBM_SCOPE:
                continue
            obs_time = row.get("obs_time", "")
            if obs_time < window_start_iso:
                continue
            e_raw = row.get("error_raw_nbm")
            e_l2 = row.get("error_l2_nbm")
            if e_raw is None or e_l2 is None:
                continue
            lead_h = row.get("lead_h")
            band = _band_for(lead_h)
            if band is None:
                continue
            if field == "wd":
                ar = _wd_abs_err(e_raw)
                al = _wd_abs_err(e_l2)
                # signed bias meaningless for circular; use 0 as placeholder
                sr = 0.0
                sl = 0.0
            else:
                ar = abs(float(e_raw))
                al = abs(float(e_l2))
                sr = float(e_raw)
                sl = float(e_l2)
            c = cells[(field, band)]
            c["n"] += 1
            c["abs_raw"] += ar
            c["abs_l2"] += al
            c["sig_raw"] += sr
            c["sig_l2"] += sl
            if obs_time >= midpoint_iso:
                c["n_b"] += 1
                c["abs_raw_b"] += ar
                c["abs_l2_b"] += al
            else:
                c["n_a"] += 1
                c["abs_raw_a"] += ar
                c["abs_l2_a"] += al
    return cells


def _lift_pct(base, curr):
    if base is None or curr is None or base <= 0:
        return None
    return 100.0 * (base - curr) / base


def _mean(s, n):
    return (s / n) if n > 0 else None


def _agree_sign(a, b):
    if a is None or b is None:
        return None
    return (a >= 0 and b >= 0) or (a < 0 and b < 0)


def main():
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=WINDOW_DAYS)
    midpoint = now - timedelta(days=WINDOW_DAYS // 2)
    window_start_iso = window_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    midpoint_iso = midpoint.strftime("%Y-%m-%dT%H:%M:%SZ")

    merged = defaultdict(lambda: {
        "n": 0,
        "abs_raw": 0.0, "abs_l2": 0.0,
        "sig_raw": 0.0, "sig_l2": 0.0,
        "n_a": 0, "abs_raw_a": 0.0, "abs_l2_a": 0.0,
        "n_b": 0, "abs_raw_b": 0.0, "abs_l2_b": 0.0,
    })
    for path in pair_log_paths():
        cells = _accumulate(path, window_start_iso, midpoint_iso)
        for k, v in cells.items():
            m = merged[k]
            for kk, vv in v.items():
                m[kk] += vv

    # Roll up per (field, band) + per field overall.
    per_cell = {}
    per_field = defaultdict(lambda: {
        "n": 0, "abs_raw": 0.0, "abs_l2": 0.0, "sig_raw": 0.0, "sig_l2": 0.0,
    })
    for (field, band), c in merged.items():
        mae_raw = _mean(c["abs_raw"], c["n"])
        mae_l2 = _mean(c["abs_l2"], c["n"])
        lift = _lift_pct(mae_raw, mae_l2)
        # halves
        lift_a = _lift_pct(_mean(c["abs_raw_a"], c["n_a"]), _mean(c["abs_l2_a"], c["n_a"]))
        lift_b = _lift_pct(_mean(c["abs_raw_b"], c["n_b"]), _mean(c["abs_l2_b"], c["n_b"]))
        halves_agree = _agree_sign(lift_a, lift_b)
        # signed bias (mean signed error) — for non-wd only, meaningful
        bias_raw = _mean(c["sig_raw"], c["n"]) if field != "wd" else None
        bias_l2 = _mean(c["sig_l2"], c["n"]) if field != "wd" else None
        bias_sign_flip = None
        if bias_raw is not None and bias_l2 is not None:
            bias_sign_flip = (bias_raw >= 0) != (bias_l2 >= 0) and abs(bias_raw) > 0.1
        per_cell[(field, band)] = {
            "n": c["n"],
            "mae_raw": mae_raw,
            "mae_l2": mae_l2,
            "lift_pct": lift,
            "lift_a_pct": lift_a,
            "lift_b_pct": lift_b,
            "halves_agree": halves_agree,
            "bias_raw": bias_raw,
            "bias_l2": bias_l2,
            "bias_sign_flip": bias_sign_flip,
            "n_a": c["n_a"],
            "n_b": c["n_b"],
        }
        pf = per_field[field]
        pf["n"] += c["n"]
        pf["abs_raw"] += c["abs_raw"]
        pf["abs_l2"] += c["abs_l2"]
        pf["sig_raw"] += c["sig_raw"]
        pf["sig_l2"] += c["sig_l2"]

    # Field totals
    per_field_totals = {}
    for f, c in per_field.items():
        mae_raw = _mean(c["abs_raw"], c["n"])
        mae_l2 = _mean(c["abs_l2"], c["n"])
        per_field_totals[f] = {
            "n": c["n"],
            "mae_raw": mae_raw,
            "mae_l2": mae_l2,
            "lift_pct": _lift_pct(mae_raw, mae_l2),
            "bias_raw": _mean(c["sig_raw"], c["n"]) if f != "wd" else None,
            "bias_l2": _mean(c["sig_l2"], c["n"]) if f != "wd" else None,
        }

    # Verdict per cell.
    hurts = []
    helps = []
    washes = []
    thin = []
    for (field, band), c in per_cell.items():
        if c["n"] < MIN_N_CELL:
            thin.append((field, band, c["n"]))
            continue
        lift = c["lift_pct"]
        if lift is None:
            thin.append((field, band, c["n"]))
            continue
        if lift <= -3.0 and c["halves_agree"]:
            hurts.append((field, band, lift, c["n"]))
        elif lift >= 3.0 and c["halves_agree"]:
            helps.append((field, band, lift, c["n"]))
        else:
            washes.append((field, band, lift, c["n"]))

    hurts.sort(key=lambda x: x[2])   # most negative first
    helps.sort(key=lambda x: -x[2])  # most positive first

    # ---- TXT output ----
    lines = []
    lines.append(f"L2_NBM soundness audit — {WINDOW_DAYS}d window ending {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 100)
    lines.append("")
    lines.append("Question: does l2_nbm = raw_nbm + (l2_hrrr − raw_hrrr) actually lift l2_nbm vs raw_nbm?")
    lines.append("  positive lift = HRRR-delta transfer helps NBM (assumption vindicated for this cell)")
    lines.append("  near zero     = neutral, delta washes out")
    lines.append("  negative lift = delta HURTS — Wyman Cove bias is model-dependent for this (field, band)")
    lines.append("  ★ halves_agree flags cells where both halves of the window agree on sign (stable signal)")
    lines.append("")
    lines.append("Per-field totals (pooled across all leads):")
    lines.append(f"  {'field':6} {'n':>7} {'MAE raw_nbm':>14} {'MAE l2_nbm':>14} {'lift %':>8}  {'bias raw':>10} {'bias l2':>10}")
    lines.append("  " + "-" * 90)
    for f in NBM_SCOPE:
        c = per_field_totals.get(f)
        if not c:
            continue
        br = f"{c['bias_raw']:+8.3f}" if c["bias_raw"] is not None else "     —  "
        bl = f"{c['bias_l2']:+8.3f}"  if c["bias_l2"]  is not None else "     —  "
        lp = f"{c['lift_pct']:+6.1f}" if c["lift_pct"] is not None else "   —  "
        lines.append(f"  {f:6} {c['n']:>7} {c['mae_raw']:>14.3f} {c['mae_l2']:>14.3f} {lp:>8}  {br:>10} {bl:>10}")

    lines.append("")
    lines.append("Per-cell (field × lead band):")
    lines.append(f"  {'field':6} {'band':7} {'n':>6} {'MAE raw':>10} {'MAE l2':>10} {'lift %':>8}  {'A':>7} {'B':>7} {'agree':>6}  {'bias flip':>10}")
    lines.append("  " + "-" * 100)
    for f in NBM_SCOPE:
        for band, _lo, _hi in LEAD_BANDS:
            c = per_cell.get((f, band))
            if not c:
                continue
            lp = f"{c['lift_pct']:+6.1f}" if c["lift_pct"] is not None else "   —  "
            la = f"{c['lift_a_pct']:+6.1f}" if c["lift_a_pct"] is not None else "   —  "
            lb = f"{c['lift_b_pct']:+6.1f}" if c["lift_b_pct"] is not None else "   —  "
            ag = "★" if c["halves_agree"] else ("—" if c["halves_agree"] is not None else "?")
            bf = "FLIP!" if c["bias_sign_flip"] else ("—" if c["bias_sign_flip"] is not None else "?")
            lines.append(f"  {f:6} {band:7} {c['n']:>6} {c['mae_raw']:>10.3f} {c['mae_l2']:>10.3f} {lp:>8}  {la:>7} {lb:>7} {ag:>6}  {bf:>10}")

    lines.append("")
    lines.append("Verdict per cell (n>=%d, |lift|>=3%%, halves agree):" % MIN_N_CELL)
    lines.append("=" * 100)
    if hurts:
        lines.append(f"  HURTS ({len(hurts)}): the delta transfer is worse than raw NBM for these cells.")
        for f, band, lift, n in hurts:
            lines.append(f"    {f:6} {band:7} lift={lift:+6.1f}% n={n}")
    else:
        lines.append("  HURTS (0): none.")
    lines.append("")
    if helps:
        lines.append(f"  HELPS ({len(helps)}): the delta transfer wins.")
        for f, band, lift, n in helps:
            lines.append(f"    {f:6} {band:7} lift={lift:+6.1f}% n={n}")
    else:
        lines.append("  HELPS (0): none.")
    lines.append("")
    lines.append(f"  WASHES ({len(washes)}): |lift| < 3% or halves disagree (noise-adjacent).")
    lines.append(f"  THIN ({len(thin)}): n < {MIN_N_CELL}.")

    # Overall verdict summary
    n_hurts = len(hurts)
    n_helps = len(helps)
    n_total_gradeable = n_hurts + n_helps + len(washes)
    lines.append("")
    lines.append("=" * 100)
    if n_total_gradeable == 0:
        verdict = "VERDICT: NO SIGNAL — insufficient graded cells."
    elif n_hurts == 0 and n_helps > 0:
        verdict = f"VERDICT: FOUNDATION SOUND — delta helps in {n_helps} cells, hurts in 0, washes in {len(washes)}."
    elif n_hurts > 0 and n_helps > n_hurts * 2:
        verdict = f"VERDICT: MOSTLY SOUND — delta helps in {n_helps}, hurts in {n_hurts} (helps dominate 2:1)."
    elif n_hurts >= n_helps:
        verdict = f"VERDICT: FOUNDATION AT RISK — delta hurts {n_hurts} cells, helps only {n_helps}. Investigate before adding more layers on top."
    else:
        verdict = f"VERDICT: MIXED — {n_helps} help, {n_hurts} hurt, {len(washes)} wash."
    lines.append(verdict)

    txt = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as f:
        f.write(txt)
    print(txt)

    # ---- JSON output ----
    def _to_json(cell):
        return {k: v for k, v in cell.items()}
    out_json = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": WINDOW_DAYS,
        "min_n_cell": MIN_N_CELL,
        "per_field_totals": per_field_totals,
        "per_cell": {f"{f}::{b}": _to_json(c) for (f, b), c in per_cell.items()},
        "hurts": [{"field": f, "band": b, "lift_pct": lift, "n": n} for f, b, lift, n in hurts],
        "helps": [{"field": f, "band": b, "lift_pct": lift, "n": n} for f, b, lift, n in helps],
        "verdict": verdict,
    }
    with open(OUT_JSON, "w") as f:
        json.dump(out_json, f, indent=2, default=str)
    print(f"wrote {OUT_TXT}")
    print(f"wrote {OUT_JSON}")

    try:
        from weather_collector.gcs_io import upload_json  # noqa: E402
        upload_json(out_json, "nbm_l2_delta_audit.json", "nbm_l2_delta_audit.json")
        print("  ✓ Published to gs://myweather-data/nbm_l2_delta_audit.json")
    except Exception as e:
        print(f"  ⚠ GCS upload skipped ({type(e).__name__}: {e}) — local file still written")


if __name__ == "__main__":
    main()
