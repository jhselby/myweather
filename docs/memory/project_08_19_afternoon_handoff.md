---
name: 08-19-afternoon-handoff
description: "2026-08-19 mid-day handoff. Morning session shipped Phases 3, 4, 4b (v0.6.435-437) + scoreboard v2 (v0.6.438) + pipeline-status table reshape (v0.6.439) + NBM cascade expansion to 9 fields + Prod-vs-Prod selector rewrite (v0.6.440). Session ended in frustration — Claude iterated too fast on UI, made a Phase 4 raw-vs-raw selector design flaw discovered hours in, and left several known-broken items for afternoon cleanup. READ-FIRST for the afternoon session."
metadata:
  node_type: memory
  type: project
  originSessionId: 0987755d-ce9c-4540-a7e2-2dab3448cc43
  modified: 2026-08-19T15:48:18.516Z
---

# 08-19 afternoon handoff — pipeline hardware done, UI needs polish + design flaws to fix

**This supersedes** [[08-19-morning-handoff]] which was the entry point for the morning session. Read this first for the afternoon.

## What shipped this morning (v0.6.435 → v0.6.440)

### v0.6.435 — Phase 3 L3_NBM (scalar fit + apply)
- `weather_collector/processors/l3_nbm.py` — apply-time per-lead bias, identity fall-through pre-warmup
- `analysis/l3_nbm_fit.py` — pair-log-only fitter (training-serving parity decision documented)
- `weather_collector/data/l3_nbm_curated.json` — stub
- Scalar fields at Phase 3 ship: t/ws/wg/h + wd via sin/cos components

### v0.6.436 — Phase 4 L1 selector (SHIPPED but had a design flaw — see below)
- `weather_collector/processors/l1_selector.py` — apply-time source picker
- `analysis/l1_selector_fit.py` — **initially compared raw HRRR vs raw NBM** — WRONG. Rewritten in v0.6.440.
- `l1_selector_table_curated.json` — first fit
- 🎯 selector tile added to debug page

### v0.6.437 — wdp NBM sibling + v0.6.432 L1 router retired
- `wd_persistence_gate.py` gains `should_fire_at()` + `persistence_value()` public helpers
- `forecast_snapshot` applies wdp gate to `wd_l3_nbm`
- `l1_router.py` deleted; router tile hidden

### v0.6.438 — Scoreboard v2 first cut
- `analysis/scoreboard_v2.py` publisher writes `scoreboard_v2.json` to GCS
- Debug page `renderScoreboardV2()` replaces old `#scorecard-banner` tiles + `#headlineBox` Right-Now table

### v0.6.439 — Per-field pipeline-status table reshaped
- "Current pipeline state — per-field snapshot" → "Per-field pipeline architecture + status"
- Dropped numeric MAE columns (now in scoreboard v2 above)
- New Pipeline column with HRRR + NBM cascades side-by-side
- New Selector column (majority vote — a bug, see below)

### v0.6.440 — NBM cascade expanded + selector Prod-vs-Prod rewrite
- **`_L2_NBM_FIELDS` = 9 fields** (was 5) — added ch/cc/sr/dp. sr no-HRRR-L2 case: `l2_nbm = raw_nbm` passthrough.
- **`L3_NBM_FIELDS` = 8 scalar + wd** — added ch/cc/sr/dp
- **`l1_selector_fit.py` rewritten** to compare `error_{deepest_applied_hrrr_layer}` (HRRR Prod) vs `error_l3_nbm` (NBM Prod). Priority list per field: `dpbp/wsbp/wdp/clp/chp/l6/l5/l4/l3/l2/l1`. Fixes the v0.6.436 raw-vs-raw flaw.
- **Scoreboard v2 extended**: Prod uses `error_{applied_layer}` per row (fixes v0.6.438 L2-residual under-reporting); best_public argmin for in-scope, HRRR-only for out-of-scope; per-cell drill-down; `per_field_band` block; `mae_pct_of_hrrr` rollup.
- Publisher CF PUBLISHERS list gains `scoreboard_v2`.

## Known-broken (afternoon cleanup queue)

### 1. Selected column in Right Now table is a MAJORITY-VOTE LIE
`renderScoreboardV2()` displays `selector_pick` from scoreboard_v2 payload — which is `_select_lift()` collapsing 4 per-band picks into one label via majority vote. For a field with mixed picks (t: HRRR at 0-11h, NBM at 12-47h) this shows one word that doesn't match reality. Joe called this out **repeatedly**; the fix was agreed but never landed.

**Fix options (Joe hasn't picked):**
- Delete the column (per-band picks are on the 🎯 selector tile below)
- Per-band strip `H·H·N·N` with color code
- Show MAE of picked source (Prod-of-selected as a number)

### 2. Style guide inconsistencies across tiles
Session drifted through 3 vocabularies and 2 separator conventions. Joe called this out. Need one pass:
- Metric name: "lift" everywhere (positive = Prod better)
- Verdict: STRONG/GOOD/WATCH/REGRESS only; drop separate green/amber/red bucket
- Separator `·` between counts, `/` only inside paired labels ("7d/24h")

### 3. Scoreboard rollup mean = -39% is honest signal, looks alarming
sr Prod (Lsr on HRRR) = 87.98 MAE, NBM raw sr = 17.77 MAE. sr's -395% contribution drags arithmetic mean to -39%. Will self-correct as selector flips sr to NBM once pair log has enough `error_l3_nbm` for sr (needs post-v0.6.440 collector + ~6-24h). Same story for other in-scope fields where NBM was raw-wins.

**Meanwhile the tile looks alarming.** May want to:
- Show median more prominently than mean (median = +0.1%, honest)
- Or note "post-Phase-4 warmup — expected to normalize in ~1 week"

### 4. National Source Score tile — Joe wants it dropped
Not diagnostic for Wyman Cove. Same data lives in per-field table. Wasn't deleted this session.

### 5. Opportunity-gap column shows bogus +100% for sr
NBM sr = 0.0 aggregate MAE (nighttime hours dominate — real NBM sr correctly predicts 0 at night, so many `abs(0-0)=0` samples). Not a bug per se, but the display makes it look like NBM sr has zero error. Need to either filter nighttime for sr specifically or annotate the caveat.

### 6. `renderPerFieldSnapshot()` still called but numeric columns removed
Function early-return was patched; still populates `.pf-status` spans and `pf-snapshot-narrative`. Works but has dead code paths for missing pf-mae/pf-today cells. Cleanup low priority.

## Current live state (verified 15:50 UTC 2026-08-19)

- **Collector:** v0.6.440 deployed. Stamping l2_nbm/l3_nbm for all 9 NBM-emitted fields.
- **Publisher CF:** v0.6.440 deployed. `scoreboard_v2.json` refit hourly at :00 UTC.
- **NBM ingester CF:** unchanged.
- **NBM backfill CF:** idle (downsized to 2vCPU/4GB per morning cost audit). Coverage stopped at 1,127/2,568 (44%).
- **Pair log:** carries `error_l3_nbm` for t/ws/wg/wd/h (Phase 3 fields) since ~10:41 UTC. ch/cc/sr/dp `error_l3_nbm` begins accumulating from v0.6.440 collector deploy.
- **`l1_selector_table_curated.json`:** all cells fall through to HRRR (safe default — no post-v0.6.440 data yet).
- **`scoreboard_v2.json`:** last written 15:43 UTC via local force-publish. Publisher CF will refit at 16:00 UTC.

## Cost check
- Morning session spent ~$10-11 on GCP (mostly backfill CF at expensive spec R4 + R5)
- Downsize to 2vCPU/4GB shipped in Makefile
- Ongoing baseline: ~$5-10/month for collector + ingester + publisher

## Lessons for the afternoon session (Claude-directed)

See [[feedback_selector_prod_vs_prod]] and [[feedback_ui_incremental_drift]].

**Don't:**
- Take mockups as literal specs (Joe said direction-only, Claude built exact tiles)
- Iterate on frontend without a shared style guide
- Add derived columns (Selected, majority-vote) without asking "does this convey what a reader needs?"
- Build a pipeline mechanism (selector) without asking "does this compare the right things?" (raw vs Prod matters)

**Do:**
- Reason from first principles about what the pipeline actually does
- Verify math against known reference points (old scoreboard's -10.5% would have caught the L2-residual bug immediately)
- Ask before adding features — Joe wants counsel mode
- Show per-cell / per-band data when the summary hides real signal

## Immediate next moves (afternoon session)

1. **Fix the Selected column** (pick a design, ship it) — highest priority per Joe
2. **Style guide pass** (vocab + separators consistent across all tiles)
3. **Delete National Source Score tile**
4. **Verify collector's ch/cc/sr/dp cascade stamping is working** (grep forecast_log.json for new fields)
5. **Consider promoting median over mean in Tile 1** while pre-Phase-4 data dominates 7d window

## Reference (memory)

- [[08-19-morning-handoff]] — morning session entry (superseded)
- [[08-18-evening-handoff-build]] — pre-morning plan (fully executed)
- [[option-1-full-parallel-plan]] — original option-1 architecture doc
- [[pair-log-dual-source-schema]] — post-Phase-4 pair-log field reference
- [[feedback_selector_prod_vs_prod]] — the raw-vs-raw design lesson
- [[feedback_ui_incremental_drift]] — the UI iteration failure lesson
