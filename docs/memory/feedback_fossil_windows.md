---
name: feedback-fossil-windows
description: Fossil-window bug class was CLOSED 2026-08-09 v0.6.398 via analysis/_windows.py rolling helper. Historical context below for the pre-fix era.
metadata:
  node_type: memory
  type: feedback
  originSessionId: af17d512-4939-4875-aa25-7dc730a23e19
  modified: 2026-08-09T10:39:58.721Z
---

**Status 2026-08-09 v0.6.398: CLOSED.** 14 fossil-prone analysis scripts migrated to `analysis/_windows.py` `rolling_windows()` helper. Windows now anchor at midnight-today automatically; no hardcoded date literals remain in any `WIN_*` assignment. The stale_window_audit in `build_executive_summary.py` still runs — it will fire again only if someone reintroduces hardcoded literals.

**Why the fix:** Every 3–4 days the digest re-flagged 8–11 scripts as fossil-window suspects and required a hand-slide of `WIN_A_LO/HI/WIN_B_LO/HI/WIN_FULL_LO/HI` literals. Happened at least 4 times: 07-19 (h/l4 catch), 07-22, 07-28, 08-01, 08-06, 08-08. Not a bug about any one script — a class of bug that recurred until someone abstracted it out.

**How to apply going forward:**
- New analysis scripts with time-windowed comparisons: `from _windows import rolling_windows` then `WIN_A_LO, WIN_A_HI, WIN_B_LO, WIN_B_HI, WIN_FULL_LO, WIN_FULL_HI = rolling_windows()`. Pass `recent_days=N, prior_days=N` for non-15d shapes.
- If a script needs a *pinned* historical window (e.g. matched-baseline against a specific incident, not a rolling comparison), use hardcoded literals AND add a `# PINNED: <reason>` comment so future me knows it's intentional. The stale_window_audit will flag it — that's fine, the fossil-detector uses one channel and pinning is the other.
- Do NOT reintroduce the "slide these 11 scripts +4d" ritual. The helper does it.

**Pre-fix incident record (kept for historical context):**
2026-07-19 caught first: `h/l4 narrow-add` gate ✓ CLEARED 7/7 with 2 SHIP cells, "SHIP set identical 6 consecutive days." All 7 reads used a window that ended 2026-07-11 — 8 days behind today, entirely before the MLC-collapse / cc-cluster distribution shift. Sliding the window 8 days forward collapsed the streak to 1/7 with 0 SHIP cells. Same-day sweep of 8 fossil-window scripts also refreshed the 07-21 candidates (wg L3 6→12 SKIP, wg residual 6→8 SHIP, cl linear ramp MODERATE→STRONG) — gate shapes shifted materially on refreshed data even where the SHIP/SKIP verdict survived.

Related: [[feedback_check_contamination_before_acting]] · [[feedback_two_gates_per_layer]] · [[feedback_fresh_per_day_recompute]].
