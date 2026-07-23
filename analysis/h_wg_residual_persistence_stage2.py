"""Stage 2 preview — wg residual-persistence per-cell verification.

Follow-on to Stage 1 (h_wg_residual_persistence_stage1.py), which found the
uniform-mean rolling residual over the prior 14d at the same clock hour,
applied on top of L2, reduces held-out wg MAE +16.54% pooled (6/7 regimes
WIN, halves both positive).

Stage 2 answers: does the correction hold PER-CELL (regime × lead_band),
or does the pooled win hide long-lead / narrow-regime regressions?

Windows mirror ch Stage 2 exactly (30d, split into recent 15d + prior 15d
halves) so pooled numbers reconcile across the pipeline.

Correction: forecast_gated = fc_l2 + mean_prior_14d(daily_res[(date-lag, hour)]),
where daily_res[(date, hour)] = mean_over_that_slot(obs - fc_l2).

Per-cell verdict rules:
  SHIP   — n >= MIN_N and gated MAE beats baseline by >= MAE_IMPROVE_FLOOR_PCT
           on BOTH halves AND full window (halves-stability required)
  MARGIN — gated beats on full but one half is < floor
  SKIP   — gated loses on full or halves disagree in sign
  THIN   — n < MIN_N in any window

Emits:
  analysis/output/h_wg_residual_persistence_stage2.txt
  weather_collector/data/wg_residual_persistence_curated.json   (preview, not wired)
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_TXT = os.path.join(HERE, "output", "h_wg_residual_persistence_stage2.txt")
OUT_JSON = os.path.abspath(os.path.join(
    HERE, "..", "weather_collector", "data", "wg_residual_persistence_curated.json"
))

# 2026-07-19: slid forward 8 days so windows cover post-shift data
# (MLC collapse / cc-cluster distribution shift). See v0.6.358.
WIN_A_LO, WIN_A_HI = "2026-07-08T00:00", "2026-07-23T00:00"
WIN_B_LO, WIN_B_HI = "2026-06-23T00:00", "2026-07-08T00:00"
WIN_FULL_LO, WIN_FULL_HI = "2026-06-23T00:00", "2026-07-23T00:00"

FIELD = "wg"
WINDOW_DAYS = 14
MIN_N_CELL = 200
MAE_IMPROVE_FLOOR_PCT = 3.0

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


def parse_date(vt):
    return vt[:10] if vt and len(vt) >= 10 else None


def parse_hour(vt):
    try:
        return int(vt[11:13])
    except (TypeError, ValueError, IndexError):
        return None


def compute():
    path = cached_path(URL)

    # Pass 1: build daily_res[(date, hour)] = mean signed L2 residual (obs - fc_l2)
    # from ALL wg rows across full available history. Correction skips lag=0, so
    # test-window rows use only prior days' residuals (no leak).
    print("[1/2] Building wg daily L2-residual index...", file=sys.stderr)
    slot_sum = defaultdict(float)
    slot_n = defaultdict(int)
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
            fc2 = r.get("forecast_l2")
            if vt is None or ob is None or fc2 is None:
                continue
            date = parse_date(vt)
            hour = parse_hour(vt)
            if date is None or hour is None:
                continue
            key = (date, hour)
            slot_sum[key] += (ob - fc2)
            slot_n[key] += 1
    daily_res = {k: slot_sum[k] / slot_n[k] for k in slot_sum}
    print(f"    daily-residual slots: {len(daily_res):,}", file=sys.stderr)

    # Runtime correction table: for each clock hour (0..23), mean L2 residual
    # over the last WINDOW_DAYS days (relative to the most recent date in the
    # log). This is what a live tick "tomorrow" would apply given today's fit.
    all_dates = sorted({d for (d, _) in daily_res})
    hourly_corr = {}
    hourly_corr_meta = {}
    if all_dates:
        max_date = datetime.strptime(all_dates[-1], "%Y-%m-%d").date()
        for h in range(24):
            vals = []
            for lag in range(0, WINDOW_DAYS):
                d = (max_date - timedelta(days=lag)).isoformat()
                v = daily_res.get((d, h))
                if v is not None:
                    vals.append(v)
            if vals:
                hourly_corr[h] = round(sum(vals) / len(vals), 3)
                hourly_corr_meta[h] = {"n_days": len(vals)}
            else:
                hourly_corr[h] = None
                hourly_corr_meta[h] = {"n_days": 0}
    print(f"    hour-of-day correction slots populated: "
          f"{sum(1 for v in hourly_corr.values() if v is not None)}/24",
          file=sys.stderr)

    # Pass 2: score baseline vs gated (L2 + mean-prior-14d residual)
    # per (window, regime, lead_band).
    print("[2/2] Scoring wg scenarios per (regime × lead_band)...", file=sys.stderr)
    accum = defaultdict(lambda: {"n": 0, "ae_base": 0.0, "ae_gate": 0.0,
                                  "se_base": 0.0, "se_gate": 0.0})
    n_rows = 0
    n_no_prior = 0

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
                windows = [("A", None), ("FULL", None)]
            elif WIN_B_LO <= rt < WIN_B_HI:
                windows = [("B", None), ("FULL", None)]
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
            fc2 = r.get("forecast_l2")
            if ob is None or fc2 is None:
                continue
            vt = r.get("valid_time")
            date = parse_date(vt)
            hour = parse_hour(vt)
            if date is None or hour is None:
                continue

            # Correction: mean of prior 14 days' daily_res at same hour
            try:
                d = datetime.strptime(date, "%Y-%m-%d").date()
            except Exception:
                continue
            vals = []
            for lag in range(1, WINDOW_DAYS + 1):
                prev = (d - timedelta(days=lag)).isoformat()
                v = daily_res.get((prev, hour))
                if v is not None:
                    vals.append(v)
            if not vals:
                n_no_prior += 1
                continue
            corr = sum(vals) / len(vals)

            fc_base = fc2
            fc_gate = fc2 + corr

            state_fc = r.get("state_fc") or {}
            regime = state_fc.get("regime_synoptic") or "unknown"

            err_base = fc_base - ob
            err_gate = fc_gate - ob

            n_rows += 1
            for win, _ in windows:
                a = accum[(win, regime, band)]
                a["n"] += 1
                a["ae_base"] += abs(err_base)
                a["ae_gate"] += abs(err_gate)
                a["se_base"] += err_base * err_base
                a["se_gate"] += err_gate * err_gate

    print(f"    scored {n_rows:,} wg rows; {n_no_prior:,} skipped (no prior residual)",
          file=sys.stderr)
    return accum, hourly_corr, hourly_corr_meta, (all_dates[-1] if all_dates else None)


def mae(bkt, key):
    n = bkt["n"]
    return (bkt[key] / n) if n else None


def cell_verdict(base_f, gate_f, base_a, gate_a, base_b, gate_b, n_full):
    if n_full < MIN_N_CELL:
        return "THIN", None, None, None
    d_full = 100.0 * (gate_f - base_f) / base_f if base_f else 0.0
    d_a = 100.0 * (gate_a - base_a) / base_a if (base_a and gate_a is not None) else None
    d_b = 100.0 * (gate_b - base_b) / base_b if (base_b and gate_b is not None) else None
    # SHIP: negative Δ (gate better) on full AND both halves, all beyond floor
    if (d_full <= -MAE_IMPROVE_FLOOR_PCT
        and d_a is not None and d_a <= -MAE_IMPROVE_FLOOR_PCT
        and d_b is not None and d_b <= -MAE_IMPROVE_FLOOR_PCT):
        return "SHIP", d_full, d_a, d_b
    # SKIP: full loses OR halves disagree in sign
    if d_full > 0 or (d_a is not None and d_b is not None and (d_a * d_b) < 0):
        return "SKIP", d_full, d_a, d_b
    return "MARGIN", d_full, d_a, d_b


def emit(accum, hourly_corr, hourly_corr_meta, fit_asof):
    regimes = sorted({key[1] for key in accum.keys()})
    bands = [name for name, _, _ in LEAD_BANDS]

    lines = []
    lines.append("=" * 100)
    lines.append("wg RESIDUAL-PERSISTENCE — Stage 2 preview (per regime × lead_band)")
    lines.append("=" * 100)
    lines.append("")
    lines.append(f"Correction: fc_gate = fc_l2 + mean_prior_{WINDOW_DAYS}d(daily_res[(date-lag, hour)])")
    lines.append(f"Windows: A={WIN_A_LO[:10]}→{WIN_A_HI[:10]}, "
                 f"B={WIN_B_LO[:10]}→{WIN_B_HI[:10]}, FULL={WIN_FULL_LO[:10]}→{WIN_FULL_HI[:10]}")
    lines.append(f"Per-cell verdict: halves-stability + full window > {MAE_IMPROVE_FLOOR_PCT}% improvement.")
    lines.append(f"MIN_N per cell: {MIN_N_CELL}")
    lines.append("")

    lines.append("=" * 100)
    lines.append("PER-CELL: L2 + prior-14d residual mean vs L2 alone")
    lines.append("=" * 100)
    header = (f"{'regime':<12}{'band':<8}{'n':>8}"
              f"{'base MAE':>10}{'gate MAE':>10}"
              f"{'Δ full %':>10}{'Δ A %':>9}{'Δ B %':>9}  verdict")
    lines.append(header)
    lines.append("-" * len(header))

    cells = {}
    for regime in regimes:
        for band in bands:
            base_f = mae(accum[("FULL", regime, band)], "ae_base")
            gate_f = mae(accum[("FULL", regime, band)], "ae_gate")
            base_a = mae(accum[("A", regime, band)], "ae_base")
            gate_a = mae(accum[("A", regime, band)], "ae_gate")
            base_b = mae(accum[("B", regime, band)], "ae_base")
            gate_b = mae(accum[("B", regime, band)], "ae_gate")
            n_full = accum[("FULL", regime, band)]["n"]
            if n_full == 0 or base_f is None or gate_f is None:
                continue
            verdict, d_full, d_a, d_b = cell_verdict(
                base_f, gate_f, base_a, gate_a, base_b, gate_b, n_full
            )
            star = " ★" if verdict == "SHIP" else ""
            d_full_s = f"{d_full:+.2f}" if d_full is not None else "  n/a"
            d_a_s = f"{d_a:+.2f}" if d_a is not None else "  n/a"
            d_b_s = f"{d_b:+.2f}" if d_b is not None else "  n/a"
            lines.append(f"{regime:<12}{band:<8}{n_full:>8,}"
                         f"{base_f:>10.3f}{gate_f:>10.3f}"
                         f"{d_full_s:>10}{d_a_s:>9}{d_b_s:>9}  {verdict}{star}")
            cells.setdefault(regime, {})[band] = {
                "n": n_full,
                "mae_base": round(base_f, 3),
                "mae_gate": round(gate_f, 3),
                "delta_full_pct": round(d_full, 2) if d_full is not None else None,
                "delta_a_pct": round(d_a, 2) if d_a is not None else None,
                "delta_b_pct": round(d_b, 2) if d_b is not None else None,
                "verdict": verdict,
            }
        lines.append("")

    ship_cells, skip_cells, margin_cells, thin_cells = [], [], [], []
    for regime, bandmap in cells.items():
        for band, d in bandmap.items():
            bucket = {"SHIP": ship_cells, "SKIP": skip_cells,
                      "MARGIN": margin_cells, "THIN": thin_cells}[d["verdict"]]
            bucket.append((regime, band))

    lines.append("=" * 100)
    lines.append("ROLLUP")
    lines.append("=" * 100)
    total = len(ship_cells) + len(skip_cells) + len(margin_cells) + len(thin_cells)
    lines.append(f"  SHIP:   {len(ship_cells):>3} cells")
    lines.append(f"  MARGIN: {len(margin_cells):>3} cells")
    lines.append(f"  SKIP:   {len(skip_cells):>3} cells")
    lines.append(f"  THIN:   {len(thin_cells):>3} cells")
    lines.append(f"  total judged: {total}")
    lines.append("")

    skip_by_band = defaultdict(list)
    skip_by_regime = defaultdict(list)
    for regime, band in skip_cells:
        skip_by_band[band].append(regime)
        skip_by_regime[regime].append(band)

    if skip_cells:
        lines.append("SKIP concentration:")
        for band, regs in sorted(skip_by_band.items()):
            lines.append(f"  band {band:<6}: {len(regs)} regimes → {sorted(regs)}")
        for regime, bnds in sorted(skip_by_regime.items()):
            lines.append(f"  regime {regime:<12}: {len(bnds)} bands → {sorted(bnds)}")
        lines.append("")

    lines.append("=" * 100)
    lines.append("PROPOSED GATE SHAPE")
    lines.append("=" * 100)
    lines.append(f"  base rule: forecast = fc_l2 + mean prior-{WINDOW_DAYS}d L2-residual at same hour")
    if skip_cells:
        lines.append("  fall back to L2-alone (no correction) when:")
        for regime, band in sorted(skip_cells):
            lines.append(f"    - regime == '{regime}' AND lead_band == '{band}'  (Stage 2 SKIP)")
    else:
        lines.append("  (no per-cell skips required — clean gate across all judged cells)")
    lines.append("")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "forecast_error_log.jsonl",
        "field": FIELD,
        "windows": {
            "A_recent_15d": [WIN_A_LO, WIN_A_HI],
            "B_prior_15d":  [WIN_B_LO, WIN_B_HI],
            "FULL_30d":     [WIN_FULL_LO, WIN_FULL_HI],
        },
        "correction": {
            "form": "fc_l2 + mean_prior_Nd(daily_res[(date-lag, hour)])",
            "window_days": WINDOW_DAYS,
            "weighting": "uniform mean",
            "residual_definition": "obs - fc_l2 at (date, hour)",
        },
        "fit_rules": {
            "min_n_cell": MIN_N_CELL,
            "mae_improve_floor_pct": MAE_IMPROVE_FLOOR_PCT,
            "halves_stability_required": True,
            "lead_bands": bands,
        },
        "gate": {
            "additional_skips": [
                {"regime": r, "lead_band": b} for r, b in sorted(skip_cells)
            ],
        },
        "hourly_correction": {
            "fit_asof": fit_asof,
            "hour_of_day": {str(h): hourly_corr.get(h) for h in range(24)},
            "hour_of_day_n_days": {str(h): hourly_corr_meta.get(h, {}).get("n_days", 0)
                                    for h in range(24)},
            "units": "mph (add to fc_l2_wg on SHIP cells)",
            "note": (
                f"Mean L2 residual (obs - fc_l2) at each clock hour over the last "
                f"{WINDOW_DAYS} days ending {fit_asof}. Refreshed each Stage 2 run."
            ),
        },
        "cells": cells,
        "rollup": {
            "ship": len(ship_cells),
            "margin": len(margin_cells),
            "skip": len(skip_cells),
            "thin": len(thin_cells),
        },
        "notes": (
            "Stage 2 preview only. Not wired to production. Correction adds the "
            f"prior-{WINDOW_DAYS}d mean L2-residual at the same clock hour on top of L2. "
            "Cells with verdict=SHIP or MARGIN use the correction at runtime; SKIP "
            "cells fall back to L2 alone. Wire via a new wg_residual_persistence "
            "processor with ENABLED=False on ship and a 7-day gate before enabling."
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
    emit(*compute())
