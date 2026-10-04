---
name: layer34-over-correcting-watch
description: Watch item — Layer 3 (decay) and Layer 4 (diurnal) corrections may be net-negative for most fields now that the v0.6.17 expanded mesonet (81 stations + octant balancing) is so stable. Currently dismissed as too-little-data + mid-seasonal-shift; revisit if pattern persists.
metadata: 
  node_type: memory
  type: project
  originSessionId: b64b54ae-d13f-48c0-b164-388979caa9c3
---

After v0.6.27 (14-field correction stack live), the Forecast Pipeline per-layer MAE chart at lead 6h showed Layer 3 + Layer 4 corrections making things WORSE than Layer 2 alone for most fields. Final-vs-raw at lead 6h on 2026-06-03 afternoon:
- Wind speed: +46% better (final beats raw)
- Pressure: +23% better (tiny absolute)
- Temp: −11% WORSE
- Dew point: −67% WORSE
- Wind gust: −84% WORSE
- Humidity: −88% WORSE

**Why:** Layer 2 mesonet correction got dramatically more accurate after v0.6.17 (81-station octant-balanced + MAD-trimmed). Hypothesis: L3 decay corrections trained on a 14-day rolling window are pulling forecasts AWAY from where the now-stable Layer 2 anchor lands, because the historical pair data spans periods when mesonet was less reliable.

**Why: He says it didn't run long enough to be conclusive** Joe explicitly dismissed this on 2026-06-03 as: (1) only a few days of data since v0.6.17, (2) mid-June seasonal shift (spring → summer marine layer dynamics). Will let it run more before making any structural changes.

**How to apply:** When reviewing per-layer MAE chart in future sessions, specifically check whether L3/L4 are still net-negative at meaningful leads (6h+). If after ~2 weeks of stable conditions the pattern persists, candidates to investigate:
- Shorten tau (currently 14d) to track current state more closely
- Tighten CAPS for fields where mesonet is dominant
- Per-field decision: drop decay/diurnal for fields where they're net-negative (e.g., humidity)
- Investigate whether per-station Kalman calibration interaction with mesonet is partly causing it

Related: [[per-layer-mae-tracking]] (v0.6.25 infrastructure).
