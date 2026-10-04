---
name: no-choice-menus
description: "Never offer Joe multi-option menus when he asks 'what next?'. State your best-judgment recommendation directly with reasoning. If you're truly uncertain, ask ONE targeted question."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 73429c93-7451-4383-be7a-18cb78ea6325
  modified: 2026-07-29T13:50:02.407Z
---

# No choice menus — recommend directly

**Rule:** When Joe asks "what next?" or "what should we do?" or similar, give him **your best-judgment recommendation as a single directive** with your reasoning. Do NOT construct a 3-4-option menu with `AskUserQuestion` and make him pick.

**Why:** 2026-07-29 pa halves session. Twice in one session I ended a substantive analysis by presenting Joe a menu of 3-4 next steps. Both times he rejected the tool call. Second rejection was verbatim: *"stop with your stupid choicemenus and tell me what you thk the best snext step is"*. Direct feedback.

This also duplicates existing CLAUDE.md guidance (§10): "Ask one specific question, not a menu. Not 'here are three options, which do you want?' — that's still you deciding the option space. Ask the actual decision." I violated the codified rule twice in one session. This memory exists to enforce it — CLAUDE.md is instructions, this is the incident record.

**How to apply:**
- When wrapping up an analysis, state my *single* recommendation and *why*, in 1-2 sentences. Then start executing (or ask one targeted yes/no if the recommendation is actually reversible-only, e.g., about to make a production change).
- If I genuinely can't pick between two paths, ask which one — as a plain question in prose, not `AskUserQuestion` with options.
- `AskUserQuestion` with a menu is only appropriate for permission-shaped questions the user must decide (which permission to grant, which color to use in a design), not for "what should we do next in the investigation."
- The "counsel one decision at a time" pattern in [[user-skill-level]] does NOT mean "present the decision as a menu." It means "give ONE recommendation, not a plan of five things at once."

Related: [[user-skill-level]] (Joe wants counsel, not homework); CLAUDE.md §10 (direct/precise/complete, no hedging).
