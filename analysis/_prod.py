"""Reconstruct real production residual from a pair-log row.

The pair log's top-level `error` field is L2 residual by design — snapshot
sets `entry[field] = entry[f"{field}_l2"]` at forecast_snapshot.py:246-249
so the Fitter can calibrate decay coefficients from `forecast - obs`. See
`feedback_top_level_forecast_is_l2`.

Any analysis script scoring "what the user saw" must reconstruct from
`error_{applied_layer}` — the applied-layer stamp records which layer's
value was actually served. Fall back to `error_l4` when the stamp is
missing (pre-v0.6.269 rows, aged out by end of July 2026), then to
top-level `error` as a last resort.
"""


def prod_error(row):
    """Return the real production residual for a pair-log row, or None.

    Prefers `error_{applied_layer}`, falls back to `error_l4`, then to
    top-level `error`. Never returns the L2 residual when a deeper layer
    is available."""
    applied = row.get("applied_layer")
    if applied:
        v = row.get(f"error_{applied}")
        if v is not None:
            return v
    v = row.get("error_l4")
    if v is not None:
        return v
    return row.get("error")
