"""Stage 0 — NWS-optimal cell detection for L1 selector routing.

Current L1 selector picks HRRR OR NBM per (field, band, regime). The pair log
has `forecast_nws` and `error_nws` per row — is NWS ever materially better
than both HRRR and NBM at any (field, band, regime) cell?

If yes, extend L1 selector to 3-way (HRRR / NBM / NWS).

Method:
  1. Per (field, band, regime), compute MAE from error_l1 (HRRR-side),
     error_raw_nbm, error_nws over a rolling 30d window.
  2. Halves-stability check on each of the three sources.
  3. Cell is "NWS-optimal" if NWS_MAE ≤ 0.95 × min(HRRR_MAE, NBM_MAE)
     with n ≥ 200 AND halves-stable direction.

Verdict:
  STAGE 0 PROMOTE if ≥3 NWS-optimal cells found — extend selector to 3-way.
  HOLD otherwise — NWS is either noise or subsumed by HRRR/NBM.
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS   = ("t", "h", "ws", "wg", "wd", "cc", "cl", "cm", "ch", "dp", "sr")
BANDS    = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N = 200
MIN_ADVANTAGE = 0.05  # NWS must be ≥ 5% better than best of HRRR/NBM

def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None

# (field, band, regime) -> {source: [n, sum|err|, n_A, sum_A, n_B, sum_B]}
sums = defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0, 0.0, 0, 0.0]))

print("Streaming pair log...")
rows = []
with open(cached_path(PAIR_URL), "rb") as fh:
    for raw in fh:
        try: r = json.loads(raw)
        except Exception: continue
        f = r.get("field")
        if f not in FIELDS: continue
        lead = r.get("lead_h")
        if lead is None: continue
        band = lead_band(int(lead))
        if not band: continue
        reg = (r.get("state_fc") or {}).get("regime_synoptic")
        if not reg: continue
        e_h = r.get("error_l1")
        e_n = r.get("error_raw_nbm")
        e_w = r.get("error_nws")
        try: odt = datetime.fromisoformat((r.get("obs_time") or "")[:19])
        except Exception: continue
        rows.append((odt, f, band, reg, e_h, e_n, e_w))

rows.sort(key=lambda x: x[0])
if not rows:
    print("VERDICT: THIN"); sys.exit(0)
median_dt = rows[len(rows) // 2][0]

for odt, f, band, reg, e_h, e_n, e_w in rows:
    for src, e in (("hrrr", e_h), ("nbm", e_n), ("nws", e_w)):
        if e is None: continue
        s = sums[(f, band, reg)][src]
        ae = abs(float(e))
        s[0] += 1; s[1] += ae
        if odt <= median_dt: s[2] += 1; s[3] += ae
        else:                s[4] += 1; s[5] += ae

print(f"{'field':<5} {'band':<7} {'regime':<12} {'MAE_hrrr':>9} {'MAE_nbm':>8} {'MAE_nws':>8} {'n_nws':>6}  verdict")
print("-" * 78)
verdict_count = defaultdict(int)
optimal_cells = []
for (f, band, reg), srcs in sorted(sums.items()):
    def mae(src, half=None):
        s = srcs.get(src)
        if not s: return None, 0
        if half == "A": return (s[3]/s[2] if s[2] > 0 else None), s[2]
        if half == "B": return (s[5]/s[4] if s[4] > 0 else None), s[4]
        return (s[1]/s[0] if s[0] > 0 else None), s[0]
    mae_h, n_h = mae("hrrr")
    mae_n, n_n = mae("nbm")
    mae_w, n_w = mae("nws")
    if mae_h is None or mae_n is None or mae_w is None: continue
    if n_w < MIN_N: continue
    best_hnn = min(mae_h, mae_n)
    if mae_w > best_hnn * (1 - MIN_ADVANTAGE):
        verdict = "not-optimal"
    else:
        # Halves check for NWS advantage direction stability
        mae_w_a, _ = mae("nws", "A")
        mae_w_b, _ = mae("nws", "B")
        mae_hn_a = min([m for m, _ in (mae("hrrr", "A"), mae("nbm", "A")) if m is not None] or [1e9])
        mae_hn_b = min([m for m, _ in (mae("hrrr", "B"), mae("nbm", "B")) if m is not None] or [1e9])
        stable = (mae_w_a is not None and mae_w_a < mae_hn_a and
                  mae_w_b is not None and mae_w_b < mae_hn_b)
        verdict = "NWS-OPTIMAL ★" if stable else "unstable"
        if stable:
            optimal_cells.append((f, band, reg, mae_h, mae_n, mae_w, n_w))
    verdict_count[verdict] += 1
    if verdict in ("NWS-OPTIMAL ★", "unstable"):
        print(f"{f:<5} {band:<7} {reg:<12} {mae_h:>9.3f} {mae_n:>8.3f} {mae_w:>8.3f} {n_w:>6,}  {verdict}")

print("=" * 78)
print(f"NWS-OPTIMAL cells: {verdict_count['NWS-OPTIMAL ★']} · unstable: {verdict_count['unstable']} · not-optimal: {verdict_count['not-optimal']}")
if verdict_count["NWS-OPTIMAL ★"] >= 3:
    print(f"VERDICT: STAGE 0 PROMOTE — NWS beats both HRRR and NBM in {verdict_count['NWS-OPTIMAL ★']} halves-stable cells. Extend L1 selector to 3-way (HRRR/NBM/NWS).")
    print("NWS-optimal cells:")
    for f, band, reg, mh, mn, mw in [(x[0], x[1], x[2], x[3], x[4], x[5]) for x in optimal_cells]:
        adv = (min(mh, mn) - mw) / min(mh, mn) * 100
        print(f"  {f}/{band}/{reg}: NWS {mw:.3f} vs best-of-HRRR-NBM {min(mh, mn):.3f} (advantage {adv:.1f}%)")
else:
    print(f"VERDICT: HOLD — NWS is not decisively best in ≥3 halves-stable cells. Selector's 2-way (HRRR/NBM) is correct.")
