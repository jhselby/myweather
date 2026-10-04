---
name: wg-l2-windblend-cell-concern
description: "08-12 Stage 0 refined the hypothesis: only sea_breeze/6-11 is a real L2 SKIP candidate (Δ +17.2%, halves A+9%/B+24%, n=315). wg L2 (BLEND_HOURS=4) can't be causing damage where it doesn't fire — long-lead top-of-stack-vs-raw claims from the debug page must be from something else. 6-11h MARGIN cluster (nw/pre_frontal/sw/se) halves-diverge coinciding with BLEND_HOURS 24→4 shrink; re-cut in ~10 days."
metadata:
  node_type: memory
  type: project
  originSessionId: 043cf4f5-2188-4d1d-823b-be30b3f16747
  modified: 2026-08-12T14:46:28.447Z
---

# 08-12 STAGE 0 RESULTS (analysis/h_wg_l2_cell_stage0.py)

Ran Stage 0 on the four originally-flagged focus cells. Result refined the hypothesis:

| cell | Δ L2 vs L1 (full) | halves A / B | verdict |
|---|---|---|---|
| sea_breeze / 6-11 | +17.2% | +9.0% / +24.1% | **L2 SKIP candidate** (n=315) |
| calm / 12-23 | −4.1% | 0.0 / −14.9 | KEEP (L2 helps when it fires) |
| calm / 24-47 | +0.0% | 0/0 | L2 doesn't fire at long lead |
| sea_breeze / 24-47 | +0.0% | 0/0 | L2 doesn't fire at long lead |

**Key correction to the original hypothesis:** wg L2 (wind_blend) uses `BLEND_HOURS=4` since v0.6.384. At 24-47h and mostly 12-23h, L2 output ≡ L1 by design — L2 CANNOT cause damage where it doesn't fire. The debug page's "top-of-stack vs raw +8-12%" at long leads must be from something else (stale calculation, ROUND_DIGITS artifact, or an mae_over_time bucketing detail). That long-lead concern is not on wg L2.

**Genuine finding — sea_breeze/6-11:** L2 hurts by 17% on both halves (n=315). Halves-verified stable direction. Candidate for a wg L2 SKIP entry in `wind_blend.py`, mirroring the L3 SKIP pattern in `decay_apply.py`.

**Secondary observation — halves-divergent 6-11h MARGIN cluster:** nw_flow +22.2% (A 0.0 / B +27.5%), pre_frontal +24.4% (A +0.5 / B +32.3%), sw_flow +20.6% (A −0.5 / B +29.5%), se_flow +15.1% (A +0.6 / B +24.5%). Half B is 07-28→08-12; half A is 07-13→07-28. BLEND_HOURS shrink shipped mid-B (~08-04). L2 fires harder at short lead post-shrink; may be over-blending station consensus at 6-11h in these regimes. Wait ~10 days for B to fully cover post-shrink era, then re-cut.

**Next action (deferred):** re-run this Stage 0 weekly. If sea_breeze/6-11 holds AND the 6-11h cluster resolves (either MARGIN → L2 SKIP or reverts to KEEP), advance to Stage 1 wire. Skip infrastructure: add SKIP_TABLE consult to `wind_blend.py`, or (simpler) narrow BLEND_HOURS per-regime.

---

# ORIGINAL HYPOTHESIS (2026-08-12, superseded by Stage 0 above)

# wg L2 (wind_blend) cell-level concern (2026-08-12)

## Discovery

Investigating the debug page's "wg L3 SKIP_TABLE — 4/7 cells regressing" watch. Today's `h_wg_l3_regression_stage1` halves-verified numbers CONFIRM all 6 measurable SKIP cells (L3 vs L2 hurts by 5.9-28.4% on both halves) — the SKIPs are correct. But the mae_over_time cell-level shows top-of-stack (L2, since L3 skipped) is worse than raw L1 in 4 SKIP cells:

| cell | top-of-stack vs raw L1 |
|---|---|
| calm 12-23 | +23% |
| calm 24-47 | +12% |
| sea_breeze 6-11 | +14% |
| sea_breeze 24-47 | +8% |

Since L3 is skipped in all four, top-of-stack = L2 = wind_blend output. So wind_blend is the culprit, not the SKIP.

## Why the earlier interpretation was wrong

The debug page bullet had said "4/7 SKIP cells regressing." That conflated two measurements:
- **Stage 1 (L3 vs L2)**: validates SKIP — L3 would hurt if applied.
- **mae_over_time (top-of-stack vs L1)**: reveals L2 is hurting even without L3.

Removing the SKIP would make the cell WORSE (L3 would compound L2's damage). The right fix is on L2, not L3.

## Physical hypothesis

Post-BLEND_HOURS 24→4 (v0.6.384) wind_blend is more aggressive at short leads and less at long leads. In calm and sea_breeze regimes at mid-to-long lead, HRRR/GFS may be more accurate than the station consensus (marine air is a homogeneous airmass; station variance at Wyman Cove isn't informative about the regional-scale wind field). Blending pulls the forecast toward station consensus that isn't representative of the model's target scale.

## Deferred — not a same-session workstream

Investigation requires:
1. Per-(regime, band) `L2 vs raw L1` split for wg in those cells (n≥200 floor, halves-verified).
2. Ablation: what happens if wg L2 is skipped in the same cells L3 is skipped?
3. If the numbers hold, propose an L2 SKIP_TABLE entry mirroring the L3 one — or narrow BLEND_HOURS further per-regime.

Related infrastructure: no L2-SKIP_TABLE exists yet for wg. Adding one is architecturally similar to the L3 skip table in `decay_apply.py` but needs the wind_blend layer to consult it.

## Related

- [[project_wg_l3_skip_table]] — the SKIP that's correctly validated today
- [[project_wd_l2_blend]] — sibling closed clean 08-11 after BLEND_HOURS shrink
- `weather_collector/processors/wind_blend.py` — the code that would host any wg-L2 skip
