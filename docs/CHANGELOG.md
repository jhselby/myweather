# v0.6.0 — Decay-correction milestone

<details open>
<summary><strong>v0.6.317 • July 9, 2026</strong></summary>

- **Fitter preflight — applied-layer consistency gate.** Audit logic refactored from `analysis/applied_layer_audit.py` into `weather_collector/processors/applied_layer_audit.py::run_audit()`; the analysis CLI is now a thin wrapper delegating to the same function. `decay_fit.py::fit_decay_corrections()` calls `run_audit()` at the top of every daily Fitter tick; on any failure it logs the specific problems and returns without publishing new `decay_corrections.json` — the previous (still-valid) corrections stay in place. Same two categories as the standalone: (A) every field in `L3_FIELDS`/`L4_FIELDS`/`SKIP_TABLE` resolves in `TARGET_ARRAY` + `CAPS`; (B) every declared `derived.X.Y` read in the correction stack has a writer somewhere under `weather_collector/`. Closes the loop between "Fitter tick recommends" and "would this recommendation actually apply?" Upgrades the audit from a next-morning digest surface to a real-time deploy gate.

</details>

<details open>
<summary><strong>v0.6.316e • July 9, 2026</strong></summary>

Analysis-side bundle — three small, unrelated additions/fixes ganged into one push:

- **`analysis/applied_layer_audit.py` — new.** Static consistency checker for the correction stack. Catches the class of mismatch that hid the ws L3 skip-table dormancy for 4 days: config declares a field gets a correction, but nothing writes the state the correction reads from. Two categories: (A) every field in `L3_FIELDS` / `L4_FIELDS` / `SKIP_TABLE` resolves in `TARGET_ARRAY` + `CAPS`; (B) hand-curated table of `(reader_module, derived_path, writer_regex)` — each declared derived read has a writer somewhere under `weather_collector/`. Seeded with three known reads of `derived.state.regime_synoptic`. Exit 0 clean, exit 1 on any failure. Auto-picked up by the nightly digest's `analysis/*.py` loop — first digest run 07-09 06:25 PASSes green. Fitter-preflight wiring is a separate follow-up.
- **`analysis/h_wind_shift_rate_orthogonality.py` — verdict guard.** Added an `ortho == 0 → KILL` branch above the `red/total ≥ 0.7` KILL check. Yesterday's digest surfaced this as MIXED with `0 ortho / 36 total. Narrow promote or hold.` — nonsensical, since there are no orthogonal cells to narrow-promote. Root cause: today's balance was `0 ortho / 25 red / 0 confounded / 11 ambiguous` — redundant ratio 25/36 = 69.4%, just below the 0.7 KILL threshold, so it fell through to MIXED. Semantically 0 orthogonal is a KILL regardless of the specific redundant ratio. Guard fires cleanly on today's numbers; verdict now reads `→ KILL: wind_shift_rate is captured by C1a (0 orthogonal cells / 36 — nothing to narrow-promote).` Restores the 06-24 kill conclusion.
- **`analysis/c1_stage4_audit.py` — non-precip subset audit added.** New `SUBSET_EXCLUDE_FIELDS = {"pp", "pa"}` + `subset_view()` helper computes a parallel counts / recommendation over the SHIP-cell results with pp + pa filtered out. Prints alongside the primary verdict for both legacy and multi-axis views; JSON output gains `non_precip_subset` blocks. Motivation: the 07-08 07-11 contingency assumed the Stage 4 failure was measurement-only (MAE→0 drift-metric blowup on pa/pp dry-regime cells) and that a partial ENABLE would be safe on the non-precip subset. Today's first read disconfirms: legacy full 17 PASS / 12 WATCH / 13 FAIL (40%); subset 15 PASS / 10 WATCH / 7 FAIL (47%). Excluding pp + pa cut 6 FAILs but only lifted pass rate by 7pp — still below the 60% MIXED threshold. Top non-precip drifter: `cm/0-5h [stable] +78.2%`. So the escape hatch generalized to the legacy C1 axis is off the table; the standalone C1h + C1d table path remains viable. 07-11 checkpoint plan tightened accordingly in memory.

No live pipeline changes; all three files are analysis-only. No collector deploy.

</details>

<details open>
<summary><strong>v0.6.316d • July 8, 2026</strong></summary>

- **07-08 checkpoint closed + debug-page scorecard refresh.** T Production convergence verified via today's 15:07 Fitter: T Prod −1.1% vs raw / +0.3% vs L2 (sitting on the L2 line); pr flat 0%; ws +5.3% vs raw (skip table healthy — already below both +22.7% and +19.6% targets, still shrinking); sr −4.6% vs raw (baseline still contaminated through 07-10, expected). Removed the "07-08 T Production convergence check" checkpoint from all three debug-page slots (Calendar, inline commentary, Q/E/D detail block) — the whole "Mon 07-08" day-of-week rendering bug was orthogonal to the passing verdict, so removing the block also drops the misrendered label. Winning-fields summary + Real-Production-per-field table refreshed to today's numbers for t/pr/ws — t swapped from "+9.3% in flight" (yellow) to "−1.1%" (green), pr from "+2.6% in flight" (yellow) to "0.0% (flat)" (dim), ws story kept intact but leading percentage moved 25.7% → 5.3% with the "already below target" clause added.

</details>

<details open>
<summary><strong>v0.6.316c • July 8, 2026</strong></summary>

- **Retire the migration-language caveat on the accuracy section.** 7-day window fully filled with post-v0.6.269 stamped rows per plan; live GCS confirms every primary field at 48/48 coverage (cc/ch/cl/cm/dp/h/pa/pp/pr/sr/t/wg/ws), which crosses the ≥40/48 threshold and drops the "*" marker on every Production card. Only wd stays at 0/48 (circular field, structural — separate treatment). Debug-page prose on the Accuracy section and the "Per-row applied-layer stamping" ship-log item now describe the auto-drop as a stable steady state rather than a pending migration. n≥30 noise-floor rationale kept — small-sample noise protection is orthogonal to the migration window.

</details>

<details open>
<summary><strong>v0.6.316b • July 8, 2026</strong></summary>

- **Lc gate history writer + 7-day rolling check.** `analysis/lc_fit.py` now appends each run to `.cache_lc_gate_history.json` (30-day retention) and prints a 7-day rolling gate summary: entries/distinct days in window, FIT/HOLD day rollup, trailing FIT streak, and SHIP-cell stability (which cells' verdicts changed within the window). `gate_clear` requires ≥7 distinct days + zero HOLD days + zero SHIP-set changes. Mirrors the `.cache_l5_gate_history.json` pattern, adapted for the analysis-side context (lc_fit runs inside the nightly digest via the `for f in analysis/*.py` loop). **Real state:** today = day 1/7. The previously prose-codified "day 5/7" was fiction — the nightly digest was running `lc_fit` but nothing persisted per-run verdicts, so no dated evidence existed for the manual count. Same silent-failure class as `feedback_verify_writers_for_read_paths`. Silver lining: today's SHIP set (15 cells) matches the 07-04 ship-day read in shape and magnitude — directional evidence is fine, formal gate is now machine-enforced going forward. Earliest real flip: 2026-07-15.

</details>

<details open>
<summary><strong>v0.6.316a • July 8, 2026</strong></summary>

- **Canon page sweep for v0.6.316 ship.** Recent-activity block gets today's entry (v0.6.316 Stage 3 wiring + Stage 1/2 build for both axes) and the 07-05 entry rotates out per the rolling 3-day window. Executive-summary cards for C1h + C1d flip from candidate ("ortho passed", "resurrected") to Stage-3-wired-gated-OFF with correct day counts (C1h day 2/7 as of 07-07 verdict; C1d day 5/7 as of 07-04 verdict; pre-frontal day 5/7). Retired section's "C1d killed 06-29 / re-confirmed 07-02" language deleted and replaced with a pointer to the C1 confidence-layer section (C1d is no longer purely retired). Big C1 confidence-layer bullet updated: 5 axes → 7 axes, marginal C1h/C1d wiring flagged as standalone tables kept off the multi-axis join to avoid cell-dilution. Stage 1 rolling-table entries + killed-hypothesis C1d block sync'd to the same Stage 3 stamp. Scope note added: C1h wiring is broader than the ortho-verdict narrow scope (ch ambiguous, t redundant included) — Stage 4 audit filters at flip. Applicability map on live GCS confirmed rendering all 7 axes.

</details>

<details open>
<summary><strong>v0.6.316 • July 8, 2026</strong></summary>

- **C1h + C1d Stage 3 wired (gated OFF).** `confidence_layer.py` now loads two new curated marginal-premium tables (`c1h_curated.json`, `c1d_curated.json`) and composes them multiplicatively on top of the existing `base_displayed` MAE. C1h reads `forecast_log.json` for the ~6h-old L1 snapshot (rejects matches >90 min off), compares to current L1 at each band's midpoint target hour, fires when `|Δ| > THRESH[field]` (cc 20, cl 15, cm 15, ch 15, t 3). C1d classifies live `cloud_inter_source_sigma` against Q1/Q3 cuts (`≥Q3 → "high"`) and applies the WIDEN/NARROW premium from the curated cell. Both add per-cell `c1h` + `c1d` sub-dicts to `weather_data.confidence.cells[field][band]` and telemetry to `live_axes` (`c1d_slot`, `c1h_hits`, `c1d_hits`). Stage 3 stamp is transparency-only — `ENABLED` still False; Stage 4 audit gates the flip.
- **Stage 1 + Stage 2 for both axes**: `analysis/c1h_calibration.py` + `c1h_curate.py` produced 15/15 SHIP cells (all WIDEN; strongest cl 6-11h +290%, ch 6-11h +183%). `analysis/c1d_calibration.py` + `c1d_curate.py` produced 13 SHIP + 1 MARGINAL + 2 SKIP (ch short-lead +85-93%; cc 24-47h MARGINAL NARROW -7.06% — outlier detector under 75% dominance threshold, flagged for the eventual Stage 4 audit).
- **Live tick verification (14:07 UTC)**: 4 C1h fires (cc/ch/t 6-11h widen ×1.47/×2.83/×1.24 matching curated pcts); C1d slot `null` this tick (σ in middle Q1<σ<Q3 band, baseline no-op). `applied: False` throughout — no UI impact.

</details>

<details open>
<summary><strong>v0.6.315 • July 7, 2026</strong></summary>

- **"Right now" headline box: 4-tile grid → all-fields correction table.** Old box showed an arbitrary 4-tile subset (Temp / Humidity / Confidence / Briefing source) — two field tiles that duplicated the pipeline state table below, plus two operational-status tiles. Replaced with a 13-row table showing Field / Raw model / Production / Correction for every field the pipeline has raw-vs-corrected data for at `hourly[0]` — the current-tick composed shift the pipeline is applying to THIS forecast (fills a gap: no other page section shows composed current-tick corrections in one view). Field labels carry symbol in parens (`Temperature (t)`, `Wind speed (ws)`, etc.) to teach the vocabulary the scorecard uses. Correction column color-coded green (pipeline adds), red (subtracts), gray (flat). For percentage-valued fields (h, cc/cl/cm/ch, pp), the correction unit is `pts` not `%` to avoid the "+57%" reading as a multiplier ambiguity. t/h source `hyperlocal.weighted_bias` (raw derived as corrected − bias); other fields source `hourly.raw_*` directly. Degraded-mode handling preserved (t/h show "paused" when GFS/HRRR unavailable). Confidence + Briefing source drop to a compact ops-status footer row below the table.
- **Scorecard banner moved above "Right now" box** — headline-at-top convention (the top-line pipeline health number is the first thing a debug visitor sees). Was headline / scorecard; now scorecard / headline.

</details>

<details open>
<summary><strong>v0.6.314 • July 7, 2026</strong></summary>

- **C1h ortho check shipped + PROMOTE verdict.** New `analysis/h_c1h_orthogonality.py`: for each pair row at lead L≥6, computes trend-direction axis H = |fc[L] − fc[L−6]| > per-field threshold (mirrors `h_trend_direction.py` thresholds), then cross-tabs by (field × band × H × C1f × C1e) to test whether C1h's MAE elevation persists inside AND outside the incumbent-fires subset. Result: **10 orthogonal cells / 29 judged across two checks → PROMOTE narrow scope {cc, cl, cm}.** Detail: cm orthogonal in all 3 bands vs C1f (mid cloud rising is its own signal); cl orthogonal in all 3 bands vs C1e with elevation up to 6.00× at 6-11h (huge signal outside the post-frontal window); cc orthogonal at 6-11h vs both. ch ambiguous everywhere — would not ship for ch; t redundant on both checks — would not ship for t. Debug page updated to reflect: tri-column "What's improving" card shows ✓ ortho passed + narrow-promote gate day 1/7; long-form Stage 1 bullet + rolling table row updated with full verdict. C1h now on the 7-day live-layer change gate (earliest ship 2026-07-14) and separately gated on C1 as a whole clearing Stage 4 audit (currently NOT READY).

</details>

<details open>
<summary><strong>v0.6.313 • July 7, 2026</strong></summary>

- **Accuracy card Production column: red/green color-coding per lead band.** Was `color: #ffffff !important` with no comparison logic — every Production cell rendered white regardless of value. Now each cell compares its Production MAE to the same band's Raw (L1) MAE: green if Production < Raw by >0.5% (correction helped), red if Production > Raw by >0.5% (correction hurt), white if within ±0.5% (noise / flat). Threshold matches the scorecard's `FLAT_EPS` so per-band coloring and the scorecard's flat bucket agree on what counts as signal.

</details>

<details open>
<summary><strong>v0.6.312 • July 7, 2026</strong></summary>

- **Debug page canon refresh + analysis wiring.** Sweep: "Last curated" and "Current pipeline state" dates bumped to 2026-07-07. Recent activity rolling window rotated (07-04 entries fall off; new 07-07 entries added). Calendar past-dated "Mon 07-06" entry removed; added 07-11 sr shortwave-vs-cc confound checkpoint. sr Lsr snapshot (both quick-view row and long-form Engineering status paragraph) updated with the first shadow-log read outcome (n=1,200, day 1): the unit-mismatch hypothesis was partially wrong — shortwave MAE is *not* uniformly smaller than direct-beam MAE; direction is regime-specific. nw_flow shortwave MAE −55%; pre_frontal/sea_breeze/unknown show shortwave *worse* with bias flipping from direct-under to shortwave-over. Prior "switch to shortwave + refit Lsr" fix chain now on hold pending Cause A (cc-miss surfacing through sr) vs Cause B (real Open-Meteo diffuse/aerosol gap) resolution. Analysis changes shipped alongside: `analysis/runlog/divergence_report.py` regex fix (was greping `L3_ENABLED`/`L4_ENABLED`, walkforward emits `L3_FIELDS`/`L4_FIELDS` — both keys silently fell into UNKNOWN status in every digest); new `analysis/sr_shortwave_cc_confound.py` diagnostic to disentangle Cause A vs B, queued for first real read ~2026-07-11.

- **Engineering-updates subsections now collapsable.** The two title-blocks under "Engineering updates — where we are" ("Current pipeline state" and "Recent activity — rolling 3-day window") were plain `<div>`s while the cards below (Production stack, Built not applied, Retired, Upcoming decisions) already used `<details open>`. Converted both to `<details open>` with `<summary>` headers matching the existing card pattern. Meta-line already read "click any sub-box header to collapse it" — the affordance now works everywhere it claimed to.

- **Deleted broken L3/L4 applicability banners.** `<div id="banner-l3-paused">` and `<div id="banner-l4-paused">` were meant to surface when the applied L3/L4 field set differed from the fitted set. The intended check was never wired up — `renderMeta()` set `.hidden = false` on both unconditionally on every page load, and the banner body was just a static "⏸ L3/L4 — applicability state changed." string with no diff info. Effectively persistent noise duplicating the "Currently applied: …" span already in the Applicability div above. Removed both div wrappers and the two JS lines that populated them.

- **Scorecard banner: three honesty fixes.** (a) *Winning-fields denominator now excludes flat.* Was `7/13` (12 MAE + 1 Brier); now `7/10 · 2 flat` where the denominator is winners + regressors only. Reason: `pa` (no correction applied, prod == raw exactly) and `cl` (L2 blend confined to lead 0, deliberately excluded by the 1–47h average) were counting against the pipeline as "not winning" even though there's no attempt to correct them in the measured range. Conflates "no attempt made" with "attempt failed." (b) *pp Brier pulled out of the Overall mean into its own line.* The footer note already said "pp excluded (Brier, not MAE)" but the code was folding pp into the same `rows` array the mean iterated. Now a separate `brierRows` array renders as `Brier-scored · pp<sup>B</sup> ±N.N%` below the main tiles; Overall / Winning / Biggest gain / Worst regression / Worst cell all operate on MAE fields only. Footer note reworded from "pp excluded" to "pp shown separately." (c) *Median shown alongside mean in the Overall tile.* Mean is amplified by tiny-denominator fields (e.g. pressure raw MAE ~0.019 → any small change reads as a huge %). Median is robust to that. When the two agree the mean is trustworthy; when they diverge, it's the honest signal that a couple big wins are carrying the average. Mean is primary (larger text), median subordinate underneath, each colored red/green independently.

</details>

<details>
<summary><strong>v0.6.311 • July 6, 2026</strong></summary>

- **Fix 10° coverage gap in `classify_synoptic_regime`.** Caught immediately after v0.6.310 wired `derived.state` — post-deploy verification showed `regime_synoptic: null` on a tick where the classifier should have returned a label. Inputs looked fine (wind_dir=84.4°, wind_speed=9.8, pressure=1021.5 hPa, temp=70.6°F, pressure_trend_3h=0.6). Cause: `classify_synoptic_regime` had branches `30 ≤ d < 80` (NE), `90 ≤ d < 200` (SE), `200 ≤ d < 290` (SW), `290 ≤ d or d < 30` (NW) — leaving `[80, 90)` uncovered. Any easterly wind in that 10° window returned None. This has been silently affecting every pair-log record + live tick since the classifier was written. Fix: extend NE range to `[30, 90)` so easterly winds classify as `ne_flow` (matches Marblehead's marine/cool-air behavior for east winds). Post-fix expectation: current tick's regime_synoptic becomes `ne_flow`, `skip_table_l3_cells_skipped` finally non-zero because ws L3's ne_flow skip cells activate.

</details>

<details>
<summary><strong>v0.6.310 • July 6, 2026</strong></summary>

- **Populate `derived.state` every tick — L3/L4 skip table starts firing.** Silent structural bug caught while chasing the shortwave work: multiple processors (`decay_apply.py`, `solar_correction.py`, `backtest_snapshot.py`, `confidence_layer.py`, `state_stratified.py`) read `weather_data["derived"]["state"]["regime_synoptic"]`, but nothing in the codebase ever WROTE to `derived["state"]`. Every read got `None`. `solar_correction.py` worked around it by classifying inline (line 255-269 comment says exactly that). But `decay_apply.py:461` didn't — it read None and `_should_skip()` fail-safed to False on every row, which means the L3/L4 skip table shipped v0.6.279 on 2026-07-02 **has never fired since ship day**. Current tick's GCS `weather_data.json` proves it: `skip_table_l3_cells_skipped: 0`, `skip_table_l4_cells_skipped: 0`, `skip_table_regime: None`. Every ws L3 row in ne_flow all bands + sea_breeze 0-11h has been applying despite the skip cells being populated in `SKIP_TABLE`. That's four days of the +25.7% ws Production regression that the skip table was designed to fix continuing to hit users. New `processors/state_stamp.py::stamp_state()` runs after `preserve_raw_forecast_arrays` and before `stamp_solar_correction` / `apply_decay_corrections`. It calls `classify_synoptic_regime` + `classify_flow_regime` on current-tick wind/pressure/temp and populates `derived["state"]` with `regime_synoptic`, `regime_flow`, `wind_dir`, `wind_speed`, `wind_octant`, `cloud_cover` — matching the schema every downstream reader expects. Expected impact: next-tick `skip_table_l3_cells_skipped > 0` when the regime is ne_flow or sea_breeze, and the ws Production %-vs-raw should shrink toward what `production_whatif.py ws_L3_skip` predicted.

</details>

<details>
<summary><strong>v0.6.309 • July 6, 2026</strong></summary>

- **Shadow-log model shortwave + diffuse on every sr pair row.** Next step in the sr Lsr unit-mismatch fix chain (see v0.6.308). Every sr pair row in `forecast_error_log.jsonl` now carries `forecast_shortwave` (from Open-Meteo `shortwave_radiation`) and `forecast_diffuse` (from `diffuse_radiation`) alongside the existing `forecast_l1` (direct-beam only). Primary sr forecast stays direct-beam for now — this is diagnostic data. `analysis/sr_shortwave_bias.py` reads the pair log and compares `|observed − forecast_direct|` vs `|observed − forecast_shortwave|` per regime; expected outcome once a few hours of daytime pairs accumulate: shortwave MAE much lower than direct-beam MAE in every regime (because Tempest measures total shortwave), with the largest collapse in ne_flow + calm where Lsr misbehaves worst. That result would confirm Lsr has been fitting the definitional gap and give us the number to justify the migration to shortwave-as-primary. Wired in `forecast_snapshot.py` (stamps `sr_sw`/`sr_diffuse` per hour) + `forecast_error_log.py` (propagates to pair rows).

</details>

<details>
<summary><strong>v0.6.308 • July 6, 2026</strong></summary>

- **Fetch total shortwave + diffuse radiation from Open-Meteo.** Investigation into "sr τ=24h L2 lead-decay" ship candidate exposed a unit mismatch masquerading as a station bias: model `direct_radiation` is direct-beam only, but Tempest station `solar_radiation_wm2` measures total shortwave (direct + diffuse). Current tick had 18/19 Tempest stations reporting sr at 96–165 W/m² while model direct_radiation[0] = 4 W/m². That gap has been contaminating Lsr — its per-regime bias magnitudes (−60 to −110 W/m²) are fitting the direct-vs-total unit gap on top of any real regime signal, which likely explains why Lsr tanks in ne_flow + calm (highly variable cloud cover → the unit gap swings hardest there). Step 1 of the fix chain: start fetching `shortwave_radiation` and `diffuse_radiation` alongside `direct_radiation` so we have apples-to-apples data to compare against Tempest. No downstream code changes yet — Lsr / pair log / debug chart still use `direct_radiation`. Once a few hours of paired shortwave data accumulate, we can quantify how much of Lsr's "regime bias" was really the unit gap, then decide the migration path.

</details>

<details>
<summary><strong>v0.6.307 • July 5, 2026</strong></summary>

- **Digest suppress-until infrastructure.** Morning digest was firing ⚠ `l5_solar_analysis` post-ship watch alerts every day even though the debug page already ruled the verdict contaminated through 07-10 (raw_direct_radiation pollution + per-lead scalar bugs, both fixed 07-03; 7-day rolling window doesn't fill with clean rows until 07-10). Structural fix: `shipped_ledger.jsonl` entries now carry optional `suppress_until` (YYYY-MM-DD) + `suppress_reason`. `build_executive_summary.py` honors them — suppressed alerts route to a separate "Suppressed (known contamination — do not act)" block and drop out of the top-of-digest ⚠ slot. Applied to both open Lsr ledger entries (v0.6.248 shipping L5 + v0.6.280 skip regimes) with `suppress_until: 2026-07-10`. Alerts self-resurface once the date passes — either self-resolving as clean rows fill the window, or resurfacing for real action. Also codified as memory `feedback_check_contamination_before_acting`: before recommending action on any ⚠ alert, check the debug page + ledger for a suppress-until / contamination note first.

</details>

<details>
<summary><strong>v0.6.279–v0.6.285 • July 2, 2026</strong></summary>

- **v0.6.279 skip-table architecture.** Shipped in `decay_apply.py` for L3/L4. First cells: `(ws, l3, ne_flow, *)`, `(ws, l3, sea_breeze, 0-11h)`. ws τ=7 reverted to global τ=14 after read flipped. Preview via `production_whatif.py`: ws +25.7% → +22.7%.
- **v0.6.280 Lsr skip regimes.** ne_flow (+32% worse) and calm (+11% worse). `compute_solar_correction` returns 0.0 in these regimes; sr forecast falls back to raw L1 (no L2/L3/L4 apply to sr).
- **v0.6.281–v0.6.284 canon-page catch-up sweep.** 12 stale spots knocked out across L3/Lsr prose, Upcoming, Retired, Open Q, Production Stack, Lt/Lsr render staleness.
- **v0.6.285 raw_direct_radiation pollution fix.** Week-long pipeline-order bug live since Lsr shipped 2026-06-28: `raw_direct_radiation` was captured AFTER Lsr mutated `direct_radiation`, so debug page + Production accumulator saw Lsr-corrected values as "raw." Fixed by extracting raw preservation into `preserve_raw_forecast_arrays()` and calling BEFORE `stamp_solar_correction`. Structural guard added in v0.6.291.

</details>

<details open>
<summary><strong>v0.6.306 • July 4, 2026</strong></summary>

- **Scorecard subtitle: third row for flat fields.** Was showing 10/13 fields (7 winning + 3 regressing); the 3 flat fields (pa, cl, ppᴮ) had no home in the display. Added a neutral-gray `○` row so all 13 fields are visible. Bucket boundary tightened to ±0.5pp so noise-level rows (e.g. cl at −0.2%) fall into "flat" rather than sneaking into "winning." Primary count of winning fields stays strict (pct < 0) for consistency with prior tallies.

</details>

<details open>
<summary><strong>v0.6.305 • July 4, 2026</strong></summary>

- **Scorecard includes pp via Brier.** pp is now scored in the "Winning fields" count using `per_layer_brier_by_lead.pp` instead of being filtered out entirely. Same "how much did we reduce the raw error metric" semantics for both MAE-scored and Brier-scored fields; superscript `ᴮ` marks the Brier field to keep the scoring rule visible. Count becomes N/13 (was N/12). Uses production Brier when populated; falls back to the deepest-applied-layer Brier otherwise. For pp under the current `L3_FIELDS = {ws, wg, ch, cm}` (no pp), deepest applied = L1 = raw → delta 0% — an honest read while pp has no correction path.
- **Winning-fields subtitle.** Small text under the "N/M" number lists the actual winning fields (green ✓) and regressing fields (red ✗). Answers "which 7 of 12?" at a glance without asking. Same list, small font, low-opacity — doesn't fight the primary numbers for attention.
- **Result today**: 7 winning (ch, cc, dp, h, cm, wg, sr), 3 regressing (pr, t, ws), 3 flat (pa, cl, ppᴮ). Once the next Fitter cycle populates the pp Brier production key, pp will read from real per-row Brier instead of the l1 fallback (and today's L1-only path means 0% anyway).

</details>

<details open>
<summary><strong>v0.6.304 • July 4, 2026</strong></summary>

- **pp dropped from `L3_FIELDS`.** Reconciliation of four audit tools all agreed L3 hurts pp: Fitter Brier `l1=0.0734 → l3=0.0765` (+4.2% worse; lower Brier = better); `production_whatif.py` `pp +87.3% BAD`; `h_regime_l3.py` `pp sea_breeze -96.1% ★ L3 LOSES`; walkforward L3_FIELDS claim has never included pp across 13 daily reads spanning 06-25 → 07-04. **The only signal for keeping pp in L3 was a "+8.0% pp L3 Brier gain L2→L3" claim I wrote into the v0.6.288–289 changelog earlier today — that number is not present in any script output.** Reverting the fabricated-number-driven decision to match what all four tools have been saying. Skipped the 7-day live-layer gate because this is pulling a bad decision back out (based on invented evidence), not shipping a new one. `shipped_ledger.jsonl` entry appended so the 14-day post-ship watch flags any regression.
- **Fitter's pp Brier `production` key.** Previously missing — the scorecard's fall-back to `l1` gave a false `+0.0%` reading. Added a `per_field_prod_brier_sq` accumulator on the deepest-applied-layer path (mirroring the existing `per_field_prod_abs` for MAE), populated per-row from `error_{applied}`, emitted as `per_layer_brier_by_lead["pp"]["production"]`. Next Fitter cycle after deploy will populate the array; pp then reads cleanly for future scorecard extension.
- **Debug page canon fixes.** Deleted the fabricated `+8.0%` sentence from the v0.6.288–289 changelog bullet. `Current pipeline state` pp row updated to `L1 (L3 dropped 2026-07-04 v0.6.304 — Fitter Brier + production_whatif + h_regime_l3 + walkforward all agree L3 hurts pp)`. Tri-column band's What's-running list now reads `L3 lead-decay: ws · wg · ch · cm (pp dropped 2026-07-04 v0.6.304 · skip: ...)`. Mon 07-06 upcoming-decision reworded from "ws/pp L3 strip?" to "ws L3 skip cells? (pp already dropped 07-04)."
- **Memory note: `feedback-dont-invent-numbers`.** Codifies the underlying failure. Every percentage / delta / ratio that lands in codified prose (CHANGELOG, debug page, ledger, memory) must be cited from a specific script output. If I can't cite the source, either fetch the number verbatim or omit it. A wrong specific number is worse than no number — it looks like real evidence and drives real decisions.

</details>

<details open>
<summary><strong>v0.6.303 • July 4, 2026</strong></summary>

- **Section-title standardization.** All layer section headers now read as `L{X} — {what it does}` for consistency. "Layer 1 — Raw model" → "L1 — Raw model"; same for L2, L3, L4. Lsr already followed the format. Prose in the accuracy-chart color-key legend, the "post-aggregate-bias" subsection header, the L3/L4 applicability-change banners, and the chart-legend labels for drill-down layers were all switched from "Layer N" to "L{N}." One user-facing status message that referenced "Layer 5 corrections" now correctly reads "Lsr corrections." HTML section-boundary comments switched to the new style. Non-user-facing CSS and JS comments were left alone; they aren't visible.
- **Convention recap in memory.** `project_specialists_vs_layers` extended: **names are stable across ENABLED state.** Lsr is Lsr on or off; Lc will still be Lc after ENABLED=True. Visual "what's firing this tick" belongs to display state (badges, colors, the tri-column band's ✓/○), not to the name. Codified after a brief detour today where I considered on/off-drives-numbering and Joe correctly reverted after seeing it brought back the bookkeeping-in-terminology problem the scope rule was invented to solve.

</details>

<details open>
<summary><strong>v0.6.302 • July 4, 2026</strong></summary>

- **G1 = candidates only.** Lt and Lsr live-state panels moved to their own sections. Lt's per-tick card now renders inside the R&D → Lt subsection (where the dormant-layer entry already lived); Lsr's card renders inside the Lsr h2 section under "Live state — what Lsr is doing this tick" (which had prose but no data view before). G1 shows only Lc (the actual gated candidate). Renamed G1 summary to "what Lc would do this tick."
- **JS refactor.** Split the old `renderGatedCandidatesSection` into `renderLtLiveState`, `renderLsrLiveState`, and a slimmed-down `renderGatedCandidatesSection` that only handles Lc. Shared badge helper factored out. Dispatch loop calls all three each tick.
- **Semantic**: G1 is for candidates awaiting a promotion decision. Dormant layers (like Lt) aren't candidates. Shipped-and-live layers (like Lsr) aren't candidates. Only Lc is a candidate today (7-day gate, day 1/7).

</details>

<details open>
<summary><strong>v0.6.301 • July 4, 2026</strong></summary>

- **G1 section renamed.** "Gated correction candidates — what C1 would do right now" → "Gated correction candidates — what Lt, Lsr, and Lc would do this tick." The old tail claimed C1 (confidence layer) but the section actually renders per-tick stamps for the three specialists (Lt, Lsr, Lc). Fixed the label to match the content.

</details>

<details open>
<summary><strong>v0.6.300 • July 4, 2026</strong></summary>

- **Divergence report keys renamed** to match the specialist convention: `L5_ENABLED` → `LSR_ENABLED`, `COVE_ENABLED` → `LT_ENABLED`. Applied consistently across `analysis/runlog/divergence_report.py`, `analysis/runlog/claims.py`, and `weather_collector/processors/decay_fit.py` (which aliased the ENABLED constants under the old names). Python constant names inside the specialist modules themselves (`solar_correction.ENABLED`, `cove_correction.ENABLED`) stay as `ENABLED` — those are per-module locals, not the divergence-tracking labels.
- **Lt moved from Archive to Research & Diagnostics.** Rule: disabled layers don't get separate top-level sections; dormant work lives in R&D. Physical DOM node relocated (kept the content verbatim); anchor renamed `sec-archive-l6` → `sec-rd-lt`; all three intra-page references updated. Archive intro adjusted — it no longer claims "dormant layers" as one of its categories; a pointer sends readers to the R&D → Lt entry instead.
- **TOC bookmark for Lt removed.** Top-of-page nav only carries top-level h2 sections. Lt is a subsection of R&D now, so its individual bookmark comes off. Readers still find it under R&D.
- **Follow-on effect on the divergence-report streak history.** `claims.py` will start emitting the new key names tonight; the streak tracker keys off the label, so the first read under the new names will show a fresh streak (previous history was under the old labels). That's a one-time reset, not a bug. Watching the next several digest cycles will re-establish the streak under the corrected names.

</details>

<details open>
<summary><strong>v0.6.299 • July 4, 2026</strong></summary>

- **Lc live-state panel added to G1. Gated correction candidates.** Third card alongside Lt and Lsr. Renders per-tick from `weather_data["cloud_saturation_correction"]`: enabled state + gate-day badge, total cells firing this tick, per-field table (cells fire / leads, mean |Δ| pp, max |Δ| pp), and fit-table generated_at. When `ENABLED=False` (today), reads as "dormant · telemetry only (7-day live-layer change gate; day 1/7 as of 2026-07-04)" — the exact table a reader needs to watch across the 7-day gate. When flipped `ENABLED=True`, the badge turns green and the descriptor switches to "Live: hourly.cloud_cover* arrays are shifted..."
- **`divergence_report.py` tracks `LC_ENABLED`.** New row surfaces production vs. `lc_fit.py` verdict. Today (before the first digest run of lc_fit): UNKNOWN, "lc_fit hasn't reported." After tonight's digest, once `lc_fit` writes its state entry, the row will read `DISAGREE — 7-day live-layer gate — flip after 7 daily reads agree` — the gate progress is the reader's mental model, not a divergence to act on.
- **`analysis/lc_fit.py` auto-runs in the daily digest.** It's under `analysis/*.py`, so `run_digest.sh` picks it up. Each night the fit table refreshes against latest pair-log; the exec-summary's SHIP-ELIGIBLE bucket enforces the 7-day agreement rule before we consider flipping `LC_ENABLED=True`.

</details>

<details open>
<summary><strong>v0.6.298 • July 4, 2026</strong></summary>

- **Lc (cloud saturation-unbiasing) — code shipped, ENABLED=False.** New specialist correction on cloud fields (cc, cl, cm, ch), fitted from pair-log. Post-L4 per-(field, value_bin) shift with clamp to [0, 100]. Live-layer change gate: 7-day agreement + telemetry watch before flipping ENABLED.
- **`analysis/lc_fit.py`** — fits the per-(field, bin) shift table from `forecast_error_log.jsonl`. Uses the deepest available forecast_lN (L4 if present, else L3/L2/L1) — matches the runtime order Lc sees. Ship rules per cell: n ≥ 200, |mean_bias| ≥ 5.0 pp, post-shift MAE improvement ≥ 2%. First fit: **15 SHIP / 0 MARGINAL / 9 SKIP** of 24 cells. Biggest impact: cl 80-95 −55% MAE, cl 95-100 −47%, cl 50-80 −47%, ch 50-80 −37%, cm 95-100 −34%. Skip cells cluster at low-end bins (0-5, 5-20) where the mean-shift correction interacts badly with the [0, 100] clamp and adds error rather than removing it. cc 5-20 has −20pp mean bias but only +0.8% MAE improvement — bimodal obs distribution defeats mean-shift; SKIP verdict is correct.
- **`weather_collector/data/lc_correction_table.json`** — fit output the collector consumes. Contains generated_at, fit_rules, and per-(field, bin) `{shift, n, mae_pre, mae_post, improve_pct, verdict}`.
- **`weather_collector/processors/cloud_saturation_correction.py`** — new processor. `stamp_cloud_saturation_correction(weather_data)` runs after L3/L4 and Lt in the pipeline. Even with ENABLED=False, stamps `weather_data["cloud_saturation_correction"]` telemetry every tick (per-field per-lead would-be deltas, cells_fired count, fit-table meta) so the 7-day watch can read what the layer would do. When flipped ENABLED=True, mutates `hourly["cloud_cover*"]` arrays in place, preserving pre-Lc state as `hourly["cloud_cover*_post_l4"]` for forecast-snapshot attribution. Applicability descriptor added, wired into `applicability_map` assembly in `collector.py`.
- **Debug page canon.** Production Stack Specialists list includes Lc with fit-result summary. Applicability-map intro category text updated (specialists = domain-scoped by construction, not single-field). Tri-column band's What's-improving Lc card reads "code shipped, gate day 1/7." Category prose updated from "single-field, parallel to the core stack" to "domain-scoped, parallel to the core stack" for consistency with the corrected specialist definition.

</details>

<details open>
<summary><strong>v0.6.297 • July 4, 2026</strong></summary>

- **Cloud saturation-unbiasing reclassified as specialist Lc.** Corrected the specialist convention: the distinguishing test is **universal vs. domain-scoped**, not single-field vs. multi-field. Cloud saturation hits four fields (cc/cl/cm/ch) but is a specialist because the physics (bounded-percentage sigmoid saturation) is inherent to cloud fields — won't apply to wind, temperature, precipitation. Renamed the 5 remaining L5 references on the debug page to Lc. The L5 slot is again unused. Sibling of Lsr (solar) and Lt (temperature) in the specialist family.

- **Memory updated: `project-specialists-vs-layers`.** Distinguishing rule made explicit: universal (any field via whitelist) → numbered core; domain-scoped (physics bound to a field type) → letter-suffix specialist. Corrects the earlier "multi-field = core" framing that would have put Lc in the wrong slot.

</details>

<details open>
<summary><strong>v0.6.296 • July 4, 2026</strong></summary>

- **Specialist reclass — debug page rename.** Codified naming convention: core stack layers are numbered L1–L{N} (multi-field, general-dimension corrections); specialists get letter-suffix names describing what they act on. Applied to the debug page canon: current L5 synoptic-regime solar → **Lsr**; current L6 cove microclimate → **Lt**. 120 references renamed across corrections_debug.html: section headers, TOC, tri-column current-state band, Production Stack, Applicability map, Retired hypotheses, chart labels, badges, and prose. Anchor IDs (`sec-layer5`, `sec-archive-l6`) preserved for URL stability; only display text changed.

- **Naming convention (dynamic).** A specialist earns a numbered slot when it proves broadly applicable (Lsr → L{N} if it later covers more than one field). A numbered layer loses its number if it demotes to specialist scope. Naming reflects current architectural fit, not historical branding. Codified in memory `project-specialists-vs-layers`.

- **Frees the L5 slot for the next core layer.** Design conversation this evening settled the architectural home for the Cloud saturation-unbiasing correction (`h_cloud_floor_ceiling.py` — cl 95-100 +64.7pp, 3 direction-stable reads). It ships as new core **L5** (cloud-scoped, forecast-value axis; peer of L3-lead and L4-hour in the pair-log family; post-L4, pre-Lsr). Stage 2 wiring is the next ship. All references to the discarded "L2.5" and "L3-axis extension" naming proposals removed from the debug page.

- **Collector-side rename queued.** `solar_correction.py`, `cove_correction.py`, frontend JS badge strings, and analysis scripts still contain L5/L6 references. Those ride along with the L5-cloud-saturation ship since they need coordinated updates and there's no urgency to touch them in isolation. Stamp keys (e.g. `weather_data["solar_correction"]`) stay stable for pair-log parser compatibility.

</details>

<details open>
<summary><strong>v0.6.295 • July 4, 2026</strong></summary>

- **Tri-column current-state band added above Engineering updates.** Three cards side-by-side (stack vertically on mobile): 🟢 What's running, 🟡 What's improving, 🔵 What's being evaluated next. Answers the "where do things stand right now" question in one glance without scrolling through history. Sits above the fold, right below the auto-computed scorecard banner. Retention rules noted in the section comment: What's running = live state, no history; What's improving = active Stage 1 only; What's being evaluated next = forward calendar + frozen items + post-ship watches.

- **What's running card.** Compact stack (L2/L3/L4/L5 with skip qualifiers, L6 dormant), Production vs raw scorecard (6 stable wins + 1 open regression + in-flight), guards row (verifier healthy, live-layer change gate active).

- **What's improving card.** Mini stacked cards for the 5 active Stage 1 candidates, each with today's read + concrete next action. Ship-ready Cloud saturation-unbiasing gets top slot with a green left-border; dp depression regime gets a "decaying" amber flag noting the frontal bias is shrinking; C1d resurrected and pre-frontal flagged as narrow-promote candidates with day 1/7 gate progress.

- **What's being evaluated next card.** Calendar grid (07-06, 07-08, 07-10, 07-11) with what fires when + expected action. Frozen bucket (h→L4, sr→L4, L5 skip regime changes) below. Post-ship watches (L5 SHIP→HOLD alerts, v0.6.291 verifier watch) at bottom.

- **L5 "Engineering status" shipped-history log collapsed.** The seven historical bullets (v0.6.248 initial ship through v0.6.286 per-lead delta fix) now live inside a closed `<details>` block. Section summary compresses to a one-liner + the current-state facts (skip regimes, clean audit window date, verifier note). Reduces vertical noise while keeping the full history a click away.

</details>

<details open>
<summary><strong>v0.6.294 • July 4, 2026</strong></summary>

- **Debug page "Recent activity" block trimmed to a rolling 3-day window.** The block (formerly "Since last curation") had been accumulating every version since 2026-06-30 — 30+ ship entries by 07-04, defeating the purpose of a daily read. Retention rule codified: today + 2 prior calendar days of ship entries; older content lives in `docs/CHANGELOG.md`. Consolidated 07-02 → 07-04 into compact bullets (one bullet per day for related version bumps). Living-reference blocks retained: "Live-layer change gate — rule of the road" (added a second bullet explicitly reminding that the gate governs live-layer flips, not exploration — see `feedback-dont-over-gate`) and "Still open watches" (refreshed: 07-08 T convergence checkpoint added; h→L4 marked FROZEN; C1 calibration pass rate updated 50.00% → 52.63% from today's digest; C1 Stage 4 INSUFFICIENT-DATA re-check ~07-11 noted).

- **Memory note added: `feedback-recent-activity-rolling-window`.** Codifies the retention rule so future curations don't let the block grow forever again.

</details>

<details open>
<summary><strong>v0.6.293 • July 4, 2026</strong></summary>

- **Print-safe debug page.** Existing `@media print` block covered inline dark backgrounds starting with `#1`/`#2`/`#3`, but the "Current pipeline state" block at the top of Engineering updates uses `background:#0e1620` — `#0` prefix, slipped through, printed as light text on black. Extended attribute selectors to include `#0`; added a descendant rule so nested inline light colors on originally-dark blocks also get forced dark; added a final safety pass that forces any element with an inline `color:#7…#f` (dark-theme accent) to `#111` in print. Field-badge and band-table accent colors preserved (class-based rules retain their specificity). Nothing prints as light text on dark now.

</details>

<details open>
<summary><strong>v0.6.292 • July 4, 2026</strong></summary>

- **Debug page hypothesis-state refresh.** Stage 1 rolling table + long-form bullets walked forward from 06-24 stamps to 07-04. Every candidate now reflects today's digest verdict, not the 10-day-old snapshot. Live changes: (1) **Cloud saturation-unbiasing** ship criterion met — direction-stable across 3 reads spanning 11 days on cl 95-100 (+63.4 → +57.5 → +64.7 pp); flagged as highest-leverage next move, ready for L2.5 vs L3-axis architectural design decision. (2) **C1h trend-direction** — n on cm/ch/cc/t rising cells now ≥340; next action is writing `h_c1h_orthogonality.py` vs C1f + C1e. (3) **dp depression regime** — frontal bias decaying (-2.19 → -1.98 → -1.51); course-of-action question added about when a decaying signal falls below action threshold. (4) **C1d cloud disagreement** — RESURRECTED. Killed 06-29 as a global axis, but 07-04 read flipped to MIXED (3 orthogonal / 20 redundant / 9 other); narrow-promote path is a valid option. (5) **h_pre_front_orthogonality** — new MIXED verdict, same narrow-promote path. (6) **cm ride-along on L4** — declined; sim flipped from +3.0% (06-24) to -3.8% today. Rolling-table legend updated: all candidates now auto-run in the daily digest (was ⚫ Manual, now 🟢 Auto).

- **Upcoming Decisions section reflowed.** 07-03 h + sr → L4 marked FROZEN (walkforward SHIP vs l4_regime_lead_analysis KILL disagreement on h; sr baseline corrupted through 07-10). Added: 07-04 v0.6.291 raw-baseline verifier ship + C1 v2 multi-axis audit INSUFFICIENT-DATA result. 07-08 T Production convergence check explicitly framed as the diagnostic that decides whether the deferred `applied_layer` walker moves from nice-to-have to blocking. 07-10 Fri consolidated: sr clean read + ws/wg L3 strip earliest ship + L5 skip-cell re-audit. Ongoing L5 post-ship watch alerts through 07-10 tagged as expected/known-cause.

- **Product ideas section added to Upcoming Decisions.** Wyman Cove Swim Index (WCSI) noted as a product-facing scoring idea combining rainfall runoff / tidal flushing / outfall / beach closures / wind direction. Details + open design questions in the `project-todo` memory. No date; pull in on a low-load day.

- **Retired section — C1d annotated with 07-04 resurrection.** Global kill stands; the 3 orthogonal cells are now a valid narrow-promote candidate tracked as "Still confirming, day 1/7" in the digest exec summary.

- **Rolling-table framing note.** New callout under the table synthesizes course-of-action: Cloud saturation-unbiasing is the highest-leverage next move; C1h has enough n to run its owed ortho check; C1d/pre-frontal narrow-promote is a low-effort ship if 7-day agreement holds. Explicit reminder that the live-layer gate governs live-layer flips only, not exploration or Stage 1 refinement — see the new `feedback-dont-over-gate` memory.

- **Framework hygiene: "Current pipeline state" date bumped 07-03 → 07-04.** L5 "Where we are" section date bumped as well.

</details>

<details open>
<summary><strong>v0.6.291 • July 4, 2026</strong></summary>

- **Shape 1 raw-baseline verifier shipped.** Structural guard for the L5-class silent failure that ate a week of solar analyses ending 2026-07-02. New `weather_collector/processors/raw_integrity.py`: `snapshot_raw_baseline()` called from `collector.py:145` — before `blend_observed_into_hourly`, which is the first correction to touch any hourly array — deep-copies every hourly array with a `raw_*` counterpart. `verify_raw_integrity()` runs at the end of `build_weather_data` (line 394) and compares each `raw_<field>` against the snapshot byte-for-byte. Any drift is appended to `gs://myweather-data/raw_pollution_log.jsonl` with field, source, first-bad index, and max delta. Covers 10 fields: `direct_radiation`, `precipitation`, `precipitation_probability`, `cloud_cover`, `cloud_cover_low`, `cloud_cover_mid`, `cloud_cover_high`, `wind_direction`, `wind_speed`, `wind_gusts`. Non-blocking by design (raw pollution corrupts analyses, not user-facing forecasts, so a bug in the verifier can't take down the pipeline).

- **Digest-side companion.** New `analysis/raw_integrity_check.py` reads the pollution log and emits CLEAN when the log is absent or drift-free in the last 24h, DRIFT otherwise. `build_executive_summary.py` bucket taxonomy extended: DRIFT now surfaces as a `kill` verdict so pollution events land prominently in the exec summary instead of hiding in the `info` bucket. Silent baseline: absent log == healthy.

- **First-deploy ordering fix.** Initial deploy caught a false-positive drift on `raw_wind_speed` and `raw_wind_gusts` at index 0 — the snapshot was originally placed after `preserve_raw_forecast_arrays` (line 324), which is downstream of `blend_observed_into_hourly` at line 139. `wind_blend`'s own lazy `raw_wind_speed` init correctly captures pre-blend HRRR, so the raw was right and the snapshot was late. Snapshot moved upstream of every layer that touches hourly arrays; false positives cleared from GCS; healthy since 11:37 UTC on the fresh deploy.

- **Debug page canon.** New v0.6.291 entry in "Since last curation" (extended range to 2026-07-04). L5 engineering-status section annotates the v0.6.285 raw-pollution-fix bullet with a note that v0.6.291 is the structural guard: any future layer that mutates a source array before its `raw_*` copy exists will now fire a drift event on the next tick and land in the digest, instead of hiding for a week.

</details>

<details open>
<summary><strong>v0.6.286 • July 3, 2026</strong></summary>

- **L5 per-lead delta fix.** `stamp_solar_correction` was computing a single Δ from the current tick's regime + current hour's raw solar value, then applying that scalar to all 48 forecast leads. When the collector ran below the sun-up threshold (pre-dawn / dawn — every ~6 AM tick this week), delta = 0 → no L5 correction anywhere in the 48h forecast. Live since L5 shipped 2026-06-28 v0.6.248. Fixed by iterating the `direct_radiation` array with each lead's own raw value + parsed local hour, matching the pattern `cove_correction.stamp_cove_correction()` already uses. L5 now fires at every daytime lead in every non-skip regime. Clean 7-day audit window closes ~2026-07-10.

- **L6 ENABLED = False.** Both L6 branches were disabled inside `compute_cove_correction()` on 07-01 v0.6.276 (function returns 0.0 unconditionally), but the top-level `ENABLED` flag was never flipped. Kept `stamp_cove_correction` telemetry claiming `applied: True`, `describe_applicability()` reporting L6 as active, and the T-card badge showing "L6 ✓ microclimate." All cosmetic — L6 was already a no-op numerically — but the debug page + applicability map were lying. Flipped to `ENABLED = False` so telemetry matches reality.

- **Walkforward L3+L4 validator rewrite — per-(field, regime, lead_band) shape.** Old aggregate output shape led to shipping decisions that missed regime-specific damage (see the h + L4 walkforward-vs-cross-cut incident: aggregate said +5.2% overall win; per-cell cross-cut said 21 L4 LOSES / 4 WIN). Rewrite emits per-cell verdicts under BOTH `state_fc` (skip-gate side) and `state_obs` (efficacy side) bindings. SHIP only when both views agree; ENT (entangled) flag when they disagree — a correction that's entangled with classifier accuracy can't be shipped clean by any skip table. Drop-in `L3_FIELDS` / `L4_FIELDS` / `SKIP_TABLE` proposal ready to paste into `decay_apply.py`.

- **Debug page canon catch-up.** Version stamp, "Current pipeline state" date, "Since last curation" range, and the full list of v0.6.281–286 entries added. Stage 4 audit numbers refreshed (15 PASS / 11 WATCH / 22 FAIL vs previous 27/19/16). C1 calibration pass rate refreshed (50% vs previous 61.54%). L5 "Where we are" section rewritten with both 07-03 collector bug fixes + updated clean-window date (07-10, not 07-05). Upcoming Decisions block updated: h + sr to L4 held pending reconciliation between walkforward and l4_regime_lead_analysis (h) and clean data window (sr).

</details>

<details open>
<summary><strong>v0.6.262 • June 30, 2026</strong></summary>

- **walk-forward L3/L4 validator bugfix.** The per-field recommendation logic in `analysis/walkforward_l3l4_validator.py` gated L4 evaluation on L3 earning its keep first — but for fields not in `L3_FIELDS` (cc, t, dp, h, ws, wg, sr, pr, pa), `forecast_l3 == forecast_l2` by construction, so L3 trivially "didn't earn the ≥2% threshold" and L4 was silently never evaluated. Result: the validator recommended `off_off` for nearly every field, including cc where L4 visibly beats baseline 36.06 → 32.78 (9.1%) at every lead band. Fix evaluates L3 and L4 INDEPENDENTLY: each compared to the best simpler state available. Added `off_on` as a valid recommendation (matches actual production state for fields like cc that are in L4_FIELDS but not L3_FIELDS). Re-running the validator now produces correct recommendations: **L3_ENABLED = {ch, cm}** (unchanged), **L4_ENABLED = {h, cc, ch}** — cc stays in L4 (the "drop-cc gate" was a phantom from the bug), and **h emerges as a new L4 candidate** (5.2% MAE win, 6.39 → 6.05). Status entry reframed accordingly. Bug-rationale comments preserved inline; docstring rewritten to describe the four-state validator and the L3-not-in-L3_FIELDS case explicitly.

- **Editorial sweep — round 2.** (a) **Status section** rewritten compactly: dropped the verbose One-line summary, dropped redundant Stage-2-auto-wired-audits sub-box, dropped past DONE entries from Upcoming Decisions, collapsed Retired sub-box to a one-liner pointing to the Research section. Now ~30 lines instead of ~80. (b) **L6 section summary** updated to lead with current state ("warming branch only") and explain the disabled cooling branch + reference for the live trigger. (c) **R2 (state-stratified accuracy)** renderer now tags already-addressed fields (sr → L5, t → L6) with an "addressed" badge and dimmed row; the "#1 opportunity" chart now skips past addressed rows and is labeled "Top actionable opportunity." (d) **G1 (Gated candidates)** R5 entry removed entirely (R5 retired since 06-17 — doesn't belong in a gated-candidates list); L5 entry removed (shipped, lives in Production stack). Only C1 left, with description updated to 06-30 audit numbers. (e) **S1 (Shadow tuner)** scope clarified — it reasons about field membership only, NOT per-field gates (CALM_GATE_ENABLED, future per-(field, regime, lead_band) skip tables). (f) **Marine layer entry** stale "weekly Sun-morning re-reads (06-28/07-05/07-12)" prose removed — the stage1/stage2 scripts run in the daily digest; entry now cites today's digest numbers (mean +32.65 / median +43.00) directly. (g) **Backlog cleanup** — removed C1d + C1g KILLED entries from Group A active list (they live only in Retired now); removed KILLED rows (C1d, C1g, wind_shift_rate) from the Stage 1 candidates table; compacted shipped entries (C1b, C1c, C1f, Humidity K-taper, cc→L4) to one-liner pointers ("SHIPPED — history in git log") so the backlog now contains only ACTIVE candidates: 4 in the prioritization table (Cloud sat, C1e bidirectional, C1h trend-direction, dp depression). (h) **JS render bug** — the live gated-candidates panel called the cove correction "R5 Cove correction" with hardcoded "audit: HOLD" text; renamed to "L6 Cove correction" with "(warming branch only since v0.6.259)" annotation; dropped the hardcoded audit verdict (the chart's L6 line + L6 section carry that signal). (i) **R5 retired section's Current Status** subsection updated to reflect the v0.6.259 cooling-branch disable (was still describing the bidirectional table as live).

</details>

<details open>
<summary><strong>v0.6.261 • June 30, 2026</strong></summary>

- **Corrections debug page cleanup pass.** Editorial sweep to refresh the page against today's shipped state. (a) **Status section** refreshed: "Last curated" stamp moved to 2026-06-30 v0.6.260; Since-last-curation block rewritten with v0.6.259 / v0.6.260 entries plus the pending L4 drop-cc and L5-RETIRE puzzles for tomorrow; Pipeline delta line updated; Production stack box "L3 whitelist / L4 whitelist" lines reframed as "L3 currently applies to / L4 currently applies to" with links to the new Applicability map; Next scheduled decisions list refreshed (L6 disable-gate entry resolved by today's surgical fix; L4 drop-cc gate flagged as do-not-act tomorrow; Open architectural questions trimmed). (b) **"Whitelist" → "applicability" framing** in user-facing prose throughout: L3/L4 section headers, L4 diurnal methodology, D1 drill-down explainer, S1 Shadow tuner heading + description, B1 backtest sweep description, applicability methodology, JS shadow-tuner per-tick prose, Group C wind-direction-sector entry. JS variable + URL names (SHADOW_WHITELIST_URL, shadow-whitelist div id) intentionally left alone — internal identifiers. (c) **L5 subsections filled out** (5a live correction, 5b regime classifier, 5c per-regime delta table, 5d L5 vs L4 audit) — replaced 4 placeholder lines with substantive prose describing what's where + how to read it. Real JS render functions deferred to a future session; the prose tells the reader where to look (weather_data.solar_correction, _BIAS_BY_REGIME_HOUR table, Forecast Accuracy chart sr card, l5_gate_history.json). (d) **Killed C1d candidate moved to Retired:** Stage 1 backlog entry rewritten with the 2026-06-29 KILL summary + cross-reference; new KILLED row added to the Stage 1 candidates table; Retired section's "Recently ruled out" list extended with full C1d killshot and the L6-double-counting-hypothesis killshot (rejected by data 2026-06-30, replaced by surgical fix). Group A intro line updated to note C1d was promoted then killed. Pipeline counter dropped to 5 active candidates. (e) **Forecast Accuracy chart legend color bug fixed.** `generateLabels` was indexing `LAYER_LINES[i]` by raw dataset position, but `_layersFor()` filters L5 out for non-solar and L6 out for non-temperature fields — so on the T chart, dataset[4] is L6 (mint green) but `LAYER_LINES[4]` is L5 (amber), and the legend swatch picked up L5's amber instead. Fix: read `ds.borderColor` directly (it's already set from the filtered LAYERS list). Same bug pattern affected any chart where L5 or L6 was filtered out — applies cleanly to all of them. (f) **G1 cleanup.** R5 cove correction entry removed entirely (retired since 06-17; doesn't belong in a "gated candidates" list anymore). L5 entry removed (shipped 06-28; lives in Production stack box above, not in G1). G1 now contains only the C1 confidence layer entry, with the description updated to reflect the latest Stage 4 audit read (06-30 digest). (g) **S1 tuner scope tightened.** Description clarifies that the shadow tuner only reasons about field membership in <code>L3_FIELDS</code> / <code>L4_FIELDS</code> — NOT about per-field gates like <code>CALM_GATE_ENABLED</code> or per-(field, regime, lead_band) skip tables (those richer gates live in the Applicability map). The shadow tuner addresses the on/off-per-field axis only. (h) **R2 origin-story updated.** Was "L5 in <code>solar_correction.py</code> was built off this signal (gated off; see G1)" — L5 has shipped, so reframed as "the synoptic-regime bias spread in solar drove L5; L5 shipped 2026-06-28 v0.6.248 and now lives in production." (i) **Stage 1 candidates table** header re-dated as "rolling table (last manual batch re-run: 2026-06-24)" with a note that &gt;1-week-old rows are dormant pending re-fire; cloud-ceiling regime candidate marked dormant (the 06-26 paired read didn't fire and the per-(field, regime, lead_band) work now supersedes it).

</details>

<details open>
<summary><strong>v0.6.260 • June 30, 2026</strong></summary>

- **Applicability map — collector plumbing + Section D rendering (steps 1–5 of `project_applicability_map_design`).** Each correction module now exposes a `describe_applicability()` function returning per-layer gating descriptors; the collector concatenates the union into `weather_data["applicability_map"]` each tick; the debug page reads that block and renders a single global view at the top of the page. Pieces: (a) schema example `weather_collector/data/applicability_map_schema.json` documents the shape — per-layer descriptors with `layer_id` / `name` / `category` and a `fields` list of per-field gating entries (`field`, `fires_when`, `gated_by`, `current_state`); C1 uses an `axes` subkey instead of `fields` because its gating cuts across fields rather than firing per-field. (b) `decay_apply.describe_applicability()` covers L3 (5 fields, with ws/wg carrying the CALM_GATE_ENABLED gate metadata) and L4 (ch, cc). (c) `solar_correction.describe_applicability()` covers L5 (sr, gated by ENABLED + sun-up threshold + regime-hour bias entry). (d) `cove_correction.describe_applicability()` covers L6 (t, gated by ENABLED with the v0.6.259 cooling-branch-off note inline). (e) `confidence_layer.describe_applicability()` covers C1 with its four live axes (C1a regime-transition, C1f pre-frontal, pt_bin pressure tendency, cluster_spread mesonet quartile). (f) Collector wires the four modules right after `stamp_cove_correction` and stamps `weather_data["applicability_map"]` with `generated_at` + assembled `layers` list. (g) Debug page gets a new **"Applicability map — what corrections trigger, and why"** section between Accuracy and Layer 1 (TOC chip added), reading from `wxDoc.applicability_map.layers` via `renderApplicabilityMap()`. Per-layer cards show layer_id + name + category badge (general-purpose / specialist / confidence color-coded), a table of (field|axis, triggers when, gated by, current state) rows, and per-row + per-layer notes inline. Falls back to a graceful "not available yet" message when the collector hasn't shipped the block. Accuracy section stays second (after Status) — it's the closest existing "is the pipeline working?" view, so it earns precedence over the applicability detail. A proper headline scorecard ("Stack vs raw: −X% MAE, M/N fields net-positive") above Status is a future small follow-up. No correction behavior change — all of this is read-only metadata. Step 6 (migrate existing layer sections to per-layer filtered slices reading from the same block) and step 7 (top-level reorg into A/B/C) deferred to a future session — current per-layer sections keep their existing prose for now.

</details>

<details open>
<summary><strong>v0.6.259 • June 30, 2026</strong></summary>

- **L6 cooling branch disabled (cove_correction.py).** New `analysis/l6_l2_double_counting.py` ran 19,975 t pairs where L6 fired. Original "L2 already pulls toward cove → L6 double-counts" hypothesis rejected: L2 only erases 3.7% of L1's MAE on cove rows. Real cause: L1 itself is structurally cold ~2.25 °F at the cove (HRRR microclimate gap L2's Kalman blend doesn't close). Stratifying by the signed applied Δ exposed the asymmetry — when L6 cooled by ≥2 °F (n=3,284, all from the sb_off offshore hour table), MAE 3.52 → 6.16 (−74.9%); when L6 warmed (sb_active sea-breeze branch), MAE neutral-to-better (mid-warm Δ +10.1%). **Independently confirmed by today's `r5_cove_analysis` digest:** S/SE/SW sea-breeze warming gradient PASS (+1.80°F, n=382, threshold +1.0°F), 06-10 EDT offshore cooling gradient FAIL (−0.54°F, n=286, threshold −1.0°F) — the cooling gradient the lookup encodes isn't reliably present in the obs anymore. The divergence-report `COVE_ENABLED True→False READY (3/2)` signal is the binary form of the same finding; this ship is the refined response (kill the failing branch, keep the working one). Fix: `compute_cove_correction` now returns 0.0 in the sb_off branch instead of the `_HOUR_DELTA_SB_OFF` value. Sea-breeze warming branch (sb_active, S/SE/SW) unchanged. Sanity check confirmed L2 == L4 on every t pair (T not in L3_FIELDS/L4_FIELDS), so the production audit's "L4 vs L4+L6" framing IS a clean "L2 vs L2+L6" comparison. Expected effect on next `l6_gate_history.json` reads: still HOLD (because the L6 audit measures vs L4-with-L6-applied, and we're shrinking what L6 does), but the magnitude of HOLD should compress as the worst cooling rows stop firing. Long-term Fix B (refit the lookup against L2-baseline) still queued — see `project_l6_l2_double_counting_hypothesis`.

</details>

<details open>
<summary><strong>v0.6.249–v0.6.257 • June 29, 2026</strong></summary>

* **L5 attribution fix (v0.6.249).** The v0.6.248 ship silently absorbed L5 into the L4 column — `stamp_solar_correction` mutated `hourly.direct_radiation` in place, and the snapshot writer read that as `sr_l4`. Same bug shape as the earlier L6-into-L2 issue. Fixed by preserving `direct_radiation_post_l4` before mutation and adding an `sr_l5` column to the snapshot writer; `forecast_error_log.py` + `decay_fit.py` layer iterations extended to include `l5`. `L5_VALID_FROM = "2026-06-28T07:05"` gates pre-fix rows out of L5 aggregation.

* **L5 chart + badge wired (v0.6.250).** Forecast Accuracy chart's sr card now shows an amber L5 line + column + `L5 ✓ synoptic` badge. `_layersFor()` and `_shouldShow()` filter the L5 entry to the sr card only — symmetric with how L6 lands on the t card. Methodology accordion gets an L5 bullet next to L6.

* **Debug page content refresh (v0.6.251).** Status header + Since-last-curation block rolled forward; pipeline-delta line refreshed with current gate counters and earliest-clear dates; new **Layer 5 — Synoptic-regime correction (solar)** section between L4 and L6 with summary + 5a–5d placeholder subsections (full subsection build deferred); TOC chip row gains an L5 anchor; upcoming-gates list resolved 06-26/06-29 entries and added 07-03/07-04/07-05/07-06 milestones plus an L6 cove-watch line; open architectural questions list adds per-regime L6 gating and the specialists-vs-layers naming question.

* **L3 regime × lead-band analysis + gated calm-wind L3 skip (v0.6.252).** New `analysis/l3_regime_lead_analysis.py` splits L3 marginal effect (|error_l2| vs |error_l3|) by (synoptic regime × lead_band) and (forecast wind speed × lead_band) for ws/wg/ch/cm. Resolves the apparent contradiction between `h_regime_l3` (ws L3 wins under every regime) and the per-lead chart (ws L3 hurts at leads 18–47h) — the real story is calm forecast wind, not lead distance: ws/wg L3 LOSES −19.8% to −69% MAE when fc_ws<3 mph, WINS +5% to +47% when ≥3 mph. `decay_apply.py` gains a gated calm-wind L3 skip — `CALM_GATE_ENABLED=False` by default; when flipped, ws/wg L3 corrections zero out at any lead where `wind_speed_post_l2[lead]<3.0` mph. Standard Stage 2 promotion: audit a few digest cycles before flipping. Auto-picked up by the daily digest run.

* **Debug page roll-forward for v0.6.252 + calm-wind gate milestone (v0.6.253).** Since-last-curation block extended to v0.6.252; pipeline-delta line references the calm-wind gate flip target; upcoming-gates list gets a 2026-07-02 milestone for the earliest `CALM_GATE_ENABLED` flip.

* **L4 regime × lead-band analysis + fresh C1 curated tables (v0.6.254).** New `analysis/l4_regime_lead_analysis.py` mirrors the L3 script for L4 fields (ch, cc). First-run result: ch L4 is unambiguously good across every (regime, lead_band) cell (27 WIN / 5 flat / 0 LOSES). cc L4 has a specific frontal-regime weakness (LOSES at frontal × {6–11h, 12–23h, 24–47h} and ne_flow × 0–5h) but WIN or flat in every other regime — the walk-forward's flat-drop-cc gate at 5/7 is reading regime-specific weakness, not field-wide failure. C1 calibration re-curate sanity check: pass rate moved 47.92% → 61.36% with fresh data — still HOLD (<75% threshold) but confirms re-curating absorbs real drift; fresh curated tables (32 SHIP / 12 MARGINAL / 12 SKIP) staged for next collector tick.

* **Debug page roll-forward for v0.6.254 + regime/lead-band pattern (v0.6.255).** Since-last-curation block extended through v0.6.255 with L4 regime × lead-band result, cm L3 reframing (06-24 all-windows-OFF verdict contradicted — long-lead WIN with regime-specific frontal losses), and the C1 re-curate finding. Pipeline-delta line flags the emerging meta-pattern: walk-forward flat-drop verdicts consistently hide regime-specific weakness. Open architectural questions list gets a meta-pattern entry pointing at a future per-(field, regime, lead_band) skip table in `decay_apply.py`.

* **C1d killed by orthogonality (v0.6.256).** New `analysis/h_cloud_disagreement_orthogonality.py` companion to yesterday's smoke test. Verdict: **KILL C1d** — holding C1a (transition) fixed, the σ_HIGH/σ_LOW MAE ratio inverts to <1.0 in 3 of 4 (field, band) cells that cleared the n≥100 floor. The σ signal was the regime-transition signal C1a already encodes. C1e check insufficient (n=0 cells) — could refine with more data, but C1a redundancy is decisive. SMOKE_ALIVE → orthogonality KILL flow worked as designed; saved us from promoting a redundant axis.

* **Debug page roll-forward for v0.6.256 (v0.6.257).** Since-last-curation block gets the C1d KILL bullet; pipeline-delta line updated; upcoming-gates 06-28 entry resolved with the 2026-06-29 KILL outcome.

</details>

<details open>
<summary><strong>v0.6.248 • June 28, 2026</strong></summary>

- **L5 synoptic-regime solar correction SHIPPED.** `solar_correction.ENABLED=True` after the L5 promotion gate cleared 7/7 ship days (12-cycle SHIP streak). The amber L5 line on the sr card and the `L5 ✓ synoptic` badge come with v0.6.250's chart wiring (June 29); the v0.6.249 attribution fix (June 29) was needed to make the column actually populate. L5 row moved out of "Gated off — built, not applied" in the debug page.

</details>

<details open>
<summary><strong>v0.6.244–v0.6.247 • June 27, 2026</strong></summary>

* **t-card paired-L4 baseline series added and pulled (v0.6.244 → v0.6.245).** Initial v0.6.244 added a dashed-blue "Diurnal (paired with L6)" series on the t card so L6 could be compared against L4 restricted to the same row subset L6 had been applied to (L6 had a shorter history than L3/L4 until ~2026-07-03). After a short discussion the column was pulled — we didn't build one for L3 or L4 when they shipped, so adding one for L6 was inconsistent. Replaced with a one-line note above the legend explaining the window mismatch will self-resolve by ~2026-07-03.

* **Debug page status refresh (v0.6.246).** Since-last-curation block rolled forward; the three 2026-06-26 upcoming-gates entries resolved with today's digest outcomes — walk-forward read returned no L3/L4 additions (instead recommended drops), C1 calibration HOLD at 47.92%, KBOS-vs-KBVY smoke test flagged for investigation.

* **C1d candidate infrastructure built (v0.6.247).** New `cloud_obs_blend.py` stamps `derived.cloud_inter_source_sigma` from the KBOS+KBVY cc `bias_std` at L2 blend time. `forecast_snapshot.py` carries it onto each `snap_entry` next to `pressure_trend_hpa_3h`; `forecast_error_log.py` attaches it (plus `cloud_n_sources`) to every pair row. New `analysis/h_cloud_disagreement.py` smoke-tests whether high inter-source σ predicts cloud-field |error|. Same infrastructure-gap pattern as `h_lightning_proximity`.

</details>

<details open>
<summary><strong>v0.6.243 • June 26, 2026</strong></summary>

- Debug page Status section's "Open architectural questions" sub-box gains a new entry: **ws L3 long-lead regression** — per-lead chart shows L3 makes wind speed +20–31% worse at leads 18–47h while wg L3 helps −15 to −22% over the same band. Walkforward validator's per-field aggregate hides this. Queued (not today's work): add per-band rollup to walkforward output, then drop ws from L3 or wire per-(field, lead_band) whitelist in `decay_apply.py`. Memory note: `project_ws_l3_long_lead_regression`.

</details>

<details open>
<summary><strong>v0.6.242 • June 26, 2026</strong></summary>

- L6 prose accuracy fix on the debug page. Two places (Layer 6 section summary + cove R5 section's "Current status") described the morning marine-cooling regime as *"06–13 EDT under offshore flow"* — both wrong. Per the actual lookup table, cooling is negligible at 06:00 (−0.2 °F), meaningful starting 09:00 (−1.6 °F), peak at 12:00 (−3.7 °F), holds through 14:00 (−3.0 °F), recovers through 17:00 — so the honest window is **09–16 EDT**. And the sb-off branch fires when the sea breeze is inactive regardless of wind direction, not specifically under offshore flow. Both phrases corrected.

</details>

<details open>
<summary><strong>v0.6.241 • June 26, 2026</strong></summary>

- Debug page L6 visibility pass — three places that still described a 4-layer stack updated to match the shipped 5-layer reality:
  - **TOC chip strip** gains an `L6 Microclimate` chip between L4 Diurnal and Research & Diagnostics, linking to `#sec-layer6`.
  - **"How to read these charts" methodology accordion** in Forecast Accuracy: lead-in rewritten from "four lines" → honest "L1–L4 stack across every field; L6 only stacks on the temperature card"; new Microclimate bullet added; the hedged "For fields where L6 is off" parenthetical on the Diurnal bullet replaced with a clean "every field except temperature, this is the final line."
  - **Per-field badge row** on the Forecast Accuracy temperature card now shows a green `L6 ✓ microclimate` badge alongside L2 / L3 / L4. Other fields don't render an L6 badge (structurally absent — same approach `_layersFor()` already takes for the chart legend).

</details>

<details open>
<summary><strong>v0.6.240 • June 26, 2026</strong></summary>

- L6 conditional audit added alongside L5 and R6. Every Fitter cycle compares paired L4 vs L4+L6 MAE on cove temperature (rows that pass the L6 valid-from filter and carry both error fields) and emits a SHIP/HOLD verdict. SHIP threshold: L6 beats L4 MAE by ≥2%. Verdict persisted to `l6_gate_history.json` with the same 7-day rolling gate shape as L5. Since L6 is already shipped, the gate asks "is L6 still earning its place?" — a 7-day HOLD-dominant window would be grounds to revert `cove_correction.ENABLED`.
- Debug page S1 audit table now shows an L6 column alongside L5 and R6, and an "L6 microclimate (ENABLED): SHIP/HOLD" row in the Latest panel with MAE numbers, improvement %, sample size, and the trailing 7-day keep-gate status. First Fitter cycle landed `insufficient_data` (n=4) as expected — real SHIP/HOLD verdicts start once n≥100, roughly 6 hours of post-deploy pair-log accumulation.

</details>

<details open>
<summary><strong>v0.6.239 • June 26, 2026</strong></summary>

- Debug page L6 audit pass — make all L6 text reflect the per-lead application that shipped earlier today (v0.6.237). Updates:
  - Layer 6 section "How L6 works" methodology now describes per-lead projection (forecast wind dir + parsed local hour + heuristic sb_active), why per-lead matters (uniform-Δ implementation was wrong by 3–5 °F at distant leads), and where L6 is evaluated (both 6d and the Forecast Accuracy chart, with the pre-deploy contamination called out and the natural 7-day clean-out date).
  - 6a "Live correction" card adds a "Per-lead Δ range (48h)" row from `weather_data.cove_correction.per_lead_delta_summary` so you can see at a glance whether the per-lead projection is producing the expected spread, not just the current-tick Δ.
  - 6d "L6 evaluation" anchors `L6_ENABLED_AT` on the per-lead deploy timestamp (17:19 EDT) so the L4 reconstruction is honest — subtracting today's lookup Δ from ambient_t only works against the per-lead-correct era.
  - Production stack list entry, cove R5 section's "Current status" block, and the "Since last curation" block all rotated to match.
  - Status section's "How to read the rest of this page" text updated to "Layer sections (L1–L4 and L6)" — was stuck at L1–L4 since before L6 shipped.

</details>

<details open>
<summary><strong>v0.6.238 • June 26, 2026</strong></summary>

- Fitter L6 filter: pairs whose snapshot was generated between the L6 ship (06-26 ~08:00) and the per-lead fix (v0.6.237 deploy at 06-26 17:19 EDT) carry an `error_l6` from the old uniform-Δ implementation that applied the current-tick Δ to all 48 leads. Filter those rows out of the L6 per-layer aggregation by `run_time` so the Forecast Accuracy chart shows only per-lead-correct era. Remove the guard once those rows age out of the 7-day window (~2026-07-03).
- New collector entry-point query: `?fit=1` short-circuits the normal collector run and triggers the Decay-Fitter once. Used to force a Fitter rebuild outside the 03:07 / 15:07 EDT windows after an L6 implementation change. Fitter rebuilt at 17:36 EDT; L6 starts clean from there.

</details>

<details open>
<summary><strong>v0.6.237 • June 26, 2026</strong></summary>

- **L6 per-lead application.** `cove_correction.py` previously applied the current-tick Δ°F to all 48 forecast leads — wrong by 3–5°F at distant leads when the regime swing crossed zero (e.g. applying noon's −3.7°F to a midnight lead). Now each forecast lead gets the Δ°F appropriate to that lead's projected regime: forecast wind direction from `hourly.wind_direction[i]`, local hour parsed from `hourly.times[i]`, and a heuristic `sb_active` (on in 13–18 EDT with S-half wind, off otherwise — coarser than the live detector but uses only forecast wind dir). `weather_data.cove_correction` now also includes a `per_lead_delta_summary` block (min/max/mean Δ) so the L6 chart can show the spread. Live verification: range −3.7 to +2.0 across the 48-hour horizon.

</details>

<details open>
<summary><strong>v0.6.236 • June 26, 2026</strong></summary>

- Status section now uses `<h2 class="section" id="sec-status">` so its header matches the Layer section headers and inherits the same click-to-collapse behavior. Each of the six sub-boxes (Production stack, Gated off, Stage 2 audits, Retired, Next scheduled decisions, Open architectural questions) is now an individual `<details>` collapsible. Defaults: Production stack, Gated off, Next scheduled decisions are open; Stage 2 audits, Retired, Open architectural questions are closed so the at-a-glance view leads with actionable state rather than reference material.

</details>

<details open>
<summary><strong>v0.6.235 • June 26, 2026</strong></summary>

- Consistent layer naming pass across the debug page. Each L-class now follows `LN — <structure> correction` with scope in parens when field-limited:
  - L1 — Raw model (baseline)
  - L2 — Aggregate-bias correction
  - L3 — Lead-decay correction
  - L4 — Diurnal correction
  - L5 — Synoptic-regime correction (solar)
  - L6 — Microclimate correction (temperature)
- Updated section headers, TOC link, chart legend / band-table headers, one-line summary, Production stack list, methodology prose, the "Since last curation" entry, and L6 section summary (now leads with "first layer trained on a spatial differential between station subgroups" — the actual architectural distinction). Comments in JS are left as-is.

</details>

<details open>
<summary><strong>v0.6.234 • June 26, 2026</strong></summary>

- Debug page data refresh: L5 trajectory updated to live values (5 SHIP / 0 HOLD, 8-cycle SHIP streak — two more SHIP days to clear); "Since last curation" block rotated to reflect today's curation cycle (L6 ship + ordering fix + tooling pipeline) and the new active-candidate count.

</details>

<details open>
<summary><strong>v0.6.233 • June 26, 2026</strong></summary>

- Forecast Accuracy band-table headers were hardcoded to 4 columns while data rows iterated `LAYER_LINES` (now 5 with L6) — so the temperature card had a 5th data column with no header label. Headers now generated from the same array as the data. Non-temperature cards filter L6 out of their layer set so the legend / column / line don't render where they'd never have data.

</details>

<details open>
<summary><strong>v0.6.232 • June 26, 2026</strong></summary>

- **L6 ordering fix.** Cove correction was previously applied inside `build_weather_data` BEFORE L3/L4 ran, so the Δ was silently absorbed into the L2 column and L3/L4 stacked on top of cove-modified temperatures. Moved `stamp_cove_correction` to after `apply_decay_corrections` so cove is genuinely the last layer in the stack. Forecast snapshot now distinguishes `t_l4` (pre-cove) from `t_l6` (post-cove); pair log captures `error_l6` for temperature rows; Fitter aggregates L6 into `per_layer_mae_by_lead`. Debug page Forecast Accuracy chart now shows L6 as its own line, populated only for the temperature row.
- New Layer 6 debug-page section with subsections 6a (live correction), 6b (lookup tables with APPLIED badge on the active branch), 6c (waterfront-vs-inland Δ history), 6d (cove-specific MAE evaluation: L4 vs L4+L6).

</details>

<details open>
<summary><strong>v0.6.231 • June 26, 2026</strong></summary>

- **L6 — cove regime correction shipped.** `cove_correction.ENABLED = True`. Two consecutive PASS reads on `r5_cove_analysis.py` (06-25, 06-26) cleared the post-build confirmation gate. Per-tick Δ°F now applied to `corrected_temperature` at all leads, indexed by (wind octant × sea-breeze active × hour-of-day). Scope-limited to the cove output only — distinct from the retired global R5. Lookup table built on 12-day waterfront-vs-inland gradient log (n=1,732). Debug page updated: one-line summary, Production stack list, and cove section all reflect the new L6 in the live pipeline.

</details>

<details open>
<summary><strong>v0.6.230 • June 25, 2026</strong></summary>

- Debug page sections 3a (fitted correction curves) and 3b (live forecast with vs without) now show the same APPLIED / diagnostic badge per field that 3c already used, and dim diagnostic cards to 0.65 opacity. Whitelist status is now consistent across all three subsections of L3.

</details>

<details open>
<summary><strong>v0.6.229 • June 25, 2026</strong></summary>

- Divergence-report streak counter now collapses multiple runs on the same calendar day into one read. Prevents re-running the digest on cached data from falsely advancing the gate counter — gates are designed around independent reads on different days.

</details>

<details open>
<summary><strong>v0.6.228 • June 25, 2026</strong></summary>

- Debug page data refresh: L5 status updated to live trajectory (4 SHIP / 0 HOLD over trailing 7d, 6-cycle SHIP streak; earliest plausible promotion now late-June if streak holds); C1 axes list in the one-line summary now includes C1f; cove section split into the retired global R5 decision and the current module-scoped gate (1/2 confirming reads, next read ~2026-07-01).

</details>

<details open>
<summary><strong>v0.6.227 • June 25, 2026</strong></summary>

- Divergence report: DISAGREE → GATED for clarity; status icons added (✓ aligned, ⏳ gated, ↑ ready-to-enable, ↓ ready-to-drop, ✗ unknown).
- Debug page: "Calibration-verdict, not MAE-verdict." → "C1 is evaluated by calibration, not forecast error." as its own sentence; removed redundant "Currently applied:" line from L4 intro; "Current-conditions sync" → "Current conditions" in the Production stack list.

</details>

<details open>
<summary><strong>v0.6.226 • June 25, 2026</strong></summary>

- `analysis/walkforward_l3l4_validator.py` default cutoff bumped from 2d → 10d. The 2d window is regime-fragile (documented 06-22 diagnostic) and causes the divergence-report streak counter to bounce.
- Divergence report L5 row now reads from the live Fitter-cycle trajectory file (`data.wymancove.com/l5_gate_history.json`) instead of the freshly-started divergence-history streak. Shows ship-days / hold-days / SHIP streak so the L5 row reflects the actual promotion gate, not just today's reads.
- Runner skips files matching `*.skip*` in the name (parked scripts).

</details>

<details open>
<summary><strong>v0.6.225 • June 25, 2026</strong></summary>

- Analysis tooling: single-command digest runner (`analysis/runlog/run_digest.sh`) executes all 63 analysis scripts and writes one summary at `analysis/output/DIGEST.txt`. Output includes pass/fail table, executive summary (deltas vs prior run), per-script verdict + tail, and a divergence report (production state vs latest script verdict, with streak counters against per-key promotion gates). History accumulates in `analysis/output/runlog/digest_history.jsonl` so gates become actionable as reads stack up. Skipping a script: rename it to `*.py.skip`.

</details>

<details open>
<summary><strong>v0.6.224 • June 25, 2026</strong></summary>

- Debug page "Since last curation" box: list text was inheriting too-dark color against the dark callout background (icons rendered, prose did not). Added explicit list color and a `.since-last-curation` print rule so the box flips to white background / dark text on print to match the rest of the page.

</details>

<details open>
<summary><strong>v0.6.223 • June 25, 2026</strong></summary>

- Debug page copy pass: L4 intro rewritten to reflect cc+ch shipped and the "stable hour-of-day signal" framing; "Shipped & live" → "Production stack"; L3 whitelist line clarified ("remains enabled only if it continues to beat the layer below"); L2 cloud blend names KBOS (Boston) and KBVY (Beverly) explicitly as coastal-gradient sources; current-conditions sync gains plain-language opener while keeping the `weather_data["current"]` / `condition_source` / `weather_code` debug handles; L5 phrasing softened ("today's snapshot strongly favors L5"); "Calibration-verdict, not MAE-verdict" bolded as the structural insight; "Pending decision (dated)" → "Next scheduled decisions (dated)"; "Most are confidence signals, not bias signals" → "Most surviving hypotheses measure forecast uncertainty, not forecast bias."

</details>

<details open>
<summary><strong>v0.6.222 • June 24, 2026</strong></summary>

- Wind card (Weather tab): removed C1 ±uncertainty suffix from collapsed-preview sustained/gust numbers — restores prior cleaner look. Confidence bands still live on the expanded chart.
- Debug page: cove gradient diurnal trough updated to refit values (−3.7°F at 12:00 EDT, n=1,732 over 12 days). Day-4 octant snapshot replaced with day-12 refit (S/SE/SW sea-breeze warming and N/NE/E/NW offshore cooling now reflect 1,732-tick window).
- `cove_correction.py` lookup tables refreshed from r5_cove_analysis day-12 read (n=1,732). Module remains `ENABLED = False` — input values updated for whenever the second confirming read clears the gate.

</details>

<details open>
<summary><strong>v0.6.221 • June 24, 2026</strong></summary>

- **Debug page page-1 summary fix.** The "Shipped & live" card still read `L4 whitelist: ch only` after cc → L4 shipped earlier today. Joe caught it on a read-through. Updated to `L4 whitelist: ch, cc` with the cc-added note. Added a fourth canon rule to memory: skim the page-1 summary on every Stage 2 ship for stale references.

</details>

<details>
<summary><strong>v0.6.220 • June 24, 2026</strong></summary>

- **Added "Since last curation" block at top of debug page.** Per Joe's request: a tight delta-list right below the curated-stamp summarizing what shipped, killed, weakened, or built since the previous curation. Glyph palette: ✓ shipped, ✗ killed, ↺ weakened, ⚙ infrastructure. The block replaces the implicit "you'd have to read the whole page to know what changed today" pattern with an explicit at-a-glance status. Will get rewritten each curation so the debug page is always preceded by a fresh diff against the prior state.

</details>

<details>
<summary><strong>v0.6.219 • June 24, 2026</strong></summary>

- **Debug page cleanup.** Fixed two stale lines from today's marathon: pipeline-count line read "7 active candidates" but should have been 6 after h K-taper shipped (the count was set before v0.6.218 promoted). Also removed a duplicate-fragment in the Group D h K-taper entry — a leftover passage from when I edited the "promote to Stage 2 by adding..." text into the SHIPPED block. Debug page is now consistent with the live production state.

</details>

<details>
<summary><strong>v0.6.218 • June 24, 2026</strong></summary>

- **Stage 2 SHIP: Humidity K-taper (lead-conditional L2 Kalman gain).** `weather_collector/processors/corrected_hourly.py` now applies a piecewise-linear soft_ramp to the L2 humidity bias instead of the prior exp(-lead/240) shape. Curve: K(0h)=1.0 → K(6h)=0.85 → K(12h)=0.70 → K(18h)=0.55 → K(24h+)=0.40. The prior exponential was effectively flat (~91% at lead 24); the soft_ramp pulls the L2 bias toward 40% at long leads where the station-network signal is stale. New `_soft_ramp_factors()` helper alongside `_decay_factors()`. `t` and `pr` continue to use the exponential decay (≤0.5% drift across ramp shapes — flat K is optimal for them). `weather_data["l2_decay_meta"]["humidity_shape"]` exposes the curve for the debug page.
- Justified by `analysis/h_lead_l2_ktaper_sim.py`: two confirming reads on a 7-day window — +7.75% MAE improvement on 2026-06-22, +6.60% on 2026-06-24. Direction-stable across both reads. Joe's-top-3 candidate since 06-22.
- **Debug page updated** to mark Humidity K-taper [🟢 Auto-wired · STAGE 2 SHIPPED 2026-06-24]. Monitor cc L4 + h K-taper on the live audit table for 7 days; revert either if their layer doesn't beat the prior layer by ≥3% in production.
- **Today's final tally:** 3 Stage 2 ships (cc → L4, C1f, h K-taper), 2 orthogonality kills (wind_shift_rate, C1g), 1 audit infra (Stage 4). Stage 1 pipeline: 10 → 6 active candidates.

</details>

<details>
<summary><strong>v0.6.217 • June 24, 2026</strong></summary>

- **C1g KILLED — orthogonality check.** `analysis/h_c1g_orthogonality.py` cross-tabbed C1g (obs_humidity ≥95, fog regime) vs C1f (precip_fc>0) and vs cc-saturation (cc_fc≥95). Marginalized over the unused axis. Result: **1 ORTHOGONAL / 69 REDUNDANT / 0 CONFOUNDED / 2 AMBIGUOUS** across 72 cells. The Stage 0 +134% cm / +149% ch elevation was sampling-driven — fog co-occurs strongly with both rain-forecast (C1f) and high-cc-forecast (cc-saturation). When you control for either, fog rows actually have *smaller* MAE than non-fog (ratio 0.02–0.25× across cl/cm/ch in the F=False or S=False subsets). No independent widening signal. Moved to Retired section per the canon rule. Second same-day kill (wind_shift_rate also killed earlier this morning).
- **Stage 1 pipeline now 7 active candidates** (was 10 this morning). Today's tally: 2 Stage 2 ships (cc→L4, C1f) + 2 orthogonality kills (wind_shift_rate, C1g). Solid Stage 0→ortho discipline.

</details>

<details>
<summary><strong>v0.6.216 • June 24, 2026</strong></summary>

- **Stage 4 UI-readiness audit infrastructure landed.** `analysis/c1_stage4_audit.py` compares each SHIP cell's calibrated MAE against its realized MAE on a 7d recent-holdout window vs a 7d preceding calib window. PASS ≤20% drift, WATCH ≤40%, FAIL >40%. Handles both the legacy single-axis (transition × stable) cells AND the v3 multi-axis cells (Q × pt × trans × c1f). First read: legacy axis (62 SHIP cells) returned 17 PASS / 20 WATCH / 25 FAIL — NOT READY, with FAILs dominated by `pp` (Brier-evaluated, MAE is the wrong yardstick) and `pa` (precip amount, naturally bursty). Multi-axis (296 SHIP cells) DEFERRED — cluster_spread_log only goes back to 06-20 (~4 days); calib window needs 14 days of history. **First multi-axis audit ETA ~2026-07-04** as cluster_spread accumulates.
- **wind_shift_rate KILLED same-day.** `analysis/h_wind_shift_rate_orthogonality.py` cross-tabbed the rotating ≥80° wind class vs C1a transition flag across 9 fields × 4 bands. Result: **1 ORTHOGONAL / 22 REDUNDANT / 2 CONFOUNDED / 11 AMBIGUOUS.** C1a already captures the signal (wind shifts and regime transitions co-occur). Only ch at 24-47h is independently orthogonal — too narrow to ship as a standalone axis. Moved to Retired section per the canon rule.
- Stage 1 pipeline now 8 active candidates (was 10 this morning): cc→L4 + C1f shipped Stage 2; wind_shift_rate killed; humidity K-taper / cloud saturation / C1e / C1g / C1h / dp depression still in queue.

</details>

<details>
<summary><strong>v0.6.215 • June 24, 2026</strong></summary>

- **Stage 2 SHIP: C1f precip_fc>0 wired as 4th confidence-layer axis.** `analysis/c1_confidence_calibration_v2.py` now stratifies multi-axis cells by a binary `c1f` flag drawn from `state_fc.precip_in > 0`. `weather_collector/processors/confidence_layer.py` computes the live c1f flag per-band (each band uses its own lead window of `hourly.precipitation`) and appends it to the lookup axis_key. Regenerated curated v3 table on 14-day window (1.29M pairs, 296,898 multi-axis pairs joined): **296 SHIP / 42 MARGINAL / 1048 SKIP** across 39 axis-keys. Top SHIP-bearing keys: Q23::rising::transition::p0 (43 cells), Q23::rising::stable::p0 (41), Q1::rising::transition::p0 (41). p1 cells are sparser (~5-10% prior on precip_fc>0) — most p1 cells SKIP on sample floor for now; will fill in as more rain-regime data accumulates.
- **ENABLED still False.** Stage 3 stamps the bands on `weather_data["confidence"]` so the live signal is observable, but ENABLED=False keeps the UI from consuming them as authoritative. Stage 4 gate = UI calibration audit confirming displayed bands contain truth at the claimed rate.
- **Debug page updated** to mark C1f entry [🟢 Auto-wired · STAGE 2 SHIPPED 2026-06-24] in the prioritization table and the Group A Stage 1 entry per the canon rule.
- Pipeline ship count today: cc → L4 (v0.6.214) + C1f (v0.6.215). Two Stage 2 promotions in one session.

</details>

<details>
<summary><strong>v0.6.214 • June 24, 2026</strong></summary>

- **Stage 2 SHIP: cc → L4.** Added `cc` to `L4_FIELDS` in `weather_collector/processors/decay_apply.py:70`. Cloud-cover forecasts now receive the diurnal hour-of-day correction alongside `ch`. Justified by `h_cloud_l4_sim.py` 70/30 train/test simulation: +5.0% MAE improvement on both 2026-06-22 and 2026-06-24 reads (06-23 dipped to +2.7% — a 1-day artifact). Two reads ≥3% with one ≥5% clears the 2-read promotion gate. cm rides along at +3.0% on 06-24 (was +2.7% on 06-23) — borderline; reconfirm 2026-06-29 before adding. cl stays disqualified. Monitor cc per-layer MAE on the live audit table over the next 7 days; if cc L4 doesn't beat L3 by ≥3% in production, revert.
- **Debug page updated** to mark cc→L4 entry [🟢 Auto-wired · STAGE 2 SHIPPED 2026-06-24] in both the prioritization table and the Group D Stage 1 entry per the canon rule.

</details>

<details>
<summary><strong>v0.6.213 • June 24, 2026</strong></summary>

- **Full Stage 1 manual re-run batch — debug page updated all at once.** Ran all 8 Stage 1 candidate scripts in parallel with refreshed pair-log cache (MYWEATHER_REFRESH=1 on first script, others share cache). Updated prioritization table + each candidate's Group A/D entry with new last-run dates and result deltas per the canon rule. Key shifts: (1) **cc → L4 recovered to +5.0%** (from +2.7% on 06-23), passing the 2-read ≥3% gate — now SHIP-READY, promoting to Stage 2 implementation (add `cc` to L4 whitelist in `decay_apply.py`); cm rides along at +3.0%. (2) **C1f precip_fc>0 strengthened** to 23 ortho cells (up from 21). (3) **Humidity K-taper held** at +6.60% soft_ramp (was +7.75%, still well above 5% floor). (4) **C1e post-frontal weakened** from 6 ortho to 3 (signal degrading as 06-17→-22 frontal cluster ages out; ch holds). (5) **dp depression nor_easter +3.79°F NEW** flag (n=279, small but extreme). (6) Cloud saturation, C1g, C1h all direction-stable across both reads.
- **Four new Stage 0 hypotheses tested.** `h_wind_shift_rate.py` — rotating ≥80° wind shift class shows ch +33%★, cm +24%, cc +15% MAE elevation; **promoted to Stage 1 as alt-transition axis** (Tier 2, needs orthogonality vs C1a). `h_mesonet_conf.py` — regime-scatter proxy null across all fields (0.93×–1.22×); retired. `h_persistence.py` — ws/wg lose to "current obs" baseline at all leads, initially flagged as possible mph/m/s unit bug; investigated and ruled out (both fc and obs are mph; L2+L3 already correct the 2× model over-prediction from 4.17→2.44 mph MAE; live frontend already does persistence-blending via blend_observed_into_hourly). Retired as expected behavior. `h_lightning_proximity.py` — pair log doesn't carry lightning data; infrastructure gap, not killed.
- **Stage 1 pipeline now 10 candidates** (was 9). cc→L4 ready to promote to Stage 2 implementation 2026-06-24.

</details>

<details>
<summary><strong>v0.6.212 • June 23, 2026</strong></summary>

- **Kills + nulls moved into Retired section.** Per Joe's instruction — Retired is the canonical home for ruled-out hypotheses, not the Stage 0 explorations log. Added "Recently ruled out — 2026-06-22 to 06-23 Stage 0 kills" subsection at the top of the Retired wrapper with compact entries (no charts, just verdict + script ref). Removed duplicate entries from Stage 0 explorations log so each kill lives in exactly one place. Stage 0 log now holds only design seeds, promoted breadcrumbs, data-limitation flags, and the wd×ws_obs script bug. 7 kills + tunings relocated: regime-conditional L3, L3 regime mismatch, lead × C1a, solar zenith × cloud (duplicate), state_fc.solar_wm2 × cloud (duplicate), weekday vs weekend artifact, L4 window-size null, lead-bin granularity null.

</details>

<details>
<summary><strong>v0.6.211 • June 23, 2026</strong></summary>

- **Tier labels added inline to every Stage 1 candidate** (was only in the comparison table — Joe caught the gap). Each entry now shows [Tier N] color-coded next to the wired badge: green=1, yellow=2, brown=3. Eight Stage 1 entries updated across Group A + Group D.
- **C1g and C1h promoted to proper Group A entries** with full Stage 1 narratives. They were previously only listed in the prioritization table + Stage 0 explorations log — incomplete per the canon rule. Each entry now carries its full hypothesis statement, magnitude findings, architectural slot, and open-questions section.

</details>

<details>
<summary><strong>v0.6.210 • June 23, 2026</strong></summary>

- **Debug-page-is-canon convention codified.** Joe explicitly said "I want that page to be the canon" (2026-06-23). Two non-negotiable rules now in memory under `feedback_debug_page_canon.md`: (1) every Stage 1+ candidate carries a wired-state badge (🟢 Auto-wired · 🟡 Hybrid · ⚫ Manual · 🔒 Gated off) right next to the title; (2) every manual run updates the relevant page entry with new numbers + date stamp. Memory and changelog accumulate sediment — the page IS read.
- **Wiring badges added inline to every Stage 1+ candidate** on the Backlog + Group A + Group B + Group D + S1 sections. Prioritization table now has a "Wired" column and a "Last manual run" column. Legend rendered at the bottom of the table.
- **`h_cloud_l4_sim.py` gained `--cutoff DATE` argument** for cleaner multi-cutoff stability testing.
- **★ cc → L4 hypothesis WEAKENED on 06-23 re-run.** Today's read: cc +2.7% (was +5.0% on 06-22 — below 3% ship floor). ch rose to +4.5%, cm +2.7%, cl -2.0%. Day-over-day cc dropped 2.3pp — more window-sensitive than humidity K-taper. cc demoted from Tier 1 ship-ready to "watch" status; needs ≥2 future reads ≥3% before earning the 7-cutoff simulator gate. ch could take over as the priority cloud field if its rise stabilizes. cl confirmed disqualified.

</details>

<details>
<summary><strong>v0.6.209 • June 23, 2026</strong></summary>

- **Final Stage 0 batch + prioritization lockdown.** Wrote 4 more scripts (`h_rh_saturation.py`, `h_ws_wd_error.py`, `h_trend_direction.py`, `h_lead_c1a.py`), found 2 new Stage 1 candidates + 1 kill + 1 script bug to debug later.
- **★ C1g RH ≥95% fog axis (Stage 1, Tier 2).** When state_obs.humidity hits saturation, cm MAE +158%, ch +139%, pa +4649%. Cloud cover saturates -59% (model less wrong because clouds are usually there). Temp/dp converge. Promote as obs-keyed confidence axis. Needs ortho check vs cc-saturation and C1f.
- **★ C1h trend direction (Stage 1, Tier 3).** When model predicts sharp 0→6h cloud change, accuracy collapses: cl rising +1030%, cm rising +315%, ch rising +91%. Stable forecasts dramatically better. Real signal but only 1 read; magnitudes need 30d window confirmation.
- **KILL: Lead × C1a transition interaction.** Only ch shows monotonic lead-growing penalty, and ch is already in C1e — redundant.
- **Bug logged: wd × ws_obs join.** `h_ws_wd_error.py` returned empty output. Investigate later.
- **Prioritization framework added to debug page Backlog section.** All 9 Stage 1 candidates ranked into 3 tiers with re-run scripts and promote criteria, so manual weekly re-reads can decide which graduate to Stage 2 implementation. Tier 1 = 3 candidates ready to ship when 06-29 confirms (C1f, humidity K-taper, cc→L4). Tier 2 = 3 candidates needing stability proof (cloud saturation-unbiasing, C1e bidirectional, C1g RH≥95%). Tier 3 = 2 candidates needing more evidence (C1h trend, dp depression).

</details>

<details>
<summary><strong>v0.6.208 • June 23, 2026</strong></summary>

- **4 more Stage 0 scripts; 1 new Stage 1 (architectural); 2 design seeds; 1 data limitation.**
- **★ Cloud saturation-unbiasing (Stage 1, Group D).** `h_cloud_floor_ceiling.py` revealed dramatic asymmetry at forecast saturation extremes: cc fc=95-100% averages -32.7pp signed bias, cl 95-100% averages **-63.4pp** (n=13,391), cm -54.3pp, ch -47.5pp. When the model commits to "fully cloudy," observation runs 50-60 pp lower on average. **Architectural significance:** no existing layer (L1-L4) conditions on the forecast VALUE bin — they condition on lead and hour-of-day. The current correction stack structurally cannot fix this saturation bias. Stage 2 implementation = "saturation unbiasing" pre-correction (likely L2.5, between mesonet and decay) learning per-forecast-value-bin signed shifts.
- **Design seed — precip_obs > 0 as obs-keyed confidence mirror.** Worst case: false-alarm cell (precip_fc>0, precip_obs=0, n=2,904) shows cl +283%, wg +57%, h +50%, cm +107%. Real signal but architecturally tricky — at current tick we have precip_obs[now] not precip_obs[future]. Different mechanism than C1f. Could extend as "currently-raining widens future cloud/wind confidence." Needs design before promoting.
- **Design seed — cloud composition (layered skies).** wg +65% on three-layer, ws +25% on two-layer, t/h ~18-35%. Real but small; cloud portion confounded with cc magnitude.
- **Data limitation — front-type asymmetry.** `frontal_events_log.json` carries type field but detector only classifies sea_breeze (1 of 6); rest are "unknown." Need `frontal_detection.py` to learn cold/warm classification (wind-rotation direction + pressure-tendency shape) before this becomes testable.

</details>

<details>
<summary><strong>v0.6.207 • June 23, 2026</strong></summary>

- **3 more Stage 0 scripts + 2 new Stage 1 promotions + 1 kill.** Wrote `h_pre_frontal.py`, `h_solar_cloud_selfcheck.py`, `h_forecast_coherence.py`.
- **★ C1e extended bidirectional (pre+post-frontal).** `h_pre_frontal.py` showed pre-frontal MAE hits **wind hardest** — opposite physics from post-frontal which hits clouds. ws +143% at 3-6h before passage, wg +138%, cm +98%. Temp/humidity actually LOWER pre-frontal. Orthogonality check (`h_pre_front_orthogonality.py`): 8 ortho cells but all at 24-47h band (short-lead × pre-frontal × no-transition × no-post-frontal is too sparse). Narrow promote — extends C1e from one-sided (post) to bidirectional via `time_to_nearest_front_h` signed value.
- **★ C1f: state_fc.precip_in>0 as confidence axis (broadest scope today).** `h_forecast_coherence.py` showed when model forecasts precip but obs reports clear sky (n=257), every field's MAE explodes — cl +959%, pa +674%, cm +547%, t +89%, h +76%. Generalization: `precip_fc>0` ALONE is a confidence axis. Orthogonality (`h_precip_fc_orthogonality.py`): **13 ORTHOGONAL vs C1a, 8 ORTHOGONAL vs C1e, 21 total** across t/h/ws/wg/cl/cm/ch. cl 3.5-3.7× elevation is the cleanest cell. cc REDUNDANT (definitionally correlated with precip_fc). Wire as binary axis in `confidence_layer.py` v3.
- **KILL: state_fc.solar_wm2 × cloud MAE.** Apparent cloud-MAE-by-solar spread (cl 134%, cm 376%) is just the day/night cloud bias the cc→L4 hypothesis already addresses. Same axis, different slice. Duplicate.

</details>

<details>
<summary><strong>v0.6.206 • June 23, 2026</strong></summary>

- **C1e orthogonality check — narrow promote.** `analysis/h_hsf_orthogonality.py` cross-tabbed each (field, lead-band) by hsf_group (0-24h post-frontal vs ≥24h baseline) × C1a transition flag (state_fc.regime ≠ state_obs.regime). Verdict: **6 ORTHOGONAL / 23 REDUNDANT / 4 CONFOUNDED / 3 AMBIGUOUS**. The ORTHOGONAL cells are tightly concentrated: ch (all 4 bands, stable post/baseline ratio 2.08-2.91×) and cc (12-23h, 24-47h, stable 1.45-1.62×). Everything else — temp, wind, humidity, dewpoint, cl, cm, short-lead cc — is redundant with C1a (regime-transition already captures the post-frontal effect for those fields). Verdict overall: PROMOTE as **narrow C1e covering only ch (all bands) + cc (long-lead)**. Not a generic axis. Compounds with C1a: when both fire, ch MAE hits 6.64× baseline at 6-11h. Stage 2 wires hsf into `confidence_layer.py` v3 as the 4th axis (alongside C1a/C1b/C1c). Stage 1 re-confirm 2026-06-29.

</details>

<details>
<summary><strong>v0.6.205 • June 23, 2026</strong></summary>

- **Hours-since-front × MAE — debugged and promoted.** Yesterday's 06-22 run hit HTTP 403 because Cloudflare blocks the default `python-urllib/3.x` User-Agent. Fixed by adding `User-Agent: curl/8.4.0` header in `analysis/h_hours_since_front.py`. Re-ran successfully: joined 306,612 pair-log rows with 6 frontal passages (06-17 to 06-22). Big finding: **cloud-high (ch) MAE runs 3.5× baseline for the entire 24h post-passage window** (+253-281% across all 4 bands); cc +94/+117/+54/+7%, cm +60/+47/+43/+21%, h +23/+32/+16/+3%. t mixed (+14% short, -31% mid-window). Promoted to Stage 1 as **C1e axis candidate**. Next step (Stage 1.5) is orthogonality check vs C1a (regime-transition penalty): C1a measures "model thinks different regime than reality" while C1e measures "absolute time since transition" — related but distinct. If orthogonal across (field, band) cells, ship as C1e; if redundant, fold into C1a as time-since-passage stratification. Caveat: only 6 frontal passages in sample, so magnitudes may be overfit to specific weather; direction is robust but size needs more passages.

</details>

<details>
<summary><strong>v0.6.204 • June 23, 2026</strong></summary>

- **Debug page Stage 0 explorations log.** Six smoke tests from last night's third Stage 0 brainstorm batch now documented on the debug page under the new "Stage 0 explorations — completed, not promoted" subsection. Tracks each script + verdict + reason so future Joe doesn't re-explore them without new evidence: asymmetric L3 (design seed), regime-conditional L3 (killed), L3 regime mismatch (killed), run-time issuance bias (design seed, needs valid-time control), hours-since-front (failed on GCS 403), L4 window size (methodological null), lead-bin granularity (methodological null), solar zenith × cloud (duplicate of cc→L4), weekday vs weekend (likely artifact at 21d window, revisit 2027).
- **New Stage 1 candidate: regime-conditional dewpoint depression correction.** Added under Group D. `h_dewpoint_depression.py` joined t-rows and dp-rows at each obs_time (n=121,922); overall depression |err|=4.36°F with near-zero overall bias, but stratified by observed regime: frontal -2.19°F (n=5,243), sea_breeze +1.45°F (n=5,119), sw_flow +1.41°F (n=15,661). Frontal forecasts say drier than reality, sea_breeze + SW says wetter. Re-confirm 2026-06-29 alongside walk-forward #4 and other Group D candidates. Stage 2 needs sub-analysis: which of t or dp contributes more to the residual? Likely dp (L2/L3/L4 already correct t aggressively). Implementation = regime-conditional dp shift table, L5-shape but dp-only. Affects fog probability, feels-like, comfort scoring downstream.

</details>

<details>
<summary><strong>v0.6.203 • June 22, 2026</strong></summary>

- **Top-3 markers updated.** ★-marker on the curated backlog moved from the 06-20 Joe-top-3 (marine-layer, cloud-ceiling regime, cluster-spread) to the two NEW Group D candidates that emerged 06-22 (humidity K-taper, cc→L4). Memory note records why: expected user-MAE delta per unit time favors the newer Stage 1 candidates given today's evidence. Old top-3 items still active in their respective groups; rank ordering reflects current EV, not historical interest.

</details>

<details>
<summary><strong>v0.6.202 • June 22, 2026</strong></summary>

- **Second Stage 0 brainstorm batch — 4 new scripts, 1 ship candidate, 2 kills, 1 design seed.** Wrote and ran `h_cloud_diurnal.py`, `h_l3_regime_mismatch.py`, `h_run_time_bias.py`, and the follow-up `h_cloud_l4_sim.py`.
- **★ Cloud-cover → L4 whitelist (Stage 1, Group D).** Diurnal stratification on cc/cl/cm/ch showed huge signed bias spreads — cc 33pp, ch 51pp, cl 24pp, cm 25pp — across hour-of-day. Model over-calls cloud cover heavily pre-dawn (cc +29pp at 04Z, ch +42pp at 04Z), under-calls afternoons. The train/test L4-fit simulation (70/30 split, mean-zero-normalized per-hour correction) however shows only **cc clears the 5% ship threshold (+5.0%)**; ch +2.8%, cm +1.8%, cl -0.8% (actually hurts). Same lesson as L2 K-taper sim earlier today: bias spread ≠ shippable gain. Stage 1 scope = cc only. Re-confirm 06-29; if ≥3% holds, 7-cutoff simulator gate (per the cm-drop cautionary tale) before adding "cc" to L4_FIELDS.
- **L3 regime-mismatch kill.** `h_l3_regime_mismatch.py` showed L3 wins less under regime mismatch (ws +50% on match → +40% on mismatch, 10pp gap) but still wins big on both sides. Gating L3 to regime-agreement would lose the +40% to clean up marginal noise. Not worth it.
- **Run-time issuance bias — held.** `h_run_time_bias.py` showed clean sinusoidal pattern on humidity L1 MAE by run_time hour (8.0 at run_h=0-2Z → 10.5 at run_h=12-13Z, 32.9% spread). t and cm also ≥10% spread. But this could be confounded with valid-time-of-day (each run_h pairs with a specific obs distribution). Needs a controlled follow-up that holds valid_time fixed. Logged as design seed, not promoted.

</details>

<details>
<summary><strong>v0.6.201 • June 22, 2026</strong></summary>

- **Marine-layer sandbox field-name bugs (silent no-op fix).** `stamp_marine_layer_correction` was reading `hourly.time` (singular) and `hourly.wind_direction_10m`, but the live payload uses `hourly.times` (plural) and `hourly.wind_direction`. The function's early-return on empty arrays meant no stamp + no error log. Fixed by trying the correct names first, with the wrong names as fallbacks. Verified by reading the live payload's `hourly` keys before deploying.
- **L2 K-taper simulation reframes the Stage 1 finding to h-only.** New `analysis/h_lead_l2_ktaper_sim.py` models the actual ship: replace flat K with K×ramp(lead) and recompute MAE per pair. Result on today's window: **h gains +7.75% with soft_ramp (100% at lead 0 → 40% floor at lead 24)**; t and pr show ≤0.3% drift across every ramp shape — flat K is optimal for them. The per-lead-band MAE pattern from `h_lead_l2.py` was real but didn't translate to a per-pair simulation gain for t/pr because the small mid-lead help approximately cancels the long-lead waste. Stage 1 entry on debug page rewritten to reflect h-only target. Useful lesson recorded: lead-band MAE shape ≠ shippable gain; always simulate the actual modification before promoting.

</details>

<details>
<summary><strong>v0.6.200 • June 22, 2026</strong></summary>

- **New hypothesis: lead-conditional L2 Kalman gain (Stage 1, Group D).** Three Stage 0 scripts written + run: `h_asymmetric_l3.py`, `h_regime_l3.py`, `h_lead_l2.py`. The lead-conditional L2 K hit hard: additive L2 bias (t, h, pr) gives huge gains in the first 5 hours and decays to near-zero by 24-47h. Multi-cutoff verified across 06-15 / 06-18 / 06-22 windows: h @ 0-5h holds rock-solid at +45/+47/+45%; t @ 0-5h at +16/+16/+22%; pr @ 0-5h at +10/+12/+16%. 24-47h gains weak or flickering — L2's flat K is wasting correction at long leads. Wind already linearly tapers K 0→100% across hours 0-24; the proposal is to generalize the shape to additive-bias fields. Promoted to Stage 1 with re-confirm date 2026-06-29 (alongside walk-forward #4). New "Group D — Methodological refinements" section added to the curated backlog on the debug page.
- **Regime-conditional L3 hypothesis killed cleanly.** `h_regime_l3.py` showed L3 wins in every regime for ws/wg/ch/cm (no regime where L3 loses by ≥3% with n≥500). pp loses in every regime but that's the documented Brier exception, already handled by the R0 audit's MAE-Δ suppression. The current whitelist is correctly tuned per-regime; no opportunity here. Useful negative result — eliminates a hypothesis without wasting Stage 2 cycles on it.
- **Asymmetric L3 — design seed.** `h_asymmetric_l3.py` showed dramatic asymmetry: wind L3 wins +57% on over-calls but loses -120 to -166% on under-calls; ch +24% vs -13%. Not directly actionable (you can't predict over- vs under-call before obs comes in), but informs a future "L3-with-confidence-gate" hypothesis: skip L3 when recent bias trend isn't strong enough to predict the sign. Logged as design input, not promoted.

</details>

<details>
<summary><strong>v0.6.199 • June 22, 2026</strong></summary>

- **Marine-layer cc correction — Stage 3 sandbox (gated OFF).** New `weather_collector/processors/marine_layer_correction.py` stamps `weather_data["marine_layer_correction"]` every tick with the NE-flow-morning cc over-call deltas from Stage 2 (06-21 read): -18.8% at 6-11h, -31.8% at 12-23h, -35.5% at 24-47h. Gate: `wd ∈ [45°, 105°)` AND `hour_local ∈ [4, 9)`. Cap: 40% magnitude (inherits L5's cc cap). 0-5h band skipped (Stage 2 bias was -2.0, indistinguishable from noise). Wired into `collector.py` after solar_correction stamp. `ENABLED=False` until weekly Sun-morning re-reads (06-28 / 07-05 / 07-12) confirm. Live stamping starts now so we can validate per-tick gated-leads counts match forecast conditions before flipping the switch. Smoke-tested: 5/5 gate scenarios produce expected deltas; cloud_cover unmodified at ENABLED=False.
- **τ sweep extended to 35d/42d.** `analysis/decay_tau_tuning.py` grid extended. Findings: curve hasn't flattened — 6 of 9 fields prefer τ=42, the longest tested. `pa` at τ=42 gives +8.2% (yesterday's τ=28 was +9.4%, within noise — no change). `pr` moved from -1.10% at τ=28 (yesterday, fell back to default) to +3.1% at τ=42 (today, approaching 5% threshold). One more read could promote `pr` to τ=42; watch. Other improving fields (ws +2.2%, wg +1.8%) below threshold.

</details>

<details>
<summary><strong>v0.6.198 • June 22, 2026</strong></summary>

- **C1 confidence table re-curated (Stage 1 + Stage 2 refresh).** Dry-run of `c1_calibration_audit.py` ahead of the 06-26 gated read showed 12 of 41 cells DRIFTED — wind ws/wg at short leads (+20-42%), pa across all bands (+24-90%), pr at mid leads (-10 to -21%), sr 12-23h (-19%). Curated bands were ~14 days stale; sea-breeze seasonality + marine-layer escalation had shifted the underlying spreads. Re-ran `c1_confidence_calibration.py` + `c1_curate_confidence_table.py` → fresh `c1_confidence_curated.json` with **46 cells wired** (was 39): 34 SHIP + 10 MARGINAL + 2 REVIEW (excluded) + 10 SKIP. Post-refresh re-audit landed at 70.45% pass rate, still under the 75% threshold — the bands are structurally fresher and broader, but 7d-window MAE variance makes the strict gate hard to clear. Audit framework verified working (caught real drift on first dry run). 06-26 audit will likely also HOLD unless threshold is loosened or measurement window is widened, but the deployed bands themselves are now strictly better than before.
- **Shadow whitelist tuner — pp Brier exclusion.** S1 panel L3 match rate was reading 0% across all 7 logged cycles. Diagnosed as a metric-mismatch artifact: production keeps `pp` in L3 for the -5% Brier improvement (v0.6.20), but the shadow tuner is MAE-only and will always recommend dropping it. Added a `BRIER_FIELDS = {"pp"}` strip on both sides of the L3/L4 set comparison in `corrections_debug.html` so the displayed match rate reflects the metric the shadow tuner actually evaluates. Today's panel should now show ~100% L3 match — accurately reflecting that production is tuned correctly on MAE-graded fields.
- **Fog card activation bug.** `app-main.js:577` read `data.derived.fog_likelihood` to decide whether the fog risk card should dim out as inactive — but the collector field is `fog_probability`. Result: card stayed grayed even at 95% fog probability with a "Likely" label. Renamed the JS reference. Verified live data: `fog_probability=95, fog_label="Likely"` → card now activates and gets the appropriate `tile-fog-high` gradient.

</details>

<details>
<summary><strong>v0.6.197 • June 22, 2026</strong></summary>

- **Backtest sweep default window 2d → 7d.** `backtest/sweep.py` `test_days` default + `--days` CLI default both bumped. 2-day windows kept echoing whatever short-term regime we were in — today's walk-forward L3/L4 #3 diagnostic showed the same window-artifact pattern (ws/wg L3 "losing" at 2d, winning -26%/-35% at 10d). The B1 sweep was reading the same false alarm. Re-ran with new default: wind L3 wins -34.9% wg, -24.6% ws, ch L3+L4 wins -24.5% over l2_only on 599,504 pairs. Result written to `gs://myweather-data/backtest_sweep_results.json`; debug page B1 caption auto-updates to "Window: last 7.0 days".

</details>

<details>
<summary><strong>v0.6.196 • June 22, 2026</strong></summary>

- **Debug page sync.** L3 per-field τ override paragraph now lists both `pp` and `pa` (was `pp` only — pre-v0.6.195). L5 promotion-gate verdict refreshed to today's 2×SHIP / 5×HOLD (was the 06-21 post-refit 3/4 snapshot), with a note that `l5_solar_analysis.py` reads SHIP on the standalone window while the 7-day-trailing gate hasn't cleared.

</details>

<details>
<summary><strong>v0.6.195 • June 22, 2026</strong></summary>

- **L3 per-field τ override #2: `pa` (precip amount) → τ=28d.** `decay_tau_tuning.py` re-read on 06-22 (held-out 145k pairs) showed precip amount gains -9.4% MAE at τ=28 vs the τ=14 default. Joins `pp` in the `TAU_DAYS_BY_FIELD` map (second override). Same precip-family pattern: noisier observation truth, smoother bias estimate wins. Next Fitter cycle (21:07 EDT) refits `pa` corrections with the longer window; `decay_corrections.json` metadata will stamp `tau_days_by_field: {pp: 28, pa: 28}`.
- **Walk-forward L3/L4 #3 read (06-22) + 5d/10d diagnostic.** Default 2d run flagged ws/wg L3 drops (L2-only verdict). Wider windows reinstated wind L3 wins (ws -26%, wg -35% at 10d) — diagnosed as 2d-window artifact, not a real regression. ch L3+L4 + cm L3 stable across all reads. Wind L4 dead at every window. No whitelist edit. Debug page "pending decisions" updated.

</details>

<details>
<summary><strong>v0.6.194 • June 22, 2026</strong></summary>

- **Tempest cull: Preston Ct (85569).** Moved from `TEMPEST_STATIONS` to `CULLED_TEMPEST_STATIONS` in `weather_collector/fetchers/tempest.py`. 7-day uptime was 5.7% (57/1008 successes) — either offline or hit the same field-level API sharing restriction as the 06-04 batch. 60 → 60 active mesonet seats (45 WU + 19 Tempest – 5 humidity denylist).

</details>

<details>
<summary><strong>v0.6.158–v0.6.174 • June 21, 2026</strong></summary>

A long Sunday — 17 versions shipped, 16 manual analyses run, two production bugs caught and fixed in live operation.

* **Briefing — three prompt iterations + two validator additions.** v0.6.159 added the "pleasant day IS the story" rule so the model leads with comfortable today-conditions instead of reaching into tomorrow for drama. v0.6.160 added explicit value-judgment guidance ("Beautiful morning at the cove," "Picture-perfect afternoon") gated to days where every objective test (clear sky, comfortable temp, light wind, low humidity, no precip) is met. v0.6.172 plugged two real-data failure modes: (1b) reject present-tense "rain/showers/drizzle/downpour" in the headline when `current.precipitation == 0` AND Pirate minutely[:10] is all dry AND `weather_description` carries no rain word — caught by the 17:47 ET "Light rain and 71° with calm NE breeze" hallucination when the sky card correctly read Overcast; (1c) sky-card consistency — when `weather_description` is set, the headline cannot contradict it (no "clear/sunny" when Overcast, no "overcast/cloudy" when Clear). Future-tense and trend-verb forms still pass.
* **Marine-layer hypothesis — Stages 1+2 complete in one day (v0.6.161).** New scripts `analysis/marine_layer_stage{1,2}.py`. Stage 1 stratified the pair log on NE flow (wd 45-105°) × morning hours (4-9 EDT) and found a +28.1 mean / +25.0 median over-call bias in cloud cover (n=3,119) vs near-zero in every other stratum. Temp/dewpoint/humidity unaffected — this is a cloud-skill bias, not a temp bias. Invisible to global L3/L4 walk-forward (consistently L2-only-recommend for cc/cl) because it lives in ~3% of conditions. Stage 2 verified robustness to bin perturbation, strong lead-dependence (−2.0 at 0-5h → +35.5 at 24-47h), and temporal non-stationarity (ISO-week W23 +11.6 → W25 +38.0). Conditional SHIP-candidate; weekly Sun-morning re-reads scheduled through 07-12.
* **L3 per-field recency-weighting τ (v0.6.167) + metadata emission (v0.6.170).** `decay_tau_tuning.py` flagged precipitation amount (pp) as gaining +11.1% MAE at τ=28 days vs the global default τ=14. Added `TAU_DAYS_BY_FIELD` override map in `decay_fit.py` with `pp: 28` as the first entry. v0.6.170 patched all four metadata-emit sites so `decay_corrections.json` now carries `tau_days_by_field` alongside the scalar default.
* **L5 bias refit (v0.6.168).** Last fit was 06-17 v0.6.112 — 4 days stale, dragging the simulator. Re-ran `l5_recompute_biases{,_hourly}.py`, patched `solar_correction.py` with refreshed `_BIAS_FALLBACK_BY_REGIME` + `_BIAS_BY_REGIME_HOUR`. Largest fallback shifts: frontal -169.2 → -81.1, se_flow -27.3 → -114.9. Promotion-gate verdict moved 1×SHIP/6×HOLD → 3×SHIP/4×HOLD, ceiling +7.2% → +8.1%. Still NOT promoting; earliest plausible mid-July (06-24/06-25 estimates retired).
* **Thunderstorm severity gate tightened (v0.6.171) — caught the 17:47 ET headline live.** Detector was firing `severity="severe"` on close lightning alone, even with zero current precip and Low CAPE. Today's case: 25 strikes / closest 19km / 0.0"/hr precip / CAPE 357 (Low). Briefing model picked up "severe" from the sky_override and produced "Severe thunderstorm pounding the cove." Fix: require `heavy_precip` (≥0.3"/hr) as a necessary condition for "severe." Close-but-dry lightning is now "active" not severe.
* **Audit-revealed bug fixes (v0.6.158).** Bug 2: `backtest_snapshot` was capturing L2-blended cloud as "raw HRRR" because `apply_decay`'s raw-preservation block runs after `cloud_obs_blend` mutates. Fixed by preserving `raw_cloud_cover{_low,_mid,_high}` in `cloud_obs_blend.py` BEFORE the mutation loop. Bug 3: `briefing.js` had a stale hard-coded wind exposure table drifting from `config.WIND_EXPOSURE_TABLE` — now reads from `data.wind_exposure_table`. Bug 4: `briefing.js` and `app-main.js` had drifting hardcoded WORRY thresholds — both now read `data.worry_thresholds`. Source of truth lives only in `weather_collector/config.py`.
* **Sources drawer overhaul (v0.6.162-v0.6.166).** Five small ships. v0.6.162 refreshed stale descriptions (KBOS/KBVY now mention cloud-cover obs, Tempest corrected from "3 within 0.4mi" to "20 within ~2.5mi"). v0.6.163 made the per-station list collapsible. v0.6.164 removed the dead Gemini row and simplified the briefing-source logic to "Groq down = critical." v0.6.165 renamed "WU Multi" to "Mesonet" with live totals in the row description. v0.6.166 dropped the "Station list" expander label in favor of the native disclosure triangle.
* **L6 → C1 rename (v0.6.174, 3 commits).** L-class is for correction layers that change forecast values; the confidence layer attaches uncertainty without changing values, so it earns its own naming. New scheme: **C1** = the multi-axis confidence layer (was L6), with sub-letters for axes feeding the same calibration — **C1a** regime-transition (R6's input signal), **C1b** cluster-spread quartile, **C1c** pressure-tendency bin, **C1d** (future) KBOS-vs-KBVY cloud disagreement. Commit 1: production code + bundled data files (`weather_collector/data/l6_*.json → c1_*.json`, loader updated atomically). Commit 2: 5 `analysis/l6_*.py → c1_*.py` + internal refs. Commit 3: 15+ HTML mentions + 3 JS mentions rewritten with sub-letters surfaced throughout. Future confidence consumers earn new C-numbers; new axes earn new sub-letters.
* **R0 audit UX — amber color for disabled-layer-winning deltas (v0.6.173).** Today's table showed `h L4 Δ=▼0.26` in green while `Applied? = No` was red and the banner above was orange warning about exactly that cell — three contradicting colors on the same row. Disabled-layer-winning deltas now render amber to match the opportunity banner. Same logic adds the `⚠ (band +N%)` flag mirroring the loss-side ⚠.
* **Maintenance — corrections debug canonicity (v0.6.169).** L5 Stage 3 list, L5 G1 entry, L3 methodology blurb, and date-gated section all refreshed to reflect today's post-refit trajectory and the new L3 per-field τ override.

</details>


<details>
<summary><strong>v0.6.147–v0.6.157 • June 20, 2026</strong></summary>

C1 (then L6) multi-axis confidence plumbing + correction stack honesty fixes for current-conditions.

* **C1/L6 confidence-layer v2 — multi-axis plumbing (v0.6.151).** Extended the single-axis Stage 3 from 06-19 into a multi-axis lookup: regime-synoptic transition × cluster-spread quartile × pressure-tendency bin. Runtime classifies live axes each tick, builds an `axis_key` like `Q1::flat::stable`, looks up the matching cell, falls back to legacy single-axis cell on miss. New `confidence_layer.py` helpers `_current_spread_quartile()` and `_current_pt_bin()` use cuts published in the curated table's `stage1_meta`. `live_axes` block stamped on `weather_data["confidence"]` carries the runtime classification + `multi_hits` counter for monitoring.
* **Cluster-spread per-tick logger shipped (v0.6.149).** New `processors/cluster_spread.py` writes per-tick `spread_t` (std across Marblehead/Salem/Swampscott PWS cluster medians) to `cluster_spread_log.json` (60-day retention). Provides the data layer for C1b. Persistent log needed because the value at every past tick is required for Stage 1 calibration joining — only forward-going data accumulates from here.
* **Wind card fix — authoritative-source floor + corrected exposure table (v0.6.150).** Two fixes triggered by today's "wind 9 N / Light Winds" headline when reality was 17 mph from NW. (1) Added an authoritative-source floor in `wind_blend.py`: when both KBOS and KBVY METARs agree on a wind speed >1.4× the octant-median pick, defer to their median. Mirrors the WU_CAP guardrail in the opposite direction. Plus a direction guardrail that rejects the chosen direction if >60° off the airport+buoy+Tempest consensus. (2) Corrected `WIND_EXPOSURE_TABLE` in `config.py` to reflect Joe's actual geography — direct exposure from ~270° through 0° (was previously modeled as if a peninsula blocked NW winds, which is geographically wrong).
* **Current-conditions sync + L2 cloud blend + 5-band cloud labels + gust fixes (v0.6.153/154).** Multi-fix consolidation. (a) `current_from_hourly.py` syncs `weather_data["current"]` cloud_cover / weather_code / weather_description / uv_index from the L1→L4-corrected hourly[0] value, not the separate `fetch_current_gfs()` call (which was bypassing the correction stack for these fields). (b) New `cloud_obs_blend.py` applies a Kalman-gated L2 blend on hourly[0] cloud cover using KBOS+KBVY METAR observations — same pattern as the temp/humidity L2 blend, with a cloud-tuned gain function (`_kalman_gain_cloud`) that treats KBOS-KBVY disagreement as real spatial gradient rather than sensor noise. (c) 5-band cloud labels with a new local weather code 100 "Mostly Cloudy" to fill the perceptual gap between Partly Cloudy (37-62%) and Overcast (≥87%). (d) Gust < wind impossibility guardrail in `wind_blend.py` — physical sanity floor enforces `gust >= wind` on the final blended values.
* **Shadow whitelist tuner — held_cycles + promotion-gate counter (v0.6.147).** When the shadow tuner's recommendation is unchanged from the previous Fitter cycle, it now bumps `held_cycles` and updates `last_seen_at` rather than appending a duplicate row. A `last_evaluated_at` top-level field surfaces the latest run time even when no entry was appended. After 7 consecutive cycles with the same recommendation, the entry becomes eligible to weigh into the next walk-forward read.
* **Backlog reframed by C1-axis vs bias-correction (v0.6.148).** Stage-1 hypothesis backlog section in `corrections_debug.html` regrouped into A (C1 multi-axis confidence extension), B (bias candidates, paced), C (lower priority — dominated by existing layers). Framing: most candidates fold into C1 as orthogonal confidence axes, not standalone correction layers. Two real bias candidates remain (marine layer, cloud-ceiling regime), both with overlap risk vs L2/L4 that needs to be ruled out before scoping a script.
* **Debug page maintenance (v0.6.152, v0.6.155, v0.6.156, v0.6.157).** v0.6.152 full sync after the v0.6.151 L6 v2 ship. v0.6.155 documented v0.6.153/154's current-sync + L2 cloud blend + 5-band + gust fixes. v0.6.156 + v0.6.157 stripped narrative changelog-style language from the Status panel, L2 header, R6, and R2 sections — page is for the math, not the deploy log.

</details>


<details>
<summary><strong>v0.6.134–v0.6.146 • June 19, 2026</strong></summary>

L6 confidence-layer Stages 3 + 4a shipped gated, KBVY METAR cloud added to joiner truth, mesonet dead-station cull.

* **L6 confidence layer — Stage 3 wiring (v0.6.141) + Stage 4a dormant briefing line (v0.6.142).** The Stage 1 calibration table from 06-19 morning gets wired into the collector. Every tick, `confidence_layer.py` classifies the current observed regime, compares to the model's predicted regime, looks up the matching (field, band) cell in `l6_confidence_curated.json`, and stamps `weather_data["confidence"]` with per-(field, band) `stable_mae`, `transition_mae`, `displayed_mae`, and `direction`. `ENABLED=False` — the layer is gated until the Stage 3.5 calibration audit (gated 06-26) confirms displayed bands contain truth at the claimed rate. Stage 4a adds a dormant briefing status line in `js/briefing.js` that reads `data.confidence.applied`; renders nothing while `applied=False` so it's safe to ship gated.
* **KBVY METAR cloud obs blended with KBOS for joiner truth (v0.6.134).** New `fetch_kbvy_obs` parses cloud cover + L/M/H splits from KBVY's METAR `clouds[]` array. `daily_extremes.py:_gather_current_observation` replaces the KBOS-only cloud read with a mean-of-two blend. Goal: cleaner truth signal for the cc/cl walk-forward validator — single-source obs at 12mi was too noisy to beat the 3% L3 threshold. The walk-forward read with 7+ days of dual-source data is gated to 06-26.
* **Briefing prompt + validator rewrite (v0.6.136, v0.6.137, v0.6.140).** v0.6.136 split the headline-vs-now check from the sub-vs-forecast-trend check; the previous combined-text matcher was rejecting valid sub language ("clearing overnight") whenever the present-now cloud_cover contradicted the trend. v0.6.137 banned generic sky labels ("Partly Cloudy," "Mostly Sunny") as standalone headlines while still allowing trend verbs ("clearing," "brightening"). v0.6.140 hardened the Groq waterfall: `response_format=json_object` forces JSON-only output (guards against "empty content" failure), `reasoning_effort=low` for gpt-oss reduces latency without quality loss, and the 4h 429-cooldown is now gated on `GEMINI_ENABLED` so it doesn't lock Groq out when Gemini is disabled.
* **Dead-station cull + per-station humidity denylist (v0.6.144, v0.6.145).** v0.6.144 removed 5 WU stations showing 0% uptime over the trailing 30 days. v0.6.145 added a per-station field-level denylist for stations with broken humidity sensors but valid temp/wind/pressure — KMASALEM15 and KMAMARBL87 specifically. Their humidity readings were tripping the MAD outlier trim but the trim-after-fetch was wasteful. The denylist skips the bad field at collection time.
* **Debug page surfacing for new layers (v0.6.143, v0.6.146, v0.6.138).** v0.6.143 added the L6 confidence-layer status section (gated badge, per-(field, band) bands, calibration audit date). v0.6.146 synced the curated date stamp + station network count after the cull. v0.6.138 refreshed the Status section with KBVY cloud obs + the 06-26 walk-forward gate.

</details>


<details>
<summary><strong>v0.6.133 • June 18, 2026</strong></summary>

- **Validator rain-word check now headline-only.** `_validate_headline()` in `weather_collector/fetchers/briefing_ai.py` was rejecting valid headlines whose subheadlines mentioned rain in negation ("no rain expected," "clearing — rain stays south"). Caught 2026-06-18 21:17 when Groq Llama produced the entirely correct headline "Clearing Tonight" — but its sub said "no rain expected" and the combined-text rain-word search tripped a rejection. Same false positive killed the cached-headline rescue. Whole chain collapsed to the deterministic template ("Mostly Clear at the cove / Currently 65°F, high upper 70s"). New helper `has_headline_word()` runs the rain check against the headline only; cloud and intensity checks (#2, #3) still use combined text where breadth helps.
- **Gemini disabled — Groq waterfall is primary.** New module-level flag `GEMINI_ENABLED = False`. Gates the entire Gemini try-block in `generate_briefing()`. The new free-tier project (rotated this morning to `WymanCoveWeather20260618`) gets exhausted by mid-evening — 20 requests/day cap is too tight for our 10-min tick cadence even with the 30-min briefing throttle. Every tick after the cap hit was 429ing, then waterfalling to Groq anyway. Skipping Gemini straight to Groq saves ~5s of wasted retry per tick and stops cluttering the logs with quota errors. The 30-min briefing throttle is unchanged — it's a UX choice ("don't churn the headline every 10 min"), now applied to Groq directly. Flag flipped back to True once we either pay for a Gemini tier or stretch the throttle past 20/day.



## v0.6.132 • June 18, 2026

- **Precip prompt-gate tightened — was leaking 20% POP / 0.0" rain as "rain in play."** `_build_weather_summary()` in `weather_collector/fetchers/briefing_ai.py` used to enter the "Precip: …" branch whenever any hour in the next 48h had POP ≥ 20%, regardless of accumulation. Today's 21:17 Gemini briefing hit that path with max_pop=20% and 0.0" total — prompt said "Precip: max 20% POP, 0.0\" total" with no intensity word, and Gemini still hallucinated "Heavy rain, fog likely overnight" off it (the Sky & Precip card correctly showed dry). New gate requires BOTH `max_pop ≥ 30` AND `rain_inches ≥ 0.05` before the prompt mentions rain at all; otherwise the prompt explicitly says "No significant rain expected next 48h — do NOT mention rain," which also wires the validator's contradiction check back on. `precip_arr`/`rain_inches` lifted above the gate so the new condition can see them.
- **NWS alerts get the headline; forecast stays in the sub.** New `SYSTEM_PROMPT` rule: when the prompt's `Alerts:` line shows one or more active NWS alerts, the model MUST write the headline as `"NWS <Alert Name> in effect"` and nothing else (most severe alert only if multiple). The subheadline then carries the normal forecast. Triggered by today's "Thunderstorms heading our way tonight" headline produced when a regional Severe Thunderstorm Watch was active but our local CAPE/lightning detector was clear ("No Risk"). The watch covered our point per NWS but didn't reflect actual local risk; the model led with thunderstorms anyway because it saw the alert event name in the prompt with no instruction on how to handle it. New rule separates "what NWS is saying" (headline) from "what we forecast for the cove" (sub), and avoids the model conflating regional watches with local conditions.
- **Frontal-context prompt — stop the "fronted" coinage.** GPT-OSS-120B took the loose phrasing "feel free to name it as such" in the frontal-context line of `_build_weather_summary()` and verbed the noun, producing headlines like "Fronted fog and rain chance linger tonight." Replaced the open-ended instruction in `weather_collector/fetchers/briefing_ai.py:309` with explicit allowed phrasings ("after the cold front," "behind the cold front," "the cold front brought…") plus an explicit ban on using "front" as a verb. Gemini and Llama-3.3 didn't make this mistake; GPT-OSS-120B (now first in the Groq waterfall) did.



## v0.6.131 • June 18, 2026

- **Stale-rescue briefings now visually distinguished.** When `generate_briefing()` falls through to the "last-good cached" branch because every live LLM tier failed or was validator-rejected this tick, the returned briefing now carries `stale: True`. `briefing_ai.py:732` updated. Sources drawer (`js/sources.js`) reads the flag and renders the `(active)` chip as amber `(stale rescue)` instead of green `(active)` — same color language we use elsewhere for degraded but non-failing state. Without this, the displayed briefing read as a normal `gemini` headline that happened to be aging within the throttle window, hiding the fact that the live pipeline had silently fallen back to a previous-tick cache. Now you can see at a glance whether the headline on screen is a fresh Gemini/Groq output that just hasn't been refreshed yet (green, normal throttle) versus a stale rescue (amber, two LLM tiers below failed and we're serving whatever the last good run produced).



## v0.6.130 • June 18, 2026

- **Briefing fallback chain overhauled.** Three changes to `weather_collector/fetchers/briefing_ai.py`. (1) The single hard-coded `GROQ_MODEL = "llama-3.3-70b-versatile"` becomes a two-tier waterfall `GROQ_MODELS = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"]` — when Gemini fails, GPT-OSS-120B writes the briefing; if it also fails (rare), Llama-3.3 catches it. Both models live on Groq with the same `GROQ_API_KEY`, so voice stays within one provider's family across the intra-fallback. Selection driven by `analysis/briefing_bakeoff.py` — GPT-OSS-120B produced the most atmospheric, sea-breeze-aware briefings of the eight contenders tested. (2) `temperature` bumped 0.5 → 0.85 (named `GROQ_TEMPERATURE`). The 0.5 was the dominant cause of stilted Groq prose; same model at 0.85 reads markedly better. (3) `max_tokens` bumped 256 → 600 so longer subheadlines aren't truncated mid-sentence. New helper `_call_groq_waterfall` iterates the models and logs each tried; cache write goes through the existing atomic `_update_briefing_cache`. Briefing cache `model` field now stamped as `groq/<model-id>` so the debug page can show which Groq tier actually served.
- **Prompt rule: no specific precip amounts for light/moderate rain.** Added to `SYSTEM_PROMPT`: "Never cite specific precipitation amounts in inches (e.g., '0.1 inches', 'a tenth of an inch') for light, brief, or moderate rain. Use qualitative descriptors: 'a quick shower,' 'light rain,' 'brief drizzle,' 'scattered showers,' 'moderate rain.' Only cite a specific amount when the data line shows ≥0.5 inches total — and even then, prefer rounded language ('about an inch,' 'over half an inch') to decimals." Verified post-change in the bake-off — GPT-OSS-120B no longer says "a moderate 0.1″ shower could start"; produces "a front will bring moderate rain in about two hours" instead.
- **Sources drawer surfaces the specific Groq model when serving.** `js/sources.js` updated for the new `briefing.model` shape (`"gemini"` or `"groq/<model-id>"`). The Gemini row's static label becomes `"Gemini 2.5 Flash-Lite"` (was just `"Gemini 2.5 Flash"`); the Groq row's static label becomes `"Groq"` with the waterfall in the description. When the Groq layer is active, the `(active)` tag is annotated with the actual serving model — e.g. `(active: openai/gpt-oss-120b)` or `(active: llama-3.3-70b-versatile)` — so you can confirm at a glance which tier of the waterfall actually produced the briefing on screen. The standby/active matching now uses provider prefix (`startsWith("groq/")`) so the new compound model id maps cleanly to the existing `groq` row.
- **Bake-off harness shipped at `analysis/briefing_bakeoff.py`.** Runs from the Mac, NOT deployed. Calls a list of `(provider, model, temperature)` configs against the current live `weather_data.json` (same `SYSTEM_PROMPT` and `_build_weather_summary` as production), prints headline + subheadline side-by-side for eyeball comparison. Currently sweeps Groq + OpenRouter free routes; Gemini omitted by default to avoid burning the live quota during testing. Re-run any time we want to revisit model choice — model lineups churn (today's run flagged 3 Groq decommissioning errors and 2 OpenRouter free routes retired). New secret `openrouter-api-key` in Secret Manager for the OpenRouter calls.



## v0.6.129 • June 18, 2026

- **Briefing sanity check: word-boundary matching to stop falsely rejecting "clearing" as "clear".** The `_validate_headline` substring test (`"clear" in combined`) treated "skies clearing overnight" as a "clear/sunny" claim, then rejected the headline whenever cloud cover was ≥75%. Caught today after two false rejections fell through to a 4h-old cached headline: Gemini 09:37 ("Light rain moving in this afternoon.") and Groq 12:17 ("Cloudy with Evening Rain") — both had subs mentioning "clearing." Replaced raw `in` checks with a `re.search(rf"\b{word}\b", combined)` helper applied to all three rules (precip contradiction, sky contradiction, intensity words). Validator stays conservative — only flags actual word hits, not substrings inside unrelated words.



## v0.6.128 • June 18, 2026

- **Briefing cache: collapse the two-write success path into one atomic update.** v0.6.113 (yesterday) split a single read-modify-write on `briefing_cache.json` into two sequential calls — `_save_cached_briefing` (briefing fields) and the new `_record_gemini_attempt` (throttle timestamps). On the Gemini-success path both ran back-to-back; the cache file ended up with a fresh `last_attempt_at` but the **old** briefing (still the previous Groq from 05:37 ET this morning), as if only the second write took effect. GCS metageneration confirmed a single object version per tick, ruling out a simple overwrite race — but whatever the underlying cause (silent exception in the first write, GCS client buffering quirk, JSON serialization edge case), the symptom was reproducible: every Gemini success returned a fresh `model:gemini` briefing in `weather_data.json` but failed to persist to the cache, so for the 20-min throttle window after every successful tick the user saw the stale Groq headline instead of the just-generated Gemini one. Fix: collapse to a single `_update_briefing_cache(briefing=None, was_429=False)` doing one read-modify-write — overlay briefing fields when provided, always bump `last_attempt_at`, optionally set `last_429_at`. All four call sites in `generate_briefing` updated. Eliminates the race regardless of root cause.



## v0.6.127 • June 18, 2026

- **Briefing: switch Gemini auth from URL `?key=` to `x-goog-api-key` header.** Two days of intermittent 429s ("You exceeded your current quota") with no visible quota dimension — the log truncated the error body at 300 chars, right before the `violations` block that names which quota. Diagnostic from local shell: ten back-to-back calls using the **same key** (`gcloud secrets versions access latest --secret=gemini-api-key`) and the **same model** (`gemini-2.5-flash-lite`) returned 9× HTTP 200 + 1× transient 503, no 429s. The only material difference between the working calls and the function's failing calls was the auth form: header vs URL query string. The URL form is a long-deprecated path on `generativelanguage.googleapis.com/v1beta` and accounts to a different quota lane. Switched both the initial call and the 5xx retry in `briefing_ai.py` to use `requests.post(GEMINI_URL, headers={"x-goog-api-key": ..., "Content-Type": "application/json"}, ...)`. Side benefit: the key no longer appears in any URL that could be logged. Also bumped the failure-body log truncation from `body[:300]` to `body[:2000]` so the next 429 (if any) shows the full quota dimension instead of being cut off at "Quota ex…".



## v0.6.126 • June 18, 2026

* **Briefing: switch to `gemini-2.5-flash-lite` + stop retrying on 429.** Two changes to `briefing_ai.py`. (1) `GEMINI_MODEL` default reverts from `gemini-2.5-flash` (set in v0.5.146 because flash-lite was returning 503 — it has since GA'd) to `gemini-2.5-flash-lite`. Free-tier daily limit jumps from 250 RPD to 1000 RPD — 4× the headroom for our 144 calls/day pattern. (2) The inner Gemini retry loop (around line 607) no longer retries on 429. 429 means "you exceeded quota"; retrying the same key 5 seconds later just burns ANOTHER request from the quota that just rejected us. Pre-fix, every rate-limited tick was double-counted — the multiplicative explanation for why we hit the daily ceiling fast. 5xx (transient capacity) still retries once with 5s sleep, since those clear quickly.



## v0.6.125 • June 18, 2026

* **L3 whitelist: cm added.** 7-window MAE audit across 06-12 to 06-18 (42k–53k pairs per window) shows cm-in-L3 beats cm-not-in-L3 by **+2.5% to +6.5% in every window**, unanimous. Production whitelist is now `L3 = {ws, wg, ch, cm, pp}`. Updated `weather_collector/processors/decay_apply.py:L3_FIELDS` and `backtest/run.py:NAMED_CONFIGS["production"]` to match. Debug page status panel + B1 backtest sweep description updated accordingly.



## v0.6.124 • June 18, 2026

* **R6 promoted to Stage 2 (auto-wired) + R5 retired from Stage 2 (stripped).** Backend swap in `weather_collector/processors/decay_fit.py`: the old R5 accumulator setup (cove-conditions map load + per-pair scoring + verdict computation) and its `conditional_audits.r5` write are gone; R6 takes its place. R6's per-pair classifier reads `state_fc.regime_synoptic` and `state_obs.regime_synoptic` from the pair, buckets sum-of-abs-error by (field, lead_band, is_transition). Verdict counts (field, band) buckets where transition MAE exceeds stable MAE by ≥10% with both sides ≥200 pairs; SHIP if ≥10 buckets, HOLD otherwise. Same shape as the standalone `analysis/regime_transition_audit.py`. Verdict written under `conditional_audits.r6` for the S1 renderer.
* **Debug-page S1 renderer updated.** R5 row + history column removed; R6 row + history column added. The R6 row shows the verdict, flagged-buckets count, worst (field, band, penalty %), and total pair count. R6's "match rate" line explains the quirk that a match here means verdict=HOLD until L6 is built (no production layer to compare against yet).
* **Status panel + R6 section + G1 prose updated** to reflect Stage 2 status: "Promotion candidate" card became "Stage 2 — auto-wired audits" listing L5 + R6. The "Pending decision" card now says verify on next Fitter cycle.
* **Verification:** next Fitter cycle (~07:xx or 19:xx UTC) should produce a `shadow_whitelist_log.json` entry with `conditional_audits.r6` populated and no `conditional_audits.r5`. Watch for the S1 section rendering an "R6 regime-transition (audit only): ..." row.



## v0.6.123 • June 18, 2026

* **Research & Diagnostics section reorder + new Operational tools subheader.** Joe's catch — when the Retired wrapper was expanded, G1/S1/B1/F1 appeared right after it with no subheader, so they visually bled into looking retired. Two fixes: (1) added an "Operational tools — live audits & shadow tracking" subheader before G1; (2) reordered so the narrative is Diagnostics → Active hypotheses → Operational tools → Retired. Retired is now unambiguously the last block on the page; everything above it is alive.



## v0.6.122 • June 18, 2026

* **Retired section: wrap in a single collapsed details block.** Joe's catch — "in what way is the shadow whitelist tuner retired?" The previous h3 header had no visual closing marker, so G1 / S1 / B1 / F1 (which are all live) looked like they were still inside the Retired section. Fix: wrapped the entire Retired block in one outer `<details>` that's collapsed by default. When collapsed it's a single line; the boundary is unambiguous and everything below is obviously NOT retired.



## v0.6.121 • June 18, 2026

* **Retired section: tag each entry by kind.** Joe's catch — "Retired hypotheses" was hiding the fact that not every entry under it was actually a hypothesis. Renamed the header to "Retired — hypotheses ruled out & settled tunings" and tagged every entry: `[HYPOTHESIS]` for things we tested and the data answered no (tide-phase, derived humidity, R4, R5), `[SETTLED TUNING]` for parameter sweeps that concluded "current value is fine" (τ-tuning). Folded the tide-timeseries entry into the tide-phase entry as a "companion view" sub-details — they were two views of the same retired hypothesis, not separate items.



## v0.6.120 • June 18, 2026

* **Debug-page taxonomy cleanup.** R1 → D1 (drill-down isn't a research hypothesis; it's a teaching/demo view). Status panel convention key gains `D = drill-down / teaching view` and `B = backtest`. The duplicate "Discarded hypotheses" section is merged into the single "Retired hypotheses" header at the top of Research & Diagnostics — the four 06-08 retired items (tide-phase, tide-timeseries, derived humidity, τ-tuning) now sit alongside R4 and R5 under one consolidated header. No more "Discarded vs Retired" word collision — one canonical place for things that were tested, settled, and removed. R3a/b/c/d losing the R prefix since they were never research-hypothesis-numbered in the new taxonomy.



## v0.6.119 • June 18, 2026

* **Headline box moved above the Status panel.** "Right now — what the pipeline is doing" is the live, fresh data you actually check daily (current temp correction, humidity correction, confidence, briefing source). It now sits at the top of the page where it belongs. The curated Status panel is still right below, collapsed-or-not at your discretion.



## v0.6.118 • June 18, 2026

* **Status panel is now collapsible.** Wrapped the Status — where we are panel in `<details open>` so it matches the rest of the page's collapsible sections. Click the header to fold it away once you've absorbed the current state; expand it again when something looks off elsewhere and you want to re-check what's pending.



## v0.6.117 • June 18, 2026

* **Promotion-gate simulator + four hypothesis status changes.** New `analysis/simulate_windows.py` runs L5 / R5 / R6 verdicts across 7 trailing daily cutoffs (each on a 7-day window) in a single pair-log pass. The promotion rule: a hypothesis only earns Stage 1 → Stage 2 (or Stage 2 → Stage 3) advancement if all 7 cutoffs return the same verdict. Any flicker = stay put.
* **L5 — FLICKER (stays Stage 2, do not flip ENABLED).** Sequence: HOLD HOLD HOLD HOLD HOLD SHIP SHIP. Cause: L5 lookup tables were refit 2026-06-17 in v0.6.112; first 5 windows scored against OLD tables, last 2 against NEW. Need 7 consecutive SHIP under post-refit tables before promoting to Stage 3 — eligible ~2026-06-24 if stable. Until then, ENABLED stays False.
* **R5 — RETIRED.** Standalone audit at 32,816 pairs returned HOLD at −20.58% MAE. L2's waterfront-weighted station blend already captures the cove signal; R5 double-counts. Status panel + R5 section updated to RETIRED. Stage 2 wiring stays in `decay_fit.py` until the next collector deploy strips it (queued).
* **R4 — RETIRED.** Standalone audit at 112,877 joined pairs returned CLOSE; max |ρ|=0.012 across all fields. HRRR vs GFS spread doesn't correlate with forecast error. R4 was Stage 1 only (no decay_fit.py wiring), so retirement is just the debug-page move.
* **R6 — PROMOTION CANDIDATE.** Passed the gate 7/7 cutoffs SHIP, with 19–32 flagged (field × lead band) buckets per window. Queued to auto-wire into `decay_fit.py` on the next collector deploy. Once Stage 2 verdicts agree for 7+ days under shipped wiring, design L6 (transition-aware confidence band or per-field L1 fallback during predicted regime changes).
* **Debug page additions:** new "Retired hypotheses" section header with R4 + R5 collapsed under it; new "Promotion candidate" + "Retired" cards on the Status panel; R6 section updated with the gate-passed banner; G1 description updated to reflect L5 FLICKER + R5 retired; "Pending decision" card lists the next collector deploy as the operational next step.

</details>


<details>
<summary><strong>v0.6.116 • June 17, 2026</strong></summary>

* **R6 hypothesis: regime-transition penalty.** New analysis script `analysis/regime_transition_audit.py` classifies each pair as "stable" (state_fc.regime_synoptic == state_obs.regime_synoptic) or "transition" (regimes disagree — model expected A, B materialized) and reports MAE per (field, lead band, classification). First read on 134k pairs strongly confirms the hypothesis: 25 of 56 buckets show ≥10% transition penalty with rock-solid sample sizes. Strongest effects: wind speed +73% at 0-5h, wind direction +45–72% across all bands, wind gust +63% at 0-5h, temperature +12–24% at short-to-mid leads. ~40% of pairs are "transition" pairs — not a rare edge case. **Decision rule:** re-confirm 2026-06-22. If it holds, design transition-aware confidence bands or per-field L1 fallback during predicted transitions as L6. Debug page R6 section + status panel updated to reflect the first-read verdict and the 06-22 re-run gate.



## v0.6.115 • June 17, 2026

* **Debug page print stylesheet: consistent light treatment.** Printing `corrections_debug.html` to PDF produced a mixed result — sections styled by CSS classes (already covered by the existing `@media print` block) printed light, but sections with inline `style="background:#..."` (the new status panel cards, the headline box, the per-chart verdict boxes) kept their dark fills. Looked broken. Added attribute-selector overrides under `@media print` that catch any inline hex background in the dark-theme range (`#1xxxxx`, `#2xxxxx`, `#3xxxxx`) and force it to white with dark text. Status-panel card headings keep their colored accent (green/amber/yellow/purple) so the four cards remain visually distinct without backgrounds. Field-state badges (`L2 ✓`, `L3 off`, etc.) get light backgrounds with semantic colors. Band-table active-column shading switches to a light green tint instead of the dark green. Headline box stat cards print white.



## v0.6.114 • June 17, 2026

* **Debug page gets a curated status panel at the top.** New "Status — where we are" section above the headline box, with four cards: Shipped & live, Gated off, Pending decision (dated), and Live hypotheses. Includes a "How to read the rest of this page" pointer paragraph and a prefix convention key (L = applied layer, R = research hypothesis, S = shadow tuner, G = guardrail, F = failure diagnostic). Hand-curated with a "Last curated: YYYY-MM-DD" stamp so a third-party reviewer can tell how stale the curation is. The rest of the page is automatic; this panel is not. Reason: the page now shows accurate state but doesn't tell a story — a smart outside reviewer can see the charts and numbers but can't piece together which hypotheses are alive vs gated vs dead. This panel fixes that without changing any of the auto-rendered sections below.



## v0.6.113 • June 17, 2026

* **Briefing rate-limit retry loop fixed.** Symptom caught today: Gemini hit its daily quota at 04:37 UTC and we then retried every 10 minutes for **12 hours straight**, each call burning more quota and getting 429'd. Two causes: (1) the 30-min throttle was keyed on `cached_at` (last successful response) — when Gemini fails, `cached_at` stays stale and the throttle never fires. (2) The in-memory failure flag `_last_gemini_call_time` survives only within a single Cloud Run instance; new instances reset it to None and retry immediately. Fix: persist `last_attempt_at` to `briefing_cache.json` on every Gemini attempt (success OR failure), via a new `_record_gemini_attempt()` helper that writes a thin update without disturbing the cached headline. The throttle now respects any-attempt, not just success. Additionally: on HTTP 429 specifically, set `last_429_at` and apply a 4-hour cooldown (well past Google's daily-quota midnight-Pacific reset) instead of retrying every 10 min.
* **Groq fallback now updates the displayed briefing.** Pre-v0.6.113, the cache was "reserved for last-good Gemini" — when Gemini was down, Groq returned a fresh briefing each tick but the GCS cache stayed at the last Gemini value, so the displayed briefing was hours stale. Today users saw a "Calm harbor, then sea breeze kicks in" headline from 11:27 EDT for 5+ hours. Fix: when Groq succeeds and passes validation, save it to the cache too. Gemini's next success overwrites with the higher-quality output. Users get the freshest available briefing instead of stale-Gemini-from-this-morning.



## v0.6.112 • June 17, 2026

* **L5 lookup refit on 7-day window.** Re-ran `analysis/l5_recompute_biases_hourly.py --days 7` to produce fresh `_BIAS_FALLBACK_BY_REGIME` and `_BIAS_BY_REGIME_HOUR` lookup tables in `solar_correction.py`. Updated values reflect the most recent 7 days of pair-log data (vs the original snapshot taken on day-15). Audit re-run confirms substantial improvement: realistic-view overall MAE went from −14.9% (pre-refit) to **−19.3% improvement** vs baseline, and ceiling view from −11.6% to **−33.4%**. Both views still SHIP. Six of eight regimes show ≥3% individual improvement on realistic view (threshold is ≥5).
* **L5 audit wired into the shadow tuner (Phase B for L5).** Mirrors the v0.6.110 R5 wiring. Added solar audit accumulators to `decay_fit.py`'s existing pair-stream loop — no second GCS read. For each solar pair (lead ≥ 1, `forecast_l1 ≥ SUN_UP_THRESHOLD`, state metadata present), accumulates baseline `|error_l4|` and `|error_l4 + L5_delta|` per (regime_fc, band). After the main loop, computes a verdict using the same thresholds as `analysis/l5_solar_analysis.py` (≥5% overall, ≥5/8 regimes improving by ≥3%). Passes the verdict to `log_shadow_recommendation()` under `conditional_audits["l5"]`. First populated log entry writes at the next 03:xx local Fitter cycle.
* **Debug page S1 surfaces both R5 and L5 audits.** Latest-recommendation table gets an L5 row with verdict + improvement % + regimes-winning count. Agreement panel adds "L5 match rate" line. History table grows an "L5 audit" column when any entry has L5 audit data. All conditional layers are tracked the same way — adding R6 / L6 / etc. later is a one-line shadow tuner addition + matching debug-page helper.
* **`l5_recompute_biases_hourly.py` migrated to the cache.** Was still using the legacy direct `urllib.request.urlopen` pattern; now uses `_cache.py` like the rest of `analysis/`. Refits with `--days 7` now reuse the cached pair log (no extra egress charge per re-run).



## v0.6.111 • June 17, 2026

* **Drop `cm` from L3 whitelist.** Two independent held-out methods agree it should come out: walk-forward L3/L4 validator re-run on 2026-06-15 recommended dropping cm from L3, and B1 backtest sweep on 2026-06-16 (173k pairs over 2 days) confirmed cm out of L3 improves cloud-mid MAE by ~3.8% vs production. The hard rule for whitelist changes is "two consecutive re-runs agree" — that bar is met. `L3_FIELDS = {"ws", "wg", "ch", "pp"}` going forward. `backtest/run.py` named-config "production" updated to match so future sweeps compare against the new live state. Debug page B1 section text updated to reflect the new whitelist. Verified post-deploy: 12:27 UTC tick shows `decay_meta.layer_3_fields = ["ch", "pp", "wg", "ws"]`. No change to L4 (`{ch}`) — walk-forward says clear L4, but sweep refuted that (clearing L4 would lose 12.2% on ch), so L4 stays as-is pending the Monday 06-22 walk-forward re-run that resolves the conflict.
* **L5 solar audit extended to do Step 2 (held-out MAE).** `analysis/l5_solar_analysis.py` rewritten to compute both "realistic" (uses `state_fc.regime_synoptic` — the regime the model predicted at lead time, which is what production would key on) and "ceiling" (uses `state_obs.regime_synoptic` — theoretical best case) views in one tool. Same step-1+step-2 separation as R5, applied preemptively per the lesson from yesterday. **Verdict on current data: HOLD by a wide margin.** Overall MAE goes from 163 W/m² baseline → 172 W/m² with L5 applied (−5.6%, significantly WORSE). Per-regime: only 3/8 regimes show improvement; nw_flow (−23.6%) and calm (−16.1%) are the worst losers. Step 1 reported a 31.6% drop, 7/8 regimes — both methods can't be right; the Step 2 view (using model-predicted regime, like production would) is the honest one. L5 stays gated off through 06-22 and likely beyond unless the lookup is refined. Confirms the value of the audit pattern: without this check we would have shipped a measurable regression on Monday.



## v0.6.110 • June 17, 2026

* **Shadow tuner extended to cover conditional layers (R5 today, L5+ later).** Three changes that together make the shadow tracker a general "watch every layer's ship/don't-ship decision over months" instead of only L3/L4 whitelists.
  * **R5 audit runs every Fitter cycle in production.** Added cove-conditions lookup at the start of `fit_decay_corrections()` and per-pair R5 accumulators in the existing pair-stream loop — no second GCS read. For each temperature pair with cove conditions matching its obs hour, accumulates baseline `|error_l4|`, `|error_l4 + R5_delta|`, `|error_l1 + R5_delta|` per (sb_active, band) bucket. After the main loop, computes a verdict (SHIP / HOLD / insufficient_data) using the same 1% MAE threshold + 200-pair minimum as `analysis/r5_audit.py`. Passes the verdict to `log_shadow_recommendation()`. First populated log entry writes at the next 03:xx local Fitter cycle (~07:xx UTC).
  * **Shadow log schema generalized.** `log_shadow_recommendation()` now takes an optional `conditional_audits` dict mapping layer name → `{verdict, enabled, mae_baseline, mae_with_layer, improvement_pct, n_pairs, best_variant}`. R5 uses it today; L5/L6/etc. plug in with the same shape without further changes to this function. Dedup logic extended to consider verdict changes meaningful: a HOLD→SHIP flip on R5 generates a new log entry even if L3/L4 didn't change.
  * **Cascade constraint removed.** Old `shadow_whitelist._recommend()` gated L4 consideration on L3 being recommended ("only consider L4 if L3 is in"). But L4 is fit on `error_l3` which equals `error_l2` by construction when L3 is off — so L4 ON without L3 is architecturally valid (L4 fits on the L2 residual). Removing the gate lets the shadow surface "bad L3, good L4" cases for fields where the diurnal signal is real but the per-lead bias signal isn't. No behavior change for fields where L3 already helps.
* **Debug page S1 section surfaces R5 audit alongside L3/L4.** Latest recommendation table gets a new R5 row showing the verdict (SHIP/HOLD/insufficient), with detail line including both R5-on-top-of-L4 and R5-alone improvement percentages plus pair count. Agreement panel gets a new "R5 match rate" line — match here means the audit verdict aligns with the current ENABLED state (HOLD + disabled = match; SHIP + enabled = match). History table grows a new "R5 audit" column when any history entry has R5 audit data. Same shadow pattern, three layers tracked at once.

</details>


<details>
<summary><strong>v0.6.103–v0.6.109 • June 16, 2026</strong></summary>

* **Debug page R5 section + G1 card reflect the Step 2 audit verdict.** The R5 section text and the G1 candidate card were both written when R5 was on a "ship Friday if regime tests pass" trajectory. Today's Step 2 audit (n=29,444 matched pairs) concluded HOLD — applying R5 makes cove forecasts ~20% worse because L2's station weighting already captures the waterfront signal. Updated the R5 section to lay out the two-step plan (Step 1 = measurement stable, Step 2 = held-out MAE audit) and show a red-bordered Step 2 verdict box with the actual numbers, the L2-overlap explanation, the long-lead-sea-breeze niche subtlety, and the decision that ENABLED stays False. Updated the G1 R5 card to add an "audit: HOLD" badge, drop wind direction from the inactive-regime display (the code ignores it at inactive), and add a footer making explicit that the lookup value is NOT a prediction of forecast change — it's a diagnostic of the underlying physical pattern. G1 description now flags that L5 should also get its own held-out audit before shipping (lesson learned from R5).

* **Debug page consolidated.** Promoted `accuracy_debug.html` (the v0.6.107 v2 work) into `corrections_debug.html` so there's one canonical debug page going forward, not two files differing in one section. All v2 improvements (per-chart whitelist badges, lead-band MAE summary tables, single-column "this is the final answer" box on the rightmost active column, expanded plain-language explainer, renamed "Decay"→"Lead-time decay" / "Diurnal"→"Hour of day", shadow-whitelist agreement-rate panel + uncapped history + local-time formatting) now live in the main debug page. `accuracy_debug.html` removed; both existing links in the app (`index.html` Settings modal "Forecast Pipeline (live) ↗" and `js/corrections.js` corrections card footer "why →") still point at `corrections_debug.html` and pick up the v2 layout automatically. No more two-files-to-maintain.
* **R5 Step 2 — held-out MAE audit, verdict: HOLD.** New `analysis/r5_audit.py` runs the actual ship question for R5: does applying the cove correction improve forecast accuracy on held-out pairs? Streams the pair log + cove gradient log, joins by obs-hour, scores three configs on n=29,444 matched temperature pairs (baseline = existing L4-corrected, R5 added on top of L4, R5 replacing the stack). Result: **baseline 2.547°F MAE, R5+L4 3.045°F (−19.6%), R5 alone 3.066°F (−20.4%) — both R5 variants make things significantly worse.** The L2-overlap hypothesis is empirically confirmed: L2's per-station 1/d² weighting already pulls the cove forecast toward the waterfront Tempests, so layering R5's (waterfront−inland) delta on top double-counts the signal. One subtle win: long-lead (24-47h) sea-breeze forecasts get +7.85% with R5 because L2's τ=4h decay has long since faded by 24h. Net: don't flip `cove_correction.ENABLED = True` on Friday. R5 stays as a confirmed-physical-finding diagnostic per Path 3 of the two-step plan.

* **New debug page: `accuracy_debug.html`.** A second-pass version of `corrections_debug.html` focused on the Forecast Accuracy section's comprehension. Same data, same charts, three additions targeted at "smart visitor walks up and understands what's happening": (a) per-chart whitelist badges in each card header showing `L2 ✓ additive · L3 ✓ · L4 off` with ✓ on active layers and the L2 variant labeled (additive/direct/n/a/Brier); (b) lead-band MAE summary table beneath each chart, 5 rows (0-5h, 6-11h, 12-23h, 24-47h, ALL) × 4 columns (Raw, Mesonet, Lead-time decay, Hour of day), with best/worst row coloring AND a single subtle green box around the rightmost active column (the column whose value is what the user actually sees); (c) expanded "How to read these charts" expander with one paragraph per layer in plain language, an explanation for why lines overlap (whitelist-off vs structurally-not-applicable), and a guide to reading the lead-band table. Renamed "Decay" → "Lead-time decay" and "Diurnal" → "Hour of day" in chart legends and table headers for clarity. Removed the ✓ from inside chart legend swatches (was redundant with the badges). Original `corrections_debug.html` is byte-identical with this file outside the Forecast Accuracy section. Standalone — navigate to `/accuracy_debug.html` directly when you want it.
* **Shadow whitelist tuner UI — full history + agreement rate + local-time formatting.** S1 section was misleading three ways: it labeled the dropdown "last 2 entries" suggesting the log only kept the last 2 (actually retains all entries per 60-day retention), it showed `fitted_at` as bare `2026-06-16T15:08` which got misread as UTC (it's actually America/New_York local), and it didn't surface the actual agreement-rate signal the 90-day analysis is supposed to evaluate. Fixed all three: dropdown now says "all N entries since shadow deployed" and shows the full table (uncapped); timestamps render as "Mon Jun 16, 3:08 PM EDT" with explicit timezone; new agreement-rate panel above the history shows L3 and L4 match rates as percentages ("L3 match rate: 0% (0 of 3)"). Each history row gets a new "match?" column showing `both` / `L3 only` / `L4 only` / `neither`. Lets the 90-day convergence be watched live instead of computed manually later. Same changes mirrored into `accuracy_debug.html` so the two files don't drift apart outside the Forecast Accuracy section.

* **Wind direction guardrail hardened against METAR "VRB" (v0.6.106).** The v0.6.103 wind guardrail crashed three consecutive ticks at 17:57/18:07/18:17 UTC when KBVY reported `wind_dir: "VRB"` (METAR convention for variable-direction wind in light/calm conditions). `_circular_mean` was doing `[float(d) for d in directions if d is not None]` and the list-comp raised `ValueError: could not convert string to float: 'VRB'`. Fixed by replacing the list-comp with an explicit try/except that skips any non-numeric entry — VRB now acts as "no direction signal from this source" instead of crashing the tick. Caught because Joe asked me to check; would have continued failing for hours otherwise. The pattern this exposes is documented above (declaring "healthy" after one clean tick instead of watching several).

* **L2 fitter bias-sign bug (root cause of the "degenerate" fit since v0.6.44).** While previewing the v0.6.104 train/test fitter against the cached pair log, the new code ALSO picked τ=0.5h on every field — same as before. SSE vs MAE didn't matter. Investigation: the fitter's `bias` variable was computed as `err_l1 - err_l2`, but the corrected-residual formula `err_l1 + decay × bias` requires `bias = err_l2 - err_l1` so that decay=1 yields err_l2 (full L2 applied). The sign was inverted since v0.6.44 — at any non-zero decay, the formula computed the OPPOSITE of the L2 correction, making any τ > 0.5 look worse on the held-out set. The fitter wasn't optimizing what it claimed to. The hardcoded defaults survived because they were derived from `analysis/l2_lead_decay_fit.py` which uses the correctly-signed `applied_bias = forecast_l2 - forecast_l1`. Fixed by flipping the sign. Preview verification on 1.3M-row cached pair log now produces: h τ=120h (+2.89% held-out vs default), pr τ=18h (+0.54%), t τ=4h matching default, ws/wg flat — all three fields with hardcoded defaults pass the guardrail and would be adopted.
* **L2 fitter: SSE → MAE on held-out (v0.6.105).** Same fitter, also switched the loss function from closed-form SSE (squared-error) to per-pair MAE (absolute-error). MAE matches what the loader's guardrail actually cares about (forecast error users experience) and matches the metric the hardcoded defaults were originally fit on. SSE penalizes outlier overshoots quadratically; in the original sign-correct world this still mostly agrees with MAE, but MAE is more aligned with the production loss. Per-pair iteration over the 15-element τ grid for ~70k train + ~11k test pairs per field × 5 fields is sub-second. Output schema renamed `rmse_*` → `mae_*` accordingly. The `analysis/l2_fitter_preview.py` script mirrors the live fitter logic so we can verify locally without waiting for the next 15:xx fit cycle (egress is free now — pair log comes from `~/.cache/myweather/`).

* **Wind direction consensus guardrail.** Found overnight: pipeline reported wind from E (92°) while every reliable source (KBVY METAR, KBOS, NOAA buoy 44013, 12 of 14 Tempest stations) agreed on NW (310-320°). Joe's flagpole confirmed NW. Cause: `select_observed_wind` direction selector prefers waterfront Tempests by highest gust — Neptune Rd was reading 18.3 mph + 92° (sensor likely misaligned or transiently drifting), beating Willow Rd's correct 6.3 mph + 319°. Speed had an octant-median smoothing and a WU sanity cap; direction had neither. Added a consensus guardrail: if the chosen direction is >90° off the circular mean across all reliable direction sources (KBVY + KBOS + buoy + valid Tempests, requires n≥3), reject and fall back to consensus. Stamps `current.wind_direction_guardrail = {rejected_value, rejected_source, consensus_value, consensus_n, offset_deg}` for debug visibility when it triggers. Handles transient AND chronic sensor failures the same way — no permanent station cull needed.
* **L2 τ fitter — held-out validation + per-field guardrail.** The twice-daily L2 τ fit had been silently failing for 15+ days. Every grid search collapsed to the minimum τ (0.5h) because the fit was pure in-sample (the bias is learned from the same pairs being scored, so shorter τ trivially "explains" lead 0 and skips longer leads where the bias doesn't transfer). A guard flagged the result "degenerate, starved signal" and fell back to hardcoded defaults; the warning was misleading (the SSE curves were strongly monotonic, not flat — 65% spread on wind speed), the real problem was the rigged in-sample test. Rebuilt the fitter with a proper train/test split: pairs older than the last 2 days fit τ, last 2 days score it. `l2_decay.json` now carries per-field held-out RMSE at flat / default / fitted τ, plus % improvement vs default. The loader's degenerate-string check is replaced with a per-field guardrail: adopt the fitted τ only if (a) it beat the default on held-out RMSE (≥0% improvement, ≥100 test pairs), AND (b) the fitted τ is within 0.25×–4× of the default. Otherwise fall back to that field's default. Field-by-field — one bad fit can't poison the others. The misleading log line is gone, replaced by a per-field adoption log showing fitted τ, source (fitted/default), and held-out delta. Debug-page section 2d gets a new per-field adoption table surfacing the same info live. First fitted output writes at the next scheduled fit cycle (03:xx local).
* **Analysis-script egress cleanup — local cache.** Investigating why the bucket bill stayed elevated post-soft-delete-fix: the Cloud Storage line split into 54% "Standard Storage US" ($9.18) and 46% "NA Storage Data Transfer Out" ($7.97). The storage half was the soft-delete ghost (already fixed). The egress half was every analysis script re-downloading the 935 MB pair log from Cloudflare each run — ~$0.075/run. Running R5/L5/walk-forward/τ-tuning iterations 100x in June quietly added ~$8. New `analysis/_cache.py` caches each downloaded file at `~/.cache/myweather/` for 12h by default (configurable). All 12 analysis scripts updated to read from the local cache instead of urlopen'ing directly. Set `MYWEATHER_REFRESH=1` to force a re-download. Verified end-to-end: r5_cove_analysis (175 KB) and l2_lead_decay_fit (935 MB) both run on cold-cache and warm-cache; warm-cache run goes from 3:32 → 0:11.
* **Schema additions for the new L2 behavior.** `l2_decay.json` new fields: `heldout_days`, `heldout` (per-field RMSE/improvement report), `default_taus`; `n_pairs_per_field` is now `{train, test}` instead of flat. `weather_data.l2_decay_meta` now carries `fields[field] = {tau_hours, default_tau_hours, fitted_tau_hours, source, reason, n_test, improvement_vs_default_pct, rmse_*}` plus `fitted_at`, `heldout_days`, and `guardrail` thresholds — drives the new debug-page table without needing a separate fetch.

</details>


<details>
<summary><strong>v0.6.78–v0.6.102 • June 15, 2026</strong></summary>

* **Backtest framework — Phases 2-4, surfaced on debug page.** `apply_decay_corrections(weather_data, config=None)` accepts an optional config dict that overrides L3/L4 whitelists. New `backtest/replay.py` + `run.py` CLI A/B compares per-field MAE for any enable subset against held-out pair-log data (named configs: `production`, `walkforward_15jun`, `walkforward_08jun`, `stable_core`, `l2_only`). New `backtest/sweep.py` runs N configs against one download of the log, with per-lead-band breakdown via `--by-band`. Results surface on the debug page as section **B1** — color-coded matrix vs production baseline, config-definitions accordion, "By lead band — where do the wins live?" drilldown for fields with ≥0.5% spread across configs. First populated run (727K pairs / 2 days): wind L3 confirms huge wins (ws −27%, wg −41% vs l2_only), cloud high L4 gives ~0.5% edge over L3-only.
* **R0 audit table — a full rebuild.** Renamed `L3/L4 Live?` → `L3/L4 Applied?` with Yes/No instead of ON/off, and made the `No` cells red so the "do the colors agree?" scan is instant. Added new **L2 Applied?** column (Yes for fields with an obs network, `—` for n/a). Zero deltas now render neutral gray with no arrow (was misleading green/red). Each MAE cell now shows the signed bias as dim subtext alongside (`2.75 +0.51`) — reveals "MAE flat but bias dropped" cases that MAE alone hides. Added the symmetric "disabled-but-should-be-enabled" banner mirroring the existing regression check at the same 3% threshold.
* **L3/L4 historical-fit charts — APPLIED / diagnostic badges.** Each chart header gets a green "APPLIED" pill for fields in the live whitelist, gray "diagnostic" for the rest. Diagnostic-only charts dimmed to 65% opacity so the eye lands on applied ones first.
* **POP per-layer L4 tracking — known quirk fixed.** POP was using a standalone joiner code path that only emitted a single `error` field, bypassing the per-layer (l1/l2/l3/l4) split. Refactored: added `pp` to `FIELD_MAP` with a one-line special case for binary observed (100 if precip > 0 else 0); deleted the standalone block. POP pairs now flow through the same path as everything else.
* **Frontal detector — end-to-end validation.** Detector live since 06-13 with no real fronts; new `analysis/frontal_detector_test.py` exercises four synthetic signatures (cold front, modest sea-breeze, noise, strong sea-breeze). All four pass with correct type classification. Detector confirmed end-to-end functional for the next real front.
* **Manual pair-log dedup — 4.6 GB → 819 MB instantly.** Instead of waiting 30 days for the v0.6.77 dedup to age in, downloaded the log via curl, ran a one-shot Python dedup keeping the first row per (run, lead, field, hour), uploaded the deduped 819 MB. Backup retained as `forecast_error_log_pre_dedup_backup.jsonl`. The 14:07 UTC Joiner appended to the old file mid-upload and got clobbered; rewound `forecast_error_state.json` so the next Joiner reprocessed the 10:07 EDT obs. Net win: backtest sweeps drop from ~7 min to ~5 sec, walk-forward confidence intervals become honest immediately, GCS cost drops 6× going forward. Side effect: MAE numbers shifted upward (most fields 20-30% higher under honest single-sample-per-hour vs pre-dedup 6× averaging) — expected behavior of honest stats, not a regression.
* **Station uptime — Tempest culled zombies hidden.** The 6 Tempest stations culled on 2026-06-04 were still showing on the debug page with "0% uptime, 0/183 ticks" because (1) `station_uptime._CULLED` only included WU culls and (2) per-tick pruning only runs for stations actively polled. Fixed: import `CULLED_TEMPEST_STATIONS` into the filter set; one-shot cleanup ran (16 zombies removed: 10 WU + 6 Tempest), 80 active stations remain in summary.
* **R5 cove correction — sketched + evaluation script.** New `cove_correction.py` implements the bidirectional bias from 3 days of R5 data: cove warms +1.5 to +2.1°F under active S/SE/SW sea breeze (peninsula-lee heating), cools 3-5°F at 06-10 AM under offshore/calm (morning marine cooling). Indexed by (wind_octant, sb_active, hour_local). `weather_data["cove_correction"]` stamped per tick; `ENABLED = False` (06-19 decision). New `analysis/r5_cove_analysis.py` runs the regime tests and emits SHIP/HOLD; **day-4 data already passes both thresholds.**
* **R4 first-read script + the fetcher bug it surfaced.** New `analysis/r4_spread_analysis.py` joins GFS L1 log against pair-log HRRR L1, computes Spearman ρ per (field, lead band). First test run came back with all-zero spread — discovered `fetch_hourly_gfs_7day` didn't specify `models=gfs_seamless`, so Open-Meteo defaulted to "best available" (HRRR for 0-48h). For three days `gfs_l1_log.json` had been capturing HRRR data, not GFS — spread = 0 by construction. Added `models: gfs_seamless` to the params dict. R4 first-read date shifts to **~2026-06-22** (7 days of clean data from the fix). Caught in low-pressure prep time, not at the decision point under deadline.
* **L5 solar regime correction — sketched → iterated → SHIP verdict.** R2 state-stratified analysis ranks solar `regime_synoptic` as the #1 correction opportunity across all fields. Initial `solar_correction.py` indexed by regime only, biases seeded from `state_stratified_accuracy.json` (which averaged across nighttime zeros). New `analysis/l5_solar_analysis.py` evaluation: HOLD (0.7% MAE drop, 0/8 regimes improving). Refinement #1: `l5_recompute_biases.py` recomputes from daytime-only data — multiple regimes had their bias sign flipped. Re-eval: HOLD (4.9%, just shy of 5% bar, 2/8 regimes). Refinement #2: `l5_recompute_biases_hourly.py` builds a (regime × hour_local) lookup table — bias varies massively by hour within each regime (ne_flow swings from −238 W/m² at 10:00 to +247 W/m² at 14:00 same regime). Re-eval: **SHIP — overall MAE drops 31.6%, 7/8 regimes improving by ≥3%.** 3 regimes flipped sign from hurting to helping. Per discipline, not flipping ENABLED today — wait for 06-22 confirmation. Also discovered the live stamp needed an inline regime-classifier call because `derived.state.regime_synoptic` is populated only via the Joiner for pair rows, not for the live tick.
* **Shadow whitelist tuner.** New `shadow_whitelist.py` runs after each Fitter cycle, applies the same 3%-per-band MAE + bias-no-worse rule a naive auto-tuner would use, logs recommended L3/L4 sets to `shadow_whitelist_log.json` (60-day retention, deduped on unchanged recommendation). Pure observation, no production changes. After 90+ days we can evaluate "how often does shadow agree with human choices?" — the precondition for considering automation. Initial run: shadow would add `t` and `pr` to L3, drop `pp` (its Brier blindspot — informative finding, not a bug), shift L4 from `ch` to `ws+wg`.
* **Three new debug-page sections.** **G1 Gated correction candidates** — side-by-side cards showing live R5 cove + L5 solar candidates each tick (Δ, regime context, ENABLED badge). **S1 Shadow whitelist tuner** — reads the shadow log, shows latest recommendation vs production with match/differ flags, collapsible history. **B1 Backtest sweep** — color-coded matrix as described above. All three accumulate value over time without ever touching production behavior.
* **Debug page text sweep.** Multiple passes through stale/confusing wording. R0 description rewritten for bias subtext + both banners. R2 description leads with "what this is" + "where it's pointing today" (solar dominates → why L5). R5 day-1 table replaced with day-4 numbers (5-6× larger samples, magnitudes settled lower as expected). R4 status reflects the fetcher bug + shifted date. L3/L4 paused banners dropped the version annotations (`v0.6.45`, `POP re-added v0.6.49`). L4 banner rewritten to explain WHY L4 is hard to win at. R1 drill-down: removed the "someone new" framing — only audience is Joe + Claude.

</details>


<details>
<summary><strong>v0.6.77 • June 14, 2026</strong></summary>

- **Pair-log dedup: one obs per hour, not six.** Joiner was emitting one pair per collector tick (6 per hour × N forecast snapshots × N fields) when only 1 per hour represents an independent atmospheric observation. Effect: pair counts inflated 6×, MAE comparisons unaffected (both sides equally inflated) but bootstrap-variance CIs were ~√6 ≈ 2.5× too tight. Added `last_processed_hour` watermark to `forecast_error_state.json` and a per-call `seen_hours_in_call` set; first obs of each hour wins, later ticks in same hour are skipped. Existing pair-log rows keep their 6× inflation until they age out of the 30-day retention window; new rows from now on are 1× per hour. Will unlock honest confidence intervals for any future L3 regularization or A/B work.



## v0.6.76 • June 14, 2026
- **Sunset azimuth fix — directional clouds were being sampled in the wrong direction.** Bug in `sunset_directional.py:40` had `sin_az = sin(H)` (positive) with a `+180` modulo wrap, which mirrored sunset azimuths across due south. Effect was largest near the solstices: today (2026-06-14) the code returned 239° (WSW) when actual sunset azimuth is 303° (WNW) — a 63° miss. Spring/fall sunsets near equinox had near-zero error, summer/winter were ~60° off. Fixed by using the standard formula `sin_az = -sin(H)*cos(dec)/cos(alt)` with proper sign convention; `atan2 % 360` gives the answer directly without the +180 hack. Sanity-checked across summer solstice (303° expected vs 303.1° actual), equinox (270° vs 270.3°), winter solstice (239° vs 238°), April (285° vs 284°). Implication: all prior sunset calibration data points (May 28, June 10, 11, 12) were scored against clouds in the wrong patch of sky; PW haze factor shipped in v0.6.71 was tuned against that bad data. Calibration memory updated to mark prior data points invalid. Clean calibration starts tonight.

</details>


<details>
<summary><strong>v0.6.75 • June 13, 2026</strong></summary>

- **Backtest framework — Phase 1 (snapshot collector).** New `backtest_snapshot.py` writes per-tick raw L1 forecast arrays (T, Td, H, wind, pressure, clouds 0-47h leads) plus per-station observations (Tempest, WU medians, KBVY METAR) to per-day files at `backtest_snapshots/YYYY-MM-DD.json` with 14-day retention. Phase 1 is record-only — replay runner comes in phase 3. Foundational record so that any future correction-stack tuning idea (L3 regularization, L5 design, Kalman gain re-tuning, τ sweeps) can be tested in minutes by replaying historical ticks under alternative configs, instead of waiting 2 weeks per live-data iteration. Also commits cove_gradient_log.py which was deployed but never landed in the repo.



## v0.6.74b • June 13, 2026
- Frontal events on debug page (F1 section under Active hypotheses). Live table reads `frontal_events_log.json` and lists detected passages in the 14-day window with type, confidence, dewpoint Δ, wind-octant shift, and pressure bounce. Sanity-check for whether the detector is catching real fronts before letting the briefing AI rely on it. Empty until first detection.



## v0.6.74a • June 13, 2026
- Frontal card matches the t-storm pattern: always visible, content changes by state. Quiet state shows "No recent passage" and surfaces the last logged passage if any; recent/active states show full cause attribution.



## v0.6.74 • June 13, 2026
- **Frontal-passage detector + card.** Names the cause when the weather changes. New `frontal_log.py` captures per-tick Tempest obs (T, Td, P, wind) at the cove; new `frontal_detection.py` reads a 90-min rolling window each tick and classifies cold-front / warm-front / sea-breeze-front passages from three signals (dewpoint drop >8°F, wind direction shift >60°, pressure inflection). Requires 2-of-3 to declare a passage. Surfaces in three places: a hidden-when-quiet card (col-6) showing compact "Front Passing" or "Front Passed at 11:42 PM last night" with dewpoint Δ and wind shift; a line injected into the Gemini briefing prompt so morning copy can say "a cold front cleared things out overnight" instead of just listing new numbers; events log retained 14 days for the debug page (next slot). Card hides entirely when no passage detected (95% of the time). First useful read after the next real front passes.



## v0.6.73 • June 13, 2026
- **R5 reframed on the debug page after Joe pointed out the geography.** Original hypothesis ("waterfront cools during sea breeze") was backwards for this specific cove — Wyman Cove sits in the lee of the Marblehead peninsula on the dominant S/SE/SW sea breeze, so marine air crosses ~2 miles of sun-heated land before reaching the waterfront stations and arrives warmer than inland. Day-1 data (104 ticks) confirms: cove runs +3.4°F (S), +3.7°F (SE), +3.8°F (SW) warmer than inland under active sea breeze, flat under N/NE/E (wind not crossing peninsula). Diurnal curve under active sea breeze peaks at +5.6°F at 12:00 EDT and decays to −0.2°F by 19:00 — tracks solar surface flux. Debug page updated with reframed hypothesis, day-1 table, decision rule shifted from "land-water gap regression" to "wind-octant + hour-of-day conditional correction." Still holding for 7-day confirmation before shipping.

</details>


<details>
<summary><strong>v0.6.72 • June 12, 2026</strong></summary>

- **Two new active hypotheses on the debug page + the loggers that feed them.** R4 (HRRR vs GFS spread as confidence signal): new `gfs_l1_log.json` captures raw GFS values per tick for the 0-48h window, joinable against HRRR L1 already in `forecast_log.json`. Hypothesis is that `|HRRR − GFS|` per hour predicts actual error magnitude — if it does, the spread becomes a free uncertainty number to feed Gemini hedge language and widen displayed intervals. R5 (cove gradient): new `cove_gradient_log.json` captures waterfront Tempest median (Willow, Neptune Rd), inland Tempest median (18 stations), ambient T, wind dir/speed, salem_water_temp_f, buoy water, and sb_active per tick. Hypothesis is that `delta_wf_inland = f(land_water_gap)` stratified by sea-breeze state. First meaningful read on both: ~2026-06-19 (7 days of accumulated ticks). Per the debug-UI stability rule, the section shows "collecting data" placeholders only — charts go in if and only if the regression confirms signal.



## v0.6.71 • June 12, 2026
- **Sunset scorer now penalizes high precipitable water — kills the "every morning Spectacular, every evening dud" failure mode.** Two confirming data points: June 10 (PW 49.1mm) and June 12 (PW 43.9mm) both predicted Spectacular by morning, both were duds. Mechanism: high column moisture washes out color regardless of how "clear" the sky reads to the transmissivity calc — sky stays milky-blue, no orange. Collector: added `precipitable_water` to the directional-cloud Open-Meteo fetch, exposed as `precip_water_mm` in each cloud array of `sunset_directional`. Frontend: scorer now averages PW over the sunset window the same way it averages cloud/humidity, applies a multiplicative `pwFactor = 1 − clamp((PW − 30) / 40, 0, 0.8)` — no penalty under 30mm, −35% at 44mm, capped at −80% by 70mm — and a hard label ceiling so muggy days can't get above Very Good (no Spectacular above 35mm PW, no Very Good above 50mm PW). Belt and suspenders. Holding the rule: ship after two consecutive misses with matching signature, not one.

</details>


<details>
<summary><strong>v0.6.70 • June 11, 2026</strong></summary>

- **Thunderstorm risk now keys off the daytime CAPE peak, not the current value — Gemini stops missing pulse-storm setups.** Investigating a textbook NE pulse setup today (NWS "slight chance thunderstorms" 6pm–11pm, Pirate Weather CAPE peaking ~1,170 J/kg midday): the morning briefing was silent on storm risk. Root cause in `briefing_ai.py:283`: the gate is `severity == "watch" and cape_label not in ("", "Weak")`, but `cape_label` was computed off `cape_current` only. Current CAPE at 8:47am was 601 J/kg → "Weak" → line suppressed, even though peak was Moderate. (1) Added `cape_peak_label = _cape_label(cape_peak_value)` to `derived.thunderstorm` so the daytime peak gets a label of its own. (2) Expanded the "watch" severity trigger to also fire when peak ≥ 1000 J/kg even if current is below the 500 threshold — otherwise a hot afternoon setup reads as "clear" at sunrise. (3) Switched Gemini's prompt gate, the fallback briefing (`briefing.js:871`), the t-storm tile's "Risk Level" badge, and the expanded card's "Risk Level" row to use `cape_peak_label` (falling back to `cape_label` for old payloads). The CAPE-value row still shows current. Kept the "do NOT overstate, mention only briefly" hedge so Gemini doesn't over-correct into hype.



## v0.6.69 • June 11, 2026
- **GCS payloads now gzipped + compact JSON — ~85% smaller on the wire.** Investigating Joe's 15-second iPhone load this morning: response headers on `weather_data.json` showed `x-goog-stored-content-encoding: identity` with `content-length: 420872`. We were serving the main payload uncompressed every fetch — 420KB on cellular is real time. Also `json.dumps(data, indent=2)` was burning ~30% on whitespace. Fixed `gcs_io.upload_json` to (1) emit compact JSON via `separators=(",", ":")`, (2) gzip the payload before upload, (3) set `blob.content_encoding = "gzip"` so GCS serves with `Content-Encoding: gzip` and browsers + iOS Safari + the google-cloud-storage Python client transparently decompress. Applies to all 15+ GCS write paths (weather_data, briefing_cache, decay_corrections, obs_temp_log, etc.) — every read path uses `download_as_text()` which already handles compressed responses, so nothing else needed changing. Expected weather_data.json: ~420KB → ~50KB.



## v0.6.68 • June 11, 2026
- **Debug headline box: graceful degrade when the model is unavailable.** When Open-Meteo's GFS/HRRR is down (as it's been intermittently this morning), the collector falls back to using WU stations directly with no model-comparison bias — so `hyperlocal.weighted_bias` and `weighted_bias_humidity` aren't written at all. The new v0.6.66 headline box was honestly showing "—" + "vs raw model" but looked broken. Now detects degraded mode (`aggregation: fallback_*`, `note: ...unavailable...`, or both bias keys absent) and renders an explicit "paused — model unavailable — using stations directly" message. Also handles the case where `stations_total` is missing by falling back to `"N stations reporting"` instead of `"— stations reporting"`.



## v0.6.67 • June 11, 2026
- **Forecast-text indexer no longer crashes the collector on a partial cache fallback.** Six ERROR 500s overnight (07:47, 08:07, 08:17, 08:27, 09:17, 09:47 UTC) all traced to the same shape: Open-Meteo SSL flap (`SSL: UNEXPECTED_EOF_WHILE_READING`) took down HRRR + GFS-fallback + GFS-7day + directional-sky simultaneously; the cache fallback loaded a previous-tick `hourly` block that was shorter than the per-period indices `forecast_text.py:198` walks, producing `IndexError: list index out of range` → unhandled → 500 → scheduler error email. Fixed by guarding `_generate_period_forecast` with a `safe_len = min(len(arr))` across the seven arrays it actually indexes (temperature, apparent_temperature, wind_speed/gusts/direction, precipitation_probability, weather_code), trimming `period_indices` (and the matching `period_hours`) to that bound. If nothing usable survives, returns None and the caller skips that period — same behavior as the existing "no indices" path. Open-Meteo's outage was their problem; the unhandled crash on our side was a real hardening gap.

</details>


<details>
<summary><strong>v0.6.66 • June 10, 2026</strong></summary>

- **Debug page: phone-friendly headline + plain-English summaries.** Two changes on `corrections_debug.html` aimed at making the pipeline anatomy legible to a reader on iPhone, not just a self-debug surface. (1) New "Right now — what the pipeline is doing" box at the top of the page: four stat cards (temp correction, humidity correction, confidence, briefing source) populated from `hyperlocal` + `briefing`. Mobile-first grid that stacks gracefully on narrow screens. Each correction value gets a plain-English sub-line ("model running cool — we warm it" / "model running dry — we add moisture"). (2) Each Layer section (Accuracy, L1, L2, L3, L4) now leads with a one-line plain-English summary of what the layer does. The existing technical wall of text (Kalman gain, τ, octant aggregation, lead-decay formulas) is folded into a collapsible `▸ How it works` toggle, defaulting closed. Reader gets the gist on first scroll; the math is one tap away for anyone curious. Lowest-cost iteration of the "make it readable on a phone" thread — more polish (table → card stacks, glossary chips, sticky nav) deferred.



## v0.6.65 • June 10, 2026
- **Debug page roster count now reads live, not static.** Layer 2 intro blurb still said "81-station local network" — a stale number from a bigger-roster era; current active is 66 (46 WU + 20 Tempest after the v0.6.64 cull). Replaced with `<span id="layer2NetworkCount">` that `renderLayer2Panel()` updates from `hyperlocal.stations_total` on every refresh. Self-corrects forever after future culls/adds.



## v0.6.64 • June 10, 2026
- **Cull 4 zombie WU stations, hide all culls from debug uptime panel.** KMAMARBL40, 61, 95, 114 had 0% uptime across the full 7-day station_uptime window (1002 fetch-fails each) — moved from `STATIONS` to `CULLED_STATIONS` in `wu_scraper_realtime.py`, same shape as the 2026-06-04 batch. Saves ~576 API calls/day and trues up the "X of Y stations" denominator. Culls are preserved in the `CULLED_STATIONS` list (not deleted) so they can be manually re-probed later if owners come back online. `station_uptime.py` now filters culled IDs out of the summary block it stamps into `hyperlocal.station_uptime` — the debug page's dead-count and mean-uptime are no longer polluted by stations we've deliberately stopped hitting (their on-disk log entries still age out naturally over 7 days).



## v0.6.63 • June 10, 2026
- **Corrections card now compares shade feels-like, not full sun.** The card was using `corrected_feels_like` (Steadman + direct solar — "standing on hot asphalt at noon"), which runs 15–25°F above air temp on clear days. Open-Meteo's `apparent_temperature` (the model side of the comparison) is shade-leaning — no aggressive solar term — so the displayed "bias" was actually the gap between two different physical quantities, not a real correction error. Switched the corrections card to compare against the shade number: NWS heat index when valid (T ≥ 80°F + RH ≥ 35%), else Australian apparent-temperature formula with solar=0 (mirrors the fallback in `feelslike.js`). Full-sun Steadman stays in the Feels Like card with its three-way air/shade/sun chart — that's the right home for it.



## v0.6.62 • June 10, 2026
- **Defang the sea-breeze Δ in the Gemini prompt.** First post-v0.6.61 briefing produced "the sea breeze is active, adding about 22 degrees to the current 82°F" — sea breezes cool the land, they don't heat it. The 22° was real (land 81.5°F − water 59.4°F = 22.1°F land–water gradient), but the prompt fed Gemini the cryptic `Sea breeze: Active — Δ+22.1°F, 7 mph from 195°` and it misread `Δ` as a temperature change applied by the breeze rather than the gradient that drives it. Same failure shape as the torrential incident: reaching for the wrong meaning of a real number. Fixed by replacing the compact reason string in `briefing_ai.py` with a verbose LLM-only form that names the values explicitly — "Land 81.5°F, water 59.4°F (land–water gap of 22.1°F drives the breeze — this gradient is NOT a temperature change). Wind 7 mph from SSW." Frontend sea-breeze card untouched; it still gets the compact Δ form from `sea_breeze.py`.



## v0.6.61 • June 10, 2026
- **Fence intensity words in the Gemini system prompt.** Added a rule barring upgraded precip adjectives: if the data line labels the storm "light," Gemini can't write "heavy," "downpour," "torrential," "deluge," "soaking," or "severe." "Torrential"/"deluge" only when the data line explicitly says "torrential"; "heavy"/"downpour" only when it says "heavy" or "torrential." Prose stays alive at temp 0.9 — the prompt fence shuts off the specific hallucination mode that triggered yesterday's torrential incident. `_validate_headline()` stays in place as the post-generation backstop; this is belt-and-suspenders.



## v0.6.60 • June 10, 2026
- **Full pipeline audit + precip unit bug fixed in three places (including un-doing v0.6.54's wrong fix).** Three-agent audit of the collector flow, correction stack, and derived/frontend layers. Verdict: the stack is sound — bias sign conventions consistent, no double-correction, pair-log has no circularity, lead-time math correct, all physics formulas correct (Magnus, Steadman, NWS heat index bounds, Haurwitz, 225 ft/°F cloud base), L3_FIELDS wd exclusion confirmed as deliberate whitelist (now documented in decay_apply.py). One real bug: `hourly.precipitation` has been in **inches** since the modular refactor (`OM_UNITS` requests `precipitation_unit="inch"`), but three readers divided it by 25.4 as if it were mm: **(1)** `briefing_ai.py` rain_inches — 48h rain total under-reported 25× since the briefing existed (a 1" storm read as 0.0" in the AI prompt); **(2)** `briefing_ai.py` peak_intensity — v0.6.54 added this division believing it fixed the "torrential" headlines; it actually broke a correct computation (real downpours would have read as drizzle). The torrential headlines were model hallucination, already handled by the v0.6.54 `_validate_headline()` + templated fallback; **(3)** `js/briefing.js` rainInches — frontend made the same mistake, which is why briefing rain totals always showed 0.0" (including the May 7 "why does it show 0 inches" incident — the answer then was incomplete). Survivors of the 25.4 sweep are all justified: `tempest.py` converts genuine mm at fetch.



## v0.6.59a • June 10, 2026
- **Forecast sky narrative now reads solar-derived cloud cover (forecast_text.py + current_derived.py).** Extension of v0.6.59: the same transmissivity trick that fixed the Right Now label now applies across the full 48h forecast horizon. `current_derived._forecast_sky_arrays` walks each forecast hour, computes solar elevation for that timestamp, builds Haurwitz clear-sky GHI for that elevation, and back-solves `(1 − direct_radiation/clearsky) × 100` into a cloud-cover percentage per hour. Catches the model contradicting itself — when HRRR forecasts 100% cloud_cover but its own radiation scheme says 600 W/m² is getting through (thin/high cloud), the narrative sees the radiation, not the cover number. `forecast_text.py` prefers `derived.forecast_cloud_cover_solar[i]` over `hourly.cloud_cover[i]` when present; nighttime hours stay None and fall back to model cloud_cover. Also writes `derived.forecast_sky_label[]` + `derived.forecast_transmissivity[]` for debug. Forecast SR error is ~80–150 W/m² across leads — noise on derived τ is ±0.10–0.17, which keeps the Clear/Hazy vs Cloudy/Overcast boundary right almost always (sufficient to fix the "today says overcast but it'll be sunny" narrative bug). Sharpens automatically once L5 regime-aware SR correction ships (~6/22).



## v0.6.59 • June 10, 2026
- **Observed-sky reconciliation (current_derived.py + right_now.js).** HRRR was reporting `cloud_cover: 100` / weather_code 3 (Overcast) while direct radiation at the surface was 396 W/m² and visibility was 73 mi — the actual sky was hazy/thin-cirrus, not overcast. The display believed the model because there's no station ground truth for cloud cover and Layer 2 doesn't apply to `cc`. Two-step fix: **(collector)** new `derived.observed_sky_label` backs out cloud cover from observed solar via Haurwitz clear-sky GHI: `τ = observed_solar / clearsky`, binned to Clear (τ≥0.80) / Hazy (0.55) / Partly Cloudy (0.35) / Mostly Cloudy (0.15) / Overcast (<0.15). Skipped when sun is below 10° — observed solar isn't a reliable sky signal at low angles. Also exposes `solar_transmissivity`, `solar_observed_wm2`, `solar_clearsky_wm2`, `solar_elevation_deg` for debugging. **(frontend)** Right Now card prefers `derived.observed_sky_label` over `weather_code` when present (non-precip days only); falls back to a `direct_radiation ≥ 250 W/m²` heuristic when the derived field is unavailable (sun too low or no observed solar source). Sky/Precip tile, condition label, and weather graphic all see the new label.

</details>


<details>
<summary><strong>v0.6.58a • June 9, 2026</strong></summary>

- **Per-station detail accordions moved from bottom of Layer 2 to directly under 2a.** The "Per-station detail (map + Kalman offsets)" and "Per-station uptime" accordions had been sitting orphaned at the end of Layer 2, after 2e (post-mesonet output grid). They're conceptually about the same thing as 2a (the station network's geographic distribution) — the 2a description text already pointed to "the 2a accordion" for per-station offsets. Reordered so the structural story reads as: 2a coverage rose → per-station detail / uptime accordions (deeper drill-down on the same network) → 2b–2e (what the network's bias correction did this tick). Section now closes cleanly with the post-mesonet output grid before Layer 3 starts.



## v0.6.58 • June 9, 2026
- **L2 τ degenerate-fit guards added at both write and read sides.** When the pair log is starved of signal (today's OOMs and Open-Meteo 429s did exactly this), the Fitter's grid search collapses to the smallest τ in the grid for every field (0.5h) because every τ scores ~identically. Before today, that result clobbered `l2_decay.json` and the live forecast pipeline lost months of validated τ knowledge (Temperature 4h, Humidity 240h, Pressure 12h) in favor of effectively-L1 behavior at every lead. Two guards now in place: **(1)** `decay_fit.py` detects the all-fields-at-min-τ signature and refuses to write — previous good values stay in GCS — history file still gets the degenerate fit for forensics. **(2)** `corrected_hourly.py`'s loader also detects the signature; if a degenerate `l2_decay.json` is already in GCS (today's case), the loader treats it as missing and falls back to `DEFAULT_L2_TAUS` instead of applying 0.5h to every field. Belt + suspenders: the fitter shouldn't write garbage, but if it ever does (or has historically), the pipeline doesn't use it.



## v0.6.52–v0.6.57 • June 9, 2026

* **Briefing reliability + end-to-end audit.** Triggered by morning headlines reading "Cloudy Now" with sky=Clear (Groq hallucination) and "torrential downpours" on light-rain forecasts (unit bug). Fixed the immediate causes and audited the whole module so the next class-of-bug catches itself:
  - **mm/hr vs in/hr unit bug** in `briefing_ai.py:161` — raw Open-Meteo precip rate (mm/hr) was compared against thresholds intended as inches/hr, so 1.0 mm/hr (light rain) was being labeled "torrential" in the prompt and Gemini faithfully wrote "torrential downpours." Divided by 25.4 to convert to in/hr before the threshold check.
  - **Post-generation sanity check (`_validate_headline`).** Every LLM headline now compared to the structured data before shipping; rejects rain words when no rain expected, clear/sunny when cloud cover ≥75%, cloudy/overcast when ≤20%, "torrential"/"deluge" when data doesn't label it that. Conservative — only catches clear contradictions.
  - **Deterministic template fallback (`_templated_briefing`).** Last-resort headline from structured data when Gemini, Groq, and cached headline all fail or all get rejected. Boring but never wrong.
  - **Cache poisoning fix.** Groq output no longer overwrites the GCS cache (cache strictly holds the last validated Gemini headline). Gemini throttle no longer trips on Groq success (so Gemini can be retried on the very next collector run after a transient failure).
  - **Switched Gemini Flash → Flash Lite**, lowered Groq temperature 0.9 → 0.5, broadened the retry window from 503/429 to any 5xx + 429 (single 5s retry).
  - **Wind impact score exposed to the model** alongside the label, for internal severity judgment (existing rule against printing the number stays).
  - **Minor:** empty alert events filtered, thunderstorm distance string suppressed when distance is None or 0.

* **Collector resilience to upstream outages.** Three independent issues surfaced when Open-Meteo started 429-ing during peak hours and the Cloud Function started OOMing.
  - **Memory bump 1024 → 1536 MB.** Memory crashes had been firing every ~70 min since 06-07 (15h after v0.6.42's longer fitter snapshot read deployed). New ceiling gives 489 MiB headroom over today's peak; three consecutive clean runs since.
  - **Octant coverage panel no longer reads all zeros during forecast-model fallback.** When Open-Meteo (HRRR + GFS) is 429, `hyperlocal.py` falls back to a distance-weighted-mean branch that bypasses the L2 octant aggregation. That branch wasn't writing `octant_coverage`, so the debug panel saw `null`, rendered zeros across all eight sectors, and made it look like the entire station network had gone dark (when actually 57 stations were contributing). Fix: fallback branch now computes octant counts and writes `octant_coverage` / `octants_used` / `aggregation` ("fallback_distance_weighted"). An amber banner above the rose explains "Fallback mode active" so the cause is visible.
  - **Settings gear icon no longer lights up on transient source failures that the fallback chain covers.** Old rule lit the dot on any critical-source error — meaning every Open-Meteo 429 (which Pirate Weather covered) made the gear scream for ~10 min even though the data shown was fine. New rule: gear lights only on data staleness >25 min or briefing genuinely empty. Sources-panel dot keeps per-source red/green coloring for debug visibility.

* **Public-sharing prep.** Open Graph + Twitter Card meta tags on `index.html` so iMessage / Slack / X / WhatsApp / Instagram DMs all render a clean preview instead of a bare URL. `tab_nav.js` now honors `?tab=<name>` from the URL so the Instagram bio link `https://wymancove.com/?tab=briefing` lands directly on the Briefing tab regardless of the user's last-active tab.

</details>


<details>
<summary><strong>v0.6.51a • June 8, 2026</strong></summary>

- **L2 lead-decay "Note" rewritten to match reality.** The v0.6.51 note framed "flat" for the eight untreated fields (dp, cc, sr, cl, cm, ch, pp, pa) as a *default pending a future refit*. Tonight's L2-extension investigation showed that framing is wrong — those fields already go through the fitter (`FIELDS` covers all twelve), but `applied_bias = forecast_l2 − forecast_l1 = 0` for every pair because L2 has no additive bias term for them, so the τ grid search is degenerate. The note now says: flat is *structural*, not pending; extending L2 here requires first building a station-network bias tracker per field; `sr` is the only viable candidate (Tempest 20/20 coverage), and even there the planned L5 regime correction is the better tool. The others lack the right sensors entirely. Cuts a misleading promissory line and replaces it with a working explanation of why those columns are flat.
- **build.py version regex fixed to accept letter suffixes.** `(v[\d.]+)` → `(v[\d.]+[a-z]?)`. Previously the regex truncated `v0.6.51a` to `v0.6.51` when writing `version.json`, which would silently break the PWA's update-detection (`version_check.js`) for any suffix release. Caught while shipping this very entry; would have bitten every future `a/b/c` bump.



## v0.6.51 • June 8, 2026
- **L2 lead-decay documented in the debug page.** The v0.6.44 per-field τ lead-decay (`bias_applied(lead) = current_bias × exp(-lead/τ_field)`, τ_t=4h, τ_h=240h, τ_pr=12h) was invisible from the Layer 2 panel — the prose described uniform application and never mentioned the decay. Added a sentence to L2's additive-bias paragraph and a new **2d. Lead-decay applied to L2 bias** subsection placed *before* the post-mesonet output grid (renumbered to 2e), matching the actual pipeline order. Live chart of `exp(-lead/τ)` over 48h for t/h/pr fed by `weather_data.l2_decay_meta.tau_hours`, plus the wind/gust linear 0–24h ramp and a flat reference for every other field. Y-axis is fraction of L2 contribution applied. Copy makes explicit that "flat" for the untested fields (dp, cc, sr, cl, cm, ch, pp, pa) is a *default*, not a winning grid-search candidate — a future refit could expand `L2_TAU_FIELDS` to cover them.
- **R3d τ tuning disambiguated.** The Discarded entry tested the Fitter's *recency-weighting* τ (how much old pairs count when fitting decay curves). Adjacent prose now distinguishes it from the L2 *lead-decay* τ added in v0.6.44 — two different knobs sharing a Greek letter, easy to confuse on skim.
- **Research & Diagnostics intro box removed.** The "Diagnostic only — these signals are tracked but not applied to the live forecast" subhead duplicated the h2 above it, and its secondary line still referenced tide as the active hypothesis (now in Discarded). Section header alone now.
- **Page header meta de-cluttered.** Was showing full enabled-field code lists (e.g. "L3: ch, cm, pp, wg, ws · L4: ch") plus a "(v0.6.45)" version tag, duplicating the banners under each Layer section — and singling out L3/L4 while ignoring L2 (which runs on every field) was misleading. Replaced with a plain freshness line: "decay applied {ts}". Per-layer enabled-field detail lives in the L3/L4 banners; L2 is universal.



## v0.6.50 • June 8, 2026
- **Removed R3e POP entry from Discarded.** With POP re-enabled in v0.6.49, the R3e entry was contradictory ("settled" in the Discarded section). POP is live, settled, and documented in the L3 banner. The Discarded section now contains only genuinely discarded hypotheses.



## v0.6.49 • June 8, 2026
- **POP re-added to L3 — the v0.6.45 audit discarded it with the wrong metric.** The v0.6.45 per-field whitelist used held-out MAE to decide which fields L3/L4 should run on. POP was flagged net-negative and removed. But POP is a *probabilistic* forecast and is properly evaluated by Brier score, not MAE — the original v0.6.20 calibration analysis (`analysis/pop_calibration.py`) showed the flat-additive correction cuts Brier from 783 → 745 (5% improvement). The MAE-based audit was correctly noticing that L3 hurts MAE on POP, but that's the price of better Brier calibration, not a regression. Between v0.6.45 and v0.6.49 we were shipping raw HRRR POP, which is measurably worse than corrected POP on the right metric. Fix: `pp` added back to `L3_FIELDS` in `decay_apply.py`. New `L3_BRIER_FIELDS = {"pp"}` set is published in `decay_meta.layer_3_brier_fields` so the R0 audit table tags POP rows with "[Brier]" and suppresses the MAE-based ⚠ rule for it.



## v0.6.48 • June 8, 2026
- **R2: State-stratified accuracy promoted to live active hypothesis.** Manual-only run of `analysis/state_stratified_accuracy.py` revealed huge regime-conditional spreads: Solar rad × flow regime = 120 W/m² across bins (vs 27 W/m² overall bias), four solar dimensions in the top 5 ranks (98–120 W/m² spread), Cloud cover at 14–17% across multiple dimensions. New module `weather_collector/processors/state_stratified.py` mirrors the analysis script's math (equal-weight, MIN_PAIRS_PER_BIN=20, six dimensions, MIN top-spread verdict threshold=1.0) and is fed in-loop by `decay_fit.py` alongside the recency-weighted accumulators. Publishes `state_stratified_accuracy.json` to GCS at every Fitter pass — per-field per-dimension tables + top-15 ranked opportunities + verdict line. Twice-daily cadence (matches the new Fitter schedule). Frontend renders the top-10 opportunities table + the #1 opportunity's per-bin breakdown (sorted worst → best, red/green bars vs overall MAE). Caveat surfaced in the card: magnitudes are from the 30-day rolling window mostly dominated by pre-v0.6.45 pairs; confirm headlines survive after ~2026-06-22.
- **Research & Diagnostics restructured into three labeled buckets** (`<h3>` subheaders): Diagnostics (R0 live audit, R1 drill-down teaching view), Active hypotheses (R2 state-stratified), Discarded hypotheses (R3 tide + derived humidity + τ tuning + POP). Renumbered titles inside the discarded section R3a–R3e; details element IDs preserved for back-link stability.



## v0.6.47 • June 8, 2026
- **GCP cost trim: Fitter 4×/day → 2×/day, dead-hypothesis tracking gated off.** Daily Fitter compute was driving a 615% MoM jump in GCP spend after the v0.6.42 timeout bump (300s → 540s) and v0.6.44c τ-refit pass. Cadence dropped to 03:07 + 15:07 EDT (post-overnight + mid-afternoon). The active build phase is over (L2 lead-decay shipped, L3/L4 per-field whitelist settled), so same-day refit is no longer required. **Dead hypotheses gated, code preserved:** `RUN_TIDE_TRACKING = False` in `decay_fit.py` skips the per-pair tide-phase accumulator, the tide-phase JSON + history upload, and the NOAA tide-elevation fetch for the time series — about 69 lines of compute + one HTTP request + two GCS writes per Fitter pass. Code remains in place; one-line flip revives it. **UI: new "R4. Discarded hypotheses" section** at the bottom of Research & Diagnostics — R1/R2 tide charts moved inside (showing the frozen final state), plus text-only writeups for R4c derived humidity (27k triples, equivalent), R4d τ-tuning (settled at 14d), and R4e POP calibration (flat-additive shipped v0.6.20). Each notes its analysis script in `analysis/`.



## v0.6.46 • June 8, 2026
- **R0 live audit table — is each layer earning its keep?** New research-section card on `corrections_debug.html` that recomputes the same L1→L4 average-MAE table that drove the v0.6.45 whitelist, live from the already-published `time_series_diagnostic.per_layer_mae_by_lead`. Average is over leads 1–47 (lead 0 excluded — circular by construction). Per field: shows MAE per layer, Δ vs the layer below (green ▼ = improvement, red ▲ = regression), and a `Live?` column reading `decay_meta.layer_3_fields` / `layer_4_fields`. When an enabled layer is currently regressing on its field, the cell flags `⚠`; a banner above the table summarizes "all clean" or "review needed." Pure-JS — no collector change, no new GCS file. Updates as soon as `time_series_diagnostic.json` republishes (every fit cycle, 4×/day). Frontend-only release.



## v0.6.45 • June 8, 2026
- **L3/L4 per-field whitelist (Phase 0 of the L3/L4 audit).** Replaces the global v0.6.44 pause with per-field gating based on held-out MAE from `time_series_diagnostic`. L3 enabled for `ws`, `wg`, `ch`, `cm` (clear wins vs L2: gusts +53%, wind speed +44%, high cloud +18%, mid cloud +5%); L4 enabled for `ch` only (the one field where L4 beats L3 cleanly). Everything else (`t`, `h`, `dp`, `sr`, `cc`, `cl`, `pa`, `pr`) stays disabled — L3/L4 were net-negative there because they were learning residuals from a flat-applied L2 bias; the L2 lead-decay fix from v0.6.44 fixed the input signal but the data hasn't accumulated yet to revalidate. `decay_apply.py` swaps `APPLY_LAYER_3/4` booleans for `L3_FIELDS` / `L4_FIELDS` sets; `decay_meta` publishes both as sorted lists. `_post_l2` / `_post_l3` snapshots still happen for every field so the per-layer MAE diagnostic continues to publish — disabled fields show L3 = L2 and L4 = L3 by construction. `per_field_24h` now only contains fields actually applied.
- **UI: corrections card + debug page reflect per-field state.** Home corrections card shows a unified +24h delta table: L2-only fields (`t`, `h`, `pr`) come from the L2-lead-decayed delta at lead 24h tagged with τ; L3-enabled fields (`ws`, `wg`, `ch`, `cm`, etc.) come from `per_field_24h` tagged "(L3)". Header right shows "L3 on: ws/wg/cm/ch". `corrections_debug.html` Layer 3 and Layer 4 banners updated to explain the audit framing and surface the live enabled-field list; chart labels drop the "(paused)" tags since pause is now field-specific.



## v0.6.44–v0.6.44c • June 8, 2026
- **L2 lead-decay shipped; L3/L4 paused; daily τ refit wired in.** Audit of held-out per-layer MAE showed L3 (decay) and L4 (diurnal) were net-negative on temperature, humidity, dew point, solar, low cloud, pressure, and precip amount — fitting residuals from a flat-applied L2 bias and learning the wrong thing as a result. New `analysis/l2_lead_decay_fit.py` fits a single τ per field via grid search on 73,510 train pairs: `bias_applied(lead) = current_bias × exp(-lead/τ)`. Held-out wins vs flat L2: t +5.1% (τ=4h), h +3.8% (τ=240h), pr +4.2% (τ=12h), dp +3.3% inherited. Wind speed/gust prefer τ=∞ (current flat behavior remains correct). Productionized: `corrected_hourly.py` applies bias × exp(-i/τ_field) per lead index; `DEFAULT_L2_TAUS = {t: 4, h: 240, pr: 12}` baked in with `l2_decay.json` GCS override path. L3 and L4 paused via `APPLY_LAYER_3 = False` / `APPLY_LAYER_4 = False` switches in `decay_apply.py` for ~14 days while the recency-weighted fitter rebuilds against correct-L2 residuals; `_post_l2`/`_post_l3` snapshots still publish so the per-layer MAE diagnostic continues to record.

- **Daily τ refit pass.** `decay_fit.py` extended with three new accumulators per (field, lead): `Σw·e_l1²`, `Σw·e_l1·bias`, `Σw·bias²`. Lets the grid search compute SSE(τ) = Σ_l [e2 + 2·exp(-l/τ)·eb + exp(-2l/τ)·b2] in O(48·15) per field after the pair-log pass. Fits τ for t, h, pr, ws, wg on the same recency-weighted window as L3/L4 (τ=14d). Publishes `l2_decay.json` to GCS with `tau_hours`, `n_pairs_per_field`, `sse_at_grid`; rolling 365d history at `l2_decay_history.json`. `corrected_hourly.py` loader prefers the GCS-published fit and falls back to `DEFAULT_L2_TAUS` if absent or thin (<500 pairs/field). Daily cadence chosen because τ describes a slow process (drivers: seasonal shift, station network changes, big synoptic regime shifts) and sub-daily refit only adds noise; same pair-log read as L3/L4 so marginal cost is zero.

- **UI: corrections card + accuracy chart labels reflect the pause.** When `decay_meta.layer_3_paused` is true, the home corrections card swaps "Forecast Decay Corrections" → "Forecast Corrections at +24h" and shows the actual L2-lead-decayed delta at lead 24h (computed from corrected vs raw hourly arrays), with each row tagged by its τ value — instead of the previous `per_field_24h` (what L3 *would* apply, not currently in the live forecast). `corrections_debug.html` Layer 3 and Layer 4 sections gain an amber paused banner; the "how accurate is it?" chart's legend relabels "+ Mesonet" → "+ Mesonet (final)" and "+ Decay" / "+ Diurnal" → "(paused)"; the drill-down preview legend matches. Header meta line shows "L3/L4 paused (v0.6.44) · L2 lead-decay only" when paused.



## v0.6.43 • June 8, 2026
- **Corrections card + debug page UI tweaks.** Hyperlocal corrections card: Feels Like row labeled `(full sun)` to make explicit that the corrected apparent-temperature uses the unshaded solar load (shade variant TBD). Forecast Decay Corrections subsection expanded from 6 → 10 fields — added Pressure, Cloud Cover, Solar Rad, Precip Rate; layer-specific cloud bands (cl/cm/ch) intentionally omitted as too technical for the home card. `corrections_debug.html` accuracy section heading reworded "is it actually working?" → "how accurate is it?". Sticky TOC bar gains a "← Back" chip as the first item that returns to `/` (index.html) — no in-page way to leave the debug view existed before.

</details>


<details>
<summary><strong>v0.6.42 • June 6, 2026</strong></summary>

- **Fitter race-condition fix.** The Daily Fitter was failing on every recent run because it read `forecast_error_log.jsonl` directly from the live blob handle while the Joiner appended to that same file every 10 min via GCS compose. Reads of the ~800MB file took several minutes — long enough for the Joiner to replace the file mid-read, producing either a `Bytes stream is in unexpected state` desync error or a 404 on the pinned generation. Fix: server-side `copy_blob` to an immutable snapshot path `forecast_error_log_fitter_snapshot.jsonl` before the read, then stream from the snapshot. Snapshot is deleted after the main rewrite swap (or in the error path). Manual run verified — 1.99M pairs processed, all 14 fields fitted with sensible decay corrections. Also bumped the Cloud Function timeout from 300s → 540s (`Makefile`) since a clean Fitter pass on the current log size takes ~3 min and the collector has other work to do on the same invocation. Added an HTTP-status + body-excerpt diagnostic to the Briefing module's Gemini fallback path (`briefing_ai.py`) — confirmed the chronic Gemini failures are HTTP 429 quota exceeded (AI Studio free-tier limit, not GCP billing) with Groq fallback succeeding 100%.
- **Humidity now uses Kalman gain.** The temperature pipeline blends `model_t + K × weighted_bias` where K scales from 0.40 (sparse / scattered stations) to 0.90 (many stations agreeing tightly). Humidity was doing pure station-mean replacement of the model value — no confidence gating, so a few drifty hygrometers could swing `corrected_humidity` 20%+ in either direction. Extended the Kalman blending to humidity with a separate threshold function `_kalman_gain_humidity(n, std)` calibrated for the humidity % scale (thresholds `3.0` / `7.0` vs temp's `0.4` / `0.8` °F — hygrometers are noisier than thermistors, so analogous "tight" / "moderate" buckets land at different absolute numbers). Pressure intentionally skipped: 30-day Fitter shows pressure bias is essentially zero (`pa` corrections all `-0.001` across 48 lead bins), station consensus matches model after altitude normalization, so K would always be 0.9 and the visible effect would round to zero. New `hyperlocal` fields: `weighted_bias_humidity`, `bias_std_humidity`, `kalman_gain_humidity`, `stations_used_humidity`. `corrections_debug.html` Layer 3 panel now renders temp and humidity side-by-side (K, percentage trusted, weighted bias, applied bias, scatter, n stations); methodology note updated; per-station bias header stats add `Kalman gain (RH)` and `bias σ (RH)`.

</details>


<details>
<summary><strong>v0.6.41 • June 4, 2026</strong></summary>

- **Layer 2 accordions now remember open/closed state across page refresh.** Both `#bias-details` ("Per-station detail") and `#uptime-details` ("Per-station uptime") accordions on `corrections_debug.html` lost their open state on every reload, forcing re-expansion every visit. Added `initBiasAccordions()` (mirrors the existing `initResearchAccordions` pattern but with a separate localStorage key `forecastPipelineBiasAccordionsOpen`) which restores the open state per `details.bias-accordion[id]` element on load and persists toggle changes. The existing map-invalidation handler on `#bias-details` continues to coexist — both toggle listeners fire on user interaction; the map-resize handler's `if (_biasMap)` guard prevents it firing prematurely when state is restored before render.



## v0.6.40 • June 4, 2026
- **Per-station uptime UI on debug page.** New accordion under Layer 2's "Per-station detail" section displays a sortable table of all tracked stations with `uptime_pct / n_success / n_attempts`. Color tiers: green ≥95%, amber 80-95%, red <80%, bold dark-red 0%. Header strip summarizes total stations, mean uptime, healthy/degraded/dead counts. Sort defaults to worst-first (ascending pct) so dead stations rise to the top. Data source: `hyperlocal.station_uptime` (7-day rolling window from `station_uptime.py`). Implementation: ~110 lines of JS (`_uptimeState`, `_uptimeTier`, `_renderUptimeTable`, `renderUptimeSection`) reusing the existing `offset-table` CSS pattern. Reveals what wasn't visible before — the new view immediately surfaced 23 dead stations (0% over 179 ticks) and prompted the cull below.
- **Cull 16 dead stations from the fetcher lists.** Direct API probes confirmed two distinct failure modes:
  - **10 WU stations return HTTP 204 (No Content)** every tick — station IDs are still valid in WU's directory (the `wunderground.com/hourly/...` page resolves) but the owners aren't uploading recent observations. Culled: `KMAMARBL89, KMAMARBL117, KMAMARBL118, KMAMARBL17, KMAMARBL26, KMAMARBL84, KMASALEM35, KMASALEM86, KMASALEM111, KMASWAMP28`.
  - **6 Tempest stations return partial obs records** through the developer API — only lightning + precip fields, with temp / wind / humidity blanked. The stations ARE online (full data visible on tempestwx.com) but the owners have restricted field-level sharing for API access. Useless for our mesonet bias correction which requires temp + wind. Culled: `28679 (Broadmere Way), 51384 (Memorial Dr), 72262 (Spray Ave), 85260 (Driftwood Rd), 100037 (Bass Rock Ln), 159204 (Marblehead)`.
  - Both fetcher files retain a `CULLED_STATIONS` / `CULLED_TEMPEST_STATIONS` constant beneath the active list — the cull list lives with the data so anyone editing the file sees what was removed and why. Easy to un-cull if a station comes back online.
  - **Effect:** total stations attempted per tick goes 86 → 70. The 16 culled stations will continue to appear in the uptime UI at 0% for ~7 days (the rolling window's retention) and then age out naturally — no GCS log cleanup needed.



## v0.6.39 • June 4, 2026
- **Prominent zero line on historical fits charts.** Sections 3c (decay history), 4a (diurnal history), and R1 (tide-phase history) on `corrections_debug.html` plot many overlaid grey-on-dark curves; the existing thin grid line at y=0 was hard to spot, making it ambiguous whether a field's bias started positive or negative — and therefore which direction "good evolution" (curves moving toward zero) actually looked like. Added a small inline Chart.js plugin `zeroLinePlugin` that draws a white 1.5px line at y=0 before the datasets render, with a bounds check so it's skipped when zero is outside the visible y-range. Wired into all three `build*HistoryChart` functions via the chart config's top-level `plugins: [zeroLinePlugin]`. The recency gradient (oldest pale grey → newest solid blue) was already in place; this fix just makes the reference baseline visible.



## v0.6.38 • June 4, 2026
- **Wind regime classifier shipped.** New module `weather_collector/processors/regime_classifier.py` exposes two orthogonal classifiers: `classify_flow_regime` (pure direction — n/ne/e/se/s/sw/w/nw/calm, 9 labels) and `classify_synoptic_regime` (coastal-flavored synoptic pattern — nw_flow/sw_flow/se_flow/ne_flow/sea_breeze/nor_easter/frontal/pre_frontal/calm, 9 labels). Both axes get stamped onto every pair (`state_fc.regime_flow` + `state_fc.regime_synoptic` for forecast-time state, `state_obs.regime_flow` + `state_obs.regime_synoptic` for observation-time state) inside `forecast_error_log.py` as the Joiner builds state metadata. Rule-based: sea_breeze requires SE-quadrant flow + summer afternoon hour + warm + light wind + steady pressure; nor_easter requires NE flow + low pressure + ≥12 mph; frontal/pre_frontal triggered by pressure trend. Pre-v0.6.38 pairs don't carry these keys and are silently skipped by downstream analytics. `analysis/state_stratified_accuracy.py` extended with both regime axes as the 5th and 6th stratification dimensions — re-run in ~1 week once regime-bearing pairs accumulate to see which regimes show the biggest forecast-error spread.



## v0.6.37 • June 4, 2026
- **Debug page browser tab title is now "Wyman Cove — Forecast Pipeline"** (was "MyWeather — Forecast Pipeline"). Project nickname is for the codebase, not the user-facing page.
- **Research-section subsections are now individually collapsible.** R1 (tide-phase curves) and R2 (error-vs-tide timeseries) on the Forecast Pipeline page were always-on under the Research h2, so opening that section dumped both charts at once. Wrapped each in a `<details class="research-subsection">` with closed default state and localStorage persistence (key: `forecastPipelineResearchOpen`). Matches the existing bias-accordion pattern but in the orange/amber research palette. New `initResearchAccordions()` wires the toggle persistence.
- **Two new analysis scripts** for hypothesis testing as data accumulates:
  - `analysis/state_stratified_accuracy.py` — slices forecast MAE by wind octant, wind speed, cloud cover, and pressure tendency to find which regime dimensions matter. First run: humidity-by-wind-direction shows 9.9% RH spread across octants (NW dry vs SE marine); temperature-by-wind-direction shows 3.8°F spread. Both are candidates for future regime-stratified correction.
  - `analysis/decay_tau_tuning.py` — walk-forward validation of τ ∈ {7,10,14,21,28} per field. First run verdict: KEEP τ=14 global (no field gains ≥5% vs τ=14). Caveat: the recent v0.6.34/35/36 changes mean current pair log mixes schemas; re-run in ~1 week for cleaner read.



## v0.6.36 • June 4, 2026
- **Fix: moisture derivation didn't run in fallback mode.** v0.6.35 added Magnus-derived corrected_humidity inside `apply_decay_corrections`, which runs BEFORE `apply_stale_fallbacks` in collector.main(). When an upstream fetch fails (e.g. today's Open-Meteo outage), `apply_stale_fallbacks` overwrites `weather_data["hourly"]` with the previous run's cached hourly array — which silently overwrote the derived corrected_humidity with the old independently-corrected value. Audit caught it: live corrected_humidity differed from Magnus(corrected_T, corrected_T_d) by 0.5–2.6% across every hour. Fix: factored the Magnus humidity + Steadman apparent_temp + absolute_humidity recompute into a standalone `recompute_derived_moisture_arrays(weather_data)` function in decay_apply.py. Called both inside `apply_decay_corrections` (fresh-data path) and from collector.main() immediately after `apply_stale_fallbacks` (cached-data path). Idempotent — safe to call multiple times. The (T, T_d, RH, AH) moisture quadruple now ships consistent whether the data is fresh or stale-cached.



## v0.6.35 • June 4, 2026
- **Humidity now derived from corrected (T, T_d) via Magnus.** Architectural consistency fix. apparent_temperature and absolute_humidity already derive from corrected T and corrected T_d so they stay internally consistent; humidity was the holdout — independently corrected through L2/L3/L4. Even though the offline analysis (`analysis/derived_humidity.py`) showed independent vs derived MAE were a wash (Δ ≈ 0% across all leads, n=1947 triples), individual point forecasts can disagree — heat index computed from (T_corrected, RH_corrected) wouldn't match heat index from (T_corrected, Magnus(T_corrected, T_d_corrected)). Fix: in `decay_apply.py`, after all L1-L4 corrections complete, overwrite `corrected_humidity[i]` with `_relative_humidity(corrected_temperature[i], corrected_dew_point[i])` via Magnus before recomputing apparent_temp and absolute_humidity. Independent L2/L3/L4 humidity corrections still run (visible in pair-log per-layer fields for diagnostic comparison) but the shipped value is derived. The full (T, T_d, RH, AH) moisture state now ships as one consistent quadruple. dp_l4 > t_l4 (unphysical) clamps RH to 100.



## v0.6.34 • June 4, 2026
- **Fix: Layer 4 diurnal was structurally over-correcting on most fields.** The 03:07 EDT fit on June 4 showed L4 MAE worse than L3 on temp/dp/h at 6h lead, and catastrophically worse on cloud cover (L4=14.44 vs L3=6.36, −130% vs raw). Root cause: the diurnal fit accumulated the legacy `error` field (= L2 residual, same signal Layer 3 was fit on). Layer 3 captured per-lead means; Layer 4 captured per-hour means; both latched onto the same hour-of-day bias signal. The mean-zero normalization on L4 was a partial hack to decouple them, but it only removes the grand mean — it can't decompose the lead × hour-of-day interaction when those are correlated (which they are for cloud cover, solar, wind). Fix in `decay_fit.py`: (1) accumulate diurnal sums from `error_l3` (L3 residual) instead of `error`; legacy pre-v0.6.25 pairs fall back to `error`. (2) Remove the mean-zero normalization — when fitting on L3 residuals, L3's contribution is already removed, so the raw per-hour mean is the correct adjustment. Simulated on the current 1.28M-pair log: L4 MAE drops 26–65% across every field (cc 12.79→4.43, sr 27.62→13.89, wg 2.94→1.56, t 2.33→1.60, dp 3.95→2.72). New corrections take effect at the next Fitter run (09:07 EDT today).

</details>


<details>
<summary><strong>v0.6.33a • June 3, 2026</strong></summary>

- **Removed v0.6.33's past-observation overlay from drill-down charts.** Standalone past observations aren't diagnostic on their own — they're just "what the weather did," which isn't the drill-down's job. The drill-down's purpose is "preview the next 48h, see what each layer thinks." Past-forecast-vs-past-observation comparison belongs in the Accuracy section, which already does it statistically. Removed: x-axis past-extension (back to leads 0–47), the white observed-line dataset, the obs_temp_log fetch in load(), and the DRILL_OBS_KEY + _drillObsByHour helpers. Kept from v0.6.33: confidence band around L4 (±near-term MAE width) and the MAE annotation strip under each card. Both add the accuracy context the drill-down actually needs.



## v0.6.33 • June 3, 2026
- **Drill-down charts get three accuracy enhancements.** Same chart per field as before, but now with: (1) **Past-24h observation overlay** — solid white dots+line on the past portion of the x-axis showing the actual observed values from `obs_temp_log` for the last 24 hours (binned to nearest hour, closest entry per bin). X-axis extended from leads 0→47 to leads −24→+47. POP gets binary 0/100 obs from `precip_in > 0`. (2) **MAE annotation under each card** — small text strip showing "Near-term (6h) ±X · Day-ahead (24h) ±Y" sourced from `time_series_diagnostic.json::per_layer_mae_by_lead.l4` with `errors_by_lead` mean-of-abs fallback (same logic as Almanac accuracy block). (3) **Confidence band around L4 line** — translucent blue fill at ±near-term-MAE width, visually indicating the typical error envelope of the final forecast. Hidden from chart legend. New `DRILL_OBS_KEY` table maps field keys to obs_log field names. New `_drillObsByHour` helper buckets obs by integer hour offset. Chart tooltips now distinguish "Xh ago (observed)" from "+Xh (forecast)". Five `_drillRender()` call sites updated to thread `tsDoc` + `obsLog` through.



## v0.6.32a • June 3, 2026
- **Fix: 24h-ahead column was blank in the new Forecast accuracy block.** Cause: `per_layer_mae_by_lead.l4[24]` requires a snapshot taken 24h ago that has L4 captured, but v0.6.25b (which added L4 capture) deployed only ~10h ago. Lead-24 L4 data won't exist for another ~14h. Fix: `renderForecastAccuracy()` now falls back to the legacy `errors_by_lead` field (which exists on every pair going back the full 7d) when L4 is missing at a given lead — computes MAE as mean-of-abs of per-hour errors. Slightly conservative as a proxy for L4 (uses L2-stage forecast vs obs) but available immediately at all leads. Will switch back to L4 naturally as that data accumulates.



## v0.6.32 • June 3, 2026
- **Forecast accuracy block on the Almanac → Observed card.** Surfaces practical accuracy numbers to the main app for the first time. New `renderForecastAccuracy()` in `obschart.js` fetches `time_series_diagnostic.json::per_layer_mae_by_lead`, pulls Layer 4 (final corrected forecast) MAE for the 7-day rolling window at lead 6h ("6h ahead") and lead 24h ("24h ahead"), and renders a compact 3-column table under the obs chart for 7 fields: Temp, Wind, Gust, Humidity, Dew point, Pressure, Cloud. Format: `±1.2 °F`. Pulls in fresh data on each `buildObsChart()` call (i.e., every page load / refresh). 7-day window for stability; 6h/24h leads for "near-term vs day-ahead" framing. Source notes that lead 0 is intentionally skipped (circular comparison).



## v0.6.31 • June 3, 2026
- **Fix: exclude wind direction from diurnal fit.** The diurnal aggregator in `decay_fit.py` was applying its signed-mean-error logic to wind direction's angular-delta `error` field, producing nonsensical ±139° "diurnal corrections" by averaging across the 0°/360° wraparound. Currently saved from being applied by the accident that wd isn't in diurnal's TARGET_ARRAY, but the bogus values were sitting in `diurnal_corrections.json`. Added explicit `field != "wd"` check in the diurnal accumulator. Wind-direction Layer 4 (diurnal) needs its own sin/cos special-case (same as the decay one); deferred to a future version per v0.6.27 scope. Other two surfaced "bugs" (cloud diurnal ±53% and cloud L1=0 in per-layer chart) are NOT data quality issues — first may be real seasonal signal, second is a transition artifact from old snapshots aging out of the pair log.



## v0.6.30a • June 3, 2026
- **Fix: Forecast Pipeline link in settings drawer was invisible in light theme.** Was using `color:var(--accent)` which renders white-on-white in light mode. Switched to `color:var(--muted)` to match the sibling label styling (How It Works, Changelog, etc.); ↗ glyph still signals it's a link.



## v0.6.30 • June 3, 2026
- **Per-station uptime tracking** (foundation for future auto-cull). New `processors/station_uptime.py` writes a rolling 7-day per-station success/fail log to `station_uptime.json` in GCS. Each tick records whether every attempted WU + Tempest station returned usable data (WU = has `temperature_f`; Tempest = `valid` flag). A per-station summary (`{uptime_pct, n_attempts, n_success}`) is also stamped into `weather_data["hyperlocal"]["station_uptime"]` so the debug page can render uptime without an extra fetch. Auto-culling stays MANUAL for now — the data first needs a week to be meaningful before threshold decisions. Reads `STATIONS` from `wu_scraper_realtime.py` and `TEMPEST_STATIONS` from `tempest.py` to determine the attempted set.



## v0.6.29 • June 3, 2026
- **Conditional-state metadata stamped on every pair.** Foundation for Research-section hypothesis stratifications (e.g., "temp bias when wind is from NW vs SE", "humidity bias on sunny vs overcast days"). Each pair row in `forecast_error_log.jsonl` now carries two dicts: `state_fc` (forecast-side state at snapshot time, pulled from the snapshot's target_hour + snapshot-level metadata) and `state_obs` (observed-side state at obs time, pulled from `obs_temp_log`). Fields captured: wind_speed, wind_dir, solar_wm2, cloud_cover, cloud_low/mid/high, pressure_in, precip, plus pressure_trend_hpa_3h (forecast-side only, snapshot-level) and humidity/temp (obs-side only). `forecast_snapshot.py` now accepts a `derived=` arg to capture snapshot-level state (pressure trend) as snapshot metadata. Same value applied to every pair born from the same (snapshot, obs) join. The Fitter doesn't aggregate by these yet — they're logged for downstream conditional analyses. Starting log NOW means we don't lose the next week of data while debating the analysis design.



## v0.6.28 • June 3, 2026
- **AI briefing now gets cloud cover + pressure trend.** Gemini prompt had no idea whether it was sunny or overcast (clear gap — a 75° sunny day and a 75° overcast day read completely differently). Added two new optional prompt lines in `briefing_ai.py`: (a) **Sky** — current cloud % + 24h range when range > 25% (e.g., "Sky: 30% cloud now, ranges 0-90% next 24h"); steady-state phrasing when it's holding flat. (b) **Pressure trend** — when 3h trend ≥ ±1.5 hPa, includes a labeled trend with severity ("falling" → "FALLING FAST — storm signal — front likely incoming"). Skipped when steady. Both pull from already-corrected post-Layer-4 hourly data + the existing `derived.pressure_trend_hpa_3h`.



## v0.6.27a • June 3, 2026
- **Sanity cap on wind-direction correction.** v0.6.27 had no cap on the sin/cos correction magnitudes — with one pair in the log, lead-0 correction was (1.63, -1.14) which flipped wind direction by 170° (south wind → north wind). Added `WD_COMPONENT_CAP = 0.30` in `decay_apply.py` clamp on each sin/cos component before recombining via atan2. Max angular shift ≈ asin(0.3) ≈ 17° single-axis (~24° combined). Symmetric with the other fields' CAPS.



## v0.6.27 • June 3, 2026
- **Wind direction added as the 14th correction field — Layer 3 (decay) only, with proper circular math.** Wind direction is a circular variable (5° vs 355° = 10° apart, not 350°); standard signed-mean-error fitting breaks completely. Solution: fit corrections in **(sin, cos) component space**. (1) `forecast_snapshot.py` captures `wind_direction` per layer (l2=l1 and l4=l3 since wd has no mesonet or diurnal layer yet). (2) `forecast_error_log.py` special-cases wd: computes `error` as wrap-aware angular delta in [-180, 180] via new `_circular_diff_deg` helper, plus `error_sin` and `error_cos` as forecast-vs-observed component differences. Per-layer `error_lN` for wd also uses circular delta. (3) `decay_fit.py` adds `wd` to FIELDS and a parallel sin/cos accumulator (`wd_sin_sums/cos_sums/weights`) per lead bin. Outputs `corrections["wd_components"] = {"sin": [...48], "cos": [...48]}`. (4) `decay_apply.py` applies wd correction via `atan2`: `corrected_sin = sin(raw) − sin_corr`, same for cos, then `atan2(s, c)` recovers the corrected angle. Preserves `raw_wind_direction` before mutation. (5) Frontend FIELDS gets a wd entry; appears in Layer 1 raw grid, drill-down, and the per-layer accuracy chart with units in degrees. Layer 2 (mesonet vector blend) and Layer 4 (diurnal) for wd are explicitly NOT in v0.6.27 — start with decay, see if it earns its keep, add the others if data warrants.



## v0.6.26b • June 3, 2026
- **Collapsible top-level sections on the Forecast Pipeline page.** Click any `h2.section` heading to collapse/expand its content. ▾/▸ indicator shows state. Collapsed state persisted per section to `localStorage` (key `forecastPipelineCollapsed`) so the page remembers what you collapsed across refreshes. TOC links still work — heading stays visible; click to expand. With 13 fields × multi-section layout the page got long; this trims it back to whatever sections you actually want to see.



## v0.6.26a • June 3, 2026
- **Drill-down section reworked as multi-select.** Was "Single-field drill-down" with radio buttons. Now: rename to **"Drill-down"**, field selector is checkboxes (default: just temperature), each checked field gets its own chart (4-layer stack). Adds **"Clear all" button** for fast deselect. Play layer-build-up animation now applies in sync across every selected field's chart. Unit-mismatch problem solved by giving each field its own y-axis card rather than overlaying. With 13 fields now in the stack, this is the better navigation pattern.



## v0.6.26 • June 3, 2026
- **Correction stack expanded from 8 to 13 fields.** Five additions, all wired through Layers 3 (decay) + 4 (diurnal). No Layer 2 for these (no per-station-network bias path makes sense). All hooked into the per-layer MAE-by-lead chart on the diagnostic page.
  - **Solar radiation (`sr`)** — forecast: `hourly.direct_radiation` (HRRR, W/m²). Obs: median across Tempest stations' `solar_radiation_wm2` (skips shaded outliers via median). Cap ±300 W/m², bounds [0, 1400].
  - **Precipitation amount (`pa`)** — forecast: `hourly.precipitation` (HRRR, in/hr). Obs: MAX of WU stations' `precip_rate_in` (rain is patchy; one station in the cell is the right signal). Cap ±0.20 in/hr — strict because the field is sparse and noisy.
  - **Cloud cover low/mid/high (`cl`/`cm`/`ch`)** — forecast: `hourly.cloud_cover_low/mid/high` (HRRR, 0–100% each). Obs: parsed from KBOS METAR `clouds[]` array per layer altitude using FAA bands (low <6500ft, mid 6500–20000ft, high >20000ft); new helper `_metar_cloud_splits_pct` in `noaa.py`. Per-altitude bias drives fog/cloud-base accuracy independently of the total-cover metric.
- **Six file changes** to wire the 5 new fields: `obs_log.py` (new kwargs), `daily_extremes.py` (Tempest solar aggregation + WU precip max + KBOS cloud splits), `noaa.py` (METAR altitude parsing), `decay_fit.py::FIELDS`, `decay_apply.py` (TARGET_ARRAY/CAPS/ROUND_DIGITS/FIELD_BOUNDS + raw_* preservation), `forecast_snapshot.py` (4-layer capture for each), `forecast_error_log.py::FIELD_MAP`, `corrections_debug.html::FIELDS`. Per-layer pair data starts accumulating from this deploy; meaningful corrections after ~24h, full lead coverage after 48h.



## v0.6.25e • June 3, 2026
- **Docs catch-up:** `HOW_IT_WORKS.md` rewritten end-to-end for the v0.6.25 architecture — 81-station mesonet, 4-layer model (Raw / Mesonet / Decay / Diurnal), octant balancing, MAD outlier trimming, Kalman retune, per-station calibration, pressure + cloud as correction fields, every-6h Fitter cadence. `DATA_PIPELINE.md` got surgical updates to the framing block, temperature section (octant aggregation + new Kalman thresholds + outlier trimming), pressure section (Layer 3/4 now applied, not skipped), wind blend (per-octant max → median, not flat max), wind gust section (radius 1.5 → 2.5mi), plus a new Cloud Cover section. Docs were previously dated June 1 and described pre-v0.6.17 internals.



## v0.6.25d • June 3, 2026
- **Plain-English labels on Forecast Accuracy charts.** Card summary now reads "Average forecast error by lead time" (was "MAE vs lead"), y-axis "Average error (°F)" (was "MAE (°F)"), x-axis "Hours ahead of forecast" (was "lead (h)"). Same data, less jargon.



## v0.6.25c • June 3, 2026
- **Per-layer accuracy section reframed as MAE-vs-lead chart per field.** v0.6.25/25b aggregated only at lead 0 — which is the one lead where the comparison is circular (the "observation" is the same-moment mesonet, so L2 forecast = L2 obs ≈ 0 error by construction). Now aggregates at ALL 48 lead bins over the 7-day window. Frontend rewritten from 4-row table to per-field MAE-vs-lead chart with 4 lines overlaid (Raw model, +Mesonet, +Decay, +Diurnal final). The gap between gray dashed (raw) and blue (final) at each lead = how much our pipeline reduces error at that forecast horizon. Lead 0 still shows ~0 for L2; lead 1+ is meaningful signal. Backend: `decay_fit.py` now writes `per_layer_mae_by_lead`, `per_layer_bias_by_lead`, `per_layer_n_by_lead` (each field × layer × 48-bin array) to `time_series_diagnostic.json`.



## v0.6.25b • June 3, 2026
- **Fix:** v0.6.25 per-layer MAE table showed L1 + L4 populated but L2 + L3 empty. Cause: `append_forecast_snapshot` was called from inside `compute_daily_extremes` BEFORE `apply_decay_corrections` ran, so the `*_post_l2` / `*_post_l3` intermediate arrays (which decay_apply stamps as side-effects) didn't exist yet at snapshot time. Moved the snapshot call out of `daily_extremes.py` and into `collector.py` immediately AFTER `apply_decay_corrections`. Legacy top-level snapshot keys (`t`, `h`, etc.) now explicitly set to `*_l2` values (was implicitly L2 from pre-decay timing) so the Fitter's decay-correction calibration is unaffected by the timing change.



## v0.6.25a • June 3, 2026
- **Fitter cadence bumped from once-daily to every 6 hours** during active build phase. Gate in `collector.py` changed from `now_local.hour == 3` to `now_local.hour in (3, 9, 15, 21)` — fires at 03:07/09:07/15:07/21:07 EDT. Each Fitter pass is ~$0.0001 in compute (truly free) and the daily-only cadence was leaving newly-deployed correction fields (pressure, cloud, per-layer tracking) un-fitted until next 03:07. Revert to `hour == 3` once the stack stabilizes.



## v0.6.25 • June 3, 2026
- **Per-layer MAE tracking for the Forecast Accuracy section.** Was: one MAE per field (final post-Layer-4). Now: 4-row table per field showing MAE after each correction layer (Raw → +Mesonet → +Decay → +Diurnal), with % improvement vs prior layer next to each. Answers the highest-ROI question — which corrections actually earn their keep vs polish noise. Five-file pipeline change: (1) `decay_apply.py` snapshots intermediate hourly arrays as side effects — `corrected_*_post_l2` (= what corrected_hourly built, pre-decay) and `corrected_*_post_l3` (= after decay, pre-diurnal). (2) `forecast_snapshot.py` captures per-hour forecast values at all 4 layers (`t_l1`, `t_l2`, `t_l3`, `t_l4`, etc., plus derived dew-point per layer via Magnus). Backward-compat top-level keys still written. (3) `forecast_error_log.py` emits `forecast_lN` and `error_lN` fields per pair when the snapshot captured them. Pre-v0.6.25 pairs silently lack per-layer detail. (4) `decay_fit.py` aggregates per-(field, layer) MAE and bias in 24h and 7d windows at lead 0, writes to `time_series_diagnostic.json::per_layer_stats`. (5) `corrections_debug.html::renderAccuracySection` rewritten as the 4-row per-field table with delta percentages — green for improvement, amber for regression.
- **Live Forecast Pipeline link added to the settings drawer's "How It Works" area.** New row pointing to `corrections_debug.html` so users can jump from the main app to the live layer-by-layer diagnostic view.

</details>


<details>
<summary><strong>v0.6.24 • June 2, 2026</strong></summary>

- **Per-octant outlier trimming in Layer 2 aggregation** to defend against busted-sensor reads in sparse octants. Before: each octant's weighted mean included every contributing station; a single +5°F sensor in a 4-station octant could pull the octant mean by ~1.25°F and the network bias by ~0.16°F. Now: within each octant we first compute the median + median-absolute-deviation (MAD), drop any station whose value is more than `OUTLIER_K * 1.4826 * MAD` from the median (k=3.5 → ~4°F threshold for temp at typical spread), then take the weighted mean of what's left. Critical choice: MAD instead of std for the threshold — std gets inflated by the very outlier we want to catch (a +5°F sensor near +0.5°F median pushes std past its own deviation, protecting itself), MAD is unaffected. Skipped when fewer than 3 stations in an octant (can't detect outliers with <3 samples). Same trimming applied to humidity and pressure per-octant aggregations. New `hyperlocal.outliers_trimmed` field stamped each tick; surfaced on the debug page octant panel as "Outliers trimmed this tick: N".



## v0.6.23a • June 2, 2026
- **Print/PDF styling:** added `@media print` block to `corrections_debug.html` so the page is readable when printed or saved to PDF. Flips background to white, text to dark, hides the sticky TOC (useless in print), keeps section accent bars but at darker color, gives accuracy/info panels and cards white backgrounds with gray borders, and applies dark-on-light styling to the octant rose, bias offsets table, and stats text. Canvas charts can't be flipped (they're rasterized with dark theme baked into the bitmap) — those stay dark in PDF, but the surrounding text is now legible.



## v0.6.23 • June 2, 2026
- **Retuned Kalman gain thresholds for the v0.6.17 octant-scatter `bias_std` metric.** The old `_kalman_gain` thresholds (`std<1.0 → 0.9`, `std<2.0 → 0.65`) were calibrated for the pre-v0.6.17 per-STATION scatter (~30 individual stations disagreeing). Under v0.6.17's per-OCTANT scatter (8 geographic means of stations), values are tighter by construction — averages of averages — so typical std lands in 0.3–1.0 range, which always tripped the old "high confidence" bucket and pushed K to 0.9. This was over-applying the network bias: today's K=0.9 with old thresholds vs K=0.65 with new (matches yesterday's same-conditions value). New thresholds: `std<0.4 → K=0.9`, `std<0.8 → K=0.65`, else K=0.4 — preserves the same approximate fraction of days in each confidence bucket as the original calibration. One-line fix in `hyperlocal.py`.



## v0.6.22a • June 2, 2026
- **Forecast pipeline section headings made prominent.** Previously a small uppercase muted-color label, which was easy to miss when jumping via the TOC. Now: large 21px high-contrast text, accent left-border bar, subtle gradient background. Plus a 1.2s `:target` flash animation so clicking a TOC chip visibly punches the destination heading. Research section gets an amber variant matching its TOC chip color.



## v0.6.22 • June 2, 2026
- **Cloud cover added as the 8th correction field.** Same Layer 3 (decay) + Layer 4 (diurnal) treatment as the rest, no Layer 2 (no station network reports cloud cover, only METAR stations do). Six file changes wire it through: (1) `noaa.py::fetch_kbos_obs` now parses the METAR `clouds[]` array via a new `_metar_cloud_cover_pct` helper that maps NWS sky-condition codes to percent (SKC/CLR=0, FEW=12, SCT=38, BKN=75, OVC=100, VV=100) and takes the maximum coverage across all reported layers (NWS total-sky-cover convention). (2) `daily_extremes.py::_gather_current_observation` now reads `kbos.cloud_cover_pct` as the cloud observation instead of the meaningless model `cur.cloud_cover` (which was just the forecast paired against itself, giving zero error — useless to fit). No fallback to model: when KBOS is down, obs_log omits the cloud field for that tick and the Joiner skips it. (3) `decay_fit.py` adds `"cc"` to FIELDS. (4) `decay_apply.py` adds `"cc"` to TARGET_ARRAY (mutates `hourly.cloud_cover` in place), CAPS (40% sanity cap — cloud varies enough that we shouldn't allow corrections that can flip clear↔overcast), ROUND_DIGITS (0), FIELD_BOUNDS (0–100%). Also preserves `raw_cloud_cover` before mutation (same pattern as wind/POP). (5) `forecast_snapshot.py` captures `cloud_cover` per hour as `"cc"`. (6) `forecast_error_log.py` adds `"cc" → "cloud_cover"` to FIELD_MAP. `corrections_debug.html` FIELDS gets an 8th entry; cloud uses 0-digit display + 25% "good" MAE threshold. Cloud observation is from KBOS (~15mi south, also coastal — better-than-KBVY proximity for marine-layer dynamics, though still imperfect for Wyman-specific microclimate). Layer 3/4 cloud corrections start at zero and need ~24h of pairs to populate.



## v0.6.21a • June 2, 2026
- **Fix:** v0.6.21 pressure wiring read `hourly["pressure_msl"]` but `normalize_hourly` (which runs before `add_corrected_hourly_arrays`) had already renamed the key to `pressure`. Result: `corrected_pressure_in` and `raw_pressure_in` arrays were empty in the payload even though `hyperlocal.bias_pressure_in` was correctly populated. One-line fix in `corrected_hourly.py` to read the post-normalize key.



## v0.6.21 • June 2, 2026
- **Pressure now flows through all 4 correction layers** (was only Layer 2 before, applied to a scalar `corrected_pressure_in` value — not the hourly forecast array). Six file changes wire pressure into the same pipeline as temp/humidity/wind/POP: (1) `hyperlocal.py` now writes `bias_pressure_in` (network mean − model, in inHg, octant-balanced like the others). (2) `corrected_hourly.py` builds two new hourly arrays — `raw_pressure_in` (model `pressure_msl` converted from hPa to inHg) and `corrected_pressure_in` (raw + Layer-2 bias). (3) `decay_apply.py` adds `"pr"` to TARGET_ARRAY / CAPS (0.30 inHg sanity cap) / ROUND_DIGITS (3) / FIELD_BOUNDS (25.0–32.0 inHg physical limits). (4) `decay_fit.py` adds `"pr"` to FIELDS so the daily Fitter computes per-lead and per-hour-of-day pressure correction curves. (5) `forecast_snapshot.py` captures `corrected_pressure_in` in each snapshot under the `"pr"` short key. (6) `forecast_error_log.py` adds `"pr" → "pressure_in"` to FIELD_MAP so the Joiner pairs forecast pressure against observed station pressure (both in inHg). `corrections_debug.html` FIELDS gets a 7th entry; drill-down, raw grid, mesonet grid, decay/diurnal grids, and forecast accuracy section all populate for pressure automatically (pressure-specific 3-digit rounding + 0.05 inHg "good" MAE threshold added). Layer 3 (decay) and Layer 4 (diurnal) corrections for pressure will start at zero and shrink toward the historical mean as the Fitter accumulates 24h+ of pressure pairs.



## v0.6.20 • June 2, 2026
- **POP correction reverted to flat-additive** (v0.6.5 → v0.6.19 used piecewise-scaled). Offline Brier-score analysis (`analysis/pop_calibration.py`, n=131,320 pp pairs) found the piecewise-scaled approach was barely better than no correction at all (Brier 768.9 vs raw 782.8), while the original flat-additive was meaningfully better (Brier 745.4). The "inflates clear-sky hours" concern that motivated the v0.6.5 piecewise change turned out to be over-cautious — the existing [0, 100] clamp in `FIELD_BOUNDS` already prevents pathological inflation, and per-lead corrections shrink toward zero where the model is reliable. POP now uses the same simple `final = raw - correction` as every other field. `POP_NOISE_FLOOR=2.0` constant removed.



## v0.6.19 • June 2, 2026
- **Debug page promoted to "Forecast pipeline":** four-part renovation. (1) **Renamed** from "Corrections debug" to "Forecast pipeline" — the page outgrew its dev-tool branding. New tagline under the H1 explains what it is. (2) **Sticky TOC navigation** at top of page with chips for Accuracy / Drill-down / L1 / L2 / L3 / L4 / Research — jumps land cleanly below the sticky bar via scroll-padding-top. Color-coded chips for Research (amber) and Accuracy (green). (3) **New "Forecast accuracy" section at top** answers the question the page was missing: IS the forecast actually working? Per-field cards show near-term MAE (last 24h at shortest available lead), 7d MAE, day-ahead MAE (lead 24h), and recent bias direction (over/under). Each card auto-flags good (≥ field threshold) vs poor with a checkmark or warning glyph. (4) **Tide research split out:** moved sub-sections 3d (tide-phase) and 3e (error vs tide elevation) from inside Layer 3 to a dedicated "Research — experimental signals" section at the bottom, renamed R1 and R2. Layer 3 now contains only the three applied-correction sub-sections (3a fitted, 3b live with-vs-without, 3c historical fits). Cleaner separation between "this layer is in production" vs "we're investigating this." Backend unchanged.



## v0.6.18 • June 2, 2026
- **Debug page restructured to 4-layer model:** the conceptual stack collapses old Layers 2 (network bias) and 3 (Kalman) into a single new Layer 2 called "Mesonet corrections" — Kalman gain was always a confidence scalar inside the mesonet pipeline, not a peer correction. Layers 3 (decay) and 4 (diurnal) are the renumbered old Layers 4 and 5. New Layer 2 has four sub-sections (2a octant coverage, 2b network bias estimate, 2c network confidence/Kalman, 2d post-mesonet forecast grid) plus the per-station map + Kalman-tracked offsets in a collapsed accordion. The drill-down chart drops to 4 lines (raw → +mesonet → +decay → +diurnal); the pre-K vs post-K split that used to be its own line is no longer cross-layer relevant — that internal detail stays inside Layer 2's own sub-panels. All sub-section labels renumbered (4a-e → 3a-e, 5a → 4a). Backend unchanged — pure frontend reshape of the existing data.



## v0.6.17a • June 2, 2026
- **Fix: station_bias.py wasn't updated for the 2.5mi expansion** — `_weight()` still had a `dist > 1.5` cap and required `elevation_ft` to be non-None for Tempest stations, so the 43 new stations were silently filtered out before getting Kalman-tracked offsets, meaning they wouldn't appear in the Layer 3 bias map or offsets table. Raised cap to 2.5mi (matching `hyperlocal.py`) and fall back to `elevation_ft = ELEVATION_FT` when missing (no elevation penalty), same as the hyperlocal fallback. Also relaxed the Tempest filter in `_build_station_list` to no longer require `elevation_ft`. After this deploys, new stations will start collecting Kalman state immediately, but the offsets table needs the 48h rolling window to populate meaningful per-station deltas — full population in ~2 days.



## v0.6.17 • June 2, 2026
- **Layer 2 station network: 2.5mi expansion + octant-balanced aggregation:** WU station list grew from 29 → 56 (added 27 mostly Salem-side stations); Tempest station list grew from 9 → 25 (added 16). Distance cap raised from 1.5mi to 2.5mi in both fetchers (`wu_scraper_realtime.py`, `tempest.py`) and in `hyperlocal.py`. Open-Elevation API used to populate elevations for the 21 new WU stations not previously in the hardcoded lookup. **The real math change:** `hyperlocal.py` no longer does a flat distance²-weighted mean across all stations — instead it groups stations by compass octant (8 sectors, N/NE/E/SE/S/SW/W/NW), computes a weighted bias per octant (still using dist² × exp(-elev_diff/30) within each sector), then takes an unweighted mean across non-empty octants. This prevents the dense Marblehead-side PWS cluster from dominating just because more stations happen to live there — a sparse Salem-side octant with 2 stations now contributes equally to the network bias as a dense Marblehead octant with 12. Same outputs (`weighted_bias`, `bias_humidity`, `corrected_pressure_in`), same downstream wiring through Layers 3/4/5 — internal aggregation only. Falls back to flat-weighted mean when fewer than 3 octants have data (rare at 2.5mi/81-station catchment). New `hyperlocal` fields: `aggregation` ("octant_balanced" vs "flat_fallback"), `octants_used` (count 0–8), `octant_coverage` (dict of label→station_count per octant). `bias_std` now measures geographic disagreement between octants (was per-station scatter) — this feeds Kalman gain in Layer 3, so K is now responsive to directional disagreement as well as station count.
- **Wind blend gets the same treatment:** `wind_blend.py`'s `select_observed_wind` was previously `max(candidates, key=gust)` — a pure max across all stations. A single Salem-ridge station seeing an exposure-specific gust spike would set Wyman's whole forecast wind. Now: tag each candidate with its octant (model/KBVY land in a neutral None bucket), take the max gust within each populated octant, then the MEDIAN across those octant maxes. Result: a gust seen by 1 station out of 81 won't survive (gets median-filtered out), but a genuinely regional gust visible in multiple octants does. Falls back to flat max when fewer than 3 octants have wind data. New `current.wind_aggregation` field documents which mode each tick used.
- **Debug page octant coverage panel:** new compact 3×3 compass-rose visualization under Layer 2 showing how many stations fed each octant this tick (red = empty/gap, amber = sparse/1 station, green = ok/≥2). Plus footer line showing which aggregation mode (octant_balanced vs flat_fallback) and the wind aggregation mode. Surfaces the geographic-coverage health of the network at a glance — if a sector goes dark, you see it immediately.



## v0.6.16 • June 2, 2026
- **Layer 3 (Kalman) now actually scales the hourly forecast bias, not just the Right-Now reading:** Caught while wiring v0.6.15's drill-down — `corrected_hourly.py` was applying the full `weighted_bias` to the 48h corrected_temperature array regardless of Kalman gain K, while `hyperlocal.py` was correctly applying `K * weighted_bias` only to the single Right-Now temp. Two places computing the same thing, with the forecast side ignoring the confidence throttling. Fixed by routing the hourly forecast through `K * weighted_bias` to match. Few stations or high station-to-station scatter → low K → forecast moves less toward the network reading, which is the whole point of the adaptive layer. User-visible impact: forecast temps will shift by `(1 - K) × weighted_bias` from yesterday's values (typically a few tenths to a degree); the new values are more conservative and more honest about network uncertainty. Humidity, wind, and POP not touched — they don't have Kalman scaling in the Right-Now flow either, so this matches existing scope. **Drill-down updated:** the per-field drill-down chart on `corrections_debug.html` now has a fifth layer line ("+ Layer 3, Kalman-scaled bias") between Layer 2 and Layer 4. For temperature the L2 and L3 lines visibly differ by factor K; for fields without Kalman scaling (humidity, wind, POP) the L2 and L3 lines overlap, which itself is informative. New Layer 3 info panel on the debug page surfaces the current K value, the un-scaled L2 temp bias, and the actually-applied L3 temp bias side-by-side.
- **Debug page polish:** (1) Layer 2 and Layer 3 now each have their own grid of 6 small per-field charts (raw dashed + post-layer-bias solid), matching the Layer 1 raw-model grid added in v0.6.15. Lets you see at a glance what the forecast looks like after each correction layer is applied — for temp, the L2 vs L3 shift is visibly different (full -3.14°F vs Kalman-scaled -2.04°F); for fields without bias the solid overlays the dashed. (2) The Layer 3 per-station bias map + offsets table are now wrapped in a collapsed `<details>` accordion (a CSS-styled native one, no JS framework); calls `_biasMap.invalidateSize()` on toggle so Leaflet tiles render correctly when expanded from a zero-size container. (3) Sections 4d (tide-phase curves) and 4e (error vs tide elevation) now display an explicit "Diagnostic only — not currently applied to the live forecast" callout box at the top of each, in an amber color to distinguish from the green-go applied sections. Was previously implicit; users now know these are research/exploration, not active corrections.



## v0.6.15 • June 2, 2026
- **`corrections_debug.html` reorganized by correction layer + single-field drill-down:** Page is now structured top-to-bottom by the actual correction stack — Layer 1 (Raw model) → Layer 2 (Station network bias) → Layer 3 (Adaptive Kalman calibration) → Layer 4 (Decay curves, with sub-sections 4a fitted curves, 4b live with/without, 4c historical fits, 4d tide-phase curves, 4e error vs tide elevation) → Layer 5 (Diurnal hour-of-day, sub-section 5a historical fits). Every existing chart kept; just regrouped under the layer that produces it. New "drill-down" section at the top: pick one field (radio buttons), then toggle which layers stack visibly (checkboxes for Raw, +Layer 2, +Layer 4, +Layer 5 = final). Play button animates the build-up — each layer fades in 0.9s apart so you can see the model start raw and watch each correction transform it into the live forecast. Layer 1 also gets its own per-field grid of raw-model curves for completeness. Layer 2 gets a compact info panel showing the actual bias values being applied right now (temp/humidity/wind/gust offsets, station count, Kalman gain). No backend changes — pure frontend reshape of the existing data.



## v0.6.14 • June 2, 2026
- **Layer 5 — diurnal (hour-of-day) correction:** New `diurnal_corrections.json` + `diurnal_corrections_history.json` (365-day retention) written daily by `decay_fit.py`. 24 bins, one per local hour. Same exponential-decay recency weighting as Layer 4. `decay_apply.py` now also subtracts the per-hour-of-day correction from each forecast hour based on that hour's local clock time (parsed from `hourly.times[i]`). Same physical bounds clamp (wind ≥ 0, humidity 0–100, etc.). New `decay_meta` fields: `diurnal_fitted_at`, `diurnal_cells_corrected`, `diurnal_cells_capped`. **Important math choice:** the per-hour values are normalized to be mean-zero across the 24 bins so they don't double-count the overall mean error (which Layer 4 already captures). Layer 5 contributes only the deviation-from-average diurnal cycle, not the bulk bias. New Section 7 on `corrections_debug.html` renders the diurnal curves stacked across days, same pattern as Section 5. Built because the offline `analysis/tide_hypothesis.py` revealed the diurnal signal is much stronger and cleaner than the tide signal — afternoon under-prediction of temperature (-3 to -5°F at lead 24h), wind speed/gust (+5-10 mph), humidity (+15%).



## v0.6.13 • June 2, 2026
- **Cloud Function memory bump 512MB → 1024MB to fix OOM on the daily Fitter tick:** Today's scheduled 03:07 EDT tick crashed with `'Memory limit of 488 MiB exceeded with 507 MiB used'`. The combination of the regular collector + the Fitter doing multi-lead time-series accumulation + the new NOAA tide fetch + history-file load/append pushed the function over its 512 MB ceiling. Bumped to 1024 MB in `Makefile`. Cost impact negligible (each tick is ~30s, function pricing scales with memory × time). Verified Fitter logic itself is fine — ran cleanly when triggered manually. The real test is tomorrow's scheduled 03:07 tick.

</details>


<details>
<summary><strong>v0.6.12 • June 1, 2026</strong></summary>

- **Real NOAA tide heights in Section 6, replacing the M2 cosine approximation:** `decay_fit.py` now fetches hourly harmonic tide predictions from the NOAA Tides & Currents API for Salem station 8442645 covering the time-series window. The tide overlay in Section 6 now shows actual Salem tide heights (peak-to-peak ~9 ft on typical days, ~12 ft on spring tides) instead of the old single-harmonic M2 cosine which was capped at ±4 ft. Falls back to the M2 cosine if the NOAA fetch fails, with `tide_source` field in the JSON documenting which was used. Section 5's reference cosine (still M2-only since the x-axis is *phase* not time) had its amplitude bumped from 4 to 5 ft to better match Salem's actual M2 component. The pre-v0.6.12 amplitude was visibly wrong — Salem tides regularly exceed 4 ft each direction.



## v0.6.11 • June 1, 2026
- **Section 6 lead-time selector:** `time_series_diagnostic.json` now contains per-hour mean error for 8 leads (0, 6, 12, 18, 24, 30, 36, 42h) instead of just lead 18h, under a new `errors_by_lead` key. File grew from ~9 KB to ~70 KB. Section 6 of `corrections_debug.html` gets a dropdown above the chart grid: pick which lead to render. Default 18h (where the offline tide hypothesis analysis showed the cleanest signal). Switching leads is instant — all data is loaded with the page; the dropdown just toggles which slice the 6 charts render. Lets the user explore whether the tide pattern is lead-specific (visible only at one lead) or general (visible across multiple leads). Backward-compatible read of the old single-lead `errors` key in case any pre-v0.6.11 payloads are still around.



## v0.6.10 • June 1, 2026
- **Wind gust floor + 4-layer doc reframing + annual curve retention:** Three small but real fixes in one commit. (1) `decay_apply.py` now clamps the corrected forecast values to physical bounds per field (wind ≥ 0, humidity 0–100, POP 0–100; temperature/dew-point intentionally unbounded). Without this, a large negative-sign correction at low raw values could push wind gust to negative mph. (2) `decay_fit.py` retention for `decay_corrections_history.json` and `tide_phase_corrections_history.json` extended from 30 days to 365 days so we can eventually watch curves evolve across a full annual cycle. Storage cost is ~3 MB/year per file — trivial. (3) `HOW_IT_WORKS.md`, `DATA_PIPELINE.md`, and `README.md` doc reframing from a 3-layer model (station bias / wind blend / decay) to a cleaner 4-layer model (raw model / station corrections including wind blend / adaptive station calibration / decay), separating the data-quality calibration step from the correction-application step. Wind blend is now correctly framed as a sub-method of Layer 2 rather than its own layer.



## v0.6.9 • June 1, 2026
- **Section 5 gets tide-elevation reference; Section 6 stays alongside:** Section 5's per-field phase-binned charts on `corrections_debug.html` now include a single gray reference cosine showing tide elevation across the M2 cycle (Salem M2 amplitude ~4ft, anchored to the reference high tide). Makes the x-axis interpretable at a glance: if the error lines bump up where the tide line bottoms out (around hour 6 since high tide = low tide), the bias tracks the tide. Section 6 (clock-time x-axis, error vs tide elevation over the last 7 days) stays alongside as the intuitive time-domain view. Two views of the same question — Section 5 is statistically rigorous (phase-binned, multiple days stacked), Section 6 is directly readable (do two squiggles oscillate together in real time). If both show the signal, it's robust.



## v0.6.8 • June 1, 2026
- **Section 6 — error vs tide elevation over time:** `processors/decay_fit.py` now also writes `time_series_diagnostic.json` — for each hour in the last 7 days, mean forecast error per field at lead 18h (the lead where the tide signal was strongest in `analysis/tide_hypothesis.py`) plus the approximate M2 tide elevation at that hour (single-component cosine model, Salem amplitude ~4ft). New Section 6 on `corrections_debug.html` renders this as 6 charts — one per field — with clock time on the x-axis, forecast error on the left y-axis, and tide elevation overlaid on the right y-axis. Read it as "do the two squiggles oscillate together?" — yes = tide drives the error, no = no signal at this lead/field. Complements Section 5 (the same question, statistically rigorous via phase-binning).



## v0.6.7 • June 1, 2026
- **Tide-phase decay curves + Section 5 historical watcher:** `processors/decay_fit.py` now also bins each pair by tide phase (12 bins across the M2 cycle of 12.4206h, anchored to a hardcoded Salem reference high tide) alongside the existing lead-h binning. Writes `tide_phase_corrections.json` and appends to `tide_phase_corrections_history.json` (30-day rolling) on every Fitter run. New Section 5 on `corrections_debug.html` renders one chart per field showing the historical tide-phase curves stacked, oldest pale gray → newest solid blue. The point of the historical view is the time-evolution test: stable curves across days → tide is the real driver; curves that drift across days → it's diurnal masquerading (because tide phase shifts ~50 min/day vs the 24h solar clock, so a clock-time pattern bins differently each day in tide-phase space). First fit shows clear humps at low-tide bins for wind speed (+3.8 mph) and gust (+9.3 mph), matching the lead-18h finding from `analysis/tide_hypothesis.py`. POP shows a dramatic −34% at the just-past-low-tide bin. Watching these stack over the next week will tell us if the patterns are physically real or alignment artifacts.



## v0.6.6 • June 1, 2026
- **POP reliability-diagram analysis script:** New standalone `analysis/pop_calibration.py` — same pattern as the tide-hypothesis script. Downloads `forecast_error_log.jsonl` + `decay_corrections.json`, replays every `pp` pair through three correction strategies (raw model / flat additive / piecewise scaled), bins resulting "corrected POP" against observed rain frequency, and renders a reliability diagram with Brier scores. CLI flag `--tau` tunes the noise floor for the scaled strategy. First run on ~80k pp pairs showed scaled is well-calibrated bin-by-bin but Brier-loses to flat because flat's aggressive mid-range boost partly compensates for a real ~25-point under-prediction the model has in the 30–60% range. Path forward when we have more post-storm data: tune T per data, or build proper isotonic regression.



## v0.6.5 • June 1, 2026
- **Piecewise-linear POP correction scaling:** `processors/decay_apply.py` no longer applies the flat additive POP decay correction. Previously, a fitted POP correction of −15% would push a raw 0% (clear sky) forecast to 15% corrected — claiming a 15% rain chance on what the model thinks is a definitely-clear hour. New formula scales the applied correction by the raw value: `applied = POP_NOISE_FLOOR + (raw_correction − POP_NOISE_FLOOR) × R/100`. At R=0 → applied ≈ POP_NOISE_FLOOR (= 2, a small "you don't know nothing" floor — and the clamp to [0,100] usually drops corrected back to 0). At R=100 → full raw correction applies. Linear in between. Only POP is scaled; temp/humidity/dew-point/wind/gust still use flat additive (no zero-floor problem there). Stopgap until we add proper isotonic regression or logistic POP calibration, which would learn the actual reliability curve from data. Bumping POP_NOISE_FLOOR to tune the noise-floor admission as we get post-storm data.



## v0.6.4 • June 1, 2026
- **Joiner emits pairs every tick, not just at top of hour:** `processors/forecast_error_log.py::_generate_new_pairs` dropped the `hour_key >= current_hour_iso` gate that held back obs from the in-progress hour. Pairs now flow into `forecast_error_log.jsonl` every 10-min tick instead of in hourly batches. Pairs are per-obs (not per-hour-aggregate), so emitting immediately is semantically identical to waiting — just smoother data flow. Compose appends jump from ~24/day to ~144/day; still well under the 5,300-component ceiling because the daily Fitter flatten resets it. The watermark in `forecast_error_state.json` now advances within the current hour instead of getting stuck at the prior hour's last obs. Pre-v0.6.4 the "wait for completed hour" rule was a vestigial state-machine simplification, not a correctness requirement.



## v0.6.3 • June 1, 2026
- **Section 4 age-color legend:** Each historical-curves card on `corrections_debug.html` Section 4 now has a small gradient-bar legend between the title and the chart — pale gray (oldest fit) → bold blue (newest), with the oldest and newest `fitted_at` timestamps labeled at the ends and a "hover line for date" hint at the right. Makes the color encoding readable without needing to know the rule.



## v0.6.2 • June 1, 2026
- **Decay-curve evolution watcher (history file + Section 4):** `decay_fit.py` now also appends each fit to `decay_corrections_history.json` in GCS — 30-day rolling, each entry is a full snapshot of that fit (fitted_at, n_pairs, weighting, corrections, n_samples). Storage cost is fractions of a cent per year. New Section 4 on `corrections_debug.html` ("Decay curves over time") renders one chart per field showing all historical fits stacked, color-gradient from pale gray (oldest) to solid blue (newest). Hover any line to see its fitted_at timestamp. Pairs naturally with the v0.6.1 recency-weighting — over the next 1–2 weeks you'll be able to watch the curves drift as nor'easter pairs age out and the post-fix humidity pairs gain weight.



## v0.6.1 • June 1, 2026
- **Recency-weighted Fitter (exponential decay, τ=14d):** `processors/decay_fit.py` now weights each pair by `exp(-age_days / 14)` instead of uniform 30-day window. Fresh pairs full weight; 10-day-old pairs ~half weight; 30-day-old pairs ~12%. Lets the fit track seasonal transitions (spring→summer is happening now) and recover faster from upstream data-quality changes (e.g. the May 31 humidity-bug fix in `obs_log.py` will dilute its contaminated pairs faster). Bin mean = `Σ(error × w) / Σw`. `n_samples` in output stays as unweighted raw counts for display. New `weighting` block in `decay_corrections.json` documents the parameters. Updated `docs/HOW_IT_WORKS.md` and `docs/DATA_PIPELINE.md` Piece-3 sections to match.

</details>


<details>
<summary><strong>v0.6.0 • May 31, 2026</strong></summary>

- **Milestone bump** marking the completion of the full three-layer correction pipeline. The headline addition across the 0.5 series is the new Layer 3 (lead-time decay correction) system: a four-piece pipeline (Logger → Joiner → Fitter → Apply) that measures the model's own past forecast errors at every lead hour, fits a per-(field, lead_h) residual daily, and subtracts it from the user-facing 48-hour forecast each tick. Temperature, humidity, dew point, wind, gust, and precipitation probability are all now lead-time corrected with per-field sanity caps. Companion tooling: combined corrections debug page (`corrections_debug.html`) with fitted curves, live forecast with vs without decay, and a per-station bias map; PWA Corrections-card section showing the +24h adjustment per field; offline tide-cycle hypothesis tool (`analysis/tide_hypothesis.py`) with diurnal-control stratification; complete docs sweep (`HOW_IT_WORKS`, `README`, `DATA_PIPELINE`, `CLAUDE_RULES`); humidity-contamination bug found and fixed. Detailed per-version notes for everything in this milestone are below in the v0.5.229–v0.5.244 block.

---


## v0.5.229–v0.5.244 • May 31, 2026
* **obs_temp_log humidity fix — store station-corrected, not raw model (v0.5.244):** `_gather_current_observation` in `daily_extremes.py` was passing `cur.get("humidity")` (raw HRRR model) to `obs_log.py`. The Joiner then paired the snapshot's `corrected_humidity` (= raw + Kalman bias) against this raw "observed" value, so the Fitter saw the bias itself as "error" and Piece 4's decay correction effectively undid Layer 1 — humidity at lead 0 was getting +10% bias added and ~9% decay subtracted, netting ~0 change. Fix: pass `hyp.get("corrected_humidity")` (station-network value, falls back to `cur.humidity` if missing). Matches how `corrected_temp` is sourced two lines above. Dew point in obs_log re-derives from `corrected_temp` + `humidity` via Magnus, so it now uses two consistent corrected inputs instead of the mixed pair. Verified at the 20:27 EDT tick: `obs_temp_log` humidity entry = 96.6 (matches `hyperlocal.corrected_humidity`) where the previous tick stored 87 (raw). Dew point jumped from 50.1 to 53.4°F at the same tick, expected — magnus now consistent. Decay correction for humidity will drift toward the real residual over the next ~2 weeks as new corrected pairs dilute the contaminated ones in the rolling pair-log window.
* **Docs sweep + Chart.js version sync (v0.5.243):** `README.md` updated — "Cloud Run service" → "Cloud Functions (Gen 2)", "ECMWF 10-day" → "GFS 7-day", "29 stations" → "up to 29", processor list rewritten to group by correction layer (Layer 1 / Layer 3 decay / derived scores / helpers), added pointer to `corrections_debug.html` and `analysis/`. `docs/CLAUDE_RULES.md` re-synced with the root `CLAUDE.md` (was missing rules #11, #12, and the localhost-testing addition to #8). `docs/DATA_PIPELINE.md` got a new "DECAY PIPELINE (LAYER 3)" section detailing all four pieces, marked Improvements #1 and #2 as RESOLVED in v0.5.235, fixed the actively-wrong "Decay: NONE — Same bias applied to all 48 hours" claim in the Temperature forecast section, updated humidity forecast section to mention Layer 3, and refreshed the Correction Status Matrix to show Layer 3 columns. `corrections_debug.html` bumped Chart.js 4.4.1 → 4.4.4 to match `index.html`.
* **HOW_IT_WORKS rewrite (v0.5.242):** Total rewrite of `docs/HOW_IT_WORKS.md`. Replaces the implicit "single bias correction" model with the actual three-layer pipeline (station-network bias / wind blend / lead-time decay correction). New section explaining the decay-curve pipeline as four pieces (Logger / Joiner / Fitter / Apply). Updated source list (Open-Meteo HRRR+GFS, Pirate Weather, WU, Tempest, KBVY, KBOS, NWS gridpoints, GoMOFS, NOAA tides, eBird, Gemini with Groq fallback). New sections for fog/sea-breeze/thunderstorm detectors, tides, pressure trend, dock-day score, hair-day score. Removed the now-false "flat bias across all 48 hours" claim. Added pointers to the corrections debug page and the live data URL.
* **Station bias map on corrections debug page (v0.5.241):** Section 3 gets a Leaflet map above the table. One colored circle marker per station (with both lat/lng and a temp offset available), colored on a diverging hue scale (cool blue for stations that under-read, warm red for over-read, neutral gray near zero, clamped to ±3°F). Wyman Cove marked with a white-bordered dot at `42.5014, -70.8750`. Click any marker for popup with station_id, distance, and temp/day/night offsets. Legend in bottom-right. Map auto-fits to include all plotted stations + Wyman Cove. Tile layer is OpenStreetMap (free, no key). Spatial pattern visible at a glance — e.g., consistent warm-side bias clustering in one direction would point to a microclimate effect the Kalman tracker is already correcting.
* **Tempest distances in corrections-debug bias table (v0.5.240):** The new distance column was only checking `wu_stations.stations[]` and missing Tempest stations entirely (9 of 11 "blanks" were Tempests). Now also looks up `tempest.stations[].distance_mi`. Remaining blanks (~2) are genuine — WU stations the bias tracker has from the 48h history that didn't return data this tick.
* **Station distance column on corrections debug page (v0.5.239):** Section 3 (per-station bias) gets a new "Dist (mi)" column, populated from `weather_data.wu_stations.stations[].distance_mi`. Default sort is now distance ascending (nearest first) instead of |temp| descending. Click any column header to sort by it — distance/station sort ascending by raw value, bias columns still sort descending by magnitude. Stations without a distance match (e.g., Tempest stations) show "—" and sink to the bottom.
* **Tide vs diurnal stratification in analysis script (v0.5.238):** Extended `analysis/tide_hypothesis.py` to also bin errors by hour-of-day alongside tide phase, plus a stratified diagnostic. Per-field figure now shows two rows × 5 leads: top row = error vs M2 tide phase (existing), bottom row = error vs local hour-of-day (new). Side-by-side comparison surfaces whether a "tide" pattern is actually just diurnal aliasing (12.42h tide period vs 12h half-diurnal solar). New companion figure `stratified_<field>.png` per field: tide-phase error plotted as separate lines for each of 4 hour-of-day strata (night / morning / afternoon / evening). If all 4 lines share the same shape → tide is the real driver. If they differ wildly → diurnal is.
* **Tide-cycle hypothesis analysis script (v0.5.237):** New standalone `analysis/tide_hypothesis.py` — pure offline analysis, touches no app code. Downloads `forecast_log.json` (4 days of corrected 48h snapshots) and NOAA harmonic tide predictions for Salem (station 8442645). Synthesizes forecast-vs-observed pairs by treating each snapshot's `lead_h=0` entry as the "observation" for its run hour (extends usable obs span to ~99h vs the ~28h currently in the live pair log). Bins errors by M2 tide phase (12.42h period, 12 bins) at the observation time and renders one PNG per field showing mean error per phase bin across 5 leads (6/12/18/24/36h). First run produced 121,354 pairs spanning 8 tide cycles; preliminary signals visible in wind/gust and humidity at mid-leads but tide vs diurnal still confounded.
* **Corrections card decay section + combined corrections debug page (v0.5.236):** Weather-tab Corrections card gets a new "Forecast Decay Corrections ▾" collapsible below the existing Station Calibration Offsets, mirroring its style. Header line shows applied/fitted timestamps and cells-corrected count; mini-table shows the per-field correction at +24h lead (the most actionable forecast horizon); footer links to the full debug page. `decay_apply.py` now stashes `per_field_24h` in `decay_meta` so the PWA doesn't need a separate fetch. `wind_blend.py` snapshots `raw_wind_speed`/`raw_wind_gusts` before its in-place mutation, and `decay_apply.py` snapshots `raw_precipitation_probability` before its mutation — gives downstream (debug page) access to raw-model values for the three fields that get mutated in place. `decay_debug.html` renamed to `corrections_debug.html` (`git mv` preserves history); page title/h1 updated; Section 2 charts now show a third dotted "raw model" line (computed in JS via a port of `magnus_dew_point_f` for dew point, the others read straight from the new `raw_*` arrays); new Section 3 renders a sortable per-station bias-offset table covering all 34 stations across temp / temp_day / temp_night / humidity / pressure (the existing card shows only the top 8 temp offsets), plus a header stats panel with weighted_bias, kalman_gain, bias_std, and the KBVY anchor.
* **Decay-curve Apply + live-forecast debug view (v0.5.235):** New `processors/decay_apply.py` reads `decay_corrections.json` each tick and subtracts the per-(field, lead_h) mean error from the hourly arrays (`corrected_temperature`, `corrected_humidity`, `corrected_dew_point`, `wind_speed`, `wind_gusts`, `precipitation_probability`) — runs after `trim_hourly_to_current_hour` so array index == lead_h, and after the forecast snapshot is logged so the Fitter's residual stays a fair measurement. Sanity caps per field (5°F / 5°F / 20% / 10mph / 15mph / 25%) prevent any pathological future fit from blowing up the forecast. Falls back to a clean no-op if the corrections file is missing, malformed, or stale (>7 days old). After applying corrections, recomputes `corrected_apparent_temperature` and `corrected_absolute_humidity` from the now-corrected base values so derived arrays stay self-consistent. Stamps `weather_data["decay_meta"]` with `fitted_at`, `applied_at`, `cells_corrected`, `cells_capped` so the debug page can show whether decay was actually applied to the live payload. Debug page extended with a second section ("Live forecast — with vs without decay correction"): one chart per field overlaying the live forecast against the reverse-derived alternative line, with labels that adapt depending on the `decay_meta` state.
* **Decay-curve debug page (v0.5.234):** New standalone `decay_debug.html` (not linked from the PWA) fetches `decay_corrections.json` from GCS and renders one Chart.js line chart per field (6 total) showing mean error vs `lead_h`, with sample counts as a faint bar overlay on a secondary axis. Shows fitted-at timestamp, total pair count, and per-field |mean| summary. Renders an empty state if `decay_corrections.json` doesn't exist yet.
* **Decay-curve Fitter (v0.5.233):** New `processors/decay_fit.py` reads `forecast_error_log.jsonl` once a day (gated on the 03:X7 tick in `collector.main()`), computes mean signed error per `(field, lead_h)` bin across all 6 fields × 48 lead bins, and writes `decay_corrections.json` to GCS. Same pass also prunes the input to a 30-day rolling window and rewrites it as a single non-composed blob — resets the GCS compose component count back to 1 (Joiner's compose-append would hit the 5,300-component ceiling around day 36 without this). Streaming I/O via `blob.open` keeps memory bounded regardless of file size (~1.3 GB at steady state). Fitter call placed after the main `weather_data.json` upload so a slow Fitter cannot delay the user-facing payload. Piece 3 of 4 in the decay model; Piece 4 (Apply) waits for ≥1 week of fitted data.
* **Forecast-error Joiner (v0.5.232):** New `processors/forecast_error_log.py` pairs every 10-min obs entry against each `forecast_log.json` snapshot that predicted its hour, appending one row per `(obs × snapshot × field)` to `forecast_error_log.jsonl` via GCS compose (constant per-tick cost regardless of file size). Watermark tracked in `forecast_error_state.json`. First run produced 243,648 pairs across 6 fields. Foundation for the decay-curve fitter.
* **Collector refactor (v0.5.231):** AI briefing wiring tail moved from `collector.main()` into `briefing_ai.py` as `apply_briefing_to_weather_data(data)` (handles the try/cached_at/sources["gemini"] dance + failure path). Hourly-array trim block extracted into a new `processors/hourly_trim.py` as `trim_hourly_to_current_hour(data)`. collector.py 406 → 380 lines. Verified live by 8:57 run.
* **Frontend split (v0.5.230):** tab navigation extracted from `app-main.js` into `js/tab_nav.js` — `showTab` + swipe-nav IIFE + bottom-tab-bar sync wrapper + tab-restore IIFE, all four pieces moved together so the existing wrap-then-call execution order is preserved. app-main.js 983 → 835 lines.
* **Docs cleanup (v0.5.229):** stripped 23 stale code-line-number references from `DATA_PIPELINE.md` (most had been wrong for months — they pointed into `app-main.js` line 3787 etc., which hasn't existed since the file was split). Doc now uses file paths only as navigation; new note explains why. Updated stale version header. Also fixed the "Frontend" line in `CLAUDE.md` + `docs/CLAUDE_RULES.md` to reflect the modular `js/*.js` structure instead of just naming two files.

</details>


<details>
<summary><strong>v0.5.201–v0.5.228 • May 30, 2026</strong></summary>

* **Frontend split (v0.5.228):** theme + pressure-unit helpers (~95 lines: `setTheme`, `applyTheme`, `updateSettingBtns`, `isLight`, `chartTextColor`, `chartGridColor`, `hpaToInhg`, `fmtPressure`, `rerenderPressure`, on-load IIFE) extracted into `js/theme.js`. app-main.js 1,071 → 983 lines — under 1,000 for the first time.
* **Frontend split (v0.5.227):** formatting helpers (`fmtLocal`, `fmtRelAge`, `toCompass`) extracted from `app-main.js` into `js/format.js`. Pure functions, no DOM or state. Loaded before app-main.js so they stay globally available. app-main.js 1,095 → 1,071 lines.
* **Frontend split (v0.5.226):** Right Now card render (~320 lines — every visible field, from big temperature and thermometer mercury through lifestyle scores) extracted from `app-main.js` into `js/right_now.js` as `renderRightNow(data)`. Done in 6 incremental chunks with localhost verification between each. app-main.js 1,416 → 1,095 lines.
* **Frontend split (v0.5.224–v0.5.225):** pressure-alarm + storm-mode logic (~60 lines) extracted into `js/alarms.js` as `renderPressureAlarm(data)` + `renderStormMode(data)`; NWS alerts panel + TEST-alert filter (~40 lines) extracted into `js/alerts.js` as `renderAlerts(data)`. app-main.js 1,513 → 1,416 lines.
* **Tooling fix (v0.5.223):** version pill was missed in the v0.5.222 commit due to an Edit ordering error; this commit catches it up.
* **Frontend split (v0.5.221–v0.5.222):** version-update detection + refresh-on-return (~78 lines) extracted into `js/version_check.js`; pull-to-refresh gesture (~64 lines) extracted into `js/pull_refresh.js`. app-main.js 1,654 → 1,513 lines.
* **Docs (v0.5.220):** consolidated same-day entries in `CHANGELOG.md` — May 27, May 28, and today's entries each collapsed into a single range header with concise themed bullets, matching the established format for earlier dates.
* **Right Now click-throughs (v0.5.215):** tapping a value field in the expanded Right Now card now navigates to the matching detail card; tapping outside the detail returns you to Right Now. Modal's `outsideHandler` was eating the synthetic click on the sibling target — fix dismisses the source's modal state before navigating.
* **Frontend dedup (v0.5.215–v0.5.217):** seven hyperlocal-link click handlers → one `wireHyperlocalLink()` helper; seven dimmed-suffix span literals → one `dim()` helper; twelve weather-art SVG conditionals → `WEATHER_GRAPHICS` lookup table with a `matchWeatherType()` precedence helper.
* **Collector formula consolidation (v0.5.201):** Magnus dew-point (4 copies) and Steadman feels-like (2 copies) collapsed into `utils.py` helpers.
* **Collector cleanup (v0.5.202):** 8 mid-function `pytz`/`datetime` imports hoisted; `_obs_log` initialized up front so the `NameError` catch goes away; unused `now_utc` removed.
* **Collector module extractions (v0.5.203–v0.5.214, v0.5.218–v0.5.219):** carved out of `collector.py` into focused modules — `wind_blend`, `corrected_hourly`, `gcs_io`, `obs_log`, `forecast_snapshot`, `daily_extremes`, `current_derived`, `fog_metrics`, `hourly_7day`, `normalize`, `stale_cache`, `fetch_parallel`, `fetch_all`. `concurrent.futures` and 16 now-unused fetcher imports removed. collector.py 1,653 → 406 lines (−76%). Zero behavior change throughout.

</details>


<details>
<summary><strong>v0.5.197–v0.5.200 • May 28, 2026</strong></summary>

* **Collector:** obs_temp_log now records observed precip rate from WU rain gauges (replaces forecast model precip); WU aggregate also includes `precip_rate_in` and `precip_today_in` from station network. Earlier in the day: obs_temp_log added observed humidity and dew point (Magnus formula from temp + RH).
* **Forecast snapshots:** Each hourly entry now includes dew point (`dp`) and precipitation probability (`pp`) — enables POP calibration and dew point decay analysis alongside temp/wind.
* **Settings drawer:** "Data generated" always shows relative time ("just now", "5m ago") — previously switched to absolute time when a background refresh fired while the drawer was open.

</details>


<details>
<summary><strong>v0.5.190–v0.5.196 • May 27, 2026</strong></summary>

* **Outside card (Lifestyle tab):** New card scoring current outdoor conditions — rain, wind, comfort (dew point), UV (hidden when unavailable) — with overall label (Great/Good/Fair/Poor/Stay inside), per-factor bars, and best-window hint when current conditions are poor. Pollen and AQI placeholders for future additions.
* **Forecast snapshot logger:** Collector now writes `forecast_log.json` to GCS each run — 48h corrected temp, humidity, wind speed, gusts — rolling 14-day window. Foundation for decay curve calibration.
* **UV in Watch For:** Briefing Watch For section now shows UV index when today's peak is ≥ 6 (high or above) — dimmed at 6–7, orange at 8–10, red at 11+. Hidden on low-UV days.
* **Watch For links:** UV and Heat stress rows now navigate to the Outside card on the Lifestyle tab when tapped.
* **Watch For layout fix:** Wrapped rows in brief-rows container so thin item dividers and thick section separator render correctly; UV label no longer dimmed.
* **UV Watch For time gate:** UV warning now only appears when UV ≥ 6 hours remain today — hides after the UV window has passed (e.g. evenings).
* **Briefing prompt fix:** Groq/Gemini no longer append "no change since last update" when forecast is stable — prior forecast is only mentioned when something shifted meaningfully.

</details>


<details>
<summary><strong>v0.5.184–v0.5.189 • May 23–26, 2026</strong></summary>

* **Sunset scorer: horizon low cloud fix:** 50mi low cloud now weighted 60% in penalty calculation — a blocked distant horizon correctly scores Fair/Poor even when local sky is clear. Canvas bonus (mid/high cloud) only activates when the distant horizon is actually clear enough to back-light it.
* **Heat stress in Watch For:** WBGT computed from corrected wet bulb, temperature, and solar radiation — appears in briefing Watch For section when peak daytime WBGT ≥ 80°F, with Caution/Moderate/High risk labels
* **Rain intensity in briefing context:** Peak rain rate (in/hr) and label (drizzle/light/moderate/heavy/torrential) now included in Gemini/Groq precip context line
* **Sky & Precip chart intensity shading:** Rain bars shade from pale blue (drizzle) to dark blue (heavy) by hourly precipitation rate — intensity visible at a glance
* **Obs chart pressure smoothing:** 9-point moving average applied before scaling — eliminates staircase artifact from 0.01 inHg sensor quantization
* **Obs chart sky background:** Per-column cloud-cover gradient (same logic as 48h forecast) — collector now writes cloud_cover to obs log each run; x-axis label spacing fixed to prevent overlap near chart start
* **Sunset scorer: high cirrus fix:** highBonus cap now scales from 0.30→0.55 as horizon clears — high cirrus with a clear horizon correctly scores Very Good instead of Fair (ground-truth: May 26 dramatic cirrus sunset)
* **Collector crash fix:** forecast_text.py returns None when daily high/low are None — prevents TypeError during upstream Open-Meteo outages


## v0.5.17–v0.5.17c • April 27–28, 2026
* **Single Source of Truth for Temperatures**
  * Collector computes `derived.today_high/low` from observed past + corrected forecast
  * Observed temp log (`obs_temp_log.json`) tracks hourly corrected readings
  * All display paths read from `derived` — eliminated 6+ redundant bias computations
  * Corrected dew point and feels-like computed once in collector
  * Forecast text uses derived high/low
* **Gemini Briefing Discipline**
  * Wind impact score is authoritative; raw speed demoted to context
  * Tomorrow high/low sent to prevent invented temperatures
  * Test alert filtering in frontend and Gemini input
* **Infrastructure**
  * Open-Meteo calls sequential (rate-limit sensitive); non-OM calls parallelized


## v0.5.0–v0.5.15 • April 25–26, 2026
* **Briefing Tab — AI-Powered Weather Briefing**
  * New first tab: Gemini headline + subheadline, stat boxes, conditional data rows
  * Template fallback when AI unavailable
  * Cross-card navigation: tap any row to open its detail card
  * Lifestyle section: sunset, beach day, hair day scores
  * Watch For section: wind impact, frost risk, fog, sea breeze alerts
  * Sun/tide/moon/birds rows
  * Wind chill and heat index display
* **PWA Install Prompt**
  * iOS action sheet style; Android native beforeinstallprompt
* **Settings**
  * Changelog, data pipeline, licenses behind "Nerd Stuff" toggle
  * Bird hotspot links open in OpenStreetMap


## v0.4.78–v0.4.82 • April 21–24, 2026
* **Hair Day — Hair Type Selector**
  * Four profiles: Straight, Wavy, Curly, Coily with tuned AH curves and wind thresholds
  * Wind scoring added (10% weight) using first-bad-hour logic
  * Restyle opportunity detection
* **Birds Card**
  * eBird sightings grouped by hotspot, sorted by distance
  * Notable species highlighted; clickable links to eBird and maps
* **Tab Reorganization**
  * Weather tab: objective data and forecasts
  * Hyperlocal tab: derived scores and curated metrics
  * Feels Like, Fog, Sea Breeze moved to Weather tab
* **Sea Breeze Fix**
  * 0% likelihood no longer shows as "No data"
  * Collapsed tile shows actual wind direction


## v0.4.65–v0.4.77 • April 20–21, 2026
* **Hair Day Card**
  * Scoring based on Absolute Humidity with inverted-U curve (sweet spot 4-5 g/m³)
  * Morning-weighted aggregation; precip type matters (snow/freezing rain penalized more)
* **Card Modal System**
  * Fixed-position modal with backdrop, max-height with internal scroll
  * Measured header/tab bar heights for correct positioning
  * Tap backdrop or Escape to dismiss
* **Pirate Weather Next Hour**
  * Fixed false triggers on raw intensity when probability is 0%
  * Always-visible header badges with colored dot for active state
* **UI Polish**
  * Card open animation smoothed (removed bouncy overshoot)
  * Dead top tab nav HTML removed
  * Right Now card lifestyle scores show /100 format


## v0.4.50–v0.4.61 • April 18–20, 2026
* **Pirate Weather Integration**
  * Minutely precip, solar irradiance, CAPE
  * Next-hour rain badge with 60-bar chart and plain-language summary
* **Feels Like Card**
  * 48-hour Chart.js line chart with hover data bar
* **Sunset Headline**
  * Plain-English summary above day grid
* **Infrastructure**
  * GCS migration: collector on Cloud Functions + Cloud Scheduler
  * weather_data.json served from GCS bucket
  * Stale page indicator (gear/refresh turn red when data >2h old)


## v0.4.34–v0.4.48 • April 12–18, 2026
* **Corrected Values Audit**
  * All display paths use corrected temp, humidity, wind, pressure, dew point
  * Forecast temperatures corrected for today and tomorrow
* **UI/Native App Polish**
  * Fixed header with frosted glass effect
  * Storm alerts consolidated into badge modal
  * Swipe-down to dismiss settings and alert modals
  * Gradient backgrounds persist into expanded cards
* **Scoring Refinements**
  * Dock Day: below 50°F scores 0, thresholds raised
  * All scores unified to 1-100 scale
* **Station Network**
  * Expanded from 15 to 36 WU stations


## v0.3.1–v0.3.18 • March 21–30, 2026
* **Forecast Text Generator**
  * NWS NBM gridpoint integration for temperature overrides
  * 850mb precipitation type classifier
  * Wet bulb temperature display
  * Morning/afternoon cloud split for sky narratives
* **Wind System**
  * Wind chart redesign (time horizontal, speed vertical, worry zones)
  * Max(KBVY, WU) for current conditions; observed wind blended into forecast
  * Wind exposure thresholds tuned for waterfront
* **Overhead Tab**
  * Live aircraft tracker with Mapbox map
  * Route validation, private aircraft detection, selected plane highlighting
* **48-Hour Chart**
  * Sky condition bars, touch-action fixes, consolidated data bar


## v0.1.0 • Late 2025
* **Initial Build**
  * Multi-model weather (GFS, HRRR, ECMWF via Open-Meteo), tides, buoy, NWS alerts
  * Multi-tab layout (Weather / Wind / Almanac / Radar / Sources)
  * KBOS / KBVY / PWS observed conditions

</details>


<details>
<summary><strong>v0.5.182–v0.5.183 • May 22, 2026</strong></summary>

* **Obs chart fixes:** Wind line changed to purple, dew point to vivid blue — distinct from teal gust bars; x-axis day label always shown at chart start; 6h tick labels now fire on entries at :07 instead of requiring exact :00
* **Almanac card previews:** Today card now shows Sunrise/Sunset times and daylight hours (was reading wrong data path); Frost Log now shows last freeze date, days since, and season freeze-day count (was reading nonexistent field)

</details>


<details>
<summary><strong>v0.5.171–v0.5.181 • May 21, 2026</strong></summary>

* **Observed history chart:** New full-width card at the bottom of the Almanac tab showing past 24h of 10-minute observed readings — temp (orange), dew point (blue dashed), pressure trend (gray scaled), wind (teal dashed), and peak gust (teal bars). Data bar on hover shows temp, dew point, pressure, wind/gust, and wind impact label
* **Obs log redesign:** Collector now records a snapshot every 10 minutes (instead of one entry per hour) and keeps 24 hours of history. Each entry includes temp, precip, gust, wind speed, wind direction, dew point, and pressure
* **Wind impact in obs data bar:** Uses the real `combinedWindImpact` + `worryLevel` functions (with site-specific exposure table) to show impact label per reading when direction is available
* **Fog card atmospheric context:** Cloud base (~X,XXX ft), freezing level (X,XXX ft), and precipitable water (X.X mm) displayed as tiles above the fog card footnote
* **Low cloud cover in fog model:** HRRR `cloud_cover_low` feeds fog probability — +10% at ≥90% low cloud, +5% at ≥70%, −8% below 20%
* **Freezing level in precip type:** `freezinglevel_height` from HRRR overrides wet-bulb classification — >5,000 ft + wb>30 → rain; <1,500 ft + wb<33 → snow
* **PWAT in briefing:** Precipitable water ≥25mm logged in Gemini/Groq context when thunderstorms are active or on watch — "heavy rainfall rates likely with any storm"
* **Cloudflare Worker proxy:** `data.wymancove.com` proxies GCS bucket — fixes data loading in Firefox Focus and DuckDuckGo which block `storage.googleapis.com`
* **counter.dev analytics:** Replaced Microsoft Clarity (blocked by Safari ITP, useless for iOS PWA users) with counter.dev — privacy-friendly, works on iOS Safari
* **Sunset scoring fix:** Mid/high cloud with clear horizon now scores correctly — 0% low + 100% mid scores Spectacular instead of Poor. Low cloud is the blocker; mid/high cloud is the color canvas
* **Dead close button cleanup:** Removed 23 hidden `card-close-btn` elements from all cards and dead querySelector logic from ui.js


## v0.5.169–v0.5.170 • May 21, 2026
* **Briefing historical context:** Yesterday's high, precip total, and peak gust now logged in `obs_temp_log.json` and passed to Gemini/Groq prompt — model can frame today relative to yesterday without a hard rule (e.g., "sharp cooldown after yesterday's heat")
* **Groq model upgrade:** Fallback briefing model upgraded from `llama-3.1-8b-instant` to `llama-3.3-70b-versatile` for better prompt compliance (temperature ranges, no hallucinated context)
* **Stat box lining numerals:** `font-variant-numeric: lining-nums` on briefing stat values — fixes old-style figure misalignment where "7" sat visually lower than "8" in Playfair Display
* **Sky text font race fix:** Sky condition fit-sizing re-runs after `document.fonts.ready` — fixes stale small size on cold cache when Playfair loads after initial measurement
* **Source error labels:** Raw Python exception strings parsed to readable labels ("Connection reset", "429 Rate limited", "404 Not found", etc.)
* **Settings alert dot:** Now only lights for critical source failures (GFS, HRRR, WU, Pirate Weather, NWS Alerts, both briefing models down) — KBVY, KBOS, eBird, buoy, tides fail silently

</details>


<details>
<summary><strong>v0.5.159–v0.5.168 • May 20, 2026</strong></summary>

* **Groq fallback (briefing):** Groq API (`llama-3.1-8b-instant`) added as fallback briefing generator when Gemini is unavailable; model tagged on every saved briefing; Sources card shows Gemini/Groq with active/standby indicator and age
* **Gemini no-redundancy rule:** Prompt now instructs model to ensure headline and subheadline carry different information — headline sets the story, subheadline adds detail
* **Briefing stale indicator:** Dim italic "headline from Xh ago" shown below headline when briefing is >90 minutes old
* **Corrections card bias:** Display now shows actual applied delta (corrected − model) rather than raw weighted_bias, correctly reflecting the Kalman-scaled correction
* **Wind briefing row:** Reformatted to "Light winds at the cove (9 mph NW, gusts 23)" — concise and location-specific
* **Birds briefing row:** "X species spotted nearby · Last 48h" format
* **Briefing lifestyle rows:** Numeric scores removed; label-only display (e.g., "Good hair day" not "Good hair day (78/100)")
* **Terminology audit:** mph spacing fixed throughout; MPH→mph; °F symbol normalized; Peak Impact, Risk Level, Last 48h capitalization corrected

</details>


<details>
<summary><strong>v0.5.145–v0.5.158 • May 19, 2026</strong></summary>

* **Thunderstorm card:** New weather tab card with severity status (Clear/Watch/Active/Severe), CAPE current + 12h peak, color-coded hourly CAPE bar chart, lightning count and closest distance; click-through from Watch For rows and alert drawer
* **Thunderstorm detector (collector):** `processors/thunderstorm.py` computes severity from Tempest lightning (MAX across 9 stations, not sum) and Pirate Weather CAPE; `sky_override` sets condition to "Thunderstorm" or "Severe Thunderstorm" when active
* **Thunderstorm in alert drawer:** Watch/Active/Severe states appear in Active Alerts modal with click-through to thunderstorm card; alert badge dot lights up
* **Watch For ordering:** Lightning/thunderstorm row moved before precip bar so NWS alerts are never split by rain
* **Lightning count fix:** Was summing across 9 Tempest stations (9× inflation); corrected to MAX
* **Wind chart observed override:** Current hour substituted with hyperlocal observed speed/direction so chart reflects actual conditions during convective events (forecast direction can be wrong)
* **Gemini rain hallucination fix:** Explicit "No significant rain expected" signal sent when max POP < 20%, preventing stale storm context from carrying forward
* **CAPE chart:** Height increased 160→200px; layout padding added to prevent x-axis labels overlapping footnote; footnote top margin added for breathing room
* **Card close button artifact:** `.card-close-btn` default changed to `display:none` to fix flash on collapse
* **Fog dissipation timing:** Collector computes `fog_dissipation_hour` from 18h hourly fog probability; expanded fog card shows "Expected to clear by Xpm"; collapsed tile front shows "Clears by Xpm" when risk ≥20%
* **Fog card text color:** Dissipation line inherits card text color instead of hardcoded rgba(255,255,255,0.7) — readable in both light and dark mode
* **Briefing stat boxes:** Now/High/Sky boxes in briefing header click through to their respective cards
* **Settings relative times:** Data generated and code loaded times shown as relative ("3 min ago") instead of absolute timestamps
* **Feels Like consistency:** Briefing heat index row uses `der.heat_index` (Kalman-corrected) for display; shade AT falls back to JS computation if collector value missing
* **Heat index threshold:** Lowered RH threshold 40→35% so heat index activates in more conditions; Tonight briefing row click-through added; feelslike badge fallback improved
* **Update-reload loop fix:** Version check suppressed for 30s after an update-triggered reload to prevent infinite reload loop
* **Feels Like chart:** Three distinct lines — In shade (AT formula, solar=0), Full sun (AT + direct_radiation), Air temp; legend updated; "In shade" replaces "Feels Like" label for clarity
* **Gemini briefing:** Switched to gemini-2.5-flash (flash-lite returned 503); maxOutputTokens 200→2048 to accommodate thinking token overhead; in-memory backoff prevents retry storm on failure
* **Pirate Weather cloud cover fallback:** Sky/Precip card no longer goes blank when Open-Meteo HRRR is down; collector injects Pirate Weather 48h cloud cover as fallback

</details>


<details>
<summary><strong>v0.5.125–v0.5.144 • May 15, 2026</strong></summary>

* Tab bar icons repositioned to sit flush above the home indicator on iOS (align-items: flex-start, safe-area bottom padding corrected)
* Lifestyle tab tab bar height normalized: min-height 100svh on all tab views prevents short-content tabs from rendering the fixed bar differently
* iOS tap highlight flash and long-press callout suppressed globally
* Tab button taps now animate with the same directional slide as swipe navigation
* Tab icon spring-bounce animation on tap
* Red alert dot appears on Briefing tab icon when active weather alerts are present
* Scroll position remembered per tab — returning to a tab restores where you left off
* Card body fades in on open (short slide + opacity animation)
* Pull-to-refresh: drag down from top of any tab to reload weather data; arrow indicator fades in and flips when past threshold
* Fixed tab bar jumping on page load: removed redundant showTab call that triggered iOS URL bar flash on every refresh
* Pull-to-refresh indicator refined: CSS border spinner replaces arc indicator; fixed position, light mode color, and tab bar jump on load
* Stale-while-revalidate: cached weather data rendered immediately on load from localStorage before network fetch completes; schema version guard prevents restoring incompatible data
* 10-day forecast: precip probability bar per row (filled by PoP%); wind label shown when Breezy or worse; fixed POP extraction to read field directly from collector output; fixed row alignment (fixed-width % column, flex-start to prevent tall rows shifting temps)
* Text selection (long-press menu) disabled globally for native app feel
* Sunset scoring algorithm improved: forward-weighted time window [0.15, 0.50, 0.35] so clearing trends aren't buried; low cloud color contribution term (partial low clouds catch horizon light from below); humidity penalty eased above 70% for coastal air
* Wine-scale scoring applied to sunset, hair day, and beach day: display = 50 + 50×(raw/100)^0.6 — compresses the floor, spreads meaningful variance into 75–100 range, matching user expectations from wine/school-grade scoring
* Beach day wind display: was showing "kt", corrected to mph
* Briefing tab lifestyle rows: switched to label-based color mapping for sunset, hair, and beach day (rgba passthrough was incompatible with the cm color-class map)
* Design pass: background deepened to navy (#0d1525); card opacity, blur, and border increased for better panel definition; tab bar active color changed from iOS blue (#0a84ff) to ocean teal (#3BAABD); briefing headline bumped 1.8→2rem; card border radius 18→22px; tile labels slightly more readable

</details>


<details>
<summary><strong>v0.5.122–v0.5.124 • May 14, 2026</strong></summary>

* SVG tab icons replace emoji tabs across all four tabs
* Wind card tile redesigned: split compass/speed layout
* PWA manifest updated for wymancove.com custom domain
* Move notice banner added for users still on old GitHub Pages URL (only shown from jhselby.github.io)
* iOS card close bug fixed: tapping outside an expanded card now closes it without opening the card behind it; switched from backdrop click listener to document-level capture-phase touchstart/click handlers
* Corrections card moved from Lifestyle tab to bottom of Weather tab (col-6); collapsed tile shows station count and confidence level
* Birds card collapsed tile now shows "last 48 hrs" label

</details>


<details>
<summary><strong>v0.5.102–v0.5.121 • May 13, 2026</strong></summary>

* Tempest stations expanded from 3 to 9 within ~1.5mi of Wyman Cove
* WU station list trimmed from 36 to 29 (removed 7 confirmed out-of-range stations)
* Station denominator now counts all attempted stations (29 WU + 9 Tempest = 38), not just responders
* Adaptive bias correction: new station_bias.py tracks per-station chronic offsets for temp, humidity, and pressure using leave-one-out consensus over a 48h rolling window; MIN_READINGS=6 before offset applied
* Temperature diurnal split: separate day/night bias offsets (7am–7pm ET boundary); captures sensors whose drift varies across the day
* Kalman gain blend: corrected_temp = model + K × weighted_bias; K = 0.90/0.65/0.40 based on station count and agreement; model contributes when stations disagree
* KBVY temp logged as external calibration anchor: kbvy_temp_f and kbvy_local_delta in hyperlocal output every run
* Tempest stations shown in Settings → Sources card
* Version update detection: refresh button dot lights up when a new deploy is available; polls version.json every 5 min
* Fixed version dot always showing (DOM timing bug — appVersion not yet in DOM at script execution time)
* Added How It Works prose doc to Settings → Under the Hood
* Corrections card extracted to js/corrections.js; per-station adaptive bias offsets table (tap to expand, top 8 by magnitude, warm=red/cold=blue); KBVY anchor line in expanded card
* Lightning alerts from Tempest network: Watch For row + Active Alerts modal when ≥3 strikes/hr or ≥1 strike within 20 km; badge lights standalone; red if close, orange if distant
* Wind compass tile: wind lull (min across Tempest stations) added below sustained speed; gusts top / sustained center / lull bottom layout
* Wind rendering extracted to js/wind.js (renderWindTile, renderWindImpactCollapsed, renderWindChart, renderWindRisk, initWindPills, buildWindChart)
* Tempest hardware wet bulb replaces Stull formula for corrected_wet_bulb (fallback retained)
* Fix: Next rain day label suppressed when minutely shows rain within 60 min
* Extract renderSun/renderMoon/renderSolarSystem to js/sky.js; renderSources to js/sources.js; renderBirds to js/birds.js; radar functions to js/radar.js; renderTides/buildTideChart to js/tides.js; renderFrostTracker to js/frost.js; renderSunsetQuality to js/sunset.js; renderHairDay to js/hair.js; renderDockDay to js/dock.js; renderBriefing to js/briefing.js; buildTempPrecipChart to js/tempchart.js; renderForecast to js/forecast.js; renderTodayAlmanac to js/almanac.js; renderSeaBreezeDetail to js/seabreeze.js; renderFeelsLikeCard/renderFogDetail to js/feelslike.js; populateCollapsedPreviews to js/previews.js; card toggle/nav helpers to js/ui.js; settings/alert/precip modals to js/modals.js
* app-main.js: 5,900 → 1,449 lines
* NWS Extreme/Severe alerts now headline over active rain in briefing priority
* Fog: advection fog now fires correctly when dew point spread is large (was dead code path)
* Sea breeze: minimum land/sea differential raised 3°F → 5°F; hard vetoes for offshore wind and winds >15 mph
* Wind blend: stale observations (>20 min) excluded from Tempest and WU candidates; direction sourced from best fresh waterfront Tempest station
* Watch For: red border/background for Extreme/Severe alerts; fog and sea breeze rows dimmed as informational
* Briefing dateline: data age ("3m ago") shown right-aligned
* Schema version check: app stops rendering and prompts refresh on mismatch
* Tab: Hyperlocal renamed to Lifestyle
* Settings: opening one accordion closes the others
* Collector: all print() replaced with logging.info/warning/error across 16 files
* Tests: 17 passing tests added for fog, wet bulb, and sea breeze processors

</details>


<details>
<summary><strong>v0.5.100–v0.5.101 • May 12, 2026</strong></summary>

* Fix data refresh on Mac: add window focus listener alongside visibilitychange so Cmd+Tab back to browser triggers a reload (visibilitychange alone only fires on tab switches)
* Fix sunset score too low: clear-sky branch no longer requires low humidity (humid clear nights were scoring 1)
* Raise low-cloud overcast cutoff from 60% to 75% (patchy boundary-layer clouds were hardcoding "Poor"/10)

</details>


<details>
<summary><strong>v0.5.86–v0.5.99 • May 10, 2026</strong></summary>

* WeatherFlow Tempest integration: fetches 3 public stations within 0.4mi of Wyman Cove (Willow Rd, Driftwood Rd, Neptune Rd) via tempestwx.com web API
* Tempest stations wired into hyperlocal temperature bias calculation and wind max-selection alongside WU stations
* Tempest humidity preferred over WU aggregate for corrected_humidity (closer, fresher)
* Corrections card now shows 27/32 stations (30 WU + 2 valid Tempest)
* Fixed UnboundLocalError in build_weather_data: datetime local variable shadowed by conditional imports
* Gemini fallback model updated from deprecated gemini-1.5-flash-8b to gemini-2.0-flash-lite

</details>


<details>
<summary><strong>v0.5.68–v0.5.85 • May 9, 2026</strong></summary>

* Wet bulb and precip type classification (rain/snow/sleet/freezing rain) now fully corrected: both wet_bulb.py and precip_surface.py use corrected_temperature and corrected_humidity arrays throughout
* Updated DATA_PIPELINE.md: corrected stale placeholder/bug notes for wind speed, wet bulb, and feels-like; removed duplicate AI Briefing section
* build.py no longer creates index.html.backup on each run; deleted stale backup file
* Bias confidence indicator: shows correction amount and confidence level (Moderate=yellow, Low=red) below Feels Like when stations disagree; hidden when High confidence
* Removed dead NWS text forecast code: fetch_nws_forecast() from nws.py, renderNWSForecast() and nwsToggleExpand() from app-main.js, disabled collector references — replaced by forecast_text.py since v0.5.41
* Wind exposure table now single source of truth: collector embeds it in weather_data.json, frontend reads and updates from data on each load; JS fallback retained for offline/stale data
* Briefing click-throughs: Almanac rows (Sun, Tide, Moon) and Watch For rows now tap through to their detail cards
* Fixed fog+temperature double-period punctuation in forecast text
* Gemini briefing falls back to gemini-1.5-flash-8b on 429; both models configurable via env vars
* Briefing interval check now has in-memory guard (survives GCS failures; max-instances=1)
* Gemini briefing now receives previous headline as context; can note forecast shifts in subheadline
* Stale data indicator threshold raised from 20 to 25 minutes (fires only after 2+ missed collector runs)
* Briefing third stat changed from 48h rain to current conditions (sky text)
* All conditions displays now use weather_description (HRRR model) with condition_override (KBVY) as fallback
* Wind arrow redesigned: single line + arrowhead SVG; switched to SVG rotate() attribute to fix broken rotation in macOS PWA (WKWebView CSS transform-origin bug)
* Watch For storm flags: title now derives from most specific flag (freezing rain > snow > heavy rain > mixed > gusts > system > pressure)
* Watch For detail line now visible inline below alert/flag title without requiring a tap
* Precip flag no longer fires for rain on the surface — only for snow, sleet, freezing rain, and mixed
* Fixed collector crash: removed leftover forecast_data parameter; fixed missing WIND_EXPOSURE_TABLE import
* Fixed ReferenceError: conditions stat rendering placed before const cur declaration

</details>


<details>
<summary><strong>v0.5.66–v0.5.67 • May 8, 2026</strong></summary>

* Exposure-aware wind narratives in forecast text ("Calm at the cove despite..." / "Windy at the cove...")
* Added wind_worry_score, wind_worry_label, wind_exposure_factor to forecast periods
* Removed "toward morning" noise from night lows; removed false-precision temp timing on GFS days
* Suppressed contradictory sky descriptions during heavy precip
* Days 8–10 now include ECMWF sky condition and gust data
* Fixed UnboundLocalError from shadowed datetime import; fixed "VRB" wind direction crashes

</details>


<details>
<summary><strong>v0.5.64–v0.5.65 • May 7, 2026</strong></summary>

* Frontend fallbacks for Fog and Wind Impact tiles when GFS current data unavailable
* Collector fallback: HRRR hourly[0] for fog when GFS fails
* Briefing rain stat shows three states: "No rain", "Trace" (POP ≥ 40% but zero accumulation), or inches
* TODAY section: High / Low row shows full temp range without scrolling
* Forecast text now always prefers corrected data; fixed false "Chance of rain" from GFS fallthrough
* 10-day rain icons now driven by corrected data upstream

</details>


<details>
<summary><strong>v0.5.54–v0.5.62c • May 6, 2026</strong></summary>

* **Rain Stat (v0.5.62)**
  * Shows "Trace" instead of 0" when precip is measurable but rounds to zero
  * Trace stat correctly sized (1.8rem) and vertically centered
  * brief-stat cells flex-centered for consistent alignment
* **Briefing Tab Restructure (v0.5.61)**
  * WATCH FOR floats to top (below stats) when active; static HTML order replaces runtime DOM reordering
  * New ALMANAC section (sun rise/set, next tide, moon phase) split out from TODAY
  * Fog and rain rows removed from TODAY — covered exclusively by WATCH FOR
  * "No alerts" quiet note suppressed — WATCH FOR div simply empty when inactive
  * Separator line spacing normalized between WATCH FOR and TODAY
* **Briefing Tab Improvements**
  * Storm alerts (pressure/trough/wind/precip signals) now appear in Watch For section
  * Precip mini bar in Watch For when rain is imminent — taps to open full precip modal
  * Watch For moves above Lifestyle whenever it has any content
  * Tonight section now shows detailed forecast text from forecast_text.py
  * Rain stat label clarified to "rain · next 48h"
* **Gemini Briefing Prompt**
  * Wind Impact score reframed as authoritative hyperlocal measure; numeric score stripped from payload
  * Gemini decides when to mention contrast with regional forecast
  * Cloud Function max-instances=1 — prevents concurrent execution and 429 rate limit collisions
* **Feels Like / Apparent Temperature**
  * Implemented Steadman radiation formula using Open-Meteo direct_radiation (cloud-attenuated)
  * Radiation formula used when direct_radiation > 0; falls back to shade formula when overcast/night
  * Q = direct_radiation × 0.17; applied to both current feels-like and 48h hourly array
* **Wind Compass**
  * Arrow tail made full opacity and extended; tail dot removed for cleaner direction reading
* **Collector / Data Pipeline**
  * Sunset directional cloud fetches reduced from 5 days to 3 — eliminates Open-Meteo 429 errors
  * direct_radiation added to HRRR hourly pipeline (replaced shortwave_radiation)

</details>


<details>
<summary><strong>v0.5.43–v0.5.53 • May 5, 2026</strong></summary>

* **Feels Like Overhaul**
  * Replaced piecewise NWS wind chill / heat index with continuous Steadman shade formula
  * Eliminates 50–80°F dead zone; collector computes corrected_apparent_temperature for all 48h
  * Feels-like chart reads from collector (single source of truth); Wind Chill / Heat Index labels removed
* **Water Temperature**
  * Now sourced from GoMOFS (Gulf of Maine Operational Forecast System), grid point Salem Channel (~1.5mi)
  * Buoy 44013 retained as fallback; ocean card and Beach Day scoring both updated
* **Briefing Tab**
  * Watch For: alerts move above Lifestyle; alert rows simplified, tap to open modal
  * Gemini prompt rewritten — geographic context, exposure table, conditional data, token reduction
  * Precip threshold: <20% POP = no mention; 20–30% minor; 40%+ featured
* **Collector Cleanup**
  * Corrected hourly dew point, absolute humidity, wet bulb all computed in collector
  * Dead JS functions removed: calculateWetBulb, dewPointF, absHumidity, dockWindScore
  * Dead tempBias parameter removed from forecast renderers
  * Settings modal resets subsections on close
* **Beach Day**
  * Now uses combinedWindImpact (exposure model) instead of custom dockWindScore

</details>


<details>
<summary><strong>v0.5.42 • May 3, 2026</strong></summary>

* Fixed 13 broken HTML attributes where `class` was inside `style` — elements now get proper theme-aware colors in light mode
* Fixed settings theme buttons not syncing active state (wrong IDs)
* Fixed precip badge lighting up without probability check — now matches modal's ≥30% threshold
* Renamed "Swim Float" card to "Beach Day"
* Redesigned wind compass arrow — full-length through center with gap for speed number, extends past circle, bolder styling
* Removed dead code: `toggleSettings()`, `toggleMenu()`, `toggleMenuSection()`, duplicate `updateForecastSelection()` call, test comment
* Removed hidden meta-row, rewired timestamps to settings modal directly

</details>


<details>
<summary><strong>v0.5.41 • May 2, 2026</strong></summary>

* **Meteorological Audit — 7 fixes across precipitation, forecast, and resilience**
  * Surface precip type (wet bulb) now used everywhere instead of 850mb column type
  * 850mb override catches all frozen/mixed types when surface temp > 40°F
  * Fixed precip_surface.py dead code — never returned "rain"
  * Fixed HRRR/GFS handoff dropping Monday from 7-day forecast
  * Days 8-10 forecasts now use temp-based precip type
  * 7-day GFS data now gets wet bulb and surface precip processing
* **Processor Improvements**
  * Sea breeze uses corrected hyperlocal temp for land/water differential
  * Added advection fog detection (warm moist air over cold water) — primary coastal fog type
  * fog.py now returns fog_type (radiation vs advection)
* **GFS Failure Resilience**
  * Hyperlocal temp correction works when GFS model temp unavailable (uses WU station weighted average)
  * Briefing AI falls back to cache when current temp missing/zero (prevents 0°F briefings)
* **Frontend**
  * Active weather alert shows both surface and column precip types
  * App returns to briefing tab after 5+ minutes away; always opens on briefing
  * Sunset quality score smoothed with 3-hour averaging window (reduces model wobble)

</details>


<details>
<summary><strong>v0.5.33 • May 1, 2026</strong></summary>

* **Tile & Briefing Fixes**
  * Beach/hair day tiles switch to tomorrow at sunset (was hardcoded 6 PM)
  * Fixed briefing sunset score reading from wrong data source
  * Fixed "undefined (undefined/100)" when sunset score unavailable
  * Fixed swim float card showing wrong day after 8 PM EDT
  * Fixed tide calendar grouping using UTC dates

</details>


<details>
<summary><strong>v0.5.25–v0.5.28 • April 30, 2026</strong></summary>

* **Briefing Polish**
  * Tomorrow scores (sunset, beach, hair) display correctly after civil dusk
  * Clickthrough navigation for all "(tomorrow)" rows
  * Rain rows suppressed when accumulation is 0"
  * Next-hour rain indicator triggers on any precip intensity
* **Collector**
  * Switched Gemini from deprecated 2.0-flash-lite to 2.5-flash-lite
  * Added missing `import re` to fetcher files
  * Temperature ranges sent to Gemini to prevent hallucinated exact temps
* **Overhead**
  * Zoomed out to capture BOS approach traffic
  * Plane info overlays map instead of pushing content down

</details>


<details>
<summary><strong>v0.5.19 • April 29, 2026</strong></summary>

* **Bug Fixes & AI Briefing**
  * Fixed wind impact constant mismatch between frontend and backend
  * Guarded precip_850mb against missing hourly key
  * AI prevented from saying "no rain in sight" when rain is imminent
  * Pirate Weather minutely precip signal added to briefing
  * Cloud Function secured with OIDC auth
  * Data Sources moved to settings with health status dots
  * Lazy-load overhead.js on card tap

</details>


<details>
<summary><strong>v0.4.0–v0.4.33 • March 31 – April 12, 2026</strong></summary>

* **Comprehensive Hyperlocal Correction System**
  * All derived values use corrected data (wet bulb, feels like, dew point, precip type)
  * Wind gust corrections blended into 48h forecast with 24h decay
  * Tab reorganization: Wind and Radar tabs removed, Hyperlocal Corrections tab created
* **Collapsible Tile System**
  * All cards converted to col-6 tiles expanding to modal overlays
  * Preview data in collapsed state; localStorage persistence
* **NEXRAD Radar**
  * Switched from RainViewer to IEM NEXRAD WMS (5-min updates, 2h history)
* **Chart Redesign**
  * Sky conditions as per-column background gradients
  * Precip bars colored by type; 6-hour x-axis ticks
* **iOS-Style Bottom Tab Bar**
  * Frosted glass nav, swipe between tabs
  * Settings as slide-up modal sheet
* **Moon Phase**
  * Canvas-rendered moon replacing emoji
* **Tides Card**
  * 3-column calendar layout with next-tide indicator

</details>


<details>
<summary><strong>v0.2.0–v0.2.77 • February – March 18, 2026</strong></summary>

* **Modular Collector Refactor**
  * Split monolithic collector.py into fetchers/ and processors/ packages
  * Processors: fog, frost, hyperlocal, pressure, sea breeze, trough, wet bulb, wind risk
  * KBOS/KBVY migrated to Aviation Weather API; buoy wind data added
* **Smart Hyperlocal Corrections**
  * Distance + elevation weighted bias from WU stations
  * Quality filtering: stale data rejection and outlier detection
* **Sea Breeze Detector**
  * Terrain-based wind exposure table from contour map analysis
  * Wind impact cards with forward-looking peak windows
* **Core Features**
  * 10-day forecast with NWS integration
  * Gust & sustained wind impact cards
  * Frost & freeze tracker
  * Dock Day Score with tide-window scoring
  * Sunset Quality forecast
  * RainViewer radar
  * Light/dark/system theme toggle
  * Mobile responsive layout

</details>

