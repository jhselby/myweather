"""Stage 0 — Lead-bin granularity.

Current bands [0-5, 6-11, 12-23, 24-47] are arbitrary. Maybe L2 or L3 wins
are concentrated in 0-1h or 0-2h windows that get averaged-out in the 0-5h
bucket. Re-bucket with finer near-term bands.
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ["t", "h", "ws", "wg", "ch", "cm", "cc", "cl", "pr"]
BANDS = [(0,1,"0-1h"), (1,2,"1-2h"), (2,3,"2-3h"), (3,5,"3-5h"),
         (5,8,"5-8h"), (8,12,"8-12h"), (12,18,"12-18h"), (18,24,"18-24h"),
         (24,36,"24-36h"), (36,48,"36-48h")]
now = datetime.utcnow()
cutoff = (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M")

# (field, band) -> [n, sum|e1|, sum|e2|, sum|e3|, sum|e4|]
sums = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0])
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in FIELDS:
            continue
        ot = r.get("obs_time") or ""
        if ot < cutoff:
            continue
        lead = r.get("lead_h")
        if lead is None:
            continue
        band = None
        for lo, hi, lab in BANDS:
            if lo <= lead < hi:
                band = lab; break
        if not band:
            continue
        e1 = r.get("error_l1"); e2 = r.get("error_l2") or r.get("error_l1")
        e3 = r.get("error_l3") or e2; e4 = r.get("error_l4") or e3
        if e1 is None:
            continue
        s = sums[(f, band)]
        s[0] += 1
        s[1] += abs(e1); s[2] += abs(e2); s[3] += abs(e3); s[4] += abs(e4)

print(f"{'field':<5} {'band':<7} {'n':>7} {'|L1|':>7} {'|L2|':>7} {'L2 Δ%':>7} {'|L4|':>7} {'L4 Δ%':>7}")
print("-" * 65)
for f in FIELDS:
    for lo, hi, lab in BANDS:
        n, e1, e2, e3, e4 = sums.get((f, lab), (0, 0.0, 0.0, 0.0, 0.0))
        if n < 100:
            continue
        m1 = e1/n; m2 = e2/n; m4 = e4/n
        d2 = (m1 - m2)/m1*100 if m1 > 0 else 0
        d4 = (m1 - m4)/m1*100 if m1 > 0 else 0
        print(f"{f:<5} {lab:<7} {n:>7,} {m1:>7.3f} {m2:>7.3f} {d2:>+6.1f}% {m4:>7.3f} {d4:>+6.1f}%")
    print()
