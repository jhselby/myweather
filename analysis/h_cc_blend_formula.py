#!/usr/bin/env python3
"""Stage 0 tuner: which cc composition formula wins per regime?

Compares three overlap formulas for deriving cc from corrected cl/cm/ch:
  1. max         — cc = max(cl, cm, ch)                (HRRR's convention, Ccd today)
  2. random      — cc = 100*(1 - Π(1-x/100))            (independent layers)
  3. max_random  — cc = 100*(1 - (1-max(cl,cm)/100)*(1-ch/100))
                    (ECMWF/GFS convention: cl+cm contiguous, random with ch)

For each synoptic regime, ranks the three formulas by held-out MAE vs observed
cc. Emits a regime→formula table candidate for extending Ccd.

This is Stage 0 (magnitude check). Halves-verify is Stage 2 territory. Any
regime with ≥3% MAE gain from a non-max formula is a candidate for wire.

Run:
    python3 -m analysis.h_cc_blend_formula
    python3 -m analysis.h_cc_blend_formula --min-obs-date 2026-07-01
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
OUT_TXT = Path(__file__).resolve().parent / "output" / "h_cc_blend_formula.txt"

CLOUD_FIELDS = {"cc", "cl", "cm", "ch"}
LEAD_BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]
FORMULAS = ("max", "random", "max_random")
MIN_N_REGIME = 100
GAIN_THRESHOLD_PCT = 3.0  # non-max must beat max by this to be a candidate


def band_of(lead):
    for lab, lo, hi in LEAD_BANDS:
        if lo <= lead < hi:
            return lab
    return None


def deepest_available(r):
    for k in ("forecast_l6", "forecast_l4", "forecast_l3", "forecast_l2", "forecast_l1"):
        v = r.get(k)
        if v is not None:
            return float(v)
    return None


def clip(v):
    return max(0.0, min(100.0, v))


def derive_max(cl, cm, ch):
    return clip(max(cl, cm, ch))


def derive_random(cl, cm, ch):
    a = 1.0 - cl / 100.0
    b = 1.0 - cm / 100.0
    c = 1.0 - ch / 100.0
    return clip(100.0 * (1.0 - a * b * c))


def derive_max_random(cl, cm, ch):
    """cl+cm treated as adjacent (max), then random overlap with ch."""
    lm = max(cl, cm)
    a = 1.0 - lm / 100.0
    b = 1.0 - ch / 100.0
    return clip(100.0 * (1.0 - a * b))


DERIVERS = {"max": derive_max, "random": derive_random, "max_random": derive_max_random}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-obs-date", default="2026-07-01")
    args = ap.parse_args()

    groups = defaultdict(dict)
    n_read = 0
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
    print(f"  rows read: {n_read:,}   unique quads: {len(groups):,}")

    def new_agg():
        d = {"n": 0}
        for name in FORMULAS:
            d[name] = 0.0
        d["obs_sum"] = 0.0
        return d

    overall = new_agg()
    by_regime = defaultdict(new_agg)
    by_regime_band = defaultdict(new_agg)
    per_day_by_regime = defaultdict(lambda: defaultdict(new_agg))

    complete = 0
    for (run_time, lead_h), fields in groups.items():
        if not (CLOUD_FIELDS <= set(fields.keys())):
            continue
        cc_row = fields["cc"]
        cc_obs = cc_row.get("observed")
        if cc_obs is None:
            continue
        cl_c = deepest_available(fields["cl"])
        cm_c = deepest_available(fields["cm"])
        ch_c = deepest_available(fields["ch"])
        if None in (cl_c, cm_c, ch_c):
            continue

        band = band_of(int(lead_h))
        regime = ((cc_row.get("state_fc") or {}).get("regime_synoptic")) or "unknown"
        day = (cc_row.get("obs_time") or "")[:10]

        per_row = {name: DERIVERS[name](cl_c, cm_c, ch_c) for name in FORMULAS}
        for agg in [overall, by_regime[regime], by_regime_band[(regime, band)],
                    per_day_by_regime[regime][day]]:
            agg["n"] += 1
            agg["obs_sum"] += cc_obs
            for name in FORMULAS:
                agg[name] += abs(per_row[name] - cc_obs)
        complete += 1

    print(f"  complete quads with obs: {complete:,}")
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
    p("h_cc_blend_formula — which cc overlap formula wins per regime?")
    p("=" * 100)
    p(f"filter: obs_time >= {args.min_obs_date}")
    p(f"n = {overall['n']:,} joined cc/cl/cm/ch quads with cc obs")
    p()

    # ── Overall ──
    baseline = mae(overall, "max")
    p("OVERALL MAE (lower is better):")
    for name in FORMULAS:
        v = mae(overall, name)
        marker = " ← baseline" if name == "max" else f"  ({pct(v, baseline):+.2f}% vs max)"
        p(f"  {name:<12} {v:.3f}{marker}")
    p()

    # ── Per regime ──
    p("=" * 100)
    p("PER REGIME — MAE for each formula, Δ% vs max baseline:")
    p("=" * 100)
    p(f"{'regime':<14} {'n':>7} {'mean_obs':>9} {'max':>7} {'random':>7} {'m_rand':>7} "
      f"{'random vs max':>15} {'m_rand vs max':>15} {'best':>10}")
    regime_winners = {}
    for regime in sorted(by_regime.keys(), key=lambda k: -by_regime[k]["n"]):
        agg = by_regime[regime]
        if agg["n"] < MIN_N_REGIME:
            continue
        vals = {name: mae(agg, name) for name in FORMULAS}
        obs_mean = agg["obs_sum"] / agg["n"]
        d_rand = pct(vals["random"], vals["max"])
        d_mrand = pct(vals["max_random"], vals["max"])
        best_name = min(FORMULAS, key=lambda n: vals[n])
        best_gain = pct(vals[best_name], vals["max"]) if best_name != "max" else 0.0
        star = " ★" if best_name != "max" and best_gain >= GAIN_THRESHOLD_PCT else ""
        regime_winners[regime] = (best_name, best_gain, agg["n"])
        p(f"{regime:<14} {agg['n']:>7,} {obs_mean:>9.2f} {vals['max']:>7.2f} "
          f"{vals['random']:>7.2f} {vals['max_random']:>7.2f} "
          f"{d_rand:>+14.2f}% {d_mrand:>+14.2f}% {best_name:>10}{star}")
    p()

    # ── Per regime × lead-band ──
    p("=" * 100)
    p("PER REGIME × LEAD-BAND — best formula per cell (min n=50):")
    p("=" * 100)
    p(f"{'regime':<14} {'band':<8} {'n':>6} {'max':>6} {'random':>6} {'m_rand':>6} "
      f"{'best':>10} {'gain vs max':>12}")
    for regime in sorted(by_regime.keys(), key=lambda k: -by_regime[k]["n"]):
        if by_regime[regime]["n"] < MIN_N_REGIME:
            continue
        for band, _, _ in LEAD_BANDS:
            agg = by_regime_band[(regime, band)]
            if agg["n"] < 50:
                continue
            vals = {name: mae(agg, name) for name in FORMULAS}
            best_name = min(FORMULAS, key=lambda n: vals[n])
            gain = pct(vals[best_name], vals["max"]) if best_name != "max" else 0.0
            star = " ★" if best_name != "max" and gain >= GAIN_THRESHOLD_PCT else ""
            p(f"{regime:<14} {band:<8} {agg['n']:>6,} {vals['max']:>6.2f} "
              f"{vals['random']:>6.2f} {vals['max_random']:>6.2f} "
              f"{best_name:>10} {gain:>+11.2f}%{star}")
    p()

    # ── Halves-stability per regime for non-max winners ──
    p("=" * 100)
    p("HALVES-STABILITY for regimes where non-max wins (chronological split):")
    p("=" * 100)
    any_stable = False
    for regime, (best_name, best_gain, n) in regime_winners.items():
        if best_name == "max":
            continue
        days_agg = per_day_by_regime[regime]
        day_ns = sorted([(d, days_agg[d]["n"]) for d in days_agg.keys()])
        tot = sum(n for _, n in day_ns)
        if tot == 0:
            continue
        cumsum = 0
        split_day = None
        for d, cnt in day_ns:
            cumsum += cnt
            if cumsum >= tot / 2:
                split_day = d
                break
        if not split_day:
            continue
        A = new_agg(); B = new_agg()
        for d, _ in day_ns:
            target = A if d < split_day else B
            for k in target:
                target[k] += days_agg[d][k]
        if A["n"] < 50 or B["n"] < 50:
            p(f"  {regime:<14} best={best_name} — halves too thin (A={A['n']}, B={B['n']})")
            continue
        gA = pct(mae(A, best_name), mae(A, "max"))
        gB = pct(mae(B, best_name), mae(B, "max"))
        stable = (gA >= 1.0 and gB >= 1.0)
        marker = " STABLE ★" if stable else " UNSTABLE"
        if stable:
            any_stable = True
        p(f"  {regime:<14} best={best_name:<10} pooled +{best_gain:.2f}%  "
          f"halves A={gA:+.2f}% (n={A['n']:,})  B={gB:+.2f}% (n={B['n']:,}){marker}")
    if not regime_winners or all(v[0] == "max" for v in regime_winners.values()):
        p("  (no non-max winners at regime level)")
    p()

    # ── Verdict ──
    candidates = [(r, best_name, gain, n)
                  for r, (best_name, gain, n) in regime_winners.items()
                  if best_name != "max" and gain >= GAIN_THRESHOLD_PCT]
    p("=" * 100)
    if not candidates:
        v = ("VERDICT: STAGE 0 HOLD — max wins or ties in every regime with n≥100. "
             "No blend-formula candidate above +3% gain. Keep Ccd max-only.")
    else:
        names = ", ".join(f"{r}→{f} (+{g:.1f}%, n={n:,})"
                          for r, f, g, n in candidates)
        v = (f"VERDICT: STAGE 0 PROMOTE — {len(candidates)} regime(s) show non-max wins "
             f"≥+3%: {names}. Advance to Stage 1 halves-verify.")
    p(v)
    p("=" * 100)

    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(out) + "\n")
    print(f"\nwrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
