---
name: feedback-whitelist-promotion-gate
description: "Whitelist changes (L3/L4 add/drop) must pass the 7-window promotion gate, same discipline as conditional layers. Two same-day reads from different methods are NOT enough."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4a8831ed-d0ae-48ad-9c90-349a29eadd94
---

L3/L4 whitelist add/drop decisions must clear the 7-cutoff promotion gate before shipping. Two same-day reads from different methods (e.g., walk-forward + sweep on the same day) do NOT meet the bar, even when they agree.

**Why this rule exists:** the cm-drop on 2026-06-16 (v0.6.111) was shipped because a 06-15 walk-forward and a 06-16 sweep both said cm OUT. Re-checked retroactively on 2026-06-18 with the new 7-window simulator, every cutoff from 06-12 through 06-18 unanimously said cm IN — by +2.5% to +6.5% MAE. Including the 06-15 cutoff. Including the 06-16 cutoff. The decision was driven by a noisier read of the same signal, not by a real shift. **cm should never have been removed.**

**The rule, restated:**

- Before adding OR removing a field from L3_FIELDS / L4_FIELDS, run a 7-cutoff simulation (analysis/simulate_windows.py pattern: 7 trailing daily cutoffs, each on a 7-day window).
- All 7 cutoffs must agree on the same verdict (all SHIP / all HOLD).
- If they flicker, hold the current state. Do NOT ship.
- Two same-day reads from different methods are equivalent to one read for gate purposes — they share a window, not just a method.

**How to apply:**

- When walk-forward suggests a change, run the 7-window check on the same field BEFORE deploying.
- The backtest sweep is a sister tool — same data, different framing; it shouldn't be treated as independent confirmation.
- If a deployment slipped through and a later 7-window read disagrees, revert. The framework values stability over flickering ship decisions.

**Historical reference:**

- 2026-06-16 cm drop (v0.6.111) — shipped on 2 reads; reverted 2026-06-18 (v0.6.125) when 7-window read unanimous the other way.
- Don't surface this in the public changelog — Joe's call. But the lesson stays here.

## Related

- [[feedback-hypothesis-promotion-pipeline]] — same gate framework, applied to research hypotheses (L5/R5/R6). This memo extends it to whitelist decisions.
- [[project-walkforward-l3l4-validator]] — the tool whose output triggers whitelist consideration; not a ship signal on its own.
