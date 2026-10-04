---
name: feedback-shipped-flag-verify-effect
description: Shipping a flag flip is not the same as shipping an effect. Verify the mechanism actually fires on real data before declaring a ship done. Silent no-op state is possible when the flag is True but the data/config the flag gates is missing or malformed — and no loader/digest tool will flag it.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 393ff97d-5dfc-493b-a2fb-a7e2f400b4b7
  modified: 2026-09-29T16:34:52.331Z
---

# Shipping a flag is not the same as shipping an effect

**Rule.** After flipping a runtime flag, always verify the mechanism actually fires on live data. Loader silence + digest OK is not proof of firing. Check the pair-log for the expected attribution stamp within one deploy cycle.

**Why.** v0.7.5 (2026-09-26) flipped `LEARNED_SELECTOR_SHADOW_ENABLED = True` for the GBM per-obs classifier. For ch, the mechanism fired: `ims_threshold` cells wired correctly. For sr, the shipped curated JSON was empty, so the GBM path never fired — but nothing complained:
- The loader logs no warnings for a valid JSON with 0 cells
- The `..._SHADOW_ENABLED = True` flag was True — nothing to alert on
- The digest's `l1_selector_per_obs_classifier_stage1_v5` reported "9 STABLE cells" as ready to ship — the fitter said the mechanism was ready, but the shipped file was independent from what the fitter emitted
- Even mechanism-attribution telemetry (v0.7.7 `selector_mechanism` stamp), when it finally landed, was interpreted as "sr scope narrowed to ch-only" — the right observation (zero learned_gbm rows) framed as an intended scope reduction rather than a live no-op

The sr side of v0.7.5 was silently a no-op for **3 days** before it was caught. Fixed 2026-09-29 v0.7.15.

**Contributing failure mode this time:** the v5 candidate JSON's band field was `"12-23h"` (with `h` suffix); the runtime's band mapper returns `"12-23"` (no suffix). Even if the candidate had been copied verbatim, cells would have loaded without warning but never keyed correctly at lookup time — the same silent-no-op state.

## How to apply

After ANY flag flip on a runtime mechanism, before declaring the ship done:

1. **Grep the pair-log for the expected attribution stamp** on rows written after the deploy cutoff. If the mechanism has a `selector_mechanism` (or equivalent) field, filter by `run_time >= deploy_time` and confirm the mechanism value appears. Zero rows with the stamp = mechanism isn't firing, regardless of what the loader says.

2. **If the mechanism keys on (field, regime, band), verify the key schema matches the runtime lookup.** Candidate JSONs from analysis scripts may use display strings (`"12-23h"`, `"nw flow"`, etc.) while the runtime uses canonical forms (`"12-23"`, `"nw_flow"`). A silent lookup miss looks identical to "no covered cell" from the outside.

3. **Set a watch: overnight verification of a fresh runtime stamp.** For mechanisms that only fire on obs-side backstamped rows (short-lead: hours; long-lead: 12-47h), the pair-log won't show attribution until backstamps land. Schedule the verify.

4. **A digest verdict of "STABLE / promote" on a fitter does NOT verify the shipped table.** The fitter emits its own candidate; someone/something has to copy it into the shipped path AND get the schema right. Any friction in that step can leave a fully-approved analysis unwired.

## Symptoms this pattern produces

- Metric didn't improve after a "successful" ship
- Digest and logs both look clean
- Later dig finds "zero rows stamped with mechanism X since ship date"
- Team explanation drifts toward "scope was narrower than we thought" rather than "the mechanism isn't firing"

If any of those show up, check the shipped table + runtime lookup key schema before believing the "narrower scope" story.

## Related
- [[project_09_29_session]] — origin (v0.7.15 fix + diagnosis)
- [[project_09_28_session]] — the moment the gap was almost caught; framed as scope narrowing, missed the actual bug
- [[project_router_as_authority_pivot]] — v0.7.5 pivot memory should carry an update noting the 3-day silent no-op on the sr side
- [[feedback_cloud_run_logging_dropped]] — similar-class "shipped a thing that silently didn't work" trap (v0.6.620/621 `logging.info` dropped by Cloud Run)
