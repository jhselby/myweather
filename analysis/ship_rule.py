"""Pre-registered ship rule: day-block bootstrap + frozen holdout + test ledger.

Why (network-dev second opinion, 11-02): the pair log holds ~30 independent days. Rows
within a day and across leads are strongly dependent, so a row-level MAE gain or a
"9/17 days" win count can come from noise. Hundreds of analysis scripts each with their
own bar is a forking-paths setting. This module fixes the bar once.

The rule
--------
1. Unit of resampling = the valid day. Candidate and baseline are scored on IDENTICAL rows.
2. Gain = 1 - sum|cand error| / sum|base error|, pooled over the resampled days.
3. SHIP only if the lower end of the 95% day-block bootstrap interval (2000 draws) is > 0
   on the HOLDOUT days, with halves of the holdout both positive once >= 8 holdout days.
4. HOLDOUT = valid days >= HOLDOUT_START (frozen 2026-11-03). Nobody tunes on holdout days:
   weights, tables and thresholds are fit on days < the scored day (walk-forward) and the
   headline number is the score on holdout days only. Days before HOLDOUT_START are for
   exploration and carry no ship weight. Moving HOLDOUT_START forward is allowed (more
   days become exploration); moving it back is not.
5. Every test goes in the ledger (`record`) whether it ships or not, so the number of
   looks is visible next to the number of ships.

Use:
    from analysis.ship_rule import day_block_gain, verdict, record
    g = day_block_gain(per_day)      # per_day: {day: (sum_abs_base, sum_abs_cand, n)}
    print(verdict(g))
    record("name", "t 12-23h", g)
"""
import json
import random
from datetime import datetime, timezone
from pathlib import Path

HOLDOUT_START = "2026-11-03"
DRAWS = 2000
LEDGER = Path(__file__).resolve().parent / "runlog" / "ship_tests.jsonl"


def is_holdout(day):
    return day >= HOLDOUT_START


def day_block_gain(per_day, holdout_only=True, draws=DRAWS, seed=11):
    """per_day: {day: (sum_abs_base, sum_abs_cand, n_rows)}. Returns dict with the pooled
    gain, the 95% day-block interval, days, wins and the two halves."""
    days = sorted(d for d in per_day if (is_holdout(d) or not holdout_only))
    if not days:
        return {"days": 0, "gain": None, "lo": None, "hi": None, "wins": 0,
                "halves": (None, None), "n": 0, "holdout_only": holdout_only}

    def gain(ds):
        b = sum(per_day[d][0] for d in ds)
        c = sum(per_day[d][1] for d in ds)
        return 100.0 * (1.0 - c / b) if b else 0.0

    rng = random.Random(seed)
    gs = sorted(gain([rng.choice(days) for _ in days]) for _ in range(draws))
    h = len(days) // 2
    return {
        "days": len(days),
        "n": sum(per_day[d][2] for d in days),
        "gain": round(gain(days), 2),
        "lo": round(gs[int(0.025 * draws)], 2),
        "hi": round(gs[int(0.975 * draws) - 1], 2),
        "wins": sum(1 for d in days if per_day[d][1] < per_day[d][0]),
        "halves": (round(gain(days[:h]), 2), round(gain(days[h:]), 2)) if h else (None, None),
        "holdout_only": holdout_only,
    }


def verdict(g):
    if g["days"] == 0:
        return "NO HOLDOUT DAYS YET"
    ok = g["lo"] is not None and g["lo"] > 0
    if g["days"] >= 8:
        ok = ok and all(x is not None and x > 0 for x in g["halves"])
    scope = "holdout" if g["holdout_only"] else "ALL DAYS (exploratory, not a ship test)"
    flag = "PASS" if (ok and g["holdout_only"]) else ("lo>0 (exploratory)" if ok else "FAIL")
    return (f"{flag}: gain {g['gain']:+.1f}% [{g['lo']:+.1f}, {g['hi']:+.1f}] "
            f"{g['wins']}/{g['days']} days, halves {g['halves']}, n={g['n']:,} ({scope})")


def record(name, cell, g, shipped=False, note=""):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "test": name,
           "cell": cell, "gain": g.get("gain"), "lo": g.get("lo"), "hi": g.get("hi"),
           "days": g.get("days"), "holdout_only": g.get("holdout_only"),
           "shipped": shipped, "note": note}
    with open(LEDGER, "a") as f:
        f.write(json.dumps(row) + "\n")
