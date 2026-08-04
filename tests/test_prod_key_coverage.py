"""
Debug-page prod-key coverage: PROD_PRIORITY and _prodKey in
corrections_debug.html must include every currently-ENABLED specialist in
weather_collector/processors/. If a specialist ships ENABLED=True but its
key isn't in the priority list, the pf-mae / pf-today fallback silently
picks a stale layer — same class as v0.6.390j (shadow-write applied_layer
trap) and v0.6.390y (h_persistence_skill top-level forecast reconstruction
bug). Enforce at commit time.

Discovery: any weather_collector/processors/*.py with a module-level
ENABLED = True constant that also declares a specialist key. Key is either
(a) the module's `LAYER_ID` / `SPECIALIST_KEY` constant if present, or
(b) derived from filename convention (dp_bias_persistence.py → dpbp,
ch_persistence_gate.py → chp, wd_persistence.py → wdp, cl_persistence_gate.py
→ clp, cc_from_derivation.py → ccd, solar_correction.py → l5, ...). The
existing SPECIALIST_KEY_MAP below covers the current stack; add new
mappings when a new specialist ships.

Run: python3 -m pytest tests/test_prod_key_coverage.py -v
"""
import ast
import re
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = Path(__file__).resolve().parent.parent
PROCESSORS = REPO / "weather_collector" / "processors"
DEBUG_HTML = REPO / "corrections_debug.html"

# Filename → (key surfaced in pair-log / applied_layer stamp, field(s) it touches).
# When a new specialist ships, add its entry here. This is the canonical
# registry the test uses; the pair-log emit tuple, PROD_PRIORITY, and
# _prodKey/_applied all must cover every entry.
SPECIALIST_KEY_MAP = {
    "dp_bias_persistence.py":     ("dpbp", ["dp"]),
    "ws_bias_persistence.py":     ("wsbp", ["ws"]),
    "wd_persistence.py":          ("wdp",  ["wd"]),
    "ch_persistence_gate.py":     ("chp",  ["ch"]),
    "cl_persistence_gate.py":     ("clp",  ["cl"]),
    # cc_from_derivation stamps hourly.cloud_cover in place — Ccd shows up
    # as l6 in the pair log (cc's deepest cloud layer), not as its own key.
    # No entry required.
    # solar_correction (L5/Lsr) surfaces as l5 — already in PROD_PRIORITY.
    # cloud_saturation_correction (Lc) surfaces as l6.
}


def _is_enabled(src):
    """Return True if module has a top-level ENABLED = True."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and tgt.id == "ENABLED":
                if isinstance(node.value, ast.Constant) and node.value.value is True:
                    return True
    return False


def _load_prod_priority():
    """Return dict field → list-of-layer-keys from the PROD_PRIORITY literal
    in corrections_debug.html."""
    html = DEBUG_HTML.read_text()
    m = re.search(r"const\s+PROD_PRIORITY\s*=\s*\{(.*?)\};", html, re.S)
    assert m, "PROD_PRIORITY not found in corrections_debug.html"
    body = m.group(1)
    out = {}
    for line in body.splitlines():
        line = line.split("//", 1)[0].rstrip().rstrip(",")
        m2 = re.match(r"\s*([a-z]+)\s*:\s*\[(.*)\]\s*$", line)
        if not m2:
            continue
        field = m2.group(1)
        keys = [s.strip().strip('"').strip("'") for s in m2.group(2).split(",")]
        keys = [k for k in keys if k]
        out[field] = keys
    return out


def _load_prod_key_list():
    """Return the layer-key list from _prodKey's `for (const k of [...])`."""
    html = DEBUG_HTML.read_text()
    m = re.search(
        r"const\s+_prodKey\s*=.*?for\s*\(\s*const\s+k\s+of\s+\[([^\]]+)\]",
        html, re.S,
    )
    assert m, "_prodKey priority list not found in corrections_debug.html"
    return [s.strip().strip('"').strip("'") for s in m.group(1).split(",") if s.strip()]


def _load_applied_map():
    """Return dict specialist_key → set(fields), unioned across every
    `const _applied = ...` block in corrections_debug.html. The debug page
    has two implementations (renderStackOverview + renderPerFieldSnapshot);
    tolerate either `k/f` or `layerKey/fieldKey` variable naming."""
    html = DEBUG_HTML.read_text()
    out = {}
    # Match each _applied assignment and its balanced body separately.
    for block in re.finditer(r"const\s+_applied\s*=\s*\([^)]*\)\s*=>\s*\{(.*?)\n\s*\};", html, re.S):
        body = block.group(1)
        # Accept either variable name style (k/f or layerKey/fieldKey).
        # Single-field: `if (k === "dpbp") return f === "dp";`
        for match in re.finditer(
            r'if\s*\(\s*(?:k|layerKey)\s*===\s*"(\w+)"\s*\)\s*return\s+(?:f|fieldKey)\s*===\s*"(\w+)"\s*;',
            body,
        ):
            out.setdefault(match.group(1), set()).add(match.group(2))
        # Multi-field: `if (k === "l6") return ["cc","cl","cm","ch"].includes(f);`
        for match in re.finditer(
            r'if\s*\(\s*(?:k|layerKey)\s*===\s*"(\w+)"\s*\)\s*return\s*\[([^\]]+)\]\.includes\s*\(\s*(?:f|fieldKey)\s*\)',
            body,
        ):
            fields = {s.strip().strip('"').strip("'") for s in match.group(2).split(",")}
            out.setdefault(match.group(1), set()).update(fields)
    return out


def discover_enabled_specialists():
    """Walk processors/, return list of (specialist_key, [fields])."""
    found = []
    for path in sorted(PROCESSORS.glob("*.py")):
        entry = SPECIALIST_KEY_MAP.get(path.name)
        if not entry:
            continue
        if not _is_enabled(path.read_text()):
            continue
        found.append(entry)
    return found


def test_prod_priority_covers_enabled_specialists():
    priority = _load_prod_priority()
    enabled = discover_enabled_specialists()
    missing = []
    for key, fields in enabled:
        for f in fields:
            chain = priority.get(f, [])
            if key not in chain:
                missing.append(f"{f} chain missing '{key}': {chain}")
    assert not missing, (
        "PROD_PRIORITY in corrections_debug.html is missing ENABLED specialists.\n"
        "Add them to the priority list for the fields they touch:\n  "
        + "\n  ".join(missing)
    )


def test_prod_key_list_covers_enabled_specialists():
    key_list = _load_prod_key_list()
    enabled = discover_enabled_specialists()
    missing = [key for key, _fields in enabled if key not in key_list]
    assert not missing, (
        "_prodKey's priority array in corrections_debug.html is missing "
        f"ENABLED specialists: {missing}. "
        "Add them to the `for (const k of [...])` list in _prodKey."
    )


def test_applied_map_covers_enabled_specialists():
    applied = _load_applied_map()
    enabled = discover_enabled_specialists()
    missing = []
    for key, fields in enabled:
        mapped = applied.get(key, set())
        for f in fields:
            if f not in mapped:
                missing.append(f"_applied('{key}', '{f}') → not mapped (currently maps to {sorted(mapped) or 'nothing'})")
    assert not missing, (
        "_applied in corrections_debug.html doesn't map ENABLED specialists "
        "to the fields they touch:\n  " + "\n  ".join(missing)
    )


def test_prod_priority_prod_real_first():
    """Every field must have 'prod_real' as its first-preference layer.
    Anything else means the pf-mae / pf-today fallback would ignore the
    real per-row aggregate keyed on applied_layer stamps."""
    priority = _load_prod_priority()
    bad = [f for f, chain in priority.items() if not chain or chain[0] != "prod_real"]
    assert not bad, (
        f"PROD_PRIORITY fields missing prod_real as first entry: {bad}"
    )
