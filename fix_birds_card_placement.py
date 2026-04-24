#!/usr/bin/env python3
"""
fix_birds_card_placement.py

The Birds card is currently outside the .grid container on the Hyperlocal tab,
which breaks its width (col-6 has no grid parent to halve against) and removes
the grid gap spacing from above it.

This script:
  1. Removes the misplaced Birds card block
  2. Re-inserts it inside the .grid, immediately after the Dock Day card

Run from ~/Documents/myweather/

Usage:
    python3 fix_birds_card_placement.py            # dry-run
    python3 fix_birds_card_placement.py --apply    # writes + backup
"""

import sys
import shutil
import difflib
from datetime import datetime
from pathlib import Path

INDEX_HTML = Path("index.html")

# ----------------------------------------------------------------------
# The full Birds card block — must match EXACTLY what apply_birds_card.py
# inserted (leading blank line + 8-space indent block + trailing blank line).
# ----------------------------------------------------------------------
BIRDS_CARD_HTML = '''        
        <div class="card col-6" data-collapse-key="birds" data-default-open="false" onclick="if(!this.classList.contains('card-expanded')) toggleCard('birds', this.querySelector('.card-title-collapsible'))">
          <div class="card-title card-title-collapsible" style="cursor:default;">
            Birds<span class="collapse-chevron" style="display:none;">&#9660;</span>
          </div>
          <button class="card-close-btn" style="display:none;" onclick="event.stopPropagation(); toggleCard('birds', this.closest('.card').querySelector('.card-title-collapsible'))">\u2715</button>
          <div class="card-collapsed-preview" style="display:none;position:relative;min-height:192px;margin:-16px;">
            <div class="tile-label" style="top:12px;left:16px;">Birds</div>
            <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:192px;padding-top:12px;">
              <div style="font-size:2.4rem;line-height:1;margin-bottom:6px;">\U0001F426</div>
              <div id="birdsPrimaryCollapsed" style="font-size:1.05rem;font-weight:500;line-height:1.2;margin-bottom:4px;text-align:center;padding:0 12px;"></div>
              <div id="birdsSecondaryCollapsed" style="font-size:0.82rem;opacity:0.65;"></div>
            </div>
          </div>
          <div class="card-body" style="display:none;">
            <div id="birdsContent"></div>
          </div>
        </div>

'''

# ----------------------------------------------------------------------
# Anchor for re-insertion: we need a unique string that identifies the END
# of the Dock Day card. We find the Dock Day opening div, then find its
# matching closing </div> by counting depth.
# ----------------------------------------------------------------------
DOCK_DAY_OPEN = '<div class="card col-6" data-collapse-key="dock_day"'


def find_matching_close(content, open_idx):
    """Given the index of an opening <div ...>, find its matching </div>
    by counting nesting depth. Returns the index just AFTER the closing tag."""
    # Find end of the opening tag
    open_end = content.find(">", open_idx)
    if open_end == -1:
        return -1
    depth = 1
    pos = open_end + 1
    while pos < len(content) and depth > 0:
        next_open  = content.find("<div", pos)
        next_close = content.find("</div>", pos)
        if next_close == -1:
            return -1
        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + 4
        else:
            depth -= 1
            pos = next_close + len("</div>")
    if depth != 0:
        return -1
    return pos  # just after the closing </div>


def main():
    apply_mode = "--apply" in sys.argv

    if not INDEX_HTML.exists():
        print("ERROR: Must be run from ~/Documents/myweather/")
        sys.exit(1)

    original = INDEX_HTML.read_text(encoding="utf-8")

    # --- Sanity checks ------------------------------------------------
    card_count = original.count('data-collapse-key="birds"')
    if card_count == 0:
        print("ERROR: No Birds card found in index.html. Nothing to fix.")
        sys.exit(1)
    if card_count > 1:
        print(f"ERROR: Found {card_count} Birds cards. Refusing to modify \u2014 resolve manually.")
        sys.exit(1)

    if BIRDS_CARD_HTML not in original:
        print("ERROR: Could not find the exact Birds card block I inserted earlier.")
        print("       The card may have been hand-edited. Refusing to proceed.")
        print()
        print("       Looking for this block:")
        print("       " + repr(BIRDS_CARD_HTML[:80]) + "...")
        sys.exit(1)

    dock_day_count = original.count(DOCK_DAY_OPEN)
    if dock_day_count != 1:
        print(f"ERROR: Expected 1 Dock Day card, found {dock_day_count}")
        sys.exit(1)

    # --- Step 1: remove the current (misplaced) Birds card ------------
    step1 = original.replace(BIRDS_CARD_HTML, "", 1)

    # --- Step 2: find Dock Day's closing </div> and insert Birds after it
    dock_open_idx = step1.find(DOCK_DAY_OPEN)
    if dock_open_idx == -1:
        print("ERROR: Could not find Dock Day card after removing Birds")
        sys.exit(1)

    dock_close_end = find_matching_close(step1, dock_open_idx)
    if dock_close_end == -1:
        print("ERROR: Could not find matching </div> for Dock Day card")
        sys.exit(1)

    # Skip trailing newline so our block sits cleanly on its own lines
    insert_at = dock_close_end
    if insert_at < len(step1) and step1[insert_at] == "\n":
        insert_at += 1

    modified = step1[:insert_at] + BIRDS_CARD_HTML + step1[insert_at:]

    # --- Verify: Birds should now appear before the grid-closing </div>
    # Quick check: find the hyperlocalView section, find the Birds card
    # inside it, then check that between Birds-close and </section> there
    # is exactly one </div> (the grid wrapper close).
    hyp_start = modified.find('<section id="hyperlocalView"')
    hyp_end   = modified.find('</section>', hyp_start)
    birds_idx = modified.find('data-collapse-key="birds"', hyp_start, hyp_end)
    if birds_idx == -1:
        print("ERROR: Birds card not found inside hyperlocalView after fix")
        sys.exit(1)

    # Find Birds card's closing </div>
    birds_open_tag_start = modified.rfind("<div ", 0, birds_idx)
    birds_close_end = find_matching_close(modified, birds_open_tag_start)
    if birds_close_end == -1:
        print("ERROR: Could not find matching </div> for relocated Birds card")
        sys.exit(1)

    after_birds = modified[birds_close_end:hyp_end]
    div_closes_after = after_birds.count("</div>")
    div_opens_after  = after_birds.count("<div")
    if div_closes_after - div_opens_after != 1:
        print(f"WARNING: Expected exactly 1 net </div> between Birds-close and </section>,")
        print(f"         got {div_closes_after} closes and {div_opens_after} opens.")
        print(f"         This usually means the fix is still wrong. Review diff carefully.")
        # Don't bail \u2014 show the user anyway, they can decide

    # --- Report -------------------------------------------------------
    mode = "APPLY" if apply_mode else "DRY-RUN"
    print("=" * 72)
    print(f"  fix_birds_card_placement.py \u2014 {mode}")
    print("=" * 72)
    print()
    print("Plan:")
    print("  [+] Remove Birds card from current (misplaced) location")
    print("  [+] Re-insert Birds card immediately after Dock Day card's </div>")
    print()
    print("-" * 72)
    print("Diff:")
    print("-" * 72)
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        modified.splitlines(keepends=True),
        fromfile="index.html (before)",
        tofile="index.html (after)",
        n=3
    )
    print("".join(diff))
    print()

    if not apply_mode:
        print("=" * 72)
        print("  Dry-run complete. Re-run with --apply to write.")
        print("=" * 72)
        sys.exit(0)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = INDEX_HTML.with_suffix(INDEX_HTML.suffix + f".bak.{ts}")
    shutil.copy2(INDEX_HTML, bak)
    INDEX_HTML.write_text(modified, encoding="utf-8")

    print("=" * 72)
    print("  Applied.")
    print("=" * 72)
    print(f"  wrote:  {INDEX_HTML}")
    print(f"  backup: {bak}")
    print()
    print("Next steps:")
    print("  1. python3 build.py")
    print("  2. Reload the PWA, check Hyperlocal tab \u2014 Birds should be half-width")
    print("     next to Dock Day, with normal grid gap spacing above it.")
    print("  3. If good: git add -A && git commit -m 'v4.79: fix Birds card placement'")


if __name__ == "__main__":
    main()
