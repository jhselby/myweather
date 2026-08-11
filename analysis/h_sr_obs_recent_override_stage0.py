"""Stage 0 — sr obs-recent override (backlog #8, 08-11).

Motivated by Joe's 08-11 observation: sr 24h rolling MAE shows a sawtooth
(worse in morning, recovers in afternoon) driven by 1-2 outlier hours per
day where fc cloud cover is very wrong. Examples 08-10 pre_frontal:
  07:00 (fc=1144, obs=502)   over-forecast by 642 W/m²
  08:00 (fc=2, obs=649)      under-forecast by 647
  10:00 (fc=0, obs=796)      under-forecast by 796

Hypothesis 8a from the backlog: when the previous-hour observed sr
disagrees with the current fc sr by a lot, prefer obs.  Blanket
persistence would be terrible (sr swings hard through dawn/dusk), so
this is a GATED override — only fire when disagreement exceeds
threshold and hour-of-day is in the flat-midday band where obs_prev
is a reasonable proxy.

Method:
  1. Build dict[vt → obs_sr] from pair log rows in window.
  2. For each pair-log row (sr, lead ≤ LEAD_MAX):
       - obs_prev = dict[vt − 1h]  (skip if absent)
       - baseline_err = |fc − obs|
       - if fc-vs-obs_prev disagreement > TRIGGER and hour_local ∈ MIDDAY:
             override_fc = obs_prev
         else:
             override_fc = fc
       - override_err = |override_fc − obs|
  3. Split train (older) / test (last 7d). Report MAE lift on test.

Blockers per backlog:
  (a) verify sawtooth persists ≥7 days (test window is 7d)
  (b) verify fault mode is symmetric (both fc-high-obs-low AND fc-low-obs-high)
  (c) confirm Lsb non-overlap — Lsb only fires on sea_breeze + cc<25, so
      report override fire count inside vs outside that slice separately.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402
from _windows import rolling_windows  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_sr_obs_recent_override_stage0.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_sr_obs_recent_override_stage0.json")

WINDOW_DAYS = 21
HELD_OUT_DAYS = 7
LEAD_MAX = 6
TRIGGER_DELTA = 200.0        # |fc - obs_prev| threshold to fire override
MIDDAY_LOCAL_HOURS = set(range(10, 15))  # 10-14 EDT local
LOCAL_UTC_OFFSET_H = 4       # EDT
STAGE0_LIFT_PCT = 5.0        # test MAE lift threshold to declare HIT


def _local_hour(iso_utc):
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "").replace("+00:00", "")[:19])
    except Exception:
        return None
    return (dt - timedelta(hours=LOCAL_UTC_OFFSET_H)).hour


def _vt_minus_1h(vt):
    try:
        dt = datetime.fromisoformat(vt.replace("Z", "").replace("+00:00", "")[:19])
    except Exception:
        return None
    return (dt - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")


def main():
    WIN = rolling_windows(recent_days=WINDOW_DAYS, prior_days=0)
    lo_win, hi_win = WIN.A_LO, WIN.A_HI

    obs_sr_by_vt = {}
    rows = []
    n_scanned = 0
    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            n_scanned += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != "sr":
                continue
            vt = r.get("valid_time") or ""
            if vt < lo_win or vt >= hi_win:
                continue
            obs = r.get("observed")
            fc = (r.get("forecast_l4") or r.get("forecast_l3")
                  or r.get("forecast_l2") or r.get("forecast_l1")
                  or r.get("forecast"))
            lh = r.get("lead_h")
            if obs is None or fc is None or lh is None:
                continue
            obs = float(obs)
            fc = float(fc)
            # Populate the vt→obs map (first observation per vt wins).
            key = vt[:16]
            if key not in obs_sr_by_vt:
                obs_sr_by_vt[key] = obs
            if lh > LEAD_MAX:
                continue
            sfc = r.get("state_fc") or {}
            regime = sfc.get("regime_synoptic")
            cc_fc = sfc.get("cloud_cover")
            rows.append({
                "vt": vt,
                "vt_key": key,
                "lh": lh,
                "obs": obs,
                "fc": fc,
                "local_hour": _local_hour(vt),
                "regime": regime,
                "cc_fc": cc_fc,
            })

    if not rows:
        print("VERDICT: INSUFFICIENT DATA — no sr rows in window.")
        return 0

    max_vt = max(r["vt"] for r in rows)
    max_date = datetime.strptime(max_vt[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    # Score each row
    per_row = []
    for r in rows:
        prev_key = _vt_minus_1h(r["vt"])
        obs_prev = obs_sr_by_vt.get(prev_key) if prev_key else None
        baseline_err = abs(r["fc"] - r["obs"])
        override_err = baseline_err
        fired = False
        if obs_prev is not None and r["local_hour"] in MIDDAY_LOCAL_HOURS:
            if abs(r["fc"] - obs_prev) > TRIGGER_DELTA:
                fired = True
                override_err = abs(obs_prev - r["obs"])
        in_lsb = (r["regime"] == "sea_breeze"
                  and r["cc_fc"] is not None and r["cc_fc"] < 25)
        per_row.append({
            "obs_time_prefix": r["vt"][:10],
            "baseline_err": baseline_err,
            "override_err": override_err,
            "fired": fired,
            "in_lsb": in_lsb,
        })

    train = [p for p in per_row if p["obs_time_prefix"] < test_start]
    test = [p for p in per_row if p["obs_time_prefix"] >= test_start]

    def summarize(subset, label):
        n = len(subset)
        n_fired = sum(1 for p in subset if p["fired"])
        n_lsb_fired = sum(1 for p in subset if p["fired"] and p["in_lsb"])
        n_nonlsb_fired = n_fired - n_lsb_fired
        base_mae = mean(p["baseline_err"] for p in subset) if subset else 0
        over_mae = mean(p["override_err"] for p in subset) if subset else 0
        base_fired = mean(p["baseline_err"] for p in subset if p["fired"]) if n_fired else 0
        over_fired = mean(p["override_err"] for p in subset if p["fired"]) if n_fired else 0
        lift = base_mae - over_mae
        lift_pct = 100 * lift / base_mae if base_mae > 0 else 0
        fired_lift = base_fired - over_fired
        fired_lift_pct = 100 * fired_lift / base_fired if base_fired > 0 else 0
        return {
            "label": label, "n": n, "n_fired": n_fired,
            "n_lsb_fired": n_lsb_fired, "n_nonlsb_fired": n_nonlsb_fired,
            "base_mae": base_mae, "over_mae": over_mae,
            "lift": lift, "lift_pct": lift_pct,
            "base_fired": base_fired, "over_fired": over_fired,
            "fired_lift": fired_lift, "fired_lift_pct": fired_lift_pct,
        }

    train_s = summarize(train, "TRAIN")
    test_s = summarize(test, "TEST")

    lines = []
    lines.append("=" * 100)
    lines.append("STAGE 0 — sr obs-recent override (gated at |fc − obs_prev| > 200 W/m², midday 10-14 EDT)")
    lines.append("=" * 100)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Held-out (test): last {HELD_OUT_DAYS}d.  "
                 f"Lead cap: {LEAD_MAX}h.")
    lines.append(f"Trigger: |fc − obs_prev| > {TRIGGER_DELTA:.0f} W/m² AND local hour ∈ {sorted(MIDDAY_LOCAL_HOURS)}.")
    lines.append(f"Test starts: {test_start}   Scanned {n_scanned:,} pair-log rows.")
    lines.append("")

    for s in (train_s, test_s):
        lines.append(f"[{s['label']}]  n={s['n']:,}  fired={s['n_fired']}  "
                     f"(non-Lsb fires={s['n_nonlsb_fired']}, Lsb-overlap fires={s['n_lsb_fired']})")
        lines.append(f"  pooled:  baseline MAE={s['base_mae']:.2f}  override MAE={s['over_mae']:.2f}  "
                     f"lift={s['lift']:+.2f} ({s['lift_pct']:+.2f}%)")
        if s["n_fired"]:
            lines.append(f"  on fired subset only:  baseline={s['base_fired']:.2f}  "
                         f"override={s['over_fired']:.2f}  lift={s['fired_lift']:+.2f} "
                         f"({s['fired_lift_pct']:+.2f}%)")
        lines.append("")

    ok = test_s["lift_pct"] >= STAGE0_LIFT_PCT and test_s["n_fired"] >= 10
    non_lsb_frac = (test_s["n_nonlsb_fired"] / test_s["n_fired"]
                    if test_s["n_fired"] else 0)
    lsb_overlap_warning = non_lsb_frac < 0.5 and test_s["n_fired"] >= 10

    if ok and not lsb_overlap_warning:
        lines.append(f"VERDICT: STAGE 0 HIT — held-out pooled lift {test_s['lift_pct']:+.2f}% "
                     f"clears {STAGE0_LIFT_PCT}% gate on {test_s['n_fired']} fires "
                     f"({test_s['n_nonlsb_fired']} outside Lsb slice). Warrants Stage 1 — a "
                     f"proper obs-recent override specialist with tuned trigger threshold.")
    elif ok and lsb_overlap_warning:
        lines.append(f"VERDICT: HIT BUT LSB-COLLAPSED — {test_s['n_lsb_fired']}/{test_s['n_fired']} "
                     f"fires ({100*(1-non_lsb_frac):.0f}%) fall inside the Lsb slice. Signal "
                     f"is largely Lsb in disguise. Do NOT scope a new specialist.")
    elif test_s["n_fired"] < 10:
        lines.append(f"VERDICT: THIN — only {test_s['n_fired']} fires on held-out. Trigger too strict "
                     f"or the disagreement pattern is rare in the test window.")
    else:
        lines.append(f"VERDICT: NO HIT — held-out lift {test_s['lift_pct']:+.2f}% below {STAGE0_LIFT_PCT}% "
                     f"gate. Naive override (fc := obs_prev) doesn't beat baseline enough to "
                     f"justify scoping a specialist.")

    text = "\n".join(lines)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump({
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_lo": lo_win,
            "window_hi": hi_win,
            "test_start": test_start,
            "train": train_s,
            "test": test_s,
        }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
