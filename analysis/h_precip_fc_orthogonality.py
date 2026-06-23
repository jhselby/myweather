"""Orthogonality: precip_fc>0 (C1f candidate) vs C1a (transition) AND vs C1e (post-frontal).

Stage 0 (h_forecast_coherence.py) showed precip_fc>0 elevates MAE on every
field (especially cm/cl 5-9× baseline). Check if that elevation persists
within transition=False subset (i.e., independent of C1a) AND outside the
post-frontal window (independent of C1e).
"""
import os, sys, json, urllib.request
from collections import defaultdict
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL  = "https://data.wymancove.com/forecast_error_log.jsonl"
FRONT_URL = "https://data.wymancove.com/frontal_events_log.json"
FIELDS = ("t", "h", "ws", "wg", "cc", "cl", "cm", "ch")
BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]

def lead_band(lh):
    for lab, lo, hi in BANDS:
        if lo <= lh < hi: return lab
    return None

req = urllib.request.Request(FRONT_URL, headers={"User-Agent": "curl/8.4.0"})
with urllib.request.urlopen(req, timeout=15) as r:
    passage_dts = sorted(
        datetime.fromisoformat(e.get("ts","").replace("Z","")[:19])
        for e in json.loads(r.read()).get("entries", []) if e.get("ts")
    )

def hsf(odt):
    lo, hi = 0, len(passage_dts)
    while lo < hi:
        mid = (lo+hi)//2
        if passage_dts[mid] <= odt: lo = mid+1
        else: hi = mid
    return (odt - passage_dts[lo-1]).total_seconds()/3600 if lo > 0 else None

# axes: P=precip_fc>0.01, B=transition, C=post_frontal (hsf<24)
sums = defaultdict(lambda: [0, 0.0])
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
        sf = r.get("state_fc") or {}
        so = r.get("state_obs") or {}
        precip_fc = sf.get("precip_in")
        if precip_fc is None: continue
        rfc = sf.get("regime_synoptic"); rob = so.get("regime_synoptic")
        if not rfc or not rob: continue
        s_hsf = hsf(odt)
        P = precip_fc > 0.01
        B = (rfc != rob)
        C = (s_hsf is not None and s_hsf < 24)
        sums[(f, band, P, B, C)][0] += 1
        sums[(f, band, P, B, C)][1] += abs(err)

def get(f, label, P, B, C):
    n, e = sums.get((f, label, P, B, C), (0, 0.0))
    return n, (e/n if n else 0)

print("precip_fc>0 × C1a (transition) orthogonality")
print(f"{'field':<5} {'band':<7} {'stable_P/base':>14} {'trans_P/base':>13}  verdict")
print("-" * 65)
v1 = defaultdict(int)
for f in FIELDS:
    for lab, _, _ in BANDS:
        n_p_st, m_p_st = get(f, lab, True, False, False)
        n_b_st, m_b_st = get(f, lab, False, False, False)
        n_p_tr, m_p_tr = get(f, lab, True, True, False)
        n_b_tr, m_b_tr = get(f, lab, False, True, False)
        if min(n_p_st, n_b_st, n_p_tr, n_b_tr) < 80:
            continue
        r_st = m_p_st/m_b_st if m_b_st else 0
        r_tr = m_p_tr/m_b_tr if m_b_tr else 0
        if r_st >= 1.30 and r_tr >= 1.30: verdict = "ORTHOGONAL"
        elif r_st <= 1.10: verdict = "REDUNDANT"
        elif r_tr >= 1.30: verdict = "CONFOUNDED"
        else: verdict = "AMBIGUOUS"
        v1[verdict] += 1
        print(f"{f:<5} {lab:<7} {r_st:>13.2f}× {r_tr:>12.2f}×  {verdict}")
    print()
print(f"vs C1a: ORTHOGONAL: {v1['ORTHOGONAL']}, REDUNDANT: {v1['REDUNDANT']}, CONFOUNDED: {v1['CONFOUNDED']}, AMBIGUOUS: {v1['AMBIGUOUS']}\n")

print("precip_fc>0 × C1e (post-frontal) orthogonality")
print(f"{'field':<5} {'band':<7} {'~post_P/base':>14} {'post_P/base':>13}  verdict")
print("-" * 65)
v2 = defaultdict(int)
for f in FIELDS:
    for lab, _, _ in BANDS:
        n_p_np, m_p_np = get(f, lab, True, False, False)
        n_b_np, m_b_np = get(f, lab, False, False, False)
        n_p_p,  m_p_p  = get(f, lab, True,  False, True)
        n_b_p,  m_b_p  = get(f, lab, False, False, True)
        if min(n_p_np, n_b_np, n_p_p, n_b_p) < 80:
            continue
        r_np = m_p_np/m_b_np if m_b_np else 0
        r_p  = m_p_p/m_b_p   if m_b_p  else 0
        if r_np >= 1.30 and r_p >= 1.30: verdict = "ORTHOGONAL"
        elif r_np <= 1.10: verdict = "REDUNDANT"
        elif r_p >= 1.30: verdict = "CONFOUNDED"
        else: verdict = "AMBIGUOUS"
        v2[verdict] += 1
        print(f"{f:<5} {lab:<7} {r_np:>13.2f}× {r_p:>12.2f}×  {verdict}")
    print()
print(f"vs C1e: ORTHOGONAL: {v2['ORTHOGONAL']}, REDUNDANT: {v2['REDUNDANT']}, CONFOUNDED: {v2['CONFOUNDED']}, AMBIGUOUS: {v2['AMBIGUOUS']}")
print()
ortho = v1['ORTHOGONAL'] + v2['ORTHOGONAL']
red   = v1['REDUNDANT'] + v2['REDUNDANT']
total = sum(v1.values()) + sum(v2.values())
if ortho >= 8:
    print(f"→ PROMOTE: precip_fc is independent of both C1a and C1e ({ortho} orthogonal cells).")
elif red / total >= 0.7 if total else False:
    print("→ KILL: precip_fc is captured by existing axes.")
else:
    print(f"→ MIXED: {ortho} orthogonal across both checks. Narrow promote on orthogonal cells.")
