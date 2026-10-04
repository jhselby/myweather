---
name: do-it-right
description: "Default to fixing the root problem, not adding process gates that require human discipline. Don't ask \"should I do it right\" — do it right."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0fb7dc49-7264-449c-9db2-c3b615b2950b
---

When a decision has "rebuild the tool so the failure is impossible" vs "add a manual gate / discipline requirement" as options, pick the rebuild. Don't offer the manual gate.

**Why:** Manual gates require discipline that has already failed. Every failure mode Joe has flagged in this project traces back to "we knew we should check X but forgot / trusted the aggregate / skipped the second tool." Adding a rule that says "always run tool B before shipping" is proposing the same solution that has failed for weeks. The whole point of building tools is so the correct behavior is automatic, not a discipline requirement.

**How to apply:**
- When presenting a fix, don't offer a smaller "process gate" version as if it were a legitimate alternative to a proper structural fix. It isn't.
- Never phrase a structural fix as optional relative to a "keep muddling with more discipline" path.
- "Do it right" is the default. Don't ask permission to build the correct thing; recommend it directly and build it when authorized.
- Codified 2026-07-03 after the h → L4 walkforward-vs-cross-cut incident. Walkforward emits an aggregate that hid regime-specific damage; I proposed "keep the tool, add a process gate requiring cross-cut agreement." Joe correctly identified this as the failing pattern.

Related: [[user_skill_level]] (counsel mode = give the best technical option, not the cheapest one), [[feedback_best_way_first]].
