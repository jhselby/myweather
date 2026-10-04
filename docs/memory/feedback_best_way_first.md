---
name: feedback-best-way-first
description: "Joe always wants the best/correct technical answer presented first with pros/cons, regardless of cost or complexity. Cost is HIS factor to weigh, not yours to pre-filter."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4a8831ed-d0ae-48ad-9c90-349a29eadd94
---

When presenting options for any technical decision, ALWAYS include the best way to do it — the most correct, robust, complete solution — with its pros and cons. Even if it's expensive or complex.

**Why:** Joe wants to understand the full solution space before deciding. He factors in cost and complexity himself when choosing what to actually do. If you pre-filter the "best" option out because you assumed he'd reject it on cost grounds, you've made the decision for him and robbed him of the information he needs. He'd rather see "best way costs $X and takes Y weeks" and pick something cheaper deliberately than be steered toward the cheap option without knowing what he's giving up.

**How to apply:**
- When sketching options, the best technical answer is always on the list — labeled as such.
- Include pros AND cons for each option, especially the best one. Cost and complexity belong in the cons, not as a reason to omit the option.
- Don't recommend the cheap option just because it's cheap. Recommend based on technical merit; let Joe weigh tradeoffs.
- If asked "what's the best way," answer directly. Don't deflect with "depends on your priorities" — give the technical answer, then note the tradeoff.

Surfaced during the 2026-06-16 L2 decay fitter discussion: I'd offered three options (manual refresh, manual refresh+upload, scheduled auto-fit) and recommended option 1 because it was simplest. Joe asked "what's the reason not to do 3?" — meaning he'd already noticed that the best technical option (full automation) wasn't being treated as a real candidate. The actual best answer turned out to be "scheduled auto-fit WITH a guardrail" — a fourth option I'd only mentioned as an afterthought. Should have led with it.

Related: [[user-skill-level]] (Joe wants counsel-mode, one decision at a time, but counsel means presenting the real options, not pre-filtering).
