---
name: project-06-08-to-06-22-plan
description: "2026-06-08 → 2026-06-22 work plan. Most live correction-stack questions are date-gated on R0 audit maturity + R2 re-confirmation; this captures what's queued for which date."
metadata: 
  node_type: memory
  type: project
  originSessionId: 43ac5ed4-a539-4e44-be37-7cbc5fe435f9
---

## Where things stand (2026-06-08)

Live: **v0.6.51**. Today's session shipped nothing (all decisions deferred); built `analysis/walkforward_l3l4_validator.py` as infrastructure prep.

The L2 lead-decay extension question is fully resolved (see [[project-l2-extension-assessment]]). The remaining open question is: which of L3 / L4 / L5 / sr-L2-build is the right next correction-stack move, and that's gated on data maturity, not on building more.

## Calendar

### ~2026-06-11
- **GCP bill check** — confirm v0.6.47 cost trim bent the trajectory down (was 615% MoM jump). 5-minute check.

### ~2026-06-15 (R0 audit window matures)
- **Re-run walk-forward L3/L4 validator** (`python3 analysis/walkforward_l3l4_validator.py`). Compare against the 2026-06-08 result captured in [[project-walkforward-l3l4-validator]]. Looking for stability.
- **Scan R0 audit table for ⚠ flags** on enabled layers.

### ~2026-06-22 (R2 magnitudes re-confirmable)
- **Re-run walk-forward L3/L4 validator** for the third time. If recommendation matches 06-15, ship the config to `decay_apply.py`.
- **Re-run `analysis/derived_humidity.py`** with post-L2-fix data. If verdict flips, derived RH is back in play (build it live then, not before).
- **Re-run R2 state-stratified accuracy**, focusing on Solar × flow regime spread.
  - Spread ≥ ~100 W/m²: green-light **L5 regime correction** build (append-style).
  - Spread < ~50 W/m²: L5 payoff too small. Reconsider **sr L2 build** (Tempest-network bias) instead.
  - Spread in between: ambiguous, defer another window.

## Hard rule for this window

**Don't ship corrections to production until at least two consecutive re-runs agree.** This applies to L3/L4 config, derived_humidity, and the L5-vs-sr-L2 decision. A single result is one read of a noisy window; two consecutive results that agree is signal.

**Why:** the discipline is exactly what kept the L2 extension question from turning into 2 sessions of wasted sr-builder work. Same rule, applied uniformly. See [[feedback-debug-ui-stability]].

## What NOT to do

- Don't build L5 yet (date-gated 06-22).
- Don't build sr L2 yet (date-gated against L5 decision).
- Don't wire the walk-forward validator into the debug page (no story until config is committed).
- Don't wire derived_humidity into R section live (dismissed; re-run manually first).
- Don't start "bigger architectural" items (ensemble model, ML over stack, backtesting framework) — none are 2-week-window-sized.

Related: [[project-todo]], [[project-l2-extension-assessment]], [[project-walkforward-l3l4-validator]], [[project-layer34-watch]], [[project-correction-stack]].
