"""Registry of runtime tables the refitter owns.

Each entry: the runtime file name (also its GCS name under runtime_tables/),
the fitter steps that write `out`, a publish guard, and a one-line summary
for the status file. Entries run in order; a later entry sees the tables
earlier entries left in place (published, or the previous copy restored).

A step is {"module", "call"} (call that function) or {"module", "argv"}
(run the module as __main__, as the digest does). `state` lists repo
files a fitter reads back the next day (gate histories); they persist at
runtime_tables/state/<name> and are saved only when the table publishes.

Add a table here only if it is meant to refit on its own. Ship decisions
stay in the repo (see analysis/_candidates.py). The runtime consumer must
read it through weather_collector/runtime_tables.get() or the refit has
no effect.
"""
from weather_collector.processors.ch_persistence_gate import validate_chp_gate as _chp_gate_structure
from weather_collector.processors.cloud_saturation_correction import (
    validate_gate as _lc_gate_structure,
    validate_table as _lc_structure,
)
from weather_collector.processors.l1_selector import (
    validate_learned as _learned_structure,
    validate_regime_walker as _walker_structure,
    validate_table as _selector_structure,
)
from weather_collector.processors.l3_nbm import validate_table as _l3_nbm_structure
from weather_collector.processors.l4_nbm import validate_table as _l4_nbm_structure
from weather_collector.processors.solar_correction import validate_table as _lsr_structure
from weather_collector.processors.sr_sea_breeze_lsr_override import validate_table as _sb_structure

MIN_ROWS_RATIO = 0.5   # refuse a fit that saw < half the rows of the previous one


def _selector_guard(new, prev):
    reason = _selector_structure(new)
    if reason:
        return reason
    fields = set(new["table"])
    if prev:
        missing = set(prev.get("table") or {}) - fields
        if missing:
            return f"fields dropped vs previous: {sorted(missing)}"
        pk, nk = prev.get("n_rows_kept") or 0, new.get("n_rows_kept") or 0
        if pk and nk < MIN_ROWS_RATIO * pk:
            return f"n_rows_kept {nk:,} < {MIN_ROWS_RATIO:.0%} of previous {pk:,}"
        if (new.get("fitted_at") or "") < (prev.get("fitted_at") or ""):
            return f"fitted_at {new.get('fitted_at')} older than previous {prev.get('fitted_at')}"
    if (new.get("n_rows_kept") or 0) < 100_000:
        return f"n_rows_kept {new.get('n_rows_kept')} below 100,000 floor"
    return None


def _selector_summary(new, prev):
    def picks(d):
        return {(f, b): (c or {}).get("source") for f, cells in ((d or {}).get("table") or {}).items()
                for b, c in cells.items()}
    a, b = picks(prev), picks(new)
    changed = sorted(f"{f}/{band}:{a.get((f, band))}→{src}" for (f, band), src in b.items()
                     if a.get((f, band)) not in (None, src))
    return (f"n_rows_kept {new.get('n_rows_kept'):,}, overrides {new.get('override_count')}, "
            f"{len(changed)} pick change(s){': ' + ', '.join(changed) if changed else ''}")


def _rows_guard(structure, rows_key, floor):
    """Guard for a pooled fit: structure OK, ≥ MIN_ROWS_RATIO of the previous
    fit's rows, ≥ floor rows, fitted_at not older than the previous one."""
    def guard(new, prev):
        reason = structure(new)
        if reason:
            return reason
        nk = new.get(rows_key) or 0
        if prev:
            pk = prev.get(rows_key) or 0
            if pk and nk < MIN_ROWS_RATIO * pk:
                return f"{rows_key} {nk:,} < {MIN_ROWS_RATIO:.0%} of previous {pk:,}"
            if (new.get("fitted_at") or "") < (prev.get("fitted_at") or ""):
                return f"fitted_at {new.get('fitted_at')} older than previous {prev.get('fitted_at')}"
        if nk < floor:
            return f"{rows_key} {nk:,} below {floor:,} floor"
        return None
    return guard


def _rows_summary(rows_key):
    def summary(new, prev):
        return f"{rows_key} {new.get(rows_key):,} (previous {(prev or {}).get(rows_key)})"
    return summary


def _guard(structure, stamp, size, size_rule):
    """Generic guard: structure OK, `stamp` not older than the previous
    table's, and `size(table)` not collapsed vs the previous table.
    size_rule "ratio": size ≥ MIN_ROWS_RATIO × previous (row counts).
    size_rule "nonzero": size > 0 whenever previous > 0 (cell sets, which
    can legitimately shrink but never vanish without a human looking)."""
    def guard(new, prev):
        reason = structure(new)
        if reason:
            return reason
        if not prev:
            return None
        if str(new.get(stamp) or "") < str(prev.get(stamp) or ""):
            return f"{stamp} {new.get(stamp)} older than previous {prev.get(stamp)}"
        n, p = size(new), size(prev)
        if size_rule == "ratio" and p and n < MIN_ROWS_RATIO * p:
            return f"size {n:,} < {MIN_ROWS_RATIO:.0%} of previous {p:,}"
        if size_rule == "nonzero" and p and not n:
            return f"empty table (previous had {p})"
        return None
    return guard


def _size_summary(label, size):
    def summary(new, prev):
        return f"{label} {size(new):,} (previous {size(prev) if prev else None})"
    return summary


def _lc_rows(t):
    return sum((c or {}).get("n") or 0 for cells in (t.get("cells") or {}).values() for c in cells.values())


def _lc_ship(t):
    return sum(1 for cells in (t.get("cells") or {}).values() for c in cells.values()
               if (c or {}).get("verdict") == "SHIP")


def _lc_guard(new, prev):
    reason = _guard(_lc_structure, "generated_at", _lc_rows, "ratio")(new, prev)
    if reason or not prev:
        return reason
    missing = set(prev.get("cells") or {}) - set(new.get("cells") or {})
    return f"fields dropped vs previous: {sorted(missing)}" if missing else None


def _n_gate_cells(key):
    def size(t):
        return sum(len(bands) for regs in (t.get(key) or {}).values() for bands in regs.values())
    return size


def _learned_cells(t):
    return len(t.get("cells") or [])


def _lsr_regimes(t):
    return len(t.get("bias_by_regime_hour") or {})


def _sb_hours(t):
    return len(t.get("hourly_bias_wm2") or {}) + 1   # +1: overall bias always present


TABLES = [
    {
        "name": "l1_selector_table_curated.json",
        "out": "weather_collector/data/l1_selector_table_curated.json",
        "steps": [{"module": "analysis.l1_selector_fit", "call": "fit"}],
        "guard": _selector_guard,
        "summary": _selector_summary,
    },
    {   # L3_NBM per-lead bias (live on wg/ch/sr + wd). Goes no-op after 7 days unrefit.
        "name": "l3_nbm_curated.json",
        "out": "weather_collector/data/l3_nbm_curated.json",
        "steps": [{"module": "analysis.l3_nbm_fit", "call": "fit"}],
        "guard": _rows_guard(_l3_nbm_structure, "n_pairs", 100_000),
        "summary": _rows_summary("n_pairs"),
    },
    {   # L4_NBM diurnal residual (live on ch). Goes no-op after 7 days unrefit.
        "name": "l4_nbm_curated.json",
        "out": "weather_collector/data/l4_nbm_curated.json",
        "steps": [{"module": "analysis.l4_nbm_fit", "call": "fit"}],
        "guard": _rows_guard(_l4_nbm_structure, "n_pairs", 10_000),
        "summary": _rows_summary("n_pairs"),
    },
    {   # Lc cloud saturation fit (live on cm/ch). Before the recent-bias gate, which reads it.
        "name": "lc_correction_table.json",
        "out": "weather_collector/data/lc_correction_table.json",
        "steps": [{"module": "analysis.lc_fit", "argv": []}],
        "guard": _lc_guard,
        "summary": lambda new, prev: (f"rows {_lc_rows(new):,}, SHIP cells {_lc_ship(new)} "
                                      f"(previous {_lc_ship(prev) if prev else None})"),
    },
    {   # Lc recent-bias gate (live). Self-gating: 7-day streak in its history file.
        "name": "lc_recent_bias_gate.json",
        "out": "weather_collector/data/lc_recent_bias_gate.json",
        "steps": [{"module": "analysis.h_lc_recent_bias_gate", "argv": []}],
        "state": [".cache_lc_recent_bias_gate_history.json"],
        "guard": _guard(_lc_gate_structure, "generated_at", _n_gate_cells("per_cell"), "nonzero"),
        "summary": lambda new, prev: (f"fields_cleared {new.get('fields_cleared')}, "
                                      f"cells {_n_gate_cells('per_cell')(new)}"),
    },
    {   # Lsr solar bias by regime × hour (live).
        "name": "lsr_bias_table_curated.json",
        "out": "weather_collector/data/lsr_bias_table_curated.json",
        "steps": [{"module": "analysis.l5_recompute_biases_hourly", "argv": []}],
        "guard": _guard(_lsr_structure, "generated_at", _lsr_regimes, "nonzero"),
        "summary": _size_summary("regimes", _lsr_regimes),
    },
    {   # sr sea-breeze clear-sky override (live). `generated` = last sea_breeze obs fitted.
        "name": "sr_sea_breeze_lsr_curated.json",
        "out": "weather_collector/data/sr_sea_breeze_lsr_curated.json",
        "steps": [{"module": "analysis.sr_sea_breeze_lsr_refit_stage2", "argv": []}],
        "guard": _guard(_sb_structure, "generated", _sb_hours, "nonzero"),
        "summary": lambda new, prev: (f"overall {new.get('overall_bias_wm2')} W/m², "
                                      f"{len(new.get('hourly_bias_wm2') or {})} hourly cells, "
                                      f"last obs {new.get('generated')}"),
    },
    {   # chp dynamic per-cell gate (live). Self-gating: 7-day streak in its history file.
        # Reads the live ch_persistence_gate_curated.json (a ship decision, bundled).
        "name": "chp_cell_gate.json",
        "out": "weather_collector/data/chp_cell_gate.json",
        "steps": [{"module": "analysis.h_ch_persistence_blend_stage2_vs_l6", "argv": []},
                  {"module": "analysis.h_chp_cell_gate", "argv": []}],
        "state": [".cache_chp_cell_gate_history.json"],
        "guard": _guard(_chp_gate_structure, "generated_at", _n_gate_cells("per_cell"), "nonzero"),
        "summary": lambda new, prev: (f"{new.get('n_cells_gated_off')} cell(s) gated off: "
                                      f"{new.get('cells_cleared_off')}"),
    },
    {   # Selector regime overrides (live). Self-gating: 3-day streak in its history file.
        "name": "l1_selector_by_regime_walker.json",
        "out": "weather_collector/data/l1_selector_by_regime_walker.json",
        "steps": [{"module": "analysis.l1_selector_fit_by_regime", "argv": []},
                  {"module": "analysis.l1_selector_fit_3way", "argv": []},
                  {"module": "analysis.l1_selector_fit_by_regime_walker", "argv": []}],
        "state": [".cache_l1_selector_by_regime_walker_history.json"],
        "guard": _guard(_walker_structure, "generated_at", _n_gate_cells("per_cell"), "nonzero"),
        "summary": lambda new, prev: (f"cleared nbm {new.get('n_cells_cleared')} / "
                                      f"hrrr {new.get('n_cells_cleared_hrrr')} / "
                                      f"nws {new.get('n_cells_cleared_nws')}"),
    },
    {   # Learned per-obs selector (live on sr). LIVE_DEMOTED in the curate script stays a ship decision.
        "name": "l1_learned_selector_curated.json",
        "out": "weather_collector/data/l1_learned_selector_curated.json",
        "steps": [{"module": "analysis.l1_selector_per_obs_classifier_stage1_v2", "argv": []},
                  {"module": "analysis.l1_selector_per_obs_classifier_stage1_v5", "argv": []},
                  {"module": "analysis.l1_learned_selector_curate", "argv": []}],
        "guard": _guard(_learned_structure, "generated_at", _learned_cells, "nonzero"),
        "summary": lambda new, prev: "cells: " + (", ".join(
            f"{c['field']}/{c['regime']}/{c['band']}" for c in new.get("cells") or []) or "none"),
    },
]
