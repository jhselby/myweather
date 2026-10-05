"""C1d cc/0-5h premium stability: does the high-vs-low sigma MAE premium hold?

Mirrors analysis/c1d_calibration.py (14-day rolling window, Q1/Q3 sigma cuts
over all four cloud fields, forecast_l4 -> l3 -> l2 -> l1 -> forecast as the
forecast value, middle quartiles dropped) and re-runs it for each of the last
N end dates, so the daily history that the digest does not keep becomes visible.

Per end date, for cc at 0-5h:
  n_low / n_high, low MAE, high MAE, premium % (as c1d_calibration)
  halves: premium % on the first / second 7 days of the window (same sigma cuts)
  prod%:  premium % when the error is |error_{applied_layer}| (analysis/_prod.py),
          i.e. what users saw, instead of forecast_l4

The cc/0-5h watch (project_cc_0_5h_c1d_watch) expects the premium to be real and
stable. Today's digest-run row was +429.6% against +110% on 09-13.

Run from the repo root:  python3 scripts/c1d_cc05_stability.py [--days 21] [--field cc] [--band 0-5h]
Set MYWEATHER_REFRESH=1 to force a fresh pair-log download.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from analysis._cache import cached_path, PAIR_LOG_URL
from analysis._prod import prod_error

FIELDS = ("cc", "cl", "cm", "ch")
BANDS = {"0-5h": (0, 6), "6-11h": (6, 12), "12-23h": (12, 24), "24-47h": (24, 48)}
WINDOW_DAYS = 14
MIN_N = 100


def parse_t(s):
    try:
        return datetime.strptime(s[:16], "%Y-%m-%dT%H:%M")
    except (ValueError, TypeError):
        return None


def load(field, lo, hi):
    sig = []     # (t, sigma) for all four fields: the cuts are taken over these
    tgt = []     # (t, sigma, e_l4, e_prod) for the target field and band
    with open(cached_path(PAIR_LOG_URL)) as fh:
        for line in fh:
            if '"cloud_inter_source_sigma"' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            f = r.get("field")
            if f not in FIELDS:
                continue
            s = r.get("cloud_inter_source_sigma")
            t = parse_t(r.get("obs_time") or "")
            if s is None or t is None:
                continue
            s = float(s)
            sig.append((t, s))
            if f != field:
                continue
            lead = r.get("lead_h")
            if lead is None or not (lo <= lead < hi):
                continue
            obs = r.get("observed")
            fc = (r.get("forecast_l4") or r.get("forecast_l3") or r.get("forecast_l2")
                  or r.get("forecast_l1") or r.get("forecast"))
            if obs is None or fc is None:
                continue
            ep = prod_error(r)
            tgt.append((t, s, abs(fc - obs), abs(ep) if ep is not None else None))
    return sig, tgt


def premium(rows, q1, q3, col):
    low = [r[col] for r in rows if r[1] <= q1 and r[col] is not None]
    high = [r[col] for r in rows if r[1] >= q3 and r[col] is not None]
    # c1d_calibration drops q1 < sigma < q3, keeps sigma <= q1 as low and >= q3 as high
    if len(low) < MIN_N or len(high) < MIN_N:
        return None
    lm, hm = sum(low) / len(low), sum(high) / len(high)
    return {"n_low": len(low), "n_high": len(high), "low": lm, "high": hm,
            "pct": 100 * (hm - lm) / lm if lm else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21, help="number of daily end dates to evaluate")
    ap.add_argument("--field", default="cc", choices=FIELDS)
    ap.add_argument("--band", default="0-5h", choices=list(BANDS))
    a = ap.parse_args()
    lo, hi = BANDS[a.band]

    sig, tgt = load(a.field, lo, hi)
    if not sig:
        print("No rows with cloud_inter_source_sigma. Pair log is stale or empty.")
        return
    t_max = max(t for t, _ in sig)
    print(f"{a.field}/{a.band}: {len(tgt):,} target rows, {len(sig):,} sigma rows, newest obs {t_max:%Y-%m-%dT%H:%M}")
    print(f"window = {WINDOW_DAYS}d trailing, cuts over {'/'.join(FIELDS)}; sigma <= Q1 = low, >= Q3 = high\n")
    hdr = f"{'window end':<12}{'n_low':>6}{'n_high':>7}{'low':>8}{'high':>8}{'prem%':>9}   {'half A':>9}{'half B':>9}{'prod%':>9}"
    print(hdr)
    print("-" * len(hdr))

    end_day = datetime(t_max.year, t_max.month, t_max.day)
    pcts = []
    for k in range(a.days - 1, -1, -1):
        end = end_day - timedelta(days=k) + timedelta(days=1)   # exclusive end of that day
        start = end - timedelta(days=WINDOW_DAYS)
        sigs = sorted(s for t, s in sig if start <= t < end)
        if len(sigs) < 5000:
            continue
        q1 = sigs[len(sigs) // 4]
        q3 = sigs[(3 * len(sigs)) // 4]
        rows = [r for r in tgt if start <= r[0] < end]
        full = premium(rows, q1, q3, 2)
        if not full:
            print(f"{(end - timedelta(days=1)):%Y-%m-%d}   thin (<{MIN_N} per side)")
            continue
        mid = start + timedelta(days=WINDOW_DAYS / 2)
        ha = premium([r for r in rows if r[0] < mid], q1, q3, 2)
        hb = premium([r for r in rows if r[0] >= mid], q1, q3, 2)
        pr = premium(rows, q1, q3, 3)
        pcts.append(full["pct"])
        fmt = lambda x: f"{x['pct']:+8.1f}%" if x else "     thin"
        print(f"{(end - timedelta(days=1)):%Y-%m-%d}  {full['n_low']:>6}{full['n_high']:>7}{full['low']:>8.2f}{full['high']:>8.2f}"
              f"{full['pct']:>+8.1f}%   {fmt(ha)}{fmt(hb)}{fmt(pr)}")
    if pcts:
        print(f"\npremium % over the evaluated windows: min {min(pcts):+.1f}  max {max(pcts):+.1f}  "
              f"(max/min = {max(pcts)/min(pcts):.1f}x)" if min(pcts) > 0 else
              f"\npremium % over the evaluated windows: min {min(pcts):+.1f}  max {max(pcts):+.1f}")
        print("Premium is 'stable' only if the range is narrow and both halves agree in sign and rough size.")


if __name__ == "__main__":
    main()
