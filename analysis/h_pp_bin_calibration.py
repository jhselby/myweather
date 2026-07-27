"""
Stage 0 corrective test — pp bin-lift calibration.

Companion to pp_brier_reliability.py. That script *describes* the raw HRRR
pp under-forecast pattern (fc 30-40% → obs 62%); this script *tests* whether
a bin-weighted lift table applied to raw fc actually reduces Brier on
held-out data.

Method:
  1. Load pair-log pp rows, sort by observed_at.
  2. Split into halves A (older 50%) and B (newer 50%).
  3. On half A: compute per-decile bin-lift table (lift = obs_freq − pred_freq
     per bin, in percentage points).
  4. On half B: apply half-A's lifts to raw fc, clamp to [0, 100], score
     Brier vs raw baseline.
  5. Also swap (fit on B, score on A) — halves must AGREE in direction to
     promote past Stage 0.

Promotion verdict:
  SHIP if both halves improve Brier ≥5% AND bin-lift signs agree in ≥7 of
    10 bins (halves-consistency gate).
  MARGINAL if both halves improve but <5% or agree in <7 bins.
  HOLD otherwise.

Run:
    python3 analysis/h_pp_bin_calibration.py

Output:
    analysis/output/h_pp_bin_calibration.txt
    analysis/output/h_pp_bin_calibration.json  (uploaded to GCS)
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_pp_bin_calibration.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_pp_bin_calibration.json")

FIELD = "pp"
BIN_EDGES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100.0001]
BIN_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50",
              "50-60", "60-70", "70-80", "80-90", "90-100"]
MIN_N_PER_BIN = 30
SHIP_BRIER_PCT = 5.0        # both halves must improve ≥ this % to SHIP
SHIP_AGREE_BINS = 7         # of 10 bins must agree in sign to SHIP


def bin_of(p):
    for i in range(len(BIN_EDGES) - 1):
        if BIN_EDGES[i] <= p < BIN_EDGES[i + 1]:
            return i
    return None


def load_rows():
    rows = []
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
            ts = r.get("obs_time") or r.get("valid_time") or r.get("run_time")
            if ob is None or fc_l1 is None or lead is None or ts is None:
                continue
            rows.append({
                "ts": ts,
                "obs": float(ob) / 100.0,
                "raw": float(fc_l1) / 100.0,
                "lead": int(lead),
            })
    rows.sort(key=lambda r: r["ts"])
    return rows


def fit_lifts(rows):
    """Return per-bin lift in percentage-point space (obs_freq − pred_freq)."""
    agg = defaultdict(lambda: {"sum_p": 0.0, "sum_o": 0.0, "n": 0})
    for r in rows:
        b = bin_of(r["raw"] * 100.0)
        if b is None:
            continue
        agg[b]["sum_p"] += r["raw"]
        agg[b]["sum_o"] += r["obs"]
        agg[b]["n"] += 1
    lifts = {}
    for b in range(len(BIN_LABELS)):
        e = agg.get(b)
        if not e or e["n"] < MIN_N_PER_BIN:
            lifts[b] = {"lift_pp": 0.0, "n": e["n"] if e else 0, "eligible": False}
            continue
        p_mean = e["sum_p"] / e["n"]
        o_mean = e["sum_o"] / e["n"]
        lifts[b] = {
            "lift_pp": round((o_mean - p_mean) * 100, 3),
            "n": e["n"],
            "eligible": True,
        }
    return lifts


def apply_and_score(rows, lifts):
    """Apply lifts to raw fc on each row; return (raw_brier, lifted_brier, n)."""
    if not rows:
        return None, None, 0
    sum_raw = 0.0
    sum_lifted = 0.0
    for r in rows:
        raw_p = r["raw"]
        b = bin_of(raw_p * 100.0)
        lift = lifts.get(b, {}).get("lift_pp", 0.0) / 100.0 if b is not None else 0.0
        lifted_p = max(0.0, min(1.0, raw_p + lift))
        sum_raw += (raw_p - r["obs"]) ** 2
        sum_lifted += (lifted_p - r["obs"]) ** 2
    n = len(rows)
    return sum_raw / n, sum_lifted / n, n


def _brier_pct(raw, lifted):
    if not raw or raw == 0:
        return 0.0
    return (lifted - raw) / raw * 100.0


def main():
    rows = load_rows()
    if len(rows) < 2 * MIN_N_PER_BIN * 10:
        print(f"Not enough pp rows ({len(rows)}) for halves test — need "
              f"≥{2 * MIN_N_PER_BIN * 10:,}.", file=sys.stderr)
        return 1

    mid = len(rows) // 2
    half_a = rows[:mid]
    half_b = rows[mid:]

    lifts_a = fit_lifts(half_a)
    lifts_b = fit_lifts(half_b)

    raw_b, lifted_b, n_b = apply_and_score(half_b, lifts_a)
    raw_a, lifted_a, n_a = apply_and_score(half_a, lifts_b)

    pct_b = _brier_pct(raw_b, lifted_b)
    pct_a = _brier_pct(raw_a, lifted_a)

    agree = 0
    for b in range(len(BIN_LABELS)):
        la = lifts_a.get(b, {})
        lb = lifts_b.get(b, {})
        if not la.get("eligible") or not lb.get("eligible"):
            continue
        if (la["lift_pp"] > 0 and lb["lift_pp"] > 0) or (la["lift_pp"] < 0 and lb["lift_pp"] < 0):
            agree += 1

    lines = []
    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 100)
    emit("pp BIN-LIFT CALIBRATION — Stage 0 corrective halves test")
    emit("=" * 100)
    emit(f"Rows: {len(rows):,} (half A: {len(half_a):,}, half B: {len(half_b):,}); "
         f"span {rows[0]['ts']} → {rows[-1]['ts']}.")
    emit("")

    emit("Per-bin lift tables (obs_freq − pred_freq, in pp; positive = raise raw fc):")
    emit(f"  {'bin':>7}   {'half-A lift':>12}  {'A n':>7}   {'half-B lift':>12}  {'B n':>7}   agree?")
    for b in range(len(BIN_LABELS)):
        la = lifts_a.get(b, {})
        lb = lifts_b.get(b, {})
        la_str = f"{la['lift_pp']:+.2f}" if la.get("eligible") else "  —  "
        lb_str = f"{lb['lift_pp']:+.2f}" if lb.get("eligible") else "  —  "
        a_ok = la.get("eligible") and lb.get("eligible")
        if a_ok and ((la["lift_pp"] > 0 and lb["lift_pp"] > 0)
                     or (la["lift_pp"] < 0 and lb["lift_pp"] < 0)):
            tag = "✓"
        elif a_ok:
            tag = "✗"
        else:
            tag = " "
        emit(f"  {BIN_LABELS[b]:>7}   {la_str:>12}  {la.get('n', 0):>7,}   "
             f"{lb_str:>12}  {lb.get('n', 0):>7,}   {tag}")
    emit(f"  Bins agreeing in sign: {agree} of {sum(1 for b in range(10) if lifts_a.get(b, {}).get('eligible') and lifts_b.get(b, {}).get('eligible'))}")
    emit("")

    emit("Held-out Brier deltas (fit on one half → score on the other):")
    emit(f"  Fit A → score B:  raw={raw_b:.5f}  lifted={lifted_b:.5f}  Δ={pct_b:+.2f}%  (n={n_b:,})")
    emit(f"  Fit B → score A:  raw={raw_a:.5f}  lifted={lifted_a:.5f}  Δ={pct_a:+.2f}%  (n={n_a:,})")
    emit("")

    both_improve = pct_a < 0 and pct_b < 0
    both_strong = pct_a <= -SHIP_BRIER_PCT and pct_b <= -SHIP_BRIER_PCT
    agree_ok = agree >= SHIP_AGREE_BINS

    if both_strong and agree_ok:
        verdict_state = "SHIP"
        verdict_arrow = "→ SHIP"
        rationale = (f"both halves improve Brier ≥{SHIP_BRIER_PCT}% "
                     f"({pct_a:+.2f}% / {pct_b:+.2f}%) AND {agree}/10 bins agree in sign "
                     f"(≥{SHIP_AGREE_BINS} required).")
    elif both_improve and agree_ok:
        verdict_state = "MARGINAL"
        verdict_arrow = "→ MARGINAL"
        rationale = (f"both halves improve Brier but below {SHIP_BRIER_PCT}% "
                     f"({pct_a:+.2f}% / {pct_b:+.2f}%); {agree}/10 bin-signs agree.")
    elif both_improve:
        verdict_state = "MARGINAL"
        verdict_arrow = "→ MARGINAL"
        rationale = (f"both halves improve Brier ({pct_a:+.2f}% / {pct_b:+.2f}%) "
                     f"but only {agree}/10 bins agree in sign (need ≥{SHIP_AGREE_BINS}).")
    else:
        verdict_state = "HOLD"
        verdict_arrow = "→ HOLD"
        rationale = (f"halves diverge ({pct_a:+.2f}% / {pct_b:+.2f}%); "
                     f"lift table is not stable across time.")

    emit("=" * 100)
    emit(f"{verdict_arrow}: {rationale}")
    emit(f"VERDICT: {verdict_state} pp_bin_lift_calibration "
         f"halfA→B={pct_b:+.2f}% halfB→A={pct_a:+.2f}% agree={agree}/10")
    emit("=" * 100)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"forecast_error_log.jsonl (field={FIELD})",
        "n_rows": len(rows),
        "halves": {
            "A": {"n": len(half_a), "ts_start": str(half_a[0]["ts"]), "ts_end": str(half_a[-1]["ts"])},
            "B": {"n": len(half_b), "ts_start": str(half_b[0]["ts"]), "ts_end": str(half_b[-1]["ts"])},
        },
        "lifts_A": {BIN_LABELS[b]: lifts_a.get(b, {}) for b in range(len(BIN_LABELS))},
        "lifts_B": {BIN_LABELS[b]: lifts_b.get(b, {}) for b in range(len(BIN_LABELS))},
        "brier": {
            "fit_A_score_B": {"raw": raw_b, "lifted": lifted_b, "pct": pct_b, "n": n_b},
            "fit_B_score_A": {"raw": raw_a, "lifted": lifted_a, "pct": pct_a, "n": n_a},
        },
        "bins_agree_in_sign": agree,
        "gates": {
            "ship_brier_pct_threshold": SHIP_BRIER_PCT,
            "ship_agree_bins_threshold": SHIP_AGREE_BINS,
        },
        "verdict": {
            "state": verdict_state,
            "candidate": "pp_bin_lift_calibration",
            "rationale": rationale,
        },
    }

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    print(f"wrote {OUT_JSON}", file=sys.stderr)

    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from weather_collector.gcs_io import upload_json  # noqa: E402
        upload_json(payload, "h_pp_bin_calibration.json", "h_pp_bin_calibration.json")
        print("  ✓ Published to gs://myweather-data/h_pp_bin_calibration.json", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠ GCS upload skipped ({type(e).__name__}: {e}) — local file still written", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
