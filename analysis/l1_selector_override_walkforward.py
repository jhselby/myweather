#!/usr/bin/env python3
"""L1 selector recency-override walk-forward (2026-10-07).

Question: does the selector's 7-day recency override (v0.6.546) earn its
keep, and does it matter that production only gets a fresh selector table
when the collector is deployed?

The runtime selector (`weather_collector/processors/l1_selector.py`) reads
only the `l1_selector_table_curated.json` bundled into the deploy. The
table is refit by `analysis/l1_selector_fit.py`, which runs in the daily
digest on the Mac — so production's picks are whatever that morning's fit
said on the last deploy day, frozen until the next deploy.

This script replays the fitter's decision rule each morning D (fit on rows
observed before D) and scores the picks on rows issued on D (run_time
date), for several policies:

  actual          — what production served (selector_source per row)
  always_hrrr / always_nbm — references
  daily_30d       — 30d base rule only, refit every morning
  daily_30d+7d5   — current rule (30d base + 7d override at ≥5%), refit daily
  daily_30d+14d5  — 14d override window
  daily_30d+7d10  — 7d override, 10% bar
  daily_14d       — 14d base rule only
  frozen7_30d+7d5 / frozen14_30d+7d5 — current rule, but the table is the one
                    fit 7 / 14 days earlier (what happens if the digest + deploy
                    stop: the bundled table ages in place)

Errors are the fitter's own: `_hrrr_prod_error` / `_nbm_prod_error`
(deepest stamped layer per side), so every policy is scored on the same
paired rows. Pooled-n per cell, fields compared as % vs `actual`, overall
= mean of per-field %.

Read-only. Auto-discovered by `analysis/runlog/run_digest.sh`.

Run:  python3 -m analysis.l1_selector_override_walkforward
"""
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analysis._cache import pair_log_paths
from analysis.l1_selector_fit import (
    FIELDS, MIN_N, MIN_LIFT_PCT, MIN_N_RECENT, MIN_LIFT_RECENT_PCT,
    _band_for, _hrrr_prod_error, _nbm_prod_error,
)

OUT_TXT = Path(__file__).resolve().parent / "output" / "l1_selector_override_walkforward.txt"
OUT_JSON = Path(__file__).resolve().parent / "output" / "l1_selector_override_walkforward.json"

# (name, base_window_days, override_window_days or None, override_bar_pct, freeze_days)
POLICIES = [
    ("daily_30d",         30, None, None,                0),
    ("daily_30d+7d5",     30, 7,    MIN_LIFT_RECENT_PCT, 0),
    ("daily_30d+14d5",    30, 14,   MIN_LIFT_RECENT_PCT, 0),
    ("daily_30d+7d10",    30, 7,    10.0,                0),
    ("daily_14d",         14, None, None,                0),
    ("frozen7_30d+7d5",   30, 7,    MIN_LIFT_RECENT_PCT, 7),
    ("frozen14_30d+7d5",  30, 7,    MIN_LIFT_RECENT_PCT, 14),
]
VERDICT_MIN_PCT = 1.0   # policy must beat its comparison by ≥1% mean AND in both halves


def _d(s):
    return date.fromisoformat(s[:10])


def load():
    fit = defaultdict(lambda: [0.0, 0.0, 0])        # (field, band, obs_date) → [Σh, Σn, n]
    score = defaultdict(lambda: [0.0, 0.0, 0.0, 0])  # (field, band, run_date) → [Σh, Σn, Σactual, n]
    seen = set()
    n_dup = 0
    for path in pair_log_paths():
        with open(path) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                f = r.get("field")
                if f not in FIELDS:
                    continue
                band = _band_for(r.get("lead_h"))
                if band is None or not r.get("obs_time") or not r.get("run_time"):
                    continue
                key = (f, r["run_time"], r["lead_h"])
                if key in seen:
                    n_dup += 1
                    continue
                seen.add(key)
                h = _hrrr_prod_error(r, f)
                n = _nbm_prod_error(r)
                if h is None or n is None:
                    continue
                a = fit[(f, band, _d(r["obs_time"]))]
                a[0] += h; a[1] += n; a[2] += 1
                src = r.get("selector_source")
                if src not in ("hrrr", "nbm"):
                    continue
                s = score[(f, band, _d(r["run_time"]))]
                s[0] += h; s[1] += n; s[2] += (h if src == "hrrr" else n); s[3] += 1
    return fit, score, n_dup


def _window(fit, f, band, day, days):
    sh = sn = cnt = 0
    for k in range(1, days + 1):
        a = fit.get((f, band, day - timedelta(days=k)))
        if a:
            sh += a[0]; sn += a[1]; cnt += a[2]
    if not cnt or not sh:
        return None, cnt
    return 100.0 * (sh - sn) / sh, cnt


def pick(fit, f, band, day, base_days, ovr_days, ovr_bar):
    lift, n = _window(fit, f, band, day, base_days)
    src = "nbm" if (lift is not None and n >= MIN_N and lift >= MIN_LIFT_PCT) else "hrrr"
    if ovr_days:
        rl, rn = _window(fit, f, band, day, ovr_days)
        if rl is not None and rn >= MIN_N_RECENT:
            if src == "hrrr" and rl >= ovr_bar:
                src = "nbm"
            elif src == "nbm" and rl <= -ovr_bar:
                src = "hrrr"
    return src


def main():
    fit, score, n_dup = load()
    obs_days = sorted({k[2] for k in fit})
    run_days = sorted({k[2] for k in score})
    if not obs_days or not run_days:
        print("VERDICT: NO DATA — pair log empty or unreadable.")
        return
    # Daily policies need a full 30d history. Frozen policies fit as of D-7/D-14,
    # so early in the log their 30d base window is partial (same n gates apply).
    first = obs_days[0] + timedelta(days=30)
    days = [d for d in run_days if d >= first]
    if len(days) < 4:
        print(f"VERDICT: THIN — only {len(days)} scoreable run day(s) with a full 30d history.")
        return

    names = ["actual", "always_hrrr", "always_nbm"] + [p[0] for p in POLICIES]
    # (policy, field, half) → [Σerr, n]
    acc = defaultdict(lambda: [0.0, 0])
    flips = defaultdict(int)
    prev = {}
    mid = days[len(days) // 2]
    for d in days:
        half = "A" if d < mid else "B"
        for (f, band, rd), (sh, sn, sa, n) in score.items():
            if rd != d:
                continue
            vals = {"actual": sa, "always_hrrr": sh, "always_nbm": sn}
            for name, bd, od, ob, fz in POLICIES:
                src = pick(fit, f, band, d - timedelta(days=fz), bd, od, ob)
                vals[name] = sh if src == "hrrr" else sn
                if prev.get((name, f, band)) not in (None, src):
                    flips[name] += 1
                prev[(name, f, band)] = src
            for name, v in vals.items():
                for h in (half, "ALL"):
                    acc[(name, f, h)][0] += v
                    acc[(name, f, h)][1] += n

    fields = sorted({k[1] for k in acc})

    def mae(name, f, h):
        s, n = acc.get((name, f, h), (0.0, 0))
        return s / n if n else None

    def pct(name, f, h, ref="actual"):
        a, b = mae(ref, f, h), mae(name, f, h)
        return 100.0 * (a - b) / a if a and b is not None else None

    def mean_pct(name, h, ref="actual"):
        xs = [pct(name, f, h, ref) for f in fields]
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    lines = []
    lines.append(f"L1 selector recency-override walk-forward — scored run days {days[0]} → {days[-1]} "
                 f"({len(days)} days; halves split at {mid})")
    lines.append(f"Frozen policies fit as of D-7 / D-14; before {obs_days[0] + timedelta(days=44)} their 30d base window is partial.")
    lines.append(f"Pair-log duplicate rows skipped (same field/run_time/lead in both logs): {n_dup:,}")
    lines.append("Lift % = improvement vs what production actually served (positive = better). "
                 "Errors = fitter's prod-error per side.")
    lines.append("")
    hdr = f"{'policy':16} {'flips':>5}  {'mean%':>7} {'A%':>7} {'B%':>7}  " + " ".join(f"{f:>6}" for f in fields)
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for name in names:
        row = f"{name:16} {flips.get(name, 0):5d}  "
        for h in ("ALL", "A", "B"):
            m = mean_pct(name, h)
            row += f"{m:+7.1f} " if m is not None else f"{'—':>7} "
        row += " " + " ".join((f"{pct(name, f, 'ALL'):+6.1f}" if pct(name, f, "ALL") is not None else f"{'—':>6}")
                              for f in fields)
        lines.append(row)
    lines.append("")
    lines.append("Override value (current rule vs 30d-only, both refit daily):")
    ov = {h: mean_pct("daily_30d+7d5", h, ref="daily_30d") for h in ("ALL", "A", "B")}
    lines.append(f"  mean {ov['ALL']:+.1f}%  halves {ov['A']:+.1f}% / {ov['B']:+.1f}%")
    dr = {h: mean_pct("daily_30d+7d5", h) for h in ("ALL", "A", "B")}
    lines.append("Daily refresh value (current rule refit daily vs actual deploy-frozen picks):")
    lines.append(f"  mean {dr['ALL']:+.1f}%  halves {dr['A']:+.1f}% / {dr['B']:+.1f}%")
    fz = {h: mean_pct("frozen14_30d+7d5", h, ref="daily_30d+7d5") for h in ("ALL", "A", "B")}
    lines.append("Staleness cost (table frozen 14 days vs refit daily, current rule):")
    lines.append(f"  mean {fz['ALL']:+.1f}%  halves {fz['A']:+.1f}% / {fz['B']:+.1f}%")

    def verdict_word(v):
        if all(x is not None and x >= VERDICT_MIN_PCT for x in v.values()):
            return "EARNS"
        if all(x is not None and x <= -VERDICT_MIN_PCT for x in v.values()):
            return "HURTS"
        return "FLAT"

    best = max((p[0] for p in POLICIES), key=lambda n: mean_pct(n, "ALL") or -1e9)
    verdict = (f"VERDICT: override {verdict_word(ov)} ({ov['ALL']:+.1f}% vs 30d-only); "
               f"daily refresh {verdict_word(dr)} ({dr['ALL']:+.1f}% vs deploy-frozen); "
               f"14d-stale table {verdict_word(fz)} ({fz['ALL']:+.1f}% vs daily); "
               f"best policy {best} ({mean_pct(best, 'ALL'):+.1f}% vs actual) over {len(days)} days.")
    lines.append("")
    lines.append(verdict)
    text = "\n".join(lines)
    print(text)
    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text(text + "\n")
    OUT_JSON.write_text(json.dumps({
        "days": [str(d) for d in days],
        "flips": dict(flips),
        "mean_pct_vs_actual": {n: {h: mean_pct(n, h) for h in ("ALL", "A", "B")} for n in names},
        "per_field_pct_vs_actual": {n: {f: pct(n, f, "ALL") for f in fields} for n in names},
        "override_vs_30d": ov,
        "daily_vs_actual": dr,
        "frozen14_vs_daily": fz,
        "verdict": verdict,
    }, indent=2))


if __name__ == "__main__":
    main()
