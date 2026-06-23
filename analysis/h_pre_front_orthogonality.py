"""Orthogonality: pre-frontal (hu<24h) vs C1a (transition) AND vs post-frontal (hsf<24h).

Check if pre-frontal signal is independent of (a) C1a regime-transition penalty
and (b) the C1e post-frontal axis we just promoted. If yes, ship as either an
extension of C1e (bidirectional) or a new C1g axis.
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
sums = defaultdict(lambda: [0, 0.0])  # (field, band, A, B, C) -> [n, sum|err|]
with open(cached_path(PAIR_URL), "rb") as fh:
    for raw in fh:
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
        sums[(f, band, A, B, C)][0] += 1
        sums[(f, band, A, B, C)][1] += abs(err)

# Pairwise: pre-frontal vs each other axis
print("Pre-frontal × C1a (transition) orthogonality")
print(f"{'field':<5} {'band':<6} {'stable_pre/base':>15} {'trans_pre/base':>14}  vs_C1a")
print("-" * 70)
v1 = defaultdict(int)
for f in FIELDS:
    for label, _, _ in BANDS:
        # Within transition=False: pre vs baseline (both axes need C=False to isolate)
        def get(A, B, C):
            n, e = sums.get((f, label, A, B, C), (0, 0.0))
            return n, (e/n if n else 0)
        # post=False, transition=False subset: pre vs baseline
        n_pre_st, m_pre_st = get(True, False, False)
        n_base_st, m_base_st = get(False, False, False)
        n_pre_tr, m_pre_tr = get(True, True, False)
        n_base_tr, m_base_tr = get(False, True, False)
        if min(n_pre_st, n_base_st, n_pre_tr, n_base_tr) < 100:
            continue
        r_st = m_pre_st/m_base_st if m_base_st else 0
        r_tr = m_pre_tr/m_base_tr if m_base_tr else 0
        if r_st >= 1.30 and r_tr >= 1.30:
            verdict = "ORTHOGONAL"
        elif r_st <= 1.10:
            verdict = "REDUNDANT"
        elif r_tr >= 1.30:
            verdict = "CONFOUNDED"
        else:
            verdict = "AMBIGUOUS"
        v1[verdict] += 1
        print(f"{f:<5} {label:<6} {r_st:>14.2f}× {r_tr:>13.2f}×  {verdict}")
    print()
print(f"vs C1a: ORTHOGONAL: {v1['ORTHOGONAL']}, REDUNDANT: {v1['REDUNDANT']}, CONFOUNDED: {v1['CONFOUNDED']}, AMBIGUOUS: {v1['AMBIGUOUS']}\n")

print("Pre-frontal × post-frontal (C1e) orthogonality")
print(f"{'field':<5} {'band':<6} {'~post_pre/base':>15} {'post_pre/base':>14}  vs_C1e")
print("-" * 70)
v2 = defaultdict(int)
for f in FIELDS:
    for label, _, _ in BANDS:
        def get(A, B, C):
            n, e = sums.get((f, label, A, B, C), (0, 0.0))
            return n, (e/n if n else 0)
        # B=False (no transition) and split on C
        n_pre_pf, m_pre_pf = get(True, False, False)   # pre AND not post
        n_base_pf, m_base_pf = get(False, False, False)
        n_pre_p, m_pre_p = get(True, False, True)      # pre AND post (rare)
        n_base_p, m_base_p = get(False, False, True)    # not pre AND post
        if min(n_pre_pf, n_base_pf, n_base_p) < 100:
            continue
        r_no_post = m_pre_pf/m_base_pf if m_base_pf else 0
        # Within post=True: hard to evaluate "pre AND post" if rare
        if n_pre_p < 50:
            r_post = float('nan')
        else:
            r_post = m_pre_p/m_base_p if m_base_p else 0
        if r_no_post >= 1.30 and (r_post != r_post or r_post >= 1.30):
            verdict = "ORTHOGONAL"
        elif r_no_post <= 1.10:
            verdict = "REDUNDANT"
        else:
            verdict = "AMBIGUOUS"
        v2[verdict] += 1
        rp_str = "    n/a" if r_post != r_post else f"{r_post:>13.2f}×"
        print(f"{f:<5} {label:<6} {r_no_post:>14.2f}× {rp_str}  {verdict}")
    print()
print(f"vs C1e: ORTHOGONAL: {v2['ORTHOGONAL']}, REDUNDANT: {v2['REDUNDANT']}, AMBIGUOUS: {v2['AMBIGUOUS']}")
print()
total = sum(v1.values()) + sum(v2.values())
ortho = v1['ORTHOGONAL'] + v2['ORTHOGONAL']
if ortho >= 6:
    print(f"→ PROMOTE: pre-frontal is independent of both C1a and C1e ({ortho} orthogonal cells).")
elif sum(v1[k] for k in ('REDUNDANT',)) + sum(v2[k] for k in ('REDUNDANT',)) >= 0.7*total:
    print("→ KILL: pre-frontal is largely captured by existing axes.")
else:
    print(f"→ MIXED: {ortho} orthogonal across both checks. Narrow promote on the orthogonal cells.")
