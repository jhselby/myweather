---
name: dp-v0540-warmup-watch
description: "Watch memo: v0.6.540 selector fix routed dp to NBM 09-02 16:17 UTC. Scoreboard 09-03 shows dp -91.6% — traced to pre-fix long-lead pairs still closing in the window. Predict collapse to flat-to-modestly-positive within 48h. Re-check trigger Fri 09-05: if 6-11h band holds at ≈-15% vs NBM raw post-full-warmup, L2_nbm Kalman+decay is net-harmful for dp at short-mid lead = real bug."
metadata: 
  node_type: memory
  type: project
  originSessionId: 46a33a93-0070-4414-a452-3ba08bf441da
  modified: 2026-09-03T16:16:13.113Z
---

# dp v0.6.540 warmup watch

Ship: v0.6.540 (2026-09-02 16:17 UTC deploy) added dp to the runtime NBM writeback loop. Prior to this, selector table said route-to-NBM for dp but the writeback loop iterated only 5 fields (silent drop). Post-fix: dp routes to l2_nbm.

## What the 09-03 scoreboard actually shows

Overall dp lift vs best-public: **-91.6%** (7d), **-94.1%** (24h). REGRESS verdict.

Per-band 24h split:
- 0-5h  (mostly post-fix): prod 1.15 vs NBM raw 1.54 → **+25.4%** Ldp corrections beating NBM raw — fix working correctly
- 6-11h (mixed pre/post): prod 1.58 vs NBM raw 1.34 → **-17.6%** (n=105 thin)
- 12-23h (mostly pre-fix): prod 2.56 vs NBM 1.31 → -95.8%
- 24-47h (100% pre-fix): prod 2.53 vs NBM 1.02 → -148.7%

Pair log keys forecasts by issue time. Fix landed ~19h before digest ran; long-lead forecasts closing today were issued BEFORE the fix and remain HRRR-derived until they age out.

## Prediction (expected outcome)

By Fri 09-05 (48h post-fix), all long-lead pairs in the 24h window will have been issued post-fix. Expected values:
- 0-5h: ~1.15 (holds — corrections beating NBM raw)
- 6-11h: ~1.5-1.6 (if corrections modest; may still lose to NBM)
- 12-23h: ~1.4-1.6
- 24-47h: ~1.3-1.5

Overall dp lift-vs-best-public should collapse from -91.6% to somewhere between flat and modestly positive. **~15-20 point swing in overall scoreboard mean from dp alone.**

## Re-check trigger — Fri 09-05

**Trigger:** run scoreboard_v2.py after 09-05 07:00 EDT (48h post-fix).

**Pass condition:** dp overall lift-vs-best-public between -20% and +15%; per-band 0-5h positive; 12-47h no worse than -30%.

**Fail condition (real bug):** 6-11h band holds at ≈-15% vs NBM raw with n≥200 after full warmup. This would mean L2_nbm Kalman+decay on dp is net-harmful for short-mid lead — real bug. Investigation would look at the dp L2 stack: dp is Magnus-derived from h + t; L2_nbm applied via `wind_blend`-style additive Kalman on raw NBM dp. If h L2 corrections already improve h (they do), applying an additional Kalman on dp derived from a different NBM source may be double-correcting.

**Also watch:** overall scoreboard L5 rolling ladder. Was +2.8 → -3.0 over 7 days going into today. If it flattens or reverses by Fri, the dp fix accounted for most of the slide.

Related: [[project_09_02_session]], [[project_09_03_session]].
