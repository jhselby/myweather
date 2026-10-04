---
name: verify-pipeline-ordering
description: "Before assuming where a correction module sits in the layer stack, grep the call site in `weather_collector/collector.py`. The module's own docstring or class structure can be wrong about pipeline position. Cost of getting it wrong is wasted hours interpreting bad metrics."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a8f5db73-5a54-4321-a927-279049b8212d
---

Before making any claim about which layer a correction module belongs to — or interpreting per-layer MAE numbers as evidence of how a layer is performing — verify the actual call ordering in `weather_collector/collector.py`. Run a grep like `grep -nE "stamp_.*_correction|apply_.*_corrections" weather_collector/collector.py` and look at the actual sequence of calls.

**Why:** the cove correction's module docstring described L6 as the last layer applied to temperature. The call site put `stamp_cove_correction` *inside* `build_weather_data` at line 318, **before** `apply_decay_corrections` ran at line 464. So the cove Δ was silently absorbed into the L2 column for the first ~10 hours after shipping (06-26 morning), and the L3/L4 layers were stacking on top of cove-modified L2 values. The Forecast Accuracy chart's L6 line was bogus until v0.6.232 fixed the ordering. Documented in [[project-06-26-session]].

**How to apply:**
- Any time a correction module ships, deploys, or its outputs start appearing in pair-log diagnostics: grep the call ordering FIRST. Do not trust the module's docstring or the surrounding comments about position.
- Specifically for snapshot/pair-log diagnostics: the snapshot captures values at one specific moment in the pipeline. If a correction runs after that snapshot, its effect won't be in the per-layer columns; if it runs before, it gets silently absorbed into whichever layer's column comes after.
- When debugging "why does this layer's MAE look terrible/great" — first sanity-check the snapshot is capturing the value before the next layer runs. Don't waste hours interpreting metrics from a broken pipeline order.

Related: [[feedback-read-inline-rules-before-editing]], [[feedback-debug-page-canon]], [[project-06-26-session]].
