---
name: feedback-two-window-needs-independent-rows
description: "A two-window (14d + 50d) CONFIRMED verdict is only independent if the long window contains substantially more rows than the short one. For a rare or new regime (nor_easter) the 50d n barely exceeds the 14d n: both windows are the same event and the gate confirms itself. Compare n14 vs n50 before treating a skip-ADD as confirmed; ship as TEMPORARY with a re-review date if not independent."
metadata:
  node_type: memory
  type: feedback
  modified: 2026-10-05T15:00:00.000Z
---

# Rule

Before shipping a `nbm_skip_add_audit` CONFIRMED cell, read `n14` against `n50`. If `n50 - n14` is small relative to `n14`, the 50-day window is the same rows as the 14-day window and the "two-window" agreement is one observation. Treat the cell as single-event evidence: ship only as **TEMPORARY with a re-review date**, or hold.

# Why (10-05)

The digest's four CONFIRMED cells, with n14 -> n50:
- `wd/se_flow/24-47`: 620 -> 6,052 (independent; real depth) — shipped normally.
- `wd/nor_easter/12-23`: 228 -> 270 (+42 rows) — one event.
- `wd/nor_easter/24-47`: 206 -> 208 (+2 rows) — one event.
- `wg/nor_easter/12-23`: 346 -> 350 (+4 rows), and half A degenerate at -0.00 — dropped.
My first pass (carried from the 10-03 note) said "ship the three wd cells" without comparing n. The same trap is documented for sr nor_easter in the v0.7.11 skip-table note ("new-regime blocks the 14d+50d two-window gate"). The nor_easter regime is rare outside the late-Sep event.

# How to apply

- Compute `n50/n14` when reading any CONFIRMED list; flag ratios near 1.
- Single-event cells: ship as TEMPORARY, put the re-review date in the table note, the history reason, the CHANGELOG, and the memory (10-13 for the v0.7.11 and v0.7.24 nor_easter cells).
- A degenerate half (-0.00) is not stability evidence, even when the other half is large.

Related: [[project_10_05_session]] · [[feedback_dont_over_gate]] · [[feedback_grid_select_halves_stable]] · [[project_nbm_skip_proposals_review]]
