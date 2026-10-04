---
name: feedback-streak-walker-robustness
description: "Narrow-promote streak walker uses Jaccard ≥ 0.8 on SHIP-cell sets, not exact identity. Preserves fossil detection while tolerating single-cell borderline drift. Set at v0.6.362 after exact-match hid stable C1h/C1d gates for 10 days."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: af17d512-4939-4875-aa25-7dc730a23e19
  modified: 2026-07-19T22:50:46.900Z
---

`build_executive_summary.py`'s narrow-promote gate walker compares today's SHIP-cell claim against prior days via **Jaccard similarity ≥ 0.8**, not exact list equality. See `_claim_match()` around line ~700.

**Why:** On 2026-07-19 the exact-match walker (`c == today_claim`) produced three false readings in a single digest:
1. **h/l4 narrow-add fossil** — Jaccard would have caught this too (windows fossilised, cells drifted 100%). Both walkers agree.
2. **pre-frontal same-day reset** — Jaccard 3/7 ≈ 0.43, correctly stays reset (40% cell turnover is real churn).
3. **C1h + C1d — the actual win.** Both had been ⏳ 5/7 and 1/7 for weeks due to single-cell in-window churn (12 → 13 → 14 cells across the window). Under Jaccard the walker sees ✓ GATE CLEARED (10/7 days, oldest match 2026-07-10). Structurally stable the whole time — exact-match was actively hiding the promotion.

**Threshold rationale (0.8):** allows one-cell drift in a 5-6 cell set (Jaccard 5/6 ≈ 0.83, 6/7 ≈ 0.86); rejects two-cell drift (Jaccard 3/7 ≈ 0.43, 4/7 ≈ 0.57). Chosen deliberately tight — the goal is to catch fossils and true instability, not to paper over half-cell churn.

**How to apply:**
- When adding a new narrow-promote gate to `_NARROW_PROMOTE_GATES` in `build_executive_summary.py`, no change needed — it inherits the Jaccard walker.
- When designing a NEW streak gate elsewhere, prefer Jaccard-on-set over exact-equality-on-list from the start. Related: [[feedback_fossil_windows]] (window-side), [[feedback_two_gates_per_layer]] (divergence-report streak ≠ fitter's own gate), [[feedback_check_contamination_before_acting]].
- If a gate shows GATE CLEARED but subjective read says "the cell set has been drifting a lot," check the Jaccard values directly — the walker doesn't currently emit them. Adding per-day Jaccard to the marker line is a possible future refinement.

## Related pattern: transition-only detection also hides sustained signals

Same session (2026-07-19) uncovered a sibling brittleness in the same file (`build_executive_summary.py`). The **script-level bucket-transition walker** at the SHIP-ELIGIBLE section iterated `promotes_new` — only scripts that flipped INTO the promote bucket TODAY. Scripts that transitioned days or weeks ago and stayed in promote never re-entered `promotes_new`, so they never surfaced even after clearing the 7-day streak + multi-tool gate. Fixed in v0.6.364: iterate `all_promote_ship_res` (all promote-bucket ship-resolution scripts). Uncovered four hidden signals:
- `h_cloud_disagreement_orthogonality` (C1d) — 16/7 days
- `h_pre_front_orthogonality` — 23/7 days
- `walkforward_l3l4_validator` — 25/7 days
- `h_wind_shift_rate_orthogonality` — 6/7 days (still confirming)

**Common lesson:** streak/gate walkers built on any form of "did this change since last time?" comparison miss the case where nothing changed but something is now ready. If you design a walker, ask: does it distinguish "state changed" from "state is at ship threshold"? Ship-threshold is what actually matters; state-change is a proxy for it that decays as time passes.
