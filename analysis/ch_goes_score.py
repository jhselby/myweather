"""Forward check of served high cloud (v0.7.154: raw HRRR ch_l1 served at 6-23h, v0.7.171 at 0-5h too) against what would have been served (ch_pre_hrrr),
on the GOES-19 cloud-top-height truth (analysis/goes_cloud_layers.py, high = tops above 6 km, Cove 3x3).

Fetches the last 3 days of satellite heights first. Per valid day; tripwire = trailing 3 days worse than ch_pre_hrrr -> flip
serve_ch to false in urma_blend_serve.json.

    PYTHONPATH=. .venv/bin/python -m analysis.ch_goes_score [forecast_log.json]
"""
import collections
import json
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from analysis.goes_cloud_layers import OUT, fetch
from analysis.ship_rule import day_block_gain
from analysis.urma_shadow_score import snapshots

ET = ZoneInfo("America/New_York")


def main():
    fetch(3)
    G = {}
    for line in open(OUT):
        r = json.loads(line)
        G[r["hour"]] = 100 * sum(1 for v in r["ht"] if v is not None and v >= 6000) / 9
    per = collections.defaultdict(lambda: [0.0, 0.0, 0])
    for s in snapshots(sys.argv[1] if len(sys.argv) > 1 else None):
        run = datetime.strptime(s["run"], "%Y-%m-%dT%H:%M").replace(tzinfo=ET)
        for h in s["hours"]:
            if "ch_pre_hrrr" not in h:
                continue
            v = datetime.strptime(h["v"], "%Y-%m-%dT%H:%M").replace(tzinfo=ET)
            g = G.get(v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H"))
            if g is None:
                continue
            a = per[h["v"][:10]]
            a[0] += abs(h["ch_pre_hrrr"] - g); a[1] += abs(h["ch"] - g); a[2] += 1
    print("ch served (raw HRRR, 0-23h) vs ch_pre_hrrr on GOES high-top truth")
    d = {k: tuple(v) for k, v in per.items()}
    if not d:
        print("  no scored days yet")
        return
    g = day_block_gain(d, holdout_only=False)
    t3 = sorted(d)[-3:]
    trip = sum(d[k][1] for k in t3) > sum(d[k][0] for k in t3)
    print(f"  gain {g['gain']:+.1f}% [{g['lo']:+.1f},{g['hi']:+.1f}] over {g['days']} d, n={g['n']}, "
          f"tripwire {'too few days (<3)' if len(t3) < 3 else ('TRIPPED' if trip else 'ok')}")


if __name__ == "__main__":
    main()
