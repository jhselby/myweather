"""
Retro cross-cut: does pr L2 (τ=12h, K=1) beat raw in ANY regime × lead cell?

Context:
  pr L2 additive bias was disabled 2026-07-01 (v0.6.276) on a POOLED
  Production-vs-raw number (+2.4% worse than raw). That decision predates
  the regime-gate-first discipline (feedback_regime_gate_first, formalized
  ~07-11) and the skip-table architecture (v0.6.279). This script re-asks
  the question with the regime × lead cross-cut we now run before every
  ship/drop decision — AND with halves-verification, the discipline every
  Stage-1-ship-candidate specialist (dpbp, wsbp, pp Platt) has gotten.

Method:
  Stream pair log, pr rows only. Keep only rows where forecast_l2 !=
  forecast_l1 (i.e., L2 was actually applied — this naturally filters to
  the pre-07-01 window today; post-v0.6.389 shadow-wire adds live-shadow
  rows to the same filter, so the script transparently transitions from
  retro-only to shadow-heavy as the pair log fills).

  Per (regime × lead_band):
    |raw|     = |err_l1|              — L2 OFF (current production)
    |L2-on|   = |err_l2|              — L2 ON (τ=12h decay baked in by writer)
    Δ%        = (|raw| - |L2-on|) / |raw| * 100

  Halves-verification (Section B): sort qualifying rows by obs_time, split
  at row-count median into halves A (earlier) / B (later). Compute cell
  verdicts independently in each half. Report Jaccard overlap of WIN sets
  and per-strong-cell (n≥MIN_N_PER_CELL in BOTH halves) A/B Δ%. A cell is
  BOTH-WIN if it exceeds WIN threshold in both halves.

Verdicts per cell (n≥200 floor):
    WIN      Δ ≥ +2%   — L2 on beats raw
    flat    -2% < Δ < +2%
    ★ L2 LOSES  Δ ≤ -2%   — L2 on worse than raw (current pooled verdict)

What to do with the output:
  Pooled (Section A):
    All-LOSS / all-flat → 07-01 kill was correct at cell resolution too.
    Any WIN cell → gate-ON-where-wins shape identified. Go to halves.
  Halves (Section B):
    Jaccard ≥ 0.5 AND ≥1 BOTH-WIN cell → Stage 1 evidence. Can consider
      shipping gate-ON-where-wins config w/o waiting full shadow window.
    Jaccard < 0.5 OR zero BOTH-WIN cells → single-window artifact. Wait
      for fresh shadow data (~2 weeks post-v0.6.389 deploy).

Companion to analysis/l2_regime_lead_analysis.py (sr, blocked). The core
regime × lead machinery is the same; this variant compares on-vs-off
rather than flat-vs-decay because pr's open question is re-enable, not
τ-tuning.
"""
import json
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "pr_l2_regime_lead_retro.txt")

FIELD = "pr"
LEAD_BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N_PER_CELL = 200
WIN_THRESHOLD_PCT = 2.0
LOSS_THRESHOLD_PCT = -2.0
JACCARD_STAGE1_THRESHOLD = 0.5

# Cells where pr L2 is already firing in production (corrected_hourly.py
# _PR_L2_FIRE_CELLS, shipped v0.6.401 2026-08-10). Reported separately in
# the verdict so cross-window movement on candidate cells doesn't mask the
# health of the live gate.
SHIPPED_CELLS = {("nw_flow", "0-5h"), ("nw_flow", "6-11h")}


def lead_band(lead_h):
    for label, lo, hi in LEAD_BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def verdict_for(delta_pct, n):
    if n < MIN_N_PER_CELL:
        return "thin"
    if delta_pct <= LOSS_THRESHOLD_PCT:
        return "★ L2 LOSES"
    if delta_pct >= WIN_THRESHOLD_PCT:
        return "WIN"
    return "flat"


def aggregate(rows):
    """rows: iterable of (band, regime, e_raw, e_l2). Returns
    dict[(band, regime)] -> (n, mean_raw, mean_l2, delta_pct, verdict)."""
    by_cell = defaultdict(lambda: [0, 0.0, 0.0])
    for band, regime, e_raw, e_l2 in rows:
        c = by_cell[(band, regime)]
        c[0] += 1
        c[1] += e_raw
        c[2] += e_l2
    out = {}
    for key, (n, s_raw, s_l2) in by_cell.items():
        if n == 0:
            continue
        m_raw = s_raw / n
        m_l2 = s_l2 / n
        d_pct = (m_raw - m_l2) / m_raw * 100 if m_raw > 0 else 0.0
        out[key] = (n, m_raw, m_l2, d_pct, verdict_for(d_pct, n))
    return out


def main():
    print("=" * 86)
    print(f"pr L2 REGIME × LEAD-BAND RETRO — raw (L2 OFF) vs L2 ON (τ=12h)")
    print("=" * 86)

    print("\n[1/3] Streaming pair log (pr only, filtered to rows where L2 actually applied)...")
    # Collect per-row so we can split by obs_time for halves-verification.
    # Filtered pr rows ~11k in current window — memory fine.
    rows = []  # (obs_time, band, regime, e_raw, e_l2)

    n_total = n_field = n_l2_applied = n_no_regime = 0
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            n_total += 1
            if r.get("field") != FIELD:
                continue
            n_field += 1

            lead_h = r.get("lead_h")
            f_l1 = r.get("forecast_l1")
            f_l2 = r.get("forecast_l2")
            obs = r.get("observed")
            if lead_h is None or f_l1 is None or f_l2 is None or obs is None:
                continue
            if abs(float(f_l2) - float(f_l1)) < 1e-9:
                continue
            n_l2_applied += 1

            band = lead_band(lead_h)
            if band is None:
                continue

            so = r.get("state_obs") or {}
            regime = so.get("regime_synoptic")
            if not regime:
                n_no_regime += 1
                continue

            obs_time = r.get("obs_time") or r.get("valid_time") or ""
            e_raw = abs(float(f_l1) - float(obs))
            e_l2 = abs(float(f_l2) - float(obs))
            rows.append((obs_time, band, regime, e_raw, e_l2))

    print(f"  total pair rows:            {n_total:,}")
    print(f"  {FIELD} rows:                     {n_field:,}")
    print(f"  {FIELD} rows w/ L2 applied:       {n_l2_applied:,}")
    print(f"  kept (with regime):         {len(rows):,}")
    print(f"  skipped (no regime):        {n_no_regime:,}")

    if not rows:
        print("\nNo usable rows. Pair log has no pr rows with a live L2 shift.")
        print("Post-v0.6.389 this should populate within ~1 collector tick.")
        return 1

    lines = []

    def emit(s):
        print(s)
        lines.append(s)

    # ============================================================
    # SECTION A — pooled
    # ============================================================
    emit("\n" + "=" * 86)
    emit("[A] pr L2 effect by SYNOPTIC REGIME × LEAD BAND — POOLED (all L2-applied rows)")
    emit("    raw = err_l1 (L2 OFF, current prod)   L2-on = err_l2 (τ=12h applied)")
    emit("=" * 86)

    pooled = aggregate((band, regime, e_raw, e_l2)
                       for (_, band, regime, e_raw, e_l2) in rows)
    all_regimes = sorted({k[1] for k in pooled.keys()})

    header = (f"  {'regime':<14} {'lead':<8} {'n':>8} "
              f"{'|raw|':>9} {'|L2-on|':>9} {'Δ%':>7}  verdict")
    emit(header)
    emit("  " + "-" * 80)

    tally = {"WIN": 0, "flat": 0, "★ L2 LOSES": 0, "thin": 0}
    win_cells = []
    loss_cells = []
    for regime in all_regimes:
        for band_label, _, _ in LEAD_BANDS:
            v_tuple = pooled.get((band_label, regime))
            if not v_tuple:
                continue
            n, m_raw, m_l2, d_pct, v = v_tuple
            tally[v] = tally.get(v, 0) + 1
            if v == "WIN":
                win_cells.append((regime, band_label, n, d_pct))
            elif v == "★ L2 LOSES":
                loss_cells.append((regime, band_label, n, d_pct))
            emit(f"  {regime:<14} {band_label:<8} {n:>8,} "
                 f"{m_raw:>9.4f} {m_l2:>9.4f} {d_pct:>6.1f}%  {v}")
        emit("")

    emit(f"Summary (pooled): {tally.get('WIN', 0)} WIN / {tally.get('flat', 0)} flat / "
         f"{tally.get('★ L2 LOSES', 0)} L2 LOSES / {tally.get('thin', 0)} thin")

    # ============================================================
    # SECTION B — halves-verified
    # ============================================================
    emit("\n" + "=" * 86)
    emit("[B] HALVES-VERIFICATION — split L2-applied rows at row-count median obs_time")
    emit("    Cell qualifies BOTH-WIN if Δ ≥ +2% with n≥200 in EACH half independently.")
    emit("=" * 86)

    rows_sorted = sorted(rows, key=lambda r: r[0])
    mid = len(rows_sorted) // 2
    half_a = rows_sorted[:mid]
    half_b = rows_sorted[mid:]
    a_range = (half_a[0][0][:10], half_a[-1][0][:10]) if half_a else ("", "")
    b_range = (half_b[0][0][:10], half_b[-1][0][:10]) if half_b else ("", "")
    emit(f"  half A: {a_range[0]} → {a_range[1]}   n={len(half_a):,}")
    emit(f"  half B: {b_range[0]} → {b_range[1]}   n={len(half_b):,}")

    agg_a = aggregate((band, regime, e_raw, e_l2)
                      for (_, band, regime, e_raw, e_l2) in half_a)
    agg_b = aggregate((band, regime, e_raw, e_l2)
                      for (_, band, regime, e_raw, e_l2) in half_b)

    wins_a = {k for k, v in agg_a.items() if v[4] == "WIN"}
    wins_b = {k for k, v in agg_b.items() if v[4] == "WIN"}
    union = wins_a | wins_b
    inter = wins_a & wins_b
    jaccard = len(inter) / len(union) if union else 0.0

    emit("")
    emit(f"  half A WIN set (n={len(wins_a)}): "
         + (", ".join(f"{r}/{b}" for b, r in sorted(wins_a)) if wins_a else "none"))
    emit(f"  half B WIN set (n={len(wins_b)}): "
         + (", ".join(f"{r}/{b}" for b, r in sorted(wins_b)) if wins_b else "none"))
    emit(f"  intersection (BOTH-WIN, n={len(inter)}): "
         + (", ".join(f"{r}/{b}" for b, r in sorted(inter)) if inter else "none"))
    emit(f"  Jaccard(A, B) = {jaccard:.2f}   (Stage 1 threshold: ≥ {JACCARD_STAGE1_THRESHOLD})")

    # Per-cell A vs B table for cells with n≥MIN_N_PER_CELL in BOTH halves
    emit("")
    emit("  Per-cell A vs B (both halves n ≥ MIN):")
    emit(f"  {'regime':<14} {'lead':<8} {'nA':>6} {'ΔA%':>7} {'nB':>6} {'ΔB%':>7}  status")
    emit("  " + "-" * 70)
    strong_both = []
    all_keys = sorted(set(agg_a.keys()) | set(agg_b.keys()))
    for key in all_keys:
        a = agg_a.get(key)
        b = agg_b.get(key)
        if not a or not b:
            continue
        nA, _, _, dA, vA = a
        nB, _, _, dB, vB = b
        if nA < MIN_N_PER_CELL or nB < MIN_N_PER_CELL:
            continue
        both_win = (vA == "WIN") and (vB == "WIN")
        one_win_one_loss = (vA == "WIN" and vB == "★ L2 LOSES") or \
                           (vB == "WIN" and vA == "★ L2 LOSES")
        if both_win:
            status = "★ BOTH-WIN"
            strong_both.append((key, nA, dA, nB, dB))
        elif one_win_one_loss:
            status = "☠ FLIPS"
        elif vA == "WIN" or vB == "WIN":
            status = "half-only WIN"
        else:
            status = ""
        band_label, regime = key
        emit(f"  {regime:<14} {band_label:<8} {nA:>6,} {dA:>6.1f}% "
             f"{nB:>6,} {dB:>6.1f}%  {status}")

    # ============================================================
    # SHIPPED CELLS STATUS — health of the live pr L2 gate
    # ============================================================
    emit("\n" + "=" * 86)
    emit("SHIPPED CELLS STATUS  (live pr L2 gate — v0.6.401)")
    emit("=" * 86)
    shipped_lines = []
    shipped_healthy = 0
    shipped_at_risk = 0
    for (regime, band_label) in sorted(SHIPPED_CELLS):
        key = (band_label, regime)
        p = pooled.get(key)
        a = agg_a.get(key)
        b = agg_b.get(key)
        p_txt = f"pooled Δ {p[3]:+.1f}% n={p[0]:,} [{p[4]}]" if p else "pooled: no data"
        a_txt = f"A Δ {a[3]:+.1f}%/n={a[0]:,}" if a else "A: —"
        b_txt = f"B Δ {b[3]:+.1f}%/n={b[0]:,}" if b else "B: —"
        # Health: pooled WIN AND both halves ≥ 0 (not backsliding). Flag if
        # either half loses even if pooled still wins — that's the early
        # signal the live gate is degrading.
        healthy = (p is not None and p[4] == "WIN"
                   and a is not None and a[3] >= 0
                   and b is not None and b[3] >= 0)
        mark = "✓ HEALTHY" if healthy else "⚠ AT RISK"
        if healthy: shipped_healthy += 1
        else:       shipped_at_risk += 1
        shipped_lines.append(f"  {regime}/{band_label:<8}  {mark}   {p_txt}   {a_txt}   {b_txt}")
    for line in shipped_lines:
        emit(line)
    emit(f"  → {shipped_healthy}/{len(SHIPPED_CELLS)} shipped cells healthy, "
         f"{shipped_at_risk} at risk.")

    # Candidate-only Jaccard — excludes SHIPPED_CELLS so today's cross-half
    # WIN-set movement reflects genuine candidate churn, not membership of
    # cells that are already live.
    cand_wins_a = {k for k in wins_a if (k[1], k[0]) not in SHIPPED_CELLS}
    cand_wins_b = {k for k in wins_b if (k[1], k[0]) not in SHIPPED_CELLS}
    cand_union = cand_wins_a | cand_wins_b
    cand_inter = cand_wins_a & cand_wins_b
    cand_jaccard = len(cand_inter) / len(cand_union) if cand_union else 0.0
    emit(f"  candidate-only Jaccard(A, B) = {cand_jaccard:.2f}   "
         f"(shipped cells excluded; use this to judge NEW ship candidates)")

    # ============================================================
    # VERDICT  (about NEW ship candidates — shipped cells covered above)
    # ============================================================
    emit("\n" + "=" * 86)
    emit("VERDICT")
    emit("=" * 86)
    if tally["WIN"] == 0:
        emit("  → 07-01 KILL HOLDS at cell resolution. No pooled (regime × lead_band)")
        emit("    cell shows pr L2 beating raw ≥2% with n≥200. Close the door on")
        emit("    re-enable.")
    else:
        pooled_win_str = "; ".join(f"{r}/{b} ({d:+.1f}%, n={n:,})"
                                   for r, b, n, d in win_cells)
        if strong_both and jaccard >= JACCARD_STAGE1_THRESHOLD:
            both_str = "; ".join(
                f"{r}/{b} (A {dA:+.1f}%/nA={nA:,}, B {dB:+.1f}%/nB={nB:,})"
                for (b, r), nA, dA, nB, dB in strong_both
            )
            emit(f"  → STAGE 1 SHIP CANDIDATE — Jaccard(A,B) = {jaccard:.2f} ≥ "
                 f"{JACCARD_STAGE1_THRESHOLD}, and {len(strong_both)} cell(s) win in")
            emit(f"    both halves independently: {both_str}")
            emit(f"    Recommended action: enable pr L2 (K=1, τ=12h) gate-ON-where-wins")
            emit(f"    with SKIP_TABLE excluding the pooled LOSS cells. Confirm with")
            emit(f"    ~1 week of Fitter agreement post-flip before removing skip.")
            emit(f"    Pooled WINS (context): {pooled_win_str}")
        elif strong_both:
            emit(f"  → MIXED — pooled shows {tally['WIN']} WIN cells, {len(strong_both)}")
            emit(f"    survive BOTH-WIN test but Jaccard(A,B) = {jaccard:.2f} < "
                 f"{JACCARD_STAGE1_THRESHOLD}. WIN set unstable across window halves.")
            emit(f"    Recommended action: shadow-wire (v0.6.389 already deployed);")
            emit(f"    re-cut on ~2 weeks of fresh data before ship decision.")
            emit(f"    Pooled WINS: {pooled_win_str}")
        else:
            emit(f"  → SHADOW-WIRE ONLY — pooled shows {tally['WIN']} WIN cells but")
            emit(f"    ZERO cells win in both halves independently. Single-window")
            emit(f"    artifact risk high.")
            emit(f"    Recommended action: shadow-wire (v0.6.389 already deployed);")
            emit(f"    re-cut on ~2 weeks of fresh data before any ship decision.")
            emit(f"    Pooled WINS: {pooled_win_str}")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
