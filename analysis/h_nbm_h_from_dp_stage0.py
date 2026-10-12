"""Stage 0: replace NBM's raw humidity with RH(NBM t, NBM dp) on the NBM path.

10-12 finding (project_10_12_session): NBM's native dewpoint beats the dewpoint we
derive from NBM's own t and h, and RH computed from NBM t + NBM dp beats NBM's raw h
by ~13% (stable across every half-month since 08-20, ~17% at 12-47h). Served dp on
the NBM path is Magnus(l2_nbm t, l2_nbm h), so NBM's h error lands in dp too. Per
project_dp_is_derived_no_dp_work the fix belongs in h; dp then follows.

This tool rebuilds the live NBM h path on the derived input and scores served h and dp.
Two input arms:
  A  h_der_raw[j] = RH(raw_nbm t[j], raw_nbm dp[j])
  B  h_der_raw[j] = RH(served t[j], raw_nbm dp[j])   (10-12: arm A inherits NBM's t error —
     on 10-06 NBM t ran 4F cold and arm A's h ran +10 wet; B tests the obs-anchored t.
     B also lost 10-06 and 10-10, so those days are not explained by t alone)
For each arm:
  l2_nbm h      = raw[j] + ramp[j] * K * (consensus - raw[0])      (forecast_snapshot.py:345)
             -> new[j] = h_der_raw[j] + ramp[j] * (d0 + K * (raw[0] - h_der_raw[0]))
                where d0 = l2_nbm[0] - raw_nbm[0] (lead-0 row of the same run) and
                K = (d0 - (l2[0] - l1[0])) / (l1[0] - raw_nbm[0]) when |l1[0]-raw_nbm[0]| >= 3, else median K
  l1_blend h    = w * l1 + (1 - w) * raw_nbm  ->  served + (1 - w) * (h_der_raw - raw_nbm)
  dp (l2_nbm)   = Magnus(l2_nbm t, new l2_nbm h)
Rows served from HRRR layers are unchanged. The selector section reports, per cell,
whether the NBM terminal would beat the HRRR terminal more often after the change
(a selector refit would follow any ship).

Verdict (computed for arm A; B lost on the 30d read: h +3.9% vs +11.0%, dp +11% vs +24%) per (regime_runtime, lead band) cell for h: STABLE if n >= MIN_N in each
chronological half and the change cuts served h MAE by >= MIN_LIFT_PCT in both halves.
dp is reported alongside, not gated (dp is derived).

Aggregate-only Stage 0 tool. Changes nothing in production.

Run:  python3 -m analysis.h_nbm_h_from_dp_stage0   [--days 30]
"""
import argparse
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from _cache import pair_log_paths, RegimeRuntime
from _prod import prod_error
from weather_collector.utils import magnus_dew_point_f
from weather_collector.processors.corrected_hourly import _soft_ramp_factors
from weather_collector.processors import l1_static_blend

BANDS = (("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48))
MIN_N = 100
MIN_LIFT_PCT = 3.0
RAMP = _soft_ramp_factors(48)
OUT_TXT = os.path.join(HERE, "output", "h_nbm_h_from_dp_stage0.txt")


def band_of(lead):
    for name, lo, hi in BANDS:
        if lo <= lead < hi:
            return name
    return None


def _es(tf):
    c = (tf - 32) * 5 / 9
    return math.exp(17.625 * c / (243.04 + c))


def rh(tf, dpf):
    if tf is None or dpf is None:
        return None
    return min(100.0, 100.0 * _es(dpf) / _es(tf))


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def pct(old, new):
    return 100.0 * (old - new) / old if old else float("nan")


KEEP = ("obs_time", "lead_h", "observed", "applied_layer", "forecast_l1", "forecast_l2",
        "forecast_l4", "forecast_raw_nbm", "forecast_l2_nbm", "forecast_l1_blend_shadow")


def load(days):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
    paths = pair_log_paths()
    rr = RegimeRuntime()
    rr.prime(paths)
    runs = defaultdict(lambda: defaultdict(dict))  # run_time -> lead -> field -> row
    for p in paths:
        with open(p) as fh:
            for line in fh:
                if '"field": "t"' not in line and '"field": "h"' not in line and '"field": "dp"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                f = r.get("field")
                if f not in ("t", "h", "dp") or (r.get("obs_time") or "") < cutoff:
                    continue
                lead = r.get("lead_h")
                if lead is None or r.get("run_time") is None:
                    continue
                row = {k: r.get(k) for k in KEEP}
                row["prod_err"] = prod_error(r)
                if f == "h":
                    row["regime"] = rr.get(r)
                runs[r["run_time"]][int(lead)][f] = row
    return runs, rr.counts


def served_t(t):
    if t.get("observed") is None or t.get("prod_err") is None:
        return None
    return t["observed"] + t["prod_err"]


def run_k(lead0):
    """(d0, K) for a run from its lead-0 h row; K None when not identifiable."""
    h = lead0.get("h")
    if not h:
        return None, None
    raw0, l2n0, l1_0, l2_0 = (h.get("forecast_raw_nbm"), h.get("forecast_l2_nbm"),
                              h.get("forecast_l1"), h.get("forecast_l2"))
    if None in (raw0, l2n0):
        return None, None
    d0 = l2n0 - raw0
    if None in (l1_0, l2_0) or abs(l1_0 - raw0) < 3:
        return d0, None
    k = (d0 - (l2_0 - l1_0)) / (l1_0 - raw0)
    return d0, max(0.0, min(1.0, k))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()

    runs, rr_counts = load(args.days)
    ks = []
    run_meta = {}
    for rt, leads in runs.items():
        d0, k = run_k(leads.get(0, {}))
        lead0 = leads.get(0, {})
        der0 = {"A": None, "B": None}
        if "t" in lead0 and "dp" in lead0:
            der0["A"] = rh(lead0["t"].get("forecast_raw_nbm"), lead0["dp"].get("forecast_raw_nbm"))
            der0["B"] = rh(served_t(lead0["t"]), lead0["dp"].get("forecast_raw_nbm"))
        run_meta[rt] = (d0, k, der0)
        if k is not None:
            ks.append(k)
    k_med = statistics.median(ks) if ks else 1.0

    try:
        w_h = l1_static_blend._OMEGA_BY_FIELD["h"]
    except (AttributeError, KeyError):
        w_h = None

    recon = []
    out = []  # per h row: dict
    for rt, leads in runs.items():
        d0, k, der0 = run_meta[rt]
        h0 = leads.get(0, {}).get("h")
        for lead, g in leads.items():
            if lead >= 48 or not all(x in g for x in ("t", "h", "dp")):
                continue
            t, h, dp = g["t"], g["h"], g["dp"]
            o = h.get("observed")
            if o is None or h.get("prod_err") is None:
                continue
            raw = h.get("forecast_raw_nbm")
            if raw is None:
                continue
            ders = {"A": rh(t.get("forecast_raw_nbm"), dp.get("forecast_raw_nbm")),
                    "B": rh(served_t(t), dp.get("forecast_raw_nbm"))}
            if ders["A"] is None or ders["B"] is None:
                continue
            al = h.get("applied_layer")
            served = o + h["prod_err"]
            hrrr_term = h.get("forecast_l4") or h.get("forecast_l2")
            row = {
                "day": h["obs_time"][:10], "regime": h.get("regime") or "unknown", "band": band_of(lead),
                "routed": al, "served": abs(h["prod_err"]), "raw": abs(raw - o),
                "nbm_old": abs(h["forecast_l2_nbm"] - o) if h.get("forecast_l2_nbm") is not None else None,
                "hrrr": abs(hrrr_term - o) if hrrr_term is not None else None,
                "dp_served": None,
            }
            dp_ok = (dp.get("applied_layer") == "l2_nbm" and dp.get("prod_err") is not None
                     and dp.get("observed") is not None)
            if dp_ok:
                row["dp_served"] = abs(dp["prod_err"])
            skip = False
            for arm, der in ders.items():
                new_l2n = None
                if d0 is not None and der0[arm] is not None and h0 is not None:
                    kk = k if k is not None else k_med
                    new_l2n = der + RAMP[lead] * (d0 + kk * (h0["forecast_raw_nbm"] - der0[arm]))
                    if arm == "A" and h.get("forecast_l2_nbm") is not None:
                        recon.append(abs(raw + RAMP[lead] * d0 - h["forecast_l2_nbm"]))
                if al == "l2_nbm":
                    if new_l2n is None:
                        skip = True
                        break
                    cand = new_l2n
                elif al == "l1_blend":
                    if w_h is None:
                        skip = True
                        break
                    cand = served + (1 - w_h) * (der - raw)
                else:
                    cand = served
                cand = max(0.0, min(100.0, cand))
                row["cand" + arm] = abs(cand - o)
                row["der" + arm] = abs(der - o)
                row["nbm_new" + arm] = abs(new_l2n - o) if new_l2n is not None else None
                row["dp_cand" + arm] = None
                t2 = t.get("forecast_l2_nbm")
                if dp_ok and t2 is not None and new_l2n is not None:
                    v = magnus_dew_point_f(t2, max(1.0, min(100.0, new_l2n)))
                    row["dp_cand" + arm] = abs(v - dp["observed"]) if v is not None else None
            if not skip:
                out.append(row)

    days = sorted({r["day"] for r in out})
    mid = days[len(days) // 2] if days else ""
    L = []
    L.append(f"h_nbm_h_from_dp_stage0 — {datetime.now().strftime('%Y-%m-%d %H:%M')}  window {args.days}d  ({days[0] if days else '?'} .. {days[-1] if days else '?'}, halves split at {mid})")
    L.append(f"regime labels: {rr_counts}")
    L.append(f"K: median {k_med:.2f} over {len(ks)} identifiable runs (of {len(run_meta)}); blender w_h={w_h}")
    L.append(f"L2 ramp reconstruction check |raw + ramp*d0 - l2_nbm|: mean {mean(recon):.3f} (n={len(recon)}) — must be ~0 for the rebuild to mean anything")
    L.append("")
    L.append("Raw input (all rows): NBM h vs A = RH(NBM t, NBM dp), B = RH(served t, NBM dp)")
    for name, lo, hi in BANDS:
        rs = [r for r in out if r["band"] == name]
        rw, da, db = mean([r["raw"] for r in rs]), mean([r["derA"] for r in rs]), mean([r["derB"] for r in rs])
        L.append(f"  {name:6} n={len(rs):6}  raw {rw:5.2f}  A {da:5.2f} ({pct(rw, da):+.1f}%)  B {db:5.2f} ({pct(rw, db):+.1f}%)")
    L.append("")

    def summarize(rs, arm="A"):
        a, b = mean([r["served"] for r in rs]), mean([r["cand" + arm] for r in rs])
        return a, b, pct(a, b)

    def dp_pair(rs, arm="A"):
        ds = [r for r in rs if r["dp_served"] is not None and r["dp_cand" + arm] is not None]
        a, b = mean([r["dp_served"] for r in ds]), mean([r["dp_cand" + arm] for r in ds])
        return len(ds), a, b, pct(a, b)

    changed = [r for r in out if r["routed"] in ("l2_nbm", "l1_blend")]
    for arm in ("A", "B"):
        a, b, g = summarize(out, arm)
        L.append(f"[{arm}] Served h, all rows        n={len(out):6}  served {a:5.2f}  candidate {b:5.2f}  ({g:+.1f}%)")
        a, b, g = summarize(changed, arm)
        L.append(f"[{arm}] Served h, NBM-path rows   n={len(changed):6}  served {a:5.2f}  candidate {b:5.2f}  ({g:+.1f}%)")
        n2, a2, b2, g2 = dp_pair(out, arm)
        L.append(f"[{arm}] Served dp, l2_nbm rows    n={n2:6}  served {a2:5.2f}  candidate {b2:5.2f}  ({g2:+.1f}%)")
    L.append("")
    L.append("By day — h on NBM-path rows (served -> A / B) | dp on l2_nbm rows (served -> A / B):")
    for d in days:
        rs = [r for r in changed if r["day"] == d]
        if not rs:
            continue
        a, ba, ga = summarize(rs, "A")
        _, bb, gb = summarize(rs, "B")
        _, da, dca, _ = dp_pair([r for r in out if r["day"] == d], "A")
        _, _, dcb, _ = dp_pair([r for r in out if r["day"] == d], "B")
        L.append(f"  {d}  h n={len(rs):5} {a:5.2f} -> {ba:5.2f} ({ga:+6.1f}%) / {bb:5.2f} ({gb:+6.1f}%)   dp {da:5.2f} -> {dca:5.2f} / {dcb:5.2f}")
    L.append("")
    L.append(f"Per (regime, band) on NBM-path rows, arm A — STABLE needs n>={MIN_N} per half and >= {MIN_LIFT_PCT}% in both halves")
    L.append(f"  {'regime':12} {'band':6} {'n':>6} {'served':>7} {'cand':>7} {'lift':>7} {'half A':>7} {'half B':>7}  {'dp lift':>7}  {'B lift':>7}  verdict")
    cells = defaultdict(list)
    for r in changed:
        cells[(r["regime"], r["band"])].append(r)
    stable = []
    for key in sorted(cells):
        rs = cells[key]
        ha = [r for r in rs if r["day"] < mid]
        hb = [r for r in rs if r["day"] >= mid]
        a, b, g = summarize(rs)
        ga = summarize(ha)[2] if ha else float("nan")
        gb = summarize(hb)[2] if hb else float("nan")
        gdp = dp_pair(rs, "A")[3]
        g_a = summarize(rs, "B")[2]
        if len(ha) < MIN_N or len(hb) < MIN_N:
            v = "THIN"
        elif ga >= MIN_LIFT_PCT and gb >= MIN_LIFT_PCT:
            v = "STABLE"
            stable.append(key)
        elif ga < 0 and gb < 0:
            v = "HURTS"
        else:
            v = "MIXED"
        L.append(f"  {key[0]:12} {key[1]:6} {len(rs):6} {a:7.2f} {b:7.2f} {g:+6.1f}% {ga:+6.1f}% {gb:+6.1f}%  {gdp:+6.1f}%  {g_a:+6.1f}%  {v}")
    L.append("")
    L.append("Selector interaction (all rows, arm A): NBM terminal vs HRRR terminal h MAE, before -> after")
    L.append(f"  {'regime':12} {'band':6} {'n':>6} {'hrrr':>6} {'nbm old':>8} {'nbm new':>8}  winner old -> new")
    sel = defaultdict(list)
    for r in out:
        if r["hrrr"] is not None and r["nbm_old"] is not None and r["nbm_newA"] is not None:
            sel[(r["regime"], r["band"])].append(r)
    flips = 0
    for key in sorted(sel):
        rs = sel[key]
        if len(rs) < MIN_N:
            continue
        hh, no, nn = mean([r["hrrr"] for r in rs]), mean([r["nbm_old"] for r in rs]), mean([r["nbm_newA"] for r in rs])
        wo, wn = ("nbm" if no < hh else "hrrr"), ("nbm" if nn < hh else "hrrr")
        mark = "  <- flips" if wo != wn else ""
        flips += wo != wn
        L.append(f"  {key[0]:12} {key[1]:6} {len(rs):6} {hh:6.2f} {no:8.2f} {nn:8.2f}  {wo} -> {wn}{mark}")
    L.append("")
    if stable:
        L.append(f"VERDICT: STAGE 0 PROMOTE — arm A (RH(NBM t, NBM dp)): {len(stable)} (regime, band) cell(s) halves-stable >= {MIN_LIFT_PCT}% on served h: "
                 + ", ".join(f"{a}/{b}" for a, b in stable) + f". Selector winner flips in {flips} cell(s); a ship needs a selector refit.")
    else:
        L.append(f"VERDICT: STAGE 0 HOLD — no (regime, band) cell clears halves-stable >= {MIN_LIFT_PCT}% on served h.")
    text = "\n".join(L)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
