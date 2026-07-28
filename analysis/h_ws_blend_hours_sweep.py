"""Stage 0 — sweep BLEND_HOURS for wind_blend.py's ws hourly bleed.

Motivation (from mae_over_time / time_series_diagnostic 2026-07-28 check):
  ws is Prod +30.5% WORSE than raw today, ≥+20% worse for 4 days running.
  Per-lead breakdown shows L2 wins at lead 1 (−21% vs raw) but catastrophically
  loses at leads 3-16 (+40% to +85%). L3 is bit-identical to L2 (SKIP additive
  doing nothing on top). Root cause is `wind_blend.py::blend_observed_into_hourly`
  bleeding the current observed wind into next `BLEND_HOURS=24` with linear
  decay. The observation is noisier than the model at those leads (turbulence,
  gustiness, calm-variable oscillation).

Hypothesis:
  Shrinking BLEND_HOURS from 24 → some smaller value preserves the lead-1 win
  while killing the lead-3-onward damage. Sweep {1, 2, 3, 4, 6, 8, 12, 24}
  and pick the value that minimizes ws MAE overall.

Method:
  1. Stream pair log for ws rows in a recent window.
  2. Group by run_time. For each run, back-solve observed_current from a
     low-lead row: obs = (L2 - (1-w) * L1) / w, where w = max(0, 1 - lead/24).
     Use earliest lead where w > 0.5 for numerical stability. Prefer lead=1
     (w = 0.958), fall back to lead=2 (w = 0.917) if lead=1 missing.
  3. For each test BLEND_HOURS ∈ {1, 2, 3, 4, 6, 8, 12, 24}, simulate
     alt_L2 = w_test * obs + (1 - w_test) * L1 per lead in that run.
     w_test = max(0, 1 - lead / BLEND_HOURS_test)
  4. Pooled MAE + per-lead-band (0-5, 6-11, 12-23, 24-47) for each test value.
  5. Compare to current-production (BLEND_HOURS=24) MAE.
  6. Halves stability check on test/train split.

Ship gate:
  Cleanest smaller BLEND_HOURS with:
    - pooled MAE improvement ≥ 1.0% vs current 24h
    - both halves show the improvement (no divergence > 5pp)
    - no lead-band goes materially worse (< −2% degradation in any band)
  → propose flip as a wind_blend.py constant edit.

Run:
    python3 analysis/h_ws_blend_hours_sweep.py

Emits:
    analysis/output/h_ws_blend_hours_sweep.txt
"""
import json
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_ws_blend_hours_sweep.txt")

FIELD = "ws"
CURRENT_BLEND_HOURS = 24.0    # from wind_blend.py:78
TEST_VALUES = [1, 2, 3, 4, 6, 8, 12, 24]
LEAD_BANDS = [("0-5", 0, 5), ("6-11", 6, 11), ("12-23", 12, 23), ("24-47", 24, 47)]

# Recent window — align with time_series_diagnostic default (7-day)
WINDOW_DAYS = 7

MIN_BACKSOLVE_WEIGHT = 0.5    # skip runs where earliest available lead has weight < 0.5
SHIP_GATE_PCT = 1.0            # min pooled improvement to propose ship
LEAD_BAND_TOLERANCE_PCT = -2.0  # no lead-band worse than this


def lead_band(h):
    for name, lo, hi in LEAD_BANDS:
        if lo <= h <= hi:
            return name
    return None


def weight(lead_h, blend_hours):
    if blend_hours <= 0:
        return 0.0
    return max(0.0, 1.0 - lead_h / blend_hours)


def load_ws_rows():
    """Return list of dicts: {run_time, lead_h, obs, l1, l2, obs_date}."""
    path = cached_path(URL)
    rows = []
    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            lead = r.get("lead_h")
            l1 = r.get("forecast_l1")
            l2 = r.get("forecast_l2")
            obs = r.get("observed")
            rt = r.get("run_time")
            ot = r.get("obs_time")
            if lead is None or l1 is None or l2 is None or obs is None or not rt:
                continue
            try:
                lead = int(lead)
                l1 = float(l1)
                l2 = float(l2)
                obs = float(obs)
            except (ValueError, TypeError):
                continue
            if lead < 0 or lead > 47:
                continue
            rows.append({
                "run_time": rt, "lead_h": lead, "obs": obs,
                "l1": l1, "l2": l2, "obs_date": ot[:10] if ot else rt[:10],
            })
    return rows


def backsolve_obs_current(run_rows):
    """Given all rows for one run_time, back-solve the observed_current used
    in the wind_blend at collector tick time. Returns None if no lead has
    sufficient weight for numerical stability.

    obs_current = (L2 - (1 - w) * L1) / w
    where w = weight(lead, CURRENT_BLEND_HOURS)
    """
    # Try leads in order of decreasing weight (lowest lead first)
    for row in sorted(run_rows, key=lambda r: r["lead_h"]):
        w = weight(row["lead_h"], CURRENT_BLEND_HOURS)
        if w < MIN_BACKSOLVE_WEIGHT:
            continue
        # If L1 == L2, then either w == 0 (no blend applied) or obs == L1.
        # Either way, obs_current = L1 is the identity-consistent read.
        if abs(row["l2"] - row["l1"]) < 1e-9:
            return row["l1"]
        obs_current = (row["l2"] - (1 - w) * row["l1"]) / w
        return obs_current
    return None


def simulate(rows, blend_hours):
    """For each row, compute alt_L2 = w_test * obs_current + (1 - w_test) * L1.
    Returns dict lead_band -> {mae, n} plus pooled {mae, n}.
    """
    band_ae = defaultdict(lambda: {"ae": 0.0, "n": 0})
    pooled_ae, pooled_n = 0.0, 0
    for r in rows:
        w = weight(r["lead_h"], blend_hours)
        alt_l2 = w * r["obs_current"] + (1 - w) * r["l1"]
        ae = abs(alt_l2 - r["obs"])
        band = lead_band(r["lead_h"])
        if band:
            band_ae[band]["ae"] += ae
            band_ae[band]["n"] += 1
        pooled_ae += ae
        pooled_n += 1
    out = {}
    for band, d in band_ae.items():
        out[band] = {"mae": d["ae"] / d["n"] if d["n"] else None, "n": d["n"]}
    out["pooled"] = {"mae": pooled_ae / pooled_n if pooled_n else None, "n": pooled_n}
    return out


def main():
    print("Loading pair log...", file=sys.stderr)
    all_rows = load_ws_rows()
    if not all_rows:
        print("No ws rows.")
        return

    # Recent window
    all_rows.sort(key=lambda r: r["obs_date"])
    latest_date = all_rows[-1]["obs_date"]
    from datetime import datetime, timedelta
    cutoff = (datetime.fromisoformat(latest_date) - timedelta(days=WINDOW_DAYS)).isoformat()[:10]
    window_rows = [r for r in all_rows if r["obs_date"] >= cutoff]
    print(f"  loaded {len(all_rows):,} ws rows; window {cutoff} → {latest_date} keeps {len(window_rows):,}",
          file=sys.stderr)

    # Group by run_time and back-solve obs_current
    by_run = defaultdict(list)
    for r in window_rows:
        by_run[r["run_time"]].append(r)

    solved_rows = []
    skipped_runs = 0
    for rt, rrs in by_run.items():
        obs_cur = backsolve_obs_current(rrs)
        if obs_cur is None:
            skipped_runs += 1
            continue
        for r in rrs:
            r2 = dict(r)
            r2["obs_current"] = obs_cur
            solved_rows.append(r2)
    print(f"  runs kept {len(by_run) - skipped_runs:,} / {len(by_run):,}"
          f" ({skipped_runs:,} skipped: no low-lead row for back-solve)",
          file=sys.stderr)

    # Halves split by obs_date
    solved_rows.sort(key=lambda r: r["obs_date"])
    mid = len(solved_rows) // 2
    half_a = solved_rows[:mid]
    half_b = solved_rows[mid:]

    out = []
    def emit(s=""):
        print(s)
        out.append(s)

    emit("=" * 96)
    emit(f"ws BLEND_HOURS sweep — window {cutoff} → {latest_date}, {WINDOW_DAYS} days")
    emit("=" * 96)
    emit(f"Current production: wind_blend.py BLEND_HOURS = {CURRENT_BLEND_HOURS:g}")
    emit(f"n rows: {len(solved_rows):,}   halves: A={len(half_a):,}, B={len(half_b):,}")
    emit(f"Ship-gate: pooled Δ ≥ {SHIP_GATE_PCT:.1f}% AND both halves match AND no lead-band < {LEAD_BAND_TOLERANCE_PCT:.1f}%")
    emit("")

    # Baseline: current BLEND_HOURS=24 (should match live L2 MAE)
    base = simulate(solved_rows, CURRENT_BLEND_HOURS)
    base_a = simulate(half_a, CURRENT_BLEND_HOURS)
    base_b = simulate(half_b, CURRENT_BLEND_HOURS)

    emit(f"BASELINE (BLEND_HOURS={CURRENT_BLEND_HOURS:g}) — should match live L2 pair-log MAE")
    emit(f"  pooled MAE: {base['pooled']['mae']:.4f}  (n={base['pooled']['n']:,})")
    for band in ("0-5", "6-11", "12-23", "24-47"):
        b = base.get(band, {})
        if b.get("mae") is not None:
            emit(f"    {band:<7}: {b['mae']:.4f}  (n={b['n']:,})")
    emit("")

    # Sweep
    emit(f"{'BLEND_H':>8}  {'pooled':>8}  {'Δ%':>7}  {'halfA':>7}  {'halfB':>7}  {'0-5':>7}  {'6-11':>7}  {'12-23':>7}  {'24-47':>7}  verdict")
    emit("-" * 96)

    winners = []
    for bh in TEST_VALUES:
        s = simulate(solved_rows, bh)
        sa = simulate(half_a, bh)
        sb = simulate(half_b, bh)
        pooled = s['pooled']['mae']
        d_pct = (base['pooled']['mae'] - pooled) / base['pooled']['mae'] * 100 if base['pooled']['mae'] else 0
        d_a = (base_a['pooled']['mae'] - sa['pooled']['mae']) / base_a['pooled']['mae'] * 100 if base_a['pooled']['mae'] else 0
        d_b = (base_b['pooled']['mae'] - sb['pooled']['mae']) / base_b['pooled']['mae'] * 100 if base_b['pooled']['mae'] else 0
        band_dpcts = {}
        for band in ("0-5", "6-11", "12-23", "24-47"):
            bb = base.get(band, {}); tb = s.get(band, {})
            if bb.get("mae") is not None and tb.get("mae") is not None and bb["mae"] > 0:
                band_dpcts[band] = (bb["mae"] - tb["mae"]) / bb["mae"] * 100
            else:
                band_dpcts[band] = None
        # Verdict
        verdict = "flat"
        if d_pct >= SHIP_GATE_PCT and min(d_a, d_b) >= 0:
            worst_band_delta = min((v for v in band_dpcts.values() if v is not None), default=0)
            if worst_band_delta >= LEAD_BAND_TOLERANCE_PCT:
                verdict = "SHIP"
                winners.append((bh, d_pct, d_a, d_b))
            else:
                verdict = "MARGIN (band regression)"
        elif d_pct >= SHIP_GATE_PCT:
            verdict = "MARGIN (halves)"
        elif d_pct < -SHIP_GATE_PCT:
            verdict = "WORSE"

        emit(f"{bh:>8g}  {pooled:>8.4f}  {d_pct:>+6.2f}%  {d_a:>+6.2f}%  {d_b:>+6.2f}%  " +
             "  ".join(f"{band_dpcts[b]:>+6.2f}%" if band_dpcts[b] is not None else "     --" for b in ("0-5", "6-11", "12-23", "24-47")) +
             f"  {verdict}")

    emit("")
    if winners:
        best = max(winners, key=lambda x: x[1])
        emit(f"VERDICT: SHIP — BLEND_HOURS={best[0]:g} clears gate ({best[1]:+.2f}% pooled, halves {best[2]:+.2f}% / {best[3]:+.2f}%).")
        emit(f"  Ship path: edit wind_blend.py:78 BLEND_HOURS = {best[0]}. No config file, one-constant edit.")
    else:
        emit("VERDICT: NO SHIP CANDIDATE — no test value clears the pooled + halves + lead-band gate.")
        emit("  Consider: (a) sharper decay curve (exp instead of linear), or (b) kill L2 blend for ws entirely.")

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
