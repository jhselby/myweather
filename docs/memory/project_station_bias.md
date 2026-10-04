---
name: project-station-bias
description: Per-station bias tracking for hyperlocal temp correction — built and deployed
metadata: 
  node_type: memory
  type: project
  originSessionId: 263d9e31-8651-4d6d-a7fc-f90ef99692e0
---

Station bias tracking is built and running as of May 2026.

**Why:** 38 stations is past the point of diminishing returns on count. The limiting factor is uncalibrated consumer sensors with persistent offsets.

**How to apply:** This is live — don't plan to build it, reference it as existing infrastructure.

## What's built

- `weather_collector/processors/station_bias.py` — Kalman tracker, leave-one-out consensus, 48h rolling window
- `station_history.json` in GCS — rolling per-station readings
- Per-station chronic offsets applied as weight adjustments in `hyperlocal.py`
- Diurnal split: separate day/night bias offsets (7am–7pm ET)
- Kalman gain K = 0.90/0.65/0.40 based on station count and agreement
- KBVY logged as external calibration anchor (`kbvy_temp_f`, `kbvy_local_delta`)
- MIN_READINGS=6 before offset is applied
