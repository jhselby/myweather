"""Stage 2 preview — wd persistence gate with predicted-transition fire signal.

Stage 1 (h_wd_persistence_gate_stage1.py) established:
  * pooled per-cell: 4 SHIP cells for a plain (regime × band) gate
  * transition-vs-stable split reveals persistence beats L1 by 13-38% on
    transition rows across se_flow, sw_flow, sea_breeze, all bands — where
    "transition" = state_fc.regime != state_obs.regime (post-facto).

Stage 1's "transition" label is not knowable at forecast time. Stage 2
tests a proxy signal that IS knowable at forecast issue:

    state_curr.regime  = observed regime at hour_floor(run_time)
    state_fc.regime    = model-predicted regime at valid_time
    transition_risk    = (state_curr != state_fc) for this specific lead

Fire condition: if transition_risk is True for this (lead), use persistence
of the wd obs at forecast issue. Otherwise use L1.

Two things being tested:
  1. Does the predicted-transition signal correlate well enough with actual
     transitions to be actionable? (Diagnostic joint table.)
  2. On rows where the fire condition triggers, does the intervention beat
     L1 per (state_fc.regime, band)? Halves-stable? (Per-cell verdict.)

state_curr construction: build obs_regime_index[valid_time] = regime seen
in the shortest-lead pair's state_obs for that valid_time. Then for a pair
with run_time RT, state_curr = obs_regime_index[hour_floor(RT)].

Emits:
  analysis/output/h_wd_persistence_gate_stage2.txt
  weather_collector/data/wd_persistence_gate_curated.json  (overwrites Stage 1
    preview with the transition-signal-conditioned SHIP list)
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_TXT = os.path.join(HERE, "output", "h_wd_persistence_gate_stage2.txt")
OUT_JSON = os.path.abspath(os.path.join(
    HERE, "..", "weather_collector", "data", "wd_persistence_gate_curated.json"
))

WIN_A_LO, WIN_A_HI = "2026-07-04T00:00", "2026-07-19T00:00"
WIN_B_LO, WIN_B_HI = "2026-06-19T00:00", "2026-07-04T00:00"
WIN_FULL_LO, WIN_FULL_HI = "2026-06-19T00:00", "2026-07-19T00:00"

FIELD = "wd"
MIN_N_CELL = 200
MAE_IMPROVE_FLOOR_PCT = 3.0

LEAD_BANDS = [
    ("0-5",   1,  5),
    ("6-11",  6, 11),
    ("12-23", 12, 23),
    ("24-47", 24, 47),
]


def lead_band(lead):
    for name, lo, hi in LEAD_BANDS:
        if lo <= lead <= hi:
            return name
    return None


def hour_floor(ts):
    if ts is None or len(ts) < 16:
        return None
    return ts[:14] + "00"


def angular_diff(a, b):
    d = abs(float(a) - float(b)) % 360.0
    return d if d <= 180.0 else 360.0 - d


def compute():
    path = cached_path(URL)

    # Pass 1: wd obs index (for persistence baseline) + obs_regime_index
    # (for state_curr construction). obs_regime_index keeps the smallest-lead
    # pair's state_obs.regime for each valid_time — that's the regime that
    # was observed at hour_floor(valid_time).
    print("[1/2] Building wd obs + regime indexes...", file=sys.stderr)
    obs_ts = {}
    # For state_curr: track the SHORTEST lead we've seen for each valid_time,
    # keeping its state_obs.regime as most-authoritative.
    regime_ts = {}   # valid_time → (lead_h, regime)
    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            field = r.get("field")
            vt = r.get("valid_time")
            if vt is None:
                continue
            if field == FIELD:
                ob = r.get("observed")
                if ob is not None and vt not in obs_ts:
                    obs_ts[vt] = float(ob)
            state_obs = r.get("state_obs") or {}
            rg = state_obs.get("regime_synoptic")
            lh = r.get("lead_h")
            if rg is None or lh is None:
                continue
            try:
                lh = int(lh)
            except Exception:
                continue
            prev = regime_ts.get(vt)
            if prev is None or lh < prev[0]:
                regime_ts[vt] = (lh, rg)
    obs_regime_index = {vt: rg for vt, (_, rg) in regime_ts.items()}
    print(f"    wd obs index: {len(obs_ts):,};  obs_regime index: {len(obs_regime_index):,}",
          file=sys.stderr)

    # accum[(window, scenario, state_fc_regime, band, fire_slot)] = {n, ae}
    # scenario ∈ {"l1", "persist", "gate"}
    # fire_slot ∈ {"fires", "no_fire", "all"}
    print("[2/2] Scoring under predicted-transition fire condition...", file=sys.stderr)
    accum = defaultdict(lambda: {"n": 0, "ae": 0.0})
    joint = defaultdict(int)  # (fires_predicted, actual_transition) → n
    n_joined = 0
    n_no_persist = 0
    n_no_curr = 0

    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            rt = r.get("run_time", "")
            if WIN_A_LO <= rt < WIN_A_HI:
                windows = ["A", "FULL"]
            elif WIN_B_LO <= rt < WIN_B_HI:
                windows = ["B", "FULL"]
            else:
                continue

            lead = r.get("lead_h")
            if lead is None:
                continue
            try:
                lead = int(lead)
            except Exception:
                continue
            band = lead_band(lead)
            if band is None:
                continue

            ob = r.get("observed")
            fc = r.get("forecast")
            if ob is None or fc is None:
                continue

            persist = obs_ts.get(hour_floor(rt))
            if persist is None:
                n_no_persist += 1
                continue

            state_fc = r.get("state_fc") or {}
            state_obs = r.get("state_obs") or {}
            fc_regime = state_fc.get("regime_synoptic") or "unknown"
            obs_regime = state_obs.get("regime_synoptic")

            state_curr = obs_regime_index.get(hour_floor(rt))
            if state_curr is None:
                n_no_curr += 1
                continue

            fires_predicted = (state_curr != fc_regime)
            actual_transition = (
                obs_regime is not None and obs_regime != fc_regime
            )
            joint[(fires_predicted, actual_transition)] += 1

            n_joined += 1

            err_l1 = angular_diff(fc, ob)
            err_pers = angular_diff(persist, ob)
            err_gate = err_pers if fires_predicted else err_l1

            fire_slot = "fires" if fires_predicted else "no_fire"

            for win in windows:
                for slot in (fire_slot, "all"):
                    for scen, err in (("l1", err_l1),
                                       ("persist", err_pers),
                                       ("gate", err_gate)):
                        a = accum[(win, scen, fc_regime, band, slot)]
                        a["n"] += 1
                        a["ae"] += err

    print(f"    joined {n_joined:,} wd rows; {n_no_persist:,} orphans (no persist); "
          f"{n_no_curr:,} skipped (no state_curr)", file=sys.stderr)
    return accum, joint


def mae(bkt):
    n = bkt["n"]
    return (bkt["ae"] / n) if n else None


def cell_verdict(l1_full, gate_full, l1_a, gate_a, l1_b, gate_b, n_full):
    if n_full < MIN_N_CELL:
        return "THIN", None, None, None
    if l1_full is None or gate_full is None:
        return "THIN", None, None, None
    d_full = 100.0 * (gate_full - l1_full) / l1_full if l1_full else 0.0
    d_a = 100.0 * (gate_a - l1_a) / l1_a if (l1_a and gate_a is not None) else None
    d_b = 100.0 * (gate_b - l1_b) / l1_b if (l1_b and gate_b is not None) else None
    if (d_full <= -MAE_IMPROVE_FLOOR_PCT
        and d_a is not None and d_a <= -MAE_IMPROVE_FLOOR_PCT
        and d_b is not None and d_b <= -MAE_IMPROVE_FLOOR_PCT):
        return "SHIP", d_full, d_a, d_b
    if d_full > 0 or (d_a is not None and d_b is not None and (d_a * d_b) < 0):
        return "SKIP", d_full, d_a, d_b
    return "MARGIN", d_full, d_a, d_b


def emit(accum, joint):
    regimes = sorted({key[2] for key in accum.keys()})
    bands = [name for name, _, _ in LEAD_BANDS]

    lines = []
    lines.append("=" * 100)
    lines.append("wd PERSISTENCE GATE — Stage 2 preview (predicted-transition fire signal)")
    lines.append("=" * 100)
    lines.append("")
    lines.append("Gate under test: fire persistence-of-obs when state_curr != state_fc.regime")
    lines.append("for this specific lead. Both known at forecast time (state_curr = observed")
    lines.append("regime at hour_floor(run_time); state_fc from target_hour).")
    lines.append(f"Windows: A={WIN_A_LO[:10]}→{WIN_A_HI[:10]}, "
                 f"B={WIN_B_LO[:10]}→{WIN_B_HI[:10]}, FULL={WIN_FULL_LO[:10]}→{WIN_FULL_HI[:10]}")
    lines.append("")

    # === Confusion matrix: predicted-transition vs actual-transition ===
    lines.append("=" * 100)
    lines.append("SIGNAL QUALITY — predicted-transition (state_curr ≠ state_fc) vs actual")
    lines.append("=" * 100)
    tt = joint.get((True,  True),  0)
    tf = joint.get((True,  False), 0)
    ft = joint.get((False, True),  0)
    ff = joint.get((False, False), 0)
    total = tt + tf + ft + ff
    lines.append(f"                          actual TRANSITION   actual STABLE")
    lines.append(f"  predicted TRANSITION    {tt:>10,} (TP)     {tf:>10,} (FP)")
    lines.append(f"  predicted STABLE        {ft:>10,} (FN)     {ff:>10,} (TN)")
    lines.append("")
    if total:
        prec = 100.0 * tt / (tt + tf) if (tt + tf) else 0.0
        rec  = 100.0 * tt / (tt + ft) if (tt + ft) else 0.0
        acc  = 100.0 * (tt + ff) / total
        lines.append(f"  precision = {prec:.1f}% (of fires, share that hit actual transition)")
        lines.append(f"  recall    = {rec:.1f}% (of actual transitions, share we fire on)")
        lines.append(f"  accuracy  = {acc:.1f}%")
        lines.append(f"  fire rate = {100.0 * (tt + tf) / total:.1f}% of rows")
    lines.append("")

    # === Per-cell: gate vs L1, on rows where the gate fires ===
    lines.append("=" * 100)
    lines.append("PER-CELL — gate vs L1 on FIRING rows (state_fc.regime × lead_band)")
    lines.append("=" * 100)
    header = (f"{'fc_regime':<12}{'band':<8}{'n_fires':>10}"
              f"{'L1 MAE':>10}{'gate MAE':>10}"
              f"{'Δ full %':>10}{'Δ A %':>9}{'Δ B %':>9}  verdict")
    lines.append(header)
    lines.append("-" * len(header))

    cells = {}
    for regime in regimes:
        for band in bands:
            l1_f = mae(accum[("FULL", "l1", regime, band, "fires")])
            gate_f = mae(accum[("FULL", "persist", regime, band, "fires")])
            l1_a = mae(accum[("A", "l1", regime, band, "fires")])
            gate_a = mae(accum[("A", "persist", regime, band, "fires")])
            l1_b = mae(accum[("B", "l1", regime, band, "fires")])
            gate_b = mae(accum[("B", "persist", regime, band, "fires")])
            n_full = accum[("FULL", "l1", regime, band, "fires")]["n"]
            if n_full == 0 or l1_f is None or gate_f is None:
                continue
            verdict, d_full, d_a, d_b = cell_verdict(
                l1_f, gate_f, l1_a, gate_a, l1_b, gate_b, n_full
            )
            star = " ★" if verdict == "SHIP" else ""
            d_full_s = f"{d_full:+.2f}" if d_full is not None else "  n/a"
            d_a_s    = f"{d_a:+.2f}"    if d_a    is not None else "  n/a"
            d_b_s    = f"{d_b:+.2f}"    if d_b    is not None else "  n/a"
            lines.append(f"{regime:<12}{band:<8}{n_full:>10,}"
                         f"{l1_f:>10.3f}{gate_f:>10.3f}"
                         f"{d_full_s:>10}{d_a_s:>9}{d_b_s:>9}  {verdict}{star}")
            cells.setdefault(regime, {})[band] = {
                "n_fires": n_full,
                "mae_l1": round(l1_f, 3),
                "mae_gate": round(gate_f, 3),
                "delta_full_pct": round(d_full, 2) if d_full is not None else None,
                "delta_a_pct": round(d_a, 2) if d_a is not None else None,
                "delta_b_pct": round(d_b, 2) if d_b is not None else None,
                "verdict": verdict,
            }
        lines.append("")

    # === Sanity: overall gate on ALL rows (fires and non-fires composed) ===
    lines.append("=" * 100)
    lines.append("OVERALL — composed gate (fires: persistence; no_fire: L1) vs L1 baseline")
    lines.append("=" * 100)
    hdr2 = (f"{'fc_regime':<12}{'band':<8}{'n_all':>10}"
            f"{'L1 MAE':>10}{'gate MAE':>10}{'Δ %':>10}")
    lines.append(hdr2)
    lines.append("-" * len(hdr2))
    for regime in regimes:
        for band in bands:
            l1_all = mae(accum[("FULL", "l1", regime, band, "all")])
            gate_all = mae(accum[("FULL", "gate", regime, band, "all")])
            n_all = accum[("FULL", "l1", regime, band, "all")]["n"]
            if n_all < MIN_N_CELL or l1_all is None or gate_all is None:
                continue
            d = 100.0 * (gate_all - l1_all) / l1_all if l1_all else 0.0
            mark = ""
            if d <= -MAE_IMPROVE_FLOOR_PCT: mark = " ★"
            elif d >= MAE_IMPROVE_FLOOR_PCT: mark = " ⚠"
            lines.append(f"{regime:<12}{band:<8}{n_all:>10,}"
                         f"{l1_all:>10.3f}{gate_all:>10.3f}{d:>+10.2f}{mark}")
        lines.append("")

    # === Rollup ===
    ship_cells, skip_cells, margin_cells, thin_cells = [], [], [], []
    for regime, bandmap in cells.items():
        for band, d in bandmap.items():
            key = (regime, band)
            {"SHIP": ship_cells, "SKIP": skip_cells,
             "MARGIN": margin_cells, "THIN": thin_cells}[d["verdict"]].append(key)

    lines.append("=" * 100)
    lines.append("ROLLUP")
    lines.append("=" * 100)
    total_cells = len(ship_cells) + len(skip_cells) + len(margin_cells) + len(thin_cells)
    lines.append(f"  SHIP:   {len(ship_cells):>3} cells")
    lines.append(f"  MARGIN: {len(margin_cells):>3} cells")
    lines.append(f"  SKIP:   {len(skip_cells):>3} cells")
    lines.append(f"  THIN:   {len(thin_cells):>3} cells")
    lines.append(f"  total judged: {total_cells}")
    lines.append("")

    lines.append("=" * 100)
    lines.append("PROPOSED GATE SHAPE")
    lines.append("=" * 100)
    if ship_cells or margin_cells:
        lines.append("  base rule: forecast = L1 (current behavior)")
        lines.append("  fire condition: state_curr != state_fc.regime for the lead")
        lines.append("  override with persistence-of-obs when fire condition AND cell in:")
        for regime, band in sorted(ship_cells + margin_cells):
            verdict = cells[regime][band]["verdict"]
            lines.append(f"    - fc_regime == '{regime}' AND lead_band == '{band}'  ({verdict})")
    else:
        lines.append("  no cells cleared halves-stable ship gate on firing rows.")
    lines.append("")

    if len(ship_cells) >= 2:
        overall = (f"Verdict: STAGE 2 HIT — {len(ship_cells)} SHIP cell(s) at floor "
                   f"{MAE_IMPROVE_FLOOR_PCT}% under predicted-transition fire signal. "
                   f"Move to Stage 3 wiring.")
    elif ship_cells:
        overall = f"Verdict: MARGINAL — {len(ship_cells)} SHIP + {len(margin_cells)} MARGIN. Re-run after 3-day window roll."
    else:
        overall = f"Verdict: HOLD — predicted-transition fire signal doesn't produce a stable per-cell win."
    lines.append(overall)
    lines.append("")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "forecast_error_log.jsonl",
        "field": FIELD,
        "stage": 2,
        "windows": {
            "A_recent_15d": [WIN_A_LO, WIN_A_HI],
            "B_prior_15d":  [WIN_B_LO, WIN_B_HI],
            "FULL_30d":     [WIN_FULL_LO, WIN_FULL_HI],
        },
        "fit_rules": {
            "min_n_cell": MIN_N_CELL,
            "mae_improve_floor_pct": MAE_IMPROVE_FLOOR_PCT,
            "halves_stability_required": True,
            "lead_bands": bands,
            "arithmetic": "circular_angular_diff",
        },
        "signal_quality": {
            "tp": tt, "fp": tf, "fn": ft, "tn": ff,
            "precision_pct": round(prec, 2) if total else None,
            "recall_pct": round(rec, 2) if total else None,
            "accuracy_pct": round(acc, 2) if total else None,
            "fire_rate_pct": round(100.0 * (tt + tf) / total, 2) if total else None,
        },
        "gate": {
            "fire_condition": "state_curr != state_fc.regime_synoptic (per lead)",
            "baseline": "L1 (raw HRRR forecast)",
            "intervention": "persistence-of-obs (flat carry of wd obs at hour_floor(run_time))",
            "fire_cells": [
                {"fc_regime": r, "lead_band": b, "verdict": cells[r][b]["verdict"]}
                for r, b in sorted(ship_cells + margin_cells)
            ],
        },
        "cells": cells,
        "rollup": {
            "ship": len(ship_cells),
            "margin": len(margin_cells),
            "skip": len(skip_cells),
            "thin": len(thin_cells),
        },
        "notes": (
            "Stage 2 preview. Not wired to production. Fire condition uses "
            "predicted-transition signal (state_curr != state_fc.regime); both "
            "knowable at forecast time. Wire via wd_persistence_gate processor "
            "with ENABLED=False on ship and 7-day narrow-promote gate."
        ),
    }

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    print("\n".join(lines))
    print(f"\nwrote {OUT_TXT}")
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    accum, joint = compute()
    emit(accum, joint)
