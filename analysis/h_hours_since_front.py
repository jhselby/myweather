"""Stage 0 — Hours-since-front × MAE.

Post-frontal hours are well-known to be a high-error window in numerical
weather prediction (model relaxes back to climatology before it should).
Test: does forecast MAE crater in the 0-6h after frontal passage and recover?
If yes, "hours_since_front" becomes a confidence axis (C1e candidate) or a
correction filter.

Method: load frontal_events_log.json, parse passage timestamps. For each
pair, compute hours_since_most_recent_front. Bucket and stratify MAE per
field. Use error_l4 (production output) to measure user-visible impact.
"""
import os, sys, json, urllib.request
from collections import defaultdict
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL  = "https://data.wymancove.com/forecast_error_log.jsonl"
FRONT_URL = "https://data.wymancove.com/frontal_events_log.json"
FIELDS = ["t", "h", "ws", "wg", "cc", "ch", "cm", "cl"]
BANDS = [(0, 3, "0-3h"), (3, 6, "3-6h"), (6, 12, "6-12h"),
         (12, 24, "12-24h"), (24, 999, "≥24h")]

# Load frontal passages
try:
    with urllib.request.urlopen(FRONT_URL, timeout=15) as r:
        front_doc = json.loads(r.read())
except Exception as e:
    print(f"Couldn't load frontal log: {e}"); sys.exit(1)

events = front_doc.get("events") or front_doc.get("entries") or front_doc.get("frontal_events") or []
if not events and isinstance(front_doc, list):
    events = front_doc
passage_dts = []
for e in events:
    ts = e.get("ts") or e.get("timestamp") or e.get("when")
    if not ts:
        continue
    try:
        # Handle both with/without 'Z'
        ts = ts.replace("Z", "").replace("+00:00", "")
        passage_dts.append(datetime.fromisoformat(ts[:19]))
    except Exception:
        continue
passage_dts.sort()
print(f"Loaded {len(passage_dts)} frontal passages, range {passage_dts[0] if passage_dts else 'none'} → {passage_dts[-1] if passage_dts else 'none'}")
if not passage_dts:
    print("No usable frontal events; aborting."); sys.exit(1)

def hours_since_front(obs_dt):
    """Binary search for most recent passage at or before obs_dt."""
    lo, hi = 0, len(passage_dts)
    while lo < hi:
        mid = (lo + hi) // 2
        if passage_dts[mid] <= obs_dt:
            lo = mid + 1
        else:
            hi = mid
    if lo == 0:
        return None
    delta = (obs_dt - passage_dts[lo - 1]).total_seconds() / 3600
    return delta if delta >= 0 else None

# (field, band) -> [n, sum|err|]
sums = defaultdict(lambda: [0, 0.0])
n_in = n_use = 0
with open(cached_path(PAIR_URL), "rb") as fh:
    for raw in fh:
        n_in += 1
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in FIELDS:
            continue
        ot = r.get("obs_time") or ""
        try:
            odt = datetime.fromisoformat(ot[:19])
        except Exception:
            continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None:
            continue
        hsf = hours_since_front(odt)
        if hsf is None:
            continue
        band = None
        for lo, hi, lab in BANDS:
            if lo <= hsf < hi:
                band = lab; break
        if not band:
            continue
        s = sums[(f, band)]
        s[0] += 1; s[1] += abs(err)
        n_use += 1

print(f"Joined {n_use:,} of {n_in:,} pairs to a frontal-distance bucket")
print()
print(f"{'field':<6} {'band':<8} {'n':>8} {'|err|':>8} {'Δ vs ≥24h':>10}")
print("-" * 50)
for f in FIELDS:
    base = sums.get((f, "≥24h"))
    if not base or base[0] < 200:
        continue
    base_mae = base[1] / base[0]
    rows = []
    for lo, hi, lab in BANDS:
        n, s = sums.get((f, lab), (0, 0.0))
        if n < 100:
            continue
        m = s/n
        d = (m - base_mae)/base_mae*100
        rows.append((lab, n, m, d))
    if not rows:
        continue
    for lab, n, m, d in rows:
        flag = "★" if d >= 25 else ("⚠" if d >= 10 else "")
        print(f"{f:<6} {lab:<8} {n:>8,} {m:>8.3f} {d:>+9.1f}% {flag}")
    print()
