#!/usr/bin/env python3
"""L2 amplitude walk-forward (11-08 mesonet review).

Question: does L2 apply too little of the station bias? L2 adds
Δ = K * weighted_bias * decay(lead) to the raw HRRR (forecast_l2 - forecast_l1).
K (0.9/0.65/0.4) was tuned against the shrunk `observed`, which itself is
model + K * bias, so K could never be tested. On 11-02..11-08 station truth the
best-fit multiple of Δ was ~2.0-2.3x at 2-5h for t.

Candidate: forecast_l1 + α_b * Δ, α per lead band, fit walk-forward (prior
FIT_DAYS days, grid 0..3 step 0.1; truth = observed_stations where the row has it,
shrunk observed otherwise) and scored on the next day against observed_stations.

Two scores per field x band:
  component: candidate vs forecast_l2 (the HRRR-side layer itself)
  served:    served + w_hrrr(band) * (α - 1) * Δ vs served, with w_hrrr from the
             live field-blend table (t 0-5h is 1.0, so served == L2 there and the
             served score is exact; elsewhere it assumes today's weight held).
Leads 0-1 are reported but carry no verdict (truth and input are the same reading).
Verdicts go through analysis/ship_rule.py on holdout days and into the ledger.

    python3 -m analysis.l2_amplitude_wf [--no-record]
"""
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path
from analysis.ship_rule import day_block_gain, verdict, record

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ("t", "wg")
BANDS = ((0, 1), (2, 5), (6, 11))
FIT_DAYS = 14
GRID = [round(0.1 * i, 1) for i in range(31)]
# Live field-blend HRRR weight by band (runtime_tables/terminal_blend_field_curated.json,
# fit 11-08 04:30): t w3_by_band[*][0]; wg is 2-way w=0.2 on every band.
W_HRRR = {"t": {"0-1": 1.0, "2-5": 1.0, "6-11": 0.85}, "wg": {"0-1": 0.2, "2-5": 0.2, "6-11": 0.2}}


def _band(lead):
    for a, b in BANDS:
        if a <= lead <= b:
            return f"{a}-{b}"
    return None


def _served(r):
    a = r.get("applied_layer")
    return r.get(f"forecast_{a}") if a and r.get(f"forecast_{a}") is not None else r.get("forecast")


def load():
    rows = defaultdict(list)  # (field, band) -> [(day, l1, delta, served, obs_fit, obs_s)]
    with open(cached_path(PAIR_LOG_URL, max_age_hours=0.5)) as fin:
        for line in fin:
            if '"forecast_l2"' not in line:
                continue
            r = json.loads(line)
            f = r.get("field")
            if f not in FIELDS:
                continue
            l1, l2, lead, obs = r.get("forecast_l1"), r.get("forecast_l2"), r.get("lead_h"), r.get("observed")
            srv = _served(r)
            if None in (l1, l2, lead, obs, srv):
                continue
            b = _band(lead)
            if b is None:
                continue
            obs_s = r.get("observed_stations")
            rows[(f, b)].append((r["valid_time"][:10], l1, l2 - l1, srv,
                                 obs_s if obs_s is not None else obs, obs_s))
    return rows


def fit_alpha(train):
    best = None
    for a in GRID:
        s = sum(abs(l1 + a * d - o) for _, l1, d, _, o, _ in train)
        if best is None or s < best[1]:
            best = (a, s)
    return best[0] if best else 1.0


def run(do_record=True):
    data = load()
    out = {}
    for (f, b), rs in sorted(data.items()):
        days = sorted({r[0] for r in rs})
        by_day = defaultdict(list)
        for r in rs:
            by_day[r[0]].append(r)
        comp, serv, alphas = {}, {}, {}
        for d in days:
            d0 = (date.fromisoformat(d) - timedelta(days=FIT_DAYS)).isoformat()
            train = [r for r in rs if d0 <= r[0] < d]
            scored = [r for r in by_day[d] if r[5] is not None]
            if len({r[0] for r in train}) < FIT_DAYS // 2 or not scored:
                continue
            a = fit_alpha(train)
            alphas[d] = a
            w = W_HRRR[f][b]
            cb = cc = sb = sc = 0.0
            for _, l1, dl, srv, _, os_ in scored:
                cb += abs(l1 + dl - os_); cc += abs(l1 + a * dl - os_)
                sb += abs(srv - os_); sc += abs(srv + w * (a - 1) * dl - os_)
            comp[d] = (cb, cc, len(scored)); serv[d] = (sb, sc, len(scored))
        gc, gs = day_block_gain(comp), day_block_gain(serv)
        out[f"{f} {b}"] = {"alpha_by_day": alphas, "component": gc, "served": gs}
        tag = "(circular, no verdict)" if b == "0-1" else ""
        print(f"{f:2} {b:5} alphas {list(alphas.values())[-6:]}  component {gc['gain']and round(gc['gain'],1)}% "
              f"[{gc['lo'] and round(gc['lo'],1)}, {gc['hi'] and round(gc['hi'],1)}] {gc['days']}d | served "
              f"{gs['gain'] and round(gs['gain'],1)}% [{gs['lo'] and round(gs['lo'],1)}, {gs['hi'] and round(gs['hi'],1)}] "
              f"-> {verdict(gs) if b != '0-1' else tag}")
        live = any(r[2] for r in rs)  # L2 applies nothing in this band (e.g. wg 6-11): not a test
        if do_record and live and b != "0-1" and gs["days"]:
            record("l2_amplitude_wf", f"{f} {b} served (station truth)", gs,
                   note=f"alpha walk-forward {FIT_DAYS}d; w_hrrr={W_HRRR[f][b]}")
    return out


if __name__ == "__main__":
    run(do_record="--no-record" not in sys.argv)
