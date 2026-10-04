---
name: 07-24-session
description: Fri 07-24. 4 ships (v0.6.378/379/379a/379b). Registry-backfill class-case fix (C1h miss) + cl_persistence_gate Stage 3 wire (retires cl_persistence_short_lead — narrow shape hypothesis disproven). Two Fri 07-24 Calendar items silently skipped until Joe pointed at them → new feedback_day_scope_from_calendar rule.
metadata: 
  node_type: memory
  type: project
  originSessionId: ee219fc7-b19d-45bb-958f-2e0e51617443
  modified: 2026-07-25T01:03:24.761Z
---

# 2026-07-24 Session — 4 ships + 1 process lesson

## Ships

- **v0.6.378** — KNOWN_LIVE_PIPELINES registry backfill + h_cl_persistence_blend Stage 2 preview.
  Root cause: 07-23's v0.6.376 backstop was seeded with 1 entry (`h_l3_asymmetric_stage1` class case) and treated as finished. Every other live pipeline (C1h, C1d, chp, Lc) still emitted un-relabeled action verbs. This morning's triage misread the C1h `GATE CLEARED 15/7 · 13 SHIP cells today` stability tick as a ship recommendation for a pipeline live since 2026-07-10. Backfilled 4 entries + registered h_cl_persistence_blend + _stage2 at Stage 3 ship time same commit. New rule codified in [[project_already_live_backstops]]: register in same commit as ship.
  Stage 2 preview shipped `analysis/h_cl_persistence_blend_stage2.py`: 12 SHIP / 8 MARGIN / 16 SKIP / 1 THIN. Emits BOTH gate shapes for comparison: blacklist (17 rules) vs whitelist (16 rules). Whitelist wins and reads as coherent story (calm all-leads + se_flow all-leads + unknown all-leads + short-lead across most flow regimes). Frontal MARGIN cells excluded from whitelist because gate contract forces frontal→baseline, so gate_mae == base_mae by construction — definitional artifact not signal. Pattern reusable for future gate-shape scripts.

- **v0.6.379** — cl_persistence_gate Stage 3 wire + retire cl_persistence_short_lead.
  Wiring surfaced a schema mismatch: existing `cl_persistence_short_lead.py` read `cell.status` + `"0-5h"` bands; new Stage 2 preview writes `cell.verdict` + `"0-5"`. Both read the SAME `cl_persistence_gate_curated.json`. Old was ENABLED=False so no user-visible break, but contract had silently shifted. New feedback [[feedback_curated_json_schema_contract]]. Chose retire-and-replace (not coexist / rewrite-in-place): narrow shape hypothesis proven wrong by halves-verified Stage 2 (persistence wins beyond 0-5h in calm/se_flow/unknown all-leads + nw_flow 24-47h, LOSES at sea_breeze 0-5h). Deployed collector rev 00448; GCS tick 15:47Z verified new stamp with fires matching Stage 2 exactly (se_flow 5/0/12/24 across bands).

- **v0.6.379a** — Debug page + memory follow-through. Added "Day 1/7 today" counter to Stage 3 gated card. Updated Persistence-skill narrative (was still describing retired short-lead). Memory index refresh: [[project_cl_persistence_investigation]] RESOLVED, [[project_clp_regime_gate_opportunity]] SUPERSEDED.

- **v0.6.379b** — Debug page Fri 07-24 sweep. Removed 3 stale Calendar entries + 2 stale Upcoming decisions entries. Added Recent activity 07-24 today entry.

## Digest reads I did NOT act on until Joe pointed at Calendar

- **sr Lsb Stage 3 halves re-run** — VERDICT HOLD. Pooled +7.34%, halves (+24.1%, -1.6%) — halves diverged > ±5pp gate. Stays ENABLED=False. Would have missed if Joe hadn't pointed at Calendar.
- **h_ws_octant_bias re-read 2/3** — 4 REAL octants (NE +0.81, E +1.71, SW -0.80, W -0.92). Up from 07-17 2 REAL + 2 WATCH (NE + W promoted). Signal strengthening. Read #3 due 07-31.

Both scripts ran in the morning digest. I never read their verdicts against the decision criteria in the Calendar. New feedback [[feedback_day_scope_from_calendar]].

## Process lesson (this session's failure)

Two lenses required at session start:
1. Digest = tools that ran + auto-triage
2. Calendar (`corrections_debug.html` Calendar + Upcoming decisions blocks) = decisions Joe expected made today

Missing #2 silently skips scheduled work even when the underlying scripts DID run. The digest surfaces "what tools said"; the Calendar surfaces "what decisions were owed today." Both are load-bearing.

## Related

- [[project_already_live_backstops]] — updated with 07-24 registry backfill section.
- [[feedback_day_scope_from_calendar]] — new rule from this session.
- [[feedback_curated_json_schema_contract]] — new rule from cl_persistence_gate wire.
- [[project_cl_persistence_investigation]] — RESOLVED by v0.6.379.
- [[project_clp_regime_gate_opportunity]] — SUPERSEDED by v0.6.379.
