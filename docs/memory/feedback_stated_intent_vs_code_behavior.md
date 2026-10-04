---
name: stated-intent-vs-code-behavior
description: Documentation/comments state one thing; code does another. Both look reasonable in isolation. Catch this class by grep-matching docstring/comment claims against actual code paths whenever you touch either.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6bb3eadf-bcbe-4bab-ba53-c02b00010f53
---

**The pattern.** A docstring, footer note, or in-file comment asserts a behavior. The code implementing that behavior contradicts it. Both look defensible in isolation — the doc reads plausible; the code reads clean. The mismatch only shows up when someone cross-references them.

**Why:** Documented as a distinct silent-failure class after two examples caught on 2026-07-07:

1. **Divergence reporter regex mismatch.** `analysis/runlog/divergence_report.py::claim_from_walkforward` docstring said "walkforward_l3l4_validator's last log emits `L3_ENABLED` / `L4_ENABLED` lines." The regex matched that literal. But `walkforward_l3l4_validator.py` actually emitted `L3_FIELDS = {...}` / `L4_FIELDS = {...}` — the field names had been renamed at some point without updating the reporter. Both reporter regex and walkforward output looked correct in isolation. Result: every digest silently reported L3_FIELDS and L4_FIELDS as UNKNOWN status, hiding the fact that walkforward wanted to drop ws/wg from L3 and add sr to L4. Fixed by matching regex to actual output token.

2. **Scorecard pp Brier mixing.** The scorecard banner's footer note explicitly said "pp excluded (Brier, not MAE)." The code's per-pp Brier collection loop pushed pp's Brier % into the same `rows` array that meanPct averaged. So Overall % IS mixing MAE% and Brier% every render, despite the note asserting it isn't. Note read plausible; code read clean. Fixed by splitting into separate `brierRows` array and rendering pp Brier as its own row below the tiles.

**How to apply:**

When you touch code that has ANY documented intent — a docstring, an inline note above a rendered value, a README bullet, a footer caption — cross-check the doc against what the code actually does. Specifically:
- Does the regex/lookup match the literal token names the source emits?
- Does the filter/exclusion the doc names actually happen in the code path?
- Does the "we do X here" claim match the sequence of function calls?

When you write code that will be paired with a doc note, add the doc alongside the code path that implements it, in the same file, next to the relevant line. Doc drift across files is the failure mode. Doc in the same block as the code it describes stays honest.

If a note says "X excluded" or "X only" or "we skip Y in this case," grep the immediate code path for the guard that implements it. Absence of a guard → note is lying → fix one or the other before shipping.

Related class of failure to [[verify-writers-for-read-paths]] (readers exist without writers) — both are silent-drift patterns where nothing errors and reviewers don't notice.

## Third example — 2026-07-09 h_precip_fc_orthogonality "PROMOTE" verdict

`analysis/h_precip_fc_orthogonality.py` returned "PROMOTE: precip_fc is independent of both C1a and C1e (23 orthogonal cells)." Digest surfaced it in the "New candidates" section with day 1/7 gate tracking. Read as: *precip_fc is a new axis worth promoting to Stage 2 curation.*

Reality: **C1f (precip_fc>0) already shipped as v0.6.215 on 2026-06-24** — it's live in `confidence_layer.py:104` with `axis_id = "C1f"` and wired into the multi-axis 5-tuple keys. Today's script run is a *stability re-check* against the newer C1e axis (shipped 07-01), not a candidate for a new promotion. The script's verdict language "PROMOTE" doesn't know the axis is already live — same class as the wind-shift-rate ortho=0 → MIXED verdict fixed this morning.

Same failure mode as (1) and (2): script output looks defensible in isolation, memory says one thing, code is doing another. Fixed by rewording the ≥8-orthogonal-cells branch as "STABLE: C1f remains independent … Axis is live since v0.6.215; this is a stability re-check pass, not a new candidate." Also added similar re-wording to the KILL and MIXED branches so no branch produces a misleading action verb.

**Reinforced rule:** when writing a script that outputs "PROMOTE" / "KILL" / "SHIP" verdicts, check what live production actually reflects before believing the verdict verb. A verdict of "PROMOTE something-already-live" is nonsensical; the script should say "STABILITY CONFIRMED" or similar.

## Fourth example — 2026-07-09 simulate_windows R6 verdict

`analysis/simulate_windows.py` reported "R6: all 7 cutoffs agree → SHIP → PROMOTE" in today's digest. Read as: *R6 (regime-transition penalty) has cleared the Stage 1→Stage 2 gate; promote it to a bias correction.*

Reality: **R6 was pivoted from bias-correction to confidence axis on 2026-06-19 v0.6.141** ([[project_c1_pivot_to_confidence]]). The signal is live as `confidence_layer.py:104` axis_id `"C1a"` — "Regime transition." Today's SHIP verdict is a health-check pass on C1a's underlying signal, NOT a candidate for a new bias-correction ship. Promoting R6 as a bias correction would either double-count C1a or reverse the pivot.

Fix: added an `ALREADY_SHIPPED_AS = {"R6": "C1a — Regime transition ..."}` map to the verdict printer. When the mapped hypothesis is in this dict, reinterpret verdicts: SHIP → "STABLE (health check pass)", HOLD → "REGRESSION WATCH (underlying signal weakened)", INSUF → "INSUF". Keeps the health-check value while removing the promotion-verb misread.

Same class as R6's neighbor L5 (solar_correction, ENABLED=True) and R5 (cove_correction, both branches disabled — different signal, different story). The `ALREADY_SHIPPED_AS` map means future hypotheses that get repurposed to different architectural slots (C1 axes, L4 subsets, etc.) can be added there instead of being freshly retagged in the verdict prose each time.

Four instances now: divergence-reporter regex (07-07), scorecard-Brier folding (07-07), wind-shift-rate ortho=0 (07-09 AM), precip_fc live-axis (07-09 PM), simulate_windows R6 (07-09 PM). **Bright-line rule:** any script that outputs an action verb like "PROMOTE", "KILL", "SHIP", "RETIRE" needs an "already live?" check against production before it's trustworthy.
