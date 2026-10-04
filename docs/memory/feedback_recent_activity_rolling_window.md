---
name: recent-activity-rolling-window
description: "The \"Recent activity\" block on corrections_debug.html is a rolling 3-day window (today + 2 prior days), not a full changelog. Older entries get trimmed on next curation; full history lives in docs/CHANGELOG.md."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 20ea0996-7e2b-434e-a249-5e0a5fcdc5fc
---

The "Recent activity" block (formerly "Since last curation") at the top of the Engineering updates section on `corrections_debug.html` is NOT a full changelog. It is a **rolling 3-day window** meant for a reader who checks the page daily or most days.

**Retention rules:**
- Keep: today + 2 prior calendar days of ship entries.
- On each curation, drop any date bullets older than the 3-day window.
- Living-reference blocks are exempt: "Live-layer change gate — rule of the road" and "Still open watches" stay across curations until they no longer apply.

**Why:** Full history was letting the block grow forever — v0.6.263 (2026-06-30) was still there on 2026-07-04. That defeats the purpose of a daily read: the reader can't tell what's new. The full changelog already lives in `docs/CHANGELOG.md`; the debug page block is for orientation, not archaeology.

**How to apply:**
- When adding a new day's entry, check whether the oldest date bullet is now older than "today − 2 days." If yes, drop it. Move the content to `docs/CHANGELOG.md` if it isn't already there.
- Consolidate same-day version bumps into one bullet when the changes are related; don't emit a bullet per micro-version.
- Codified 2026-07-04 after Joe called out that the block was becoming a "fill changelog that keeps growing forever."

Related: [[feedback-debug-page-canon]] (the page IS the source of truth — but that doesn't mean it should be a landfill).
