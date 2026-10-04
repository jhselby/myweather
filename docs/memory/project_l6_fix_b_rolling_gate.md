---
name: project_l6_fix_b_rolling_gate
description: L6 Fix B refit script has a 7-day rolling gate. Gate is confirming high variance — 08-12 read has 2 SHIP / 3 HOLD / 5 distinct days with ship_bins CHURN. No live signal survives held-out.
metadata:
  node_type: memory
  type: project
  originSessionId: 7c9d7aa9-9a64-4be2-8251-1d31c6c73f86
  modified: 2026-08-15T09:49:26.658Z
---

# 08-15 CLOSE UNCLEAN (7-day watch expired)

Watch opened 08-08 closed today. Latest gate state: 7d window, 8 distinct days, ship_days 4 / hold_days 4, `ship_bins` CHURN (6 bins flipped inside window: `sb_off|{03,04,06,07,10,11}`). Held-out +3.02% on last-7d is real but noisy — the gate correctly refused to ship a churning shape. Outcome matches the 08-12 read: Fix B is high-variance, nothing durable, L2 Kalman already captures the microclimate signal.

**Action taken:** Removed from `OPEN_WATCHES` in `corrections_debug.html`. Script keeps running (rolling gate is the sentry); reopen only on the escalation rule below.

**Escalation rule to reopen:** ≥3 consecutive SHIP days on the rolling gate with a stable `ship_bins` set. Anything short of that stays parked.

---

# 08-12 UPDATE (gate working as designed)

Digest flagged verdict change HOLD-GATE → HOLD. Semantic no-op — both bucket as "hold". Cause: single-day held-out slipped from +1.54% (day passing, gate stuck) to +0.44% (day not passing). Rolling gate state: 5 distinct days, 2 SHIP / 3 HOLD, ship_bins CHURN across `sb_off|03`, `sb_off|04`, `sb_off|10`. Very unlikely to clear the "no HOLD days + stable ship_bins" gate.

Interpretation from original memory holds: L2's Kalman blend captures the microclimate signal; Fix B has nothing durable to add. Gate is exactly the sentry that would surface a change of story; today it's suppressing a fossil peak (08-08 +2.15%). Keep running, no action.

**How to apply on future digest flips of this script:** if `bucket(prior) == bucket(new)`, skip investigation. Escalate only on bucket-crossing flips (e.g., HOLD → SHIP or SHIP → KILL) or a run of ≥3 consecutive SHIP days on the rolling gate.

---

**Shipped 2026-08-08 (analysis-only, no collector deploy).**

`analysis/l6_fix_b_refit.py` now runs a 7-day rolling gate mirroring the shape used by `lc_fit.py`. `.cache_l6_fix_b_gate_history.json` accumulates per-run entries (30-day retention). Gate clears when: ≥7 distinct days in window, no HOLD days, `ship_bins` set stable across window, at least one bin currently shipping.

**Why:** Fix B reported SHIP +2.15% held-out on 2026-08-08. Was retired 2026-07-13 at +0.29% (below the +1.0% single-day gate). No infrastructure between the two runs tracked whether the signal was consistent — a single lucky window could trigger PROMOTE and mask that Fix B is high-variance.

**How to apply:** Verdict emission now says `VERDICT: HOLD-GATE — day-only +X% but 7-day gate not cleared (N/7 days)` when day-level ships but gate hasn't cleared. Buckets as HOLD in exec-summary classifier — no false ship-eligible signal. Only becomes `VERDICT: SHIP` when the full 7-day rolling gate clears with the same `ship_bins` set.

**What Fix B actually is:** Two branches. [A] sb_on × octant (sea-breeze warming by wind direction) — currently 0 ship cells (std too wide). [B] sb_off × hour (diurnal residual) — 6 ship cells (03-06am +0.6-0.9°F, 08-09am -0.5-0.6°F). Physically plausible: cove has water thermal inertia, holds marine air longer. Per-row improvement ~0.19°F on 25% of test rows — small, invisible to users individually but scoreboard-real if consistent.

**Lt still on do-not-reopen list.** Gate clearing here doesn't mean auto-ship — it means the signal has passed the consistency bar and reopening the Lt decision is now defensible. The flip itself (populate `_DELTA_BY_OCTANT` + `_HOUR_DELTA_SB_OFF` in `cove_correction.py`, remove `return 0.0`, flip `ENABLED = True`) remains a separate deliberate action.

**Sibling context:** Same class of fix as [[project_lc_regime_stage1_pool_prereq]] (2026-08-08) — script was emitting misleading SHIP without a persistence check. Both problems solved by consistency-across-days gating.
