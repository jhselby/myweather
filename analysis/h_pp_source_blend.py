"""
Stage 0 sniff — pp source-blend (HRRR + GFS).

Booked 2026-07-27 PM after three pp recalibration halves-tests all HOLD:
h_pp_bin_calibration.py, h_pp_platt_calibration.py, h_pp_kalman_recalibrate.py.
Root cause identified there: raw HRRR pp Brier ≈ 0.086 with Reliability
component only ~5% of the total — Uncertainty + Resolution dominate,
so even perfect recalibration can't move the needle. See
[[project_pp_recalibration_session]].

This script attacks the **Resolution** term instead of Reliability by
blending two independent-model pp forecasts (HRRR + GFS). GFS L1 is
already logged every tick in `gfs_l1_log.json` on GCS with 14-day
retention, joinable to the pair log by (run_hour, valid_time). Pirate
Weather pp is fetched live but NOT historically logged — Pirate is not
available for a historical halves test today. If this Stage 0 shows
signal from a 2-source blend, a follow-up would add per-tick pp logging
for Pirate and re-run at 3 sources.

Two blend forms tested:

  weighted  =    α · HRRR + (1−α) · GFS
              fitted α ∈ [0, 1] minimizing Brier on half A, scored on B.

  logistic  =  σ(a + b_H · logit(HRRR) + b_G · logit(GFS))
              2-hidden Newton fit on half A, scored on half B.
              Same recipe as h_pp_platt_calibration.py but with two
              input features instead of one.

Halves-test convention matches the earlier pp scripts. Both halves must
improve Brier ≥ SHIP_BRIER_PCT (5%) with fitted params stable across
halves to promote past Stage 0.

Run:
    python3 analysis/h_pp_source_blend.py

Output:
    analysis/output/h_pp_source_blend.txt
    analysis/output/h_pp_source_blend.json
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
GFS_LOG_URL = "https://data.wymancove.com/gfs_l1_log.json"

OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_pp_source_blend.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_pp_source_blend.json")

FIELD = "pp"
CLIP = 1e-3
SHIP_BRIER_PCT = 5.0
STABLE_DALPHA = 0.10
STABLE_DA = 0.5
STABLE_DBH = 0.3
STABLE_DBG = 0.3
GOLDEN_ITERS = 60
NEWTON_ITERS = 50
NEWTON_TOL = 1e-8
# Ridge damping on the logistic Hessian. HRRR pp and GFS pp are near-collinear
# at the forecast-issue horizon (first Stage 0 07-27 saw Newton diverge to
# |b_H| ≈ 8e10 without this — same numerical trap that bit h_pp_kalman_recalibrate
# per HANDOFF). λ scales with n so it stays small vs the data-driven Hessian
# when features are well-conditioned; kicks in only when the Hessian is
# rank-deficient. Interpret non-zero coefficients as directionally-meaningful
# but not physically-tight when |b_H| or |b_G| approaches √(1/λ_scaled) ≈ 32.
LOGISTIC_RIDGE = 1e-3


def _sigmoid(z):
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def _logit(p):
    p = min(max(p, CLIP), 1.0 - CLIP)
    return math.log(p / (1.0 - p))


def _run_hour_of(ts):
    """Bucket a HRRR run timestamp to its hour so GFS snapshots (logged
    every 10 min) match a single hour key like the pair log's dedup."""
    return ts[:13] if ts and len(ts) >= 13 else None


def load_gfs_index():
    """Return {(run_hour, valid_time): gfs_pp_frac} across the GFS log.
    Skips snapshots with no `pp` field on the hour."""
    with open(cached_path(GFS_LOG_URL), "rb") as fh:
        log = json.load(fh)
    idx = {}
    for snap in log.get("snapshots", []):
        rh = _run_hour_of(snap.get("run"))
        if not rh:
            continue
        for hr in snap.get("hours", []):
            v = hr.get("v")
            pp = hr.get("pp")
            if v is None or pp is None:
                continue
            key = (rh, v)
            if key in idx:
                continue  # first-write-wins mirrors HRRR run-hour dedup
            idx[key] = float(pp) / 100.0
    return idx


def load_rows(gfs_idx):
    """Load pp pair-log rows, join GFS on (run_hour, valid_time).
    Only rows with a GFS join are kept."""
    rows = []
    joined = 0
    skipped_no_gfs = 0
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            ob = r.get("observed")
            fc_l1 = r.get("forecast_l1")
            lead = r.get("lead_h")
            ts = r.get("obs_time") or r.get("valid_time")
            run = r.get("run_time")
            valid = r.get("valid_time")
            if ob is None or fc_l1 is None or lead is None or run is None or valid is None:
                continue
            rh = _run_hour_of(run)
            gfs_pp = gfs_idx.get((rh, valid))
            if gfs_pp is None:
                skipped_no_gfs += 1
                continue
            rows.append({
                "ts": ts,
                "obs": float(ob) / 100.0,
                "hrrr": float(fc_l1) / 100.0,
                "gfs": gfs_pp,
                "lead": int(lead),
            })
            joined += 1
    rows.sort(key=lambda r: r["ts"])
    return rows, joined, skipped_no_gfs


# ─────────────────────── weighted blend ───────────────────────

def _brier(rows, mixer):
    n = len(rows)
    if n == 0:
        return None
    s = 0.0
    for r in rows:
        p = mixer(r)
        s += (p - r["obs"]) ** 2
    return s / n


def fit_alpha(rows):
    """1-D minimize Brier over α ∈ [0, 1] by golden-section search.
    Convex-ish + bounded, so no need for gradients."""
    lo, hi = 0.0, 1.0
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    a = hi - phi * (hi - lo)
    b = lo + phi * (hi - lo)
    fa = _brier(rows, lambda r: a * r["hrrr"] + (1 - a) * r["gfs"])
    fb = _brier(rows, lambda r: b * r["hrrr"] + (1 - b) * r["gfs"])
    for _ in range(GOLDEN_ITERS):
        if fa < fb:
            hi = b
            b = a
            fb = fa
            a = hi - phi * (hi - lo)
            fa = _brier(rows, lambda r: a * r["hrrr"] + (1 - a) * r["gfs"])
        else:
            lo = a
            a = b
            fa = fb
            b = lo + phi * (hi - lo)
            fb = _brier(rows, lambda r: b * r["hrrr"] + (1 - b) * r["gfs"])
    return (lo + hi) / 2.0


def score_weighted(rows, alpha):
    raw = _brier(rows, lambda r: r["hrrr"])
    cal = _brier(rows, lambda r: alpha * r["hrrr"] + (1 - alpha) * r["gfs"])
    return raw, cal


# ─────────────────────── logistic blend ───────────────────────

def fit_logistic(rows):
    """Newton-Raphson on binary log-loss with features [1, logit(H), logit(G)].
    Returns (a, bH, bG, converged, iters, final_loss)."""
    xh = [_logit(r["hrrr"]) for r in rows]
    xg = [_logit(r["gfs"])  for r in rows]
    ys = [r["obs"] for r in rows]
    n = len(rows)
    a, bH, bG = 0.0, 0.5, 0.5
    prev = None
    for it in range(NEWTON_ITERS):
        g = [0.0, 0.0, 0.0]
        H = [[0.0]*3 for _ in range(3)]
        loss = 0.0
        for i in range(n):
            z = a + bH * xh[i] + bG * xg[i]
            p = _sigmoid(z)
            pc = min(max(p, CLIP), 1.0 - CLIP)
            loss -= ys[i] * math.log(pc) + (1 - ys[i]) * math.log(1 - pc)
            r = p - ys[i]
            g[0] += r
            g[1] += r * xh[i]
            g[2] += r * xg[i]
            w = p * (1 - p)
            H[0][0] += w
            H[0][1] += w * xh[i]
            H[0][2] += w * xg[i]
            H[1][1] += w * xh[i] * xh[i]
            H[1][2] += w * xh[i] * xg[i]
            H[2][2] += w * xg[i] * xg[i]
        loss /= n
        H[1][0] = H[0][1]
        H[2][0] = H[0][2]
        H[2][1] = H[1][2]
        # Ridge: add λ·n·I to the Hessian. See LOGISTIC_RIDGE note.
        ridge = LOGISTIC_RIDGE * n
        H[0][0] += ridge
        H[1][1] += ridge
        H[2][2] += ridge
        step = _solve3x3(H, g)
        if step is None:
            break
        a  -= step[0]
        bH -= step[1]
        bG -= step[2]
        if prev is not None and abs(prev - loss) < NEWTON_TOL:
            return a, bH, bG, True, it + 1, loss
        prev = loss
    return a, bH, bG, False, NEWTON_ITERS, loss


def _solve3x3(M, v):
    """Solve M·x = v by Gaussian elimination with partial pivoting.
    None on singular."""
    A = [row[:] + [v[i]] for i, row in enumerate(M)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(A[r][col]))
        if abs(A[piv][col]) < 1e-12:
            return None
        A[col], A[piv] = A[piv], A[col]
        for r in range(col + 1, 3):
            f = A[r][col] / A[col][col]
            for c in range(col, 4):
                A[r][c] -= f * A[col][c]
    x = [0.0] * 3
    for r in range(2, -1, -1):
        s = A[r][3] - sum(A[r][c] * x[c] for c in range(r + 1, 3))
        x[r] = s / A[r][r]
    return x


def score_logistic(rows, a, bH, bG):
    raw = _brier(rows, lambda r: r["hrrr"])
    cal = _brier(rows, lambda r: _sigmoid(a + bH * _logit(r["hrrr"]) + bG * _logit(r["gfs"])))
    return raw, cal


def _pct(raw, cal):
    if raw is None or cal is None or raw == 0:
        return None
    return (cal - raw) / raw * 100.0


def _verdict(pct_a, pct_b, stable):
    if pct_a is None or pct_b is None:
        return "HOLD", "no held-out score (insufficient rows)"
    both_improve = pct_a < 0 and pct_b < 0
    both_strong = pct_a <= -SHIP_BRIER_PCT and pct_b <= -SHIP_BRIER_PCT
    if both_strong and stable:
        return "SHIP", (f"both halves improve Brier ≥{SHIP_BRIER_PCT}% "
                        f"({pct_a:+.2f}% / {pct_b:+.2f}%) with stable params.")
    if both_improve and stable:
        return "MARGINAL", (f"both halves improve ({pct_a:+.2f}% / {pct_b:+.2f}%) "
                            f"with stable params but below {SHIP_BRIER_PCT}% ship gate.")
    if both_improve:
        return "MARGINAL", (f"both halves improve ({pct_a:+.2f}% / {pct_b:+.2f}%) "
                            f"but params drift.")
    return "HOLD", (f"halves diverge ({pct_a:+.2f}% / {pct_b:+.2f}%); "
                    f"blend does not transfer.")


def main():
    gfs_idx = load_gfs_index()
    if not gfs_idx:
        print("GFS log empty or unreadable; cannot proceed.", file=sys.stderr)
        return 1
    rows, joined, skipped = load_rows(gfs_idx)

    if len(rows) < 1000:
        print(f"Not enough joined pp rows ({len(rows)}) for halves test — need ≥1000. "
              f"GFS index size: {len(gfs_idx):,}; joined: {joined:,}; skipped_no_gfs: {skipped:,}.",
              file=sys.stderr)
        return 1

    mid = len(rows) // 2
    half_a = rows[:mid]
    half_b = rows[mid:]

    # Weighted blend
    alpha_A = fit_alpha(half_a)
    alpha_B = fit_alpha(half_b)
    raw_wB, cal_wB = score_weighted(half_b, alpha_A)
    raw_wA, cal_wA = score_weighted(half_a, alpha_B)
    pct_wB = _pct(raw_wB, cal_wB)
    pct_wA = _pct(raw_wA, cal_wA)
    w_stable = abs(alpha_A - alpha_B) <= STABLE_DALPHA
    w_verdict, w_rationale = _verdict(pct_wA, pct_wB, w_stable)

    # Logistic blend
    aA, bhA, bgA, cA, iA, lA = fit_logistic(half_a)
    aB, bhB, bgB, cB, iB, lB = fit_logistic(half_b)
    raw_lB, cal_lB = score_logistic(half_b, aA, bhA, bgA)
    raw_lA, cal_lA = score_logistic(half_a, aB, bhB, bgB)
    pct_lB = _pct(raw_lB, cal_lB)
    pct_lA = _pct(raw_lA, cal_lA)
    l_stable = (abs(aA - aB) <= STABLE_DA and abs(bhA - bhB) <= STABLE_DBH
                and abs(bgA - bgB) <= STABLE_DBG)
    l_verdict, l_rationale = _verdict(pct_lA, pct_lB, l_stable)

    # Combined verdict = best of the two
    best_pct = None
    for pcts, label in [((pct_wA, pct_wB), "weighted"),
                        ((pct_lA, pct_lB), "logistic")]:
        if pcts[0] is not None and pcts[1] is not None:
            avg = 0.5 * (pcts[0] + pcts[1])
            if best_pct is None or avg < best_pct[0]:
                best_pct = (avg, label)
    overall = w_verdict if w_verdict == "SHIP" or (l_verdict != "SHIP" and w_verdict >= l_verdict) else l_verdict

    lines = []
    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 100)
    emit("pp SOURCE BLEND — Stage 0 sniff (HRRR + GFS)")
    emit("=" * 100)
    emit(f"Rows: {len(rows):,} joined "
         f"(half A: {len(half_a):,}, half B: {len(half_b):,}); "
         f"span {rows[0]['ts']} → {rows[-1]['ts']}. "
         f"GFS index: {len(gfs_idx):,} (run_hour, valid) keys; "
         f"pair-log pp rows without GFS join: {skipped:,}.")
    emit("")
    emit("── Weighted blend  (α·HRRR + (1−α)·GFS)  ──")
    emit(f"  Fit half A: α={alpha_A:.4f}   |   Fit half B: α={alpha_B:.4f}   "
         f"|Δα|={abs(alpha_A - alpha_B):.4f}  (stable≤{STABLE_DALPHA})")
    emit(f"  Fit A → score B:  raw={raw_wB:.5f}  blended={cal_wB:.5f}  "
         f"Δ={pct_wB:+.2f}%")
    emit(f"  Fit B → score A:  raw={raw_wA:.5f}  blended={cal_wA:.5f}  "
         f"Δ={pct_wA:+.2f}%")
    emit(f"  → {w_verdict}: {w_rationale}")
    emit("")
    emit("── Logistic blend  σ(a + b_H·logit(H) + b_G·logit(G))  ──")
    emit(f"  Fit half A: a={aA:+.4f}  b_H={bhA:+.4f}  b_G={bgA:+.4f}  "
         f"converged={cA}  iters={iA}  log-loss={lA:.5f}")
    emit(f"  Fit half B: a={aB:+.4f}  b_H={bhB:+.4f}  b_G={bgB:+.4f}  "
         f"converged={cB}  iters={iB}  log-loss={lB:.5f}")
    emit(f"  Parameter drift: |Δa|={abs(aA - aB):.4f}  "
         f"|Δb_H|={abs(bhA - bhB):.4f}  |Δb_G|={abs(bgA - bgB):.4f}")
    emit(f"  Fit A → score B:  raw={raw_lB:.5f}  blended={cal_lB:.5f}  "
         f"Δ={pct_lB:+.2f}%")
    emit(f"  Fit B → score A:  raw={raw_lA:.5f}  blended={cal_lA:.5f}  "
         f"Δ={pct_lA:+.2f}%")
    emit(f"  → {l_verdict}: {l_rationale}")
    emit("")
    emit("=" * 100)
    emit(f"→ {overall}: best-of-two blend attack on Resolution term "
         f"(best avg Δ = {best_pct[0]:+.2f}% via {best_pct[1]}).")
    emit(f"VERDICT: {overall} pp_source_blend "
         f"weighted[A→B={pct_wB:+.2f}% B→A={pct_wA:+.2f}%] "
         f"logistic[A→B={pct_lB:+.2f}% B→A={pct_lA:+.2f}%]")
    emit("=" * 100)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {
            "hrrr": f"forecast_error_log.jsonl (field={FIELD}, forecast_l1)",
            "gfs": f"gfs_l1_log.json (pp; joined on run_hour + valid_time)",
        },
        "n_rows": len(rows),
        "n_skipped_no_gfs": skipped,
        "gfs_index_size": len(gfs_idx),
        "halves": {
            "A": {"n": len(half_a), "ts_start": str(half_a[0]["ts"]),
                  "ts_end": str(half_a[-1]["ts"])},
            "B": {"n": len(half_b), "ts_start": str(half_b[0]["ts"]),
                  "ts_end": str(half_b[-1]["ts"])},
        },
        "weighted": {
            "alpha_A": alpha_A, "alpha_B": alpha_B,
            "brier": {"fit_A_score_B": {"raw": raw_wB, "blended": cal_wB, "pct": pct_wB},
                      "fit_B_score_A": {"raw": raw_wA, "blended": cal_wA, "pct": pct_wA}},
            "verdict": {"state": w_verdict, "rationale": w_rationale},
        },
        "logistic": {
            "fit_A": {"a": aA, "bH": bhA, "bG": bgA, "converged": cA,
                      "iters": iA, "log_loss": lA},
            "fit_B": {"a": aB, "bH": bhB, "bG": bgB, "converged": cB,
                      "iters": iB, "log_loss": lB},
            "param_drift": {"da": abs(aA - aB), "dbH": abs(bhA - bhB),
                            "dbG": abs(bgA - bgB)},
            "brier": {"fit_A_score_B": {"raw": raw_lB, "blended": cal_lB, "pct": pct_lB},
                      "fit_B_score_A": {"raw": raw_lA, "blended": cal_lA, "pct": pct_lA}},
            "verdict": {"state": l_verdict, "rationale": l_rationale},
        },
        "gates": {
            "ship_brier_pct": SHIP_BRIER_PCT,
            "stable_dalpha": STABLE_DALPHA,
            "stable_da": STABLE_DA,
            "stable_dbH": STABLE_DBH,
            "stable_dbG": STABLE_DBG,
        },
        "verdict": {
            "state": overall,
            "candidate": "pp_source_blend",
            "best_form": best_pct[1] if best_pct else None,
            "best_avg_pct": best_pct[0] if best_pct else None,
        },
    }

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
