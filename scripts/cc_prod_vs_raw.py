"""Why is cc production worse than raw at 0-5h / 6-11h?

Joins the cc, cl, cm, ch pair-log rows of each (run_time, lead_h) and compares, per row:
  raw     = |forecast_l1 - observed|                       raw HRRR/Pirate cc
  live    = |error_{applied_layer}| via analysis/_prod.py  what users saw
  dmax    = |max(cl, cm, ch) - observed|                   offline derived-max from each component's
                                                           deepest layer (l6 -> l4 -> ... as h_cc_derivation)
  dmax_p  = same but ch taken from forecast_chp            (tests: does cc lose ch's persistence gain
                                                           because Ccd runs BEFORE chp/clp in collector.py?)
It then splits the live-vs-raw gap by whether Ccd actually changed the value (live forecast != raw
forecast), whether raw was saturated (>= 90, where Ccd keeps raw), and by regime.

Reads the live pair log (post-v0.6.390, Ccd ENABLED). Run from the repo root:
  python3 scripts/cc_prod_vs_raw.py [--days 14] [--bands 0-5,6-11]
Set MYWEATHER_REFRESH=1 to force a fresh pair-log download.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from analysis._cache import cached_path, PAIR_LOG_URL
from analysis._prod import prod_error

CLOUD = ("cc", "cl", "cm", "ch")
BANDS = {"0-5": (0, 6), "6-11": (6, 12), "12-23": (12, 24), "24-47": (24, 48)}
SAT = 90.0
LAYERS = ("forecast_l6", "forecast_l4", "forecast_l3", "forecast_l2", "forecast_l1")


def deepest(r, extra=None):
    for k in ((extra,) if extra else ()) + LAYERS:
        v = r.get(k)
        if v is not None:
            return float(v)
    return None


def band_of(lead):
    for name, (lo, hi) in BANDS.items():
        if lo <= lead < hi:
            return name
    return None


def load(days):
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
    groups = defaultdict(dict)
    with open(cached_path(PAIR_LOG_URL)) as fh:
        for line in fh:
            if '"field": "c' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            f = r.get("field")
            if f not in CLOUD or (r.get("obs_time") or "") < cutoff:
                continue
            rt, lead = r.get("run_time"), r.get("lead_h")
            if rt is None or lead is None:
                continue
            groups[(rt, int(lead))][f] = r
    return groups


class Agg:
    def __init__(self):
        self.n = 0
        self.s = defaultdict(float)

    def add(self, **kw):
        self.n += 1
        for k, v in kw.items():
            self.s[k] += v

    def m(self, k):
        return self.s[k] / self.n if self.n else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--bands", default="0-5,6-11")
    a = ap.parse_args()
    bands = a.bands.split(",")

    groups = load(a.days)
    rows = []
    for (rt, lead), fs in groups.items():
        if not set(CLOUD) <= set(fs):
            continue
        b = band_of(lead)
        if b not in bands:
            continue
        cc = fs["cc"]
        obs = cc.get("observed")
        l1 = cc.get("forecast_l1")
        ep = prod_error(cc)
        cl, cm, ch = deepest(fs["cl"]), deepest(fs["cm"]), deepest(fs["ch"])
        chp = deepest(fs["ch"], extra="forecast_chp")
        if None in (obs, l1, ep, cl, cm, ch, chp):
            continue
        applied = cc.get("applied_layer") or "?"
        live_fc = cc.get("forecast_" + applied)
        if live_fc is None:
            live_fc = obs + ep
        rows.append({
            "b": b, "t": (cc.get("obs_time") or "")[:10],
            "reg": (cc.get("state_fc") or {}).get("regime_synoptic") or "unknown",
            "raw": abs(float(l1) - obs), "live": abs(ep),
            "dmax": abs(max(cl, cm, ch) - obs), "dmax_p": abs(max(cl, cm, chp) - obs),
            "changed": abs(float(live_fc) - float(l1)) > 0.5,
            "sat": float(l1) >= SAT,
            "live_is_dmax": abs(float(live_fc) - min(100.0, max(cl, cm, ch))) <= 1.0,
            "applied": applied,
            "live_bias": float(live_fc) - obs, "raw_bias": float(l1) - obs,
        })
    print(f"quads used: {len(rows):,}  (last {a.days}d, bands {','.join(bands)})\n")

    def table(title, keyf):
        print(title)
        print(f"  {'slice':<24}{'n':>6}{'raw':>8}{'live':>8}{'dmax':>8}{'dmax_p':>8}{'live-raw':>9}{'live==dmax':>11}")
        buckets = defaultdict(Agg)
        for r in rows:
            buckets[keyf(r)].add(raw=r["raw"], live=r["live"], dmax=r["dmax"], dmax_p=r["dmax_p"],
                                 ldm=1.0 if r["live_is_dmax"] else 0.0)
        for k in sorted(buckets):
            g = buckets[k]
            d = 100 * (g.m("live") - g.m("raw")) / g.m("raw") if g.m("raw") else float("nan")
            print(f"  {str(k):<24}{g.n:>6}{g.m('raw'):>8.2f}{g.m('live'):>8.2f}{g.m('dmax'):>8.2f}"
                  f"{g.m('dmax_p'):>8.2f}{d:>+8.1f}%{100*g.m('ldm'):>10.0f}%")
        print()

    table("BY BAND", lambda r: r["b"])
    table("BY BAND x CCd CHANGED THE VALUE? (live fc differs from raw by > 0.5)",
          lambda r: (r["b"], "changed" if r["changed"] else "unchanged"))
    table("BY BAND x SATURATED RAW (>= 90)", lambda r: (r["b"], "sat" if r["sat"] else "not sat"))
    table("BY BAND x REGIME (state_fc, per-lead; the live gate uses the tick regime)",
          lambda r: (r["b"], r["reg"]))
    table("BY BAND x APPLIED LAYER", lambda r: (r["b"], r["applied"]))

    print("DAILY (0-5 band only): n, raw, live, live-raw")
    days = defaultdict(Agg)
    for r in rows:
        if r["b"] == "0-5":
            days[r["t"]].add(raw=r["raw"], live=r["live"])
    for d in sorted(days):
        g = days[d]
        print(f"  {d}  n={g.n:>4}  {g.m('raw'):6.2f}  {g.m('live'):6.2f}  {100*(g.m('live')-g.m('raw'))/g.m('raw'):+7.1f}%")

    print("\nSIGNED BIAS (forecast - obs), mean:")
    for b in bands:
        sub = [r for r in rows if r["b"] == b]
        if sub:
            print(f"  {b:<6} raw {sum(r['raw_bias'] for r in sub)/len(sub):+7.2f}   live {sum(r['live_bias'] for r in sub)/len(sub):+7.2f}")
    print("\nReading guide: dmax_p < dmax means cc would gain from deriving after chp. 'live==dmax' near 100% on "
          "'changed' rows means Ccd is working as designed; if live-raw > 0 there, the derived value itself is worse than raw.")


if __name__ == "__main__":
    main()
