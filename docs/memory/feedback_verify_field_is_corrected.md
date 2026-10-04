---
name: feedback-verify-field-is-corrected
description: "Before recommending any correction-stack workstream, verify (a) the field is actually corrected in production and (b) the ship isn't already done. All checks are one grep away. Skipping them has produced repeated false-positive recommendations."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 4497b339-2efa-4cc6-a9d8-ca9e374ecf4a
  modified: 2026-08-09T11:01:40.860Z
---

Before recommending Stage 0/1/2/3 work, τ retuning, gate wiring, ship-eligible follow-up, or any correction-stack change involving field X or ship-item Y, run all three checks:

1. **grep `_FIELD_SKIP` in `weather_collector/processors/`** — if X is in a `_FIELD_SKIP` set, the layer doesn't touch X. Any script that reports a signal for X in that layer is a false positive for actionable production work.
2. **Check MEMORY.md for `[[project_X_derived_field]]` or `[[project_X_detection_gap]]` or "X is L1-only"** — settled findings that the field is either derived (Ccd for cc; Magnus for dp; wg from ws blend), L1-only in production (pa, pp today), or otherwise not eligible for the workstream shape being proposed.
3. **`git log --oneline -30 | grep -iE "<workstream keyword>"` before proposing a ship.** The digest reports GATE CLEARED / SHIP-ELIGIBLE for items that have ALREADY shipped — those lines describe the result, not a pending action. Also check `KNOWN_LIVE_PIPELINES` in `analysis/runlog/build_executive_summary.py` and the "Auto-relabeled STABLE" digest section — if the script is there, it's already wired.

**Why:** 2026-08-09 session — three false-positive recommendations in one hour:
- (a) "implement per-field τ for pa/pp" when both are L1-only ([[project_pa_detection_gap]], [[project_pp_recalibration_session]]).
- (b) "wire ch recent-bias gate for cc/ch" when cc is in `_FIELD_SKIP` as derived-composition via Ccd ([[project_cc_derived_field]]).
- (c) "add C1h to KNOWN_LIVE_PIPELINES so it stops appearing in SHIP-ELIGIBLE" when C1h had shipped v0.6.396 the same morning AND `h_c1h_orthogonality` was already in the Auto-relabeled STABLE section of the same digest I was reading.

All three were catchable in <30 seconds. All three were in files loaded at session start. User called it: half the session was reading recommendations that fell apart on trivial verification.

**How to apply:** Trigger these checks on ANY of these phrases before writing the recommendation:
- "implement per-field τ" / "τ retune for X"
- "wire the X gate" / "Stage N workup for X"
- "ship the X correction" / "flip ENABLED=True for X"
- "add X to KNOWN_LIVE_PIPELINES" / "housekeeping — register X"
- Any script verdict that names a field or ship-item in an actionable-sounding recommendation

The check is cheap. Skipping it destroys session credibility fast — the correction-stack architecture depends on the user trusting that recommended actions actually touch production.

Related: [[project_correction_stack]] · [[project_cc_derived_field]] · [[project_dp_derived_field]] · [[project_cc_is_blend_of_clchcm]] · [[project_pa_detection_gap]] · [[project_pp_recalibration_session]] · [[project_already_live_backstops]] · [[feedback_check_contamination_before_acting]] · [[feedback_measure_before_concluding]].
