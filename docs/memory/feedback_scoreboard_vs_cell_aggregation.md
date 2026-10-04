---
name: feedback-scoreboard-vs-cell-aggregation
description: "Two views can both label themselves \"7-day\" and still disagree — same window, different aggregation semantics. When adding a new metric view, spell out both."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3560e921-8599-49f3-83b5-575306c2083c
  modified: 2026-08-05T01:03:18.119Z
---

Two views on the debug page can both label themselves "7-day" and still show different numbers for the same field. Same window, different aggregation. If the reader assumes "same label = same math," they'll waste time hunting a nonexistent bug.

**Why:** 08-04 evening. Joe saw cl in scoreboard's "5 flat" bucket while the per-field snapshot 7d cell read +45.7% for the same field. Same 7-day window from the same pair log. Aggregation differed:

- **Scoreboard** (`tsDoc.per_layer_mae_by_lead`): per-lead MAE bins, `_prodArr` prefers `layers.production` where per-lead n ≥ 30, else falls back to `_prodKey(f)` approximation (which for `_FIELD_SKIP` cl reduces to raw). Then arithmetic mean across leads 1-47.
- **Per-field snapshot 7d cell** (`mot.last_7d`): n-weighted pool of raw pair-log errors keyed on `applied_layer` stamp. No per-lead floor.

Under active poison + `_FIELD_SKIP`, the two paths diverge from ~0% (scoreboard) to +45.7% (cell). Both are honest against their own definitions.

**How to apply:**
- When you build a new metric view — a tile, a cell, an audit label — write down its aggregation in code near where it renders, and make sure the debug page can trace it (source, window, method) per `[[feedback_metric_provenance_labels]]`.
- If a new view claims the same window as an existing one, either share the numeric source or document the divergence *at the render site*, not in a session log.
- Aggregation gotchas to watch: per-bucket floors with silent fallback, arithmetic vs n-weighted means, per-lead-then-average vs pool-then-average.
- Do not "fix" a divergence by making one view look like the other unless you understand which is honest — the scoreboard's `_prodKey` approximation silently reads `_FIELD_SKIP` fields as flat, which hides real damage; that's the drift, not the pool.

Related: `[[feedback_metric_provenance_labels]]`, `[[project_metric_provenance_v0391]]`, `[[project_08_04_session]]`.
