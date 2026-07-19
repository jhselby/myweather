"""Stage 1 preview - t L2 skip-table halves-verified per-cell verdict.

t is currently one of the weakest fields by "Production beats raw" metric:
recent Production MAE 1.90 F vs raw L1 MAE ~1.87 F. Since t has L1 -> L2
only (no L3/L4, Lt retired 07-13), the ~0.03 F gap between Production and
raw IS L2's damage on average. This Stage 1 asks: is the damage
concentrated in specific (regime x lead_band) cells where a SKIP would
fall back to raw and improve pooled Production?

Follow-on to tonight's wg/ws L3 Stage 1 pattern, but attacking L2 instead
of L3. Same halves-verified per-cell architecture.

Windows mirror ch Stage 2 + wg/ws L3 Stage 1 exactly (30d, split into
recent 15d + prior 15d halves).

Per-cell verdict rules (baseline = L1 raw, gated = L2 applied):
  SKIP    - n >= MIN_N and L2 loses to L1 by >= L2_HURT_FLOOR_PCT on
            BOTH halves AND full window (halves-stability required). L1
            must also beat persistence in the full window (otherwise the
            cell is a persistence-gate candidate, not an L2-skip
            candidate).
  MARGIN  - L2 loses full but one half is < floor
  KEEP    - L2 helps on full or halves disagree in sign
  THIN    - n < MIN_N in any window

Emits:
  analysis/output/h_t_l2_regression_stage1.txt
  weather_collector/data/t_l2_skip_table_curated.json   (preview, not wired)
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_TXT = os.path.join(HERE, "output", "h_t_l2_regression_stage1.txt")
OUT_JSON = os.path.abspath(os.path.join(
    HERE, "..", "weather_collector", "data", "t_l2_skip_table_curated.json"
))

# 2026-07-19: slid forward 8 days so windows cover post-shift data
# (MLC collapse / cc-cluster distribution shift). See v0.6.358.
WIN_A_LO, WIN_A_HI = "2026-07-04T00:00", "2026-07-19T00:00"
WIN_B_LO, WIN_B_HI = "2026-06-19T00:00", "2026-07-04T00:00"
WIN_FULL_LO, WIN_FULL_HI = "2026-06-19T00:00", "2026-07-19T00:00"

FIELD = "t"
MIN_N_CELL = 200
L2_HURT_FLOOR_PCT = 3.0

LEAD_BANDS = [
    ("0-5",   1,  5),
    ("6-11",  6, 11),
    ("12-23", 12, 23),
    ("24-47", 24, 47),
]


def lead_band(lead):
    for name, lo, hi in LEAD_BANDS:
        if lo <= lead <= hi:
            return name
    return None


def hour_floor(ts):
    if ts is None or len(ts) < 16:
        return None
    return ts[:14] + "00"


def compute():
    path = cached_path(URL)

    print("[1/2] Building t obs index for persistence sanity check...", file=sys.stderr)
    obs_ts = {}
    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            vt = r.get("valid_time")
            ob = r.get("observed")
            if vt is None or ob is None:
                continue
            if vt not in obs_ts:
                obs_ts[vt] = float(ob)
    print(f"    obs index size: {len(obs_ts):,}", file=sys.stderr)

    print("[2/2] Scoring L1 vs L2 vs persistence per (regime x lead_band)...", file=sys.stderr)
    accum = defaultdict(lambda: {"n": 0, "ae_l1": 0.0, "ae_l2": 0.0,
                                  "ae_pers": 0.0, "n_l1_missing": 0})
    n_rows = 0
    n_no_persist = 0

    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
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
            fc_l1 = r.get("forecast_l1")
            fc_l2 = r.get("forecast_l2")
            if ob is None or fc_l2 is None:
                continue

            persist = obs_ts.get(hour_floor(rt))
            if persist is None:
                n_no_persist += 1
                continue

            state_fc = r.get("state_fc") or {}
            regime = state_fc.get("regime_synoptic") or "unknown"

            ob_f = float(ob)
            err_l2 = float(fc_l2) - ob_f
            err_pers = float(persist) - ob_f

            n_rows += 1
            for win in windows:
                a = accum[(win, regime, band)]
                a["n"] += 1
                a["ae_l2"] += abs(err_l2)
                a["ae_pers"] += abs(err_pers)
                if fc_l1 is None:
                    a["n_l1_missing"] += 1
                    continue
                err_l1 = float(fc_l1) - ob_f
                a["ae_l1"] += abs(err_l1)

    print(f"    scored {n_rows:,} t rows; {n_no_persist:,} skipped (no persist)",
          file=sys.stderr)
    return accum


def mae(bkt, key, n_key="n"):
    n = bkt[n_key]
    return (bkt[key] / n) if n else None


def cell_verdict(l1_f, l2_f, l1_a, l2_a, l1_b, l2_b,
                 pers_f, n_full, n_l1_missing_full):
    if n_full < MIN_N_CELL:
        return "THIN", None, None, None
    if n_l1_missing_full > 0.1 * n_full:
        return "THIN", None, None, None
    if l1_f is None or l2_f is None:
        return "THIN", None, None, None
    if pers_f is not None and pers_f < l1_f:
        return "PERSISTENCE_TERRITORY", None, None, None
    d_full = 100.0 * (l2_f - l1_f) / l1_f if l1_f else 0.0
    d_a = 100.0 * (l2_a - l1_a) / l1_a if (l1_a and l2_a is not None) else None
    d_b = 100.0 * (l2_b - l1_b) / l1_b if (l1_b and l2_b is not None) else None
    if (d_full >= L2_HURT_FLOOR_PCT
        and d_a is not None and d_a >= L2_HURT_FLOOR_PCT
        and d_b is not None and d_b >= L2_HURT_FLOOR_PCT):
        return "SKIP", d_full, d_a, d_b
    if d_full < 0 or (d_a is not None and d_b is not None and (d_a * d_b) < 0):
        return "KEEP", d_full, d_a, d_b
    return "MARGIN", d_full, d_a, d_b


def emit(accum):
    regimes = sorted({key[1] for key in accum.keys()})
    bands = [name for name, _, _ in LEAD_BANDS]

    lines = []
    lines.append("=" * 100)
    lines.append("t L2 SKIP-TABLE - Stage 1 preview (halves-verified per regime x lead_band)")
    lines.append("=" * 100)
    lines.append("")
    lines.append("Baseline = L1 raw HRRR. Gated = L2 applied (Kalman-blended station bias).")
    lines.append(f"Windows: A={WIN_A_LO[:10]}->{WIN_A_HI[:10]}, "
                 f"B={WIN_B_LO[:10]}->{WIN_B_HI[:10]}, FULL={WIN_FULL_LO[:10]}->{WIN_FULL_HI[:10]}")
    lines.append(f"Per-cell SKIP verdict: halves-stability + full > +{L2_HURT_FLOOR_PCT}% (L2 worse than L1).")
    lines.append(f"PERSISTENCE_TERRITORY = persistence beats L1 in full window; separate discussion.")
    lines.append(f"MIN_N per cell: {MIN_N_CELL}")
    lines.append("")

    lines.append("=" * 100)
    lines.append("PER-CELL: L2 vs L1 (positive delta = L2 hurts)")
    lines.append("=" * 100)
    header = (f"{'regime':<12}{'band':<8}{'n':>8}"
              f"{'L1 MAE':>10}{'L2 MAE':>10}{'pers MAE':>10}"
              f"{'D full %':>10}{'D A %':>9}{'D B %':>9}  verdict")
    lines.append(header)
    lines.append("-" * len(header))

    cells = {}
    for regime in regimes:
        for band in bands:
            bkt_f = accum[("FULL", regime, band)]
            n_full = bkt_f["n"]
            n_l1_ok_f = n_full - bkt_f["n_l1_missing"]
            l1_f = (bkt_f["ae_l1"] / n_l1_ok_f) if n_l1_ok_f else None
            l2_f = mae(bkt_f, "ae_l2")
            pers_f = mae(bkt_f, "ae_pers")

            bkt_a = accum[("A", regime, band)]
            n_l1_ok_a = bkt_a["n"] - bkt_a["n_l1_missing"]
            l1_a = (bkt_a["ae_l1"] / n_l1_ok_a) if n_l1_ok_a else None
            l2_a = mae(bkt_a, "ae_l2")

            bkt_b = accum[("B", regime, band)]
            n_l1_ok_b = bkt_b["n"] - bkt_b["n_l1_missing"]
            l1_b = (bkt_b["ae_l1"] / n_l1_ok_b) if n_l1_ok_b else None
            l2_b = mae(bkt_b, "ae_l2")

            if n_full == 0:
                continue
            verdict, d_full, d_a, d_b = cell_verdict(
                l1_f, l2_f, l1_a, l2_a, l1_b, l2_b, pers_f, n_full, bkt_f["n_l1_missing"]
            )
            star = " *" if verdict == "SKIP" else ""
            d_full_s = f"{d_full:+.2f}" if d_full is not None else "  n/a"
            d_a_s = f"{d_a:+.2f}" if d_a is not None else "  n/a"
            d_b_s = f"{d_b:+.2f}" if d_b is not None else "  n/a"
            l1_s = f"{l1_f:>10.3f}" if l1_f is not None else "       n/a"
            l2_s = f"{l2_f:>10.3f}" if l2_f is not None else "       n/a"
            pers_s = f"{pers_f:>10.3f}" if pers_f is not None else "       n/a"
            lines.append(f"{regime:<12}{band:<8}{n_full:>8,}"
                         f"{l1_s}{l2_s}{pers_s}"
                         f"{d_full_s:>10}{d_a_s:>9}{d_b_s:>9}  {verdict}{star}")
            cells.setdefault(regime, {})[band] = {
                "n": n_full,
                "mae_l1": round(l1_f, 3) if l1_f is not None else None,
                "mae_l2": round(l2_f, 3) if l2_f is not None else None,
                "mae_pers": round(pers_f, 3) if pers_f is not None else None,
                "delta_full_pct": round(d_full, 2) if d_full is not None else None,
                "delta_a_pct": round(d_a, 2) if d_a is not None else None,
                "delta_b_pct": round(d_b, 2) if d_b is not None else None,
                "verdict": verdict,
            }
        lines.append("")

    skip_cells, margin_cells, keep_cells, thin_cells, pers_cells = [], [], [], [], []
    for regime, bandmap in cells.items():
        for band, d in bandmap.items():
            key = (regime, band)
            v = d["verdict"]
            if v == "SKIP":
                skip_cells.append(key)
            elif v == "MARGIN":
                margin_cells.append(key)
            elif v == "KEEP":
                keep_cells.append(key)
            elif v == "THIN":
                thin_cells.append(key)
            elif v == "PERSISTENCE_TERRITORY":
                pers_cells.append(key)

    lines.append("=" * 100)
    lines.append("ROLLUP")
    lines.append("=" * 100)
    total = len(skip_cells) + len(margin_cells) + len(keep_cells) + len(thin_cells) + len(pers_cells)
    lines.append(f"  SKIP:                 {len(skip_cells):>3} cells  (candidate for L2 skip table)")
    lines.append(f"  MARGIN:               {len(margin_cells):>3} cells")
    lines.append(f"  KEEP:                 {len(keep_cells):>3} cells  (L2 helps or halves disagree)")
    lines.append(f"  THIN:                 {len(thin_cells):>3} cells")
    lines.append(f"  PERSISTENCE_TERRITORY:{len(pers_cells):>3} cells  (persistence-gate discussion)")
    lines.append(f"  total judged: {total}")
    lines.append("")

    if skip_cells:
        lines.append("SKIP concentration:")
        skip_by_band = defaultdict(list)
        skip_by_regime = defaultdict(list)
        for regime, band in skip_cells:
            skip_by_band[band].append(regime)
            skip_by_regime[regime].append(band)
        for band, regs in sorted(skip_by_band.items()):
            lines.append(f"  band {band:<6}: {len(regs)} regimes -> {sorted(regs)}")
        for regime, bnds in sorted(skip_by_regime.items()):
            lines.append(f"  regime {regime:<12}: {len(bnds)} bands -> {sorted(bnds)}")
        lines.append("")

    lines.append("=" * 100)
    lines.append("PROPOSED SKIP_TABLE ENTRY for decay_apply.py")
    lines.append("=" * 100)
    if skip_cells:
        lines.append('  # No existing t L2 skip cells (t is L1->L2 only, no prior skip table).')
        lines.append('  SKIP_TABLE[("t", "l2")] = [')
        band_bounds = {name: (lo, hi) for name, lo, hi in LEAD_BANDS}
        by_regime = defaultdict(list)
        for regime, band in skip_cells:
            lo, hi = band_bounds[band]
            by_regime[regime].append((lo, hi + 1))
        for regime in sorted(by_regime):
            spans = sorted(by_regime[regime])
            merged = [spans[0]]
            for lo, hi in spans[1:]:
                if lo <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
                else:
                    merged.append((lo, hi))
            for lo, hi in merged:
                covered_bands = [b for b, (blo, bhi) in band_bounds.items() if lo <= blo and bhi + 1 <= hi]
                lines.append(f'      ("{regime}", {lo:>2}, {hi:>2}),  # bands: {"+".join(covered_bands)}')
        lines.append('  ]')
        lines.append('  # Note: decay_apply.py SKIP_TABLE architecture currently only supports L3/L4.')
        lines.append('  # Wiring an L2 skip needs either extending _should_skip() to L2 or adding a')
        lines.append('  # sibling skip in corrected_hourly.py (or wherever L2 is applied for t).')
        lines.append('  # Small infra change; verify placement before shipping.')
    else:
        lines.append("  (no per-cell skips required - L2 helps or is halves-unstable everywhere)")
        lines.append("  Interpretation: t is at ceiling - L2's average slight damage is not concentrated")
        lines.append("  in extractable cells. Consider option 2 (Lt regime-skip halves-verified) or")
        lines.append("  option 3 (accept raw-HRRR ceiling).")
    lines.append("")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "forecast_error_log.jsonl",
        "field": FIELD,
        "layer": "l2",
        "windows": {
            "A_recent_15d": [WIN_A_LO, WIN_A_HI],
            "B_prior_15d":  [WIN_B_LO, WIN_B_HI],
            "FULL_30d":     [WIN_FULL_LO, WIN_FULL_HI],
        },
        "fit_rules": {
            "min_n_cell": MIN_N_CELL,
            "l2_hurt_floor_pct": L2_HURT_FLOOR_PCT,
            "halves_stability_required": True,
            "lead_bands": bands,
        },
        "cells": cells,
        "skip_cells": [{"regime": r, "lead_band": b} for r, b in sorted(skip_cells)],
        "persistence_territory_cells": [
            {"regime": r, "lead_band": b} for r, b in sorted(pers_cells)
        ],
        "rollup": {
            "skip": len(skip_cells),
            "margin": len(margin_cells),
            "keep": len(keep_cells),
            "thin": len(thin_cells),
            "persistence_territory": len(pers_cells),
        },
        "notes": (
            "Stage 1 preview. Not wired. SKIP cells are candidates to add to a new "
            "SKIP_TABLE[('t','l2')] entry once decay_apply.py extends the skip "
            "table architecture to cover L2 (currently only L3/L4). "
            "PERSISTENCE_TERRITORY cells belong to a separate persistence-gate "
            "discussion, not the L2 skip table."
        ),
    }

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    print("\n".join(lines))
    print(f"\nwrote {OUT_TXT}")
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    emit(compute())
