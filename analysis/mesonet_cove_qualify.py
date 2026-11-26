"""Cove-side qualification of the Mesonet for temperature and dew point.

Implements docs/PLAN_mesonet_model_split.md section 1.8, drafted 11-22 BEFORE any score was computed.
Thresholds below are copied from that section; nothing here was tuned on results.

References (kept apart, never pooled):
  yard     KMAMARBL124, not in the Mesonet. Provisional: its day and night offset against the mean of
           Driftwood Rd and Neptune Rd is estimated on the first CALIBRATION_DAYS days that have yard
           data, then fixed; scoring uses only later days.
  driftwood / neptune   Tempest stations that ARE in the Mesonet, so the Mesonet is recomputed WITHOUT
           that station (analysis.mesonet_recompute, the collector's own functions) before comparing.

Rows: hourly means, same hours for every comparison, day (08-18 ET) and night separately.

GUARD (the rule is a minimum of MIN_NIGHTS nights per reference): until EVERY reference has that many
nights, the output has NO scores, only the night counts. The verdict combines all references, so reading
one early is reading a partial result. This stops anyone peeking before the pre-registered dates
(yard Dec 2, Driftwood Rd Dec 6).

Verdict for t (dp likewise with its own limits): qualifies only if
  A. precision (held-out agreement, from mesonet_validation.json) passes, AND
  B. against the yard, after its offset, night rows: |bias| <= BIAS_MAX[f] and, for t, RMSE <= RMSE_MAX, AND
  C. against Driftwood Rd and Neptune Rd: |night bias| <= NIGHT_BIAS_STATION_MAX each.
Otherwise t stays graded on URMA, labelled, as now.

    PYTHONPATH=. .venv/bin/python -m analysis.mesonet_cove_qualify [archive_dir]
Writes analysis/mesonet_cove_qualify.json. The Cove adjustment (1.7) is a separate shadow and is not
part of this plain-Mesonet comparison.
"""
import collections
import json
import math
import statistics as st
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from analysis.mesonet_recompute import recompute_dp, recompute_t, station_inputs
from weather_collector.utils import magnus_dew_point_f

ET = ZoneInfo("America/New_York")
OUT = Path(__file__).parent / "mesonet_cove_qualify.json"

# --- pre-registered (plan 1.8, 11-22) ---
MIN_NIGHTS = 10
BIAS_MAX = {"t": 0.5, "dp": 0.7}          # F, per reference, day and night separately
RMSE_MAX = {"t": 1.0}                      # F, hourly RMSE of the difference (t only)
NIGHT_BIAS_STATION_MAX = 1.0               # F, vs Driftwood Rd and Neptune Rd
# --- fixed here, before any scoring (not stated numerically in 1.8) ---
CALIBRATION_DAYS = 5                       # first N yard days fit the yard offset; scoring uses later days
MIN_NIGHT_HOURS = 8                        # a calendar night counts only with this many valid hours
STATIONS = {"driftwood": "226429", "neptune": "192019"}
YARD = "KMAMARBL124"
EARLIEST = {"yard": "2026-12-02", "driftwood": "2026-12-06"}   # plan 1.8; Neptune Rd already has the nights


def period_of(hour_epoch):
    return "day" if 8 <= datetime.fromtimestamp(hour_epoch, ET).hour < 18 else "night"


def night_key(hour_epoch):
    """Calendar night an ET night hour belongs to (hours 00-07 belong to the previous evening)."""
    d = datetime.fromtimestamp(hour_epoch, ET)
    return (d.date() if d.hour >= 18 else (d - timedelta(days=1)).date()).isoformat()


def hourly(points):
    """{hour_epoch: mean} from [(epoch_seconds, value)]."""
    acc = collections.defaultdict(list)
    for ep, v in points:
        if v is not None:
            acc[int(ep // 3600 * 3600)].append(v)
    return {h: st.mean(v) for h, v in acc.items()}


def count_nights(hours):
    c = collections.Counter(night_key(h) for h in hours if period_of(h) == "night")
    return sum(1 for n in c.values() if n >= MIN_NIGHT_HOURS)


def compare(mes, ref, hours):
    """{period: {n, bias, rmse}} of mes - ref over the given hours (both present)."""
    out = {}
    for per in ("day", "night"):
        d = [mes[h] - ref[h] for h in sorted(hours) if h in mes and h in ref and period_of(h) == per]
        out[per] = ({"n": len(d), "bias": round(st.mean(d), 3), "rmse": round(math.sqrt(st.mean(x * x for x in d)), 3)}
                    if d else {"n": 0, "bias": None, "rmse": None})
    return out


def yard_offsets(yard, anchor, hours):
    """{period: mean(yard - anchor)} on the calibration hours; anchor = mean of Driftwood and Neptune."""
    out = {}
    for per in ("day", "night"):
        d = [yard[h] - anchor[h] for h in hours if h in yard and h in anchor and period_of(h) == per]
        out[per] = st.mean(d) if d else None
    return out


def verdict(field, yard_res, station_res, precision_ok):
    """Plan 1.8 verdict for one field from the per-reference results (each None when ineligible)."""
    if yard_res is None or any(r is None for r in station_res.values()):
        return {"qualifies": None, "why": "not eligible yet: a reference has fewer than %d nights" % MIN_NIGHTS}
    y = yard_res["night"]
    b_ok = y["bias"] is not None and abs(y["bias"]) <= BIAS_MAX[field] and (
        field not in RMSE_MAX or y["rmse"] <= RMSE_MAX[field])
    c_ok = all(r["night"]["bias"] is not None and abs(r["night"]["bias"]) <= NIGHT_BIAS_STATION_MAX
               for r in station_res.values())
    return {"qualifies": bool(precision_ok and b_ok and c_ok), "A_precision": bool(precision_ok),
            "B_yard_night": bool(b_ok), "C_stations_night": bool(c_ok)}


def score(ticks, stations_meta, yard_obs, precision_ok, today=None):
    """ticks: {ts: tick}; yard_obs: [(epoch, {"t":..., "dp":...})]. Returns the output dict."""
    inp = station_inputs(stations_meta)
    out = {"min_nights": MIN_NIGHTS, "calibration_days": CALIBRATION_DAYS, "references": {}, "verdict": {}}
    mes_all = {f: [] for f in ("t", "dp")}
    mes_wo = {k: {f: [] for f in ("t", "dp")} for k in STATIONS}
    stn = {k: {f: [] for f in ("t", "dp")} for k in STATIONS}
    for ts, tick in sorted(ticks.items()):
        ep = datetime.strptime(ts, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).timestamp()
        for f, fn in (("t", recompute_t), ("dp", recompute_dp)):
            v = fn(tick, inp)
            v = v[0] if isinstance(v, tuple) else v
            mes_all[f].append((ep, v))
            for k, sid in STATIONS.items():
                w = fn(tick, inp, drop={sid})
                mes_wo[k][f].append((ep, w[0] if isinstance(w, tuple) else w))
        for k, sid in STATIONS.items():
            r = (tick.get("readings") or {}).get(sid) or {}
            if r.get("valid") and r.get("t") is not None:
                stn[k]["t"].append((ep, r["t"]))
                if r.get("rh"):
                    stn[k]["dp"].append((ep, magnus_dew_point_f(r["t"], r["rh"])))
    H = {k: {f: hourly(v) for f, v in d.items()} for k, d in mes_wo.items()}
    S = {k: {f: hourly(v) for f, v in d.items()} for k, d in stn.items()}
    A = {f: hourly(v) for f, v in mes_all.items()}
    Y = {f: hourly([(e, o.get(f)) for e, o in yard_obs]) for f in ("t", "dp")}

    results = {"yard": {}, "driftwood": {}, "neptune": {}}
    nights = {}
    for f in ("t", "dp"):
        # stations: Mesonet without that station vs that station's own reading (offset-corrected by the archive)
        for k in STATIONS:
            hrs = set(H[k][f]) & set(S[k][f])
            nights.setdefault(k, count_nights(hrs))
            results[k][f] = compare(H[k][f], S[k][f], hrs)
        # yard: offset from calibration days, scored on later days
        yh = sorted(set(Y[f]) & set(A[f]))
        days = sorted({datetime.fromtimestamp(h, ET).date().isoformat() for h in yh})
        cal, score_days = set(days[:CALIBRATION_DAYS]), set(days[CALIBRATION_DAYS:])
        anchor = {h: st.mean([S["driftwood"][f][h], S["neptune"][f][h]]) for h in S["driftwood"][f]
                  if h in S["neptune"][f]}
        cal_hours = [h for h in yh if datetime.fromtimestamp(h, ET).date().isoformat() in cal]
        off = yard_offsets(Y[f], anchor, cal_hours)
        yc = {h: Y[f][h] - (off[period_of(h)] or 0.0) for h in yh}
        sc_hours = [h for h in yh if datetime.fromtimestamp(h, ET).date().isoformat() in score_days]
        nights.setdefault("yard", count_nights(sc_hours))
        results["yard"][f] = {"offset_day": None if off["day"] is None else round(off["day"], 3),
                              "offset_night": None if off["night"] is None else round(off["night"], 3),
                              **compare(A[f], yc, sc_hours)}
    all_eligible = all(nights.get(ref, 0) >= MIN_NIGHTS for ref in results)
    for ref in results:
        eligible = nights.get(ref, 0) >= MIN_NIGHTS
        out["references"][ref] = {"nights": nights.get(ref, 0), "eligible": eligible,
                                  "earliest_read": EARLIEST.get(ref, "with the other references")}
        # The verdict combines every reference, so NO score is shown until all of them have the
        # pre-registered minimum: reading one reference early is reading a partial result.
        if all_eligible:
            out["references"][ref]["scores"] = results[ref]
    for f in ("t", "dp"):
        yr = results["yard"][f] if out["references"]["yard"]["eligible"] else None
        sr = {k: (results[k][f] if out["references"][k]["eligible"] else None) for k in STATIONS}
        out["verdict"][f] = verdict(f, yr, sr, precision_ok.get(f, False))
    return out


def main():
    from analysis.l2_loo_score import load
    from analysis.mesonet_vs_urma import _cat
    arch = sys.argv[1] if len(sys.argv) > 1 else None
    ticks = load(arch)
    days = sorted({t[:10] for t in ticks})
    meta = {}
    yard = []
    for d in days:
        doc = _cat(f"station_readings/{d}.json") or {}
        meta.update(doc.get("stations") or {})
        for ep_rows in [((_cat(f"wu_readings/{d}.json") or {}).get("obs") or {}).get(YARD, [])]:
            yard += [(r["ep"], {"t": r.get("t"), "dp": r.get("dp")}) for r in ep_rows]
    prec = {}
    try:
        v = json.load(open(Path(__file__).parent / "mesonet_validation.json"))["verdict"]
        prec = {f: bool(v[f]["pass_A"]) for f in ("t", "dp")}
    except Exception:
        pass
    res = score(ticks, meta, yard, prec)
    OUT.write_text(json.dumps(res, indent=1))
    for k, r in res["references"].items():
        print(f"{k}: {r['nights']} nights, {'ELIGIBLE' if r['eligible'] else 'not eligible until >= %d nights (earliest read %s)' % (MIN_NIGHTS, r['earliest_read'])}")
    for f, v in res["verdict"].items():
        print(f, v)


if __name__ == "__main__":
    main()
