---
name: feedback_grid_select_halves_stable
description: "In multi-window promotion-gate harnesses, select best by \"highest test-MAE among halves-passing\", not by raw max. Raw-max + validate-after silently ships noise."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a29ce1bf-0957-49ab-aaf1-66e92fba77a9
  modified: 2026-08-31T10:40:12.988Z
---

Grid-search harnesses that pick a "best" combo by raw test-MAE and then validate halves stability on THAT combo will misreport verdicts on days when a shorter/noisier window's raw-max happens to beat the halves-stable option.

**Why:** discovered 2026-08-31 v0.6.528 in `analysis/_residual_persistence_stage1.py`. h Stage 1 flipped PROMOTE→MARGINAL between 08-30 and 08-31 with no underlying regression. Grid had window=5d at test +28.04% (halves ✗: first -3.57%, second +1.14%) vs window=14d at test +24.51% (halves ✓ +0.56 / +4.10). Old harness picked 5d by raw max, ran halves on it, failed, downgraded verdict. dp/wg happened to have halves-passing raw-max, so this hid until h's raw-max flipped windows today. The fix: compute halves for every grid combo, pick highest-test that passes halves; fall back to raw-max only when nothing clears.

**How to apply:** any new grid-search / hyperparameter-select harness that combines a "best" pick with a stability validation must:
1. Compute the stability check for every candidate, not just the raw-max.
2. Select best as `max(pct) WHERE stable`, not `max(pct)` then validate.
3. Emit an override line (`raw-max X fails halves; selecting stable Y`) when the two differ, so the decision is visible in the log.

Same class as [[feedback_pooled_n_time_thin]] — a single-slice optimum isn't robust; the promotion gate must actively prefer the robust option, not report a spurious failure when the wrong option happens to win the single-slice metric.
