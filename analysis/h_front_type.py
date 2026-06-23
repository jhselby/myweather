"""Stage 0 — Front-type asymmetry.

If `frontal_events_log.json` carries front-type metadata (cold/warm/occluded),
test whether post-frontal MAE patterns differ by type. Cold fronts: violent
short-window transitions; warm fronts: slow gradients. Expected: cold-front
post-window shows steeper signal than warm-front.
"""
import os, sys, json, urllib.request
from collections import defaultdict
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL  = "https://data.wymancove.com/forecast_error_log.jsonl"
FRONT_URL = "https://data.wymancove.com/frontal_events_log.json"
FIELDS = ["t", "h", "ws", "wg", "cc", "cl", "cm", "ch"]
POST_H = 24

req = urllib.request.Request(FRONT_URL, headers={"User-Agent": "curl/8.4.0"})
with urllib.request.urlopen(req, timeout=15) as r:
    events = json.loads(r.read()).get("entries", [])
# Inspect the first event to see what type/fields are stored
print("Sample frontal event:", json.dumps(events[0] if events else {}, default=str)[:300])

passages = []
for e in events:
    ts = e.get("ts")
    if not ts: continue
    try:
        dt = datetime.fromisoformat(ts.replace("Z","")[:19])
    except: continue
    # Try common type field names
    ft = e.get("type") or e.get("front_type") or e.get("classification") or "unknown"
    passages.append((dt, ft))
passages.sort()

type_counts = defaultdict(int)
for _, ft in passages:
    type_counts[ft] += 1
print("Front-type distribution:", dict(type_counts))

def hsf_and_type(odt):
    """Hours since most recent passage + that passage's type."""
    lo, hi = 0, len(passages)
    while lo < hi:
        mid = (lo+hi)//2
        if passages[mid][0] <= odt: lo = mid+1
        else: hi = mid
    if lo == 0: return None, None
    dt0, ft = passages[lo-1]
    return (odt - dt0).total_seconds()/3600, ft

# (field, type, hsf_group) -> [n, sum|err|]
sums = defaultdict(lambda: [0, 0.0])
with open(cached_path(PAIR_URL), "rb") as fh:
    for raw in fh:
        try: r = json.loads(raw)
        except: continue
        f = r.get("field")
        if f not in FIELDS: continue
        try: odt = datetime.fromisoformat((r.get("obs_time") or "")[:19])
        except: continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None: continue
        hsf, ft = hsf_and_type(odt)
        if hsf is None: continue
        grp = "post" if hsf < POST_H else "baseline"
        s = sums[(f, ft, grp)]
        s[0] += 1; s[1] += abs(err)

print(f"\n{'field':<5} {'type':<14} {'post_n':>7} {'post_MAE':>9} {'base_MAE':>9} {'ratio':>7}")
print("-" * 60)
for f in FIELDS:
    for ft in sorted(type_counts.keys()):
        np, ep = sums.get((f, ft, "post"), (0, 0.0))
        nb, eb = sums.get((f, ft, "baseline"), (0, 0.0))
        if np < 100 or nb < 100: continue
        mp = ep/np; mb = eb/nb
        ratio = mp/mb if mb else 0
        flag = "★" if ratio >= 2.0 else ("⚠" if ratio >= 1.3 else "")
        print(f"{f:<5} {ft:<14} {np:>7,} {mp:>9.3f} {mb:>9.3f} {ratio:>6.2f}× {flag}")
    print()
