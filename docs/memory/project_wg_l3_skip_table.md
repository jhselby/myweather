---
name: wg-l3-skip-table
description: "**08-04 v0.6.391 re-cut adds 3 cells; live table now 7:** calm 0-5, calm 12-23, ne_flow 6-11, sea_breeze 6-11 (all from 07-28 v0.6.385) + calm 24-47 (+45.2% halves +4.3/+53.1, held cell cleared A drifted 7→4), sea_breeze 24-47 (+31.1% halves +4.0/+45.0, same pattern), frontal 12-23 (+8.8% halves +13.2/+4.5 NEW). A halves on the 24-47 pair drifted but still above 3% floor — pooled damage +45%/+31% justifies shipping now with demote-on-A-negative watch at next re-cut. 14-day fresh watch on the 3 new cells through 08-18. See [[project_07_28_post_reboot]], [[project_08_04_session]]."
metadata: 
  node_type: memory
  type: project
  originSessionId: 74becc06-fe2f-4d6a-af5c-9236cb08ecdd
  modified: 2026-08-04T14:55:53.963Z
---

## Ship path

- **Stage 0 (07-13 v0.6.339):** `analysis/h_wg_l3_regression.py` diagnostic. Aggregate per (regime × band) MAE on 10 HURT cells: calm all 4 bands +23-77%, unknown 3 bands +22-38%, sea_breeze 6-11 + 24-47, ne_flow 6-11. Not shippable at Stage 0 — pooled numbers hide halves-instability.
- **Stage 1 (07-14 v0.6.351b):** `analysis/h_wg_l3_regression_stage1.py`. Same halves-verified template as ch persistence gate Stage 2. 30d window split into recent 15d + prior 15d halves.

## Stage 1 verdict (07-14, MIN_N_CELL=200, floor=3.0%)

**6 SKIP / 20 KEEP / 2 MARGIN / 1 THIN / 8 PERSISTENCE_TERRITORY** of 37 judged cells.

**SKIP cells (halves-verified L3 hurts stably):**

| regime | band | pooled Δ | halves |
|---|---|---:|---|
| calm | 0-5 | +24.99% | +12.78 / +34.02 |
| calm | 6-11 | +59.61% | +33.14 / +77.01 |
| calm | 12-23 | +75.53% | +51.99 / +136.57 |
| calm | 24-47 | +73.29% | +65.58 / +87.52 |
| sea_breeze | 0-5 | +4.63% | +5.03 / +3.81 |
| unknown | 24-47 | +34.63% | +28.85 / +57.52 |

**PERSISTENCE_TERRITORY cells (persistence beats L2 in full window — belong to wg residual persistence gate discussion, not L3 skip table):**
- frontal 6-11, 12-23, 24-47
- pre_frontal 12-23, 24-47
- se_flow 12-23, 24-47
- sw_flow 24-47

5 of these 6 (excluding frontal 6-11 and 12-23, and pre_frontal 12-23) exactly match the 6 SHIP cells of today's wg residual persistence gate — confirming clean disaggregation between the two interventions. Persistence gate handles long-lead flow-regime cells; L3 skip handles short-lead calm/edge regimes.

## Proposed extension

```python
SKIP_TABLE[("wg", "l3")] = [
    ("calm",       1, 48),   # bands: 0-5+6-11+12-23+24-47
    ("sea_breeze", 1,  6),   # bands: 0-5
    ("unknown",   24, 48),   # bands: 24-47
]
```

## 7-day gate

- Day 1 = 07-14. Earliest ship = 07-21.
- Weekly re-run of `h_wg_l3_regression_stage1.py` in nightly digest refreshes cells.
- Any halves sign-flip in a SHIP cell demotes it out of the ship set.

## Volume math

Total wg pair rows: ~201k. SKIP cells total ~14k rows = ~7% of live wg L3 firing volume. Small extraction but the pooled damage from these cells is what dragged wg into "MIXED" persistence-skill; removing it should tighten wg further.

## Sibling ships (same architecture, same 07-21 flip)

- [[ws-l3-skip-table]] — 10 SKIP cells, halves-verified, same template. Would dissolve walkforward "drop ws" flat verdict.
- [[wg-residual-persistence]] — Stage 3 wired 07-14. Different intervention (L2 residual add-on, not L3 skip). Same 07-21 flip. Handles the PERSISTENCE_TERRITORY cells this Stage 1 identified.

## Related

- [[07-14-session]] — parent session.
- [[feedback-regime-gate-first]] — the architectural frame.
- [[feedback-whitelist-promotion-gate]] — the 7-day / halves-verified gate governing 07-21.
- [[persistence-skill-baseline]] — original signal (wg pipeline hurts vs L4-alone by −0.09 persistence skill).
