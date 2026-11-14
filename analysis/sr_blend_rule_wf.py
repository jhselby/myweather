"""sr: does the field-level blend weight beat the 4 h block weights that are served? (11-14)

Walk-forward with per_field_scoring._walkforward_weights (each obs day fit on the days before it,
same HRRR/NBM prod residuals the scoreboard uses). Per obs day: sum |w*e_hrrr + (1-w)*e_nbm| with the
block w (what terminal_static_blend serves for sr) vs the field w vs the band w. Through ship_rule:
holdout = obs days >= 2026-11-03. Ledger only with SR_RULE_RECORD=1.

    PYTHONPATH=. .venv/bin/python -m analysis.sr_blend_rule_wf
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis import per_field_scoring as pfs  # noqa: E402
from analysis._cache import PAIR_LOG_URL, cached_path  # noqa: E402
from analysis.ship_rule import day_block_gain, record, verdict  # noqa: E402

FIRST = "2026-10-15"


def main():
    path = cached_path(PAIR_LOG_URL, max_age_hours=6)
    W = pfs._walkforward_weights(path, FIRST)
    per = {k: defaultdict(lambda: [0.0, 0.0, 0]) for k in ("field", "band")}
    with open(path) as fh:
        for line in fh:
            if '"field":"sr"' not in line and '"field": "sr"' not in line:
                continue
            r = json.loads(line)
            ot = (r.get("obs_time") or "")[:10]
            vt = r.get("valid_time") or ""
            ww = W.get(("sr", ot))
            if not ww or len(vt) < 13:
                continue
            h, n = pfs._hrrr_prod_error(r), pfs._nbm_prod_error(r)
            if h is None or n is None:
                continue
            wb = ww["block"].get(int(vt[11:13]) // pfs.WF_BLOCK_HOURS * pfs.WF_BLOCK_HOURS, ww["field"])
            wd = ww["band"].get(pfs._band_for(r.get("lead_h")), ww["field"])
            base = abs(wb * h + (1 - wb) * n)
            for k, w in (("field", ww["field"]), ("band", wd)):
                p = per[k][ot]
                p[0] += base
                p[1] += abs(w * h + (1 - w) * n)
                p[2] += 1
    for k in per:
        pd = {d: tuple(v) for d, v in per[k].items()}
        print(f"sr {k} w vs served block w   ALL     {verdict(day_block_gain(pd, holdout_only=False))}")
        gh = day_block_gain(pd)
        print(f"sr {k} w vs served block w   HOLDOUT {verdict(gh)}")
        if os.environ.get("SR_RULE_RECORD") == "1":
            record("sr_blend_rule_wf", f"sr {k} w vs block w (walk-forward)", gh, note="per_field_scoring walk-forward weights")


if __name__ == "__main__":
    main()
