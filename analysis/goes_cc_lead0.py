"""Lead-0 cloud cover: which "now" value is closer to GOES-19 satellite cloud fraction?

Written 11-25 for the question "should the sky card read the airport-blended current value or the served
hourly[0]?" (the two disagreed: 10 vs 41). Same rows for every source, lead_h == 0 only, truth =
analysis/output/goes_cc_truth.jsonl cf3 (see goes_cc_score.py for the caution: GOES runs ~13 points cloudier
than URMA and METAR, a constant offset that cancels in the gaps between sources).

  served   = pair-log prod error + observed   (what the selector put in hourly[0])
  observed = pair-log `observed` (METAR-shrunk, i.e. the airport-blended value the card used to show)
  raw NBM, URMA TCDC for reference

11-25 result (499 h, 22 d): served MAE 21.3, observed 22.1, URMA 22.2, raw NBM 23.7; observed beats served on
9 of 22 days. No evidence for the airport-blended value, so the card follows the served hourly[0].

    PYTHONPATH=. .venv/bin/python analysis/goes_cc_lead0.py
"""
import json
import statistics as st
from collections import defaultdict

from analysis._cache import cached_path
from analysis.truth_compare import PAIR_LOG_URL, _prod_error, _urma, _utc_hour


def main():
    sat = {}
    for line in open("analysis/output/goes_cc_truth.jsonl"):
        r = json.loads(line)
        if r.get("cf3") is not None:
            sat[r["hour"]] = 100 * r["cf3"]
    urma = _urma("TCDC", "urma_truth_tcdc.json")
    rows = []
    for line in open(cached_path(PAIR_LOG_URL, max_age_hours=0.5)):
        if '"field": "cc"' not in line and '"field":"cc"' not in line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("lead_h") != 0:
            continue
        h = _utc_hour(r.get("valid_time") or "")
        t, srv, obs, raw = sat.get(h), _prod_error(r), r.get("observed"), r.get("error_raw_nbm")
        if t is None or srv is None or obs is None:
            continue
        u = urma.get(h)
        rows.append((h, srv + obs - t, obs - t, None if raw is None else raw + obs - t, None if u is None else u - t))
    print(f"lead-0 cc rows with GOES truth: {len(rows)} hours, {len({r[0][:10] for r in rows})} days")
    for name, i in (("served hourly[0] (selector)", 1), ("observed (airport-blended)", 2), ("raw NBM", 3), ("URMA TCDC", 4)):
        v = [r[i] for r in rows if r[i] is not None]
        print(f"{name:32s} MAE {st.mean(abs(x) for x in v):.1f}  bias {st.mean(v):+.1f}  n={len(v)}")
    by_day = defaultdict(lambda: ([], []))
    for h, s, o, _, _ in rows:
        by_day[h[:10]][0].append(abs(s))
        by_day[h[:10]][1].append(abs(o))
    wins = sum(1 for a, b in by_day.values() if st.mean(b) < st.mean(a))
    print(f"days observed beats served: {wins} of {len(by_day)}")


if __name__ == "__main__":
    main()
