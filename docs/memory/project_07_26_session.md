---
name: project-07-26-session
description: "2026-07-26 (Sun) session log. 2 ships (v0.6.380c dashboard sweep + walkforward diagnosis, v0.6.381 walkforward SKIP-aware structural fix). Closed both 07-25 Calendar items. 07-27 flip triage: wdp only. Big discovery: walkforward_l3l4_validator was SKIP_TABLE-blind — fixed same day."
metadata: 
  node_type: memory
  type: project
  originSessionId: fdd0e82f-b10c-462c-8432-365c0f4fa99f
  modified: 2026-07-26T17:15:56.478Z
---

## Ships

- **v0.6.380c** — 07-25 calendar sweep. Closed chp mid-lead re-check (aggregate persistence-skill Δ stable at −1.03, deferred to 07-28); C1 Stage 4 re-audit (HOLD-again 32.43%, cl now DEGRADED at 12-23h + 6-11h replacing cleared cm, same failure pattern different cell, next re-audit 07-30); h/L4 07-26 retest declined (Jaccard walker 8/7 but 0 SHIP cells — live-empty fossil pattern, retest 08-02+). Debug page ~15 edits.
- **v0.6.381** — walkforward_l3l4_validator SKIP-aware structural fix. Imports `_should_skip` + `_should_skip_asymmetric` from `decay_apply.py`; preprocesses each pair-log row's L3/L4 predictions with production SKIP logic before MAE aggregation. Uses `forecast_l1` as raw fc for asymmetric quartile lookup. Default is skip-aware; `--ignore-skip-table` flag restores old behavior for A/B checks.

## 07-27 flip triage — TRIPLE → SINGLE

- **wdp ✓ CLEARED.** Jaccard 1.0 vs 07-20 baseline across all 5 committed daily reads (07-20, 07-23, 07-24, 07-25, 07-26). SHIP set bit-stable: {calm/12-23, calm/24-47, pre_frontal/0-5, se_flow/0-5, sw_flow/0-5}. Only cell-set change: 1 MARGIN dropped. Preflight [[docs/preflight/wdp_ship_patches.md]] re-verified 07-26 EOD — all 7 sites still valid (line numbers drifted 12-27 in corrections_debug.html but text-unique anchors intact).
- **ws L3 REPLACEMENT ⚠ HOLD.** Asymmetric Jaccard trajectory: 07-25=0.75, 07-24=0.75, 07-23=0.70, 07-21=0.52, 07-20=0.52 — none clear 0.8 gate. Post-collapse from 44 → ~24 cells, cell-set still churning. HOLD until 2+ consecutive daily Jaccards ≥ 0.8 against a stable baseline. Re-evaluate ~07-31.
- **wg residual persistence ⚠ HOLD.** h_wg_residual_persistence_stage1 flipped PROMOTE → MARGINAL 07-26 (best combo +20.24%, was +17.74%). Persistence hypothesis's own aggregate signal weakened. Hold until Stage 1 recovers PROMOTE.

## Big discovery — walkforward SKIP-blind

Investigating today's divergence report showing `L3_FIELDS wants {cm, ch}` (i.e. drop wg + ws), GATED 1/7. Opened `walkforward_l3l4_summary.txt` per-cell: wg has huge WINS (+30.9% ne_flow/24-47, +21.1% se_flow/24-47, +13.3% se_flow/12-23) AND huge LOSSES (−41.4% calm/24-47, −20.2% sw_flow/24-47) — field aggregate +0.4% because they cancel. But asymmetric fc-bin SKIP (v0.6.366 wg, v0.6.370 ws) already skips the loss cells in production. Walkforward doesn't apply SKIP_TABLE → aggregate compares against a pre-asymmetric baseline that no longer exists. Filed [[feedback_walkforward_skip_table_blind]].

**Near-miss avoided:** almost wrote a HOLD recommendation for ws L3 REPLACEMENT citing the divergence "drop ws" signal as the reason. That would have been a wrong-because-tool-broken decision. Real HOLD reason is Jaccard 0.75.

**Post-fix verification:** skip-aware mode produces `L3_FIELDS = {wg, ch, cm}` matching production (drops wg from the drop-proposal). wg L3 verdict flipped `ENT/off/+1.1%` → `SHIP/+3.1% fc / +2.6% obs`. ws L3 stays `off/-0.3%` — honest signal that ws L3 aggregate is genuinely marginal beyond the 26 asymmetric SKIP cells; production keeps ws because per-cell surgical wins matter regardless of aggregate. Tomorrow's digest divergence report should show AGREE on wg + `drop ws` as a real (not spurious) marginal signal.

## Memory adds

- [[feedback_walkforward_skip_table_blind]] — rule + fix status (SHIPPED 2026-07-26 v0.6.381)
- This session log
