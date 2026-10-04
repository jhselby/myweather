---
name: feedback-walkforward-skip-table-blind
description: "walkforward_l3l4_validator's field-level verdict ignores the live SKIP_TABLE (including asymmetric fc-bin SKIPs shipped v0.6.366/370). \"Drop {wg, ws} from L3\" style aggregate proposals compare against an all-cells-active baseline that isn't production — do not treat as a real regression signal."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: fdd0e82f-b10c-462c-8432-365c0f4fa99f
  modified: 2026-07-26T12:03:27.403Z
---

**Rule:** When `walkforward_l3l4_validator` proposes dropping a field from `L3_FIELDS` (or `L4_FIELDS`), do NOT treat it as a real production regression until you check the per-cell breakdown in `analysis/output/walkforward_l3l4_summary.txt` AND compare against the live `SKIP_TABLE` in `decay_apply.py`. The tool's field-level `SHIP/off` verdict averages over ALL cells, including the loss cells that asymmetric fc-bin SKIP infrastructure is actively skipping in production.

**Why:** Discovered 2026-07-26. Digest divergence report showed `L3_FIELDS wants {cm, ch}` (i.e. drop wg + ws), GATED 1/7. Investigating: wg per-cell has huge wins (+30.9% ne_flow/24-47, +21.1% se_flow/24-47, +13.3% se_flow/12-23) AND huge losses (−41.4% calm/24-47, −20.2% sw_flow/24-47). Field aggregate = +0.4%, below the +2% ship threshold → validator says "off". But asymmetric SKIP (v0.6.366) already skips the loss cells; production wg L3 effect is materially better than the +0.4% aggregate. Walkforward's baseline is pre-asymmetric-SKIP, no longer matches production. Same story for ws (v0.6.370). Almost caused a wrong HOLD on 07-27 ws L3 REPLACEMENT.

**How to apply:**
- On any divergence-report `L3_FIELDS` or `L4_FIELDS` proposal that would drop a field: open `walkforward_l3l4_summary.txt`, scan the field's per-cell table. If big wins and big losses coexist and net near zero, the asymmetric-SKIP infrastructure is masking the true production delta — verdict is spurious.
- Correct signal for "drop field X from L3" is: per-cell view shows losses dominate WINS everywhere (not just canceling them), OR a Stage 1 hypothesis script (like `h_wg_residual_persistence_stage1`) flips PROMOTE → MARGINAL/HOLD on its own aggregate.
- Structural fix: **SHIPPED 2026-07-26 v0.6.381.** Validator now imports `_should_skip` + `_should_skip_asymmetric` from `decay_apply.py` and preprocesses each pair-log row's L3/L4 predictions with production SKIP logic before MAE aggregation. Uses `forecast_l1` as raw fc for asymmetric quartile lookup. Default is skip-aware; `--ignore-skip-table` restores old behavior for A/B checks. Post-ship verify: wg L3 flipped `ENT`/`off` → `SHIP` at +3.1% fc / +2.6% obs (matches production keeping wg in L3_FIELDS). ws L3 stays `off` even skip-aware — honest signal that ws L3 aggregate is genuinely marginal beyond the 26 asymmetric SKIP cells; production keeps ws because the surgical per-cell wins matter regardless of aggregate.
- Related: [[feedback_measure_against_live_stack_baseline]] — same class of bug (tool baseline drifting from production reality).
