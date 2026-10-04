---
name: feedback-prod-real-vs-replay-divergence
description: "When the sentry flags a regression, compare prod_real to prod-replay before hunting for a correction-quality cause. Divergence isolates runtime/state-only bugs cleanly."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 826ae698-1457-47e2-a670-9f046fb5ffca
  modified: 2026-09-17T12:32:23.156Z
---

When the regression sentry flags a "FRESH FIRE" on a field, the first cut is **prod_real vs prod** from `mae_over_time.json`'s `series` block.

**Corrected semantics (verified 2026-09-17 in `analysis/mae_over_time.py`):**
- `prod` = `error_l4` from the pair log — **HRRR L4 cascade error, live-stamped**. Not a replay. It's the HRRR-only path (STRICT_LAYER_KEYS = raw:error_l1, l2:error_l2, l3:error_l3, prod:error_l4).
- `prod_real` = `error_{applied_layer}` from the pair log — **what the collector actually served, live-stamped**. Includes NBM path when the L1 selector picked NBM.
- Divergence is a **routing/selector effect**, not a runtime-vs-replay bug. When prod_real > prod, the L1 selector picked NBM on rows where HRRR L4 would have been better (or NBM quality regressed on those rows).

**If prod (HRRR L4) is clean but prod_real is hot:** the HRRR-only cascade would have shipped better than what was actually served — the L1 selector is picking NBM when HRRR would've been better, or NBM raw quality regressed on those rows. Look at selector-pick counts per day (should be stable), then raw_nbm vs raw_hrrr per day. **Not** an L2/L3/L4 shape problem.

**If both are hot:** correction quality is genuinely bad on the HRRR side too. Dig on the fitter's per-regime/per-band output.

**If prod_real diverges suddenly on a specific day:** check what actually changed. Options in priority order: (1) NBM raw quality shifted upstream (Open-Meteo GFS/NBM data glitch), (2) selector pick rate changed (a wire/gate flip), (3) publisher freshness on the NBM side of the pair log. Selector picks per day are stable in normal operation — if they're stable AND raw_nbm degraded, it's upstream data, not us.

**Why:** Before this shortcut existed, "the sentry is hot on h" led into a full L2 shape / walker / scoreboard sweep. The shortcut settles the corrections-vs-runtime split in one column comparison.

**How to apply:** on any FRESH FIRE, load the field's `raw` / `prod` / `prod_real` rows for the last 7-14 days from `analysis/output/mae_over_time.json`, print them side by side, and check whether prod-replay tracks raw while prod_real diverges. If yes, look at recent runtime-touching ships (regime classifier, detector thresholds, state stamps, applied_layer plumbing) before touching corrections.

**Case study 2026-09-15:** dp + h "FRESH FIRE" (3d prod_real +30/+35% vs raw). prod ≈ raw on the hot days but prod_real +40% worse. Divergence → selector routing effect, HRRR L4 was fine but NBM was being served at long lead. Correlated timing with v0.6.620 frontal DP_DROP 8→4°F ship, but the mechanism is selector routing changing under new regime tags, not a "replay uses new threshold" story (there is no replay).

**Case study 2026-09-17:** t FRESH FIRE was NOT a routing issue despite prod/prod_real divergence — it was a lucky-baseline artifact from an anomalously-good 09-14 NBM day. Selector picks were stable across all 6 days (~48% HRRR / ~44% NBM). Raw NBM MAE for t: 09-12: 1.578 / 09-13: 1.342 / 09-14: 0.887 / 09-15: 1.476 / 09-16: 1.632. 09-14 broke pattern; 09-15/16 returned to baseline. See [[feedback_fresh_fire_lucky_baseline_artifact]] — check daily raw MAE FIRST to rule out baseline artifact before assuming routing loss.

Related: [[project_frontal_detector_health_09_14]] · [[feedback_pair_log_error_field]] · [[feedback_shadow_write_applied_layer_trap]] · [[feedback_fresh_fire_lucky_baseline_artifact]] · [[feedback_fresh_routing_loss_diagnosis]].
