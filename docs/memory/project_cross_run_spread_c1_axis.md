---
name: project-cross-run-spread-c1-axis
description: Novel c1 confidence axis — same-model cross-run forecast spread per valid_time. Stage 0 HIT (8 fields), Stage 1 PROMOTE (7 fields ortho to transition + pt), Stage 2 PROMOTE (7/7 ortho to cluster_spread_q). Cleared for c1_v2 wiring 08-11.
metadata: 
  node_type: memory
  type: project
  originSessionId: 795b3253-14c7-40c1-bfc6-2279cd08d765
  modified: 2026-08-11T13:13:52.822Z
---

Cross-run ensemble spread per (field, valid_time) — the max-minus-min of `forecast` across all `run_time`s in the pair log that produced a forecast for that valid_time — cleanly stratifies |err| for most non-trivial fields.

Landed scripts:
- `analysis/h_cross_run_spread_stage0.py` — Stage 0 held-out (45d train / 7d test) quintile monotonicity check. **HIT for 8 fields**: wd(7.30x), t(3.59x), pr(2.64x), wg(2.57x), dp(2.54x), h(2.38x), ws(1.89x), cl(238x — bottom quintile near-zero, mechanism real). cc/ch/cm failed monotonicity (Q4 hole; investigate separately if pursued).
- `analysis/h_cross_run_spread_c1_stage1.py` — Stage 1 orthogonality vs c1's transition_flag and pt axes. **PROMOTE for 7/7 tested fields**: t, wd, wg, dp, h, pr, ws are ORTHOGONAL to BOTH axes on held-out. Q5/Q1 ratios inside every non-thin incumbent level range 1.80–8.18.
- `analysis/h_cross_run_spread_c1_stage2.py` — Stage 2 orthogonality vs `cluster_spread_q` (incumbent axis_2, spread_t-based). **PROMOTE 7/7** on 08-11: every scored (field, cluster_spread_level) cell holds Q5/Q1 |err| >= 1.35. Ranges 1.38 (ws@Q1) → 15.68 (wd@Q4). Two THIN cells only (dp/h@Q1) — cluster-low never produces cross-run-high in those bins, not a mechanism failure.

**Why:** The signal is per-valid_time same-model disagreement. Distinct from c1's existing `cluster_spread_q` (axis_2), which measures inter-source disagreement (Open-Meteo vs Pirate vs NWS). Same phenomenon in spirit ("hard valid_times") but different data-generating axis. Landed 08-10 after a smoke sweep found nothing in `analysis/` covers intra-model cross-run spread.

**How to apply:**
- Stage 2 cleared 08-11. Ready to wire into `c1_confidence_calibration_v2.py` as axis_6 (multi-axis accumulator addition, mirrors how axis_2 was added 06-20). Curate cells at Stage 3, ship narrow at Stage 4.
- Two spread signals confirmed empirically distinct: intra-model cross-run (this one) vs inter-source (cluster_spread_q). Their conjunction is expected to slice hardest cells further — that's the whole point of adding as a new axis.
- Thin bin: only ~700 valid_times had ≥3 runs in the 45d window. Watch that the count grows before making bin-conditional recommendations narrower than quintile.

Related: [[feedback_orthogonality_gate]] · [[feedback_measure_against_live_stack_baseline]] · [[project_c1_pivot_to_confidence]] · [[project_metric_provenance_v0391]]. See also failed sibling: `h_run_bias_carryover_t_stage0.py` (same session, different mechanism — died at Stage 0).
