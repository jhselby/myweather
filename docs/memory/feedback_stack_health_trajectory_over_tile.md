---
name: feedback-stack-health-trajectory-over-tile
description: "When the Selector Skill 24h tile and the Stack Health trajectory chart disagree, the trajectory wins. The 24h tile is a routing-only sub-metric that swings on small-n and single-day regime shifts; the trajectory is aggregate Prod vs 90d-ref raw across 12 fields."
metadata: 
  node_type: memory
  type: feedback
  modified: 2026-09-26T11:33:27.748Z
  originSessionId: b263e9cd-d969-4acf-add7-b0c4f9f5625c
---

# Stack health trajectory > Selector Skill 24h tile

## Rule

When the Selector Skill 24h tile says the selector is bleeding and the Stack Health trajectory chart shows the 7d rolling median holding or climbing, **the trajectory wins**. Do not start a diagnosis loop off the 24h tile alone.

## Why

- The 24h tile is a routing-only sub-metric (Value Captured of what a perfect picker could have gotten). It swings hard on:
  - Small n (~700 rows per field, one bad regime afternoon dominates).
  - Regime shifts that flip a per-obs cell against truth for a day.
  - Tied-row math noise (sr has ~50% ties → tiny denominators).
- The Stack Health trajectory is aggregate `(1 − prod_MAE / raw_MAE_90d_ref) × 100` across 12 fields per obs-day. Fixed 90d-ref baseline absorbs daily weather difficulty. Prod moves are the only thing that move it.
- If Prod is up on 7d rolling, THE STACK IS WINNING regardless of what any single tile says about the pick.

Documented instance 2026-09-26: v0.7.5 deploy morning, 24h Selector Skill slid −33% → −44.8% median over 90 minutes. I proposed opening a diagnosis. User showed the trajectory chart: 7d rolling median ~30%, trend +1.60pp/week UP. The stack was fine. The diagnosis would have been chasing regime noise.

## How to apply

Before starting a "why is the selector bleeding" investigation:

1. **Look at the Stack Health trajectory 7d rolling first.** If it's up or flat, the tile is noise — stop.
2. **Only investigate if trajectory is trending DOWN over the last 3-7 days.** A single-day dip is regime, not disease.
3. **v0.7.5-class ships take 24h+ to show up in the 24h tile** (23 of 24 window hours are pre-deploy immediately after ship). Post-deploy tile moves in the first hour are pre-existing data rolling around; the ship cannot be the cause.

Related: [[feedback_scorecard_lag_vs_accuracy_chart]] (same species — scorecard lags real metrics), [[project_selector_recency_override_watch]] (the 09-11 recency-override checkpoint documented the same 24h-vs-7d divergence).
