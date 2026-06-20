"""
Pair-log-based backtest replay — conditional-layer extension.

Sibling of `backtest/replay.py`. Adds L5 (regime-conditional, currently solar)
and L6 (regime-transition treatment, not yet shipped) evaluation on top of the
existing L1-L4 layer-pick logic.

Step 1 scope (this file's initial state):
  - L1-L4 layer-pick delegates to `replay._pick_forecast` — identical results
    to the L3/L4 sweep machinery when L5 / L6 are off.
  - L5 / L6 hooks exist but are stubs (no-op). Next steps will populate them
    with real treatment math.

This file's contract:
  evaluate_conditional_config({"L3_FIELDS": ..., "L4_FIELDS": ...,
                               "L5_ENABLED": False, "L6_FIELDS": set(),
                               "L6_TREATMENT": "none"})
  produces the SAME per-field MAE numbers as
  evaluate_config({"L3_FIELDS": ..., "L4_FIELDS": ...}) when L5/L6 are off.

Future steps will add:
  - L5 transformation (currently `solar_correction.py`, regime-keyed bias table)
  - L6 treatment families: "widen_confidence", "l1_fallback", "regime_bias"
  - Bias + Brier metrics alongside MAE
  - Regime stratification (filter pairs by state_fc.regime_synoptic before scoring)
"""
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from analysis._cache import cached_path
from backtest.replay import _pick_forecast, _stream_pairs
from weather_collector.processors.solar_correction import (
    compute_solar_correction,
    SUN_UP_THRESHOLD,
)


PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"

# Lead-time bands. Mirrors analysis/regime_transition_audit.py and the walk-
# forward validator's bucketing — the same partition R6's signal was measured
# in. Used for band-aware regime_bias cells.
_BANDS = [
    ("0-5h",   0, 6),
    ("6-11h",  6, 12),
    ("12-23h", 12, 24),
    ("24-47h", 24, 48),
]


def _band_for_lead(lead_h):
    """Map a lead_h value to its band label, or None if lead_h is missing or
    outside the known bands."""
    if lead_h is None:
        return None
    for label, lo, hi in _BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def _iter_cached_pairs(test_days):
    """Iterate pairs within the last `test_days` window, reading from the
    on-disk cache via analysis._cache. Re-callable cheaply for sweeps —
    subsequent calls read from disk (no network) until the cache ages out
    of the 12-hour TTL or MYWEATHER_REFRESH=1 forces a refetch.

    Mirrors the time-window filter in `backtest.replay._stream_pairs` so
    the L5/L6 numbers stay comparable to the existing replay.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=test_days)).strftime("%Y-%m-%dT%H:%M")
    path = cached_path(PAIR_LOG_URL)
    with open(path) as f:
        for line in f:
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (r.get("obs_time") or "") >= cutoff:
                yield r


# Treatment family identifiers for L6. "none" is the no-op default.
L6_TREATMENTS = ("none", "widen_confidence", "l1_fallback", "regime_bias")

# Fields that L5 applies to. Currently only solar radiation. If solar_correction
# ever expands to other fields, add them here AND verify the bias tables exist.
L5_FIELDS = {"sr"}


def _apply_l5(pair, layer_value, config):
    """L5 (regime-conditional solar correction). Mirrors what
    `weather_collector/processors/solar_correction.py` would apply if
    ENABLED=True flipped on.

    Adds a regime-keyed Δ W/m² to the L1-L4 layer value when:
      - config["L5_ENABLED"] is True
      - pair's field is in L5_FIELDS (solar only)
      - lead_h ≥ 1 (skip the trivial nowcast pair — matches simulate_windows)
      - raw L1 solar ≥ SUN_UP_THRESHOLD (night suppression)
      - state_fc.regime_synoptic and state_fc.hour_local are present

    Hour source is `state_fc.hour_local` (not parsed from obs_time) to match
    the live `solar_correction.stamp_solar_correction` semantics AND the
    `simulate_windows.py` audit, which both pull hour from the regime
    classifier's state metadata.

    Returns (new_value, "l5") on apply, (layer_value, None) on no-op.
    """
    if not config.get("L5_ENABLED", False):
        return layer_value, None
    field = pair.get("field")
    if field not in L5_FIELDS:
        return layer_value, None

    lead = pair.get("lead_h")
    if lead is None or lead < 1:
        return layer_value, None

    raw_l1 = pair.get("forecast_l1")
    if raw_l1 is None or raw_l1 < SUN_UP_THRESHOLD:
        return layer_value, None

    state_fc = pair.get("state_fc") or {}
    regime = state_fc.get("regime_synoptic")
    if regime is None:
        return layer_value, None

    hour_local = state_fc.get("hour_local")
    delta = compute_solar_correction(regime, raw_l1, hour_local=hour_local)
    if delta == 0.0:
        return layer_value, None
    return layer_value + delta, "l5"


def _apply_l6(pair, layer_value, config):
    """L6 (regime-transition treatment). Detects transition pairs by comparing
    state_fc.regime_synoptic to state_obs.regime_synoptic; on mismatch, applies
    the configured treatment.

    Dispatch:
      - "none"            — no-op (default)
      - "l1_fallback"     — blend toward raw L1 forecast by L6_FALLBACK_BLEND
                            (0.0 = full L1 revert, 1.0 = no fallback / no-op)
      - "widen_confidence"— stub (UI-side; no value change. Returns layer_value
                            with "l6" label so layer_dist counts transition
                            pairs even when MAE math is identical.)
      - "regime_bias"     — stub (needs (regime_fc, regime_obs) bias table built
                            from pair log; deferred to a later step).

    Returns (new_value, "l6") on apply, (layer_value, None) on no-op.
    """
    field = pair.get("field")
    treatment = config.get("L6_TREATMENT", "none")
    l6_fields = config.get("L6_FIELDS", set())
    if treatment == "none" or field not in l6_fields:
        return layer_value, None

    state_fc = pair.get("state_fc") or {}
    state_obs = pair.get("state_obs") or {}
    rfc = state_fc.get("regime_synoptic")
    rob = state_obs.get("regime_synoptic")
    if not rfc or not rob:
        # Without both regime labels we can't classify transition-ness; no-op
        # preserves the baseline behavior so missing-metadata pairs don't poison
        # the MAE calculation.
        return layer_value, None
    if rfc == rob:
        # Stable-regime pair — L6 is a no-op by design (treatment targets only
        # the transition subset where L2/L3/L4 over-correct).
        return layer_value, None

    if treatment == "l1_fallback":
        raw_l1 = pair.get("forecast_l1")
        if raw_l1 is None:
            return layer_value, None
        blend = float(config.get("L6_FALLBACK_BLEND", 0.0))
        # blend = 0.0 → full L1 revert; blend = 1.0 → keep the layer value.
        new_value = blend * layer_value + (1.0 - blend) * raw_l1
        return new_value, "l6"

    if treatment == "widen_confidence":
        # UI-side treatment; no change to the forecast value. Return the layer
        # value but tag as l6 so layer_dist counts the transition pairs that
        # would have gotten a wider band in the live system.
        return layer_value, "l6"

    if treatment == "regime_bias":
        # Look up the (field, rfc, rob[, band]) bias. The table's `_band_aware`
        # tag (set by build_regime_bias_table) selects which key shape to use.
        # If no table is present or the cell isn't covered, return no-op.
        table = config.get("L6_REGIME_BIAS_TABLE") or {}
        if table.get("_band_aware"):
            band = _band_for_lead(pair.get("lead_h"))
            if band is None:
                return layer_value, None
            bias = table.get((field, rfc, rob, band))
        else:
            bias = table.get((field, rfc, rob))
        if bias is None:
            return layer_value, None
        return layer_value - bias, "l6"

    # Unknown treatment string — no-op (safe default).
    return layer_value, None


def _pick_forecast_conditional(pair, config):
    """Choose the forecast value for this pair given an extended config that
    may include L5/L6 hooks.

    Returns (forecast_value, layer_label). Layer label reflects the LAST hook
    that produced a value (l6 > l5 > l4 > l3 > l2 > l1 > raw), so layer_dist
    counts surface where each pair was decided.
    """
    base_value, base_layer = _pick_forecast(pair, config)
    if base_value is None:
        return None, None
    after_l5, l5_label = _apply_l5(pair, base_value, config)
    after_l6, l6_label = _apply_l6(pair, after_l5, config)
    # Last hook that fired wins the label. Stubs return their label even when
    # they don't change the value — that's intentional so we can verify the
    # wiring before any math goes in.
    label = l6_label or l5_label or base_layer
    return after_l6, label


def evaluate_conditional_config(config, test_days=2, pairs_iter=None):
    """Per-field MAE for `config` on the last `test_days` of pair log.

    Mirrors `replay.evaluate_config` but routes pairs through the conditional
    pick that adds L5/L6 hooks. Identical output to `evaluate_config` when
    L5_ENABLED is False and L6_FIELDS is empty (the step-1 contract).

    When `pairs_iter` is None (the default), pairs are loaded via the on-disk
    cache (`_iter_cached_pairs`). Pass an iterable explicitly when you want to
    score multiple configs against the same materialized pair list — cheaper
    than re-iterating the cache file N times for an N-config sweep.
    """
    per_field = defaultdict(lambda: {"n": 0, "sum_abs_err": 0.0, "layer_dist": defaultdict(int)})
    total = 0
    pairs = pairs_iter if pairs_iter is not None else _iter_cached_pairs(test_days)
    for pair in pairs:
        field = pair.get("field")
        obs = pair.get("observed")
        if field is None or obs is None:
            continue
        fc, layer = _pick_forecast_conditional(pair, config)
        if fc is None:
            continue
        per_field[field]["n"] += 1
        per_field[field]["sum_abs_err"] += abs(fc - obs)
        per_field[field]["layer_dist"][layer] += 1
        total += 1

    result_per_field = {}
    for field, stats in per_field.items():
        result_per_field[field] = {
            "n":   stats["n"],
            "mae": round(stats["sum_abs_err"] / stats["n"], 4) if stats["n"] else None,
            "layer_dist": dict(stats["layer_dist"]),
        }
    return {
        "config": {
            "L3_FIELDS":          sorted(config.get("L3_FIELDS", [])),
            "L4_FIELDS":          sorted(config.get("L4_FIELDS", [])),
            "L5_ENABLED":         bool(config.get("L5_ENABLED", False)),
            "L6_FIELDS":          sorted(config.get("L6_FIELDS", [])),
            "L6_TREATMENT":       config.get("L6_TREATMENT", "none"),
            "L6_FALLBACK_BLEND":  float(config.get("L6_FALLBACK_BLEND", 0.0)),
        },
        "per_field": result_per_field,
        "test_days": test_days,
        "total_pairs": total,
    }


def evaluate_configs_streamed(configs, test_days=2):
    """Score N configs against the same pair window in a single cache pass.

    For sweeps where you want to A/B/C/... many candidates, this is much
    faster than calling `evaluate_conditional_config` N times: each cached
    pair row is read once and scored against every config.

    Args:
      configs: list of (name, config_dict) tuples — the name is echoed in
               the result for easy table-building.
      test_days: window size in days.

    Returns a list of {name, per_field, total_pairs, config} dicts in the
    same order as `configs`.
    """
    # Per-config accumulators. Indexed by config slot.
    accs = [defaultdict(lambda: {"n": 0, "sum_abs_err": 0.0,
                                  "layer_dist": defaultdict(int)})
            for _ in configs]
    totals = [0 for _ in configs]

    for pair in _iter_cached_pairs(test_days):
        field = pair.get("field")
        obs = pair.get("observed")
        if field is None or obs is None:
            continue
        for i, (_name, cfg) in enumerate(configs):
            fc, layer = _pick_forecast_conditional(pair, cfg)
            if fc is None:
                continue
            slot = accs[i][field]
            slot["n"] += 1
            slot["sum_abs_err"] += abs(fc - obs)
            slot["layer_dist"][layer] += 1
            totals[i] += 1

    out = []
    for (name, cfg), acc, total in zip(configs, accs, totals):
        per_field = {}
        for field, stats in acc.items():
            per_field[field] = {
                "n":   stats["n"],
                "mae": round(stats["sum_abs_err"] / stats["n"], 4) if stats["n"] else None,
                "layer_dist": dict(stats["layer_dist"]),
            }
        out.append({
            "name": name,
            "config": {
                "L3_FIELDS":         sorted(cfg.get("L3_FIELDS", [])),
                "L4_FIELDS":         sorted(cfg.get("L4_FIELDS", [])),
                "L5_ENABLED":        bool(cfg.get("L5_ENABLED", False)),
                "L6_FIELDS":         sorted(cfg.get("L6_FIELDS", [])),
                "L6_TREATMENT":      cfg.get("L6_TREATMENT", "none"),
                "L6_FALLBACK_BLEND": float(cfg.get("L6_FALLBACK_BLEND", 0.0)),
            },
            "per_field": per_field,
            "test_days": test_days,
            "total_pairs": total,
        })
    return out


def build_regime_bias_table(fields, train_window=(7, 14), min_n=30,
                            base_config=None, band_aware=False):
    """Build a regime-bias lookup table for L6 regime_bias treatment.

    Cell key shape:
      - `band_aware=False`: (field, rfc, rob)             — 3-tuple, default
      - `band_aware=True`:  (field, rfc, rob, band_label) — 4-tuple

    Per-band cells slice the transition pairs by lead band (matches the
    R6 audit's bucketing). 4× more cells but each more homogeneous —
    R6 showed wg transition penalty +56% at 0-5h vs +13% at 12-23h, so
    a single average per (rfc, rob) blends those into noise.

    train_window is (days_ago_end, days_ago_start) — so (7, 14) means "pairs
    older than 7 days and newer than 14 days." That keeps the training window
    strictly before the typical 7-day test window.

    Cells with fewer than `min_n` training pairs are dropped — single-digit
    samples produce unstable means that hurt more than they help.

    The table is tagged with `_band_aware` so `_apply_l6` knows which key
    shape to look up at apply time.
    """
    if base_config is None:
        base_config = {}
    target_fields = set(fields)
    now_utc = datetime.now(timezone.utc)
    end_cutoff = (now_utc - timedelta(days=train_window[0])).strftime("%Y-%m-%dT%H:%M")
    start_cutoff = (now_utc - timedelta(days=train_window[1])).strftime("%Y-%m-%dT%H:%M")

    accs = defaultdict(lambda: [0.0, 0])
    path = cached_path(PAIR_LOG_URL)
    with open(path) as f:
        for line in f:
            if not line:
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            ot = p.get("obs_time") or ""
            if not (start_cutoff <= ot < end_cutoff):
                continue
            field = p.get("field")
            if field not in target_fields:
                continue
            obs = p.get("observed")
            if obs is None:
                continue
            sfc = p.get("state_fc") or {}
            sob = p.get("state_obs") or {}
            rfc = sfc.get("regime_synoptic")
            rob = sob.get("regime_synoptic")
            if not rfc or not rob or rfc == rob:
                continue
            if band_aware:
                band = _band_for_lead(p.get("lead_h"))
                if band is None:
                    continue
                key = (field, rfc, rob, band)
            else:
                key = (field, rfc, rob)
            fc, _layer = _pick_forecast_conditional(p, base_config)
            if fc is None:
                continue
            accs[key][0] += (fc - obs)
            accs[key][1] += 1

    table = {}
    for cell, (sum_err, n) in accs.items():
        if n < min_n:
            continue
        table[cell] = sum_err / n
    # Tag the table with its key shape so the applier knows what to look up.
    # Using a sentinel key (None tuple component) avoids polluting the cell
    # keyspace and survives dict iteration.
    table["_band_aware"] = band_aware
    return table


def build_regime_bias_table_around(reference_date, fields, train_window=(7, 28),
                                    min_n=30, base_config=None, band_aware=False,
                                    shrinkage_k=0.0):
    """Same as build_regime_bias_table but with the training window anchored to
    `reference_date` (a datetime.date) instead of "now."

    Used by per-cutoff evaluators that need a separate, leakage-free training
    window per cutoff. (today − 7d) anchor reproduces the original behavior.

    shrinkage_k > 0 applies James-Stein-style shrinkage toward zero:
    cell_bias = (sum_err / n) * (n / (n + shrinkage_k))
    Cells with low n get pulled toward zero (the conservative null); cells
    with high n keep most of their estimated bias. shrinkage_k=0 = no shrinkage
    (the unregularized estimator that lost the 5/7 cutoffs earlier tonight).
    """
    if base_config is None:
        base_config = {}
    target_fields = set(fields)
    # Anchor cutoffs are date-only; convert to midnight UTC for the ISO compare.
    end_cutoff = (reference_date - timedelta(days=train_window[0])).strftime("%Y-%m-%dT%H:%M")
    start_cutoff = (reference_date - timedelta(days=train_window[1])).strftime("%Y-%m-%dT%H:%M")

    accs = defaultdict(lambda: [0.0, 0])
    path = cached_path(PAIR_LOG_URL)
    with open(path) as f:
        for line in f:
            if not line:
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            ot = p.get("obs_time") or ""
            if not (start_cutoff <= ot < end_cutoff):
                continue
            field = p.get("field")
            if field not in target_fields:
                continue
            obs = p.get("observed")
            if obs is None:
                continue
            sfc = p.get("state_fc") or {}
            sob = p.get("state_obs") or {}
            rfc = sfc.get("regime_synoptic")
            rob = sob.get("regime_synoptic")
            if not rfc or not rob or rfc == rob:
                continue
            if band_aware:
                band = _band_for_lead(p.get("lead_h"))
                if band is None:
                    continue
                key = (field, rfc, rob, band)
            else:
                key = (field, rfc, rob)
            fc, _layer = _pick_forecast_conditional(p, base_config)
            if fc is None:
                continue
            accs[key][0] += (fc - obs)
            accs[key][1] += 1

    table = {}
    for cell, (sum_err, n) in accs.items():
        if n < min_n:
            continue
        raw_bias = sum_err / n
        if shrinkage_k > 0:
            # James-Stein shrinkage toward zero. n/(n+k) gradient: as n grows
            # the multiplier approaches 1 (no shrinkage); as n shrinks toward
            # min_n the multiplier shrinks the bias proportionally.
            shrunk = raw_bias * n / (n + shrinkage_k)
            table[cell] = shrunk
        else:
            table[cell] = raw_bias
    table["_band_aware"] = band_aware
    return table


def evaluate_configs_per_cutoff_dynamic(config_factories, n_cutoffs=7, window_days=7):
    """Per-cutoff sweep where each cutoff gets a freshly-built config.

    `config_factories` is a list of (name, factory) tuples where each factory
    takes a cutoff `date` and returns a config dict. This enables per-cutoff
    regime_bias tables built strictly older than that cutoff's test window —
    eliminating the train/test leakage that contaminates a single-table sweep
    on older cutoffs.

    Returns the same shape as `evaluate_configs_per_cutoff`.
    """
    today_utc = datetime.now(timezone.utc).date()
    cutoffs = [today_utc - timedelta(days=(n_cutoffs - 1 - i)) for i in range(n_cutoffs)]

    # Materialize each cutoff's config once (so factories that build bias
    # tables don't re-stream the pair log inside the main scoring loop).
    cutoff_configs = []
    for c in cutoffs:
        cfg_row = []
        for name, factory in config_factories:
            cfg_row.append((name, factory(c)))
        cutoff_configs.append(cfg_row)

    # accs[cfg_idx][cutoff_idx][field] = stats
    n_cfgs = len(config_factories)
    accs = [[defaultdict(lambda: {"n": 0, "sum_abs_err": 0.0,
                                   "layer_dist": defaultdict(int)})
             for _ in cutoffs] for _ in range(n_cfgs)]
    totals = [[0 for _ in cutoffs] for _ in range(n_cfgs)]

    earliest_start = cutoffs[0] - timedelta(days=window_days)
    earliest_start_str = earliest_start.strftime("%Y-%m-%d")

    path = cached_path(PAIR_LOG_URL)
    with open(path) as f:
        for line in f:
            if not line:
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            obs_time = p.get("obs_time") or ""
            if obs_time[:10] < earliest_start_str:
                continue
            obs_date_str = obs_time[:10]
            applicable = []
            for ci, c in enumerate(cutoffs):
                if (c - timedelta(days=window_days)).strftime("%Y-%m-%d") <= obs_date_str <= c.strftime("%Y-%m-%d"):
                    applicable.append(ci)
            if not applicable:
                continue
            field = p.get("field")
            obs = p.get("observed")
            if field is None or obs is None:
                continue
            for ci in applicable:
                for cfg_idx in range(n_cfgs):
                    _name, cfg = cutoff_configs[ci][cfg_idx]
                    fc, layer = _pick_forecast_conditional(p, cfg)
                    if fc is None:
                        continue
                    err = abs(fc - obs)
                    slot = accs[cfg_idx][ci][field]
                    slot["n"] += 1
                    slot["sum_abs_err"] += err
                    slot["layer_dist"][layer] += 1
                    totals[cfg_idx][ci] += 1

    out = []
    for cfg_idx, (name, _) in enumerate(config_factories):
        per_cutoff = []
        for ci, c in enumerate(cutoffs):
            per_field = {}
            for field, stats in accs[cfg_idx][ci].items():
                per_field[field] = {
                    "n":   stats["n"],
                    "mae": round(stats["sum_abs_err"] / stats["n"], 4) if stats["n"] else None,
                    "layer_dist": dict(stats["layer_dist"]),
                }
            per_cutoff.append({
                "cutoff": c.strftime("%Y-%m-%d"),
                "per_field": per_field,
                "total_pairs": totals[cfg_idx][ci],
            })
        out.append({
            "name": name,
            "per_cutoff": per_cutoff,
        })
    return out


def evaluate_configs_per_cutoff(configs, n_cutoffs=7, window_days=7):
    """N-cutoff × N-config sweep — mirrors `analysis/simulate_windows.py`.

    For each of the last `n_cutoffs` trailing daily cutoffs, score every config
    against the trailing `window_days` of pair data ending at that cutoff.
    Used to check stability of an L6 (or L5) verdict across days.

    Returns a list of dicts shaped:
      [{name, config, per_cutoff: [{cutoff, per_field: {...}, total_pairs}, ...]}, ...]
    """
    today_utc = datetime.now(timezone.utc).date()
    cutoffs = [today_utc - timedelta(days=(n_cutoffs - 1 - i)) for i in range(n_cutoffs)]
    # Pre-compute per-cutoff string cutoffs for the window's lower bound. A pair
    # with obs_date d contributes to cutoff c iff (c - window_days) <= d <= c.
    # Earliest start = (earliest cutoff - window_days). Skip pairs older than
    # that to avoid a full second pass on irrelevant data.
    earliest_start = cutoffs[0] - timedelta(days=window_days)
    earliest_start_str = earliest_start.strftime("%Y-%m-%d")
    # Per-config per-cutoff accumulators: accs[cfg_idx][cutoff_idx][field] = stats
    accs = [[defaultdict(lambda: {"n": 0, "sum_abs_err": 0.0,
                                   "layer_dist": defaultdict(int)})
             for _ in cutoffs]
            for _ in configs]
    totals = [[0 for _ in cutoffs] for _ in configs]

    # Stream the cache once; for each row, derive obs_date once, then iterate
    # configs × applicable-cutoffs inside the tight loop.
    path = cached_path(PAIR_LOG_URL)
    with open(path) as f:
        for line in f:
            if not line:
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            obs_time = p.get("obs_time") or ""
            if obs_time[:10] < earliest_start_str:
                continue
            obs_date_str = obs_time[:10]
            # Bucket of cutoff indices this pair contributes to. obs_date must
            # be <= cutoff and >= (cutoff - window_days).
            applicable = []
            for ci, c in enumerate(cutoffs):
                if (c - timedelta(days=window_days)).strftime("%Y-%m-%d") <= obs_date_str <= c.strftime("%Y-%m-%d"):
                    applicable.append(ci)
            if not applicable:
                continue
            field = p.get("field")
            obs = p.get("observed")
            if field is None or obs is None:
                continue
            for cfg_idx, (_name, cfg) in enumerate(configs):
                fc, layer = _pick_forecast_conditional(p, cfg)
                if fc is None:
                    continue
                err = abs(fc - obs)
                for ci in applicable:
                    slot = accs[cfg_idx][ci][field]
                    slot["n"] += 1
                    slot["sum_abs_err"] += err
                    slot["layer_dist"][layer] += 1
                    totals[cfg_idx][ci] += 1

    out = []
    for (name, cfg), per_cfg_accs, per_cfg_totals in zip(configs, accs, totals):
        per_cutoff = []
        for ci, c in enumerate(cutoffs):
            per_field = {}
            for field, stats in per_cfg_accs[ci].items():
                per_field[field] = {
                    "n":   stats["n"],
                    "mae": round(stats["sum_abs_err"] / stats["n"], 4) if stats["n"] else None,
                    "layer_dist": dict(stats["layer_dist"]),
                }
            per_cutoff.append({
                "cutoff": c.strftime("%Y-%m-%d"),
                "per_field": per_field,
                "total_pairs": per_cfg_totals[ci],
            })
        out.append({
            "name": name,
            "config": {
                "L3_FIELDS":         sorted(cfg.get("L3_FIELDS", [])),
                "L4_FIELDS":         sorted(cfg.get("L4_FIELDS", [])),
                "L5_ENABLED":        bool(cfg.get("L5_ENABLED", False)),
                "L6_FIELDS":         sorted(cfg.get("L6_FIELDS", [])),
                "L6_TREATMENT":      cfg.get("L6_TREATMENT", "none"),
                "L6_FALLBACK_BLEND": float(cfg.get("L6_FALLBACK_BLEND", 0.0)),
            },
            "per_cutoff": per_cutoff,
        })
    return out


def compare_conditional_configs(baseline, candidate, test_days=2):
    """A/B two conditional configs against the same held-out window."""
    a = evaluate_conditional_config(baseline, test_days=test_days)
    b = evaluate_conditional_config(candidate, test_days=test_days)

    rows = []
    all_fields = sorted(set(a["per_field"]) | set(b["per_field"]))
    for f in all_fields:
        a_mae = a["per_field"].get(f, {}).get("mae")
        b_mae = b["per_field"].get(f, {}).get("mae")
        n     = a["per_field"].get(f, {}).get("n") or b["per_field"].get(f, {}).get("n") or 0
        if a_mae is None or b_mae is None:
            verdict, delta, pct = "missing", None, None
        else:
            delta = round(b_mae - a_mae, 4)
            pct = round(100 * delta / a_mae, 2) if a_mae else None
            if abs(pct or 0) < 1.0:
                verdict = "tie (~)"
            elif delta < 0:
                verdict = "candidate wins"
            else:
                verdict = "baseline wins"
        rows.append({
            "field": f, "n": n,
            "baseline_mae": a_mae, "candidate_mae": b_mae,
            "delta": delta, "pct": pct, "verdict": verdict,
        })
    return {"baseline": a, "candidate": b, "comparison": rows}
