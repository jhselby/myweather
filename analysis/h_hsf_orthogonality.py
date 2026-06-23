"""Orthogonality check: hours-since-front (C1e candidate) vs C1a (R6 transition).

Background: h_hours_since_front.py showed huge cloud-field MAE elevation in
the 0-24h post-frontal window — ch +253%, cc +94%, cm +60%. Question: is this
just the same pairs that C1a (regime-transition penalty) already flags?
Or is hours-since-front capturing an independent signal?

Method:
  1. Load frontal_events_log.json (curl-spoofed UA).
  2. Stream pair log. For each row, tag with:
       hsf_group   : "post" (0-24h since last front) | "baseline" (≥24h)
       transition  : True if state_fc.regime_synoptic != state_obs.regime_synoptic
  3. Cross-tab MAE by (field, lead_band, hsf_group, transition).
  4. For each (field, band): does post/baseline MAE ratio hold WITHIN
     transition=False subset? If yes → orthogonal. If ratio collapses
     to ~1.0 on transition=False → redundant with C1a.

Verdicts per (field, band):
  ORTHOGONAL   — post/baseline >= 1.30 within transition=False AND
                 within transition=True. Independent signal.
  REDUNDANT    — post/baseline <= 1.10 within transition=False.
                 All elevation is C1a in disguise.
  CONFOUNDED   — post/baseline only inflated within transition=True.
                 C1e amplifies C1a, doesn't add signal.
  THIN         — Insufficient sample in one or more subsets.

Overall: PROMOTE if ≥3 (field, band) ORTHOGONAL. KILL if ≥80% REDUNDANT.
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
POST_WINDOW_H = 24

def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None

# Load frontal passages
print("Loading frontal events...")
req = urllib.request.Request(FRONT_URL, headers={"User-Agent": "curl/8.4.0"})
with urllib.request.urlopen(req, timeout=15) as r:
    front_doc = json.loads(r.read())
events = front_doc.get("entries") or front_doc.get("events") or front_doc.get("frontal_events") or []
passage_dts = sorted(
    datetime.fromisoformat(e.get("ts", "").replace("Z", "").replace("+00:00", "")[:19])
    for e in events if e.get("ts")
)
print(f"  {len(passage_dts)} frontal passages, range {passage_dts[0]} → {passage_dts[-1]}\n")

def hours_since(obs_dt):
    lo, hi = 0, len(passage_dts)
    while lo < hi:
        mid = (lo + hi) // 2
        if passage_dts[mid] <= obs_dt:
            lo = mid + 1
        else:
            hi = mid
    if lo == 0:
        return None
    delta = (obs_dt - passage_dts[lo - 1]).total_seconds() / 3600
    return delta if delta >= 0 else None

# (field, band, hsf_group, transition) -> [n, sum|err|]
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
        hsf = hours_since(odt)
        if hsf is None:
            continue
        hsf_group = "post" if hsf < POST_WINDOW_H else "baseline"
        sf = (r.get("state_fc") or {}).get("regime_synoptic")
        so = (r.get("state_obs") or {}).get("regime_synoptic")
        if not sf or not so:
            continue
        transition = (sf != so)
        s = sums[(f, band, hsf_group, transition)]
        s[0] += 1; s[1] += abs(err)
        n_use += 1
print(f"  {n_use:,} of {n_in:,} pairs joined\n")

# Per (field, band): compute post/baseline ratio for each transition subset
print(f"{'field':<5} {'band':<7} {'stable_n_post':>13} {'stable_ratio':>12} {'trans_n_post':>12} {'trans_ratio':>11}  verdict")
print("-" * 90)
verdict_count = defaultdict(int)
for f in FIELDS:
    for label, lo, hi in BANDS:
        cells = {(g, t): sums.get((f, label, g, t), (0, 0.0))
                 for g in ("post", "baseline") for t in (False, True)}
        # Check sample sizes
        thin = any(c[0] < 100 for c in cells.values())
        if thin:
            continue
        # Stable (transition=False) ratio
        st_post_n, st_post_e = cells[("post", False)]
        st_base_n, st_base_e = cells[("baseline", False)]
        st_ratio = (st_post_e/st_post_n) / (st_base_e/st_base_n) if st_base_e > 0 else 0
        # Transition (transition=True) ratio
        tr_post_n, tr_post_e = cells[("post", True)]
        tr_base_n, tr_base_e = cells[("baseline", True)]
        tr_ratio = (tr_post_e/tr_post_n) / (tr_base_e/tr_base_n) if tr_base_e > 0 else 0
        # Verdict
        if st_ratio >= 1.30 and tr_ratio >= 1.30:
            verdict = "ORTHOGONAL"
        elif st_ratio <= 1.10:
            verdict = "REDUNDANT"
        elif tr_ratio >= 1.30 and st_ratio < 1.30:
            verdict = "CONFOUNDED"
        else:
            verdict = "AMBIGUOUS"
        verdict_count[verdict] += 1
        print(f"{f:<5} {label:<7} {st_post_n:>13,} {st_ratio:>11.2f}× {tr_post_n:>12,} {tr_ratio:>10.2f}×  {verdict}")
    print()

print("=" * 90)
print(f"Overall: ORTHOGONAL: {verdict_count['ORTHOGONAL']}, REDUNDANT: {verdict_count['REDUNDANT']}, "
      f"CONFOUNDED: {verdict_count['CONFOUNDED']}, AMBIGUOUS: {verdict_count['AMBIGUOUS']}")
total = sum(verdict_count.values())
if total == 0:
    print("  → THIN: all cells under-sampled. Re-run after more frontal passages accumulate.")
elif verdict_count["ORTHOGONAL"] >= 3:
    print("  → PROMOTE: hours-since-front is independent of C1a. Ship as C1e axis.")
elif verdict_count["REDUNDANT"] / total >= 0.8:
    print("  → KILL: hours-since-front is just C1a re-skinned. Fold into C1a's bias table if anywhere.")
else:
    print(f"  → AMBIGUOUS: ORTHOGONAL fraction {verdict_count['ORTHOGONAL']/total:.0%}. "
          "Re-run after more frontal passages accumulate.")
