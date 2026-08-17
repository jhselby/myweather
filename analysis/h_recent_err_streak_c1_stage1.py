"""Stage 1 — recent-|err|-streak orthogonality vs c1 axes + cross-run spread.

Follow-on to h_recent_err_streak_stage0.py (08-10) which showed on held-out
data that past-3h hourly-mean |err| stratifies the next hour's |err| by
2-4x on 5 (field, band) cells: t/4-12 (4.18x), t/13-36 (3.59x),
wd/4-12 (2.67x), wd/13-36 (2.50x), wg/4-12 (2.03x).

Two questions:
  (a) does it survive conditioning on the c1 incumbents (transition, pt)?
  (b) does it survive conditioning on cross-run spread, which the 08-10
      sweep memo flagged as the most likely confound (both are
      "difficulty proxies")?

Cross-run spread is itself PROMOTE-status from h_cross_run_spread_c1_stage1
(ahead in the queue), so we test against it as if already-live.

Method mirrors [[project_cross_run_spread_c1_axis]] Stage 1:
  * TRAIN-fit quintile edges for past-3h |err|.
  * For each conditioning axis A and level a, compare test |err|
    in past-3h Q1 vs Q5, restricted to rows in level a.
  * Per axis verdict:
      ORTHOGONAL — ratio >= ORTHO_GATE in every non-thin level
      CONFOUNDED — mixed
      REDUNDANT  — collapses everywhere
      THIN       — not enough n

Overall verdict per cell: PROMOTE if ORTHOGONAL to ALL three axes.
Aggregate PROMOTE if >= 3 of 5 cells clear.
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
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_recent_err_streak_c1_stage1.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_recent_err_streak_c1_stage1.json")

WINDOW_DAYS = 45
HELD_OUT_DAYS = 7
MIN_N_LEVEL = 40
MIN_RUNS_PER_VT = 3
ORTHO_GATE = 1.35
REDUNDANT_CEILING = 1.10
PROMOTE_MIN_CELLS = 3  # of 5

# Cells that cleared Stage 0.
HIT_CELLS = [
    ("t",  "4-12",  4, 12),
    ("t",  "13-36", 13, 36),
    ("wd", "4-12",  4, 12),
    ("wd", "13-36", 13, 36),
    ("wg", "4-12",  4, 12),
]

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


def h_step(k, n):
    dt = datetime.strptime(k, "%Y-%m-%dT%H")
    return (dt + timedelta(hours=n)).strftime("%Y-%m-%dT%H")


def _band_of(lh, lo, hi):
    return lh is not None and lo <= lh <= hi


def _load():
    WIN = rolling_windows(recent_days=WINDOW_DAYS, prior_days=0)
    lo_win, hi_win = WIN.A_LO, WIN.A_HI
    target_fields = {c[0] for c in HIT_CELLS}
    # per-field per-hour |err| aggregates for streak signal
    hourly_by_cell = defaultdict(dict)  # (f, band) -> {hour_key: [sum_abs, n]}
    # per-row store (test-only later), tagged with axis levels
    rows = []
    # per (field, vt) forecast list for spread
    fc_by_vt = defaultdict(list)
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
            if f not in target_fields:
                continue
            lh = r.get("lead_h")
            err = prod_error(r)
            fc = r.get("forecast")
            if lh is None or err is None or fc is None:
                continue
            # Accumulate hourly-mean |err| per matching cell for streak signal
            k = vt[:13]
            aerr = abs(float(err))
            for cf, band, lo, hi in HIT_CELLS:
                if cf == f and _band_of(lh, lo, hi):
                    bucket = hourly_by_cell[(f, band)]
                    if k not in bucket:
                        bucket[k] = [0.0, 0]
                    bucket[k][0] += aerr
                    bucket[k][1] += 1
            # Also track per-row for orthogonality bucketing
            sfc = r.get("state_fc") or {}
            sob = r.get("state_obs") or {}
            rfc = sfc.get("regime_synoptic")
            rob = sob.get("regime_synoptic")
            transition = None
            if rfc is not None and rob is not None:
                transition = "transition" if rfc != rob else "stable"
            pt = pt_label(sfc.get("pressure_trend_hpa_3h"))
            rows.append({
                "field": f, "vt": vt, "lh": int(lh),
                "aerr": aerr,
                "transition": transition,
                "pt": pt,
            })
            fc_by_vt[(f, vt)].append(float(fc))
    return rows, hourly_by_cell, fc_by_vt, n_scanned, lo_win, hi_win


def analyze_cell(field, band, lo, hi, rows, hourly_by_cell, spread_by_vt, test_start):
    hourly = {k: v[0] / v[1] for k, v in hourly_by_cell[(field, band)].items() if v[1] > 0}
    # Build train pt3 to fit edges
    train_pt3 = []
    for k in hourly:
        p1 = hourly.get(h_step(k, -1))
        p2 = hourly.get(h_step(k, -2))
        p3 = hourly.get(h_step(k, -3))
        if p1 is None or p2 is None or p3 is None:
            continue
        if k[:10] < test_start:
            train_pt3.append((p1 + p2 + p3) / 3.0)
    if len(train_pt3) < 200:
        return {"field": field, "band": band, "status": "THIN_TRAIN",
                "n_train_pt3": len(train_pt3)}
    edges = _quintile_edges(sorted(train_pt3))

    # Bucket test rows by axis-level x streak-quintile.
    per_axis = {
        "transition":   defaultdict(lambda: defaultdict(list)),
        "pt":           defaultdict(lambda: defaultdict(list)),
        "spread":       defaultdict(lambda: defaultdict(list)),
    }
    # spread axis: we need to bin spread — do the same TRAIN quintile fit as
    # h_cross_run_spread_c1_stage1 (per-field, only vt's with >=3 runs).
    train_spreads = [sp for (f2, vt), sp in spread_by_vt.items()
                     if f2 == field and vt[:10] < test_start]
    if len(train_spreads) < 200:
        spread_edges = None
    else:
        spread_edges = _quintile_edges(sorted(train_spreads))

    n_test_rows = 0
    for r in rows:
        if r["field"] != field or not (lo <= r["lh"] <= hi):
            continue
        if r["vt"][:10] < test_start:
            continue
        k = r["vt"][:13]
        p1 = hourly.get(h_step(k, -1))
        p2 = hourly.get(h_step(k, -2))
        p3 = hourly.get(h_step(k, -3))
        if p1 is None or p2 is None or p3 is None:
            continue
        pt3 = (p1 + p2 + p3) / 3.0
        qbin = _bin(pt3, edges)
        aerr = r["aerr"]
        if r["transition"] is not None:
            per_axis["transition"][r["transition"]][qbin].append(aerr)
        if r["pt"] is not None:
            per_axis["pt"][r["pt"]][qbin].append(aerr)
        if spread_edges is not None:
            sp = spread_by_vt.get((field, r["vt"]))
            if sp is not None:
                sp_lvl = "spread_Q" + str(_bin(sp, spread_edges) + 1)
                per_axis["spread"][sp_lvl][qbin].append(aerr)
        n_test_rows += 1

    def verdict_for(axis_bucket):
        verdicts_per_level = []
        detail = {}
        for level, qbins in axis_bucket.items():
            q1 = qbins.get(0, [])
            q5 = qbins.get(4, [])
            n1, n5 = len(q1), len(q5)
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
    sp_v, sp_d = verdict_for(per_axis["spread"])

    return {
        "field": field, "band": band, "status": "SCORED",
        "n_test_rows": n_test_rows,
        "streak_edges": [round(e, 4) for e in edges],
        "spread_edges": [round(e, 4) for e in spread_edges] if spread_edges else None,
        "vs_transition": {"verdict": trans_v, "levels": trans_d},
        "vs_pt":         {"verdict": pt_v,    "levels": pt_d},
        "vs_spread":     {"verdict": sp_v,    "levels": sp_d},
    }


def main():
    print(f"loading pair log (last {WINDOW_DAYS}d) ...")
    rows, hourly_by_cell, fc_by_vt, n_scanned, lo_win, hi_win = _load()

    spread_by_vt = {k: max(v) - min(v) for k, v in fc_by_vt.items()
                    if len(v) >= MIN_RUNS_PER_VT}

    if not hourly_by_cell:
        print("VERDICT: INSUFFICIENT DATA — no rows in window.")
        return 0

    all_keys = [k for bucket in hourly_by_cell.values() for k in bucket]
    max_key = max(all_keys)
    max_date = datetime.strptime(max_key[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    results = [analyze_cell(f, band, lo, hi, rows, hourly_by_cell, spread_by_vt, test_start)
               for (f, band, lo, hi) in HIT_CELLS]

    lines = []
    lines.append("=" * 100)
    lines.append("STAGE 1 — recent-|err|-streak orthogonality vs c1 axes + cross-run spread")
    lines.append("=" * 100)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Held-out (test): last {HELD_OUT_DAYS}d.")
    lines.append(f"Ortho gate: Q5/Q1 |err| ratio >= {ORTHO_GATE} in every non-thin level.")
    lines.append(f"Redundant ceiling: ratio <= {REDUNDANT_CEILING} everywhere.  "
                 f"Min n per level (Q1, Q5): {MIN_N_LEVEL}.")
    lines.append(f"Cells: {', '.join(f + '/' + b for f, b, _, _ in HIT_CELLS)}")
    lines.append(f"Test starts: {test_start}   Scanned {n_scanned:,} pair-log rows.")
    lines.append("")

    lines.append(f"{'cell':>10}  {'vs trans':>12}  {'vs pt':>10}  {'vs spread':>12}   "
                 f"n_test")
    lines.append("-" * 100)

    def _short(d):
        parts = []
        for lv, det in d.items():
            if det.get("status") == "THIN":
                parts.append(f"{lv}:THIN({det['n_q1']}/{det['n_q5']})")
            else:
                parts.append(f"{lv}:{det.get('ratio','?')}")
        return ", ".join(parts)

    promote_cells = []
    partial_cells = []
    for r in results:
        cell = f"{r['field']}/{r['band']}"
        if r["status"] != "SCORED":
            lines.append(f"{cell:>10}  {'-':>12}  {'-':>10}  {'-':>12}   "
                         f"({r['status']})")
            continue
        vt = r["vs_transition"]["verdict"]
        pv = r["vs_pt"]["verdict"]
        sv = r["vs_spread"]["verdict"]
        lines.append(f"{cell:>10}  {vt:>12}  {pv:>10}  {sv:>12}   "
                     f"n={r['n_test_rows']}")
        lines.append(f"           trans[{_short(r['vs_transition']['levels'])}]")
        lines.append(f"              pt[{_short(r['vs_pt']['levels'])}]")
        lines.append(f"          spread[{_short(r['vs_spread']['levels'])}]")
        real = [v for v in (vt, pv, sv) if v not in ("THIN",)]
        if real and all(v == "ORTHOGONAL" for v in real):
            promote_cells.append(cell)
        elif any(v == "ORTHOGONAL" for v in real):
            partial_cells.append(cell)
    lines.append("")

    if len(promote_cells) >= PROMOTE_MIN_CELLS:
        lines.append(f"VERDICT: PROMOTE — recent-|err|-streak orthogonal to transition + pt + "
                     f"spread on {len(promote_cells)} cell(s): {', '.join(promote_cells)}.")
        lines.append("Warrants Stage 2: add per-cell streak quintile as c1 axis "
                     "(narrow — promoted cells only), curate, ship.")
    elif promote_cells or partial_cells:
        all_partial = sorted(set(promote_cells + partial_cells))
        lines.append(f"VERDICT: NARROW PROMOTE — orthogonal to at least one axis in "
                     f"{len(all_partial)} cell(s): {', '.join(all_partial)}. "
                     f"Full gate ({PROMOTE_MIN_CELLS} cells ortho to all axes) not met.")
    else:
        lines.append("VERDICT: REDUNDANT — recent-|err|-streak signal collapses inside "
                     "incumbent axes.  Likely disguised as cross-run spread or pt.  "
                     "Do not promote.")

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
            "promote_cells": promote_cells,
            "partial_cells": partial_cells,
        }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
