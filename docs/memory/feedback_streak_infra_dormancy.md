---
name: feedback-streak-infra-dormancy
description: "Streak counters and gate-history writers are themselves silent-dormancy surfaces. A null claim row co-occurring with a populated source verdict = broken parser, not \"no signal today.\" Refuse to write; warn instead."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bddeb1dc-3ff1-42f6-9d5c-dd78607b5456
---

If a digest infrastructure writes a "claim row" derived from another script's log (e.g., `_claim:L3_FIELDS` scraped from `walkforward_l3l4_validator.log`), guard against writing a null claim when the source script's verdict field in the same row is populated. That co-occurrence is the smoking-gun signature of a silent parser failure — writing the null row resets any downstream streak gate. Skip the write and emit a WARN.

**Why:** 2026-07-10 morning — discovered the L3-drop-ws streak had been wedged at 0 for **7 straight days** (07-04 through 07-10). Every daily digest wrote `_claim:L3_FIELDS: null` while the source `walkforward_l3l4_validator` verdict field was populated in the same history row. Ran the parser directly against the same log file — it succeeded. Ran it via the digest orchestration path — silently failed. Best-fit hypothesis: Python's block-buffered stdout when redirected via bash `>` occasionally leaves the .log incomplete at the moment claims.py reads it, even though walkforward has already "finished." A functionally identical duplicate of the same parser in `divergence_report.py` succeeded in the same run because it ran a few seconds later. Both problems fixed 2026-07-10:
- claims.py now falls back to `walkforward_l3l4_summary.txt` (direct `with open("w")` — deterministic flush) when the .log regex misses
- divergence_report imports the one canonical impl from claims (no more duplicate silently drifting)
- build_executive_summary dormancy-guards the null-claim-with-populated-verdict case
- `_streak_for` filters today by UTC date, not by row-index (safe against skipped writes)

**How to apply:** any new digest field that derives structured state from another script's log needs the same three defenses: (a) at least one belt-and-suspenders read path (direct-written file, not stdout-redirect), (b) a source-verdict guard before writing null, (c) date-filtered "skip today" logic in the streak walker. Same class as [[feedback-verify-writers-for-read-paths]] but applied to *streak/history writers* rather than *runtime state writers*.

Related: [[feedback-verify-writers-for-read-paths]], [[feedback-stated-intent-vs-code-behavior]], [[project-todo]].
