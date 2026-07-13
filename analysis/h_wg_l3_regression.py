"""
wg L3 regression diagnostic — Stage 0 follow-up to the v0.6.336 finding
that wg pooled Production persistence skill is −0.09 vs L4-alone (which
is where wg would sit if L3 didn't fire) at +0.10 — a 19pp drop across
the L3 step.

Question: which (regime × lead_band) cells account for L3's drag on wg
persistence skill? Same "gate ON where it wins, OFF elsewhere — ship"
frame as ch persistence gate — if the loss concentrates in a handful of
cells, the fix is a skip-table extension, not a full L3 drop.

For each pair row with field=='wg':
  persistence = obs at forecast issue time (run_time hour-floor from same
                obs series the pair log carries)
  L2 forecast = forecast_l2 (pre-L3, present when snapshot writer captured it)
  L3 forecast = forecast_l3, else fall back to top-level `forecast`

Emits MAE_persist / MAE_L2 / MAE_L3 per (regime × lead_band) cell + verdict.

Verdict rule per cell (n ≥ 500):
  L3 HURTS     L3 MAE > L2 MAE by ≥3% AND L2 MAE < persistence MAE
               (removing L3 in this cell would improve; L2 already beats persistence)
  L3 HELPS     L3 MAE < L2 MAE by ≥3%
  FLAT         |Δ| < 3%

Then rollup: how much of the pooled Production drag is concentrated
in the L3 HURTS cells?

Run:
    python3 analysis/h_wg_l3_regression.py

Output:
    analysis/output/h_wg_l3_regression.txt
    analysis/output/h_wg_l3_regression.json
"""
import json
import math
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_wg_l3_regression.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_wg_l3_regression.json")

BANDS = [
    ("0-5h",   1, 5),
    ("6-11h",  6, 11),
    ("12-23h", 12, 23),
    ("24-47h", 24, 47),
]
REGIMES = ["nw_flow", "se_flow", "sw_flow", "pre_frontal", "sea_breeze",
           "ne_flow", "calm", "frontal", "unknown"]

MIN_N_PER_CELL = 500
DELTA_ACT_PCT = 3.0  # cell verdict threshold


def band_of(lead):
    for name, lo, hi in BANDS:
        if lo <= lead <= hi:
            return name
    return None


def hour_floor(ts):
    if ts is None or len(ts) < 16:
        return None
    return ts[:14] + "00"


def compute():
    # Pass 1: obs index for wg persistence baseline
    obs_ts = {}
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != "wg":
                continue
            vt = r.get("valid_time")
            ob = r.get("observed")
            if vt is None or ob is None:
                continue
            if vt not in obs_ts:
                obs_ts[vt] = float(ob)

    # Pass 2: bucket by (regime × band)
    cells = defaultdict(lambda: {"n": 0,
                                 "ae_pers": 0.0, "ae_l2": 0.0, "ae_l3": 0.0,
                                 "se_pers": 0.0, "se_l2": 0.0, "se_l3": 0.0,
                                 "n_l2_missing": 0})
    n_scanned = n_joined = 0
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != "wg":
                continue
            n_scanned += 1
            lead = r.get("lead_h")
            if lead is None:
                continue
            band = band_of(int(lead))
            if band is None:
                continue
            rt = r.get("run_time")
            ob = r.get("observed")
            if rt is None or ob is None:
                continue
            fc = r.get("forecast")
            fc_l2 = r.get("forecast_l2")
            fc_l3 = r.get("forecast_l3")
            if fc is None:
                continue
            # If forecast_l3 missing (pre-v0.6.25 snapshot), the top-level
            # forecast IS L3 for wg (wg is in L3_FIELDS since v0.6.44).
            if fc_l3 is None:
                fc_l3 = fc
            # If forecast_l2 missing, skip the row for the L2 baseline —
            # we can't measure L3's contribution without it.
            fc_state = r.get("state_fc") or {}
            regime = fc_state.get("regime_synoptic") or "unknown"
            persist = obs_ts.get(hour_floor(rt))
            if persist is None:
                continue
            n_joined += 1
            ob_f = float(ob)
            e_p = persist - ob_f
            e_3 = float(fc_l3) - ob_f
            c = cells[(regime, band)]
            c["n"] += 1
            c["ae_pers"] += abs(e_p)
            c["se_pers"] += e_p * e_p
            c["ae_l3"]   += abs(e_3)
            c["se_l3"]   += e_3 * e_3
            if fc_l2 is None:
                c["n_l2_missing"] += 1
                continue
            e_2 = float(fc_l2) - ob_f
            c["ae_l2"] += abs(e_2)
            c["se_l2"] += e_2 * e_2

    return cells, n_scanned, n_joined


def emit(cells, n_scanned, n_joined):
    lines = []
    lines.append("=" * 100)
    lines.append("wg L3 REGRESSION DIAGNOSTIC — per (regime × lead_band)")
    lines.append("=" * 100)
    lines.append(f"Scanned {n_scanned:,} wg pairs; joined {n_joined:,} to persistence baseline.")
    lines.append("MAE_L2 = pipeline pre-L3 (from forecast_l2). MAE_L3 = post-L3 Production (from forecast_l3).")
    lines.append("skill = 1 − MAE_layer / MAE_persistence. Positive = layer beats persistence.")
    lines.append(f"Verdict per cell (n ≥ {MIN_N_PER_CELL}):")
    lines.append(f"  L3 HURTS ★  MAE_L3 > MAE_L2 by ≥{DELTA_ACT_PCT:.0f}% AND L2 already beats persistence")
    lines.append(f"  L3 HELPS    MAE_L3 < MAE_L2 by ≥{DELTA_ACT_PCT:.0f}%")
    lines.append(f"  FLAT        |Δ| < {DELTA_ACT_PCT:.0f}%")
    lines.append(f"  THIN        n < {MIN_N_PER_CELL}")
    lines.append("")

    hdr = (f"{'regime':<14}{'band':<8}{'n':>8}{'MAE_p':>8}{'MAE_L2':>9}"
           f"{'MAE_L3':>9}{'skill_L2':>10}{'skill_L3':>10}{'Δ_L3vL2%':>11}  verdict")
    lines.append(hdr)
    lines.append("-" * len(hdr))

    verdicts = {}
    hurts_impact = 0.0  # sum n × Δ(L3−L2) across HURT cells
    for regime in REGIMES:
        for band_name, _, _ in BANDS:
            c = cells.get((regime, band_name))
            if not c or c["n"] < MIN_N_PER_CELL:
                verdicts[(regime, band_name)] = "THIN"
                continue
            n = c["n"]
            # L2 stats require rows where fc_l2 was present
            n_l2 = n - c["n_l2_missing"]
            mae_p = c["ae_pers"] / n
            mae_l3 = c["ae_l3"] / n
            skill_l3 = 1 - mae_l3 / mae_p if mae_p > 0 else None
            if n_l2 < MIN_N_PER_CELL:
                # L3 present but L2 not — can't judge L3-vs-L2
                lines.append(
                    f"{regime:<14}{band_name:<8}{n:>8,}{mae_p:>8.3f}{'--':>9}"
                    f"{mae_l3:>9.3f}{'--':>10}"
                    f"{skill_l3 if skill_l3 is not None else 0:>+10.3f}"
                    f"{'--':>11}  L2 THIN"
                )
                verdicts[(regime, band_name)] = "L2_THIN"
                continue
            mae_l2 = c["ae_l2"] / n_l2
            skill_l2 = 1 - mae_l2 / mae_p if mae_p > 0 else None
            d_l3_l2_pct = (mae_l3 - mae_l2) / mae_l2 * 100 if mae_l2 > 0 else 0.0
            if d_l3_l2_pct >= DELTA_ACT_PCT and (skill_l2 or 0) > 0:
                v = "L3 HURTS ★"
                hurts_impact += n_l2 * (mae_l3 - mae_l2)
            elif d_l3_l2_pct <= -DELTA_ACT_PCT:
                v = "L3 HELPS"
            elif d_l3_l2_pct >= DELTA_ACT_PCT:
                v = "L3 HURTS (persist ≤ L2)"
            else:
                v = "FLAT"
            verdicts[(regime, band_name)] = v
            lines.append(
                f"{regime:<14}{band_name:<8}{n:>8,}{mae_p:>8.3f}{mae_l2:>9.3f}"
                f"{mae_l3:>9.3f}{skill_l2 if skill_l2 is not None else 0:>+10.3f}"
                f"{skill_l3 if skill_l3 is not None else 0:>+10.3f}"
                f"{d_l3_l2_pct:>+11.2f}  {v}"
            )
        lines.append("")

    n_hurts = sum(1 for v in verdicts.values() if v.startswith("L3 HURTS"))
    n_helps = sum(1 for v in verdicts.values() if v == "L3 HELPS")
    n_flat  = sum(1 for v in verdicts.values() if v == "FLAT")
    n_thin  = sum(1 for v in verdicts.values() if v in ("THIN", "L2_THIN"))

    lines.append("=" * 100)
    lines.append(f"ROLLUP: {n_hurts} HURTS · {n_helps} HELPS · {n_flat} FLAT · {n_thin} THIN")
    if n_hurts:
        hurts_cells = sorted(
            [(cell, v) for cell, v in verdicts.items() if v.startswith("L3 HURTS")],
            key=lambda x: x[0]
        )
        for (regime, band), _v in hurts_cells:
            c = cells[(regime, band)]
            n_l2 = c["n"] - c["n_l2_missing"]
            mae_l2 = c["ae_l2"] / n_l2
            mae_l3 = c["ae_l3"] / c["n"]
            lines.append(f"  · {regime}/{band}: L2 MAE {mae_l2:.3f} → L3 MAE {mae_l3:.3f} "
                         f"(+{(mae_l3 - mae_l2) / mae_l2 * 100:.1f}%, n≥{n_l2:,})")
    lines.append("")

    if n_hurts >= 1:
        lines.append(f"Verdict: wg L3 REGRESSES in {n_hurts} cell(s) — candidate for SKIP_TABLE "
                     f"extension. Fits the same skip-table architecture as ws L3.")
    elif n_helps > n_thin:
        lines.append("Verdict: wg L3 nets positive per-cell — the pooled persistence-skill "
                     "loss must come from cells where BOTH L2 and L3 lose to persistence "
                     "(persistence dominates the regime, both layers irrelevant).")
    else:
        lines.append("Verdict: FLAT / THIN — no per-cell action. Re-run with more data.")

    return "\n".join(lines), verdicts


def main():
    cells, n_scanned, n_joined = compute()
    text, verdicts = emit(cells, n_scanned, n_joined)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")

    # JSON payload
    per_cell_out = {}
    for (regime, band), c in cells.items():
        if c["n"] < 30:
            continue
        n_l2 = c["n"] - c["n_l2_missing"]
        per_cell_out[f"{regime}/{band}"] = {
            "n": c["n"],
            "n_l2": n_l2,
            "mae_persist": round(c["ae_pers"] / c["n"], 4),
            "mae_l2": round(c["ae_l2"] / n_l2, 4) if n_l2 > 0 else None,
            "mae_l3": round(c["ae_l3"] / c["n"], 4),
            "verdict": verdicts.get((regime, band), "?"),
        }
    from datetime import datetime as _dt, timezone as _tz
    payload = {
        "generated_at": _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "forecast_error_log.jsonl (field=wg)",
        "min_n_per_cell": MIN_N_PER_CELL,
        "delta_act_pct": DELTA_ACT_PCT,
        "cells": per_cell_out,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
