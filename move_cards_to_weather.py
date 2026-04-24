#!/usr/bin/env python3
"""
move_cards_to_weather.py  (v2 - with feelsLike markup repair)

Three jobs in one script:

  1. Fix the broken #feelsLike div in the Right Now card.
     Current (broken):
       <div id="feelsLike" class="feels-like">{const c=document.querySelector('[data-collapse-key="feels_like"]'); if(c) c.click();},100);">
     Target (clean, non-interactive):
       <div id="feelsLike" class="feels-like">
     Also strips the now-meaningless chevron from the child line.

  2. Move three cards from Hyperlocal to end of Weather tab:
       - Feels Like  (data-collapse-key="feels_like")
       - Fog         (data-collapse-key="fog_risk")
       - Sea Breeze  (data-collapse-key="sea_breeze_detail")

  3. Bump version v4.79 -> v4.80.

Run from ~/Documents/myweather/

Usage:
    python3 move_cards_to_weather.py          # dry-run
    python3 move_cards_to_weather.py --apply  # writes + backup
"""

import sys
import shutil
import difflib
from datetime import datetime
from pathlib import Path

INDEX_HTML = Path("index.html")

VERSION_OLD = '<span class="version-pill" id="appVersion">v4.79</span>'
VERSION_NEW = '<span class="version-pill" id="appVersion">v4.80</span>'

# ----------------------------------------------------------------------
# Broken markup fix
# ----------------------------------------------------------------------
BROKEN_FEELSLIKE = '<div id="feelsLike" class="feels-like">{const c=document.querySelector(\'[data-collapse-key="feels_like"]\'); if(c) c.click();},100);">'
FIXED_FEELSLIKE  = '<div id="feelsLike" class="feels-like">'

CHEVRON_LINE_OLD = 'Feels like --&deg;F <span style="font-size:0.7em;opacity:0.5;">&#8250;</span>'
CHEVRON_LINE_NEW = 'Feels like --&deg;F'

# ----------------------------------------------------------------------
# Card moves - use full opening-tag prefix to avoid collision with the
# [data-collapse-key="feels_like"] querySelector string embedded elsewhere
# ----------------------------------------------------------------------
CARDS_TO_MOVE = [
    ("feels_like",        '<div class="card col-6" data-collapse-key="feels_like"'),
    ("fog_risk",          '<div class="card col-6" data-collapse-key="fog_risk"'),
    ("sea_breeze_detail", '<div class="card col-6" data-collapse-key="sea_breeze_detail"'),
]

WEATHER_SECTION_OPEN    = '<section id="weatherView">'
HYPERLOCAL_SECTION_OPEN = '<section id="hyperlocalView"'


def find_card_bounds(content, opening_anchor):
    """Find start/end offsets of the card whose opening tag matches opening_anchor.
    Includes leading/trailing blank lines for clean spacing preservation.
    Returns (None, None) on parse failure."""
    start_idx = content.find(opening_anchor)
    if start_idx == -1:
        return None, None

    open_end = content.find(">", start_idx)
    if open_end == -1:
        return None, None
    depth = 1
    pos = open_end + 1
    while pos < len(content) and depth > 0:
        next_open  = content.find("<div", pos)
        next_close = content.find("</div>", pos)
        if next_close == -1:
            return None, None
        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + 4
        else:
            depth -= 1
            pos = next_close + len("</div>")
    if depth != 0:
        return None, None

    end_idx = pos
    if end_idx < len(content) and content[end_idx] == "\n":
        end_idx += 1
    while end_idx < len(content):
        line_end = content.find("\n", end_idx)
        if line_end == -1:
            break
        line = content[end_idx:line_end]
        if line.strip() == "":
            end_idx = line_end + 1
        else:
            break

    leading = start_idx
    while leading > 0:
        prev_newline_start = content.rfind("\n", 0, leading - 1)
        if prev_newline_start == -1:
            break
        prev_line = content[prev_newline_start + 1:leading - 1]
        if prev_line.strip() == "":
            leading = prev_newline_start + 1
        else:
            break

    return leading, end_idx


def find_weather_tab_grid_close(content):
    """Find index of the <div>-closing </div> that terminates the .grid
    container inside <section id="weatherView">."""
    sec_start = content.find(WEATHER_SECTION_OPEN)
    if sec_start == -1:
        return None
    sec_open_end = content.find(">", sec_start)
    if sec_open_end == -1:
        return None

    depth = 1
    pos = sec_open_end + 1
    section_close_start = None
    while pos < len(content) and depth > 0:
        next_open  = content.find("<section", pos)
        next_close = content.find("</section>", pos)
        if next_close == -1:
            return None
        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + len("<section")
        else:
            depth -= 1
            if depth == 0:
                section_close_start = next_close
                break
            pos = next_close + len("</section>")
    if section_close_start is None:
        return None

    segment = content[:section_close_start]
    grid_close = segment.rfind("</div>")
    if grid_close == -1:
        return None
    return grid_close


def main():
    apply_mode = "--apply" in sys.argv

    if not INDEX_HTML.exists():
        print("ERROR: Must be run from ~/Documents/myweather/")
        sys.exit(1)

    original = INDEX_HTML.read_text(encoding="utf-8")
    working = original

    # ----- Preflight -----
    errors = []

    feelslike_broken_count = working.count(BROKEN_FEELSLIKE)
    if feelslike_broken_count > 1:
        errors.append(f"  [!] Broken feelsLike markup appears {feelslike_broken_count}x (expected 0 or 1)")

    for key, anchor in CARDS_TO_MOVE:
        count = working.count(anchor)
        if count == 0:
            errors.append(f"  [!] {key}: anchor not found (already moved?)")
        elif count > 1:
            errors.append(f"  [!] {key}: anchor appears {count} times (expected 1)")

    hyp_start = working.find(HYPERLOCAL_SECTION_OPEN)
    if hyp_start == -1:
        errors.append("  [!] Could not find hyperlocalView section")
    else:
        for key, anchor in CARDS_TO_MOVE:
            idx = working.find(anchor)
            if idx != -1 and idx < hyp_start:
                errors.append(f"  [!] {key}: not in Hyperlocal section (already moved?)")

    if VERSION_OLD not in working and VERSION_NEW not in working:
        errors.append("  [!] Could not find version v4.79 or v4.80")

    if errors:
        print("Preflight FAILED:")
        for e in errors:
            print(e)
        sys.exit(1)

    # ----- Transform 1: feelsLike markup repair -----
    feelslike_fix_applied = False
    chevron_removed = False
    if feelslike_broken_count == 1:
        working = working.replace(BROKEN_FEELSLIKE, FIXED_FEELSLIKE, 1)
        feelslike_fix_applied = True
        if CHEVRON_LINE_OLD in working:
            working = working.replace(CHEVRON_LINE_OLD, CHEVRON_LINE_NEW, 1)
            chevron_removed = True

    # ----- Transform 2: Move cards -----
    extracted_blocks = []
    for key, anchor in CARDS_TO_MOVE:
        start, end = find_card_bounds(working, anchor)
        if start is None:
            print(f"ERROR: Could not determine bounds of {key} card")
            sys.exit(1)
        extracted_blocks.append((key, working[start:end]))
        working = working[:start] + working[end:]

    grid_close_idx = find_weather_tab_grid_close(working)
    if grid_close_idx is None:
        print("ERROR: Could not find Weather tab grid close")
        sys.exit(1)
    line_start = working.rfind("\n", 0, grid_close_idx) + 1
    insertion = "".join(block for _, block in extracted_blocks)
    working = working[:line_start] + insertion + working[line_start:]

    # ----- Transform 3: Version bump -----
    if VERSION_OLD in working:
        working = working.replace(VERSION_OLD, VERSION_NEW, 1)
        version_msg = "Bumped v4.79 -> v4.80"
    else:
        version_msg = "Version already v4.80 (no change)"

    # ----- Post checks -----
    checks = []
    for key, anchor in CARDS_TO_MOVE:
        count = working.count(anchor)
        checks.append((f"{key} card present exactly once", count == 1, count))

    weather_sec = working.find(WEATHER_SECTION_OPEN)
    hyp_sec = working.find(HYPERLOCAL_SECTION_OPEN)
    for key, _ in CARDS_TO_MOVE:
        # For feels_like, the string data-collapse-key="feels_like" may appear
        # in the onclick handler too (now fixed out, but belt and suspenders).
        # Use the full opening-tag anchor to find just the card itself.
        card_opening = f'<div class="card col-6" data-collapse-key="{key}"'
        idx = working.find(card_opening)
        in_weather = (weather_sec != -1 and hyp_sec != -1 and
                      weather_sec < idx < hyp_sec)
        checks.append((f"{key} card inside Weather section", in_weather, "yes" if in_weather else "no"))

    still_broken = BROKEN_FEELSLIKE in working
    checks.append(("feelsLike markup clean", not still_broken, "clean" if not still_broken else "STILL BROKEN"))

    # ----- Report -----
    mode = "APPLY" if apply_mode else "DRY-RUN"
    print("=" * 72)
    print(f"  move_cards_to_weather.py (v2) \u2014 {mode}")
    print("=" * 72)
    print()
    print("Plan:")
    if feelslike_fix_applied:
        print(f"  [+] Fix broken #feelsLike div markup")
        if chevron_removed:
            print(f"  [+] Remove now-meaningless chevron next to 'Feels like --\u00b0F'")
    else:
        print(f"  [=] feelsLike markup already clean")
    for key, _ in CARDS_TO_MOVE:
        print(f"  [+] Move {key} card to Weather tab")
    print(f"  [+] {version_msg}")
    print()
    print("-" * 72)
    print("Diff (abbreviated):")
    print("-" * 72)
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        working.splitlines(keepends=True),
        fromfile="index.html (before)",
        tofile="index.html (after)",
        n=1
    )
    diff_text = "".join(diff)
    diff_lines = diff_text.splitlines(keepends=True)
    if len(diff_lines) > 400:
        head = "".join(diff_lines[:200])
        tail = "".join(diff_lines[-100:])
        print(head)
        print(f"\n... [{len(diff_lines) - 300} diff lines omitted] ...\n")
        print(tail)
    else:
        print(diff_text)
    print()

    print("Post-transform checks:")
    all_ok = True
    for name, ok, detail in checks:
        marker = "[\u2713]" if ok else "[!]"
        if not ok:
            all_ok = False
        print(f"  {marker} {name}: {detail}")
    if not all_ok:
        print()
        print("  \u26a0  Some checks failed. Review diff carefully before applying.")
        if apply_mode:
            print("  Refusing to apply with failed checks.")
            sys.exit(2)
    print()

    if not apply_mode:
        print("=" * 72)
        print("  Dry-run complete. Re-run with --apply to write.")
        print("=" * 72)
        sys.exit(0)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = INDEX_HTML.with_suffix(INDEX_HTML.suffix + f".bak.{ts}")
    shutil.copy2(INDEX_HTML, bak)
    INDEX_HTML.write_text(working, encoding="utf-8")

    print("=" * 72)
    print("  Applied.")
    print("=" * 72)
    print(f"  wrote:  {INDEX_HTML}")
    print(f"  backup: {bak}")
    print()
    print("Next steps:")
    print("  1. python3 build.py")
    print("  2. Reload PWA and verify:")
    print("     a. Weather tab ends with Feels Like \u2192 Fog \u2192 Sea Breeze")
    print("     b. Hyperlocal tab: those three are GONE; remaining:")
    print("        Corrections, Wind Impact, Hair Day, Sunset, Dock Day, Birds")
    print("     c. Tap each moved card \u2014 content renders correctly")
    print("     d. 'Feels like --\u00b0F' chevron gone and no longer tappable")
    print("  3. Update docs/CHANGELOG.md with v4.80 entry")
    print("  4. git add -A && git commit -m 'v4.80 reorganize Weather and Hyperlocal tabs'")
    print("  5. git push --force-with-lease")


if __name__ == "__main__":
    main()
