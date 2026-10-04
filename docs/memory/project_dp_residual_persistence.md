---
name: project-dp-residual-persistence
description: dp residual persistence gate. SHIPPED 07-25 v0.6.380 Stage 3 wire ENABLED=False. Flip gate closed 08-01 HOLD — cell set collapsed 8 SHIP → 3 SHIP + 1 MARGIN. Re-arm 7-day gate on the narrowed 3-cell shape (nw_flow/24-47, sw_flow/12-23, sw_flow/24-47). ENABLED stays False.
metadata: 
  node_type: memory
  type: project
  originSessionId: 6eaa9453-6bb5-43c6-a502-11181da39f47
  modified: 2026-08-01T11:15:45.078Z
---

# dp residual persistence — Stage 3 wired 2026-07-25 v0.6.380

## Status — 2026-08-01 HOLD

7-day flip gate closed. **HOLD** — cell set collapsed from original 8 SHIP + 2 MARGIN to today's 3 SHIP + 1 MARGIN. Jaccard well below 0.8. Curated JSON regenerates each digest cycle from `h_dp_residual_persistence_stage2.py`; today's SHIP set is nw_flow/24-47, sw_flow/12-23, sw_flow/24-47 (stable across window) plus frontal/12-23 MARGIN (thin, n=426).

**Next action:** re-arm 7-day gate on the narrowed 3-cell shape. Earliest flip 2026-08-08 if the 3-cell set stays stable across 7 daily reads. ENABLED remains False.

## Original ship

**Shipped Stage 3 2026-07-25 v0.6.380, ENABLED=False.** 7-day live-layer flip gate scheduled to close 2026-08-01. Original SHIP set: 8 cells.

`weather_collector/processors/dp_residual_persistence.py` — cloned from `wg_residual_persistence.py`. Runs AFTER `wg_residual_persistence` in the specialist stack in `collector.py`. Where the gate fires, replaces post-L3 dp with `fc_l2 + hour_of_day_correction`. Preserve-before-mutate pre-key `corrected_dew_point_post_l3_pre_dprp`. Sanity clamp `_MAX_ABS_CORRECTION_F = 10.0` (Stage 2 fit range is |≤3.15|°F — clamp is a data-pathology guard).

Post-deploy first-tick verify (calm regime, no SHIP cells for dp): 47 correct skips, 0 fires — telemetry stamping healthy.

## Gate shape (Stage 2 preview, 07-22 v0.6.372d)

Rollup: **8 SHIP / 2 MARGIN / 26 SKIP / 1 THIN of 37 judged.**

SHIP cells (best 5 bold):
- **sw_flow 24-47h −18.46%**
- **sw_flow 12-23h −16.87%**
- **frontal 24-47h −14.09%**
- **sw_flow 6-11h −12.03%**
- **pre_frontal 24-47h −10.73%**
- pre_frontal 12-23h −8.34%
- nw_flow 24-47h −6.83%
- se_flow 24-47h −6.43%

MARGIN cells: nw_flow 12-23h −5.26%, se_flow 12-23h −5.68%.

**Structural finding: zero SHIP at 0-5h in any regime.** Same long-lead-only shape as wg — L2/Kalman close-in dominance means short-lead residual persistence re-introduces stale bias.

## Registrations (same-commit per v0.6.378 rule)

- `analysis/runlog/build_executive_summary.py` `KNOWN_LIVE_PIPELINES`: `h_dp_residual_persistence_stage2` — relabels action verbs to STABLE.
- `analysis/gate_firing_rollup.py` `EXPECTED_DORMANT_OPERATORS`: `dp_residual_persistence` — suppresses spurious Day-0 UNEXPECTED alert.

## Debug page (corrections_debug.html)

Full sweep in v0.6.380 commit:
- Section D layer stack card (green-bordered, after wg card).
- Calendar row: Sat 08-01 flip decision.
- Stage 3 gated table row + row count summary bumped 5 → 6.
- Specialists list `<li>` after wg entry.
- Recent activity 07-25 (Sat) entry with both v0.6.380 items.

## Next

**Flip decision Sat 08-01.** Gate criteria (same as wg per [[feedback_whitelist_promotion_gate]]):
- 7-day agreement — Jaccard ≥ 0.8 on SHIP-set week-over-week (streak walker per [[feedback_streak_walker_robustness]]).
- Halves stability on all SHIP cells (no A/B sign flips).
- Post-flip 14-day watch through ~2026-08-15.

Weekly re-run of `h_dp_residual_persistence_stage2.py` (auto in digest) governs cell-set stability + refreshes the 24-slot hour-of-day corrections. Any halves sign-flip in a SHIP cell demotes it to SKIP.

## Files

- `weather_collector/processors/dp_residual_persistence.py` — Stage 3 processor.
- `weather_collector/data/dp_residual_persistence_curated.json` — Stage 2 cell verdicts + 24-slot hour-of-day correction table (refreshed each Stage 2 run).
- `analysis/h_dp_residual_persistence_stage2.py` — Stage 2 preview generator.
- `analysis/h_dp_residual_persistence_stage1.py` — Stage 1 (07-21 STAGE 1 PROMOTE: test MAE +11.14%, 4/6 regime WIN, halves both positive).

Related: [[project_wg_residual_persistence]], [[feedback_hypothesis_promotion_pipeline]], [[feedback_regime_gate_first]], [[feedback_whitelist_promotion_gate]].
