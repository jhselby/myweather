"""Orthogonality: pre-frontal (hu<24h) vs C1a (transition) AND vs post-frontal (hsf<24h).

Check if pre-frontal signal is independent of (a) C1a regime-transition penalty
and (b) the C1e post-frontal axis we just promoted. If yes, ship as either an
extension of C1e (bidirectional) or a new C1g axis.

2026-07-22 (v0.6.372a): matched-regime baseline (same Simpson's-paradox fix
applied to h_hsf_orthogonality.py — see [[project_c1e_hsf_kill_investigation]]).
Ratios computed per regime with MIN_N_REG=30, aggregated as weighted mean
weighted by min(n_pre, n_base). Cell needs ≥2 regimes contributing to score.
"""
import os, sys, json, urllib.request
from collections import defaultdict
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL  = "https://data.wymancove.com/forecast_error_log.jsonl"
FRONT_URL = "https://data.wymancove.com/frontal_events_log.json"
FIELDS = ("t", "h", "ws", "wg", "cc", "cl", "cm", "ch")
BANDS  = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
WIN_H = 24  # both directions

def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None

req = urllib.request.Request(FRONT_URL, headers={"User-Agent": "curl/8.4.0"})
with urllib.request.urlopen(req, timeout=15) as r:
    passage_dts = sorted(
        datetime.fromisoformat(e.get("ts","").replace("Z","")[:19])
        for e in json.loads(r.read()).get("entries", []) if e.get("ts")
    )

def hsf(obs_dt):
    lo, hi = 0, len(passage_dts)
    while lo < hi:
        mid = (lo+hi)//2
        if passage_dts[mid] <= obs_dt: lo = mid+1
        else: hi = mid
    return (obs_dt - passage_dts[lo-1]).total_seconds()/3600 if lo > 0 else None

def hu(obs_dt):
    lo, hi = 0, len(passage_dts)
    while lo < hi:
        mid = (lo+hi)//2
        if passage_dts[mid] > obs_dt: hi = mid
        else: lo = mid+1
    return (passage_dts[lo] - obs_dt).total_seconds()/3600 if lo < len(passage_dts) else None

# axes: A=pre_frontal (hu<24), B=transition (C1a), C=post_frontal (hsf<24)
# regime = state_fc.regime_synoptic (Simpson's-paradox stratifier, 2026-07-22)
sums = defaultdict(lambda: [0, 0.0])  # (field, band, A, B, C, regime) -> [n, sum|err|]
n_in = n_use = 0
with open(cached_path(PAIR_URL), "rb") as fh:
    for raw in fh:
        n_in += 1
        try: r = json.loads(raw)
        except: continue
        f = r.get("field")
        if f not in FIELDS: continue
        try: odt = datetime.fromisoformat((r.get("obs_time") or "")[:19])
        except: continue
        lead = r.get("lead_h")
        if lead is None: continue
        band = lead_band(int(lead))
        if not band: continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None: continue
        s_hu  = hu(odt); s_hsf = hsf(odt)
        if s_hu is None or s_hsf is None: continue
        sf = (r.get("state_fc") or {}).get("regime_synoptic")
        so = (r.get("state_obs") or {}).get("regime_synoptic")
        if not sf or not so: continue
        A = s_hu  < WIN_H
        C = s_hsf < WIN_H
        B = (sf != so)
        sums[(f, band, A, B, C, sf)][0] += 1
        sums[(f, band, A, B, C, sf)][1] += abs(err)
        n_use += 1

MIN_N_REG = 30
MIN_REGIMES = 2

def matched_ratio(f, band, pre_filter, base_filter):
    """Compute matched-regime post/baseline ratio.
    pre_filter and base_filter are (A, B, C) tuples that select the numerator
    and denominator subsets. Returns (weighted_ratio, total_n_pre, n_regimes).
    """
    regimes = set()
    for key in sums.keys():
        if key[0] == f and key[1] == band:
            regimes.add(key[5])
    num = 0.0
    wsum = 0.0
    n_pre_total = 0
    n_reg = 0
    for reg in regimes:
        n_p, e_p = sums.get((f, band, *pre_filter, reg), (0, 0.0))
        n_b, e_b = sums.get((f, band, *base_filter, reg), (0, 0.0))
        if n_p < MIN_N_REG or n_b < MIN_N_REG or e_b == 0:
            continue
        ratio = (e_p / n_p) / (e_b / n_b)
        w = min(n_p, n_b)
        num += ratio * w
        wsum += w
        n_pre_total += n_p
        n_reg += 1
    if wsum == 0:
        return 0.0, 0, 0
    return num / wsum, n_pre_total, n_reg

# Per-cell verdict maps — captured during both loops so we can emit the
# Stage 2 curated table at end. SHIP = ORTHOGONAL in BOTH checks (the
# axis needs to be independent of both C1a and C1e to earn a Stage 3
# stamp). Consumed by analysis/runlog/claims.py::_claim_marginal_ship_cells
# via the "PRE_FRONTAL_SHIP_CELLS" gate registered in
# build_executive_summary.py — 7-day narrow-promote counter analogous
# to C1h/C1d.
_cell_v1 = {}  # (field, band) -> verdict vs C1a
_cell_v2 = {}  # (field, band) -> verdict vs C1e

# Pairwise: pre-frontal vs each other axis (matched-regime aggregation)
print("Pre-frontal × C1a (transition) orthogonality  [matched-regime, MIN_N_REG=30, ≥2 regimes]")
print(f"{'field':<5} {'band':<6} {'stable_pre/base':>15} {'st_nR':>5} {'trans_pre/base':>14} {'tr_nR':>5}  vs_C1a")
print("-" * 85)
v1 = defaultdict(int)
for f in FIELDS:
    for label, _, _ in BANDS:
        # stable subset: transition=False, post=False; pre=True vs pre=False
        r_st, n_pre_st, nR_st = matched_ratio(f, label,
            pre_filter=(True, False, False), base_filter=(False, False, False))
        # transition subset: transition=True, post=False; pre=True vs pre=False
        r_tr, n_pre_tr, nR_tr = matched_ratio(f, label,
            pre_filter=(True, True, False), base_filter=(False, True, False))
        if nR_st < MIN_REGIMES or nR_tr < MIN_REGIMES:
            continue
        if r_st >= 1.30 and r_tr >= 1.30:
            verdict = "ORTHOGONAL"
        elif r_st <= 1.10:
            verdict = "REDUNDANT"
        elif r_tr >= 1.30:
            verdict = "CONFOUNDED"
        else:
            verdict = "AMBIGUOUS"
        v1[verdict] += 1
        _cell_v1[(f, label)] = verdict
        print(f"{f:<5} {label:<6} {r_st:>14.2f}× {nR_st:>5} {r_tr:>13.2f}× {nR_tr:>5}  {verdict}")
    print()
print(f"vs C1a: ORTHOGONAL: {v1['ORTHOGONAL']}, REDUNDANT: {v1['REDUNDANT']}, CONFOUNDED: {v1['CONFOUNDED']}, AMBIGUOUS: {v1['AMBIGUOUS']}\n")

print("Pre-frontal × post-frontal (C1e) orthogonality  [matched-regime, MIN_N_REG=30, ≥2 regimes]")
print(f"{'field':<5} {'band':<6} {'~post_pre/base':>15} {'np_nR':>5} {'post_pre/base':>14} {'p_nR':>4}  vs_C1e")
print("-" * 85)
v2 = defaultdict(int)
for f in FIELDS:
    for label, _, _ in BANDS:
        # not-post subset (B=False, C=False): pre vs baseline
        r_no_post, n_pre_np, nR_np = matched_ratio(f, label,
            pre_filter=(True, False, False), base_filter=(False, False, False))
        # post subset (B=False, C=True): pre AND post vs not-pre AND post (often thin)
        r_post, n_pre_p, nR_p = matched_ratio(f, label,
            pre_filter=(True, False, True), base_filter=(False, False, True))
        if nR_np < MIN_REGIMES:
            continue
        # If post-subset too thin, accept ORTHO on not-post evidence alone (matches
        # pre-fix behavior where n_pre_p < 50 fell through to NaN and ORTHO passed).
        post_ok = (nR_p < MIN_REGIMES) or (r_post >= 1.30)
        if r_no_post >= 1.30 and post_ok:
            verdict = "ORTHOGONAL"
        elif r_no_post <= 1.10:
            verdict = "REDUNDANT"
        else:
            verdict = "AMBIGUOUS"
        v2[verdict] += 1
        _cell_v2[(f, label)] = verdict
        rp_str = "    n/a" if nR_p < MIN_REGIMES else f"{r_post:>13.2f}×"
        print(f"{f:<5} {label:<6} {r_no_post:>14.2f}× {nR_np:>5} {rp_str} {nR_p:>4}  {verdict}")
    print()
print(f"vs C1e: ORTHOGONAL: {v2['ORTHOGONAL']}, REDUNDANT: {v2['REDUNDANT']}, AMBIGUOUS: {v2['AMBIGUOUS']}")
print()

# Emit Stage 2 curated table for the narrow-promote gate. SHIP = ORTHOGONAL
# on BOTH checks (independence from C1a AND C1e). Anything else = SKIP.
# Cells that only appeared in one loop (sample floor filtered them from the
# other) fall through to SKIP. Written to weather_collector/data/ so
# claims._claim_marginal_ship_cells reads it via the standard path.
from datetime import datetime as _dt, timezone as _tz
_CURATED_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "weather_collector", "data", "pre_frontal_curated.json"
))
_cells_out = {}
_cell_keys = set(_cell_v1.keys()) | set(_cell_v2.keys())
_ship_count = 0
for (f, band) in sorted(_cell_keys):
    v_a = _cell_v1.get((f, band))
    v_e = _cell_v2.get((f, band))
    if v_a == "ORTHOGONAL" and v_e == "ORTHOGONAL":
        status = "SHIP"
        _ship_count += 1
    else:
        status = "SKIP"
    _cells_out.setdefault(f, {})[band] = {
        "status": status,
        "vs_c1a": v_a,
        "vs_c1e": v_e,
    }
_curated_payload = {
    "generated_at": _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "source": "h_pre_front_orthogonality.py",
    "ship_rule": "cell is SHIP iff ORTHOGONAL vs C1a AND ORTHOGONAL vs C1e",
    "cells": _cells_out,
}
try:
    os.makedirs(os.path.dirname(_CURATED_PATH), exist_ok=True)
    with open(_CURATED_PATH, "w") as _fh:
        json.dump(_curated_payload, _fh, indent=2)
    print(f"→ wrote {_CURATED_PATH}  ({_ship_count} SHIP cells / {len(_cell_keys)} judged)")
except Exception as _e:
    print(f"⚠ curated table write failed: {_e}")
print()
# Population tag — this script's verdict is highly sensitive to frontal
# passage count and pair-log join rate. Inlined on the verdict line so the
# digest surfaces the caveat automatically. THIN when <15 passages. v0.6.373.
_pop_pct = (n_use / n_in * 100) if n_in else 0.0
_pop_qual = "THIN" if len(passage_dts) < 15 else "OK"
_pop_tag = f"[n={len(passage_dts)} passages, {_pop_pct:.0f}% join → {_pop_qual}]"
total = sum(v1.values()) + sum(v2.values())
ortho = v1['ORTHOGONAL'] + v2['ORTHOGONAL']
if ortho >= 6:
    print(f"→ PROMOTE: pre-frontal is independent of both C1a and C1e ({ortho} orthogonal cells).  {_pop_tag}")
elif sum(v1[k] for k in ('REDUNDANT',)) + sum(v2[k] for k in ('REDUNDANT',)) >= 0.7*total:
    print(f"→ KILL: pre-frontal is largely captured by existing axes.  {_pop_tag}")
else:
    print(f"→ MIXED: {ortho} orthogonal across both checks. Narrow promote on the orthogonal cells.  {_pop_tag}")
