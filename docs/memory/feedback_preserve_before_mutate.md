---
name: feedback-preserve-before-mutate
description: "When shipping a new correction layer that mutates a shared hourly array (like direct_radiation, cloud_cover, precipitation, wind_direction), the raw copy (raw_direct_radiation, raw_cloud_cover, etc.) MUST be preserved BEFORE the mutation runs. The preserve-in-decay_apply.py pattern is wrong if the new layer runs before decay_apply. L5 solar sat with this bug for a week (2026-06-28 → 2026-07-02) — the debug page's Raw model line for sr showed L5-corrected values, and Production for sr appeared identical to raw."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 56248ef4-af78-48a9-998a-163e8a07965d
---

**The rule.** Every new correction layer that mutates a shared `hourly[<field>]` array must do one of:

1. Run AFTER `decay_apply.preserve_raw_forecast_arrays()` is called (currently at `collector.py:322-ish`, before `stamp_solar_correction`), OR
2. Do its own inline preserve BEFORE its mutation (like `cloud_obs_blend.py:88` does for cc/cl/cm/ch), OR
3. Add its target array name to the tuple inside `preserve_raw_forecast_arrays`.

Audit every new correction layer against this at ship time.

**Why.** Downstream diagnostic code assumes `raw_<field>` holds the actual raw HRRR/GFS value. If a correction mutates `<field>` before the raw is preserved, the raw copy will hold the post-correction value. This has three symptoms, ranked by user impact:

- **Debug page "Raw model" line becomes wrong.** Shows corrected values as if they were raw.
- **Production accumulator can't tell the difference between raw and the corrected layer.** Both use the same numeric value; `error_l1` in the pair log equals the corrected error.
- **User-facing forecast is unaffected** — the `<field>` array is still post-correction as intended.

L5 solar shipped 2026-06-28 v0.6.248 with `stamp_solar_correction` on `collector.py:322`. `raw_direct_radiation` was preserved on line ~459 inside `apply_decay_corrections`. L5 ran first, mutated `direct_radiation`, then decay_apply captured the mutated value as "raw."

Bug lived for ~1 week. Would have persisted longer, but Joe screenshot showed sr Production line == raw line at every lead while L5 line was clearly lower. Debug traced it to snapshot values `sr_l1 == sr_l5` at every daytime lead, `sr_l4` holding the true raw. Fix in `v0.6.285`: extract preserve to a standalone function `preserve_raw_forecast_arrays()` and call it from `collector.py:322` BEFORE any correction runs. Also called from `apply_decay_corrections` (idempotent — guarded by `dst not in hourly`).

**How to apply:**

- When adding a new correction layer to the pipeline, check where `preserve_raw_forecast_arrays()` is called in `collector.py`. If your new layer runs before it, either move your layer after, or extend the preserve list.
- Same lesson for `direct_radiation_post_l4`, `corrected_temperature_post_l4`, and any other "post-<layer>" preservation. Every such preservation must happen at the exact right point in the pipeline; a shift in call order corrupts the diagnostic view.
- Sanity check post-deploy: fetch `weather_data.json` and check `hourly[i]` values for the new correction's field. For a lead where the layer fires with non-zero delta, `raw_<field>[i]` and `<field>[i]` should differ by the delta. If they're equal, the raw is polluted.

**How the fix should look on the debug page.** For the sr case, the first daytime tick post-deploy should show `sr_l1 != sr_l5` in the snapshot (with `sr_l1 = sr_l4 = raw HRRR`, `sr_l5 = raw - delta`). If they're equal at daytime with a non-skip regime, the fix didn't land. Nighttime ticks are ambiguous (L5 delta = 0 whether or not the fix is in) — can't verify from a nighttime snapshot alone.

**Related patterns**:
- [[feedback-hybrid-transition-pattern]] — same "backend key that fills over rolling window" theme, but for a different class of bug (transient sparse data, not schema pollution)
- [[project-07-02-session]] — the session where this bug was found and fixed
- [[project-l6-l2-double-counting-hypothesis]] — different mechanism but same principle: a correction that operates against a polluted baseline will systematically miscalibrate
