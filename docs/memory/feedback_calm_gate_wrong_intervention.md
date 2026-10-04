---
name: feedback-calm-gate-wrong-intervention
description: "2026-06-30: CALM_GATE_ENABLED (fc_ws<3 ws/wg L3 skip) killed as wrong intervention. ws L3 in the calm regime WINS +15% to +44% across lead bands; the actual L3 losers are ne_flow (all bands) and short-lead sea_breeze. Lesson: a gate motivated by 'L3 hurts at low wind speeds' needs the regime cross-cut BEFORE shipping the gate, not after — fc_ws<3 and the calm synoptic regime are not the same set."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 56248ef4-af78-48a9-998a-163e8a07965d
---

**The rule.** Before shipping a fc_<field> threshold gate (e.g. "skip L3 when fc_ws<3"), confirm with `l3_regime_lead_analysis` (or its L4 sibling) that the threshold tracks where L3 actually loses. Threshold predicates and synoptic-regime labels are not interchangeable categories — a "low fc_ws" row can fall in the calm regime (where ws L3 wins big) OR in ne_flow / sea_breeze (where ws L3 loses).

**Why:** 2026-06-30 incident. CALM_GATE_ENABLED was built in v0.6.252 off-by-default, premise = "ws L3 hurts at low wind speeds." On 2026-06-30 the post-walkforward-bugfix run pulled the regime cross-cut on 694,842 L3-field pair rows. Result: ws L3 in the **calm** regime WINS at every lead band:
- 0-5h: +15.3% (n=4,833)
- 6-11h: +29.9% (n=5,233)
- 12-23h: +44.0% (n=10,307)
- 24-47h: +44.3% (n=20,458)

The actual losers are **ne_flow** at every band (n=1.0K → 4.1K, −5% to −9%) and short-lead **sea_breeze** (0-5h −9.5% n=966; 6-11h −15.2% n=918). The fc_ws<3 gate would have skipped L3 in the calm regime — exactly where it wins biggest. Killed without flipping. Gate removal from `decay_apply.py` queued for the next collector ship (gate is off-by-default, so it's a no-op in code; removal is cleanup).

**How to apply:**
- Any future "skip L<N> when fc_<field> {op} threshold" gate needs the regime cross-cut as Stage 1.5, before adding the constant. The cheap way: re-run `l3_regime_lead_analysis` (or write the L4 sibling for L4 gates) and confirm the threshold's row set sits inside a losing regime, not a winning one.
- The right home for "skip L3 in ne_flow + short-lead sea_breeze" is the per-(field, regime, lead_band) skip table (queued in Open architectural questions on the debug page) — the regime axis IS the right gate, just not via a wind-speed proxy.
- See also [[feedback-regime-lead-band-cross-cut]] (ALWAYS run regime cross-cut before acting on a walk-forward verdict) — same pattern; that memory predicted this outcome.

**See also:** [[project-06-30-session]] for the session context.
