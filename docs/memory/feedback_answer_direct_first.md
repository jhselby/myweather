---
name: feedback-answer-direct-first
description: "When Joe asks \"are we done with X?\" answer yes/no first, then reason. Don't lead with a menu of remaining gaps unless they're X-specific."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 59e82d06-cdfb-4ebe-9ff9-4ea3ac9e7b83
  modified: 2026-08-21T12:31:01.009Z
---

# Answer direct first — yes/no, then the reason

When Joe asks a closure question like "is L4 done?", "are we ready to move on?", "is X really complete?" — lead with a one-word answer.

**Why:** Joe is confirming a state so he can plan the next move. He is NOT asking for a completeness audit. Answering with a bulleted list of "yes but here are 6 gaps" makes him re-do the parse work to figure out whether the gaps are blockers or noise. Recorded 08-21 morning session — Joe said "stop confusing me. I'm probing whether we're really ready to move on or whether there is more L4 work. I understand that the data may take time to build out, but what else do I need to do so that we are completely caught up re: L4" and later "jesus, fine, move on" when I kept qualifying.

**How to apply:**
- First word: **Yes** or **No**.
- Second sentence: the ONE reason it's yes, or the ONE gap that makes it no.
- Only list additional gaps if they're **specific to the thing being asked about** — not cross-cutting infra shared with other components.
- If gaps exist but are deferred by design (plan-of-record, follow-up sweep), say so in one clause: "Yes; the [X, Y] cleanup is a shared post-cascade sweep, not L4-specific."
- Never invent new terminology mid-answer. If a term isn't already in Joe's vocabulary from the conversation, use plain English.

Related: [[feedback-recommend-never-menu]], [[feedback-strunk-white]].
