---
name: t-6-11h-tau-watch-08-31
description: "08-31 day 3 pre-read of t/6-11h τ-suspect. Last-7 vs prior-7: L2 flipped from helping +5% to hurting -7%. Absolute Δ ~0.075°F/day, within noise band. Authoritative 457K-row decay_tau_tuning still says τ=42 optimal. Verdict: WATCH day 4. Trigger threshold: sustained >0.15°F delta across another 7d window."
metadata: 
  node_type: memory
  type: project
  originSessionId: 132ee303-a10d-41fa-9c87-55f062f955a8
  modified: 2026-08-31T15:40:50.187Z
---

# t/6-11h τ-suspect — day 3 pre-read

Per READ FIRST (08-31), t/6-11h flagged as TOP ALERT day 2 with Δ 0.06°F noise-band. Pre-read for day 3:

## Last 14 days daily MAE (t/6-11h, n=4,092)

Notable "L1 wins" days in the last 7:
- 08-25: prod 1.595 vs L1 1.338 (Δ +0.257)
- 08-28: prod 1.226 vs L1 1.183 (Δ +0.043)
- 08-29: prod 0.853 vs L1 0.819 (Δ +0.034)
- 08-31: prod 1.667 vs L1 1.564 (Δ +0.102, partial day)

## 7-vs-7 comparison

- **Prior 7d** (08-18..08-24, n=972): MAE_prod=1.335, MAE_l1=1.403 → L2 helping +4.8%
- **Last 7d** (08-25..08-31, n=756): MAE_prod=1.099, MAE_l1=1.024 → L2 hurting -7.3%

**Swing: L2 flipped from +5% to -7% in one week. Absolute magnitude ~0.075°F/day.**

## Verdict: WATCH day 4

- Absolute delta stays within the 0.06°F noise band flagged 08-31.
- Authoritative `decay_tau_tuning` (457K rows) still says τ=42 optimal.
- Not yet a ship trigger. If sustained >0.15°F delta appears in another 7d window, retune becomes actionable.

## What would trigger a τ investigation

1. Sustained L2-hurting-prod >0.15°F across a full 7d window
2. Halves stability within the losing window (both halves same-sign)
3. A specific regime concentrating the loss (not seen yet — this read pooled)

Follow-up: re-run 09-04 with fresh 7d. If drift persists, expand into regime × lead cross-cut on t/6-11h to identify the losing cell.

Related: [[project_08_31_session]], [[feedback_measure_against_live_stack_baseline]].
