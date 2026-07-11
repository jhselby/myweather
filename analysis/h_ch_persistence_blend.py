"""Stage 0-1 — ch regime-gated persistence blend.

Follow-on to [[project-ch-persistence-gap]] + [[project-persistence-skill-baseline]].
The ch pipeline (L3+L4) loses to naive persistence in 8 of 9 regimes;
only `frontal` beats persistence. Joe's proposal (2026-07-11):

  For ch: use L4 in `frontal` regime; use persistence-of-obs elsewhere.

Rough back-of-envelope from the earlier by-regime table projected
~20% pooled ch MAE improvement. This script tests that projection
rigorously via halves-stability check + measured MAE per scenario.

Given today's regime-gate sweep experience (see [[project-regime-gate-sweep-07-11]]),
we do NOT trust a single-window verdict on regime-gated designs.
Every scenario is scored on:
  - Recent 15d (matches production_whatif window)
  - Prior 15d
  - Full 30d well-stamped window
Verdicts require agreement on recent + prior halves.

Scenarios:
  baseline           — current pipeline (L4 everywhere for ch)
  regime_gate        — L4 for frontal only, persistence elsewhere (Joe's proposal)
  persistence_only   — persistence for every ch, ignore L4
  linear_ramp        — w(lead)=max(0, 1 - lead/24) × persist + (1-w) × L4

Metric:
  Per-scenario ch MAE + RMSE, plus decomposition by regime.

Verdict:
  ★ SHIP CANDIDATE     — scenario beats baseline on BOTH halves AND full window
                         with Δ MAE ≥ 3% pooled ch
  ⚠ RECENT-ONLY WIN    — scenario beats baseline on recent only; prior differs
                         → likely anomaly-contaminated per today's diagnostic
  ★ FLAT              — no consistent improvement
"""
import os, sys, json, math
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "output", "h_ch_persistence_blend_summary.txt")

# Halves windows (matches today's regime-gate sweep convention)
WIN_A_LO, WIN_A_HI = "2026-06-26T00:00", "2026-07-11T00:00"  # recent 15d
WIN_B_LO, WIN_B_HI = "2026-06-11T00:00", "2026-06-26T00:00"  # prior 15d
WIN_FULL_LO, WIN_FULL_HI = "2026-06-11T00:00", "2026-07-11T00:00"  # 30d combined

FIELD = "ch"
MIN_N_REGIME = 300


def hour_floor(ts):
    if ts is None or len(ts) < 16:
        return None
    return ts[:14] + "00"


def compute():
    path = cached_path(URL)

    # Pass 1: build obs index for ch (valid_time -> observed)
    print("[1/2] Building ch obs index...", file=sys.stderr)
    obs_ts = {}
    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            vt = r.get("valid_time")
            ob = r.get("observed")
            if vt is None or ob is None:
                continue
            if vt not in obs_ts:
                obs_ts[vt] = ob
    print(f"    ch obs index size: {len(obs_ts):,}", file=sys.stderr)

    # Pass 2: for every ch pair row, compute forecasts under each scenario.
    # accum[(window, scenario, regime)] = {n, ae, se}
    print("[2/2] Scoring ch scenarios...", file=sys.stderr)
    accum = defaultdict(lambda: {"n": 0, "ae": 0.0, "se": 0.0})
    n_joined = 0
    n_orphan = 0

    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            rt = r.get("run_time", "")
            if WIN_A_LO <= rt < WIN_A_HI:
                windows = [("A", None)]  # recent 15d
            elif WIN_B_LO <= rt < WIN_B_HI:
                windows = [("B", None)]  # prior 15d
            else:
                continue
            # Also accumulate into full-window
            windows.append(("FULL", None))

            lead = r.get("lead_h")
            if lead is None:
                continue
            try:
                lead = int(lead)
            except Exception:
                continue
            if lead <= 0 or lead > 47:
                continue

            ob = r.get("observed")
            fc4 = r.get("forecast_l4")
            if ob is None or fc4 is None:
                continue

            persist = obs_ts.get(hour_floor(rt))
            if persist is None:
                n_orphan += 1
                continue
            n_joined += 1

            state_fc = r.get("state_fc") or {}
            regime = state_fc.get("regime_synoptic") or "unknown"

            # Scenario forecasts (persistence + L4 blends)
            fc_baseline = fc4
            fc_regime_gate = fc4 if regime == "frontal" else persist
            fc_persist_only = persist
            w = max(0.0, 1.0 - lead / 24.0)
            fc_linear_ramp = w * persist + (1 - w) * fc4

            forecasts = {
                "baseline":        fc_baseline,
                "regime_gate":     fc_regime_gate,
                "persist_only":    fc_persist_only,
                "linear_ramp":     fc_linear_ramp,
            }
            for win, _ in windows:
                for scenario, fc in forecasts.items():
                    err = fc - ob
                    a = accum[(win, scenario, regime)]
                    a["n"] += 1
                    a["ae"] += abs(err)
                    a["se"] += err * err
                    # Also aggregate across all regimes
                    a_all = accum[(win, scenario, "ALL")]
                    a_all["n"] += 1
                    a_all["ae"] += abs(err)
                    a_all["se"] += err * err

    print(f"    joined {n_joined:,} ch rows to persistence; {n_orphan:,} orphans", file=sys.stderr)
    return accum


def stats(bkt):
    n = bkt["n"]
    if not n:
        return None
    return {
        "n": n,
        "mae": bkt["ae"] / n,
        "rmse": math.sqrt(bkt["se"] / n),
    }


def emit(accum):
    lines = []
    lines.append("=" * 100)
    lines.append("ch REGIME-GATED PERSISTENCE BLEND — Stage 0-1 (halves-stability verified)")
    lines.append("=" * 100)
    lines.append("")
    lines.append("Follow-on to [[project-ch-persistence-gap]]. Joe's design: L4 for `frontal` regime")
    lines.append("only, persistence-of-obs elsewhere. Compared to persistence-only + linear-ramp.")
    lines.append("")

    scenarios = ["baseline", "regime_gate", "persist_only", "linear_ramp"]
    scenario_labels = {
        "baseline":     "current pipeline (L4 everywhere)",
        "regime_gate":  "L4 for `frontal` only, persistence elsewhere",
        "persist_only": "persistence everywhere (no pipeline for ch)",
        "linear_ramp":  "w(lead)=max(0, 1-lead/24) × persist + (1-w) × L4",
    }

    # === Pooled ch MAE per scenario per window ===
    lines.append("=" * 100)
    lines.append("POOLED ch MAE PER SCENARIO PER WINDOW")
    lines.append("=" * 100)
    header = f"{'scenario':<20}{'A recent MAE':>15}{'A recent RMSE':>16}" \
             f"{'B prior MAE':>14}{'B prior RMSE':>15}" \
             f"{'FULL MAE':>12}{'FULL RMSE':>12}"
    lines.append(header)
    lines.append("-" * len(header))
    baseline_recent = stats(accum[("A", "baseline", "ALL")])
    baseline_prior  = stats(accum[("B", "baseline", "ALL")])
    baseline_full   = stats(accum[("FULL", "baseline", "ALL")])
    scenario_results = {}
    for sc in scenarios:
        a = stats(accum[("A", sc, "ALL")])
        b = stats(accum[("B", sc, "ALL")])
        f = stats(accum[("FULL", sc, "ALL")])
        if a and b and f:
            lines.append(f"{sc:<20}{a['mae']:>15.3f}{a['rmse']:>16.3f}"
                         f"{b['mae']:>14.3f}{b['rmse']:>15.3f}"
                         f"{f['mae']:>12.3f}{f['rmse']:>12.3f}")
            scenario_results[sc] = {"A": a, "B": b, "FULL": f}
    lines.append("")

    # === Δ vs baseline (halves + full) ===
    lines.append("=" * 100)
    lines.append("Δ vs BASELINE per scenario per window (negative = scenario beats baseline)")
    lines.append("=" * 100)
    header2 = f"{'scenario':<20}{'A Δ MAE %':>12}{'B Δ MAE %':>12}{'FULL Δ MAE %':>15}  halves-verdict"
    lines.append(header2)
    lines.append("-" * len(header2))
    verdicts = {}
    for sc in scenarios:
        if sc == "baseline":
            continue
        r = scenario_results.get(sc)
        if not r or not baseline_recent or not baseline_prior or not baseline_full:
            continue
        da = (r["A"]["mae"] - baseline_recent["mae"]) / baseline_recent["mae"] * 100
        db = (r["B"]["mae"] - baseline_prior["mae"]) / baseline_prior["mae"] * 100
        df = (r["FULL"]["mae"] - baseline_full["mae"]) / baseline_full["mae"] * 100
        # Halves verdict: both must show ≥3% improvement (negative Δ) for SHIP
        both_win = da <= -3.0 and db <= -3.0
        both_flat = -3.0 < da < 3.0 and -3.0 < db < 3.0
        if both_win:
            verdict = "★ SHIP CANDIDATE"
        elif both_flat:
            verdict = "flat both"
        elif (da <= -3.0) != (db <= -3.0):
            verdict = "⚠ RECENT/PRIOR DIVERGE"
        else:
            verdict = "mixed"
        verdicts[sc] = verdict
        lines.append(f"{sc:<20}{da:>+12.2f}{db:>+12.2f}{df:>+15.2f}  {verdict}")
    lines.append("")

    # === Per-regime detail for the top candidate scenario ===
    top_sc = "regime_gate"  # Joe's proposal is the main design under test
    lines.append("=" * 100)
    lines.append(f"PER-REGIME BREAKDOWN — {top_sc} vs baseline (FULL 30d window)")
    lines.append("=" * 100)
    header3 = f"{'regime':<14}{'n':>8}{'base MAE':>10}{'gate MAE':>10}{'Δ %':>10}"
    lines.append(header3)
    lines.append("-" * len(header3))
    regimes_seen = set()
    for (win, sc, reg), _ in accum.items():
        if win == "FULL" and sc == "baseline":
            regimes_seen.add(reg)
    for reg in sorted(regimes_seen - {"ALL"}, key=lambda r: -accum[("FULL","baseline",r)]["n"]):
        b_r = stats(accum[("FULL", "baseline", reg)])
        s_r = stats(accum[("FULL", top_sc, reg)])
        if not b_r or not s_r or b_r["n"] < MIN_N_REGIME:
            continue
        delta = (s_r["mae"] - b_r["mae"]) / b_r["mae"] * 100
        marker = ""
        if delta <= -5:
            marker = "★"
        elif delta >= 5:
            marker = "⚠"
        lines.append(f"{reg:<14}{b_r['n']:>8,}{b_r['mae']:>10.2f}{s_r['mae']:>10.2f}{delta:>+10.2f}  {marker}")
    lines.append("")

    # === Final verdict line for digest ===
    lines.append("=" * 100)
    if verdicts.get("regime_gate") == "★ SHIP CANDIDATE":
        lines.append("Verdict: SHIP — regime_gate (frontal→L4, else persistence) beats baseline "
                     "on both halves + full window.")
    elif verdicts.get("regime_gate") == "⚠ RECENT/PRIOR DIVERGE":
        lines.append("Verdict: HOLD — regime_gate wins one half but not the other. "
                     "Likely anomaly contamination; re-audit after next Stage 4 window.")
    else:
        lines.append(f"Verdict: {verdicts.get('regime_gate', 'unclear')} — "
                     "regime_gate doesn't cleanly beat baseline on halves check.")

    # If persist_only ships too, that's the landmark
    if verdicts.get("persist_only") == "★ SHIP CANDIDATE":
        lines.append("★★ LANDMARK: persistence-only ALSO beats baseline on halves — "
                     "consider pulling ch from L3+L4 entirely.")

    return "\n".join(lines)


def main():
    accum = compute()
    text = emit(accum)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)


if __name__ == "__main__":
    main()
