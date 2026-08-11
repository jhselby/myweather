"""Stage 1 — forecast-magnitude quintile orthogonality vs incumbent c1 axes.

Follow-on to h_forecast_magnitude_confidence_stage0.py which found on
held-out data that:
  * t   high forecasts harder (Q5/Q1 ~2.94x — hot afternoons)
  * wg  high forecasts harder (Q5/Q1 ~2.72x — high wind)
  * dp  low  forecasts harder (Q1/Q5 ~2.77x — dry air)

Question this script answers: does the forecast-magnitude signal survive
conditioning on the c1 axes already in use (transition, pt)?  If yes ->
promote as a per-field c1 axis.  If it collapses inside every incumbent
level -> the effect is that axis in disguise.

Method mirrors h_cross_run_spread_c1_stage1.py.
Direction is set per field:
  hi (t, wg):  ratio Q5/Q1 — high-forecast bin harder.
  lo (dp):     ratio Q1/Q5 — low-forecast bin harder.

Overall PROMOTE if ORTHOGONAL to BOTH incumbent axes on >= 2 fields.
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
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_forecast_magnitude_confidence_c1_stage1.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_forecast_magnitude_confidence_c1_stage1.json")

WINDOW_DAYS = 45
HELD_OUT_DAYS = 7
LEAD_LO = 4
LEAD_HI = 12
MIN_N_LEVEL = 40
ORTHO_GATE = 1.35
REDUNDANT_CEILING = 1.10
FIELDS = {
    "t":  "hi",
    "wg": "hi",
    "dp": "lo",
}
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
    rows_by_field = defaultdict(list)
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
            if f not in FIELDS:
                continue
            lh = r.get("lead_h")
            if lh is None or not (LEAD_LO <= lh <= LEAD_HI):
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
            rows_by_field[f].append({
                "vt": vt,
                "fc": float(fc),
                "err": abs(float(err)),
                "transition": transition,
                "pt": pt,
            })
    return rows_by_field, n_scanned, lo_win, hi_win


def analyze_field(field, direction, rows_by_field, test_start):
    rows = rows_by_field.get(field, [])
    train_fcs = [r["fc"] for r in rows if r["vt"][:10] < test_start]
    if len(train_fcs) < 500:
        return {"field": field, "status": "THIN_TRAIN",
                "n_train": len(train_fcs)}
    edges = _quintile_edges(sorted(train_fcs))

    per_axis = {
        "transition": defaultdict(lambda: defaultdict(list)),
        "pt":         defaultdict(lambda: defaultdict(list)),
    }
    n_test = 0
    for r in rows:
        if r["vt"][:10] < test_start:
            continue
        qbin = _bin(r["fc"], edges)
        if r["transition"] is not None:
            per_axis["transition"][r["transition"]][qbin].append(r["err"])
        if r["pt"] is not None:
            per_axis["pt"][r["pt"]][qbin].append(r["err"])
        n_test += 1

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
            if direction == "hi":
                ratio = m5 / m1 if m1 > 0 else 0
            else:  # "lo"
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
        "direction": direction,
        "status": "SCORED",
        "n_test_rows": n_test,
        "fc_edges": [round(e, 4) for e in edges],
        "vs_transition": {"verdict": trans_v, "levels": trans_d},
        "vs_pt": {"verdict": pt_v, "levels": pt_d},
    }


def main():
    print(f"loading pair log (last {WINDOW_DAYS}d) ...")
    rows_by_field, n_scanned, lo_win, hi_win = _load()

    if not rows_by_field:
        print("VERDICT: INSUFFICIENT DATA — no target-field rows in window.")
        return 0

    max_vt = max(r["vt"] for rows in rows_by_field.values() for r in rows)
    max_date = datetime.strptime(max_vt[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    results = [analyze_field(f, d, rows_by_field, test_start)
               for f, d in FIELDS.items()]

    lines = []
    lines.append("=" * 100)
    lines.append("STAGE 1 — forecast-magnitude orthogonality vs c1 axes (transition, pt)")
    lines.append("=" * 100)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Held-out (test): last {HELD_OUT_DAYS}d.  "
                 f"Lead band: {LEAD_LO}-{LEAD_HI}h.")
    lines.append(f"Ortho gate: hard/easy |err| ratio (dir-specific) >= {ORTHO_GATE} "
                 f"inside every non-thin level.")
    lines.append(f"Redundant ceiling: ratio <= {REDUNDANT_CEILING} everywhere.  "
                 f"Min n per level (Q1, Q5): {MIN_N_LEVEL}.")
    lines.append(f"Test starts: {test_start}   Scanned {n_scanned:,} pair-log rows.")
    lines.append("")

    lines.append(f"{'field':>6}  {'dir':>4}  {'vs transition':>15}  {'vs pt':>10}   levels detail")
    lines.append("-" * 100)
    both_ortho_fields = []
    for r in results:
        if r["status"] != "SCORED":
            lines.append(f"{r['field']:>6}  {'-':>4}  {'-':>15}  {'-':>10}   ({r['status']})")
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
        lines.append(f"{r['field']:>6}  {r['direction']:>4}  {vt:>15}  {pv:>10}   "
                     f"trans[{trans_short}]  pt[{pt_short}]")
        if vt == "ORTHOGONAL" and pv == "ORTHOGONAL":
            both_ortho_fields.append(r["field"])
    lines.append("")

    scored = [r for r in results if r["status"] == "SCORED"]
    any_orth = [r["field"] for r in scored
                if r["vs_transition"]["verdict"] == "ORTHOGONAL"
                or r["vs_pt"]["verdict"] == "ORTHOGONAL"]
    if len(both_ortho_fields) >= PROMOTE_MIN_FIELDS:
        lines.append(f"VERDICT: PROMOTE — forecast-magnitude is ORTHOGONAL to BOTH transition "
                     f"and pt in {len(both_ortho_fields)} field(s): "
                     f"{', '.join(both_ortho_fields)}.")
        lines.append("Warrants Stage 2: check ortho vs cross_run_spread and "
                     "vs cluster_spread_q before wiring as a per-field c1 axis.")
    elif any_orth:
        lines.append(f"VERDICT: NARROW PROMOTE — orthogonal to at least one axis in "
                     f"{len(any_orth)} field(s): {', '.join(any_orth)}.  "
                     f"Full-axis promotion gate ({PROMOTE_MIN_FIELDS} fields ortho to both) "
                     f"not met.")
    else:
        lines.append("VERDICT: REDUNDANT — forecast-magnitude signal collapses inside "
                     "incumbent c1 axes.  Do not promote.")

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
