
import sys, os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from _cache import cached_path
#!/usr/bin/env python3
"""
State-stratified accuracy: slice forecast MAE by observed state to find
which dimensions matter for future regime-stratified correction.

Hypothesis: corrected-forecast error is not uniformly distributed — it
depends on the meteorological regime at the observation time. If
temperature errors are 2°F larger under SE flow than NW, that's a regime
worth correcting for. If errors are flat across all bins, the dimension
doesn't matter.

Uses state_obs metadata stamped on every pair since v0.6.29:
  - wind_dir   → 8-octant compass sector
  - wind_speed → calm / light / breezy
  - cloud_cover → clear / partly / overcast
  - pressure_trend_hpa_3h (from state_fc) → rising / falling / steady

For each (field, dimension, bin), accumulates n, bias (signed mean error),
and MAE. Compares per-bin MAE to overall MAE — large spread across bins
means the dimension is informative; small spread means it isn't.

Output:
  analysis/output/state_stratified_summary.txt — per-field tables + ranked dimensions

Run:
    python3 analysis/state_stratified_accuracy.py

Note: state_obs is on pairs from v0.6.29 onward. Older pairs are skipped.
Pressure-trend comes from state_fc (snapshot-level) so all leads from one
snapshot share the same value. Wind dir uses observed-at-obs-time direction
(not forecast direction) — this is "what regime were we actually in."
"""
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# Fields worth stratifying — skip POP (binary obs) and cloud splits (mostly 0s).
FIELDS = ["t", "dp", "h", "ws", "wg", "cc", "sr", "pr", "pa"]
FIELD_LABELS = {
    "t": "Temperature", "dp": "Dew point", "h": "Humidity",
    "ws": "Wind speed", "wg": "Wind gust", "cc": "Cloud cover",
    "sr": "Solar rad.", "pr": "Pressure", "pa": "Precip amt",
}

OCTANTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _fetch_jsonl_lines(url):
    with open(cached_path(url), 'rb') as resp:
        for raw in resp:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def wind_octant(deg):
    if deg is None: return None
    d = (float(deg) + 22.5) % 360
    return OCTANTS[int(d // 45)]


def wind_speed_bin(mph):
    if mph is None: return None
    if mph < 5:  return "calm (<5)"
    if mph < 15: return "light (5-15)"
    return "breezy (>15)"


def cloud_bin(pct):
    if pct is None: return None
    if pct < 25: return "clear (<25)"
    if pct < 75: return "partly (25-75)"
    return "overcast (>75)"


def pressure_trend_bin(hpa_3h):
    if hpa_3h is None: return None
    if hpa_3h >  0.5: return "rising (>+0.5)"
    if hpa_3h < -0.5: return "falling (<-0.5)"
    return "steady"


DIMENSIONS = [
    ("wind_octant",     "wind dir (obs)",      OCTANTS,                                                wind_octant),
    ("wind_speed",      "wind speed (obs)",    ["calm (<5)", "light (5-15)", "breezy (>15)"],         wind_speed_bin),
    ("cloud_cover",     "cloud cover (obs)",   ["clear (<25)", "partly (25-75)", "overcast (>75)"],   cloud_bin),
    ("pressure_trend",  "pressure trend (fc)", ["rising (>+0.5)", "steady", "falling (<-0.5)"],        pressure_trend_bin),
    # v0.6.38 regime labels (state_obs.regime_flow / regime_synoptic).
    # Pre-v0.6.38 pairs have no regime keys and are silently skipped here.
    ("regime_flow",     "flow regime (obs)",   ["n", "ne", "e", "se", "s", "sw", "w", "nw", "calm"],   lambda v: v),
    ("regime_synoptic", "synoptic (obs)",      ["nw_flow", "sw_flow", "se_flow", "ne_flow",
                                                "sea_breeze", "nor_easter", "frontal",
                                                "pre_frontal", "calm"],                                lambda v: v),
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Fetching {ERROR_LOG_URL}…")

    # bins[(field, dim_key, bin_label)] -> [sum_abs_err, sum_signed_err, n]
    bins = defaultdict(lambda: [0.0, 0.0, 0])
    overall = defaultdict(lambda: [0.0, 0.0, 0])  # field -> [sum_abs, sum_signed, n]

    n_in = 0
    n_with_state = 0
    n_used = 0

    for row in _fetch_jsonl_lines(ERROR_LOG_URL):
        n_in += 1
        field = row.get("field")
        if field not in FIELDS:
            continue
        err = row.get("error_l4")
        if err is None:
            err = row.get("error")
        if err is None:
            continue
        err = float(err)
        sobs = row.get("state_obs") or {}
        sfc  = row.get("state_fc")  or {}
        if not sobs and not sfc:
            continue
        n_with_state += 1

        # Classify each dimension
        vals = {
            "wind_octant":     wind_octant(sobs.get("wind_dir")),
            "wind_speed":      wind_speed_bin(sobs.get("wind_speed")),
            "cloud_cover":     cloud_bin(sobs.get("cloud_cover")),
            "pressure_trend":  pressure_trend_bin(sfc.get("pressure_trend_hpa_3h")),
            "regime_flow":     sobs.get("regime_flow"),
            "regime_synoptic": sobs.get("regime_synoptic"),
        }

        n_used += 1
        overall[field][0] += abs(err)
        overall[field][1] += err
        overall[field][2] += 1
        for dim_key, _, _, _ in DIMENSIONS:
            b = vals[dim_key]
            if b is None:
                continue
            key = (field, dim_key, b)
            bins[key][0] += abs(err)
            bins[key][1] += err
            bins[key][2] += 1

    print(f"  {n_in:,} rows scanned, {n_with_state:,} with state metadata, {n_used:,} used")
    if not n_used:
        print("No usable pairs.", file=sys.stderr)
        sys.exit(1)

    # Build summary
    lines = [
        f"State-stratified accuracy — generated {datetime.now().isoformat(timespec='seconds')}",
        f"Rows scanned:       {n_in:,}",
        f"Rows with state:    {n_with_state:,}",
        f"Rows used (field in {{{','.join(FIELDS)}}}): {n_used:,}",
        "",
        "Per-field MAE stratified by observed/forecast state.",
        "  bias = signed mean error (forecast − obs); MAE = mean |error|.",
        "  Δ MAE = (bin MAE − overall MAE).",
        "",
    ]
    field_dim_rank = []  # (max_mae_spread, field, dim_key, dim_label)

    for field in FIELDS:
        ov = overall[field]
        if ov[2] < 50:
            continue
        ov_mae = ov[0] / ov[2]
        ov_bias = ov[1] / ov[2]
        lines.append(f"=== {FIELD_LABELS[field]} ({field}) ===")
        lines.append(f"  overall:  n={ov[2]:,}   bias={ov_bias:+.3f}   MAE={ov_mae:.3f}")
        for dim_key, dim_label, bin_order, _ in DIMENSIONS:
            present_bins = [b for b in bin_order if (field, dim_key, b) in bins and bins[(field, dim_key, b)][2] >= 20]
            if len(present_bins) < 2:
                continue
            lines.append(f"  by {dim_label}:")
            lines.append(f"    {'bin':<18} {'n':>7}  {'bias':>8}  {'MAE':>8}  {'Δ MAE':>8}")
            bin_maes = []
            for b in present_bins:
                s_abs, s_signed, n = bins[(field, dim_key, b)]
                mae = s_abs / n
                bias = s_signed / n
                delta = mae - ov_mae
                bin_maes.append(mae)
                lines.append(f"    {b:<18} {n:>7,}  {bias:>+8.3f}  {mae:>8.3f}  {delta:>+8.3f}")
            spread = max(bin_maes) - min(bin_maes)
            field_dim_rank.append((spread, field, dim_key, dim_label))
            lines.append(f"    → spread (max−min MAE across bins): {spread:.3f}")
        lines.append("")

    # Ranking section: which (field, dimension) combos have the biggest spread?
    # That's where state-stratified correction would help most.
    field_dim_rank.sort(reverse=True)
    lines.append("=" * 64)
    lines.append("RANKED OPPORTUNITIES — top 15 (field, dimension) pairs")
    lines.append("Bigger spread = bigger payoff from stratifying corrections by this state.")
    lines.append("=" * 64)
    lines.append(f"  {'rank':>4}  {'spread':>8}  {'field':<14} {'dimension':<22}")
    for i, (spread, field, dim_key, dim_label) in enumerate(field_dim_rank[:15], 1):
        lines.append(f"  {i:>4}  {spread:>8.3f}  {FIELD_LABELS[field]:<14} {dim_label:<22}")
    lines.append("")
    if field_dim_rank:
        top_spread, top_field, _, top_dim = field_dim_rank[0]
        if top_spread > 1.0:
            lines.append(f"Verdict: {FIELD_LABELS[top_field]} stratified by {top_dim} shows "
                         f"{top_spread:.2f}-unit spread across bins — worth building a regime-aware "
                         f"correction layer.")
        else:
            lines.append(f"Verdict: max spread is {top_spread:.2f} — no dimension shows enough "
                         f"variation to justify stratified correction yet. Re-run after more data.")
    summary_path = os.path.join(OUT_DIR, "state_stratified_summary.txt")
    with open(summary_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  ✓ {summary_path}")
    print()
    print("\n".join(lines[-15:]))


if __name__ == "__main__":
    main()
