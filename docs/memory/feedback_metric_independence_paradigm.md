---
name: feedback-metric-independence-paradigm
description: "Each scoreboard metric must isolate one layer's work such that improving the metric implies improving that specific layer. No merging — no metrics that share denominators to make additivity work, no referee-caps of one metric by another, no averaging separate cascades into one score. Merging destroys attribution."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f4f9924e-0098-4fb2-bee7-03e379adcce9
  modified: 2026-09-09T00:30:28.787Z
---

# Every metric measures one thing — no merging

**The rule.** A scoreboard metric is valid iff improving the number implies improving the specific layer the metric is nominally about. If moving the number could mean "the layer got better OR some other layer/decision changed," the metric is merged and attribution is destroyed.

**Why:** Joe uses these metrics to decide where to work. A merged metric that could move for any of three reasons is worse than nothing — it invites work on the wrong layer. Documented in the 09-08 late-evening session ([[project_09_08_late_evening_session]]) after I proposed three separate merged fixes in one conversation, each of which Joe rejected as "you're being imprecise and it's pissing me off."

**How to apply:**
- Before proposing a metric change, ask: "does improving this number imply improving one specific layer?" If not, the proposal violates the paradigm.
- Referee-caps ("Selector Skill can't be green if Total Lift is red") merge. Rejected.
- Averaging cascade metrics into one number ("Cascade Skill = mean of HRRR + NBM") merges. Two separate cascades need two separate tiles or two separate columns.
- Sharing denominators across metrics to force additive decomposition merges. The trade-off is real: additive AND independent AND user-anchored baseline can't all hold together (three natural counterfactuals don't nest).

**Where additive decomposition IS OK:** in a SEPARATE panel labeled as attribution, not as quality. The 09-08 v0.6.569 Attribution panel does this — Total = Routing + Cascade in pp of user default, kept explicitly separate from the top-row quality tiles. The additive panel's Routing = 0 blind spot when selector picks the user default is honest, not a bug.

**Existing top-row tiles that pass the paradigm:**
- Total Lift = prod vs user default → user-visible outcome
- Pipeline Lift = corr_vs_l1_pct → cascade quality on the picked stack
- Selector Skill = VC → selector quality vs oracle

These three don't sum. Not a bug. Different questions.

**When to change a metric:** only when the number could improve without improving the nominal layer. Then propose a replacement that closes that gap — but check the replacement against this rule before shipping.

Related: [[project_09_08_late_evening_session]] · [[feedback_verify_writers_for_read_paths]] · [[feedback_measure_before_concluding]] · [[feedback_scoreboard_vs_cell_aggregation]].
