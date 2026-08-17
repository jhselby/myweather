"""Stage 1 — observed windspeed orthogonality vs incumbent c1 axes.

Follow-on to h_windspeed_t_confidence_stage0.py which showed that at short
lead (0-3h), t |err| grows monotonically across observed ws bins (top/bottom
ratio 1.92x on held-out).

Question: does the ws signal survive conditioning on the c1 axes already
in use for t (transition, pt)? If yes -> promote as a new c1 axis for t.
If it collapses inside every incumbent level -> the effect is that axis
in disguise.

Method (mirrors h_depression_cloud_confidence_c1_stage1.py):
  1. Join short-lead (0-3h) t rows with same-valid_time observed ws.
  2. Fixed bins matching Stage 0: LOW = 0-5 kt, HIGH = 15+ kt.
  3. For each incumbent axis A and each level a, compute test mean|err|
     in HIGH ws vs LOW ws, restricted to rows in a.
  4. Verdict per axis — direction is HIGH/LOW (windy harder):
       ORTHOGONAL — ratio >= ORTHO_GATE inside EVERY non-thin level.
       CONFOUNDED — ratio >= ORTHO_GATE only inside minority level(s).
       REDUNDANT  — ratio < REDUNDANT_CEILING inside every level.
       THIN       — not enough n in the level to judge.

  Overall PROMOTE if ORTHOGONAL to BOTH incumbent axes (single field: t).
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
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_windspeed_t_confidence_c1_stage1.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_windspeed_t_confidence_c1_stage1.json")

WINDOW_DAYS = 45
HELD_OUT_DAYS = 7
LEAD_MAX = 3
MIN_N_LEVEL = 40
ORTHO_GATE = 1.35
REDUNDANT_CEILING = 1.10
LOW_WS_HI = 5.0     # LOW bin = [0, 5)
HIGH_WS_LO = 10.0   # HIGH bin = [10, inf) — Stage 0's top two bins (10-15 + 15+)

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


def ws_bucket(ws):
    if ws < LOW_WS_HI:
        return "LOW"
    if ws >= HIGH_WS_LO:
        return "HIGH"
    return None  # middle range excluded


def _load():
    WIN = rolling_windows(recent_days=WINDOW_DAYS, prior_days=0)
    lo_win, hi_win = WIN.A_LO, WIN.A_HI
    ws_obs = {}
    t_rows = []
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
            if f == "ws":
                ob = r.get("observed")
                if ob is not None and vt not in ws_obs:
                    ws_obs[vt] = float(ob)
            elif f == "t":
                lh = r.get("lead_h")
                err = prod_error(r)
                if lh is None or lh > LEAD_MAX or err is None:
                    continue
                sfc = r.get("state_fc") or {}
                sob = r.get("state_obs") or {}
                rfc = sfc.get("regime_synoptic")
                rob = sob.get("regime_synoptic")
                transition = None
                if rfc is not None and rob is not None:
                    transition = "transition" if rfc != rob else "stable"
                pt = pt_label(sfc.get("pressure_trend_hpa_3h"))
                t_rows.append({
                    "vt": vt,
                    "err": abs(float(err)),
                    "transition": transition,
                    "pt": pt,
                })
    return t_rows, ws_obs, n_scanned, lo_win, hi_win


def analyze(t_rows, ws_obs, test_start):
    per_axis = {
        "transition": defaultdict(lambda: defaultdict(list)),
        "pt":         defaultdict(lambda: defaultdict(list)),
    }
    n_test = 0
    n_train_matched = 0
    for r in t_rows:
        ws = ws_obs.get(r["vt"])
        if ws is None:
            continue
        bucket = ws_bucket(ws)
        if bucket is None:
            continue
        if r["vt"][:10] < test_start:
            n_train_matched += 1
            continue
        if r["transition"] is not None:
            per_axis["transition"][r["transition"]][bucket].append(r["err"])
        if r["pt"] is not None:
            per_axis["pt"][r["pt"]][bucket].append(r["err"])
        n_test += 1

    def verdict_for(axis_bucket):
        verdicts_per_level = []
        detail = {}
        for level, buckets in axis_bucket.items():
            lo = buckets.get("LOW", [])
            hi = buckets.get("HIGH", [])
            nl = len(lo)
            nh = len(hi)
            if nl < MIN_N_LEVEL or nh < MIN_N_LEVEL:
                detail[level] = {"n_low": nl, "n_high": nh, "status": "THIN"}
                verdicts_per_level.append("THIN")
                continue
            ml = mean(lo)
            mh = mean(hi)
            ratio = mh / ml if ml > 0 else 0
            detail[level] = {"n_low": nl, "n_high": nh,
                             "mae_low": round(ml, 3), "mae_high": round(mh, 3),
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
        "n_train_matched": n_train_matched,
        "n_test_rows": n_test,
        "vs_transition": {"verdict": trans_v, "levels": trans_d},
        "vs_pt": {"verdict": pt_v, "levels": pt_d},
    }


def main():
    print(f"loading pair log (last {WINDOW_DAYS}d) ...")
    t_rows, ws_obs, n_scanned, lo_win, hi_win = _load()

    if not t_rows or not ws_obs:
        print("VERDICT: INSUFFICIENT DATA — no t rows or ws map empty.")
        return 0

    max_vt = max(r["vt"] for r in t_rows)
    max_date = datetime.strptime(max_vt[:10], "%Y-%m-%d").date()
    test_start = (max_date - timedelta(days=HELD_OUT_DAYS)).isoformat()

    result = analyze(t_rows, ws_obs, test_start)

    lines = []
    lines.append("=" * 100)
    lines.append("STAGE 1 — observed ws (HIGH vs LOW) orthogonality vs c1 axes (transition, pt) — field=t")
    lines.append("=" * 100)
    lines.append(f"Window: last {WINDOW_DAYS}d.  Held-out (test): last {HELD_OUT_DAYS}d.  "
                 f"Lead cap: {LEAD_MAX}h.")
    lines.append(f"Ortho gate: HIGH/LOW |err| ratio >= {ORTHO_GATE} inside every non-thin level.")
    lines.append(f"Redundant ceiling: ratio <= {REDUNDANT_CEILING} everywhere.  "
                 f"Min n per level (LOW, HIGH): {MIN_N_LEVEL}.")
    lines.append(f"LOW bucket = [0, {LOW_WS_HI:.0f}) kt.  HIGH bucket = [{HIGH_WS_LO:.0f}, inf) kt.  "
                 f"Middle range excluded.")
    lines.append(f"Test starts: {test_start}   Scanned {n_scanned:,} pair-log rows.  "
                 f"n_test={result['n_test_rows']:,}")
    lines.append("")

    def _short(d):
        parts = []
        for lv, det in d.items():
            if det.get("status") == "THIN":
                parts.append(f"{lv}:THIN({det['n_low']}/{det['n_high']})")
            else:
                parts.append(f"{lv}:{det.get('ratio','?')}")
        return ", ".join(parts)

    vt = result["vs_transition"]["verdict"]
    pv = result["vs_pt"]["verdict"]
    lines.append(f"vs transition: {vt}   levels: [{_short(result['vs_transition']['levels'])}]")
    lines.append(f"vs pt:         {pv}   levels: [{_short(result['vs_pt']['levels'])}]")
    lines.append("")

    if vt == "ORTHOGONAL" and pv == "ORTHOGONAL":
        lines.append("VERDICT: PROMOTE — observed ws is ORTHOGONAL to BOTH transition and pt for t.")
        lines.append("Warrants Stage 2: check ortho vs cross_run_spread (new c1 axis candidate) "
                     "and vs cluster_spread_q before wiring as a c1 t axis.")
    elif vt == "ORTHOGONAL" or pv == "ORTHOGONAL":
        lines.append(f"VERDICT: NARROW PROMOTE — orthogonal to one axis only "
                     f"(transition={vt}, pt={pv}).")
    else:
        lines.append(f"VERDICT: REDUNDANT — ws signal collapses inside incumbent c1 axes "
                     f"(transition={vt}, pt={pv}).  Do not promote.")

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
            "result": result,
        }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
