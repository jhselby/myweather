"""Stage 1 — observed T-Td depression orthogonality vs incumbent c1 axes.

Follow-on to h_depression_cloud_confidence_stage0.py which found on held-out
data that low-depression (moist) rows have 2.33x |err| of high-depression
(dry) rows for cl and ch cloud fields.

Question this script answers: does the depression signal survive conditioning
on the c1 axes already in use (transition, pt)?  If yes -> promote as a new
c1 axis for cloud fields.  If it collapses inside every incumbent level ->
the effect is that axis in disguise.

Method (mirrors h_cross_run_spread_c1_stage1.py):
  1. Compute obs depression per valid_time = obs_t - obs_dp.
  2. Quintile per field, TRAIN-fit edges only.  Held-out = last 7d.
  3. For each incumbent axis A and each level a, compute test mean|err|
     in the LOW dep quintile (Q1, moist) vs HIGH quintile (Q5, dry),
     restricted to rows in a.
  4. Verdict per (field, axis) — direction is Q1/Q5 (moist harder):
       ORTHOGONAL — ratio >= ORTHO_GATE inside EVERY non-thin level.
       CONFOUNDED — ratio >= ORTHO_GATE only inside minority level(s).
       REDUNDANT  — ratio < REDUNDANT_CEILING inside every level.
       THIN       — not enough n in the level to judge.

  Overall PROMOTE if ORTHOGONAL to BOTH incumbent axes on both fields (cl, ch).
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
from _prod import prod_error  # noqa: E402
from _windows import rolling_windows  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_depression_cloud_confidence_c1_stage1.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_depression_cloud_confidence_c1_stage1.json")

WINDOW_DAYS = 45
HELD_OUT_DAYS = 7
LEAD_LO = 4
LEAD_HI = 24
MIN_N_LEVEL = 40
ORTHO_GATE = 1.35        # Q1/Q5 |err| ratio (moist over dry) inside a level
REDUNDANT_CEILING = 1.10
TARGET_FIELDS = ["cl", "ch", "cc", "cm"]  # Stage 0 hit cl+ch; carry cc+cm for
                                          #  completeness (they'll show THIN or FLAT)
PROMOTE_MIN_FIELDS = 2

PT_BINS = [
    ("falling_fast", float("-inf"), -1.0),
    ("falling",      -1.0,         -0.3),
    ("flat",         -0.3,         0.3),
    ("rising",       0.3,          float("inf")),
]


def pt_label(v):
    if v is None:
        return None
    try:
        v = float(v)
    except Exception:
        return None
    for lab, lo, hi in PT_BINS:
        if lo <= v < hi:
            return lab
    return None


def _quintile_edges(sorted_vals):
    n = len(sorted_vals)
    return [sorted_vals[int(n * p)] for p in (0.20, 0.40, 0.60, 0.80)]


def _bin(x, edges):
    for i, e in enumerate(edges):
        if x < e:
            return i
    return len(edges)


def _load():
    WIN = rolling_windows(recent_days=WINDOW_DAYS, prior_days=0)
    lo_win, hi_win = WIN.A_LO, WIN.A_HI
    obs_t = {}
    obs_dp = {}
    cloud_rows = []
    n_scanned = 0
    with open(cached_path(URL), "rb") as fh:
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
            elif f in TARGET_FIELDS:
                lh = r.get("lead_h")
                err = prod_error(r)
                if lh is None or not (LEAD_LO <= lh <= LEAD_HI) or err is None:
                    continue
                sfc = r.get("state_fc") or {}
                sob = r.get("state_obs") or {}
                rfc = sfc.get("regime_synoptic")
                rob = sob.get("regime_synoptic")
                transition = None
                if rfc is not None and rob is not None:
                    transition = "transition" if rfc != rob else "stable"
                pt = pt_label(sfc.get("pressure_trend_hpa_3h"))
                cloud_rows.append({
                    "field": f,
                    "vt": vt,
                    "err": abs(float(err)),
                    "transition": transition,
                    "pt": pt,
                })
    dep = {vt: obs_t[vt] - obs_dp[vt] for vt in obs_t.keys() & obs_dp.keys()}
    return cloud_rows, dep, n_scanned, lo_win, hi_win


def analyze_field(field, cloud_rows, dep, test_start):
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
    edges = _quintile_edges(sorted(train_deps))

    per_axis = {
        "transition": defaultdict(lambda: defaultdict(list)),
        "pt":         defaultdict(lambda: defaultdict(list)),
    }
    n_test_field = 0
    for r in cloud_rows:
        if r["field"] != field:
            continue
        if r["vt"][:10] < test_start:
            continue
        d = dep.get(r["vt"])
        if d is None:
            continue
        qbin = _bin(d, edges)
        if r["transition"] is not None:
            per_axis["transition"][r["transition"]][qbin].append(r["err"])
        if r["pt"] is not None:
            per_axis["pt"][r["pt"]][qbin].append(r["err"])
        n_test_field += 1

    def verdict_for(axis_bucket):
        verdicts_per_level = []
        detail = {}
        for level, qbins in axis_bucket.items():
            q1 = qbins.get(0, [])
            q5 = qbins.get(4, [])
            n1 = len(q1)
            n5 = len(q5)
            if n1 < MIN_N_LEVEL or n5 < MIN_N_LEVEL:
                detail[level] = {"n_q1": n1, "n_q5": n5, "status": "THIN"}
                verdicts_per_level.append("THIN")
                continue
            m1 = mean(q1)
            m5 = mean(q5)
            # Moist (Q1) harder than dry (Q5) — ratio is Q1/Q5.
            ratio = m1 / m5 if m5 > 0 else 0
            detail[level] = {"n_q1": n1, "n_q5": n5,
                             "mae_q1": round(m1, 3), "mae_q5": round(m5, 3),
                             "ratio": round(ratio, 2)}
            if ratio >= ORTHO_GATE:
                verdicts_per_level.append("HIT")
            elif ratio <= REDUNDANT_CEILING:
                verdicts_per_level.append("FLAT")
            else:
                verdicts_per_level.append("WEAK")

        real = [v for v in verdicts_per_level if v != "THIN"]
        if not real:
            return "THIN", detail
        if all(v == "HIT" for v in real):
            return "ORTHOGONAL", detail
        if all(v == "FLAT" for v in real):
            return "REDUNDANT", detail
        if any(v == "HIT" for v in real) and any(v in ("FLAT", "WEAK") for v in real):
            return "CONFOUNDED", detail
        return "WEAK", detail

    trans_v, trans_d = verdict_for(per_axis["transition"])
    pt_v, pt_d = verdict_for(per_axis["pt"])

    return {
        "field": field,
        "status": "SCORED",
        "n_test_rows": n_test_field,
        "dep_edges": [round(e, 3) for e in edges],
        "vs_transition": {"verdict": trans_v, "levels": trans_d},
        "vs_pt": {"verdict": pt_v, "levels": pt_d},
    }


def main():
    print(f"loading pair log (last {WINDOW_DAYS}d) ...")
    cloud_rows, dep, n_scanned, lo_win, hi_win = _load()

    if not cloud_rows or not dep:
        print("VERDICT: INSUFFICIENT DATA — cloud rows or depression map empty.")
        return 0

    max_vt = max(r["vt"] for r in cloud_rows)
    max_date = datetime.strptime(max_vt[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    results = [analyze_field(f, cloud_rows, dep, test_start) for f in TARGET_FIELDS]

    lines = []
    lines.append("=" * 100)
    lines.append("STAGE 1 — observed T-Td depression orthogonality vs c1 axes (transition, pt)")
    lines.append("=" * 100)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Held-out (test): last {HELD_OUT_DAYS}d.  "
                 f"Lead band: {LEAD_LO}-{LEAD_HI}h.")
    lines.append(f"Ortho gate: Q1/Q5 |err| ratio (moist/dry) >= {ORTHO_GATE} "
                 f"inside every non-thin level.")
    lines.append(f"Redundant ceiling: ratio <= {REDUNDANT_CEILING} everywhere.  "
                 f"Min n per level (Q1, Q5): {MIN_N_LEVEL}.")
    lines.append(f"Test starts: {test_start}   Scanned {n_scanned:,} pair-log rows.")
    lines.append("")

    lines.append(f"{'field':>6}  {'vs transition':>15}  {'vs pt':>10}   levels detail")
    lines.append("-" * 100)
    both_ortho_fields = []
    for r in results:
        if r["status"] != "SCORED":
            lines.append(f"{r['field']:>6}  {'-':>15}  {'-':>10}   ({r['status']})")
            continue
        vt = r["vs_transition"]["verdict"]
        pv = r["vs_pt"]["verdict"]

        def _short(d):
            parts = []
            for lv, det in d.items():
                if det.get("status") == "THIN":
                    parts.append(f"{lv}:THIN({det['n_q1']}/{det['n_q5']})")
                else:
                    parts.append(f"{lv}:{det.get('ratio','?')}")
            return ", ".join(parts)
        trans_short = _short(r["vs_transition"]["levels"])
        pt_short = _short(r["vs_pt"]["levels"])
        lines.append(f"{r['field']:>6}  {vt:>15}  {pv:>10}   "
                     f"trans[{trans_short}]  pt[{pt_short}]")
        if vt == "ORTHOGONAL" and pv == "ORTHOGONAL":
            both_ortho_fields.append(r["field"])
    lines.append("")

    scored = [r for r in results if r["status"] == "SCORED"]
    any_orth = [r["field"] for r in scored
                if r["vs_transition"]["verdict"] == "ORTHOGONAL"
                or r["vs_pt"]["verdict"] == "ORTHOGONAL"]
    if len(both_ortho_fields) >= PROMOTE_MIN_FIELDS:
        lines.append(f"VERDICT: PROMOTE — depression is ORTHOGONAL to BOTH transition and pt "
                     f"in {len(both_ortho_fields)} field(s): {', '.join(both_ortho_fields)}.")
        lines.append("Warrants Stage 2: check ortho vs cross_run_spread (new c1 axis candidate) "
                     "and vs cluster_spread_q before wiring as a c1 cloud axis.")
    elif any_orth:
        lines.append(f"VERDICT: NARROW PROMOTE — orthogonal to at least one axis in "
                     f"{len(any_orth)} field(s): {', '.join(any_orth)}.  "
                     f"Full-axis promotion gate ({PROMOTE_MIN_FIELDS} fields ortho to both) "
                     f"not met.")
    else:
        lines.append("VERDICT: REDUNDANT — depression signal collapses inside incumbent "
                     "c1 axes.  Do not promote.")

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
            "results": results,
            "both_ortho_fields": both_ortho_fields,
        }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
