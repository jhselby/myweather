#!/usr/bin/env python3
"""NBM walkforward validator (F2, 2026-08-21).

Companion to `walkforward_l3l4_validator.py` for the NBM cascade. Where the
HRRR walkforward proposes L3_FIELDS / L4_FIELDS whitelists, this proposes
L3_NBM_FIELDS / L4_NBM_FIELDS and diffs them against the hard-coded live
whitelists in `l3_nbm.py` / `l4_nbm.py`. Digest SHIP-ELIGIBLE section reads
the JSON to surface divergence.

Method:
  1. Stream pair-log rows (live + backstamp) for the last WINDOW_DAYS.
  2. Per (field, layer, band), aggregate MAE from `error_{layer}`.
  3. Compare each layer's MAE against the layer immediately shallower
     (l3_nbm vs l2_nbm; l4_nbm vs l3_nbm; l5_nbm vs l3_nbm since sr skips
     L4_NBM; l6_nbm vs l3_nbm since t skips L4_NBM+L5_NBM; chp_nbm vs
     l4_nbm; wdp_nbm vs l3_nbm).
  4. Whitelist rule: layer earns membership for a field if aggregate
     (all-bands) lift ≥ FIELD_WIN_PCT AND paired_n ≥ MIN_N.
  5. Emit proposed L3_NBM_FIELDS / L4_NBM_FIELDS / etc. and diff vs the
     runtime-live tuples.

Run:
    python3 analysis/nbm_walkforward_validator.py

Output:
    analysis/output/nbm_walkforward.txt
    analysis/output/nbm_walkforward.json
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import pair_log_paths  # noqa: E402

sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
from weather_collector.processors.l3_nbm import L3_NBM_FIELDS as LIVE_L3
from weather_collector.processors.l4_nbm import L4_NBM_FIELDS as LIVE_L4
from weather_collector.processors.l6_nbm import L6_NBM_FIELDS as LIVE_L6  # noqa
LIVE_L5 = ("sr",)  # l5_nbm.py has no module-level FIELDS tuple; sr-only by design

OUT_TXT = os.path.join(SCRIPT_DIR, "output", "nbm_walkforward.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "nbm_walkforward.json")

WINDOW_DAYS = 14
MIN_N = 200
FIELD_WIN_PCT = 2.0   # aggregate lift %; matches HRRR walkforward gate
SKIP_CELL_LOSS_PCT = 3.0   # per-band lift ≤ -this fires a skip_table_nbm proposal
SKIP_CELL_MIN_N = 200      # per-band paired n floor to trust the proposal

BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]

# For each candidate layer: which shallower layer is the baseline it must
# beat, and which fields it may apply to. Order matches apply-time cascade.
COMPARE = [
    ("l3_nbm", "l2_nbm", ("t", "ws", "wg", "h", "ch", "sr", "dp", "cc", "wd")),
    ("l4_nbm", "l3_nbm", ("cc", "ch")),
    ("l5_nbm", "l3_nbm", ("sr",)),
    ("l6_nbm", "l3_nbm", ("t",)),
    ("chp_nbm", "l4_nbm", ("ch",)),
    ("wdp_nbm", "l3_nbm", ("wd",)),
]

LIVE_WHITELIST = {
    "l3_nbm": set(LIVE_L3),
    "l4_nbm": set(LIVE_L4),
    "l5_nbm": set(LIVE_L5),
    "l6_nbm": set(LIVE_L6),
    "chp_nbm": {"ch"},   # runtime gate always applies to ch when chp table cell fires
    "wdp_nbm": {"wd"},
}


def _band_of(lead_h):
    if lead_h is None:
        return None
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def fit():
    now = datetime.utcnow()
    window_start = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M")

    # acc[(field, layer, band)] = [|err|...]
    acc = defaultdict(list)
    # paired_acc[(field, cand, base, band)] = (Σ|err_cand|, Σ|err_base|, n)
    paired = defaultdict(lambda: [0.0, 0.0, 0])
    # Regime × band cross-cut. Regime = row's state_fc.regime_synoptic
    # (matches runtime skip check + HRRR walkforward's fc-side view).
    # paired_by_regime[(field, cand, base, band, regime)] = same shape as paired.
    paired_by_regime = defaultdict(lambda: [0.0, 0.0, 0])

    for path in pair_log_paths():
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                field = r.get("field")
                if field is None:
                    continue
                if r.get("obs_time", "") < window_start:
                    continue
                lead_h = r.get("lead_h")
                band = _band_of(lead_h)
                if band is None:
                    continue
                regime = ((r.get("state_fc") or {}).get("regime_synoptic")) or None
                for cand, base, fields in COMPARE:
                    if field not in fields:
                        continue
                    ec = r.get(f"error_{cand}")
                    eb = r.get(f"error_{base}")
                    # Backstamp identity filter: pre-08-21 rows carry
                    # error_l3_nbm == error_l2_nbm by construction (nbm_backstamp
                    # writes l3_nbm = l2_nbm when no curated L3 bias existed).
                    # Those rows are 0-lift noise for the l3 vs l2 comparison
                    # and drown out the real signal from live post-refit rows.
                    # Auto-sunset in ~28d as backstamped rows age out.
                    if (cand == "l3_nbm" and base == "l2_nbm"
                            and ec is not None and eb is not None
                            and abs(float(ec) - float(eb)) < 1e-6):
                        continue
                    if ec is not None:
                        acc[(field, cand, band)].append(abs(float(ec)))
                    if ec is not None and eb is not None:
                        p = paired[(field, cand, base, band)]
                        p[0] += abs(float(ec))
                        p[1] += abs(float(eb))
                        p[2] += 1
                        if regime:
                            pr = paired_by_regime[(field, cand, base, band, regime)]
                            pr[0] += abs(float(ec))
                            pr[1] += abs(float(eb))
                            pr[2] += 1

    # Roll up per (field, cand): aggregate across bands using paired samples.
    results = []
    proposed = defaultdict(set)
    # F5 (2026-08-21) — per-band SKIP proposals for skip_table_nbm.
    # Entry shape mirrors HRRR SKIP_TABLE cells: [regime, lead_lo, lead_hi].
    # Walkforward currently pools regimes, so proposed cells use "*" as a
    # placeholder regime — curator translates to per-regime cells when
    # regime cross-cut lands. skip_table_nbm treats "*" as "never matches"
    # (no unknown regime fires the wildcard), so these are advisory-only
    # until manually translated. Digest surfaces them under skip_proposals.
    skip_proposals = {ln: {} for ln, _, _ in COMPARE}
    for cand, base, fields in COMPARE:
        for field in fields:
            cand_sum = base_sum = 0.0
            paired_n = 0
            per_band = []
            for band, _, _ in BANDS:
                p = paired.get((field, cand, base, band))
                if not p:
                    per_band.append({"band": band, "n": 0})
                    continue
                cs, bs, n = p
                cand_sum += cs
                base_sum += bs
                paired_n += n
                mae_c = cs / n if n else None
                mae_b = bs / n if n else None
                lift = (100.0 * (mae_b - mae_c) / mae_b) if (mae_b and mae_b > 0) else None
                per_band.append({
                    "band": band, "n": n,
                    f"mae_{cand}": round(mae_c, 3) if mae_c is not None else None,
                    f"mae_{base}": round(mae_b, 3) if mae_b is not None else None,
                    "lift_pct": round(lift, 1) if lift is not None else None,
                })
                # F5 per-band SKIP proposal — now with regime cross-cut.
                # For each (band, regime) cell that hurts by ≥ threshold with
                # enough paired rows, emit a real per-regime cell drop-in for
                # skip_table_nbm_curated.json. The band's pooled "*" line is
                # kept only as informational fallback when no regime clears.
                _band_bounds = None
                for _lbl, _lo, _hi in BANDS:
                    if _lbl == band:
                        _band_bounds = (_lo, _hi)
                        break
                if _band_bounds is None:
                    continue
                _lo, _hi = _band_bounds
                _regime_hits = 0
                for (_f, _c, _b, _band, _regime), pr in paired_by_regime.items():
                    if (_f, _c, _b, _band) != (field, cand, base, band):
                        continue
                    rn = pr[2]
                    if rn < SKIP_CELL_MIN_N:
                        continue
                    r_mae_c = pr[0] / rn
                    r_mae_b = pr[1] / rn
                    if not r_mae_b or r_mae_b <= 0:
                        continue
                    r_lift = 100.0 * (r_mae_b - r_mae_c) / r_mae_b
                    if r_lift > -SKIP_CELL_LOSS_PCT:
                        continue
                    skip_proposals[cand].setdefault(field, []).append(
                        {"regime": _regime, "lead_lo": _lo, "lead_hi": _hi,
                         "band": band, "n": rn, "lift_pct": round(r_lift, 1)}
                    )
                    _regime_hits += 1
                # Fallback: no regime cleared but pooled band hurts — surface
                # the pooled cell as advisory-only (regime "*"), so we see
                # something is off even before per-regime n's thicken.
                if (_regime_hits == 0 and lift is not None
                        and n >= SKIP_CELL_MIN_N and lift <= -SKIP_CELL_LOSS_PCT):
                    skip_proposals[cand].setdefault(field, []).append(
                        {"regime": "*", "lead_lo": _lo, "lead_hi": _hi,
                         "band": band, "n": n, "lift_pct": round(lift, 1),
                         "note": "pooled — no single regime cleared n floor"}
                    )
            agg_mae_c = cand_sum / paired_n if paired_n else None
            agg_mae_b = base_sum / paired_n if paired_n else None
            agg_lift = (100.0 * (agg_mae_b - agg_mae_c) / agg_mae_b) if (agg_mae_b and agg_mae_b > 0) else None
            verdict = "THIN"
            if paired_n >= MIN_N and agg_lift is not None:
                verdict = "EARN" if agg_lift >= FIELD_WIN_PCT else "SKIP"
            if verdict == "EARN":
                proposed[cand].add(field)
            results.append({
                "field": field,
                "candidate": cand,
                "baseline": base,
                "paired_n": paired_n,
                f"agg_mae_{cand}": round(agg_mae_c, 3) if agg_mae_c is not None else None,
                f"agg_mae_{base}": round(agg_mae_b, 3) if agg_mae_b is not None else None,
                "agg_lift_pct": round(agg_lift, 1) if agg_lift is not None else None,
                "verdict": verdict,
                "per_band": per_band,
            })

    # Divergence vs live whitelist.
    divergence = {}
    for cand, base, fields in COMPARE:
        live = LIVE_WHITELIST.get(cand, set())
        prop = proposed.get(cand, set())
        divergence[cand] = {
            "live": sorted(live),
            "proposed": sorted(prop),
            "add": sorted(prop - live),
            "drop": sorted(live - prop),
        }
    return results, divergence, skip_proposals


def emit(results, divergence, skip_proposals):
    lines = []
    lines.append("=" * 96)
    lines.append("NBM WALKFORWARD — per-layer field-membership proposal (14d window)")
    lines.append("=" * 96)
    lines.append(f"Whitelist rule: aggregate lift ≥ {FIELD_WIN_PCT:.1f}% AND paired_n ≥ {MIN_N}.")
    lines.append("Caveat: l3_nbm vs l2_nbm skips backstamp identity rows (err_l3 == err_l2), so its")
    lines.append("paired_n reflects only live post-refit rows since 2026-08-19. Auto-clears in ~28d.")
    lines.append("Deeper NBM layers (l4/l5/l6/chp/wdp) only start accumulating rows from their ship")
    lines.append("date (2026-08-21) — most cells will read THIN until the window fills.")
    lines.append("")

    hdr = f"{'field':<6}{'candidate':<10}{'vs':<8}{'paired_n':>10}{'MAE_base':>10}{'MAE_cand':>10}{'lift%':>8}{'verdict':>10}"
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for r in sorted(results, key=lambda x: (x["candidate"], x["field"])):
        cand = r["candidate"]; base = r["baseline"]
        mae_c = r.get(f"agg_mae_{cand}")
        mae_b = r.get(f"agg_mae_{base}")
        lift = r.get("agg_lift_pct")
        mae_c_s = f"{mae_c:.2f}" if mae_c is not None else "—"
        mae_b_s = f"{mae_b:.2f}" if mae_b is not None else "—"
        lift_s = f"{lift:+.1f}%" if lift is not None else "—"
        lines.append(
            f"{r['field']:<6}{cand:<10}{base:<8}{r['paired_n']:>10,}"
            f"{mae_b_s:>10}{mae_c_s:>10}{lift_s:>8}{r['verdict']:>10}"
        )
    lines.append("")

    lines.append("-" * 96)
    lines.append("Whitelist divergence (proposed vs live runtime):")
    lines.append("-" * 96)
    any_diff = False
    for cand in ("l3_nbm", "l4_nbm", "l5_nbm", "l6_nbm", "chp_nbm", "wdp_nbm"):
        d = divergence.get(cand) or {}
        add = d.get("add") or []
        drop = d.get("drop") or []
        if not add and not drop:
            lines.append(f"  {cand:<9} — unchanged  (live={','.join(d.get('live') or []) or '∅'})")
            continue
        any_diff = True
        parts = []
        if add:  parts.append(f"ADD {','.join(add)}")
        if drop: parts.append(f"DROP {','.join(drop)}")
        lines.append(f"  {cand:<9} — {'; '.join(parts)}   (live={','.join(d.get('live') or []) or '∅'} → prop={','.join(d.get('proposed') or []) or '∅'})")
    if not any_diff:
        lines.append("")
        lines.append("All NBM whitelists match live runtime. Nothing to ship.")

    # F5 per-band SKIP proposals (advisory; regime column is "*" wildcard —
    # translate manually to per-regime cells before dropping into
    # skip_table_nbm_curated.json). Empty when no per-band cell hits the
    # SKIP_CELL_LOSS_PCT / SKIP_CELL_MIN_N gate.
    lines.append("")
    lines.append("-" * 96)
    lines.append(f"Skip-table proposals (lift ≤ -{SKIP_CELL_LOSS_PCT:.0f}% AND n ≥ {SKIP_CELL_MIN_N}; per-regime cross-cut, fallback pooled *):")
    lines.append("-" * 96)
    any_prop = False
    for lyr in ("l3_nbm", "l4_nbm", "l5_nbm", "l6_nbm", "chp_nbm", "wdp_nbm"):
        by_field = skip_proposals.get(lyr) or {}
        for field, cells in sorted(by_field.items()):
            for c in cells:
                any_prop = True
                note = f"  [{c['note']}]" if c.get("note") else ""
                lines.append(
                    f"  {lyr:<9} {field:<3} {c['regime']:<12} {c['band']:<8} n={c['n']:>6,} lift={c['lift_pct']:+.1f}%{note}"
                )
    if not any_prop:
        lines.append("  (no per-band cells hit the skip threshold)")
    return "\n".join(lines)


def main():
    results, divergence, skip_proposals = fit()
    text = emit(results, divergence, skip_proposals)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "window_days": WINDOW_DAYS,
        "min_n": MIN_N,
        "field_win_pct": FIELD_WIN_PCT,
        "results": results,
        "divergence": divergence,
        "skip_proposals": skip_proposals,
        "skip_thresholds": {
            "loss_pct": SKIP_CELL_LOSS_PCT,
            "min_n": SKIP_CELL_MIN_N,
        },
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    print(f"wrote {OUT_JSON}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
