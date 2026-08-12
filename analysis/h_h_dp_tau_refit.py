#!/usr/bin/env python3
"""Stage 0: shorter τ sweep restricted to h and dp, with per-lead-band scoring.

SUPERSEDED 2026-08-07 by v0.6.390g h L2 shape retune (H_SOFT_RAMP_FLOOR
0.4→0.1, H_SOFT_RAMP_END 24→10). The τ-decay path this script tests is
NOT what h or dp actually use in production:
  - h uses soft_ramp(lead) piecewise-linear in corrected_hourly.py, not
    exp(-lead/τ). The τ=240 in _L2_TAUS_DEFAULT for h is orphan.
  - dp is Magnus-derived from t + h — no direct L2 bias to tune τ for.

Adopting any Stage 0 PROMOTE this script emits would revert the
CLOSED-CLEAN shape retune. Verdict downgraded to DIAGNOSTIC-ONLY —
"STAGE 0 PROMOTE" text is retained for the sentry that surfaces the
underlying |err| pattern, but the summary caps at KILL so the digest
does not treat it as ship-eligible. See [[project_h_l2_shape_retune]]
and [[project_h_dp_tau_refit]] for the full supersession history.

Original motivation (preserved): 2026-07-31 layer-shape sentry flagged
both h and dp as τ-suspect — production helps at 0-5h but hurts at
6-23h+ (classic decay-time-constant-too-long signature). Superseded
mechanism was retuned instead; the underlying sentry pattern is
addressed by the soft_ramp shape change.

Design gate (historical, no longer live):
  1. Best τ beats τ=14 on pooled MAE by ≥ 2%
  2. No lead-band gets worse than raw (all 4 bands must be ≤ 0 vs raw)
  3. Halves-stable — both chronological halves improve
  4. Applies to h AND/OR dp — one field alone qualifies for its own τ

Walk-forward split: train pre-cutoff, evaluate post-cutoff.

Run:
    python3 -m analysis.h_h_dp_tau_refit
    python3 -m analysis.h_h_dp_tau_refit --cutoff-days 5
"""
import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = Path(__file__).resolve().parent / "output" / "h_h_dp_tau_refit.txt"

FIELDS = ("h", "dp")
TAUS = [3, 4, 5, 6, 8, 10, 14, 18, 24]
LEAD_BINS = 48
LEAD_BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]
POOLED_GAIN_THRESHOLD = 2.0   # best τ must beat τ=14 by ≥ this pct pooled
MIN_TRAIN_ROWS = 500
MIN_TEST_ROWS = 100


def band_of(lead):
    for lab, lo, hi in LEAD_BANDS:
        if lo <= lead < hi:
            return lab
    return None


def _fetch(url):
    with open(cached_path(url), "rb") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff-days", type=float, default=3.0,
                    help="Days back from now for train/test split (default 3.0)")
    args = ap.parse_args()

    now = datetime.utcnow()
    cutoff = now - timedelta(days=args.cutoff_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M")
    print(f"reading {URL}  (train < {cutoff_iso} < test)")

    # error_l1 = L1 (raw HRRR) residual — the true "no correction" baseline.
    # The unsuffixed `error` field is production residual (forecast_error_log.py:229),
    # not what we want here.
    train = defaultdict(list)   # field -> [(obs_dt, lead, error_l1)]
    test = defaultdict(list)
    n_train = n_test = 0
    n_missing_l1 = 0
    for row in _fetch(URL):
        f = row.get("field")
        if f not in FIELDS:
            continue
        lead = row.get("lead_h")
        err = row.get("error_l1")
        obs_t = row.get("obs_time", "")
        if err is None:
            n_missing_l1 += 1
            continue
        if lead is None or not obs_t:
            continue
        if not (0 <= lead < LEAD_BINS):
            continue
        try:
            obs_dt = datetime.strptime(obs_t, "%Y-%m-%dT%H:%M")
        except ValueError:
            continue
        rec = (obs_dt, int(lead), float(err))
        if obs_dt < cutoff:
            train[f].append(rec); n_train += 1
        else:
            test[f].append(rec); n_test += 1
    print(f"  train {n_train:,}   test {n_test:,}   (skipped {n_missing_l1:,} rows w/o error_l1)")

    out = []
    def p(*a):
        line = " ".join(str(x) for x in a)
        print(line); out.append(line)

    p("=" * 100)
    p("h_h_dp_tau_refit — shorter τ sweep for h and dp with per-lead-band scoring")
    p("=" * 100)
    p(f"train cutoff {cutoff_iso}  ({args.cutoff_days}d back)")
    p(f"τ candidates {TAUS}")
    p()

    per_field_verdicts = {}
    for field in FIELDS:
        tr = train[field]
        te = test[field]
        if len(tr) < MIN_TRAIN_ROWS or len(te) < MIN_TEST_ROWS:
            p(f"[{field}] SKIP — train={len(tr)}, test={len(te)}, need ≥{MIN_TRAIN_ROWS}/≥{MIN_TEST_ROWS}")
            continue

        # ── Baseline (uncorrected) MAE overall + per band ──
        baseline_abs = 0.0; baseline_n = 0
        base_by_band = defaultdict(lambda: [0.0, 0])
        for (_, lead, err) in te:
            b = band_of(lead)
            baseline_abs += abs(err); baseline_n += 1
            base_by_band[b][0] += abs(err); base_by_band[b][1] += 1
        base_mae = baseline_abs / baseline_n
        base_band_mae = {b: (s / n if n else None) for b, (s, n) in base_by_band.items()}

        # ── For each τ, fit correction from train, evaluate on test ──
        by_tau = {}     # tau -> {pooled: mae, bands: {band: mae}}
        fit_ref = cutoff
        for tau in TAUS:
            sums = defaultdict(float); wts = defaultdict(float)
            for (obs_dt, lead, err) in tr:
                age = max(0.0, (fit_ref - obs_dt).total_seconds() / 86400.0)
                w = math.exp(-age / tau)
                sums[lead] += err * w
                wts[lead] += w
            corr = [(sums[l] / wts[l]) if wts[l] > 0 else 0.0 for l in range(LEAD_BINS)]

            c_abs = 0.0; c_n = 0
            c_by_band = defaultdict(lambda: [0.0, 0])
            for (_, lead, err) in te:
                ce = err - corr[lead]
                b = band_of(lead)
                c_abs += abs(ce); c_n += 1
                c_by_band[b][0] += abs(ce); c_by_band[b][1] += 1
            pooled_mae = c_abs / c_n
            band_mae = {b: (s / n if n else None) for b, (s, n) in c_by_band.items()}
            by_tau[tau] = {"pooled": pooled_mae, "bands": band_mae}

        # ── Halves-stability check for the best-pooled τ ──
        # Split test rows chronologically by median obs_dt
        te_sorted = sorted(te, key=lambda x: x[0])
        mid = len(te_sorted) // 2
        half_A = te_sorted[:mid]
        half_B = te_sorted[mid:]

        def _eval_half(half, corr):
            if not half: return None
            s = 0.0
            for (_, lead, err) in half:
                s += abs(err - corr[lead])
            return s / len(half)

        halves_by_tau = {}
        for tau in TAUS:
            sums = defaultdict(float); wts = defaultdict(float)
            for (obs_dt, lead, err) in tr:
                age = max(0.0, (fit_ref - obs_dt).total_seconds() / 86400.0)
                w = math.exp(-age / tau)
                sums[lead] += err * w
                wts[lead] += w
            corr = [(sums[l] / wts[l]) if wts[l] > 0 else 0.0 for l in range(LEAD_BINS)]
            a_base = sum(abs(e) for (_, _, e) in half_A) / len(half_A) if half_A else None
            b_base = sum(abs(e) for (_, _, e) in half_B) / len(half_B) if half_B else None
            halves_by_tau[tau] = {
                "A": _eval_half(half_A, corr),
                "B": _eval_half(half_B, corr),
                "A_base": a_base,
                "B_base": b_base,
            }

        # ── Print table ──
        p("=" * 100)
        p(f"FIELD: {field}   n_train={len(tr):,}   n_test={len(te):,}")
        p("=" * 100)
        p(f"  {'τ':>4}  {'pooled':>7} {'vs raw':>8} {'vs τ=14':>8}   "
          + " ".join([f"{b:>7}" for b, _, _ in LEAD_BANDS])
          + "     halves(A/B vs raw)")
        p(f"  {'-':>4}  {base_mae:>7.3f} {'—':>8} {'—':>8}   "
          + " ".join([f"{base_band_mae[b]:>7.3f}" if base_band_mae[b] is not None else f"{'—':>7}"
                     for b, _, _ in LEAD_BANDS])
          + "   raw baseline")

        t14_pooled = by_tau[14]["pooled"] if 14 in by_tau else None
        for tau in TAUS:
            d = by_tau[tau]
            vs_raw = 100 * (base_mae - d["pooled"]) / base_mae
            vs_14 = 100 * (t14_pooled - d["pooled"]) / t14_pooled if t14_pooled else 0.0
            band_cells = []
            for b, _, _ in LEAD_BANDS:
                bv = d["bands"].get(b)
                if bv is None or base_band_mae[b] is None:
                    band_cells.append(f"{'—':>7}")
                else:
                    d_band = 100 * (base_band_mae[b] - bv) / base_band_mae[b]
                    marker = "" if d_band >= 0 else "!"
                    band_cells.append(f"{d_band:>+6.1f}%{marker}")
            hA = halves_by_tau[tau]["A"]; hB = halves_by_tau[tau]["B"]
            hA_base = halves_by_tau[tau]["A_base"]; hB_base = halves_by_tau[tau]["B_base"]
            hA_pct = 100 * (hA_base - hA) / hA_base if (hA and hA_base) else 0
            hB_pct = 100 * (hB_base - hB) / hB_base if (hB and hB_base) else 0
            p(f"  {tau:>4}  {d['pooled']:>7.3f} {vs_raw:>+7.1f}% {vs_14:>+7.1f}%   "
              + " ".join(band_cells)
              + f"     {hA_pct:+5.1f} / {hB_pct:+5.1f}")

        p()
        p(f"  {'! marker'} = band worse than raw (band correction hurts).")
        p()

        # ── Per-field verdict ──
        best_tau = min(TAUS, key=lambda t: by_tau[t]["pooled"])
        best = by_tau[best_tau]
        vs_14 = 100 * (t14_pooled - best["pooled"]) / t14_pooled if t14_pooled else 0.0
        vs_raw_best = 100 * (base_mae - best["pooled"]) / base_mae
        # All-bands-improve gate
        all_bands_improve = all(
            (best["bands"].get(b) is not None and base_band_mae[b] is not None and
             best["bands"][b] <= base_band_mae[b])
            for b, _, _ in LEAD_BANDS
        )
        halves_ok = (
            halves_by_tau[best_tau]["A"] is not None and halves_by_tau[best_tau]["B"] is not None and
            halves_by_tau[best_tau]["A_base"] is not None and halves_by_tau[best_tau]["B_base"] is not None and
            (halves_by_tau[best_tau]["A"] < halves_by_tau[best_tau]["A_base"]) and
            (halves_by_tau[best_tau]["B"] < halves_by_tau[best_tau]["B_base"])
        )

        if best_tau == 14:
            v = f"HOLD — best τ IS 14 ({best['pooled']:.3f} vs raw {base_mae:.3f}, {vs_raw_best:+.1f}%). No change."
        elif vs_14 < POOLED_GAIN_THRESHOLD:
            v = (f"HOLD — best τ={best_tau} gains only {vs_14:+.2f}% vs τ=14 "
                 f"(threshold {POOLED_GAIN_THRESHOLD:.1f}%). Not worth per-field τ complexity.")
        elif not all_bands_improve:
            bad_bands = [b for b, _, _ in LEAD_BANDS
                         if best["bands"].get(b) is not None
                         and base_band_mae[b] is not None
                         and best["bands"][b] > base_band_mae[b]]
            v = (f"HOLD — best τ={best_tau} gains {vs_14:+.2f}% pooled vs τ=14 but "
                 f"HURTS bands {bad_bands} vs raw. Per-lead-band SKIP needed instead of τ change alone.")
        elif not halves_ok:
            v = (f"HOLD — best τ={best_tau} improves pooled + all bands, but halves NOT stable "
                 f"(A vs raw = {(halves_by_tau[best_tau]['A_base']-halves_by_tau[best_tau]['A']):+.3f}, "
                 f"B = {(halves_by_tau[best_tau]['B_base']-halves_by_tau[best_tau]['B']):+.3f}).")
        else:
            v = (f"STAGE 0 PROMOTE — τ={best_tau} for {field}: pooled {vs_14:+.2f}% vs τ=14, "
                 f"{vs_raw_best:+.2f}% vs raw, all 4 bands improve, halves stable. "
                 f"Advance to Stage 1 halves-strict.")

        per_field_verdicts[field] = (best_tau, vs_14, vs_raw_best, v)
        p(f"[{field}] {v}")
        p()

    # ── Cross-field summary ──
    p("=" * 100)
    p("SUMMARY")
    p("=" * 100)
    if not per_field_verdicts:
        p("VERDICT: NULL — neither h nor dp had enough data.")
    else:
        promotes = [f for f, (_, _, _, v) in per_field_verdicts.items() if v.startswith("STAGE 0 PROMOTE")]
        if promotes:
            # Downgrade to KILL — the τ-decay mechanism being tested is not
            # what h/dp use in production (see docstring). Emitting PROMOTE
            # would mislead the digest into treating a mechanism-swap as a
            # parameter tweak. See project_h_l2_shape_retune.
            per_field_str = ", ".join(
                f"{f}→τ={per_field_verdicts[f][0]} ({per_field_verdicts[f][1]:+.1f}% vs τ=14)"
                for f in promotes
            )
            p(f"VERDICT: KILL (supersession guard) — per-field τ candidates were "
              f"[{per_field_str}] but adopting them would revert the CLOSED-CLEAN "
              f"soft_ramp retune (v0.6.390g). h uses piecewise soft_ramp not exp(-lead/τ); "
              f"dp is Magnus-derived. Do not scope Stage 1. Underlying |err| pattern "
              f"is already addressed by the shape retune.")
        else:
            p("VERDICT: STAGE 0 HOLD — neither h nor dp promotes. "
              "Best-τ either IS 14, gains too little, hurts a band, or halves-unstable.")
    p("=" * 100)

    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(out) + "\n")
    print(f"\nwrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
