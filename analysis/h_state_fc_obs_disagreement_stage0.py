"""Stage 0 — State_fc vs state_obs disagreement AT issue time as a C1 axis.

Hypothesis: when the model's cloud/solar state at issue time (`state_fc`)
already disagrees with the observed state (`state_obs`), the forecast is
starting from a bad initial condition and downstream errors are elevated.

Two candidate deltas per row (per-row available, no join needed):
  • cloud_delta = |state_fc.cloud_cover − state_obs.cloud_cover|
  • solar_delta = |state_fc.solar_wm2   − state_obs.solar_wm2|

For each (field, band), bin rows by cloud_delta quartile and solar_delta
quartile. Compare MAE Q1 vs Q4. If elevated MAE at high delta with halves-
stability, PROMOTE as a per-row C1 confidence axis.

Ship shape: new C1 axis on (cloud_delta_bin, solar_delta_bin) — widens CI
when issue-time state is inconsistent with observed state.
"""
import os, sys, json
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

def run_delta(delta_name):
    print(f"\n========== DELTA: {delta_name} ==========")
    spread_vals = defaultdict(list)
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
            sf = r.get("state_fc") or {}
            so = r.get("state_obs") or {}
            v_fc = sf.get(delta_name)
            v_obs = so.get(delta_name)
            if v_fc is None or v_obs is None: continue
            delta = abs(float(v_fc) - float(v_obs))
            err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
            if err is None: continue
            try: odt = datetime.fromisoformat((r.get("obs_time") or "")[:19])
            except Exception: continue
            spread_vals[(f, band)].append(delta)
            all_rows.append((odt, f, band, delta, abs(float(err))))

    quartiles = {}
    for k, arr in spread_vals.items():
        if len(arr) < 4 * MIN_N_BIN: continue
        arr.sort(); n = len(arr)
        quartiles[k] = (arr[n//4], arr[3*n//4])

    sums = defaultdict(lambda: [0, 0.0, 0, 0.0, 0, 0.0])
    all_rows.sort(key=lambda x: x[0])
    if not all_rows: return
    median_dt = all_rows[len(all_rows) // 2][0]
    for odt, f, band, delta, err in all_rows:
        q = quartiles.get((f, band))
        if not q: continue
        q1, q3 = q
        if delta <= q1: b = "Q1"
        elif delta >= q3: b = "Q4"
        else: continue
        s = sums[(f, band, b)]
        s[0] += 1; s[1] += err
        if odt <= median_dt: s[2] += 1; s[3] += err
        else:                s[4] += 1; s[5] += err

    print(f"{'field':<5} {'band':<7} {'n_Q1':>7} {'MAE_Q1':>8} {'n_Q4':>7} {'MAE_Q4':>8} {'ratio':>7} {'halves':>10}  verdict")
    print("-" * 88)
    vc = defaultdict(int)
    for f in FIELDS:
        for label, _, _ in BANDS:
            q1 = sums.get((f, label, "Q1")); q4 = sums.get((f, label, "Q4"))
            if not q1 or not q4 or q1[0] < MIN_N_BIN or q4[0] < MIN_N_BIN: continue
            mae1 = q1[1]/q1[0]; mae4 = q4[1]/q4[0]
            if mae1 == 0: continue
            ratio = mae4/mae1
            mae1a = q1[3]/q1[2] if q1[2] > 0 else 0
            mae1b = q1[5]/q1[4] if q1[4] > 0 else 0
            mae4a = q4[3]/q4[2] if q4[2] > 0 else 0
            mae4b = q4[5]/q4[4] if q4[4] > 0 else 0
            ra = mae4a/mae1a if mae1a > 0 else 0
            rb = mae4b/mae1b if mae1b > 0 else 0
            hs = (ra >= 1.15 and rb >= 1.15)
            if ratio >= 1.30 and hs: v = "PROMOTE"
            elif ratio >= 1.15 and hs: v = "MARGINAL"
            elif 0.90 <= ratio <= 1.10: v = "FLAT"
            elif ratio >= 1.15: v = "UNSTABLE"
            else: v = "HOLD"
            vc[v] += 1
            print(f"{f:<5} {label:<7} {q1[0]:>7,} {mae1:>8.3f} {q4[0]:>7,} {mae4:>8.3f} {ratio:>7.2f}× {ra:.2f}/{rb:.2f}  {v}")
    print(f"  → {delta_name}: PROMOTE {vc['PROMOTE']} / MARGINAL {vc['MARGINAL']} / FLAT {vc['FLAT']} / UNSTABLE {vc['UNSTABLE']} / HOLD {vc['HOLD']}")
    return vc

vc_cloud = run_delta("cloud_cover")
vc_solar = run_delta("solar_wm2")

print("\n" + "=" * 88)
p_c = (vc_cloud or {}).get("PROMOTE", 0)
p_s = (vc_solar or {}).get("PROMOTE", 0)
if p_c >= 3 and p_s >= 3:
    print(f"VERDICT: STAGE 0 PROMOTE — both cloud_delta ({p_c}) and solar_delta ({p_s}) are viable C1 axes.")
elif p_c >= 3:
    print(f"VERDICT: STAGE 0 PROMOTE — cloud_delta ({p_c} cells) is a viable C1 axis; solar_delta HOLD.")
elif p_s >= 3:
    print(f"VERDICT: STAGE 0 PROMOTE — solar_delta ({p_s} cells) is a viable C1 axis; cloud_delta HOLD.")
else:
    print(f"VERDICT: HOLD — state_fc vs state_obs disagreement at issue time is not a strong C1 axis. cloud_delta={p_c}, solar_delta={p_s}.")
