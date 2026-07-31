#!/usr/bin/env python3
"""Pure composition error: does Ccd's formula match METAR total sky cover
even when component values are perfect?

Method: apply each candidate formula to OBSERVED cl/cm/ch values (from METAR
per-layer sky cover reports) and compare against OBSERVED total cc (METAR
total sky cover). This strips cascade error — cl/cm/ch correction quality
doesn't enter — leaving only "does the formula reproduce how observers
report total sky cover?"

Interpretation:
  MAE near 0 → the formula is the right choice; nothing to tune
  MAE > 0    → composition error is a real independent quantity worth scoring
              → belongs in scoreboard mean, currently ignored

Compares max / random / max_random per regime, plus pooled.

Run:
    python3 -m analysis.h_cc_composition_pure
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
OUT_TXT = Path(__file__).resolve().parent / "output" / "h_cc_composition_pure.txt"

CLOUD_FIELDS = {"cc", "cl", "cm", "ch"}
FORMULAS = ("max", "random", "max_random")


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
    lm = max(cl, cm)
    a = 1.0 - lm / 100.0
    b = 1.0 - ch / 100.0
    return clip(100.0 * (1.0 - a * b))


DERIVERS = {"max": derive_max, "random": derive_random, "max_random": derive_max_random}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-obs-date", default="2026-07-01")
    args = ap.parse_args()

    # Group by (run_time, lead_h) → {field: row}. All 4 fields share the
    # same obs at a given (obs_time, lead_h), but joining on the pair-log's
    # native key handles the shape uniformly.
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
    print(f"  cloud rows scanned: {n_read:,}   unique quads: {len(groups):,}")

    # Aggregate pooled + per-regime pure composition error using OBSERVED
    # component values. Also keep the reference "max-of-obs vs obs_cc"
    # residual = how far METAR total is from max(METAR layer obs). If this
    # is meaningful and non-zero, the formula choice matters.
    def new_agg():
        d = {"n": 0, "obs_sum": 0.0}
        for name in FORMULAS:
            d[f"{name}_abs"] = 0.0
            d[f"{name}_bias"] = 0.0
        return d

    overall = new_agg()
    by_regime = defaultdict(new_agg)

    complete = 0
    for (rt, lead), fields in groups.items():
        if not (CLOUD_FIELDS <= set(fields.keys())):
            continue
        # Read OBSERVED values (each field's `observed`)
        obs_cc = fields["cc"].get("observed")
        obs_cl = fields["cl"].get("observed")
        obs_cm = fields["cm"].get("observed")
        obs_ch = fields["ch"].get("observed")
        if None in (obs_cc, obs_cl, obs_cm, obs_ch):
            continue

        cc_row = fields["cc"]
        regime = ((cc_row.get("state_fc") or {}).get("regime_synoptic")) or "unknown"

        for agg in [overall, by_regime[regime]]:
            agg["n"] += 1
            agg["obs_sum"] += obs_cc
            for name in FORMULAS:
                pred = DERIVERS[name](obs_cl, obs_cm, obs_ch)
                agg[f"{name}_abs"] += abs(pred - obs_cc)
                agg[f"{name}_bias"] += (pred - obs_cc)
        complete += 1

    print(f"  complete cc/cl/cm/ch obs quads: {complete:,}")
    print()

    def mae(agg, name): return agg[f"{name}_abs"] / agg["n"] if agg["n"] else None
    def bias(agg, name): return agg[f"{name}_bias"] / agg["n"] if agg["n"] else None

    out = []
    def p(*a):
        line = " ".join(str(x) for x in a)
        print(line); out.append(line)

    p("=" * 100)
    p("h_cc_composition_pure — formula error using OBSERVED components (strips cascade)")
    p("=" * 100)
    p(f"filter: obs_time >= {args.min_obs_date}")
    p(f"n = {overall['n']:,} joined obs quads (cc, cl, cm, ch)")
    p(f"obs_cc mean = {overall['obs_sum']/overall['n']:.2f}")
    p()

    # ── Overall ──
    p("OVERALL PURE COMPOSITION MAE (formula(obs_cl, obs_cm, obs_ch) vs obs_cc):")
    p(f"  {'formula':<12} {'MAE':>8} {'bias':>8}   (bias = mean signed err; +ve = formula over-reports vs METAR)")
    for name in FORMULAS:
        p(f"  {name:<12} {mae(overall, name):>8.3f} {bias(overall, name):>+8.3f}")
    p()

    # ── Per regime ──
    p("=" * 100)
    p("PER REGIME PURE COMPOSITION MAE:")
    p("=" * 100)
    p(f"  {'regime':<14} {'n':>7} {'mean_obs':>9}   "
      + "  ".join(f"{n:>18}" for n in FORMULAS))
    p(f"  {'':<14} {'':>7} {'':>9}   "
      + "  ".join(f"{'MAE / bias':>18}" for _ in FORMULAS))
    winner_by_regime = {}
    for regime in sorted(by_regime.keys(), key=lambda k: -by_regime[k]["n"]):
        agg = by_regime[regime]
        if agg["n"] < 100:
            continue
        obs_mean = agg["obs_sum"] / agg["n"]
        cells = []
        maes = {}
        for name in FORMULAS:
            m = mae(agg, name); b = bias(agg, name)
            cells.append(f"{m:>7.3f} / {b:>+6.2f}   ")
            maes[name] = m
        best = min(FORMULAS, key=lambda n: maes[n])
        winner_by_regime[regime] = (best, maes[best], agg["n"])
        marker = f" ← {best}"
        p(f"  {regime:<14} {agg['n']:>7,} {obs_mean:>9.2f}   " + "  ".join(cells) + marker)
    p()

    # ── Interpretation ──
    p("=" * 100)
    p("INTERPRETATION")
    p("=" * 100)
    max_mae_overall = mae(overall, "max")
    max_bias_overall = bias(overall, "max")

    obs_mean_cc = overall["obs_sum"] / overall["n"]
    p(f"Reference: obs_cc mean is {obs_mean_cc:.1f}, so a pure composition MAE of")
    p(f"~1-2 points is negligible relative to what users see. Non-trivial only if MAE ≥ 3.")
    p()
    p(f"Current LIVE formula = max. Pure composition MAE = {max_mae_overall:.3f} (bias {max_bias_overall:+.3f}).")
    if max_mae_overall < 2.0:
        p(f"→ CLEAN. max() reproduces METAR total sky cover to within ~2 points on average.")
        p(f"  Composition error is negligible; cc's damage vs raw is essentially all cascade.")
        p(f"  Keeping cc out of scoreboard mean stays correct — no new independent signal.")
    elif max_mae_overall < 4.0:
        p(f"→ MODEST. max() has a real ~{max_mae_overall:.1f}-point composition error.")
        p(f"  Worth exposing as a scoreboard line, but wouldn't change ship priorities.")
    else:
        p(f"→ SUBSTANTIAL. max() has a >{max_mae_overall:.0f}-point composition error.")
        p(f"  cc's damage vs raw contains significant independent signal beyond cl/cm/ch.")
        p(f"  → Recommend adding a 'cc composition' scoreboard line and re-including cc-style signal in mean.")
    p()

    # Regime-level winners disagreeing with max would motivate a regime-conditional table
    non_max = [(r, w[0], w[1], w[2]) for r, w in winner_by_regime.items() if w[0] != "max"]
    if non_max:
        p("Regimes where a non-max formula wins pure composition:")
        for r, best, m, n in non_max:
            max_m = mae(by_regime[r], "max")
            p(f"  {r} (n={n:,}): {best} wins at {m:.3f} vs max {max_m:.3f} (Δ={max_m-m:+.3f})")
    else:
        p("max wins pure composition in every regime with n≥100 — no formula-tuning signal.")
    p()

    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(out) + "\n")
    print(f"\nwrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
