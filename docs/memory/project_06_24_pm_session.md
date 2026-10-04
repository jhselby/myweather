---
name: 06-24-pm-session
description: "Afternoon 2026-06-24 session — ran all 63 analysis scripts, refreshed cove correction lookup (gated), removed C1 ±band from wind card front (v0.6.222). Key lesson: don't refit L5 biases mid-trajectory."
metadata: 
  node_type: memory
  type: project
  originSessionId: a8f5db73-5a54-4321-a927-279049b8212d
---

## Shipped (v0.6.222)

- Removed `c1Band` ±N suffix from wind-card collapsed preview (`js/wind.js`). Joe found it visually busy. Confidence bands still render in the expanded chart.
- Refreshed `cove_correction.py` lookup tables from r5_cove_analysis day-12 read (n=1,732). Module still `ENABLED = False`. Lookup values are inputs to a gated module, so the refit is safe (no live trajectory tracker on cove). Updated debug page table + diurnal description to match.

## Tried then reverted

- Refit `solar_correction.py` bias tables from today's l5_recompute. **Reverted**: violated the documented "don't re-refit L5 biases mid-trajectory" rule on debug page line 1061. The L5 trajectory gate was tracking against 06-21 biases; refitting mid-window invalidates the simulator. Source of [[feedback-read-inline-rules-before-editing]].
- Widened C1 calibration TEST_DAYS 14→30 and Stage 4 CALIB_DAYS 7→30 chasing the pp/pa drift FAILs. Neither helped — the dry-then-wet weather transition is the real cause, not window length. Reverted, then logged finding in [[project-stage4-audit-metric-limitation]].

## Findings, not actions

- **Walk-forward L3/L4 4th read (06-24)** — 2d/5d/10d triple-window. Stable across all windows: L3 ch+wg, L4 ch. cm/pp/cc each had first all-windows-OFF reads — one consistent read, not enough by gate. Re-check 06-29. Saved to [[project-walkforward-l3l4-validator]].
- **r5_cove SHIP verdict** is the post-build confirmation read the `cove_correction.py` module was waiting on (PASS on both regime tests). One more confirming read ~07-01 → flip `ENABLED = True`. Confirmed in code: this is the NEW conditional cove correction, distinct from the OLD global R5 that stays retired (r5_audit.py today: HOLD baseline 2.170 vs R5-stack 2.843).
- **L5 solar single-read SHIP −14.7%** conflicts with [[project-l5-trajectory]] FLICKER — script verdict ≠ trajectory gate verdict. Trajectory is the binding gate, not the single read.
- **L2 lead-decay verdict for h (τ=36) and dp (τ=120)** is not actionable today: h fit is below the guardrail floor (60h = 0.25× of 240h default), dp is a derived field (Magnus from corrected t + corrected h, no independent bias).

## Pipeline-stage moves that look obvious but aren't

The orthogonality "PROMOTE" verdicts on pressure-tendency, precip_fc, and cluster_spread were *confirming* existing wiring, not new promotions — they're already C1 axes in `c1_confidence_calibration_v2.py`. Only hours-since-front is a genuinely new candidate, and adding it would push the already-data-starved multi-axis table (0/320 cells with sufficient n) further past the floor. Defer until after the 07-04 multi-axis Stage 4 audit settles.

## Convention reminder (the actual lesson)

`ENABLED = False` ≠ "safe to edit freely." Gated modules can still have live trajectory tracking around them ([[feedback-read-inline-rules-before-editing]]). Always read the module docstring + debug page section before touching tuned values.

Related: [[project-walkforward-l3l4-validator]], [[project-l5-trajectory]], [[project-stage4-audit-metric-limitation]], [[feedback-read-inline-rules-before-editing]], [[feedback-debug-page-canon]].
