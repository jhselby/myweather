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

L1_selected residual (v0.6.555): the raw of the source the selector
picked — error_raw_nbm on NBM picks, error_l1 (raw HRRR) on HRRR picks.
Both cascades symmetric: L1_selected IS the raw baseline; every Wyman
Cove correction layer above raw (L2_NBM/L3_NBM/L4_NBM/L5_NBM/L6_NBM/
chp_nbm/wdp_nbm on NBM; L2/L3/L4/L5/L6/chp/dpbp/wsbp/wdp/clp on HRRR)
counts as our local correction stack in corr_vs_l1_pct.

Runtime:
    python3 -m analysis.per_field_scoring
    MYWEATHER_REFRESH=1 python3 -m analysis.per_field_scoring
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pytz
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
MAE_OVER_TIME_JSON_PATH = _out("mae_over_time.json")


def _load_raw_difficulty():
    """Read raw_difficulty_index.per_field from the local mae_over_time.json
    written earlier in the same publisher run. Returns {field: ratio} where
    ratio = raw_mae_7d / raw_mae_90d_ref (>1 = harder than usual, <1 = easier).
    Silent {} on any failure — this is an optional 7d audit signal, not a
    gating input."""
    try:
        with open(MAE_OVER_TIME_JSON_PATH) as fin:
            payload = json.load(fin)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    rdi = payload.get("raw_difficulty_index") or {}
    pf = rdi.get("per_field") or {}
    return {f: cell.get("ratio") for f, cell in pf.items() if cell.get("ratio") is not None}

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
# v0.6.615 (2026-09-14) added 12h. See scoreboard_v2.py for why 6h was tried and dropped.
WINDOWS = [("7d", 7), ("24h", 1), ("12h", 0.5)]

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


# v0.6.494 — NBM-side layer stamps to SKIP when computing current-config Prod.
# Any NBM-cascade layer whose runtime ENABLED flag is False belongs here so its
# historical stamps stop contaminating the rolling window post-kill/scaffold.
# When a layer is re-enabled, remove its stamp key from this set.
#
# Snapshot as of 2026-08-26:
#   error_l5_nbm — l5_nbm.ENABLED = False (killed 2026-08-25, sr regression)
#   error_l6_nbm — l6_nbm.ENABLED = False (scaffold, waterfront investigation)
#
# HRRR-side deliberately NOT listed: HRRR `l6` slot is Lt for t (disabled) but
# Lc for cm/ch (enabled). Correct HRRR-side counterfactual needs per-field
# disable logic — deferred. As of 2026-09-07 this is moot in practice: Lt
# retired 2026-07-13, so the 7d/24h rolling windows no longer contain any
# error_l6 stamps that trace back to Lt. HRRR-side counterfactual ≡ as-
# shipped Prod. Add back the per-field logic if any HRRR-side layer is
# scaffolded/disabled while still stamping error_{layer} in the pair log.
_DISABLED_LAYER_KEYS = frozenset({
    "error_l5_nbm",
    "error_l6_nbm",
})


def _prod_error_current_config(row):
    """Prod residual under CURRENT enable-flags — walks the appropriate
    cascade side (NBM if row's applied_layer ends in `_nbm`, HRRR otherwise)
    and SKIPS stamps for currently-disabled layers. Killed layers stop
    poisoning the rolling window even for rows stamped while they were live.

    Fall-through: if no non-disabled stamp is present on the side, returns
    None (caller treats it the same as any missing residual).
    """
    applied = (row.get("applied_layer") or "")
    # v0.7.60 — blend rows: the served blend IS current config (it walks
    # neither cascade); was scored as the HRRR cascade.
    if row.get("selector_source") in BLEND_SOURCES:
        return _prod_error(row)
    keys = NBM_PROD_KEYS if applied.endswith("_nbm") else HRRR_PROD_KEYS
    for k in keys:
        if k in _DISABLED_LAYER_KEYS:
            continue
        v = row.get(k)
        if v is not None:
            return v
    return None


# v0.7.59 — wd residuals are circular; a linear blend of signed residuals is
# meaningless, so wd's best rule is the better single cascade.
CIRCULAR_FIELDS = frozenset({"wd"})

# v0.7.73 — walk-forward Selector Score ceiling (see _compute_field).
WF_TRAIN_DAYS = 14
WF_BLOCK_HOURS = 4
WF_MIN_BLOCK_N = 300
WF_MIN_FIELD_N = 2000
WF_MIN_COVERAGE = 0.8


def _walkforward_weights(pair_log_path, first_day):
    """{(field, obs_day): {"field": w, "block": {block_start_hour: w}}} for
    every obs_day >= first_day, each fit on the WF_TRAIN_DAYS before it from
    the same HRRR/NBM prod residuals the score uses. Same fit as
    analysis/terminal_blend_field_fit.py, refit per day."""
    grids = defaultdict(lambda: [0.0] * 22)  # (field, day, block|None) -> 21 sums + n
    lo = (datetime.strptime(first_day, "%Y-%m-%d") - timedelta(days=WF_TRAIN_DAYS)).strftime("%Y-%m-%d")
    with open(pair_log_path) as fin:
        for line in fin:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            field = row.get("field")
            day = (row.get("obs_time") or "")[:10]
            if field not in NBM_SCOPE or field in CIRCULAR_FIELDS or day < lo:
                continue
            e_hp, e_np = _hrrr_prod_error(row), _nbm_prod_error(row)
            if e_hp is None or e_np is None:
                continue
            sh, sn = float(e_hp), float(e_np)
            vt = row.get("valid_time") or ""
            keys = [(field, day, None)]
            if len(vt) >= 13:
                keys.append((field, day, int(vt[11:13]) // WF_BLOCK_HOURS * WF_BLOCK_HOURS))
            gs = [grids[k] for k in keys]
            for i in range(21):
                w = i / 20.0
                e = abs(w * sh + (1.0 - w) * sn)
                for g in gs:
                    g[i] += e
            for g in gs:
                g[21] += 1

    def best(sums, n, floor):
        return min(range(21), key=lambda i: sums[i]) / 20.0 if n >= floor else None

    days = sorted({d for (_, d, _) in grids})
    out = {}
    for field in NBM_SCOPE - CIRCULAR_FIELDS:
        for d in days:
            if d < first_day:
                continue
            start = (datetime.strptime(d, "%Y-%m-%d") - timedelta(days=WF_TRAIN_DAYS)).strftime("%Y-%m-%d")
            agg = defaultdict(lambda: [0.0] * 22)
            for (f, dd, blk), g in grids.items():
                if f == field and start <= dd < d:
                    a = agg[blk]
                    for i in range(22):
                        a[i] += g[i]
            wf = best(agg[None], agg[None][21], WF_MIN_FIELD_N) if None in agg else None
            if wf is None:
                continue
            blocks = {blk: best(a, a[21], WF_MIN_BLOCK_N) for blk, a in agg.items() if blk is not None}
            out[(field, d)] = {"field": wf, "block": {k: v for k, v in blocks.items() if v is not None}}
    return out

# Sources where the served value is a blend of both cascades, not one side.
BLEND_SOURCES = ("l1_blend", "blend", "tblend")


def _selected_l1_error(row, band_picks):
    """L1_selected residual — the raw of the source the selector picked.
    Everything above the raw counts as our local correction stack.

    Rule:
      selector picks "nbm" → error_raw_nbm
      selector picks "hrrr" or falls through → error_l1 (raw HRRR)

    Both cascades treated symmetrically: L1_selected is the RAW of the
    picked source; every Wyman Cove layer above raw (L2_NBM, L3_NBM,
    L4_NBM, L5_NBM, L6_NBM, chp_nbm, wdp_nbm on the NBM side; L2, L3, L4,
    L5, L6, chp, dpbp, wsbp, wdp, clp on the HRRR side) is our
    correction stack. corr_vs_l1_pct honestly measures the full local
    contribution.

    Pre-v0.6.555 the NBM walk went `error_l3_nbm → error_raw_nbm`, which
    excluded L3_NBM from corr_vs_l1 credit. But L3_NBM is a Wyman Cove
    local bias-shift table (analysis/l3_nbm_fit.py fits it from pair-log
    residuals) — it belongs on the correction side, not the reference
    side. Moved 2026-09-07.
    """
    field = row.get("field")
    band = _band_for(row.get("lead_h"))
    # v0.7.57 — grade the pick that actually SHIPPED on this row
    # (selector_source stamp; for a blend row, the pick the blend
    # pre-empted). Pre-v0.7.57 every row in the window was graded on
    # TODAY's band-pool table, blind to regime cells, the recency override,
    # learned cells and any table change during the window.
    src = row.get("selector_source")
    if src in BLEND_SOURCES:
        src = row.get("preempted_source_shadow")
    if src in ("hrrr", "nbm"):
        pick = src
    else:
        pick = "hrrr"
        if field in band_picks and band in band_picks[field]:
            pick = band_picks[field][band]
    # v0.7.57 — an applied L1 static blend IS the L1 seat (omega*l1 +
    # (1-omega)*raw_nbm), so Routing attribution credits the blend's raw-level
    # residual. Terminal blends (tblend/blend) sit above both cascades; their
    # gain lands in the Cascade column against the pre-empted pick's raw.
    # v0.7.60 — a terminal blend's routing decision is its weight w: credit
    # routing with the same w applied to the two raws, so Cascade keeps only
    # the corrections (blend of terminals − blend of raws). Without this the
    # blend's routing gain landed in Pipeline Lift / Cascade.
    if row.get("selector_source") == "tblend":
        w = row.get("tblend_w_shadow")
        e_h, e_n = row.get("error_l1"), row.get("error_raw_nbm")
        if w is not None and e_h is not None and e_n is not None:
            return float(w) * float(e_h) + (1.0 - float(w)) * float(e_n), pick
    if row.get("selector_source") == "l1_blend":
        v = row.get("error_l1_blend")
        if v is None and row.get("l1_blend_shadow") is not None and row.get("observed") is not None:
            v = float(row["l1_blend_shadow"]) - float(row["observed"])
        if v is not None:
            return v, pick
    if pick == "nbm":
        v = row.get("error_raw_nbm")
        if v is not None:
            return v, "nbm"
        # NBM pick but neither NBM stamp on this row → fall through to HRRR.
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
        # v0.7.59 — per (regime_runtime, band) sums of |HRRR prod| and |NBM
        # prod| on the chooser pool. Summed to field level for the
        # best-fixed-routing baseline; kept per cell for diagnostics.
        "cell_fixed":   {},
        # v0.7.59 — sum |w*e_hrrr + (1-w)*e_nbm| for w in W_GRID (signed
        # cascade residuals, same chooser rows). min over w = the best
        # constant blend in hindsight = the Selector Score's "perfect".
        "wgrid":        [0.0] * 21,
        # v0.7.73 — walk-forward rule errors on the same rows: w fit on the
        # 14 days before each row's obs day, one w per field ("wf_field") or
        # one per 4-hour block of local valid time ("wf_block"). The Selector
        # Score's "perfect" is the better of the two (see _compute_field).
        "wf_field":     [0.0, 0],
        "wf_block":     [0.0, 0],
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
        # v0.7.60 — Lift Trend: [sum|prod|, sum|public baseline|, n] per
        # window on rows carrying both. Public baseline = NBM raw (NBM
        # scope) or HRRR raw (HRRR-only fields), same as Total Lift.
        "lift_cur":   [0.0, 0.0, 0],
        "lift_prior": [0.0, 0.0, 0],
        # Per-row oracle Prod (v0.6.481): min(|chosen_prod_err|, |alt_prod_err|)
        # per row over the paired chosen/alt pool. Feeds Value Captured.
        "oracle_prod":  [0.0, 0],
        # Selector Win Rate (v0.6.556): rows where the picked cascade's
        # Prod strictly beat the alternative. Ties (chosen == alt) drop
        # out of the denominator entirely — those rows don't test picker
        # skill (the cascades happen to agree, the router earns no
        # credit). Losses are strict too. Pre-v0.6.556 counted ties as
        # hits, which inflated the tile 15-30pp on small-magnitude
        # fields and hid catastrophic magnitude losses on kill-transition
        # rows (see ch 24h 2026-09-07: 97.9% hit rate, -895% VC — the
        # near-perfect hit rate was all ties, non-tie rows were the
        # catastrophe VC caught).
        "wins":         0,
        "losses":       0,
        "ties":         0,
        "prod_prior":   [0.0, 0],
        "selector_picks": {"hrrr": 0, "nbm": 0, "hrrr_fallback": 0, "na": 0},
        # v0.6.493 — per-band buckets for Notable Calls + High-Conf tiles.
        # Total Lift per (field, band) uses the Public Baseline rule
        # (v0.6.478): NBM raw for NBM-scope, HRRR raw for HRRR-only. Both
        # raws accumulated per band; renderer picks by scope. Populated
        # inside the pool_ok block so it inherits Total Lift's pool
        # discipline.
        "per_band": {name: {"hrrr_raw": [0.0, 0], "nbm_raw": [0.0, 0],
                             "prod": [0.0, 0], "prod_cc": [0.0, 0]}
                     for _lo, _hi, name in BANDS},
        # v0.6.494 — current-config Prod. Same pool discipline as `prod`
        # (populated inside pool_ok). Skips historical stamps for layers
        # currently disabled — see _DISABLED_LAYER_KEYS.
        "prod_current_config": [0.0, 0],
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


def _accumulate(pair_log_path, window_start, halves_midpoint, prior_start, band_picks, wf_weights=None):
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
                    _base = e_nbm if in_nbm_scope else e_hrrr
                    if _base is not None:
                        _lp = acc[field]["lift_prior"]
                        _lp[0] += vw; _lp[1] += abs(float(_base)); _lp[2] += 1
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
                # v0.6.494 — current-config Prod: walk the applied cascade
                # skipping disabled layers.
                e_pcc = _prod_error_current_config(row)
                v_pcc = None
                if e_pcc is not None:
                    v_pcc = abs(float(e_pcc))
                    b["prod_current_config"][0] += v_pcc
                    b["prod_current_config"][1] += 1
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
                        if v_pcc is not None:
                            pb["prod_cc"][0] += v_pcc; pb["prod_cc"][1] += 1

            # v0.6.487 — current-window prod on the wider pool (any row
            # with a Prod stamp, no intersection requirement). Paired with
            # `prod_prior_wider` above to compute prod_trend_pct.
            if e_prod is not None:
                vw = abs(float(e_prod))
                b["prod_wider"][0] += vw
                b["prod_wider"][1] += 1
                _base = e_nbm if in_nbm_scope else e_hrrr
                if _base is not None:
                    _lc = b["lift_cur"]
                    _lc[0] += vw; _lc[1] += abs(float(_base)); _lc[2] += 1

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
                # v0.7.57 — blend rows: what shipped is the blend, so
                # chosen = served residual; alt stays the side the selector's
                # own pick would have left out. Oracle stays the per-row
                # PICK oracle min(hp, np), so a blend can beat it.
                # v0.7.60 — chosen = what actually shipped on EVERY row
                # (was the picked side's cascade walk; differed on ~1.4% of
                # t/ws rows routed to NWS, graded as NBM).
                chosen = abs(float(e_prod))
                b["chosen_prod"][0] += chosen; b["chosen_prod"][1] += 1
                b["alt_prod"][0] += alt;       b["alt_prod"][1] += 1
                half["chosen_prod"][0] += chosen; half["chosen_prod"][1] += 1
                half["alt_prod"][0] += alt;       half["alt_prod"][1] += 1
                # v0.6.481: per-row oracle. Oracle picks the lower
                # cascade every row.
                orc = min(hp, np_)
                _sf = row.get("state_fc") or {}
                _ck = (_sf.get("regime_runtime") or _sf.get("regime_synoptic"),
                       _band_for(row.get("lead_h")))
                _cf = b["cell_fixed"].setdefault(_ck, [0.0, 0.0])
                _cf[0] += hp; _cf[1] += np_
                if field not in CIRCULAR_FIELDS:
                    _sh, _sn = float(e_hp), float(e_np)
                    _wg = b["wgrid"]
                    for _i in range(21):
                        _w = _i / 20.0
                        _wg[_i] += abs(_w * _sh + (1.0 - _w) * _sn)
                    _ww = (wf_weights or {}).get((field, obs_time[:10]))
                    if _ww:
                        _vt = row.get("valid_time") or ""
                        _wb = (_ww["block"].get(int(_vt[11:13]) // WF_BLOCK_HOURS * WF_BLOCK_HOURS)
                               if len(_vt) >= 13 else None)
                        _wb = _ww["field"] if _wb is None else _wb
                        b["wf_field"][0] += abs(_ww["field"] * _sh + (1.0 - _ww["field"]) * _sn)
                        b["wf_field"][1] += 1
                        b["wf_block"][0] += abs(_wb * _sh + (1.0 - _wb) * _sn)
                        b["wf_block"][1] += 1
                b["oracle_prod"][0] += orc; b["oracle_prod"][1] += 1
                # v0.6.556: split wins / losses / ties. Ties (chosen ==
                # alt) are cascades-agree rows, not router-skill rows —
                # excluded from Win Rate denominator downstream.
                if chosen < alt:
                    b["wins"] += 1
                elif chosen > alt:
                    b["losses"] += 1
                else:
                    b["ties"] += 1
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
    # v0.7.60 — Lift Trend (pp) = Total Lift this window − Total Lift the
    # prior equal window, each vs the public baseline on its own rows.
    # Replaces Prod Trend as the tile grade: raw Prod MAE across windows
    # tracks the weather (10-14: ws Prod "−33% regressing" while the public
    # forecast got 36% worse and our lift rose +1.5 → +3.7 pp).
    lift_trend_pp = None
    _lc, _lp = buckets["lift_cur"], buckets["lift_prior"]
    if (field not in TREND_EXCLUDE_FIELDS and _lp[2] >= MIN_N_TREND and _lc[2] > 0
            and _lp[1] > 0 and _lc[1] > 0):
        lift_trend_pp = (100.0 * (_lc[1] - _lc[0]) / _lc[1]) - (100.0 * (_lp[1] - _lp[0]) / _lp[1])

    # v0.6.481 — Selector Win Rate + Value Captured (both diagnostic,
    # NBM-scope only; null for HRRR-only fields where there's no alt
    # cascade to compare against). Both computed on the paired
    # chosen_prod / alt_prod pool.
    #
    # v0.6.556 — Hit Rate replaced by Win Rate. Ties (chosen == alt)
    # excluded from the denominator: those rows don't test picker skill,
    # the two cascades happen to agree and the router earns nothing.
    # Win Rate = wins / (wins + losses); None when the router had no
    # differentiable rows (all ties). Prior "hit_rate_pct" inflated the
    # tile 15-30pp on small-magnitude fields and hid catastrophic
    # magnitude losses on kill-transition rows.
    oracle_prod = _mean(buckets["oracle_prod"])
    n_paired = buckets["chosen_prod"][1]
    n_wins = buckets["wins"]; n_losses = buckets["losses"]; n_ties = buckets["ties"]
    n_decisive = n_wins + n_losses
    if in_nbm_scope and n_decisive > 0:
        win_rate_pct = 100.0 * n_wins / n_decisive
    else:
        win_rate_pct = None
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

    # v0.7.59 — Selector Skill = served vs the BEST FIXED ROUTING for the
    # field (always-HRRR or always-NBM cascade, whichever had the lower error
    # on the same rows and window). + = the selector (plus any blend) beats
    # the simplest static choice; 0 = matches it (wd: always-NBM is optimal);
    # − = loses to it. Same quantity as scoreboard_v2's
    # selector_lift_vs_best_fixed_pct, so the two scoreboards agree.
    # Replaces Value Captured as the tile grade: VC's per-row oracle credits
    # chance per-hour wins no forecast-time rule can capture, so fields where
    # one source wins everywhere read red forever. A per-(regime, band)
    # hindsight bar was tried and rejected: 35 cells over 7d is itself an
    # oracle (wd −0.8%, 24h ch −233% on 0.6-MAE cells). VC stays in the JSON
    # as the theoretical ceiling.
    cf = buckets["cell_fixed"]
    best_fixed_sum = min(sum(hs for hs, _ in cf.values()), sum(ns for _, ns in cf.values())) if cf else 0.0
    chosen_sum = buckets["chosen_prod"][0]
    if in_nbm_scope and best_fixed_sum > 0 and buckets["chosen_prod"][1] > 0:
        selector_vs_fixed_pct = 100.0 * (best_fixed_sum - chosen_sum) / best_fixed_sum
        best_fixed_mae = best_fixed_sum / buckets["chosen_prod"][1]
    else:
        selector_vs_fixed_pct = None
        best_fixed_mae = None

    # v0.7.59 — Selector Score = improvement achieved / improvement a perfect
    # rule could have achieved, both measured from the best fixed routing.
    # "Perfect" = the best CONSTANT blend weight for the field in hindsight
    # on the same rows (w in 0..1 step 0.05; w=0/1 are the fixed routings) —
    # a rule we could actually run, unlike the per-row oracle behind Value
    # Captured. 100% = as good as the best real rule; 0% = no better than
    # always one cascade; negative = worse. Headroom < 2% of the fixed
    # routing's error = nothing to gain (score None, selector_headroom_pct
    # says why). Can exceed 100% when per-cell blends beat one field weight.
    #
    # v0.7.73 — "perfect" is now WALK-FORWARD, not hindsight: each row is
    # blended with the w fit on the 14 days before its obs day (one w per
    # field, or one per 4-hour local block), the better shape over the window
    # wins. Reachable by construction, so 100% = serving the best rule that
    # holds up out of sample. Hindsight was no longer a ceiling once the
    # served blend IS a constant w (v0.7.71), and a hindsight per-block bar
    # overfits (7d t read 12.6% room; walk-forward block gain was +0.4%).
    # The hindsight constant w stays as best_constant_w_hindsight.
    wg = buckets["wgrid"]
    n_ch = buckets["chosen_prod"][1]
    best_rule_w = best_rule_kind = None
    if field not in CIRCULAR_FIELDS and any(wg):
        best_rule_w = min(range(21), key=lambda i: wg[i]) / 20.0
    best_rule_sum = best_fixed_sum
    _wf_cov = buckets["wf_field"][1] / n_ch if n_ch else 0.0
    if field not in CIRCULAR_FIELDS and _wf_cov >= WF_MIN_COVERAGE:
        # Rows without a walk-forward fit (thin prior days) score as the
        # served value would have, so coverage gaps don't add or hide room.
        _gap = chosen_sum * (1.0 - _wf_cov)
        for _kind in ("field", "block"):
            _sum = buckets[f"wf_{_kind}"][0] + _gap
            if _sum < best_rule_sum:
                best_rule_sum, best_rule_kind = _sum, _kind
    selector_score_pct = selector_headroom_pct = best_rule_mae = None
    if in_nbm_scope and best_fixed_sum > 0 and n_ch > 0:
        selector_headroom_pct = 100.0 * (best_fixed_sum - best_rule_sum) / best_fixed_sum
        best_rule_mae = best_rule_sum / n_ch
        if selector_headroom_pct >= 2.0:
            selector_score_pct = 100.0 * (best_fixed_sum - chosen_sum) / (best_fixed_sum - best_rule_sum)

    return {
        "selector_vs_fixed_pct": round(selector_vs_fixed_pct, 2) if selector_vs_fixed_pct is not None else None,
        "selector_score_pct": round(selector_score_pct, 1) if selector_score_pct is not None else None,
        "selector_headroom_pct": round(selector_headroom_pct, 2) if selector_headroom_pct is not None else None,
        "best_rule_mae": round(best_rule_mae, 3) if best_rule_mae is not None else None,
        "best_rule_kind": best_rule_kind,
        "best_constant_w_hindsight": best_rule_w,
        "wf_field_mae": round(buckets["wf_field"][0] / buckets["wf_field"][1], 3) if buckets["wf_field"][1] else None,
        "wf_block_mae": round(buckets["wf_block"][0] / buckets["wf_block"][1], 3) if buckets["wf_block"][1] else None,
        "wf_coverage": round(_wf_cov, 3),
        "best_fixed_mae": round(best_fixed_mae, 3) if best_fixed_mae is not None else None,
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
        "win_rate_pct":    round(win_rate_pct, 2) if win_rate_pct is not None else None,
        "n_wins":          n_wins,
        "n_losses":        n_losses,
        "n_ties":          n_ties,
        "value_captured_pct": round(value_captured_pct, 2) if value_captured_pct is not None else None,
        "prod_prior_mae": round(prod_prior, 3) if prod_prior is not None else None,
        "n_prod_prior":   buckets["prod_prior"][1],
        "prod_trend_pct": round(prod_trend_pct, 2) if prod_trend_pct is not None else None,
        "lift_trend_pp": round(lift_trend_pp, 2) if lift_trend_pp is not None else None,
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
        # v0.6.630 — paired additive decomposition of total_vs_best_raw_pct.
        # routing_paired_pct = (best_raw − l1_selected) / best_raw × 100
        # cascade_paired_pct = (l1_selected − prod)     / best_raw × 100
        # By construction routing_paired_pct + cascade_paired_pct =
        # total_vs_best_raw_pct on the same paired pool, at the same 2-dp
        # rounding. Frontend Attribution tile reads these directly instead
        # of recomputing from *_mae — recomputation via 3-dp intermediates
        # was drifting from Total Lift by ~0.5pp per aggregate.
        "routing_paired_pct": (round(_lift_pct(best_raw, sel), 2)
                                if _lift_pct(best_raw, sel) is not None else None),
        "cascade_paired_pct": (round(100.0 * (sel - prod) / best_raw, 2)
                                if (best_raw is not None and best_raw > 0
                                    and sel is not None and prod is not None)
                                else None),
        # v0.6.494 — current-config counterfactual Total Lift. Same math as
        # total_vs_best_raw_pct but Prod is recomputed by walking cascade
        # stamps and skipping currently-disabled layers (see
        # _DISABLED_LAYER_KEYS). Big delta vs total_vs_best_raw_pct = a
        # recent kill is still poisoning the rolling window; small delta =
        # historical stamps and current config agree.
        "total_current_config_pct": (
            round(_lift_pct(best_raw, _mean(buckets["prod_current_config"])), 2)
            if _lift_pct(best_raw, _mean(buckets["prod_current_config"])) is not None
            else None),
        "prod_current_config_mae": (round(_mean(buckets["prod_current_config"]), 3)
                                     if _mean(buckets["prod_current_config"]) is not None else None),
        "n_prod_current_config":   buckets["prod_current_config"][1],
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
                # v0.6.494 — per-band current-config counterfactual.
                "total_current_config_pct": (
                    round(_lift_pct(
                        _mean(pb["nbm_raw"]) if in_nbm_scope and _mean(pb["nbm_raw"]) is not None
                        else _mean(pb["hrrr_raw"]),
                        _mean(pb["prod_cc"])
                    ), 2)
                    if _lift_pct(
                        _mean(pb["nbm_raw"]) if in_nbm_scope and _mean(pb["nbm_raw"]) is not None
                        else _mean(pb["hrrr_raw"]),
                        _mean(pb["prod_cc"])
                    ) is not None else None
                ),
                "prod_cc_mae": round(_mean(pb["prod_cc"]), 3) if _mean(pb["prod_cc"]) is not None else None,
                "n_prod_cc":   pb["prod_cc"][1],
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
    # Pair-log obs_time is local (America/New_York) naive, so window edges
    # must be local too. v0.7.64: was UTC now, which cut every window 4h short.
    now = datetime.now(pytz.timezone("America/New_York")).replace(tzinfo=None, microsecond=0)

    wf_first_day = (now - timedelta(days=max(d for _, d in WINDOWS))).strftime("%Y-%m-%d")
    wf_weights = _walkforward_weights(path, wf_first_day)

    windows_out = {}
    for label, days in WINDOWS:
        window_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
        halves_midpoint = (now - timedelta(days=days / 2)).strftime("%Y-%m-%dT%H:%M")
        prior_start = (now - timedelta(days=days * 2)).strftime("%Y-%m-%dT%H:%M")
        acc, halves = _accumulate(path, window_start, halves_midpoint, prior_start, band_picks, wf_weights)
        per_field = {f: _compute_field(f, acc[f], halves[f]) for f in FIELDS}
        # Raw-difficulty index (7d only — reference is trailing 90d, no 24h
        # analog). Attaches per_field ratio so the diagnostic table can show
        # "was the underlying weather harder or easier than usual" alongside
        # Total Lift. Direction-neutral display per feedback_audit_label_direction_neutral.
        if label == "7d":
            rdi = _load_raw_difficulty()
            for f in FIELDS:
                per_field[f]["raw_difficulty_ratio"] = rdi.get(f)
        windows_out[label] = {"per_field": per_field}

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z",
        "source": "forecast_error_log.jsonl",
        "selector_table_source": str(SELECTOR_TABLE_PATH.name),
        "windows": windows_out,
        "conventions": {
            "positive_pct": "current beats baseline (lift)",
            "sel_vs_hrrr_pct": "L1_selected vs raw HRRR — positive means the selector was smart to sometimes pick NBM",
            "sel_vs_nbm_pct":  "L1_selected vs raw NBM — positive means the selector was smart to sometimes pick HRRR",
            "corr_vs_l1_pct":  "Prod vs L1_selected — positive means the local correction stack adds value on top of the selector's pick",
            "total_vs_best_raw_pct": "Prod vs 'what the user's default weather app already shows them' (v0.6.478): baseline = NBM raw for NBM-scope fields (NBM is the NWS backbone, i.e. iPhone Weather / weather.gov / vendor displays); HRRR raw for the 5 HRRR-only fields (cl/cm/pp/pa/pr — NBM doesn't publish). Replaces the v0.6.477 per-row oracle (too strict — no real user picks HRRR/NBM per lead-hour) and the pre-v0.6.477 pooled-min (too generous — credited us for beating whichever raw source wins on average).",
            "routing_paired_pct": "Additive decomposition (v0.6.630): (best_raw − l1_selected) / best_raw × 100. How much of Total Lift comes from the selector picking the better raw source. Zero on rows where the pick IS the default. Paired pool = same rows as total_vs_best_raw_pct.",
            "cascade_paired_pct": "Additive decomposition (v0.6.630): (l1_selected − prod) / best_raw × 100. How much of Total Lift comes from the local correction stack on top of the selected raw. Paired pool = same rows as total_vs_best_raw_pct. By construction routing_paired_pct + cascade_paired_pct = total_vs_best_raw_pct.",
            "l1_selected_definition": "The raw of the source the selector picked (v0.6.555 — symmetric across cascades): NBM pick → error_raw_nbm; HRRR pick or fall-through → error_l1 (raw HRRR). Every Wyman Cove correction layer above raw counts as our local stack in corr_vs_l1_pct. Pre-v0.6.555 NBM walked error_l3_nbm → error_raw_nbm, which excluded L3_NBM from corr credit even though L3_NBM is our local bias table (analysis/l3_nbm_fit.py). Moved to correction side 2026-09-07.",
            "chooser_vs_prod_pct": "Chosen cascade's Prod vs alternative cascade's Prod, paired per row. Positive = selector picked the better cascade. This is the v0.6.440-rule chooser lift (Prod-vs-Prod, not raw-vs-raw).",
            "hrrr_prod_mae": "Deepest HRRR-side layer residual pooled over all rows — 'what would Prod be if we always picked HRRR'.",
            "nbm_prod_mae":  "Deepest NBM-side layer residual pooled over all rows — 'what would Prod be if we always picked NBM'.",
            "prod_trend_pct": "Current-window Prod MAE vs the equal-length window immediately preceding it. Positive = we improved. No external anchor — this is the 'am I doing my tuning job well' score.",
            "raw_difficulty_ratio": "7d only. raw_mae_7d / raw_mae_ref where ref = trailing 90d excluding the 7d itself. >1.0 = raw model had it harder than usual (harder-to-predict week); <1.0 = easier than usual. Per-field normalized so units don't mix. Sourced from mae_over_time.json's raw_difficulty_index (v0.6.392). Direction-neutral audit signal — does not prescribe how to reinterpret weekly lift.",
        },
        "nbm_scope": sorted(list(NBM_SCOPE)),
        "warmup_note": "Selector is actively flipping cells since v0.6.546 (recency overrides) and v0.6.552 (by-regime walker wire). Currently ~11 recency overrides + walker overrides accumulating post-2026-09-07 (earliest walker clear 09-14). Any fresh cascade change (e.g. L3_NBM kill 09-05 v0.6.551, sr add 09-04 v0.6.549) will show a ~7d transient where the rolling window mixes pre-change and post-change rows — 24h reads honest current behavior; 7d lags by up to a week.",
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
