---
name: feedback-analysis-tools-drift-from-runtime
description: "Analysis-side verdicts must reflect runtime overrides (_FIELD_SKIP, _CELL_SKIP, ENABLED, KNOWN_LIVE_PIPELINES) — a script that ignores those issues actionable-looking recommendations that are already implemented or that would regress."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9a1f61c0-0486-4626-81ae-ca4da37e80cb
  modified: 2026-08-14T13:25:20.730Z
---

Analysis scripts (`analysis/**/*.py`) that recommend or verify runtime behavior must consult the processor's current state, not just fit a fresh table. When they don't, the digest surfaces verdicts that look actionable but are either already shipped, already vetoed, or would regress live behavior.

**Why**: three false alarms in a single triage session on 2026-08-14:

1. `h_ch_persistence_blend_stage2_vs_l6` reported "WATCH — 11 live chp cells lose to L6." Truth: 9 of 11 were already forced to L4 by the processor's `_CELL_SKIP` (v0.6.405). Real actionable count: **2**. Script only read the curated JSON; ignored the processor override. Fixed by importing `_CELL_SKIP` and subtracting from `live_ship_set`.

2. `h_wd_persistence_gate_stage2` verdict: "STAGE 2 HIT — Move to Stage 3 wiring." Truth: Stage 3 wiring shipped 2026-07-27 v0.6.382. Fixed by adding `h_wd_persistence_gate_stage1` and `h_wd_persistence_gate_stage2` entries to `KNOWN_LIVE_PIPELINES` in `analysis/runlog/build_executive_summary.py`.

3. `h_lc_rolling_window` verdict: "SWITCH TO W=3d — shortest window where all 4 fields beat raw." Truth: cc + cl are in `_FIELD_SKIP`, so their window improvement is moot. On the two runtime-active fields (cm, ch), W=3d **regresses** ch by ~10pp vs best-per-field. Fixed by importing `_FIELD_SKIP` and computing verdict over runtime-active fields only. Corrected verdict: SWITCH TO W=10d (real Pareto win).

**How to apply**: when writing or reviewing an analysis script that emits a verdict about a shipped target, check whether the runtime processor has `_FIELD_SKIP`, `_CELL_SKIP`, `ENABLED`, a curated-table filter, or any similar override, and either:

- Import that override and reflect it in the verdict (e.g., "over runtime-active fields"), OR
- Add the script to `KNOWN_LIVE_PIPELINES` if the entire target is already-live (auto-relabel to STABLE re-check), OR
- Have the script emit its own STABLE self-check line (see `h_precip_fc_orthogonality.py`).

Verdicts that don't reflect runtime state waste triage time and — worse — invite "obvious" regressions when someone acts on them without cross-checking. This pattern is a class-level failure, not a per-script bug; treat any analysis script that references shipped runtime behavior as needing this cross-check by default.

Related:
- [[feedback_shipped_items_leave_backlog]] — sibling in spirit.
- [[feedback_verify_completeness_claims]] — sibling in spirit.
- [[feedback_specialist_attribution_wiring]] — different failure but same "verify code, not intent" prescription.
