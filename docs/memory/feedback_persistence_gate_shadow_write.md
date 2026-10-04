---
name: persistence-gate-shadow-write
description: "Persistence-gate specialists (chp/clp/wdp/dpp/wgp template) MUST write an unconditional `<HOURLY_KEY>_shadow_<specname>` array holding the would-apply values, regardless of ENABLED state. The original template guarded ALL hourly writes behind `if ENABLED and persist_val is not None`, so ENABLED=False shadow weeks produced zero pair-log-visible data — the shadow values only landed in the per-tick telemetry blob, which is not what the snapshot writer or Fitter reads."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0ee657df-54d0-435a-bbf2-1a02cf3244b5
  modified: 2026-07-27T17:48:40.108Z
---

# Persistence-gate specialists must write an unconditional shadow array

**Rule.** When scaffolding a new persistence-gate specialist from the
wdp/clp/chp template, the hourly-array write MUST be split into two
parts: (1) an **unconditional** `hourly[HOURLY_KEY + "_shadow_<name>"]`
array containing the would-apply values (persist_val on fire cells,
arr[i] on skip cells), and (2) the **ENABLED-gated** in-place overwrite
of `hourly[HOURLY_KEY]` and the pre-gate stash. The snapshot writer
slot for the specialist must prefer the shadow key over the live-array
fallback so shadow-week rows carry distinct forecast values.

**Why.** The original template (wdp until v0.6.382p) put all writes
behind `if ENABLED and persist_val is not None:`, so during Stage 3
`ENABLED=False`:

- `wind_direction` was never overwritten (correct).
- `wind_direction_pre_wd_gate` was never stashed.
- `hourly.wind_direction_shadow_wdp` didn't exist.
- Snapshot writer's `"wdp"` slot fell back to `hourly.wind_direction`,
  which equalled `"l2"` byte-for-byte.
- Snapshot dedup + pair-log path saw `forecast_wdp == forecast_l2` on
  every row → zero shadow rows survived.
- The `per_lead_would_apply` array wdp computed each tick DID hold the
  shadow values, but it only landed in the per-tick telemetry blob
  (`weather_data["wd_persistence_gate"]`) which is overwritten every
  collector tick and never lands in the pair log.

Result: the entire 07-20 → 07-27 wdp shadow week produced zero
pair-log-visible data. clp had the same bug and its 7-day flip gate
through 07-31 was being evaluated against zero real shadow data too.
chp had the same bug but is ENABLED=True since 07-19 so it hasn't
mattered post-ship.

**How to apply.** In the specialist's `stamp_*` function, replace:

```python
if ENABLED and persist_val is not None:
    if PRE_GATE_KEY not in hourly:
        hourly[PRE_GATE_KEY] = list(arr)
    new_arr = list(arr)
    for i, fires in enumerate(per_lead_fires):
        if fires and new_arr[i] is not None:
            new_arr[i] = <apply_value>
    hourly[HOURLY_KEY] = new_arr
```

with:

```python
shadow_arr = list(arr)
if persist_val is not None:
    for i, fires in enumerate(per_lead_fires):
        if fires and shadow_arr[i] is not None:
            shadow_arr[i] = <apply_value>
hourly[HOURLY_KEY + "_shadow_<name>"] = shadow_arr

if ENABLED and persist_val is not None:
    if PRE_GATE_KEY not in hourly:
        hourly[PRE_GATE_KEY] = list(arr)
    hourly[HOURLY_KEY] = shadow_arr
```

And update `forecast_snapshot.py`'s specialist slot to prefer the
shadow key:

```python
"<specname>": hourly.get("<HOURLY_KEY>_shadow_<name>",
                         hourly.get("<HOURLY_KEY>", []))
```

**Verification.** After deploying a new specialist Stage 3 wired
ENABLED=False, wait one collector tick, then grep the pair log for
rows where `forecast_<specname> != forecast_l4` (or whichever layer
sits immediately upstream). If zero survive, the shadow-write is
broken. Add this check to the preflight doc alongside the SITE anchor
verifications.

## Related

- [[project_wd_persistence_gate]] — the specialist that surfaced the bug
- [[feedback_streak_infra_dormancy]] — same failure family (guard the
  write, don't reset the gate)
- [[feedback_stated_intent_vs_code_behavior]] — module docstrings said
  "still stamps telemetry when ENABLED=False" which was true but
  misleading — the telemetry blob is not what any consumer reads
- [[feedback_verify_writers_for_read_paths]] — grep for WRITER before
  shipping a reader; this bug is the mirror image (grep for CONSUMER
  before shipping a writer)
