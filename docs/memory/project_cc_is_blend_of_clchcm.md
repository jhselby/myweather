---
name: project-derived-fields-inherit-work
description: "Non-independent fields inherit work from their components. cc = blend(cl,cm,ch). Magnus triangle: (t, h, dp) mutually derivable — any two determine the third; h and dp shown to users come from re-derivation after per-field corrections. When triaging 'quiet fields,' NEVER list a derived field as quiet based on its own memories alone — check components."
metadata: 
  node_type: memory
  type: project
  originSessionId: 2612e533-b493-4573-96ed-5a4b19d7982c
  modified: 2026-07-29T17:43:34.602Z
---

## The rules

**cc = blend(cl, cm, ch).** Not an independent forecast field.

**Magnus triangle: (t, h, dp).** Any two determine the third. Each has its own per-field corrections in decay_apply.py TARGET_ARRAY, but coherence steps re-derive the third after corrections apply:
- `forecast_snapshot.py:241-247` — dp per-layer = Magnus(t_lk, h_lk)
- `decay_apply.py::_recompute_derived` — corrected_humidity from corrected(t, dp), then re-recompute corrected_apparent_temperature + corrected_absolute_humidity

User-visible dp and h are derivation-driven, not independent corrections.

**Practically: t is the only fully-independent field in the (t, h, dp) triangle.** Work on any of the three ripples to the others through re-derivation.

## Why this matters

When asked "which fields have no current work," don't grep the field's own memories in isolation. Correct check for a derived field:
- **cc** = cc-specific memories + (cl OR cm OR ch active)
- **dp** = dp-specific memories + (t OR h active) + own direct corrections active
- **h**  = h-specific memories + (t OR dp active) + own direct corrections active

## Incidents

**07-29 (this session):** listed cc as one of 4 all-quiet fields alongside t/h/sr. Joe corrected: cc inherits from cl/cm/ch (all active). Corrected list was t/h. Joe then corrected AGAIN: dp is the same shape as cc — Magnus-derived — so h inherits from t/dp. Since dp has active work (residual persistence + dpbp preflight), h inherits activity through the triangle. **True all-quiet list = t only.**

## Related

- [[project_correction_stack]] — 4-layer, 14 fields architecture
- [[project_cloud_obs_kbvy]] — cc obs blend (KBVY+KBOS METAR)
- [[project_cc_sat_correction]] — settled cc-specific work
- [[project_cm_investigation_07_28]] / [[project_cl_transition_watch]] / [[project_ch_persistence_gate_ship]] — component work keeping cc active
- [[project_dp_residual_persistence]] / [[preflight_dpbp]] — dp direct work keeping h active by inheritance
