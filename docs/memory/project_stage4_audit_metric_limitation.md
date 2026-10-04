---
name: stage4-audit-metric-limitation
description: "C1 Stage 4 audit's % drift metric breaks near zero — pp and pa calib MAEs are ~0.001–0.005 in dry/quiescent regimes, so any rain or pressure activity blows drift to +500-3000%. Widening CALIB_DAYS doesn't fix it."
metadata: 
  node_type: memory
  type: project
  originSessionId: a8f5db73-5a54-4321-a927-279049b8212d
---

## What happened (2026-06-24)

Today's c1_stage4_audit run flagged 26 FAILs of 62 cells with pp and pa as the worst drifters (pp 24-47h stable: calib MAE 1.33 → recent 44.35, drift +3226%; pa 0-5h transition: 0.002 → 0.046, +2237%).

**Cause:** the calibration window (06-10 → 06-17) was a dry, pressure-quiet week. Joe confirmed: "it has been very dry until a few days ago." Recent week (06-17 → 06-24) had actual rain and pressure activity. Calib MAE for "always dry" baseline is ~0; recent reality is far from that. Dividing by a near-zero baseline inflates drift % to nonsense.

**Tried:** widening CALIB_DAYS from 7 → 30 in stage 4. Slight help on pa (drift 2237% → 590%) but pp essentially unchanged (3210%). Because the *prior 30 days were also mostly dry*, there was no rain history to widen into. Reverted both the audit's CALIB_DAYS and the calibration script's TEST_DAYS=30 back to canonical 7 and 14.

## Why: this is a metric-design issue, not a calibration bug

**Why:** the audit's `drift_pct = (recent − calib) / calib × 100` blows up when calib → 0. This is fine when calib MAE reflects normal real-world error magnitude; it's nonsense when the calib regime is fundamentally different from the test regime (e.g., dry vs wet).

**How to apply:** before treating Stage 4 pp/pa FAILs as a model degradation signal, ask first: was the calib window an outlier regime? Check Joe's weather memory or the actual obs in the calib window. If yes, the FAIL is regime-shift, not drift. Don't ship calibration changes based on it.

## What would actually fix it

1. **Floor in the drift metric:** `(recent − calib) / max(calib, floor)` with a per-field floor (e.g., 5% for pp, 0.01 inHg for pa). Cheapest fix.
2. **Regime-conditional calibration:** separate curated tables for dry-vs-wet and quiescent-vs-active synoptic states. Lines up with the existing R2 + L5 work. Higher complexity.
3. **Exclude pp/pa from C1 confidence wiring during regime transitions.** A degenerate option but cheap.

None implemented today — flagged as a project finding. Address as part of [[project-c1-pivot-to-confidence]] follow-up, not standalone.

## Second blowup mode — mixture drift (2026-07-09)

The subset audit shipped in v0.6.316e was designed to sidestep the near-zero-calib pp/pa blowup by excluding those fields. It surfaced `cm/0-5h [stable]` at +78% drift — I initially read this as a real cell-level FAIL and told Joe the escape hatch was off the table. Wrong.

Stratifying the two windows by forecast-cm bin proved cm/0-5h drift is ~90% **mixture drift**, not cell-level drift. Recent window had 4× more 95-100 forecast rows (260 → 986) and half as many 0-5 forecast rows (1840 → 1279). Within-bin MAEs were mostly stable (0-5 stayed 6.67 → 7.18, 95-100 improved 60.86 → 52.36); only 80-95 showed real drift and only at n=59. Weighted-average sanity check reproduced the +78% number almost exactly from the mixture shift alone.

**Same class of failure as the pp/pa near-zero blowup:** the drift metric is population-weighted, so any shift in the forecast-bin distribution between windows produces a spurious drift signal even when correction-layer accuracy is stable per cell.

## Third blowup mode — unsigned improvement reads as failure (2026-07-09)

Same afternoon, extending the mixture check across all FAIL cells surfaced 3 cells (sr/12-23h stable, sr/6-11h stable, cl/24-47h transition) where **recent MAE is LOWER than calib MAE** across every populous forecast bin. The correction is *improving*. But Stage 4's `|Δ|/calib` is unsigned, so an improvement of −50% reads identical to a degradation of +50%. sr's improvements are exactly the Lsr bug fix that landed 07-03 finally showing up in the recent window — the layer works, and Stage 4 called it drift.

## Fix landed 2026-07-09 (v0.6.317... + follow-up)

Integrated a **refined view** into `c1_stage4_audit.py`. After primary classification, every FAIL and WATCH cell gets a mixture-check pass (`analysis/c1_stage4_mixture_check.py::refine_verdicts`). Per-cell verdicts DEGRADED/IMPROVED/SAFE/PARTIAL/THIN/SKIP map to raw PASS/WATCH/FAIL/INSUFFICIENT via:
  - IMPROVED, SAFE → PASS   (recent MAE ≤ calib or mixture drift, no signal degradation)
  - DEGRADED → FAIL         (real cell-level degradation, ≥40% within-bin at n≥80)
  - PARTIAL → WATCH         (25-40% within-bin, watch)
  - THIN → keep raw
  - SKIP → excluded from denominator (metric-artifact fields: pp, pa, wd)

Today's refined counts: legacy 27 PASS / 1 WATCH / 2 FAIL / +12 excluded (vs raw 18/11/13). Real FAILs identified: ws/24-47h transition (3 wind bins degrading), cl/12-23h stable (b1 low-forecast bin doubled MAE). Both actionable.

**Extends the "what would fix it" list:**

4. **Mixture-normalized drift metric** — LANDED 2026-07-09 as the refined view.
5. **Signed drift metric** — LANDED 2026-07-09 as part of the mixture-check classifier (DEGRADED requires positive drift).
6. **Metric-artifact field exclusion** — LANDED 2026-07-09 via the SKIP verdict (pp, pa, wd).

**Practical rule (updated 2026-07-09):** trust the audit's `refined.counts` and `refined.recommendation`, not the raw `counts` / `recommendation`. The raw view is kept for backward compat but is systematically pessimistic — it fires on the three metric-artifact classes.

**Codified 2026-07-16 v0.6.353e:** the practical rule is now baked into the script. `c1_stage4_audit.py` prints refined FIRST (labeled PRIMARY), legacy second (labeled `[legacy — not authoritative]`), and closes with a pinned `Verdict: ...` line carrying the refined recommendation so `extract_verdict()` picks refined for the digest exec summary. JSON now has a top-level `primary` field (source = `multi_axis.refined` when multi is present, else `legacy_axis.refined`) — downstream code should read `primary.recommendation` instead of `legacy_axis.recommendation`. Legacy fields retained under the same keys for backward compat.

## Silent 15-day multi-axis stratification bug (2026-07-16 v0.6.353f)

Immediately after v0.6.353e promoted the refined view to primary, the multi-axis result was clearly broken: 1013 cells all n=0, all INSUFFICIENT. Investigation:

- Curated ship-cells in `c1_confidence_curated_v2.json` use 5-part axis_key: `sq::pt::slot::c1f::hsf`.
- `c1_stage4_audit.py::stratify()` built 4-part accumulator keys: `sq::pt::slot::c1f`.
- Every ship-cell lookup missed → all cells n=0 → all INSUFFICIENT.

Root cause: on 2026-07-01 v0.6.272, C1e (hours-since-front) shipped end-to-end and `c1_confidence_calibration_v2.py` extended the axis_key format to 5-part. `c1_stage4_audit.py` was never updated. **The multi-axis Stage 4 audit had been silently dead for 15 days.** Nobody caught it because the legacy single-axis view kept producing plausible numbers.

Fix: added `_load_frontal_passages()` and `_hsf_group()` to c1_stage4_audit.py mirroring the calibration script, extended axis_key to 5 parts, added `passages` argument to `stratify()`. First real read: 195 PASS / 139 WATCH / 320 FAIL / 143 INSUFFICIENT / +216 excluded → NOT READY.

**Why:** the split legacy-vs-refined view was hiding infrastructure failure. Legacy single-axis produced plausible numbers, so no metric ever reported total failure. Promoting refined to primary made "1013 INSUFFICIENT" visible, which surfaced the bug.

**How to apply:** whenever a Stage 3+ correction extends its curated-table axis_key format, grep for every accumulator that builds that key format and update in the same commit — it's the "SKIP_TABLE grep on live-layer flip" pattern applied to axis_keys instead of skip cells. Related: [[feedback_verify_writers_for_read_paths]] — the class of bug where readers and writers drift out of sync silently.

Related: [[project-c1-pivot-to-confidence]], [[project-stage4-audit]], [[feedback-hypothesis-promotion-pipeline]].
