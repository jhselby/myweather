"""Stage 2 preview — cl regime-gated persistence blend.

Follow-on to Stage 0-1 (h_cl_persistence_blend.py), which verified on
halves-stability that a regime-gate (frontal→baseline, else persistence)
beats baseline pooled cl MAE.

Stage 2 preview answers: does the gate hold PER-CELL (regime × lead_band),
or does persistence decay at long leads inside some winning regimes?
If any winning regime shows SKIP at 24-47h, the shipped gate needs a
second condition (frontal → baseline, lead>=24 → baseline, else persistence).

For cl, "baseline" = forecast_l4 field in the pair log = raw L1 forecast
(cl has no L4 correction). The gate falls back to baseline, not to L4,
because there is no L4 to fall back to.

Windows match Stage 1 exactly (30d, split into recent 15d + prior 15d halves)
so the pooled numbers reconcile.

Persistence definition: flat carry of the joined cl observation at
forecast issue time (hour-floor of run_time). Must match production.

Per-cell verdict rules:
  SHIP   — n >= MIN_N and gate MAE beats baseline by >= MAE_IMPROVE_FLOOR_PCT
           on BOTH halves AND full window (halves-stability required)
  MARGIN — gate beats on full but one half is < floor
  SKIP   — gate loses on full or halves disagree in sign
  THIN   — n < MIN_N in any window

Emits:
  analysis/output/h_cl_persistence_blend_stage2.txt
  weather_collector/data/cl_persistence_gate_curated.json   (preview, not wired)
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_TXT = os.path.join(HERE, "output", "h_cl_persistence_blend_stage2.txt")
OUT_JSON = os.path.abspath(os.path.join(
    HERE, "..", "weather_collector", "data", "cl_persistence_gate_curated.json"
))

# Windows mirror h_cl_persistence_blend.py exactly. If you slide one, slide both.
WIN_A_LO, WIN_A_HI = "2026-07-08T00:00", "2026-07-23T00:00"
WIN_B_LO, WIN_B_HI = "2026-06-23T00:00", "2026-07-08T00:00"
WIN_FULL_LO, WIN_FULL_HI = "2026-06-23T00:00", "2026-07-23T00:00"

FIELD = "cl"
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


def compute():
    path = cached_path(URL)

    print("[1/2] Building cl obs index...", file=sys.stderr)
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
    print(f"    cl obs index size: {len(obs_ts):,}", file=sys.stderr)

    print("[2/2] Scoring cl scenarios per (regime x lead_band)...", file=sys.stderr)
    accum = defaultdict(lambda: {"n": 0, "ae": 0.0, "se": 0.0})
    n_joined = 0
    n_orphan = 0

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
            fc4 = r.get("forecast_l4")
            if ob is None or fc4 is None:
                continue

            persist = obs_ts.get(hour_floor(rt))
            if persist is None:
                n_orphan += 1
                continue
            n_joined += 1

            state_fc = r.get("state_fc") or {}
            regime = state_fc.get("regime_synoptic") or "unknown"

            fc_baseline = fc4
            fc_regime_gate = fc4 if regime == "frontal" else persist
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

    print(f"    joined {n_joined:,} cl rows; {n_orphan:,} orphans", file=sys.stderr)
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


def emit(accum):
    regimes = sorted({key[2] for key in accum.keys()})
    bands = [name for name, _, _ in LEAD_BANDS]

    lines = []
    lines.append("=" * 100)
    lines.append("cl REGIME-GATED PERSISTENCE BLEND - Stage 2 preview (per regime x lead_band)")
    lines.append("=" * 100)
    lines.append("")
    lines.append("Gate under test: forecast = baseline if regime==frontal else persistence-of-obs.")
    lines.append("Baseline for cl = forecast_l4 field = raw L1 (cl has no L4 correction).")
    lines.append("Per-cell verdict requires halves-stability + full window > 3.0% improvement.")
    lines.append("")

    lines.append("=" * 100)
    lines.append("PER-CELL: regime_gate vs baseline")
    lines.append("=" * 100)
    header = (f"{'regime':<12}{'band':<8}{'n':>8}"
              f"{'base MAE':>10}{'gate MAE':>10}"
              f"{'d full %':>10}{'d A %':>9}{'d B %':>9}  verdict")
    lines.append(header)
    lines.append("-" * len(header))

    cells = {}
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
            star = " *" if verdict == "SHIP" else ""
            d_full_s = f"{d_full:+.2f}" if d_full is not None else "  n/a"
            d_a_s    = f"{d_a:+.2f}" if d_a is not None else "  n/a"
            d_b_s    = f"{d_b:+.2f}" if d_b is not None else "  n/a"
            lines.append(f"{regime:<12}{band:<8}{n_full:>8,}"
                         f"{base_f:>10.3f}{gate_f:>10.3f}"
                         f"{d_full_s:>10}{d_a_s:>9}{d_b_s:>9}  {verdict}{star}")
            cells.setdefault(regime, {})[band] = {
                "n": n_full,
                "mae_base": round(base_f, 3),
                "mae_gate": round(gate_f, 3),
                "delta_full_pct": round(d_full, 2) if d_full is not None else None,
                "delta_a_pct": round(d_a, 2) if d_a is not None else None,
                "delta_b_pct": round(d_b, 2) if d_b is not None else None,
                "verdict": verdict,
            }
        lines.append("")

    lines.append("=" * 100)
    lines.append("PERSISTENCE-ONLY vs baseline (does persistence hold at long leads inside winning regimes?)")
    lines.append("=" * 100)
    header2 = (f"{'regime':<12}{'band':<8}{'n':>8}"
               f"{'base MAE':>10}{'pers MAE':>10}{'d full %':>10}  note")
    lines.append(header2)
    lines.append("-" * len(header2))
    for regime in regimes:
        if regime == "frontal":
            continue
        for band in bands:
            base_f = mae(accum[("FULL", "baseline", regime, band)])
            pers_f = mae(accum[("FULL", "persist_only", regime, band)])
            n_full = accum[("FULL", "baseline", regime, band)]["n"]
            if n_full < MIN_N_CELL or base_f is None or pers_f is None:
                continue
            d = 100.0 * (pers_f - base_f) / base_f if base_f else 0.0
            note = ""
            if d > 0:
                note = "persistence loses"
            elif d < -MAE_IMPROVE_FLOOR_PCT:
                note = "* persistence wins"
            lines.append(f"{regime:<12}{band:<8}{n_full:>8,}"
                         f"{base_f:>10.3f}{pers_f:>10.3f}{d:>+10.2f}  {note}")
        lines.append("")

    ship_cells = []
    skip_cells = []
    margin_cells = []
    thin_cells = []
    for regime, bandmap in cells.items():
        for band, d in bandmap.items():
            key = (regime, band)
            {"SHIP": ship_cells, "SKIP": skip_cells,
             "MARGIN": margin_cells, "THIN": thin_cells}[d["verdict"]].append(key)

    lines.append("=" * 100)
    lines.append("ROLLUP")
    lines.append("=" * 100)
    total = len(ship_cells) + len(skip_cells) + len(margin_cells) + len(thin_cells)
    lines.append(f"  SHIP:   {len(ship_cells):>3} cells")
    lines.append(f"  MARGIN: {len(margin_cells):>3} cells")
    lines.append(f"  SKIP:   {len(skip_cells):>3} cells")
    lines.append(f"  THIN:   {len(thin_cells):>3} cells")
    lines.append(f"  total judged: {total}")
    lines.append("")

    skip_by_band = defaultdict(list)
    skip_by_regime = defaultdict(list)
    for regime, band in skip_cells:
        skip_by_band[band].append(regime)
        skip_by_regime[regime].append(band)

    lines.append("SKIP concentration:")
    for band, regs in sorted(skip_by_band.items()):
        lines.append(f"  band {band:<6}: {len(regs)} regimes -> {sorted(regs)}")
    for regime, bnds in sorted(skip_by_regime.items()):
        lines.append(f"  regime {regime:<12}: {len(bnds)} bands -> {sorted(bnds)}")
    lines.append("")

    # Two candidate gate shapes; the shorter one is easier to reason about.
    # Blacklist: persistence by default, list SKIP cells as exceptions.
    # Whitelist: baseline by default, list SHIP+MARGIN cells as exceptions.
    # frontal is excluded from the whitelist because the gate contract
    # forces frontal->baseline; its MARGIN 0.0% cells are a definitional
    # artifact (gate_mae == base_mae by construction), not a persistence win.
    persist_cells = sorted(
        (r, b) for r, b in ship_cells + margin_cells if r != "frontal"
    )
    n_blacklist = 1 + len(skip_cells)  # frontal rule + skips
    n_whitelist = len(persist_cells)
    shorter = "whitelist" if n_whitelist < n_blacklist else "blacklist"

    lines.append("=" * 100)
    lines.append(f"PROPOSED GATE SHAPE — comparison ({n_blacklist} blacklist rules vs "
                 f"{n_whitelist} whitelist rules; shorter = {shorter})")
    lines.append("=" * 100)

    lines.append("")
    lines.append("[A] BLACKLIST shape: persistence by default, baseline on exceptions")
    lines.append("  base rule: forecast = persistence-of-obs (flat carry)")
    lines.append("  fall back to baseline (raw L1) when:")
    lines.append("    - regime == 'frontal' (design; baseline is the only winner there)")
    if skip_cells:
        for regime, band in sorted(skip_cells):
            lines.append(f"    - regime == '{regime}' AND lead_band == '{band}'  (Stage 2 SKIP)")
    else:
        lines.append("    (no additional per-cell skips required)")
    lines.append("")

    lines.append("[B] WHITELIST shape: baseline by default, persistence on winners")
    lines.append("  base rule: forecast = baseline (raw L1)")
    lines.append("  use persistence-of-obs when:")
    if persist_cells:
        for regime, band in persist_cells:
            v = cells[regime][band]["verdict"]
            d = cells[regime][band]["delta_full_pct"]
            lines.append(f"    - regime == '{regime}' AND lead_band == '{band}'  "
                         f"(Stage 2 {v}, {d:+.1f}%)")
    else:
        lines.append("    (no winning cells)")
    lines.append("")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "forecast_error_log.jsonl",
        "field": FIELD,
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
        },
        "gate": {
            "persistence_source": "hour-floor of run_time in cl obs index (matches Stage 1)",
            "frontal_uses_baseline": True,
            "baseline_definition": "forecast_l4 field = raw L1 (cl has no L4)",
            "shorter_shape": shorter,
            "blacklist": {
                "n_rules": n_blacklist,
                "additional_skips": [
                    {"regime": r, "lead_band": b} for r, b in sorted(skip_cells)
                ],
            },
            "whitelist": {
                "n_rules": n_whitelist,
                "persist_cells": [
                    {
                        "regime": r,
                        "lead_band": b,
                        "verdict": cells[r][b]["verdict"],
                        "delta_full_pct": cells[r][b]["delta_full_pct"],
                    }
                    for r, b in sorted(persist_cells)
                ],
            },
        },
        "cells": cells,
        "rollup": {
            "ship": len(ship_cells),
            "margin": len(margin_cells),
            "skip": len(skip_cells),
            "thin": len(thin_cells),
        },
        "notes": (
            "Stage 2 preview only. Not wired to production. Persistence = flat-carry "
            "of the joined cl obs at forecast issue time. Cells with verdict=SHIP or "
            "MARGIN use persistence at runtime; SKIP + frontal fall back to baseline "
            "(raw L1). Wire via a new cl_persistence_gate processor with ENABLED=False "
            "on ship and a 7-day gate before enabling."
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
