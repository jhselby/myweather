"""Orthogonality check: PRE-frontal window (C1e-bidirectional candidate) vs C1a.

Rewritten 2026-09-12 with matched-regime baseline. The prior version
(archived as h_pre_front_orthogonality.skip.py) used a global-baseline
denominator and flip-flopped PROMOTE↔KILL across weekly reads for artifact
reasons — see project_c1e_hsf_kill_investigation + method-fix backlog in
project_hypothesis_backlog.md.

Mirror of h_hsf_orthogonality.py structure, applied to the PRE window
(hours BEFORE the next frontal passage, 0-24h ahead) rather than post.

Method:
  1. Load frontal_events_log.json.
  2. Stream pair log. For each row, tag with:
       pre_group   : "pre" (0-24h before next front) | "baseline" (≥24h before or no upcoming front)
       transition  : True if state_fc.regime_synoptic != state_obs.regime_synoptic
       regime      : state_fc.regime_synoptic (the Simpson's-paradox stratifier)
  3. Cross-tab MAE by (field, lead_band, pre_group, transition, regime).
  4. For each (field, band, transition): matched-regime pre/baseline ratio
     within each regime with MIN_N_REG on both sides, aggregate as
     min(n_pre, n_base)-weighted mean across regimes.

Verdicts (same shape as h_hsf_orthogonality):
  ORTHOGONAL   — pre/baseline ≥ 1.30 in BOTH transition=False AND transition=True
  REDUNDANT    — pre/baseline ≤ 1.10 in transition=False
  CONFOUNDED   — inflated only in transition=True (C1e-pre amplifies C1a)
  AMBIGUOUS    — mixed
  THIN         — <2 regimes populated on both sides

Overall: PROMOTE if ≥3 ORTHOGONAL cells. KILL if ≥80% REDUNDANT.
"""
import os, sys, json, urllib.request
from collections import defaultdict
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL  = "https://data.wymancove.com/forecast_error_log.jsonl"
FRONT_URL = "https://data.wymancove.com/frontal_events_log.json"
FIELDS = ("t", "h", "ws", "wg", "cc", "cl", "cm", "ch", "dp")
BANDS  = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
PRE_WINDOW_H = 24

def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None

print("Loading frontal events...")
req = urllib.request.Request(FRONT_URL, headers={"User-Agent": "curl/8.4.0"})
with urllib.request.urlopen(req, timeout=15) as r:
    front_doc = json.loads(r.read())
events = front_doc.get("entries") or front_doc.get("events") or front_doc.get("frontal_events") or []
passage_dts = sorted(
    datetime.fromisoformat(e.get("ts", "").replace("Z", "").replace("+00:00", "")[:19])
    for e in events if e.get("ts")
)
print(f"  {len(passage_dts)} frontal passages, range {passage_dts[0] if passage_dts else '—'} → {passage_dts[-1] if passage_dts else '—'}\n")

def hours_until_next(obs_dt):
    """Hours until the NEXT frontal passage at or after obs_dt. None if none upcoming."""
    lo, hi = 0, len(passage_dts)
    while lo < hi:
        mid = (lo + hi) // 2
        if passage_dts[mid] < obs_dt:
            lo = mid + 1
        else:
            hi = mid
    if lo == len(passage_dts):
        return None
    delta = (passage_dts[lo] - obs_dt).total_seconds() / 3600
    return delta if delta >= 0 else None

sums = defaultdict(lambda: [0, 0.0])
n_in = n_use = 0
print("Streaming pair log...")
with open(cached_path(PAIR_URL), "rb") as fh:
    for raw in fh:
        n_in += 1
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in FIELDS:
            continue
        try:
            odt = datetime.fromisoformat((r.get("obs_time") or "")[:19])
        except Exception:
            continue
        lead = r.get("lead_h")
        if lead is None:
            continue
        band = lead_band(int(lead))
        if not band:
            continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None:
            continue
        pre_h = hours_until_next(odt)
        # "pre" if within PRE_WINDOW_H hours before next front; "baseline" if further out or no upcoming front.
        if pre_h is None:
            pre_group = "baseline"
        else:
            pre_group = "pre" if pre_h < PRE_WINDOW_H else "baseline"
        sf = (r.get("state_fc") or {}).get("regime_synoptic")
        so = (r.get("state_obs") or {}).get("regime_synoptic")
        if not sf or not so:
            continue
        transition = (sf != so)
        s = sums[(f, band, pre_group, transition, sf)]
        s[0] += 1; s[1] += abs(err)
        n_use += 1
print(f"  {n_use:,} of {n_in:,} pairs joined\n")

MIN_N_REG = 30

def matched_ratio(f, band, transition):
    regimes = set()
    for key in sums.keys():
        if key[0] == f and key[1] == band and key[3] == transition:
            regimes.add(key[4])
    num = 0.0
    wsum = 0.0
    n_pre_total = 0
    n_reg = 0
    for reg in regimes:
        n_p, e_p = sums.get((f, band, "pre", transition, reg), (0, 0.0))
        n_b, e_b = sums.get((f, band, "baseline", transition, reg), (0, 0.0))
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

print(f"{'field':<5} {'band':<7} {'stable_n_pre':>13} {'stable_ratio':>12} {'st_nR':>5}"
      f" {'trans_n_pre':>12} {'trans_ratio':>11} {'tr_nR':>5}  verdict")
print("-" * 100)
verdict_count = defaultdict(int)
for f in FIELDS:
    for label, lo, hi in BANDS:
        st_ratio, st_pre_n, st_nR = matched_ratio(f, label, False)
        tr_ratio, tr_pre_n, tr_nR = matched_ratio(f, label, True)
        if st_nR < 2 or tr_nR < 2:
            continue
        if st_ratio >= 1.30 and tr_ratio >= 1.30:
            verdict = "ORTHOGONAL"
        elif st_ratio <= 1.10:
            verdict = "REDUNDANT"
        elif tr_ratio >= 1.30 and st_ratio < 1.30:
            verdict = "CONFOUNDED"
        else:
            verdict = "AMBIGUOUS"
        verdict_count[verdict] += 1
        print(f"{f:<5} {label:<7} {st_pre_n:>13,} {st_ratio:>11.2f}× {st_nR:>5}"
              f" {tr_pre_n:>12,} {tr_ratio:>10.2f}× {tr_nR:>5}  {verdict}")
    print()

print("=" * 90)
print(f"Overall: ORTHOGONAL: {verdict_count['ORTHOGONAL']}, REDUNDANT: {verdict_count['REDUNDANT']}, "
      f"CONFOUNDED: {verdict_count['CONFOUNDED']}, AMBIGUOUS: {verdict_count['AMBIGUOUS']}")
_pop_pct = (n_use / n_in * 100) if n_in else 0.0
_pop_qual = "THIN" if len(passage_dts) < 15 else "OK"
_pop_tag = f"[n={len(passage_dts)} passages, {_pop_pct:.0f}% join → {_pop_qual}]"
total = sum(verdict_count.values())
if total == 0:
    print(f"  → THIN: all cells under-sampled. Re-run after more frontal passages accumulate.  {_pop_tag}")
elif verdict_count["ORTHOGONAL"] >= 3:
    print(f"  → PROMOTE: pre-frontal window is independent of C1a. Ship as C1e-pre axis (bidirectional companion).  {_pop_tag}")
elif verdict_count["REDUNDANT"] / total >= 0.8:
    print(f"  → KILL: pre-frontal is just C1a re-skinned. No new axis.  {_pop_tag}")
else:
    print(f"  → AMBIGUOUS: ORTHOGONAL fraction {verdict_count['ORTHOGONAL']/total:.0%}. "
          f"Re-run after more frontal passages accumulate.  {_pop_tag}")
