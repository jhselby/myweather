---
name: project-cloud-obs-kbvy
description: v0.6.134 shipped 2026-06-19 — KBVY METAR cloud obs added and blended (mean) with KBOS for cc/cl/cm/ch obs truth. Walk-forward read for L3/L4 whitelist promotion gated to ~2026-06-26 (7+ days of dual-source data).
metadata: 
  node_type: memory
  type: project
  originSessionId: e7a479cb-0418-4bd9-91ef-19777cc97612
---

## What shipped 2026-06-19 (v0.6.134)

- `weather_collector/fetchers/noaa.py:fetch_kbvy_obs` — KBVY now parses METAR sky condition into cloud_cover_pct + cloud_low/mid/high_pct (mirrors KBOS).
- `weather_collector/processors/daily_extremes.py:_gather_current_observation` — obs cloud fields now `_blend(kbvy, kbos)` (mean when both, single source when one missing, None when both missing).
- First-tick verified at 12:27 UTC: KBVY=0%, KBOS=75% high cirrus, obs_log carried blended `cloud_cover: 38`. End-to-end working.

## Why this matters

cc was the worst-corrected non-solar field on the 06-19 audit (raw MAE 30.3, L2 n/a, L3/L4 not whitelisted). cc/cl/cm/ch obs already flowed to the pair log but obs source was KBOS-only at 12 mi south. Thesis: single-source-at-12mi was too noisy/regime-biased for the walk-forward validator to clear the 3% L3 threshold; KBVY at 2.5 mi NW + KBOS mean should give the joiner a cleaner truth signal.

**Why:** Cloud cover is the biggest untapped MAE opportunity on the live report after solar (which is its own L5 workstream). No new architecture required — reuses existing joiner, fitter, and walk-forward validator.

**How to apply:** Don't open a parallel cloud workstream until the 06-26 read returns a verdict. If validator still says HOLD after dual-source data, escalate to L5 cloud_correction.py (mirror solar_correction.py) per [[feedback-hypothesis-promotion-pipeline]] stage 1.

## Pending gate: 2026-06-26 (Fri) — walk-forward read #1

Run the L3/L4 walk-forward validator after ~7 days of dual-source obs (deployed 06-19 ~12:27 UTC → 06-26 morning).

For cc and cl, does adding to L3_FIELDS beat the 3% threshold on held-out MAE? Does L4 beat the 2% threshold?

**If SHIP:** record verdict, schedule confirmation read for ~07-03 (7-window agreement per [[feedback-whitelist-promotion-gate]]). If 07-03 agrees, edit `decay_apply.py:69-70` to add cc and/or cl to the whitelists, bump version, deploy.

**If HOLD:** bias is regime-conditional, escalate to L5 cloud layer. Build `weather_collector/processors/cloud_correction.py` mirroring `solar_correction.py` and start at stage 1 of the hypothesis promotion pipeline.

## Architecture facts (current as of 06-19)

- L3_FIELDS = {ws, wg, ch, cm, pp}; L4_FIELDS = {ch} in `decay_apply.py:69-70`. Manual whitelist edits only — validator is advisory.
- Joiner already pairs cc/cl/cm/ch (`forecast_error_log.py:49-54, 110-112`); no joiner change needed.
- obs_log writes cloud fields when present (`obs_log.py:78-79, 91-96`); field-agnostic.
- "No fallback to model value" invariant preserved in the blend — joiner must never see forecast-vs-forecast pairs.

Related: [[project-correction-stack]], [[feedback-whitelist-promotion-gate]], [[feedback-hypothesis-promotion-pipeline]], [[project-walkforward-l3l4-validator]], [[project-l5-trajectory]].
