"""Confound-check for the Stage 4 audit: is the calibrated-vs-recent MAE
drift really a calibration miss, or just weather-shift between the two
windows?

Motivating finding (2026-07-10, `production_trajectory_by_difficulty`):
Production %-vs-raw for L2-additive-bias fields (dp, h, ws, wg) is a
strong function of raw-MAE difficulty. On easy days (low raw MAE) the
correction overshoots; on hard days it hits the mark. If the Stage 4
calib window happens to be harder weather than the recent window, the
Production MAE drop reads as huge drift → FAIL — but nothing about
the calibration itself has changed; only the weather has.

Method:
  Same 7d calib + 7d recent windows as Stage 4. Same pair-log scan. For
  each (field, band, slot) legacy cell:
    - drift_prod = (recent_mae_prod  − calib_mae_prod) / calib_mae_prod
    - drift_raw  = (recent_mae_raw   − calib_mae_raw)  / calib_mae_raw
  Compare. If drift_raw and drift_prod are both large and in the same
  direction, the drift is a weather-shift confound. If raw is stable
  but Prod drifted, that's a real calibration miss and belongs in the
  Stage 4 FAIL bucket.

  Reports two new views:
    A) Per (field, band): raw drift, prod drift, ratio, verdict tag
    B) Aggregate confound-shift indicator: how much of the reported
       Stage 4 drift budget is likely weather-mixture

Not modifying c1_stage4_audit.py yet — this is a companion audit. Once we
trust the lens we can wire it into the Stage 4 verdict logic.

Output:
  Stdout + analysis/output/c1_stage4_difficulty_lens.txt

Run:
  python3 analysis/c1_stage4_difficulty_lens.py
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(os.path.dirname(__file__), "output",
                       "c1_stage4_difficulty_lens.txt")

RECENT_DAYS = 7
CALIB_DAYS  = 7
MIN_N_CELL  = 15
BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
FIELDS_L2_ADDITIVE = {"dp", "h", "ws", "wg"}  # noise-vs-signal starred

# Where the confound is a genuine risk vs. where we can trust drift as-is.
CONFOUND_RATIO_MIN = 0.5  # drift_prod / drift_raw < this → drift is prob weather
REAL_DRIFT_MIN    = 15.0  # abs(drift_prod%) below this → nothing to flag


def band_for_lead(lh):
    for label, lo, hi in BANDS:
        if lo <= lh < hi:
            return label
    return None


def main():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recent_start = now - timedelta(days=RECENT_DAYS)
    calib_end    = recent_start
    calib_start  = calib_end - timedelta(days=CALIB_DAYS)

    print(f"Stage 4 difficulty-confound lens")
    print(f"  calib  window: {calib_start.date()} → {calib_end.date()}")
    print(f"  recent window: {recent_start.date()} → {now.date()}")
    print()

    # (field, band, slot, window) → [n, sum_abs_err_prod, sum_abs_err_raw]
    accs = defaultdict(lambda: [0, 0.0, 0.0])
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            field = r.get("field")
            if not field:
                continue
            obs_t = r.get("obs_time")
            if not obs_t:
                continue
            try:
                dt = datetime.strptime(obs_t[:16], "%Y-%m-%dT%H:%M")
            except ValueError:
                continue
            if dt < calib_start:
                continue
            if dt >= now:
                continue
            window = "recent" if dt >= recent_start else "calib"
            band = band_for_lead(r.get("lead_h") or -1)
            if band is None:
                continue
            sfc = r.get("state_fc") or {}
            sob = r.get("state_obs") or {}
            rfc = sfc.get("regime_synoptic")
            rob = sob.get("regime_synoptic")
            if not rfc or not rob:
                continue
            slot = "transition" if rfc != rob else "stable"
            fc_l1 = r.get("forecast_l1")
            fc_prod = (r.get("forecast_l4") or r.get("forecast_l3")
                       or r.get("forecast_l2") or fc_l1 or r.get("forecast"))
            obs = r.get("observed")
            if fc_l1 is None or fc_prod is None or obs is None:
                continue
            try:
                err_prod = abs(float(fc_prod) - float(obs))
                err_raw  = abs(float(fc_l1) - float(obs))
            except (TypeError, ValueError):
                continue
            key = (field, band, slot, window)
            a = accs[key]
            a[0] += 1
            a[1] += err_prod
            a[2] += err_raw

    # Reduce to per (field, band, slot) view with both windows joined
    per_cell = defaultdict(dict)
    for (field, band, slot, window), (n, ep, er) in accs.items():
        per_cell[(field, band, slot)][window] = (n, ep / n if n else 0.0, er / n if n else 0.0)

    out_lines = []
    def emit(s):
        print(s); out_lines.append(s)

    emit(f"Per-cell drift comparison (Production MAE drift vs Raw MAE drift)")
    emit(f"  drift = (recent - calib) / calib × 100")
    emit(f"  ratio = drift_prod / drift_raw  — near 1 means both moved together (weather confound)")
    emit(f"                                    — far from 1 means Production moved independently (real drift)")
    emit(f"  ★ = L2-additive-bias field (dp/h/ws/wg) — most vulnerable to this confound")
    emit("")
    emit(f"  {'field':<5} {'band':<8} {'slot':<11} {'n_c':>5} {'n_r':>5}   "
         f"{'MAE_raw calib→recent':>24}   {'MAE_prod calib→recent':>24}   "
         f"{'drift_raw%':>10} {'drift_prod%':>11} {'ratio':>7}  tag")
    emit("  " + "-" * 130)

    tags = defaultdict(int)
    for key in sorted(per_cell.keys()):
        (field, band, slot) = key
        rec = per_cell[key]
        c = rec.get("calib")
        r = rec.get("recent")
        if not c or not r or c[0] < MIN_N_CELL or r[0] < MIN_N_CELL:
            continue
        _, mp_c, mr_c = c
        _, mp_r, mr_r = r
        if mp_c == 0 or mr_c == 0:
            continue
        drift_prod = (mp_r - mp_c) / mp_c * 100
        drift_raw  = (mr_r - mr_c) / mr_c * 100
        if drift_raw != 0:
            ratio = drift_prod / drift_raw
        else:
            ratio = float("nan")
        # Tag
        if abs(drift_prod) < REAL_DRIFT_MIN:
            tag = "small — ignore"
        elif drift_raw != 0 and abs(ratio - 1) < 0.35:
            tag = "★ weather-confound" if field in FIELDS_L2_ADDITIVE else "weather-confound"
        elif drift_raw != 0 and (ratio < CONFOUND_RATIO_MIN or ratio > 1.7):
            tag = "★ REAL DRIFT" if field in FIELDS_L2_ADDITIVE else "REAL DRIFT"
        else:
            tag = "review"
        tags[tag] += 1
        star = "★" if field in FIELDS_L2_ADDITIVE else " "
        emit(f"  {star}{field:<4} {band:<8} {slot:<11} {c[0]:>5,} {r[0]:>5,}   "
             f"{mr_c:>10.3f} → {mr_r:>10.3f}   "
             f"{mp_c:>10.3f} → {mp_r:>10.3f}   "
             f"{drift_raw:>+10.1f} {drift_prod:>+11.1f} {ratio:>+7.2f}  {tag}")

    emit("")
    emit("Tag counts:")
    for t, n in sorted(tags.items(), key=lambda x: -x[1]):
        emit(f"  {t}: {n}")

    # Aggregate confound share
    emit("")
    emit(f"Interpretation:")
    weather_n = tags.get("weather-confound", 0) + tags.get("★ weather-confound", 0)
    real_n = tags.get("REAL DRIFT", 0) + tags.get("★ REAL DRIFT", 0)
    small_n = tags.get("small — ignore", 0)
    review_n = tags.get("review", 0)
    total = weather_n + real_n + small_n + review_n
    if total > 0:
        emit(f"  {weather_n}/{total} cells are weather-confound (Prod and Raw drifted together).")
        emit(f"  {real_n}/{total} cells are REAL DRIFT (Prod moved independently of Raw) — these belong in Stage 4 FAIL.")
        emit(f"  {small_n}/{total} cells have small Production drift ({REAL_DRIFT_MIN}% threshold), safe to ignore.")
        emit(f"  {review_n}/{total} cells are ambiguous, review manually.")
        if weather_n > real_n:
            emit(f"  → Stage 4 FAIL count is likely INFLATED by weather-mixture shift between the calib and recent windows.")
            emit(f"  → Adjusted FAIL count (only REAL DRIFT): {real_n}. Compare to Stage 4's own tally.")

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(out_lines) + "\n")
    print(f"\nwrote {OUT_TXT}")


if __name__ == "__main__":
    main()
