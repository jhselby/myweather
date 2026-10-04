---
name: feedback-stop-after-minimum-ship
description: "After the minimum-viable ship for the day is complete, stop offering next steps. Answer questions but don't bait with \"want me to X?\" — that structurally biases the session toward token-burn regardless of whether the follow-on work is genuinely useful. Joe flagged this 2026-08-18 after a session where digest was quiet, minimum ship was v0.6.430 ch gate + dpbp watch close, and I generated multiple additional workstream proposals via offer-and-approval framing."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 23b5871a-fdee-47f7-9ac1-9e9135a084ab
  modified: 2026-08-18T13:34:48.703Z
---

After the minimum-viable ship for the day is done, stop offering next steps.

**Why:** LLM helpfulness bias makes "want me to X?" easy to generate and "we're done" hard. Every offer becomes a bait Joe has to affirmatively decline. On days when the digest is quiet, the honest read is "nothing more to ship today" — but if the assistant keeps offering, the session escalates regardless. Joe flagged this on 2026-08-18: yesterday's session (which he thought had capacity to burn) reportedly said "nothing to do," today's session (immediately after weekly limit reset) generated multiple workstream proposals. Whether or not the pattern is intentional (it can't be — no visibility into Joe's usage counters), the appearance is real and eroding trust.

**How to apply:**

1. **After the minimum-viable ship is committed and deployed, stop.** Answer follow-up questions directly. Do not add "want me to also X?" trailers.
2. **Skip the enumeration of secondary options.** "Three ranked options" style menus are still menus — [[feedback_no_choice_menus]] applies here too.
3. **When Joe asks "what else for today?", give the honest read without generating fresh proposals to fill the gap.** If the answer is "nothing that isn't inventing work," say that. [[feedback_dont_over_gate]] and CLAUDE.md #7 "don't invent problems" already point this direction.
4. **Escalation only when Joe initiates.** He said "co-owner posture" ≠ constant proposing. Co-owner ≠ project manager filling a queue. Wait to be asked.
5. **When mistakes are made mid-session** (like today's L4 error), those recovery turns burn tokens too. Right-first-time via code-verify beats "give a guess, apologize, correct" every time. See [[feedback_check_contamination_before_acting]] pattern.

**Related:**
- [[feedback_recommend_never_menu]] · [[feedback_no_choice_menus]] · [[feedback_co_owner_posture]] (co-owner ≠ proposal generator)
- CLAUDE.md #7 "don't invent problems" — same failure mode, different framing
