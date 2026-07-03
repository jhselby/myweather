
import sys, os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from _cache import cached_path
#!/usr/bin/env python3
"""
Walk-forward L3+L4 on/off validator — per-(field, regime, lead_band) shape.

Emits recommendations at the granularity the ship gate needs:
  1. Per-cell (field × regime × lead_band) verdict — helps / hurts / flat
  2. Proposed L3_FIELDS / L4_FIELDS whitelist
  3. Proposed SKIP_TABLE entries (drop-in for decay_apply.py)

Rebuilt 2026-07-03 because the previous aggregate-MAE output shape led to
shipping decisions that missed regime-specific damage. See the h + L4
walkforward-vs-cross-cut incident: aggregate said +5.2% overall win; per-cell
cross-cut said 21 L4 LOSES / 4 WIN — catastrophic short-lead damage under
sea_breeze / nw_flow / pre_frontal / sw_flow was hidden by long-lead wins.
The fix isn't "always remember to run the cross-cut manually" (that's
discipline, which fails). It's "emit the cross-cut shape as the primary
recommendation so the ship decision reads directly off the output."

Method:
  1. Pull every pair-log row with all of forecast_l2, forecast_l3, forecast_l4,
     observed, lead_h, obs_time, state_fc.regime_synoptic.
  2. Train/test split on obs_time (last N days = test).
  3. For each (field, regime, lead_band, state) cell, compute test MAE.
  4. Per-cell verdict: L3 helps if MAE(L3) < MAE(L2) by >= 3%, hurts if
     MAE(L3) > MAE(L2) by >= 3%, else flat. Same for L4 vs its baseline.
  5. Roll up per (field, layer):
       - Sample-weighted net win across cells → decides whitelist inclusion.
       - Cells that hurt by >= 3% under a whitelisted layer → skip cells.
  6. Emit drop-in decay_apply.py config.

Output:
  analysis/output/walkforward_l3l4_summary.txt

Run:
    python3 -m analysis.walkforward_l3l4_validator
    python3 -m analysis.walkforward_l3l4_validator --cutoff-days 3
"""
import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

FIELDS = ["t", "dp", "h", "ws", "wg", "cc", "sr", "pr", "pa", "ch", "cm", "cl"]
FIELD_LABELS = {
    "t": "Temperature", "dp": "Dew point",  "h": "Humidity",
    "ws": "Wind speed", "wg": "Wind gust",  "cc": "Cloud cover",
    "sr": "Solar rad.", "pr": "Pressure",   "pa": "Precip amt",
    "ch": "Cloud high", "cm": "Cloud mid",  "cl": "Cloud low",
}
LEAD_BINS = 48
BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]

# Per-cell decision thresholds.
CELL_WIN_PCT   = 0.03   # layer helps this cell if MAE drops >= 3%
CELL_LOSS_PCT  = 0.03   # layer hurts this cell if MAE rises >= 3%
MIN_N_PER_CELL = 200    # cells below this are "thin" — no verdict either way

# Whitelist inclusion rule. A layer earns whitelist membership for a field if
# the sample-weighted net improvement across all cells is >= this threshold.
FIELD_WIN_PCT = 0.02    # 2% weighted overall win required

# Emit skip cells for cells where the whitelisted layer hurts by >= this.
SKIP_LOSS_PCT = 0.03    # 3% loss triggers a skip cell recommendation


def _fetch_lines(url):
    with open(cached_path(url), 'rb') as resp:
        for raw in resp:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _band_of(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def _mae(rows, get_pred):
    """Weighted MAE. rows = iter of (f_l2, f_l3, f_l4, obs)."""
    n = 0; s = 0.0
    for r in rows:
        pred = get_pred(r)
        obs  = r[3]
        s += abs(pred - obs); n += 1
    return (s / n if n else None), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff-days", type=float, default=10.0,
                    help="Hold out the last N days as test (default 10.0; "
                         "2d/5d are regime-fragile per 06-22 diagnostic)")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    now = datetime.utcnow()
    cutoff = now - timedelta(days=args.cutoff_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M")
    print(f"Fetching {ERROR_LOG_URL}…")
    print(f"  train <  {cutoff_iso}  <= test")

    # Two parallel bindings — same rows, keyed by two different regime sources.
    # state_fc = what the classifier said at forecast time (what the skip table
    # can actually gate on). state_obs = what the regime actually turned out to
    # be (what real-world correction efficacy is measured against). When the
    # two views agree on a per-cell verdict, the ship decision is safe. When
    # they disagree, the correction is entangled with classifier accuracy —
    # not fixable by a skip table alone.
    # cells[field][(regime, band)] = list of (f_l2, f_l3, f_l4, obs)
    train_cells_fc  = defaultdict(lambda: defaultdict(list))
    test_cells_fc   = defaultdict(lambda: defaultdict(list))
    train_cells_obs = defaultdict(lambda: defaultdict(list))
    test_cells_obs  = defaultdict(lambda: defaultdict(list))
    n_in = n_use = 0
    for row in _fetch_lines(ERROR_LOG_URL):
        n_in += 1
        field = row.get("field")
        if field not in FIELDS:
            continue
        lead = row.get("lead_h")
        f_l2 = row.get("forecast_l2")
        f_l3 = row.get("forecast_l3")
        f_l4 = row.get("forecast_l4")
        obs  = row.get("observed")
        obs_t = row.get("obs_time", "")
        regime_fc  = (row.get("state_fc")  or {}).get("regime_synoptic") or "unknown"
        regime_obs = (row.get("state_obs") or {}).get("regime_synoptic") or "unknown"
        if lead is None or f_l2 is None or f_l3 is None or f_l4 is None or obs is None or not obs_t:
            continue
        if not (0 <= lead < LEAD_BINS):
            continue
        band = _band_of(int(lead))
        if band is None:
            continue
        try:
            obs_dt = datetime.strptime(obs_t, "%Y-%m-%dT%H:%M")
        except ValueError:
            continue
        rec = (float(f_l2), float(f_l3), float(f_l4), float(obs))
        is_test = obs_dt >= cutoff
        (test_cells_fc  if is_test else train_cells_fc )[field][(regime_fc,  band)].append(rec)
        (test_cells_obs if is_test else train_cells_obs)[field][(regime_obs, band)].append(rec)
        n_use += 1
    n_train = sum(len(v) for cells in train_cells_fc.values() for v in cells.values())
    n_test  = sum(len(v) for cells in test_cells_fc.values() for v in cells.values())
    print(f"  {n_in:,} rows scanned, {n_use:,} usable ({n_train:,} train / {n_test:,} test)")
    print()

    # Per-cell verdicts. Compute independently for state_fc and state_obs
    # bindings; disagreement between the two flags a classifier-entanglement.
    def _compute_field_cells(test_cells_by_field):
        out = {}
        for field in FIELDS:
            rows_by_cell = test_cells_by_field.get(field) or {}
            cell_rows = []
            for (regime, band), rows in sorted(rows_by_cell.items()):
                if len(rows) < MIN_N_PER_CELL:
                    cell_rows.append({"regime": regime, "band": band, "n": len(rows), "thin": True})
                    continue
                mae_l2, _ = _mae(rows, lambda r: r[0])
                mae_l3, _ = _mae(rows, lambda r: r[1])
                mae_l4, _ = _mae(rows, lambda r: r[2])
                l3_delta = (mae_l2 - mae_l3) / mae_l2 if mae_l2 > 0 else 0.0
                if l3_delta >= CELL_WIN_PCT: l3_verdict = "WIN"
                elif l3_delta <= -CELL_LOSS_PCT: l3_verdict = "LOSS"
                else: l3_verdict = "flat"
                # L4 baseline: L3 if L3 helps here, else L2 (matches production
                # behavior where L4 fits on L3 residual when L3 applies, else on L2).
                l4_baseline = mae_l3 if l3_verdict == "WIN" else mae_l2
                l4_delta = (l4_baseline - mae_l4) / l4_baseline if l4_baseline > 0 else 0.0
                if l4_delta >= CELL_WIN_PCT: l4_verdict = "WIN"
                elif l4_delta <= -CELL_LOSS_PCT: l4_verdict = "LOSS"
                else: l4_verdict = "flat"
                cell_rows.append({
                    "regime": regime, "band": band, "n": len(rows), "thin": False,
                    "mae_l2": mae_l2, "mae_l3": mae_l3, "mae_l4": mae_l4,
                    "l3_delta": l3_delta, "l4_delta": l4_delta,
                    "l3_verdict": l3_verdict, "l4_verdict": l4_verdict,
                })
            out[field] = cell_rows
        return out

    field_cells_fc  = _compute_field_cells(test_cells_fc)
    field_cells_obs = _compute_field_cells(test_cells_obs)
    field_cells     = field_cells_fc  # Skip-table gates on state_fc; primary view.

    # Field-level roll-up under BOTH regime views. A ship-safe field is one
    # where fc-view says SHIP AND obs-view agrees. Disagreement = correction
    # is entangled with classifier accuracy — a skip table can't fix it.
    def _rollup(field_cells_view):
        out = {}
        for field, cells in field_cells_view.items():
            judgeable = [c for c in cells if not c["thin"]]
            n_total = sum(c["n"] for c in judgeable)
            if not judgeable or n_total == 0:
                out[field] = {"l3_ship": False, "l4_ship": False,
                              "l3_weighted": None, "l4_weighted": None,
                              "l3_skip": [], "l4_skip": [], "cells": cells, "n_test": 0}
                continue
            l3_weighted = sum(c["l3_delta"] * c["n"] for c in judgeable) / n_total
            l4_weighted = sum(c["l4_delta"] * c["n"] for c in judgeable) / n_total
            l3_ship = l3_weighted >= FIELD_WIN_PCT
            l4_ship = l4_weighted >= FIELD_WIN_PCT
            l3_skip = [c for c in judgeable if c["l3_delta"] <= -SKIP_LOSS_PCT] if l3_ship else []
            l4_skip = [c for c in judgeable if c["l4_delta"] <= -SKIP_LOSS_PCT] if l4_ship else []
            out[field] = {
                "l3_ship": l3_ship, "l4_ship": l4_ship,
                "l3_weighted": l3_weighted, "l4_weighted": l4_weighted,
                "l3_skip": l3_skip, "l4_skip": l4_skip,
                "cells": cells, "n_test": n_total,
            }
        return out

    rollups_fc  = _rollup(field_cells_fc)
    rollups_obs = _rollup(field_cells_obs)
    # Combined verdict: SHIP only if both views agree. Skip cells taken from
    # the state_fc view (that's what the skip table actually gates on).
    field_rollups = {}
    for field in FIELDS:
        rfc  = rollups_fc.get(field)  or {}
        robs = rollups_obs.get(field) or {}
        # l3
        l3_fc = rfc.get("l3_ship", False)
        l3_obs = robs.get("l3_ship", False)
        l3_ship = l3_fc and l3_obs
        l3_entangled = (l3_fc != l3_obs)
        # l4
        l4_fc = rfc.get("l4_ship", False)
        l4_obs = robs.get("l4_ship", False)
        l4_ship = l4_fc and l4_obs
        l4_entangled = (l4_fc != l4_obs)
        field_rollups[field] = {
            "l3_ship": l3_ship, "l4_ship": l4_ship,
            "l3_entangled": l3_entangled, "l4_entangled": l4_entangled,
            "l3_weighted_fc":  rfc.get("l3_weighted"),
            "l3_weighted_obs": robs.get("l3_weighted"),
            "l4_weighted_fc":  rfc.get("l4_weighted"),
            "l4_weighted_obs": robs.get("l4_weighted"),
            "l3_skip": rfc.get("l3_skip", []),
            "l4_skip": rfc.get("l4_skip", []),
            "cells": rfc.get("cells", []),
            "cells_obs": robs.get("cells", []),
            "n_test": rfc.get("n_test", 0),
        }

    # Roll skip cells into (regime, lead_lo, lead_hi) tuples matching
    # decay_apply.SKIP_TABLE format.
    def _skip_tuples(cells):
        by_regime = defaultdict(set)
        for c in cells:
            by_regime[c["regime"]].add(c["band"])
        out = []
        # BANDS in lead order. If a regime has all 4 bands as skips, collapse to (regime, 0, 48).
        all_band_labels = {b[0] for b in BANDS}
        band_lookup = {b[0]: (b[1], b[2]) for b in BANDS}
        for regime, bands in sorted(by_regime.items()):
            if bands == all_band_labels:
                out.append((regime, 0, 48))
            else:
                for b in sorted(bands, key=lambda x: band_lookup[x][0]):
                    lo, hi = band_lookup[b]
                    out.append((regime, lo, hi))
        return out

    # Build human-readable summary.
    lines = [
        f"Walk-forward L3+L4 per-cell validator — generated {datetime.now().isoformat(timespec='seconds')}",
        f"Train cutoff: {cutoff_iso} UTC  (test = last {args.cutoff_days:.1f}d)",
        f"Per-cell thresholds: WIN >= {int(CELL_WIN_PCT*100)}%, LOSS <= -{int(CELL_LOSS_PCT*100)}%",
        f"Whitelist rule: weighted overall win >= {int(FIELD_WIN_PCT*100)}%; skip cells: LOSS >= {int(SKIP_LOSS_PCT*100)}%",
        f"Cell min-n: {MIN_N_PER_CELL}",
        "",
        "=== FIELD SUMMARY ===",
        "",
    ]
    hdr = (f"  {'field':<14} {'n_test':>8}  "
           f"{'L3 fc%':>7}  {'L3 obs%':>7}  {'L3':>4}  {'L3 skip':>7}  "
           f"{'L4 fc%':>7}  {'L4 obs%':>7}  {'L4':>4}  {'L4 skip':>7}")
    lines.append(hdr)
    lines.append("  " + "-" * (len(hdr) - 2))
    for field in FIELDS:
        r = field_rollups.get(field) or {}
        if not r or r.get("n_test", 0) == 0:
            continue
        def pct(x): return f"{x*100:+6.1f}%" if x is not None else "     -"
        def verdict(ship, entangled):
            if entangled: return "ENT"   # entangled — fc and obs disagree
            return "SHIP" if ship else "off"
        lines.append(
            f"  {FIELD_LABELS[field]:<14} {r.get('n_test',0):>8,}  "
            f"{pct(r.get('l3_weighted_fc')):>7}  {pct(r.get('l3_weighted_obs')):>7}  "
            f"{verdict(r['l3_ship'], r['l3_entangled']):>4}  {len(r['l3_skip']):>7}  "
            f"{pct(r.get('l4_weighted_fc')):>7}  {pct(r.get('l4_weighted_obs')):>7}  "
            f"{verdict(r['l4_ship'], r['l4_entangled']):>4}  {len(r['l4_skip']):>7}"
        )
    lines.append("")
    lines.append("  Verdict codes: SHIP = both views agree ship; off = both agree don't ship;")
    lines.append("                 ENT = views disagree (correction entangled with classifier accuracy —")
    lines.append("                       no skip table can fix; requires classifier work or different axis).")

    lines.append("")
    lines.append("=== PER-CELL BREAKDOWN (regime × lead_band) ===")
    for field in FIELDS:
        r = field_rollups.get(field) or {}
        cells = r.get("cells") or []
        if not cells:
            continue
        lines.append("")
        lines.append(f"  {FIELD_LABELS[field]}:")
        lines.append(f"    {'regime':<14} {'band':<8} {'n':>7}  {'|L2|':>8}  {'|L3|':>8}  {'|L4|':>8}  {'L3 Δ%':>8}  {'L4 Δ%':>8}  {'L3':>5}  {'L4':>5}")
        for c in cells:
            if c["thin"]:
                lines.append(f"    {c['regime']:<14} {c['band']:<8} {c['n']:>7,}  {'—':>8}  {'—':>8}  {'—':>8}  {'—':>8}  {'—':>8}  {'thin':>5}  {'thin':>5}")
                continue
            lines.append(
                f"    {c['regime']:<14} {c['band']:<8} {c['n']:>7,}  "
                f"{c['mae_l2']:>8.3f}  {c['mae_l3']:>8.3f}  {c['mae_l4']:>8.3f}  "
                f"{c['l3_delta']*100:>+7.1f}%  {c['l4_delta']*100:>+7.1f}%  "
                f"{c['l3_verdict']:>5}  {c['l4_verdict']:>5}"
            )

    # Proposed decay_apply.py config.
    l3_fields = [f for f in FIELDS if field_rollups.get(f, {}).get("l3_ship")]
    l4_fields = [f for f in FIELDS if field_rollups.get(f, {}).get("l4_ship")]

    lines.append("")
    lines.append("=== PROPOSED decay_apply.py CONFIG ===")
    lines.append("")
    lines.append(f"L3_FIELDS = {{{', '.join(repr(f) for f in l3_fields)}}}")
    lines.append(f"L4_FIELDS = {{{', '.join(repr(f) for f in l4_fields)}}}")
    lines.append("")
    lines.append("# Skip cells — add to SKIP_TABLE in decay_apply.py.")
    lines.append("SKIP_TABLE_PROPOSAL = {")
    for field in FIELDS:
        r = field_rollups.get(field) or {}
        for layer_key, cells_ in (("l3", r.get("l3_skip", [])), ("l4", r.get("l4_skip", []))):
            tuples = _skip_tuples(cells_)
            if not tuples:
                continue
            lines.append(f'    ("{field}", "{layer_key}"): [')
            for regime, lo, hi in tuples:
                lines.append(f'        ("{regime}", {lo}, {hi}),')
            lines.append(f'    ],')
    lines.append("}")

    # Per-field verdict for the digest exec summary.
    lines.append("")
    lines.append("=== PER-FIELD VERDICTS ===")
    for field in FIELDS:
        r = field_rollups.get(field) or {}
        if not r or r.get("n_test", 0) == 0:
            continue
        def _verdict_line(layer, ship, entangled, w_fc, w_obs, skip_n):
            if entangled:
                return (f"{layer} ENTANGLED (fc {w_fc*100:+.1f}% / obs {w_obs*100:+.1f}%) — "
                        f"do not ship; skip table can't gate on obs-regime")
            if ship:
                return f"{layer} SHIP" + (f" + skip {skip_n} cells" if skip_n else "")
            # Both views agree not-ship.
            fc = f"{w_fc*100:+.1f}%" if w_fc is not None else "—"
            obs = f"{w_obs*100:+.1f}%" if w_obs is not None else "—"
            return f"{layer} off (fc {fc} / obs {obs})"
        parts = [
            _verdict_line("L3", r["l3_ship"], r["l3_entangled"],
                         r.get("l3_weighted_fc"), r.get("l3_weighted_obs"), len(r["l3_skip"])),
            _verdict_line("L4", r["l4_ship"], r["l4_entangled"],
                         r.get("l4_weighted_fc"), r.get("l4_weighted_obs"), len(r["l4_skip"])),
        ]
        lines.append(f"  {FIELD_LABELS[field]:<14} → {' | '.join(parts)}")

    # Top-line verdict.
    lines.append("")
    n_l3_ship = sum(1 for f in FIELDS if field_rollups.get(f, {}).get("l3_ship"))
    n_l4_ship = sum(1 for f in FIELDS if field_rollups.get(f, {}).get("l4_ship"))
    n_l3_ent  = sum(1 for f in FIELDS if field_rollups.get(f, {}).get("l3_entangled"))
    n_l4_ent  = sum(1 for f in FIELDS if field_rollups.get(f, {}).get("l4_entangled"))
    n_skip_cells = sum(len(r.get("l3_skip", [])) + len(r.get("l4_skip", []))
                       for r in field_rollups.values())
    lines.append(f"Verdict: L3 ship {n_l3_ship} field(s) [entangled: {n_l3_ent}], "
                 f"L4 ship {n_l4_ship} field(s) [entangled: {n_l4_ent}], "
                 f"{n_skip_cells} skip cell(s) proposed.")

    summary_path = os.path.join(OUT_DIR, "walkforward_l3l4_summary.txt")
    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  ✓ {summary_path}")
    print()
    # Echo the field summary + verdict.
    in_summary = False
    for line in lines:
        if line.startswith("=== FIELD SUMMARY"):
            in_summary = True; print(line); continue
        if line.startswith("=== PER-CELL"):
            in_summary = False; continue
        if in_summary or line.startswith("Verdict") or line.startswith("=== PROPOSED") \
           or line.startswith("L3_FIELDS") or line.startswith("L4_FIELDS") \
           or line.startswith("=== PER-FIELD"):
            print(line)


if __name__ == "__main__":
    main()
