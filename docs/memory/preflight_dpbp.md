---
name: preflight-dpbp
description: "Preflight checklist for the 2026-08-04 dp_bias_persistence ENABLED=True flip. Shipped 07-28 v0.6.387 ENABLED=False. Verifies (a) gate has enough fires in shadow-log week, (b) shadow-vs-live comparison stays positive, (c) params haven't drifted, (d) state file is healthy, (e) all code sites still match Stage 3 shape."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9463fe7b-3db7-4c49-86b6-9979ab35e0e0
  modified: 2026-07-28T17:33:08.579Z
---

## Pre-flip verify checklist (run before flipping `ENABLED = True`)

### 1. Gate has real shadow-week data

- [ ] `weather_data.decay_meta` shows dpbp fires accumulating in `hourly.corrected_dew_point_shadow_dpbp` for at least 3 focus-regime ticks over the past 7 days.
- [ ] Sanity: state file `dp_bias_antecedent_state.json` on GCS is present, non-empty, and has entries dated within the last 60 min.
- [ ] Antecedent maps have `n >= 20` for at least one of {pre_frontal, nw_flow, sw_flow} — if not, extend the shadow-log window instead of flipping.

Command:
```
gsutil cat gs://myweather-data/dp_bias_antecedent_state.json | jq '.entries | length'
gsutil cat gs://myweather-data/weather_data.json | jq '.dp_bias_persistence'
```

### 2. Shadow-vs-live comparison stays positive on the last 7 days

Re-cut Stage 1 walkforward against last 7 days ONLY (WIN_A_LO through today). Should show pooled Δ ≥ +5% and each of the 3 focus regimes ≥ +3% on both halves.

```
python3 /path/to/analysis/dp_bias_persistence_stage1.py  # after moving from scratchpad
```

If the pooled 7-day recheck says < +5% or any regime goes negative → HOLD flip, investigate whether the July event that drove the Stage 1 signal has now passed.

### 3. Params haven't drifted

Grep code + JSON for the 4 constants:

```
grep -rn "DEFAULT_TRIGGER_THRESHOLD\|DEFAULT_CORRECTION\|DEFAULT_MIN_LEAD\|DEFAULT_FOCUS_REGIMES" weather_collector/
cat weather_collector/data/dp_bias_persistence_curated.json | jq '.trigger_threshold_f,.correction_f,.min_lead_h,.focus_regimes'
```

Expect: trigger `-1.5`, correction `+2.0`, min_lead `6`, focus_regimes `[pre_frontal, nw_flow, sw_flow]`.

### 4. State file health

- [ ] Size of `dp_bias_antecedent_state.json` on GCS < 200KB (should be ~30-50KB).
- [ ] `entries` count between 200 and 2000 (48h × ~6 ticks/hr = ~288 in steady state).
- [ ] No entry with `regime: null` or `bias > 20` (data quality sanity).

### 5. Code shape unchanged since 07-28

```
git log --oneline weather_collector/processors/dp_bias_persistence.py
git log --oneline weather_collector/data/dp_bias_persistence_curated.json
```

Expect: single commit `d095cb7 v0.6.387` (plus this preflight doc's own commit if any).

### 6. Flip

If all above check clean, flip:

```
sed -i '' 's/^ENABLED = False.*$/ENABLED = True  # Flipped 2026-08-04 vX.Y.Z after 7-day gate cleared. Stage 3 preview shipped 2026-07-28./' weather_collector/processors/dp_bias_persistence.py
```

Then bump version + changelog + deploy + verify + push per the standard ship sequence.

### 7. Post-flip watch

- [ ] Verify next tick after flip: `dp_bias_persistence.enabled = true`, `leads_fired > 0` when regime + antecedent permit.
- [ ] Compare `hourly.corrected_dew_point[i]` vs `hourly.corrected_dew_point_pre_dpbp[i]` — should differ by exactly +2.0°F where gate fires.
- [ ] 14-day post-flip watch: any of the 3 focus regimes regressing worse than v0.6.387-baseline once n ≥ 200 rows/regime; overall dp MAE drifting up.

## Gotchas known from adjacent specialists

- **Shadow-write must remain unconditional** — the ENABLED-gated shadow bug bit wdp (07-20 → 07-27 entire shadow week silently empty) and clp (7-day gate through 07-31 reading zero real data). The `dpbp` code always writes `corrected_dew_point_shadow_dpbp` regardless of ENABLED — verify no future edit gates the shadow write.

- **Preserve-before-mutate** — `corrected_dew_point_pre_dpbp` snapshot happens BEFORE any mutation. Verify no future edit calls the correction directly on the live array without preserving.

- **State file is CRITICAL** — if the state file is deleted or its `entries` list emptied, the gate silently stops firing until 24h of new entries accumulate. Add a monitoring alarm if this becomes production behavior.

## Related

- [[project_07_28_post_reboot]] — the ship arc
- [[project_hypothesis_backlog]] — #6 closed by this ship
- [[feedback_persistence_gate_shadow_write]] — invariant this ship honors
- [[feedback_preserve_before_mutate]] — invariant this ship honors
- [[feedback_whitelist_promotion_gate]] — the 7-day gate discipline
