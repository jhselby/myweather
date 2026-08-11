"""Stage 1 — cross-run ensemble spread as an orthogonal c1 confidence axis.

Follow-on to h_cross_run_spread_stage0.py (08-10) which showed on held-out
data that same-vt cross-run spread cleanly stratifies |err| for 8 fields
(t 3.6x, wd 7.3x, wg 2.6x, dp 2.5x, h 2.4x, pr 2.6x, ws 1.9x, cl 238x).

Question this script answers: does the spread signal survive conditioning
on the axes c1 already uses?  If yes -> promote as a 6th c1 axis.
If it collapses inside every incumbent level -> the effect is that axis
in disguise (probably transition or pt), not new information.

Incumbent axes tested (drawn straight from pair-log fields, same as
c1_confidence_calibration_v2 uses):
  * transition_flag   := (state_fc.regime_synoptic != state_obs.regime_synoptic)
  * pt_bin            := pressure_trend_hpa_3h binned into 4 groups

Method (per [[feedback_orthogonality_gate]] / [[project_walkforward_l3l4_validator]]):
  1. Compute cross-run spread per (field, valid_time).
  2. Quintile per field, TRAIN-fit edges only.  Held-out = last 7d.
  3. For each incumbent axis A and each level a, compute test mean|err|
     in the LOW spread quintile vs HIGH quintile, restricted to rows in a.
  4. Verdict per (field, axis):
       ORTHOGONAL — ratio >= ORTHO_GATE inside EVERY level of A that has
                    enough n.  Signal is not axis A in disguise.
       CONFOUNDED — ratio >= ORTHO_GATE only inside minority level(s).
       REDUNDANT  — ratio < 1.10 inside every level; signal collapses.
       THIN       — not enough n in the level to judge.

  Overall PROMOTE if ORTHOGONAL to BOTH incumbent axes on >= 4 fields.
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

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_cross_run_spread_c1_stage1.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_cross_run_spread_c1_stage1.json")

WINDOW_DAYS = 45
HELD_OUT_DAYS = 7
MIN_RUNS_PER_VT = 3
MIN_N_LEVEL = 40      # per level of an incumbent axis (test set)
ORTHO_GATE = 1.35     # Q5/Q1 |err| ratio inside a level must clear this
REDUNDANT_CEILING = 1.10
TARGET_FIELDS = ["t", "wd", "wg", "dp", "h", "pr", "ws"]  # cl skipped: bottom-bin near-zero
PROMOTE_MIN_FIELDS = 4  # need >=4 fields ORTHOGONAL to BOTH incumbents

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
    rows = []  # dict per row with what we need
    groups = defaultdict(list)  # (field, vt) -> [forecast, ...] for spread
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
            if f not in TARGET_FIELDS:
                continue
            fc = r.get("forecast")
            err = r.get("error")
            if fc is None or err is None:
                continue
            sfc = r.get("state_fc") or {}
            sob = r.get("state_obs") or {}
            rfc = sfc.get("regime_synoptic")
            rob = sob.get("regime_synoptic")
            transition = None
            if rfc is not None and rob is not None:
                transition = "transition" if rfc != rob else "stable"
            pt = pt_label(sfc.get("pressure_trend_hpa_3h"))
            rows.append({
                "field": f,
                "vt": vt,
                "fc": float(fc),
                "err": float(err),
                "transition": transition,
                "pt": pt,
            })
            groups[(f, vt)].append(float(fc))
    return rows, groups, n_scanned, lo_win, hi_win


def analyze_field(field, rows, spread_by_vt, test_start):
    # Attach spread and Q-bin per row, using TRAIN edges
    train_spreads = []
    for (f, vt), sp in spread_by_vt.items():
        if f == field and vt[:10] < test_start:
            train_spreads.append(sp)
    if len(train_spreads) < 200:
        return {"field": field, "status": "THIN_TRAIN_SPREAD",
                "n_train_spreads": len(train_spreads)}
    edges = _quintile_edges(sorted(train_spreads))

    # Bucket rows by (test/train, incumbent_axis_level, spread_bin)
    per_axis = {
        "transition": defaultdict(lambda: defaultdict(list)),  # level -> {Qi:[|err|]}
        "pt":         defaultdict(lambda: defaultdict(list)),
    }
    n_test_field = 0
    for r in rows:
        if r["field"] != field:
            continue
        if r["vt"][:10] < test_start:
            continue  # test-only
        sp = spread_by_vt.get((field, r["vt"]))
        if sp is None:
            continue
        # skip cases where too few runs contributed (already length-filtered in spread_by_vt)
        qbin = _bin(sp, edges)
        aerr = abs(r["err"])
        if r["transition"] is not None:
            per_axis["transition"][r["transition"]][qbin].append(aerr)
        if r["pt"] is not None:
            per_axis["pt"][r["pt"]][qbin].append(aerr)
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
            ratio = m5 / m1 if m1 > 0 else 0
            detail[level] = {"n_q1": n1, "n_q5": n5,
                             "mae_q1": round(m1, 3), "mae_q5": round(m5, 3),
                             "ratio": round(ratio, 2)}
            if ratio >= ORTHO_GATE:
                verdicts_per_level.append("HIT")
            elif ratio <= REDUNDANT_CEILING:
                verdicts_per_level.append("FLAT")
            else:
                verdicts_per_level.append("WEAK")

        # Aggregate: ORTHOGONAL if every non-THIN level HIT
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
        "spread_edges": [round(e, 4) for e in edges],
        "vs_transition": {"verdict": trans_v, "levels": trans_d},
        "vs_pt": {"verdict": pt_v, "levels": pt_d},
    }


def main():
    print(f"loading pair log (last {WINDOW_DAYS}d) ...")
    rows, groups_all_fc, n_scanned, lo_win, hi_win = _load()

    # Compute per-(field, vt) spread only where >= MIN_RUNS_PER_VT runs
    spread_by_vt = {}
    for k, fcs in groups_all_fc.items():
        if len(fcs) >= MIN_RUNS_PER_VT:
            spread_by_vt[k] = max(fcs) - min(fcs)

    if not spread_by_vt:
        print("VERDICT: INSUFFICIENT DATA — no valid_times with >=3 runs.")
        return 0

    max_vt = max(vt for _, vt in spread_by_vt.keys())
    max_date = datetime.strptime(max_vt[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    results = [analyze_field(f, rows, spread_by_vt, test_start) for f in TARGET_FIELDS]

    lines = []
    lines.append("=" * 100)
    lines.append("STAGE 1 — cross-run spread orthogonality vs c1 axes (transition, pt)")
    lines.append("=" * 100)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Held-out (test): last {HELD_OUT_DAYS}d.")
    lines.append(f"Min runs per valid_time: {MIN_RUNS_PER_VT}.  "
                 f"Ortho gate: Q5/Q1 |err| ratio >= {ORTHO_GATE} inside every non-thin level.")
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
        # short levels detail
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
        lines.append(f"VERDICT: PROMOTE — cross-run spread is ORTHOGONAL to BOTH transition and pt "
                     f"in {len(both_ortho_fields)} field(s): {', '.join(both_ortho_fields)}.")
        lines.append("Warrants Stage 2: add spread quintile as 6th c1 axis in "
                     "c1_confidence_calibration_v2, curate cells, ship narrow.")
    elif any_orth:
        lines.append(f"VERDICT: NARROW PROMOTE — orthogonal to at least one axis in "
                     f"{len(any_orth)} field(s): {', '.join(any_orth)}.  "
                     f"Full-axis promotion gate ({PROMOTE_MIN_FIELDS} fields ortho to both) "
                     f"not met.")
    else:
        lines.append("VERDICT: REDUNDANT — cross-run spread signal collapses inside incumbent "
                     "c1 axes.  Do not promote as new c1 axis.")

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
