#!/usr/bin/env python3
"""Write architecture.json for the debug page's "Architecture now" block (v0.7.99).

Two parts, both read from the repo at build time so the block cannot drift from the code:
  components  - each piece of the pipeline and whether it is served, shadow or off, read from
                the flags in the code that decide it (regex on the source, no imports).
  changes     - every CHANGELOG.md entry carrying a "- Architecture: ..." line, newest first.
                A release that changes the architecture adds that line; nothing else is curated.

Run by build.py on every release; also runnable alone:  python3 scripts/architecture_state.py
"""
import json
import re
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
    rows = [
        ("HRRR cascade", "served", "L1 raw HRRR, L2 station bias, L3 decay, L4 diurnal, specialists.", None),
        ("NBM cascade", "served", "raw NBM, L2_nbm, L3_nbm, L4_nbm, wdp_nbm; runs beside the HRRR cascade.", None),
        ("Terminal blend", "served",
         "HRRR / NBM / ECMWF weights per field and lead band (t, h, ws 3-way), refit daily at 04:30 by the refitter. "
         f"Fit truth: {'station readings (t, h)' if station_truth else 'shrunk observed (station bias toward the model)'}.",
         "analysis/terminal_blend_field_fit.py STATION_TRUTH"),
        ("Selector", "served", "Picks HRRR side, NBM side or blend per field x regime x lead band and writes it into the served arrays.", None),
        ("t_urmab (URMA-truth blend)", "shadow" if urmab else "off",
         "Per-source bias vs URMA removed, then HRRR/NBM/ECMWF blended, 6 to 47 h. Logged as forecast_urmab; never served. "
         f"Refit table {'registered' if 'urma_blend_shadow_curated.json' in tables else 'NOT registered'} with the refitter.",
         "weather_collector/processors/urma_blend_shadow.py ENABLED"),
        ("Scoreboard truth", "served",
         "Tiles grade on the pair-log observed: the station network shrunk toward the model, which is L2's own output. "
         "The truth table grades the same rows on station readings and (t) on URMA.", None),
        ("Weather Underground", "on" if _flag("weather_collector/fetchers/wu.py", "WU_ENABLED") else "off",
         "Key throttled since October; Tempest is the only station feed.", "weather_collector/fetchers/wu.py WU_ENABLED"),
        ("WU archive poller", "on" if _flag("weather_collector/processors/wu_archive.py", "WU_ARCHIVE_ENABLED") else "off",
         "Dormant until a working key exists.", "weather_collector/processors/wu_archive.py WU_ARCHIVE_ENABLED"),
    ]
    return [{"name": n, "status": s, "what": w, "flag": f} for n, s, w, f in rows], tables


def changes():
    text = (ROOT / "docs" / "CHANGELOG.md").read_text()
    out = []
    for m in re.finditer(r"<summary><strong>(v[\d.]+(?:[–-]v[\d.]+)?) • ([^(<]+?)\s*(?:\(([^)]*)\))?</strong></summary>(.*?)</details>", text, re.S):
        for a in re.findall(r"^[-*]\s*Architecture:\s*(.+)$", m.group(4), re.M):
            out.append({"version": m.group(1), "date": m.group(2).strip(), "title": m.group(3) or "", "change": a.strip()})
    return out


def main():
    comps, tables = components()
    version = json.loads((ROOT / "version.json").read_text())["version"]
    payload = {"version": version, "components": comps, "refit_tables": tables, "changes": changes()}
    (ROOT / "architecture.json").write_text(json.dumps(payload, indent=1) + "\n")
    print(f"  ✓ architecture.json → {len(comps)} components, {len(payload['changes'])} architecture changes")


if __name__ == "__main__":
    main()
