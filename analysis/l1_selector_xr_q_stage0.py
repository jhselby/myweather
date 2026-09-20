"""Stage 0 — Does cross_run_spread (xr_q) predict per-obs L1 SELECTOR winner?

Sister script to h_l1_selector_ims_stage0.py. Same gate + shadow-lift math,
different per-obs axis: xr_spread = max(forecasts across runs for a given
(field, valid_time)) - min. Rationale (per 2026-09-19 finding): ims Stage 0
promoted 6 fields (ch/wg/cc/wd/h/dp) but HELD on sr/t/ws — signal exists on
sr in Stage 0 win-rate spreads (40-97pp) but not halves-stable on ims
quartile splits. Working hypothesis: sr/t/ws respond to day-to-day
cross-run uncertainty (captured by xr_q) rather than inter-model disagreement.

Method: two-pass over pair log.
  Pass 1 — group rows by (field, valid_time), compute xr_spread once per VT.
  Pass 2 — for each row, look up xr_spread by its valid_time and treat it as
           the per-obs axis. Quartile-split per (regime, band) as in ims stage0.

Field via argv[1] (default: sr). Same MIN_N_BIN=100, spread≥10pp, shadow
lift ≥ 3.0% halves-stable promote gate.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_URL = "https://data.wymancove.com/forecast_error_log_backstamped.jsonl"
FIELD = sys.argv[1] if len(sys.argv) > 1 else "sr"
BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_N_BIN = 100
MIN_WIN_RATE_SPREAD = 0.10
MIN_MAE_LIFT_PCT = 3.0
MIN_RUNS_PER_VT = 2  # need at least two runs to have a spread


def lead_band(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def load_pair_log():
    """One-shot iter over pair log; yield raw dicts filtered to FIELD."""
    with open(cached_path(PAIR_URL), "rb") as fh:
        for raw in fh:
            try: r = json.loads(raw)
            except Exception: continue
            if r.get("field") != FIELD: continue
            yield r


print(f"Loading pair-log for field={FIELD}...")

# Pass 1: gather forecasts per (valid_time) to compute xr_spread
fc_by_vt = defaultdict(list)   # vt -> list of forecasts across runs
rows_raw = []                   # keep the rows we care about
for r in load_pair_log():
    vt = r.get("valid_time")
    fc = r.get("forecast")
    if vt is None or fc is None: continue
    fc_by_vt[vt].append(float(fc))
    rows_raw.append(r)

vt_spread = {}
for vt, fcs in fc_by_vt.items():
    if len(fcs) < MIN_RUNS_PER_VT: continue
    vt_spread[vt] = max(fcs) - min(fcs)

print(f"  {len(rows_raw):,} rows scanned, {len(fc_by_vt):,} distinct VTs, "
      f"{len(vt_spread):,} VTs with ≥{MIN_RUNS_PER_VT} runs")

# Pass 2: build per-row records with xr_spread + errors
by_cell = defaultdict(list)
for r in rows_raw:
    vt = r.get("valid_time")
    xr = vt_spread.get(vt)
    if xr is None: continue
    lead = r.get("lead_h")
    if lead is None: continue
    band = lead_band(int(lead))
    if not band: continue
    err_l4, err_l3_nbm = r.get("error_l4"), r.get("error_l3_nbm")
    if err_l4 is None or err_l3_nbm is None: continue
    regime = (r.get("state_fc") or {}).get("regime_synoptic")
    if not regime: continue
    by_cell[(regime, band)].append({
        "xr": xr,
        "eh": abs(float(err_l4)),
        "en": abs(float(err_l3_nbm)),
        "t": r.get("obs_time", ""),
    })

print(f"  {len(by_cell)} (regime, band) cells\n")

quartiles = {}
for key, rows in by_cell.items():
    if len(rows) < 4 * MIN_N_BIN: continue
    vals = sorted(r["xr"] for r in rows)
    n = len(vals)
    quartiles[key] = (vals[n // 4], vals[n // 2], vals[3 * n // 4])


def qbin(xr, t):
    if xr <= t[0]: return "Q1"
    if xr <= t[1]: return "Q2"
    if xr <= t[2]: return "Q3"
    return "Q4"


def summarize(rows):
    if not rows: return (0, 0.0, 0.0, 0.0, 0.0)
    n = len(rows)
    n_hrrr = sum(1 for r in rows if r["eh"] < r["en"])
    seh = sum(r["eh"] for r in rows)
    sen = sum(r["en"] for r in rows)
    sper = sum(min(r["eh"], r["en"]) for r in rows)
    return (n, n_hrrr / n, seh / n, sen / n, sper / n)


print("=" * 108)
print(f"l1_selector_xr_q_stage0 — per-obs winner signal in xr_q for field={FIELD}")
print("=" * 108)
print(f"{'regime':<14}{'band':<8}{'qbin':<5}{'n':>6}  {'H_win%':>7}  {'mae_H':>7}  {'mae_N':>7}  {'always_min':>10}  {'per_obs':>8}  {'gap%':>6}  {'shadow':>7}  half✓")
print("-" * 108)

promote_cells = []
sub_gate_cells = []
for key in sorted(quartiles.keys()):
    regime, band = key
    rows = by_cell[key]
    rows.sort(key=lambda r: r["t"])
    mid = len(rows) // 2
    rows_A, rows_B = rows[:mid], rows[mid:]

    per_q = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    per_q_A = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    per_q_B = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    for r in rows: per_q[qbin(r["xr"], quartiles[key])].append(r)
    for r in rows_A: per_q_A[qbin(r["xr"], quartiles[key])].append(r)
    for r in rows_B: per_q_B[qbin(r["xr"], quartiles[key])].append(r)

    if not all(len(per_q[q]) >= MIN_N_BIN for q in per_q): continue

    stats_by_q = {q: summarize(per_q[q]) for q in per_q}
    stats_by_q_A = {q: summarize(per_q_A[q]) for q in per_q}
    stats_by_q_B = {q: summarize(per_q_B[q]) for q in per_q}

    n_tot = sum(s[0] for s in stats_by_q.values())
    always_H_mae = sum(s[0] * s[2] for s in stats_by_q.values()) / n_tot
    always_N_mae = sum(s[0] * s[3] for s in stats_by_q.values()) / n_tot
    always_min_mae = min(always_H_mae, always_N_mae)
    per_obs_mae = sum(s[0] * s[4] for s in stats_by_q.values()) / n_tot
    gap_pct = (always_min_mae - per_obs_mae) / always_min_mae * 100 if always_min_mae > 0 else 0.0

    shadow_mae = 0.0
    for q, s in stats_by_q.items():
        n_q, _, mh, mn, _ = s
        shadow_mae += n_q * min(mh, mn)
    shadow_mae /= n_tot
    shadow_lift_pct = (always_min_mae - shadow_mae) / always_min_mae * 100 if always_min_mae > 0 else 0.0

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
    elif spread >= MIN_WIN_RATE_SPREAD:
        sub_gate_cells.append((regime, band, win_rates, shadow_lift_pct, gap_pct, halves_ok))
    print()

print("=" * 108)
if promote_cells:
    print(f"VERDICT: STAGE 0 PROMOTE — {len(promote_cells)} (regime, band) cell(s) show xr_q-conditioned")
    print(f"         per-obs winner signal with halves-stable ordering AND shadow MAE lift ≥ {MIN_MAE_LIFT_PCT}%.")
    print(f"         Advance to Stage 1: fit a per-obs decision rule and validate on held-out data.")
    for reg, band, wr, lift, gap in promote_cells:
        wr_str = "/".join(f"{w*100:.0f}%" for w in wr)
        print(f"           {reg:<14}{band:<8}  H-win by Q: {wr_str}  shadow_lift={lift:+.2f}%  per-obs gap={gap:.1f}%")
else:
    print("VERDICT: STAGE 0 HOLD — xr_q does not carry halves-stable per-obs picking signal for")
    print(f"         field={FIELD} at MIN_WIN_RATE_SPREAD={MIN_WIN_RATE_SPREAD*100:.0f}pp / MIN_MAE_LIFT_PCT={MIN_MAE_LIFT_PCT}%.")
if sub_gate_cells:
    print(f"         Sub-gate cells (spread ≥ {MIN_WIN_RATE_SPREAD*100:.0f}pp but failed halves or shadow lift):")
    for reg, band, wr, lift, gap, halves in sub_gate_cells:
        wr_str = "/".join(f"{w*100:.0f}%" for w in wr)
        print(f"           {reg:<14}{band:<8}  H-win by Q: {wr_str}  shadow_lift={lift:+.2f}%  gap={gap:.1f}%  halves={'✓' if halves else '✗'}")
print("=" * 108)
