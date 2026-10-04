---
name: feedback-metric-provenance-labels
description: "Every user-visible metric on the debug page must trace to (source file, window, aggregation method, refresh timestamp). Two same-named metrics with different values is worse than one arguable metric. Hand-typed prose that quotes numbers goes stale — either wire live or stamp as historical."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d49c29ee-d186-4c2d-9b3a-2ab60600aff6
  modified: 2026-08-04T14:52:52.061Z
---

# Rule

Every displayed % or state assertion on the debug page must be one of:

1. **Live-sourced from a named canonical source.** The audit label under the section names the file, window, aggregation method, and refresh time. Two cells in the same row must come from the same source and same aggregation method.
2. **Explicitly stamped as historical** with an `[as of YYYY-MM-DD]` marker if it's prose that quotes numbers.

Never a third option: hand-typed prose quoting current-state numbers without a stamp. That prose goes stale silently and the reader can't tell.

**Same-name-different-value is the worst failure mode.** If two "7-day" numbers appear on the page from different cuts, a reader making a ship decision doesn't know which to trust. Unify to one canonical cut, or rename the cuts so they're clearly different.

## Why

08-04 session: external review flagged that the top per-field table showed h −0.2% and ws +0.7% ("7-day") while the narrative below claimed h +2.8% and ws +5.2% ("7-day"). Both correct for their own definition — top table was `tsDoc.per_layer_mae_by_lead` (unweighted mean of lead-1-47 MAEs), narrative was hand-typed from a past sweep. Same window, different aggregation, different value. Reader can't tell.

Underlying class is the same as this week's silent-lie metric bugs (v0.6.390j applied_layer poison, v0.6.390o cl backfill, v0.6.390p wd L1_ONLY trap, v0.6.390y h_persistence_skill top-level forecast). All four cases: a displayed metric was computed from the wrong source and no label caught it.

## How to apply

- When adding any new metric display: also add its audit label (source, window, method, refresh time). Not optional.
- When two metrics with the same label appear in the same visual context (row, tile, section): they must share the same source and aggregation method. If they can't, rename the labels to name the difference.
- Prefer server-emit `analysis/mae_over_time.py`-shaped canonical blocks (`last_24h`, `last_7d`) over client-side re-aggregation of the same underlying data — the emit block is single-authored and testable.
- When killing a hand-typed narrative that quotes numbers: replace with either an auto-populated container (JS reads from the same source that populates nearby live cells) or a prose block with `[as of {date}]` stamp.
- Add coverage tests for metric-plumbing gaps as they surface. See `[[tests/test_prod_key_coverage.py]]` and `[[tests/test_layer_tuple_sanity.py]]` for the pattern.

Related: [[feedback_debug_page_canon]], [[feedback_top_level_forecast_is_l2]], [[feedback_shadow_write_applied_layer_trap]], [[feedback_l1_only_field_routing_trap]], [[project_metric_provenance_v0391]].
