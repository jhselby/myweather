"""Holdout tracker: served error vs baselines by field x lead band, scored by ship_rule.

Served = pair-log `error` (what shipped). Baselines on IDENTICAL rows:
  nbm  = error_raw_nbm (the normal source where NBM publishes the field)
  hrrr = error_l4      (HRRR cascade)
Valid day = valid_time date; rows need both errors. Run any date:
    python3 analysis/holdout_tracker.py [log_path]
Prints holdout verdicts (ship-eligible) and since-10-29 exploratory (not a ship test).
Ledger rows are written only for the holdout scoring.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analysis.ship_rule import day_block_gain, verdict, record, HOLDOUT_START

LOG = Path.home() / ".cache/myweather/forecast_error_log.jsonl"
FIELDS = ("t", "h", "ws")
BANDS = {"0-5": (0, 5), "6-11": (6, 11), "12-23": (12, 23), "24-47": (24, 47)}
BASES = {"nbm": "error_raw_nbm", "hrrr": "error_l4"}
EXPLORE_START = "2026-10-29"
MIN_DAYS = 8  # below this the day-block bootstrap is degenerate; no verdict, no ledger row


def band(lead):
    for k, (a, b) in BANDS.items():
        if a <= lead <= b:
            return k


def load(path):
    acc = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0]))
    with open(path) as f:
        for line in f:
            if not any(f'"field": "{x}"' in line for x in FIELDS):
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            fld, lead = d.get("field"), d.get("lead_h")
            if fld not in FIELDS or lead is None or d.get("error") is None:
                continue
            day = d["valid_time"][:10]
            if day < EXPLORE_START:
                continue
            b = band(lead)
            if not b:
                continue
            for bn, key in BASES.items():
                if d.get(key) is None:
                    continue
                a = acc[(fld, b, bn)][day]
                a[0] += abs(d[key])
                a[1] += abs(d["error"])
                a[2] += 1
    return acc


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else LOG
    acc = load(path)
    for holdout in (True, False):
        print(f"\n== {'HOLDOUT (valid day >= ' + HOLDOUT_START + ')' if holdout else 'EXPLORATORY since ' + EXPLORE_START} ==")
        for (fld, b, bn) in sorted(acc):
            g = day_block_gain(acc[(fld, b, bn)], holdout_only=holdout)
            if holdout and g["days"] < MIN_DAYS:
                print(f"{fld:3} {b:6} vs {bn:4}: {g['days']} holdout day(s), need {MIN_DAYS}: not evaluable (gain {g['gain']})")
                continue
            print(f"{fld:3} {b:6} vs {bn:4}: {verdict(g)}")
            if holdout:
                record("holdout_tracker", f"{fld} {b} served vs {bn}", g)


if __name__ == "__main__":
    main()
