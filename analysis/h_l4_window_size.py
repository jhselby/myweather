"""Stage 0 — L4 fit-window size sweep.

L4 is currently fit on a 30-day window with exponential recency weighting
(τ=14d). Does a shorter rolling window (7d, 14d) track seasonal shifts
better, or does the longer window's larger sample beat noise?

Method: simulate. Pick a cutoff. Train L4 on last N days ending at the
cutoff; test on the 7 days after. Try N ∈ {7, 14, 21, 30}.

L4 = per-(field, hour-of-day) mean residual on top of L3, mean-zero
normalized. Apply to test, measure MAE.
"""
import os, sys, json, argparse
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = {"ch", "cm", "ws", "wg", "pp", "t", "h", "pr"}

ap = argparse.ArgumentParser()
ap.add_argument("--test-end", default=None)
args = ap.parse_args()

test_end = datetime.fromisoformat(args.test_end) if args.test_end else datetime.utcnow()
test_start = test_end - timedelta(days=7)
test_start_iso = test_start.strftime("%Y-%m-%dT%H:%M")
test_end_iso = test_end.strftime("%Y-%m-%dT%H:%M")

# Per-window-size: collect train rows
train_window_sizes = [7, 14, 21, 30]
# field -> list of (obs_dt_iso, hour, baseline, observed)
train_rows = defaultdict(list)
test_rows  = defaultdict(list)
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in FIELDS:
            continue
        ot = r.get("obs_time") or ""
        if len(ot) < 13:
            continue
        try:
            hour = int(ot[11:13])
        except ValueError:
            continue
        baseline = r.get("forecast_l3") or r.get("forecast_l2") or r.get("forecast_l1")
        obs = r.get("observed")
        if baseline is None or obs is None:
            continue
        if test_start_iso <= ot < test_end_iso:
            test_rows[f].append((ot, hour, baseline, obs))
        elif ot < test_start_iso:
            train_rows[f].append((ot, hour, baseline, obs))

print(f"Test window: {test_start_iso} → {test_end_iso}\n")
print(f"{'field':<6} {'win d':>6} {'n_tr':>9} {'n_te':>8} {'MAE_l3':>8} {'MAE_l4':>8} {'Δ%':>7}")
print("-" * 60)
for f in sorted(FIELDS):
    test = test_rows[f]
    if len(test) < 200:
        continue
    train = train_rows[f]
    # MAE_l3 = baseline MAE on test
    mae_l3 = sum(abs(b - o) for _, _, b, o in test) / len(test)

    for win in train_window_sizes:
        train_start = (test_start - timedelta(days=win)).strftime("%Y-%m-%dT%H:%M")
        win_train = [t for t in train if t[0] >= train_start]
        if len(win_train) < 500:
            continue
        bin_sum = defaultdict(float); bin_n = defaultdict(int)
        for _, h, base, obs in win_train:
            bin_sum[h] += (obs - base); bin_n[h] += 1
        raw_corr = {h: bin_sum[h]/bin_n[h] for h in bin_sum if bin_n[h] > 0}
        if raw_corr:
            m = sum(raw_corr.values())/len(raw_corr)
            corr = {h: v - m for h, v in raw_corr.items()}
        else:
            corr = {}
        l4_sum = sum(abs(base + corr.get(h, 0.0) - obs) for _, h, base, obs in test)
        mae_l4 = l4_sum / len(test)
        delta = (mae_l3 - mae_l4)/mae_l3*100 if mae_l3 > 0 else 0
        print(f"{f:<6} {win:>6} {len(win_train):>9,} {len(test):>8,} {mae_l3:>8.3f} {mae_l4:>8.3f} {delta:>+6.1f}%")
    print()
