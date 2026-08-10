"""clp whitelist streak — archives daily cl_persistence_gate cell set and
reports 7-day Jaccard stability for the flip-gate decision.

Reads: weather_collector/data/cl_persistence_gate_curated.json (overwritten
daily by h_cl_persistence_blend_stage2.py).
Writes/appends: analysis/output/clp_whitelist_streak.json — list of
per-day snapshots, idempotent by UTC date.

Effective fire set = SHIP + MARGIN-excluding-frontal (matches the runtime
gate contract in weather_collector/processors/cl_persistence_gate.py:
frontal cells never fire regardless of verdict).

Flip gate (per feedback_whitelist_promotion_gate + feedback_streak_walker_robustness):
7 consecutive daily reads with pairwise Jaccard >= 0.8 vs the latest day.
"""
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CURATED = os.path.join(HERE, "..", "weather_collector", "data",
                       "cl_persistence_gate_curated.json")
ARCHIVE = os.path.join(HERE, "output", "clp_whitelist_streak.json")

JACCARD_FLOOR = 0.80
STREAK_REQUIRED = 7


def effective_fire_set(cells):
    fire = set()
    for regime, bandmap in cells.items():
        if regime == "frontal":
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


def load_archive():
    if not os.path.exists(ARCHIVE):
        return []
    with open(ARCHIVE) as fh:
        return json.load(fh)


def save_archive(entries):
    os.makedirs(os.path.dirname(ARCHIVE), exist_ok=True)
    with open(ARCHIVE, "w") as fh:
        json.dump(entries, fh, indent=2)


def main():
    if not os.path.exists(CURATED):
        print(f"clp_whitelist_streak: curated JSON missing at {CURATED}")
        return 1

    with open(CURATED) as fh:
        curated = json.load(fh)

    cells = curated.get("cells", {})
    fire = sorted(effective_fire_set(cells))
    today = datetime.now(timezone.utc).date().isoformat()

    entry = {
        "date": today,
        "curated_generated_at": curated.get("generated_at"),
        "fire_set": fire,
        "n_fire": len(fire),
        "rollup": curated.get("rollup"),
    }

    entries = load_archive()
    if entries and entries[-1]["date"] == today:
        entries[-1] = entry
        action = "updated"
    else:
        entries.append(entry)
        action = "appended"
    save_archive(entries)

    tail = entries[-STREAK_REQUIRED:]
    latest_fire = set(tail[-1]["fire_set"])

    lines = []
    lines.append("clp whitelist streak walker")
    lines.append("=" * 60)
    lines.append(f"today ({today}): {action}. Fire set n={len(fire)}: {fire}")
    lines.append(f"archive length: {len(entries)} day(s)")
    lines.append("")
    lines.append(f"trailing {min(len(tail), STREAK_REQUIRED)}-day Jaccard vs today:")
    lines.append(f"  {'date':<12}{'n_fire':>7}  {'J vs today':>11}  {'delta cells':<30}")

    min_j = 1.0
    for e in tail:
        s = set(e["fire_set"])
        j = jaccard(s, latest_fire)
        min_j = min(min_j, j)
        diff = latest_fire.symmetric_difference(s)
        diff_s = ", ".join(sorted(diff)) if diff else "-"
        lines.append(f"  {e['date']:<12}{e['n_fire']:>7}  {j:>11.3f}  {diff_s}")

    lines.append("")
    if len(entries) < STREAK_REQUIRED:
        need = STREAK_REQUIRED - len(entries)
        lines.append(f"STATUS: BUILDING — need {need} more daily read(s) before flip decision.")
    elif min_j >= JACCARD_FLOOR:
        lines.append(f"STATUS: PASS — {STREAK_REQUIRED}-day min Jaccard {min_j:.3f} >= {JACCARD_FLOOR}. "
                     "Whitelist stable; flip gate cleared.")
    else:
        lines.append(f"STATUS: FAIL — {STREAK_REQUIRED}-day min Jaccard {min_j:.3f} < {JACCARD_FLOOR}. "
                     "Whitelist churn; do not flip.")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
