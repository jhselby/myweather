#!/usr/bin/env python3
"""Direct measurement: for h and dp, what MAE does each layer produce, per
lead-band, per day. NO fitting, NO tau. Just: read the pair log, aggregate
error_lN per (day, band, layer), print tables.

Motivation 2026-07-31: layer-shape sentry shows h/production helps at 0-5h
but hurts +14.8% at 6-11h. Joe reports h was winning 2-3% consistently for
weeks, then went bad. Need to identify WHICH LAYER started hurting and WHEN.

Run:
    python3 -m analysis.h_h_dp_layer_walk
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = Path(__file__).resolve().parent / "output" / "h_h_dp_layer_walk.txt"

FIELDS = ("h", "dp")
LAYERS = ("l1", "l2", "l3", "l4")   # h has no l5/l6/specialists
LEAD_BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]


def band_of(lead):
    for lab, lo, hi in LEAD_BANDS:
        if lo <= lead < hi:
            return lab
    return None


def _fetch(url):
    with open(cached_path(url), "rb") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    out = []
    def p(*a):
        line = " ".join(str(x) for x in a)
        print(line); out.append(line)

    # aggregation: (field, day, band, layer) -> [abs_sum, n]
    agg = defaultdict(lambda: [0.0, 0])
    # also pooled per (field, band, layer) across the whole window
    pooled = defaultdict(lambda: [0.0, 0])

    n_rows = 0
    n_used = 0
    for row in _fetch(URL):
        n_rows += 1
        f = row.get("field")
        if f not in FIELDS:
            continue
        lead = row.get("lead_h")
        obs_t = row.get("obs_time", "")
        if lead is None or not obs_t:
            continue
        if not (0 <= lead < 48):
            continue
        band = band_of(int(lead))
        day = obs_t[:10]
        used_any = False
        for lyr in LAYERS:
            err = row.get(f"error_{lyr}")
            if err is None:
                continue
            a = abs(float(err))
            agg[(f, day, band, lyr)][0] += a
            agg[(f, day, band, lyr)][1] += 1
            pooled[(f, band, lyr)][0] += a
            pooled[(f, band, lyr)][1] += 1
            used_any = True
        if used_any:
            n_used += 1

    p(f"rows scanned {n_rows:,}   h/dp rows used {n_used:,}")
    p()

    days = sorted({d for (f, d, b, l) in agg.keys()})
    p(f"days present: {len(days)}   ({days[0]} .. {days[-1]})")
    p()

    # ── Pooled table across the full window ──
    p("=" * 100)
    p("POOLED across full window — MAE per (field, band, layer)")
    p("=" * 100)
    p(f"  {'field':<4} {'band':<7} {'n':>6}  "
      + " ".join(f"{l:>7}" for l in LAYERS)
      + f"   {'l4-vs-l1':>9} {'l4-vs-l2':>9} {'l4-vs-l3':>9}")
    for f in FIELDS:
        for b, _, _ in LEAD_BANDS:
            cells = {l: pooled[(f, b, l)] for l in LAYERS}
            n_max = max((c[1] for c in cells.values()), default=0)
            if n_max == 0: continue
            maes = {l: (c[0]/c[1] if c[1] else None) for l, c in cells.items()}
            def _pct(new, base):
                if new is None or base is None or base == 0: return None
                return 100.0 * (new - base) / base
            mae_cells = " ".join(f"{maes[l]:>7.3f}" if maes[l] is not None else f"{'—':>7}" for l in LAYERS)
            def _d(pair):
                v = _pct(*pair)
                return f"{v:>+8.1f}%" if v is not None else f"{'—':>9}"
            d_l1 = _d((maes["l4"], maes["l1"]))
            d_l2 = _d((maes["l4"], maes["l2"]))
            d_l3 = _d((maes["l4"], maes["l3"]))
            p(f"  {f:<4} {b:<7} {n_max:>6,}  {mae_cells}   {d_l1:>9} {d_l2:>9} {d_l3:>9}")
    p()
    p("  l4-vs-lN reads: negative = l4 better than lN (correction helped);")
    p("  positive = l4 worse than lN (correction hurt). Look for the last")
    p("  layer where the number stays negative — that's where the win came")
    p("  from; anything downstream that goes positive is the leak.")
    p()

    # ── Per-day trajectory (find WHEN it went bad) ──
    # Show l4-vs-l1 % per day per band per field. Compact.
    p("=" * 100)
    p("PER-DAY l4-vs-l1 % — negative = l4 better; positive = l4 worse")
    p("=" * 100)
    for f in FIELDS:
        p(f"  === {f} ===")
        p(f"  {'day':<12}  "
          + " ".join(f"{b:>10}" for b, _, _ in LEAD_BANDS)
          + f"   {'pooled':>10}")
        for d in days:
            row_cells = []
            day_num = 0.0; day_den = 0.0
            for b, _, _ in LEAD_BANDS:
                c1 = agg.get((f, d, b, "l1"), [0.0, 0])
                c4 = agg.get((f, d, b, "l4"), [0.0, 0])
                if c1[1] == 0 or c4[1] == 0:
                    row_cells.append(f"{'—':>10}")
                    continue
                m1 = c1[0]/c1[1]; m4 = c4[0]/c4[1]
                d_pct = 100.0 * (m4 - m1) / m1 if m1 else 0.0
                marker = "" if d_pct <= 0 else "!"
                row_cells.append(f"{d_pct:>+8.1f}%{marker}")
                day_num += (m4 - m1) * c1[1]
                day_den += m1 * c1[1]
            pooled_d = f"{100.0*day_num/day_den:>+8.1f}%" if day_den else f"{'—':>10}"
            marker = "!" if day_den and day_num/day_den > 0 else " "
            p(f"  {d:<12}  " + " ".join(row_cells) + f"   {pooled_d}{marker}")
        p()

    # ── Per-day per-layer marginal contribution (l2 vs l1, l3 vs l2, l4 vs l3) ──
    p("=" * 100)
    p("PER-DAY MARGINAL layer deltas (positive = that layer HURT vs the prior layer)")
    p("=" * 100)
    for f in FIELDS:
        p(f"  === {f} ===")
        p(f"  {'day':<12}  {'l2-vs-l1':>10} {'l3-vs-l2':>10} {'l4-vs-l3':>10}   {'pooled band':<}")
        for d in days:
            # Compute across all bands pooled (weighted by n)
            def _delta(lyr_new, lyr_base):
                num = 0.0; den = 0.0
                for b, _, _ in LEAD_BANDS:
                    a_new = agg.get((f, d, b, lyr_new))
                    a_base = agg.get((f, d, b, lyr_base))
                    if not a_new or not a_base or a_new[1] == 0 or a_base[1] == 0:
                        continue
                    m_new = a_new[0]/a_new[1]; m_base = a_base[0]/a_base[1]
                    num += (m_new - m_base) * a_base[1]
                    den += m_base * a_base[1]
                return (100.0 * num/den) if den else None
            d21 = _delta("l2", "l1")
            d32 = _delta("l3", "l2")
            d43 = _delta("l4", "l3")
            def _fmt(v):
                if v is None: return f"{'—':>10}"
                m = "!" if v > 0 else " "
                return f"{v:>+8.1f}%{m}"
            p(f"  {d:<12}  {_fmt(d21)} {_fmt(d32)} {_fmt(d43)}")
        p()

    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(out) + "\n")
    print(f"\nwrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
