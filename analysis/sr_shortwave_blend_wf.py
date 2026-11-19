"""sr: does swapping HRRR direct-beam for HRRR total shortwave in the HRRR/NBM blend beat what is served? (11-19)

Observed sr is Tempest total shortwave; HRRR l1 is direct-beam only (sr_shortwave_bias.py), NBM DSWRF is total.
Per pair-log sr row (lead 24-47h, daylight, raw NBM present): candidates fit on the prior 14 valid days per
lead band and scored on the next day, identical rows, baseline = served (error_{applied_layer}):
  A  w*forecast_shortwave + (1-w)*forecast_raw_nbm   (w grid 0..1 by 0.1, min sum|err|)
  B  same with forecast_l1 (direct) in place of shortwave (control: is the swap what matters?)
Through ship_rule (holdout valid days >= 2026-11-03). Rows before the v0.7.104 NBM gap fill (runs < 11-15T14)
have no raw NBM at 34-47h and drop out, so the 34-47 band is thin until ~11-29. Exploratory; ledger only
with SR_SW_RECORD=1.

    PYTHONPATH=. .venv/bin/python -m analysis.sr_shortwave_blend_wf
"""
import collections
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.ship_rule import day_block_gain, record, verdict  # noqa: E402

LOG = Path.home() / ".cache" / "myweather" / "forecast_error_log_backstamped.jsonl"
BANDS = (("24-33", 24, 34), ("34-47", 34, 48))
WIN, MIN_N = 14, 150
GRID = [i / 10 for i in range(11)]


def rows():
    out = []
    for line in open(LOG):
        r = json.loads(line)
        if r.get("field") != "sr" or r["lead_h"] < 24:
            continue
        obs, sw, nb, l1 = r.get("observed"), r.get("forecast_shortwave"), r.get("forecast_raw_nbm"), r.get("forecast_l1")
        ap = r.get("applied_layer")
        sv = r.get(f"error_{ap}") if ap else None
        if None in (obs, sw, nb, l1, sv) or (obs <= 0 and sw <= 0):
            continue
        band = next(n for n, lo, hi in BANDS if lo <= r["lead_h"] < hi)
        out.append((band, r["valid_time"][:10], obs, float(sw), float(nb), float(l1), sv))
    return out


def best_w(rs, which):
    best, bw = None, 1.0
    for w in GRID:
        e = sum(abs(w * r[which] + (1 - w) * r[4] - r[2]) for r in rs)
        if best is None or e < best:
            best, bw = e, w
    return bw


def main():
    R = rows()
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in R:
        by[r[0]][r[1]].append(r)
    for band, _, _ in BANDS:
        days = sorted(by[band])
        per = {"A": {}, "B": {}}
        ws = {"A": [], "B": []}
        for i, d in enumerate(days):
            fit = [r for dd in days[max(0, i - WIN):i] for r in by[band][dd]]
            if len(fit) < MIN_N:
                continue
            for key, idx in (("A", 3), ("B", 5)):
                w = best_w(fit, idx)
                ws[key].append(w)
                base = sum(abs(r[6]) for r in by[band][d])
                cand = sum(abs(w * r[idx] + (1 - w) * r[4] - r[2]) for r in by[band][d])
                per[key][d] = (base, cand, len(by[band][d]))
        print(f"\n== sr {band}h, baseline = served ({len(days)} days with rows) ==")
        for key, name in (("A", "shortwave+NBM"), ("B", "direct+NBM (control)")):
            if not per[key]:
                print(f"  {name}: not enough days"); continue
            mean_w = sum(ws[key]) / len(ws[key])
            for ho in (False, True):
                g = day_block_gain(per[key], holdout_only=ho)
                if g["gain"] is None:
                    continue
                print(f"  {name:22s} {'HOLDOUT' if ho else 'ALL    '} gain {g['gain']:+.1f}% [{g['lo']:+.1f},{g['hi']:+.1f}] "
                      f"{g['wins']}/{g['days']} d, halves {g['halves']}, n={g['n']}, mean w={mean_w:.2f}")
            if os.environ.get("SR_SW_RECORD") == "1":
                g = day_block_gain(per[key], holdout_only=True)
                record("sr_shortwave_blend_wf", f"sr {band} {name} vs served", g, False, "walk-forward 14d")


if __name__ == "__main__":
    main()
