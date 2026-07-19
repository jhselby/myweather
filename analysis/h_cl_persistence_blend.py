"""Stage 0-1 — cl regime-gated persistence blend.

Follow-on to [[project-persistence-skill-baseline]] + Stage 3 ship of the
ch regime-gated persistence gate ([[project-ch-persistence-gate-ship]],
v0.6.327 on 2026-07-12). h_persistence_skill.py put cl in the same "NO
SKILL" bucket as ch and cm — the current pipeline (L1 raw for cl; cl
is NOT in L3_FIELDS or L4_FIELDS, only L2 blend on hourly[0]) does not
beat naive persistence at any lead band.

Question: does the ch regime-gate shape ("L4 for `frontal`, persistence
elsewhere") replicate for cl, or does cl have a different regime shape?
Halves-verified verdict per scenario (matches ch script structure).

For cl, "baseline" = forecast_l4 field in pair log = raw L1 forecast
(cl passes through decay_apply unchanged). So the regime_gate scenario
under test is really "L1 for frontal, persistence elsewhere" — same
architectural shape as ch's ship, adapted for the different pipeline.

Scenarios:
  baseline           — current pipeline for cl (L1 raw; no L3/L4)
  regime_gate        — baseline in `frontal` regime, persistence elsewhere
  persistence_only   — persistence-of-obs for every cl, ignore baseline
  linear_ramp        — w(lead)=max(0, 1-lead/24) × persist + (1-w) × baseline

Verdict rules match ch: SHIP requires both halves + full window
≥ 3% MAE improvement. RECENT-ONLY WIN or PRIOR-ONLY WIN → HOLD.

If regime_gate ships: Stage 2 preview (per regime × lead_band) becomes
next Sunday's deliverable. If persistence_only ships too, landmark
thread same as ch — flag but do not ship persistence-only globally
without cell-conditioned verification.

If regime_gate does NOT ship but persistence_only does, cl has a
different regime shape than ch (no single-regime-wins carve-out) — go
straight to Stage 2 per-regime slicing to identify the actual winner.
"""
import os, sys, json, math
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "output", "h_cl_persistence_blend_summary.txt")

# Halves windows match the ch script exactly.
# 2026-07-19: slid forward 8 days so windows cover post-shift data
# (MLC collapse / cc-cluster distribution shift). See v0.6.359.
WIN_A_LO, WIN_A_HI = "2026-07-04T00:00", "2026-07-19T00:00"  # recent 15d
WIN_B_LO, WIN_B_HI = "2026-06-19T00:00", "2026-07-04T00:00"  # prior 15d
WIN_FULL_LO, WIN_FULL_HI = "2026-06-19T00:00", "2026-07-19T00:00"  # 30d combined

FIELD = "cl"
MIN_N_REGIME = 300


def hour_floor(ts):
    if ts is None or len(ts) < 16:
        return None
    return ts[:14] + "00"


def compute():
    path = cached_path(URL)

    print("[1/2] Building cl obs index...", file=sys.stderr)
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
    print(f"    cl obs index size: {len(obs_ts):,}", file=sys.stderr)

    print("[2/2] Scoring cl scenarios...", file=sys.stderr)
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
                windows = [("A", None)]
            elif WIN_B_LO <= rt < WIN_B_HI:
                windows = [("B", None)]
            else:
                continue
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

            fc_baseline = fc4
            fc_regime_gate = fc4 if regime == "frontal" else persist
            fc_persist_only = persist
            w = max(0.0, 1.0 - lead / 24.0)
            fc_linear_ramp = w * persist + (1 - w) * fc4

            forecasts = {
                "baseline":     fc_baseline,
                "regime_gate":  fc_regime_gate,
                "persist_only": fc_persist_only,
                "linear_ramp":  fc_linear_ramp,
            }
            for win, _ in windows:
                for scenario, fc in forecasts.items():
                    err = fc - ob
                    a = accum[(win, scenario, regime)]
                    a["n"] += 1
                    a["ae"] += abs(err)
                    a["se"] += err * err
                    a_all = accum[(win, scenario, "ALL")]
                    a_all["n"] += 1
                    a_all["ae"] += abs(err)
                    a_all["se"] += err * err

    print(f"    joined {n_joined:,} cl rows to persistence; {n_orphan:,} orphans", file=sys.stderr)
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
    lines.append("cl REGIME-GATED PERSISTENCE BLEND — Stage 0-1 (halves-stability verified)")
    lines.append("=" * 100)
    lines.append("")
    lines.append("Follow-on to ch persistence gate ship (v0.6.327 2026-07-12). Does the ch")
    lines.append("regime-gate shape ('L4 for `frontal`, persistence else') replicate for cl,")
    lines.append("or does cl have a different regime shape?")
    lines.append("")
    lines.append("Note: for cl, baseline = raw L1 (cl is not in L3_FIELDS or L4_FIELDS).")
    lines.append("So 'regime_gate' under test = 'L1 for frontal, persistence elsewhere'.")
    lines.append("")

    scenarios = ["baseline", "regime_gate", "persist_only", "linear_ramp"]

    lines.append("=" * 100)
    lines.append("POOLED cl MAE PER SCENARIO PER WINDOW")
    lines.append("=" * 100)
    header = (f"{'scenario':<20}{'A recent MAE':>15}{'A recent RMSE':>16}"
              f"{'B prior MAE':>14}{'B prior RMSE':>15}"
              f"{'FULL MAE':>12}{'FULL RMSE':>12}")
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

    # Per-regime detail for regime_gate
    top_sc = "regime_gate"
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

    # Also print per-regime for persist_only — cl may not have a frontal exception
    lines.append("=" * 100)
    lines.append("PER-REGIME BREAKDOWN — persist_only vs baseline (FULL 30d window)")
    lines.append("Reveals whether ANY regime prefers baseline over persistence for cl.")
    lines.append("=" * 100)
    lines.append(header3)
    lines.append("-" * len(header3))
    for reg in sorted(regimes_seen - {"ALL"}, key=lambda r: -accum[("FULL","baseline",r)]["n"]):
        b_r = stats(accum[("FULL", "baseline", reg)])
        s_r = stats(accum[("FULL", "persist_only", reg)])
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

    # linear_ramp per-regime — sanity: is the pooled win just the same
    # {se_flow, calm, unknown} carve-out, diluted by 50/50 average?
    lines.append("=" * 100)
    lines.append("PER-REGIME BREAKDOWN — linear_ramp vs baseline (FULL 30d window)")
    lines.append("Is the halves-passing linear_ramp win a separate architecture, or just a")
    lines.append("diluted persist_only? If wins/losses track persist_only sign-for-sign, it's dilution.")
    lines.append("=" * 100)
    header_lr = f"{'regime':<14}{'n':>8}{'base MAE':>10}{'lramp MAE':>10}{'Δ %':>10}   persist Δ %"
    lines.append(header_lr)
    lines.append("-" * len(header_lr))
    for reg in sorted(regimes_seen - {"ALL"}, key=lambda r: -accum[("FULL","baseline",r)]["n"]):
        b_r = stats(accum[("FULL", "baseline", reg)])
        lr_r = stats(accum[("FULL", "linear_ramp", reg)])
        p_r  = stats(accum[("FULL", "persist_only", reg)])
        if not b_r or not lr_r or not p_r or b_r["n"] < MIN_N_REGIME:
            continue
        lr_delta = (lr_r["mae"] - b_r["mae"]) / b_r["mae"] * 100
        p_delta  = (p_r["mae"]  - b_r["mae"]) / b_r["mae"] * 100
        marker = ""
        if lr_delta <= -5:
            marker = "★"
        elif lr_delta >= 5:
            marker = "⚠"
        lines.append(f"{reg:<14}{b_r['n']:>8,}{b_r['mae']:>10.2f}{lr_r['mae']:>10.2f}"
                     f"{lr_delta:>+10.2f}   {p_delta:>+10.2f}  {marker}")
    lines.append("")

    # Final verdict
    lines.append("=" * 100)
    if verdicts.get("regime_gate") == "★ SHIP CANDIDATE":
        lines.append("Verdict: SHIP CANDIDATE — regime_gate (frontal→baseline, else persistence) "
                     "beats baseline on both halves + full window. Stage 2 preview next.")
    elif verdicts.get("regime_gate") == "⚠ RECENT/PRIOR DIVERGE":
        lines.append("Verdict: HOLD — regime_gate wins one half but not the other. "
                     "Likely anomaly contamination; re-audit after window roll.")
    elif verdicts.get("persist_only") == "★ SHIP CANDIDATE":
        lines.append("Verdict: DIFFERENT REGIME SHAPE THAN ch — regime_gate does NOT win "
                     "cleanly but persistence_only does. cl may not have a 'frontal exception'. "
                     "Go straight to Stage 2 per-regime × lead_band slicing.")
    else:
        lines.append(f"Verdict: {verdicts.get('regime_gate', 'unclear')} — "
                     "regime_gate doesn't cleanly beat baseline on halves check.")

    if verdicts.get("persist_only") == "★ SHIP CANDIDATE":
        lines.append("★★ Persistence-only also passes halves — same landmark thread as ch. "
                     "Do NOT ship persistence-only globally; require Stage 2 cell verification.")

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
