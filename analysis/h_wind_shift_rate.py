"""Stage 0 — Wind direction shift rate as transition predictor.

When wind_dir changes >40° in 3 hours, the atmosphere is in transition.
Different framing than C1a (which uses regime tag mismatch): here we use
the raw |Δwind_dir| over a 3h window as a continuous transition signal.

Could be a finer-grained transition axis than C1a — captures partial
transitions C1a doesn't classify.

Method: for each pair, look up the wd at obs_time-3h and obs_time. Compute
|circular Δ|. Stratify other-field MAE by Δwd bin.
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ["t", "h", "ws", "cc", "ch", "cm", "pa"]

def circ_diff(a, b):
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d

# Build obs_wd_by_time: dict ts -> obs wd
wd_by_time = {}
# Also collect pairs to score
pair_rows = []
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try: r = json.loads(raw)
        except: continue
        f = r.get("field")
        if f == "wd":
            ot = r.get("obs_time")
            obs = r.get("observed")
            if ot and obs is not None:
                wd_by_time[ot[:16]] = obs
        if f in FIELDS:
            ot = r.get("obs_time")
            err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
            if ot and err is not None:
                pair_rows.append((ot, f, abs(err)))

def shift_class(ot_iso):
    try:
        dt = datetime.fromisoformat(ot_iso[:19])
    except:
        return None
    prev = (dt - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    cur  = dt.strftime("%Y-%m-%dT%H:%M")
    wd_prev = wd_by_time.get(prev)
    wd_cur  = wd_by_time.get(cur)
    if wd_prev is None or wd_cur is None:
        return None
    d = circ_diff(wd_prev, wd_cur)
    if d < 15: return "stable (<15°)"
    if d < 40: return "drifting (15-40°)"
    if d < 80: return "shifting (40-80°)"
    return "rotating (≥80°)"

sums = defaultdict(lambda: [0, 0.0])
for ot, f, abs_err in pair_rows:
    cls = shift_class(ot)
    if not cls: continue
    s = sums[(f, cls)]
    s[0] += 1; s[1] += abs_err

ORDER = ["stable (<15°)", "drifting (15-40°)", "shifting (40-80°)", "rotating (≥80°)"]
print(f"{'field':<5} {'shift_class':<22} {'n':>8} {'|err|':>8} {'Δ vs stable':>13}")
print("-" * 65)
for f in FIELDS:
    base_n, base_e = sums.get((f, "stable (<15°)"), (0, 0.0))
    if base_n < 200: continue
    base_mae = base_e/base_n
    for cls in ORDER:
        n, e = sums.get((f, cls), (0, 0.0))
        if n < 100: continue
        m = e/n
        d = (m - base_mae)/base_mae*100 if base_mae else 0
        flag = "★" if d >= 30 else ("⚠" if d >= 15 else "")
        print(f"{f:<5} {cls:<22} {n:>8,} {m:>8.3f} {d:>+12.1f}% {flag}")
    print()
