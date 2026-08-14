"""Stage 2 preview — ch regime-gated persistence blend, L6-BASELINE variant.

Fork of `h_ch_persistence_blend_stage2.py` created 2026-07-27 v0.6.382r
in response to the h_chp_midlead_regression.py ESCALATE finding:

  Six leads (10-15h) show chp WORSE than Lc alone by +20-30% MAE at
  n=176-186 per lead. The shipped Stage 2 measured chp against
  `forecast_l4` (pre-Lc baseline) because Lc hadn't flipped yet when
  Stage 2 shipped. Post-Lc-flip (2026-07-17 v0.6.355), the meaningful
  baseline for chp is `forecast_l6` (Lc-corrected L4) — chp REPLACES
  the Lc value on SHIP cells, so the honest comparison is chp vs Lc.

This variant re-derives per-cell SHIP/SKIP verdicts under the L6
baseline. **Preview only — writes to a _vs_l6 suffix, does not touch
the live curated JSON.** If the mid-lead cells flip SHIP → SKIP under
this baseline, the escalation playbook (per
[[project_chp_midlead_regression_watch]]) is to promote this script
to the SHIPPED Stage 2 and let Joe's live-layer change gate decide the
curated-JSON update.

Window: post-Lc-flip only (2026-07-17 → present) so `forecast_l6`
reflects the actual live stack, not Lc-off telemetry. Halves-split
inside that window is tight (5-day halves) — MIN_N_CELL relaxed to 100
to keep cells addressable. Because the window is short, a MARGIN
verdict here doesn't have the halves-stability guarantee that the
original Stage 2 provided; treat MARGIN as "worth watching," SHIP as
"chp still wins vs Lc," SKIP as "chp materially loses vs Lc."

Emits:
  analysis/output/h_ch_persistence_blend_stage2_vs_l6.txt
  weather_collector/data/ch_persistence_gate_curated_vs_l6.json  (preview)
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402
from _windows import rolling_windows  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_TXT = os.path.join(HERE, "output", "h_ch_persistence_blend_stage2_vs_l6.txt")
OUT_JSON = os.path.abspath(os.path.join(
    HERE, "..", "weather_collector", "data", "ch_persistence_gate_curated_vs_l6.json"
))
LIVE_CURATED = os.path.abspath(os.path.join(
    HERE, "..", "weather_collector", "data", "ch_persistence_gate_curated.json"
))

# Post-Lc-flip windows only. Lc FLIPPED 2026-07-17 v0.6.355.
# Full: last 10 days including today. Halves: last 5d + prior 5d.
WIN_A_LO, WIN_A_HI, WIN_B_LO, WIN_B_HI, WIN_FULL_LO, WIN_FULL_HI = rolling_windows(recent_days=5, prior_days=5)

FIELD = "ch"
MIN_N_CELL = 100                # relaxed from 200 for the tighter 10-day window
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


def compute():
    path = cached_path(URL)

    print("[1/2] Building ch obs index...", file=sys.stderr)
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
            if vt is None or ob is None:
                continue
            if vt not in obs_ts:
                obs_ts[vt] = ob
    print(f"    ch obs index size: {len(obs_ts):,}", file=sys.stderr)

    print("[2/2] Scoring ch scenarios per (regime × lead_band) — L6 baseline...", file=sys.stderr)
    accum = defaultdict(lambda: {"n": 0, "ae": 0.0, "se": 0.0})
    n_joined = 0
    n_orphan = 0
    n_no_l6 = 0

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
                windows = [("A", None), ("FULL", None)]
            elif WIN_B_LO <= rt < WIN_B_HI:
                windows = [("B", None), ("FULL", None)]
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
            fc6 = r.get("forecast_l6")
            if ob is None or fc6 is None:
                n_no_l6 += 1
                continue

            persist = obs_ts.get(hour_floor(rt))
            if persist is None:
                n_orphan += 1
                continue
            n_joined += 1

            state_fc = r.get("state_fc") or {}
            regime = state_fc.get("regime_synoptic") or "unknown"

            fc_baseline = fc6                                     # ← changed
            fc_regime_gate = fc6 if regime == "frontal" else persist
            fc_persist_only = persist

            forecasts = {
                "baseline":     fc_baseline,
                "regime_gate":  fc_regime_gate,
                "persist_only": fc_persist_only,
            }
            for win, _ in windows:
                for sc, fc in forecasts.items():
                    err = fc - ob
                    a = accum[(win, sc, regime, band)]
                    a["n"] += 1
                    a["ae"] += abs(err)
                    a["se"] += err * err

    print(f"    joined {n_joined:,} ch rows; {n_orphan:,} orphans; "
          f"{n_no_l6:,} skipped (no forecast_l6 — pre-Lc-flip or fetch fail)",
          file=sys.stderr)
    return accum


def mae(bkt):
    n = bkt["n"]
    return (bkt["ae"] / n) if n else None


def cell_verdict(base_full, gate_full, base_a, gate_a, base_b, gate_b, n_full):
    if n_full < MIN_N_CELL:
        return "THIN", None, None, None
    d_full = 100.0 * (gate_full - base_full) / base_full if base_full else 0.0
    d_a = 100.0 * (gate_a - base_a) / base_a if (base_a and gate_a is not None) else None
    d_b = 100.0 * (gate_b - base_b) / base_b if (base_b and gate_b is not None) else None
    if (d_full <= -MAE_IMPROVE_FLOOR_PCT
        and d_a is not None and d_a <= -MAE_IMPROVE_FLOOR_PCT
        and d_b is not None and d_b <= -MAE_IMPROVE_FLOOR_PCT):
        return "SHIP", d_full, d_a, d_b
    if d_full > 0 or (d_a is not None and d_b is not None and (d_a * d_b) < 0):
        return "SKIP", d_full, d_a, d_b
    return "MARGIN", d_full, d_a, d_b


def _load_processor_cell_skip():
    """Read the runtime _CELL_SKIP frozenset from ch_persistence_gate.py.
    These cells are demoted to L4 in the processor regardless of the curated
    JSON verdict (v0.6.405+ emergency demote pattern). We subtract them from
    the "live SHIP" set so this preview only flags cells that would ACTUALLY
    fire chp under the L6 baseline test — otherwise the flip_ship_to_skip
    count double-counts cells already forced to L4 at runtime.
    """
    try:
        sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
        from weather_collector.processors.ch_persistence_gate import _CELL_SKIP
        return set(_CELL_SKIP)
    except Exception as e:
        print(f"    ⚠  could not load processor _CELL_SKIP: {e}", file=sys.stderr)
        return set()


def load_live_ship_set():
    """Read the currently-live curated JSON's SHIP+MARGIN set for comparison.
    Subtracts cells that the processor's _CELL_SKIP forces to L4 regardless
    of curated verdict — those cells never fire chp at runtime, so counting
    them as 'live SHIP' overstates the amount of active regression."""
    try:
        with open(LIVE_CURATED) as fh:
            payload = json.load(fh)
    except Exception as e:
        print(f"    ⚠  could not read live curated JSON: {e}", file=sys.stderr)
        return set()
    live = set()
    for regime, bandmap in (payload.get("cells") or {}).items():
        for band, cell in bandmap.items():
            if cell.get("verdict") in ("SHIP", "MARGIN"):
                live.add((regime, band))
    processor_skip = _load_processor_cell_skip()
    if processor_skip:
        overlap = live & processor_skip
        if overlap:
            print(f"    ℹ  subtracting {len(overlap)} cell(s) from live_ship_set — "
                  f"already demoted by processor _CELL_SKIP: {sorted(overlap)}",
                  file=sys.stderr)
        live -= processor_skip
    return live


def emit(accum):
    regimes = sorted({key[2] for key in accum.keys()})
    bands = [name for name, _, _ in LEAD_BANDS]
    live_ship_set = load_live_ship_set()

    lines = []
    def L(s=""):
        lines.append(s)

    L("=" * 100)
    L("ch REGIME-GATED PERSISTENCE BLEND — Stage 2 preview (L6-BASELINE variant)")
    L("=" * 100)
    L("")
    L("Gate under test: forecast = L6 (Lc-corrected) if regime==frontal else persistence-of-obs.")
    L(f"Windows: A={WIN_A_LO[:10]}→{WIN_A_HI[:10]}, B={WIN_B_LO[:10]}→{WIN_B_HI[:10]},")
    L(f"         FULL={WIN_FULL_LO[:10]}→{WIN_FULL_HI[:10]} (post-Lc-flip only).")
    L(f"Cell verdict: SHIP requires halves-stability + full window ≤ -{MAE_IMPROVE_FLOOR_PCT}% vs L6.")
    L(f"Live SHIP+MARGIN set (from ch_persistence_gate_curated.json): {len(live_ship_set)} cells.")
    L("")

    L("=" * 100)
    L("PER-CELL: regime_gate (chp) vs L6 baseline")
    L("=" * 100)
    header = (f"{'regime':<12}{'band':<8}{'n':>8}"
              f"{'L6 MAE':>10}{'chp MAE':>10}"
              f"{'Δ full %':>10}{'Δ A %':>9}{'Δ B %':>9}  verdict  live?")
    L(header)
    L("-" * len(header))

    cells = {}
    flip_ship_to_skip = []
    flip_ship_to_margin = []
    new_ship = []
    for regime in regimes:
        for band in bands:
            base_f = mae(accum[("FULL", "baseline", regime, band)])
            gate_f = mae(accum[("FULL", "regime_gate", regime, band)])
            base_a = mae(accum[("A", "baseline", regime, band)])
            gate_a = mae(accum[("A", "regime_gate", regime, band)])
            base_b = mae(accum[("B", "baseline", regime, band)])
            gate_b = mae(accum[("B", "regime_gate", regime, band)])
            n_full = accum[("FULL", "baseline", regime, band)]["n"]
            if n_full == 0 or base_f is None or gate_f is None:
                continue
            verdict, d_full, d_a, d_b = cell_verdict(
                base_f, gate_f, base_a, gate_a, base_b, gate_b, n_full
            )
            is_live = (regime, band) in live_ship_set
            if is_live and verdict == "SKIP":
                flip_ship_to_skip.append((regime, band, d_full))
            elif is_live and verdict in ("THIN",):
                flip_ship_to_margin.append((regime, band, verdict))
            elif not is_live and verdict == "SHIP":
                new_ship.append((regime, band, d_full))
            star = " ★" if verdict == "SHIP" else ""
            live_marker = "(LIVE)" if is_live else "     "
            d_full_s = f"{d_full:+.2f}" if d_full is not None else "  n/a"
            d_a_s    = f"{d_a:+.2f}" if d_a is not None else "  n/a"
            d_b_s    = f"{d_b:+.2f}" if d_b is not None else "  n/a"
            L(f"{regime:<12}{band:<8}{n_full:>8,}"
              f"{base_f:>10.3f}{gate_f:>10.3f}"
              f"{d_full_s:>10}{d_a_s:>9}{d_b_s:>9}  {verdict:<7}{star}  {live_marker}")
            cells.setdefault(regime, {})[band] = {
                "n": n_full,
                "mae_baseline_l6": round(base_f, 3),
                "mae_chp": round(gate_f, 3),
                "delta_full_pct": round(d_full, 2) if d_full is not None else None,
                "delta_a_pct": round(d_a, 2) if d_a is not None else None,
                "delta_b_pct": round(d_b, 2) if d_b is not None else None,
                "verdict": verdict,
                "is_live_ship_or_margin": is_live,
            }
        L("")

    # Rollup
    ship_cells = []
    margin_cells = []
    skip_cells = []
    thin_cells = []
    for regime, bandmap in cells.items():
        for band, d in bandmap.items():
            key = (regime, band)
            {"SHIP": ship_cells, "MARGIN": margin_cells,
             "SKIP": skip_cells, "THIN": thin_cells}[d["verdict"]].append(key)

    L("=" * 100)
    L("ROLLUP (L6 BASELINE)")
    L("=" * 100)
    total = len(ship_cells) + len(margin_cells) + len(skip_cells) + len(thin_cells)
    L(f"  SHIP:   {len(ship_cells):>3} cells")
    L(f"  MARGIN: {len(margin_cells):>3} cells")
    L(f"  SKIP:   {len(skip_cells):>3} cells")
    L(f"  THIN:   {len(thin_cells):>3} cells   (below MIN_N_CELL={MIN_N_CELL})")
    L(f"  total judged: {total}")
    L("")

    L("=" * 100)
    L("DIFF vs LIVE curated JSON")
    L("=" * 100)
    L(f"Live SHIP+MARGIN: {len(live_ship_set)} cells (chp currently ENABLED on these).")
    L(f"New SHIP (post-rebuild): {len(ship_cells)} cells.")
    L(f"New SHIP+MARGIN (post-rebuild): {len(ship_cells) + len(margin_cells)} cells.")
    L("")
    if flip_ship_to_skip:
        L(f"⚠ {len(flip_ship_to_skip)} live cell(s) flip → SKIP under L6 baseline (chp materially loses vs Lc here):")
        for r, b, d in sorted(flip_ship_to_skip, key=lambda x: (x[0], x[1])):
            L(f"    {r:<12}/{b:<6}  Δ={d:+.2f}%")
        worst_r, worst_b, worst_d = max(flip_ship_to_skip, key=lambda x: x[2])
        L("")
        L(f"Verdict: WATCH — {len(flip_ship_to_skip)} live chp cell(s) lose to L6 baseline; worst {worst_r}/{worst_b} Δ={worst_d:+.2f}%. See NEXT STEPS below.")
    else:
        L("✓ No live SHIP/MARGIN cell flips to SKIP under L6 baseline.")
        L("")
        L("Verdict: CLEAN — no live chp cell loses to L6 baseline in this window.")
    if flip_ship_to_margin:
        L(f"⚠ {len(flip_ship_to_margin)} live cell(s) go to THIN (n < {MIN_N_CELL} in the 10-day window):")
        for r, b, v in sorted(flip_ship_to_margin, key=lambda x: (x[0], x[1])):
            L(f"    {r:<12}/{b:<6}  new_verdict={v}")
    if new_ship:
        L(f"→ {len(new_ship)} cell(s) NEW SHIP under L6 baseline (not currently live):")
        for r, b, d in sorted(new_ship, key=lambda x: (x[0], x[1])):
            L(f"    {r:<12}/{b:<6}  Δ={d:+.2f}%")
    L("")
    L("=" * 100)
    L("NEXT STEPS (per project_chp_midlead_regression_watch escalation playbook)")
    L("=" * 100)
    if flip_ship_to_skip:
        L(f"1. {len(flip_ship_to_skip)} live cells lose to Lc under the corrected baseline —")
        L(f"   these are the mid-lead regression cells.")
        L(f"2. To ship the demote: copy this preview to")
        L(f"   weather_collector/data/ch_persistence_gate_curated.json + deploy collector.")
        L(f"   OR promote this script to the SHIPPED Stage 2, regenerate, and let the")
        L(f"   normal Stage 2 authority own the update.")
        L(f"3. Live-layer change gate applies: 7 daily reads / 2-tool / per-cell / no-ENT")
        L(f"   before flipping — this run is day 1 of that gate.")
    else:
        L(f"No demotes signaled tonight. If h_chp_midlead_regression.py still fires")
        L(f"ESCALATE with fresh data tomorrow, re-run this to confirm.")
    L("")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "forecast_error_log.jsonl",
        "field": FIELD,
        "baseline": "forecast_l6 (Lc-corrected)",
        "windows": {
            "A_recent_5d": [WIN_A_LO, WIN_A_HI],
            "B_prior_5d":  [WIN_B_LO, WIN_B_HI],
            "FULL_10d":    [WIN_FULL_LO, WIN_FULL_HI],
        },
        "fit_rules": {
            "min_n_cell": MIN_N_CELL,
            "mae_improve_floor_pct": MAE_IMPROVE_FLOOR_PCT,
            "halves_stability_required": True,
            "lead_bands": bands,
        },
        "gate": {
            "persistence_source": "hour-floor of run_time in ch obs index",
            "frontal_uses_L6": True,
            "additional_skips": [
                {"regime": r, "lead_band": b} for r, b in sorted(skip_cells)
            ],
        },
        "cells": cells,
        "rollup": {
            "ship": len(ship_cells),
            "margin": len(margin_cells),
            "skip": len(skip_cells),
            "thin": len(thin_cells),
        },
        "diff_vs_live": {
            "live_ship_or_margin_count": len(live_ship_set),
            "flip_ship_to_skip": [
                {"regime": r, "band": b, "delta_full_pct": d}
                for r, b, d in flip_ship_to_skip
            ],
            "flip_ship_to_thin": [
                {"regime": r, "band": b, "new_verdict": v}
                for r, b, v in flip_ship_to_margin
            ],
            "new_ship_not_live": [
                {"regime": r, "band": b, "delta_full_pct": d}
                for r, b, d in new_ship
            ],
        },
        "notes": (
            "L6-BASELINE variant preview. Not wired. Writes to _vs_l6 suffix so "
            "the live ch_persistence_gate_curated.json is untouched. Ship path: "
            "promote this script to the shipped Stage 2 OR copy this JSON's cells "
            "onto the live curated JSON. Live-layer change gate applies before "
            "flipping."
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
    emit(compute())
