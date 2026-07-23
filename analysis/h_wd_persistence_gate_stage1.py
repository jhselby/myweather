"""Stage 1 preview — wd persistence gate per (regime × lead_band).

Follow-on to [[regime_transition_audit]] Stage 0 verdict: wind direction
(wd) shows +93-111% MAE penalty on rows where state_fc.regime_synoptic
!= state_obs.regime_synoptic. wd has NO L2/L3/L4/L5/Lc corrections wired
today — the pair log's `forecast` value for wd is the raw HRRR (L1) with
station blending in some cases via wind_blend.py, but no forecast-side
correction layer. So the transition penalty is L1's alone.

This Stage 1 tests the obvious corrective: replace L1 wd with
persistence-of-obs (last observed wd at forecast issue time) in cells
where persistence beats L1 stably. Fire condition (state_fc.regime + band)
is available at forecast time — same architecture as
[[ch_persistence_gate_ship]].

Circular arithmetic: wd is periodic on [0, 360). All differences use
angular_diff = min(|a-b|, 360-|a-b|), yielding values in [0, 180].

Windows mirror the ch persistence blend Stage 2 exactly (30d well-stamped,
split into recent 15d + prior 15d halves) so numbers reconcile with the
sibling scripts.

Per-cell verdict rules (baseline = L1, gated = persistence):
  SHIP   — n >= MIN_N and persistence MAE beats L1 by >= MAE_IMPROVE_FLOOR_PCT
           on BOTH halves AND full window (halves-stability required)
  MARGIN — persistence wins full but one half is < floor
  SKIP   — persistence loses on full or halves disagree in sign
  THIN   — n < MIN_N in any window

Emits:
  analysis/output/h_wd_persistence_gate_stage1.txt
  weather_collector/data/wd_persistence_gate_curated.json   (preview, not wired)
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_TXT = os.path.join(HERE, "output", "h_wd_persistence_gate_stage1.txt")
OUT_JSON = os.path.abspath(os.path.join(
    HERE, "..", "weather_collector", "data", "wd_persistence_gate_curated.json"
))

# Mirror ch persistence blend windows: post-06-30 mixture-shift seam split.
WIN_A_LO, WIN_A_HI = "2026-07-08T00:00", "2026-07-23T00:00"
WIN_B_LO, WIN_B_HI = "2026-06-23T00:00", "2026-07-08T00:00"
WIN_FULL_LO, WIN_FULL_HI = "2026-06-23T00:00", "2026-07-23T00:00"

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
    """Absolute angular difference on [0, 180]. a, b in degrees on [0, 360)."""
    d = abs(float(a) - float(b)) % 360.0
    return d if d <= 180.0 else 360.0 - d


def compute():
    path = cached_path(URL)

    print("[1/2] Building wd obs index...", file=sys.stderr)
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
                obs_ts[vt] = float(ob)
    print(f"    wd obs index size: {len(obs_ts):,}", file=sys.stderr)

    # accum[(window, scenario, regime, band, transition)] = {n, ae}
    # transition ∈ {"stable", "transition", "all"}
    print("[2/2] Scoring wd L1 vs persistence per (regime × lead_band × transition)...",
          file=sys.stderr)
    accum = defaultdict(lambda: {"n": 0, "ae": 0.0})
    n_joined = 0
    n_orphan = 0
    n_missing_state = 0

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
                n_orphan += 1
                continue

            state_fc = r.get("state_fc") or {}
            state_obs = r.get("state_obs") or {}
            regime = state_fc.get("regime_synoptic") or "unknown"
            regime_obs = state_obs.get("regime_synoptic")
            if regime_obs is None:
                n_missing_state += 1
                trans_slot = "all"
            elif regime_obs == state_fc.get("regime_synoptic"):
                trans_slot = "stable"
            else:
                trans_slot = "transition"

            n_joined += 1

            err_l1 = angular_diff(fc, ob)
            err_pers = angular_diff(persist, ob)

            for win in windows:
                # All rows go into (scenario, regime, band, "all") for the
                # overall gate decision. Transition-split cells also feed
                # (scenario, regime, band, transition_slot) for diagnostics.
                for slot in ("all", trans_slot):
                    a = accum[(win, "l1", regime, band, slot)]
                    a["n"] += 1
                    a["ae"] += err_l1
                    a = accum[(win, "persist", regime, band, slot)]
                    a["n"] += 1
                    a["ae"] += err_pers

    print(f"    joined {n_joined:,} wd rows; {n_orphan:,} orphans; "
          f"{n_missing_state:,} missing state_obs", file=sys.stderr)
    return accum


def mae(bkt):
    n = bkt["n"]
    return (bkt["ae"] / n) if n else None


def cell_verdict(l1_full, pers_full, l1_a, pers_a, l1_b, pers_b, n_full):
    if n_full < MIN_N_CELL:
        return "THIN", None, None, None
    if l1_full is None or pers_full is None:
        return "THIN", None, None, None
    d_full = 100.0 * (pers_full - l1_full) / l1_full if l1_full else 0.0
    d_a = 100.0 * (pers_a - l1_a) / l1_a if (l1_a and pers_a is not None) else None
    d_b = 100.0 * (pers_b - l1_b) / l1_b if (l1_b and pers_b is not None) else None
    # SHIP: persistence beats L1 (negative Δ) on full AND both halves >= floor
    if (d_full <= -MAE_IMPROVE_FLOOR_PCT
        and d_a is not None and d_a <= -MAE_IMPROVE_FLOOR_PCT
        and d_b is not None and d_b <= -MAE_IMPROVE_FLOOR_PCT):
        return "SHIP", d_full, d_a, d_b
    # SKIP: persistence loses full OR halves disagree in sign
    if d_full > 0 or (d_a is not None and d_b is not None and (d_a * d_b) < 0):
        return "SKIP", d_full, d_a, d_b
    return "MARGIN", d_full, d_a, d_b


def emit(accum):
    regimes = sorted({key[2] for key in accum.keys()})
    bands = [name for name, _, _ in LEAD_BANDS]

    lines = []
    lines.append("=" * 100)
    lines.append("wd PERSISTENCE GATE — Stage 1 preview (per regime × lead_band, halves-verified)")
    lines.append("=" * 100)
    lines.append("")
    lines.append("Gate under test: forecast = persistence-of-obs (flat carry of latest hourly wd obs).")
    lines.append("Baseline: L1 (raw HRRR wd; no L2/L3/L4 corrections wired for wd today).")
    lines.append(f"Per-cell verdict requires halves-stability + full window > {MAE_IMPROVE_FLOOR_PCT}% MAE improvement.")
    lines.append(f"Windows: A={WIN_A_LO[:10]}→{WIN_A_HI[:10]}, "
                 f"B={WIN_B_LO[:10]}→{WIN_B_HI[:10]}, FULL={WIN_FULL_LO[:10]}→{WIN_FULL_HI[:10]}")
    lines.append(f"MIN_N per cell: {MIN_N_CELL}")
    lines.append("Angular arithmetic: MAE uses min(|Δ|, 360-|Δ|), so values are on [0, 180].")
    lines.append("")

    # === Per-cell table (all rows) ===
    lines.append("=" * 100)
    lines.append("PER-CELL: persistence vs L1 (all rows)")
    lines.append("=" * 100)
    header = (f"{'regime':<12}{'band':<8}{'n':>8}"
              f"{'L1 MAE':>10}{'pers MAE':>10}"
              f"{'Δ full %':>10}{'Δ A %':>9}{'Δ B %':>9}  verdict")
    lines.append(header)
    lines.append("-" * len(header))

    cells = {}
    for regime in regimes:
        for band in bands:
            l1_f = mae(accum[("FULL", "l1", regime, band, "all")])
            pers_f = mae(accum[("FULL", "persist", regime, band, "all")])
            l1_a = mae(accum[("A", "l1", regime, band, "all")])
            pers_a = mae(accum[("A", "persist", regime, band, "all")])
            l1_b = mae(accum[("B", "l1", regime, band, "all")])
            pers_b = mae(accum[("B", "persist", regime, band, "all")])
            n_full = accum[("FULL", "l1", regime, band, "all")]["n"]
            if n_full == 0 or l1_f is None or pers_f is None:
                continue
            verdict, d_full, d_a, d_b = cell_verdict(
                l1_f, pers_f, l1_a, pers_a, l1_b, pers_b, n_full
            )
            star = " ★" if verdict == "SHIP" else ""
            d_full_s = f"{d_full:+.2f}" if d_full is not None else "  n/a"
            d_a_s    = f"{d_a:+.2f}"    if d_a    is not None else "  n/a"
            d_b_s    = f"{d_b:+.2f}"    if d_b    is not None else "  n/a"
            lines.append(f"{regime:<12}{band:<8}{n_full:>8,}"
                         f"{l1_f:>10.3f}{pers_f:>10.3f}"
                         f"{d_full_s:>10}{d_a_s:>9}{d_b_s:>9}  {verdict}{star}")
            cells.setdefault(regime, {})[band] = {
                "n": n_full,
                "mae_l1": round(l1_f, 3),
                "mae_persist": round(pers_f, 3),
                "delta_full_pct": round(d_full, 2) if d_full is not None else None,
                "delta_a_pct": round(d_a, 2) if d_a is not None else None,
                "delta_b_pct": round(d_b, 2) if d_b is not None else None,
                "verdict": verdict,
            }
        lines.append("")

    # === Transition vs stable split (diagnostic — where does the gain concentrate?) ===
    lines.append("=" * 100)
    lines.append("TRANSITION vs STABLE split (does persistence gain concentrate on transition rows?)")
    lines.append("=" * 100)
    hdr2 = (f"{'regime':<12}{'band':<8}{'slot':<11}{'n':>8}"
            f"{'L1 MAE':>10}{'pers MAE':>10}{'Δ %':>9}")
    lines.append(hdr2)
    lines.append("-" * len(hdr2))
    for regime in regimes:
        for band in bands:
            for slot in ("stable", "transition"):
                l1_f = mae(accum[("FULL", "l1", regime, band, slot)])
                pers_f = mae(accum[("FULL", "persist", regime, band, slot)])
                n = accum[("FULL", "l1", regime, band, slot)]["n"]
                if n < MIN_N_CELL or l1_f is None or pers_f is None:
                    continue
                d = 100.0 * (pers_f - l1_f) / l1_f if l1_f else 0.0
                mark = ""
                if d <= -MAE_IMPROVE_FLOOR_PCT: mark = " ★"
                elif d >= MAE_IMPROVE_FLOOR_PCT: mark = " ⚠"
                lines.append(f"{regime:<12}{band:<8}{slot:<11}{n:>8,}"
                             f"{l1_f:>10.3f}{pers_f:>10.3f}{d:>+9.2f}{mark}")
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
    total = len(ship_cells) + len(skip_cells) + len(margin_cells) + len(thin_cells)
    lines.append(f"  SHIP:   {len(ship_cells):>3} cells")
    lines.append(f"  MARGIN: {len(margin_cells):>3} cells")
    lines.append(f"  SKIP:   {len(skip_cells):>3} cells")
    lines.append(f"  THIN:   {len(thin_cells):>3} cells")
    lines.append(f"  total judged: {total}")
    lines.append("")

    lines.append("=" * 100)
    lines.append("PROPOSED GATE SHAPE")
    lines.append("=" * 100)
    if ship_cells or margin_cells:
        lines.append("  base rule: forecast = L1 (current behavior)")
        lines.append("  override with persistence-of-obs when:")
        for regime, band in sorted(ship_cells + margin_cells):
            verdict = cells[regime][band]["verdict"]
            lines.append(f"    - regime == '{regime}' AND lead_band == '{band}'  ({verdict})")
    else:
        lines.append("  no cells cleared halves-stable ship gate — persistence does not")
        lines.append("  systematically beat L1 for wd at cell granularity in this window.")
    lines.append("")

    # ── verdict for the digest exec summary ───────────────────────────
    if len(ship_cells) >= 2:
        overall = f"Verdict: STAGE 1 HIT — {len(ship_cells)} SHIP cell(s) at floor {MAE_IMPROVE_FLOOR_PCT}%. Move to Stage 2 wiring + halves re-check."
    elif ship_cells:
        overall = f"Verdict: MARGINAL — {len(ship_cells)} SHIP cell + {len(margin_cells)} MARGIN. Re-run after 3-day window roll."
    else:
        overall = f"Verdict: HOLD — no cells cleared halves-stable floor. wd persistence gate not viable at (regime × band) granularity."
    lines.append(overall)
    lines.append("")

    # === JSON payload ===
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
            "arithmetic": "circular_angular_diff",
        },
        "gate": {
            "persistence_source": "hour-floor of run_time in wd obs index",
            "baseline": "L1 (raw HRRR forecast; no correction layers wired for wd)",
            "fire_cells": [
                {"regime": r, "lead_band": b, "verdict": cells[r][b]["verdict"]}
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
            "Stage 1 preview only. Not wired to production. Persistence = "
            "flat-carry of the joined wd obs at forecast issue time. Follow-on "
            "to regime_transition_audit Stage 0 (wd +93-111% transition penalty). "
            "Wire via a new wd_persistence_gate processor with ENABLED=False on "
            "ship and a 7-day gate before enabling."
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
