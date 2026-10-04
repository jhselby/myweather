---
name: project-state-fc-obs-disagreement-narrow-ship
description: "09-13 Stage 1 orthogonality on cloud_delta + solar_delta — neither is a general C1 axis (mixed ORTHO/REDUND across axes), but both show strong per-cell orthogonality in narrow pockets. cloud_delta: cc/0-5h (5-6x), cl/0-5h (1.7-2.2x), cm/0-5h, dp/0-5h. solar_delta: sr/0-5h (extreme night baseline), cm/0-5h, h/0-5h. Belongs in the C1 marginal-axis narrow-ship pool alongside pre-frontal / hsf — not the inter_model_spread full-axis Stage 2 pipeline. Curation deferred."
metadata: 
  node_type: memory
  type: project
  originSessionId: 45cfd381-3cb4-4d5d-bfc4-10e1c2ebd46b
  modified: 2026-09-13T12:33:42.375Z
---

# state_fc-vs-state_obs disagreement — narrow-ship pool candidate

## 09-13 Stage 1 orthogonality result

Ran `analysis/h_state_fc_obs_disagreement_orthogonality.py` (mirrors
`h_inter_model_spread_orthogonality.py`). Two candidate axes tested vs
C1a_trans / cluster / pt_mag on 44 (field, band) cells each.

**Per-axis rollup:**

| candidate | C1a_trans (O/R/P) | cluster (O/R/P) | pt_mag (O/R/P) |
|-----------|-------------------|-----------------|----------------|
| cloud_delta | 17 / 20 / 7 | 12 / 22 / 10 | 13 / 22 / 9 |
| solar_delta | 14 / 18 / 12 | 18 / 20 / 5 | 13 / 19 / 11 |

Neither clears the "ORTHOGONAL vs all 3 axes" bar. Redundant cells
slightly outnumber orthogonal on 5 of 6 axis combos. Overall verdict:
HOLD — MIXED for both candidates.

## Narrow pockets that ARE orthogonal (per-cell)

**cloud_delta** — cells with ORTHOGONAL across all 3 axes:
- cc/0-5h: 5.15× / 5.96× / 3.18×  (very strong)
- cl/0-5h: 1.73× / 2.23× / 1.85×  (strong)
- cm/0-5h: 1.94× / 1.32× / 1.40×  (moderate)
- dp/0-5h: 1.39× / 1.35× (pt_mag PARTIAL)
- wd/0-5h: 1.54× / 1.56× (pt_mag PARTIAL)

**solar_delta** — cells with ORTHOGONAL across all 3 axes:
- sr/0-5h: 749× / 386× (extreme — near-zero-MAE nighttime baseline
  inflates ratio; needs floor filter at Stage 2 like inter_model_spread's
  sr cells did)
- cm/0-5h: 1.61× / 1.94× / 1.66×
- h/0-5h: 1.37× / 1.57× / 1.43×

Pattern: signals concentrated in cloud/moisture cells at short lead.
That's exactly where you'd expect model issue-time cloud/solar
disagreement with observations to matter — the model already got a fast-
changing weather element wrong at t=0, so its forecasts for the next
few hours are more likely to be off.

## Ship shape when this advances

NOT the inter_model_spread full-C1-axis Stage 2 pipeline (which advances
to a 7-day gate + wire as `c1_confidence_calibration_v2` axis_N). Instead,
fold into the **C1 marginal-axis narrow-ship pool** alongside pre_frontal,
hsf, and other narrow-shipping axes.

Narrow-ship shape:
- Per-cell wire: only the cells that showed ORTHOGONAL across all 3 axes
  in Stage 1.
- Bidirectional: cloud_delta HIGH → widen CI; cloud_delta LOW → possibly
  narrow (Stage 2 preview would establish direction).
- Same daily gate as pre_frontal (`h_pre_front_orthogonality`) — 7-day
  rolling gate on the narrow-ship cell list.
- Wire target: `confidence_layer.py` under a new `_C1_CLOUD_DELTA_CELLS`
  and `_C1_SOLAR_DELTA_CELLS` alongside `_C1_PRE_FRONT_CELLS`.

## Not-doing list

- Do NOT advance to Stage 2 as a full C1 axis via
  `h_state_fc_obs_disagreement_c1_stage2.py`. That path is designed for
  cleanly orthogonal signals like inter_model_spread; running it on a
  mixed signal would surface many false-positive SHIP cells that are
  actually just C1a-transition or cluster-spread rediscoveries.
- Do NOT ship sr/0-5h based on the 749× ratio alone — the extreme value
  is a night-baseline artifact (near-zero MAE inflates ratios). Same
  class as inter_model_spread's sr cells that needed a floor filter.

## Related

- [[project_09_13_session]] — session that produced this result.
- [[project_09_12_session]] — inter_model_spread Stage 1 orthogonality
  (the template for this analysis). That candidate came back cleanly
  orthogonal (33/36, 36/36, 34/36) and advanced to Stage 2.
- [[project_c1_pivot_to_confidence]] — the broader C1 architecture.
- `analysis/h_state_fc_obs_disagreement_stage0.py` — Stage 0 that
  originally promoted both candidates (11 + 12 cells).
- `analysis/h_state_fc_obs_disagreement_orthogonality.py` — this Stage 1
  script.
