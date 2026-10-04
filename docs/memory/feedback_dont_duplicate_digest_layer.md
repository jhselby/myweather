---
name: feedback-dont-duplicate-digest-layer
description: "Don't build debug-page UI that duplicates what the daily digest already surfaces. The plan file is a strategic short-list (~5 long-arc items); the ~124 daily diagnostics + sentries + post-ship watches are the tactical layer that the digest already reports. New surfaces on the debug page must earn their space by showing something the digest can't."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a8a69f06-666f-4488-b366-dc669629e691
  modified: 2026-08-10T21:28:05.027Z
---

# Don't build debug-page UI that duplicates the digest layer

Before adding a new block to `corrections_debug.html`, ask: does the daily digest already surface this same information? If yes, don't build it — you're duplicating a layer Joe already reads.

**Why:** Discovered 08-10 PM after I built a "Standing plan tickler" block at the top of Current state. It showed 1 open plan item (item #3, cl root-cause fix) padded with 4 historical rows. Joe: "I don't see the point." Correct read — the plan file is deliberately strategic (5 long-arc items) while the ~124 daily diagnostics + sentries + post-ship watches carry the tactical load, all summarized in the digest. The tickler mirrored what the digest already tells him at 06:30 every morning. Screen space that didn't earn its keep. Removed same turn.

**How to apply:**
- Two distinct layers exist:
  - **Strategic layer** — `project_plan_pipeline_to_good.md`. Small (~5 items), long-arc, curated by hand. Rarely changes day-to-day.
  - **Tactical layer** — ~124 daily diagnostics, sentries (regression / layer-shape / field-skip), post-ship watches, verdict tracking. Managed by the digest and the existing debug-page sections.
- New debug-page surfaces must show something these layers *don't* — e.g., v0.6.401d's staleness audit flags temporal drift (past-due close dates) that neither layer catches on its own; the countdown-clock enhancements make "CLOSES TODAY / OVERDUE" visible without mental date-math.
- If a proposed block just re-displays a single row Joe already sees in the digest, cut it.
- Corollary: don't confuse the strategic plan (small, curated) with the tactical work (large, automated). "The plan is thin" is not a warning — a drained plan means the strategic priorities got executed. Do not build UI alerts around plan size.

Related: [[project_plan_pipeline_to_good]], [[feedback_debug_page_canon]], [[feedback_narrative_prose_auto_populate]].
