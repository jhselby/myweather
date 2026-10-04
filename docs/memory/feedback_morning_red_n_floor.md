---
name: feedback_morning_red_n_floor
description: "On morning digest triage, defer any red flag on a cell with n<100 pairs to the next day. Do not investigate, do not ship a fix. Small-n morning reds are usually sampling luck that self-heals as the window rolls."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: de85e7c6-dd3f-479b-af80-317414027d77
  modified: 2026-08-16T17:32:09.936Z
---

**Rule: if a morning-red flag is on a cell with n < 100 pairs, defer to tomorrow. Do not investigate. Do not ship code.**

`n` means matched (forecast, observation) pairs in the cell's window — the count that appears next to the flagged metric. If pooled n is large but a called-out sub-cell has n < 100, the rule applies to the sub-cell.

**Why:** Joe surfaced the pattern on 2026-08-16: morning digest flags red things → we investigate/ship fixes in the morning → afternoon looks green. Two hypotheses were compatible with that observation:
- **H1 — our fixes are working.**
- **H2 — self-heal would have happened anyway (rolling `last_24h` window ages out the problematic hours; overnight clear-sky exposes structural cloud-shift biases that normalize as diurnal conditions arrive).**

Discriminator: check untouched morning-reds. Today's four "diagnosed as self-heal, no action" items (h WATCH, pr WATCH, wg WATCH, ch@6-11h +372% on n=60) *all* recovered to green by afternoon. 4/4 is not conclusive on its own, but the mechanism story is real — `last_24h` is a rolling window, small-n cells resolve as the window rolls, and overnight clear-sky whipsaws cloud fields whose historical shifts learned on partly-cloudy climatology.

**Cost asymmetry that justifies the bias:**
- False positive (act on something that would have self-healed): often unbounded — this is exactly how chp `_CELL_SKIP` grew 0 → 9 → 10 in two days ([[project_chp_cell_skip_to_dynamic_gate]]).
- False negative (skip something real): usually one-day lag. Small.

**How to apply:**
- On any morning digest red flag, first look at `n`. If n < 100, defer.
- Above n=100, keep normal triage — but hold the posture: *look for a mechanism that won't recover on its own before shipping code*. Bias toward "wait one more read" unless there's a clear structural cause.
- Don't over-engineer this into a 3-check discriminator — the single n-floor rule captures most of the value with zero triage overhead.

**Reopen if:** the n<100 defer rule ever misses a real regression that then compounded. Adjust the floor upward or add a second gate then, based on the specific miss.

**Sibling context:**
- [[project_chp_cell_skip_to_dynamic_gate]] — the scar-tissue precedent (hand-typed static skips growing from noise-driven morning-reds)
- [[feedback_pooled_n_time_thin]] — related "large n but time-thin" trap
- [[feedback_measure_before_concluding]] — the general discipline this specializes
