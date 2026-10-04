---
name: feedback-session-start-load-project-state
description: "At session start, load the actual project state before responding — not on-demand when a topic comes up. Read the pipeline-to-good plan, correction-stack architecture, most recent session log, and grep the fetchers directory for what data sources are actually pulled. Otherwise the session reads as \"acting new\" — Joe flagged this 2026-08-18 after multiple basics errors (didn't know Wyman Cove was the target location, didn't know NWS gridpoints were already fetched, framed regime-change as untried when it's central, misread an L4 comment)."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 23b5871a-fdee-47f7-9ac1-9e9135a084ab
  modified: 2026-08-18T13:53:49.862Z
---

At session start — before responding to whatever Joe pastes — load the actual project state. Not on-demand searches when a topic surfaces. Proactive load.

**Why:** every session starts fresh. MEMORY.md exists so this doesn't matter, but only if actually consumed. Skimming the index and pulling files reactively produces "acting new" behavior — asking for orientation instead of offering it, presenting known things as fresh insights, missing that a data source is already wired. Joe flagged this on 2026-08-18 after a session where I:
- Called the target location "KBVY" (it's Wyman Cove; KBVY is one of ~30 data sources)
- Proposed pulling NBM as a fresh data source (already fetched via NWS gridpoint API, just not used as a forecast input)
- Framed "regime-change detection" as the untried lever (it's a C1 axis and drives multiple persistence gates)
- Called L4 "regime × lead_band" from a SKIP-table comment (L4 is diurnal hour-of-day)

**How to apply — session-start checklist (before responding to the first substantive prompt):**

1. **Read `project_plan_pipeline_to_good.md`** — the ranked roadmap. Know which items are shipped/in-progress/deferred.
2. **Read `project_correction_stack.md`** — layer-by-layer with which fields run which layer today. Prevents architectural miscalls.
3. **Read the most-recent `project_MM_DD_session.md`** — what happened yesterday, what's still open, what the meta-finding was. Prevents repackaging yesterday's insights as fresh ones.
4. **`ls weather_collector/fetchers/`** — know what data sources are actually pulled. Prevents proposing to add sources that already exist.
5. **Scan `MEMORY.md` "Active watches / open work" section** — five to ten items are usually in-flight. Know their names before Joe references them.

Time cost of this load: ~3-5 tool calls, mostly parallel-safe. Saves multi-turn corrections from Joe when I speak from ignorance.

**How to apply — when about to make an architectural claim:**

Never quote a comment or a nearby line as evidence for how the system behaves. Quote the actual application code — the loop that runs, the lookup that fires, the file that gets written. Comments drift; skip-tables live next to lookup-tables; docstrings age. The L4 mistake was pattern-matching on comment context instead of reading the actual apply function.

**Related:**
- [[feedback_verify_writers_for_read_paths]] · [[feedback_verify_pipeline_ordering]] · [[feedback_stated_intent_vs_code_behavior]] · [[feedback_check_contamination_before_acting]]
- CLAUDE.md #4 "Don't Guess — Verify"
- [[feedback_co_owner_posture]] — "co-owner behavior would be raising meta-questions proactively, not waiting for Joe to catch me"
