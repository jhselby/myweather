---
name: local-json-stale-vs-live-page
description: Never interpret a live-scoreboard reading against local analysis/output/*.json — those are frozen at last script run and go stale within hours of any ship. The debug page reads live GCS snapshots.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 22b868ee-caeb-49df-87e2-e054ece110d1
  modified: 2026-09-12T10:10:10.523Z
---

If Joe pastes a scoreboard number from the debug page, do not cross-check it against `analysis/output/*.json` on disk without first reading the file's `generated_at` and confirming it's fresher than the ship history (git log since that timestamp).

**Why:** 09-12 session — Joe pasted 24h Selector Skill VC scoreboard readings. I opened `analysis/output/per_field_scoring.json` and saw completely different numbers. Concluded the scoreboard was stale. Wrong: the JSON was generated 09-10 10:12Z, and 09-11 shipped 9 things (including the escalation clause that wired h/calm/24-47 and ws/sea_breeze/24-47). The **local JSON was 2 days behind the live page**, not the other way around.

**How to apply:**
- Live-scoreboard number pasted → trust it, or ask Joe to hard-refresh, or read the live GCS artifact directly. Do not open local analysis JSON as a cross-check unless you first verify it's post-latest-ship.
- If you must use a local analysis JSON: check its `generated_at`, then `git log --since=<that_ts>` to see if anything shipped since. If yes, the JSON is stale relative to what the page shows.
- The debug page reads per-field snapshots via GCS. Any per_field_scoring script run against local data is a point-in-time artifact that decays fast.

Related: [[feedback_analysis_tools_drift_from_runtime]] — analysis scripts drift from processor overrides. This is the sibling case: local script *output* drifting from live snapshot.
