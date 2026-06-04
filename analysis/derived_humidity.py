#!/usr/bin/env python3
"""
Hypothesis check: does Magnus-derived RH from corrected (T, T_d) beat the
independently-corrected RH that the 4-layer stack currently produces?

Question: weather data scientists treat T and T_d as fundamental and derive
RH from them via Magnus. Our current pipeline corrects T, T_d, and RH as
three independent fields. The independent RH correction may be fighting the
T+T_d corrections, leaving more residual error than necessary. This script
quantifies it.

For each (run_time, valid_time, lead_h) triple in the pair log where t, dp,
and h all have forecast_l4 + observed:
  - h_independent = h forecast after L4 (what we ship today)
  - h_derived     = magnus(t_l4, dp_l4)   ← proposed
  - h_obs         = observed humidity

Compare MAE between h_independent and h_derived, stratified by lead.

Output:
  analysis/output/derived_humidity.png         — MAE vs lead, two curves
  analysis/output/derived_humidity_summary.txt — per-lead table + verdict

Run:
    python3 analysis/derived_humidity.py

Note: pair log carries forecast_l4 only on post-v0.6.25 snapshots. Older
pairs without forecast_l4 are skipped. Results may shift over the next
~1 week as the v0.6.34 L4 fit settles — re-run then to confirm.
"""
import json
import math
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime

SKIP_CHARTS = os.environ.get("ANALYSIS_NO_CHARTS") == "1"
if not SKIP_CHARTS:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt


ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def _fetch_jsonl_lines(url):
    req = urllib.request.Request(url, headers={"User-Agent": "myweather-derived-humidity/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw in resp:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def f_to_c(t_f):
    return (t_f - 32.0) * 5.0 / 9.0


def magnus_rh(t_f, dp_f):
    """Return RH (0-100) from temperature and dewpoint in °F using Magnus.
    Returns None if dewpoint > temperature (unphysical) or inputs invalid."""
    if t_f is None or dp_f is None:
        return None
    if dp_f > t_f + 0.05:  # tiny tolerance for rounding
        return None
    t_c = f_to_c(t_f)
    td_c = f_to_c(dp_f)
    a = 17.625
    b = 243.04
    e_s = math.exp(a * t_c / (t_c + b))
    e   = math.exp(a * td_c / (td_c + b))
    rh = 100.0 * e / e_s
    return max(0.0, min(100.0, rh))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"Fetching {ERROR_LOG_URL}…  (can take a minute)")
    # Group rows by (run_time, valid_time, lead_h). For each group, collect
    # t, dp, h entries with their forecast_l4 + observed values.
    groups = defaultdict(dict)  # key -> {field: row}
    n_in = 0
    n_kept = 0
    for row in _fetch_jsonl_lines(ERROR_LOG_URL):
        n_in += 1
        field = row.get("field")
        if field not in ("t", "dp", "h"):
            continue
        if row.get("forecast_l4") is None or row.get("observed") is None:
            continue
        key = (row.get("run_time"), row.get("valid_time"), row.get("lead_h"))
        if None in key:
            continue
        groups[key][field] = row
        n_kept += 1

    print(f"  {n_in:,} pair rows scanned, {n_kept:,} t/dp/h rows with L4")
    print(f"  {len(groups):,} (run, valid, lead) groups")

    # Per-lead accumulators.
    indep_abs    = defaultdict(float)
    derived_abs  = defaultdict(float)
    n_per_lead   = defaultdict(int)
    unphysical   = 0   # cases where dp_l4 > t_l4 → Magnus returns None
    n_complete   = 0

    for key, fields in groups.items():
        if not all(f in fields for f in ("t", "dp", "h")):
            continue
        t_row  = fields["t"]
        dp_row = fields["dp"]
        h_row  = fields["h"]
        lead = h_row.get("lead_h")
        t_l4  = t_row.get("forecast_l4")
        dp_l4 = dp_row.get("forecast_l4")
        h_l4  = h_row.get("forecast_l4")
        h_obs = h_row.get("observed")
        if t_l4 is None or dp_l4 is None or h_l4 is None or h_obs is None:
            continue
        derived = magnus_rh(float(t_l4), float(dp_l4))
        if derived is None:
            unphysical += 1
            continue
        n_complete += 1
        n_per_lead[lead] += 1
        indep_abs[lead]   += abs(float(h_l4) - float(h_obs))
        derived_abs[lead] += abs(derived     - float(h_obs))

    print(f"  {n_complete:,} complete (t, dp, h) triples")
    if unphysical:
        print(f"  ⚠  {unphysical:,} triples had dp_l4 > t_l4 (unphysical) — skipped")
    if not n_complete:
        print("No complete triples to analyze.", file=sys.stderr)
        sys.exit(1)

    # Per-lead summary.
    leads_sorted = sorted(n_per_lead.keys())
    summary_lines = [
        f"Derived-humidity hypothesis — generated {datetime.now().isoformat(timespec='seconds')}",
        f"Pair log rows scanned:   {n_in:,}",
        f"Rows with L4 (t/dp/h):   {n_kept:,}",
        f"Complete triples used:   {n_complete:,}",
        f"Unphysical (dp>T):       {unphysical:,}",
        "",
        f"Per-lead MAE (% RH points):",
        f"  lead |     n    | independent | derived |  Δ (derived − independent) |  Δ %",
        f"  ---- | -------- | ----------- | ------- | -------------------------- | ------",
    ]
    overall_indep_sum = 0.0
    overall_derived_sum = 0.0
    overall_n = 0
    for lead in leads_sorted:
        n = n_per_lead[lead]
        if n < 1:
            continue
        mae_i = indep_abs[lead] / n
        mae_d = derived_abs[lead] / n
        delta = mae_d - mae_i
        pct = (delta / mae_i * 100.0) if mae_i > 0 else float("nan")
        summary_lines.append(
            f"  {lead:>4} | {n:>8,} | {mae_i:>11.3f} | {mae_d:>7.3f} | {delta:>+27.3f} | {pct:>+5.1f}%"
        )
        overall_indep_sum   += indep_abs[lead]
        overall_derived_sum += derived_abs[lead]
        overall_n += n
    mae_i_overall = overall_indep_sum / overall_n
    mae_d_overall = overall_derived_sum / overall_n
    delta_overall = mae_d_overall - mae_i_overall
    pct_overall = delta_overall / mae_i_overall * 100.0 if mae_i_overall > 0 else float("nan")
    summary_lines += [
        "",
        f"Overall (all leads pooled):",
        f"  independent MAE: {mae_i_overall:.3f}",
        f"  derived MAE:     {mae_d_overall:.3f}",
        f"  Δ:               {delta_overall:+.3f}  ({pct_overall:+.1f}%)",
        "",
    ]
    if pct_overall <= -20:
        verdict = "SHIP — derived RH wins by >20% overall. Implement Magnus post-L4 in decay_apply.py."
    elif pct_overall <= -5:
        verdict = "MARGINAL — derived wins but not dramatically. Re-run after v0.6.34 settles (~1 week) before committing."
    elif pct_overall < 5:
        verdict = "WASH — within noise. No clear win. Shelve."
    else:
        verdict = "REJECT — derived loses. Independent correction is doing real work. Shelve."
    summary_lines.append(f"Verdict: {verdict}")

    summary_path = os.path.join(OUT_DIR, "derived_humidity_summary.txt")
    with open(summary_path, "w") as f:
        f.write("\n".join(summary_lines) + "\n")
    print(f"  ✓ {summary_path}")

    # Chart.
    if SKIP_CHARTS:
        print("\n".join(summary_lines[-10:]))
        return
    fig, ax = plt.subplots(figsize=(10, 6))
    xs = leads_sorted
    indep_y   = [indep_abs[l]   / n_per_lead[l] for l in xs]
    derived_y = [derived_abs[l] / n_per_lead[l] for l in xs]
    ax.plot(xs, indep_y,   marker="o", linewidth=2, color="#ef6450",
            label=f"Independent L4 (current)  overall {mae_i_overall:.2f}")
    ax.plot(xs, derived_y, marker="o", linewidth=2, color="#4aa3ff",
            label=f"Magnus-derived from corrected (T, T_d)  overall {mae_d_overall:.2f}")
    ax.set_xlabel("Forecast lead (h)")
    ax.set_ylabel("Humidity MAE (% RH points)")
    ax.set_title(f"Derived vs independently-corrected RH  ·  n={n_complete:,} triples")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=10)
    out_path = os.path.join(OUT_DIR, "derived_humidity.png")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"  ✓ {out_path}")
    print()
    print("\n".join(summary_lines[-10:]))


if __name__ == "__main__":
    main()
