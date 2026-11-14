#!/usr/bin/env python3
"""Dual-truth scoring (v0.7.91): the same served forecast graded on both truths.

Why: the scored `observed` for t/h/dp/ws/wg is the station reading shrunk toward
the model (model_t + K * weighted bias), so it flatters layers that stay close to
the model, and L2 is graded on the stations that feed it (at lead 0-1h the
correction and the truth are the same reading). `observed_stations` (K=1, stations
only, logged since 2026-11-02 18:07) is the model-free column. This script scores
the SAME rows on both and shows the gap, per field, so the contamination is
visible every day instead of guessed at.

For a pair row, error = forecast - observed, so a layer residual re-expressed on
the station truth is:   e_stations = e + (observed - observed_stations).

Per field (t, h, dp, ws, wg; all NBM-scope, so the public baseline is raw NBM):
  - Total Lift on each truth = (public_MAE - served_MAE) / public_MAE * 100
    served = error_{applied_layer} (what the collector actually shipped),
    public = error_raw_nbm. Rows with both residuals present only.
  - split by lead: 0-1h (nowcast: station-truth overlaps L2's own input) vs 2h+.
  - L2 gain on each truth = (MAE_l1 - MAE_l2) / MAE_l1 * 100, same lead split.
    L2 is graded at 2-5h (`lead_2_5h`, v0.7.94): it decays to ~0 by 6-8h, so the
    2-47h pool hides it (t 0.8% pooled vs ~15% at 2-3h on 11-02..11-08).
  - per-day station-truth lift so a thin window is visible.
  - t only (v0.7.99): a third truth, URMA (NOAA's hourly analysis, independent of
    our stations and of L2), from the refitter's GCS store urma_truth_t.json (TMP
    only; h/dp need DPT in that store first). URMA publishes ~8h late, so the
    newest hours have no URMA row.

Runtime:
    python3 -m analysis.truth_compare
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path
from analysis._output import out as _out

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_JSON = _out("truth_compare.json")
FIELDS = ["t", "h", "dp", "ws", "wg"]
NOWCAST_MAX_LEAD = 1  # leads 0..1 overlap L2's own station input
L2_GRADE_MAX_LEAD = 5  # L2 is graded on leads 2..5


def _prod_error(row):
    applied = row.get("applied_layer")
    if applied:
        v = row.get(f"error_{applied}")
        if v is not None:
            return v
    return row.get("error")


def _new():
    return {"n": 0, "pub_o": 0.0, "pub_s": 0.0, "srv_o": 0.0, "srv_s": 0.0,
            "l1_o": 0.0, "l1_s": 0.0, "l2_o": 0.0, "l2_s": 0.0, "n_l2": 0,
            "n_u": 0, "pub_u": 0.0, "srv_u": 0.0}


def _urma_t():
    """{UTC 'YYYY-MM-DDTHH': URMA t (F)}: inverse-distance mean of the 4 cells around the Cove."""
    def idw(nb):
        w = [1 / max(x[2], 0.1) ** 2 for x in nb]
        return (sum(wi * x[3] for wi, x in zip(w, nb)) / sum(w) - 273.15) * 9 / 5 + 32
    try:
        if os.environ.get("MYWEATHER_CACHE_MODE") == "gcs":
            from weather_collector.gcs_io import load_json
            return {k: idw(nb) for k, nb in (load_json("urma_truth_t.json") or {}).items()}
        out = {}
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "urma_truth", "urma_cell.jsonl")
        if os.path.exists(local):
            for line in open(local):
                r = json.loads(line)
                if r.get("var") == "TMP":
                    out[r["valid"][:13]] = idw(r["nb"])
        return out
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ URMA truth unavailable ({type(e).__name__}: {e})")
        return {}


def _utc_hour(valid_time):
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    try:
        d = datetime.strptime(valid_time[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=ZoneInfo("America/New_York"))
    except ValueError:
        return None
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


def _lift(pub, srv):
    return None if not pub else round((pub - srv) / pub * 100, 2)


def _summ(b):
    n = b["n"]
    if not n:
        return None
    return {
        "n": n,
        "public_mae_shrunk": round(b["pub_o"] / n, 4), "public_mae_stations": round(b["pub_s"] / n, 4),
        "served_mae_shrunk": round(b["srv_o"] / n, 4), "served_mae_stations": round(b["srv_s"] / n, 4),
        "total_lift_shrunk_pct": _lift(b["pub_o"], b["srv_o"]),
        "total_lift_stations_pct": _lift(b["pub_s"], b["srv_s"]),
        "l2_gain_shrunk_pct": _lift(b["l1_o"], b["l2_o"]) if b["n_l2"] else None,
        "l2_gain_stations_pct": _lift(b["l1_s"], b["l2_s"]) if b["n_l2"] else None,
        "n_l2": b["n_l2"],
        "n_urma": b["n_u"],
        "public_mae_urma": round(b["pub_u"] / b["n_u"], 4) if b["n_u"] else None,
        "served_mae_urma": round(b["srv_u"] / b["n_u"], 4) if b["n_u"] else None,
        "total_lift_urma_pct": _lift(b["pub_u"], b["srv_u"]) if b["n_u"] else None,
    }


def build():
    path = cached_path(PAIR_LOG_URL, max_age_hours=0.5)
    split = {f: {"nowcast_0_1h": _new(), "lead_2h_plus": _new(), "lead_2_5h": _new()} for f in FIELDS}
    per_day = {f: defaultdict(_new) for f in FIELDS}
    first = last = None
    urma = _urma_t()
    with open(path) as fin:
        for line in fin:
            if '"observed_stations"' not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            f = r.get("field")
            if f not in FIELDS:
                continue
            obs, obs_s = r.get("observed"), r.get("observed_stations")
            if obs is None or obs_s is None:
                continue
            srv, pub = _prod_error(r), r.get("error_raw_nbm")
            if srv is None or pub is None:
                continue
            lead = r.get("lead_h")
            if lead is None:
                continue
            shift = obs - obs_s
            tu = urma.get(_utc_hour(r.get("valid_time") or "")) if f == "t" else None
            day = (r.get("valid_time") or "")[:10]
            first = day if first is None or day < first else first
            last = day if last is None or day > last else last
            for b in (split[f]["nowcast_0_1h" if lead <= NOWCAST_MAX_LEAD else "lead_2h_plus"],
                      per_day[f][day] if lead > NOWCAST_MAX_LEAD else None,
                      split[f]["lead_2_5h"] if NOWCAST_MAX_LEAD < lead <= L2_GRADE_MAX_LEAD else None):
                if b is None:
                    continue
                b["n"] += 1
                b["pub_o"] += abs(pub); b["pub_s"] += abs(pub + shift)
                b["srv_o"] += abs(srv); b["srv_s"] += abs(srv + shift)
                if tu is not None:   # error vs URMA = error + (observed - urma)
                    b["n_u"] += 1
                    b["pub_u"] += abs(pub + obs - tu); b["srv_u"] += abs(srv + obs - tu)
                e1, e2 = r.get("error_l1"), r.get("error_l2")
                if e1 is not None and e2 is not None:
                    b["n_l2"] += 1
                    b["l1_o"] += abs(e1); b["l1_s"] += abs(e1 + shift)
                    b["l2_o"] += abs(e2); b["l2_s"] += abs(e2 + shift)
    fields = {}
    for f in FIELDS:
        two = _summ(split[f]["lead_2h_plus"])
        fields[f] = {
            "nowcast_0_1h": _summ(split[f]["nowcast_0_1h"]),
            "lead_2h_plus": two,
            "lead_2_5h": _summ(split[f]["lead_2_5h"]),
            "gap_pts_2h_plus": (None if not two or two["total_lift_shrunk_pct"] is None
                                or two["total_lift_stations_pct"] is None
                                else round(two["total_lift_shrunk_pct"] - two["total_lift_stations_pct"], 2)),
            "per_day_2h_plus": {d: _summ(b) for d, b in sorted(per_day[f].items())},
        }
    return {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "first_day": first, "last_day": last,
        "definition": ("Total Lift = (public_MAE - served_MAE)/public_MAE; served = error_{applied_layer}, "
                       "public = error_raw_nbm; same rows on both truths; station truth = "
                       "observed_stations (model-free). gap = shrunk lift - station lift (the flattery). "
                       "t also on URMA (total_lift_urma_pct), independent of stations and L2."),
        "urma_hours": len(urma),
        "fields": fields,
    }


def main():
    payload = build()
    with open(OUT_JSON, "w") as fout:
        json.dump(payload, fout, indent=2)
    print(f"wrote {OUT_JSON} (days {payload['first_day']}..{payload['last_day']})")
    try:
        from weather_collector.gcs_io import upload_json
        upload_json(payload, "truth_compare.json", "truth_compare.json")
        print("  ✓ Published to gs://myweather-data/truth_compare.json")
    except Exception as e:
        print(f"  ⚠ GCS upload skipped ({type(e).__name__}: {e}) — local file still written")
    for f, v in payload["fields"].items():
        two, now, l2w = v["lead_2h_plus"], v["nowcast_0_1h"], v["lead_2_5h"]
        if not two:
            continue
        print(f"{f:2} 2h+  n={two['n']:5}  lift shrunk {two['total_lift_shrunk_pct']:>6}%  stations {two['total_lift_stations_pct']:>6}%  "
              f"gap {v['gap_pts_2h_plus']:>6} pts | L2 gain 2-5h shrunk {l2w['l2_gain_shrunk_pct'] if l2w else None}% stations {l2w['l2_gain_stations_pct'] if l2w else None}%"
              + (f" || 0-1h L2 gain shrunk {now['l2_gain_shrunk_pct']}% stations {now['l2_gain_stations_pct']}%" if now else ""))


if __name__ == "__main__":
    main()
