---
name: feedback-self-refit-tables-run-in-cloud
description: "Joe's 10-07 rule: any runtime table meant to refit on its own must refit automatically in the cloud with guards; live behavior may never depend on the Mac digest running. Ship decisions stay in the repo."
metadata:
  node_type: memory
  type: feedback
  modified: 2026-10-07T18:00:00.000Z
---

**Rule:** If a live table is meant to track recent data, the cloud refitter owns it ([[project_cloud_refitter]]). The model must work if the Mac digest never runs again. If a table encodes a decision (skips, allowlists, demotions, frozen cell sets), it lives in the repo and changes only through a ship.

Joe, 10-07: "The run own their own stuff should actually run on its own. The model shouldn't need me to run the daily digest to work."

**Why:** Until 10-07 every "daily refit" table reached the collector only when the digest ran on the Mac AND someone deployed. The selector table had silently been deploy-gated ([[project_10_07_session]]), and the auto-curate wipes ([[feedback_auto_curate_wholesale_overwrite]]) came from the same digest-writes-runtime-JSON path.

**How to apply:**
- For any new live mechanism with a fitted table, decide in the ship whether it is self-refit or a ship decision. If self-refit, register it in `refitter/tables.py` and read it via `runtime_tables.get()` in the same ship.
- Churning Stage 1/2 cell sets count as ship decisions (Joe, 10-07): the tool writes a candidate, and a human promotes it.
- Never propose "the digest will pick it up" as the mechanism for a live change.
- Joe has authorized Claude to run deploys itself (10-07) — see [[feedback_edit_deploy_division_of_labor]].
