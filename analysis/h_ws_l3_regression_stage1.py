"""Stage 1 preview — ws L3 skip-table halves-verified per-cell verdict.

Follow-on to ws-in-h_regime_l3 Stage 0 verdict (07-14 digest): L3 helps in
5 of 8 regimes (frontal −48%, calm −31%, sw_flow −15%, pre_frontal −12%,
se_flow −5%), flat in sea_breeze (+3%), loses in ne_flow (+4%, already
skipped in SKIP_TABLE[("ws","l3")] since v0.6.279) and nw_flow (+6%, NOT
currently skipped). nw_flow is n=64,327 = ~32% of all ws pair rows — the
big single regime bucket driving walkforward's flat "drop ws" verdict.

This Stage 1 halves-verifies whether nw_flow is a stable SKIP (extend the
skip table) vs a recency-dependent halves flip (leave alone; walkforward's
flat-drop verdict is noise). Same architecture as [[wg-l3-skip-table]]
Stage 1 shipped today v0.6.351b.

Windows mirror ch Stage 2 + wg L3 Stage 1 exactly (30d, split into recent
15d + prior 15d halves).

Per-cell verdict rules (baseline = L2 alone, gated = L3 applied on top):
  SKIP    — n >= MIN_N and L3 loses to L2 by >= L3_HURT_FLOOR_PCT on
            BOTH halves AND full window (halves-stability required). L2
            must also beat persistence in the full window (otherwise the
            cell is a persistence-gate candidate, not an L3-skip
            candidate — different intervention).
  MARGIN  — L3 loses full but one half is < floor
  KEEP    — L3 helps on full or halves disagree in sign
  THIN    — n < MIN_N in any window

Emits:
  analysis/output/h_ws_l3_regression_stage1.txt
  weather_collector/data/ws_l3_skip_table_curated.json   (preview, not wired)
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_TXT = os.path.join(HERE, "output", "h_ws_l3_regression_stage1.txt")
OUT_JSON = os.path.abspath(os.path.join(
    HERE, "..", "weather_collector", "data", "ws_l3_skip_table_curated.json"
))

# 2026-07-19: slid forward 8 days so windows cover post-shift data
# (MLC collapse / cc-cluster distribution shift). See v0.6.358.
WIN_A_LO, WIN_A_HI = "2026-07-04T00:00", "2026-07-19T00:00"
WIN_B_LO, WIN_B_HI = "2026-06-19T00:00", "2026-07-04T00:00"
WIN_FULL_LO, WIN_FULL_HI = "2026-06-19T00:00", "2026-07-19T00:00"

FIELD = "ws"
MIN_N_CELL = 200
L3_HURT_FLOOR_PCT = 3.0

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

    # Pass 1: obs index for persistence sanity check
    print("[1/2] Building wg obs index for persistence sanity check...", file=sys.stderr)
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

    # Pass 2: score L2 vs L3 vs persistence per (window, regime, band)
    print("[2/2] Scoring L2 vs L3 vs persistence per (regime x lead_band)...", file=sys.stderr)
    accum = defaultdict(lambda: {"n": 0, "ae_l2": 0.0, "ae_l3": 0.0,
                                  "ae_pers": 0.0, "n_l2_missing": 0})
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
            fc = r.get("forecast")
            if ob is None or fc is None:
                continue
            fc_l2 = r.get("forecast_l2")
            fc_l3 = r.get("forecast_l3")
            if fc_l3 is None:
                fc_l3 = fc

            persist = obs_ts.get(hour_floor(rt))
            if persist is None:
                n_no_persist += 1
                continue

            state_fc = r.get("state_fc") or {}
            regime = state_fc.get("regime_synoptic") or "unknown"

            ob_f = float(ob)
            err_l3 = float(fc_l3) - ob_f
            err_pers = float(persist) - ob_f

            n_rows += 1
            for win in windows:
                a = accum[(win, regime, band)]
                a["n"] += 1
                a["ae_l3"] += abs(err_l3)
                a["ae_pers"] += abs(err_pers)
                if fc_l2 is None:
                    a["n_l2_missing"] += 1
                    continue
                err_l2 = float(fc_l2) - ob_f
                a["ae_l2"] += abs(err_l2)

    print(f"    scored {n_rows:,} wg rows; {n_no_persist:,} skipped (no persist)",
          file=sys.stderr)
    return accum


def mae(bkt, key, n_key="n"):
    n = bkt[n_key]
    return (bkt[key] / n) if n else None


def cell_verdict(l2_f, l3_f, l2_a, l3_a, l2_b, l3_b,
                 pers_f, n_full, n_l2_missing_full):
    """Verdict for whether to SKIP L3 in this cell."""
    if n_full < MIN_N_CELL:
        return "THIN", None, None, None
    # L2 must be measurable (>= 90% of rows have L2)
    if n_l2_missing_full > 0.1 * n_full:
        return "THIN", None, None, None
    if l2_f is None or l3_f is None:
        return "THIN", None, None, None
    # Persistence-gate candidate check: if persistence beats L2, this cell
    # belongs to the persistence gate discussion (wg residual persistence),
    # not the L3 skip table.
    if pers_f is not None and pers_f < l2_f:
        return "PERSISTENCE_TERRITORY", None, None, None
    d_full = 100.0 * (l3_f - l2_f) / l2_f if l2_f else 0.0
    d_a = 100.0 * (l3_a - l2_a) / l2_a if (l2_a and l3_a is not None) else None
    d_b = 100.0 * (l3_b - l2_b) / l2_b if (l2_b and l3_b is not None) else None
    # SKIP: L3 loses on full AND both halves >= floor
    if (d_full >= L3_HURT_FLOOR_PCT
        and d_a is not None and d_a >= L3_HURT_FLOOR_PCT
        and d_b is not None and d_b >= L3_HURT_FLOOR_PCT):
        return "SKIP", d_full, d_a, d_b
    # KEEP: L3 helps on full OR halves disagree in sign
    if d_full < 0 or (d_a is not None and d_b is not None and (d_a * d_b) < 0):
        return "KEEP", d_full, d_a, d_b
    return "MARGIN", d_full, d_a, d_b


def emit(accum):
    regimes = sorted({key[1] for key in accum.keys()})
    bands = [name for name, _, _ in LEAD_BANDS]

    lines = []
    lines.append("=" * 100)
    lines.append("ws L3 SKIP-TABLE — Stage 1 preview (halves-verified per regime × lead_band)")
    lines.append("=" * 100)
    lines.append("")
    lines.append("Baseline = L2 alone. Gated = L3 applied on top. SKIP = L3 hurts stably.")
    lines.append(f"Windows: A={WIN_A_LO[:10]}→{WIN_A_HI[:10]}, "
                 f"B={WIN_B_LO[:10]}→{WIN_B_HI[:10]}, FULL={WIN_FULL_LO[:10]}→{WIN_FULL_HI[:10]}")
    lines.append(f"Per-cell SKIP verdict: halves-stability + full > +{L3_HURT_FLOOR_PCT}% (L3 worse than L2).")
    lines.append(f"PERSISTENCE_TERRITORY = persistence beats L2 in full window; separate persistence-gate discussion, not L3 skip table.")
    lines.append(f"MIN_N per cell: {MIN_N_CELL}")
    lines.append("")

    lines.append("=" * 100)
    lines.append("PER-CELL: L3 vs L2 (positive Δ = L3 hurts)")
    lines.append("=" * 100)
    header = (f"{'regime':<12}{'band':<8}{'n':>8}"
              f"{'L2 MAE':>10}{'L3 MAE':>10}{'pers MAE':>10}"
              f"{'Δ full %':>10}{'Δ A %':>9}{'Δ B %':>9}  verdict")
    lines.append(header)
    lines.append("-" * len(header))

    cells = {}
    for regime in regimes:
        for band in bands:
            bkt_f = accum[("FULL", regime, band)]
            n_full = bkt_f["n"]
            n_l2_ok_f = n_full - bkt_f["n_l2_missing"]
            l2_f = (bkt_f["ae_l2"] / n_l2_ok_f) if n_l2_ok_f else None
            l3_f = mae(bkt_f, "ae_l3")
            pers_f = mae(bkt_f, "ae_pers")

            bkt_a = accum[("A", regime, band)]
            n_l2_ok_a = bkt_a["n"] - bkt_a["n_l2_missing"]
            l2_a = (bkt_a["ae_l2"] / n_l2_ok_a) if n_l2_ok_a else None
            l3_a = mae(bkt_a, "ae_l3")

            bkt_b = accum[("B", regime, band)]
            n_l2_ok_b = bkt_b["n"] - bkt_b["n_l2_missing"]
            l2_b = (bkt_b["ae_l2"] / n_l2_ok_b) if n_l2_ok_b else None
            l3_b = mae(bkt_b, "ae_l3")

            if n_full == 0:
                continue
            verdict, d_full, d_a, d_b = cell_verdict(
                l2_f, l3_f, l2_a, l3_a, l2_b, l3_b, pers_f, n_full, bkt_f["n_l2_missing"]
            )
            star = " ★" if verdict == "SKIP" else ""
            d_full_s = f"{d_full:+.2f}" if d_full is not None else "  n/a"
            d_a_s = f"{d_a:+.2f}" if d_a is not None else "  n/a"
            d_b_s = f"{d_b:+.2f}" if d_b is not None else "  n/a"
            l2_s = f"{l2_f:>10.3f}" if l2_f is not None else "       n/a"
            l3_s = f"{l3_f:>10.3f}" if l3_f is not None else "       n/a"
            pers_s = f"{pers_f:>10.3f}" if pers_f is not None else "       n/a"
            lines.append(f"{regime:<12}{band:<8}{n_full:>8,}"
                         f"{l2_s}{l3_s}{pers_s}"
                         f"{d_full_s:>10}{d_a_s:>9}{d_b_s:>9}  {verdict}{star}")
            cells.setdefault(regime, {})[band] = {
                "n": n_full,
                "mae_l2": round(l2_f, 3) if l2_f is not None else None,
                "mae_l3": round(l3_f, 3) if l3_f is not None else None,
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
    lines.append(f"  SKIP:                 {len(skip_cells):>3} cells  (candidate for L3 skip table)")
    lines.append(f"  MARGIN:               {len(margin_cells):>3} cells")
    lines.append(f"  KEEP:                 {len(keep_cells):>3} cells  (L3 helps or halves disagree)")
    lines.append(f"  THIN:                 {len(thin_cells):>3} cells")
    lines.append(f"  PERSISTENCE_TERRITORY:{len(pers_cells):>3} cells  (wg residual persistence gate territory)")
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
            lines.append(f"  band {band:<6}: {len(regs)} regimes → {sorted(regs)}")
        for regime, bnds in sorted(skip_by_regime.items()):
            lines.append(f"  regime {regime:<12}: {len(bnds)} bands → {sorted(bnds)}")
        lines.append("")

    lines.append("=" * 100)
    lines.append("PROPOSED SKIP_TABLE EXTENSION for decay_apply.py")
    lines.append("=" * 100)
    if skip_cells:
        lines.append('  # Existing (v0.6.279): ("ne_flow", 0, 48), ("sea_breeze", 0, 12)')
        lines.append('  # Full proposed SKIP_TABLE entry after merging (do not remove existing rows):')
        lines.append('  SKIP_TABLE[("ws", "l3")] = [')
        # Group contiguous bands by regime for the (lo, hi) format
        band_bounds = {name: (lo, hi) for name, lo, hi in LEAD_BANDS}
        by_regime = defaultdict(list)
        for regime, band in skip_cells:
            lo, hi = band_bounds[band]
            by_regime[regime].append((lo, hi + 1))  # +1 because SKIP_TABLE uses half-open [lo, hi)
        for regime in sorted(by_regime):
            spans = sorted(by_regime[regime])
            # Merge contiguous spans
            merged = [spans[0]]
            for lo, hi in spans[1:]:
                if lo <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
                else:
                    merged.append((lo, hi))
            for lo, hi in merged:
                # Coverage note
                covered_bands = [b for b, (blo, bhi) in band_bounds.items() if lo <= blo and bhi + 1 <= hi]
                lines.append(f'      ("{regime}", {lo:>2}, {hi:>2}),  # bands: {"+".join(covered_bands)}')
        lines.append('  ]')
    else:
        lines.append("  (no per-cell skips required — L3 helps or is halves-unstable everywhere)")
    lines.append("")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "forecast_error_log.jsonl",
        "field": FIELD,
        "layer": "l3",
        "windows": {
            "A_recent_15d": [WIN_A_LO, WIN_A_HI],
            "B_prior_15d":  [WIN_B_LO, WIN_B_HI],
            "FULL_30d":     [WIN_FULL_LO, WIN_FULL_HI],
        },
        "fit_rules": {
            "min_n_cell": MIN_N_CELL,
            "l3_hurt_floor_pct": L3_HURT_FLOOR_PCT,
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
            "Stage 1 preview. Not wired. SKIP cells are candidates to add to "
            "SKIP_TABLE[('ws','l3')] in decay_apply.py once the 7-day streak + "
            "no-halves-flip gate clears. Existing v0.6.279 skip cells "
            "(ne_flow all bands + sea_breeze 0-11h) not double-counted here — "
            "verdict shown is what happens with L3 applied, so ne_flow/sea_breeze "
            "may re-appear as SKIP candidates; if so, that's confirmation the "
            "existing skip is right, not a duplicate ship."
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
