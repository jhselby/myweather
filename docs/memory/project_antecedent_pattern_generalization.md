---
name: project-antecedent-pattern-generalization
description: "07-28 post-reboot findings on how the antecedent-error-based gate pattern (v0.6.387 dpbp, v0.6.388 wsbp) generalizes across fields. Two null results captured: (1) pp antecedent = NULL (per-regime lag-1 near-zero or negative for pre_frontal / sea_breeze), (2) ws under-forecast regimes = NEGATIVE Stage 1 (nw_flow / pre_frontal / sw_flow all HURT despite moderate lag-1 correlation). Pattern only ships when the model has a stable systematic bias in one direction; event-driven bias breaks it. Blocks future wasted probes on other fields with similar shape."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9463fe7b-3db7-4c49-86b6-9979ab35e0e0
  modified: 2026-07-28T18:01:44.660Z
---

## What generalizes

The antecedent-error gate pattern (v0.6.387 dpbp + v0.6.388 wsbp): use the previous 24h of `forecast_l1 - observed` per-regime mean bias to gate + magnitude a correction on today's forecast at leads >= 6.

**Ships when:** the model has a stable systematic bias in one direction that persists day-to-day for the regime. Correction sign is (opposite of) bias sign.

**Does NOT ship when:**
1. Per-regime lag-1 r is weak or negative (bias doesn't persist)
2. The bias is event-driven — a few big events dominate the pool but most days are quiet; correction over-corrects on quiet days

## Field-by-field verdict from the 07-28 probes

### dp — SHIPPED (v0.6.387)

- Pooled lag-1 r = **+0.583** (strong)
- pre_frontal / nw_flow / sw_flow all show consistent negative bias (~−2°F under-forecast) with moderate-to-strong lag-1
- Stage 1 halves-verified all 3 regimes: pooled +9.63%, per-regime +14 to +17%
- Ship: fixed +2.0°F correction (approximates -median(prev_bias)) at leads >= 6

### ws — PARTIAL SHIP (v0.6.388)

- Pooled lag-1 r = **+0.470** (moderate)
- **Ships: calm regime only** (r=+0.706, +2.35 mph over-forecast, Stage 1 +11.07% halves +13.35/+10.33)
- **Dropped: ne_flow** — Stage 1 SHIP by numbers (+10.91%) but recent-half 0 fires → fragile
- **Under-forecast regimes HURT:** nw_flow (−11.29%), pre_frontal (−1.47%), sw_flow (−6.93%). Physical read below.

### pp — NULL RESULT

- Pooled lag-1 r = **+0.313** (weak-moderate, but hides per-regime structure)
- Per-regime lag-1:
  - nw_flow +0.257
  - calm +0.197
  - **pre_frontal −0.026** (essentially zero)
  - **sea_breeze −0.094** (near-zero)
- Two of the four biggest regimes have zero or slightly negative lag-1 → antecedent correction cannot ship
- **Physical read:** precip is more chaotic / event-driven than a moisture-state field like dp. Yesterday's precip miss is not predictive of today's precip miss.

## The "over-forecast vs under-forecast" split

Empirical from ws Stage 1:
- **Over-forecast regimes (calm +2.35, ne_flow +1.58)** — antecedent gate WORKS. Physical: model over-forecast is a stable systematic error (model reads wind that isn't there, station reports calm). Same-shape error repeats day-to-day; subtracting works.
- **Under-forecast regimes (nw_flow, pre_frontal, sw_flow all ~−1 mph)** — antecedent gate HURTS. Physical: under-forecast is event-driven (missed gusts, missed pickups). A constant "yesterday's negative bias" correction over-corrects on quiet days.

**Rule for future antecedent probes:** always split by regime bias SIGN before deciding if the pattern applies. Pooled positive bias with moderate lag-1 is a much more tractable target than pooled negative bias with moderate lag-1.

## What fields to try next (or not)

- **wg** — likely follows ws pattern (over-forecast in calm might work, under-forecast in flow regimes might not). Worth a probe but expect similar partial result.
- **t** — station_bias.py already does Kalman-tracked L2 correction (per-station chronic offset from local consensus). The antecedent pattern would likely be redundant.
- **h** (humidity) — station_bias.py covers this too via L2.
- **pr** (pressure) — station_bias.py covers this too. Also model pressure is usually very accurate at forecast time.
- **cc / cl / cm / ch** — worth probing. Cloud cover has both systematic biases (MLC seasonal) and event-driven components. Might have a shippable subset.
- **sr** — unit-mismatch trap still open. Do NOT probe until [[project_sr_unit_mismatch]] resolves.
- **wd** — circular; would need vector antecedent. Deferred until dp/ws watches close.

## Blocked / do-not-repeat probes

- **pp regime-conditional antecedent** — probed 07-28, NULL. Do not re-run without new signal.
- **ws under-forecast regime antecedent** — probed 07-28, NEGATIVE. Do not re-run under same architecture. If we want to catch these misses, need a different mechanism (event-conditional / gust detector).

## Related

- [[project_07_28_post_reboot]] — full arc
- [[project_hypothesis_backlog]] — #6 closed via dpbp; #7 still open
- [[preflight_dpbp]] / [[preflight_wsbp]] — flip preflights
- [[feedback_persistence_gate_shadow_write]] — invariant both gates honor
