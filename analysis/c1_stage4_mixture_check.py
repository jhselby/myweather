#!/usr/bin/env python3
"""C1 Stage 4 mixture-vs-real drift check.

For each FAIL cell in the latest c1_stage4_audit.json output, stratify the
pair-log rows in the calib and recent windows into forecast-value quartile
bins (cuts defined by the calib window). Report per-bin MAE + within-bin
drift %. Classify each cell:

  MIXTURE : within-bin MAEs mostly stable — the top-line drift is
            explained by distribution shift, not degradation.
  REAL    : at least one populous bin shows within-bin drift ≥ 40%.
  PARTIAL : some evidence of real drift but ambiguous.

Produces a decision-ready table before a C1 ship: MIXTURE cells are
safe to ship under the escape hatch; REAL cells should HOLD.

Reads:
  - analysis/output/c1_stage4_audit.json  (FAIL cell list + window bounds)
  - https://data.wymancove.com/forecast_error_log.jsonl
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
AUDIT_JSON = os.path.join(os.path.dirname(__file__), "output", "c1_stage4_audit.json")

BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
BIN_FLOOR = 80             # per-bin sample floor for within-bin comparison
DEGRADED_PCT = 40.0        # any populous bin with signed drift ≥ this → DEGRADED (hold)
SAFE_MAX_PCT = 25.0        # all populous bins with signed drift ≤ this → SAFE (ship)
# Cells where every populous bin has drift ≤ 0 are IMPROVED — a strict subset
# of SAFE, called out separately because Stage 4 flagged them as FAILs but the
# recent-window MAE is actually LOWER than calib. Third metric limitation:
# the audit's |Δ|/calib treats improvement identically to degradation.

# Fields where quartile-of-forecast-value binning is not meaningful:
# wd is circular (angular MAE), pa/pp are the near-zero-calib class already
# documented in project_stage4_audit_metric_limitation.
BIN_SKIP_FIELDS = frozenset({"wd", "pa", "pp"})


def band_lo_hi(band):
    for lab, lo, hi in BANDS:
        if lab == band:
            return lo, hi
    return None


def stable_or_transition(state_fc, state_obs, key):
    rfc = (state_fc or {}).get("regime_synoptic")
    rob = (state_obs or {}).get("regime_synoptic")
    if not rfc or not rob:
        return False
    is_stable = rfc == rob
    return (is_stable and key == "stable") or ((not is_stable) and key == "transition")


def load_fail_cells(audit):
    cells = []
    for r in audit["legacy_axis"]["results"]:
        if r["verdict"] != "FAIL":
            continue
        cells.append((r["field"], r["band"], r["key"], r))
    return cells


def collect_bin_data(fail_cells, calib_window, recent_window, pair_log_path=None):
    """Single pass: per FAIL cell, collect (forecast_value, abs_err) samples
    for calib + recent windows separately."""
    targets = {(f, b, k): {"calib": [], "recent": []}
               for (f, b, k, _) in fail_cells}
    path = pair_log_path or cached_path(PAIR_LOG_URL)

    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except json.JSONDecodeError:
                continue
            f = r.get("field")
            ot = r.get("obs_time")
            lead = r.get("lead_h")
            if f is None or ot is None or lead is None:
                continue
            ot16 = ot[:16]
            if calib_window[0] <= ot16 < calib_window[1]:
                w = "calib"
            elif recent_window[0] <= ot16 < recent_window[1]:
                w = "recent"
            else:
                continue
            # find every FAIL cell this row belongs to (a single row is
            # in exactly one band × slot combination, but check every f)
            for (tf, tb, tk) in list(targets.keys()):
                if tf != f:
                    continue
                lo, hi = band_lo_hi(tb)
                if lo is None or not (lo <= lead < hi):
                    continue
                if not stable_or_transition(r.get("state_fc"), r.get("state_obs"), tk):
                    continue
                err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
                fc = r.get("forecast_l1") if r.get("forecast_l1") is not None else r.get("forecast")
                if err is None or fc is None:
                    continue
                try:
                    targets[(tf, tb, tk)][w].append((float(fc), abs(float(err))))
                except (TypeError, ValueError):
                    continue
    return targets


def quartile_cuts(values):
    """Return 3 cut points splitting sorted `values` into 4 equal buckets."""
    if len(values) < 4:
        return None
    s = sorted(values)
    n = len(s)
    return (s[n // 4], s[n // 2], s[3 * n // 4])


def bin_of(v, cuts):
    if v < cuts[0]:
        return 0
    if v < cuts[1]:
        return 1
    if v < cuts[2]:
        return 2
    return 3


def per_bin_stats(samples, cuts):
    """samples: list of (forecast_value, abs_err). Returns list of 4 dicts
    with n, mae per bin."""
    sums = [[0, 0.0] for _ in range(4)]
    for fc, ae in samples:
        b = bin_of(fc, cuts)
        sums[b][0] += 1
        sums[b][1] += ae
    return [{"n": n, "mae": (e / n if n else 0.0)} for n, e in sums]


def classify(bin_rows):
    """Returns (verdict, top_signed_drift_pct).

    Uses SIGNED drift so improvement doesn't read as degradation:
      DEGRADED : any populous bin with signed drift ≥ DEGRADED_PCT (got worse)
      IMPROVED : every populous bin has signed drift ≤ 0 (recent MAE ≤ calib)
      SAFE     : every populous bin has signed drift ≤ SAFE_MAX_PCT (mixture drift)
      PARTIAL  : some populous bin between SAFE_MAX_PCT and DEGRADED_PCT positive
      THIN     : no populous bins
    """
    populous = [b["drift_pct"] for b in bin_rows
                if b["n_calib"] >= BIN_FLOOR and b["n_recent"] >= BIN_FLOOR]
    if not populous:
        return "THIN", None
    top = max(populous)  # signed max: catches degradation (positive drifts)
    if top >= DEGRADED_PCT:
        return "DEGRADED", top
    if max(populous) <= 0:
        return "IMPROVED", top
    if top <= SAFE_MAX_PCT:
        return "SAFE", top
    return "PARTIAL", top


def refine_verdicts(fail_cells, calib_window, recent_window, pair_log_path=None):
    """Reusable entry point. Streams the pair log once, stratifies each fail
    cell by forecast-value quartile bins from the calib window, classifies
    per-cell as DEGRADED/IMPROVED/SAFE/PARTIAL/THIN/SKIP.

    Returns a list of dicts, one per fail_cell in the same order:
      {"field", "band", "key", "top_drift_pct", "verdict",
       "top_bin_drift_pct", "bin_rows": [{n_calib, mae_calib, n_recent,
       mae_recent, drift_pct} × 4]}

    fail_cells: iterable of (field, band, key, meta_dict) tuples. meta_dict
    must carry "drift_pct" (the raw top-line drift the audit reported).
    """
    path = pair_log_path or cached_path(PAIR_LOG_URL)
    data = collect_bin_data(fail_cells, calib_window, recent_window,
                            pair_log_path=path)
    results = []
    for (f, b, k, meta) in fail_cells:
        entry = {"field": f, "band": b, "key": k,
                 "top_drift_pct": meta.get("drift_pct"),
                 "verdict": None, "top_bin_drift_pct": None,
                 "bin_rows": []}
        if f in BIN_SKIP_FIELDS:
            entry["verdict"] = "SKIP"
            results.append(entry)
            continue
        calib_samples = data[(f, b, k)]["calib"]
        recent_samples = data[(f, b, k)]["recent"]
        cuts = quartile_cuts([fc for (fc, _) in calib_samples])
        if cuts is None:
            entry["verdict"] = "THIN"
            results.append(entry)
            continue
        cs = per_bin_stats(calib_samples, cuts)
        rs = per_bin_stats(recent_samples, cuts)
        rows = []
        for i in range(4):
            drift = (100.0 * (rs[i]["mae"] - cs[i]["mae"]) / cs[i]["mae"]
                     if cs[i]["mae"] else 0.0)
            rows.append({
                "n_calib": cs[i]["n"], "mae_calib": cs[i]["mae"],
                "n_recent": rs[i]["n"], "mae_recent": rs[i]["mae"],
                "drift_pct": drift,
            })
        verdict, top = classify(rows)
        entry["verdict"] = verdict
        entry["top_bin_drift_pct"] = top
        entry["bin_rows"] = rows
        results.append(entry)
    return results


def main():
    with open(AUDIT_JSON) as f:
        audit = json.load(f)
    calib_start = audit["windows"]["calib_start"]
    calib_end = audit["windows"]["calib_end"]
    recent_start = audit["windows"]["recent_start"]
    recent_end = audit["windows"]["recent_end"]

    fail_cells = load_fail_cells(audit)
    print(f"C1 Stage 4 mixture check — {len(fail_cells)} FAIL cells")
    print(f"  calib  : {calib_start} → {calib_end}")
    print(f"  recent : {recent_start} → {recent_end}")
    print(f"  bin_floor={BIN_FLOOR}  "
          f"DEGRADED if any populous bin signed-drift ≥ {DEGRADED_PCT}%, "
          f"IMPROVED if all ≤ 0, SAFE if all ≤ {SAFE_MAX_PCT}%")
    print("=" * 100)

    print("[1/2] Streaming pair log...")
    data = collect_bin_data(
        fail_cells, (calib_start, calib_end), (recent_start, recent_end),
    )

    print("[2/2] Per-cell verdicts...")
    print()
    print(f"{'cell':<28} {'top-drift':>10}  {'verdict':<10}  per-bin drift %")
    print("-" * 100)

    summary_counts = defaultdict(int)
    for (f, b, k, meta) in fail_cells:
        top = meta["drift_pct"]
        if f in BIN_SKIP_FIELDS:
            print(f"{f}/{b:<5} [{k:<10}] {top:>+9.1f}%  "
                  f"{'SKIP':<10}  binning n/a for '{f}' — see project_stage4_audit_metric_limitation")
            summary_counts["SKIP"] += 1
            continue
        calib_samples = data[(f, b, k)]["calib"]
        recent_samples = data[(f, b, k)]["recent"]
        cuts = quartile_cuts([fc for (fc, _) in calib_samples])
        if cuts is None:
            print(f"{f}/{b:<5} [{k:<10}] {top:>+9.1f}%  {'THIN':<10}  <4 calib samples")
            summary_counts["THIN"] += 1
            continue
        cs = per_bin_stats(calib_samples, cuts)
        rs = per_bin_stats(recent_samples, cuts)
        rows = []
        for i in range(4):
            drift = (100.0 * (rs[i]["mae"] - cs[i]["mae"]) / cs[i]["mae"]
                     if cs[i]["mae"] else 0.0)
            rows.append({
                "n_calib": cs[i]["n"], "mae_calib": cs[i]["mae"],
                "n_recent": rs[i]["n"], "mae_recent": rs[i]["mae"],
                "drift_pct": drift,
            })
        verdict, max_abs = classify(rows)
        summary_counts[verdict] += 1
        drifts_str = "  ".join(
            f"b{i}:{r['drift_pct']:+.0f}%(nC={r['n_calib']}/nR={r['n_recent']})"
            for i, r in enumerate(rows)
        )
        print(f"{f}/{b:<5} [{k:<10}] {top:>+9.1f}%  {verdict:<10}  {drifts_str}")

    print()
    print("=" * 100)
    parts = "  ".join(f"{k}: {v}" for k, v in sorted(summary_counts.items()))
    print(f"Summary: {parts}")


if __name__ == "__main__":
    main()
