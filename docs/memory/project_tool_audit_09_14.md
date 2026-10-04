---
name: tool-audit-09-14
description: "09-14 systematic audit after finding 3 silent-tool-bug ships (v0.6.613/v0.6.614/v0.6.616). Swept walker-cutoff pattern (2 unsafe, both fixed) and orthogonality-tool scope pattern (1 unsafe, fixed). No new bugs found. Also cleaned 3 stale ENABLED=False comments (marine_layer_correction, ws_bias_persistence, cl_persistence_gate)."
metadata: 
  node_type: memory
  type: project
  originSessionId: c656ec98-2726-4d09-8e93-674722e5843d
  modified: 2026-09-14T14:52:09.509Z
---

# Tool audit — 09-14

Motivated by 3 silent-tool-bug ships earlier today: two walker off-by-ones (v0.6.613 residual-persistence, v0.6.614 chp-cell-gate) and one orthogonality-tool scope-limit (v0.6.616 c1d KILL). Common shape: **tool with an internal threshold that silently limited its own view, producing a misleading verdict.** Swept for others.

## A. Walker off-by-one pattern

Grep'd all analysis scripts using `GATE_WINDOW_DAYS`. The unsafe pattern is:

```python
cutoff = datetime.now() - timedelta(days=GATE_WINDOW_DAYS)  # 8 dates
n_seen = ...
cleared = (n_seen == GATE_WINDOW_DAYS)  # never fires with 8 dates
```

Safe patterns found:
- `entries_sorted[-N:]` slicing (`l1_selector_fit_by_regime_walker.py:175`, `h_cc_combine_walker.py:194`). Always exactly N most recent entries.
- `len(by_day) >= N` tolerant (`h_lc_recent_bias_gate.py:459`, `h_lsr_recent_bias_gate.py:435`, `h_l2_shape_sweep.py:343`, `lc_fit.py:307`, `h_cc_blend_formula_stage1.py`, `h_frontal_t_bias_stage0.py`). Handles N+1 dates fine.

Only unsafe: `_residual_persistence_walker.py:121` (fixed v0.6.613) and `h_chp_cell_gate.py:137` (fixed v0.6.614).

## B. Orthogonality-tool scope pattern

Checked the two currently-emitting orthogonality tools on live axes.

- `h_c1h_orthogonality`: MIN_CELL_N=60, tests 5 fields × 3 bands (6-11h, 12-23h, 24-47h). All 10 live C1h SHIP cells covered. Today: 12 ORTHO / 24 judged = PROMOTE. Clean.
- `h_inter_model_spread_orthogonality`: MIN_N_BIN=100. 33/36 ORTHO vs C1a_trans, 36/36 vs cluster, 34/36 vs pt_mag. Robust PROMOTE.

Only `h_cloud_disagreement_orthogonality` had scope issue (fixed v0.6.616).

## C. Stale ENABLED comments

Not silent-tool-bugs — cosmetic. But the pattern of misleading state descriptions matters (memory index had wg residual persistence listed as "live" for weeks when it was ENABLED=False the whole time — a similar failure of state legibility).

Fixed in v0.6.617:

- `marine_layer_correction.py:55` — "Flip after 06-28/07-05/07-12 weekly re-reads confirm" → HOLD OFF INDEFINITELY per anomaly diagnosis.
- `ws_bias_persistence.py:46` — "earliest flip 2026-08-04" → HELD indefinitely on calm regime accumulation.
- `cl_persistence_gate.py:41` — "Gate EXTENDED to 2026-08-03" → gate did not clear, no target date, monitored via digest.

## What survived the audit unfixed

- **h/production τ-suspect** — real live-shape signal. h L2 helps 0-5h (−43.7%) but hurts 24-47h (+6.6%). `decay_tau_tuning` verdict HOLD (1/3 streak on {dp,h}). Actionable candidate but bigger scope — decides between τ shortening (production change with historical revert cost — see the ws τ=7 07-01/02 flip) and lead-band SKIP (safer, narrower).
- **cc/0-5h narrow-promote** into C1d — queued from v0.6.616 investigation.
- **ch/24-47h C1a-conditional recalibration** — queued from v0.6.616 investigation.

## How to apply

For future audit sweeps:
1. When a tool bug surfaces, grep for the *pattern* (not just the exact script). The walker off-by-one was 2 scripts sharing the exact `now - timedelta(days=N)` + `n_seen == N` combination — the second bug was findable in ≤5 min of grepping once we knew the shape.
2. Comment-audit is worth periodic sweep. Stale flip-date comments create false memory hits. If a comment says "flip after date X" and date X is a month past, the comment is lying about state.
3. The audit itself is a rung — future audits should re-run the walker-cutoff and orthogonality-scope sweeps if new tools land.

## Related

- [[project_residual_walker_gate_off_by_one_09_14]] — the first two bug ships (v0.6.613/v0.6.614).
- [[project_c1d_kill_scope_artifact_09_14]] — the third bug ship (v0.6.616).
- [[feedback_digest_triage_discipline]] — updated with step 6 (KILL on live axes: check test scope).
