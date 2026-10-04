---
name: dont-invent-numbers
description: "Never emit a quantitative claim (X% MAE gain, +N pp bias, N/M ship days, etc.) in prose that gets codified — CHANGELOG, debug page, memory notes, ledger — unless it came directly from a script output I can point to. If I can't cite the source, quote qualitatively or don't say."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 20ea0996-7e2b-434e-a249-5e0a5fcdc5fc
---

Codified 2026-07-04 evening after a real incident.

**What happened:** Earlier in the same session, I wrote a debug-page changelog line claiming "pp L3 Brier gain re-verified at +8.0% L2→L3 on today's data — pp stays in L3_FIELDS." That number had no analysis-script source. Every actual audit disagreed with it:

- Fitter Brier (`per_layer_brier_by_lead.pp`): l1=0.0734 → l3=0.0765 (Brier **worse** by +4.2%; lower Brier = better)
- `production_whatif.py`: `pp 45,300 11.188 +87.3%` (production 87% worse than raw)
- `h_regime_l3.py`: `pp sea_breeze -96.1% ★ L3 LOSES`
- Walkforward: pp has never been in the `L3_FIELDS` claim across 13 daily reads

The fabricated +8.0% was the sole "evidence" for keeping pp in `L3_FIELDS`, and it drove a bug that lived in production for hours until Joe caught the scorecard reading "7/12" and asked what the fields were. Real damage: a live-layer decision was set on a hallucinated number.

**How to apply:**

- Every percentage, ratio, MAE delta, or streak count that lands in codified prose (CHANGELOG entries, debug-page canon, shipped_ledger entries, memory notes) must be traceable to a specific script output. If the number isn't in a log I can grep for, don't cite it.
- When summarizing verdicts, prefer qualitative language ("L3 pp verdict re-checked and unchanged") over specific numbers unless I have the specific number in hand.
- If a specific number is required by the writing pattern (like a changelog bullet) and I don't have the exact figure, either: (a) fetch the script output and use its number verbatim, or (b) omit the number entirely.
- **Never round or estimate to a "reasonable-looking" figure.** +8.0% looks like a real audit number; that's exactly why it slipped through review and got codified. A wrong specific number is worse than no number.
- Under time pressure or when Joe is watching the ship happen, the temptation to write a plausible-looking summary is higher. That's when this rule matters most.

Related: [[feedback-do-it-right]] (structural fixes over process discipline — but this case is one where discipline of the writer is the actual bug), [[feedback-debug-page-canon]] (the debug page is canonical; codifying wrong numbers there is high-blast-radius).
