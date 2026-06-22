"""Stage 0+ — Simulated MAE if L2 K had been lead-tapered.

The Stage 0 finding (h_lead_l2.py) showed L2's gain decays sharply with lead.
This script asks the actual ship-size question: if K had tapered linearly
from 100% at lead 0 to 0% at lead 24 (mirroring the existing wind ramp),
what would total per-field MAE be vs the current flat K?

Derivation. For each pair we know:
    bias_applied = forecast_l2 - forecast_l1     # K × raw_bias
With a lead-tapered K* = K × ramp(lead):
    new_forecast_l2 = forecast_l1 + bias_applied × ramp(lead)

Ramp shapes tested:
    flat       — control (1.0 everywhere; same as production)
    wind_ramp  — linear 1.0 → 0.0 across leads 0..24 (then 0)
    soft_ramp  — linear 1.0 at 0 → 0.4 at 24h (gain doesn't go to zero)
    half_ramp  — linear 1.0 → 0.0 across leads 0..12 (then 0)
"""
import os, sys, json, argparse
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
L2_FIELDS = {"t", "h", "pr"}  # additive-bias fields (wind already tapered)

ap = argparse.ArgumentParser()
ap.add_argument("--cutoff", default=None)
ap.add_argument("--window-days", type=int, default=7)
args = ap.parse_args()

end_dt = datetime.fromisoformat(args.cutoff) if args.cutoff else datetime.utcnow()
start_dt = end_dt - timedelta(days=args.window_days)
start_iso = start_dt.strftime("%Y-%m-%dT%H:%M")
end_iso = end_dt.strftime("%Y-%m-%dT%H:%M")
print(f"Window: {start_iso} → {end_iso}\n")

RAMPS = {
    "flat":       lambda l: 1.0,
    "wind_ramp":  lambda l: max(0.0, 1.0 - l/24.0),
    "soft_ramp":  lambda l: max(0.4, 1.0 - (1.0-0.4)*l/24.0),
    "half_ramp":  lambda l: max(0.0, 1.0 - l/12.0),
}

# field -> {ramp_name: [n, sum|err|]}
sums = defaultdict(lambda: {k: [0, 0.0] for k in RAMPS})
# Also keep the L1 MAE for context
l1_sums = defaultdict(lambda: [0, 0.0])

with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in L2_FIELDS:
            continue
        ot = r.get("obs_time") or ""
        if not (start_iso <= ot < end_iso):
            continue
        lead = r.get("lead_h")
        if lead is None:
            continue
        f_l1 = r.get("forecast_l1")
        f_l2 = r.get("forecast_l2")
        obs  = r.get("observed")
        if None in (f_l1, f_l2, obs):
            continue
        bias_applied = f_l2 - f_l1
        # L1 MAE for context
        ls = l1_sums[f]
        ls[0] += 1; ls[1] += abs(f_l1 - obs)
        # Each ramp
        for name, ramp_fn in RAMPS.items():
            new_f = f_l1 + bias_applied * ramp_fn(int(lead))
            err = abs(new_f - obs)
            s = sums[f][name]
            s[0] += 1
            s[1] += err

print(f"{'field':<6} {'ramp':<11} {'n':>9} {'MAE':>8} {'Δ vs flat':>10}")
print("-" * 50)
for f in sorted(L2_FIELDS):
    n1, e1 = l1_sums[f]
    flat_n, flat_sum = sums[f]["flat"]
    flat_mae = flat_sum/flat_n if flat_n else None
    print(f"{f:<6} {'(L1 raw)':<11} {n1:>9,} {e1/n1 if n1 else 0:>8.3f}")
    for name in RAMPS:
        n, s = sums[f][name]
        if not n:
            continue
        mae = s/n
        d = (flat_mae - mae)/flat_mae*100 if flat_mae else 0
        print(f"{f:<6} {name:<11} {n:>9,} {mae:>8.3f} {d:>9.2f}%")
    print()
