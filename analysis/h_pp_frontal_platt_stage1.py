"""
Stage 1 — pp Platt recalibration, frontal regime only, halves-refit.

Follow-up to `h_pp_platt_by_regime.py` Stage 0 (2026-07-27 v0.6.382r
evening) which flagged frontal as the one positive sub-signal in an
otherwise-HOLD Platt-by-regime run: both halves improved Brier by
−15.49% / −15.60% (well above 5% ship gate) but the fit had
|Δa|=0.66 > 0.5 stability gate → MARGINAL_DRIFT verdict.

Stage 1 asks: does the drift tighten under any of these three
refinements?

  (A) Per (frontal × lead_band) fit — is one band cleanly stable
      while another band's noise pulled the pooled |Δa| above gate?
  (B) Constrained fit b=0.6 (per pooled-Platt slope-stability
      finding in project_pp_recalibration_session — |Δb|=0.06 across
      halves), fit only a. Fewer params → less drift possible.
  (C) Both — per-lead-band constrained fits.

Halves are split within the frontal subset by ts (same convention as
h_pp_platt_by_regime.py).

Promotion:
  SHIP     if any refinement variant clears BOTH halves ≥5% Brier
           AND stability (|Δa| ≤ 0.5, |Δb| ≤ 0.3 if free).
  MARGINAL if any variant clears both halves ≥5% but drifts.
  HOLD     if no variant clears both halves.

Run:
    python3 analysis/h_pp_frontal_platt_stage1.py

Output:
    analysis/output/h_pp_frontal_platt_stage1.txt
    analysis/output/h_pp_frontal_platt_stage1.json
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_pp_frontal_platt_stage1.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_pp_frontal_platt_stage1.json")

FIELD = "pp"
TARGET_REGIME = "frontal"
CLIP = 1e-3
SHIP_BRIER_PCT = 5.0
STABLE_DA = 0.5
STABLE_DB = 0.3
MIN_LEAD_BAND_ROWS = 200
FIXED_SLOPE_B = 0.60  # per pooled slope-stability finding
MAX_ITERS = 50
TOL = 1e-8
RIDGE = 1e-3

LEAD_BANDS = [
    ("0-5",   1,  5),
    ("6-11",  6, 11),
    ("12-23", 12, 23),
    ("24-47", 24, 47),
]


def _sigmoid(z):
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def _logit(p):
    p = min(max(p, CLIP), 1.0 - CLIP)
    return math.log(p / (1.0 - p))


def lead_band(lead):
    for name, lo, hi in LEAD_BANDS:
        if lo <= lead <= hi:
            return name
    return None


def load_frontal_rows():
    rows = []
    n_positive = 0
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            ob = r.get("observed")
            fc = r.get("forecast_l1")
            lead = r.get("lead_h")
            ts = r.get("obs_time") or r.get("valid_time") or r.get("run_time")
            if ob is None or fc is None or lead is None or ts is None:
                continue
            state_fc = r.get("state_fc") or {}
            if state_fc.get("regime_synoptic") != TARGET_REGIME:
                continue
            band = lead_band(int(lead))
            if band is None:
                continue
            obs = float(ob) / 100.0
            if obs > 0.5:
                n_positive += 1
            rows.append({
                "ts": ts,
                "obs": obs,
                "raw": float(fc) / 100.0,
                "lead": int(lead),
                "band": band,
            })
    rows.sort(key=lambda r: r["ts"])
    return rows, n_positive


def fit_platt_free(rows):
    """Two-param a + b·logit(raw) Newton with ridge."""
    xs = [_logit(r["raw"]) for r in rows]
    ys = [r["obs"] for r in rows]
    n = len(rows)
    a, b = 0.0, 1.0
    prev = None
    ridge = RIDGE * n
    for it in range(MAX_ITERS):
        g_a = g_b = 0.0
        h_aa = h_ab = h_bb = 0.0
        loss = 0.0
        for i in range(n):
            z = a + b * xs[i]
            p = _sigmoid(z)
            pc = min(max(p, CLIP), 1.0 - CLIP)
            loss -= ys[i] * math.log(pc) + (1 - ys[i]) * math.log(1 - pc)
            r = p - ys[i]
            g_a += r
            g_b += r * xs[i]
            w = p * (1 - p)
            h_aa += w
            h_ab += w * xs[i]
            h_bb += w * xs[i] * xs[i]
        loss /= n
        h_aa += ridge
        h_bb += ridge
        det = h_aa * h_bb - h_ab * h_ab
        if det <= 0:
            break
        step_a = (h_bb * g_a - h_ab * g_b) / det
        step_b = (-h_ab * g_a + h_aa * g_b) / det
        a -= step_a
        b -= step_b
        if prev is not None and abs(prev - loss) < TOL:
            return a, b, True, it + 1, loss
        prev = loss
    return a, b, False, MAX_ITERS, loss


def fit_platt_intercept_only(rows, b_fixed):
    """One-param a fit with b held at b_fixed. Newton in 1-D."""
    xs = [_logit(r["raw"]) for r in rows]
    ys = [r["obs"] for r in rows]
    n = len(rows)
    a = 0.0
    prev = None
    ridge = RIDGE * n
    for it in range(MAX_ITERS):
        g = 0.0
        h = ridge
        loss = 0.0
        for i in range(n):
            z = a + b_fixed * xs[i]
            p = _sigmoid(z)
            pc = min(max(p, CLIP), 1.0 - CLIP)
            loss -= ys[i] * math.log(pc) + (1 - ys[i]) * math.log(1 - pc)
            g += p - ys[i]
            h += p * (1 - p)
        loss /= n
        if h <= 0:
            break
        step = g / h
        a -= step
        if prev is not None and abs(prev - loss) < TOL:
            return a, True, it + 1, loss
        prev = loss
    return a, False, MAX_ITERS, loss


def score(rows, a, b):
    if not rows:
        return None, None, 0
    sum_raw = sum_cal = 0.0
    for r in rows:
        cal_p = _sigmoid(a + b * _logit(r["raw"]))
        sum_raw += (r["raw"] - r["obs"]) ** 2
        sum_cal += (cal_p - r["obs"]) ** 2
    n = len(rows)
    return sum_raw / n, sum_cal / n, n


def _pct(raw, cal):
    if raw is None or cal is None or raw == 0:
        return None
    return (cal - raw) / raw * 100.0


def verdict_of(pct_a, pct_b, drift_ok):
    if pct_a is None or pct_b is None:
        return "HOLD"
    both_ship = pct_a <= -SHIP_BRIER_PCT and pct_b <= -SHIP_BRIER_PCT
    both_improve = pct_a < 0 and pct_b < 0
    if both_ship and drift_ok:
        return "SHIP"
    if both_improve and drift_ok:
        return "MARGINAL_STABLE"
    if both_improve:
        return "MARGINAL_DRIFT"
    return "HOLD"


def halves_test_free(rows, label):
    """Free 2-param Platt halves test. Returns dict with verdict."""
    if len(rows) < 40:
        return {"label": label, "n": len(rows), "verdict": "THIN"}
    mid = len(rows) // 2
    hA, hB = rows[:mid], rows[mid:]
    a_A, b_A, cA, iA, lA = fit_platt_free(hA)
    a_B, b_B, cB, iB, lB = fit_platt_free(hB)
    raw_b, cal_b, n_b = score(hB, a_A, b_A)
    raw_a, cal_a, n_a = score(hA, a_B, b_B)
    pct_A = _pct(raw_a, cal_a)
    pct_B = _pct(raw_b, cal_b)
    da = abs(a_A - a_B)
    db = abs(b_A - b_B)
    drift_ok = da <= STABLE_DA and db <= STABLE_DB and b_A > 0 and b_B > 0
    return {
        "label": label,
        "n": len(rows),
        "fit_A": {"a": a_A, "b": b_A, "converged": cA, "iters": iA, "log_loss": lA},
        "fit_B": {"a": a_B, "b": b_B, "converged": cB, "iters": iB, "log_loss": lB},
        "brier": {"fit_A_score_B": {"pct": pct_B, "n": n_b},
                  "fit_B_score_A": {"pct": pct_A, "n": n_a}},
        "param_drift": {"da": da, "db": db},
        "drift_ok": drift_ok,
        "verdict": verdict_of(pct_A, pct_B, drift_ok),
    }


def halves_test_fixed_b(rows, label, b_fixed):
    """Intercept-only Platt halves test with b held at b_fixed."""
    if len(rows) < 40:
        return {"label": label, "n": len(rows), "verdict": "THIN"}
    mid = len(rows) // 2
    hA, hB = rows[:mid], rows[mid:]
    a_A, cA, iA, lA = fit_platt_intercept_only(hA, b_fixed)
    a_B, cB, iB, lB = fit_platt_intercept_only(hB, b_fixed)
    raw_b, cal_b, n_b = score(hB, a_A, b_fixed)
    raw_a, cal_a, n_a = score(hA, a_B, b_fixed)
    pct_A = _pct(raw_a, cal_a)
    pct_B = _pct(raw_b, cal_b)
    da = abs(a_A - a_B)
    drift_ok = da <= STABLE_DA
    return {
        "label": label,
        "n": len(rows),
        "b_fixed": b_fixed,
        "fit_A": {"a": a_A, "converged": cA, "iters": iA, "log_loss": lA},
        "fit_B": {"a": a_B, "converged": cB, "iters": iB, "log_loss": lB},
        "brier": {"fit_A_score_B": {"pct": pct_B, "n": n_b},
                  "fit_B_score_A": {"pct": pct_A, "n": n_a}},
        "param_drift": {"da": da, "db": 0.0},
        "drift_ok": drift_ok,
        "verdict": verdict_of(pct_A, pct_B, drift_ok),
    }


def main():
    rows, n_positive = load_frontal_rows()
    if len(rows) < 400:
        print(f"Not enough frontal pp rows ({len(rows)}); need ≥400 for halves.",
              file=sys.stderr)
        return 1

    by_band = {}
    for r in rows:
        by_band.setdefault(r["band"], []).append(r)

    lines = []
    def L(s=""):
        lines.append(s)

    L("=" * 100)
    L("pp PLATT — FRONTAL-ONLY Stage 1 (halves refit + per-band split + constrained-b variant)")
    L("=" * 100)
    L(f"Rows: {len(rows):,} frontal-regime pp pairs "
      f"(pooled positive-rate {100*n_positive/max(1,len(rows)):.1f}%). "
      f"Span {rows[0]['ts']} → {rows[-1]['ts']}.")
    L(f"Fixed-slope variant uses b={FIXED_SLOPE_B} (per pooled slope-stability finding, "
      f"|Δb|=0.06 across halves in the pooled Platt Stage 0).")
    L("")

    # Variant 1: pooled-frontal free fit (should reproduce Stage 0 finding)
    v1 = halves_test_free(rows, "pooled_frontal_free")

    # Variant 2: pooled-frontal fixed-b fit
    v2 = halves_test_fixed_b(rows, "pooled_frontal_fixed_b", FIXED_SLOPE_B)

    # Variant 3: per-band free
    v3 = {"label": "per_band_free", "bands": {}}
    for band in ("0-5", "6-11", "12-23", "24-47"):
        band_rows = by_band.get(band, [])
        if len(band_rows) < MIN_LEAD_BAND_ROWS:
            v3["bands"][band] = {"n": len(band_rows), "verdict": "THIN"}
        else:
            v3["bands"][band] = halves_test_free(band_rows, f"free_{band}")

    # Variant 4: per-band fixed-b
    v4 = {"label": "per_band_fixed_b", "bands": {}}
    for band in ("0-5", "6-11", "12-23", "24-47"):
        band_rows = by_band.get(band, [])
        if len(band_rows) < MIN_LEAD_BAND_ROWS:
            v4["bands"][band] = {"n": len(band_rows), "verdict": "THIN"}
        else:
            v4["bands"][band] = halves_test_fixed_b(band_rows, f"fixed_b_{band}", FIXED_SLOPE_B)

    def _row_free(name, r):
        if r.get("verdict") == "THIN":
            return f"  {name:<22s} n={r['n']:>4d}  THIN"
        pB = r["brier"]["fit_A_score_B"]["pct"]
        pA = r["brier"]["fit_B_score_A"]["pct"]
        return (f"  {name:<22s} n={r['n']:>4d}  a=({r['fit_A']['a']:+.2f}/{r['fit_B']['a']:+.2f}) "
                f"b=({r['fit_A']['b']:+.2f}/{r['fit_B']['b']:+.2f}) "
                f"|Δa|={r['param_drift']['da']:.2f} |Δb|={r['param_drift']['db']:.2f} "
                f"pct={pA:+.2f}/{pB:+.2f}  {r['verdict']}")

    def _row_fixed(name, r):
        if r.get("verdict") == "THIN":
            return f"  {name:<22s} n={r['n']:>4d}  THIN"
        pB = r["brier"]["fit_A_score_B"]["pct"]
        pA = r["brier"]["fit_B_score_A"]["pct"]
        return (f"  {name:<22s} n={r['n']:>4d}  a=({r['fit_A']['a']:+.2f}/{r['fit_B']['a']:+.2f}) "
                f"b={r['b_fixed']:.2f}(fixed) "
                f"|Δa|={r['param_drift']['da']:.2f} "
                f"pct={pA:+.2f}/{pB:+.2f}  {r['verdict']}")

    L("── Variant 1: pooled-frontal free (Stage 0 reproduction check) ──")
    L(_row_free("pooled_free", v1))
    L("")
    L(f"── Variant 2: pooled-frontal fixed b={FIXED_SLOPE_B} (attempt to close |Δa| drift) ──")
    L(_row_fixed("pooled_fixed_b", v2))
    L("")
    L("── Variant 3: per-band free fit ──")
    for band in ("0-5", "6-11", "12-23", "24-47"):
        L(_row_free(f"band_{band}_free", v3["bands"][band]))
    L("")
    L(f"── Variant 4: per-band fixed b={FIXED_SLOPE_B} ──")
    for band in ("0-5", "6-11", "12-23", "24-47"):
        L(_row_fixed(f"band_{band}_fix", v4["bands"][band]))
    L("")

    # Overall verdict = best of the four variants
    candidates = [v1, v2]
    for band, r in v3["bands"].items():
        if r.get("verdict") != "THIN":
            candidates.append(r)
    for band, r in v4["bands"].items():
        if r.get("verdict") != "THIN":
            candidates.append(r)

    ship = [c for c in candidates if c["verdict"] == "SHIP"]
    marg_stable = [c for c in candidates if c["verdict"] == "MARGINAL_STABLE"]
    marg_drift = [c for c in candidates if c["verdict"] == "MARGINAL_DRIFT"]

    if ship:
        overall = "SHIP"
        best = ship[0]
        rationale = f"{len(ship)} variant(s) clear SHIP; best: {best['label']}."
    elif marg_stable:
        overall = "MARGINAL_STABLE"
        best = marg_stable[0]
        rationale = (f"no SHIP but {len(marg_stable)} variant(s) improve both halves "
                     f"and clear stability; best: {best['label']}. "
                     f"Signal is present but below 5% ship gate.")
    elif marg_drift:
        overall = "MARGINAL_DRIFT"
        best = marg_drift[0]
        rationale = (f"no SHIP or STABLE; {len(marg_drift)} variant(s) improve both "
                     f"halves but drift. Recalibration works in-window but doesn't transfer.")
    else:
        overall = "HOLD"
        rationale = "no variant clears both halves; frontal recalibration is not shipping-ready."

    L("=" * 100)
    L(f"→ {overall}: {rationale}")
    L(f"VERDICT: {overall} pp_frontal_platt_stage1 "
      f"ship={len(ship)} marg_stable={len(marg_stable)} marg_drift={len(marg_drift)}")
    L("=" * 100)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"forecast_error_log.jsonl (field={FIELD}, state_fc.regime_synoptic={TARGET_REGIME})",
        "n_rows": len(rows),
        "n_positive": n_positive,
        "variants": {
            "pooled_free": v1,
            "pooled_fixed_b": v2,
            "per_band_free": v3,
            "per_band_fixed_b": v4,
        },
        "gates": {
            "ship_brier_pct": SHIP_BRIER_PCT,
            "stable_da": STABLE_DA,
            "stable_db": STABLE_DB,
            "min_lead_band_rows": MIN_LEAD_BAND_ROWS,
            "b_fixed": FIXED_SLOPE_B,
            "ridge": RIDGE,
        },
        "verdict": {
            "state": overall,
            "candidate": "pp_frontal_platt_stage1",
            "rationale": rationale,
        },
    }

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    print("\n".join(lines))

    return 0


if __name__ == "__main__":
    sys.exit(main())
