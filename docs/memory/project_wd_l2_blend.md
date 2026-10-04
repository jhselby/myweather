---
name: wd-l2-blend
description: "wd (wind direction) added to L2 blend via circular sin/cos unit-vector mean in wind_blend.py. Same 24h linear decay as ws/wg. Calm-floor 3 mph. Shipped 07-20 v0.6.368a; v0.6.384 shrank BLEND_HOURS 24→4. First circular field entering L2. Watch CLOSED CLEAN 08-11 — post-fix 0-5h delivers −23% MAE, 6-11h & 12-23h near-neutral (~±0.3%), 24-47h never fires."
metadata: 
  node_type: memory
  type: project
  originSessionId: d0ce8e13-443e-4221-9625-a6ecbc9e587f
  modified: 2026-08-11T15:27:57.064Z
---

# wd L2 blend

First wd correction shipped. Third wind field in `wind_blend.py`, after ws/wg. Skipped Stage 0→3 gating per [[feedback_l2_no_stage_gate]] — L2 new-field adds are architectural, not per-cell.

## Math

Circular unit-vector weighted mean, then atan2 back:
```python
obs_rad = math.radians(observed_dir)
fc_rad  = math.radians(dirs[i])
s = weight * math.sin(obs_rad) + (1 - weight) * math.sin(fc_rad)
c = weight * math.cos(obs_rad) + (1 - weight) * math.cos(fc_rad)
dirs[i] = round((math.degrees(math.atan2(s, c)) + 360.0) % 360.0)
```

Linear scalar averaging would produce garbage on wraparound (avg of 350°+10° = 180° instead of 0°). Vector mean handles the boundary correctly.

## Decay curve
Same linear ramp as ws/wg: `weight = max(0, 1 - lead/BLEND_HOURS)` with `BLEND_HOURS = 24`. 100% obs at h=0 → 0% at h=24 → 0 beyond.

## Calm-floor guard
`WIND_DIR_MIN_SPEED = 3.0 mph`. Skip cell when `max(observed_speed, fc_speed_i) < 3.0`. Direction is physically noise at calm speeds; blending would inject junk. Verified: fc_wd=180 + obs_wd=45 with both speeds <3 → wd unchanged.

## Observation source
`cur.get("wind_direction")` from `weather_data["current"]`. **Field name matters** — `obs_temp_log` uses `wind_dir` (short); `weather_data["current"]` uses `wind_direction` (long). v0.6.368 shipped with wrong short key → blend never fired. v0.6.368a hotfix.

## Files touched
- `weather_collector/processors/wind_blend.py` — added wd branch in `blend_observed_into_hourly()`, `WIND_DIR_MIN_SPEED` constant
- `weather_collector/processors/forecast_snapshot.py` — flipped `wd.l2` from `raw_wind_direction` to `wind_direction` so Fitter measures L2 output not raw

## First-tick verify (14:17 EDT)
```
raw_wind_direction[0:6]: [166, 146, 140, 131, 131, 136]
wind_direction[0:6]:     [204, 202, 200, 197, 194, 192]
delta:                   [+38, +56, +60, +66, +63, +56]
```
current.wind_direction = 204.5, current.wind_speed = 6.15 (above floor). Blend pulled fc toward obs at 100% weight at h=0, linear decay through h=5.

## First honest Fitter read — 07-20 15:08

`per_layer_mae_by_lead["wd"]`:
- **Lead 0: L1 42.7° → L2 27.7°, −35% MAE (−15°).**
- Leads 1–47: L1 == L2, zero delta everywhere else.

Explanation: hotfix v0.6.368a landed only ~2h before this Fitter run. Fitter's 30-day rolling window pairs recent obs against forecasts issued 1h–48h earlier — those older forecasts predate the wd wiring and have L2 == L1 by construction. Only lead 0 has enough post-fix pairs to move the average. Real 48-lead curve emerges as pre-fix pairs age out over the next day.

**Green flag on the blend:** −35% at lead 0 is in the ballpark of what a Kalman blend against fresh obs should deliver. First Fitter at 07-21 03:07 will have ~12h more post-fix pairs; leads 1–11 should start showing signal.

## v0.6.384 (2026-07-28) collateral fix — BLEND_HOURS 24 → 4

wd shares wind_blend.py's BLEND_HOURS constant with ws/wg (single shared loop). The 07-28 ws-motivated shrink from 24 → 4 automatically applied to wd. **This was a real behavior change for wd, not just for ws.**

Diagnostic run 2026-07-29 (`analysis/h_wd_l2_fire_rate.py`, splits pre-fix vs post-fix windows at obs_time 2026-07-28T00:00):

**Pre-fix (BLEND_HOURS=24):**
- 0-5h: fire 83%, conditional Δ_L2vsL1 +9.03° (+18.7%) — HELPED
- 6-11h: fire 90%, Δ −24.95° (−50.2%) — **HURT big** (stale obs blended at 54% weight)
- 12-23h: fire 85%, Δ −3.52° (−6.8%) — HURT mildly

**Post-fix (BLEND_HOURS=4):**
- 0-5h: fire 82%, Δ +11.27° (+24.7%) — **HELPS more** than pre-fix (shorter ramp leans harder at leads 0-3 without stale-blending 4+)
- 6-11h: L2 blend no longer touches. Fire counts at 62% are actually wdp firing (shares `wind_direction_pre_wd_gate` slot); the ~7% "hurt" is wdp's sw_flow 6-11 MARGIN cell, not L2.
- 12-23h: L2 no longer touches. Fire counts are wdp (calm 12-23 SHIP, expected −12% MAE — showing +5.3% conditional).
- 24-47h: never fires (correct).

**Persistence-skill scorecard (as of 2026-07-29): wd = MIXED (3 ADDS / 1 BEHIND at 0-5h skill −0.11).** This is FOSSIL — dominated by the pre-fix damage at 6-23h. Do NOT read as regression. Will drift positive over ~2 weeks as pre-fix rows age out. Predicted verdict shift: MIXED → ADDS VALUE around ~2026-08-11.

## Post-ship watch — reset to 08-11 (v0.6.384 changed the L2 shape for wd)

Triggers:
1. Spurious wd swing on wind card at short-lead (user-visible check)
2. `per_layer_mae_by_lead["wd"]["l2"]` flipping worse than `l1` after n>100 per lead (Fitter check, ~1 week to fill)
3. Calm-floor guard is top failure risk — if 3 mph is wrong (too low → noise leak, too high → gate too many cells)

Log per-cycle skip rate as proxy for whether the calm-floor is calibrated right.

## CLOSED CLEAN 2026-08-11

Watch (reset to 08-11 after v0.6.384 BLEND_HOURS shrink) closed clean. `h_wd_l2_fire_rate.py` post-fix window (obs_time ≥ 2026-07-28):

| band | fire% | MAE_L1_all | MAE_L2_all | Δ | MAE_L1_fired | MAE_L2_fired | Δ_fired |
|---|---|---|---|---|---|---|---|
| 0-5h | 65% | 46.16 | 35.44 | **−23%** | 45.52 | 29.11 | **−36%** |
| 6-11h | 6% | 48.79 | 48.94 | +0.3% | 36.88 | 39.50 | +7% |
| 12-23h | 8% | 52.82 | 52.65 | −0.3% | 38.61 | 36.55 | −5% |
| 24-47h | 0% | 53.59 | 53.59 | 0 | — | — | — |

Design intent delivered: help at short leads, don't hurt at longer leads. Calm-floor guard behaved (no spurious swings). Pre-fix fossil damage at 6-11/12-23h aged out; predicted MIXED → ADDS VALUE flip landed on schedule.

Reason to not re-widen BLEND_HOURS: the post-fix 6-11h fired subset shows +7% hurt when it does fire — so extending the ramp wouldn't be a free win. Current 4h ramp is at the sweet spot.

## Related
- [[feedback_l2_no_stage_gate]] — why we didn't Stage 0 this
- [[project_l2_as_observation_only]] — L2 = observation architecture (updated 07-20)
- [[wd_persistence_gate]] — complementary long-lead wd correction (Stage 2, 07-27 flip)
