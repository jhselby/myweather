"""
State-stratified accuracy (Fitter helper, v0.6.48): slice forecast MAE by
observed/forecast state to find dimensions worth correcting for. Live
version of analysis/state_stratified_accuracy.py — same math, run inside
the Fitter so the output ships to GCS and the debug page can render it
without manual re-runs.

For each (field, dimension, bin), accumulates n, sum_abs_err, sum_signed_err.
After the pair-log pass, computes per-bin MAE/bias/Δ vs overall MAE, ranks
(field, dimension) by max-min MAE spread across bins, and emits
state_stratified_accuracy.json.

Equal-weight (no recency decay) by design — regime-conditional bias
structure is presumably stable in time; recency weighting would add noise
from sample-size effects in recent windows.

Hypothesis under test: corrected-forecast error is not uniformly
distributed — it depends on the meteorological regime at obs time. Big
spread = candidate for a future regime-aware correction layer.
"""
from collections import defaultdict


FIELDS = ("t", "dp", "h", "ws", "wg", "cc", "sr", "pr", "pa")
FIELD_LABELS = {
    "t":  ("Temperature", "°F"),
    "dp": ("Dew point",   "°F"),
    "h":  ("Humidity",    "%"),
    "ws": ("Wind speed",  "mph"),
    "wg": ("Wind gust",   "mph"),
    "cc": ("Cloud cover", "%"),
    "sr": ("Solar rad.",  "W/m²"),
    "pr": ("Pressure",    "inHg"),
    "pa": ("Precip amt",  "in"),
}
OCTANTS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
WIND_SPEED_BINS = ("calm (<5)", "light (5-15)", "breezy (>15)")
CLOUD_BINS      = ("clear (<25)", "partly (25-75)", "overcast (>75)")
PRESSURE_BINS   = ("rising (>+0.5)", "steady", "falling (<-0.5)")
FLOW_BINS       = ("n", "ne", "e", "se", "s", "sw", "w", "nw", "calm")
SYNOPTIC_BINS   = ("nw_flow", "sw_flow", "se_flow", "ne_flow",
                   "sea_breeze", "nor_easter", "frontal",
                   "pre_frontal", "calm")

DIMENSIONS = (
    ("wind_octant",     "wind dir (obs)",      OCTANTS),
    ("wind_speed",      "wind speed (obs)",    WIND_SPEED_BINS),
    ("cloud_cover",     "cloud cover (obs)",   CLOUD_BINS),
    ("pressure_trend",  "pressure trend (fc)", PRESSURE_BINS),
    ("regime_flow",     "flow regime (obs)",   FLOW_BINS),
    ("regime_synoptic", "synoptic (obs)",      SYNOPTIC_BINS),
)
MIN_PAIRS_PER_FIELD = 50
MIN_PAIRS_PER_BIN   = 20
SPREAD_VERDICT_THRESHOLD = 1.0  # min top-spread before recommending action


def _wind_octant(deg):
    if deg is None: return None
    try: d = (float(deg) + 22.5) % 360
    except (TypeError, ValueError): return None
    return OCTANTS[int(d // 45)]


def _wind_speed_bin(mph):
    if mph is None: return None
    try: m = float(mph)
    except (TypeError, ValueError): return None
    if m < 5:  return "calm (<5)"
    if m < 15: return "light (5-15)"
    return "breezy (>15)"


def _cloud_bin(pct):
    if pct is None: return None
    try: p = float(pct)
    except (TypeError, ValueError): return None
    if p < 25: return "clear (<25)"
    if p < 75: return "partly (25-75)"
    return "overcast (>75)"


def _pressure_trend_bin(hpa_3h):
    if hpa_3h is None: return None
    try: h = float(hpa_3h)
    except (TypeError, ValueError): return None
    if h >  0.5: return "rising (>+0.5)"
    if h < -0.5: return "falling (<-0.5)"
    return "steady"


def init_accumulators():
    """Return a fresh accumulator dict for one Fitter pass."""
    return {
        "bins": defaultdict(lambda: [0.0, 0.0, 0]),     # (field, dim_key, bin_label) -> [Σ|e|, Σe, n]
        "overall": defaultdict(lambda: [0.0, 0.0, 0]),  # field -> [Σ|e|, Σe, n]
        "n_scanned": 0,
        "n_with_state": 0,
        "n_used": 0,
    }


def accumulate(acc, row):
    """Feed one pair-log row into the accumulators. Cheap — a few dict updates."""
    acc["n_scanned"] += 1
    field = row.get("field")
    if field not in FIELDS:
        return
    err = row.get("error_l4")
    if err is None:
        err = row.get("error")
    if err is None:
        return
    try:
        err = float(err)
    except (TypeError, ValueError):
        return
    sobs = row.get("state_obs") or {}
    sfc  = row.get("state_fc")  or {}
    if not sobs and not sfc:
        return
    acc["n_with_state"] += 1

    vals = {
        "wind_octant":     _wind_octant(sobs.get("wind_dir")),
        "wind_speed":      _wind_speed_bin(sobs.get("wind_speed")),
        "cloud_cover":     _cloud_bin(sobs.get("cloud_cover")),
        "pressure_trend":  _pressure_trend_bin(sfc.get("pressure_trend_hpa_3h")),
        "regime_flow":     sobs.get("regime_flow"),
        "regime_synoptic": sobs.get("regime_synoptic"),
    }

    acc["n_used"] += 1
    ov = acc["overall"][field]
    ov[0] += abs(err); ov[1] += err; ov[2] += 1
    for dim_key, _, _ in DIMENSIONS:
        b = vals[dim_key]
        if b is None:
            continue
        cell = acc["bins"][(field, dim_key, b)]
        cell[0] += abs(err); cell[1] += err; cell[2] += 1


def build_output(acc, fitted_at):
    """Convert the accumulators into the publishable JSON shape. Returns dict."""
    fields_out = []
    rank = []  # (spread, field_key, dim_key, dim_label)

    for field in FIELDS:
        ov = acc["overall"].get(field)
        if not ov or ov[2] < MIN_PAIRS_PER_FIELD:
            continue
        ov_mae = ov[0] / ov[2]
        ov_bias = ov[1] / ov[2]
        f_label, f_unit = FIELD_LABELS[field]
        by_dim = {}
        for dim_key, dim_label, bin_order in DIMENSIONS:
            present_bins = [b for b in bin_order
                            if (field, dim_key, b) in acc["bins"]
                            and acc["bins"][(field, dim_key, b)][2] >= MIN_PAIRS_PER_BIN]
            if len(present_bins) < 2:
                continue
            bin_rows = []
            maes = []
            for b in present_bins:
                s_abs, s_signed, n = acc["bins"][(field, dim_key, b)]
                mae = s_abs / n
                bias = s_signed / n
                maes.append(mae)
                bin_rows.append({
                    "label": b,
                    "n": n,
                    "bias": round(bias, 3),
                    "mae":  round(mae, 3),
                    "delta": round(mae - ov_mae, 3),
                })
            spread = max(maes) - min(maes)
            by_dim[dim_key] = {
                "label": dim_label,
                "spread": round(spread, 3),
                "bins": bin_rows,
            }
            rank.append((spread, field, dim_key, dim_label))
        fields_out.append({
            "key": field,
            "label": f_label,
            "unit":  f_unit,
            "overall": {"n": ov[2], "bias": round(ov_bias, 3), "mae": round(ov_mae, 3)},
            "by_dimension": by_dim,
        })

    rank.sort(reverse=True)
    ranked_opps = []
    for i, (spread, fk, dk, dlabel) in enumerate(rank[:15], 1):
        ranked_opps.append({
            "rank": i,
            "field_key":      fk,
            "field_label":    FIELD_LABELS[fk][0],
            "dimension_key":  dk,
            "dimension_label": dlabel,
            "spread":         round(spread, 3),
        })

    if rank:
        top_spread, top_field, _, top_dim = rank[0]
        if top_spread > SPREAD_VERDICT_THRESHOLD:
            verdict = (f"{FIELD_LABELS[top_field][0]} stratified by {top_dim} shows "
                       f"{top_spread:.2f}-unit spread — worth building a regime-aware correction layer.")
        else:
            verdict = (f"Max spread is {top_spread:.2f} — no dimension shows enough variation "
                       f"to justify stratified correction yet. Re-run after more data.")
    else:
        verdict = "No usable stratified results."

    return {
        "fitted_at": fitted_at,
        "n_pairs_scanned": acc["n_scanned"],
        "n_pairs_with_state": acc["n_with_state"],
        "n_pairs_used": acc["n_used"],
        "min_pairs_per_field": MIN_PAIRS_PER_FIELD,
        "min_pairs_per_bin":   MIN_PAIRS_PER_BIN,
        "fields": fields_out,
        "ranked_opportunities": ranked_opps,
        "verdict": verdict,
    }
