"""
Layer-tuple sanity: forecast_snapshot._derive_applied_layer walks a list
of layer keys. forecast_error_log emits forecast_/error_ pairs for a list
of layer keys. Both lists must match. Any drift = potential silent bug
where applied_layer gets stamped to a layer that has no corresponding
error_ column downstream (or vice versa).

Motivating incidents:
 - v0.6.390c: wdp missing from forecast_error_log tuple. Hid wd damage for weeks.
 - v0.6.390j: clp shadow tagged applied but clp always in tuple. Different
   failure mode (shadow-write mislabel), same class (walk-order drift).

When a new specialist ships, add it to BOTH tuples and the guard in
_derive_applied_layer. This test enforces the first two.

Run: python3 -m pytest tests/test_layer_tuple_sanity.py -v
"""
import ast
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROCESSORS = Path(__file__).resolve().parent.parent / "weather_collector" / "processors"


def _extract_tuple_after_marker(src, marker):
    """Find a `for lyr in (...)` or `for lk in (...)` line whose preceding
    comment or nearby line contains `marker`, and return the tuple literal.
    Uses ast for the tuple itself; the marker is grep-scoped."""
    tree = ast.parse(src)
    lines = src.splitlines()
    marker_lines = [i for i, ln in enumerate(lines) if marker in ln]
    if not marker_lines:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        if not isinstance(node.iter, ast.Tuple):
            continue
        # Only for-loops within ~30 lines after the marker.
        if not any(m < node.lineno <= m + 30 for m in marker_lines):
            continue
        try:
            values = tuple(ast.literal_eval(e) for e in node.iter.elts)
        except Exception:
            continue
        # Must be a tuple of layer strings.
        if not all(isinstance(v, str) and 1 <= len(v) <= 5 for v in values):
            continue
        if "l1" not in values:
            continue
        return values
    return None


def _extract_snapshot_walk():
    src = (PROCESSORS / "forecast_snapshot.py").read_text()
    return _extract_tuple_after_marker(src, "iteration order = pipeline order")


def _extract_error_log_tuple():
    src = (PROCESSORS / "forecast_error_log.py").read_text()
    return _extract_tuple_after_marker(src, "per-layer forecast values + errors")


def test_layer_tuples_match():
    snapshot = _extract_snapshot_walk()
    error_log = _extract_error_log_tuple()
    assert snapshot is not None, "could not locate _derive_applied_layer walk tuple"
    assert error_log is not None, "could not locate forecast_error_log emit tuple"
    missing_in_log = set(snapshot) - set(error_log)
    missing_in_snap = set(error_log) - set(snapshot)
    assert not missing_in_log, (
        f"layers stamped by applied_layer but NOT emitted as error_/forecast_ "
        f"columns: {missing_in_log}. Add to forecast_error_log.py per-layer tuple."
    )
    assert not missing_in_snap, (
        f"layers emitted as error_/forecast_ columns but NOT walked by "
        f"applied_layer stamper: {missing_in_snap}. Add to forecast_snapshot.py "
        f"_derive_applied_layer walk tuple."
    )


def test_specialist_enabled_guards_present():
    """Every specialist in the snapshot walk (post-l6) must have an ENABLED
    guard in _derive_applied_layer. Prevents v0.6.390j-class regression
    where a dormant specialist's shadow poisons applied_layer stamps.

    Enforced by grepping for `<key> and not <module>.ENABLED` in the
    function body. Loose match — if the pattern evolves, update this
    test alongside."""
    src = (PROCESSORS / "forecast_snapshot.py").read_text()
    walk = _extract_snapshot_walk() or ()
    specialists = [k for k in walk if k not in ("l1", "l2", "l3", "l4", "l5", "l6")]
    for sp in specialists:
        marker = f'lk == "{sp}"'
        assert marker in src, (
            f"specialist '{sp}' has no ENABLED guard in "
            f"forecast_snapshot._derive_applied_layer. Add: "
            f'`if lk == "{sp}" and not <module>.ENABLED: continue` next to '
            f"the existing guards."
        )
