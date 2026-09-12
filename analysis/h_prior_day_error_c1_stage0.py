"""Stage 0 — Prior-day-error as a C1 confidence axis.

Hypothesis: forecast error persists ACROSS days. If yesterday's forecast for
today (same valid-hour, same lead-band) missed badly, today's forecast for
tomorrow's same valid-hour will also miss more than average. This is
persistence of forecast SKILL, not persistence of state — a temporal
confidence signal orthogonal to cross_run_spread (same-model temporal
variance) and cluster_spread (station-level).

Method: for each pair-log row R at (field, lead_h, valid_time), find the
"prior-day analogue" R' at (field, lead_h, valid_time − 24h). |err(R')|
becomes today's prior_day_err feature. Bin by prior_day_err. Compare MAE
across bins. If high-prior-err rows have systematically elevated today's
MAE with halves-stability, PROMOTE as new C1 axis.

Ship shape (if it clears): additive C1 axis; widens confidence intervals
when the model was recently wrong at this lead+time-of-day. No bias
correction — pure confidence signal.

Verdict: PROMOTE if ≥3 (field, band) cells show Q4/Q1 MAE ratio ≥ 1.30
halves-stable AND ≥ MIN_N in each quartile.
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS   = ("t", "h", "ws", "wg", "cc", "cl", "cm", "ch", "dp", "sr")
BANDS    = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N_BIN = 150

def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None

# Index: (field, lead_h, valid_iso_hour) -> abs(error_final)
# Use valid_time truncated to hour as the join key. err_final is |error| (top-level).
print("Streaming pair log, building index...")
by_key = {}
rows = []
n_in = 0
with open(cached_path(PAIR_URL), "rb") as fh:
    for raw in fh:
        n_in += 1
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
        vt = r.get("valid_time")
        if not vt: continue
        try:
            vdt = datetime.fromisoformat(vt[:19])
        except Exception:
            continue
        err = r.get("error")
        if err is None:
            err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None: continue
        abs_err = abs(float(err))
        key = (f, int(lead), vdt.replace(minute=0, second=0, microsecond=0))
        by_key[key] = abs_err
        rows.append((f, int(lead), band, vdt, abs_err))
print(f"  {len(rows):,} rows indexed\n")

# For each row, look up prior-day analogue and store (field, band, prior_day_err, today_err, obs_time)
print("Joining prior-day analogues...")
joined = []
for f, lead, band, vdt, err in rows:
    prior_key = (f, lead, vdt - timedelta(hours=24))
    prior_err = by_key.get(prior_key)
    if prior_err is None: continue
    joined.append((f, band, prior_err, err, vdt))
print(f"  {len(joined):,} rows joined to a prior-day analogue\n")

# Per-(field, band) quartile split on prior_day_err. Bin today's errors accordingly.
per_cell = defaultdict(list)
for f, band, prior, today, vdt in joined:
    per_cell[(f, band)].append((prior, today, vdt))

# Compute quartile thresholds + tabulate MAE by quartile with halves check
print(f"{'field':<5} {'band':<7} {'n_Q1':>7} {'MAE_Q1':>7} {'n_Q4':>7} {'MAE_Q4':>7} {'ratio':>7} {'halves':>10}  verdict")
print("-" * 90)
verdict_count = defaultdict(int)
for f in FIELDS:
    for label, _, _ in BANDS:
        arr = per_cell.get((f, label), [])
        if len(arr) < 4 * MIN_N_BIN: continue
        arr.sort(key=lambda x: x[0])
        n = len(arr)
        q1_slice = arr[:n // 4]
        q4_slice = arr[3 * n // 4:]
        # Chronological median for halves
        by_time = sorted(arr, key=lambda x: x[2])
        median_dt = by_time[n // 2][2]
        def stats(slc):
            if not slc: return 0, 0.0, 0, 0.0, 0, 0.0
            n_all = len(slc)
            mae_all = sum(x[1] for x in slc) / n_all
            a = [x for x in slc if x[2] <= median_dt]
            b = [x for x in slc if x[2] >  median_dt]
            mae_a = (sum(x[1] for x in a) / len(a)) if a else 0.0
            mae_b = (sum(x[1] for x in b) / len(b)) if b else 0.0
            return n_all, mae_all, len(a), mae_a, len(b), mae_b
        n_q1, mae_q1, _, mae_q1_a, _, mae_q1_b = stats(q1_slice)
        n_q4, mae_q4, _, mae_q4_a, _, mae_q4_b = stats(q4_slice)
        if n_q1 < MIN_N_BIN or n_q4 < MIN_N_BIN or mae_q1 == 0: continue
        ratio = mae_q4 / mae_q1
        r_a = (mae_q4_a / mae_q1_a) if mae_q1_a > 0 else 0
        r_b = (mae_q4_b / mae_q1_b) if mae_q1_b > 0 else 0
        halves_stable = (r_a >= 1.15 and r_b >= 1.15)
        halves_tag = f"{r_a:.2f}/{r_b:.2f}"
        if ratio >= 1.30 and halves_stable: verdict = "PROMOTE"
        elif ratio >= 1.15 and halves_stable: verdict = "MARGINAL"
        elif 0.90 <= ratio <= 1.10: verdict = "FLAT"
        elif ratio >= 1.15 and not halves_stable: verdict = "UNSTABLE"
        else: verdict = "HOLD"
        verdict_count[verdict] += 1
        print(f"{f:<5} {label:<7} {n_q1:>7,} {mae_q1:>7.3f} {n_q4:>7,} {mae_q4:>7.3f} {ratio:>7.2f}× {halves_tag:>10}  {verdict}")
    print()

print("=" * 90)
total = sum(verdict_count.values())
print(f"Overall: PROMOTE {verdict_count['PROMOTE']} / MARGINAL {verdict_count['MARGINAL']} / "
      f"FLAT {verdict_count['FLAT']} / UNSTABLE {verdict_count['UNSTABLE']} / HOLD {verdict_count['HOLD']} (of {total} cells)")
if total == 0:
    print("VERDICT: THIN — no cells cleared MIN_N_BIN floor")
elif verdict_count["PROMOTE"] >= 3:
    print(f"VERDICT: STAGE 0 PROMOTE — prior-day error is a C1 axis candidate. {verdict_count['PROMOTE']} cells clear ratio ≥ 1.30 halves-stable.")
elif verdict_count["MARGINAL"] + verdict_count["PROMOTE"] >= 3:
    print(f"VERDICT: STAGE 0 MARGINAL — {verdict_count['PROMOTE']} PROMOTE + {verdict_count['MARGINAL']} MARGINAL. Watch across 7d.")
else:
    print(f"VERDICT: HOLD — prior-day error does not clear as a C1 axis.")
