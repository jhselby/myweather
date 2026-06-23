"""Stage 0 — Dewpoint depression (t − dp) bias.

Even when t and dp are individually well-corrected, errors don't cancel.
Depression drives fog formation, heat index, comfort. If forecast depression
is systematically off, that's a Group D refinement opportunity (no new layer
needed — just track which regime/hour the cancellation fails).

Method: join t-row and dp-row at each obs_time. Compute observed depression
and forecast_l4 depression. Stratify |depression_error| by regime and overall.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

# (obs_time, lead, run_time) -> {field: (forecast, observed, regime)}
joined = defaultdict(dict)
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in ("t", "dp"):
            continue
        key = (r.get("obs_time"), r.get("lead_h"), r.get("run_time"))
        if None in key:
            continue
        fc = r.get("forecast_l4") or r.get("forecast_l3") or r.get("forecast_l2") or r.get("forecast_l1")
        obs = r.get("observed")
        if fc is None or obs is None:
            continue
        regime = (r.get("state_obs") or {}).get("regime_synoptic")
        joined[key][f] = (fc, obs, regime)

# Compute depression errors
errs = []
errs_by_regime = defaultdict(list)
for key, fields in joined.items():
    if "t" not in fields or "dp" not in fields:
        continue
    t_fc, t_obs, regime = fields["t"]
    dp_fc, dp_obs, _ = fields["dp"]
    dep_fc = t_fc - dp_fc
    dep_obs = t_obs - dp_obs
    err = dep_fc - dep_obs
    errs.append(err)
    if regime:
        errs_by_regime[regime].append(err)

print(f"Joined pairs: {len(errs):,}")
if errs:
    mae = sum(abs(e) for e in errs)/len(errs)
    bias = sum(errs)/len(errs)
    print(f"Overall depression |err|: {mae:.2f}°F   signed bias: {bias:+.2f}°F")
    print()
    print(f"{'regime':<14} {'n':>7} {'|err|':>7} {'bias':>7}")
    print("-" * 40)
    rows = []
    for regime, es in errs_by_regime.items():
        if len(es) < 200:
            continue
        m = sum(abs(e) for e in es)/len(es)
        b = sum(es)/len(es)
        rows.append((regime, len(es), m, b))
    rows.sort(key=lambda r: -r[2])
    for regime, n, m, b in rows:
        flag = "★" if abs(b) >= 1.5 else ("⚠" if abs(b) >= 0.8 else "")
        print(f"{regime:<14} {n:>7,} {m:>7.2f} {b:>+7.2f} {flag}")
    print()
    print("Threshold: bias ≥1.5°F = real Stage 1; ≥0.8°F = watch.")
