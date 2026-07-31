"""wd L2 blend — how often does it actually fire, and does it help when it does?

Context:
  wd L2 blend shipped 2026-07-20 v0.6.368a (wind_blend.py, circular unit-vector,
  BLEND_HOURS=24, calm-floor 3 mph). First-tick verify at 07-20 15:08 reported
  lead-0 MAE −35% (42.7° → 27.7°). But 2026-07-29 persistence-skill scorecard
  shows L1 → L4 delta of only ~0.08° at 0-5h (50.91° → 50.83°) — the aggregate
  effect has vanished.

  Two hypotheses:
    A. Blend gates out too often (calm-floor triggering; obs missing) — fixable
    B. Blend fires nearly always but doesn't help on aggregate — kill/rethink

Method:
  Stream pair log, wd rows only. Per row: is forecast_l2 ≠ forecast_l1? (fired)
  For fired vs skipped subsets, compute angular MAE vs persistence baseline.
  Report per-band fire rate + conditional MAE, with the wd-specific circular
  angular_diff metric (0-180) used everywhere else for wd.

  Verdict:
    fire_rate < 40%  → Hypothesis A. Blend gates out too often. Fix calm-floor.
    fire_rate 40-70% AND fired-subset skill vs L1 > 5% → Blend helps when it fires;
                        gating is over-aggressive; loosening would recover value.
    fire_rate > 70%  AND fired-subset skill ≈ 0 → Hypothesis B. Blend doesn't
                        help. Kill or restrict to lead 0 only.
"""
import os
import sys
import json
import math
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "output", "h_wd_l2_fire_rate.txt")

FIELD = "wd"
BANDS = [(0, 6, "0-5h"), (6, 12, "6-11h"), (12, 24, "12-23h"), (24, 48, "24-47h")]
MIN_N = 100  # lowered because post-fix window is only days old

# v0.6.384 (2026-07-28) shrank wind_blend BLEND_HOURS 24 → 4. This affects wd
# collaterally (single shared loop). Pre-fix rows show blend firing at leads
# 0-23; post-fix only 0-3. Report BOTH windows so we can see the fix land.
POST_FIX_CUTOFF_ISO = "2026-07-28T00:00"


def angular_diff(a, b):
    d = abs(float(a) - float(b)) % 360.0
    return d if d <= 180.0 else 360.0 - d


def band_of(lead):
    for lo, hi, lab in BANDS:
        if lo <= lead < hi:
            return lab
    return None


def hour_floor(ts):
    if ts is None or len(ts) < 16:
        return None
    return ts[:14] + "00"


def main():
    path = cached_path(URL)

    # Pass 1: obs index
    obs_ts = {}
    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            vt = r.get("valid_time")
            ob = r.get("observed")
            if vt is not None and ob is not None and vt not in obs_ts:
                obs_ts[vt] = float(ob)

    # Pass 2: accumulate per (window, band), split fired vs skipped
    # window = "pre_fix" (obs_time < POST_FIX_CUTOFF_ISO) or "post_fix"
    def zeros():
        return {"n": 0,
                "n_fired": 0,
                "ae_l1_all": 0.0,   "ae_l2_all": 0.0,   "ae_pers_all": 0.0,
                "ae_l1_fired": 0.0, "ae_l2_fired": 0.0, "ae_pers_fired": 0.0,
                "ae_l1_skipped": 0.0, "ae_pers_skipped": 0.0, "n_skipped": 0}
    accum = defaultdict(zeros)  # keyed by (window, band)

    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            lead = r.get("lead_h")
            if lead is None:
                continue
            try:
                lead = int(lead)
            except Exception:
                continue
            if lead < 0 or lead > 47:
                continue
            band = band_of(lead)
            if band is None:
                continue
            rt = r.get("run_time")
            ob = r.get("observed")
            f_l1 = r.get("forecast_l1")
            f_l2 = r.get("forecast_l2")
            if rt is None or ob is None or f_l1 is None:
                continue
            if f_l2 is None:
                f_l2 = f_l1
            persist = obs_ts.get(hour_floor(rt))
            if persist is None:
                continue

            obs_time = r.get("obs_time") or r.get("valid_time") or ""
            window = "post_fix" if obs_time >= POST_FIX_CUTOFF_ISO else "pre_fix"

            ob = float(ob)
            f_l1 = float(f_l1)
            f_l2 = float(f_l2)
            persist = float(persist)

            e_l1 = angular_diff(f_l1, ob)
            e_l2 = angular_diff(f_l2, ob)
            e_pers = angular_diff(persist, ob)

            a = accum[(window, band)]
            a["n"] += 1
            a["ae_l1_all"] += e_l1
            a["ae_l2_all"] += e_l2
            a["ae_pers_all"] += e_pers

            fired = angular_diff(f_l1, f_l2) > 0.5  # blend moved wd ≥0.5°
            if fired:
                a["n_fired"] += 1
                a["ae_l1_fired"] += e_l1
                a["ae_l2_fired"] += e_l2
                a["ae_pers_fired"] += e_pers
            else:
                a["n_skipped"] += 1
                a["ae_l1_skipped"] += e_l1
                a["ae_pers_skipped"] += e_pers

    # Reduce + emit
    lines = []

    def w(s=""):
        print(s)
        lines.append(s)

    w("=" * 96)
    w("wd L2 blend — fire rate + conditional MAE (fired vs skipped subsets)")
    w("=" * 96)
    w("")
    w("Question: is the vanishing aggregate effect because the blend rarely fires,")
    w("or because when it fires it doesn't help? All errors are circular angular_diff")
    w("(0-180°).")
    w("")
    def render_window(window_label, window_key):
        w("")
        w(f"[{window_label}] (obs_time {'<' if window_key == 'pre_fix' else '>='} "
          f"{POST_FIX_CUTOFF_ISO})")
        w(f"{'band':<8}{'n':>8}{'n_fired':>10}{'fire%':>8}"
          f"{'MAE_L1_all':>12}{'MAE_L2_all':>12}{'MAE_pers':>10}"
          f"{'MAE_L1_fired':>14}{'MAE_L2_fired':>14}"
          f"{'MAE_L1_skip':>13}")
        w("-" * 129)
        stories = []
        for _, _, band in BANDS:
            a = accum.get((window_key, band))
            if not a or a["n"] < MIN_N:
                w(f"{band:<8}{(a['n'] if a else 0):>8,}   (n < {MIN_N}, skipped)")
                continue
            n = a["n"]
            nf = a["n_fired"]
            ns = a["n_skipped"]
            fire_pct = 100.0 * nf / n
            mae_l1 = a["ae_l1_all"] / n
            mae_l2 = a["ae_l2_all"] / n
            mae_p = a["ae_pers_all"] / n
            mae_l1_f = (a["ae_l1_fired"] / nf) if nf else 0
            mae_l2_f = (a["ae_l2_fired"] / nf) if nf else 0
            mae_l1_s = (a["ae_l1_skipped"] / ns) if ns else 0
            w(f"{band:<8}{n:>8,}{nf:>10,}{fire_pct:>7.1f}%"
              f"{mae_l1:>12.2f}{mae_l2:>12.2f}{mae_p:>10.2f}"
              f"{mae_l1_f:>14.2f}{mae_l2_f:>14.2f}"
              f"{mae_l1_s:>13.2f}")
            if not nf:
                stories.append(f"{band}: never fires (correct if band ≥ BLEND_HOURS)")
                continue
            conditional_delta = mae_l1_f - mae_l2_f
            conditional_skill = (conditional_delta / mae_l1_f * 100) if mae_l1_f > 0 else 0
            if fire_pct < 40:
                tag = "★ GATES OUT TOO OFTEN"
            elif conditional_skill > 5:
                tag = "★ HELPS WHEN FIRES"
            elif abs(conditional_skill) < 2:
                tag = "☠ FIRES BUT DOESN'T HELP"
            elif conditional_skill < -5:
                tag = "☠ FIRES BUT HURTS"
            else:
                tag = "marginal"
            stories.append(
                f"{band}: fire {fire_pct:.0f}%, Δ_L2vsL1 {conditional_delta:+.2f}° "
                f"({conditional_skill:+.1f}%) — {tag}"
            )
        return stories

    pre_stories = render_window("PRE-FIX (v0.6.384-)  — BLEND_HOURS=24 era",  "pre_fix")
    post_stories = render_window("POST-FIX (v0.6.384+) — BLEND_HOURS=4 era",   "post_fix")

    w("")
    w("=" * 96)
    w("VERDICT")
    w("=" * 96)
    w("PRE-FIX (fossil, aging out):")
    for s in pre_stories:
        w("  " + s)
    w("")
    w("POST-FIX (fresh, this is what production is doing):")
    for s in post_stories:
        w("  " + s)
    w("")
    if post_stories:
        w("Verdict: post-fix — " + " | ".join(post_stories)[:180] + ".")
    else:
        w("Verdict: post-fix window too thin (min n={MIN_N}) — re-run in a few days.")

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
