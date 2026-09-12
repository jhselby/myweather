"""Stage 1a — does a (cl_fc, h_fc) disagreement router actually improve cl MAE?

Stage 0 (`h_cl_h_predictor_stage0.py`) found that h_fc structures cl residual
variance: disagreement cells (cl says overcast + h says medium, or cl says
clear + h says humid) have MAE 1.59× the agreement cells. Signal is real.
This asks the ship question: does routing on that signal actually beat the
current field-skip state (production cl = raw L1)?

Routing rule tested:
  - AGREEMENT cell (cl and h both in wet-half or both in dry-half): keep raw L1.
  - DISAGREEMENT cell (cl-wet + h-dry, or cl-dry + h-wet): fall back to
    persistence — mean cl obs over the last N hours strictly before run_time.
    N tunable. If insufficient history, fall back to raw L1.

Honest walkforward:
  - Persistence lookback keyed on run_time (not obs_time) — same fix
    that exposed the Stage 0 EMA leakage.
  - Same two-phase per-obs_time processing as h_lc_ema_stage1_baseline.
  - Sweep N ∈ LOOKBACKS. Compare routing MAE vs raw baseline for cl.

Verdict:
  STAGE 1 HIT — routing beats raw L1 by ≥ SHIP_FLOOR_PCT overall AND doesn't
                make any lead-band materially worse. Advance to Stage 2:
                per-regime slice + full walkforward vs pooled Lc + halves.
  MISS        — routing doesn't clear the bar. Signal is real (Stage 0)
                but this specific routing rule doesn't monetize it. Consider
                different fallback (blend, climatology) as Stage 1b.

Run:
    python3 -m analysis.h_cl_h_predictor_stage1
"""
import bisect
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_cl_h_predictor_stage1.txt")

# Bins — must match Stage 0.
CL_BINS = [(0, 5, "0-5"), (5, 20, "5-20"), (20, 50, "20-50"),
           (50, 80, "50-80"), (80, 95, "80-95"), (95, 100.01, "95-100")]
H_BINS = [(0, 40, "0-40"), (40, 60, "40-60"), (60, 75, "60-75"),
          (75, 85, "75-85"), (85, 92, "85-92"), (92, 100.01, "92-100")]

WET_CL = {"50-80", "80-95", "95-100"}
DRY_CL = {"0-5", "5-20", "20-50"}
WET_H  = {"75-85", "85-92", "92-100"}
DRY_H  = {"0-40", "40-60", "60-75"}

LOOKBACKS = [6, 12, 24, 48]  # hours of cl-obs history for persistence
HELD_OUT_DAYS = 14
MIN_WARMUP = 6  # persistence needs at least this many obs before firing
SHIP_FLOOR_PCT = 2.0
BAND_HURT_CAP_PCT = 3.0

BANDS = [("0-5", 0, 5), ("6-11", 6, 11), ("12-23", 12, 23), ("24-47", 24, 47)]


def _bin_of(v, bins):
    for lo, hi, lab in bins:
        if lo <= v < hi:
            return lab
    return None


def _band_of(lh):
    for l, lo, hi in BANDS:
        if lo <= lh <= hi:
            return l
    return None


def _is_disagreement(cl_bin, h_bin):
    return (cl_bin in WET_CL and h_bin in DRY_H) or (cl_bin in DRY_CL and h_bin in WET_H)


def main():
    print("loading pair log (cl + h)")
    by_key = defaultdict(dict)  # (rt, ot, lh) → {field: (fc_l1, obs, err_l2)}
    cl_obs_by_ot = {}            # ot → cl_obs  (single obs per obs_time)
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
            if fld == "cl":
                cl_obs_by_ot[ot] = float(obs)
    print(f"  scanned {n_scanned:,}, {len(by_key):,} unique keys, {len(cl_obs_by_ot):,} unique cl obs_times")

    joined = [(k, v) for k, v in by_key.items() if "cl" in v and "h" in v]
    print(f"  {len(joined):,} joined cl+h rows")

    # Build sorted list of (obs_time_iso, cl_obs) for persistence lookback
    cl_obs_sorted = sorted(cl_obs_by_ot.items())  # [(ot, obs), ...]
    cl_obs_times = [t for t, _ in cl_obs_sorted]
    cl_obs_vals  = [v for _, v in cl_obs_sorted]

    max_ot = max(ot for (_, ot, _), _ in joined)
    max_dt = datetime.fromisoformat(max_ot[:19])
    cutoff_dt = max_dt - timedelta(days=HELD_OUT_DAYS)
    cutoff_ot = cutoff_dt.isoformat(timespec="minutes")

    lines = []
    def p(s): lines.append(s); print(s)

    p(f"h_cl_h_predictor_stage1 — honest walkforward of (cl_fc, h_fc) disagreement router")
    p(f"Joined rows: {len(joined):,}   held-out: {cutoff_ot} → {max_ot} ({HELD_OUT_DAYS}d)")
    p(f"Persistence lookback: N ∈ {LOOKBACKS}h (mean cl_obs strictly before run_time)")
    p(f"Warm-up: ≥{MIN_WARMUP} obs required before persistence fires; else fall back to raw L1.")
    p("")

    def _persistence_mean(rt_iso, n_hours):
        """Mean cl_obs over the last n_hours of obs strictly before rt_iso."""
        idx = bisect.bisect_left(cl_obs_times, rt_iso)
        if idx == 0:
            return None
        # Walk backward to gather obs within [rt - n_hours, rt)
        rt_dt = datetime.fromisoformat(rt_iso[:19])
        lo_dt = rt_dt - timedelta(hours=n_hours)
        lo_iso = lo_dt.isoformat(timespec="minutes")
        lo_idx = bisect.bisect_left(cl_obs_times, lo_iso)
        window = cl_obs_vals[lo_idx:idx]
        if len(window) < MIN_WARMUP:
            return None
        return sum(window) / len(window)

    # Score raw + routing at each N
    band_stats = {n: {b: {"sum_raw": 0.0, "sum_route": 0.0, "n": 0,
                          "n_disagree": 0, "n_fired_persist": 0} for b, _, _ in BANDS}
                  for n in LOOKBACKS}
    overall = {n: {"sum_raw": 0.0, "sum_route": 0.0, "n": 0,
                   "n_disagree": 0, "n_fired_persist": 0} for n in LOOKBACKS}

    for (rt, ot, lh), fields in joined:
        if ot < cutoff_ot:
            continue
        band = _band_of(lh)
        if band is None: continue
        cl_fc, cl_obs, _ = fields["cl"]
        h_fc, _, _ = fields["h"]
        cl_bin = _bin_of(cl_fc, CL_BINS)
        h_bin = _bin_of(h_fc, H_BINS)
        if cl_bin is None or h_bin is None:
            continue
        raw_err = abs(cl_fc - cl_obs)
        disagreement = _is_disagreement(cl_bin, h_bin)
        for n in LOOKBACKS:
            band_stats[n][band]["sum_raw"] += raw_err
            band_stats[n][band]["n"] += 1
            overall[n]["sum_raw"] += raw_err
            overall[n]["n"] += 1
            if disagreement:
                band_stats[n][band]["n_disagree"] += 1
                overall[n]["n_disagree"] += 1
                persist = _persistence_mean(rt, n)
                if persist is not None:
                    route_err = abs(persist - cl_obs)
                    band_stats[n][band]["n_fired_persist"] += 1
                    overall[n]["n_fired_persist"] += 1
                else:
                    route_err = raw_err
            else:
                route_err = raw_err
            band_stats[n][band]["sum_route"] += route_err
            overall[n]["sum_route"] += route_err

    p(f"Overall (14d held-out) — routing MAE vs raw L1:")
    p(f"  {'N (h)':>6}{'n':>8}{'raw MAE':>10}{'route MAE':>12}{'Δ%':>8}{'n_disagree':>12}{'n_fired':>10}")
    for n in LOOKBACKS:
        s = overall[n]
        if s["n"] == 0: continue
        raw = s["sum_raw"]/s["n"]; route = s["sum_route"]/s["n"]
        d = (raw - route)/raw*100 if raw else 0
        p(f"  {n:>6}{s['n']:>8}{raw:>10.2f}{route:>12.2f}{d:>+7.1f}%"
          f"{s['n_disagree']:>12}{s['n_fired_persist']:>10}")
    p("")

    # Per band, best N
    best_n = max(LOOKBACKS,
                 key=lambda n: (overall[n]["sum_raw"] - overall[n]["sum_route"])
                               if overall[n]["n"] else -1)
    p(f"Per lead-band at best N={best_n}h (routing vs raw L1):")
    p(f"  {'band':<8}{'n':>7}{'raw MAE':>10}{'route MAE':>12}{'Δ%':>8}")
    band_deltas = []
    for b, _, _ in BANDS:
        s = band_stats[best_n][b]
        if s["n"] == 0: continue
        raw = s["sum_raw"]/s["n"]; route = s["sum_route"]/s["n"]
        d = (raw - route)/raw*100 if raw else 0
        band_deltas.append((b, d))
        p(f"  {b:<8}{s['n']:>7}{raw:>10.2f}{route:>12.2f}{d:>+7.1f}%")
    p("")

    # Verdict
    overall_d = (overall[best_n]["sum_raw"] - overall[best_n]["sum_route"]) / overall[best_n]["sum_raw"] * 100
    worst_band = min(band_deltas, key=lambda x: x[1]) if band_deltas else ("?", 0)
    if overall_d >= SHIP_FLOOR_PCT and worst_band[1] > -BAND_HURT_CAP_PCT:
        p(f"VERDICT: STAGE 1 HIT — routing at N={best_n}h beats raw L1 by {overall_d:.1f}% "
          f"overall on 14d held-out, worst band {worst_band[0]} = {worst_band[1]:+.1f}%. "
          f"Advance to Stage 2: regime-slice halves, cross-cutoff walkforward.")
    elif overall_d >= SHIP_FLOOR_PCT:
        p(f"VERDICT: MIXED — routing beats raw overall by {overall_d:.1f}% but hurts band "
          f"{worst_band[0]} by {worst_band[1]:+.1f}%. Consider band-conditional routing "
          f"(fire persistence only in bands where it helps).")
    else:
        p(f"VERDICT: MISS — routing at best N={best_n}h beats raw L1 by only {overall_d:.1f}% "
          f"overall (floor is {SHIP_FLOOR_PCT}%). Stage 0 signal exists but this specific "
          f"persistence router doesn't monetize it. Try Stage 1b (blend HRRR cl_fc with "
          f"h-derived cl estimate) or Stage 1c (climatology-of-obs fallback).")

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    p(f"\nwrote {OUT_TXT}")


if __name__ == "__main__":
    main()
