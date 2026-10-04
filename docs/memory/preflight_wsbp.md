---
name: preflight-wsbp
description: "Preflight checklist for the ws_bias_persistence ENABLED=True flip. 2026-08-04 flip HELD (calm regime n=0). 2026-08-06 re-check: calm regime now appearing (n=25 in 48h state, up from 0), but only n=12 in the 24h antecedent window — below MIN_N_ANTECEDENT=20. Still HOLD. Predict one more calm overnight clears it. Shipped 07-28 v0.6.388 ENABLED=False. Ships calm regime only. Sibling of dpbp (flipped 08-04)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9463fe7b-3db7-4c49-86b6-9979ab35e0e0
  modified: 2026-08-06T11:37:53.568Z
---

## Pre-flip verify checklist (run before flipping `ENABLED = True`)

### 1. Gate has real shadow-week data

- [ ] `weather_data.ws_bias_persistence` shows fires accumulating for calm regime ticks over past 7 days.
- [ ] State file `ws_bias_antecedent_state.json` present on GCS, non-empty, entries dated within last 60 min.
- [ ] Antecedent map has `n >= 20` for calm; if not, extend shadow-log window.
- [ ] **Extra vs dpbp:** the calm regime must have actually appeared at least ONCE in the shadow-log week. If regime never hits calm, the gate hasn't been observed firing at all → shadow-log verdict is null. Extend the window or wait for a calm-regime day (typical: overnight/early morning calm winds).

```
gsutil cat gs://myweather-data/ws_bias_antecedent_state.json | jq '[.entries[] | select(.regime=="calm")] | length'
gsutil cat gs://myweather-data/weather_data.json | jq '.ws_bias_persistence'
```

### 2. Shadow-vs-live comparison stays positive on the last 7 days

Re-cut Stage 1 walkforward against last 7 days ONLY. Should show calm regime pooled Δ ≥ +5% and both halves positive.

If pooled 7-day recheck < +5% or calm goes negative → HOLD flip, investigate whether the calm-regime over-forecast pattern has faded.

### 3. Params haven't drifted

```
grep -rn "DEFAULT_TRIGGER_THRESHOLD\|DEFAULT_CORRECTION_CAP\|DEFAULT_MIN_LEAD\|DEFAULT_FOCUS_REGIMES" weather_collector/processors/ws_bias_persistence.py
cat weather_collector/data/ws_bias_persistence_curated.json | jq '.trigger_threshold_mph,.correction_cap_mph,.min_lead_h,.focus_regimes'
```

Expect: trigger `+1.0`, cap `3.0`, min_lead `6`, focus_regimes `[calm]`.

### 4. Sign-inversion sanity — the difference from dpbp

dpbp: prev_bias < TRIGGER (negative), ADD +correction (positive). Same direction.

wsbp: prev_bias > TRIGGER (positive over-forecast), SUBTRACT -correction (negative). **Sign-flipped.**

Verify the code still flips sign correctly:

```
grep -n "should_fire\|correction = " weather_collector/processors/ws_bias_persistence.py
```

Look for `if mean_bias is not None and mean_bias > trigger:` (positive-side trigger) and `correction = -min(max(mean_bias, -cap), cap)` (sign-flip with symmetric clamp).

### 5. Non-negative wind clamp

wsbp adds a clamp `max(0.0, shadow[i] + correction)` — wind can never go negative. Verify:

```
grep -n "max(0.0" weather_collector/processors/ws_bias_persistence.py
```

If the clamp is removed, forecasts could dip below 0 mph. **Do not flip without the clamp.**

### 6. State file health

- [ ] Size < 200KB (should be ~30-50KB).
- [ ] Entries count 200-2000 (48h × ~6 ticks/hr).
- [ ] No entry with `regime: null` or `abs(bias) > 30 mph`.
- [ ] Calm-regime subset ≥ 20 entries in last 24h.

### 7. Code shape unchanged

```
git log --oneline weather_collector/processors/ws_bias_persistence.py
```

Expect: single commit `7f6b533f v0.6.388` (plus this preflight doc's own commit if any).

### 8. Flip + post-flip watch

Flip:
```
sed -i '' 's/^ENABLED = False.*$/ENABLED = True  # Flipped 2026-08-04 vX.Y.Z after 7-day gate cleared. Stage 3 preview shipped 2026-07-28./' weather_collector/processors/ws_bias_persistence.py
```

Then bump version + changelog + deploy + verify + push.

Post-flip watch (14 days):
- [ ] Fires activate only in calm regime — verify by checking `wsbp.regime_curr` telemetry across a variety of regime ticks.
- [ ] `hourly.wind_speed_pre_wsbp[i] - hourly.wind_speed[i]` matches the correction magnitude where gate fires (should be within ±0.01 mph).
- [ ] Wind never dips below 0 mph in `hourly.wind_speed` (non-negative clamp).
- [ ] 14-day post-flip: any calm-regime lead-band regressing worse than v0.6.388-baseline once n ≥ 200 rows; overall ws MAE drifting up.

## Related

- [[project_07_28_post_reboot]] — the ship arc
- [[preflight_dpbp]] — sibling gate preflight (dpbp flips same day; consider batching)
- [[feedback_persistence_gate_shadow_write]] — shadow-write invariant honored
