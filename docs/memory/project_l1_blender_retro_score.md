---
name: project-l1-blender-retro-score
description: "Retro shadow-scoring tool for L1 blender — reconstructs ω from curated ridge coefficients on any pair-log row without needing blend_shadow stamp. Collapses shadow-accumulation wait to seconds. Shipped 2026-09-24 in same session as v0.7.1 (L4 wg). Also flags 3 POS-UNSTABLE curated cells (ch/sw_flow/12-23, wg/nw_flow/0-5, t/se_flow/12-23) — flip watch cells."
metadata: 
  node_type: memory
  type: project
  originSessionId: c0c72043-9870-48db-8ece-306fd86fbedb
  modified: 2026-09-24T13:42:26.775Z
---

# L1 blender retro shadow-scoring tool

Shipped 2026-09-24 as `analysis/l1_blender_retro_score.py`. Companion to `l1_blender_shadow_verify.py`. Reads the pair log, but instead of requiring a live `blend_shadow` stamp on each row, it RECONSTRUCTS ω from the curated table's stored ridge coefficients (β/μ/σ). Works on any historical row.

## Why

Live shadow accumulation is slow: `min_n_fires_7d=50` per cell means a curated cell that only fires when its (regime, band) matches the forecast state can take weeks to escape THIN. Retro scores months of history against the same coefficients in seconds.

## Two uses

1. **Backfill confirmation** when live shadow says THIN. If retro halves-stable lift on 30-90 days agrees with stage1's held-out numbers, that's independent walk-forward evidence and shortens the flip gate.
2. **Pre-ship validation** for candidate stage1 cells (`--stage1 analysis/output/l1_blender_stage1_{field}.json`) — see which STABLE stage1 cells survive on a longer window than the two 25%-quartile test halves.

## Halves-stable difference from stage1

- stage1: 25/25/25/25 split, pair_A trains on Q1+Q2 tests on Q3, pair_B trains on Q2+Q3 tests on Q4.
- retro: 50/50 median split, halfA/halfB on chronological median.

Retro's 50/50 is a stricter, longer out-of-time check because it evaluates coefficients on rows that were BEFORE the fitter's training window (extrapolation backward in time). Divergence between stage1 halves and retro halves is expected and useful — it exposes cells that fit well forward-in-time but don't generalize backward.

## First-run findings (2026-09-24, 13 curated cells)

**10 STABLE / 3 POS-UNSTABLE / 0 NEG.** Pooled ω̄ and cell n match memory exactly (feature extraction and cell binning verified correct).

The 3 POS-UNSTABLE cells all show the same signature: weak/negative earlier-half + strongly positive later-half. Pooled still net-positive. Interpretation: fits generalize FORWARD in time but not backward, so recent regime looks like training but distant past didn't. Not blockers for flip — retro is by design a stricter split — but watch cells during progressive rollout.

- **ch/sw_flow/12-23**: retro halves -2 / +13 (pooled +8%). Stage1 said +7/+14.
- **wg/nw_flow/0-5**: retro halves -8 / +22 (pooled +7%). Stage1 said +13/+27.
- **t/se_flow/12-23**: retro halves -6 / +12 (pooled +3%). Stage1 said +7/+12. Weakest cell overall.

## Related

- [[project_09_23_session]] — v0.7.0 ship + explicit "build retro shadow-scoring tool" in forward list
- [[project_09_21_session]] — memory item that first named this workstream
- [[project_l1_selector_blend_vs_pick]] — the diagnosis
