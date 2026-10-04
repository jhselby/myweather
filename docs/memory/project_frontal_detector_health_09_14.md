---
name: frontal-detector-health-09-14
description: "Frontal detector miscalibrated — DP_DROP_THRESHOLD=8.0°F above p99.9=6.3°F (max obs=6.8°F) so dp signal is dead and type='cold' is unreachable. New analysis/frontal_detector_health.py (v0.6.619) emits daily digest HOLD verdict until recalibrated. Runtime also missed 5/9 candidates over 14 days — root cause not traced. Related to C1e post-front axis quality."
metadata: 
  node_type: memory
  type: project
  originSessionId: ece03753-be53-47fd-b95c-6a699b0574ab
  modified: 2026-09-14T17:22:46.354Z
---

# Frontal detector health — daily digest watch (v0.6.619)

## Status (2026-09-14)

**v0.6.620 SHIPPED:** `DP_DROP_THRESHOLD` lowered 8.0→4.0°F, diagnostic logging added when score≥1. Collector redeployed 17:22 UTC. Health check verdict will auto-flip HOLD→CLEAN as new obs accumulate over 14d rolling window.

Open: miss-rate root cause still unknown. Next occurrence should now be traceable in `gcloud functions logs read myweather-collector --region=us-east1 --gen2` — look for `frontal: score=N sigs=...` lines that should have fired but didn't produce an events-log write.

## Finding

The runtime detector in `weather_collector/processors/frontal_detection.py` uses three signals over a 60-min rolling window with 2-of-3 required. The dp signal is effectively dead.

**14-day observed distribution** (Aug 31 – Sep 14, 2005 obs, 2002 60-min windows):

| Signal | Live threshold | p95 | p99 | p99.5 | p99.9 | max | Status |
|---|---|---|---|---|---|---|---|
| dp_drop °F | 8.0 | 2.0 | 3.8 | 4.5 | 6.3 | 6.8 | UNREACHABLE |
| wd_shift ° | 60 | 117 | 160 | 173 | 177 | 179 | permissive |
| press_bounce inHg | 0.02 | 0.024 | 0.030 | — | 0.04 | 0.04 | permissive |

Detector reduces in practice to `wd_shift ≥ 60° AND press_bounce ≥ 0.02 inHg`. The `_classify_type='cold'` branch requires `dp_drop ≥ 8.0` — unreachable, so **0 events have ever been tagged `cold`**. All 4 live entries are `unknown` or `sea_breeze`.

## Miss-rate finding (unexplained)

Simulating the runtime's own 2-of-3 logic on the raw obs log finds **9 candidate passages in 14 days**, only **4 landed in the events log**. All 5 misses had ≥6 obs entries in their 60-min windows — not a window-thinness issue. Not explained by dedup (misses span days). Root cause not traced this session.

## Threshold recommendation

Lower `DP_DROP_THRESHOLD` from 8.0 → 4.0°F. That's at p99.5 (~top 0.5% of observed events). Simulated event count at candidate thresholds:

| dp_thr °F | Events / 14 days |
|---|---|
| 8.0 (live) | 9 |
| 6.0 | 10 |
| 5.0 | 10 |
| 4.0 | 13 |
| 3.0 | 15 |
| 2.0 | 23 |

Cliff at 2-4°F. 4°F adds 4 real candidates without flooding. Would require downstream C1e "post-front" cells to be re-fit — currently they tag on a broader "wind-shift + pressure regime change" signal, not "cold front passed."

## Digest wire

`analysis/frontal_detector_health.py` runs on every digest cycle. Verdict shape:

```
Verdict: HOLD — dp_thr=8.0°F unreachable (max obs=6.8°F); type='cold' never classified (dp branch unreachable); runtime missed 5/9 candidates; live=4 events / 336h
```

Auto-flips to `CLEAN` when thresholds recalibrated. Cull from the digest via `.skip.py` rename if the issue is superseded or accepted as-is.

**Why:** persistent digest signal is stronger than a queued-investigation memory that decays. Joe reads the digest daily; queued investigations don't get seen unless surfaced. Follows the same pattern as `c1_calibration_audit` sitting in HOLD.
**How to apply:** when digest emits this HOLD line, remember: the fix is a threshold change in `weather_collector/processors/frontal_detection.py`, plus a re-fit of any C1e-conditional cells downstream. If verdict text changes (new problem categories), read the script's output before acting.

## Related

- [[project_ch_24_47h_c1d_c1e_split]] — the C1d × C1e split investigation that surfaced this problem. Now blocked: needs the frontal detector fixed first before C1e-conditional cells can be re-fit.
- [[feedback_hypothesis_promotion_pipeline]] — daily digest as the pipeline surface, not memory.
- `analysis/frontal_detector_health.py` (v0.6.619) — the health check script.
- `weather_collector/processors/frontal_detection.py` — the detector with the bad thresholds.
