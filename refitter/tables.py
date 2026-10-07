"""Registry of runtime tables the refitter owns.

Each entry: the runtime file name (also its GCS name under runtime_tables/),
the fitter module + function that writes `out`, a publish guard, and a
one-line summary for the status file.

Add a table here only if it is meant to refit on its own. Ship decisions
stay in the repo. The runtime consumer must read it through
weather_collector/runtime_tables.get() or the refit has no effect.
"""
from weather_collector.processors.l1_selector import validate_table as _selector_structure
from weather_collector.processors.l3_nbm import validate_table as _l3_nbm_structure
from weather_collector.processors.l4_nbm import validate_table as _l4_nbm_structure

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


TABLES = [
    {
        "name": "l1_selector_table_curated.json",
        "out": "weather_collector/data/l1_selector_table_curated.json",
        "module": "analysis.l1_selector_fit",
        "call": "fit",
        "guard": _selector_guard,
        "summary": _selector_summary,
    },
    {   # L3_NBM per-lead bias (live on wg/ch/sr + wd). Goes no-op after 7 days unrefit.
        "name": "l3_nbm_curated.json",
        "out": "weather_collector/data/l3_nbm_curated.json",
        "module": "analysis.l3_nbm_fit",
        "call": "fit",
        "guard": _rows_guard(_l3_nbm_structure, "n_pairs", 100_000),
        "summary": _rows_summary("n_pairs"),
    },
    {   # L4_NBM diurnal residual (live on ch). Goes no-op after 7 days unrefit.
        "name": "l4_nbm_curated.json",
        "out": "weather_collector/data/l4_nbm_curated.json",
        "module": "analysis.l4_nbm_fit",
        "call": "fit",
        "guard": _rows_guard(_l4_nbm_structure, "n_pairs", 10_000),
        "summary": _rows_summary("n_pairs"),
    },
]
