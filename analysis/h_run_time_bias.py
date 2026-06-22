"""Stage 0 — Run-time issuance bias.

HRRR is initialized hourly; the pair log records `run_time`. Some init cycles
(especially 00z and 12z) ingest fresh upper-air radiosonde data; others
(off-hours) rely on shorter-cycle adjustments. Bias might differ
systematically by run-time hour-of-day.

Method: stratify |error_l1| by run_time hour for each high-volume field.
A ≥10% MAE difference across run-time hours, sustained across multiple
fields, is a real signal. Free correction candidate if found.
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = {"t", "h", "ws", "wg", "cc", "cl", "cm", "ch"}

# (field, run_hour) -> [n, sum|e1|]
sums = defaultdict(lambda: [0, 0.0])
now = datetime.utcnow()
cutoff_iso = (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M")

with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in FIELDS:
            continue
        rt = r.get("run_time") or ""
        if rt < cutoff_iso or len(rt) < 13:
            continue
        try:
            rh = int(rt[11:13])
        except ValueError:
            continue
        e1 = r.get("error_l1")
        if e1 is None:
            continue
        s = sums[(f, rh)]
        s[0] += 1
        s[1] += abs(e1)

print(f"{'field':<6} {'run_h':>5} {'n':>8} {'|L1|':>8}")
print("-" * 38)
for f in sorted(FIELDS):
    by_hour = {}
    for h in range(24):
        n, e = sums.get((f, h), (0, 0.0))
        if n < 200:
            continue
        by_hour[h] = e/n
        print(f"{f:<6} {h:>5} {n:>8,} {by_hour[h]:>8.3f}")
    if len(by_hour) >= 12:
        lo = min(by_hour.values()); hi = max(by_hour.values())
        spread_pct = (hi - lo) / lo * 100 if lo > 0 else 0
        worst = max(by_hour.items(), key=lambda x: x[1])[0]
        best  = min(by_hour.items(), key=lambda x: x[1])[0]
        verdict = "★ RUN-TIME BIAS" if spread_pct >= 10 else "flat"
        print(f"  → {f}: best run_h={best} worst run_h={worst}, spread={spread_pct:.1f}%  {verdict}")
    print()
