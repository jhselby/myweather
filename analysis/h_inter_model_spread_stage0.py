"""Stage 0 — Inter-model spread (HRRR vs NBM) as a C1 confidence axis.

Hypothesis: when HRRR and NBM materially disagree at issue time, the resulting
forecast (whichever wins routing) is less trustworthy. This is inter-model
spread, orthogonal by construction to:
  • cluster_spread (intra-model station variance — cloud_inter_source_sigma)
  • cross_run_spread (same-model over consecutive runs — cross_run_spread axis)

Signal: |forecast_l1 − forecast_raw_nbm| per row. Bin by magnitude. Compare
MAE across bins. If wide-spread rows have materially elevated MAE and the
signal is direction-stable across halves, PROMOTE as new C1 axis.

Ship shape (if it clears): additive C1 axis alongside cluster_spread and
cross_run_spread. Widens confidence bounds when models disagree. No
per-field bias correction — pure confidence widening.
"""
import os, sys, json, urllib.request
from collections import defaultdict
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ("t", "h", "ws", "wg", "wd", "cc", "cl", "cm", "ch", "dp", "sr")
BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N_BIN = 200

def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None

# Circular delta for wind direction
def signed_delta(field, a, b):
    if field == "wd":
        d = (a - b) % 360
        if d > 180: d -= 360
        return abs(d)
    return abs(a - b)

# (field, band, spread_bin) -> [n, sum|err|, sum|err|_A, sum|err|_B, n_A, n_B]
sums = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0, 0])

# Two-pass: pass 1 computes per-(field, band) quartiles of spread; pass 2 tabulates MAE by quartile.
# One pass with per-cell reservoir would work but two-pass keeps code readable.
print("Pass 1: computing per-(field, band) spread quartiles...")
spread_values = defaultdict(list)
obs_times = []

with open(cached_path(PAIR_URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in FIELDS: continue
        lead = r.get("lead_h")
        if lead is None: continue
        band = lead_band(int(lead))
        if not band: continue
        f_hrrr = r.get("forecast_l1")
        f_nbm  = r.get("forecast_raw_nbm")
        if f_hrrr is None or f_nbm is None: continue
        spread = signed_delta(f, float(f_hrrr), float(f_nbm))
        spread_values[(f, band)].append(spread)

# Compute per-(field, band) quartile thresholds
quartiles = {}
for key, arr in spread_values.items():
    if len(arr) < 4 * MIN_N_BIN: continue
    arr.sort()
    n = len(arr)
    quartiles[key] = (arr[n // 4], arr[n // 2], arr[3 * n // 4])

print(f"  {len(quartiles)} (field, band) cells have enough data for quartile split\n")

def spread_bin(field, band, spread):
    q = quartiles.get((field, band))
    if not q: return None
    q1, q2, q3 = q
    if spread <= q1: return "Q1"
    if spread <= q2: return "Q2"
    if spread <= q3: return "Q3"
    return "Q4"

# Pass 2: tabulate MAE by (field, band, spread_bin) + halves
print("Pass 2: computing MAE by spread quartile with halves-stability check...")
all_obs_times = []
with open(cached_path(PAIR_URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in FIELDS: continue
        lead = r.get("lead_h")
        if lead is None: continue
        band = lead_band(int(lead))
        if not band: continue
        f_hrrr = r.get("forecast_l1")
        f_nbm  = r.get("forecast_raw_nbm")
        if f_hrrr is None or f_nbm is None: continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None: continue
        try:
            ot = r.get("obs_time")
            odt = datetime.fromisoformat(ot[:19]) if ot else None
        except Exception:
            odt = None
        spread = signed_delta(f, float(f_hrrr), float(f_nbm))
        b = spread_bin(f, band, spread)
        if not b: continue
        all_obs_times.append((odt, f, band, b, abs(float(err))))

# Halves split by median obs_time
timed = [x for x in all_obs_times if x[0] is not None]
timed.sort(key=lambda x: x[0])
if len(timed) < 2:
    print("Insufficient data for halves split.")
    print("VERDICT: THIN — insufficient data.")
    sys.exit(0)
median_dt = timed[len(timed) // 2][0]

for odt, f, band, b, err in timed:
    key = (f, band, b)
    s = sums[key]
    s[0] += 1
    s[1] += err
    if odt <= median_dt:
        s[4] += 1
        s[2] += err
    else:
        s[5] += 1
        s[3] += err

# Report per (field, band): compare Q1 (low spread) vs Q4 (high spread) MAE
print(f"{'field':<5} {'band':<7} {'n_Q1':>7} {'MAE_Q1':>7} {'n_Q4':>7} {'MAE_Q4':>7} {'ratio':>7} {'halves':>10}  verdict")
print("-" * 90)
verdict_count = defaultdict(int)
for f in FIELDS:
    for label, lo, hi in BANDS:
        q1 = sums.get((f, label, "Q1"), [0, 0.0, 0.0, 0.0, 0, 0])
        q4 = sums.get((f, label, "Q4"), [0, 0.0, 0.0, 0.0, 0, 0])
        if q1[0] < MIN_N_BIN or q4[0] < MIN_N_BIN: continue
        mae_q1 = q1[1] / q1[0]
        mae_q4 = q4[1] / q4[0]
        if mae_q1 == 0: continue
        ratio = mae_q4 / mae_q1
        # Halves
        mae_q1_a = (q1[2] / q1[4]) if q1[4] > 0 else 0
        mae_q1_b = (q1[3] / q1[5]) if q1[5] > 0 else 0
        mae_q4_a = (q4[2] / q4[4]) if q4[4] > 0 else 0
        mae_q4_b = (q4[3] / q4[5]) if q4[5] > 0 else 0
        r_a = (mae_q4_a / mae_q1_a) if mae_q1_a > 0 else 0
        r_b = (mae_q4_b / mae_q1_b) if mae_q1_b > 0 else 0
        halves_stable = (r_a >= 1.15 and r_b >= 1.15) or (r_a <= 0.85 and r_b <= 0.85)
        halves_tag = f"{r_a:.2f}/{r_b:.2f}"
        if ratio >= 1.30 and halves_stable:
            verdict = "PROMOTE"
        elif ratio >= 1.15 and halves_stable:
            verdict = "MARGINAL"
        elif 0.90 <= ratio <= 1.10:
            verdict = "FLAT"
        elif not halves_stable and ratio >= 1.15:
            verdict = "UNSTABLE"
        else:
            verdict = "HOLD"
        verdict_count[verdict] += 1
        print(f"{f:<5} {label:<7} {q1[0]:>7,} {mae_q1:>7.3f} {q4[0]:>7,} {mae_q4:>7.3f} {ratio:>7.2f}× {halves_tag:>10}  {verdict}")
    print()

print("=" * 90)
total = sum(verdict_count.values())
print(f"Overall: PROMOTE {verdict_count['PROMOTE']} / MARGINAL {verdict_count['MARGINAL']} / "
      f"FLAT {verdict_count['FLAT']} / UNSTABLE {verdict_count['UNSTABLE']} / HOLD {verdict_count['HOLD']} (of {total} cells judged)")

if total == 0:
    print("VERDICT: THIN — no cells cleared MIN_N_BIN floor")
elif verdict_count["PROMOTE"] >= 3:
    print(f"VERDICT: STAGE 0 PROMOTE — inter-model spread (HRRR-vs-NBM) shows Q4/Q1 MAE ratio ≥ 1.30 halves-stable in {verdict_count['PROMOTE']} cells. Candidate for new C1 axis alongside cluster_spread and cross_run_spread.")
elif verdict_count["MARGINAL"] + verdict_count["PROMOTE"] >= 3:
    print(f"VERDICT: STAGE 0 MARGINAL — {verdict_count['PROMOTE']} PROMOTE + {verdict_count['MARGINAL']} MARGINAL. Watch across 7d.")
else:
    print(f"VERDICT: HOLD — inter-model spread does not yet clear as a C1 axis. PROMOTE {verdict_count['PROMOTE']} / MARGINAL {verdict_count['MARGINAL']} across {total} cells.")
