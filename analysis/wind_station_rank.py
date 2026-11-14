"""Preview of the wind-on-water truth pick: rank each Tempest station against the waterfront ones.

Joe's rule (11-08): the app's wind means wind ON THE WATER. Truth = waterfront stations plus any station
that consistently reads like open air, chosen from data. For each station and ws/wg, over ticks where
>= MIN_WF waterfront stations are fresh: ratio = sum(station)/sum(waterfront median), corr with the
waterfront median, MAE after scaling by the ratio (shape match), and coverage. Exploratory until ~2 weeks.

    PYTHONPATH=. .venv/bin/python -m analysis.wind_station_rank [dir_with_station_readings_json]
"""
import glob
import json
import statistics
import sys
from pathlib import Path

MIN_WF = 1


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    meta, ticks = {}, []
    for f in sorted(glob.glob(str(Path(d) / "*.json"))):
        j = json.load(open(f))
        meta.update(j["stations"])
        ticks += j["ticks"]
    wf = {k for k, m in meta.items() if m.get("waterfront")}
    print(f"{len(ticks)} ticks, {len(meta)} stations, waterfront: " + ", ".join(sorted(meta[k]["station_name"] for k in wf)))
    for var in ("ws", "wg"):
        rows = {k: [] for k in meta}
        ref = []
        for t in ticks:
            r = {k: x[var] for k, x in t["readings"].items() if x.get("valid") and x.get(var) is not None and (x.get("age_min") or 0) < 15}
            w = [v for k, v in r.items() if k in wf]
            if len(w) < MIN_WF:
                continue
            m = statistics.median(w)
            ref.append(m)
            for k in meta:
                rows[k].append((r[k] if k in r else None, m))
        print(f"\n{var}: {len(ref)} ticks, waterfront median mean {statistics.mean(ref):.2f} mph")
        print(f"  {'station':<22}{'wf':>3}{'cover':>7}{'ratio':>7}{'corr':>7}{'shapeMAE':>9}{'MAE':>6}")
        out = []
        for k, rs in rows.items():
            p = [(a, b) for a, b in rs if a is not None]
            if len(p) < 200:
                continue
            a = [x for x, _ in p]; b = [y for _, y in p]
            ratio = sum(a) / sum(b) if sum(b) else float("nan")
            try:
                corr = statistics.correlation(a, b)
            except statistics.StatisticsError:
                corr = float("nan")
            out.append((statistics.mean(abs(x - ratio * y) for x, y in p), k, len(p) / len(rs), ratio, corr,
                        statistics.mean(abs(x - y) for x, y in p)))
        for sm, k, cov, ratio, corr, mae in sorted(out):
            print(f"  {meta[k]['station_name'][:21]:<22}{'Y' if k in wf else '':>3}{cov:7.2f}{ratio:7.2f}{corr:7.2f}{sm:9.2f}{mae:6.2f}")


if __name__ == "__main__":
    main()
