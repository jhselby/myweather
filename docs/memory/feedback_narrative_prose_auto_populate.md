---
name: feedback-narrative-prose-auto-populate
description: Any hand-typed percentage or day counter in debug-page prose ages badly. Replace with an auto-populated span pointing at the same data source as the adjacent cell.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3560e921-8599-49f3-83b5-575306c2083c
  modified: 2026-08-05T01:03:34.931Z
---

Hand-typed percentages ("cl now green −1.1%") and hand-typed day counters ("day 5/14 through 08-11") in debug-page prose ARE a drift class. They stay static while the rolling window advances and the calendar ticks. Every "sweep the debug page" session then pays rent to update them.

**Why:** 08-04 session. Debug page had a narrative note "cl now green −1.1% over 7 days" written 08-02 after the applied_layer poison backfill; two days later the 7d cell read +45.7% because the rolling window had moved. Same session had ~7 "day X/Y" watch counters that needed manual bumping. Both were manual work that could be zero.

**How to apply:**

Two span patterns codified in `corrections_debug.html`:

1. **`<span class="pf-status" data-field="X">`** — auto-populates "X 7-day vs raw: ±YY.Y% (verdict)" from `mot.last_7d[X]` via the same PROD_PRIORITY walk as the pf-mae cell above the row. Use for status prefixes in narrative status-column prose. See `renderPerFieldSnapshot` populator.

2. **`<span class="watch-day" data-shipped="YYYY-MM-DD" data-window="N">`** — auto-fills "day X/N" (or "closed Nd watch (day X)" past the window). Use anywhere a post-ship watch counter appears in prose. See `renderWatchDayCounters`.

Rule: if you're about to type a percentage or a day counter into prose, ask whether the same number is already rendered from data somewhere on the page. If it is, use a span; if it isn't, write the fetch and use a span. Do NOT hand-type it and plan to sweep later.

Related: `[[feedback_metric_provenance_labels]]`, `[[feedback_curated_json_daily_drift]]`, `[[project_metric_provenance_v0391]]`, `[[project_08_04_session]]`.
