"""Stage 0 — Weekday vs weekend temperature bias.

Anthropogenic heat: more cars, heating, AC use Mon-Fri vs weekends. The
hypothesis is that the model is climatology-trained and doesn't capture
the weekly cycle. Prior probability is low for our coastal location (heat
dispersed by ocean), but worth a strict null test — if it hits, free fix.
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ["t", "h", "ws"]  # also check h and ws for anthropogenic effects
now = datetime.utcnow()
cutoff = (now - timedelta(days=21)).strftime("%Y-%m-%dT%H:%M")

# field -> per-dow [n, signed_err_sum, abs_err_sum]
sums = defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0.0]))
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
        if ot < cutoff or len(ot) < 10:
            continue
        try:
            dow = datetime.fromisoformat(ot[:10]).weekday()  # 0=Mon ... 6=Sun
        except Exception:
            continue
        e1 = r.get("error_l1")
        if e1 is None:
            continue
        s = sums[f][dow]
        s[0] += 1; s[1] += e1; s[2] += abs(e1)

DOW_NAMES = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
print(f"{'field':<5} {'dow':<4} {'n':>7} {'mean_bias':>10} {'|err|':>7}")
print("-" * 40)
for f in FIELDS:
    weekday_bias = []; weekend_bias = []
    weekday_n = weekend_n = 0
    for dow in range(7):
        n, s_err, abs_err = sums[f].get(dow, (0, 0.0, 0.0))
        if n < 200:
            continue
        b = s_err / n
        print(f"{f:<5} {DOW_NAMES[dow]:<4} {n:>7,} {b:>+10.3f} {abs_err/n:>7.3f}")
        if dow < 5:
            weekday_bias.append((n, s_err)); weekday_n += n
        else:
            weekend_bias.append((n, s_err)); weekend_n += n
    if weekday_n > 0 and weekend_n > 0:
        wb = sum(s for _, s in weekday_bias)/weekday_n
        eb = sum(s for _, s in weekend_bias)/weekend_n
        gap = wb - eb
        flag = "★" if abs(gap) >= 0.5 else ("⚠" if abs(gap) >= 0.2 else "flat")
        print(f"  → {f} weekday bias {wb:+.3f}, weekend {eb:+.3f}, gap {gap:+.3f}  {flag}")
    print()
