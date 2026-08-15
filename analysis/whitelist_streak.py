"""whitelist streak walker — archives daily cell-based curated fire sets
across all live + shadow-write gates and reports 7-day Jaccard stability
for each.

The curated JSONs are overwritten in place daily by their h_* stage2
scripts, so without an archive there is no history to Jaccard-check on
flip-day. This driver walks a registry, appends today's effective fire
set per gate to `analysis/output/{name}_streak.json` (idempotent by UTC
date), and prints a PASS/FAIL/BUILDING line per gate.

Fire-set contract per gate matches the runtime processor's `_cell_fires`:
verdict in {SHIP, MARGIN} minus any always-excluded regimes.

Flip gate (per feedback_whitelist_promotion_gate + feedback_streak_walker_robustness):
7 consecutive daily reads with pairwise Jaccard vs latest >= JACCARD_FLOOR.
"""
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CURATED_DIR = os.path.join(HERE, "..", "weather_collector", "data")
ARCHIVE_DIR = os.path.join(HERE, "output")

JACCARD_FLOOR = 0.80
STREAK_REQUIRED = 7

# Registry: gate_name → {curated: filename, excludes: {regimes always-baseline}}
# Only cell-based curated JSONs (verdict per regime × band). Bias-persistence
# curated JSONs (dp_bias, ws_bias) use a different shape (stage1_verdicts flat)
# and would need a second extractor.
REGISTRY = {
    "chp":         {"curated": "ch_persistence_gate_curated.json",     "excludes": {"frontal"}, "status": "LIVE"},
    "clp":         {"curated": "cl_persistence_gate_curated.json",     "excludes": {"frontal"}, "status": "SHADOW"},
    "wdp":         {"curated": "wd_persistence_gate_curated.json",     "excludes": {"frontal"}, "status": "LIVE"},
    "wg_residual": {"curated": "wg_residual_persistence_curated.json", "excludes": set(),       "status": "SHADOW"},
    "dp_residual": {"curated": "dp_residual_persistence_curated.json", "excludes": set(),       "status": "SHADOW"},
    # v0.6.418 (2026-08-15) — pr L2 whitelist joins the same 7-day stability
    # tracker. Curated JSON emitted by pr_l2_regime_lead_retro.py with fire
    # set = live SHIPPED_CELLS + today's BOTH-WIN candidates. Streak clears
    # → new candidates earn a spot in _PR_L2_FIRE_CELLS. Status "LIVE" —
    # the 2 shipped cells are firing, walker is tracking candidate churn.
    "pr_l2":       {"curated": "pr_l2_regime_curated.json",            "excludes": set(),       "status": "LIVE"},
}


def effective_fire_set(cells, excludes):
    fire = set()
    for regime, bandmap in cells.items():
        if regime in excludes:
            continue
        for band, cell in bandmap.items():
            if cell.get("verdict") in ("SHIP", "MARGIN"):
                fire.add(f"{regime}/{band}")
    return fire


def jaccard(a, b):
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def load_archive(path):
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return json.load(fh)


def save_archive(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(entries, fh, indent=2)


def walk_gate(name, cfg, today):
    curated_path = os.path.join(CURATED_DIR, cfg["curated"])
    archive_path = os.path.join(ARCHIVE_DIR, f"{name}_streak.json")

    if not os.path.exists(curated_path):
        return f"{name:<14} MISSING curated at {cfg['curated']}"

    with open(curated_path) as fh:
        curated = json.load(fh)
    cells = curated.get("cells", {})
    fire = sorted(effective_fire_set(cells, cfg["excludes"]))

    entry = {
        "date": today,
        "curated_generated_at": curated.get("generated_at"),
        "fire_set": fire,
        "n_fire": len(fire),
        "rollup": curated.get("rollup"),
    }
    entries = load_archive(archive_path)
    if entries and entries[-1]["date"] == today:
        entries[-1] = entry
    else:
        entries.append(entry)
    save_archive(archive_path, entries)

    tail = entries[-STREAK_REQUIRED:]
    latest = set(tail[-1]["fire_set"])
    min_j, worst_diff = 1.0, set()
    for e in tail:
        j = jaccard(set(e["fire_set"]), latest)
        if j < min_j:
            min_j = j
            worst_diff = latest.symmetric_difference(set(e["fire_set"]))

    days = len(entries)
    if days < STREAK_REQUIRED:
        need = STREAK_REQUIRED - days
        status = f"BUILDING day {days}/{STREAK_REQUIRED} (need {need} more)"
    elif min_j >= JACCARD_FLOOR:
        status = f"PASS  min-J {min_j:.3f} over {STREAK_REQUIRED}d"
    else:
        diff_s = ",".join(sorted(worst_diff)[:4]) or "-"
        status = f"FAIL  min-J {min_j:.3f} < {JACCARD_FLOOR} (worst diff: {diff_s})"

    return f"{name:<14} {cfg['status']:<7} n_fire={len(fire):>2}  {status}"


def main():
    today = datetime.now(timezone.utc).date().isoformat()
    lines = [f"whitelist streak walker — {today}", "=" * 72]
    for name, cfg in REGISTRY.items():
        lines.append(walk_gate(name, cfg, today))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
