"""Stage 0 — Does inter-model spread (ims) predict per-obs L1 SELECTOR winner
for field=h?

Setup: current live selector picks HRRR for h in essentially every cell
because HRRR-post-L4 crushes NBM-post-L3 on cell averages. But oracle gap
on h/7d is +2.18 MAE (45% of raw) — the gap comes from PER-OBS flips
where NBM happens to be closer to obs than HRRR on specific rows. Live
chooser captures only 20% of that (VC = 20%).

Question: does ims (= |forecast_l1 - forecast_raw_nbm| at issue time)
predict which model will win THIS obs, beyond what regime × lead-band
already tells us?

Method: per (regime, band), quartile-split by ims. In each quartile
compute:
  • hrrr_win_rate  = fraction of rows where |err_HRRR| < |err_NBM|
  • always_min_MAE = min(mean|err_HRRR|, mean|err_NBM|) — current-selector floor
  • per_obs_MAE   = mean min(|err_HRRR|, |err_NBM|) — per-obs oracle floor
  • gap = always_min - per_obs = MAE on the table per obs
  • MAE_shadow    = MAE if we pick per-quartile winner (still cell-average)
  • MAE_ims_pick  = MAE if we pick per-obs based on a decision rule keyed
                   on ims quartile (better than cell-average if hrrr_win_rate
                   varies materially by quartile)

Signal criterion: hrrr_win_rate varies ≥ 10pp across quartiles AND the
variation direction is halves-stable. If yes → ims carries per-obs
picking signal beyond regime × band.

Ship shape (if it clears Stage 0→1→2→gate): L1 selector grows a per-obs
feature layer. First implementation: pick_source_by_row(field, lead_h,
regime, ims_quintile) returns pick per row instead of per cell.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"
FIELD = sys.argv[1] if len(sys.argv) > 1 else "h"
BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N_BIN = 100
MIN_WIN_RATE_SPREAD = 0.10   # 10pp variation in hrrr_win_rate across quartiles
MIN_MAE_LIFT_PCT = 3.0        # 3% MAE lift over always-min to promote


def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def load_rows():
    with open(cached_path(PAIR_URL), "rb") as fh:
        for raw in fh:
            try: r = json.loads(raw)
            except Exception: continue
            if r.get("field") != FIELD: continue
            lead = r.get("lead_h")
            if lead is None: continue
            band = lead_band(int(lead))
            if not band: continue
            fc_l1, fc_nbm_raw = r.get("forecast_l1"), r.get("forecast_raw_nbm")
            err_l4, err_l3_nbm = r.get("error_l4"), r.get("error_l3_nbm")
            if None in (fc_l1, fc_nbm_raw, err_l4, err_l3_nbm): continue
            regime = (r.get("state_fc") or {}).get("regime_synoptic")
            if not regime: continue
            yield {
                "regime": regime, "band": band,
                "ims": abs(float(fc_l1) - float(fc_nbm_raw)),
                "eh": abs(float(err_l4)),
                "en": abs(float(err_l3_nbm)),
                "t": r.get("obs_time", ""),
            }


print(f"Loading pair-log for field={FIELD}...")
by_cell = defaultdict(list)
for r in load_rows():
    by_cell[(r["regime"], r["band"])].append(r)
print(f"  {len(by_cell)} (regime, band) cells\n")

# Quartile thresholds per cell (need 4× MIN_N_BIN to make quartiles usable)
quartiles = {}
for key, rows in by_cell.items():
    if len(rows) < 4 * MIN_N_BIN: continue
    vals = sorted(r["ims"] for r in rows)
    n = len(vals)
    quartiles[key] = (vals[n // 4], vals[n // 2], vals[3 * n // 4])


def qbin(ims, t):
    if ims <= t[0]: return "Q1"
    if ims <= t[1]: return "Q2"
    if ims <= t[2]: return "Q3"
    return "Q4"


def summarize(rows):
    """Return (n, hrrr_win_rate, mean_eh, mean_en, per_obs_mae) for a row set."""
    if not rows: return (0, 0.0, 0.0, 0.0, 0.0)
    n = len(rows)
    n_hrrr = sum(1 for r in rows if r["eh"] < r["en"])
    seh = sum(r["eh"] for r in rows)
    sen = sum(r["en"] for r in rows)
    sper = sum(min(r["eh"], r["en"]) for r in rows)
    return (n, n_hrrr / n, seh / n, sen / n, sper / n)


print("=" * 108)
print(f"h_l1_selector_ims_stage0 — per-obs winner signal in ims for field={FIELD}")
print("=" * 108)
print(f"{'regime':<14}{'band':<8}{'qbin':<5}{'n':>6}  {'H_win%':>7}  {'mae_H':>7}  {'mae_N':>7}  {'always_min':>10}  {'per_obs':>8}  {'gap%':>6}  {'shadow':>7}  half✓")
print("-" * 108)

promote_cells = []
for key in sorted(quartiles.keys()):
    regime, band = key
    rows = by_cell[key]
    rows.sort(key=lambda r: r["t"])
    mid = len(rows) // 2
    rows_A, rows_B = rows[:mid], rows[mid:]

    per_q = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    per_q_A = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    per_q_B = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    for r in rows: per_q[qbin(r["ims"], quartiles[key])].append(r)
    for r in rows_A: per_q_A[qbin(r["ims"], quartiles[key])].append(r)
    for r in rows_B: per_q_B[qbin(r["ims"], quartiles[key])].append(r)

    if not all(len(per_q[q]) >= MIN_N_BIN for q in per_q): continue

    stats_by_q = {q: summarize(per_q[q]) for q in per_q}
    stats_by_q_A = {q: summarize(per_q_A[q]) for q in per_q}
    stats_by_q_B = {q: summarize(per_q_B[q]) for q in per_q}

    # Aggregate per-cell numbers
    n_tot = sum(s[0] for s in stats_by_q.values())
    always_H_mae = sum(s[0] * s[2] for s in stats_by_q.values()) / n_tot
    always_N_mae = sum(s[0] * s[3] for s in stats_by_q.values()) / n_tot
    always_min_mae = min(always_H_mae, always_N_mae)
    per_obs_mae = sum(s[0] * s[4] for s in stats_by_q.values()) / n_tot
    gap_pct = (always_min_mae - per_obs_mae) / always_min_mae * 100

    # Shadow: pick per-quartile winner (H or N based on quartile's mean_eh vs mean_en)
    shadow_mae = 0.0
    for q, s in stats_by_q.items():
        n_q, _, mh, mn, _ = s
        shadow_mae += n_q * min(mh, mn)
    shadow_mae /= n_tot
    shadow_lift_pct = (always_min_mae - shadow_mae) / always_min_mae * 100

    # win-rate spread + halves stability of the ordering
    win_rates = [stats_by_q[q][1] for q in ("Q1", "Q2", "Q3", "Q4")]
    win_rates_A = [stats_by_q_A[q][1] for q in ("Q1", "Q2", "Q3", "Q4")]
    win_rates_B = [stats_by_q_B[q][1] for q in ("Q1", "Q2", "Q3", "Q4")]
    spread = max(win_rates) - min(win_rates)
    argmax_pool = win_rates.index(max(win_rates))
    argmax_A = win_rates_A.index(max(win_rates_A))
    argmax_B = win_rates_B.index(max(win_rates_B))
    halves_ok = argmax_A == argmax_B == argmax_pool
    halves_glyph = "✓" if halves_ok else "✗"

    for q in ("Q1", "Q2", "Q3", "Q4"):
        n_q, wr, mh, mn, po = stats_by_q[q]
        print(f"{regime:<14}{band:<8}{q:<5}{n_q:>6}  {wr*100:>6.1f}%  {mh:>7.3f}  {mn:>7.3f}", end="")
        if q == "Q1":
            print(f"  {always_min_mae:>10.3f}  {per_obs_mae:>8.3f}  {gap_pct:>5.1f}%  {shadow_mae:>7.3f}  {halves_glyph}")
        else:
            print()
    is_promote = spread >= MIN_WIN_RATE_SPREAD and halves_ok and shadow_lift_pct >= MIN_MAE_LIFT_PCT
    marker = "★ PROMOTE" if is_promote else ("~ signal but sub-gate" if spread >= MIN_WIN_RATE_SPREAD else "")
    if marker:
        print(f"  {marker}: win-rate spread={spread*100:.1f}pp  shadow_lift={shadow_lift_pct:+.2f}%  halves_ok={halves_ok}")
    if is_promote:
        promote_cells.append((regime, band, win_rates, shadow_lift_pct, gap_pct))
    print()

print("=" * 108)
if promote_cells:
    print(f"VERDICT: STAGE 0 PROMOTE — {len(promote_cells)} (regime, band) cell(s) show ims-conditioned")
    print(f"         per-obs winner signal with halves-stable ordering AND shadow MAE lift ≥ {MIN_MAE_LIFT_PCT}%.")
    print(f"         Advance to Stage 1: fit a per-obs decision rule and validate on held-out data.")
    for reg, band, wr, lift, gap in promote_cells:
        wr_str = "/".join(f"{w*100:.0f}%" for w in wr)
        print(f"           {reg:<14}{band:<8}  H-win by Q: {wr_str}  shadow_lift={lift:+.2f}%  per-obs gap={gap:.1f}%")
else:
    print("VERDICT: STAGE 0 HOLD — ims does not carry halves-stable per-obs picking signal for")
    print(f"         field={FIELD} at MIN_WIN_RATE_SPREAD={MIN_WIN_RATE_SPREAD*100:.0f}pp / MIN_MAE_LIFT_PCT={MIN_MAE_LIFT_PCT}%.")
    print(f"         Try a different per-obs axis (xr_q, cluster_spread, state_fc_obs) or a different field.")
print("=" * 108)
