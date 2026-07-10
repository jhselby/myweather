"""Stage 0 — raw wind-speed forecast error stratified by observed wind octant.

Question: does raw HRRR have a *direction-conditional* bias on ws at this
site? Wyman Cove sits on a peninsula (water NE/E/SE, land W/SW/NW), so
generic coastal-New-England HRRR won't know about the specific channel /
blocking geometry. If direction-conditional bias exists in the raw model,
L2's current wind blend (per-octant-max → median across octants, no
additive) would pass it through untouched.

This is distinct from:
  - h_regime_l3.py — stratifies L3 IMPROVEMENT by SYNOPTIC REGIME (multi-
    feature; a "sea_breeze" hour and an "ne_flow" hour can share NE octant
    but they're different regimes). Not a raw-bias diagnostic.
  - h_ws_wd_error.py — measures wd MAE as function of ws (calm = noisy wd).
    Different direction of the cut.

Method:
  Pair-log ws rows have forecast_l1 + observed. But observed wind DIRECTION
  lives on the wd field's row. Join ws + wd at (run_time, obs_time, lead)
  — same pattern as h_ws_wd_error.py. Then bin ws error by wd_obs octant.

  For each (octant, lead_band):
    n, mean_signed_err = Σ(fc_ws − obs_ws) / n
    mean_|err|
    also report at ws_obs ≥ 5 mph subset (light-and-up) so calm-wind noise
    doesn't drown a real signal at moderate+ speeds.

Verdict per octant (over ALL lead bands pooled):
  ★ REAL       — |signed bias| ≥ 0.7 mph AND n ≥ 500 AND ≥5-mph subset agrees in sign
  ⚠ WATCH      — |signed bias| ≥ 0.4 mph AND n ≥ 500
  flat         — otherwise

Overall verdict:
  ★ DIRECTION-CONDITIONAL — ≥3 octants flagged REAL with mixed signs
                            (some over-forecast, some under). L2 additive
                            per-octant bias correction is the follow-up.
  ⚠ SUGGESTIVE           — 1-2 REAL octants OR ≥3 WATCH octants
  flat                   — no consistent direction signal

Skips 0-5h band by convention (matches h_c1h_orthogonality) — nowcast
band has different error dynamics than forecast bands.

Run:
    python3 analysis/h_ws_octant_bias.py
    MYWEATHER_REFRESH=1 python3 analysis/h_ws_octant_bias.py
"""
import os
import sys
import json
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

BANDS = [("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]

OCTANTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

MIN_CELL_N     = 200   # minimum n per (octant, band) for cell to display
MIN_OCTANT_N   = 500   # minimum n per octant (all bands pooled) for verdict
REAL_THRESH    = 0.7   # mph — signed bias to flag ★ REAL
WATCH_THRESH   = 0.4   # mph — signed bias to flag ⚠ WATCH
LIGHT_UP_FLOOR = 5.0   # mph — obs floor for the "moderate+" subset


def octant_of(wd_deg):
    """Bin a wind direction in degrees into 8 compass sectors, each 45° wide,
    centered on the cardinal + intercardinal points (N centered on 0°/360°).
    """
    if wd_deg is None:
        return None
    d = float(wd_deg) % 360.0
    idx = int((d + 22.5) % 360 // 45)
    return OCTANTS[idx]


def lead_band(lh):
    for lab, lo, hi in BANDS:
        if lo <= lh < hi:
            return lab
    return None


def main():
    # Streaming join: ws rows carry fc+obs for wind SPEED, wd rows carry
    # fc+obs for wind DIRECTION. Group by (run_time, obs_time, lead_h) so
    # we can bin ws error by observed wd octant.
    joined = defaultdict(dict)
    total_rows = 0
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            total_rows += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            f = r.get("field")
            if f not in ("ws", "wd"):
                continue
            key = (r.get("run_time"), r.get("obs_time"), r.get("lead_h"))
            if None in key:
                continue
            joined[key][f] = (r.get("forecast_l1"), r.get("observed"))

    # per (octant, band, subset) → [n, sum_signed_err, sum_abs_err]
    # subset: "all" or "moderate+"
    cells = defaultdict(lambda: [0, 0.0, 0.0])
    # per octant (all bands) → [n, sum_signed_err, sum_abs_err] for both subsets
    per_octant = defaultdict(lambda: {"all": [0, 0.0, 0.0], "moderate+": [0, 0.0, 0.0]})
    joined_used = 0

    for (run_t, obs_t, lead_h), fs in joined.items():
        if "ws" not in fs or "wd" not in fs:
            continue
        ws_fc, ws_obs = fs["ws"]
        wd_fc, wd_obs = fs["wd"]
        if None in (ws_fc, ws_obs, wd_obs):
            continue
        band = lead_band(lead_h)
        if band is None:
            continue
        oct_ = octant_of(wd_obs)
        if oct_ is None:
            continue
        err = float(ws_fc) - float(ws_obs)  # positive = HRRR over-forecast
        joined_used += 1
        # All-obs subset
        a = cells[(oct_, band, "all")]
        a[0] += 1
        a[1] += err
        a[2] += abs(err)
        po_a = per_octant[oct_]["all"]
        po_a[0] += 1
        po_a[1] += err
        po_a[2] += abs(err)
        # Moderate+ subset (obs ≥ 5 mph)
        if float(ws_obs) >= LIGHT_UP_FLOOR:
            b = cells[(oct_, band, "moderate+")]
            b[0] += 1
            b[1] += err
            b[2] += abs(err)
            po_m = per_octant[oct_]["moderate+"]
            po_m[0] += 1
            po_m[1] += err
            po_m[2] += abs(err)

    print(f"h_ws_octant_bias — rows scanned: {total_rows:,}   pairs joined: {joined_used:,}")
    print()

    # Per-cell table (octant × band, all-obs subset)
    print("Per-cell (obs octant × lead band, all obs)")
    print(f"  {'octant':<7} {'band':<8} {'n':>7} {'signed bias (mph)':>18} {'|err| (mph)':>13}")
    print("  " + "-" * 60)
    for oct_ in OCTANTS:
        for band, _, _ in BANDS:
            n, s, a = cells.get((oct_, band, "all"), [0, 0.0, 0.0])
            if n < MIN_CELL_N:
                continue
            print(f"  {oct_:<7} {band:<8} {n:>7,} {s / n:>+18.2f} {a / n:>13.2f}")
    print()

    # Per-octant pooled (all bands together), both subsets
    print("Per-octant pooled (all bands, both obs subsets)")
    print(f"  {'octant':<7} {'subset':<11} {'n':>7} {'signed bias':>12} {'|err|':>7}   verdict")
    print("  " + "-" * 68)

    real_octants = []
    watch_octants = []
    signs = {}  # octant -> sign of signed bias in ALL subset (for mixed-sign check)

    for oct_ in OCTANTS:
        row_all = per_octant[oct_]["all"]
        row_mod = per_octant[oct_]["moderate+"]
        n_a, s_a, a_a = row_all
        n_m, s_m, a_m = row_mod
        if n_a < MIN_CELL_N:
            continue
        bias_a = s_a / n_a if n_a else 0.0
        bias_m = s_m / n_m if n_m else 0.0
        mae_a  = a_a / n_a if n_a else 0.0
        mae_m  = a_m / n_m if n_m else 0.0
        # Verdict on ALL subset with cross-check on MODERATE+ subset for sign
        # agreement (calm-wind noise can flip an octant's mean by itself).
        verdict = "flat"
        if n_a >= MIN_OCTANT_N and abs(bias_a) >= REAL_THRESH:
            sign_agree = (bias_a > 0) == (bias_m > 0) if n_m >= MIN_CELL_N else False
            if sign_agree:
                verdict = "★ REAL"
                real_octants.append((oct_, bias_a, n_a))
            else:
                verdict = "⚠ WATCH (calm-flip)"
                watch_octants.append((oct_, bias_a, n_a))
        elif n_a >= MIN_OCTANT_N and abs(bias_a) >= WATCH_THRESH:
            verdict = "⚠ WATCH"
            watch_octants.append((oct_, bias_a, n_a))
        signs[oct_] = 1 if bias_a > 0 else -1
        print(f"  {oct_:<7} {'all':<11} {n_a:>7,} {bias_a:>+12.2f} {mae_a:>7.2f}   {verdict}")
        if n_m >= MIN_CELL_N:
            print(f"  {'':<7} {'moderate+':<11} {n_m:>7,} {bias_m:>+12.2f} {mae_m:>7.2f}")
    print()

    # Overall verdict
    mixed_signs = False
    if len(real_octants) >= 2:
        real_signs = {(1 if b > 0 else -1) for _, b, _ in real_octants}
        mixed_signs = len(real_signs) > 1

    print("=" * 68)
    if len(real_octants) >= 3 and mixed_signs:
        print(f"→ ★ DIRECTION-CONDITIONAL: {len(real_octants)} octants flagged REAL "
              f"with mixed signs.")
        for oct_, bias, n in real_octants:
            direction = "HRRR over-forecasts" if bias > 0 else "HRRR under-forecasts"
            print(f"    {oct_}: {bias:+.2f} mph   ({direction}, n={n:,})")
        print("  Follow-up: octant-conditional L2 additive bias for ws, or an "
              "octant-aware L3 layer.")
    elif len(real_octants) >= 1 or len(watch_octants) >= 3:
        print(f"→ ⚠ SUGGESTIVE: {len(real_octants)} REAL octant(s), "
              f"{len(watch_octants)} WATCH.")
        if real_octants:
            for oct_, bias, n in real_octants:
                direction = "over-forecasts" if bias > 0 else "under-forecasts"
                print(f"    {oct_}: {bias:+.2f} mph   (HRRR {direction}, n={n:,})")
        print("  Not enough signal-across-octants to justify a per-octant "
              "correction yet. Re-run weekly.")
    else:
        print("→ flat: no consistent direction-conditional bias in raw ws.")
        print("  ws structural residual (~+17-20% MAE vs raw after full "
              "targeted package) is not octant-shaped. Investigate other "
              "cuts (regime × ws-magnitude, terrain, time-of-day).")
    print("=" * 68)


if __name__ == "__main__":
    main()
