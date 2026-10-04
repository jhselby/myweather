---
name: feedback-asymmetric-gates-hide-signal
description: "Asymmetric gating in evaluation logic — 'B must pass A's gate first' — silently hides real signals when A trivially fails for reasons unrelated to B's merit. Always check: does evaluating B require A to have already won, and if A is structurally a no-op for some inputs, does B still get scored? Discovered 2026-06-30 via the walkforward_l3l4_validator bug that recommended off_off for cc despite L4 winning by 9%."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 76252fe3-ab5d-4a76-8031-bc90764206fd
---

**Rule:** When an evaluation script gates step B on step A's verdict ("only consider B if A earned its keep"), audit whether A can structurally fail for reasons unrelated to B. If yes, B never gets evaluated for those rows — its real merit is invisible.

**Why:** Discovered 2026-06-30 in `analysis/walkforward_l3l4_validator.py`. The script gated L4 evaluation on L3 beating L2 by ≥2%. Sensible-looking rule. But for fields not in `L3_FIELDS` (cc, t, dp, h, ws, wg, sr, pr, pa), `forecast_l3 == forecast_l2` by construction — L3 is a no-op, trivially fails the 2% threshold. So L4 never got scored, and the validator recommended `off_off` for nearly every field. Cloud cover was the prime victim: L4 visibly wins by 9% at every lead band on the Forecast Accuracy chart, but the validator said drop. A "drop-cc gate" was building toward 7/7 against actual evidence.

**How to apply:**
- When writing or reviewing evaluation logic with cascade rules ("only check B if A passed"), explicitly enumerate cases where A fails for structural reasons (not merit) and trace whether B's signal still surfaces.
- Prefer INDEPENDENT evaluation per step when the steps don't actually depend on each other in production. If step B's actual production wiring can fire regardless of step A's state, the evaluator should match.
- For the walkforward case: L4 in production fires for fields in `L4_FIELDS` regardless of `L3_FIELDS` membership. The evaluator's "L4 requires L3" assumption didn't match production. Always re-check: does the evaluator's dependency chain match the production code's?
- Sanity-check evaluator output against the visible chart. If a clear chart signal contradicts the evaluator's recommendation, suspect a logic bug in the evaluator, not the chart.

Related: [[project-06-30-session]] (the discovery + fix), [[feedback-debug-page-canon]] (the chart is canonical).
