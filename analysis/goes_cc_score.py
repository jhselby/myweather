"""Score cc against GOES-19 satellite cloud fraction (independent of METAR and of URMA).

Truth = analysis/output/goes_cc_truth.jsonl (analysis/goes_cc_truth.py), cloud fraction x100 of the
Cove 3x3 pixel ring (cf3) or 5x5 (cf5). Scores on identical rows, per lead band:
served cc, raw NBM cc, METAR-shrunk 'observed' cc, URMA TCDC (as a 'forecast' of the sky).
Error vs satellite = pair-log error + (observed - sat).

    PYTHONPATH=. .venv/bin/python analysis/goes_cc_score.py [cf3|cf5]
"""
import json
import sys
from collections import defaultdict

from analysis._cache import cached_path
from analysis.truth_compare import CC_BANDS, PAIR_LOG_URL, _prod_error, _urma, _utc_hour

key = sys.argv[1] if len(sys.argv) > 1 else "cf3"
sat = {}
for l in open("analysis/output/goes_cc_truth.jsonl"):
    r = json.loads(l)
    if r.get(key) is not None:
        sat[r["hour"]] = 100.0 * r[key]
urma = _urma("TCDC", "urma_truth_tcdc.json")
first = min(sat)
bands = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
nowc = defaultdict(lambda: [0, 0.0])
for line in open(cached_path(PAIR_LOG_URL, max_age_hours=0.5)):
    if '"field": "cc"' not in line and '"field":"cc"' not in line:
        continue
    try:
        r = json.loads(line)
    except json.JSONDecodeError:
        continue
    h = _utc_hour(r.get("valid_time") or "")
    t = sat.get(h)
    srv, raw, obs, lead = _prod_error(r), r.get("error_raw_nbm"), r.get("observed"), r.get("lead_h")
    if t is None or None in (srv, raw, obs, lead):
        continue
    band = next((n for n, lo, hi in CC_BANDS if lo <= lead < hi), None)
    if band is None:
        continue
    cells = {"served": abs(srv + obs - t), "raw_nbm": abs(raw + obs - t), "metar_obs": abs(obs - t)}
    if h in urma:
        cells["urma"] = abs(urma[h] - t)
    for k, v in cells.items():
        b = bands[band][k]; b[0] += 1; b[1] += v
print(f"cc vs GOES {key}; sat hours {len(sat)} from {first}")
for band in bands:
    print(f"  {band}: " + "  ".join(f"{k} {v[1]/v[0]:.1f} (n={v[0]})" for k, v in bands[band].items()))
