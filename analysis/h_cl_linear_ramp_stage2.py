"""cl linear_ramp Stage 2 preview — per (regime × lead_band) + τ scan.

Follow-on to h_cl_persistence_blend.py (Stage 1). That script found:
  - regime_gate + persist_only fail halves (anomaly contamination)
  - linear_ramp with τ=24h passes halves AND wins in 9 of 9 regimes
    against baseline (pooled −6.4%, prior half −3.8%)

Open questions for Stage 2:
  1. Are there (regime × lead_band) cells where linear_ramp actively
     hurts, hidden by pooled per-regime wins?
  2. Does τ≠24 fit better? Ramp shape: w(lead) = max(0, 1 - lead/τ).

Method: same 30d + halves + full windows as Stage 1. Compute baseline
and linear_ramp under τ ∈ {12, 18, 24, 36} for every ch pair row (well
— cl pair row). Score:
  - Pooled halves + full window per τ
  - Per (regime × lead_band) for the winning τ

Verdict rules per cell (winning τ):
  SHIP   — n ≥ MIN_N and lramp beats baseline by ≥ 3% on BOTH halves + full
  MARGIN — lramp beats baseline on full but one half below floor
  SKIP   — lramp loses on full OR halves disagree in sign
  THIN   — n < MIN_N

If τ scan picks a τ ≠ 24 clearly, the "ship as L2 lead-decay for cl"
plan wants that τ. If SKIP cells are concentrated (e.g. all sw_flow
long lead), the shipping architecture might need a skip table.
"""
import os, sys, json, math
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "output", "h_cl_linear_ramp_stage2.txt")

# 2026-07-19: slid forward 8 days so windows cover post-shift data
# (MLC collapse / cc-cluster distribution shift). See v0.6.358.
WIN_A_LO, WIN_A_HI = "2026-07-08T00:00", "2026-07-23T00:00"
WIN_B_LO, WIN_B_HI = "2026-06-23T00:00", "2026-07-08T00:00"
WIN_FULL_LO, WIN_FULL_HI = "2026-06-23T00:00", "2026-07-23T00:00"

FIELD = "cl"
MIN_N_CELL = 200
MAE_IMPROVE_FLOOR_PCT = 3.0

TAUS = [12, 18, 24, 36]

LEAD_BANDS = [
    ("0-5",   1,  5),
    ("6-11",  6, 11),
    ("12-23", 12, 23),
    ("24-47", 24, 47),
]


def lead_band(lead):
    for name, lo, hi in LEAD_BANDS:
        if lo <= lead <= hi:
            return name
    return None


def hour_floor(ts):
    if ts is None or len(ts) < 16:
        return None
    return ts[:14] + "00"


def compute():
    path = cached_path(URL)

    print(f"[1/2] Building {FIELD} obs index...", file=sys.stderr)
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
    print(f"    {FIELD} obs index size: {len(obs_ts):,}", file=sys.stderr)

    # accum[(window, scenario, regime, band)] = {n, ae}
    print("[2/2] Scoring baseline + linear_ramp(τ) per (regime × band)...", file=sys.stderr)
    accum = defaultdict(lambda: {"n": 0, "ae": 0.0})
    n_joined = 0

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
                windows = [("A", None), ("FULL", None)]
            elif WIN_B_LO <= rt < WIN_B_HI:
                windows = [("B", None), ("FULL", None)]
            else:
                continue

            lead = r.get("lead_h")
            if lead is None:
                continue
            try:
                lead = int(lead)
            except Exception:
                continue
            band = lead_band(lead)
            if band is None:
                continue

            ob = r.get("observed")
            fc4 = r.get("forecast_l4")
            if ob is None or fc4 is None:
                continue

            persist = obs_ts.get(hour_floor(rt))
            if persist is None:
                continue
            n_joined += 1

            state_fc = r.get("state_fc") or {}
            regime = state_fc.get("regime_synoptic") or "unknown"

            err_base = fc4 - ob
            for win, _ in windows:
                a = accum[(win, "baseline", regime, band)]
                a["n"] += 1
                a["ae"] += abs(err_base)
                a_all = accum[(win, "baseline", "ALL", "ALL")]
                a_all["n"] += 1
                a_all["ae"] += abs(err_base)

            for tau in TAUS:
                w = max(0.0, 1.0 - lead / float(tau))
                fc_lr = w * persist + (1 - w) * fc4
                err_lr = fc_lr - ob
                sc = f"lramp_t{tau}"
                for win, _ in windows:
                    a = accum[(win, sc, regime, band)]
                    a["n"] += 1
                    a["ae"] += abs(err_lr)
                    a_all = accum[(win, sc, "ALL", "ALL")]
                    a_all["n"] += 1
                    a_all["ae"] += abs(err_lr)

    print(f"    joined {n_joined:,} cl rows", file=sys.stderr)
    return accum


def mae(bkt):
    n = bkt["n"]
    return (bkt["ae"] / n) if n else None


def emit(accum):
    lines = []
    lines.append("=" * 100)
    lines.append("cl LINEAR_RAMP — Stage 2 preview (τ scan + per (regime × lead_band))")
    lines.append("=" * 100)
    lines.append("")

    # === τ scan pooled ===
    lines.append("=" * 100)
    lines.append("TAU SCAN — pooled cl MAE across windows (all 9 regimes, all 4 bands)")
    lines.append("=" * 100)
    header = (f"{'scenario':<12}{'A recent MAE':>15}{'B prior MAE':>14}{'FULL MAE':>12}"
              f"{'A Δ %':>10}{'B Δ %':>10}{'FULL Δ %':>12}  halves-verdict")
    lines.append(header)
    lines.append("-" * len(header))
    base_a = mae(accum[("A", "baseline", "ALL", "ALL")])
    base_b = mae(accum[("B", "baseline", "ALL", "ALL")])
    base_f = mae(accum[("FULL", "baseline", "ALL", "ALL")])
    lines.append(f"{'baseline':<12}{base_a:>15.3f}{base_b:>14.3f}{base_f:>12.3f}"
                 f"{'—':>10}{'—':>10}{'—':>12}  reference")
    best_tau = None
    best_full_delta = 0.0
    tau_verdicts = {}
    for tau in TAUS:
        sc = f"lramp_t{tau}"
        a = mae(accum[("A", sc, "ALL", "ALL")])
        b = mae(accum[("B", sc, "ALL", "ALL")])
        f = mae(accum[("FULL", sc, "ALL", "ALL")])
        if not (a and b and f and base_a and base_b and base_f):
            continue
        da = 100.0 * (a - base_a) / base_a
        db = 100.0 * (b - base_b) / base_b
        df = 100.0 * (f - base_f) / base_f
        both_win = da <= -MAE_IMPROVE_FLOOR_PCT and db <= -MAE_IMPROVE_FLOOR_PCT
        verdict = "★ SHIP CANDIDATE" if both_win else "HOLD"
        tau_verdicts[tau] = (verdict, df)
        if df < best_full_delta:
            best_full_delta = df
            best_tau = tau
        lines.append(f"{sc:<12}{a:>15.3f}{b:>14.3f}{f:>12.3f}"
                     f"{da:>+10.2f}{db:>+10.2f}{df:>+12.2f}  {verdict}")
    lines.append("")
    lines.append(f"Best τ by full-window MAE: τ={best_tau} ({best_full_delta:+.2f}%)")
    lines.append("")

    if best_tau is None:
        lines.append("No linear_ramp scenarios could be scored. Bail.")
        return "\n".join(lines)

    # === Per (regime × band) for the winning τ ===
    best_sc = f"lramp_t{best_tau}"
    lines.append("=" * 100)
    lines.append(f"PER (regime × lead_band) — linear_ramp τ={best_tau} vs baseline (FULL 30d)")
    lines.append("Cell verdict: SHIP if both halves + full ≥ 3% improvement, SKIP if loses full or halves flip sign.")
    lines.append("=" * 100)
    header2 = (f"{'regime':<12}{'band':<8}{'n':>8}"
               f"{'base MAE':>10}{'lramp MAE':>10}"
               f"{'Δ full %':>10}{'Δ A %':>9}{'Δ B %':>9}  verdict")
    lines.append(header2)
    lines.append("-" * len(header2))

    # collect regimes
    regimes = sorted({k[2] for k in accum.keys() if k[2] != "ALL"})
    bands = [name for name, _, _ in LEAD_BANDS]

    ship_cells, margin_cells, skip_cells, thin_cells = [], [], [], []

    for regime in regimes:
        for band in bands:
            b_f = mae(accum[("FULL", "baseline", regime, band)])
            l_f = mae(accum[("FULL", best_sc,   regime, band)])
            b_a = mae(accum[("A",    "baseline", regime, band)])
            l_a = mae(accum[("A",    best_sc,   regime, band)])
            b_b = mae(accum[("B",    "baseline", regime, band)])
            l_b = mae(accum[("B",    best_sc,   regime, band)])
            n_full = accum[("FULL", "baseline", regime, band)]["n"]
            if n_full == 0 or b_f is None or l_f is None:
                continue

            if n_full < MIN_N_CELL:
                verdict = "THIN"
                d_full = d_a = d_b = None
            else:
                d_full = 100.0 * (l_f - b_f) / b_f if b_f else 0.0
                d_a = 100.0 * (l_a - b_a) / b_a if (b_a and l_a is not None) else None
                d_b = 100.0 * (l_b - b_b) / b_b if (b_b and l_b is not None) else None
                halves_flip = (d_a is not None and d_b is not None
                               and (d_a * d_b) < 0)
                if (d_full <= -MAE_IMPROVE_FLOOR_PCT
                    and d_a is not None and d_a <= -MAE_IMPROVE_FLOOR_PCT
                    and d_b is not None and d_b <= -MAE_IMPROVE_FLOOR_PCT):
                    verdict = "SHIP"
                elif d_full > 0 or halves_flip:
                    verdict = "SKIP"
                else:
                    verdict = "MARGIN"

            key = (regime, band)
            {"SHIP": ship_cells, "MARGIN": margin_cells,
             "SKIP": skip_cells, "THIN": thin_cells}[verdict].append(key)

            star = " ★" if verdict == "SHIP" else ""
            d_full_s = f"{d_full:+.2f}" if d_full is not None else "  n/a"
            d_a_s    = f"{d_a:+.2f}" if d_a is not None else "  n/a"
            d_b_s    = f"{d_b:+.2f}" if d_b is not None else "  n/a"
            lines.append(f"{regime:<12}{band:<8}{n_full:>8,}"
                         f"{b_f:>10.3f}{l_f:>10.3f}"
                         f"{d_full_s:>10}{d_a_s:>9}{d_b_s:>9}  {verdict}{star}")
        lines.append("")

    lines.append("=" * 100)
    lines.append("ROLLUP")
    lines.append("=" * 100)
    lines.append(f"  SHIP:   {len(ship_cells):>3} cells")
    lines.append(f"  MARGIN: {len(margin_cells):>3} cells")
    lines.append(f"  SKIP:   {len(skip_cells):>3} cells")
    lines.append(f"  THIN:   {len(thin_cells):>3} cells")
    lines.append("")

    if skip_cells:
        by_band = defaultdict(list)
        by_regime = defaultdict(list)
        for regime, band in skip_cells:
            by_band[band].append(regime)
            by_regime[regime].append(band)
        lines.append("SKIP concentration:")
        for band, regs in sorted(by_band.items()):
            lines.append(f"  band {band:<6}: {len(regs)} regimes → {sorted(regs)}")
        for regime, bnds in sorted(by_regime.items()):
            lines.append(f"  regime {regime:<12}: {len(bnds)} bands → {sorted(bnds)}")
        lines.append("")

    lines.append("=" * 100)
    if len(ship_cells) >= 15:
        lines.append(f"Verdict: STRONG — {len(ship_cells)} SHIP cells at τ={best_tau}. "
                     "Consider shipping as cl→L2 lead-decay with skip table for SKIP cells.")
    elif len(ship_cells) >= 8:
        lines.append(f"Verdict: MODERATE — {len(ship_cells)} SHIP cells at τ={best_tau}. "
                     "Halves-diverge concerns may be mostly anomaly-driven; re-audit 07-18+.")
    else:
        lines.append(f"Verdict: WEAK — only {len(ship_cells)} SHIP cells clear halves. "
                     "cl pooled win is likely anomaly-inflated. Re-audit 07-18+.")

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
