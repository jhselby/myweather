#!/usr/bin/env python3
"""Architectural diagnostic: does derived cc = f(cl, cm, ch) beat independent
Pirate-fed cc + Lc on held-out data?

Motivation: 2026-07-30 emergency Lc intervention. cc's own shift table is
in bandage mode (95-100 kill, ne_flow demote). cm and ch Lc is working
(+34% and +50% vs raw on held-out). If cc can be derived from corrected
cl/cm/ch it inherits their wins automatically and cc's whole Lc surface
disappears. Question: does derivation actually beat independent cc?

Test setup: join per-(run_time, lead_h) rows from the pair log across the
4 cloud fields. For each joined group, compare 3 candidates against the
cc observation:

  1. current-production cc: cc row's forecast_l6 if present, else l4/l3/l2/l1.
     This is what the collector actually served (Pirate cc + Lc bandages).
  2. derived_random cc: random-overlap = 100 * (1 - Π(1 - x/100))
     where each x is that field's corrected value (l6 → l4 fallback).
  3. derived_max cc: maximum-overlap = max(corrected_cl, corrected_cm,
     corrected_ch). Conservative — assumes all three layers vertically align.

Metric: MAE per (regime × lead_band) + overall + per-field-of-day.

Verdict:
  PROMOTE — derived beats current-production by ≥ 3% pooled AND wins in
    ≥ 6 of 9 regimes AND halves-stable
  MARGINAL — derived beats by 1-3% OR wins in most cells but has some SKIP
  FLAT — within noise (< 1% either direction)
  REJECT — derived loses ≥ 3%

Run:
    python3 -m analysis.h_cc_derivation
    python3 -m analysis.h_cc_derivation --min-obs-date 2026-07-01
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = Path(__file__).resolve().parent / "output" / "h_cc_derivation.txt"

CLOUD_FIELDS = {"cc", "cl", "cm", "ch"}
LEAD_BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]


def band_of(lead):
    for lab, lo, hi in LEAD_BANDS:
        if lo <= lead < hi:
            return lab
    return None


def deepest_available(r):
    """Return the value the production stack would have applied for this row.
    Prefer forecast_l6 (post-Lc), fall back to l4/l3/l2/l1."""
    for k in ("forecast_l6", "forecast_l4", "forecast_l3", "forecast_l2", "forecast_l1"):
        v = r.get(k)
        if v is not None:
            return float(v)
    return None


def clip(v):
    return max(0.0, min(100.0, v))


def derive_random(cl, cm, ch):
    """Random-overlap: cc = 1 - (1-cl)(1-cm)(1-ch), inputs in %."""
    a = 1.0 - cl / 100.0
    b = 1.0 - cm / 100.0
    c = 1.0 - ch / 100.0
    return clip(100.0 * (1.0 - a * b * c))


def derive_max(cl, cm, ch):
    return clip(max(cl, cm, ch))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-obs-date", default="2026-07-01",
                    help="Filter obs_time >= this (default 2026-07-01)")
    args = ap.parse_args()

    # Index by (run_time, lead_h) → {field: row}
    groups = defaultdict(dict)
    n_read = 0
    n_used = 0
    print(f"reading {URL}")
    with open(cached_path(URL), "rb") as fh:
        for line in fh:
            n_read += 1
            try:
                r = json.loads(line)
            except Exception:
                continue
            f = r.get("field")
            if f not in CLOUD_FIELDS:
                continue
            obs_t = r.get("obs_time", "")
            if obs_t < args.min_obs_date:
                continue
            key = (r.get("run_time"), r.get("lead_h"))
            if key[0] is None or key[1] is None:
                continue
            groups[key][f] = r
            n_used += 1
    print(f"  rows read: {n_read:,}   cloud rows kept: {n_used:,}")
    print(f"  unique (run_time, lead_h) groups: {len(groups):,}")

    # Aggregators
    def new_agg():
        return {"n": 0, "raw_cc": 0.0, "prod_cc": 0.0, "rand_cc": 0.0, "max_cc": 0.0}
    overall = new_agg()
    by_band = defaultdict(new_agg)
    by_regime = defaultdict(new_agg)
    by_regime_band = defaultdict(new_agg)
    per_day = defaultdict(new_agg)

    complete_groups = 0
    for (run_time, lead_h), fields in groups.items():
        if not (CLOUD_FIELDS <= set(fields.keys())):
            continue
        cc_row = fields["cc"]
        cl_row, cm_row, ch_row = fields["cl"], fields["cm"], fields["ch"]
        cc_obs = cc_row.get("observed")
        if cc_obs is None:
            continue
        # Current production cc (what the collector served)
        prod_cc = deepest_available(cc_row)
        raw_cc = cc_row.get("forecast_l1")
        # Corrected component fields (l6 preferred, then l4 fallback)
        cl_c = deepest_available(cl_row)
        cm_c = deepest_available(cm_row)
        ch_c = deepest_available(ch_row)
        if None in (prod_cc, raw_cc, cl_c, cm_c, ch_c):
            continue
        derived_random = derive_random(cl_c, cm_c, ch_c)
        derived_max_v = derive_max(cl_c, cm_c, ch_c)

        band = band_of(int(lead_h))
        regime = ((cc_row.get("state_fc") or {}).get("regime_synoptic")) or "unknown"
        day = (cc_row.get("obs_time") or "")[:10]

        for agg in [overall, by_band[band], by_regime[regime],
                    by_regime_band[(regime, band)], per_day[day]]:
            agg["n"] += 1
            agg["raw_cc"] += abs(float(raw_cc) - cc_obs)
            agg["prod_cc"] += abs(prod_cc - cc_obs)
            agg["rand_cc"] += abs(derived_random - cc_obs)
            agg["max_cc"] += abs(derived_max_v - cc_obs)
        complete_groups += 1

    print(f"  complete cc/cl/cm/ch quads with obs: {complete_groups:,}")
    print()

    def mae(agg, k):
        return agg[k] / agg["n"] if agg["n"] else None

    def pct(new, base):
        return None if base is None or base == 0 else 100.0 * (base - new) / base

    out = []
    def p(*a):
        line = " ".join(str(x) for x in a)
        print(line); out.append(line)

    p("=" * 100)
    p("h_cc_derivation — does derived cc from cl/cm/ch beat independent Pirate+Lc cc?")
    p("=" * 100)
    p(f"filter: obs_time >= {args.min_obs_date}")
    p(f"n = {overall['n']:,} joined (cc, cl, cm, ch) quads with cc obs")
    p()

    # ── Overall ──
    r_raw = mae(overall, "raw_cc"); r_prod = mae(overall, "prod_cc")
    r_rand = mae(overall, "rand_cc"); r_max = mae(overall, "max_cc")
    p("OVERALL MAE (lower is better):")
    p(f"  raw HRRR/Pirate cc:     {r_raw:.3f}")
    p(f"  current production cc:  {r_prod:.3f}  ({pct(r_prod, r_raw):+.2f}% vs raw)")
    p(f"  derived (random-overlap): {r_rand:.3f}  ({pct(r_rand, r_raw):+.2f}% vs raw · "
      f"{pct(r_rand, r_prod):+.2f}% vs prod)")
    p(f"  derived (max-overlap):    {r_max:.3f}  ({pct(r_max, r_raw):+.2f}% vs raw · "
      f"{pct(r_max, r_prod):+.2f}% vs prod)")
    p()

    # ── Per lead-band ──
    p("=" * 100)
    p("PER LEAD-BAND (Δ% vs current prod, lower is better for derived):")
    p("=" * 100)
    p(f"{'band':<8} {'n':>7} {'raw':>7} {'prod':>7} {'rand':>7} {'max':>7} "
      f"{'rand vs prod':>13} {'max vs prod':>12}")
    for band, _, _ in LEAD_BANDS:
        agg = by_band[band]
        if agg["n"] == 0: continue
        p(f"{band:<8} {agg['n']:>7,} {mae(agg,'raw_cc'):>7.2f} {mae(agg,'prod_cc'):>7.2f} "
          f"{mae(agg,'rand_cc'):>7.2f} {mae(agg,'max_cc'):>7.2f} "
          f"{pct(mae(agg,'rand_cc'), mae(agg,'prod_cc')):>+12.2f}% "
          f"{pct(mae(agg,'max_cc'), mae(agg,'prod_cc')):>+11.2f}%")
    p()

    # ── Per regime ──
    p("=" * 100)
    p("PER REGIME (Δ% vs current prod):")
    p("=" * 100)
    p(f"{'regime':<14} {'n':>7} {'raw':>7} {'prod':>7} {'rand':>7} {'max':>7} "
      f"{'rand vs prod':>13} {'max vs prod':>12}")
    for regime in sorted(by_regime.keys(), key=lambda k: -by_regime[k]["n"]):
        agg = by_regime[regime]
        if agg["n"] < 100: continue
        p(f"{regime:<14} {agg['n']:>7,} {mae(agg,'raw_cc'):>7.2f} {mae(agg,'prod_cc'):>7.2f} "
          f"{mae(agg,'rand_cc'):>7.2f} {mae(agg,'max_cc'):>7.2f} "
          f"{pct(mae(agg,'rand_cc'), mae(agg,'prod_cc')):>+12.2f}% "
          f"{pct(mae(agg,'max_cc'), mae(agg,'prod_cc')):>+11.2f}%")
    p()

    # ── Per obs-day (halves-style check) ──
    p("=" * 100)
    p("PER OBS-DAY trailing 14d (last 14 days present):")
    p("=" * 100)
    p(f"{'day':<12} {'n':>6} {'raw':>7} {'prod':>7} {'rand':>7} {'max':>7} {'rand vs prod':>13}")
    days = sorted(per_day.keys())[-14:]
    for day in days:
        agg = per_day[day]
        if agg["n"] < 30: continue
        p(f"{day:<12} {agg['n']:>6,} {mae(agg,'raw_cc'):>7.2f} {mae(agg,'prod_cc'):>7.2f} "
          f"{mae(agg,'rand_cc'):>7.2f} {mae(agg,'max_cc'):>7.2f} "
          f"{pct(mae(agg,'rand_cc'), mae(agg,'prod_cc')):>+12.2f}%")
    p()

    # ── Halves check ──
    p("=" * 100)
    p("HALVES-STABILITY (chronological split by obs_time median):")
    p("=" * 100)
    # Rebuild sample counts per day, then split
    day_ns = [(d, per_day[d]["n"]) for d in sorted(per_day.keys())]
    tot = sum(n for _, n in day_ns)
    cumsum = 0
    split_day = None
    for d, n in day_ns:
        cumsum += n
        if cumsum >= tot / 2:
            split_day = d
            break
    if split_day:
        A = new_agg(); B = new_agg()
        for d in sorted(per_day.keys()):
            target = A if d < split_day else B
            for k in target: target[k] += per_day[d][k]
        for label, agg in [("half A", A), ("half B", B)]:
            if agg["n"] == 0: continue
            r_prod = mae(agg, "prod_cc"); r_rand = mae(agg, "rand_cc"); r_max = mae(agg, "max_cc")
            p(f"  {label} n={agg['n']:,}: prod={r_prod:.2f}  rand={r_rand:.2f} ({pct(r_rand,r_prod):+.2f}%)  "
              f"max={r_max:.2f} ({pct(r_max,r_prod):+.2f}%)")
    p()

    # ── Verdict ──
    r_rand_overall = pct(r_rand, r_prod)
    r_max_overall = pct(r_max, r_prod)
    best_shape = "random" if (r_rand_overall or -99) > (r_max_overall or -99) else "max"
    best_pct = max(r_rand_overall or -99, r_max_overall or -99)
    win_regimes = sum(1 for regime, agg in by_regime.items()
                      if agg["n"] >= 100 and pct(mae(agg, "rand_cc" if best_shape=="random" else "max_cc"),
                                                  mae(agg, "prod_cc")) >= 3.0)
    tot_regimes = sum(1 for agg in by_regime.values() if agg["n"] >= 100)

    p("=" * 100)
    if best_pct is None:
        v = "VERDICT: NULL — insufficient data."
    elif best_pct >= 3.0 and win_regimes >= 6:
        v = (f"VERDICT: PROMOTE — derived-{best_shape} beats current production cc "
             f"by {best_pct:+.2f}% pooled, wins {win_regimes}/{tot_regimes} regimes. "
             f"Retire cc-specific Lc; derive cc = f(cl, cm, ch) at snapshot time.")
    elif best_pct >= 1.0:
        v = (f"VERDICT: MARGINAL — derived-{best_shape} beats by {best_pct:+.2f}% pooled "
             f"({win_regimes}/{tot_regimes} regimes). Consider regime-conditional adoption.")
    elif best_pct >= -1.0:
        v = (f"VERDICT: FLAT — derived and current within noise ({best_pct:+.2f}%). "
             f"Architectural rewrite not justified on MAE alone.")
    else:
        v = (f"VERDICT: REJECT — derived loses to current production by {-best_pct:+.2f}%. "
             f"Pirate cc feed genuinely carries information beyond max/blend of layers.")
    p(v)
    p("=" * 100)

    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(out) + "\n")
    print(f"\nwrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
