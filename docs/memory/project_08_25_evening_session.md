---
name: 08-25-evening-session
description: "Aug 25 evening — Total Lift baseline reframe to NBM user default, evidence-driven NBM skip transfer (only wg L3 shipped), live tile renderer wired, product mental model settled as \"NBM + local corrections + HRRR-substitution where it wins\""
metadata: 
  node_type: memory
  type: project
  originSessionId: db1141ff-d13b-4e67-892c-8549b5624841
  modified: 2026-08-26T00:00:43.064Z
---

Continuation of [[project_08_25_session]] (morning session — v0.6.471 killed sr l5_nbm, v0.6.472 trimmed L3_NBM_FIELDS, scoreboard redesign). Evening arc: v0.6.473 → v0.6.479.

## The big reframe (v0.6.478)

Total Lift baseline went through three iterations in one sitting:

1. **pre-v0.6.477: pooled min(hrrr_mae, nbm_mae)** — one winning raw source per field per window. Too generous — credited the pipeline for beating whichever raw wins on average, when any user picking the better source per lead was already beating that baseline.
2. **v0.6.477: per-row oracle min(|error_hrrr_row|, |error_nbm_row|)** — strictest possible. Numbers went catastrophic (t −60%, dp −127%, sr −112% 7d). Joe pushed back: "the regular weather dork doesn't dynamically pick per lead — they open one app." He was right; this baseline is fantasy.
3. **v0.6.478: NBM raw for NBM-scope, HRRR raw for HRRR-only fields** — the honest user default. NBM is the NWS backbone (iPhone Weather, weather.gov, vendor consumer displays). For cl/cm/pp/pa/pr where NBM doesn't publish, baseline = HRRR raw.

**Why:** the meaningful question is "did we beat what your phone already shows you," not "did we beat a fictional oracle." Real 24h Total Lift readings under v0.6.478: t +36.7%, ch +51.0%, wg +7.4%, cm +10.1% wins; h −60.9%, dp −344.3%, sr −14.7% honest losses (NBM crushes us on dp/h and we're not catching up — actionable).

**How to apply:** Total Lift, all scoreboard aggregations, and Prod trend all now describe "vs user default." Any future baseline question defaults to "what would the user get without us?" See [[feedback_recommend_never_menu]] for the walkback pattern — I offered menus, Joe kept asking direct questions, we converged on the right answer.

## Product mental model (final)

We are building **a local model starting with NBM plus a robust local correction stack for our specific location and station network. HRRR-through-its-own-pipeline is a specialized substitution the selector fires only where Prod-vs-Prod proves it wins per (field, band).**

Not two parallel first-class pipelines with a symmetric chooser — even though the mechanism is symmetric (Prod-vs-Prod comparison). The framing matters for how we describe the product publicly, prioritize R&D, and set the story on the debug page. NBM cascade needs investment; HRRR cascade is a specialty that grew first because HRRR arrived first.

**Concrete implications, unshipped:** debug page language sweep can happen slowly (National Source panel already matches; selector-quality naming needs a look; tile subtitles updated Total Lift + renamed "Selector Quality" → "Selector Skill" tonight). The selector default direction doesn't need to flip — the current MIN_LIFT_PCT=3% is a stability gate, not a favor for HRRR, and works either way under symmetric measurement.

## Evidence-driven NBM skip transfer (v0.6.475/476)

Proposed HRRR skip topology as an educated-guess prior for NBM:
- wg L3: 8 cells from decay_apply.SKIP_TABLE[('wg','l3')]
- cc L4: 5 cells from decay_apply.SKIP_TABLE[('cc','l4')]
- chp_nbm ch: 10 cells from ch_persistence_gate._CELL_SKIP

Built `analysis/nbm_counterfactual_rescore.py` to grade any proposed skip topology against 30 days of backstamped pair data — walks per-layer error stamps (no re-fitting, no re-inference; just picks a different column of already-computed errors per row).

Initial rescore showed 0 selector flips + only 3 cells with |Δ NBM lift| ≥ 0.5%, all slightly negative. Diagnosis: deep NBM layers (l4/l5/chp/wdp) only had ~4 days of live coverage because those layers shipped 08-21. Extended `analysis/nbm_backstamp.py` with L4_NBM counterfactual (mirrors what forecast_snapshot.stamp() would stamp — hour-of-day lookup against l4_nbm_curated.json). Added 44K historical error_l4_nbm stamps across 30 days.

Re-rescore with L4 coverage extended: **wg L3 net +0.16% to +0.58% at 6-47h (KEPT — shipped in curated JSON); cc L4 ±0.11% wash (REMOVED); chp_nbm ch −1.15% at 24-47h (REMOVED — thin at 930 chp rows, re-evaluate ~09-04 when 14 days of live chp_nbm stamps accumulate).**

**How to apply:** any future NBM skip proposal → run `nbm_counterfactual_rescore.py` first with the proposed skip topology, ship only cells with 30-day evidence of net-positive lift. Anti-'ship everything from HRRR' discipline in force. See [[feedback_verify_completeness_claims]] + [[project_hypothesis_backlog]].

**Follow-up:** extend backstamp with chp_nbm / wdp_nbm counterfactuals (needs persistence-of-obs at run_time + kalman + gate primitives — bigger project than L4). Deferred to when there's a specific proposal that needs grading.

## Debug page

- v0.6.473: added Mean row to per-field diagnostic tfoot alongside Median.
- v0.6.474: split "Pipeline" column into "Pipeline · HRRR" + "Pipeline · NBM" across all 14 field rows. Status column stays merged (notes interweave both cascades).
- v0.6.475 (scoreboard tiles): added mean placeholders alongside median for all 4 headline tiles.
- v0.6.479: minimal live tile renderer — populates Total Lift / Pipeline Lift / Selector Skill / Prod Trend median + mean 7d/24h from per_field_scoring.json. Data-tile= + data-cell= DOM hooks. Colors sb-good/warn/bad by value.
  - Explicitly out of scope: W/F/L breakdown lists, per-field diagnostic table live wiring, National Source panel. Those stay static.
  - Per-field diagnostic table sub carries a ⚠ warning that its numbers are pre-v0.6.478 baseline — use tiles above for live.

## Files changed
- `weather_collector/data/skip_table_nbm_curated.json` — 8 wg L3 cells shipped; history block records the full trial including rejected buckets.
- `analysis/nbm_counterfactual_rescore.py` — new. Rescore tool.
- `analysis/nbm_backstamp.py` — L4_NBM counterfactual extension. `_maybe_add_l4_nbm` helper backfills rows that predate the live l4_nbm ship (v0.6.451, 08-21).
- `analysis/per_field_scoring.py` — baseline flipped to NBM raw for NBM-scope, HRRR raw for HRRR-only. `_new_bucket` gained `best_raw_row` bucket (still populated for potential future use — currently unused by `_compute_field` since the v0.6.478 baseline doesn't need per-row min anymore).
- `corrections_debug.html` — Mean row, split Pipeline column, mean placeholders on tiles, live tile renderer (`renderScoreboardTilesMinimal`), 08-25 evening timeline entry, per-field diagnostic ⚠ note.
- `index.html` — v0.6.472 → v0.6.479.

## Tue afternoon → evening ships (v0.6.480 → v0.6.488)

All shipped, committed, pushed, publisher redeployed where backend touched. Tree clean at end of day.

- **v0.6.480** — `renderPerFieldDiagnostic()` wires the 08-25-redesign per-field diagnostic table live from `per_field_scoring.json`. Total Lift + HRRR/NBM Pipeline Skill + n populated; Hit Rate + Value Captured dashed pending.
- **v0.6.481** — Backend adds `hit_rate_pct` + `value_captured_pct` per NBM-scope field to `per_field_scoring.py` (paired chosen/alt Prod pool). Frontend wires them + Median/Mean tfoot rows include them.
- **v0.6.482** — Prod Trend noise suppression: null `prod_trend_pct` when `n_prod_prior < 50` or field in `TREND_EXCLUDE_FIELDS = {pa, pp}`.
- **v0.6.483** — dp excluded from Total Lift aggregate + tile. Rationale: prod_dp = Magnus(prod_t, prod_h), no independent skill.
- **v0.6.484** — cc joins dp exclusion universally (all four tiles + all five diagnostic tfoot columns). Rationale per [[project_cc_derived_field]]: HRRR raw cc = max(raw cl,cm,ch) verified 20/20; our prod cc = Ccd max(prod cl,cm,ch) for ~85% ticks; no independent correction chain since 2026-07-30 v0.6.390.
- **v0.6.485** — Tile W/F/L breakdowns wired live (were hardcoded static). Includes regression: used NBM_SCOPE which dropped cl/cm/pr from Total Lift + Pipeline Lift.
- **v0.6.486** — Restores cl/cm/pr to Total Lift + Pipeline Lift via new `LIFT_SCOPE = ["t","h","ws","wg","wd","cc","ch","sr","dp","cl","cm","pr"]`; DERIVED_EXCLUDE + NON_MAE_EXCLUDE applied via `_agg`. Selector Skill stays NBM-only. dp + cc rows in diagnostic table become placeholder-only (field name + derivation note, all metric cells dashed) — "reserved for future resurrection (dp bias layer, cc composition tuner)."
- **v0.6.487** — Prod Trend backend: new `prod_wider` / `prod_prior_wider` buckets (any row with `e_prod`, no pool intersection). Both windows use the wider pool → apples-to-apples trend that survives the 7d NBM backstamp thin-out. Total Lift / Chooser Lift / Pipeline Lift stay on the intersected pool for v0.6.468/470 consistency. Publisher redeployed. New JSON fields: `prod_wider_mae`, `prod_prior_wider_mae`, `n_prod_wider`, `n_prod_prior_wider`. Frontend: Notable Calls block dashed with "wiring pending" note (was static, listed dp in 2nd worst — inconsistent with the no-dp/cc rule and violates [[feedback_no_fabricated_data_on_page]]).
- **v0.6.488** — National Source panel wired live (per-field hrrr_raw_mae vs nbm_raw_mae, dp+cc excluded). Health & Reliability partial wired: Confidence (HIGH = halves agree AND |lift|≥10; LOW = disagree OR |lift|<3; MED = else) + Halves-agree (fraction of fields matching sign, "noisy" flag <70%). High-conf cells stays dashed — needs per-cell feed.
- **v0.6.489** — dp/cc placeholder-row derivation notes moved from inline (first-column) to footnotes below the tfoot. The long inline note was stretching the field-name column and misaligning the table.

## Scoreboard truth-source discussion (documented for context)

Deep dive on dp scoring reached the settled framing:
- Our obs_dp is `Magnus(WU-network-corrected T, WU-network-corrected H)` — hyperlocal Wyman Cove truth. There is no independent hyperlocal dp truth available: Tempest dp is Magnus off Tempest's own Sensirion T+RH, WU PWS network doesn't emit dp (we pull T+RH only), METAR/ASOS at KBVY sometimes chilled-mirror-measured but the station is inland and useless as a Wyman Cove truth (Joe: "we're on the fucking water"), buoy doesn't emit dp.
- dp Total Lift's remaining bias (our Magnus vs NBM's independently-blended DPT scored against our Magnus'd truth) is unfixable given the constraint but not the primary story — the main issue was double-counting t/h through dp, which v0.6.483/484 fix by exclusion.
- **Do not** propose sourcing dp truth from a single station (KBVY, KBOS, or any airport). Joe explicit: single-station undermines the whole hyperlocal-network thesis.

Verified NBM DPT is a first-class MAE-weighted URMA-corrected blend, not a post-hoc formula off blended TMP+RH. Source: [Description of Field-Selected Algorithms for NBM v4.1](https://vlab.noaa.gov/documents/6609493/7858320/Description_of_Field-Selected_Algorithms_for_National_Blend_of_Models.pdf).

## Follow-ups queued for future sessions

**BLOCKING — must be done before the next session can end:** the debug page's own hand-curated narrative content (Recent activity timeline, Current state journal, Post-ship watches, per-field pipeline architecture Status column) has NOT yet been updated to reflect the v0.6.480 → v0.6.488 ships from this session. The scoreboard tiles + diagnostic table now show live numbers, but the narrative under Current State and the Recent activity block still describe the pre-v0.6.480 state as "today." The next session must roll v0.6.480 → v0.6.488 (plus whatever it ships) into a consolidated Recent activity entry for 2026-08-25 (evening) and update any journal entries the day's ships touched. Per [[feedback_debug_page_full_sweep]] + [[feedback_digest_triage_discipline]]. Do this before ending the next session, not before starting it — tomorrow's morning digest should be the trigger.

- **Notable Calls + High-conf cells wire.** Both need a per-(field, lead-band) MAE aggregation. Either extend `analysis/per_field_scoring.py` with a per-cell breakdown, or point the renderer at `time_series_diagnostic.json`'s `per_layer_mae_by_lead`. dp + cc excluded when wired.
- **dp bias layer (Joe's ask).** Learn a decaying-average bias between our Magnus(prod_t, prod_h) and observed hyperlocal Magnus'd dp; subtract at apply. Mirror the L2 Kalman decay pattern. Ceiling limited (dp analytically pinned to t/h), but could catch nonlinearity + correlated t/h residual amplification through Magnus. Would resurrect dp as a scored field.
- **cc composition tuner** (parallel work): `h_cc_blend_formula.py` Stage 0 tuner had a candidate cell (pre_frontal/0-5h random +3.5% at n=2,115). Re-check to see if any composition wins are still on offer.
- **Better dp formula (marginal):** Arden Buck vs Magnus — <0.1°C difference at typical ranges. Only after bias layer if that opens the door.
- **14-day live-watch on wg L3 skip transfer** — deploy cells should materialize +0.16-0.58% counterfactual lift; if not by 09-01 daily digest, roll back.
- **chp_nbm / wdp_nbm counterfactual backstamp** when a re-evaluation triggers.
- 14-day live-watch on wg L3 skip transfer (deployed cells should materialize the counterfactual lift in real data — if not by 09-01 daily digest, roll back).
- chp_nbm / wdp_nbm counterfactual backstamp when a re-evaluation triggers.
- Optional: rename "Selector Quality" → "Selector Skill" everywhere else on the page (only tile label got renamed).
- Optional: sweep of language across the page to reflect the "NBM + local corrections + HRRR substitution" framing incrementally.
