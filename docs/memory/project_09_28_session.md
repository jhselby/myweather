---
name: project-09-28-session
description: "3 ships committed: v0.7.7 (from 09-27) + v0.7.8 (regime-source fix in forecast_snapshot) + v0.7.9 (CHP_CELL_GATE_ENABLED=True). sr −77% 24h audit-triggered but router NOT the cause — L3_nbm sr / nor_easter downstream correction miscalibration on new regime. Held on emergency skip (n=39 too thin). Debug page swept and version.json bumped. All pushed."
metadata: 
  node_type: memory
  type: project
  originSessionId: a4f0acc7-44c2-4729-a282-4d308df9a657
  modified: 2026-09-28T20:33:49.189Z
---

# 2026-09-28 Monday session — 3 ships (v0.7.7/v0.7.8/v0.7.9) + sr diagnosis + debug sweep

## Ships (all committed + pushed)

**Commit 70cf2cda** — v0.7.8 + v0.7.9 (Joe deployed both, verified fresh GCS ticks):
- **v0.7.8 (`forecast_snapshot.py`)** — regime-source reconciliation. Moved `_fc_regime_i` and `_valid_hour_local_i` above the field loop; classify inline from `entry.get("wd"/"ws"/"pr"/"cc"/"t")` + snap-level pressure_trend + local valid-hour, mirroring `forecast_error_log.py`'s exact classification call (with cloud_cover). Fixes the off-curated stamping bug (78/93 rows landing on nor_easter cells not in curated JSON). Flows to `_learned_predict`, `_blender_omega`, `_l1_static_blend.blend_l1`, `_selector_pick_source_with_mech`. `_wdp_state_fc_by_lead` still consumed by `wd_persistence_gate` — different concern, not touched. Deploy 08:02:57 EDT, first tick 08:07 clean.
- **v0.7.9 (`ch_persistence_gate.py`)** — `CHP_CELL_GATE_ENABLED = True` (one-line flip). Digest 09-28 h_chp_cell_gate cleared 9 cells with days_lose=7/days_win=0: ne_flow/6-11, ne_flow/12-23, ne_flow/24-47, nw_flow/12-23, nw_flow/24-47, pre_frontal/12-23, pre_frontal/24-47, se_flow/12-23, se_flow/24-47. 4 overlap _CELL_SKIP; 5 dynamic-only new. Reversal: flag back to False; static _CELL_SKIP retained. Deploy ~11:20, first tick 11:27 clean.

**Commit 91c85048** — debug page 09-28 sweep (Recent Activity, Upcoming, Post-ship watches, L1 blender tile).

**Commit 1bb33108** — `version.json` v0.7.7 → v0.7.9 (had been lagging; debug page header reads from it).

## Real finding — sr audit trigger CLEARED

09-27 scheduled watch fired: sr −77% on 24h scorecard (was −68% yesterday), audit trigger per plan. Investigated router:

**Router is NOT the cause.**
- Post-v0.7.7-deploy sr rows (filter by `run_time`, not `valid_time`): 100% stamped `band_pool`, zero `learned_gbm`.
- v0.7.5 sr GBM path never fires because `l1_learned_selector_curated.json` has no sr cells (curated set was never populated; only ims_threshold cells for ch shipped).
- Yesterday's "75% unstamped" was pre-deploy snapshots being closed by fresh observations — legacy, not a plumbing bug. Filter by `run_time` to isolate post-deploy.

**Culprit: L3_nbm sr correction on new nor_easter regime.**
- Per-layer breakdown (48h nor_easter): raw_nbm 5.6-15 W/m² (clean), L2_nbm ≡ raw_nbm (correct), L1(HRRR) 15-40 (twice as bad), prod lands in-between → L3_nbm inflates error on low-solar.
- Corroborated by nbm_regression_sentry: `sr.l3_nbm HOT — layer help +5.8% → −1.9%, Δ +7.6pp`.
- Nor'easter regime is NEW since ~09-26; L3_nbm was calibrated on regimes with normal solar.

**Held on emergency skip.** n=39 on 0-5h too thin, other bands <20 rows, halves-stable impossible, nor_easter transient. Per feedback_fresh_fire_lucky_baseline_artifact discipline. Wait for regime to accumulate n≥200/band; walkforward already lists pre_frontal/12-23h and nw_flow/24-47h for l3_nbm sr — nor_easter will join naturally.

## Correction to 09-27 framing

- **v0.7.5 10-03 verdict is really ch-only** (via `ims_threshold`). Sr never touches the router. Attribute per-mechanism using v0.7.7's stamp.
- **v0.7.6 apply-flip target 10-03 not on track.** First shadow retro (09-28): 0 SHIP-READY / 11 HOLD / 4 KILL / 13 THIN on 20 curated cells. Curated cells may be stale-fit like v0.7.2 was; needs refit on post-v0.7.8 data before another flip attempt.

## Session lessons

1. **Filter pair-log by `run_time`, not `valid_time`, when isolating post-deploy effects.** Legacy snapshots close against fresh obs and confound mechanism attribution. Cost ~30 min of "why is 75% unstamped?" before I filtered right.
2. **When a router audit fires, verify the router ACTUALLY made the pick before rolling back.** The mechanism stamp is source of truth; zero `learned_gbm` rows means the router never entered the picture.
3. **Two callers computing the same regime independently is a divergence trap.** state_stamp built regime from raw hourly[] (no cloud_cover); forecast_error_log built it from target_hour (with cloud_cover). Any shared classifier call should read a single stamped value or share a helper.
4. **`stagnant_high` regime can ONLY appear in the pair-log path** — the classifier's stagnant branch requires cloud_cover, which state_stamp's per-lead call omitted. Not the primary bug today (nor_easter drove it via pressure/wind divergence), but same class.

## Non-goals held

- Did NOT roll back v0.7.5. Evidence pointed elsewhere.
- Did NOT ship an emergency nor_easter skip on n=39. Fresh-fire lucky-baseline discipline.
- Did NOT hand-edit curated selector JSONs. The data is right; the plumbing wasn't.

## Files touched

- `weather_collector/processors/forecast_snapshot.py` (+ import for classify_synoptic_regime, moved regime compute out of field loop, classify from entry values)
- `weather_collector/processors/ch_persistence_gate.py` (`CHP_CELL_GATE_ENABLED = True`)
- `index.html` v0.7.7 → v0.7.9
- `version.json` v0.7.7 → v0.7.9
- `docs/CHANGELOG.md` (v0.7.8 + v0.7.9 entries at top; v0.7.7 closed)
- `corrections_debug.html` (Recent Activity + Upcoming + Post-ship watches + L1 blender tile)

## Watches

- **Tue 09-29:** run `analysis/l1_static_blend_shadow_verify.py` on ~24h post-v0.7.8 rows; off-curated stamp ratio should drop ~84% → near-zero. If not, entry values still diverge from target_hour somewhere.
- **Fri 10-03:** v0.7.5 verdict (ch-only, per-mechanism attribution via selector_mechanism stamp). v0.7.6 shadow retro re-run on post-v0.7.8 data — if halves still don't clear, redo curation on fresh pair-log.
- **Mon 10-05:** v0.7.9 chp gate 7d verify — `h_ch_persistence_blend_stage2_vs_l6` WATCH count should drop from 4 to ≤1. If not, one dynamic-only cell has Simpson-paradox artifact; revert.
- **Ongoing:** nor_easter regime sr watch. L3_nbm sr / nor_easter losing to raw_nbm. When regime accumulates n≥200/band, walkforward proposes skip cleanly in its normal 14d+50d cycle.

## Related
- [[project_09_27_session]] — v0.7.7 telemetry stack (framing superseded)
- [[project_l1_static_blend_v076]] — v0.7.6 shadow retro first read shows apply-flip not on track
- [[project_router_as_authority_pivot]] — v0.7.5 verdict now scoped to ch-only
- [[project_chp_narrow_to_0_5h_watch]] — v0.7.9 delivers on this ship candidate via dynamic gate instead of hand-curated 0-5h-only
- [[feedback_fresh_fire_lucky_baseline_artifact]] — cited for holding sr skip
