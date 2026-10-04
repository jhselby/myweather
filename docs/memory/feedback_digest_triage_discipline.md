---
name: feedback-digest-triage-discipline
description: Pre-triage checklist before restating any digest verdict as an action item. Prevents the morning-flip pattern where digest lines get treated as decisions before their caveats are checked.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d3790481-8229-42a6-9301-f39add0e302a
  modified: 2026-09-14T14:42:54.721Z
---

# Rule

Before restating any digest verdict as an action item, run the pre-triage checklist:

1. **Grep MEMORY.md for the tool name + subject.** If a related project memory exists, read it before speaking. Applies especially to `marine_layer_anomaly`, `r5_cove_analysis`, `h_hsf_orthogonality`, and any tool with a same-named project file.
2. **Check for companion tools in the same digest.** `r5_cove_analysis` has `r5_audit`. `h_dp_residual_persistence_stage1` has `h_dp_residual_persistence_stage2`. Two-tool disagreement is a finding — surface it, don't pick one side.
3. **Check thin-population signals.** Passage count, join rate, sample size. For h_hsf / h_pre_front the population tag now lands inline via v0.6.373; for other tools, look at the "N frontal passages" / "X of Y pairs joined" / "n=Z rows scanned" lines near the verdict.
4. **State hypothesis as hypothesis until verified.** "The KILL is an artifact" vs "the KILL might be an artifact — I want to test by running the matched-regime variant." No confident diagnosis without either a proof or a scheduled test.
5. **Cross-check the already-live sections BEFORE flagging any SHIP-ELIGIBLE, "Narrow-promote GATE CLEARED", or walkforward-validator recommendation as an action.** The digest has three monitor-of-live-state sections whose wording reads as ship-ready but isn't:
   - **Auto-relabeled STABLE (KNOWN_LIVE_PIPELINES)** — anything here is the live target. Cross-reference this list against every ship-ish verdict.
   - **Narrow-promote gates (C1 marginal-axis Stage 3)** — "✓ GATE CLEARED — ready to ship N cells" is a monitor of the curated table's SHIP count. If the parent axis (C1h, C1d, pre-frontal, h/l4 narrow-add) is in KNOWN_LIVE_PIPELINES, those cells are already firing every tick. Not a queue. `build_executive_summary.py:1064` comment acknowledges the narrow-promote walker doesn't share the SHIP-eligible walker's known-live guard.
   - **walkforward_l3l4_validator** — "L3 ship N field(s), L4 ship M field(s)" is a monitor of the currently-deployed L3/L4 whitelist. Same set as the live config = reaffirmation, not new action. Only flag if the recommended set diverges from the live `L3_ENABLED` / `L4_ENABLED` in `decay_apply.py`.
6. **KILL verdicts on live axes: verify the tool's test scope covers all live SHIP cells.** Orthogonality / redundancy tools apply an internal `MIN_N` floor and skip cells that don't clear it. If a tool KILLs an axis but only tested a subset of the axis's live SHIP cells, the KILL is scope-limited — it says "the cells I could test are redundant," not "the axis as a whole is redundant." Before acting on a KILL: (a) list the live SHIP cells for the axis (its `_curated.json`); (b) list which cells the tool evaluated (the printed rows above the verdict); (c) if any live SHIP cell is missing from the tool's evaluated set, re-run the tool at a lower `MIN_N` to include it. If the wider view flips the verdict, the KILL was a scope artifact. Documented in [[project_c1d_kill_scope_artifact_09_14]] — C1d KILL fired with the tool testing only 24-47h (3 of 5 live SHIP cells at 12-23h invisible); at MIN_N=50 the verdict cleanly flipped to MIXED.

## Why

07-22 morning session: I confidently restated `h_hsf` KILL as "window artifact — C1e stays wired" in v0.6.372, then two hours later the matched-regime fix reproduced the KILL and I had to walk it back in v0.6.372a. Same session I proposed cross-cut work for `r5_cove_analysis` as if it were new, when `r5_audit` had already run the cross-cut 200 lines later in the same digest and said HOLD. And I initially flagged MLC ★ COLLAPSE as fresh alert until I randomly happened to check the 07-16 seasonal memory. Joe's frame: "Every single morning I run the digest, you restate the conclusions, then look into things and find out that you were wrong about things."

Structural counterparts shipped in v0.6.373 (suppress registry, companion pairs, population tags) fix the *known* misfire patterns. This checklist handles the *unknown-next* ones — new signals that haven't yet earned a registry entry or a companion pair. The digest infrastructure and the checklist are complementary, not substitutes.

**08-10 repeat miss (why step 5 exists):** Flagged C1h narrow-promote "✓ GATE CLEARED — ready to ship 8 cells" as top action of the day. C1h axis was listed as auto-relabeled STABLE in the same digest, live since v0.6.316 (grep of `confidence_layer.py` for `_C1H_CELLS`, `_C1H_CO_AXIS_GATE` confirmed). Same session, treated `walkforward_l3l4_validator` "L3 ship 3, L4 ship 2" as new promotion instead of monitor reaffirmation of an already-shipped whitelist. Joe: "this is the second or third day in a row that you've messed this up." Root cause: I read top-to-bottom, treated the Ship/Narrow-promote/Walkforward sections as decisions, and only consulted the STABLE list afterward as a lookup. Step 5 makes the cross-check mandatory *before* the recommendation, not after.

## How to apply

- Every morning-digest triage message. Not optional.
- Before restating a SHIP / KILL / COLLAPSE / DECAY / MIXED verdict from any script, run the four steps.
- The morning triage output should be structured as: "**Digest signals:** [what tools said]. **After checklist:** [memory hits, companion tools, thin-pop caveats]. **Real action items:** [filtered list]. **Suspected artifacts / already-settled:** [rest]."
- If a signal survives the checklist AND has no explaining memory, that's a real new finding — go investigate. If it doesn't survive, note it and don't act.
- Do not skip step 4. "State hypothesis as hypothesis" is the discipline that would have prevented v0.6.372's walk-back — I diagnosed then tested rather than testing then diagnosing.

Related: [[feedback_check_contamination_before_acting]], [[feedback_measure_against_live_stack_baseline]], [[feedback_two_gates_per_layer]], [[project_c1e_hsf_kill_investigation]], [[project_mlc_diagnosis]].
