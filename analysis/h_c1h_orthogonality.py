"""Orthogonality: forecast trend-direction widening (C1h candidate)
vs C1f (precip_fc>0) AND vs C1e (post-frontal hours-since-front).

Stage 0 (h_trend_direction.py) showed that when the model commits to a
big change over the next 6h (rising/falling above per-field thresholds),
MAE at the 6h lead is much higher than in "stable" forecasts. Example:
cl rising +922% n=238, cm rising +294% n=376, ch rising +83% n=630,
cc rising +58%, t rising +52% (2026-07-04 read, 3rd direction-stable
read since 06-23).

Question: is the trend-direction signal independent of the incumbent
confidence axes, or is it just those axes in disguise?
  - C1f (precip_fc>0.01): the model committing to a big cloud rise
    often coincides with predicted precip → could be redundant.
  - C1e (hours-since-front, post-frontal 0-24h): frontal transitions
    involve cloud regime changes → could be confounded.

Method:
  Pass 1 — index all pair rows by (run_time, field, lead) → forecast_l1
    so a lookup at lead L can find same-run fc at lead L-6.
  Pass 2 — for each row at lead L≥6, compute:
      H = |fc[L] − fc[L−6]| > THRESH[field]  (trend-direction fires)
      F = precip_fc > 0.01                    (C1f fires)
      E = hours_since_last_front < 24         (C1e fires)
    Bucket (field, lead_band, H, F, E) → (n, sum|err|).
  Verdict per (field, band):
    ORTHOGONAL — H-elevation ratio ≥1.30 within F=False AND F=True (same
                 check vs E=False AND E=True). Independent signal.
    REDUNDANT  — H-elevation ratio ≤1.10 within F=False (or E=False).
                 All elevation lives in the incumbent axis.
    CONFOUNDED — H-elevation only inflated within F=True (or E=True).
                 C1h amplifies the incumbent, doesn't add signal.
    AMBIGUOUS  — everything else.

Overall: PROMOTE if ≥8 orthogonal cells across both checks. KILL if
70%+ redundant. MIXED otherwise → narrow-promote on orthogonal cells.

Skips 0-5h band by construction (no lead L−6 to reference).

Run:
  python3 analysis/h_c1h_orthogonality.py
"""
import os, sys, json, urllib.request
from collections import defaultdict
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL  = "https://data.wymancove.com/forecast_error_log.jsonl"
FRONT_URL = "https://data.wymancove.com/frontal_events_log.json"
FIELDS = ("cc", "cl", "cm", "ch", "t")
# Per-field |Δ| thresholds — mirrors h_trend_direction.py.
THRESH = {"cc": 20, "cl": 15, "cm": 15, "ch": 15, "t": 3}
# 0-5h skipped (no L-6 to compare against in-same-run).
BANDS = [("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
POST_WINDOW_H = 24
MIN_CELL_N = 60  # per-subset minimum for a verdict; smaller than sibling
                 # scripts because the H=True subset is narrow.

def lead_band(lh):
    for lab, lo, hi in BANDS:
        if lo <= lh < hi: return lab
    return None

# --- frontal events for hsf lookup ---
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

# --- Pass 1: index forecasts by (run_time, field, lead) ---
fc_by_key = {}
rows = []  # (field, band, err_abs, fc_L, run_time, lead, F, E)
with open(cached_path(PAIR_URL), "rb") as fh:
    for raw in fh:
        try: r = json.loads(raw)
        except: continue
        f = r.get("field")
        if f not in FIELDS: continue
        rt = r.get("run_time")
        lead = r.get("lead_h")
        fc = r.get("forecast_l1")
        if rt is None or lead is None or fc is None: continue
        lead = int(lead)
        fc_by_key[(rt, f, lead)] = fc

        band = lead_band(lead)
        if band is None:
            # 0-5h — indexed above but no row-record needed
            continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        obs = r.get("observed")
        if err is None or obs is None: continue
        sf = r.get("state_fc") or {}
        precip_fc = sf.get("precip_in")
        if precip_fc is None: continue
        try: odt = datetime.fromisoformat((r.get("obs_time") or "")[:19])
        except: continue
        s_hsf = hsf(odt)
        F = precip_fc > 0.01
        E = (s_hsf is not None and s_hsf < POST_WINDOW_H)
        rows.append((f, band, abs(err), fc, rt, lead, F, E))

# --- Pass 2: compute H per row via L-6 lookup, bucket ---
sums = defaultdict(lambda: [0, 0.0])  # (f, band, H, F, E) -> [n, sum|err|]
for (f, band, err_abs, fc_L, rt, lead, F, E) in rows:
    fc_prev = fc_by_key.get((rt, f, lead - 6))
    if fc_prev is None: continue
    thr = THRESH.get(f, 10)
    H = abs(fc_L - fc_prev) > thr
    sums[(f, band, H, F, E)][0] += 1
    sums[(f, band, H, F, E)][1] += err_abs

def get(f, band, H, F, E):
    n, e = sums.get((f, band, H, F, E), (0, 0.0))
    return n, (e/n if n else 0)

def _verdict(r_off, r_on):
    """r_off = H-fires MAE / H-flat MAE within incumbent-OFF subset.
    r_on = same ratio within incumbent-ON subset."""
    if r_off >= 1.30 and r_on >= 1.30:
        return "ORTHOGONAL"
    if r_off <= 1.10:
        return "REDUNDANT"
    if r_on >= 1.30:
        return "CONFOUNDED"
    return "AMBIGUOUS"

# --- Check 1: C1h vs C1f (precip_fc) ---
print("C1h (trend-direction) × C1f (precip_fc>0.01) orthogonality")
print(f"{'field':<5} {'band':<7} {'H/base F=off':>13} {'H/base F=on':>12}  verdict")
print("-" * 60)
v1 = defaultdict(int)
for f in FIELDS:
    for lab, _, _ in BANDS:
        n_H_off, m_H_off = get(f, lab, True,  False, False)
        n_b_off, m_b_off = get(f, lab, False, False, False)
        n_H_on,  m_H_on  = get(f, lab, True,  True,  False)
        n_b_on,  m_b_on  = get(f, lab, False, True,  False)
        if min(n_H_off, n_b_off, n_H_on, n_b_on) < MIN_CELL_N:
            v1["THIN"] += 1
            continue
        r_off = m_H_off/m_b_off if m_b_off else 0
        r_on  = m_H_on/m_b_on   if m_b_on  else 0
        verdict = _verdict(r_off, r_on)
        v1[verdict] += 1
        print(f"{f:<5} {lab:<7} {r_off:>12.2f}× {r_on:>11.2f}×  {verdict}")
    print()
print(f"vs C1f totals: ORTHOGONAL: {v1['ORTHOGONAL']}, REDUNDANT: {v1['REDUNDANT']}, CONFOUNDED: {v1['CONFOUNDED']}, AMBIGUOUS: {v1['AMBIGUOUS']}, THIN: {v1['THIN']}\n")

# --- Check 2: C1h vs C1e (post-frontal) ---
print("C1h (trend-direction) × C1e (post-frontal <24h) orthogonality")
print(f"{'field':<5} {'band':<7} {'H/base E=off':>13} {'H/base E=on':>12}  verdict")
print("-" * 60)
v2 = defaultdict(int)
for f in FIELDS:
    for lab, _, _ in BANDS:
        n_H_off, m_H_off = get(f, lab, True,  False, False)
        n_b_off, m_b_off = get(f, lab, False, False, False)
        n_H_on,  m_H_on  = get(f, lab, True,  False, True)
        n_b_on,  m_b_on  = get(f, lab, False, False, True)
        if min(n_H_off, n_b_off, n_H_on, n_b_on) < MIN_CELL_N:
            v2["THIN"] += 1
            continue
        r_off = m_H_off/m_b_off if m_b_off else 0
        r_on  = m_H_on/m_b_on   if m_b_on  else 0
        verdict = _verdict(r_off, r_on)
        v2[verdict] += 1
        print(f"{f:<5} {lab:<7} {r_off:>12.2f}× {r_on:>11.2f}×  {verdict}")
    print()
print(f"vs C1e totals: ORTHOGONAL: {v2['ORTHOGONAL']}, REDUNDANT: {v2['REDUNDANT']}, CONFOUNDED: {v2['CONFOUNDED']}, AMBIGUOUS: {v2['AMBIGUOUS']}, THIN: {v2['THIN']}\n")

# --- Overall verdict ---
ortho = v1['ORTHOGONAL'] + v2['ORTHOGONAL']
red   = v1['REDUNDANT']  + v2['REDUNDANT']
judged = sum(v1[k] + v2[k] for k in ('ORTHOGONAL','REDUNDANT','CONFOUNDED','AMBIGUOUS'))
if judged == 0:
    print("→ THIN across the board — insufficient sample for a verdict. Re-run after more window fill.")
elif ortho >= 8:
    print(f"→ PROMOTE C1h: trend-direction is independent of both C1f and C1e ({ortho} orthogonal cells / {judged} judged).")
elif red / judged >= 0.70:
    print(f"→ KILL C1h: trend-direction is captured by existing axes ({red}/{judged} redundant).")
else:
    print(f"→ MIXED: {ortho} orthogonal cells across both checks. Narrow promote on the orthogonal cells only.")
