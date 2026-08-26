#!/usr/bin/env python3
"""Per-field two-step scoring (2026-08-19).

Answers two questions per field, cleanly separated:

  1. SELECTION LIFT — did picking between raw HRRR and raw NBM buy us
     anything vs being stuck on either one alone?
       sel_vs_hrrr_pct = (raw_HRRR_MAE − L1_selected_MAE) / raw_HRRR_MAE × 100
       sel_vs_nbm_pct  = (raw_NBM_MAE  − L1_selected_MAE) / raw_NBM_MAE  × 100

  2. CORRECTION LIFT — how much did the correction stack (L2 / L3 / L4 /
     gates) add on top of L1?
       corr_vs_l1_pct = (L1_selected_MAE − Prod_MAE) / L1_selected_MAE × 100

Plus a headline number that ties them together:

    total_vs_best_raw_pct = (best_raw_MAE − Prod_MAE) / best_raw_MAE × 100
    where best_raw = argmin(raw_HRRR, raw_NBM) per field.

Two windows: 7-day rolling and 24-hour rolling.

L1_selected residual: for each pair-log row, look up the selector table at
(field, band). If it picks "nbm", use error_l3_nbm (NBM Prod residual —
the selector compares Prod-vs-Prod, not raw-vs-raw). If "hrrr" or fall-
through, use error_{deepest_applied_hrrr_layer}. Falls back to raw HRRR
(error_l1) when the deepest-layer error is missing.

Warmup caveat: until v0.6.440-era pair-log rows accumulate + the selector
table actually flips a cell to NBM (~09-17), L1_selected == HRRR-Prod
everywhere. sel_vs_hrrr will show ~0% and sel_vs_nbm will show whatever
HRRR-Prod-vs-NBM-Prod is. That is the honest signal.

Runtime:
    python3 -m analysis.per_field_scoring
    MYWEATHER_REFRESH=1 python3 -m analysis.per_field_scoring
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path
from analysis._output import out as _out

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
SELECTOR_TABLE_PATH = (
    Path(__file__).resolve().parent.parent
    / "weather_collector" / "data" / "l1_selector_table_curated.json"
)
OUT_JSON = _out("per_field_scoring.json")

FIELDS = ["t", "h", "dp", "ws", "wg", "wd", "cc", "cl", "cm", "ch", "sr", "pp", "pa", "pr"]

# Fields with a full NBM cascade. Others have no NBM comparison and
# sel_vs_nbm_pct is None for them.
NBM_SCOPE = {"t", "ws", "wg", "wd", "h", "ch", "cc", "sr", "dp"}

# v0.6.482 — fields where MAE-ratio metrics like prod_trend_pct produce
# meaningless numbers because the underlying magnitude is near-zero (pa,
# inches of precip) or the metric isn't MAE at all (pp, Brier score).
# These fields get their trend nulled so tile medians/means aren't
# dominated by ratio noise.
TREND_EXCLUDE_FIELDS = {"pa", "pp"}

# Minimum paired-pool size for prod_trend_pct to be published. Below this
# the prior-window MAE is one or two rows' worth of error, and the ratio
# is dominated by whichever row lands there. Frontend then skips nulls
# in its median/mean aggregations.
MIN_N_TREND = 50

BANDS = [(0, 6, "0-5"), (6, 12, "6-11"), (12, 24, "12-23"), (24, 48, "24-47")]
WINDOWS = [("7d", 7), ("24h", 1)]

# HRRR-side layer priority for extracting the "HRRR Prod" residual per row.
# Deepest applied layer wins (matches selector fitter's convention).
HRRR_PROD_KEYS = [
    "error_dpbp", "error_wsbp", "error_wdp", "error_clp", "error_chp",
    "error_l6", "error_l5", "error_l4", "error_l3", "error_l2", "error_l1",
]

# NBM-side layer priority for extracting the "NBM Prod" residual per row.
# Deepest available layer wins. Mirrors HRRR order (specialists → base cascade).
NBM_PROD_KEYS = [
    "error_chp_nbm", "error_wdp_nbm",
    "error_l6_nbm", "error_l5_nbm", "error_l4_nbm", "error_l3_nbm", "error_l2_nbm",
    "error_raw_nbm",
]


def _band_for(lead_h):
    if lead_h is None:
        return None
    lh = int(lead_h)
    for lo, hi, name in BANDS:
        if lo <= lh < hi:
            return name
    return None


def _load_selector_table():
    """Returns {field: {band: 'hrrr'|'nbm'}}. Missing cells → 'hrrr' fallback."""
    try:
        with open(SELECTOR_TABLE_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    table = data.get("table") or {}
    parsed = {}
    for field, cells in table.items():
        parsed[field] = {band: (cell.get("source") or "hrrr")
                         for band, cell in (cells or {}).items()}
    return parsed


def _hrrr_prod_error(row):
    """Deepest HRRR-side layer residual on this row (signed). Falls through
    to raw HRRR (error_l1). Returns None if nothing is stamped."""
    for k in HRRR_PROD_KEYS:
        v = row.get(k)
        if v is not None:
            return v
    return None


def _nbm_prod_error(row):
    """Deepest NBM-side layer residual on this row (signed). Falls through
    to raw NBM (error_raw_nbm). Returns None if nothing is stamped."""
    for k in NBM_PROD_KEYS:
        v = row.get(k)
        if v is not None:
            return v
    return None


def _prod_error(row):
    """Whatever the collector actually shipped for user-visible Prod on this
    row — error_{applied_layer}, or top-level error as fallback (pre-v0.6.269
    rows)."""
    applied = row.get("applied_layer")
    if applied:
        v = row.get(f"error_{applied}")
        if v is not None:
            return v
    return row.get("error")


def _selected_l1_error(row, band_picks):
    """L1_selected residual — the error a user would get if they saw only the
    selector's chosen source, WITHOUT the local correction stack on top.

    Wait — read carefully. "L1_selected" here means "the output of the
    selector's pick BEFORE our local correction stack applies its final
    layers." For NBM the closest thing is NBM's L3 output (nbm-side Prod).
    For HRRR the closest thing is HRRR raw (error_l1) — everything above
    that is our local correction stack.

    So:
      selector picks "nbm" → error_l3_nbm (NBM's own bias-corrected output,
                             the thing we'd ship if we did no further work)
      selector picks "hrrr" or falls through → error_l1 (raw HRRR — our
                             correction stack builds on top of this)

    This makes corr_vs_l1_pct honestly measure "what did WE add on top of
    what the selector handed us."
    """
    field = row.get("field")
    band = _band_for(row.get("lead_h"))
    pick = "hrrr"
    if field in band_picks and band in band_picks[field]:
        pick = band_picks[field][band]
    if pick == "nbm":
        v = row.get("error_l3_nbm")
        if v is not None:
            return v, "nbm"
        # NBM pick but no NBM prod stamped this row → fall through to HRRR
        v = row.get("error_l1")
        return (v, "hrrr_fallback") if v is not None else (None, "na")
    v = row.get("error_l1")
    return (v, "hrrr") if v is not None else (None, "na")


def _new_bucket():
    return {
        "hrrr_raw":     [0.0, 0],
        "nbm_raw":      [0.0, 0],
        # Per-row oracle baseline: min(|error_hrrr_raw|, |error_nbm_raw|) per
        # row when both exist; the one that exists otherwise. Aggregating this
        # per-row-winner is the honest Total Lift baseline (v0.6.477).
        # Pooled min(hrrr_pooled, nbm_pooled) was too generous — it credited
        # us for beating whichever raw source wins a whole day, when an oracle
        # could pick the winner per lead-hour for free.
        "best_raw_row": [0.0, 0],
        "l1_selected":  [0.0, 0],
        "prod":         [0.0, 0],
        "hrrr_prod":    [0.0, 0],
        "nbm_prod":     [0.0, 0],
        "chosen_prod":  [0.0, 0],
        "alt_prod":     [0.0, 0],
        # v0.6.492 — paired per-cascade Prod buckets for the coach's table.
        # Populated only inside the pool_ok intersection so HRRR Pipeline
        # Skill / NBM Pipeline Skill / Hit Rate / Value Captured / Total
        # Lift all describe the same row set. The unpaired `hrrr_prod` /
        # `nbm_prod` buckets stay for other consumers (they answer the
        # "what would Prod be if we always picked HRRR/NBM at field level"
        # question, unconstrained by whether the peer cascade was
        # stampable — different question, different pool).
        "hrrr_prod_paired": [0.0, 0],
        "nbm_prod_paired":  [0.0, 0],
        # v0.6.487 — wider prod pool for Prod Trend. The `prod` and
        # `prod_prior` buckets above are gated by the same pool intersection
        # used for Total Lift/Chooser Lift (nbm_raw required on NBM-scope
        # rows) so those metrics stay internally consistent. Prod Trend
        # measures our stack's own MAE across time and doesn't need the
        # intersection to be interpretable — using the intersected pool
        # starves the 7d prior window (nbm_raw backstamp thins out that
        # far back) and leaves us with 0-3 rows per NBM-scope field.
        # `prod_wider` / `prod_prior_wider` require only `e_prod`.
        "prod_wider":       [0.0, 0],
        "prod_prior_wider": [0.0, 0],
        # Per-row oracle Prod (v0.6.481): min(|chosen_prod_err|, |alt_prod_err|)
        # per row over the paired chosen/alt pool. Feeds Value Captured.
        "oracle_prod":  [0.0, 0],
        # Selector Hit Rate (v0.6.481): count of paired rows where the
        # selector's chosen cascade Prod residual ≤ the alternative
        # cascade's. Denominator is chosen_prod's n. Ties count as hits
        # (the router picked something that wasn't worse).
        "hits":         0,
        "prod_prior":   [0.0, 0],
        "selector_picks": {"hrrr": 0, "nbm": 0, "hrrr_fallback": 0, "na": 0},
        # v0.6.493 — per-band buckets for Notable Calls + High-Conf tiles.
        # Total Lift per (field, band) uses the Public Baseline rule
        # (v0.6.478): NBM raw for NBM-scope, HRRR raw for HRRR-only. Both
        # raws accumulated per band; renderer picks by scope. Populated
        # inside the pool_ok block so it inherits Total Lift's pool
        # discipline.
        "per_band": {name: {"hrrr_raw": [0.0, 0], "nbm_raw": [0.0, 0], "prod": [0.0, 0]}
                     for _lo, _hi, name in BANDS},
    }


def _new_bucket_halves():
    """Same shape as _new_bucket but for one half of the window (for
    halves-agree stability check)."""
    return {
        "hrrr_raw":     [0.0, 0],
        "nbm_raw":      [0.0, 0],
        "best_raw_row": [0.0, 0],
        "l1_selected":  [0.0, 0],
        "prod":         [0.0, 0],
        "chosen_prod":  [0.0, 0],
        "alt_prod":     [0.0, 0],
    }


def _accumulate(pair_log_path, window_start, halves_midpoint, prior_start, band_picks):
    """window_start = start of current window. prior_start = start of the
    equal-length window preceding it (used for Prod trend). Rows in
    [prior_start, window_start) only contribute to prod_prior.

    v0.6.468 — value-chain pool intersection. For NBM-scope fields, a row
    contributes to hrrr_raw / nbm_raw / l1_selected / prod ONLY when all four
    residuals exist on that row. This makes the pool consistent across the
    three headline tiles so best_raw, L1, and Prod MAEs describe the same
    obs set and (1-Total) ≈ (1-Chooser)(1-Local) is meaningful.

    Non-NBM-scope fields: no NBM raw baseline exists, so the intersection
    reduces to requiring hrrr_raw + l1_selected + prod. best_raw = MAE_HRRR
    for those fields (they can't enter the value-chain tiles anyway; the
    tile renderer restricts to NBM-scope).

    Diagnostic buckets (hrrr_prod / nbm_prod / chosen_prod / alt_prod /
    prod_prior / selector_picks) stay on their prior pool discipline — they
    answer different questions and pairing rules differ per bucket.
    """
    acc = {f: _new_bucket() for f in FIELDS}
    halves = {f: {"a": _new_bucket_halves(), "b": _new_bucket_halves()} for f in FIELDS}
    with open(pair_log_path) as fin:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            field = row.get("field")
            if field not in acc:
                continue
            obs_time = row.get("obs_time", "")
            if obs_time < prior_start:
                continue
            in_current = obs_time >= window_start
            # Compute residuals + pool_ok up-front so prior-window uses the
            # SAME intersection rule as current-window. Without this, Prod
            # Trend compares a pool-intersected current-window `prod` to an
            # unfiltered `prod_prior` — apples to oranges (v0.6.468 shipped
            # this asymmetry, v0.6.470 fixes it).
            e_hrrr = row.get("error_l1")
            e_nbm = row.get("error_raw_nbm")
            e_sel, pick = _selected_l1_error(row, band_picks)
            e_prod = _prod_error(row)
            in_nbm_scope = field in NBM_SCOPE
            if in_nbm_scope:
                pool_ok = (e_hrrr is not None and e_nbm is not None
                           and e_sel is not None and e_prod is not None)
            else:
                pool_ok = (e_hrrr is not None and e_sel is not None
                           and e_prod is not None)

            if not in_current:
                # Prior-window row: contribute to prod_prior (intersected —
                # keeps parity with the current-window intersected `prod`
                # for internal consistency) AND prod_prior_wider (any row
                # with a Prod stamp — feeds prod_trend_pct on a pool wide
                # enough to survive the 7d backstamp-thinning).
                if pool_ok:
                    v = abs(float(e_prod))
                    acc[field]["prod_prior"][0] += v
                    acc[field]["prod_prior"][1] += 1
                if e_prod is not None:
                    vw = abs(float(e_prod))
                    acc[field]["prod_prior_wider"][0] += vw
                    acc[field]["prod_prior_wider"][1] += 1
                continue
            b = acc[field]
            half = halves[field]["b" if obs_time >= halves_midpoint else "a"]
            b["selector_picks"][pick] = b["selector_picks"].get(pick, 0) + 1

            # Compute per-cascade Prod residuals up-front — used both by
            # unpaired buckets below AND by paired buckets inside pool_ok.
            e_hp = _hrrr_prod_error(row)
            e_np = _nbm_prod_error(row)

            if pool_ok:
                # v0.6.492 — paired per-cascade Prod, gated on the same
                # pool intersection Total Lift uses. Keeps the coach's
                # table on one consistent row set.
                if e_hp is not None:
                    v = abs(float(e_hp))
                    b["hrrr_prod_paired"][0] += v
                    b["hrrr_prod_paired"][1] += 1
                if e_np is not None:
                    v = abs(float(e_np))
                    b["nbm_prod_paired"][0] += v
                    b["nbm_prod_paired"][1] += 1
                vh = abs(float(e_hrrr))
                b["hrrr_raw"][0] += vh; b["hrrr_raw"][1] += 1
                half["hrrr_raw"][0] += vh; half["hrrr_raw"][1] += 1
                if e_nbm is not None:
                    vn = abs(float(e_nbm))
                    b["nbm_raw"][0] += vn; b["nbm_raw"][1] += 1
                    half["nbm_raw"][0] += vn; half["nbm_raw"][1] += 1
                    # Per-row oracle baseline (v0.6.477): min of the two raws
                    # on this row. Aggregating this vs pooled Prod is the
                    # honest headline — Total Lift can no longer earn credit
                    # from a raw source that only wins at some leads.
                    br = min(vh, vn)
                else:
                    br = vh
                b["best_raw_row"][0] += br; b["best_raw_row"][1] += 1
                half["best_raw_row"][0] += br; half["best_raw_row"][1] += 1
                vs = abs(float(e_sel))
                b["l1_selected"][0] += vs; b["l1_selected"][1] += 1
                half["l1_selected"][0] += vs; half["l1_selected"][1] += 1
                vp = abs(float(e_prod))
                b["prod"][0] += vp; b["prod"][1] += 1
                half["prod"][0] += vp; half["prod"][1] += 1
                # v0.6.493 — per-band Total Lift feed. Accumulate both raws
                # so the renderer can apply the Public Baseline rule per
                # scope. wd's raws are circular-degree MAE (already |·|).
                band = _band_for(row.get("lead_h"))
                if band is not None:
                    pb = b["per_band"].get(band)
                    if pb is not None:
                        pb["hrrr_raw"][0] += vh; pb["hrrr_raw"][1] += 1
                        if e_nbm is not None:
                            pb["nbm_raw"][0] += vn; pb["nbm_raw"][1] += 1
                        pb["prod"][0] += vp; pb["prod"][1] += 1

            # v0.6.487 — current-window prod on the wider pool (any row
            # with a Prod stamp, no intersection requirement). Paired with
            # `prod_prior_wider` above to compute prod_trend_pct.
            if e_prod is not None:
                vw = abs(float(e_prod))
                b["prod_wider"][0] += vw
                b["prod_wider"][1] += 1

            # Per-cascade Prod residuals. Pooled unconditionally so we can
            # answer "what would Prod be if we always picked HRRR / always
            # NBM" at the field level. e_hp/e_np already computed above
            # (needed inside pool_ok for paired buckets).
            if e_hp is not None:
                v = abs(float(e_hp))
                b["hrrr_prod"][0] += v; b["hrrr_prod"][1] += 1
            if e_np is not None:
                v = abs(float(e_np))
                b["nbm_prod"][0] += v; b["nbm_prod"][1] += 1

            # Chosen vs alternative Prod: paired per row using the selector's
            # actual pick. This is the honest "did the chooser pick the better
            # cascade" measurement — Prod-vs-Prod per v0.6.440.
            # v0.6.492 — gate on pool_ok so Hit Rate + Value Captured live
            # on the same row set as Total Lift + paired Pipeline Skills.
            if pool_ok and e_hp is not None and e_np is not None:
                hp = abs(float(e_hp)); np_ = abs(float(e_np))
                if pick == "nbm":
                    chosen, alt = np_, hp
                else:  # "hrrr", "hrrr_fallback", or "na" → HRRR is what shipped
                    chosen, alt = hp, np_
                b["chosen_prod"][0] += chosen; b["chosen_prod"][1] += 1
                b["alt_prod"][0] += alt;       b["alt_prod"][1] += 1
                half["chosen_prod"][0] += chosen; half["chosen_prod"][1] += 1
                half["alt_prod"][0] += alt;       half["alt_prod"][1] += 1
                # v0.6.481: per-row oracle + selector hit count on the
                # paired pool. Oracle picks the lower cascade every row.
                orc = chosen if chosen <= alt else alt
                b["oracle_prod"][0] += orc; b["oracle_prod"][1] += 1
                if chosen <= alt:
                    b["hits"] += 1
    return acc, halves


def _mean(sum_n):
    s, n = sum_n
    return (s / n) if n > 0 else None


def _lift_pct(baseline, current):
    """(baseline − current) / baseline × 100. Positive = current is better."""
    if baseline is None or current is None or baseline <= 0:
        return None
    return 100.0 * (baseline - current) / baseline


def _compute_field(field, buckets, halves):
    hrrr = _mean(buckets["hrrr_raw"])
    nbm  = _mean(buckets["nbm_raw"])
    sel  = _mean(buckets["l1_selected"])
    prod = _mean(buckets["prod"])
    hrrr_prod = _mean(buckets["hrrr_prod"])
    nbm_prod  = _mean(buckets["nbm_prod"])
    # v0.6.492 — paired Prod means (pool_ok pool). Feed the coach's table's
    # Pipeline Skill columns so all four columns describe the same row set.
    hrrr_prod_paired = _mean(buckets["hrrr_prod_paired"])
    nbm_prod_paired  = _mean(buckets["nbm_prod_paired"])
    chosen_prod = _mean(buckets["chosen_prod"])
    alt_prod    = _mean(buckets["alt_prod"])
    prod_prior  = _mean(buckets["prod_prior"])

    in_nbm_scope = field in NBM_SCOPE

    # Best raw = "what the regular user's weather app already shows them"
    # (v0.6.478). For NBM-scope fields → NBM raw (NBM is the NWS backbone
    # and effectively the default single-source for iPhone Weather /
    # weather.gov / vendor consumer displays). For HRRR-only fields
    # (cl/cm/pp/pa/pr — NBM doesn't publish) → HRRR raw.
    #
    # Prior baselines this replaces:
    #   pre-v0.6.477: pooled min(hrrr_mae, nbm_mae) — too generous, gave
    #     us credit for beating whichever raw wins on average.
    #   v0.6.477: per-row oracle min(|error_hrrr_row|, |error_nbm_row|) —
    #     too strict; represents a picker no human has (nobody swaps
    #     hrrr/nbm per lead-hour dynamically).
    if in_nbm_scope and nbm is not None:
        best_raw, best_raw_src = nbm, "nbm (user default)"
    elif hrrr is not None:
        best_raw, best_raw_src = hrrr, "hrrr"
    elif nbm is not None:
        best_raw, best_raw_src = nbm, "nbm"
    else:
        best_raw, best_raw_src = None, "na"

    # Halves-agree per metric: both halves show the SAME SIGN of lift
    # (both positive or both negative). None when either half is thin.
    def _half_lift(side, baseline_key, current_key):
        base = _mean(halves[side][baseline_key])
        curr = _mean(halves[side][current_key])
        return _lift_pct(base, curr)
    def _agree(a_val, b_val):
        if a_val is None or b_val is None:
            return None
        return (a_val >= 0 and b_val >= 0) or (a_val < 0 and b_val < 0)
    sel_h_a  = _half_lift("a", "hrrr_raw", "l1_selected"); sel_h_b  = _half_lift("b", "hrrr_raw", "l1_selected")
    sel_n_a  = _half_lift("a", "nbm_raw",  "l1_selected"); sel_n_b  = _half_lift("b", "nbm_raw",  "l1_selected")
    corr_a   = _half_lift("a", "l1_selected", "prod");     corr_b   = _half_lift("b", "l1_selected", "prod")
    chooser_prod_a = _half_lift("a", "alt_prod", "chosen_prod")
    chooser_prod_b = _half_lift("b", "alt_prod", "chosen_prod")
    def _best_half(side):
        # v0.6.478: matches _compute_field — NBM raw where in scope, HRRR
        # raw otherwise. "What the regular weather app shows the user."
        if in_nbm_scope:
            v = _mean(halves[side]["nbm_raw"])
            if v is not None:
                return v
        return _mean(halves[side]["hrrr_raw"])
    total_a_base = _best_half("a"); total_b_base = _best_half("b")
    total_a = _lift_pct(total_a_base, _mean(halves["a"]["prod"]))
    total_b = _lift_pct(total_b_base, _mean(halves["b"]["prod"]))

    # Chooser lift Prod-vs-Prod (v0.6.440 rule):
    # positive = chosen cascade Prod beats alternative cascade Prod.
    chooser_vs_prod_pct = _lift_pct(alt_prod, chosen_prod)

    # Weekly Prod trend: current-window Prod vs prior-window Prod. No external
    # anchor. Positive = we improved vs the same-length window preceding this
    # one. This is the "am I doing my job well" signal — see [[08-22-session]].
    # v0.6.487 — Prod Trend uses the wider prod-only pool (both windows).
    # The intersected pool (used by Total Lift / Chooser Lift / Pipeline
    # Lift) is starved at 7d for NBM-scope fields — nbm_raw backstamp
    # thins out, leaving 0-3 rows per prior window. Prod Trend doesn't
    # need the intersection to be interpretable (it's Prod-vs-Prod on our
    # own stack across time), so it gets its own pool.
    prod_wider       = _mean(buckets["prod_wider"])
    prod_prior_wider = _mean(buckets["prod_prior_wider"])
    prod_trend_pct = _lift_pct(prod_prior_wider, prod_wider)
    # v0.6.482 gate carried forward — suppress when the wider prior pool
    # is still thin (belt and suspenders), or when the field is on the
    # trend-exclude list (pa near-zero magnitude; pp Brier-scored).
    n_prior_wider = buckets["prod_prior_wider"][1]
    if field in TREND_EXCLUDE_FIELDS or n_prior_wider < MIN_N_TREND:
        prod_trend_pct = None

    # v0.6.481 — Selector Hit Rate + Value Captured (both diagnostic,
    # NBM-scope only; null for HRRR-only fields where there's no alt
    # cascade to compare against). Both computed on the paired
    # chosen_prod / alt_prod pool.
    oracle_prod = _mean(buckets["oracle_prod"])
    n_paired = buckets["chosen_prod"][1]
    if in_nbm_scope and n_paired > 0:
        hit_rate_pct = 100.0 * buckets["hits"] / n_paired
    else:
        hit_rate_pct = None
    # Value Captured = (alt − chosen) / (alt − oracle) × 100. How much of
    # the routing gain the oracle could have captured did the selector
    # actually capture. 100% = perfect picker; 0% = every pick was a wash;
    # negative = anti-selected. Undefined when the pool is empty or when
    # oracle == alt (no routing gain available — a pure tie window).
    if (in_nbm_scope and chosen_prod is not None and alt_prod is not None
            and oracle_prod is not None and (alt_prod - oracle_prod) > 0):
        value_captured_pct = 100.0 * (alt_prod - chosen_prod) / (alt_prod - oracle_prod)
    else:
        value_captured_pct = None

    return {
        "hrrr_raw_mae":  round(hrrr, 3) if hrrr is not None else None,
        "nbm_raw_mae":   round(nbm, 3)  if nbm  is not None else None,
        "l1_selected_mae": round(sel, 3) if sel is not None else None,
        "prod_mae":      round(prod, 3) if prod is not None else None,
        "hrrr_prod_mae": round(hrrr_prod, 3) if hrrr_prod is not None else None,
        "nbm_prod_mae":  round(nbm_prod, 3)  if nbm_prod  is not None else None,
        # v0.6.492 — paired-pool per-cascade Prod (matches Total Lift's pool).
        # Coach's table reads these; unpaired *_prod_mae stays for consumers
        # that want the intrinsic per-cascade rollup.
        "hrrr_prod_paired_mae": round(hrrr_prod_paired, 3) if hrrr_prod_paired is not None else None,
        "nbm_prod_paired_mae":  round(nbm_prod_paired, 3)  if nbm_prod_paired  is not None else None,
        "n_hrrr_prod_paired":   buckets["hrrr_prod_paired"][1],
        "n_nbm_prod_paired":    buckets["nbm_prod_paired"][1],
        # Pipeline Skill lifts computed on the paired pool: paired-Prod vs
        # pool_ok-raw. Positive = the cascade's corrections lift its own raw.
        "hrrr_pipeline_skill_paired_pct": (round(_lift_pct(hrrr, hrrr_prod_paired), 2)
                                            if _lift_pct(hrrr, hrrr_prod_paired) is not None else None),
        "nbm_pipeline_skill_paired_pct":  (round(_lift_pct(nbm, nbm_prod_paired), 2)
                                            if (in_nbm_scope and _lift_pct(nbm, nbm_prod_paired) is not None) else None),
        "chosen_prod_mae": round(chosen_prod, 3) if chosen_prod is not None else None,
        "alt_prod_mae":  round(alt_prod, 3) if alt_prod is not None else None,
        "chooser_vs_prod_pct": round(chooser_vs_prod_pct, 2) if chooser_vs_prod_pct is not None else None,
        "n_chooser_prod_paired": buckets["chosen_prod"][1],
        "oracle_prod_mae": round(oracle_prod, 3) if oracle_prod is not None else None,
        "hit_rate_pct":    round(hit_rate_pct, 2) if hit_rate_pct is not None else None,
        "value_captured_pct": round(value_captured_pct, 2) if value_captured_pct is not None else None,
        "prod_prior_mae": round(prod_prior, 3) if prod_prior is not None else None,
        "n_prod_prior":   buckets["prod_prior"][1],
        "prod_trend_pct": round(prod_trend_pct, 2) if prod_trend_pct is not None else None,
        # v0.6.487 — wider-pool numbers Prod Trend is actually computed from.
        "prod_wider_mae":       round(prod_wider, 3) if prod_wider is not None else None,
        "prod_prior_wider_mae": round(prod_prior_wider, 3) if prod_prior_wider is not None else None,
        "n_prod_wider":         buckets["prod_wider"][1],
        "n_prod_prior_wider":   buckets["prod_prior_wider"][1],
        "best_raw_mae":  round(best_raw, 3) if best_raw is not None else None,
        "best_raw_source": best_raw_src,
        "in_nbm_scope":  in_nbm_scope,
        # Step 1: selection lift
        "sel_vs_hrrr_pct": round(_lift_pct(hrrr, sel), 2) if _lift_pct(hrrr, sel) is not None else None,
        "sel_vs_nbm_pct":  (round(_lift_pct(nbm, sel), 2)
                             if (in_nbm_scope and _lift_pct(nbm, sel) is not None) else None),
        # Step 2: correction lift (Prod vs L1_selected)
        "corr_vs_l1_pct": round(_lift_pct(sel, prod), 2) if _lift_pct(sel, prod) is not None else None,
        # Headline: total pipeline lift (Prod vs best raw)
        "total_vs_best_raw_pct": (round(_lift_pct(best_raw, prod), 2)
                                   if _lift_pct(best_raw, prod) is not None else None),
        "n_hrrr":         buckets["hrrr_raw"][1],
        "n_nbm":          buckets["nbm_raw"][1],
        "n_l1_selected":  buckets["l1_selected"][1],
        "n_prod":         buckets["prod"][1],
        "selector_picks": dict(buckets["selector_picks"]),
        # v0.6.493 — per-band Total Lift for Notable Calls + High-Conf tiles.
        # Baseline rule mirrors the field-level Public Baseline (v0.6.478):
        # NBM raw for NBM-scope; HRRR raw for HRRR-only. dp + cc excluded
        # at the frontend renderer per DERIVED_EXCLUDE / LIFT_SCOPE rules.
        "per_band": {
            band: (lambda pb: {
                "total_lift_pct": (
                    round(_lift_pct(
                        _mean(pb["nbm_raw"]) if in_nbm_scope and _mean(pb["nbm_raw"]) is not None
                        else _mean(pb["hrrr_raw"]),
                        _mean(pb["prod"])
                    ), 2)
                    if _lift_pct(
                        _mean(pb["nbm_raw"]) if in_nbm_scope and _mean(pb["nbm_raw"]) is not None
                        else _mean(pb["hrrr_raw"]),
                        _mean(pb["prod"])
                    ) is not None else None
                ),
                "n": pb["prod"][1],
                "baseline_mae": (
                    round(
                        _mean(pb["nbm_raw"]) if in_nbm_scope and _mean(pb["nbm_raw"]) is not None
                        else _mean(pb["hrrr_raw"]), 3
                    ) if (
                        (_mean(pb["nbm_raw"]) if in_nbm_scope else _mean(pb["hrrr_raw"])) is not None
                    ) else None
                ),
                "prod_mae": round(_mean(pb["prod"]), 3) if _mean(pb["prod"]) is not None else None,
                "baseline_src": "nbm" if in_nbm_scope else "hrrr",
            })(buckets["per_band"][band])
            for band in buckets["per_band"]
        },
        "halves_agree": {
            "sel_vs_hrrr": _agree(sel_h_a, sel_h_b),
            "sel_vs_nbm":  _agree(sel_n_a, sel_n_b) if in_nbm_scope else None,
            "corr_vs_l1":  _agree(corr_a, corr_b),
            "total_vs_best_raw": _agree(total_a, total_b),
            "chooser_vs_prod": _agree(chooser_prod_a, chooser_prod_b),
        },
    }


def main():
    band_picks = _load_selector_table()
    path = cached_path(PAIR_LOG_URL)
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

    windows_out = {}
    for label, days in WINDOWS:
        window_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
        halves_midpoint = (now - timedelta(days=days / 2)).strftime("%Y-%m-%dT%H:%M")
        prior_start = (now - timedelta(days=days * 2)).strftime("%Y-%m-%dT%H:%M")
        acc, halves = _accumulate(path, window_start, halves_midpoint, prior_start, band_picks)
        per_field = {f: _compute_field(f, acc[f], halves[f]) for f in FIELDS}
        windows_out[label] = {"per_field": per_field}

    payload = {
        "generated_at": now.isoformat() + "Z",
        "source": "forecast_error_log.jsonl",
        "selector_table_source": str(SELECTOR_TABLE_PATH.name),
        "windows": windows_out,
        "conventions": {
            "positive_pct": "current beats baseline (lift)",
            "sel_vs_hrrr_pct": "L1_selected vs raw HRRR — positive means the selector was smart to sometimes pick NBM",
            "sel_vs_nbm_pct":  "L1_selected vs raw NBM — positive means the selector was smart to sometimes pick HRRR",
            "corr_vs_l1_pct":  "Prod vs L1_selected — positive means the local correction stack adds value on top of the selector's pick",
            "total_vs_best_raw_pct": "Prod vs 'what the user's default weather app already shows them' (v0.6.478): baseline = NBM raw for NBM-scope fields (NBM is the NWS backbone, i.e. iPhone Weather / weather.gov / vendor displays); HRRR raw for the 5 HRRR-only fields (cl/cm/pp/pa/pr — NBM doesn't publish). Replaces the v0.6.477 per-row oracle (too strict — no real user picks HRRR/NBM per lead-hour) and the pre-v0.6.477 pooled-min (too generous — credited us for beating whichever raw source wins on average).",
            "l1_selected_definition": "For rows where selector picks NBM: error_l3_nbm (NBM's own bias-corrected output). For rows where selector picks HRRR (or falls through): error_l1 (raw HRRR). This makes corr_vs_l1_pct honestly measure the local correction stack's contribution.",
            "chooser_vs_prod_pct": "Chosen cascade's Prod vs alternative cascade's Prod, paired per row. Positive = selector picked the better cascade. This is the v0.6.440-rule chooser lift (Prod-vs-Prod, not raw-vs-raw).",
            "hrrr_prod_mae": "Deepest HRRR-side layer residual pooled over all rows — 'what would Prod be if we always picked HRRR'.",
            "nbm_prod_mae":  "Deepest NBM-side layer residual pooled over all rows — 'what would Prod be if we always picked NBM'.",
            "prod_trend_pct": "Current-window Prod MAE vs the equal-length window immediately preceding it. Positive = we improved. No external anchor — this is the 'am I doing my tuning job well' score.",
        },
        "nbm_scope": sorted(list(NBM_SCOPE)),
        "warmup_note": "Until pair log fills post-v0.6.440 + selector table starts flipping cells to NBM (earliest ~2026-09-17), L1_selected == raw HRRR for every row; sel_vs_hrrr_pct will read 0.0% and sel_vs_nbm_pct will read whatever raw-HRRR-vs-raw-NBM is on that field.",
    }

    with open(OUT_JSON, "w") as fout:
        json.dump(payload, fout, indent=2)
    print(f"wrote {OUT_JSON} ({os.path.getsize(OUT_JSON) / 1024:.1f} KB)")

    try:
        from weather_collector.gcs_io import upload_json  # noqa: E402
        upload_json(payload, "per_field_scoring.json", "per_field_scoring.json")
        print("  ✓ Published to gs://myweather-data/per_field_scoring.json")
    except Exception as e:
        print(f"  ⚠ GCS upload skipped ({type(e).__name__}: {e}) — local file still written")

    # Terminal summary
    for label, _ in WINDOWS:
        pf = windows_out[label]["per_field"]
        print(f"\n=== {label} ===")
        print(f"{'field':<5} {'hrrr':>7} {'nbm':>7} {'l1sel':>7} {'prod':>7}   "
              f"{'sel_h':>7} {'sel_n':>7} {'corr':>7} {'total':>7}")
        for f in FIELDS:
            c = pf[f]
            def fmt(v, w=7, dp=2, pct=False):
                if v is None: return "—".rjust(w)
                if pct: return f"{v:+.1f}%".rjust(w)
                return f"{v:.{dp}f}".rjust(w)
            print(f"{f:<5} {fmt(c['hrrr_raw_mae'])} {fmt(c['nbm_raw_mae'])} "
                  f"{fmt(c['l1_selected_mae'])} {fmt(c['prod_mae'])}   "
                  f"{fmt(c['sel_vs_hrrr_pct'],pct=True)} {fmt(c['sel_vs_nbm_pct'],pct=True)} "
                  f"{fmt(c['corr_vs_l1_pct'],pct=True)} {fmt(c['total_vs_best_raw_pct'],pct=True)}")


if __name__ == "__main__":
    main()
