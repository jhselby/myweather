---
name: cluster-spread-noisy-verdict
description: cluster_spread_orthogonality KILL verdict is single-day noisy on marginal r-values under THIN dominance. Verified 2026-07-25 KILL flipped to STABLE within 12h. Axis_2 stays live.
metadata: 
  node_type: memory
  type: project
  originSessionId: 6eaa9453-6bb5-43c6-a502-11181da39f47
  modified: 2026-07-26T10:38:15.511Z
---

# cluster_spread verdict is noisy under THIN dominance (2026-07-25)

## Background

`cluster_spread` axis is live as axis_2 in `c1_confidence_calibration_v2.py` since 2026-06-20; persistent logger `processors/cluster_spread.py` has been running the same window.

`h_cloud_disagreement_orthogonality` script self-reports STABLE by default (KNOWN_LIVE self-check). But `cluster_spread_orthogonality` itself can flip to action-verb KILL when marginal r-values swing.

## The 2026-07-25 flip

**Morning digest:** ORTHOGONAL 1 / REDUNDANT 4 / THIN 15 → verdict `KILL: cluster-spread is mostly redundant with R6 transition signal`.

**Fresh re-run same evening (~12h later):** ORTHOGONAL 3 / REDUNDANT 2 / THIN 15 → verdict `STABLE` (self-reported).

Two non-THIN cells flipped verdict category:
- **ws 24-47h**: r=0.92 REDUND → r=2.08 ORTHOGONAL
- **wg 24-47h**: r=0.98 REDUND → r=1.94 ORTHOGONAL

Non-THIN population unchanged (5 cells: t/h/ws/wg/dp all at 24-47h). Just: marginal r-values around 1.0 flipped which side of the ORTHO/REDUND threshold they landed on.

## Read

**KILL was single-day noise.** Non-THIN population is only 5 cells, and the r-ratio for most sat right at 1.0 (statistical noise floor). Don't act on the KILL verdict — axis_2 stays live.

## Rule for future triage

When `cluster_spread_orthogonality` (or any orthogonality script whose THIN cells outnumber non-THIN) surfaces a KILL verdict:
1. Check r-ratio distribution on non-THIN cells. If most are within ±0.15 of 1.0, treat as noise.
2. Wait for a fresh re-run before acting.
3. Only credit KILL if non-THIN cells cluster clearly on one side (e.g., 4+ cells with r < 0.7) AND survive 2+ consecutive daily reads.

Related: [[feedback_check_contamination_before_acting]], [[feedback_fossil_windows]], [[feedback_measure_before_concluding]].
