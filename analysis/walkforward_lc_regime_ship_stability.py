#!/usr/bin/env python3
"""Walk-forward Lc regime SHIP-set stability tracker.

Companion gate for `walkforward_lc_regime.py`. That tool re-fits regime-vs-pooled
Lc every day on a fresh train/test split and reports which (field, regime, bin)
cells beat pooled on the held-out window. But a single day's SHIP list is a
point read — before wiring Stage 3 we need to know whether the SHIP set is
time-stable.

Shape mirrors `h_lc_regime_stage1.py`'s gate:
  * 30d retention, 7d window
  * cache at `.cache_walkforward_lc_regime_ship_history.json`
  * per-day entry: {fitted_at, ship_count, ship_set: [[field, regime, bin], ...]}
  * verdict:
      BUILDING  — fewer than 7 distinct days
      UNSTABLE  — 7+ days but SHIP set changed vs prior entry in window
      READY     — 7+ days, no cell changes, ship_count > 0

Reads `analysis/output/walkforward_lc_regime.txt` (produced by
walkforward_lc_regime.py — must run first; alphabetical order in the digest
runner takes care of that).
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
WALKFORWARD_TXT = REPO / "analysis" / "output" / "walkforward_lc_regime.txt"
CACHE_PATH = REPO / ".cache_walkforward_lc_regime_ship_history.json"
OUT_TXT = REPO / "analysis" / "output" / "walkforward_lc_regime_ship_stability.txt"

RETENTION_DAYS = 30
WINDOW_DAYS = 7

_SHIP_HDR = "── SHIP cells (regime-conditional beats pooled on held-out)"
_ROW_RE = re.compile(r"^(cc|cl|cm|ch)\s+([a-z_]+)\s+([\d\-]+)\s+")


def parse_ship_set(text):
    lines = text.splitlines()
    ship = set()
    in_section = False
    for line in lines:
        if _SHIP_HDR in line:
            in_section = True
            continue
        if not in_section:
            continue
        stripped = line.strip()
        if not stripped:
            if ship:
                break
            continue
        if stripped.startswith("──") or stripped.startswith("="):
            break
        if stripped.startswith("field"):
            continue
        m = _ROW_RE.match(line)
        if m:
            ship.add((m.group(1), m.group(2), m.group(3)))
    return ship


def load_history():
    try:
        return json.loads(CACHE_PATH.read_text())
    except FileNotFoundError:
        return {"entries": []}
    except Exception as e:
        print(f"  ⚠ history load failed: {e} — starting fresh")
        return {"entries": []}


def save_history(history):
    CACHE_PATH.write_text(json.dumps(history, indent=2))


def main():
    if not WALKFORWARD_TXT.exists():
        print(f"  ⚠ walkforward output not found at {WALKFORWARD_TXT}; skipping")
        return 0

    text = WALKFORWARD_TXT.read_text()
    ship_set = parse_ship_set(text)

    now = datetime.now()
    entry = {
        "fitted_at": now.strftime("%Y-%m-%dT%H:%M"),
        "ship_count": len(ship_set),
        "ship_set": sorted([[f, r, b] for (f, r, b) in ship_set]),
    }

    history = load_history()
    entries = history.get("entries", [])
    entries.append(entry)

    cutoff_ret = (now - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M")
    entries = [e for e in entries if e.get("fitted_at", "") >= cutoff_ret]
    save_history({"entries": entries})

    cutoff_win = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M")
    window = [e for e in entries if e.get("fitted_at", "") >= cutoff_win]

    by_day = {}
    for e in window:
        day = e.get("fitted_at", "")[:10]
        if day:
            by_day.setdefault(day, []).append(e)

    n_days = len(by_day)

    current = {tuple(x) for x in entry["ship_set"]}
    prior_entries = [e for e in window if e is not entry]
    cells_changed = set()
    for e in prior_entries:
        prior = {tuple(x) for x in (e.get("ship_set") or [])}
        cells_changed |= (current ^ prior)

    stable = len(cells_changed) == 0

    if n_days < WINDOW_DAYS:
        verdict = f"BUILDING — {n_days}/{WINDOW_DAYS} days"
    elif not current:
        verdict = "HOLD — 0 SHIP cells today"
    elif not stable:
        verdict = f"UNSTABLE — {len(cells_changed)} cell(s) flipped in/out over window"
    else:
        verdict = f"READY — {n_days} days stable, {len(current)} SHIP cells"

    out = []
    p = out.append
    p("=" * 80)
    p("walkforward_lc_regime_ship_stability — day-over-day SHIP-set stability")
    p("=" * 80)
    p(f"today: {entry['fitted_at']}  ship_count={len(current)}")
    p(f"window: last {WINDOW_DAYS}d  entries={len(window)}  distinct_days={n_days}")
    p(f"retention: {RETENTION_DAYS}d  total_entries_kept={len(entries)}")
    p("")

    ship_counts = [(e.get("fitted_at", "")[:10], e.get("ship_count", 0)) for e in window]
    p("ship_count by day-in-window:")
    for d, c in ship_counts:
        p(f"  {d}  n={c}")
    p("")

    if cells_changed:
        p(f"cells that flipped in/out vs any prior window entry ({len(cells_changed)} total):")
        for (f, r, b) in sorted(cells_changed)[:30]:
            in_today = (f, r, b) in current
            p(f"  {f:<4} {r:<12} {b:<8}  {'now-SHIP' if in_today else 'was-SHIP'}")
        if len(cells_changed) > 30:
            p(f"  ...+{len(cells_changed) - 30} more")
        p("")

    p("=" * 80)
    p(f"VERDICT: {verdict}")
    p("=" * 80)

    text_out = "\n".join(out) + "\n"
    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text(text_out)
    print(text_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
