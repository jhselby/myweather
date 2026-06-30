"""
L6 / L2 double-counting investigation — step 1 of the post-2026-06-30 TODO
in `project_l6_l2_double_counting_hypothesis`.

Question:
  L6's production audit has 5 consecutive HOLD verdicts despite the lookup
  table direction matching the r5_cove_analysis gradient. Hypothesis: L2's
  Kalman mesonet blend already pulls cove temperature most of the way toward
  truth, so when L6 adds the full (waterfront − inland) gradient on top, it
  double-counts.

Test:
  On every pair where L6 actually fired (field=='t', forecast_l6 present),
  measure how much of the cove pull L2 already did. Specifically compare
  mean signed error and MAE for L1 (raw HRRR), L2 (post-Kalman), and L6
  (post-cove). If MAE(L2) << MAE(L1) on these rows, L2 was already doing
  most of the work and L6's added Δ is double-counting.

Stratification:
  - Overall (headline).
  - By state_obs.regime_synoptic (sea_breeze regime is where L6 fires
    with the largest positive Δ; that's where over-correction would bite
    hardest if the hypothesis is right).
  - By state_fc.wind octant — L6's lookup is keyed on (octant, sb_active),
    so this lets us see if the double-counting concentrates on the SE/S/SW
    sea-breeze octants.

What this does NOT do:
  - Refit the lookup table (step 2 of the TODO).
  - Re-run the production audit with a refit table (step 3).
  - Check how cove_gradient_log.json is computed today (step 4).

Run:
    python3 analysis/l6_l2_double_counting.py

Output: analysis/output/l6_l2_double_counting.txt
"""
import json
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "l6_l2_double_counting.txt")

OCTANTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def octant(deg):
    if deg is None:
        return None
    return OCTANTS[int((deg + 22.5) % 360 / 45)]


def _stats(rows):
    """rows: list of (err_l1, err_l2, err_l6, delta_applied). Returns dict of summary stats."""
    n = len(rows)
    if n == 0:
        return None
    me1 = sum(r[0] for r in rows) / n
    me2 = sum(r[1] for r in rows) / n
    me6 = sum(r[2] for r in rows) / n
    mae1 = sum(abs(r[0]) for r in rows) / n
    mae2 = sum(abs(r[1]) for r in rows) / n
    mae6 = sum(abs(r[2]) for r in rows) / n
    # Fraction of L1->truth distance L2 already covered. Negative if L2
    # overshoots past truth (which IS the double-counting prerequisite).
    l2_cover_pct = (mae1 - mae2) / mae1 * 100 if mae1 > 0 else 0.0
    # Fraction of L2->truth distance L6 covers. Negative = L6 makes it worse.
    l6_cover_pct = (mae2 - mae6) / mae2 * 100 if mae2 > 0 else 0.0
    return {
        "n": n, "me1": me1, "me2": me2, "me6": me6,
        "mae1": mae1, "mae2": mae2, "mae6": mae6,
        "l2_cover_pct": l2_cover_pct, "l6_cover_pct": l6_cover_pct,
    }


def main():
    lines = []
    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 92)
    emit("L6 / L2 DOUBLE-COUNTING INVESTIGATION")
    emit("=" * 92)
    emit("Rows: field=='t' AND forecast_l6 present (L6 actually fired).")
    emit("MAE = mean |error|.  ME = mean signed error (forecast − obs); positive = forecast warm.")
    emit("L2-cover% = how much of L1's MAE L2 erased.  L6-cover% = how much of L2's MAE L6 erased.")
    emit("Negative L6-cover% = L6 made MAE worse on this slice.")
    emit("")

    overall = []
    by_regime = defaultdict(list)
    by_octant = defaultdict(list)
    by_applied_delta = defaultdict(list)

    # Sanity counters for the L2 == L4 check (T isn't in L3_FIELDS/L4_FIELDS,
    # so forecast_l2 and forecast_l4 should be identical on every t pair).
    n_l4_present = n_l4_eq_l2 = n_l4_neq_l2 = 0
    max_l4_l2_gap = 0.0

    n_total = n_kept = 0
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            n_total += 1
            if r.get("field") != "t":
                continue
            e1 = r.get("error_l1")
            e2 = r.get("error_l2")
            e6 = r.get("error_l6")
            if e1 is None or e2 is None or e6 is None:
                continue
            n_kept += 1
            row = (float(e1), float(e2), float(e6))
            overall.append(row)

            # L2 == L4 sanity check for T (which is not in L3_FIELDS or L4_FIELDS).
            f2 = r.get("forecast_l2"); f4 = r.get("forecast_l4")
            if f2 is not None and f4 is not None:
                n_l4_present += 1
                gap = abs(float(f4) - float(f2))
                if gap < 1e-6:
                    n_l4_eq_l2 += 1
                else:
                    n_l4_neq_l2 += 1
                    if gap > max_l4_l2_gap:
                        max_l4_l2_gap = gap

            obs_state = r.get("state_obs") or {}
            regime = obs_state.get("regime_synoptic") or "(none)"
            by_regime[regime].append(row)
            fc_state = r.get("state_fc") or {}
            oc = octant(fc_state.get("wind_dir"))
            if oc:
                by_octant[oc].append(row)

            # The honest "what did L6 actually do here" axis: signed applied Δ
            # = forecast_l6 - forecast_l2. Positive Δ = L6 warmed the forecast;
            # negative = L6 cooled it. Stratifying by this answers "when L6
            # adds warmth, does it land us closer to truth?" and likewise for
            # cooling — independent of what the OBSERVED regime label says,
            # since L6 keys on FORECAST regime at the projected hour.
            f6 = r.get("forecast_l6")
            if f2 is not None and f6 is not None:
                d = float(f6) - float(f2)
                # Buckets: large cool / mid cool / small / mid warm / large warm.
                if   d <= -2.0: bucket = "Δ ≤ -2.0  (large cool)"
                elif d <= -0.5: bucket = "-2.0 < Δ ≤ -0.5 (mid cool)"
                elif d <   0.5: bucket = "-0.5 < Δ < +0.5 (small)"
                elif d <   2.0: bucket = "+0.5 ≤ Δ < +2.0 (mid warm)"
                else:           bucket = "Δ ≥ +2.0  (large warm)"
                by_applied_delta[bucket].append(row)

    emit(f"Streamed {n_total:,} pair rows; kept {n_kept:,} with l1+l2+l6 all present.")
    emit("")

    def render_block(title, key_order, source):
        emit("-" * 92)
        emit(title)
        emit("-" * 92)
        emit(f"{'slice':<22} {'n':>7} {'ME L1':>8} {'ME L2':>8} {'ME L6':>8} "
             f"{'MAE L1':>8} {'MAE L2':>8} {'MAE L6':>8} {'L2 cov%':>9} {'L6 cov%':>9}")
        for key in key_order:
            rows = source.get(key, [])
            s = _stats(rows)
            if s is None:
                continue
            emit(f"{key:<22} {s['n']:>7,} {s['me1']:>+8.2f} {s['me2']:>+8.2f} {s['me6']:>+8.2f} "
                 f"{s['mae1']:>8.3f} {s['mae2']:>8.3f} {s['mae6']:>8.3f} "
                 f"{s['l2_cover_pct']:>+9.1f} {s['l6_cover_pct']:>+9.1f}")
        emit("")

    s = _stats(overall)
    if s is None:
        emit("No qualifying rows; aborting.")
    else:
        render_block("[HEADLINE] All L6-fired rows pooled", ["all"], {"all": overall})

        regime_keys = sorted(by_regime.keys(), key=lambda k: -len(by_regime[k]))
        render_block("[A] By state_obs.regime_synoptic (most-populated first)",
                     regime_keys, by_regime)

        render_block("[B] By state_fc wind octant (L6 lookup-table key)",
                     OCTANTS, by_octant)

        delta_order = [
            "Δ ≤ -2.0  (large cool)",
            "-2.0 < Δ ≤ -0.5 (mid cool)",
            "-0.5 < Δ < +0.5 (small)",
            "+0.5 ≤ Δ < +2.0 (mid warm)",
            "Δ ≥ +2.0  (large warm)",
        ]
        render_block("[C] By APPLIED Δ = forecast_l6 − forecast_l2 (what L6 actually did)",
                     delta_order, by_applied_delta)

        emit("-" * 92)
        emit("[D] Sanity: L2 vs L4 on T rows (T is not in L3_FIELDS or L4_FIELDS → should be identical)")
        emit("-" * 92)
        emit(f"  rows with both forecast_l2 and forecast_l4 present: {n_l4_present:,}")
        emit(f"    L4 == L2 (gap < 1e-6):  {n_l4_eq_l2:,}")
        emit(f"    L4 != L2:                {n_l4_neq_l2:,}    (max gap: {max_l4_l2_gap:.4f} °F)")
        emit("  → If n_l4_neq_l2 ≈ 0, comparing L6 against L2 is identical to comparing L6")
        emit("    against L4 — and the production audit's 'L4 vs L4+L6' framing IS a")
        emit("    'L2 vs L2+L6' comparison for temperature.")
        emit("")

        emit("=" * 92)
        emit("INTERPRETATION")
        emit("=" * 92)
        emit("Hypothesis confirmed if, on rows where L6 fires hard (e.g. SE/S octants,")
        emit("sea_breeze regime), L2-cover% is large (L2 already erased most of L1's MAE)")
        emit("AND L6-cover% is negative (adding L6's full Δ on top overshoots).")
        emit("")
        emit("If L2-cover% is small everywhere, the hypothesis is wrong — L6 is failing")
        emit("for some other reason (e.g. the lookup table itself is mis-tuned or stale).")
        emit("")
        emit("Next step regardless of outcome: rebuild the L6 lookup against post-L2")
        emit("forecasts (step 2 of the TODO in project_l6_l2_double_counting_hypothesis).")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
