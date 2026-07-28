"""Stage 0 — Dewpoint depression (t − dp) bias, with t/dp attribution split.

Even when t and dp are individually well-corrected, errors don't cancel.
Depression drives fog formation, heat index, comfort. If forecast depression
is systematically off, that's a Group D refinement opportunity (no new layer
needed — just track which regime/hour the cancellation fails).

Method: join t-row and dp-row at each obs_time. Compute observed depression
and forecast_l4 depression. Stratify |depression_error| by regime.

Attribution (added 2026-07-28): also track per-regime t_bias and dp_bias
separately. Depression bias = t_bias − dp_bias by construction, so any
regime-conditional depression bias attributes to one of three shapes:
  - T-DOMINANT:   |t_bias| >= 1.5 * |dp_bias| AND |t_bias| >= 0.5°F
                  → not a dp fix, invest in t layers (Lt/L2/L3/L4-t)
  - DP-DOMINANT:  |dp_bias| >= 1.5 * |t_bias| AND |dp_bias| >= 0.5°F
                  → real dp signal, warrants dp-side correction candidate
  - BOTH-COMPOUND: t_bias and dp_bias opposite signs AND both >= 0.5°F
                  → both fields miss in opposite directions, dep gets sum
  - BOTH-CANCEL:  t_bias and dp_bias same sign, neither dominates AND
                  both >= 0.5°F → dep is small difference of two same-sign
                  biases; noise-adjacent
  - NOISE:        max(|t_bias|, |dp_bias|) < 0.5°F

Blocking rule for promotion (per project_hypothesis_backlog #6): dp-side
correction candidates only ship on DP-DOMINANT regime classifications.
T-DOMINANT regimes should trigger t-layer work instead.
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

# Compute depression errors + per-row t/dp bias contributions
errs = []
errs_by_regime = defaultdict(list)
# per-regime: t_bias contributions, dp_bias contributions
t_bias_by_regime = defaultdict(list)
dp_bias_by_regime = defaultdict(list)
for key, fields in joined.items():
    if "t" not in fields or "dp" not in fields:
        continue
    t_fc, t_obs, regime = fields["t"]
    dp_fc, dp_obs, _ = fields["dp"]
    t_bias_row = t_fc - t_obs
    dp_bias_row = dp_fc - dp_obs
    err = t_bias_row - dp_bias_row   # depression bias = t_bias − dp_bias by construction
    errs.append(err)
    if regime:
        errs_by_regime[regime].append(err)
        t_bias_by_regime[regime].append(t_bias_row)
        dp_bias_by_regime[regime].append(dp_bias_row)


def _classify(t_b, dp_b):
    """Attribute a regime's depression bias to t or dp per docstring rules."""
    at, ad = abs(t_b), abs(dp_b)
    if max(at, ad) < 0.5:
        return "NOISE"
    if at >= 1.5 * ad and at >= 0.5:
        return "T-DOMINANT"
    if ad >= 1.5 * at and ad >= 0.5:
        return "DP-DOMINANT"
    if (t_b > 0) != (dp_b > 0) and at >= 0.5 and ad >= 0.5:
        return "BOTH-COMPOUND"
    return "BOTH-CANCEL"


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

    # ── Attribution table (added 2026-07-28) ─────────────────────────────
    print()
    print("=" * 78)
    print("ATTRIBUTION — where does each regime's depression bias come from?")
    print("=" * 78)
    print("dep_bias = t_bias − dp_bias by construction. Classification per")
    print("script docstring. Ship dp-side correction only on DP-DOMINANT regimes;")
    print("T-DOMINANT signals belong to t-layer work.")
    print()
    print(f"{'regime':<14} {'n':>7} {'dep_bias':>9} {'t_bias':>8} {'dp_bias':>8}  {'source':<15} flag")
    print("-" * 78)
    attr_rows = []
    for regime, tbs in t_bias_by_regime.items():
        if len(tbs) < 200:
            continue
        dbs = dp_bias_by_regime[regime]
        n = len(tbs)
        t_b = sum(tbs) / n
        dp_b = sum(dbs) / n
        dep_b = t_b - dp_b
        cls = _classify(t_b, dp_b)
        attr_rows.append((regime, n, dep_b, t_b, dp_b, cls))
    attr_rows.sort(key=lambda r: -abs(r[2]))
    ship_candidates = []
    for regime, n, dep_b, t_b, dp_b, cls in attr_rows:
        flag = "★" if abs(dep_b) >= 1.5 else ("⚠" if abs(dep_b) >= 0.8 else "")
        print(f"{regime:<14} {n:>7,} {dep_b:>+9.2f} {t_b:>+8.2f} {dp_b:>+8.2f}  {cls:<15} {flag}")
        if cls == "DP-DOMINANT" and abs(dep_b) >= 1.5:
            ship_candidates.append(regime)
    print()
    if ship_candidates:
        print(f"VERDICT: DP-DOMINANT ★-magnitude regimes eligible for dp-correction "
              f"Stage 1 workup: {', '.join(ship_candidates)}.")
    else:
        print("VERDICT: NO DP-DOMINANT ★-magnitude regimes. Any regime-conditional")
        print("dp-correction candidate would be masking t-bias — invest in t layers")
        print("(or leave alone) instead. Per project_hypothesis_backlog #6, hold.")
