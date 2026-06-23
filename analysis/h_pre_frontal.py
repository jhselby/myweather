"""Stage 0 — Pre-frontal MAE pattern (hours UNTIL next front).

Extension of hours-since-front. Same data, opposite direction. Approaching
air mass advection may bias forecasts differently than the unsettled
post-frontal window. If pre-frontal has its own signal independent of
post-frontal, both directions matter for the C1e axis.
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

req = urllib.request.Request(FRONT_URL, headers={"User-Agent": "curl/8.4.0"})
with urllib.request.urlopen(req, timeout=15) as r:
    passage_dts = sorted(
        datetime.fromisoformat(e.get("ts", "").replace("Z", "")[:19])
        for e in json.loads(r.read()).get("entries", []) if e.get("ts")
    )
print(f"Loaded {len(passage_dts)} passages")

def hours_until_next(obs_dt):
    """Find next passage after obs_dt."""
    lo, hi = 0, len(passage_dts)
    while lo < hi:
        mid = (lo + hi) // 2
        if passage_dts[mid] > obs_dt:
            hi = mid
        else:
            lo = mid + 1
    if lo >= len(passage_dts):
        return None
    return (passage_dts[lo] - obs_dt).total_seconds() / 3600

sums = defaultdict(lambda: [0, 0.0])
with open(cached_path(PAIR_URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in FIELDS:
            continue
        try:
            odt = datetime.fromisoformat((r.get("obs_time") or "")[:19])
        except Exception:
            continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None:
            continue
        hu = hours_until_next(odt)
        if hu is None:
            continue
        band = None
        for lo, hi, lab in BANDS:
            if lo <= hu < hi:
                band = lab; break
        if not band:
            continue
        s = sums[(f, band)]
        s[0] += 1; s[1] += abs(err)

print(f"\n{'field':<6} {'band_until':<10} {'n':>8} {'|err|':>8} {'Δ vs ≥24h':>11}")
print("-" * 50)
for f in FIELDS:
    base = sums.get((f, "≥24h"))
    if not base or base[0] < 200:
        continue
    base_mae = base[1] / base[0]
    for lo, hi, lab in BANDS:
        n, s = sums.get((f, lab), (0, 0.0))
        if n < 100:
            continue
        m = s/n
        d = (m - base_mae)/base_mae*100
        flag = "★" if d >= 25 else ("⚠" if d >= 10 else "")
        print(f"{f:<6} {lab:<10} {n:>8,} {m:>8.3f} {d:>+10.1f}% {flag}")
    print()
