#!/usr/bin/env python3
"""Write architecture.json for the debug page's "Architecture now" block (v0.7.99).

Two parts, both read from the repo at build time so the block cannot drift from the code:
  components  - each piece of the pipeline and whether it is served, shadow or off, read from
                the flags in the code that decide it (regex on the source, no imports).
  changes     - every CHANGELOG.md entry carrying a "- Architecture: ..." line, newest first.
  releases    - the newest 12 CHANGELOG.md entries (version, date, plain title), for the debug
                page's "What changed recently" (v0.7.107); nothing hand-kept.
                A release that changes the architecture adds that line; nothing else is curated.

Run by build.py on every release; also runnable alone:  python3 scripts/architecture_state.py
"""
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _flag(rel, name):
    m = re.search(rf"^{name}\s*=\s*(\w+)", (ROOT / rel).read_text(), re.M)
    return None if not m else m.group(1) == "True"


def _refit_tables():
    return re.findall(r'"name":\s*"([^"]+)"', (ROOT / "refitter" / "tables.py").read_text())


def components():
    tables = _refit_tables()
    station_truth = _flag("analysis/terminal_blend_field_fit.py", "STATION_TRUTH")
    urmab = _flag("weather_collector/processors/urma_blend_shadow.py", "ENABLED")
    urmab_serve = urmab and _flag("weather_collector/processors/urma_blend_shadow.py", "SERVE")
    rows = [
        ("HRRR cascade", "served", "L1 raw HRRR, L2 station bias, L3 decay, L4 diurnal, specialists.", None),
        ("NBM cascade", "served", "raw NBM, L2_nbm, L3_nbm, L4_nbm, wdp_nbm; runs beside the HRRR cascade.", None),
        ("Terminal blend", "served",
         "HRRR / NBM / ECMWF weights per field and lead band (t, h, ws 3-way), refit daily at 04:30 by the refitter. "
         f"Fit truth: {'station readings (t, h)' if station_truth else 'shrunk observed (station bias toward the model)'}.",
         "analysis/terminal_blend_field_fit.py STATION_TRUTH"),
        ("Selector", "served", "Picks HRRR side, NBM side or blend per field x regime x lead band and writes it into the served arrays.", None),
        ("t_urmab (URMA-truth blend)", "served" if urmab_serve else ("shadow" if urmab else "off"),
         "Per-source bias vs URMA removed, then HRRR/NBM/ECMWF blended, 6 to 47 h. "
         + ("Served for t since v0.7.114 (kill switch: runtime_tables/urma_blend_serve.json); the old served t is logged as t_pre_urmab. " if urmab_serve else "Logged as forecast_urmab; never served. ")
         +
         f"Refit table {'registered' if 'urma_blend_shadow_curated.json' in tables else 'NOT registered'} with the refitter.",
         "weather_collector/processors/urma_blend_shadow.py SERVE"),
        ("Scoreboard truth", "served",
         "Tiles grade on the pair-log observed: the station network shrunk toward the model, which is L2's own output. "
         "The truth table grades the same rows on station readings and (t) on URMA.", None),
        ("Weather Underground", "on" if _flag("weather_collector/fetchers/wu.py", "WU_ENABLED") else "off",
         "Off in the live blend: Tempest is the only live station feed. WU is collected in shadow by the archive poller.", "weather_collector/fetchers/wu.py WU_ENABLED"),
        ("WU archive poller", "on" if _flag("weather_collector/processors/wu_archive.py", "WU_ARCHIVE_ENABLED") else "off",
         "Own key since 2026-11-18. Own sensor + 7 chosen neighbours every tick, the other working stations twice a day; shadow only, nothing served reads it.", "weather_collector/processors/wu_archive.py WU_ARCHIVE_ENABLED"),
    ]
    return [{"name": n, "status": s, "what": w, "flag": f} for n, s, w, f in rows], tables


def changes():
    text = (ROOT / "docs" / "CHANGELOG.md").read_text()
    out = []
    for m in re.finditer(r"<summary><strong>(v[\d.]+(?:[–-]v[\d.]+)?) • ([^(<]+?)\s*(?:\(([^)]*)\))?</strong></summary>(.*?)</details>", text, re.S):
        for a in re.findall(r"^[-*]\s*Architecture:\s*(.+)$", m.group(4), re.M):
            date = m.group(2).strip()
            try:
                iso = datetime.strptime(re.sub(r"[–-]\d+,", ",", date), "%B %d, %Y").strftime("%Y-%m-%d")
            except ValueError:
                iso = None
            out.append({"version": m.group(1), "date": date, "iso": iso, "title": m.group(3) or "", "change": a.strip()})
    return out


def releases(limit=12):
    text = (ROOT / "docs" / "CHANGELOG.md").read_text()
    out = []
    for m in re.finditer(r"<summary><strong>(v[\d.]+[a-z]?(?:[–-]v[\d.]+[a-z]?)?) • ([^(<]+?)\s*(?:\(([^)]*)\))?</strong></summary>", text):
        date = m.group(2).strip()
        try:
            iso = datetime.strptime(re.sub(r"[–-]\d+,", ",", date), "%B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            iso = None
        out.append({"version": m.group(1), "date": date, "iso": iso, "title": (m.group(3) or "").strip()})
        if len(out) >= limit:
            break
    return out


def _py_literal(rel, name):
    """Value of a top-level `NAME = <literal>` (set/dict/list/frozenset/number) in a source file, via ast; None if absent."""
    import ast
    tree = ast.parse((ROOT / rel).read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            v = node.value
            if isinstance(v, ast.Call) and getattr(v.func, "id", "") == "frozenset" and v.args:
                v = v.args[0]
            try:
                return ast.literal_eval(v)
            except ValueError:
                return None
    return None


def layers():
    """Per-layer live configuration read from the code and the fitted tables, for the debug page's layer sections."""
    da = "weather_collector/processors/decay_apply.py"
    sc = "weather_collector/processors/solar_correction.py"
    cs = "weather_collector/processors/cloud_saturation_correction.py"
    out = {
        "l3_fields": sorted(_py_literal(da, "L3_FIELDS") or []),
        "l4_fields": sorted(_py_literal(da, "L4_FIELDS") or []),
        "blend_fields": sorted(_py_literal("weather_collector/processors/terminal_static_blend.py", "FIELD_APPLIED") or []),
        "lsr": {"enabled": _flag(sc, "ENABLED"), "sun_up_wm2": _py_literal(sc, "SUN_UP_THRESHOLD"),
                "skip_regimes": sorted(_py_literal(sc, "L5_SKIP_REGIMES") or [])},
        "lc": {"enabled": _flag(cs, "ENABLED"), "field_skip": sorted(_py_literal(cs, "_FIELD_SKIP") or []), "cells": {}},
    }
    try:
        t = json.loads((ROOT / "weather_collector/data/lc_correction_table.json").read_text())
        out["lc"]["fit_generated_at"] = t.get("generated_at")
        out["lc"]["cells"] = {f: {b: {"shift": c.get("shift"), "verdict": c.get("verdict"), "improve_pct": c.get("improve_pct"), "n": c.get("n")}
                                  for b, c in bins.items()} for f, bins in (t.get("cells") or {}).items()}
    except (OSError, ValueError):
        pass
    return out


def main():
    comps, tables = components()
    version = json.loads((ROOT / "version.json").read_text())["version"]
    payload = {"version": version, "components": comps, "refit_tables": tables, "changes": changes(), "releases": releases(), "layers": layers()}
    (ROOT / "architecture.json").write_text(json.dumps(payload, indent=1) + "\n")
    print(f"  ✓ architecture.json → {len(comps)} components, {len(payload['changes'])} architecture changes")


if __name__ == "__main__":
    main()
