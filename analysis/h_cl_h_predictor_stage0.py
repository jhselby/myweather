"""Stage 0 — does HRRR's own humidity forecast (h) predict its own cl accuracy?

Motivation: [[project_lc_ema_kalman_fallback]] closed the EMA/Kalman branch as
MISS for cl. Remaining cl-rescue options include "different feature space." The
most physical candidate: relative humidity. Clouds form when RH → 100%; when
HRRR predicts high h AND high cl, both should track together and be trustworthy.
When they disagree (high cl_fc but low h_fc, or vice versa), HRRR's internal
inconsistency suggests uncertainty.

Method:
  - Multi-field join on (run_time, obs_time, lead_h) across the pair log.
  - For each cl row, look up the matching h row's forecast_l1.
  - Stratify cl's |error_l2| by h_fc bin.
  - If some h bin has systematically worse cl accuracy, we have a routing signal.

Two flavors:
  (a) Straight h_fc bin — does high-h vs low-h predict cl residual variance?
  (b) Consistency check — bin by (cl_fc bin, h_fc bin). Are the diagonal cells
      (both high, both low) more accurate than off-diagonal (disagreement)?

Verdict:
  STAGE 0 HIT — some h-bin has cl MAE ≥ HIT_RATIO × the best h-bin,
                signal is real. Advance to Stage 1 (regime slice, halves,
                honest run-time-keyed lookback compare).
  MISS        — no bin structure; h_fc doesn't predict cl accuracy.

Run:
    python3 -m analysis.h_cl_h_predictor_stage0
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_cl_h_predictor_stage0.txt")

# h-bin edges (0-100% RH)
H_BINS = [(0, 40, "0-40"), (40, 60, "40-60"), (60, 75, "60-75"),
          (75, 85, "75-85"), (85, 92, "85-92"), (92, 100.01, "92-100")]

# cl_fc bins (same as Lc)
CL_BINS = [(0, 5, "0-5"), (5, 20, "5-20"), (20, 50, "20-50"),
           (50, 80, "50-80"), (80, 95, "80-95"), (95, 100.01, "95-100")]

MIN_N = 200
HIT_RATIO = 1.30  # worst bin ≥ 30% worse than best bin → signal


def _bin_of(v, bins):
    for lo, hi, lab in bins:
        if lo <= v < hi:
            return lab
    return None


def main():
    print("loading pair log")
    # Build (rt, ot, lead) → {field: (fc_l1, obs, err_l2)}
    by_key = defaultdict(dict)
    n_scanned = 0
    with open(cached_path(PAIR_LOG_URL)) as f:
        for line in f:
            n_scanned += 1
            try:
                r = json.loads(line)
            except Exception:
                continue
            fld = r.get("field")
            if fld not in ("cl", "h"):
                continue
            rt = r.get("run_time"); ot = r.get("obs_time"); lh = r.get("lead_h")
            if not (rt and ot and lh is not None):
                continue
            fc = r.get("forecast_l1")
            obs = r.get("observed")
            err = r.get("error_l2")
            if fc is None or obs is None:
                continue
            by_key[(rt, ot, lh)][fld] = (float(fc), float(obs), err)
    print(f"  scanned {n_scanned:,} rows, {len(by_key):,} unique (rt, ot, lead) keys")

    # Filter to keys with BOTH cl and h present
    joined = [(k, v) for k, v in by_key.items() if "cl" in v and "h" in v]
    print(f"  {len(joined):,} keys have both cl and h forecast")

    # Aggregate: per (h_bin), and per (cl_bin, h_bin)
    per_h = defaultdict(lambda: {"sum": 0.0, "n": 0, "sum_signed": 0.0})
    per_cell = defaultdict(lambda: {"sum": 0.0, "n": 0})

    for (rt, ot, lh), fields in joined:
        cl_fc, cl_obs, cl_err = fields["cl"]
        h_fc, h_obs, h_err = fields["h"]
        if cl_err is None:
            cl_err = cl_fc - cl_obs  # fallback
        cl_bin = _bin_of(cl_fc, CL_BINS)
        h_bin = _bin_of(h_fc, H_BINS)
        if cl_bin is None or h_bin is None:
            continue
        per_h[h_bin]["sum"] += abs(cl_err)
        per_h[h_bin]["sum_signed"] += cl_err
        per_h[h_bin]["n"] += 1
        per_cell[(cl_bin, h_bin)]["sum"] += abs(cl_err)
        per_cell[(cl_bin, h_bin)]["n"] += 1

    lines = []
    def p(s): lines.append(s); print(s)

    p("h_cl_h_predictor_stage0 — does HRRR's h_fc predict its own cl accuracy?")
    p("")
    p("Univariate: cl error by h_fc bin")
    p(f"  {'h bin':<10}{'n':>8}{'cl MAE':>10}{'cl bias':>10}")
    p("  " + "-" * 40)
    h_maes = []
    for lo, hi, lab in H_BINS:
        s = per_h.get(lab)
        if not s or s["n"] < MIN_N:
            p(f"  {lab:<10}{(s['n'] if s else 0):>8}   thin")
            continue
        mae = s["sum"] / s["n"]
        bias = s["sum_signed"] / s["n"]
        h_maes.append((lab, mae))
        p(f"  {lab:<10}{s['n']:>8}{mae:>10.2f}{bias:>+10.2f}")

    p("")
    if len(h_maes) >= 2:
        maes = [m for _, m in h_maes]
        best = min(maes); worst = max(maes)
        ratio = worst / best if best > 0 else 0
        best_bin = [lab for lab, m in h_maes if m == best][0]
        worst_bin = [lab for lab, m in h_maes if m == worst][0]
        p(f"  Univariate spread: best h_fc bin '{best_bin}' MAE={best:.2f}, "
          f"worst '{worst_bin}' MAE={worst:.2f}, ratio={ratio:.2f}×")
        univariate_hit = ratio >= HIT_RATIO
    else:
        p(f"  Too few non-thin h bins for univariate verdict.")
        univariate_hit = False

    # 2D: (cl_bin, h_bin) — diagonal vs off-diagonal
    p("")
    p("Bivariate: cl error by (cl_fc bin × h_fc bin)")
    _corner = 'cl \\ h'
    header = f"  {_corner:<10}" + "".join(f"{lab:>10}" for _, _, lab in H_BINS)
    p(header)
    p("  " + "-" * (10 + 10 * len(H_BINS)))
    for _, _, cl_lab in CL_BINS:
        row = f"  {cl_lab:<10}"
        for _, _, h_lab in H_BINS:
            s = per_cell.get((cl_lab, h_lab))
            if not s or s["n"] < MIN_N:
                row += f"{'·':>10}"
            else:
                row += f"{s['sum']/s['n']:>10.2f}"
        p(row)
    p("")

    # Diagonal-vs-anti check: are cl_high + h_high accurate? cl_high + h_low bad?
    # Compute "consistent" cells (cl bin and h bin in same 'wet' vs 'dry' half)
    # vs "disagreement" cells.
    wet_cl = {"50-80", "80-95", "95-100"}
    wet_h = {"75-85", "85-92", "92-100"}
    dry_cl = {"0-5", "5-20", "20-50"}
    dry_h = {"0-40", "40-60", "60-75"}
    consistent_sum = consistent_n = 0
    disagreement_sum = disagreement_n = 0
    for (cl_lab, h_lab), s in per_cell.items():
        wet = cl_lab in wet_cl and h_lab in wet_h
        dry = cl_lab in dry_cl and h_lab in dry_h
        wet_dry_flip = (cl_lab in wet_cl and h_lab in dry_h) or (cl_lab in dry_cl and h_lab in wet_h)
        if wet or dry:
            consistent_sum += s["sum"]; consistent_n += s["n"]
        elif wet_dry_flip:
            disagreement_sum += s["sum"]; disagreement_n += s["n"]

    if consistent_n and disagreement_n:
        c_mae = consistent_sum / consistent_n
        d_mae = disagreement_sum / disagreement_n
        p(f"  Consistent cells (cl and h agree wet/wet or dry/dry): n={consistent_n}, MAE={c_mae:.2f}")
        p(f"  Disagreement cells (cl and h flip):                     n={disagreement_n}, MAE={d_mae:.2f}")
        ratio = d_mae / c_mae if c_mae > 0 else 0
        p(f"  Disagreement / consistent ratio: {ratio:.2f}×")
        bivariate_hit = ratio >= HIT_RATIO
    else:
        bivariate_hit = False
        p(f"  Insufficient consistent/disagreement cells for bivariate verdict.")

    p("")
    if univariate_hit and bivariate_hit:
        p(f"VERDICT: STAGE 0 HIT — h_fc predicts cl accuracy on BOTH univariate "
          f"(ratio ≥ {HIT_RATIO}×) and bivariate (disagreement cells materially worse). "
          f"Advance to Stage 1: (1) regime-slice halves, (2) honest run-time-keyed "
          f"lookback compare to confirm the routing beats the current field-skip, "
          f"(3) walkforward vs raw.")
    elif univariate_hit or bivariate_hit:
        which = "univariate" if univariate_hit else "bivariate"
        p(f"VERDICT: MIXED — {which} hits but the other doesn't. Signal is real but "
          f"narrower than hoped. Consider Stage 1 restricted to the flavor that hit.")
    else:
        p(f"VERDICT: MISS — h_fc doesn't materially structure cl residual variance. "
          f"Try a different feature (fc-trajectory, LCL, satellite low-cloud) or "
          f"pivot to persistence-of-obs specialist (clp) with a redesigned gate.")

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    p(f"\nwrote {OUT_TXT}")


if __name__ == "__main__":
    main()
