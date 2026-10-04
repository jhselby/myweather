---
name: state-fc-vs-state-obs-for-live-gates
description: "2026-07-11 evening: production_whatif.py was using state_obs.regime_synoptic for regime-based skip evaluation. Live decay_apply.py gate uses state_fc. These populations differ significantly — for wg calm/24-47h, state_obs=calm shows L3 helping +42.8%; state_fc=calm shows L3 hurting -62.9%. All prior Production impact estimates for regime-based skips were biased. Rule: any live gate must be evaluated on the same axis it can decide on (forecast-time state), not post-hoc obs."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2bd018ca-98b4-4343-badc-7b405cae24be
---

## The rule

**A live gate can only use information available at forecast time.** For regime-conditional skip decisions in decay_apply.py, that's `state_fc.regime_synoptic` (derived from forecast values via state_stamp.py). NOT `state_obs.regime_synoptic` (which requires observations that come in later).

Any analysis simulating a live gate MUST evaluate on the same axis the live code uses. Otherwise the simulation estimates a fantasy gate we can't actually build.

## The discovered bug

- **decay_apply.py** (line 87 explicit comment, line 470 code): skip cells fire on `derived.state.regime_synoptic` which is stamped from state_fc.
- **production_whatif.py** (as of 2026-07-11 afternoon): `_ws_l3_skip`, `_sr_l5_skip`, `_cc_l4_skip`, `_wg_l3_skip`, `_ws_l3_skip_extra` all read `state_obs.regime_synoptic`. Fixed in this session.

## Why it matters — populations differ significantly

For **wg at calm/24-47h** in the recent 15-day window:

| axis | n | MAE L2 | MAE L3 | Δ% verdict |
|---|---:|---:|---:|---:|
| state_obs = calm | 3,727 | 6.236 | 3.569 | **+42.8% L3 WINS** |
| state_fc = calm | 2,937 | 5.240 | 8.534 | **−62.9% L3 LOSES** |

Same time window, same cell name, opposite verdict. The overlap between "obs was calm" and "forecast said it would be calm" is far from 100%. When forecast is calm but obs isn't, L3's calm-conditioned correction misfires catastrophically.

## Direction reversed on wg skip candidate

- **Before fix** (wrong axis): skipping wg L3 in state_obs=calm cells → skipping where L3 helps → Production regressed +1.9pp on wg.
- **After fix** (correct axis): skipping wg L3 in state_fc=calm cells → skipping where L3 hurts → Production improves −0.7pp on wg.

## Implications

- **Shipped ws L3 skips + sr L5 skips: LIVE behavior is correct.** decay_apply.py always used state_fc. Only production_whatif's Production impact estimates for those cells were biased.
- **All Production impact numbers quoted today for regime-based skip candidates before this fix were biased.** Some estimates were the wrong sign.
- **Analyses using state_fc directly (h_persistence_skill.py, h_ch_persistence_blend.py, h_full_regime_sweep.py, my halves checks) were correct.** Their conclusions stand.

## Application

Whenever building a new analysis for a regime-conditional gate proposal:
1. Confirm which state axis the LIVE gate would use (usually state_fc for pre-forecast decisions).
2. Slice the pair log by that same axis.
3. If the analysis uses a different axis, its verdict describes a gate you can't build.

The distinction generalizes beyond regime_synoptic: any state_fc.* field (wind_speed, wind_direction, etc.) can be used at forecast time; state_obs.* fields cannot.

## Cross-refs

Related: [[project-regime-gate-sweep-07-11]] (findings this bug affected), [[feedback-regime-gate-first]] (framework), [[project-correction-stack]] (where the gate lives).
