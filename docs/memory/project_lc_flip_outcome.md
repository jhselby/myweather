---
name: project_lc_flip_outcome
description: Lc flipped 2026-07-17 v0.6.355. 14-day post-ship watch through 07-31. Delete after watch closes cleanly.
metadata: 
  node_type: memory
  type: project
  originSessionId: 43be4b0e-1ee6-46ca-95b4-e8e62a53c216
---

**Flipped 2026-07-17 v0.6.355.** Cloud saturation-unbiasing live for cc/cl/cm/ch.

## What landed
- `cloud_saturation_correction.py:29` ENABLED False → True
- All 4 preconditions from [[project_lc_flip_plan]] verified from morning digest: lc_fit gate_clear=True (07-10 rolled out of 7-day window), 16 SHIP cells stable 7 days (07-11 → 07-17), divergence report LC_ENABLED READY (8/7), no cc/cl/cm/ch ANOMALY.
- First live tick (15:27 EDT): **113 cells fired** — cc 46/48, ch 39/48, cm 19/48, cl 9/48. Mean |Δ| in expected 28-42 range per field.

## Rule 5 sweep executed
- Removed Lc from `DISABLED_OPERATORS` (corrections_debug.html) + `EXPECTED_DORMANT_OPERATORS` (gate_firing_rollup.py). Added Lsb to the latter.
- Added Lc SHIP_EVENTS annotations for cc/cl/cm/ch (sparkline chart marks 07-17).
- Updated applied-layers table, Still-Open Watches, applicability-map bullet, live Lc widget, active-candidates footer.

## 14-day post-ship watch (through 2026-07-31)

**Expected biggest lifts on Prod in accuracy-over-time chart:**
- cl 80-95: −55%
- cl 95-100: −47%
- ch 50-80: −37%

**Watch triggers — investigate before any other work if:**
- Any cc/cl/cm/ch cell flips **COLLAPSE** in the anomaly detector within 14 days.
- 07-19 Sunday `lc_fit` re-run shows SHIP set change (any cell demotes to SKIP).

**Contingency:** revert = flip line 29 back to `ENABLED = False` → `make deploy-collector` → document failure mode; next earliest-flip attempt +14 days minimum.

**Why:** so the 14-day watch has a self-contained reference. **Delete this memory 2026-07-31** if the watch closes cleanly, or convert to a durable feedback memory if a specific failure mode emerges.
