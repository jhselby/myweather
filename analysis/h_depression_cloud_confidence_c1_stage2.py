"""Stage 2 — observed T-Td depression orthogonality vs cluster_spread_q and
cross_run_spread quintile (the two novel/incumbent difficulty axes).

Stage 1 (08-11) cleared PROMOTE for cl+ch vs transition + pt.  Before wiring
depression as a c1 cloud axis, must show it survives conditioning on both
difficulty-family axes:
  - cluster_spread_q  (incumbent axis_2, inter-source spread_t)
  - cross_run_spread  (Stage 2 PROMOTE 08-11 — same-model intra-run spread)

Method (mirrors depression Stage 1 + cross-run Stage 2):
  1. Compute obs_depression per valid_time = obs_t - obs_dp.
  2. Per field (cl, ch): quintile depression on TRAIN, held-out = last 7d.
  3. For each incumbent axis level, compute test mean|cloud_err| in the
     LOW depression quintile (Q1, moist) vs HIGH (Q5, dry).  Direction is
     Q1/Q5 (moist harder), matching Stage 1.
  4. Verdict per (field, incumbent):
       ORTHOGONAL — Q1/Q5 ratio >= ORTHO_GATE inside every non-thin level.
       CONFOUNDED — HIT in minority level(s) only.
       REDUNDANT  — ratio < REDUNDANT_CEILING inside every level.
       THIN       — not enough n per level.

  Overall PROMOTE if ORTHOGONAL to BOTH incumbents on BOTH fields.
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
SPREAD_FIELD = "spread_t"

OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_depression_cloud_confidence_c1_stage2.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_depression_cloud_confidence_c1_stage2.json")

WINDOW_DAYS = 45
HELD_OUT_DAYS = 7
LEAD_LO = 4
LEAD_HI = 24
MIN_N_LEVEL = 40
ORTHO_GATE = 1.35
REDUNDANT_CEILING = 1.10
MIN_RUNS_PER_VT = 3
TICK_JOIN_TOLERANCE_MIN = 15
TARGET_FIELDS = ["cl", "ch"]
PROMOTE_MIN_FIELDS = 2


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
    return by_tick, s[n // 4], s[(3 * n) // 4]


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


def _load():
    """Pass over pair log building:
      - obs_t / obs_dp maps per valid_time (for depression)
      - cloud rows for cl/ch with (vt, obs_time, err, lead in 4-24h)
      - per-(field, vt) forecast list for cross_run_spread (all TARGET_FIELDS
        AND t so we can also use t-spread if cl/ch have too few runs — but
        stick to per-field for now).
    """
    WIN = rolling_windows(recent_days=WINDOW_DAYS, prior_days=0)
    lo_win, hi_win = WIN.A_LO, WIN.A_HI
    obs_t = {}
    obs_dp = {}
    cloud_rows = []
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
            if f == "t":
                ob = r.get("observed")
                if ob is not None and vt not in obs_t:
                    obs_t[vt] = float(ob)
            elif f == "dp":
                ob = r.get("observed")
                if ob is not None and vt not in obs_dp:
                    obs_dp[vt] = float(ob)
            if f in TARGET_FIELDS:
                fc = r.get("forecast")
                err = r.get("error")
                lh = r.get("lead_h")
                ot = r.get("obs_time") or ""
                if fc is None or err is None or lh is None:
                    continue
                groups[(f, vt)].append(float(fc))
                if not (LEAD_LO <= lh <= LEAD_HI):
                    continue
                cloud_rows.append({
                    "field": f,
                    "vt": vt,
                    "obs_time": ot,
                    "err": abs(float(err)),
                })
    dep = {vt: obs_t[vt] - obs_dp[vt] for vt in obs_t.keys() & obs_dp.keys()}
    return cloud_rows, dep, groups, n_scanned, lo_win, hi_win


def analyze_field_vs(field, cloud_rows, dep, spread_by_vt, cluster_idx,
                     cq1, cq3, test_start):
    train_deps = []
    for r in cloud_rows:
        if r["field"] != field:
            continue
        d = dep.get(r["vt"])
        if d is None:
            continue
        if r["vt"][:10] < test_start:
            train_deps.append(d)
    if len(train_deps) < 200:
        return {"field": field, "status": "THIN_TRAIN_DEP",
                "n_train_dep": len(train_deps)}
    dep_edges = _quintile_edges(sorted(train_deps))

    # Also need cross-run-spread quintiles PER FIELD from train
    train_spreads = [sp for (f, vt), sp in spread_by_vt.items()
                     if f == field and vt[:10] < test_start]
    xr_edges = None
    if len(train_spreads) >= 200:
        xr_edges = _quintile_edges(sorted(train_spreads))

    per_axis = {
        "cluster_spread_q": defaultdict(lambda: defaultdict(list)),
        "cross_run_spread": defaultdict(lambda: defaultdict(list)),
    }
    n_test = 0
    n_no_cluster = 0
    n_no_xr = 0
    for r in cloud_rows:
        if r["field"] != field:
            continue
        if r["vt"][:10] < test_start:
            continue
        d = dep.get(r["vt"])
        if d is None:
            continue
        dep_bin = _bin(d, dep_edges)

        cv = _lookup_spread(cluster_idx, _tick_key(r["obs_time"]))
        cq = _cluster_q(cv, cq1, cq3)
        if cq is not None:
            per_axis["cluster_spread_q"][cq][dep_bin].append(r["err"])
        else:
            n_no_cluster += 1

        if xr_edges is not None:
            sp = spread_by_vt.get((field, r["vt"]))
            if sp is not None:
                xr_bin = _bin(sp, xr_edges)
                # collapse to Q1/Q23/Q4 to mirror cluster_spread_q shape
                if xr_bin == 0:
                    xr_level = "Q1"
                elif xr_bin == 4:
                    xr_level = "Q5"
                else:
                    xr_level = "Q234"
                per_axis["cross_run_spread"][xr_level][dep_bin].append(r["err"])
            else:
                n_no_xr += 1
        n_test += 1

    def verdict_for(axis_bucket, level_order):
        verdicts = []
        detail = {}
        for level in level_order:
            qbins = axis_bucket.get(level, {})
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
            # Q1 = moist (low dep), Q5 = dry.  Direction: moist harder -> Q1/Q5.
            ratio = m1 / m5 if m5 > 0 else 0
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
            return "THIN", detail
        if all(v == "HIT" for v in real):
            return "ORTHOGONAL", detail
        if all(v == "FLAT" for v in real):
            return "REDUNDANT", detail
        if any(v == "HIT" for v in real) and any(v in ("FLAT", "WEAK") for v in real):
            return "CONFOUNDED", detail
        return "WEAK", detail

    cl_v, cl_d = verdict_for(per_axis["cluster_spread_q"], ("Q1", "Q23", "Q4"))
    xr_v, xr_d = verdict_for(per_axis["cross_run_spread"], ("Q1", "Q234", "Q5"))

    return {
        "field": field,
        "status": "SCORED",
        "n_test_rows": n_test,
        "n_no_cluster": n_no_cluster,
        "n_no_xr": n_no_xr,
        "dep_edges": [round(e, 3) for e in dep_edges],
        "xr_edges": [round(e, 3) for e in xr_edges] if xr_edges else None,
        "vs_cluster_spread_q": {"verdict": cl_v, "levels": cl_d},
        "vs_cross_run_spread": {"verdict": xr_v, "levels": xr_d},
    }


def main():
    print(f"loading pair log (last {WINDOW_DAYS}d) ...")
    cloud_rows, dep, groups, n_scanned, lo_win, hi_win = _load()
    print("loading cluster_spread ...")
    cluster_idx, cq1, cq3 = _load_cluster_spread()
    print(f"  cluster ticks: {len(cluster_idx):,}  Q1<={cq1}  Q3>={cq3}")

    spread_by_vt = {k: max(fcs) - min(fcs)
                    for k, fcs in groups.items()
                    if len(fcs) >= MIN_RUNS_PER_VT}

    if not cloud_rows or not dep:
        print("VERDICT: INSUFFICIENT DATA.")
        return 0

    max_vt = max(r["vt"] for r in cloud_rows)
    max_date = datetime.strptime(max_vt[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    results = [analyze_field_vs(f, cloud_rows, dep, spread_by_vt,
                                cluster_idx, cq1, cq3, test_start)
               for f in TARGET_FIELDS]

    lines = []
    lines.append("=" * 100)
    lines.append("STAGE 2 — depression orthogonality vs cluster_spread_q + cross_run_spread (fields cl, ch)")
    lines.append("=" * 100)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Held-out (test): last {HELD_OUT_DAYS}d.  "
                 f"Lead band: {LEAD_LO}-{LEAD_HI}h.")
    lines.append(f"Ortho gate: dep-Q1/Q5 |err| ratio (moist/dry) >= {ORTHO_GATE} inside every non-thin level.")
    lines.append(f"cluster_spread cuts: Q1<={cq1:.3f}  Q3>={cq3:.3f}. "
                 f"cross_run_spread: per-field quintiles (Q1 vs Q5, Q234 middle).")
    lines.append(f"Test starts: {test_start}   Scanned {n_scanned:,} pair-log rows.")
    lines.append("")

    def _short(d):
        parts = []
        for lv, det in d.items():
            if det.get("status") == "THIN":
                parts.append(f"{lv}:THIN({det['n_q1']}/{det['n_q5']})")
            else:
                parts.append(f"{lv}:{det.get('ratio','?')}")
        return ", ".join(parts)

    both_ortho_fields = []
    for r in results:
        if r["status"] != "SCORED":
            lines.append(f"  {r['field']}: ({r['status']})")
            continue
        cv = r["vs_cluster_spread_q"]["verdict"]
        xv = r["vs_cross_run_spread"]["verdict"]
        lines.append(f"  {r['field']}: vs cluster_spread_q={cv}  vs cross_run_spread={xv}")
        lines.append(f"      cluster levels: [{_short(r['vs_cluster_spread_q']['levels'])}]")
        lines.append(f"      xr-spread levels: [{_short(r['vs_cross_run_spread']['levels'])}]")
        if cv == "ORTHOGONAL" and xv == "ORTHOGONAL":
            both_ortho_fields.append(r["field"])
    lines.append("")

    scored = [r for r in results if r["status"] == "SCORED"]
    any_orth = [r["field"] for r in scored
                if r["vs_cluster_spread_q"]["verdict"] == "ORTHOGONAL"
                or r["vs_cross_run_spread"]["verdict"] == "ORTHOGONAL"]
    if len(both_ortho_fields) >= PROMOTE_MIN_FIELDS:
        lines.append(f"VERDICT: PROMOTE — depression ORTHOGONAL to BOTH difficulty axes "
                     f"on {len(both_ortho_fields)} field(s): {', '.join(both_ortho_fields)}. "
                     f"Cleared for c1 cloud-axis wiring alongside (or independent of) cross_run_spread.")
    elif any_orth:
        lines.append(f"VERDICT: NARROW PROMOTE — {len(any_orth)} field(s) ortho to at least one: "
                     f"{', '.join(any_orth)}. Full gate not met.")
    else:
        lines.append("VERDICT: REDUNDANT — depression signal collapses inside both difficulty axes.")

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
            "both_ortho_fields": both_ortho_fields,
        }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
