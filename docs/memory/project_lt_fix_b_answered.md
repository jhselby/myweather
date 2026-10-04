---
name: lt-fix-b-answered
description: "2026-07-13 — Fix B refit of Lt cove correction against L2 baseline held-out +0.29%, below +1.0% gate → RETIRED on mechanism (L2 Kalman blend absorbs the signal). 2026-07-15 UPDATE: same script flipped SHIP at +1.34% after 2-day window roll — retirement HELD pending 2-window stability."
metadata: 
  node_type: memory
  type: project
  originSessionId: 01566fb8-1905-4804-8e7a-7cd634f42cee
---

## 2026-07-15 UPDATE — script flipped, retirement holds

Same `l6_fix_b_refit.py`, 2 days later, ran on essentially the same data
(154,698 train / 47,716 test — vs. 154,498 / 47,823 on 07-13). Held-out
improvement jumped from **+0.29% → +1.34%**, crossing the +1.0% gate.
Verdict flipped HOLD → SHIP. Panel B (sb_off × hour) refit table looks
identical to 07-13's — 7 SHIP bins in overnight hours 00-06 with means
+0.70 to +2.01. The refit itself didn't change; only the held-out window
rolled 2 days.

**Decision: retirement holds.** Reasoning:

1. **Mechanism argument unchanged.** L2's Kalman blend still absorbs the
   overnight cove-cooling signal per-tick. Nothing in the code changed to
   invalidate the "static delta double-counts what L2 already fits"
   argument from the original retirement.
2. **Anti-overfit gate:** [[feedback_regime_gate_first]] requires
   2-window stability for promotion. One SHIP reading 2 days after a
   strong HOLD is a single reversal, not stability. Per Rule 12 in
   CLAUDE.md, don't flip-flop under pressure from a marginal read.
3. **Window contamination.** MLC in-bin bias COLLAPSE event (07-07,
   Δ −26.98) is still fresh in the anomaly detector. 6 fields on WATCH
   in today's digest. The recent window is disturbed — bad time to act
   on a marginal held-out improvement.
4. **Signal is at the noise floor.** +0.29% → +1.34% both live within
   noise of the +1.0% gate. If genuinely near-gate we should see
   flip-flopping across daily reads; that's exactly what one wants to
   filter, not act on.

**Watch:** if `l6_fix_b_refit` stays ≥+1.0% on **both** 07-16 and 07-17
reads (2-window stability), reopen the mechanism argument. If it drops
back below +1.0% on either day, the 07-15 reading was a window-roll
artifact and the retirement is confirmed twice.

**Digest history note:** `_claim:LT_ENABLED=true` has actually been
firing continuously since 07-13 T11:53, meaning the SHIP verdict
emerged the same afternoon the retirement was decided — the retirement
was made on mechanism, not on the immediate script verdict. That's the
correct read: mechanism trumps a single close-to-gate script number.

**Files touched 07-15:** `analysis/runlog/divergence_report.py` — comment
+ divergence-row note updated to reflect current state (was contradicting
itself: "will always AGREE with LT_ENABLED=False" but the row was
showing READY/GATE CLEARED).


## Verdict

**Ran 2026-07-13:** `analysis/l6_fix_b_refit.py` on 202,321 pair rows (154,498 train / 47,823 held-out). Verdict: **HOLD** — refit tables did not beat L2 by threshold.

**Held-out MAE improvement: +0.29%** vs +1.0% ship gate. Not close.

This retires Lt Fix B. Not "keep waiting for more data" — the 47k held-out sample is more than enough. L2 is already doing the work.

## Why it doesn't ship

**Panel B (sb_off × hour_of_day)** looks like a real signal on training:
- 00-06h: mean residual +0.9 to +2.1°F, std 2.0–2.5, 7 SHIP bins
- Overnight cove cooling trough visible in training data

**But held-out told a different story:** applying those refit deltas to the 47k held-out rows moved MAE by 0.006°F. Meaningless.

**Mechanism:** L2 is a Kalman blend that re-fits per-tick based on obs-vs-model bias. The overnight cove-cooling signal that shows up as +1.5°F on the training set gets absorbed into L2's `bias` term at the moment it happens. A static hourly cove table would be adding a delta that L2 already added. Net wash on held-out.

**Panel A (sb_on × octant)** — all 3 S-half sea-breeze warming candidates come back **0 SHIP bins** after refit against L2. Fix A's warming-branch signal was largely an artifact of fitting against L1 raw (which was ~2.25°F cold-biased on cove rows, per [[project_l6_l2_double_counting_hypothesis]]).

## What this closes

- **Lt module status:** retired, not dormant-pending. `cove_correction.ENABLED = False` (both branches) since v0.6.276 stays that way permanently.
- **`project_l6_warming_branch_watch` watch:** answered. Warming branch is not just net-negative on production — it's also non-productive when properly refit.
- **The Fix B thread that's been open since 2026-07-01** — 12 days. Real answer, not defer.

## What this reinforces

- **L2's Kalman blend is doing more work than we thought.** Same story as [[project_persistence_skill_baseline]]: t is +0.68 pooled skill vs persistence, one of the strongest. L2 + L3 + L4 collectively add substantial value to raw HRRR for temperature.
- **Static microclimate tables lose to dynamic per-tick bias tracking.** Any future "specialist for field X, per-regime lookup" candidate should first ask: does L2 already track this? If yes, skip.
- **Fitting on the same signal L2 already fits will always lose on held-out.** Training-set wins from double-fitting are illusion.

## Files touched at retirement

Just the debug page + memory. No collector code change needed — Lt has been ENABLED=False since 07-01. The `cove_gradient_log.json` accumulator can stop, but no rush — it's cheap and if some future refactor of L2 changes the picture, having the raw data preserved is free insurance.

## Related

- [[project_l6_microclimate_correction]] — original Lt spec (needs status update to "retired").
- [[project_l6_l2_double_counting_hypothesis]] — the mechanism-of-loss investigation that led to Fix B.
- [[project_l6_warming_branch_watch]] — the open watch that Fix B was going to resolve.
- [[project_persistence_skill_baseline]] — parallel finding that L2 does substantial work on t.
- [[feedback_do_it_right]] — retiring a candidate cleanly beats leaving it dormant with a "someday refit."
