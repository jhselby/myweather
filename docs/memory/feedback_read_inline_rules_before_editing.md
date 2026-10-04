---
name: read-inline-rules-before-editing
description: "Before editing a module's tuned values (bias tables, lookup dicts, τ values, thresholds), read the module's docstring AND the debug page section for that module — they encode usage rules that the values are not allowed to break."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a8f5db73-5a54-4321-a927-279049b8212d
---

Before changing any tuned values (bias tables, lookup dicts, τ, thresholds, gates) in a correction or audit module, read TWO things first:
1. The module's own docstring + inline comments at the dict definition.
2. The corresponding section of `corrections_debug.html` (debug page is canon per [[feedback-debug-page-canon]]).

Both encode rules about *when* refits are allowed — not just *what* the values mean.

**Why:** 2026-06-24 session, I refit `solar_correction._BIAS_FALLBACK_BY_REGIME` and `_BIAS_BY_REGIME_HOUR` from a fresh l5_recompute run, reasoning that the module was `ENABLED = False` so the edit was safe. It wasn't. The debug page (line 1061) explicitly said: *"Don't re-refit biases mid-trajectory or simulator reads become uninterpretable."* L5 had an active 7-day trajectory gate counting SHIP/HOLD reads against the 06-21 bias values. Refitting mid-trajectory mixes old-bias and new-bias rows in the simulator window and invalidates the gate. Joe caught it, I reverted. The rule exists because trajectory tracking is the whole promotion mechanism for that module — clobbering it for a freshness gain isn't a tradeoff worth making.

**How to apply:**
- When a module's docstring mentions "trajectory," "gate," "simulator," "promotion read," or "don't re-fit during X" — that's a hard constraint, not a stylistic comment.
- When the debug page has a sentence starting with "Don't" or "Never" in the section about the module, treat it as a hard rule.
- Default action: if you're tempted to refit/update tuned values and there's any tracking/gate state, ASK Joe before editing. Cost of one question is tiny; cost of invalidating a multi-week trajectory is whole sessions of re-tracking.
- "Gated OFF means safe to edit" is wrong. Gated modules can still have live trajectory tracking around them.

Related: [[feedback-debug-page-canon]], [[feedback-hypothesis-promotion-pipeline]], [[project-l5-trajectory]].
