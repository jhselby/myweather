"""Step 1 of docs/PLAN_mesonet_model_split.md: is the Wyman Cove Mesonet good enough to be the truth?

The Mesonet value has no forecast in it: per-station offsets are fit against the other stations
(station_bias.py, leave-one-out), then hyperlocal.py takes a trimmed, distance-weighted mean by
octant. `station_temp = model_t + weighted_bias` cancels the model term exactly.

  1.1 the definition table (what the Mesonet value is per field, and its source)
  1.2 held-out accuracy: every tick, every station j, j's offset-corrected reading predicted by the
      median of the OTHER stations (the l2_loo_score method). This is precision (station agreement),
      not accuracy: stations sharing a sensor type can all be wrong together.
  1.3 independent cross-checks per UTC hour: Mesonet vs URMA (inverse-distance, as mesonet_vs_urma)
      and vs KBVY ASOS (IEM archive). Bias = mean(Mesonet - reference), by hour of day (ET).
  1.4 coverage: held-out MAE by number of other stations reporting; low-coverage threshold.
  1.5 gain question (record only): station_temp (K=1) vs corrected_temp (model + K*bias) vs URMA/KBVY.
  Verdict per field by the rule fixed in the plan doc before scoring (A precision, B accuracy).

Archive: gs://myweather-data/station_readings/ (Tempest, from 11-08). Exploratory, autumn only.

    PYTHONPATH=. .venv/bin/python -m analysis.mesonet_validation [dir_with_station_readings_json]
Writes analysis/mesonet_validation.json.
"""
import collections
import json
import math
import statistics as st
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from analysis.l2_loo_score import load
from analysis.mesonet_vs_urma import _cat, hour_epoch, snap
from weather_collector.processors.hyperlocal import _octant_index, OCTANT_LABELS
from weather_collector.processors.station_bias import HUMIDITY_DENYLIST
from weather_collector.utils import magnus_dew_point_f

ET = ZoneInfo("America/New_York")
OUT = Path(__file__).parent / "mesonet_validation.json"
MS_TO_MPH = 2.236936
KT_TO_MPH = 1.150779
MIN_OTHERS = 5
COVE_PROXY = "192019"   # Neptune Rd: 0.4 mi, waterfront, below the Cliffs on Joe's side (Joe 11-22)
COVE_MIN_PRIOR_DAYS = 3

# The rule, fixed in the plan doc (Step 1) before any score was computed. Units of the field.
RULE = {
    "t": {"loo_max": 1.18, "bias_max": 0.36, "bar": "served 2.36 F station-truth MAE; lead over weather.gov 0.36 F on URMA"},
    "h": {"loo_max": 3.0, "bias_max": 3.6, "bar": "served 6.01 % station-truth MAE; lead over raw NBM 3.6 % (no weather.gov h yet)"},
    "dp": {"loo_max": 0.81, "bias_max": 0.12, "bar": "served 1.63 F station-truth MAE; lead over weather.gov 0.12 F on URMA"},
}

DEFINITION = {
    "t": "station_temp: offset-corrected Tempest readings (offsets vs the other stations, day/night), MAD-trimmed distance-weighted mean per octant, mean of octants. No forecast.",
    "h": "station_humidity: same method on relative humidity (humidity offsets; broken-sensor denylist). No forecast.",
    "dp": "Magnus dew point of station_temp and station_humidity (as the pair log's observed_stations). No forecast.",
    "pr": "corrected_pressure_in: octant mean of offset-corrected station pressure. Falls back to WU / KBOS / MODEL pressure when no station reports (model fallback = contamination, flagged).",
    "ws": "wind_speed_stations: per-octant max, median across >= 3 octants, Tempest only. Weak: backyard anemometers read 0.2-0.4x open air.",
    "wg": "wind_gusts_stations: same as ws on gusts. Weak.",
    "rain": "hour_rain_in: Tempest hour totals (>= 3 stations), else the max instantaneous rate. No forecast.",
    "sr": "median of valid Tempest solar_radiation_wm2. No forecast.",
    "cc": "not measured by the stations: KBVY + KBOS METAR sky cover (mean). Page shows it labelled; truth stays URMA TCDC.",
    "vis_fog": "not measured by the stations: KBVY METAR.",
    "wd": "current.wind_direction: consensus across Tempest and other sources (verify whether the model is one of them before using it as truth).",
}


def _download():
    from google.cloud import storage
    import gzip
    d = tempfile.mkdtemp()
    for bl in storage.Client().bucket("myweather-data").list_blobs(prefix="station_readings/"):
        raw = bl.download_as_bytes()
        Path(d, bl.name.split("/")[-1]).write_bytes(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    return d


def _meta(d):
    meta = {}
    for f in sorted(Path(d).glob("*.json")):
        meta.update(json.load(open(f)).get("stations") or {})
    return meta


def per_station(t):
    """{field: {sid: offset-corrected value}} for fresh valid stations at one tick."""
    out = collections.defaultdict(dict)
    for sid, r in t["readings"].items():
        if not r.get("valid") or (r.get("age_min") or 0) >= 15:
            continue
        tv = r["t"] - (r.get("off_t") or 0.0) if r.get("t") is not None else None
        hv = (r["rh"] - (r.get("off_rh") or 0.0)
              if r.get("rh") is not None and sid not in HUMIDITY_DENYLIST else None)
        if tv is not None:
            out["t"][sid] = tv
        if hv is not None:
            out["h"][sid] = hv
        if tv is not None and hv is not None and 0 < hv <= 100:
            out["dp"][sid] = magnus_dew_point_f(tv, hv)
        if r.get("p_mb") is not None:
            out["pr"][sid] = r["p_mb"] / 33.8639 - (r.get("off_p") or 0.0)
        for k in ("ws", "wg"):
            if r.get(k) is not None:
                out[k][sid] = r[k]
        if r.get("sr") is not None:
            out["sr"][sid] = r["sr"]
        if r.get("pa1h") is not None:
            out["rain"][sid] = r["pa1h"]
    return out


def is_day(ts_utc):
    return 7 <= ts_utc.astimezone(ET).hour < 19


def wind_agg(vals, octs):
    """Per-octant max, median across >= 3 octants (wind_blend stations-only path)."""
    by = collections.defaultdict(list)
    for sid, v in vals.items():
        if octs.get(sid) is not None:
            by[octs[sid]].append(v)
    return st.median(max(v) for v in by.values()) if len(by) >= 3 else None


def mesonet_tick(t, ps, octs):
    l2 = t.get("l2") or {}
    v = {"t": l2.get("station_temp"), "h": l2.get("station_humidity")}
    if v["t"] is not None and v["h"] is not None:
        v["dp"] = magnus_dew_point_f(v["t"], v["h"])
    if l2.get("model_temp") is not None and l2.get("kalman_gain") is not None and l2.get("weighted_bias") is not None:
        v["t_corrected"] = l2["model_temp"] + l2["kalman_gain"] * l2["weighted_bias"]
    by = collections.defaultdict(list)
    for sid, p in ps["pr"].items():
        if octs.get(sid) is not None:
            by[octs[sid]].append(p)
    if by:
        v["pr"] = st.mean(st.mean(x) for x in by.values())
    v["ws"] = wind_agg(ps["ws"], octs)
    v["wg"] = wind_agg(ps["wg"], octs)
    return v


def urma(name, conv):
    out = {}
    for k, pts in (_cat(name) or {}).items():
        w = [(1.0 / max(p[2], 0.1) ** 2, conv(p[3])) for p in pts if p[3] is not None]
        if w:
            out[hour_epoch(k)] = sum(a * b for a, b in w) / sum(a for a, _ in w)
    return out


def rh_from(tf, dpf):
    tc, dc = (tf - 32) * 5 / 9, (dpf - 32) * 5 / 9
    return 100 * math.exp(17.625 * dc / (243.04 + dc)) / math.exp(17.625 * tc / (243.04 + tc))


def kbvy(d0, d1):
    """KBVY routine METARs from the IEM ASOS archive -> {hour epoch: {t, dp, h, pr, ws, wg}}."""
    url = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=BVY&data=tmpf&data=dwpf&data=relh"
           f"&data=sknt&data=gust&data=alti&year1={d0.year}&month1={d0.month}&day1={d0.day}"
           f"&year2={d1.year}&month2={d1.month}&day2={d1.day}&tz=Etc/UTC&format=onlycomma&latlon=no"
           "&missing=M&trace=T&direct=no&report_type=3")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    rows = urllib.request.urlopen(req, timeout=60).read().decode().splitlines()
    hdr, out = rows[0].split(","), {}
    for line in rows[1:]:
        r = dict(zip(hdr, line.split(",")))
        ep = datetime.strptime(r["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()
        h = snap(ep)
        if h is None:
            continue
        num = lambda k: None if r.get(k) in (None, "M", "") else float(r[k])  # noqa: E731
        v = {"t": num("tmpf"), "dp": num("dwpf"), "h": num("relh"), "pr": num("alti")}
        if num("sknt") is not None:
            v["ws"] = num("sknt") * KT_TO_MPH
        v["wg"] = num("gust") * KT_TO_MPH if num("gust") is not None else None
        out[h] = {k: x for k, x in v.items() if x is not None}
    return out


def cove_adjustment(mes_t, proxy):
    """1.7 shadow: Cove value = Mesonet + mean(proxy raw - Mesonet) by ET hour over PRIOR days only
    (walk-forward), scored against the proxy on each later day. Stations only, no forecast. The proxy
    is also one of the Mesonet's stations (offset-corrected), a small pull toward it."""
    by_day = collections.defaultdict(dict)
    for h, v in proxy.items():
        if h in mes_t:
            by_day[day_et(h)][h] = v - mes_t[h]
    days = sorted(by_day)
    plain, adj, nb = [], [], collections.defaultdict(lambda: [[], []])
    for i, D in enumerate(days):
        if i < COVE_MIN_PRIOR_DAYS:
            continue
        hist = collections.defaultdict(list)
        for d in days[:i]:
            for h, x in by_day[d].items():
                hist[datetime.fromtimestamp(h, ET).hour].append(x)
        for h, x in by_day[D].items():
            hr = datetime.fromtimestamp(h, ET).hour
            if not hist[hr]:
                continue
            a = st.mean(hist[hr])
            plain.append(-x)          # Mesonet - proxy
            adj.append(a - x)         # Mesonet + adj - proxy
            k = "night" if (hr >= 19 or hr < 7) else "midday" if 10 <= hr < 16 else "other"
            nb[k][0].append(-x); nb[k][1].append(a - x)
    table = collections.defaultdict(list)
    for d in days:
        for h, x in by_day[d].items():
            table[datetime.fromtimestamp(h, ET).hour].append(x)
    return {"proxy": COVE_PROXY, "scored_days": max(0, len(days) - COVE_MIN_PRIOR_DAYS),
            "mesonet_vs_proxy": _stats(plain), "mesonet_plus_adj_vs_proxy": _stats(adj),
            "by_period": {k: {"mesonet": _stats(v[0]), "adjusted": _stats(v[1])} for k, v in nb.items()},
            "adjustment_by_hour_et_all_days": {hr: round(st.mean(v), 2) for hr, v in sorted(table.items())}}


def day_et(h):
    return datetime.fromtimestamp(h, ET).strftime("%Y-%m-%d")


def _stats(errs):
    if not errs:
        return None
    return {"n": len(errs), "bias": round(st.mean(errs), 3), "mae": round(st.mean(abs(e) for e in errs), 3)}


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else _download()
    ticks = load(d)
    meta = _meta(d)
    octs = {sid: _octant_index(m.get("latitude"), m.get("longitude")) for sid, m in meta.items()}
    order = sorted(ticks)
    first, last = order[0][:10], order[-1][:10]

    loo = {f: collections.defaultdict(list) for f in ("t", "h", "dp", "pr", "ws", "wg", "sr")}
    loo_by_n = {f: collections.defaultdict(list) for f in ("t", "h", "dp")}
    hourly = collections.defaultdict(lambda: collections.defaultdict(list))
    rain_hours = collections.Counter()
    proxy_acc = collections.defaultdict(list)
    n_stations, n_octants = [], []
    for ts in order:
        t = ticks[ts]
        T = datetime.strptime(ts, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        ps = per_station(t)
        n_stations.append(len(ps["t"]))
        n_octants.append(len({octs.get(s) for s in ps["t"] if octs.get(s) is not None}))
        dn = "day" if is_day(T) else "night"
        for f, lst in loo.items():
            vals = ps[f]
            if f == "sr":
                vals = {k: v for k, v in vals.items() if v > 0} if is_day(T) else {}
            for j, vj in vals.items():
                others = [v for k, v in vals.items() if k != j]
                if len(others) < MIN_OTHERS:
                    continue
                e = vj - st.median(others)
                lst[dn].append(e)
                lst["oct:" + (OCTANT_LABELS[octs[j]] if octs.get(j) is not None else "?")].append(e)
                if f in loo_by_n:
                    loo_by_n[f][len(others)].append(e)
        if ps["rain"]:
            wet = sum(1 for v in ps["rain"].values() if v > 0)
            if wet:
                rain_hours[(ts[:13], wet, len(ps["rain"]))] += 1
        h = snap(T.timestamp())
        pr_ = t["readings"].get(COVE_PROXY) or {}
        if h is not None and pr_.get("valid") and pr_.get("t") is not None and (pr_.get("age_min") or 0) < 15:
            proxy_acc[h].append(pr_["t"])
        if h is not None:
            for f, v in mesonet_tick(t, ps, octs).items():
                if v is not None:
                    hourly[h][f].append(v)
    mes = {h: {f: st.mean(v) for f, v in fs.items()} for h, fs in hourly.items()}

    cove = cove_adjustment({h: v["t"] for h, v in mes.items() if "t" in v},
                           {h: st.mean(v) for h, v in proxy_acc.items()})

    ref_urma = {
        "t": urma("urma_truth_t.json", lambda k: (k - 273.15) * 9 / 5 + 32),
        "dp": urma("urma_truth_dpt.json", lambda k: (k - 273.15) * 9 / 5 + 32),
        "ws": urma("urma_truth_wind.json", lambda v: v * MS_TO_MPH),
        "wg": urma("urma_truth_gust.json", lambda v: v * MS_TO_MPH),
    }
    ref_urma["h"] = {h: rh_from(ref_urma["t"][h], ref_urma["dp"][h]) for h in ref_urma["t"] if h in ref_urma["dp"]}
    d0 = datetime.strptime(first, "%Y-%m-%d")
    try:
        ref_kbvy = kbvy(d0, datetime.strptime(last, "%Y-%m-%d") + timedelta(days=1))
    except Exception as e:  # noqa: BLE001
        print(f"KBVY fetch failed: {e}")
        ref_kbvy = {}

    cross = {}
    for f in ("t", "h", "dp", "pr", "ws", "wg", "t_corrected"):
        cf = "t" if f == "t_corrected" else f
        row = {}
        for name, ref in (("urma", ref_urma.get(cf) or {}), ("kbvy", {h: v[cf] for h, v in ref_kbvy.items() if cf in v})):
            errs, by_hr = [], collections.defaultdict(list)
            for h, v in mes.items():
                if f in v and h in ref:
                    e = v[f] - ref[h]
                    errs.append(e)
                    by_hr[datetime.fromtimestamp(h, ET).hour].append(e)
            s = _stats(errs)
            if s:
                s["bias_by_hour_et"] = {hr: round(st.mean(v), 2) for hr, v in sorted(by_hr.items())}
            row[name] = s
        cross[f] = row

    loo_out = {f: {k: _stats(v) for k, v in sorted(g.items())} for f, g in loo.items()}
    for f in loo_out:
        loo_out[f]["all"] = _stats([e for k, v in loo[f].items() if k in ("day", "night") for e in v])
    coverage = {}
    for f, g in loo_by_n.items():
        coverage[f] = {n: _stats(v) for n, v in sorted(g.items()) if len(v) >= 200}
    cov_threshold = None
    full = [s["mae"] for n, s in coverage["t"].items() if s and n >= 12]
    if full:
        base = st.median(full)
        jump = [n for n, s in sorted(coverage["t"].items()) if s and s["mae"] > 1.25 * base]
        cov_threshold = (max(jump) + 1) if jump else min(coverage["t"])

    verdict = {}
    for f, r in RULE.items():
        a = loo_out[f]["all"]["mae"] if loo_out[f]["all"] else None
        b = (cross[f]["urma"] or {}).get("bias")
        pa = a is not None and a <= r["loo_max"]
        pb = b is not None and abs(b) <= r["bias_max"]
        verdict[f] = {"loo_mae": a, "loo_max": r["loo_max"], "urma_bias": b, "bias_max": r["bias_max"],
                      "kbvy_bias": (cross[f]["kbvy"] or {}).get("bias"), "pass_A": pa, "pass_B": pb,
                      "qualifies": pa and pb, "bar": r["bar"]}

    wet = collections.Counter()
    for (hr, w, n), c in rain_hours.items():
        wet[hr] = max(wet[hr], w / n)
    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "window": f"{first} to {last}, autumn only (Tempest archive starts 11-08)",
        "n_ticks": len(order), "n_hours": len(mes),
        "definition": DEFINITION, "rule": RULE,
        "loo_held_out": loo_out, "coverage_loo_by_n_others": coverage,
        "low_coverage_threshold_stations": cov_threshold,
        "stations_per_tick": {"median": st.median(n_stations), "min": min(n_stations), "max": max(n_stations)},
        "octants_per_tick": {"median": st.median(n_octants), "min": min(n_octants), "max": max(n_octants)},
        "cross_check": cross,
        "gain_question": {"station_temp": cross["t"], "corrected_temp": cross["t_corrected"]},
        "rain": {"wet_hours": len(wet), "mean_fraction_of_stations_wet": round(st.mean(wet.values()), 2) if wet else None},
        "verdict": verdict,
        "cove_adjustment_shadow": cove,
    }
    OUT.write_text(json.dumps(out, indent=1, default=str))

    print(f"Mesonet validation, {out['window']}; {len(order)} ticks, {len(mes)} hours")
    print("field  held-out MAE (day/night)   vs URMA bias/MAE     vs KBVY bias/MAE")
    for f in ("t", "h", "dp", "pr", "ws", "wg"):
        lo = loo_out[f]
        u, k = cross[f]["urma"], cross[f]["kbvy"]
        fmt = lambda s: f"{s['bias']:+.2f}/{s['mae']:.2f} n={s['n']}" if s else "n/a"  # noqa: E731
        print(f"{f:5} {fmt(lo['all']):18} ({lo['day']['mae'] if lo.get('day') else '-'}/{lo['night']['mae'] if lo.get('night') else '-'})"
              f"  {fmt(u):20} {fmt(k)}")
    print(f"sr held-out (daytime) {loo_out['sr']['all']}")
    print(f"gain question vs URMA: station_temp {cross['t']['urma']['mae'] if cross['t']['urma'] else '-'} "
          f"corrected_temp {cross['t_corrected']['urma']['mae'] if cross['t_corrected']['urma'] else '-'}")
    print(f"low coverage below {cov_threshold} stations; stations/tick {out['stations_per_tick']}")
    print(f"1.7 Cove adjustment (shadow, proxy Neptune Rd, walk-forward {cove['scored_days']} days): "
          f"Mesonet vs proxy {cove['mesonet_vs_proxy']} -> adjusted {cove['mesonet_plus_adj_vs_proxy']}")
    for k, v in cove["by_period"].items():
        print(f"   {k:6} Mesonet {v['mesonet']} -> adjusted {v['adjusted']}")
    for f, v in verdict.items():
        print(f"VERDICT {f}: {'QUALIFIES' if v['qualifies'] else 'DOES NOT QUALIFY'} "
              f"(A held-out {v['loo_mae']} <= {v['loo_max']}: {v['pass_A']}; B |URMA bias| {v['urma_bias']} <= {v['bias_max']}: {v['pass_B']})")


if __name__ == "__main__":
    main()
