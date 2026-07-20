"""Stage 1 preview — cloud-cover saturation correction keyed on forecast cc.

Follow-on to [[h_rh_saturation.py]] Stage 0 verdict: at OBSERVED humidity
≥95%, cloud MAE spikes — cl +79%, cm +119%, ch +89%. This is diagnostic-
only; C1g (RH≥95 confidence axis) was killed 2026-06-24 as redundant
with cc-saturation (cc_fc≥95). No L-specialist actively corrects cloud
values at saturation.

Pair log's state_fc lacks humidity, so we use cc-saturation (fc_cc ≥
threshold) as the fire-time proxy for "saturation predicted." Question:
when model predicts high cloud cover, is the individual cloud-layer
forecast (cl/cm/ch) still systematically biased vs obs, and does an
additive shift fix it?

Correction shape:

    fc_corrected = clip(fc + Δ_regime_band, 0, 100)

where Δ_regime_band is the mean signed bias (obs - fc) computed on rows
where state_fc.cloud_cover >= CC_HIGH_PCT, per (field × regime × band).
If Δ is systematically positive (obs > fc when model predicts high cc),
an additive shift UP reduces MAE for the layer field.

Method:
  1. Fit: on training window, gather rows with fc_humidity >= H_HIGH_PCT.
     Compute Δ_train = mean(obs - fc) per (field × regime × band).
  2. Test: on held-out window, apply Δ_train to same-cell rows.
     Compare MAE(fc + Δ) vs MAE(fc).
  3. Halves check on training: fit on A, test on B; fit on B, test on A.
     Both halves must show ≥ MIN_IMPROVEMENT_PCT MAE reduction.

Per-cell verdict:
  SHIP    — n_train ≥ MIN_N, held-out improvement ≥ MIN_IMPROVEMENT_PCT,
            both halves confirm same direction.
  MARGIN  — held-out clears but halves inconsistent.
  SKIP    — held-out doesn't clear or Δ has wrong sign.
  THIN    — n < MIN_N.

Fields: cl, cm, ch. (cc excluded — L4 already fires on cc; adding another
axis would double-count.)

Emits:
  analysis/output/h_rh_saturation_stage1.txt
  weather_collector/data/<field>_cc_sat_correction_curated.json
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_TXT = os.path.join(HERE, "output", "h_rh_saturation_stage1.txt")
DATA_DIR = os.path.abspath(os.path.join(HERE, "..", "weather_collector", "data"))

WIN_A_LO, WIN_A_HI = "2026-07-04T00:00", "2026-07-19T00:00"
WIN_B_LO, WIN_B_HI = "2026-06-19T00:00", "2026-07-04T00:00"

FIELDS = ("cl", "cm", "ch")
CC_HIGH_PCT = 80.0           # state_fc.cloud_cover threshold for "cc-saturated" bin
MIN_N_CELL = 100
MIN_IMPROVEMENT_PCT = 3.0

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


def _sfc_cc(pair):
    """Extract forecast cloud_cover from a pair-log row's state_fc."""
    sfc = pair.get("state_fc") or {}
    return sfc.get("cloud_cover")


def compute(field):
    path = cached_path(URL)
    print(f"[{field}] gathering high-RH rows split into A/B halves...", file=sys.stderr)

    # rows[(window, regime, band)] = [(fc, obs), ...] where state_fc.cloud_cover ≥ CC_HIGH_PCT
    rows = defaultdict(list)
    n_seen = 0
    n_high = 0
    n_no_cc = 0

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
            band = lead_band(lead)
            if band is None:
                continue

            ob = r.get("observed")
            fc = r.get("forecast")
            if ob is None or fc is None:
                continue

            cc_fc = _sfc_cc(r)
            if cc_fc is None:
                n_no_cc += 1
                continue
            try:
                cc_fc = float(cc_fc)
            except (TypeError, ValueError):
                continue
            n_seen += 1
            if cc_fc < CC_HIGH_PCT:
                continue
            n_high += 1

            state_fc = r.get("state_fc") or {}
            regime = state_fc.get("regime_synoptic") or "unknown"
            rows[(win, regime, band)].append((float(fc), float(ob)))

    print(f"    {field}: {n_seen:,} scored; {n_high:,} above state_fc.cloud_cover "
          f"{CC_HIGH_PCT}%; {n_no_cc:,} skipped (no state_fc.cloud_cover)", file=sys.stderr)
    return rows


def cell_stats(train, test, clip_lo, clip_hi):
    """Fit Δ on train, apply on test, return (n_train, n_test, delta, mae_base,
    mae_corr, improvement_pct). None if cells empty."""
    if not train or not test:
        return None
    delta = sum(o - f for f, o in train) / len(train)
    base_ae = sum(abs(f - o) for f, o in test)
    corr_ae = sum(abs(max(clip_lo, min(clip_hi, f + delta)) - o) for f, o in test)
    n_train = len(train)
    n_test = len(test)
    mae_base = base_ae / n_test
    mae_corr = corr_ae / n_test
    if mae_base <= 0:
        return None
    improvement = 100.0 * (mae_base - mae_corr) / mae_base
    return n_train, n_test, delta, mae_base, mae_corr, improvement


def emit(field, rows, lines):
    """Append per-field report to `lines`. Fit on A, test on B, and vice versa.
    Ship a cell only if BOTH cross-fits clear MIN_IMPROVEMENT_PCT."""
    lines.append("=" * 110)
    lines.append(f"{field} RH-SATURATION ADDITIVE CORRECTION — Stage 1 preview "
                 f"(fc_cc ≥ {CC_HIGH_PCT:.0f}%, per regime × lead_band)")
    lines.append("=" * 110)
    lines.append("")
    lines.append("Correction shape: fc_corrected = clip(fc + Δ_regime_band, 0, 100)")
    lines.append(f"Δ fit on TRAIN half's mean(obs - fc); tested on OTHER half.")
    lines.append("SHIP requires both cross-fits (A→B and B→A) clear "
                 f"≥{MIN_IMPROVEMENT_PCT}% MAE improvement.")
    lines.append("")

    regimes = sorted({r for (_, r, _) in rows.keys()})
    bands = [name for name, _, _ in LEAD_BANDS]

    header = (f"{'regime':<12}{'band':<8}{'n_A':>7}{'n_B':>7}"
              f"{'Δ_A':>8}{'Δ_B':>8}"
              f"{'A→B %':>9}{'B→A %':>9}  verdict")
    lines.append(header)
    lines.append("-" * len(header))

    cells = {}
    for regime in regimes:
        for band in bands:
            a_rows = rows.get(("A", regime, band), [])
            b_rows = rows.get(("B", regime, band), [])
            n_a, n_b = len(a_rows), len(b_rows)
            if n_a < MIN_N_CELL or n_b < MIN_N_CELL:
                if n_a + n_b > 0:
                    lines.append(f"{regime:<12}{band:<8}{n_a:>7}{n_b:>7}"
                                 f"{'   n/a':>8}{'   n/a':>8}"
                                 f"{'   n/a':>9}{'   n/a':>9}  THIN")
                continue
            # A→B: fit on A, test on B
            ab = cell_stats(a_rows, b_rows, 0, 100)
            # B→A: fit on B, test on A
            ba = cell_stats(b_rows, a_rows, 0, 100)
            if ab is None or ba is None:
                continue
            _, _, d_a, _, _, imp_ab = ab
            _, _, d_b, _, _, imp_ba = ba

            if imp_ab >= MIN_IMPROVEMENT_PCT and imp_ba >= MIN_IMPROVEMENT_PCT:
                verdict = "SHIP"
            elif imp_ab >= MIN_IMPROVEMENT_PCT or imp_ba >= MIN_IMPROVEMENT_PCT:
                verdict = "MARGIN"
            else:
                verdict = "SKIP"

            star = " ★" if verdict == "SHIP" else ""
            lines.append(f"{regime:<12}{band:<8}{n_a:>7,}{n_b:>7,}"
                         f"{d_a:>+8.2f}{d_b:>+8.2f}"
                         f"{imp_ab:>+9.2f}{imp_ba:>+9.2f}  {verdict}{star}")
            cells.setdefault(regime, {})[band] = {
                "n_a": n_a, "n_b": n_b,
                "delta_a": round(d_a, 3), "delta_b": round(d_b, 3),
                "improvement_ab_pct": round(imp_ab, 2),
                "improvement_ba_pct": round(imp_ba, 2),
                "delta_avg": round((d_a + d_b) / 2.0, 3),
                "verdict": verdict,
            }
        lines.append("")

    ship_cells = []
    margin_cells = []
    skip_cells = []
    for regime, bandmap in cells.items():
        for band, d in bandmap.items():
            key = (regime, band)
            if d["verdict"] == "SHIP":
                ship_cells.append(key)
            elif d["verdict"] == "MARGIN":
                margin_cells.append(key)
            elif d["verdict"] == "SKIP":
                skip_cells.append(key)

    lines.append(f"  {field}: SHIP {len(ship_cells)}  MARGIN {len(margin_cells)}  SKIP {len(skip_cells)}")

    if len(ship_cells) >= 2:
        verdict = (f"{field} verdict: STAGE 1 HIT — {len(ship_cells)} SHIP cell(s) "
                   f"cross-fit halves-stable at floor {MIN_IMPROVEMENT_PCT}%.")
    elif ship_cells:
        verdict = f"{field} verdict: MARGINAL — {len(ship_cells)} SHIP + {len(margin_cells)} MARGIN."
    else:
        verdict = f"{field} verdict: HOLD — additive RH-sat correction not halves-stable."
    lines.append(verdict)
    lines.append("")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "forecast_error_log.jsonl",
        "field": field,
        "windows": {
            "A_recent_15d": [WIN_A_LO, WIN_A_HI],
            "B_prior_15d":  [WIN_B_LO, WIN_B_HI],
        },
        "fit_rules": {
            "fc_cc_threshold_pct": CC_HIGH_PCT,
            "min_n_cell": MIN_N_CELL,
            "min_improvement_pct": MIN_IMPROVEMENT_PCT,
            "clip_range": [0, 100],
            "cross_fit_halves_stability_required": True,
        },
        "cells": cells,
        "rollup": {
            "ship": len(ship_cells),
            "margin": len(margin_cells),
            "skip": len(skip_cells),
        },
        "notes": (
            "Stage 1 preview. Not wired to production. Δ is the mean signed "
            "bias (obs - fc) at fc_cc ≥ threshold; correction adds Δ to "
            "the raw forecast when the fire condition holds. Fire condition at "
            "collector time: forecast cloud_cover for this lead ≥ threshold AND "
            "cell (regime, band) is SHIP or MARGIN."
        ),
    }

    out_json = os.path.join(DATA_DIR, f"{field}_cc_sat_correction_curated.json")
    with open(out_json, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"wrote {out_json}", file=sys.stderr)
    return ship_cells, verdict


def main():
    lines = []
    verdicts = []
    total_ship = 0
    for field in FIELDS:
        rows = compute(field)
        ship_cells, verdict = emit(field, rows, lines)
        verdicts.append((field, len(ship_cells)))
        total_ship += len(ship_cells)

    lines.append("=" * 110)
    lines.append("COMBINED VERDICT")
    lines.append("=" * 110)
    for f, n in verdicts:
        lines.append(f"  {f}: {n} SHIP cells")
    if total_ship >= 4:
        lines.append(f"Verdict: STAGE 1 HIT — {total_ship} SHIP cells across "
                     f"{sum(1 for _, n in verdicts if n)} field(s). "
                     f"Move to Stage 2 wiring (specialist keyed on state_fc.cloud_cover + regime × band).")
    elif total_ship:
        lines.append(f"Verdict: MARGINAL — {total_ship} SHIP cells total.")
    else:
        lines.append("Verdict: HOLD — additive RH-sat correction not halves-stable in any field.")
    lines.append("")

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {OUT_TXT}")


if __name__ == "__main__":
    main()
