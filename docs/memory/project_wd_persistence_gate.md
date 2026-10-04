---
name: wd-persistence-gate
description: "wdp — wd predicted-transition persistence specialist. FLIPPED 2026-07-27 v0.6.382 (5 SHIP cells). 14-day post-ship watch CLOSED CLEAN 2026-08-11 (Δ −2.7% aggregate n=16,416)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6eaa9453-6bb5-43c6-a502-11181da39f47
  modified: 2026-08-13T00:06:12.548Z
---

# wd persistence gate (wdp)

## Status (2026-08-12) — CLOSED CLEAN

FLIPPED 2026-07-27 v0.6.382 (5 SHIP cells: calm 12-23 / 24-47 / 0-5, se_flow 0-5, sw_flow 0-5). 14-day post-ship watch CLOSED CLEAN on 2026-08-11 in v0.6.401f: aggregate Δ −2.7% on n=16,416, and 07-31 outlier cells (calm/24-47 wdp +72%, sea_breeze/0-5 wdp +109%) did not recur. Debug-page metric was correct throughout — [[wd-applied-layer-stamp-fix]] (v0.6.400) affected only the Fitter fallback, not mae_over_time's `L1_ONLY_FIELDS` branch. Debug-page wd row narrative + What's-running list + Layers section updated 2026-08-12 to remove stale "closes 08-10 / day X/14" text.

## Original status (2026-07-26)

- Processor: `weather_collector/processors/wd_persistence_gate.py` — drafted 2026-07-20 v0.6.365, ENABLED=False.
- Stage 2 preview: **5 SHIP + 1 MARGIN** cells (calm 12-23/24-47, pre_frontal 0-5, se_flow 0-5, sw_flow 0-5 SHIP; sw_flow 6-11 MARGIN).
- Flip decision: earliest **2026-07-27** (7-day narrow-promote gate + cell-set stability).
- Preflight patches: `docs/preflight/wdp_ship_patches.md` — 7 sites of exact copy-paste. Drift-verified 2026-07-25: 95% still valid.

## Preflight drift verification (2026-07-25)

All 7 sites' `old_string` text-anchors still grep-unique. Line numbers drifted 1-100 lines due to intervening ships (v0.6.371 → v0.6.380b).

**Material update applied** to preflight doc: **SITE 1** insertion point moved from "after line 568" → "after line 582" because v0.6.380 (2026-07-25) inserted `stamp_dp_residual_persistence` between wg and the applicability map. Applicability-map tuple at ~line 600 now contains `_da_dprp` — wdp slots alongside it.

**Line-drift only (patches unchanged):**
- SITE 2: `"wd":` layers dict 146 → 147
- SITE 3a: `_derive_applied_layer` tuple 179 → 180
- SITE 3b: `if field == "wd":` 208 → 210
- SITE 5: decay_fit.py tuples ~685/~1162 → 692/1174 (grep still returns exactly 2 matches per contract)
- SITE 6a-e: debug page anchors drifted ~30-100 lines across v0.6.375a/v0.6.379a/v0.6.379b/v0.6.380a/v0.6.380b sweeps; all grep-findable
- SITE 7b: L1_ONLY_FIELDS branch 121-127 → 135+ (structure intact)

## Fire condition

`state_curr.regime_synoptic != state_fc.regime_synoptic[lead]` AND `(state_fc.regime[lead], lead_band)` in SHIP/MARGIN.

`state_curr` = `derived.state.regime_synoptic` (current tick).
`state_fc.regime[lead]` = `classify_synoptic_regime` on hourly forecast at that lead.

## Composed-gate MAE reductions (Stage 2)

    calm 12-23    −12.31%
    calm 24-47    −19.71%
    calm 0-5       −4.56%
    se_flow 0-5   −12.19%
    sw_flow 0-5   −26.05%  ★ biggest
    sw_flow 6-11   −9.01%
    sw_flow 12-23  −5.30%

Signal quality: precision 60%, recall 81%, fire rate 69%.

## Ship-day sequence

1. Re-verify SITE 1 insertion point + SITE 7b L1_ONLY diff (~5 min).
2. Execute 7-site copy-paste per preflight (~30 min).
3. Bump version, changelog, build.py.
4. `make deploy-collector` FIRST (per [[feedback_deploy_sequence]]).
5. Verify GCS: `weather_data.json.wd_persistence_gate.enabled=true` + `forecast_log.json` has `wd_wdp` slot + Fitter tsd populates `per_layer_mae_by_lead.wd.wdp`.
6. Commit + push frontend.
7. Post-push: 4 curl verification snippets in the preflight doc.
8. 14-day post-ship watch through ~2026-08-10.

## Position in wd stack

wdp is the SECOND wd correction (L2 blend shipped 07-20 v0.6.368a is the first). Targets long-lead regime-transition cells where L2's 24h ramp has decayed to 0. Complementary, not conflicting.

Related: [[project_wd_l2_blend]], [[feedback_specialist_attribution_wiring]], [[feedback_whitelist_promotion_gate]], [[project_dp_residual_persistence]].
