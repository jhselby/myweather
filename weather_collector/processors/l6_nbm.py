"""L6_NBM apply-time processor (option-1 Phase 7, 2026-08-21).

Mirrors HRRR's L6 (`cove_correction.py`) on the NBM cascade — t-only
regime × wind-octant × hour-of-day cove microclimate correction.

Shape-only mirror: ENABLED=False today, `l6_nbm_correction(...)` returns
0.0 unconditionally. HRRR L6 has been disabled since 2026-07-01 after
per-row Production data exposed both cooling and warming branches as
double-counting L2's waterfront-weighted Kalman blend (see
`cove_correction.py` for the full incident). Whether the same
double-count applies to the NBM cascade is a separate investigation;
until it's answered, L6_NBM is dormant scaffold with the parallel slot
wired so the layer exists in error_log + selector chain and can be
enabled by a single flag flip once the fit against L5_NBM baseline
lands.

Scope: t only. t is not in `L4_NBM_FIELDS` (cc/ch) and not `sr`, so on
the NBM cascade the t layer stack when enabled would be:
    t_raw_nbm → t_l2_nbm → t_l3_nbm → t_l6_nbm
(skips L4_NBM and L5_NBM by design, matching HRRR t which also skips
L4 and L5).

Applied inside `forecast_snapshot.stamp()` right after the L5_NBM block,
per hour. Because ENABLED=False and the correction is a no-op, the
apply block does not stamp `t_l6_nbm` today; the branch exists so
future enablement is a one-line flip.

Curated table stub lives at `weather_collector/data/l6_nbm_cove_curated.json`;
`analysis/l6_nbm_fit.py` refits (sb_active × octant × hour) means from
the pair log's `error_l3_nbm` for t once we choose to enable.
"""
from datetime import datetime

import pytz


TZ = pytz.timezone("America/New_York")

# Shape-only mirror shipped disabled; flip to True only after fitting
# against the NBM-side L5 baseline and confirming the HRRR double-count
# reason does not apply to the NBM cascade.
ENABLED = False

L6_NBM_FIELDS = ("t",)

_OCTANTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _octant(wind_dir_deg):
    if wind_dir_deg is None:
        return None
    return _OCTANTS[int((wind_dir_deg + 22.5) % 360 / 45)]


def l6_nbm_correction(wind_dir_deg, sb_active, hour_local):
    """Signed Δ°F to ADD to `t_l3_nbm`. Returns 0.0 today; shape-only
    mirror of `cove_correction.compute_cove_correction` scaffolded for
    the NBM cascade. Fit + enablement gated on the separate
    "does NBM L2 double-count waterfront" investigation."""
    if not ENABLED:
        return 0.0
    if wind_dir_deg is None or hour_local is None:
        return 0.0
    if _octant(wind_dir_deg) is None:
        return 0.0
    # Table lookup lands here when enablement path opens. Kept as 0.0
    # today so the apply block stays a strict no-op even if a caller
    # invokes the function directly.
    return 0.0


def _sb_active_forecast(hour_local, wind_dir_deg):
    """Coarse sb-active proxy for future NBM leads. Matches
    `cove_correction._sb_active_forecast` — sea breeze fires 13-18 EDT
    with S-half wind."""
    if hour_local is None or wind_dir_deg is None:
        return False
    if not (13 <= hour_local <= 18):
        return False
    return _octant(wind_dir_deg) in {"S", "SE", "SW"}


def describe_applicability():
    """F7 (2026-08-21) — applicability descriptor for L6_NBM (scaffold)."""
    return [{
        "layer_id": "L6_NBM",
        "name": "NBM cove (regime × octant × hour) correction",
        "category": "nbm-cascade",
        "stale": False,
        "fields": [{
            "field": "t",
            "fires_when": ("shape-only scaffold — ENABLED=False; enablement gated on "
                           "'does NBM L2 double-count waterfront?' investigation"),
            "gated_by": "ENABLED flag + NBM L2 double-count investigation",
            "current_state": ("enabled — firing per curated table" if ENABLED
                              else "dormant — apply is a strict no-op"),
        }],
    }]
