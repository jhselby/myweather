#!/usr/bin/env python3
"""Applied-layer consistency checker.

Catches the class of mismatch that hid the ws L3 skip-table dormancy for
4 days after v0.6.279: correction-layer config declares that a field
gets a correction, but nothing in the pipeline actually writes the state
the correction reads from.

Two categories of check:

  A. Config coherence. Every field in L3_FIELDS / L4_FIELDS / SKIP_TABLE
     must resolve in TARGET_ARRAY and CAPS. Every SKIP_TABLE key's layer
     must be a real layer name.

  B. State read/writer coherence. A hand-curated table of derived-state
     paths the correction stack reads from — for each, grep the collector
     for a writer. No writer = FAIL. Ships with the 3 known regime reads
     (decay_apply, solar_correction, confidence_layer). Extend the table
     when a new correction layer starts reading a new derived path.

Static-only: reads Python source, no I/O, no runtime data. Runs in well
under a second. Exit 0 clean, exit 1 on any hard failure.

Usage:
  python3 analysis/applied_layer_audit.py

Non-goals:
  - Runtime dormancy (writer exists but never fires) — that's the queued
    gate-firing frequency table's job.
  - Corrections-file completeness — belongs in the Fitter's own preflight.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from weather_collector.processors.decay_apply import (
    L3_FIELDS, L4_FIELDS, SKIP_TABLE, TARGET_ARRAY, CAPS,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLECTOR_DIR = os.path.join(REPO, "weather_collector")

KNOWN_LAYERS = {"l3", "l4"}

# Category B: (reader_module_relpath, derived_path, writer_regex).
# Each entry declares that reader_module reads the given derived path,
# and the audit verifies a writer matching writer_regex exists SOMEWHERE
# under weather_collector/. The writer_regex is grep-style (Python re).
#
# When adding a new correction layer that reads a new derived path,
# add its entry here — the missing-writer check kicks in automatically.
STATE_READ_TABLE = [
    (
        "weather_collector/processors/decay_apply.py",
        "derived.state.regime_synoptic",
        r'derived\[["\']state["\']\]\s*=',
    ),
    (
        "weather_collector/processors/solar_correction.py",
        "derived.state.regime_synoptic",
        r'derived\[["\']state["\']\]\s*=',
    ),
    (
        "weather_collector/processors/confidence_layer.py",
        "derived.state.regime_synoptic",
        r'derived\[["\']state["\']\]\s*=',
    ),
]


def _iter_py_files(root):
    for base, _, files in os.walk(root):
        if "__pycache__" in base:
            continue
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(base, f)


def _grep_writer(pattern):
    """Return list of (relpath, line_no, line) matching pattern under weather_collector/."""
    hits = []
    rx = re.compile(pattern)
    for path in _iter_py_files(COLLECTOR_DIR):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    # Skip comment-only lines to reduce false positives on
                    # docstrings that mention the write pattern.
                    stripped = line.lstrip()
                    if stripped.startswith("#"):
                        continue
                    if rx.search(line):
                        rel = os.path.relpath(path, REPO)
                        hits.append((rel, i, stripped.rstrip()))
        except (OSError, UnicodeDecodeError):
            continue
    return hits


def check_config_coherence():
    """Category A. Returns (passes, failures) — lists of strings."""
    passes, failures = [], []

    all_fields = set(L3_FIELDS) | set(L4_FIELDS) | {f for (f, _) in SKIP_TABLE.keys()}
    for field in sorted(all_fields):
        if field not in TARGET_ARRAY:
            failures.append(f"field '{field}' missing from TARGET_ARRAY")
        if field not in CAPS:
            failures.append(f"field '{field}' missing from CAPS")

    for (field, layer) in SKIP_TABLE.keys():
        if layer not in KNOWN_LAYERS:
            failures.append(f"SKIP_TABLE key ({field!r}, {layer!r}): unknown layer")
        # Info-level: SKIP_TABLE field not in the corresponding L{n}_FIELDS.
        # Not a failure — dp/l4 is an architectural placeholder — but visible.
        target_fields = L3_FIELDS if layer == "l3" else L4_FIELDS if layer == "l4" else set()
        if field not in target_fields:
            passes.append(
                f"INFO SKIP_TABLE has ({field!r}, {layer!r}) but {field!r} not in "
                f"L{layer[-1]}_FIELDS — placeholder, no correction to skip"
            )

    for field in sorted(L3_FIELDS):
        if field in TARGET_ARRAY and field in CAPS:
            passes.append(f"L3_FIELDS: {field} → {TARGET_ARRAY[field]} (cap {CAPS[field]})")
    for field in sorted(L4_FIELDS):
        if field in TARGET_ARRAY and field in CAPS:
            passes.append(f"L4_FIELDS: {field} → {TARGET_ARRAY[field]} (cap {CAPS[field]})")

    return passes, failures


def check_state_read_writer():
    """Category B. Returns (passes, failures) — lists of strings."""
    passes, failures = [], []
    for reader, derived_path, writer_regex in STATE_READ_TABLE:
        hits = _grep_writer(writer_regex)
        if not hits:
            failures.append(
                f"{reader} reads {derived_path} — NO WRITER found for /{writer_regex}/"
            )
            continue
        writer_locs = ", ".join(f"{p}:{ln}" for (p, ln, _) in hits[:3])
        more = f" (+{len(hits)-3} more)" if len(hits) > 3 else ""
        passes.append(f"{reader} reads {derived_path} → written at {writer_locs}{more}")
    return passes, failures


def main():
    print("=" * 72)
    print("Applied-layer consistency audit")
    print("=" * 72)

    a_pass, a_fail = check_config_coherence()
    print("\n[A] Config coherence")
    print("-" * 72)
    for line in a_pass:
        print(f"  ok    {line}")
    for line in a_fail:
        print(f"  FAIL  {line}")

    b_pass, b_fail = check_state_read_writer()
    print("\n[B] State read/writer coherence")
    print("-" * 72)
    for line in b_pass:
        print(f"  ok    {line}")
    for line in b_fail:
        print(f"  FAIL  {line}")

    total_fail = len(a_fail) + len(b_fail)
    print("\n" + "=" * 72)
    if total_fail:
        print(f"FAIL — {total_fail} problem(s)")
        return 1
    print("PASS — all checks green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
