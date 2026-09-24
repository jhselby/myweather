"""L1 selector apply-time processor (option-1 Phase 4, 2026-08-19).

Loads `weather_collector/data/l1_selector_table_curated.json` at module
import; exposes `pick_source(field, lead_h[, regime]) -> "hrrr" | "nbm" | "nws"`. Table
schema and pick rule live in `analysis/l1_selector_fit.py`.

Fall-through to "hrrr" when the field or band is out of scope, the
table is unreadable, or the cell hasn't cleared its n/lift floors —
this is the safe default (equal to current Prod behavior pre-Phase-4).

Wired into `forecast_snapshot.stamp()`: for each hour × field, if
`pick_source(field, lead_h) == "nbm"`, replace the user-visible `{field}`
value with `{field}_l3_nbm`. The pair-log joiner stamps the pick as
`{field}_selector_source` so per-row Prod attribution stays correct.

Scope: fields listed in the table's `table` block. Currently t/ws/wg/wd/h.
Everything else falls through to HRRR unconditionally.

Naming note: the layer is called "L1 selector" per the option-1 plan
because it picks between two source cascades (HRRR-side, NBM-side) —
conceptually at L1 even though it applies at the top of the L3 output.
Ripping out the v0.6.432 L1 router happens after this ships and clears
its post-deploy watch.
"""
import json
import logging
import math
from pathlib import Path


CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "l1_selector_table_curated.json"
REGIME_WALKER_PATH = Path(__file__).resolve().parent.parent / "data" / "l1_selector_by_regime_walker.json"
LEARNED_CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "l1_learned_selector_curated.json"
BLENDER_CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "l1_blender_curated.json"

BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]

# Runtime allowlist for NWS routing. The 3-way fitter covers t/wd/ws/dp/pp,
# but dp is DERIVED downstream (Magnus(t, h) at corrected_hourly.py:264 and
# forecast_snapshot.py:296/652). Routing dp to NWS while t and h stay on
# HRRR/NBM walker picks would ship a thermodynamically inconsistent
# (t, h, dp) triple to the user. Gated at wire-time, not at the walker —
# the walker's dp/... cleared cells stay in the diagnostic JSON as
# evidence for a future coherence-aware wire (back-derive h from dp_nws,
# or gate on NWS-t agreement with our t). Per v0.6.600 blocker note.
_NWS_FIELDS_WIRE_ELIGIBLE = frozenset({"t", "ws", "wd", "pp"})

_TABLE = {}       # {field: {band: "hrrr"|"nbm"}}
_META = {}        # fitted_at, ship-gate summary, etc.
_REGIME_OVERRIDES = {}  # {field: {regime: {band: "nbm"}}} — cleared cells only

# Learned per-obs classifier runtime table. See analysis/l1_learned_selector_curate.py
# for the curator, l1_selector_per_obs_classifier_stage1_v2.py for the fitter.
_LEARNED_CELLS = {}       # {(field, regime, band): {theta, beta, mu, sd}}
_LEARNED_FEATURE_NAMES = ()   # tuple, ordered — must match runtime feature dict keys

# v0.7.0 — L1 blender runtime table. Successor architecture to the picker.
# Ridge regression on the same 12 features; output is a continuous blend
# weight ω ∈ [0,1] instead of a binary pick. Curated by
# analysis/l1_blender_curate.py from Stage 1 STABLE cells. Consumer (see
# forecast_snapshot.py) computes forecast = ω·HRRR_terminal + (1-ω)·NBM_terminal
# per row when the (field, regime, band) has a curated cell.
_BLENDER_CELLS = {}       # {(field, regime, band): {beta, mu, sd}}
_BLENDER_FEATURE_NAMES = ()   # tuple, ordered — must match feature-dict keys


def _band_for(lead_h):
    for name, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return name
    return None


def _load():
    global _TABLE, _META
    try:
        with open(CURATED_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning(f"  ⚠  l1_selector: curated JSON unavailable ({e}); "
                        f"selector is a no-op (HRRR fall-through)")
        _TABLE = {}
        return
    raw = data.get("table") or {}
    parsed = {}
    for field, cells in raw.items():
        parsed[field] = {band: (cell.get("source") or "hrrr")
                         for band, cell in (cells or {}).items()}
    _TABLE = parsed
    _META = {
        "fitted_at": data.get("fitted_at"),
        "window_days": data.get("window_days"),
        "ship_gate": data.get("ship_gate_router_scope") or {},
    }


def _load_regime_overrides():
    """Load the by-regime walker's per-cell verdicts. Three-directional:
    a cell with `cleared_for_wire_nws == True` AND `flipped_in_window_nws
    == False` routes NWS (highest precedence — NWS beat both HRRR and NBM
    in the 3-way fitter); else `cleared_for_wire == True` AND
    `flipped_in_window == False` routes NBM; else `cleared_for_wire_hrrr
    == True` AND `flipped_in_window_hrrr == False` routes HRRR. The three
    directions are mutually exclusive by construction (NWS-wire cells are
    only emitted when NWS beats best-of-HRRR-NBM, so they can't co-occur
    with the other two). Missing file, empty cells list, or any load error
    → no overrides (band pool decides)."""
    global _REGIME_OVERRIDES
    try:
        with open(REGIME_WALKER_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _REGIME_OVERRIDES = {}
        return
    per_cell = data.get("per_cell") or {}
    parsed = {}
    for field, regs in per_cell.items():
        for regime, bands in (regs or {}).items():
            for band, cell in (bands or {}).items():
                if cell.get("cleared_for_wire_nws") and not cell.get("flipped_in_window_nws"):
                    parsed.setdefault(field, {}).setdefault(regime, {})[band] = "nws"
                elif cell.get("cleared_for_wire") and not cell.get("flipped_in_window"):
                    parsed.setdefault(field, {}).setdefault(regime, {})[band] = "nbm"
                elif cell.get("cleared_for_wire_hrrr") and not cell.get("flipped_in_window_hrrr"):
                    parsed.setdefault(field, {}).setdefault(regime, {})[band] = "hrrr"
    _REGIME_OVERRIDES = parsed


def _load_learned():
    """Load learned per-obs classifier cells. Missing / malformed → empty
    table (learned override is a no-op)."""
    global _LEARNED_CELLS, _LEARNED_FEATURE_NAMES
    try:
        with open(LEARNED_CURATED_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _LEARNED_CELLS = {}
        _LEARNED_FEATURE_NAMES = ()
        return
    names = tuple(data.get("feature_names") or ())
    parsed = {}
    for cell in data.get("cells") or ():
        f_ = cell.get("field")
        r_ = cell.get("regime")
        b_ = cell.get("band")
        beta = cell.get("beta")
        mu = cell.get("mu")
        sd = cell.get("sd")
        theta = cell.get("theta")
        if None in (f_, r_, b_, beta, mu, sd, theta):
            continue
        if len(beta) != len(names) + 1 or len(mu) != len(names) or len(sd) != len(names):
            logging.warning(f"  ⚠  l1_learned_selector: shape mismatch on cell "
                            f"{f_}/{r_}/{b_}; skipping")
            continue
        parsed[(f_, r_, b_)] = {
            "theta": float(theta),
            "beta": [float(x) for x in beta],
            "mu": [float(x) for x in mu],
            "sd": [float(x) for x in sd],
        }
    _LEARNED_CELLS = parsed
    _LEARNED_FEATURE_NAMES = names


def _load_blender():
    """Load blender curated cells. Missing / malformed → empty table (blender
    output is a no-op; caller falls through to selector's pick)."""
    global _BLENDER_CELLS, _BLENDER_FEATURE_NAMES
    try:
        with open(BLENDER_CURATED_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _BLENDER_CELLS = {}
        _BLENDER_FEATURE_NAMES = ()
        return
    names = tuple(data.get("feature_names") or ())
    parsed = {}
    for cell in data.get("cells") or ():
        f_ = cell.get("field")
        r_ = cell.get("regime")
        b_ = cell.get("band")
        beta = cell.get("beta")
        mu = cell.get("mu")
        sd = cell.get("sd")
        if None in (f_, r_, b_, beta, mu, sd):
            continue
        if len(beta) != len(names) + 1 or len(mu) != len(names) or len(sd) != len(names):
            logging.warning(f"  ⚠  l1_blender: shape mismatch on cell "
                            f"{f_}/{r_}/{b_}; skipping")
            continue
        parsed[(f_, r_, b_)] = {
            "beta": [float(x) for x in beta],
            "mu": [float(x) for x in mu],
            "sd": [float(x) for x in sd],
        }
    _BLENDER_CELLS = parsed
    _BLENDER_FEATURE_NAMES = names


_load()
_load_regime_overrides()
_load_learned()
_load_blender()


# v0.6.606 — HRRR PBL morning-overshoot workaround. Named routing gate for
# a specific, diagnosed HRRR failure mode: under stagnant_high conditions,
# HRRR's boundary-layer scheme mixes down aloft warm air too aggressively
# during morning heating hours, overshooting the observed surface temperature
# by 2-3°F at EDT hours 05-07. Pair-log dig 09-13 showed HRRR MAE 2.74-3.40
# vs NBM MAE 0.59-0.67 at these hours today. This is a stop-gap until the
# by-regime walker's escalation clause catches (field=t, regime=stagnant_high,
# band=0-5) via >=500 stagnant t rows accumulating with |lift|>=20%. Reversal:
# set HRRR_PBL_MORNING_OVERSHOOT_KILL = True to disable, or delete the branch.
HRRR_PBL_MORNING_OVERSHOOT_KILL = False
_HRRR_PBL_MORNING_HOURS_LOCAL = (4, 5, 6, 7, 8)  # EDT — brackets the observed 05-07 blowout

# v0.6.640 — First per-obs axis wired into the L1 selector. Stage 0/1 finding
# 2026-09-19 (analysis/h_l1_selector_ims_stage1.py, project_l1_selector_per_obs_axes):
# for h/sea_breeze/24-47h, inter-model spread ims = |forecast_l1 - forecast_raw_nbm|
# carries per-obs picking signal that regime × band alone can't see. Halves-stable
# held-out fit: pick NBM when ims < 13.0, else HRRR default. Train +9.86% / test
# +4.32% MAE lift on 380/381 rows (11.1% of per-obs oracle gap). Overfit guard was
# 0.44× (below the strict 0.5× threshold) — shadow ship first, walker validates
# before flip. Scope intentionally narrow (one cell) — proves the C1→L1 wire
# mechanic; broader deployment gated on this cell's post-deploy pair-log verdict.
IMS_SELECTOR_SHADOW_ENABLED = False   # False = code path exists but does not affect pick
_IMS_SELECTOR_CELLS = {
    # (field, regime, band): (threshold, direction)
    #   direction "H_high" = pick HRRR when ims >= T, NBM when ims < T
    #   direction "H_low"  = pick HRRR when ims <  T, NBM when ims >= T
    ("h", "sea_breeze", "24-47"): (13.0, "H_high"),
    # ch — 10 cells cleared strict Stage 1 on 2026-09-20 (v0.6.641 shadow):
    # test lifts +8 to +22%, capture 25-60% of per-obs oracle gap, all H_low
    # (small ims ⇒ trust HRRR; large ims ⇒ NBM wins the row).
    ("ch", "calm",        "24-47"): (87.0, "H_low"),
    ("ch", "nw_flow",     "12-23"): (66.0, "H_low"),
    ("ch", "pre_frontal", "6-11" ): (82.0, "H_low"),
    ("ch", "pre_frontal", "12-23"): (85.0, "H_low"),
    ("ch", "se_flow",     "6-11" ): (61.0, "H_low"),
    ("ch", "se_flow",     "12-23"): (51.0, "H_low"),
    ("ch", "se_flow",     "24-47"): (56.0, "H_low"),
    ("ch", "sea_breeze",  "24-47"): (85.0, "H_low"),
    ("ch", "sw_flow",     "12-23"): (81.0, "H_low"),
    ("ch", "sw_flow",     "24-47"): (98.0, "H_low"),
}


# v0.6.644 — First LEARNED per-obs classifier wired into the L1 selector.
# Stage 1 v2b (analysis/l1_selector_per_obs_classifier_stage1_v2.py, 2026-09-21):
# 12-feature L2-regularized logistic regression per (regime, band). Leakage-checked
# — dropped cc_disagree because state_obs.cloud_cover is post-hoc. Cleared cells
# emit a β vector + standardization stats + θ*; runtime standardizes the incoming
# feature dict, computes sigmoid(β·x), routes NBM iff P > θ*.
#
# Ships in shadow. LEARNED_SELECTOR_SHADOW_ENABLED = False → override branch inert.
# Flip to True after 7-day pair-log accumulates and retro confirms held-out lift
# replicates on fresh data. Blast radius when flipped: 1 cell today
# (h/nw_flow/24-47h at test +6.50%, capture 19.9%, fNBM 25.8%).
LEARNED_SELECTOR_SHADOW_ENABLED = False


def _sigmoid(z):
    # Clip for numerical stability — matches the classifier's sigmoid.
    if z > 30: return 1.0
    if z < -30: return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def _learned_predict(field, regime, band, features):
    """Compute the classifier's per-obs vote AND probability, independent
    of the shadow flag. Returns (pick, prob) — pick is "nbm"|"hrrr", prob is
    the sigmoid(β·x) value in [0,1]. Returns (None, None) when the classifier
    can't run (cell absent, features missing/incomplete). Consumers can use
    this for shadow telemetry regardless of whether the pick is honored."""
    if features is None:
        return (None, None)
    cell = _LEARNED_CELLS.get((field, regime, band))
    if not cell:
        return (None, None)
    xs = []
    for name in _LEARNED_FEATURE_NAMES:
        v = features.get(name)
        if v is None:
            return (None, None)
        xs.append(float(v))
    mu = cell["mu"]; sd = cell["sd"]; beta = cell["beta"]
    z = beta[0]
    for i, x in enumerate(xs):
        s = sd[i] if sd[i] > 1e-8 else 1.0
        z += beta[i + 1] * ((x - mu[i]) / s)
    prob = _sigmoid(z)
    pick = "nbm" if prob > cell["theta"] else "hrrr"
    return (pick, prob)


def _learned_override(field, regime, band, features):
    """Return the classifier's per-obs vote when SHADOW flag is on; None
    otherwise. Wraps _learned_predict with the live guard so shadow
    telemetry can still fire from consumers that call _learned_predict
    directly regardless of the flag."""
    if not LEARNED_SELECTOR_SHADOW_ENABLED:
        return None
    pick, _ = _learned_predict(field, regime, band, features)
    return pick


def learned_predict(field, regime, band, features):
    """Public entrypoint for shadow telemetry — same as internal _learned_predict.
    Consumers stamp the returned (pick, prob) alongside the actual selector
    source so retro analysis can compare classifier vs pool per row without
    depending on the shadow flag state."""
    return _learned_predict(field, regime, band, features)


# v0.7.0 — L1 blender apply allowlist. Fields listed here have their curated
# cells applied to the served forecast; fields not listed still get shadow
# telemetry stamped (blender_omega runs regardless of this set). Empty set =
# pure shadow (initial v0.7.0 behavior). v0.7.2 (2026-09-24) added "dp" as
# the first progressive-flip field — ROLLED BACK v0.7.3 (2026-09-24) after
# discovering the entire blender curated table was fit on backstamped pair
# log data ending 2026-08-20 (stale GCS backstamp). Fresh-data re-fit of
# analysis/l1_blender_stage1.py showed all 3 dp cells demote (one-window /
# UNSTABLE); 11 of 13 shipped cells fail halves-stable overall. Empty
# frozenset() = pure-shadow until re-curated on live-current data.
BLENDER_APPLIED_FIELDS = frozenset()


def blender_omega(field, regime, band, features):
    """Return ω ∈ [0,1] for this (field, regime, band) if the blender has a
    curated cell for it and all features are present, else None.

    Runs INDEPENDENT of BLENDER_APPLIED_ENABLED — the flag only gates whether
    the caller applies the blend to the served forecast. Shadow telemetry
    calls this directly to stamp forecast_blend_shadow into the pair log
    during the 7-day shadow window regardless of flag state.
    """
    if features is None:
        return None
    cell = _BLENDER_CELLS.get((field, regime, band))
    if not cell:
        return None
    xs = []
    for name in _BLENDER_FEATURE_NAMES:
        v = features.get(name)
        if v is None:
            return None
        xs.append(float(v))
    beta = cell["beta"]; mu = cell["mu"]; sd = cell["sd"]
    z = beta[0]
    for i, x in enumerate(xs):
        s = sd[i] if sd[i] > 1e-8 else 1.0
        z += beta[i + 1] * ((x - mu[i]) / s)
    # clip to [0, 1] — same as the fit-time apply_ridge in analysis.
    if z < 0.0: return 0.0
    if z > 1.0: return 1.0
    return z


def _ims_override(field, regime, band, ims):
    """Return "hrrr" or "nbm" if this cell has an ims-conditioned rule and
    ims is available, else None. Only fires when IMS_SELECTOR_SHADOW_ENABLED
    is True — the flag is a shadow guard, not a kill switch: to enable the
    override live, flip IMS_SELECTOR_SHADOW_ENABLED = True."""
    if not IMS_SELECTOR_SHADOW_ENABLED:
        return None
    if ims is None:
        return None
    rule = _IMS_SELECTOR_CELLS.get((field, regime, band))
    if not rule:
        return None
    threshold, direction = rule
    if direction == "H_high":
        return "hrrr" if ims >= threshold else "nbm"
    else:  # "H_low"
        return "hrrr" if ims < threshold else "nbm"


def pick_source(field, lead_h, regime=None, hour_local=None, ims=None, features=None):
    """Return "hrrr", "nbm", or "nws" for this (field, lead_h[, regime, hour_local, ims, features]).

    Precedence: HRRR PBL morning-overshoot workaround (t only, stagnant_high
    only, morning hours only) → learned per-obs classifier (shadow-guarded,
    NBM-vote only) → ims per-obs override (shadow-guarded) → by-regime walker
    override → band pool pick → HRRR fall-through. HRRR fall-through on any
    missing lookup remains safe (equal to pre-Phase-4 Prod). The
    forecast_snapshot consumer falls back to HRRR if "nws" is returned but the
    {field}_nws value is missing for the hour.
    """
    # HRRR PBL morning-overshoot workaround — see comment block above pick_source.
    if (not HRRR_PBL_MORNING_OVERSHOOT_KILL
            and field == "t"
            and regime == "stagnant_high"
            and hour_local in _HRRR_PBL_MORNING_HOURS_LOCAL):
        return "nbm"
    band_here = _band_for(lead_h)
    # Learned per-obs classifier — first learned model in the picker.
    learned_pick = _learned_override(field, regime, band_here, features) if band_here else None
    if learned_pick is not None:
        return learned_pick
    # ims per-obs override — first per-obs axis wired to the L1 selector (crude threshold).
    ims_pick = _ims_override(field, regime, band_here, ims) if band_here else None
    if ims_pick is not None:
        return ims_pick
    band = band_here
    if band is not None and regime:
        reg_cells = _REGIME_OVERRIDES.get(field, {}).get(regime)
        if reg_cells:
            pick = reg_cells.get(band)
            if pick == "nws" and field not in _NWS_FIELDS_WIRE_ELIGIBLE:
                pick = None  # dp gated — fall through to pool
            if pick in ("nbm", "hrrr", "nws"):
                return pick
    cells = _TABLE.get(field)
    if not cells:
        return "hrrr"
    if band is None:
        return "hrrr"
    return cells.get(band, "hrrr")


def table_meta():
    """Selector table metadata for telemetry (fitted_at + ship-gate summary)."""
    return dict(_META)
