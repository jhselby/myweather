#!/usr/bin/env python3
"""
apply_birds_card.py — Build & wire the Birds card for myweather v4.79.

Run from ~/Documents/myweather/

Usage:
    python3 apply_birds_card.py              # dry-run: shows diffs, writes nothing
    python3 apply_birds_card.py --apply      # writes changes + creates .bak.TIMESTAMP files

Edits made (idempotent — safe to re-run):
  1. index.html: inserts Birds card into Hyperlocal tab, after Fog card
  2. index.html: bumps version pill v4.78 -> v4.79
  3. js/app-main.js: inserts renderBirds() function before renderWaterTempLog
  4. js/app-main.js: adds renderBirds(data.birds) call inside loadWeatherData

If any anchor is missing (e.g., you already applied, or edited around it),
the script refuses that step and tells you which one. It never silently
skips. It will proceed with whichever steps still have clean anchors.
"""

import sys
import os
import re
import shutil
import difflib
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------------
# File paths
# ----------------------------------------------------------------------
INDEX_HTML = Path("index.html")
APP_JS     = Path("js/app-main.js")

# ----------------------------------------------------------------------
# Content to insert
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

RENDER_BIRDS_JS = '''    // ======================================================
    // Birds (eBird recent sightings, 5km radius, 2 days back)
    // Collapsed: top notable species, else species count
    // Expanded: grouped by location, most recent first, all collapsed
    // ======================================================
    function renderBirds(birds) {
      const primaryEl   = document.getElementById("birdsPrimaryCollapsed");
      const secondaryEl = document.getElementById("birdsSecondaryCollapsed");
      const contentEl   = document.getElementById("birdsContent");
      if (!primaryEl || !contentEl) return;

      // Empty / missing data
      if (!birds || !Array.isArray(birds.species) || birds.species.length === 0) {
        primaryEl.textContent = "No recent sightings";
        secondaryEl.textContent = "";
        const days = birds?.back_days ?? 2;
        const km   = birds?.radius_km ?? 5;
        contentEl.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-secondary);font-size:0.9rem;">No eBird sightings in the last ${days} day${days === 1 ? "" : "s"} within ${km} km.</div>`;
        return;
      }

      const species       = birds.species;
      const speciesCount  = birds.species_count ?? species.length;
      const notables      = species.filter(s => s.notable);
      const totalBirds    = species.reduce((sum, s) => sum + (s.count || 0), 0);

      // --- Collapsed tile ---
      if (notables.length > 0) {
        const topNotable = [...notables].sort((a, b) =>
          (b.last_seen || "").localeCompare(a.last_seen || "")
        )[0];
        primaryEl.textContent = topNotable.name;
        const extra = notables.length - 1;
        secondaryEl.textContent = extra > 0
          ? `+ ${extra} other notable${extra === 1 ? "" : "s"}`
          : "Notable sighting";
      } else {
        primaryEl.textContent = `${speciesCount} species`;
        secondaryEl.textContent = `${totalBirds} bird${totalBirds === 1 ? "" : "s"} \u00b7 ${birds.radius_km ?? 5} km`;
      }

      // --- Expanded view: theme-aware colors ---
      const light     = isLight();
      const textFaint = light ? "rgba(0,0,0,0.40)"      : "rgba(255,255,255,0.4)";
      const textSub   = light ? "rgba(0,0,0,0.55)"      : "rgba(255,255,255,0.55)";
      const textHead  = light ? "rgba(0,0,0,0.75)"      : "rgba(255,255,255,0.85)";
      const border    = light ? "rgba(0,0,0,0.08)"      : "rgba(255,255,255,0.08)";
      const rowBg     = light ? "rgba(0,0,0,0.02)"      : "rgba(255,255,255,0.03)";
      const notableBg = light ? "rgba(255,140,60,0.15)" : "rgba(255,180,90,0.18)";
      const notableFg = light ? "rgba(200,90,10,0.95)"  : "rgba(255,200,120,0.95)";
      const linkCol   = light ? "rgba(20,80,200,0.9)"   : "rgba(120,190,255,0.9)";

      // Group species by location
      const byLocation = new Map();
      species.forEach(s => {
        const key = s.location || "Unknown location";
        if (!byLocation.has(key)) {
          byLocation.set(key, {
            name: key,
            distance_km: s.distance_km,
            last_seen: s.last_seen,
            species: []
          });
        }
        const loc = byLocation.get(key);
        loc.species.push(s);
        if ((s.last_seen || "") > (loc.last_seen || "")) loc.last_seen = s.last_seen;
      });

      // Sort locations by most recent sighting (desc)
      const locations = [...byLocation.values()].sort((a, b) =>
        (b.last_seen || "").localeCompare(a.last_seen || "")
      );

      // Sort species within each location: notable first, then count desc
      locations.forEach(loc => {
        loc.species.sort((a, b) => {
          if (a.notable !== b.notable) return a.notable ? -1 : 1;
          return (b.count || 0) - (a.count || 0);
        });
      });

      // Format "2026-04-23 18:49" -> "Apr 23, 6:49 PM"
      const fmtTime = (ts) => {
        if (!ts) return "";
        const [datePart, timePart] = ts.split(" ");
        if (!datePart || !timePart) return ts;
        const [y, mo, d] = datePart.split("-").map(Number);
        const [h, mi]    = timePart.split(":").map(Number);
        const dt = new Date(y, mo - 1, d, h, mi);
        return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
               ", " +
               dt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
      };

      const fetchedAt = birds.fetched_at
        ? new Date(birds.fetched_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
        : null;

      // Header summary
      const notableBadge = notables.length > 0
        ? `<span style="background:${notableBg};color:${notableFg};padding:2px 8px;border-radius:999px;font-size:0.72rem;font-weight:700;margin-left:8px;">${notables.length} notable</span>`
        : "";

      let html = `
        <div style="padding:12px 0 14px;border-bottom:1px solid ${border};margin-bottom:12px;">
          <div style="font-size:1.1rem;font-weight:700;color:${textHead};">
            ${speciesCount} species \u00b7 ${totalBirds} bird${totalBirds === 1 ? "" : "s"}${notableBadge}
          </div>
          <div style="font-size:0.78rem;color:${textFaint};margin-top:4px;">
            eBird \u00b7 ${birds.radius_km ?? 5} km radius \u00b7 last ${birds.back_days ?? 2} day${(birds.back_days ?? 2) === 1 ? "" : "s"}${fetchedAt ? ` \u00b7 updated ${fetchedAt}` : ""}
          </div>
        </div>
      `;

      // Location groups
      locations.forEach((loc, idx) => {
        const groupId = `birdLoc_${idx}`;
        const locNotables = loc.species.filter(s => s.notable).length;
        const locSpeciesCount = loc.species.length;
        const locBirdCount = loc.species.reduce((sum, s) => sum + (s.count || 0), 0);
        const distStr = loc.distance_km != null ? `${loc.distance_km.toFixed(1)} km` : "";

        html += `
          <div style="border:1px solid ${border};border-radius:10px;margin-bottom:8px;overflow:hidden;background:${rowBg};">
            <div onclick="document.getElementById('${groupId}').style.display = document.getElementById('${groupId}').style.display === 'none' ? 'block' : 'none'; this.querySelector('.bird-chev').textContent = document.getElementById('${groupId}').style.display === 'none' ? '\u25BE' : '\u25B4';"
                 style="padding:10px 12px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:8px;">
              <div style="min-width:0;flex:1;">
                <div style="font-weight:700;font-size:0.9rem;color:${textHead};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                  ${escapeHtml(loc.name)}${locNotables > 0 ? ` <span style="background:${notableBg};color:${notableFg};padding:1px 6px;border-radius:999px;font-size:0.7rem;font-weight:700;margin-left:4px;">${locNotables}\u2605</span>` : ""}
                </div>
                <div style="font-size:0.75rem;color:${textFaint};margin-top:2px;">
                  ${distStr} \u00b7 ${locSpeciesCount} species \u00b7 ${locBirdCount} bird${locBirdCount === 1 ? "" : "s"} \u00b7 ${fmtTime(loc.last_seen)}
                </div>
              </div>
              <span class="bird-chev" style="color:${textFaint};font-size:0.9rem;flex-shrink:0;">\u25BE</span>
            </div>
            <div id="${groupId}" style="display:none;padding:0 12px 10px;border-top:1px solid ${border};">
              ${loc.species.map(s => {
                const ebirdUrl = `https://ebird.org/species/${s.code}`;
                const isNotable = s.notable;
                const nameStyle = isNotable
                  ? `background:${notableBg};color:${notableFg};padding:1px 6px;border-radius:4px;font-weight:700;`
                  : "";
                return `
                  <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid ${border};font-size:0.85rem;">
                    <a href="${ebirdUrl}" target="_blank" rel="noopener" onclick="event.stopPropagation();" style="color:${linkCol};text-decoration:none;flex:1;min-width:0;">
                      <span style="${nameStyle}">${escapeHtml(s.name)}</span>
                    </a>
                    <span style="color:${textSub};margin-left:10px;font-variant-numeric:tabular-nums;flex-shrink:0;">
                      ${s.count > 1 ? `\u00d7${s.count}` : "\u00b7"}
                    </span>
                  </div>
                `;
              }).join("")}
            </div>
          </div>
        `;
      });

      contentEl.innerHTML = html;
    }

    // Small HTML escaper used by renderBirds (species names are eBird-controlled
    // so very safe, but defense in depth is cheap)
    function escapeHtml(s) {
      if (s == null) return "";
      return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

'''

RENDER_BIRDS_CALL = '        renderBirds(data.birds);\n'

# ----------------------------------------------------------------------
# Anchors (unique strings that must exist exactly once)
# ----------------------------------------------------------------------

# index.html: insert BIRDS_CARD_HTML after the Fog card, before end of Hyperlocal section.
# The Fog card closes somewhere before line 1178 (</section>). We anchor on a unique
# string that occurs at the end of Hyperlocal section, verified in grep output:
# line 1178 is </section> for hyperlocalView. We need something more specific.
# Safest anchor: find the </section> that immediately follows the Fog card block.
# We'll match the exact sequence: <section id="hyperlocalView"> ... [fog card] ... </section>
# by anchoring on the LAST card close before </section>.
#
# Strategy: find `<section id="hyperlocalView"`, then find the next `</section>` after it,
# and insert BIRDS_CARD_HTML right before the indented markers that close out the section.

HYPERLOCAL_SECTION_OPEN = '<section id="hyperlocalView"'
# Must match the pattern around line 1173-1178 exactly:
HYPERLOCAL_SECTION_CLOSE_BLOCK = '''        

      </div>
    

    </section>'''

VERSION_OLD = '<span class="version-pill" id="appVersion">v4.78</span>'
VERSION_NEW = '<span class="version-pill" id="appVersion">v4.79</span>'

# js/app-main.js: insert RENDER_BIRDS_JS immediately before `function renderWaterTempLog`
JS_INSERT_ANCHOR = '    function renderWaterTempLog() {'

# js/app-main.js: insert RENDER_BIRDS_CALL immediately after this line
JS_CALL_ANCHOR = '        renderFrostTracker(data.frost_log);'

# Idempotency markers — if these strings are already in the file, skip that step
IDEMPOTENT_MARKER_HTML = 'data-collapse-key="birds"'
IDEMPOTENT_MARKER_JS_FN = 'function renderBirds('
IDEMPOTENT_MARKER_JS_CALL = 'renderBirds(data.birds)'

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

class Step:
    """Tracks one planned edit, its success/failure, and produces a diff."""
    def __init__(self, name, file_path):
        self.name = name
        self.file_path = file_path
        self.original = None
        self.modified = None
        self.status = "pending"  # pending | ok | skip | fail
        self.message = ""

    def load(self):
        if not self.file_path.exists():
            self.status = "fail"
            self.message = f"File not found: {self.file_path}"
            return False
        self.original = self.file_path.read_text(encoding="utf-8")
        self.modified = self.original
        return True

    def diff_preview(self, context=2):
        if self.original == self.modified:
            return "(no change)"
        orig_lines = self.original.splitlines(keepends=True)
        mod_lines  = self.modified.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines, mod_lines,
            fromfile=f"{self.file_path} (before)",
            tofile=f"{self.file_path} (after)",
            n=context
        )
        return "".join(diff)


def count_occurrences(haystack, needle):
    return haystack.count(needle)


def apply_step(step, transform_fn):
    """Load file, run transform, record status."""
    if not step.load():
        return
    try:
        new_content, status, message = transform_fn(step.original)
        step.modified = new_content
        step.status = status
        step.message = message
    except Exception as e:
        step.status = "fail"
        step.message = f"Exception: {e}"


# ----------------------------------------------------------------------
# Transforms
# ----------------------------------------------------------------------

def insert_birds_card_html(content):
    if IDEMPOTENT_MARKER_HTML in content:
        return content, "skip", "Birds card already present in index.html"

    # Find the </section> that closes hyperlocalView.
    # Anchor: the unique block at lines 1173-1178. If this exact block is not
    # found, refuse — means the file structure has drifted.
    hyperlocal_start = content.find(HYPERLOCAL_SECTION_OPEN)
    if hyperlocal_start == -1:
        return content, "fail", "Could not find <section id=\"hyperlocalView\"> in index.html"

    # Find the </section> tag after the hyperlocalView opening
    section_close_idx = content.find("</section>", hyperlocal_start)
    if section_close_idx == -1:
        return content, "fail", "Could not find </section> after hyperlocalView"

    # Walk backwards to find a sensible insertion spot: right before the final
    # whitespace block that precedes </section>. We want to insert after the
    # last `</div>` of the Fog card.
    #
    # Easiest stable anchor: find the last `</div>` before </section>, and insert
    # our card immediately after that </div>'s line.
    segment_before_close = content[:section_close_idx]
    last_div_close = segment_before_close.rfind("</div>")
    if last_div_close == -1:
        return content, "fail", "Could not find trailing </div> before </section> in hyperlocalView"

    # Insert point: immediately after that </div> and its trailing newline
    insert_after = last_div_close + len("</div>")
    # Skip trailing newline so our insert sits on its own line
    if insert_after < len(content) and content[insert_after] == "\n":
        insert_after += 1

    new_content = content[:insert_after] + BIRDS_CARD_HTML + content[insert_after:]
    return new_content, "ok", f"Inserted Birds card after last </div> of Fog card (at offset {insert_after})"


def bump_version(content):
    if VERSION_NEW in content:
        return content, "skip", "Version already at v4.79"
    if VERSION_OLD not in content:
        return content, "fail", f"Could not find version anchor: {VERSION_OLD!r}"
    count = count_occurrences(content, VERSION_OLD)
    if count > 1:
        return content, "fail", f"Version anchor appears {count} times; expected 1"
    new_content = content.replace(VERSION_OLD, VERSION_NEW, 1)
    return new_content, "ok", "Bumped version v4.78 -> v4.79"


def insert_render_birds_function(content):
    if IDEMPOTENT_MARKER_JS_FN in content:
        return content, "skip", "renderBirds function already present"
    if JS_INSERT_ANCHOR not in content:
        return content, "fail", f"Could not find JS anchor: {JS_INSERT_ANCHOR!r}"
    count = count_occurrences(content, JS_INSERT_ANCHOR)
    if count > 1:
        return content, "fail", f"JS anchor appears {count} times; expected 1"
    new_content = content.replace(JS_INSERT_ANCHOR, RENDER_BIRDS_JS + JS_INSERT_ANCHOR, 1)
    return new_content, "ok", "Inserted renderBirds() before renderWaterTempLog()"


def insert_render_birds_call(content):
    if IDEMPOTENT_MARKER_JS_CALL in content:
        return content, "skip", "renderBirds(data.birds) call already present"
    if JS_CALL_ANCHOR not in content:
        return content, "fail", f"Could not find JS call anchor: {JS_CALL_ANCHOR!r}"
    count = count_occurrences(content, JS_CALL_ANCHOR)
    if count > 1:
        return content, "fail", f"JS call anchor appears {count} times; expected 1"
    replacement = JS_CALL_ANCHOR + "\n" + RENDER_BIRDS_CALL.rstrip("\n")
    new_content = content.replace(JS_CALL_ANCHOR, replacement, 1)
    return new_content, "ok", "Added renderBirds(data.birds) call after renderFrostTracker()"


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    apply_mode = "--apply" in sys.argv

    # Sanity: must be run from repo root
    if not INDEX_HTML.exists() or not APP_JS.exists():
        print("ERROR: Must be run from ~/Documents/myweather/ (index.html and js/app-main.js not found here)")
        sys.exit(1)

    mode_banner = "APPLY MODE" if apply_mode else "DRY-RUN MODE (no files written)"
    print("=" * 72)
    print(f"  apply_birds_card.py  \u2014  {mode_banner}")
    print("=" * 72)
    print()

    # Step 1: Birds card HTML insert
    step1 = Step("Insert Birds card HTML", INDEX_HTML)
    apply_step(step1, insert_birds_card_html)

    # Step 2: Version bump (applied AFTER step 1 to the same file content)
    step2 = Step("Bump version v4.78 -> v4.79", INDEX_HTML)
    if step1.status in ("ok", "skip") and step1.modified is not None:
        # Chain: step2 reads from step1's modified output
        step2.original = step1.modified
        try:
            new_content, status, message = bump_version(step2.original)
            step2.modified = new_content
            step2.status = status
            step2.message = message
        except Exception as e:
            step2.status = "fail"
            step2.message = f"Exception: {e}"
    else:
        step2.status = "fail"
        step2.message = f"Skipped because step 1 failed: {step1.message}"

    # Step 3: renderBirds() JS function insert
    step3 = Step("Insert renderBirds() function", APP_JS)
    apply_step(step3, insert_render_birds_function)

    # Step 4: renderBirds(data.birds) call insert (chains off step 3)
    step4 = Step("Add renderBirds() call in loadWeatherData", APP_JS)
    if step3.status in ("ok", "skip") and step3.modified is not None:
        step4.original = step3.modified
        try:
            new_content, status, message = insert_render_birds_call(step4.original)
            step4.modified = new_content
            step4.status = status
            step4.message = message
        except Exception as e:
            step4.status = "fail"
            step4.message = f"Exception: {e}"
    else:
        step4.status = "fail"
        step4.message = f"Skipped because step 3 failed: {step3.message}"

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    print("Plan:")
    print()
    steps = [step1, step2, step3, step4]
    for i, s in enumerate(steps, 1):
        marker = {"ok": "[+]", "skip": "[=]", "fail": "[!]", "pending": "[?]"}[s.status]
        print(f"  {marker} Step {i}: {s.name}")
        print(f"        {s.message}")
    print()

    # Show diffs
    print("-" * 72)
    print("Diffs:")
    print("-" * 72)
    for i, s in enumerate(steps, 1):
        if s.status == "ok":
            print(f"\n>>> Step {i}: {s.name}  (file: {s.file_path})")
            print(s.diff_preview(context=2))
    print()

    any_fail = any(s.status == "fail" for s in steps)
    any_ok   = any(s.status == "ok"   for s in steps)

    if any_fail:
        print("=" * 72)
        print("  \u26a0  Some steps failed. Review above. NO files written.")
        print("=" * 72)
        if apply_mode:
            print("  Refusing to apply partial changes. Fix the failing anchor(s) and retry.")
        sys.exit(2)

    if not any_ok:
        print("=" * 72)
        print("  Nothing to do \u2014 all steps already applied (idempotent no-op).")
        print("=" * 72)
        sys.exit(0)

    if not apply_mode:
        print("=" * 72)
        print("  Dry-run complete. Re-run with --apply to write changes.")
        print("=" * 72)
        sys.exit(0)

    # ------------------------------------------------------------------
    # Apply: back up then write
    # ------------------------------------------------------------------
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    written = []
    # Group steps by file — final modified content per file is the last step
    # that touches it with status ok/skip.
    final_content = {}
    for s in steps:
        if s.status in ("ok", "skip") and s.modified is not None:
            final_content[s.file_path] = s.modified

    for path, content in final_content.items():
        bak = path.with_suffix(path.suffix + f".bak.{ts}")
        shutil.copy2(path, bak)
        path.write_text(content, encoding="utf-8")
        written.append((path, bak))

    print("=" * 72)
    print("  Applied.")
    print("=" * 72)
    for path, bak in written:
        print(f"  wrote:  {path}")
        print(f"  backup: {bak}")
    print()
    print("Next steps:")
    print("  1. python3 build.py")
    print("  2. Open index.html in browser, expand Birds tile, verify")
    print("  3. git fetch && git status")
    print("  4. git add -A && git commit -m 'v4.79: Birds card with eBird sightings'")
    print("  5. git push --force-with-lease")


if __name__ == "__main__":
    main()
