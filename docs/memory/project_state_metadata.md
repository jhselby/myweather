---
name: state-metadata-on-pairs
description: Conditional state infrastructure (v0.6.29) — every pair carries state_fc + state_obs dicts for future stratification analyses. Foundation for Research-section hypothesis work.
metadata: 
  node_type: memory
  type: project
  originSessionId: b64b54ae-d13f-48c0-b164-388979caa9c3
---

Every pair row in `forecast_error_log.jsonl` post-v0.6.29 carries two metadata dicts:
- **`state_fc`** — forecast-side state at snapshot time, pulled from snapshot's target_hour (L2-stage values via legacy top-level keys) + snapshot-level metadata
- **`state_obs`** — observed-side state at obs time, pulled from `obs_temp_log` entry

## Fields captured

In `state_fc` (forecast snapshot time):
- wind_speed, wind_dir, solar_wm2, cloud_cover, cloud_low/mid/high, pressure_in, precip_in
- pressure_trend_hpa_3h (snapshot-level, same for all pairs from one snapshot)

In `state_obs` (observation time, from `obs_temp_log`):
- wind_speed, wind_dir, solar_wm2, cloud_cover, cloud_low/mid/high, pressure_in, precip_in, humidity, temp

## Purpose

The Fitter does NOT currently aggregate by these fields. They're logged for future Research-section stratification analyses — answer questions like:
- "Is temp forecast bias different when wind is from NW vs SE?"
- "Does humidity forecast accuracy degrade more on sunny vs overcast days?"
- "Is precip POP miscalibrated under specific pressure-tendency regimes?"

## How to apply

When implementing new conditional state analyses, the data is already there going back to ~2026-06-03 evening (v0.6.29 deploy). For each pair row, both `state_fc` and `state_obs` are dicts that can be used as stratification keys.

The next natural extension is a **wind regime classifier** that derives a categorical regime label (NW flow / SE flow / sea breeze / calm / frontal / pre-frontal) from wind_dir + wind_speed + pressure_trend + temp delta. Stamps into pairs as `state_obs.regime`. That'd be the cleanest first state-stratified analysis.

Related: [[correction-stack-architecture]] (overall pipeline), [[layer34-over-correcting-watch]] (what state stratification might explain).
