---
name: feedback-debug-page-full-sweep
description: "When Joe asks for a debug-page sweep OR asks to update the debug page for work done, that always means \"bring the debug page COMPLETELY up to date.\" If you don't think a full sweep is a good idea right now, say so — but if you do it, do it right, not half-assed."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d49c29ee-d186-4c2d-9b3a-2ab60600aff6
  modified: 2026-08-04T14:52:25.410Z
---

# Rule

The debug page (`corrections_debug.html`) IS the project. It's the only surface Joe uses to see the state of the system. It cannot be left stale at the end of a session.

When Joe asks any of these — they all mean the same thing: **bring the entire debug page up to date**:
- "sweep the debug page"
- "sweep for staleness"
- "update the debug page for the work we've done"
- "debug page sweep"

Full sweep means, at minimum:
- Today's date on the "today" tile
- Recent Activity: today's ships added, missing prior-day entries filled, older-than-3-days entries trimmed to `docs/CHANGELOG.md`
- Layer status text (per-field row descriptions, post-ship watches, Ccd/Lsr/dpbp/wg-L3 blurbs) updated for every ship + gate movement in the session
- Calendar entries: past ones marked complete, upcoming ones adjusted
- Any references to superseded numbers, dates, or version strings cleaned up
- Version bump + `python3 build.py` + changelog entry
- Push

If, at any specific time, you don't think a full sweep is the right move (e.g., ships are mid-verify, more work coming that will re-touch the same text), **say so explicitly**. Half-assed is worse than not doing it. Never do a partial sweep and call it done.

## Why

08-04 session: Joe made this explicit after I did a sweep that left several layer-status blocks stale and stopped short of consolidating all of today's work.

Prior sessions had the same failure mode. Rule 5 sweeps have historically been "manual" per `[[feedback_debug_page_canon]]`; that memory says the debug page IS truth. This memory codifies the sweep discipline that follows: complete or don't start.

## How to apply

- On any sweep request, treat it as the standing-plan checklist above. Work through every item.
- If any item can't be completed cleanly (e.g., a ship is mid-flight and its status will change tomorrow), leave the current text but add an inline `[as of {date}]` marker so the reader knows it's stale-tolerated, not stale-forgotten.
- Version bump + build.py + push are part of the sweep, not a separate step to be done later.
- If time-limited and full sweep isn't possible, tell Joe upfront which parts you're skipping and why, before doing partial work.

Related: [[feedback_debug_page_canon]], [[feedback_recent_activity_rolling_window]], [[feedback_curated_json_daily_drift]], [[feedback_build_workflow]].
