"""Stage 1 preview — L3 fc-magnitude-conditional skip table (wg, ws, cm).

Follow-on to [[h_asymmetric_l3.py]] Stage 0 verdict: L3 helps on
over-forecast rows (fc > obs) but HURTS on under-forecast rows. Digest
gaps:
  wg  126.8pp  (over +40.6% / under −86.2%)
  ws   65.7pp  (over +22.9% / under −42.8%)
  cm   14.7pp  (over +10.5% / under  −4.2%)

The over/under split is not knowable at forecast time (needs obs), but
raw fc magnitude IS. Hypothesis: L3 is a mean-bias subtraction. When
raw fc is above the cell's median training value, most rows are
over-forecasts and L3 helps. When raw fc is below median, most rows are
under-forecasts and L3 hurts.

This Stage 1 extends the existing [[wg-l3-skip-table]] architecture with
an fc-magnitude dimension. Cells are (regime × lead_band × fc_quartile).
SKIP verdict at (regime, band, fc_bin) means: at collector time, when
this specific forecast row falls into fc_bin for its (regime, band),
fall back to L2 instead of applying L3.

Windows mirror wg L3 stage1 exactly (30d well-stamped, split into recent
15d + prior 15d halves).

fc_bin construction: quartiles computed per (regime, band) from the full
window's fc values. Emitted with the curated JSON so collector can look
up the boundaries at stamp time.

Per-cell verdict rules (baseline = L2 alone, gated = L3 applied on top):
  SKIP    — n >= MIN_N and L3 loses to L2 by >= L3_HURT_FLOOR_PCT on
            BOTH halves AND full window (halves-stability required)
  MARGIN  — L3 loses full but one half is < floor
  KEEP    — L3 helps on full or halves disagree in sign
  THIN    — n < MIN_N in any window

Emits:
  analysis/output/h_l3_asymmetric_stage1.txt   (combined report)
  weather_collector/data/<field>_l3_asymmetric_skip_curated.json  (one per field)
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_TXT = os.path.join(HERE, "output", "h_l3_asymmetric_stage1.txt")
DATA_DIR = os.path.abspath(os.path.join(HERE, "..", "weather_collector", "data"))

WIN_A_LO, WIN_A_HI = "2026-07-08T00:00", "2026-07-23T00:00"
WIN_B_LO, WIN_B_HI = "2026-06-23T00:00", "2026-07-08T00:00"
WIN_FULL_LO, WIN_FULL_HI = "2026-06-23T00:00", "2026-07-23T00:00"

# Fields with real asymmetric-L3 findings per Stage 0 (h_asymmetric_l3.py).
FIELDS = ("wg", "ws", "cm")
MIN_N_CELL = 100  # smaller than parent skip table because 4x fc-bin split
L3_HURT_FLOOR_PCT = 3.0

LEAD_BANDS = [
    ("0-5",   1,  5),
    ("6-11",  6, 11),
    ("12-23", 12, 23),
    ("24-47", 24, 47),
]

FC_BINS = ("Q1", "Q2", "Q3", "Q4")


def lead_band(lead):
    for name, lo, hi in LEAD_BANDS:
        if lo <= lead <= hi:
            return name
    return None


def quantiles(vals):
    """Return (q1, q2, q3) breakpoints for a list of numbers. q2 is median."""
    if not vals:
        return None
    v = sorted(vals)
    n = len(v)
    def pick(p):
        i = max(0, min(n - 1, int(p * n)))
        return v[i]
    return pick(0.25), pick(0.50), pick(0.75)


def fc_bin(fc, cuts):
    """Bucket fc into Q1..Q4 using precomputed (q1, q2, q3) cuts."""
    if cuts is None:
        return None
    q1, q2, q3 = cuts
    if fc < q1: return "Q1"
    if fc < q2: return "Q2"
    if fc < q3: return "Q3"
    return "Q4"


def compute(field):
    path = cached_path(URL)

    # Pass 1: gather fc values per (regime, band) to compute quartile cuts.
    print(f"[{field} 1/2] Gathering fc distribution for quartile cuts...", file=sys.stderr)
    fc_vals = defaultdict(list)
    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != field:
                continue
            rt = r.get("run_time", "")
            if not (WIN_FULL_LO <= rt < WIN_FULL_HI):
                continue
            lead = r.get("lead_h")
            fc = r.get("forecast")
            if lead is None or fc is None:
                continue
            try:
                lead = int(lead)
            except Exception:
                continue
            band = lead_band(lead)
            if band is None:
                continue
            state_fc = r.get("state_fc") or {}
            regime = state_fc.get("regime_synoptic") or "unknown"
            fc_vals[(regime, band)].append(float(fc))

    cuts = {k: quantiles(v) for k, v in fc_vals.items()}
    print(f"    {len(cuts)} (regime, band) cells with quartile cuts", file=sys.stderr)

    # Pass 2: score L2 vs L3 per (window, regime, band, fc_bin).
    print(f"[{field} 2/2] Scoring L2 vs L3 per (regime × band × fc_bin)...", file=sys.stderr)
    accum = defaultdict(lambda: {"n": 0, "ae_l1": 0.0, "ae_l2": 0.0, "ae_l3": 0.0,
                                  "n_l2_missing": 0, "n_l3_missing": 0})
    n_rows = 0

    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != field:
                continue
            rt = r.get("run_time", "")
            if WIN_A_LO <= rt < WIN_A_HI:
                windows = ["A", "FULL"]
            elif WIN_B_LO <= rt < WIN_B_HI:
                windows = ["B", "FULL"]
            else:
                continue

            lead = r.get("lead_h")
            if lead is None:
                continue
            try:
                lead = int(lead)
            except Exception:
                continue
            band = lead_band(lead)
            if band is None:
                continue

            ob = r.get("observed")
            fc = r.get("forecast")
            if ob is None or fc is None:
                continue
            fc_l2 = r.get("forecast_l2")
            fc_l3 = r.get("forecast_l3")

            state_fc = r.get("state_fc") or {}
            regime = state_fc.get("regime_synoptic") or "unknown"
            cell_cuts = cuts.get((regime, band))
            if cell_cuts is None:
                continue
            fcb = fc_bin(float(fc), cell_cuts)
            if fcb is None:
                continue

            ob_f = float(ob)
            err_l1 = abs(float(fc) - ob_f)
            err_l2 = abs(float(fc_l2) - ob_f) if fc_l2 is not None else None
            err_l3 = abs(float(fc_l3) - ob_f) if fc_l3 is not None else None

            n_rows += 1
            for win in windows:
                a = accum[(win, regime, band, fcb)]
                a["n"] += 1
                a["ae_l1"] += err_l1
                if err_l2 is None:
                    a["n_l2_missing"] += 1
                else:
                    a["ae_l2"] += err_l2
                if err_l3 is None:
                    a["n_l3_missing"] += 1
                else:
                    a["ae_l3"] += err_l3

    print(f"    scored {n_rows:,} {field} rows", file=sys.stderr)
    return accum, cuts


def mae(bkt, key, n_key="n", missing_key=None):
    n = bkt[n_key]
    if missing_key:
        n -= bkt.get(missing_key, 0)
    return (bkt[key] / n) if n > 0 else None


def cell_verdict(l2_f, l3_f, l2_a, l3_a, l2_b, l3_b, n_full):
    if n_full < MIN_N_CELL:
        return "THIN", None, None, None
    if l2_f is None or l3_f is None:
        return "THIN", None, None, None
    d_full = 100.0 * (l3_f - l2_f) / l2_f if l2_f else 0.0
    d_a = 100.0 * (l3_a - l2_a) / l2_a if (l2_a and l3_a is not None) else None
    d_b = 100.0 * (l3_b - l2_b) / l2_b if (l2_b and l3_b is not None) else None
    if (d_full >= L3_HURT_FLOOR_PCT
        and d_a is not None and d_a >= L3_HURT_FLOOR_PCT
        and d_b is not None and d_b >= L3_HURT_FLOOR_PCT):
        return "SKIP", d_full, d_a, d_b
    if d_full < 0 or (d_a is not None and d_b is not None and (d_a * d_b) < 0):
        return "KEEP", d_full, d_a, d_b
    return "MARGIN", d_full, d_a, d_b


def emit(field, accum, cuts, lines):
    """Append per-field report to `lines` and return (skip_cells, verdict_str,
    payload_dict). Writes the per-field curated JSON."""
    regimes = sorted({key[1] for key in accum.keys()})
    bands = [name for name, _, _ in LEAD_BANDS]

    lines.append("=" * 110)
    lines.append(f"{field} L3 ASYMMETRIC SKIP-TABLE — Stage 1 preview (regime × lead_band × fc_bin)")
    lines.append("=" * 110)
    lines.append("")
    lines.append("Hypothesis: L3 hurts on under-forecast rows (raw fc low). Split fc into")
    lines.append("quartiles per (regime, band); skip L3 in fc-bins where L3 loses stably.")
    lines.append(f"Windows: A={WIN_A_LO[:10]}→{WIN_A_HI[:10]}, "
                 f"B={WIN_B_LO[:10]}→{WIN_B_HI[:10]}, FULL={WIN_FULL_LO[:10]}→{WIN_FULL_HI[:10]}")
    lines.append(f"MIN_N per cell: {MIN_N_CELL}   L3 hurt floor: {L3_HURT_FLOOR_PCT}%")
    lines.append("")

    # === Per-cell table ===
    lines.append("=" * 110)
    lines.append("PER-CELL: L3 vs L2 by (regime × band × fc_bin)")
    lines.append("=" * 110)
    header = (f"{'regime':<12}{'band':<8}{'fc':<4}{'n':>8}"
              f"{'L2 MAE':>10}{'L3 MAE':>10}"
              f"{'Δ full %':>10}{'Δ A %':>9}{'Δ B %':>9}  verdict")
    lines.append(header)
    lines.append("-" * len(header))

    cells = {}
    for regime in regimes:
        for band in bands:
            for fcb in FC_BINS:
                bkt_f = accum[("FULL", regime, band, fcb)]
                bkt_a = accum[("A", regime, band, fcb)]
                bkt_b = accum[("B", regime, band, fcb)]
                n_full = bkt_f["n"]
                l2_f = mae(bkt_f, "ae_l2", missing_key="n_l2_missing")
                l3_f = mae(bkt_f, "ae_l3", missing_key="n_l3_missing")
                l2_a = mae(bkt_a, "ae_l2", missing_key="n_l2_missing")
                l3_a = mae(bkt_a, "ae_l3", missing_key="n_l3_missing")
                l2_b = mae(bkt_b, "ae_l2", missing_key="n_l2_missing")
                l3_b = mae(bkt_b, "ae_l3", missing_key="n_l3_missing")
                if n_full == 0:
                    continue
                verdict, d_full, d_a, d_b = cell_verdict(
                    l2_f, l3_f, l2_a, l3_a, l2_b, l3_b, n_full
                )
                star = " ★" if verdict == "SKIP" else ""
                d_full_s = f"{d_full:+.2f}" if d_full is not None else "  n/a"
                d_a_s = f"{d_a:+.2f}" if d_a is not None else "  n/a"
                d_b_s = f"{d_b:+.2f}" if d_b is not None else "  n/a"
                l2_s = f"{l2_f:>10.3f}" if l2_f is not None else "       n/a"
                l3_s = f"{l3_f:>10.3f}" if l3_f is not None else "       n/a"
                lines.append(f"{regime:<12}{band:<8}{fcb:<4}{n_full:>8,}"
                             f"{l2_s}{l3_s}"
                             f"{d_full_s:>10}{d_a_s:>9}{d_b_s:>9}  {verdict}{star}")
                cells.setdefault(regime, {}).setdefault(band, {})[fcb] = {
                    "n": n_full,
                    "mae_l2": round(l2_f, 3) if l2_f is not None else None,
                    "mae_l3": round(l3_f, 3) if l3_f is not None else None,
                    "delta_full_pct": round(d_full, 2) if d_full is not None else None,
                    "delta_a_pct": round(d_a, 2) if d_a is not None else None,
                    "delta_b_pct": round(d_b, 2) if d_b is not None else None,
                    "verdict": verdict,
                }
            lines.append("")

    # === Rollup ===
    skip_cells, keep_cells, margin_cells, thin_cells = [], [], [], []
    for regime, bandmap in cells.items():
        for band, binmap in bandmap.items():
            for fcb, d in binmap.items():
                key = (regime, band, fcb)
                {"SKIP": skip_cells, "KEEP": keep_cells,
                 "MARGIN": margin_cells, "THIN": thin_cells}[d["verdict"]].append(key)

    lines.append("=" * 110)
    lines.append("ROLLUP")
    lines.append("=" * 110)
    total = len(skip_cells) + len(keep_cells) + len(margin_cells) + len(thin_cells)
    lines.append(f"  SKIP:   {len(skip_cells):>3} cells (L3 stably hurts — skip in these fc_bins)")
    lines.append(f"  KEEP:   {len(keep_cells):>3} cells (L3 helps or mixed)")
    lines.append(f"  MARGIN: {len(margin_cells):>3} cells")
    lines.append(f"  THIN:   {len(thin_cells):>3} cells")
    lines.append(f"  total judged: {total}")
    lines.append("")

    # === Asymmetry check per (regime × band): does SKIP concentrate in low fc bins? ===
    lines.append("=" * 110)
    lines.append("ASYMMETRY BY fc_bin — does L3 fail concentrate in low-fc bins (under-forecast side)?")
    lines.append("=" * 110)
    fc_bin_skip_counts = {b: 0 for b in FC_BINS}
    fc_bin_total = {b: 0 for b in FC_BINS}
    for r, b, fcb in skip_cells:
        fc_bin_skip_counts[fcb] += 1
    for r, b, fcb in skip_cells + keep_cells + margin_cells:
        fc_bin_total[fcb] += 1
    for fcb in FC_BINS:
        total_cells = fc_bin_total[fcb]
        skip_share = 100.0 * fc_bin_skip_counts[fcb] / total_cells if total_cells else 0.0
        lines.append(f"  {fcb}: {fc_bin_skip_counts[fcb]:>2}/{total_cells:>2} SKIP  ({skip_share:.0f}%)")
    lines.append("")

    # === Per-field verdict ===
    if len(skip_cells) >= 2:
        overall = (f"{field} verdict: STAGE 1 HIT — {len(skip_cells)} SKIP cell(s) at floor "
                   f"{L3_HURT_FLOOR_PCT}% under fc-bin split.")
    elif skip_cells:
        overall = f"{field} verdict: MARGINAL — {len(skip_cells)} SKIP + {len(margin_cells)} MARGIN."
    else:
        overall = f"{field} verdict: HOLD — fc-bin split does not produce stable per-cell L3 skips."
    lines.append(overall)
    lines.append("")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "forecast_error_log.jsonl",
        "field": field,
        "windows": {
            "A_recent_15d": [WIN_A_LO, WIN_A_HI],
            "B_prior_15d":  [WIN_B_LO, WIN_B_HI],
            "FULL_30d":     [WIN_FULL_LO, WIN_FULL_HI],
        },
        "fit_rules": {
            "min_n_cell": MIN_N_CELL,
            "l3_hurt_floor_pct": L3_HURT_FLOOR_PCT,
            "halves_stability_required": True,
            "lead_bands": [b for b, _, _ in LEAD_BANDS],
            "fc_bins": list(FC_BINS),
        },
        "fc_quartile_cuts": {
            f"{r}|{b}": {"q1": round(q[0], 3), "q2": round(q[1], 3), "q3": round(q[2], 3)}
            for (r, b), q in cuts.items() if q is not None
        },
        "cells": cells,
        "rollup": {
            "skip": len(skip_cells),
            "keep": len(keep_cells),
            "margin": len(margin_cells),
            "thin": len(thin_cells),
        },
        "notes": (
            "Live. Read by decay_apply._load_asymmetric_table + "
            "_should_skip_asymmetric (v0.6.366 wg, v0.6.370 ws — additive on "
            "top of existing regime × band SKIP_TABLE). SKIP verdict at "
            "(regime, band, fc_bin) fires: fall back to L2 (no L3) when raw "
            "fc at forecast time falls into fc_bin for its (regime, band). "
            "Cells that match the pre-existing SKIP_TABLE fire the older gate "
            "first; this table only adds skips, never removes them."
        ),
    }

    out_json = os.path.join(DATA_DIR, f"{field}_l3_asymmetric_skip_curated.json")
    with open(out_json, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"wrote {out_json}", file=sys.stderr)
    return skip_cells, overall


def main():
    lines = []
    verdicts = []
    total_skip = 0
    for field in FIELDS:
        accum, cuts = compute(field)
        skip_cells, verdict = emit(field, accum, cuts, lines)
        verdicts.append((field, len(skip_cells)))
        total_skip += len(skip_cells)

    # Combined verdict for exec summary.
    lines.append("=" * 110)
    lines.append("COMBINED VERDICT")
    lines.append("=" * 110)
    for f, n in verdicts:
        lines.append(f"  {f}: {n} SKIP cells")
    if total_skip >= 4:
        lines.append(f"Verdict: LIVE — {total_skip} SKIP cells across {len(FIELDS)} fields "
                     f"({', '.join(f for f, n in verdicts if n)}). "
                     f"Table wired in decay_apply.py since v0.6.366 (wg) / v0.6.370 (ws).")
    elif total_skip:
        lines.append(f"Verdict: MARGINAL — {total_skip} SKIP cells across fields.")
    else:
        lines.append("Verdict: HOLD — no field cleared fc-bin skip threshold stably.")
    lines.append("")

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {OUT_TXT}")


if __name__ == "__main__":
    main()
