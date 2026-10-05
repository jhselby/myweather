"""Stage 0: does Ccd's saturation guard (raw cc >= SAT_THRESHOLD keeps raw) cost accuracy?

The guard in weather_collector/processors/cc_from_derivation.py was added 08-04 after a
trace restricted to rows whose OBSERVED cc was 95-100 (n=235): raw MAE ~2, Ccd MAE ~30.
That conditions on the outcome. The guard itself conditions on the FORECAST (raw cc >= 90),
so the matching test is: among rows where raw cc >= SAT_THRESHOLD, how does
derived-max(cl, cm, ch) compare with raw and with what was served?

Per (regime, lead band) cell, over the last WINDOW_DAYS:
  raw     = |forecast_l1 - observed|              raw HRRR/Pirate cc (what the guard keeps)
  served  = |error_{applied_layer}|               what users saw (analysis/_prod.prod_error)
  derived = |max(cl, cm, ch), each at its deepest layer - observed|   what Ccd would write with the guard off
Verdict per cell: STABLE if n >= MIN_N and derived beats served by >= MIN_LIFT_PCT in BOTH
chronological halves. The overall verdict also reports the guard-justification slice
(observed >= 95) so the cost side stays visible.

Aggregate-only Stage 0 tool (cross-cut by regime x band built in). It does not change
production. A flip needs the 7-day live-layer gate and a selector refit (served cc is
routed to NBM on most rows; see project_10_05_session).

Run:  python3 -m analysis.h_cc_sat_guard_stage0   [--days 14] [--sat 90]
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path, PAIR_LOG_URL
from _prod import prod_error

CLOUD = ("cc", "cl", "cm", "ch")
BANDS = (("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48))
LAYERS = ("forecast_l6", "forecast_l4", "forecast_l3", "forecast_l2", "forecast_l1")
MIN_N = 100
MIN_LIFT_PCT = 3.0


def band_of(lead):
    for name, lo, hi in BANDS:
        if lo <= lead < hi:
            return name
    return None


def deepest(r):
    for k in LAYERS:
        v = r.get(k)
        if v is not None:
            return float(v)
    return None


def load(days):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
    groups = defaultdict(dict)
    with open(cached_path(PAIR_LOG_URL)) as fh:
        for line in fh:
            if '"field": "c' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            f = r.get("field")
            if f not in CLOUD or (r.get("obs_time") or "") < cutoff:
                continue
            rt, lead = r.get("run_time"), r.get("lead_h")
            if rt is None or lead is None:
                continue
            groups[(rt, int(lead))][f] = r
    return groups


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def lift(base, new):
    return 100.0 * (base - new) / base if base else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--sat", type=float, default=90.0)
    a = ap.parse_args()

    groups = load(a.days)
    rows = []
    for (rt, lead), fs in groups.items():
        if not set(CLOUD) <= set(fs):
            continue
        b = band_of(lead)
        cc = fs["cc"]
        obs, l1, ep = cc.get("observed"), cc.get("forecast_l1"), prod_error(cc)
        cl, cm, ch = deepest(fs["cl"]), deepest(fs["cm"]), deepest(fs["ch"])
        if b is None or None in (obs, l1, ep, cl, cm, ch):
            continue
        if float(l1) < a.sat:
            continue
        rows.append({
            "t": cc.get("obs_time") or "", "b": b,
            "reg": (cc.get("state_fc") or {}).get("regime_synoptic") or "unknown",
            "raw": abs(float(l1) - obs), "srv": abs(ep),
            "der": abs(min(100.0, max(cl, cm, ch)) - obs), "obs": obs,
        })
    print(f"cc saturation guard Stage 0 · raw cc >= {a.sat:.0f} · last {a.days}d · saturated quads: {len(rows):,}")
    if not rows:
        print("No saturated quads (pair log stale or empty).")
        print("VERDICT: STAGE 0 NO DATA — nothing to evaluate.")
        return

    print("\nBY BAND (saturated raw rows only)")
    print(f"  {'band':<7}{'n':>7}{'raw':>8}{'served':>8}{'derived':>9}{'vs served':>11}{'vs raw':>9}")
    for name, _, _ in BANDS:
        sub = [r for r in rows if r["b"] == name]
        if not sub:
            continue
        s, d, w = mean([r["srv"] for r in sub]), mean([r["der"] for r in sub]), mean([r["raw"] for r in sub])
        print(f"  {name:<7}{len(sub):>7}{w:>8.2f}{s:>8.2f}{d:>9.2f}{lift(s, d):>+10.1f}%{lift(w, d):>+8.1f}%")

    hi = [r for r in rows if r["obs"] >= 95]
    if hi:
        print(f"\nGUARD-JUSTIFICATION SLICE (observed >= 95, n={len(hi):,}): raw {mean([r['raw'] for r in hi]):.2f}  "
              f"served {mean([r['srv'] for r in hi]):.2f}  derived {mean([r['der'] for r in hi]):.2f}")
        lo = [r for r in rows if r["obs"] < 95]
        print(f"                  OBSERVED < 95 (n={len(lo):,}):        raw {mean([r['raw'] for r in lo]):.2f}  "
              f"served {mean([r['srv'] for r in lo]):.2f}  derived {mean([r['der'] for r in lo]):.2f}")

    cells = defaultdict(list)
    for r in rows:
        cells[(r["reg"], r["b"])].append(r)
    print(f"\nPER CELL (regime x band), n >= {MIN_N}: derived vs served, halves chronological")
    print(f"  {'cell':<24}{'n':>6}{'served':>8}{'derived':>9}{'lift':>8}{'half A':>9}{'half B':>9}  verdict")
    stable = tested = 0
    for key in sorted(cells):
        sub = sorted(cells[key], key=lambda r: r["t"])
        if len(sub) < MIN_N:
            continue
        tested += 1
        mid = len(sub) // 2
        la = lift(mean([r["srv"] for r in sub[:mid]]), mean([r["der"] for r in sub[:mid]]))
        lb = lift(mean([r["srv"] for r in sub[mid:]]), mean([r["der"] for r in sub[mid:]]))
        s, d = mean([r["srv"] for r in sub]), mean([r["der"] for r in sub])
        ok = la >= MIN_LIFT_PCT and lb >= MIN_LIFT_PCT
        stable += ok
        verdict = "STABLE" if ok else ("LOSES" if lift(s, d) < 0 else "unstable")
        print(f"  {key[0] + '/' + key[1]:<24}{len(sub):>6}{s:>8.2f}{d:>9.2f}{lift(s, d):>+7.1f}%{la:>+8.1f}%{lb:>+8.1f}%  {verdict}")

    print("\nDAILY (all bands pooled, saturated rows): n, served, derived, lift")
    days = defaultdict(list)
    for r in rows:
        days[r["t"][:10]].append(r)
    for d in sorted(days):
        sub = days[d]
        s, dd = mean([r["srv"] for r in sub]), mean([r["der"] for r in sub])
        print(f"  {d}  n={len(sub):>5}  {s:6.2f}  {dd:6.2f}  {lift(s, dd):+7.1f}%")

    ordered = sorted(days)
    print("\nRECENCY (saturated rows pooled, n-weighted): is the edge still there in the newest days?")
    for k in (4, 7):
        keep = [r for d in ordered[-k:] for r in days[d]]
        if keep:
            s_k, d_k = mean([r["srv"] for r in keep]), mean([r["der"] for r in keep])
            print(f"  last {k} days: n={len(keep):>6}  served {s_k:6.2f}  derived {d_k:6.2f}  lift {lift(s_k, d_k):+6.1f}%")

    overall = lift(mean([r["srv"] for r in rows]), mean([r["der"] for r in rows]))
    print()
    if tested == 0:
        print("VERDICT: STAGE 0 THIN — no (regime, band) cell reached n >= %d." % MIN_N)
    elif stable >= max(1, tested // 2) and overall >= MIN_LIFT_PCT:
        print(f"VERDICT: STAGE 0 PROMOTE — derived-max beats served on saturated rows by {overall:+.1f}% overall; "
              f"{stable}/{tested} cells STABLE (both halves >= {MIN_LIFT_PCT:.0f}%). Guard re-evaluation candidate; "
              f"needs the 7-day gate and a selector refit (served cc is mostly NBM).")
    else:
        print(f"VERDICT: STAGE 0 HOLD — overall {overall:+.1f}%, {stable}/{tested} cells STABLE.")


if __name__ == "__main__":
    main()
