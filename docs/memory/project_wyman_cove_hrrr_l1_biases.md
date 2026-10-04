---
name: user-wyman-cove-hrrr-l1-biases
description: "Reference table of HRRR L1 raw systematic biases at Wyman Cove, measured 2026-08-21. Direction and magnitude persist across all lead bands — real coord-specific bias, not noise. Use when interpreting Prod vs raw comparisons."
metadata: 
  node_type: memory
  type: project
  originSessionId: 3686728f-c756-4644-9af6-ccbb2487150d
  modified: 2026-08-22T00:37:37.730Z
---

# HRRR L1 raw biases at Wyman Cove (2026-08-21 read)

Open-Meteo's HRRR/GFS raw output at Wyman Cove has real, direction-consistent biases across every lead band. Measured over 24h post-selector-arm window (~500 rows/field, all obs stations). Direction stable across 0-5h, 6-11h, 12-23h, 24-47h — this is coord-specific systematic bias, not noise.

| field | HRRR L1 mean bias | NBM raw mean bias | Notes |
|---|---|---|---|
| t | +1.0°F over | ≈0 | HRRR over-forecasts temperature. |
| h | −10% under | ≈0 | HRRR under-forecasts humidity ~10%. |
| dp | −2°F under | ≈0 | HRRR under-forecasts dew point. |
| sr | −60 W/m² under | +50 W/m² over | Both wrong, opposite directions. |
| ws | small (noise) | small | Roughly equal. |
| wg | small | small | Roughly equal. |
| wd | ~±20° (noisy circular) | ~±20° | Both noisy, roughly equal. |

**fc_std vs obs_std pattern:** HRRR raw fc-value spread is 2-4x observed spread for h and dp — HRRR over-diffuses, predicting too much variation. NBM's fc_std matches obs_std on t, h, dp closely — better calibrated.

**Why:** likely Open-Meteo's HRRR grid interpolation and/or 3km sub-grid smoothing → coastal microclimate effects (higher humidity, cooler than inland) aren't captured at Wyman Cove specifically. NBM CO 2.5km grib extract at the point captures them better.

## How to use this

- When Prod for h/dp is significantly better than raw HRRR at 7d, that's the correction stack (station bias Kalman blend + L3 lead-decay + L4 diurnal) eating the raw bias. Expected behavior.
- When Prod for h/dp/t is barely better than raw NBM, that's because NBM raw is already well-calibrated → little room for corrections to add value on the NBM side.
- If we see a NEW field-level bias emerge in raw HRRR that wasn't here (magnitude changes significantly), that's a signal to check Open-Meteo grid drift.
- **Don't add pooled bias corrections to already-calibrated fields.** The 08-21 dp L3_NBM incident was exactly this — L3_NBM subtracted +1°F pooled bias from NBM dp that was already bias-≈0, worsening every regime. HRRR's L3_FIELDS excludes dp for the same reason.

## Related memory

- [[08-21-late-night-handoff]] — the session that measured this.
- [[nbm-structural-completion-plan]] — post-completion, this table informs how to read Prod-vs-raw comparisons.
