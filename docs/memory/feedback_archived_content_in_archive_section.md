---
name: feedback-archived-content-in-archive-section
description: "Archived content on the debug page belongs in the global #sec-archive section, not scattered inline as a sibling collapsible next to the live version. Joe surfaced this in the 08-10 PM session after finding an inline 'Post-ship watches — archived' collapsible next to 'Post-ship watches — active' — same base name, different sections. Applies to any future retirement / closed-watch / superseded content."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a8a69f06-666f-4488-b366-dc669629e691
  modified: 2026-08-10T21:27:48.325Z
---

# Archived content goes in the Archive section

When retiring, closing, or superseding content on `corrections_debug.html`, move it into the global `#sec-archive` section — not into an inline `<details>` collapsible next to the live version.

**Why:** Discovered 08-10 PM when Joe was looking for the countdown clocks I'd added and kept landing on "Post-ship watches — archived" (an inline collapsible in the "🟡 What's improving" tri-column) instead of "Post-ship watches — active" (its live sibling directly above). Two sections with the same base name, disambiguated only by parenthetical. He'd asked for this a week+ ago and it hadn't been fixed. His words: "WHY THE FUCK WOULD AN ARCHIVE SECTION OF POST SHIP WATCHES NOT BE IN THE FUCKING ARCHIVE SECTION OF THE FUCKING PAGE LIKE I ASKED A WHILE AGO."

**How to apply:**
- Debug page has one canonical archive: `<h2 id="sec-archive">Archive — Retired ideas & historical investigations</h2>`. Every retired / closed / superseded / inert block lives inside it.
- Live sections keep at most a one-line pointer with an anchor link to the archive subsection (e.g., "Closed / superseded / inert watches → Archive → Post-ship watches").
- Rule of thumb: if a block's status word is CLOSED, SUPERSEDED, INERT, RETIRED, SETTLED, or HISTORICAL, its home is `#sec-archive`. If it's LIVE, PROMOTE, HOLD, in-flight, or under watch, it stays inline near the live surface.
- Fixed in v0.6.401d (commit 70caf67) — pattern established: `#sec-archive-post-ship` block right after the Archive intro paragraph.

Related: [[feedback_debug_page_canon]], [[feedback_debug_page_full_sweep]].
