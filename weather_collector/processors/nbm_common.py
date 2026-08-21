"""Shared NBM-cascade constants + helpers (F8, 2026-08-21).

Central home for per-field correction magnitude caps and the staleness
window used by every NBM applier (l3_nbm, l4_nbm, l5_nbm, l6_nbm). Kept
in its own module so all NBM appliers stay import-light and don't build
a dependency graph on decay_apply's heavier imports.

CAPS values intentionally mirror `decay_apply.CAPS` for now (same physical
bounds per field regardless of source cascade); if a future NBM-side quirk
requires a different limit the divergence lands here.
"""
from datetime import datetime
from pathlib import Path

# Per-field sanity caps on |correction| in the field's native units. A
# pathological fit cannot move the NBM-side forecast more than this
# regardless of what the curated JSON says.
CAPS_NBM = {
    "t":  5.0,    # °F
    "dp": 5.0,    # °F
    "h":  20.0,   # %
    "ws": 10.0,   # mph
    "wg": 15.0,   # mph
    "cc": 40.0,   # %
    "sr": 300.0,  # W/m²
    "ch": 40.0,   # % high cloud
    # wd handled circularly by the sin/cos branch; no scalar cap.
}

# Days after `fitted_at` before an NBM curated JSON is considered stale
# and its applier switches to identity (no-op). Matches HRRR STALE_DAYS
# in decay_apply. When stale, the applier logs a warning at load time.
STALE_DAYS_NBM = 7


def cap_correction(field, correction):
    """Clamp |correction| to CAPS_NBM.get(field, inf). Returns the signed
    corrected value. Fields without a cap pass through unchanged."""
    cap = CAPS_NBM.get(field)
    if cap is None or correction is None:
        return correction
    if correction > cap:
        return cap
    if correction < -cap:
        return -cap
    return correction


def is_stale(fitted_at):
    """Return True if `fitted_at` (ISO local naive minute string like
    '2026-08-21T22:00') is older than STALE_DAYS_NBM. Missing / unparseable
    → False (fail-safe: keep applying rather than silently going dormant)."""
    if not fitted_at:
        return False
    try:
        fdt = datetime.strptime(fitted_at[:16], "%Y-%m-%dT%H:%M")
    except (ValueError, TypeError):
        return False
    age_days = (datetime.utcnow() - fdt).total_seconds() / 86400.0
    return age_days > STALE_DAYS_NBM
