---
name: dont-over-gate
description: "The live-layer change gate + 14-day watch is a shipping brake, not a hypothesis brake. Don't let \"the gate says no\" become a reason to stop generating or exploring new ideas."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 20ea0996-7e2b-434e-a249-5e0a5fcdc5fc
---

The 7-day agreement + 2-tool + per-cell + 14-day-watch framework (codified v0.6.288–289) governs **when a live-layer switch flips**. It does NOT govern:

- Generating new hypotheses
- Building experimental analysis scripts
- Curated-text / Stage 2 promotion (per `feedback_hypothesis_promotion_pipeline`)
- Refining hypothesis candidates that aren't yet at the "flip a live switch" stage

**Why:** The gate exists because the L5 ship-then-fail week showed that aggregate-only verdicts + one-tool agreement + no post-ship watch let bad ships through. It doesn't exist to slow exploration — the whole reason we built the framework is so we can trust the "yes" when it comes. If the gate makes us stop *trying*, we've built the wrong thing.

**How to apply:**
- When Joe raises a new hypothesis or asks "what could we do about X," respond in exploration mode — don't preemptively cite the gate as a reason to hold back. The gate applies at ship time, not at ideation.
- Weekly digest reads should include exploring what NEW candidates are surfacing, not just gating existing ones.
- If the "New candidates" / "Still confirming" buckets go empty for extended stretches, that's a signal to actively generate ideas, not a signal that we're done.
- Distinguish "the gate says no to shipping" from "the hypothesis is dead" — a hypothesis that isn't ship-eligible today may still be worth iterating on.

Codified 2026-07-04 after shipping the Shape 1 verifier (v0.6.291). Joe's exact framing: *"we don't want to let the dashboard become so good at saying 'no' that we stop trying new ideas."*

Related: [[feedback_hypothesis_promotion_pipeline]], [[project_hypothesis_backlog]], [[feedback_best_way_first]].
