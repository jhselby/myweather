"""Stage 2 — cross-run spread orthogonality vs cluster_spread_q.

Stage 1 (h_cross_run_spread_c1_stage1.py, 08-10) cleared PROMOTE for 7/7
fields vs transition + pt.  Remaining blocker before wiring into
c1_confidence_calibration_v2 as a 6th axis: does cross-run spread survive
conditioning on the incumbent `cluster_spread_q` axis (axis_2, promoted
2026-06-20)?

Both signals measure "hard valid_times."  cluster_spread_q is inter-source
disagreement (Open-Meteo vs Pirate vs NWS temp spread); cross-run spread is
same-model intra-run disagreement.  Conceptually distinct — this script
tests whether they are empirically distinct too.

Method (mirrors Stage 1):
  1. Compute cross-run spread per (field, valid_time) — max-min forecast.
  2. Quintile per field, TRAIN-fit edges only.  Held-out = last 7d.
  3. Load cluster_spread log; label each row's obs_time with Q1/Q23/Q4
     (matches c1_v2 semantics: extremes only, middle collapsed).
  4. For each cluster_spread level, compute test mean|err| in the HIGH
     cross-run-spread quintile (Q5) vs LOW quintile (Q1).
  5. Verdict per field:
       ORTHOGONAL — Q5/Q1 ratio >= ORTHO_GATE inside EVERY non-thin level
                    of cluster_spread_q.  Signal is not cluster_spread in
                    disguise.
       CONFOUNDED — hits only inside minority level(s).
       REDUNDANT  — ratio < REDUNDANT_CEILING inside every level.
       THIN       — not enough n in the level to judge.

  Overall PROMOTE if ORTHOGONAL on >= PROMOTE_MIN_FIELDS fields.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402
from _windows import rolling_windows  # noqa: E402

PAIR_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
CLUSTER_SPREAD_URL = "https://data.wymancove.com/cluster_spread_log.json"
SPREAD_FIELD = "spread_t"  # matches c1_v2

OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_cross_run_spread_c1_stage2.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_cross_run_spread_c1_stage2.json")

WINDOW_DAYS = 45
HELD_OUT_DAYS = 7
MIN_RUNS_PER_VT = 3
MIN_N_LEVEL = 40
ORTHO_GATE = 1.35
REDUNDANT_CEILING = 1.10
TICK_JOIN_TOLERANCE_MIN = 15
TARGET_FIELDS = ["t", "wd", "wg", "dp", "h", "pr", "ws"]  # Stage 1 PROMOTE cohort
PROMOTE_MIN_FIELDS = 4


def _tick_key(iso_ts):
    if not iso_ts:
        return None
    return iso_ts[:16]


def _shift_tick(tick, delta_min):
    dt = datetime.strptime(tick, "%Y-%m-%dT%H:%M")
    return (dt + timedelta(minutes=delta_min)).strftime("%Y-%m-%dT%H:%M")


def _load_cluster_spread():
    try:
        path = cached_path(CLUSTER_SPREAD_URL)
        with open(path) as f:
            doc = json.load(f)
    except Exception as e:
        print(f"  ⚠ cluster_spread fetch/parse failed: {e}")
        return {}, None, None
    entries = doc.get("entries") or []
    by_tick = {}
    values = []
    for e in entries:
        ts = e.get("ts")
        v = e.get(SPREAD_FIELD)
        if ts is None or v is None:
            continue
        k = _tick_key(ts)
        if k is None:
            continue
        by_tick[k] = v
        values.append(v)
    if len(values) < 8:
        return by_tick, None, None
    s = sorted(values)
    n = len(s)
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    return by_tick, q1, q3


def _lookup_spread(idx, tick):
    if tick is None:
        return None
    if tick in idx:
        return idx[tick]
    for delta in range(1, TICK_JOIN_TOLERANCE_MIN + 1):
        for sign in (1, -1):
            cand = _shift_tick(tick, sign * delta)
            if cand in idx:
                return idx[cand]
    return None


def _cluster_q(v, q1, q3):
    if v is None or q1 is None or q3 is None:
        return None
    if v <= q1:
        return "Q1"
    if v >= q3:
        return "Q4"
    return "Q23"


def _quintile_edges(sorted_vals):
    n = len(sorted_vals)
    return [sorted_vals[int(n * p)] for p in (0.20, 0.40, 0.60, 0.80)]


def _bin(x, edges):
    for i, e in enumerate(edges):
        if x < e:
            return i
    return len(edges)


def _load_pairs():
    WIN = rolling_windows(recent_days=WINDOW_DAYS, prior_days=0)
    lo_win, hi_win = WIN.A_LO, WIN.A_HI
    rows = []
    groups = defaultdict(list)  # (field, vt) -> [forecast, ...]
    n_scanned = 0
    with open(cached_path(PAIR_URL), "rb") as fh:
        for raw in fh:
            n_scanned += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            vt = r.get("valid_time") or ""
            if vt < lo_win or vt >= hi_win:
                continue
            f = r.get("field")
            if f not in TARGET_FIELDS:
                continue
            fc = r.get("forecast")
            err = r.get("error")
            if fc is None or err is None:
                continue
            ot = r.get("obs_time") or ""
            rows.append({
                "field": f,
                "vt": vt,
                "obs_time": ot,
                "err": abs(float(err)),
            })
            groups[(f, vt)].append(float(fc))
    return rows, groups, n_scanned, lo_win, hi_win


def analyze_field(field, rows, spread_by_vt, cluster_idx, cq1, cq3, test_start):
    train_spreads = [sp for (f, vt), sp in spread_by_vt.items()
                     if f == field and vt[:10] < test_start]
    if len(train_spreads) < 200:
        return {"field": field, "status": "THIN_TRAIN_SPREAD",
                "n_train_spreads": len(train_spreads)}
    edges = _quintile_edges(sorted(train_spreads))

    # level -> {qbin: [|err|]}
    per_level = defaultdict(lambda: defaultdict(list))
    n_test_field = 0
    n_no_cluster = 0
    for r in rows:
        if r["field"] != field:
            continue
        if r["vt"][:10] < test_start:
            continue
        sp = spread_by_vt.get((field, r["vt"]))
        if sp is None:
            continue
        cv = _lookup_spread(cluster_idx, _tick_key(r["obs_time"]))
        cq = _cluster_q(cv, cq1, cq3)
        if cq is None:
            n_no_cluster += 1
            continue
        qbin = _bin(sp, edges)
        per_level[cq][qbin].append(r["err"])
        n_test_field += 1

    verdicts = []
    detail = {}
    for level in ("Q1", "Q23", "Q4"):
        qbins = per_level.get(level, {})
        q1 = qbins.get(0, [])
        q5 = qbins.get(4, [])
        n1 = len(q1)
        n5 = len(q5)
        if n1 < MIN_N_LEVEL or n5 < MIN_N_LEVEL:
            detail[level] = {"n_q1": n1, "n_q5": n5, "status": "THIN"}
            verdicts.append("THIN")
            continue
        m1 = mean(q1)
        m5 = mean(q5)
        ratio = m5 / m1 if m1 > 0 else 0
        detail[level] = {"n_q1": n1, "n_q5": n5,
                         "mae_q1": round(m1, 3), "mae_q5": round(m5, 3),
                         "ratio": round(ratio, 2)}
        if ratio >= ORTHO_GATE:
            verdicts.append("HIT")
        elif ratio <= REDUNDANT_CEILING:
            verdicts.append("FLAT")
        else:
            verdicts.append("WEAK")

    real = [v for v in verdicts if v != "THIN"]
    if not real:
        overall = "THIN"
    elif all(v == "HIT" for v in real):
        overall = "ORTHOGONAL"
    elif all(v == "FLAT" for v in real):
        overall = "REDUNDANT"
    elif any(v == "HIT" for v in real) and any(v in ("FLAT", "WEAK") for v in real):
        overall = "CONFOUNDED"
    else:
        overall = "WEAK"

    return {
        "field": field,
        "status": "SCORED",
        "n_test_rows": n_test_field,
        "n_no_cluster": n_no_cluster,
        "spread_edges": [round(e, 4) for e in edges],
        "vs_cluster_spread_q": {"verdict": overall, "levels": detail},
    }


def main():
    print(f"loading pair log (last {WINDOW_DAYS}d) ...")
    rows, groups_all_fc, n_scanned, lo_win, hi_win = _load_pairs()
    print("loading cluster_spread ...")
    cluster_idx, cq1, cq3 = _load_cluster_spread()
    print(f"  cluster ticks: {len(cluster_idx):,}  Q1<={cq1}  Q3>={cq3}")

    spread_by_vt = {k: max(fcs) - min(fcs)
                    for k, fcs in groups_all_fc.items()
                    if len(fcs) >= MIN_RUNS_PER_VT}

    if not spread_by_vt:
        print("VERDICT: INSUFFICIENT DATA — no valid_times with >=3 runs.")
        return 0
    if cq1 is None or cq3 is None:
        print("VERDICT: INSUFFICIENT DATA — cluster_spread quartiles unavailable.")
        return 0

    max_vt = max(vt for _, vt in spread_by_vt.keys())
    max_date = datetime.strptime(max_vt[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    results = [analyze_field(f, rows, spread_by_vt, cluster_idx, cq1, cq3, test_start)
               for f in TARGET_FIELDS]

    lines = []
    lines.append("=" * 100)
    lines.append("STAGE 2 — cross-run spread orthogonality vs cluster_spread_q (incumbent c1 axis)")
    lines.append("=" * 100)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Held-out (test): last {HELD_OUT_DAYS}d.")
    lines.append(f"Min runs per valid_time: {MIN_RUNS_PER_VT}.  "
                 f"Ortho gate: Q5/Q1 |err| ratio >= {ORTHO_GATE} inside every non-thin level.")
    lines.append(f"Redundant ceiling: ratio <= {REDUNDANT_CEILING}.  "
                 f"Min n per level (Q1, Q5): {MIN_N_LEVEL}.")
    lines.append(f"cluster_spread cuts: Q1<={cq1:.3f}  Q3>={cq3:.3f}  "
                 f"(field={SPREAD_FIELD}, join tol ±{TICK_JOIN_TOLERANCE_MIN}min).")
    lines.append(f"Test starts: {test_start}   Scanned {n_scanned:,} pair-log rows.")
    lines.append("")

    lines.append(f"{'field':>6}  {'verdict':>12}   levels detail (Q1/Q23/Q4)")
    lines.append("-" * 100)
    ortho_fields = []
    for r in results:
        if r["status"] != "SCORED":
            lines.append(f"{r['field']:>6}  {'-':>12}   ({r['status']})")
            continue
        v = r["vs_cluster_spread_q"]["verdict"]
        def _short(d):
            parts = []
            for lv in ("Q1", "Q23", "Q4"):
                det = d.get(lv, {})
                if not det:
                    parts.append(f"{lv}:—")
                elif det.get("status") == "THIN":
                    parts.append(f"{lv}:THIN({det['n_q1']}/{det['n_q5']})")
                else:
                    parts.append(f"{lv}:{det.get('ratio','?')}")
            return ", ".join(parts)
        lines.append(f"{r['field']:>6}  {v:>12}   [{_short(r['vs_cluster_spread_q']['levels'])}]")
        if v == "ORTHOGONAL":
            ortho_fields.append(r["field"])
    lines.append("")

    if len(ortho_fields) >= PROMOTE_MIN_FIELDS:
        lines.append(f"VERDICT: PROMOTE — cross-run spread is ORTHOGONAL to cluster_spread_q "
                     f"in {len(ortho_fields)} field(s): {', '.join(ortho_fields)}. "
                     f"Cleared for wiring into c1_confidence_calibration_v2 as a 6th axis.")
    elif ortho_fields:
        lines.append(f"VERDICT: NARROW PROMOTE — {len(ortho_fields)} field(s) ortho: "
                     f"{', '.join(ortho_fields)}.  Below full-axis gate ({PROMOTE_MIN_FIELDS}).")
    else:
        lines.append("VERDICT: REDUNDANT — cross-run spread signal collapses inside cluster_spread_q "
                     "levels.  The two signals track each other; do NOT add as new axis.")

    text = "\n".join(lines)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump({
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_lo": lo_win,
            "window_hi": hi_win,
            "test_start": test_start,
            "cluster_q1": cq1,
            "cluster_q3": cq3,
            "results": results,
            "ortho_fields": ortho_fields,
        }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
