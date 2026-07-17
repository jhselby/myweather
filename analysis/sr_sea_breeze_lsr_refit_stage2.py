"""sr sea_breeze Lsr refit — Stage 2 preview (cc-gated).

Follow-on to Stage 1 (`sr_sea_breeze_lsr_refit_stage1.py`), which found
pooled sea_breeze MAE improves +43.7% when swapping current-Prod Lsr for
per-hour-bias-corrected `forecast_shortwave`. The 2026-07-17 cross-cut
showed the pooled win is cloud-conditional inside sea_breeze:

  cc bin    Δ%       verdict
  0-25    +25.1%     SHIP (clear-sky over-prediction, stable)
  25-50   -44.2%     SKIP (partly-cloudy — fc_sw doesn't model broken cloud)
  50-75   -42.8%     SKIP (same)
  75-100  +34.3%     MARGIN (overcast under-prediction, stable-ish)

Physical read: fc_shortwave has a stable step-function bias against clear
and overcast skies but is genuinely noisy against partly-cloudy. Applying
the intervention uniformly costs the wins in the middle bins.

Stage 2 hypothesis: gate the intervention to (cc < 25) OR (cc >= 75)
within sea_breeze; keep current Prod Lsr elsewhere. Fit the per-hour bias
on cc-gated train rows only. Verify per-cell (hour, lead_band) with
halves-stability on test.

Method:
  1. Pull sr pair rows in sea_breeze regime.
  2. Split earliest 60% = train, latest 40% = test.
  3. Compute cc_gated flag per row: (cc < CC_LO) OR (cc >= CC_HI).
  4. On train ∩ cc_gated: fit per-hour signed bias (fc_sw - obs).
  5. On test: pooled and per-cell MAE, baseline vs gated intervention.
     Gated intervention = if cc_gated: fc_sw - bias(hod); else fc_l4.
  6. Halves-stability: test halves (by date), both must show gated ≥ baseline.

Ship gate (mirror Stage 1 + per-cell):
  PROMOTE — pooled Δ ≥ 5%, both halves ≥ 0, no cell axis has SKIP that
            outweighs the wins.

Run:
    python3 analysis/sr_sea_breeze_lsr_refit_stage2.py

Emits:
    analysis/output/sr_sea_breeze_lsr_refit_stage2.txt
    analysis/output/sr_sea_breeze_lsr_refit_stage2.json
    weather_collector/data/sr_sea_breeze_lsr_curated.json  (preview, not wired)
"""
import json
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"

OUT_TXT = os.path.join(SCRIPT_DIR, "output", "sr_sea_breeze_lsr_refit_stage2.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "sr_sea_breeze_lsr_refit_stage2.json")
CURATED_JSON = os.path.abspath(os.path.join(
    SCRIPT_DIR, "..", "weather_collector", "data", "sr_sea_breeze_lsr_curated.json"
))

FIELD = "sr"
REGIME = "sea_breeze"

# cc gate: apply intervention only for clear or overcast skies
CC_LO = 25.0    # apply if cc < CC_LO
CC_HI = 75.0    # apply if cc >= CC_HI

# Fit floors
MIN_N_HOUR_FIT = 15    # min train pairs to fit a per-hour bias (else use overall)
FLOOR_PCT = 5.0        # ship-gate on pooled test Δ
MIN_N_CELL = 30        # cell size to render a verdict

LEAD_BANDS = [("0-5", 0, 5), ("6-11", 6, 11), ("12-23", 12, 23), ("24-47", 24, 47)]


def lead_band(h):
    for name, lo, hi in LEAD_BANDS:
        if lo <= h <= hi:
            return name
    return None


def cc_gated(cc):
    if cc is None:
        return False
    return cc < CC_LO or cc >= CC_HI


def load_rows():
    rows = []
    with open(cached_path(URL)) as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("field") != FIELD:
                continue
            state_fc = r.get("state_fc") or {}
            if state_fc.get("regime_synoptic") != REGIME:
                continue
            fc_sw = r.get("forecast_shortwave")
            obs = r.get("observed")
            fc_l4 = r.get("forecast_l4")
            obs_time = r.get("obs_time")
            lead_h = r.get("lead_h")
            if None in (fc_sw, obs, fc_l4, obs_time, lead_h):
                continue
            try:
                hod = int(obs_time[11:13])
            except (ValueError, IndexError):
                continue
            rows.append({
                "obs_time": obs_time,
                "hod": hod,
                "lead_h": lead_h,
                "fc_sw": fc_sw,
                "obs": obs,
                "fc_l4": fc_l4,
                "cc": state_fc.get("cloud_cover"),
            })
    rows.sort(key=lambda x: x["obs_time"])
    return rows


def fit_hourly_bias(train_rows):
    """Per-hour signed bias (fc_sw - obs) on train rows that pass cc gate."""
    gated = [r for r in train_rows if cc_gated(r["cc"])]
    per_hour = defaultdict(list)
    for r in gated:
        per_hour[r["hod"]].append(r["fc_sw"] - r["obs"])
    fit = {}
    all_signed = []
    for h, errs in per_hour.items():
        all_signed.extend(errs)
        if len(errs) >= MIN_N_HOUR_FIT:
            fit[h] = sum(errs) / len(errs)
    overall = sum(all_signed) / len(all_signed) if all_signed else 0.0
    return fit, overall, len(gated)


def intervention_forecast(r, bias_by_hour, overall_bias):
    """Gated intervention: cc-eligible rows use bias-corrected fc_sw; else Prod L4."""
    if not cc_gated(r["cc"]):
        return r["fc_l4"]
    bias = bias_by_hour.get(r["hod"], overall_bias)
    return r["fc_sw"] - bias


def mae_pair(rows, bias, overall):
    n = len(rows)
    if n == 0:
        return None, None, 0
    b_sum = i_sum = 0.0
    for r in rows:
        b_sum += abs(r["fc_l4"] - r["obs"])
        i_sum += abs(intervention_forecast(r, bias, overall) - r["obs"])
    return b_sum / n, i_sum / n, n


def stratify(rows, keyfn):
    d = defaultdict(list)
    for r in rows:
        k = keyfn(r)
        if k is not None:
            d[k].append(r)
    return d


def halves_split(rows):
    n = len(rows)
    mid = n // 2
    return rows[:mid], rows[mid:]


def cell_verdict(pooled_dpct, half_a_dpct, half_b_dpct, n):
    if n < MIN_N_CELL:
        return "THIN"
    if pooled_dpct is None:
        return "THIN"
    ha = half_a_dpct if half_a_dpct is not None else 0.0
    hb = half_b_dpct if half_b_dpct is not None else 0.0
    if pooled_dpct >= FLOOR_PCT and ha >= 0 and hb >= 0:
        return "SHIP"
    if pooled_dpct >= FLOOR_PCT:
        return "MARGIN"
    return "SKIP"


def render_axis(label, cells, halves, bias, overall, out_lines):
    ha, hb = halves
    cells_a = stratify(ha, lambda r, l=label: axis_key(r, l))
    cells_b = stratify(hb, lambda r, l=label: axis_key(r, l))
    out_lines.append("")
    out_lines.append(f"=== per-{label} on TEST (baseline = Prod L4;  intervention = cc-gated fc_sw - bias(hod)) ===")
    out_lines.append(f"  {'cell':<10} {'n_test':>7}  {'base':>8}  {'inter':>8}  {'Δ%':>7}   {'halves(A,B)':>15}   verdict")
    counts = {"SHIP": 0, "MARGIN": 0, "SKIP": 0, "THIN": 0}
    for k in sorted(cells.keys(), key=lambda x: (isinstance(x, str), x)):
        rs = cells[k]
        b, i, n = mae_pair(rs, bias, overall)
        if n < MIN_N_CELL or b is None or b == 0:
            out_lines.append(f"  {str(k):<10} {n:>7}  {'-':>8}  {'-':>8}  {'-':>7}   {'-':>15}   THIN")
            counts["THIN"] += 1
            continue
        dpct = 100.0 * (b - i) / b
        ba, ia, na = mae_pair(cells_a.get(k, []), bias, overall)
        bb, ib, nb = mae_pair(cells_b.get(k, []), bias, overall)
        da = 100.0 * (ba - ia) / ba if ba and ba > 0 else None
        db = 100.0 * (bb - ib) / bb if bb and bb > 0 else None
        halves_str = f"{da:+.0f}%,{db:+.0f}%" if da is not None and db is not None else "-,-"
        v = cell_verdict(dpct, da, db, n)
        counts[v] += 1
        out_lines.append(f"  {str(k):<10} {n:>7}  {b:>8.2f}  {i:>8.2f}  {dpct:>+6.1f}%   {halves_str:>15}   {v}")
    out_lines.append(f"  → ships={counts['SHIP']}  margins={counts['MARGIN']}  skips={counts['SKIP']}  thin={counts['THIN']}")
    return counts


def axis_key(r, label):
    if label == "hour":      return r["hod"]
    if label == "lead_band": return lead_band(r["lead_h"])
    if label == "cc_bin":
        cc = r["cc"]
        if cc is None: return None
        if cc < 25:            return "0-25"
        if cc < 50:            return "25-50"
        if cc < 75:            return "50-75"
        return "75-100"
    return None


def main():
    rows = load_rows()
    n_total = len(rows)
    if n_total == 0:
        print("No sea_breeze sr rows found.")
        return

    split = int(n_total * 0.6)
    train, test = rows[:split], rows[split:]
    n_gated_test = sum(1 for r in test if cc_gated(r["cc"]))

    bias, overall, n_gated_train = fit_hourly_bias(train)

    out = []
    out.append("=" * 96)
    out.append("sr sea_breeze Lsr refit — Stage 2 preview (cc-gated)")
    out.append("=" * 96)
    out.append(f"Gate: apply intervention iff cc < {CC_LO} or cc >= {CC_HI}.  Else keep current Prod L4.")
    out.append(f"Split: earliest 60% of sea_breeze rows = train, latest 40% = test.")
    out.append(f"Ship-gate: pooled test Δ ≥ {FLOOR_PCT:.1f}% AND both test halves ≥ 0.")
    out.append("")
    out.append(f"n total sea_breeze: {n_total:,}   train: {len(train):,} ({train[0]['obs_time'][:10]} → {train[-1]['obs_time'][:10]})   test: {len(test):,} ({test[0]['obs_time'][:10]} → {test[-1]['obs_time'][:10]})")
    out.append(f"n cc-gated in train: {n_gated_train:,} ({100*n_gated_train/max(len(train),1):.0f}% of train)")
    out.append(f"n cc-gated in test:  {n_gated_test:,} ({100*n_gated_test/max(len(test),1):.0f}% of test)")
    out.append("")
    out.append(f"Fitted per-hour bias (fc_sw − obs) on cc-gated train (need ≥{MIN_N_HOUR_FIT}):")
    out.append(f"  {'hour':>4}  {'n_train':>7}  {'bias W/m²':>10}  {'fitted?':>9}")
    all_hours = sorted(set([r["hod"] for r in train if cc_gated(r["cc"])]))
    per_hour_train_n = defaultdict(int)
    per_hour_train_sum = defaultdict(float)
    for r in train:
        if cc_gated(r["cc"]):
            per_hour_train_n[r["hod"]] += 1
            per_hour_train_sum[r["hod"]] += r["fc_sw"] - r["obs"]
    for h in all_hours:
        nh = per_hour_train_n[h]
        bh = per_hour_train_sum[h] / nh
        fitted = "hourly" if nh >= MIN_N_HOUR_FIT else "fallback"
        out.append(f"  {h:>4}  {nh:>7}  {bh:>+10.2f}  {fitted:>9}")
    out.append(f"  overall bias fallback: {overall:+.2f} W/m²  (used when hour lacks fit)")

    # Pooled test comparison
    b, i, _ = mae_pair(test, bias, overall)
    dpct = 100.0 * (b - i) / b if b > 0 else 0.0
    out.append("")
    out.append("POOLED TEST (all sea_breeze rows; baseline = Prod L4, intervention gated)")
    out.append(f"  baseline MAE:       {b:.2f} W/m²")
    out.append(f"  intervention MAE:   {i:.2f} W/m²")
    out.append(f"  Δ:                 {dpct:+.2f}%")

    # Halves stability
    ha, hb = halves_split(test)
    b_a, i_a, _ = mae_pair(ha, bias, overall)
    b_b, i_b, _ = mae_pair(hb, bias, overall)
    da = 100.0 * (b_a - i_a) / b_a if b_a and b_a > 0 else 0.0
    db = 100.0 * (b_b - i_b) / b_b if b_b and b_b > 0 else 0.0
    out.append("")
    out.append("HALVES CHECK (test split by date)")
    out.append(f"  half A ({ha[0]['obs_time'][:10]} → {ha[-1]['obs_time'][:10]}):  baseline {b_a:.2f}  intervention {i_a:.2f}  Δ {da:+.2f}%")
    out.append(f"  half B ({hb[0]['obs_time'][:10]} → {hb[-1]['obs_time'][:10]}):  baseline {b_b:.2f}  intervention {i_b:.2f}  Δ {db:+.2f}%")

    # Per-cell axes
    axes = {}
    for label in ("hour", "lead_band", "cc_bin"):
        cells = stratify(test, lambda r, l=label: axis_key(r, l))
        axes[label] = render_axis(label, cells, (ha, hb), bias, overall, out)

    # Verdict
    pooled_ok = dpct >= FLOOR_PCT
    halves_ok = da >= 0 and db >= 0
    # cell health: cc_bin should have no SKIPs in the gated bins by construction;
    # allow SKIPs only in the middle bins (which fall back to baseline).
    # lead_band SHIPs > SKIPs is the sanity check.
    lb = axes["lead_band"]
    lead_ok = lb["SHIP"] + lb["MARGIN"] > lb["SKIP"]

    out.append("")
    out.append("=" * 96)
    if pooled_ok and halves_ok and lead_ok:
        verdict = "PROMOTE"
        out.append(f"VERDICT: PROMOTE")
        out.append(f"  pooled Δ {dpct:+.2f}% ≥ {FLOOR_PCT}%, halves ({da:+.1f}%, {db:+.1f}%) both ≥ 0, lead-band clean → Stage 3")
    elif pooled_ok and halves_ok:
        verdict = "MARGINAL"
        out.append(f"VERDICT: MARGINAL")
        out.append(f"  pooled + halves clean but lead-band shows regressions — investigate before Stage 3")
    else:
        verdict = "HOLD"
        out.append(f"VERDICT: HOLD")
        out.append(f"  pooled Δ {dpct:+.2f}% / halves ({da:+.1f}%, {db:+.1f}%) fails ship gate")
    out.append("=" * 96)

    text = "\n".join(out)
    print(text)

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as f:
        f.write(text + "\n")

    result = {
        "regime": REGIME,
        "cc_gate": {"lo": CC_LO, "hi": CC_HI},
        "verdict": verdict,
        "n_total": n_total,
        "n_train": len(train), "n_test": len(test),
        "n_gated_train": n_gated_train, "n_gated_test": n_gated_test,
        "train_dates": [train[0]["obs_time"][:10], train[-1]["obs_time"][:10]],
        "test_dates": [test[0]["obs_time"][:10], test[-1]["obs_time"][:10]],
        "pooled_baseline_mae": b, "pooled_intervention_mae": i, "pooled_delta_pct": dpct,
        "halves_delta_pct": {"a": da, "b": db},
        "hourly_bias": {str(h): bias[h] for h in bias},
        "overall_bias": overall,
        "axes_counts": axes,
    }
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)

    # Curated preview (not wired). Ready for Stage 3 apply-side plumbing.
    curated = {
        "source": "sr_sea_breeze_lsr_refit_stage2.py",
        "generated": test[-1]["obs_time"],
        "regime": REGIME,
        "field": FIELD,
        "cc_gate": {"lo": CC_LO, "hi": CC_HI, "rule": "apply iff cc < lo OR cc >= hi"},
        "hourly_bias_wm2": {str(h): round(bias[h], 2) for h in bias},
        "overall_bias_wm2": round(overall, 2),
        "verdict": verdict,
        "enabled": False,
    }
    os.makedirs(os.path.dirname(CURATED_JSON), exist_ok=True)
    with open(CURATED_JSON, "w") as f:
        json.dump(curated, f, indent=2, sort_keys=True)

    print()
    print(f"wrote {OUT_TXT}")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {CURATED_JSON}  (preview, ENABLED=False)")


if __name__ == "__main__":
    main()
