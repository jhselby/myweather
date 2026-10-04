---
name: nbm-structural-completion-plan
description: "Plan-of-record for the ~3 sessions of structural work to close the NBM cascade to feature parity with HRRR, so the whole project returns to purely tuning mode."
metadata: 
  node_type: memory
  type: project
  originSessionId: 59e82d06-cdfb-4ebe-9ff9-4ea3ac9e7b83
  modified: 2026-08-21T16:32:53.920Z
---

# NBM structural-completion plan — return to tuning mode

**Context:** As of 2026-08-21 the NBM parallel cascade is layer-complete (L1→L6 + wdp/chp specialists all shipped shadow-live or scaffolded). Selector picks 9 cells (cc all leads, dp 6-47h, wg 12-47h). Router-scope ship-gate lift +53.3% on n=75,023.

Before NBM, the project was purely tuning HRRR — Stage 3 flips, cell adds/drops, walkforward re-runs. NBM broke that by introducing a second cascade that lacks HRRR's monitoring / earn-your-way / dormancy scaffolding. This plan closes those gaps.

## Blockers (must ship before "back to tuning" is true)

### F3: Full NBM audit
The audit Joe queued during 08-21 debug page sweep. Walk the whole NBM pipeline end-to-end, confirm plumbing, catch anything missed. Natural checkpoint before the sentry / walkforward work — cheaper to catch a wiring mistake now than after building sentries on top of it. **Do first.**

### F1: Per-NBM-layer regression sentry
HRRR has one (regression sentry, post-ship 14-day watch, layer-shape sentry). NBM has none. Without it, a degrading L4_NBM cell won't page anyone until scoreboard hurts.

Design: mirror `analysis/anomaly_detector.py`'s pattern but keyed on `error_l3_nbm` / `error_l4_nbm` / `error_l5_nbm` / `error_l6_nbm` / `error_chp_nbm` / `error_wdp_nbm` columns. Sustained 7d vs fresh 3d, hot ≥15%. Emit into digest under a "NBM regression sentry" section.

### F2: NBM walkforward validator
HRRR uses `walkforward_l3l4_validator.py` to drive earn-your-way `L3_FIELDS` / `L4_FIELDS` membership. NBM has no equivalent — today `L3_NBM_FIELDS`/`L4_NBM_FIELDS` are hand-set. Blocks the "drop cc from L4_NBM if it stops earning" cycle.

Design: mirror walkforward pattern but score against `_nbm_prod_error` walker (l6>l5>l4>l3). Emit proposed L3_NBM_FIELDS / L4_NBM_FIELDS set daily; digest SHIP-ELIGIBLE section reports divergence from live.

## Should-haves (tuning works without them but with blind spots)

### F4: Gate-firing telemetry for NBM layers
HRRR L3/L4 write to `gate_firing_log`. NBM writes nothing. `gate_firing_rollup` therefore can't audit NBM. Add `record_firing(operator="L4_NBM", ...)` calls inside the NBM apply blocks in `forecast_snapshot.py`, mirroring the HRRR pattern in `decay_apply.py`.

### F5: Skip-table gate for NBM
HRRR uses `_should_skip(short, "l4", regime, lead)` for per-cell dormancy. NBM applies to every cell in its whitelist. When we find a bad NBM cell we can only drop the whole field, not the cell.

Design: add `_should_skip_nbm(short, layer, regime, lead)` reading a new `skip_table_nbm_curated.json`; call from each NBM apply block; wire into walkforward (F2) so bad cells auto-add.

### F6: PWA writeback trace
Confirm the selector's `entry[f] = ...` in the snapshot dict actually flows to `hourly[array_name]` the PWA reads. Possibly already works via a write path not yet traced; possibly a real gap that means the PWA is showing HRRR-only values while the pair log records NBM Prod. **One investigation session** — grep `hourly[cloud_cover]` writes, confirm end-to-end.

## Nice-to-haves (won't block tuning; cosmetic)

### F7: Applicability map entries
`describe_applicability()` per NBM module (l4_nbm.py, l5_nbm.py, l6_nbm.py) so the debug page applicability card shows them. HTML side already reads `weather_data.applicability_map.layers` correctly.

### F8: Per-field caps + staleness gates
HRRR has both. NBM's domain clamp (v0.6.450) is a safety floor for now. Add `CAPS_NBM` per-layer + `fitted_at` age check.

## Recommended sequence

**Session 1:** F3 (audit) — grounds the rest.
**Session 2:** F1 (sentry) + F2 (walkforward) — most valuable, together they restore the earn-your-way + regression-alert loop for NBM.
**Session 3:** F4 + F5 batched — gate telemetry + skip-table. Same file surface (`forecast_snapshot.py` NBM blocks).
**Session 4:** F6 (PWA writeback confirm). Investigation, then a fix if needed.
**Later, as they come up:** F7, F8.

Total ~3-4 focused sessions to close.

## Related memory
- [[08-21-evening-handoff]] — the session-close that queued this plan.
- [[nbm-parallel-pipeline-plan]] — the shipped plan of record (superseded — cascade is now built).
- [[08-21-morning-handoff]] — mid-session state before L6/chp/audit work.
- [[feedback-answer-direct-first]] — why the earlier session logged this as a plan instead of a menu.
