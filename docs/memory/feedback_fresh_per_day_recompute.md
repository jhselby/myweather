---
name: feedback_fresh_per_day_recompute
description: "When a Fitter watch series uses a cumulative/growing window, its \"collapse\" date lags the real break by however long old high-value entries take to dilute. Recompute fresh per obs-day directly from the pair log to find the actual break."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9f628bfb-c69d-4f01-8ea8-d87eb0bb20d7
---

When investigating a "COLLAPSE" or "DECAY" alert from a watch series that aggregates over a growing/cumulative window, do NOT trust the alert's date. Recompute the underlying signal fresh per obs-day directly from the pair log BEFORE reasoning about causation.

**Why:** 2026-07-16 MLC diagnostic. `marine_layer_anomaly.py` flagged collapse at 07-07. Fresh per-obs-day recompute (`marine_layer_collapse_diagnostic.py`) showed the real break was 06-30 — a 7-day lag. That lag flipped the causation story: pre-fix, the collapse looked HRRR-anomaly-coincident (07-04 onset); post-fix, it was clearly pre-HRRR and stratum-local, ruling that hypothesis out. Wrong date → wrong cause → wrong next action.

**How to apply:** Whenever a watch alert names a specific date, if the fitter aggregates cumulatively (or over a growing window), write a per-obs-day recompute BEFORE building a causation hypothesis. Cheap to do, expensive to skip. Related: [[project_mlc_diagnosis]].
