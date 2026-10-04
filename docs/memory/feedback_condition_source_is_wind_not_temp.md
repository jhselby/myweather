---
name: condition-source-is-wind-not-temp
description: "current.condition_source labels the wind-blend max-gust source, not the temperature source-of-truth"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c00612bd-49b6-498e-9bf3-3707c2c1cd1e
  modified: 2026-09-17T15:33:57.814Z
---

`current.condition_source` in `weather_data.json` (e.g. `"Tempest_Forest Ave observed"`, `"KBOS+KBVY consensus"`) is the **wind-blend selected source label**, set in `wind_blend.py:339` from the max-gust winner. It is NOT the temperature source.

Temperature source-of-truth is the WU-multi-station weighted blend in `hyperlocal.py` around L275–390, with model-anchor bias correction. Different pipeline, different sources, different code.

**Why:** the name is misleading. If Joe (or you) asks "why is temperature X — Forest Ave?", the honest answer is that Forest Ave had nothing to do with the temperature reading; it just won the gust vote.

**How to apply:** when reasoning about where a `current.temperature` value came from, ignore `condition_source`. Trace `hyperlocal.py`. When reasoning about wind selection, `condition_source` is the right field.
