---
name: feedback-rd-sweep-on-verdict-change
description: "When a candidate script's verdict flips (MIXED → PROMOTE, PROMOTE → MARGINAL, KILL, ship-then-fail), sweep the Research & Diagnostics section of corrections_debug.html at the same time — not just the top-of-page counters. R&D drifts silently because it's outside the normal Rule 5 sweep surface."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 222946da-f295-4807-baf0-368c6663308b
  modified: 2026-07-27T13:00:59.522Z
---

When a candidate script's verdict flips (MIXED → PROMOTE, PROMOTE → MARGINAL, KILL, ship-then-fail), sweep the Research & Diagnostics section of `corrections_debug.html` at the same time as the top-of-page counters. Two places usually need updates: (1) the row in the "Correction candidates in flight" table (line ~1794+), and (2) any narrative bullet describing the candidate in the Backlog Group A/B/C sections above the table.

**Why:** The 2026-07-27 R&D sweep found `h_pre_front_orthogonality` still described as "MIXED, 2 orthogonal cells" from 07-04 — the 07-22 matched-regime fix v0.6.372b that flipped it to PROMOTE with 7 SHIP cells never propagated into R&D. Same drift on `h_ws_octant_bias`: table said "07-17 re-read 1 of 3, 2 REAL octants" when the 07-24 re-read 2 of 3 already showed 4 REAL octants (NE + W promoted from WATCH). R&D drifts silently because it sits below the top-of-page decision surface that [[feedback_debug_page_canon]]'s Rule 5 sweep hits after every ship. R&D isn't a decision surface — it's the *evidence* surface — so it doesn't fire the ship-time reflex, but staleness in evidence is worse than staleness in counters because a reader might make new decisions on the basis of an old verdict.

**How to apply:** Any digest triage that surfaces a verdict change (via "Changed verdicts" bucket OR the ship-eligible / candidates buckets) — grep the debug page for the script name (`h_pre_front_orthogonality`, `h_ws_octant_bias`, `h_dewpoint_depression`, etc.) and update both the table row and the Backlog narrative in the same pass. This is a sub-checklist item to add to the general Rule 5 sweep flow. Bulk-apply once monthly if not caught in the flip triage — grep every `h_*_orthogonality` and `h_*` name in R&D against the latest digest verdict to catch aging entries. Companion rule: [[feedback_shipped_items_leave_backlog]] — shipped items should exit Backlog entirely rather than acquire "SHIPPED" annotations.
