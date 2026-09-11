#!/usr/bin/env python3
"""NBM skip-table ADD-side two-window audit — mirror of nbm_skip_earning_audit
(REMOVE side, v0.6.572+v0.6.574). Cross-checks each 14d ADD proposal emitted
by nbm_walkforward_validator against a 50d long window, so single-window
regime-transient proposals don't ship as permanent skip cells.

The REMOVE side (v0.6.574) uses BOTH 14d fresh AND 50d long — 14d catches
freshness, 50d catches robustness; neither alone is sufficient. The ADD
side has been 14d-only since v0.6.462, letting regime-transient signals
through. This closes the asymmetry.

Verdicts per candidate (layer, field, regime, band):
  CONFIRMED — 14d lift ≤ -3%, n≥50; 50d lift ≤ -3%, n≥50; both halves of
              the 50d window agree on direction. Ship as skip cell.
  FRESH     — 14d cleared but 50d doesn't (either -3% floor or halves).
              Regime-transient; hold, do not ship.
  STALE     — 14d cleared but 50d shows the cell helping (lift > 0).
              Signal is a fresh window artifact; drop the proposal.
  THIN_50D  — 50d n < 50 for this cell. Wait for accumulation.

Runs analysis-only, no runtime effect. Downstream: build_executive_summary
adds a "NBM skip-ADD two-window audit" section grep'd from JSON output;
humans review CONFIRMED before shipping to skip_table_nbm_curated.json.

Runtime:
    python3 -m analysis.nbm_skip_add_audit
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import pair_log_paths
from analysis.nbm_regression_sentry import KILLED_LAYERS

REPO = Path(__file__).resolve().parent.parent
WALKFORWARD_JSON = REPO / "analysis" / "output" / "nbm_walkforward.json"
OUT_TXT = REPO / "analysis" / "output" / "nbm_skip_add_audit.txt"
OUT_JSON = REPO / "analysis" / "output" / "nbm_skip_add_audit.json"

LONG_WINDOW_DAYS = 50
MIN_N = 50
LIFT_PCT_FLOOR = -3.0   # cell must hurt by ≥ 3% (i.e. lift ≤ -3%) in both windows


def _load_proposals():
    if not WALKFORWARD_JSON.exists():
        print(f"missing {WALKFORWARD_JSON} — run nbm_walkforward_validator first",
              file=sys.stderr)
        return None
    r = json.loads(WALKFORWARD_JSON.read_text())
    return r.get("skip_proposals", {})


def _base_layer_for(cand):
    # Mirrors COMPARE in nbm_walkforward_validator.py — kept as a small
    # local map rather than a cross-import to keep this audit standalone.
    return {
        "l3_nbm": "l2_nbm",
        "l4_nbm": "l3_nbm",
        "l5_nbm": "l3_nbm",
        "l6_nbm": "l3_nbm",
        "chp_nbm": "l4_nbm",
        "wdp_nbm": "l3_nbm",
    }.get(cand)


def _accumulate_50d(proposals):
    # Build target set: {(field, cand, base, regime, lo, hi)}
    targets = {}
    for cand, fields in proposals.items():
        base = _base_layer_for(cand)
        if base is None:
            continue
        for field, cells in fields.items():
            # Skip proposals for (field, layer) pairs already killed — the
            # layer no longer touches that field, so skip cells there are moot.
            if (field, cand) in KILLED_LAYERS:
                continue
            for c in cells:
                key = (field, cand, base, c["regime"], c["lead_lo"], c["lead_hi"])
                targets[key] = c

    now = datetime.utcnow()
    window_start = (now - timedelta(days=LONG_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M")
    window_mid = (now - timedelta(days=LONG_WINDOW_DAYS // 2)).strftime("%Y-%m-%dT%H:%M")

    # acc[(field, cand, base, regime, lo, hi)] = {"h1": [Σec, Σeb, n], "h2": ..., "all": ...}
    acc = defaultdict(lambda: {"h1": [0.0, 0.0, 0], "h2": [0.0, 0.0, 0], "all": [0.0, 0.0, 0]})

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
                obs_time = r.get("obs_time", "")
                if obs_time < window_start:
                    continue
                field = r.get("field")
                lead_h = r.get("lead_h")
                regime = ((r.get("state_fc") or {}).get("regime_synoptic")) or None
                if field is None or lead_h is None or regime is None:
                    continue
                for (tf, cand, base, treg, lo, hi), _ in targets.items():
                    if tf != field or treg != regime:
                        continue
                    if not (lo <= lead_h < hi):
                        continue
                    ec = r.get(f"error_{cand}")
                    eb = r.get(f"error_{base}")
                    # Backstamp identity filter (mirror walkforward line 130-133).
                    if (cand == "l3_nbm" and base == "l2_nbm"
                            and ec is not None and eb is not None
                            and abs(float(ec) - float(eb)) < 1e-6):
                        continue
                    if ec is None or eb is None:
                        continue
                    slot = "h2" if obs_time >= window_mid else "h1"
                    b = acc[(field, cand, base, regime, lo, hi)]
                    ec_a, eb_a = abs(float(ec)), abs(float(eb))
                    b[slot][0] += ec_a
                    b[slot][1] += eb_a
                    b[slot][2] += 1
                    b["all"][0] += ec_a
                    b["all"][1] += eb_a
                    b["all"][2] += 1

    return acc, targets


def _lift_pct(bucket):
    ec_sum, eb_sum, n = bucket
    if n == 0 or eb_sum == 0:
        return None
    mae_cand = ec_sum / n
    mae_base = eb_sum / n
    return (mae_base - mae_cand) / mae_base * 100.0


def _verdict(cell_14d_lift, cell_14d_n, acc_bucket):
    lift_50d = _lift_pct(acc_bucket["all"])
    lift_h1 = _lift_pct(acc_bucket["h1"])
    lift_h2 = _lift_pct(acc_bucket["h2"])
    n_50d = acc_bucket["all"][2]
    if n_50d < MIN_N:
        return {"verdict": "THIN_50D", "n_50d": n_50d,
                "lift_50d": lift_50d, "lift_h1": lift_h1, "lift_h2": lift_h2}
    # For an ADD-side proposal, cell HURTS in 14d (lift ≤ -3%).
    # CONFIRMED: 50d also ≤ -3% AND both halves agree (both ≤ 0).
    # FRESH: 50d lift > -3% (weaker over long window; regime-transient).
    # STALE: 50d lift > 0 (cell actually helping over long window).
    if lift_50d is None:
        return {"verdict": "THIN_50D", "n_50d": n_50d,
                "lift_50d": None, "lift_h1": lift_h1, "lift_h2": lift_h2}
    if lift_50d > 0:
        verdict = "STALE"
    elif lift_50d > LIFT_PCT_FLOOR:
        verdict = "FRESH"
    else:
        # Both halves should agree on direction (both ≤ 0 to confirm hurt).
        halves_agree = (lift_h1 is not None and lift_h2 is not None
                        and lift_h1 <= 0 and lift_h2 <= 0)
        verdict = "CONFIRMED" if halves_agree else "FRESH"
    return {"verdict": verdict, "n_50d": n_50d,
            "lift_50d": lift_50d, "lift_h1": lift_h1, "lift_h2": lift_h2}


def main():
    proposals = _load_proposals()
    if proposals is None:
        return 1

    acc, targets = _accumulate_50d(proposals)

    rows = []
    for (field, cand, base, regime, lo, hi), c14 in targets.items():
        bucket = acc.get((field, cand, base, regime, lo, hi),
                         {"h1": [0.0, 0.0, 0], "h2": [0.0, 0.0, 0], "all": [0.0, 0.0, 0]})
        v = _verdict(c14["lift_pct"], c14["n"], bucket)
        rows.append({
            "layer": cand, "field": field, "regime": regime,
            "band": c14["band"], "lead_lo": lo, "lead_hi": hi,
            "n_14d": c14["n"], "lift_14d_pct": c14["lift_pct"],
            **v,
        })

    rows.sort(key=lambda r: (0 if r["verdict"] == "CONFIRMED" else
                             1 if r["verdict"] == "FRESH" else
                             2 if r["verdict"] == "STALE" else 3,
                             r["layer"], r["field"], r["lead_lo"]))

    lines = []
    lines.append("=" * 100)
    lines.append(f"NBM SKIP-ADD TWO-WINDOW AUDIT — 14d fresh + {LONG_WINDOW_DAYS}d long")
    lines.append("=" * 100)
    lines.append(f"Rescore of walkforward ADD proposals against {LONG_WINDOW_DAYS}d window.")
    lines.append(f"CONFIRMED = 14d + {LONG_WINDOW_DAYS}d both ≤ {LIFT_PCT_FLOOR:+.0f}% AND {LONG_WINDOW_DAYS}d halves both ≤ 0.")
    lines.append(f"FRESH = {LONG_WINDOW_DAYS}d weaker than 14d (regime-transient; hold).")
    lines.append(f"STALE = {LONG_WINDOW_DAYS}d shows cell helping (drop proposal).")
    lines.append(f"THIN_50D = {LONG_WINDOW_DAYS}d n < {MIN_N} (accumulate).")
    lines.append("")
    hdr = (f"{'verdict':<10}{'layer':<10}{'field':<5}{'regime':<12}{'band':<8}"
           f"{'n_14d':>8}{'lift_14d':>10}{'n_50d':>8}{'lift_50d':>10}"
           f"{'lift_h1':>10}{'lift_h2':>10}")
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for r in rows:
        def _fmt(v, w=10, sign=True):
            if v is None:
                return f"{'—':>{w}}"
            return f"{v:>+{w}.1f}" if sign else f"{v:>{w}.1f}"
        lines.append(
            f"{r['verdict']:<10}{r['layer']:<10}{r['field']:<5}{r['regime']:<12}{r['band']:<8}"
            f"{r['n_14d']:>8,}{_fmt(r['lift_14d_pct'])}{r['n_50d']:>8,}"
            f"{_fmt(r['lift_50d'])}{_fmt(r['lift_h1'])}{_fmt(r['lift_h2'])}"
        )
    lines.append("")
    n_conf = sum(1 for r in rows if r["verdict"] == "CONFIRMED")
    n_fresh = sum(1 for r in rows if r["verdict"] == "FRESH")
    n_stale = sum(1 for r in rows if r["verdict"] == "STALE")
    n_thin = sum(1 for r in rows if r["verdict"] == "THIN_50D")
    lines.append(f"VERDICT: {n_conf} CONFIRMED, {n_fresh} FRESH, {n_stale} STALE, {n_thin} THIN_50D "
                 f"({len(rows)} proposals total)")
    if n_conf:
        conf = [f"{r['layer']} {r['field']} {r['regime']} {r['band']}"
                for r in rows if r["verdict"] == "CONFIRMED"]
        lines.append(f"CONFIRMED (ship candidates): {'; '.join(conf)}")
    out = "\n".join(lines)
    print(out)
    OUT_TXT.write_text(out + "\n")
    OUT_JSON.write_text(json.dumps({
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "long_window_days": LONG_WINDOW_DAYS,
        "min_n": MIN_N,
        "lift_pct_floor": LIFT_PCT_FLOOR,
        "n_confirmed": n_conf,
        "n_fresh": n_fresh,
        "n_stale": n_stale,
        "n_thin_50d": n_thin,
        "proposals": rows,
    }, indent=2))
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    print(f"wrote {OUT_JSON}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
