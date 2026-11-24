"""Forward scoring of the SHADOW t_stnoff (v0.7.153) against t_urmab (served) on the Mesonet stations.

Same identical rows, leads 6-47h, per valid day; ship bar as the other shadows: beats t_urmab on >= 5 of the last 7 scored
days, positive pooled gain, trailing-3-day tripwire, then analysis/ship_rule.py at >= 14 days. Forward only: ticks stamped
with t_stnoff (first tick after the v0.7.153 deploy).

    PYTHONPATH=. .venv/bin/python -m analysis.t_stnoff_shadow_score [forecast_log.json]
"""
import collections
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from analysis.ship_rule import day_block_gain
from analysis.t_night_offset_wf import stations_truth
from analysis.urma_shadow_score import BANDS, snapshots

ET = ZoneInfo("America/New_York")


def main():
    S = stations_truth()
    per = {b[0]: collections.defaultdict(lambda: [0.0, 0.0, 0]) for b in BANDS}
    ticks = 0
    for s in snapshots(sys.argv[1] if len(sys.argv) > 1 else None):
        hs = [h for h in s["hours"] if "t_stnoff" in h]
        if not hs:
            continue
        ticks += 1
        run = datetime.strptime(s["run"], "%Y-%m-%dT%H:%M").replace(tzinfo=ET)
        for h in hs:
            lead = (datetime.strptime(h["v"], "%Y-%m-%dT%H:%M").replace(tzinfo=ET) - run).total_seconds() / 3600
            tr = S.get(h["v"])
            band = next((n for n, lo, hi in BANDS if lo <= lead < hi), None)
            if tr is None or band is None:
                continue
            a = per[band][h["v"][:10]]
            a[0] += abs(h["t_urmab"] - tr); a[1] += abs(h["t_stnoff"] - tr); a[2] += 1
    print(f"t_stnoff shadow vs t_urmab on Mesonet stations: {ticks} stamped ticks")
    for band, days in per.items():
        d = {k: tuple(v) for k, v in days.items()}
        if not d:
            print(f"  {band}h: no scored days yet")
            continue
        g = day_block_gain(d, holdout_only=False)
        last7 = sorted(d)[-7:]
        wins = sum(d[k][1] < d[k][0] for k in last7)
        t3 = sorted(d)[-3:]
        trip = sum(d[k][1] for k in t3) > sum(d[k][0] for k in t3)
        tw = "too few days (<3)" if len(t3) < 3 else ("TRIPPED" if trip else "ok")
        print(f"  {band}h: gain {g['gain']:+.1f}% [{g['lo']:+.1f},{g['hi']:+.1f}] over {g['days']} d, "
              f"shadow wins {wins}/{len(last7)} (last7), n={g['n']}, tripwire {tw}")


if __name__ == "__main__":
    main()
