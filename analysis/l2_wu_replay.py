#!/usr/bin/env python3
"""Does a better station network make the L2-style temperature correction a better FORECAST?

mesonet_vs_urma.py showed Tempest + the WU live set sits closer to URMA than Tempest alone. This asks
the question that matters: does it lower the forecast error at 1-6 h? Replays the saved raw HRRR
temperature forecasts (backtest_snapshots/, one tick per hour at :07 ET) with the L2 idea
  forecast_corrected(h) = model(h) + g_h * bias,   bias = network_estimate(now) - model(now),
scored against URMA at the valid hour (independent truth, NOT the stations).
g_h is the least-squares gain per lead fitted on the OTHER days (leave-one-day-out), separately for
each network, so no variant gets a tuned advantage and nothing is scored on days that set its gain.
Networks: none (raw model), Tempest, WU live set, Tempest + WU live.
This isolates the station network's value in L2; it is not the production stack (no L3/L4/NBM blend).
Snapshots keep 14 days; URMA store starts 11-10.

Usage: python3 analysis/l2_wu_replay.py [--from 2026-11-10 --to 2026-11-18]
"""
import argparse
import math
import statistics as st
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    from analysis import mesonet_vs_urma as M
except ImportError:  # run as a script
    import mesonet_vs_urma as M

ET = ZoneInfo("America/New_York")
LEADS = (1, 2, 3, 4, 5, 6)


def et_epoch(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(tzinfo=ET).astimezone(timezone.utc).timestamp()


def origins(days):
    """{origin_hour_epoch: [model t at lead 0..47]} from the :07 tick of each hour."""
    out = {}
    for d in days:
        for e in (M._cat(f"backtest_snapshots/{d}.json") or {}).get("entries", []):
            if not e["ts"][14:16] == "07":
                continue
            lt, t = e.get("lead_times") or [], (e.get("l1") or {}).get("t") or []
            if len(lt) < 12 or len(t) < 12:
                continue
            h0 = et_epoch(lt[0])
            if abs(et_epoch(e["ts"]) - h0 - 7 * 60) < 120:  # array starts at this tick's hour
                out[h0] = t
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2026-11-10")
    ap.add_argument("--to", dest="d1", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    a = ap.parse_args()
    d0 = datetime.strptime(a.d0, "%Y-%m-%d")
    days = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((datetime.strptime(a.d1, "%Y-%m-%d") - d0).days + 1)]
    urma = M.urma_series()
    series = {**M.tempest_series(days), **M.wu_series(days)}
    tem = [s for s in series if s.startswith("T:")]
    live = [s for s in M.LIVE if s in series]
    groups = {"Tempest": tem, "WU live set": live, "Tempest + WU live": tem + live}
    orig = origins(days)
    held = sorted({M.day_of(h) for h in orig})
    # est[group][origin hour] = network estimate (offset-corrected, leave-one-day-out)
    est = {g: {} for g in groups}
    for D in held:
        cor = M.corrected(series, urma, D)
        for h in (x for x in orig if M.day_of(x) == D):
            for g, ids in groups.items():
                vals = [cor[s][h] for s in ids if s in cor and h in cor[s]]
                if len(vals) >= max(3, len(ids) // 2):
                    est[g][h] = st.mean(vals)
    # rows: (origin, day, lead, residual r = URMA(valid) - model(h), bias per group)
    rows = []
    for h, t in orig.items():
        for L in LEADS:
            v = h + L * 3600
            if v in urma and L < len(t) and all(h in est[g] for g in groups):
                rows.append((h, M.day_of(h), L, urma[v] - t[L], {g: est[g][h] - t[0] for g in groups}))
    print(f"origins={len(orig)} usable rows={len(rows)} days={held}")
    res = {g: {L: [] for L in LEADS} for g in list(groups) + ["none (raw model)"]}
    for L in LEADS:
        for D in held:
            tr = [r for r in rows if r[2] == L and r[1] != D]
            te = [r for r in rows if r[2] == L and r[1] == D]
            for r in te:
                res["none (raw model)"][L].append(r[3])
            for g in groups:
                num = sum(r[4][g] * r[3] for r in tr)
                den = sum(r[4][g] ** 2 for r in tr)
                gain = num / den if den else 0.0
                for r in te:
                    res[g][L].append(r[3] - gain * r[4][g])
    mae = lambda xs: st.mean(abs(x) for x in xs)
    print(f"\nMAE vs URMA (F), held-out days, by lead hour")
    print(f"{'network':22} " + " ".join(f"{'+' + str(L) + 'h':>6}" for L in LEADS) + "    mean")
    for g in res:
        m = [mae(res[g][L]) for L in LEADS]
        print(f"{g:22} " + " ".join(f"{x:6.2f}" for x in m) + f"   {st.mean(m):5.2f}")
    base = st.mean(mae(res["none (raw model)"][L]) for L in LEADS)
    t_ = st.mean(mae(res["Tempest"][L]) for L in LEADS)
    w_ = st.mean(mae(res["Tempest + WU live"][L]) for L in LEADS)
    print(f"\nVERDICT l2_wu_replay: temperature MAE vs URMA, mean of +1..+6 h: raw model {base:.2f}F, "
          f"L2-style with Tempest {t_:.2f}F, with Tempest+WU live {w_:.2f}F "
          f"(WU effect {100 * (t_ - w_) / t_:+.1f}% on top of Tempest; {len(rows) // len(LEADS)} origins) "
          "-> flip WU into the live blend only if the WU effect is positive at +1..+3 h on a longer window")


if __name__ == "__main__":
    main()
