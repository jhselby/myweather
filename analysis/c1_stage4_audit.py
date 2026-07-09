"""C1 Stage 4 UI-readiness audit — confidence-layer cell stability.

ENABLED=False keeps the UI from consuming the C1 bands until we know the
SHIP cells' claimed MAE values are stable across windows. The Stage 4
gate before flipping ENABLED=True is: each SHIP cell's MAE on a fresh
holdout window must match its calibrated value within tolerance.

Method:
  - "Calib" window: pairs older than the last RECENT_DAYS days, going
    back CALIB_DAYS (matches the Stage 1 calibration window shape).
  - "Recent" window: pairs from the last RECENT_DAYS days.
  - For every (field, band, axis_key) cell currently classified SHIP
    in the curated table, compute the realized MAE in both windows.
  - Report drift %: |recent - calib| / calib. PASS at ≤20%, WATCH 20-40%,
    FAIL >40%.

Output goes to stdout + analysis/output/c1_stage4_audit.json so the
debug page can render it.

Reads:
  - https://data.wymancove.com/forecast_error_log.jsonl
  - https://data.wymancove.com/cluster_spread_log.json
  - weather_collector/data/c1_confidence_curated_v2.json
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path  # noqa: E402
from analysis.c1_stage4_mixture_check import refine_verdicts  # noqa: E402


PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
CLUSTER_SPREAD_URL = "https://data.wymancove.com/cluster_spread_log.json"
CURATED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "weather_collector", "data", "c1_confidence_curated_v2.json",
)
OUTPUT_JSON = os.path.join(os.path.dirname(__file__), "output",
                           "c1_stage4_audit.json")

RECENT_DAYS = 7
CALIB_DAYS = 7    # window directly preceding the recent window
# Stage 1 used MIN_N_MULTI=30 on a 14d window — half that here since each
# audit window covers 7d (half the density per cell).
MIN_N_CELL = 15
DRIFT_PASS_PCT = 20.0
DRIFT_WATCH_PCT = 40.0
SHIP_STATUSES = ("SHIP",)  # MARGINAL excluded from Stage 4 audit by design

# Fields excluded from the "non-precip subset" recommendation. The Stage 4
# drift metric blows up when calib MAE → 0 (per project_stage4_audit_metric_limitation);
# pa is bursty in-band + sparse and drives most FAILs, and pp is Brier-evaluated so
# an MAE drift bound doesn't map to its user-facing decision anyway. The subset
# view lets us see whether the non-precip cells (t/h/wind/cloud) are stable
# enough to greenlight a partial ENABLE without waiting on pp/pa.
SUBSET_EXCLUDE_FIELDS = frozenset({"pp", "pa"})

SPREAD_FIELD = "spread_t"
TICK_TOLERANCE_MIN = 15

BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
PT_BINS = [
    ("falling_fast", float("-inf"), -1.0),
    ("falling", -1.0, -0.3),
    ("flat", -0.3, 0.3),
    ("rising", 0.3, float("inf")),
]


def band_for_lead(lh):
    for label, lo, hi in BANDS:
        if lo <= lh < hi:
            return label
    return None


def pt_bin(pt):
    if pt is None:
        return None
    for label, lo, hi in PT_BINS:
        if lo <= pt < hi:
            return label
    return None


def tick_key(iso_ts):
    return iso_ts[:16] if iso_ts else None


def shift_tick(tick, delta_min):
    dt = datetime.strptime(tick, "%Y-%m-%dT%H:%M")
    return (dt + timedelta(minutes=delta_min)).strftime("%Y-%m-%dT%H:%M")


def load_spread_index():
    """Return (by_tick, q1, q3) using the SAME quartile method as Stage 1."""
    try:
        path = cached_path(CLUSTER_SPREAD_URL)
    except Exception as e:
        print(f"  ⚠ cluster_spread fetch failed: {e}")
        return {}, None, None
    with open(path) as f:
        doc = json.load(f)
    by_tick, values = {}, []
    for e in doc.get("entries") or []:
        ts = e.get("ts")
        v = e.get(SPREAD_FIELD)
        if ts is None or v is None:
            continue
        k = tick_key(ts)
        if k:
            by_tick[k] = v
            values.append(v)
    if len(values) < 8:
        return by_tick, None, None
    s = sorted(values)
    return by_tick, s[len(s) // 4], s[(3 * len(s)) // 4]


def lookup_spread(idx, tick):
    if tick in idx:
        return idx[tick]
    for d in range(1, TICK_TOLERANCE_MIN + 1):
        for sign in (1, -1):
            cand = shift_tick(tick, sign * d)
            if cand in idx:
                return idx[cand]
    return None


def spread_quartile(v, q1, q3):
    if v is None or q1 is None or q3 is None:
        return None
    if v <= q1:
        return "Q1"
    if v >= q3:
        return "Q4"
    return "Q23"


def collect_ship_cells():
    """Walk the curated table; return (legacy_ship, multi_ship, doc).
      legacy_ship: list of (field, band, "stable"|"transition", calibrated_mae)
      multi_ship:  list of (field, band, axis_key, calibrated_mae)
    """
    with open(CURATED_PATH) as f:
        doc = json.load(f)
    legacy, multi = [], []
    for field, bands in (doc.get("cells") or {}).items():
        for band, entry in bands.items():
            if entry.get("status") in SHIP_STATUSES:
                legacy.append((field, band, "stable", entry["stable_mae"]))
                legacy.append((field, band, "transition", entry["transition_mae"]))
            for axis_key, ax in (entry.get("by_axes") or {}).items():
                if ax.get("status") in SHIP_STATUSES:
                    multi.append((field, band, axis_key, ax["mae"]))
    return legacy, multi, doc


def stratify(pair_log_path, spread_idx, q1, q3, calib_window, recent_window):
    """Single pass over the pair log; accumulate two parallel views:
      legacy_accs[(field, band, slot, window)]    -> [n, sum_abs_err]
      multi_accs[(field, band, axis_key, window)] -> [n, sum_abs_err]
    The legacy aggregator works for every pair; the multi aggregator only
    sees pairs whose tick is within the cluster_spread log's coverage.
    """
    legacy_accs = defaultdict(lambda: [0, 0.0])
    multi_accs = defaultdict(lambda: [0, 0.0])
    calib_start, calib_end = calib_window
    recent_start, recent_end = recent_window
    with open(pair_log_path) as f:
        for line in f:
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            ot = p.get("obs_time") or ""
            if ot < calib_start:
                continue
            if ot >= recent_end:
                continue
            window = ("calib" if ot < calib_end else
                      "recent" if ot >= recent_start else None)
            if window is None:
                continue
            field = p.get("field")
            obs = p.get("observed")
            lead = p.get("lead_h")
            if field is None or obs is None or lead is None:
                continue
            band = band_for_lead(lead)
            if band is None:
                continue
            sfc = p.get("state_fc") or {}
            sob = p.get("state_obs") or {}
            rfc = sfc.get("regime_synoptic")
            rob = sob.get("regime_synoptic")
            if not rfc or not rob:
                continue
            fc = (p.get("forecast_l4") or p.get("forecast_l3")
                  or p.get("forecast_l2") or p.get("forecast_l1")
                  or p.get("forecast"))
            if fc is None:
                continue
            abs_err = abs(fc - obs)
            is_trans = (rfc != rob)
            slot = "transition" if is_trans else "stable"
            # Legacy view — always available.
            cell_l = legacy_accs[(field, band, slot, window)]
            cell_l[0] += 1
            cell_l[1] += abs_err
            # Multi-axis view — only if cluster_spread + pt are both present.
            pt = pt_bin(sfc.get("pressure_trend_hpa_3h"))
            sv = lookup_spread(spread_idx, tick_key(ot))
            sq = spread_quartile(sv, q1, q3)
            if pt is None or sq is None:
                continue
            c1f = "p1" if (sfc.get("precip_in") or 0) > 0 else "p0"
            axis_key = f"{sq}::{pt}::{slot}::{c1f}"
            cell_m = multi_accs[(field, band, axis_key, window)]
            cell_m[0] += 1
            cell_m[1] += abs_err
    return legacy_accs, multi_accs


def classify_cells(ship_cells, accs, key_builder):
    """Generic per-cell drift classifier. key_builder takes a (field, band, slot|axis)
    tuple from ship_cells and returns the accs key prefix."""
    counts = {"PASS": 0, "WATCH": 0, "FAIL": 0, "INSUFFICIENT": 0}
    results = []
    for entry in ship_cells:
        field, band, ax, cal_mae = entry
        n_c, e_c = accs.get(key_builder(entry) + ("calib",), [0, 0.0])
        n_r, e_r = accs.get(key_builder(entry) + ("recent",), [0, 0.0])
        if n_c < MIN_N_CELL or n_r < MIN_N_CELL:
            counts["INSUFFICIENT"] += 1
            results.append({
                "field": field, "band": band, "key": ax,
                "calibrated_mae": cal_mae,
                "n_calib": n_c, "n_recent": n_r,
                "verdict": "INSUFFICIENT",
                "rationale": f"sample floor (n_c={n_c}, n_r={n_r})",
            })
            continue
        mae_c = e_c / n_c
        mae_r = e_r / n_r
        drift_pct = 100.0 * abs(mae_r - mae_c) / mae_c if mae_c else float("inf")
        if drift_pct <= DRIFT_PASS_PCT:
            verdict = "PASS"
        elif drift_pct <= DRIFT_WATCH_PCT:
            verdict = "WATCH"
        else:
            verdict = "FAIL"
        counts[verdict] += 1
        results.append({
            "field": field, "band": band, "key": ax,
            "calibrated_mae": cal_mae,
            "mae_calib": round(mae_c, 4), "mae_recent": round(mae_r, 4),
            "drift_pct": round(drift_pct, 2),
            "n_calib": n_c, "n_recent": n_r,
            "verdict": verdict,
        })
    return counts, results


def recommendation(counts):
    total_eval = counts["PASS"] + counts["WATCH"] + counts["FAIL"]
    if total_eval == 0:
        return "INSUFFICIENT-DATA — not enough holdout pairs yet"
    pass_rate = counts["PASS"] / total_eval
    if pass_rate >= 0.80 and counts["FAIL"] / total_eval <= 0.05:
        return "READY — flip ENABLED=True after one more weekly confirmation"
    if pass_rate >= 0.60:
        return "MIXED — most cells stable but tail unstable; hold"
    return "NOT READY — drift exceeds tolerance on majority of cells"


def subset_view(results, exclude):
    """Rebuild counts + recommendation over a subset of results with fields
    in `exclude` filtered out. Used for the non-precip subset audit."""
    counts = {"PASS": 0, "WATCH": 0, "FAIL": 0, "INSUFFICIENT": 0}
    kept = []
    for r in results:
        if r["field"] in exclude:
            continue
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        kept.append(r)
    return counts, recommendation(counts), kept


def refined_view(results, calib_window, recent_window, pair_log_path):
    """Reclassify FAILs and WATCHes using the mixture-check bin stratification.
    Produces a parallel counts + recommendation that honestly separates
    cell-level degradation from metric-artifact classes (near-zero calib,
    mixture drift, unsigned improvement, angular-MAE fields) — see
    project_stage4_audit_metric_limitation.

    Refined verdict mapping:
      raw PASS          → PASS         (never re-examined)
      raw INSUFFICIENT  → INSUFFICIENT
      raw WATCH | FAIL  → per-cell mixture check:
        DEGRADED  → FAIL       (real cell-level degradation)
        IMPROVED  → PASS       (recent MAE < calib MAE — model got better)
        SAFE      → PASS       (top-line drift is mixture, within-bin stable)
        PARTIAL   → WATCH      (borderline; watch for next window)
        SKIP      → excluded from denominator (metric-artifact field)
        THIN      → keep raw verdict (bin sample floor not met)
    """
    to_refine = [(r["field"], r["band"], r["key"], r)
                 for r in results if r["verdict"] in ("FAIL", "WATCH")]
    refined_by_key = {}
    if to_refine:
        refinements = refine_verdicts(to_refine, calib_window, recent_window,
                                       pair_log_path=pair_log_path)
        for ref in refinements:
            refined_by_key[(ref["field"], ref["band"], ref["key"])] = ref
    counts = {"PASS": 0, "WATCH": 0, "FAIL": 0, "INSUFFICIENT": 0}
    excluded_skip = 0
    per_cell = []
    for r in results:
        key = (r["field"], r["band"], r["key"])
        if r["verdict"] not in ("FAIL", "WATCH"):
            new_verdict = r["verdict"]
            per_cell.append({**r, "refined_verdict": new_verdict,
                             "refined_reason": None})
        else:
            ref = refined_by_key.get(key)
            mv = (ref or {}).get("verdict")
            if mv in ("IMPROVED", "SAFE"):
                new_verdict = "PASS"
            elif mv == "DEGRADED":
                new_verdict = "FAIL"
            elif mv == "PARTIAL":
                new_verdict = "WATCH"
            elif mv == "THIN":
                # Not enough per-bin samples for a mixture verdict — keep raw.
                new_verdict = r["verdict"]
            elif mv == "SKIP":
                excluded_skip += 1
                per_cell.append({**r, "refined_verdict": "SKIP",
                                 "refined_reason": "metric-artifact field"})
                continue
            else:
                new_verdict = r["verdict"]
            per_cell.append({**r, "refined_verdict": new_verdict,
                             "refined_reason": mv})
        counts[new_verdict] = counts.get(new_verdict, 0) + 1
    return counts, recommendation(counts), excluded_skip, per_cell


def main():
    legacy_ship, multi_ship, curated_doc = collect_ship_cells()
    print(f"C1 Stage 4 audit — {len(legacy_ship)} legacy + {len(multi_ship)} multi-axis SHIP cells")
    print(f"  RECENT_DAYS={RECENT_DAYS}, CALIB_DAYS={CALIB_DAYS}, MIN_N={MIN_N_CELL}")
    print(f"  PASS ≤{DRIFT_PASS_PCT}% / WATCH ≤{DRIFT_WATCH_PCT}% / FAIL >{DRIFT_WATCH_PCT}%")
    print("=" * 90)

    now = datetime.now(timezone.utc)
    recent_end = now.strftime("%Y-%m-%dT%H:%M")
    recent_start = (now - timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%dT%H:%M")
    calib_end = recent_start
    calib_start = (now - timedelta(days=RECENT_DAYS + CALIB_DAYS)).strftime("%Y-%m-%dT%H:%M")

    print("[1/3] Loading cluster_spread index...")
    spread_idx, q1, q3 = load_spread_index()
    multi_deferred = False
    if q1 is None or not spread_idx:
        print("  ⚠ cluster_spread history too short — multi-axis audit deferred.")
        multi_deferred = True
    else:
        # Detect whether the spread index actually reaches back into the calib window.
        earliest_spread = min(spread_idx.keys())
        if earliest_spread > calib_end:
            print(f"  ⚠ cluster_spread earliest tick {earliest_spread} is after calib window "
                  f"({calib_start} → {calib_end}). Multi-axis audit deferred.")
            multi_deferred = True
        else:
            print(f"  Q1≤{q1:.3f}, Q3≥{q3:.3f}, earliest tick {earliest_spread}")

    print("[2/3] Streaming pair log...")
    pair_path = cached_path(PAIR_LOG_URL)
    legacy_accs, multi_accs = stratify(
        pair_path, spread_idx, q1, q3,
        (calib_start, calib_end), (recent_start, recent_end),
    )

    print("[3/3] Computing drift per SHIP cell...")
    legacy_counts, legacy_results = classify_cells(
        legacy_ship, legacy_accs,
        key_builder=lambda e: (e[0], e[1], e[2]),  # (field, band, slot)
    )
    if multi_deferred:
        multi_counts = {"PASS": 0, "WATCH": 0, "FAIL": 0,
                        "INSUFFICIENT": len(multi_ship)}
        multi_results = [
            {"field": f, "band": b, "key": ak, "calibrated_mae": m,
             "n_calib": 0, "n_recent": 0, "verdict": "DEFERRED",
             "rationale": "cluster_spread log shorter than calib window"}
            for f, b, ak, m in multi_ship
        ]
    else:
        multi_counts, multi_results = classify_cells(
            multi_ship, multi_accs,
            key_builder=lambda e: (e[0], e[1], e[2]),  # (field, band, axis_key)
        )

    legacy_rec = recommendation(legacy_counts)
    multi_rec = ("DEFERRED — cluster_spread log accumulates over time; "
                 "expect first multi-axis audit ≈ 2026-07-04"
                 if multi_deferred else recommendation(multi_counts))

    legacy_subset_counts, legacy_subset_rec, _ = subset_view(
        legacy_results, SUBSET_EXCLUDE_FIELDS,
    )
    if multi_deferred:
        multi_subset_counts, multi_subset_rec = None, None
    else:
        multi_subset_counts, multi_subset_rec, _ = subset_view(
            multi_results, SUBSET_EXCLUDE_FIELDS,
        )

    calib_win = (calib_start, calib_end)
    recent_win = (recent_start, recent_end)
    (legacy_refined_counts, legacy_refined_rec,
     legacy_refined_skip, legacy_refined_results) = refined_view(
        legacy_results, calib_win, recent_win, pair_path,
    )
    if multi_deferred:
        multi_refined_counts = None
        multi_refined_rec = None
        multi_refined_skip = 0
        multi_refined_results = None
    else:
        (multi_refined_counts, multi_refined_rec,
         multi_refined_skip, multi_refined_results) = refined_view(
            multi_results, calib_win, recent_win, pair_path,
        )

    excl_label = ", ".join(sorted(SUBSET_EXCLUDE_FIELDS))
    print()
    print(f"Legacy axis (transition × stable, no spread/pt/c1f):")
    print(f"  {legacy_counts['PASS']} PASS / {legacy_counts['WATCH']} WATCH / "
          f"{legacy_counts['FAIL']} FAIL / {legacy_counts['INSUFFICIENT']} INSUFFICIENT "
          f"(of {len(legacy_ship)})")
    print(f"  → {legacy_rec}")
    print(f"  Non-precip subset (excluding {excl_label}): "
          f"{legacy_subset_counts['PASS']} PASS / {legacy_subset_counts['WATCH']} WATCH / "
          f"{legacy_subset_counts['FAIL']} FAIL / "
          f"{legacy_subset_counts['INSUFFICIENT']} INSUFFICIENT")
    print(f"  → {legacy_subset_rec}")
    print(f"  Refined (per-cell mixture check on WATCH+FAIL): "
          f"{legacy_refined_counts['PASS']} PASS / {legacy_refined_counts['WATCH']} WATCH / "
          f"{legacy_refined_counts['FAIL']} FAIL / "
          f"{legacy_refined_counts['INSUFFICIENT']} INSUFFICIENT "
          f"(+{legacy_refined_skip} excluded as metric-artifact)")
    print(f"  → {legacy_refined_rec}")
    print()
    print(f"Multi-axis (Q × pt × trans × c1f):")
    print(f"  {multi_counts['PASS']} PASS / {multi_counts['WATCH']} WATCH / "
          f"{multi_counts['FAIL']} FAIL / {multi_counts['INSUFFICIENT']} INSUFFICIENT "
          f"(of {len(multi_ship)})")
    print(f"  → {multi_rec}")
    if not multi_deferred:
        print(f"  Non-precip subset (excluding {excl_label}): "
              f"{multi_subset_counts['PASS']} PASS / {multi_subset_counts['WATCH']} WATCH / "
              f"{multi_subset_counts['FAIL']} FAIL / "
              f"{multi_subset_counts['INSUFFICIENT']} INSUFFICIENT")
        print(f"  → {multi_subset_rec}")
        print(f"  Refined (per-cell mixture check on WATCH+FAIL): "
              f"{multi_refined_counts['PASS']} PASS / {multi_refined_counts['WATCH']} WATCH / "
              f"{multi_refined_counts['FAIL']} FAIL / "
              f"{multi_refined_counts['INSUFFICIENT']} INSUFFICIENT "
              f"(+{multi_refined_skip} excluded as metric-artifact)")
        print(f"  → {multi_refined_rec}")

    # Top 5 worst drifters across both views
    all_drifters = sorted(
        (r for r in (legacy_results + multi_results)
         if r["verdict"] in ("WATCH", "FAIL")),
        key=lambda r: r["drift_pct"], reverse=True,
    )[:5]
    if all_drifters:
        print()
        print("Top drifters:")
        for r in all_drifters:
            print(f"  {r['field']}/{r['band']} [{r['key']}] "
                  f"calib={r['mae_calib']:.3f} recent={r['mae_recent']:.3f} "
                  f"drift={r['drift_pct']:+.1f}% ({r['verdict']})")

    out = {
        "generated_at": now.isoformat(),
        "windows": {
            "calib_start": calib_start, "calib_end": calib_end,
            "recent_start": recent_start, "recent_end": recent_end,
        },
        "thresholds": {
            "min_n_cell": MIN_N_CELL,
            "drift_pass_pct": DRIFT_PASS_PCT,
            "drift_watch_pct": DRIFT_WATCH_PCT,
        },
        "legacy_axis": {
            "counts": legacy_counts,
            "recommendation": legacy_rec,
            "non_precip_subset": {
                "excluded_fields": sorted(SUBSET_EXCLUDE_FIELDS),
                "counts": legacy_subset_counts,
                "recommendation": legacy_subset_rec,
            },
            "refined": {
                "counts": legacy_refined_counts,
                "recommendation": legacy_refined_rec,
                "skipped_as_metric_artifact": legacy_refined_skip,
                "results": legacy_refined_results,
            },
            "results": legacy_results,
        },
        "multi_axis": {
            "counts": multi_counts,
            "recommendation": multi_rec,
            "non_precip_subset": (
                None if multi_deferred else {
                    "excluded_fields": sorted(SUBSET_EXCLUDE_FIELDS),
                    "counts": multi_subset_counts,
                    "recommendation": multi_subset_rec,
                }
            ),
            "refined": (
                None if multi_deferred else {
                    "counts": multi_refined_counts,
                    "recommendation": multi_refined_rec,
                    "skipped_as_metric_artifact": multi_refined_skip,
                    "results": multi_refined_results,
                }
            ),
            "deferred": multi_deferred,
            "results": multi_results,
        },
        "source_table": os.path.basename(CURATED_PATH),
        "source_generated_at": curated_doc.get("generated_at"),
    }
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(out, f, indent=2)
    print()
    print(f"Wrote {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
