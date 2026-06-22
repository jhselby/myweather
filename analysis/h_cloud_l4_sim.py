"""Stage 0+ — Simulated MAE if cc/cl/cm/ch were added to L4.

Stage 0 (h_cloud_diurnal.py) showed all 4 cloud fields have strong diurnal
bias spreads (cc 33pp, ch 51pp, cl 24pp, cm 25pp). L4 currently excludes
them. This script answers the actual ship-size question:

  If we fit a per-(cloud_field, hour-of-day) L4 correction on a training
  window and apply it on a held-out test window, what is the MAE delta?

Method:
  • Split pair log on obs_time: first 70% train, last 30% test.
  • For each cloud field, training baseline = forecast_l3 (which equals
    forecast_l2 for cc/cl since they're not in L3_FIELDS).
  • Per hour-of-day bin: correction = mean(observed - baseline) over train.
  • Apply mean-zero normalization across 24 bins (so we don't double-count
    L2/L3's overall bias).
  • Test: new_forecast = baseline + correction[hour]. Compute MAE before
    and after.

Decision rule: ≥5% MAE drop on test = strong Stage 1 candidate. ≥3% =
proceed to 7-window confirmation.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
CLOUD_FIELDS = ["cc", "cl", "cm", "ch"]

# Collect all qualifying rows per field
rows_by_field = defaultdict(list)  # field -> [(obs_dt, hour_utc, baseline, observed)]
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in CLOUD_FIELDS:
            continue
        ot = r.get("obs_time") or ""
        if len(ot) < 13:
            continue
        try:
            hour = int(ot[11:13])
        except ValueError:
            continue
        baseline = r.get("forecast_l3")
        obs      = r.get("observed")
        if baseline is None or obs is None:
            continue
        rows_by_field[f].append((ot, hour, baseline, obs))

print(f"{'field':<6} {'n_train':>9} {'n_test':>8} {'MAE base':>9} {'MAE L4':>9} {'Δ%':>7}")
print("-" * 56)
for f in CLOUD_FIELDS:
    rows = rows_by_field[f]
    rows.sort()
    n_train = int(0.7 * len(rows))
    train, test = rows[:n_train], rows[n_train:]
    if len(test) < 500:
        print(f"{f:<6} (too few test rows: {len(test)})")
        continue

    # Per-hour mean residual on train
    bin_sum = defaultdict(float); bin_n = defaultdict(int)
    for _, h, base, obs in train:
        bin_sum[h] += (obs - base); bin_n[h] += 1
    raw_corr = {h: bin_sum[h]/bin_n[h] for h in bin_sum if bin_n[h] > 0}
    # Mean-zero normalize across the 24 bins present
    if raw_corr:
        m = sum(raw_corr.values())/len(raw_corr)
        corr = {h: v - m for h, v in raw_corr.items()}
    else:
        corr = {}

    base_sum = 0.0; l4_sum = 0.0; n = 0
    for _, h, base, obs in test:
        c = corr.get(h, 0.0)
        new_v = max(0.0, min(100.0, base + c))  # clamp to [0,100]
        base_sum += abs(base - obs)
        l4_sum   += abs(new_v - obs)
        n += 1
    mae_b = base_sum / n; mae_l4 = l4_sum / n
    delta = (mae_b - mae_l4) / mae_b * 100 if mae_b > 0 else 0
    print(f"{f:<6} {len(train):>9,} {len(test):>8,} {mae_b:>9.3f} {mae_l4:>9.3f} {delta:>+6.1f}%")
