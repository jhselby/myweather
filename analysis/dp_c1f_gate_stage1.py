"""Stage 1 — quantify the dp × C1f-precip_fc skip-gate.

Stage 0 (`h_raw_error_predictors.py` 2026-07-10): C1f-precip_fc is a REAL
raw-MAE predictor for dp. When precip_fc > 0 (p1), raw MAE is 2.14
across 15k pairs and Production correction HURTS by −0.017. When precip
NOT forecast (p0), raw MAE is 3.29 across 183k pairs and Production
correction HELPS by +0.577. The correction is a net hedge, but on p1
rows it's actively taking away accuracy we already had.

Stage 1 question: if we ship a skip that gates dp L2 to fire only when
C1f p0 (precip NOT forecast), what's the expected Production MAE change?

Method: counterfactual replay against the pair log. For each dp row:
  - baseline: use current Production error (error_l4 preferred, else
    error_l3/l2/l1 — matches how production_whatif and the odometer
    pick "deepest applied output").
  - intervention: same as baseline EXCEPT when state_fc.precip_in > 0,
    substitute error_l1 (skip L2 additive; use raw model output).
Then aggregate |error| across all dp rows in both cases; compare.

Reports per-lead-band + overall Production MAE:
  - baseline (current live behavior)
  - intervention (proposed dp × C1f=p1 skip)
  - Δ absolute (mph °F etc.) and Δ % improvement

Gate for Stage 2 curation:
  ★ SHIP CANDIDATE — intervention improves overall Production MAE ≥ 2%
                     AND no lead band worsens by >1%
  ⚠ MARGINAL       — improves 1-2% overall
  HOLD             — improves <1% or any band worsens materially

Run:
    python3 analysis/dp_c1f_gate_stage1.py
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(os.path.dirname(__file__), "output",
                       "dp_c1f_gate_stage1.txt")

BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
FIELD = "dp"


def band_of(lh):
    for lab, lo, hi in BANDS:
        if lo <= lh < hi:
            return lab
    return None


def prod_error(row):
    """Deepest applied error, matching odometer + state_stratified semantics."""
    for k in ("error_l4", "error_l3", "error_l2", "error_l1", "error"):
        v = row.get(k)
        if v is not None:
            return v
    return None


def main():
    # per band -> {"baseline": [n, sum_abs], "intervention": [n, sum_abs], "l1_raw": [n, sum_abs]}
    per_band = defaultdict(lambda: {
        "baseline":     [0, 0.0],
        "intervention": [0, 0.0],
        "l1_raw":       [0, 0.0],
    })
    # Also stratify by C1f state so we can see the intervention's isolated effect
    #   on the affected subset.
    per_c1f = defaultdict(lambda: {
        "baseline":     [0, 0.0],
        "intervention": [0, 0.0],
        "l1_raw":       [0, 0.0],
    })
    n_p1 = 0
    n_p0 = 0
    rows_scanned = 0
    dp_rows = 0

    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for line in fh:
            rows_scanned += 1
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            dp_rows += 1
            band = band_of(r.get("lead_h") or -1)
            if band is None:
                continue
            e_prod = prod_error(r)
            e_l1 = r.get("error_l1")
            if e_prod is None or e_l1 is None:
                continue
            sfc = r.get("state_fc") or {}
            c1f_fires = (sfc.get("precip_in") or 0) > 0
            c1f_key = "p1" if c1f_fires else "p0"
            if c1f_fires:
                n_p1 += 1
            else:
                n_p0 += 1
            # Baseline: current live pipeline error
            per_band[band]["baseline"][0] += 1
            per_band[band]["baseline"][1] += abs(e_prod)
            per_c1f[c1f_key]["baseline"][0] += 1
            per_c1f[c1f_key]["baseline"][1] += abs(e_prod)
            # Intervention: if C1f fires, revert to L1 raw (skip L2)
            e_int = e_l1 if c1f_fires else e_prod
            per_band[band]["intervention"][0] += 1
            per_band[band]["intervention"][1] += abs(e_int)
            per_c1f[c1f_key]["intervention"][0] += 1
            per_c1f[c1f_key]["intervention"][1] += abs(e_int)
            # Raw reference (L1 always)
            per_band[band]["l1_raw"][0] += 1
            per_band[band]["l1_raw"][1] += abs(e_l1)
            per_c1f[c1f_key]["l1_raw"][0] += 1
            per_c1f[c1f_key]["l1_raw"][1] += abs(e_l1)

    lines_out = []
    def emit(s):
        print(s); lines_out.append(s)

    emit(f"dp × C1f-precip_fc skip-gate Stage 1")
    emit(f"  pair-log rows scanned: {rows_scanned:,}")
    emit(f"  dp rows: {dp_rows:,}   with C1f fires (p1): {n_p1:,}   p0: {n_p0:,}")
    emit(f"  C1f-fire share: {(n_p1 / max(n_p1 + n_p0, 1) * 100):.1f}%")
    emit(f"  intervention: for dp rows where state_fc.precip_in > 0, revert to L1 raw")
    emit("")

    def mae(bucket):
        n, s = bucket
        return s / n if n else 0.0

    emit(f"Per-lead-band comparison (MAE, °F for dp):")
    emit(f"  {'band':<8} {'n':>7}  {'raw L1':>8}  {'baseline':>8}  {'intervention':>13}  "
         f"{'Δ vs base':>10}  {'Δ % vs base':>12}")
    emit(f"  " + "-" * 84)
    tot_n = 0
    tot_base = 0.0
    tot_int = 0.0
    tot_raw = 0.0
    band_flags = []
    for band, _, _ in BANDS:
        pb = per_band.get(band)
        if not pb:
            continue
        n = pb["baseline"][0]
        mae_raw  = mae(pb["l1_raw"])
        mae_base = mae(pb["baseline"])
        mae_int  = mae(pb["intervention"])
        delta_abs = mae_int - mae_base
        delta_pct = (delta_abs / mae_base * 100) if mae_base > 0 else 0.0
        flag = " ★" if delta_pct <= -2 else (" ⚠ regress" if delta_pct >= 1 else "")
        band_flags.append((band, delta_pct))
        emit(f"  {band:<8} {n:>7,}  {mae_raw:>8.3f}  {mae_base:>8.3f}  {mae_int:>13.3f}  "
             f"{delta_abs:>+10.3f}  {delta_pct:>+11.2f}%{flag}")
        tot_n += n
        tot_base += pb["baseline"][1]
        tot_int  += pb["intervention"][1]
        tot_raw  += pb["l1_raw"][1]
    emit(f"  " + "-" * 84)
    mae_base_all = tot_base / tot_n if tot_n else 0
    mae_int_all  = tot_int / tot_n if tot_n else 0
    mae_raw_all  = tot_raw / tot_n if tot_n else 0
    d_abs = mae_int_all - mae_base_all
    d_pct = (d_abs / mae_base_all * 100) if mae_base_all > 0 else 0
    emit(f"  {'OVERALL':<8} {tot_n:>7,}  {mae_raw_all:>8.3f}  {mae_base_all:>8.3f}  "
         f"{mae_int_all:>13.3f}  {d_abs:>+10.3f}  {d_pct:>+11.2f}%")
    emit("")

    # Effect isolated to the affected subset (C1f p1 rows only)
    emit(f"Isolated on the affected subset (dp rows where C1f fires, n={n_p1:,}):")
    pb = per_c1f["p1"]
    if pb["baseline"][0] > 0:
        mae_raw  = mae(pb["l1_raw"])
        mae_base = mae(pb["baseline"])
        mae_int  = mae(pb["intervention"])
        emit(f"  raw L1 MAE       : {mae_raw:.3f}")
        emit(f"  baseline (L2 on) : {mae_base:.3f}  ({(mae_base - mae_raw) / mae_raw * 100:+.2f}% vs raw)")
        emit(f"  intervention     : {mae_int:.3f}  ({(mae_int - mae_raw) / mae_raw * 100:+.2f}% vs raw)")
        emit(f"  intervention wins baseline by {(mae_base - mae_int):.3f}°F on p1 rows.")
    emit("")

    # Verdict
    any_regress = any(dp >= 1 for _, dp in band_flags)
    emit("Verdict:")
    if d_pct <= -2 and not any_regress:
        emit(f"  ★ SHIP CANDIDATE — overall Production MAE improves {d_pct:.2f}% under the intervention, no band regresses ≥1%.")
        emit(f"    Next step: Stage 2 curated skip cell (dp, L2, C1f=p1). Then wire into corrected_hourly.py.")
    elif d_pct <= -1:
        emit(f"  ⚠ MARGINAL — overall improves {d_pct:.2f}% but under the 2% SHIP threshold.")
        emit(f"    Re-run in 2 weeks with more pair data. If holds, promote.")
    elif d_pct >= 0:
        emit(f"  HOLD — overall does not improve ({d_pct:+.2f}%).")
        emit(f"    Correction is doing net work on the full dp set even though it hurts on p1.")
        emit(f"    The +0.577 help on p0 (183k pairs) outweighs the −0.017 hurt on p1 (15k pairs).")
    else:
        emit(f"  ⚠ SLIGHT — {d_pct:+.2f}% overall. Nothing to act on yet.")
    if any_regress:
        emit(f"  ⚠ At least one lead band regresses under the intervention:")
        for band, dp in band_flags:
            if dp >= 1:
                emit(f"      {band}: {dp:+.2f}%")

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines_out) + "\n")
    print(f"\nwrote {OUT_TXT}")


if __name__ == "__main__":
    main()
