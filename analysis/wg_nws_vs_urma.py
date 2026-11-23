"""wg: weather.gov (error_nws / forecast_nws, stamped since 11-22 13:18) vs raw NBM vs served, all scored on URMA gust.
Identical rows (all three present), by lead band, valid days >= first NWS day. Day-block interval via ship_rule.
Exploratory; thin until ~12-06 (14 days). Also prints the live terminal-blend wg HRRR weight.

    PYTHONPATH=. .venv/bin/python -m analysis.wg_nws_vs_urma
"""
import json
from collections import defaultdict
from pathlib import Path

from analysis.ship_rule import day_block_gain, verdict
from analysis.truth_compare import _urma, _utc_hour

LOG = Path.home() / ".cache/myweather/forecast_error_log.jsonl"
BANDS = {"2-5": (2, 5), "6-11": (6, 11), "12-23": (12, 23), "24-47": (24, 47)}


def main():
    urma = _urma("GUST", "urma_truth_gust.json")
    acc = {b: defaultdict(lambda: [0.0, 0.0, 0.0, 0]) for b in BANDS}  # day -> nws, nbm, served, n
    with open(LOG) as f:
        for line in f:
            if '"field": "wg"' not in line or '"forecast_nws"' not in line:
                continue
            d = json.loads(line)
            n, w, s, lead = d.get("forecast_raw_nbm"), d.get("forecast_nws"), d.get("forecast"), d.get("lead_h")
            u = urma.get(_utc_hour(d["valid_time"]) or "")
            if None in (n, w, s, lead, u):
                continue
            for b, (lo, hi) in BANDS.items():
                if lo <= lead <= hi:
                    a = acc[b][d["valid_time"][:10]]
                    a[0] += abs(w - u); a[1] += abs(n - u); a[2] += abs(s - u); a[3] += 1
    for b in BANDS:
        days = acc[b]
        if not days:
            print(b, "no rows"); continue
        n = sum(a[3] for a in days.values())
        m = [sum(a[i] for a in days.values()) / n for i in range(3)]
        print(f"{b:6s} n={n:5d} days={len(days)}  MAE nws {m[0]:.2f}  nbm {m[1]:.2f}  served {m[2]:.2f}")
        g = day_block_gain({k: (a[0], a[2], a[3]) for k, a in days.items()}, holdout_only=False)
        print("       served vs nws:", verdict(g))
    try:
        t = json.load(open(Path(__file__).resolve().parent.parent / "weather_collector/data/terminal_blend_field_curated.json"))
        print("bundled terminal blend wg:", t["fields"]["wg"])
    except Exception as e:
        print("terminal blend read failed", e)


if __name__ == "__main__":
    main()
