"""Stage 0 — Solar zenith × cloud MAE.

Hypothesis: clouds are harder to forecast at low sun angles (sunrise, sunset)
due to lighting/contrast affecting model resolution of cloud edges, and
because oblique radiation paths increase optical thickness sensitivity.

Method: approximate solar zenith from hour-of-day local. For Marblehead MA
(42.5°N), summer solar noon ≈ 17:00 UTC (~12:30 EDT-actual). Use a cheap
proxy: zenith ≈ |hour_utc - 17|*15° approximation (won't be exact but
captures the shape). Stratify cloud field MAE by zenith bin.
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ["cc", "cl", "cm", "ch", "sr"]
now = datetime.utcnow()
cutoff = (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M")

# (field, zenith_bin) -> [n, sum|err|]
sums = defaultdict(lambda: [0, 0.0])
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
        if ot < cutoff or len(ot) < 13:
            continue
        try:
            hour = int(ot[11:13])
        except ValueError:
            continue
        # Solar noon at Wyman Cove (~71°W) is around 17:00 UTC
        # Crude zenith proxy: |hour - 17| * 15° (capped at 90°)
        zenith = min(90.0, abs(hour - 17) * 15.0)
        zbin = ("0-30 (high sun)" if zenith < 30 else
                "30-60 (mid)"     if zenith < 60 else
                "60-90 (low)"     if zenith < 90 else
                "night")
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None:
            continue
        s = sums[(f, zbin)]
        s[0] += 1; s[1] += abs(err)

print(f"{'field':<5} {'zenith':<18} {'n':>8} {'|err|':>8}")
print("-" * 45)
for f in FIELDS:
    rows = []
    for zbin in ["0-30 (high sun)", "30-60 (mid)", "60-90 (low)", "night"]:
        n, e = sums.get((f, zbin), (0, 0.0))
        if n < 200:
            continue
        rows.append((zbin, n, e/n))
    if not rows:
        continue
    maes = [r[2] for r in rows]
    spread = (max(maes) - min(maes))/min(maes)*100 if min(maes) > 0 else 0
    for zbin, n, m in rows:
        print(f"{f:<5} {zbin:<18} {n:>8,} {m:>8.3f}")
    flag = "★" if spread >= 15 else "flat"
    print(f"  → {f} max/min spread: {spread:.1f}%  {flag}\n")
