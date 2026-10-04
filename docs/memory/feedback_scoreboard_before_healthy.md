---
name: scoreboard-before-healthy
description: "Never declare a field 'healthy' or use positive framing without first cross-checking the debug-page scoreboard (BIGGEST FIELD REGRESSION / WORST CELL tiles). Persistence-skill ADDS VALUE is not sufficient — those tiles are Prod-vs-Raw, the yardstick that actually matters."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 73429c93-7451-4383-be7a-18cb78ea6325
  modified: 2026-07-29T16:48:58.401Z
---

# Consult scoreboard-canon BEFORE calling a field 'healthy'

**Rule:** When Joe asks "how is field X doing?" and I'm about to give a positive framing, **first** check the debug-page scoreboard's `BIGGEST FIELD REGRESSION` and `WORST CELL (FIELD@BAND)` tiles. If the field appears in either, it is NOT "healthy" — no matter what persistence-skill says. Persistence is a weak baseline (especially for wind fields where MAE_pers is 70-100°); Prod-vs-Raw is what actually measures value.

**Why:** 2026-07-29 wd/ws double session. I gave clean diagnosis of wd (persistence-skill L4≈L1 forced me to look deeper → landed on v0.6.384 fossil-contamination story cleanly). Then Joe asked about ws. I saw persistence-skill said `ws = ADDS VALUE` (+0.29 pooled) and declared ws "healthy" — without checking the scoreboard, which had ws flagged as **BIGGEST FIELD REGRESSION (+15.9%)** and **WORST CELL (ws@6-11h +75%)**. Joe had to screenshot the scoreboard to correct me. Same v0.6.384 fossil story applied to both fields, but I ran the play for wd and skipped it for ws.

The failure mode: I stopped digging as soon as *one* positive metric was found. For wd there was no positive metric to stop on, so I dug and found the truth. For ws, persistence-skill said ADDS and I stopped there — inconsistent playbook across fields with the same underlying situation.

Directly duplicates [[feedback_debug_page_canon]] ("Debug page is canon"), but that rule apparently isn't loading when I'm framing a "how is X doing" answer. This memory adds a specific *pre-condition check* to any positive framing.

**How to apply:**

- Any "how is field X doing?" answer must begin with a scoreboard consult, not with persistence-skill or any single metric.
- If Prod-vs-Raw shows regression on the scoreboard, that IS the story. Persistence-skill "ADDS VALUE" alongside is context, not overriding.
- Cross-field consistency: if the same fix affected fields A and B (single shared constant, single shared processor), the diagnosis story should be the same across both fields. Don't run the fossil-contamination playbook for one and skip it for the other.
- When Joe pushes back with a screenshot of the actual dashboard, that's not a request for me to defend prior framing — that's evidence I skipped a step. Acknowledge and re-run.

Related: [[feedback_debug_page_canon]] (scoreboard is truth), [[feedback_scorecard_lag_vs_accuracy_chart]] (top-tile is 7-day rolling — factor into diagnosis), [[feedback_no_choice_menus]] (recommend directly — but only after checking the right sources first).
