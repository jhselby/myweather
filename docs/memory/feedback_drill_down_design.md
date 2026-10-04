---
name: drill-down-design-principle
description: "Drill-down section's purpose is forward-looking forecast preview (what each layer thinks), not accuracy diagnostic. Don't add past-observation overlays — pairing belongs in Accuracy section."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b64b54ae-d13f-48c0-b164-388979caa9c3
---

The drill-down section on the Forecast Pipeline page is for "preview the next 48h, see what each correction layer predicts." Forward-only x-axis (lead 0-47h).

**Why:** Joe rejected (v0.6.33a) the addition of past-observation overlays because standalone past observations aren't diagnostic — they're just "what the weather did." The diagnostic value would come from PAIRING (past forecast vs past observation), but that comparison already belongs in the Forecast Accuracy section (which does it statistically per-layer via per_layer_mae_by_lead).

**How to apply:** When tempted to add "show past observations" or "show past forecasts" to the drill-down, don't. Instead, route the request to either:
- The Forecast Accuracy section (for statistical per-layer accuracy)
- The Almanac → Observed card (for raw obs history)
- A new dedicated "forecast retrospective" view (if real per-pair past forecast vs past obs comparison is needed — substantial new work)

What the drill-down DOES need (and has, post-v0.6.33a):
- Multi-line forecast layers for the next 48h (one line per layer)
- Confidence band around the L4 line (±near-term MAE)
- MAE annotation strip under each chart (near-term + day-ahead)

Related: [[correction-stack-architecture]].
