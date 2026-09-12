"""Stage 0 — Three-way inter-model spread (HRRR × NBM × NWS) as a C1 axis.

Extension of h_inter_model_spread_stage0 (which uses |HRRR − NBM| pairwise).
The pair log carries `forecast_l1` (HRRR-side), `forecast_raw_nbm`, and
`forecast_nws` per row — genuine three-model disagreement is computable.

Hypothesis: three-way spread is a stronger error predictor than pairwise
because when all three models disagree, forecast uncertainty is higher than
when any two happen to agree.

Metric: sample std-dev across the three forecasts per row. For wd, use
matched-pair circular delta (avg of the three pairwise circular deltas).

If Q4/Q1 ratios EXCEED the two-way spread's ratios AND clear halves-stable,
this axis supersedes the two-way. If ratios are similar or worse, keep the
two-way (already at Stage 2).
"""
import os, sys, json, math
from collections import defaultdict
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS   = ("t", "h", "ws", "wg", "wd", "cc", "cl", "cm", "ch", "dp", "sr")
BANDS    = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N_BIN = 150

def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None

def circ_delta(a, b):
    d = (a - b) % 360
    if d > 180: d -= 360
    return abs(d)

def three_way_spread(field, hrrr, nbm, nws):
    vals = [v for v in (hrrr, nbm, nws) if v is not None]
    if len(vals) < 3:  # require all three
        return None
    if field == "wd":
        # average of pairwise circular deltas
        d = [circ_delta(vals[i], vals[j]) for i in range(3) for j in range(i+1, 3)]
        return sum(d) / 3
    # sample std of three values
    m = sum(vals) / 3
    return math.sqrt(sum((v - m) ** 2 for v in vals) / 3)

# Pass 1: quartile thresholds
print("Pass 1: quartile thresholds on three-way spread...")
spread_vals = defaultdict(list)
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
        s = three_way_spread(f, r.get("forecast_l1"), r.get("forecast_raw_nbm"), r.get("forecast_nws"))
        if s is None: continue
        spread_vals[(f, band)].append(s)

quartiles = {}
for k, arr in spread_vals.items():
    if len(arr) < 4 * MIN_N_BIN: continue
    arr.sort()
    n = len(arr)
    quartiles[k] = (arr[n//4], arr[3*n//4])
print(f"  {len(quartiles)} (field, band) cells have quartile split\n")

# Pass 2: tabulate MAE by (field, band, spread_bin) with halves
sums = defaultdict(lambda: [0, 0.0, 0, 0.0, 0, 0.0])  # [n, sum|err|, n_A, sum_A, n_B, sum_B]
all_rows = []
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
        s = three_way_spread(f, r.get("forecast_l1"), r.get("forecast_raw_nbm"), r.get("forecast_nws"))
        if s is None: continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None: continue
        try: odt = datetime.fromisoformat((r.get("obs_time") or "")[:19])
        except Exception: continue
        q = quartiles.get((f, band))
        if not q: continue
        q1, q3 = q
        if   s <= q1: b = "Q1"
        elif s >= q3: b = "Q4"
        else: b = None
        if b is None: continue
        all_rows.append((odt, f, band, b, abs(float(err))))

timed = sorted(all_rows, key=lambda x: x[0])
if not timed:
    print("VERDICT: THIN"); sys.exit(0)
median_dt = timed[len(timed) // 2][0]
for odt, f, band, b, err in timed:
    key = (f, band, b)
    s = sums[key]
    s[0] += 1; s[1] += err
    if odt <= median_dt: s[2] += 1; s[3] += err
    else:                s[4] += 1; s[5] += err

print(f"{'field':<5} {'band':<7} {'n_Q1':>7} {'MAE_Q1':>8} {'n_Q4':>7} {'MAE_Q4':>8} {'ratio':>7} {'halves':>10}  verdict")
print("-" * 92)
verdict_count = defaultdict(int)
for f in FIELDS:
    for label, _, _ in BANDS:
        q1 = sums.get((f, label, "Q1"))
        q4 = sums.get((f, label, "Q4"))
        if not q1 or not q4 or q1[0] < MIN_N_BIN or q4[0] < MIN_N_BIN: continue
        mae1 = q1[1] / q1[0]
        mae4 = q4[1] / q4[0]
        if mae1 == 0: continue
        ratio = mae4 / mae1
        mae1a = q1[3]/q1[2] if q1[2] > 0 else 0
        mae1b = q1[5]/q1[4] if q1[4] > 0 else 0
        mae4a = q4[3]/q4[2] if q4[2] > 0 else 0
        mae4b = q4[5]/q4[4] if q4[4] > 0 else 0
        ra = mae4a/mae1a if mae1a > 0 else 0
        rb = mae4b/mae1b if mae1b > 0 else 0
        halves_stable = (ra >= 1.15 and rb >= 1.15)
        if ratio >= 1.30 and halves_stable: v = "PROMOTE"
        elif ratio >= 1.15 and halves_stable: v = "MARGINAL"
        elif 0.90 <= ratio <= 1.10: v = "FLAT"
        elif ratio >= 1.15 and not halves_stable: v = "UNSTABLE"
        else: v = "HOLD"
        verdict_count[v] += 1
        print(f"{f:<5} {label:<7} {q1[0]:>7,} {mae1:>8.3f} {q4[0]:>7,} {mae4:>8.3f} {ratio:>7.2f}× {ra:.2f}/{rb:.2f}  {v}")
    print()

print("=" * 92)
total = sum(verdict_count.values())
print(f"Overall: PROMOTE {verdict_count['PROMOTE']} / MARGINAL {verdict_count['MARGINAL']} / "
      f"FLAT {verdict_count['FLAT']} / UNSTABLE {verdict_count['UNSTABLE']} / HOLD {verdict_count['HOLD']} (of {total} cells)")
if verdict_count["PROMOTE"] >= 3:
    print(f"VERDICT: STAGE 0 PROMOTE — 3-way spread {verdict_count['PROMOTE']} cells clear ratio ≥ 1.30 halves-stable. Compare vs 2-way spread (v0.6.593) — supersede if ratios materially larger.")
else:
    print(f"VERDICT: HOLD — 3-way spread doesn't beat 2-way. Keep the pair-log 2-way axis on the wire path.")
