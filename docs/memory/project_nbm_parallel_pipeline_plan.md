---
name: nbm-parallel-pipeline-plan
description: "Architectural direction for extending NBM through the full correction stack. Decision: full parallel cascade (not source-late). Strategy: mirror HRRR structure, init coefficients to identity, use backfill+backstamp trick to reach maturity same-session per layer. Supersedes any prior \"source-late\" thinking."
metadata: 
  node_type: memory
  type: project
  originSessionId: 711ddfce-82b9-458e-8b6c-5a713db81edb
  modified: 2026-08-21T00:57:59.216Z
---

# NBM parallel pipeline — plan of record

**Decided 2026-08-20.** Full parallel NBM cascade. Not source-late.

## The architectural decision

**Full parallel** — HRRR and NBM each run through their own complete correction stack in every collector cycle. Selector picks between `Prod_HRRR` and `Prod_NBM` at the end per (field, lead-band).

**Why not source-late** (selector picks first, one stack downstream): source-late makes Prod-vs-Prod selector comparison impossible, because only one cascade produces a Prod value per row. We already learned in v0.6.440 that raw-vs-raw selection is a bug ([[selector-prod-vs-prod]]). Source-late would reintroduce that bug.

**Why:** the selector's actual job is picking the source whose Prod better matches obs. That requires both Prods observable every hour, which means both cascades run every hour in shadow.

## The build strategy

Every HRRR-side layer gets an NBM twin:

| HRRR piece | NBM twin |
|---|---|
| L2_hrrr | L2_nbm ✅ (reuses HRRR mesonet delta — L2 is shared) |
| L3_hrrr | L3_nbm ✅ (structure built, awaiting backstamp to warm bins) |
| L4_hrrr | L4_nbm — to build |
| L5_hrrr | L5_nbm — to build |
| L6_hrrr | L6_nbm — to build |
| chp, Lc, Lsb, dpbp, cc combine, Lt | chp_nbm, Lc_nbm, Lsb_nbm, dpbp_nbm, cc_combine_nbm, Lt_nbm |
| WDP | WDP_nbm ✅ (already built) |

**What transfers from HRRR (copy directly):**
- Table structures — bin definitions (regime × lead), skip-table cell layouts
- Gate schemas, threshold shapes, τ values, fit windows
- Which cells fire, which cells skip
- Fit-to-apply plumbing pattern

**What does NOT transfer (must fit from NBM residuals):**
- Bias coefficients. HRRR and NBM have different systematic biases per cell. Copying HRRR's numbers to NBM would double error where sign differs.

Initialize NBM coefficients to identity (zeros / no-op). Let them fit against `error_l*_nbm` residual columns in the pair log.

## The backstamp accelerator (why NBM reaches parity fast)

For HRRR we waited weeks/months per layer for forward residual accumulation. For NBM we don't have to:

- **Backfill CF** already fills 108 days of raw NBM in GCS (`gs://myweather-data/nbm_backfill/`)
- **Backstamp for L3** (next session): walk pair log, join backfill blobs, stamp `error_l3_nbm` on 108 days of historical rows. L3_nbm bins clear the 20-pair floor immediately. Fits same day.
- **Same trick works for every layer** — each is pure math on the previous layer's output. Build L4_nbm apply code → run it retroactively against L3_nbm history → synthesize `error_l4_nbm` on 108 days → fit L4_nbm same session. Repeat for L5, L6, specialists.

Each ship is mature the day it ships. No forward-accumulation wait.

## Ship order

1. **Ship 1** (DONE 2026-08-20 evening): backfill CF finished at 2,455/2,568 (~95.6%, rest are NOAA archive 404s). Sizing reverted to 4GB/2CPU.
2. **Ship 2** (DONE 2026-08-20 evening, v0.6.445): `analysis/nbm_backstamp.py` shipped. L3_NBM fit filled 373/384 cells. L1 selector flipped 9 cells to NBM (wg 12-47h, dp 6-47h, cc all leads). Collector redeployed, first post-deploy tick 00:47 UTC verified picking correctly. Router-scope ship-gate NBM lift +8.5% on n=74,528.
3. **Ship 3** (next session, ~1 session): L4_nbm — mirror `analysis/l4_*_fit.py` files, add apply block in `forecast_snapshot.py`, extend backstamp to synthesize `error_l4_nbm`, fit. Live and mature same session.
4. **Ship 4:** L5_nbm — same recipe.
5. **Ship 5:** L6_nbm — same recipe.
6. **Ship 6+:** specialists one at a time (chp_nbm, Lc_nbm, Lsb_nbm, dpbp_nbm). Skip cc_combine_nbm (NBM doesn't publish cl/cm to combine from) and Lt_nbm (HRRR-side retired). Each ship: mirror the fit file, mirror the apply block, backstamp its residual, fit, ship.

Expected total: ~4 sessions remain to full parity. Each session is one file mirrored + backstamp extension + fit + registry update.

## Digest / infra work per ship

Every NBM layer ship also needs:
- New pair-log residual column (`error_l*_nbm`)
- Stratify by `selector_source` where hypothesis scripts fit HRRR-cascade residuals (so mixed-source bins don't contaminate fits)
- KNOWN_LIVE_PIPELINES registry entry (so digest doesn't flap "auto-relabeled STABLE")
- Divergence report key (`L*_NBM_FIELDS`)
- Walkforward validator learns NBM-side cell membership

These are one-time per layer, follow-the-pattern work — no new architecture per layer.

## The cost we're accepting

Maintenance surface roughly doubles. Every future hypothesis script has to decide: HRRR-side, NBM-side, or both. Every HRRR-side refactor has to consider whether the NBM twin needs the same change (see the wdp NBM-sibling patch v0.6.437 as the shape of this tax).

Accepted because the selector-quality argument is decisive: the alternative (source-late) has a selector picking blind on non-representative signal, which is worse than any amount of code duplication.

## Exit ramp (if we ever want it back)

Source-late remains theoretically available as a rewrite. Would require: reordering stamp order in `forecast_snapshot.py`, source-aware coefficients in existing L-layer fits, retire NBM-side layer files. One-time refactor. Only worth doing if the parallel-cascade tax becomes untenable after we've lived with it for months.

## Cross-refs

- [[selector-prod-vs-prod]] — the v0.6.440 rule that made source-late untenable
- [[08-19-evening-handoff]] — backfill CF status, backstamp queued
- [[pair-log-dual-source-schema]] — dual-source residual schema this plan extends
- [[option-1-full-parallel-plan]] — the earlier ship plan, now updated by this doc
