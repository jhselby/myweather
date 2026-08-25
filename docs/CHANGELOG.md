<details open>
<summary><strong>v0.6.482 • August 25, 2026 (Prod Trend noise suppression — thin prior pool + tiny-magnitude/non-MAE fields)</strong></summary>

- **Symptom.** 7d Prod Trend tile median was landing at −191.8% because pa (precip amount, `prod_prior_mae` = 0.005 in, `prod_mae` = 0.015 in) produced a ratio of −191% off two near-zero denominators. Several NBM-scope fields at 7d showed even wilder trends (t −1181%, dp −8339%, wg −674%) because the "prior window" (7-14 days ago) has almost no rows that survive the v0.6.468 pool intersection — `nbm_raw` backstamp thins out that far back, so `n_prod_prior` was 0-3 on those fields.
- **Fix in `per_field_scoring.py`.** `prod_trend_pct` is now nulled when `n_prod_prior < 50` (denominator too thin to trust) or when the field is on `TREND_EXCLUDE_FIELDS = {"pa", "pp"}` (pa's MAE is near-zero inches; pp is Brier-scored, not MAE). Nulls flow through the frontend tile's median/mean aggregation, which already skips them.
- **Effect.** 7d Prod Trend tile will now aggregate over whichever fields have real trend numbers — currently the HRRR-only fields (cl/cm/pr) whose full-history prior pool isn't gated by NBM backstamp. 24h Prod Trend unaffected (all fields have ample prior-window data at 24-48h).

</details>

<details>
<summary><strong>v0.6.481 • August 25, 2026 (Selector Hit Rate + Value Captured live in the per-field diagnostic table)</strong></summary>

- **Backend:** `analysis/per_field_scoring.py` gains two per-field diagnostics on the paired chosen/alt Prod pool: `hit_rate_pct` (fraction of paired rows where the selector's chosen cascade Prod residual ≤ the alternative cascade's; ties count as hits) and `value_captured_pct` ((alt − chosen) / (alt − oracle) × 100, where oracle = per-row min of the two). Both null for HRRR-only fields where there's no alt cascade. Also emits `oracle_prod_mae` for later use.
- **Frontend:** the per-field diagnostic table's Hit Rate + Value Captured columns now populate from those fields; Median + Mean tfoot rows include both. Table's sub-blurb replaces the "stay dashed" caveat with a description of the paired-pool + NBM-scope-only rule.
- **Publisher redeployed.** First tick after redeploy will overwrite `per_field_scoring.json` with the new fields.

</details>

<details>
<summary><strong>v0.6.480 • August 25, 2026 (Per-field diagnostic table wired live from per_field_scoring.json)</strong></summary>

- **Finishes the 08-25 evening scoreboard wire-up.** Follow-up (a) from v0.6.479: the per-field diagnostic table under Current State was still showing hand-hardcoded values from the pre-v0.6.478 pooled-min baseline. New `renderPerFieldDiagnostic()` populates rows + Median/Mean tfoot from the same hourly-refit `per_field_scoring.json` the headline tiles read (single source of truth, no drift risk).
- **Columns wired:** Total Lift (`total_vs_best_raw_pct`), HRRR Pipeline Skill (`(hrrr_raw_mae − hrrr_prod_mae)/hrrr_raw_mae`), NBM Pipeline Skill (same on NBM side; `n/a` for HRRR-only fields cl/cm/pr/pa/pp), n (`n_l1_selected` fallback to summed `selector_picks`). pp cells show "Brier" (scored differently); pa cells show "tiny mag".
- **Not wired:** Hit Rate + Value Captured columns stay dashed — these need the L1 selector fit's per-cell picked/oracle counts, not currently emitted to per_field_scoring.json. Separate work item.
- **Removed:** hand-hardcoded `<tbody>` + `<tfoot>` rows and the ⚠ stale-numbers warning in the table sub-blurb. Sub-blurb now names the exact live source and dashed-column caveat.

</details>

<details>
<summary><strong>v0.6.472 • August 25, 2026 (L3_NBM whitelist trimmed — sr, t, ws dropped on walkforward evidence; wg kept for 08-28 per-cell review)</strong></summary>

- **Same class of ship as v0.6.471, one cascade layer up.** `nbm_walkforward_validator` proposes dropping {sr, t, wg, ws} from `L3_NBM_FIELDS`. 14-day aggregate lift vs `l2_nbm` baseline: t **−2.2%**, ws **−2.5%**, sr net loss (skip-cells run −22% to −5%). All three lose at every non-trivial band. Dropped.
- **wg kept despite the tool's proposal.** wg is the only field with genuinely mixed bands: 0-5h **+3.0%**, 24-47h **+8.2%**, 6-11h −9.1%, 12-23h −3.4%; aggregate is a small −1.1% loss. The walkforward's earn-membership gate (+2%) is designed to *add* whitelist entries, not remove them — removing an already-live field should require clear harm, not just failure to clear the add gate. Two positive-lift bands worth eating a −1.1% aggregate for 72 hours while the scheduled per-cell skip-table review (2026-08-28) runs — that's the surgical fix for a mixed-signal field.
- **L3_NBM_FIELDS**: `("t", "ws", "wg", "h", "ch", "sr", "cc")` → `("wg", "h", "ch", "cc")`. sr cascade for the NBM side now walks `sr_raw_nbm → sr_l2_nbm` (l3_nbm skipped, l5_nbm already killed in v0.6.471). t and ws walk `raw_nbm → l2_nbm`.

</details>

<details>
<summary><strong>v0.6.471 • August 25, 2026 (l5_nbm sr killed — sentry HOT +238% MAE + walkforward "DROP sr" both agree, plus fitted_at write bug fixed)</strong></summary>

- **Sentry + walkforward agreement.** `nbm_regression_sentry` today: `sr.l5_nbm HOT ΔMAE +238.2%` (sustained 39, fresh 132). `nbm_walkforward_validator` skip proposals for sr on l5_nbm: pooled −126% (0-5h), −145% (6-11h), −147% (pre_frontal 12-23h). Two independent tools, unanimous — kill the layer.
- **Physical cause.** Fallback biases in `lsr_nbm_bias_table_curated.json` are large-negative for the flow regimes (calm −218, ne_flow −181, nw_flow −164, frontal −103 W/m²). Correction is `−bias`, so l5_nbm was adding +100 to +218 W/m² on cells that missed the per-hour fit and fell back to regime average — massive over-correction.
- **The kill.** `weather_collector/processors/l5_nbm.py` gains `ENABLED = False` and `l5_nbm_correction()` short-circuits to 0.0. Cascade falls back to `sr_raw_nbm → sr_l2_nbm → sr_l3_nbm`. `L5_NBM_FIELDS = ("sr",)` stays as a documentation constant; the field application is hardwired in `forecast_snapshot.py`, so the flag inside the correction function is what actually gates it.
- **Latent bug fixed on the way through.** `analysis/l5_nbm_recompute_biases_hourly.py` wrote `generated_at` but not `fitted_at`; every sibling NBM fitter (l3/l4/l6) writes both. `l5_nbm.py::_load()` reads `fitted_at`, got `None`, `is_stale(None)` returns `False` (fail-safe), so the staleness gate was silently disabled. Added `fitted_at` to the output dict so when/if l5_nbm returns after a refit, the staleness gate actually works.

</details>

<details>
<summary><strong>v0.6.470 • August 22, 2026 (Prod Trend pool symmetry — v0.6.468 was comparing intersected current-window Prod to unfiltered prior Prod)</strong></summary>

- **The asymmetry Joe caught in a screenshot.** After v0.6.468's pool intersection, the current-window `prod` bucket only accepted rows where the 4-residual pool was satisfied, but `prod_prior` still accumulated on all rows. Prod Trend = (prod_prior − prod)/prod_prior was therefore comparing two MAEs pooled over different obs sets, which produced a spurious "−2.6% regressing on 6 fields" reading with no matching real-world signal.
- **Fix.** `_accumulate` now computes `pool_ok` up-front and applies it to both branches: prior-window rows only contribute to `prod_prior` when the same intersection rule is met. Prod Trend now compares like-with-like.
- **Effect.** NBM-scope fields get a blank Prod Trend cell for now, because the backstamp doesn't yet cover the prior-equal window under the intersection rule. That's honest — the tile stays quiet until there's real trend evidence to show. Non-scope fields (cl/cm/pr) still populate; their movements reflect weather variability, not pipeline drift.
- **What survives.** Local Lift near zero (+0.4% median) is NOT a pool artifact — it appears to be a real change that needs looking at, but not tonight.

</details>

<details>
<summary><strong>v0.6.469 • August 22, 2026 (scoreboard tiles show median, not mean — the identity doesn't survive arithmetic-mean-of-percentages)</strong></summary>

- **The subtlety Joe caught.** The multiplicative identity `(1-Total) = (1-Chooser)(1-Local)` holds per field, but breaks under an arithmetic mean of per-field percentages. Under v0.6.468 the headline tiles were showing means, and the numbers were visually inviting a decomposition read that the aggregate could not actually support (mean Chooser −28.7% × mean Local +13.5% implies −11.3%, not the shown −7.3%).
- **Tiles now show median lift** across the 7 value-chain fields (labels updated: "7d median" / "24h median"). More honest for heterogeneous fields; doesn't imply a decomposition at the aggregate level.
- **Coherence check moved to per-field.** The old aggregate-vs-identity check was measuring the wrong thing. Now iterates the 7 value-chain fields and asserts `(1-Total_i) ≈ (1-Chooser_i)(1-Local_i)` per field — >5pp dev is a `console.warn` (real signal of pool mismatch inside that field); >2pp is `console.info`.

</details>

<details>
<summary><strong>v0.6.466–v0.6.468 • August 22, 2026 (scoreboard restructured as Value Chain + Diagnostics — Chooser Lift no longer measures selector skill)</strong></summary>

* **The confound.** The tile labeled "L1 Chooser Lift" was actually Selector Skill (chosen-cascade Prod vs alternative-cascade Prod). That answers "did the router pick the branch that turned out better?" — a diagnostic of the router, not value attribution. It cannot tell you whether L1 selection contributed anything over what the public forecasts already provide. The number could be positive (router picked correctly) while L1 was still worse than just always using raw NBM. Two different questions were sitting on top of each other in one tile.
* **New governing principle.** The top-level scoreboard distinguishes **value attribution** from **diagnostics**. Chooser Lift, Local Lift, and Total Lift are successive stages of one value chain: **Best Public Raw → L1 → Production**. National Source Score, Selector Skill, Prod Trend, and Health & Reliability diagnose why that chain is behaving as it is. A diagnostic never substitutes for a value-chain score.
* **Value-chain tiles (new definitions).** Chooser Lift = (best_raw_MAE − L1_MAE)/best_raw_MAE — did source selection improve on the best public raw. Local Lift = (L1_MAE − Prod_MAE)/L1_MAE — did the local correction stack add value on top of L1. Total Lift = (best_raw_MAE − Prod_MAE)/best_raw_MAE — is what Wyman Cove publishes better than the best public alternative. Under fractional-reduction semantics, (1−Total) ≈ (1−Chooser)(1−Local); the renderer logs a console warning if the two sides deviate by more than ±5pp.
* **Diagnostics row.** The old chooser-lift tile is renamed **Selector Skill** and moved below the value chain. National Source Score copy updated — the line "NBM winning is the 'chooser should flip' signal" is removed. It was wrong: corrected HRRR can beat corrected NBM even when raw NBM beats raw HRRR, so National Source Score is diagnostic of national guidance only.
* **Field scope.** All three value-chain tiles pool over the same field set — the 7 NBM-scope fields (t/h/ws/wg/wd/ch/sr) — so the multiplicative identity holds. Fields with no NBM raw baseline can't participate in a "vs best raw" chain.
* **Per-field table.** Renamed group headers to "L1 chooser (value chain)" / "Local correction stack (value chain)" / "Total (value chain)". Chooser Lift column now reads L1 vs best raw. Added a new **Selector Skill** column at the right of the table, styled as diagnostic (grey accent).
* **v0.6.466 and v0.6.467** (Chooser Lift Prod-vs-Prod rework and Prod Trend tile) shipped earlier today. Both were correct as changes-in-isolation but described the wrong tile-level story; v0.6.468 is the restructuring pass that puts the numbers in the right conceptual place.

</details>

<details>
<summary><strong>v0.6.465 • August 22, 2026 (drop dp from L3_NBM_FIELDS — pooled bias was actively harming users)</strong></summary>

- **What forced the fix.** per_field_scoring 24h (freshly regenerated post-F6) revealed dp Prod=2.895 vs NBM raw=0.841 — our correction stack was making dp forecasts **244% worse** than the raw NBM data the selector picked. Since F6 shipped writeback, users viewing dp at 6-47h were actively seeing the degraded value. My earlier "user impact zero" analysis was wrong — it only held for the 0-5h band the skip cells covered, not the 6-47h range where the selector actually picks NBM.
- **Root cause.** L3_NBM subtracts a pooled per-lead bias (~+1°F) that was fitted globally across all obs. NBM's dp is already well-calibrated at this coord: bias ≈ 0, fc_std matches obs_std. Subtracting a wrong-direction pooled bias worsens every regime. Matches HRRR's long-standing decision to exclude dp from `L3_FIELDS` — HRRR reached the same conclusion months ago via `h_l3_asymmetric` analysis. NBM-specific data confirms.
- **Fix.** dp removed from `L3_NBM_FIELDS`. dp NBM cascade now `raw_nbm → l2_nbm` (identity — dp has no HRRR L2 delta since dp is derived, not directly extracted). Selector's dp 6-47h NBM picks score against l2_nbm on the next fit.
- **Skip cells retracted.** Yesterday's `skip_table_nbm_curated.json` dp 0-5h cells are now redundant (dp not in L3_NBM_FIELDS → nothing to skip). Removed from `cells`; kept in a new `history` block with the reasoning trail. skip_table_nbm.py's loader ignores the history block.
- **Data collection confirmed honest.** Deep-dive on the "NBM raw is way better than HRRR raw for t/h/dp" numbers: verified matching timestamps between NBM and HRRR (same n_shared), sensible ranges, consistent bias direction across all lead bands. HRRR L1 has real systematic biases at this coord (h under -10%, dp under -2°F, sr under -60 W/m², t over +1°F); NBM is more physically calibrated. Correction stack closing the HRRR raw biases is exactly what it's supposed to do; adding a pooled NBM bias on TOP of already-calibrated NBM raw is what was wrong.

</details>

<details>
<summary><strong>v0.6.464 • August 21, 2026 (close L1_ONLY_FIELDS NBM gap in mae_over_time — feature parity)</strong></summary>

- **Latent gap closed.** `mae_over_time.py`'s L1_ONLY_FIELDS branch (wd) derived prod_real inline from `error_wdp || error_l2` without checking `selector_source`. When selector picked NBM for wd (not today, but the day it happens), prod_real would silently show HRRR-side wdp/l2 residual instead of the NBM-side residual users actually saw. Same class as F3-A but on a code path that intentionally skips `applied_layer`.
- **Fix.** When `selector_source == "nbm"`, walk NBM-side deepest layer: `error_wdp_nbm > error_l3_nbm > error_l2_nbm > error_raw_nbm`. Falls back to the existing HRRR walk when selector picked HRRR. No user-visible change today (selector picks NBM only for wg/dp/cc, none L1_ONLY); closes the last known metric-attribution gap between the two cascades.
- **NBM cascade now at true feature parity with HRRR.** Every code path that reads pair-log residuals routes NBM-served rows to their NBM-side answer. Project returns to pure-tuning mode: no remaining structural asymmetries between the cascades except the permanent field-scope difference (NBM doesn't emit cl/cm/pp/pa/pr) and the L6_NBM enablement question (empirical, awaiting shadow-fit signal).

</details>

<details>
<summary><strong>v0.6.463 • August 21, 2026 (first curated NBM skip cells — dp 0-5h ×3 regimes)</strong></summary>

- **First real cells landed in `skip_table_nbm_curated.json`.** Three cells for `dp l3_nbm 0-5h`: `pre_frontal`, `sw_flow`, `se_flow`. Selected because walkforward emitted -96% to -125% lift with n=202-345 each, and the badness is structural (L3_NBM's pooled +1.5°F bias fights close-to-obs L2_NBM in these regimes).
- **User impact today: zero.** Selector currently picks HRRR for `dp 0-5h` — this skip prevents future selector fits from being poisoned by a broken NBM-Prod score, doesn't change what users see.
- **Why 0-5h only, not the whole field.** dp 6-47h per-regime cells are all THIN today. Selector picks NBM for `dp 6-47h` currently, and that pick depends on `l3_nbm` helping. Dropping dp from L3_NBM_FIELDS entirely (matching HRRR) was tempting but would have been pattern-matching HRRR beyond what NBM-specific data supports — deferred pending stronger per-regime evidence at longer leads.
- **Provenance recorded.** New `provenance` block in the curated JSON captures the evidence (regime × n × lift) + reasoning behind each curated group, so future readers know why cells were added and can revisit if patterns shift.
- **Monitoring loop closed.** F1 sentry watches `dp.l3_nbm` MAE fresh-vs-sustained daily; walkforward re-runs daily and will show if these cells stop appearing (skip working) or if 6-47h cells cross the n-floor with real signal (needs another decision). Scheduled review [[nbm-skip-proposals-review]] on 2026-08-28 for the remaining 44-cell backlog.

</details>

<details>
<summary><strong>v0.6.462 • August 21, 2026 (NBM walkforward regime cross-cut — skip proposals become actionable)</strong></summary>

- **Regime dimension added to `nbm_walkforward_validator.py`.** `paired_by_regime[(field, cand, base, band, regime)]` accumulates alongside the existing pooled `paired`; regime comes from each row's `state_fc.regime_synoptic` (matches the runtime skip check and HRRR walkforward's fc-side view). For each cell that hurts by ≥3% with n ≥ 200, emits real per-regime SKIP proposals ready to drop into `skip_table_nbm_curated.json`. Pooled `*` proposal kept only as advisory fallback when no single regime cleared the n floor (labeled `[pooled — no single regime cleared n floor]`).
- **First-run results (14d window, live-only rows).** 44 actionable per-regime cells surfaced across l3_nbm: notably `dp 0-5h {sw_flow, pre_frontal, se_flow}` all -96% to -125% lift (L3_NBM identity fit still warming), `sr 0-5h {nw_flow, sw_flow, pre_frontal}` -15% to -25%, `t 12-23h pre_frontal` -30%. Digest exec-summary "NBM skip-table proposals" block now shows regime column; the walkforward's report title updated from "regime pooled" to "per-regime cross-cut, fallback pooled *".
- **What lands next.** Curated `skip_table_nbm_curated.json` stays empty pending your review — the proposals are advisory. Some numbers (dp -125%) suggest the L3_NBM fit needs another day or two of pair-log data before those cells should be treated as durable. Suggest waiting for the fresh 3d ≡ sustained 7d window to be fully post-backstamp before landing any cells.

</details>

<details>
<summary><strong>v0.6.461 • August 21, 2026 (F7 applicability + F8 caps/staleness + debug sweep — structural parity)</strong></summary>

- **F7 applicability map entries.** New `describe_applicability()` on `l3_nbm.py`, `l4_nbm.py`, `l5_nbm.py`, `l6_nbm.py`, `skip_table_nbm.py`; collector aggregation wires them into `weather_data.applicability_map.layers` alongside the HRRR descriptors. Debug page's Section D + per-layer applicability filters now render NBM cascade entries.
- **F8 CAPS_NBM + staleness gates.** New shared `weather_collector/processors/nbm_common.py` with `CAPS_NBM` (per-field magnitude caps mirroring `decay_apply.CAPS`), `STALE_DAYS_NBM = 7`, and helpers `cap_correction(field, delta)` / `is_stale(fitted_at)`. Each NBM applier (l3/l4/l5) checks `fitted_at` freshness at load — logs a warning + becomes a no-op when stale — and clamps every correction return through `cap_correction`. L6_NBM stays ENABLED=False so caps + staleness are wired but latent.
- **Debug page sweep post-F6.** Current-state NBM tile rewritten from "STRUCTURALLY COMPLETE" to **"STRUCTURAL PARITY WITH HRRR"** with an explicit list of what remains different and why (permanent field scope; L6_NBM double-count investigation; skip-table empty seed; F3-D backstamp depth). Recent activity entry updated to reflect F6 shipped (was still saying "queued next"). "11 ships today" instead of "9 ships".

</details>

<details>
<summary><strong>v0.6.460 • August 21, 2026 (F6 PWA writeback — selector picks now reach the user)</strong></summary>

- **F6 investigation found a real gap.** The selector overwrote `entry[f]` (snapshot log) and stamped `hourly.l1_selected_*` (debug-page read) when it picked NBM — but never touched `hourly[array_name]` (the arrays PWA reads: `cloud_cover`, `wind_gusts`, `corrected_dew_point`, etc.). Users have been seeing HRRR-corrected values on every screen for cells the selector picked NBM (wg 12-47h, dp 6-47h, cc all leads at ship). The pair-log's Prod attribution was correct (reads `entry[f]` = NBM), so scoreboard lift numbers were honest — the display was silently wrong.
- **Fix** — `forecast_snapshot.py` gains a `_SELECTOR_WRITEBACK` map (t → corrected_temperature, dp → corrected_dew_point, h → corrected_humidity, ws → wind_speed, wg → wind_gusts, cc → cloud_cover, sr → direct_radiation, ch → cloud_cover_high, wd → wind_direction) applied after the `l1_selected_*` publication. For each hour where `{f}_selector_source == "nbm"`, overwrites `hourly[array_name][i]` with `entry[f]` (the deepest available NBM layer per F3-A). Bounds-checked per array to avoid IndexError on shorter arrays. Runs post-decay-apply, so all HRRR corrections + Magnus dp derivation are done first — NBM overwrite lands last.
- **Coherence caveat noted.** Today's live picks (wg / dp / cc) are field-independent so no downstream physics constraint breaks. If a future selector picks NBM for `t` while leaving `h` on HRRR (or vice-versa), the displayed (t, h) pair no longer comes from the same model — Magnus-derived quantities the PWA computes from them may look slightly inconsistent. Not fixing preemptively; will revisit if a future selector fit surfaces the case.

</details>

<details>
<summary><strong>v0.6.459 • August 21, 2026 (debug page sweep — F3/F4/F5 surface changes)</strong></summary>

- **Current-state NBM cascade tile** — extended to cover today's three ships in one line: F3 audit (applied_layer NBM-aware, specialist attribution, l6_nbm_fit backstamp), F1 sentry + F2 walkforward, F4 gate telemetry + F5 skip table. "Next: F6 PWA writeback trace" queued.
- **Recent activity** — 08-21 entry re-titled "9 ships (v0.6.450–458)" with F3/F1/F2/F4/F5 explainers appended. Prior batch (v0.6.450-454 cascade completion) left intact.
- **New skip-table fit-status tile** — 🚫 NBM skip table card between the L6_NBM tile and the L1 selector card. Fetches `weather_collector/data/skip_table_nbm_curated.json` and renders per-layer cell counts; ships with empty seed. Notes the walkforward's `"*"` regime-pooled proposals need manual translation before landing here.
- **Gate-firing rollup card** — meta-line notes NBM operators (`L3_NBM`/`L4_NBM`/`L5_NBM`/`L6_NBM`/`CHP_NBM`/`WDP_NBM`) now emit per-tick from `forecast_snapshot.py` (F4). They'll appear in the 7-day rollup after the next digest cycle.
- **Held-out MAE per-field-per-layer meta-line** — notes v0.6.456 (F3-A) `applied_layer` semantics change (now stamps NBM layers on selector-picks-NBM rows). Historical rows carry the old HRRR stamp; only post-08-21 rows carry NBM-aware attribution.

</details>

<details>
<summary><strong>v0.6.458 • August 21, 2026 (F4 gate telemetry + F5 skip table — NBM per-cell dormancy)</strong></summary>

- **F4 NBM gate-firing telemetry** — `forecast_snapshot.py` NBM apply blocks (L3/L4/L5/L6/chp/wdp) now accumulate per-field fires/skips across the 48-hour snapshot loop; one `gate_firing_log.record_firing(operator="L3_NBM"|"L4_NBM"|…)` call per NBM operator after the loop. Mirrors the HRRR L3/L4 telemetry from `decay_apply.py`. `gate_firing_rollup` can now audit NBM dormancy the same way it audits HRRR — no more silent "code path enabled but never fires" gaps.
- **F5 NBM skip table** — new `weather_collector/processors/skip_table_nbm.py` + curated `weather_collector/data/skip_table_nbm_curated.json` (empty seed). Mirrors HRRR's `decay_apply.SKIP_TABLE` + `_should_skip()`: per-cell (field, layer, regime, lead-band) skip check called from each NBM apply block. When it fires: skip the layer stamp for that cell → selector's deepest-NBM-layer walk naturally falls back to the shallower layer. Cell shape `[regime, lead_lo, lead_hi_exclusive]`.
- **Walkforward emits skip proposals** — `analysis/nbm_walkforward_validator.py` gains per-band SKIP proposals (lift ≤ -3% AND paired_n ≥ 200) alongside its existing whitelist divergence. Proposals use `"*"` as pooled-regime placeholder until regime cross-cut lands. Digest exec-summary gains an "NBM skip-table proposals" block via new `nbm_skip_proposals_summary()`.
- **First-run skip candidates surfaced** — from 14d live-only rows: `l3_nbm cc 12-23h`, `ch 0-5h`, `ch 6-11h`, `dp 0-5h`, `dp 6-11h`, `sr 0-5h`, `sr 6-11h`, `t 6-11h`, `t 12-23h`, `wg 6-11h`, `wg 12-23h`. Advisory only — curated JSON stays empty pending regime cross-cut + Joe's review.

</details>

<details>
<summary><strong>v0.6.457 • August 21, 2026 (F1 sentry + F2 walkforward — NBM monitoring loop)</strong></summary>

- **F1 NBM regression sentry** — new `analysis/nbm_regression_sentry.py` mirrors `anomaly_detector.py` but keyed on `error_{l3_nbm|l4_nbm|l5_nbm|l6_nbm|chp_nbm|wdp_nbm}`. Per (field, layer): MAE fresh 3d vs sustained 7d, verdict HOT/WATCH/CLEAN/THIN at ±15%/±8% thresholds. Digest exec-summary gains an "NBM regression sentry" section that surfaces HOT/WATCH cells with n_sust/n_fresh/ΔMAE inline.
- **F2 NBM walkforward validator** — new `analysis/nbm_walkforward_validator.py` mirrors `walkforward_l3l4_validator.py` for NBM. Per (field, candidate layer, baseline layer, band): aggregate lift over 14d, whitelist rule = lift ≥ 2% AND paired_n ≥ 200. Emits proposed `L3_NBM_FIELDS`/`L4_NBM_FIELDS`/`L5_NBM_FIELDS`/`L6_NBM_FIELDS`/`chp_nbm`/`wdp_nbm` and diffs against runtime-live. Digest exec-summary gains an "NBM walkforward — proposed whitelist divergence vs live runtime" section listing ADD/DROP per layer.
- **Backstamp identity filter** — l3_nbm-vs-l2_nbm comparison skips rows where the two errors match exactly (nbm_backstamp writes `l3_nbm = l2_nbm` when no curated L3 bias existed pre-08-19). Prevents identity-noise from drowning real post-refit signal. Auto-clears in ~28d as backstamped rows sunset.
- **Digest wiring** — `analysis/runlog/build_executive_summary.py` gains `nbm_regression_sentry_summary()` + `nbm_walkforward_divergence_summary()` + new output blocks; new JSON paths `NBM_SENTRY_JSON_PATH` / `NBM_WALKFORWARD_JSON_PATH`. Both scripts auto-run via `run_digest.sh`'s `analysis/*.py` sweep — no orchestration changes needed.

</details>

<details>
<summary><strong>v0.6.456 • August 21, 2026 (F3 NBM audit — applied_layer + specialist attribution)</strong></summary>

- **F3-A applied_layer stamp now NBM-aware** — `forecast_snapshot.py` selector loop overwrites `{f}_applied` with the deepest NBM layer picked (`l3_nbm`/`l4_nbm`/`l5_nbm`/`l6_nbm`/`chp_nbm`/`wdp_nbm`) instead of leaving the HRRR-walker's stamp in place. Downstream `analysis/_prod.prod_error(row)` now returns the NBM-side residual for NBM-served rows via `error_{applied}`. Fixes systematic Prod-attribution misclassification across every prod-error-based analysis (mae_over_time, anomaly_detector, all `h_*_stage1.py`, digest scoreboards) — they were scoring HRRR-layer errors on NBM-served rows.
- **F3-B specialist attribution** — chp_nbm and wdp_nbm now stamp distinct `ch_chp_nbm` / `wd_wdp_nbm` layer values instead of overwriting `ch_l4_nbm` / `wd_l3_nbm` in place. Pair-log layer iteration extended to include `chp_nbm` / `wdp_nbm` so `error_chp_nbm` / `error_wdp_nbm` are emitted per row. Selector's deepest-NBM-layer walk picks these when fired: `wdp_nbm > l3_nbm` for wd; `chp_nbm > l4_nbm > l3_nbm` for ch. Specialists' lift can now be measured independently.
- **F3-C l6_nbm_fit reads backstamp** — `analysis/l6_nbm_fit.py` switched from `cached_path(PAIR_LOG_URL)` to `pair_log_paths()`, matching l3/l4/l5 NBM fitters. Latent (L6_NBM is ENABLED=False today) but ready for enablement.
- **F3-D deferred** — nbm_backstamp still only writes `error_l3_nbm`; backfilling `error_l4_nbm`/`l5_nbm`/`l6_nbm` for pre-08-21 rows is non-trivial and diminishes as live coverage grows over the next ~28 days.

</details>

<details>
<summary><strong>v0.6.455 • August 21, 2026 (debug page — post-NBM-cascade sweep, F1-F12 punch list)</strong></summary>

- **F1 chart LAYER_STYLE** — extended for `l4_nbm`, `l5_nbm`, `l6_nbm`, `chp_nbm`, `wdp_nbm` (all dashed to flag as NBM-cascade, mirroring HRRR-side colors).
- **F2 FIELD_LAYERS** — cascade config extended per field: cc/ch gain `l4_nbm`; ch also gains `chp_nbm`; sr gains `l5_nbm`; t gains `l6_nbm`; wd gains `wdp_nbm`. Deep NBM layers now render on the per-field trajectory charts.
- **F3 SHIP_EVENTS** — annotations added for L4_NBM (cc/ch), L5_NBM (sr), L6_NBM scaffold (t), chp_nbm (ch), wdp_nbm (wd), and the selector-armed cell flips (wg/dp/cc).
- **F4 per-field pipeline architecture table** — NBM cascade descriptions for t / cc / ch / sr updated to reflect today's shipped layers (t→l6_nbm scaffold; cc→l4_nbm; ch→l4_nbm→chp_nbm; sr→l5_nbm).
- **F5 current-state card** — "NBM parallel cascade" line rewritten from "LIVE with L3 filled" to "STRUCTURALLY COMPLETE" listing every shipped layer; L3_NBM sub-tile promoted to a broader NBM-cascade tile; "Upcoming" section retired the "L4_nbm next, ~4 sessions" language.
- **F6 Recent activity** — 08-21 entry added with all 5 ships (v0.6.450 clamp + v0.6.451-454 NBM cascade completion + deploy incident); 08-20 relabeled "1 day ago", 08-19 relabeled "2 days ago".
- **F7 L1 card meta line** — rewritten from "L4/L5/L6/specialists still to build" to the full shipped cascade.
- **F8 fit-status tiles** — three new tiles below the L3 tile, each async-fetching its curated JSON: 🧮 NBM L4 (cc/ch × 24 hours), 🧮 NBM L5 (regime × hour + fallbacks), 🧮 NBM L6 (scaffold, ENABLED=False).
- **F11 L1 router card** — v0.6.432 router card marked RETIRED with a banner, opacity dimmed. Superseded by the L1 selector 2026-08-19 v0.6.437; "current state" cells describe the retired router only.
- **F10 deferred** — applicability map is data-driven; adding NBM layer descriptors is a backend `describe_applicability()` addition per module, not a debug-page HTML fix.

</details>

<details>
<summary><strong>v0.6.454 • August 21, 2026 (NBM parallel pipeline — chp_nbm specialist)</strong></summary>

- Mirror of HRRR `ch_persistence_gate` (chp) on the NBM cascade. Reuses the HRRR-side gate primitives (`_cell_fires`, `_lead_band`, `_diurnal_skip`, `_load_table`, `_persistence_source`) — the NBM sibling cannot drift from the HRRR gate rule.
- On cells where the (regime × lead_band) table says SHIP/MARGIN and the diurnal skip doesn't suppress, overwrites `ch_l4_nbm` in place with the current-obs persistence value (Kalman-blended `hourly[0].cloud_cover_high`, clamped to [0,100]). Stamps `ch_chp_nbm_fired = True` for pair-log attribution.
- Overwrite-in-place matches the wdp_nbm precedent from v0.6.440 — the selector reads the deepest NBM layer for ch (l4_nbm), so a chp override on l4_nbm flows naturally through the existing selector substitution with no changes.
- Regime source: current-tick synoptic (same source HRRR chp uses).
- Completes the NBM specialists sweep for this cascade. clp_nbm is N/A (NBM doesn't emit cl, so cl has no NBM cascade to specialize). wdp_nbm shipped v0.6.440. chp_nbm ships here.

</details>

<details>
<summary><strong>v0.6.453 • August 21, 2026 (NBM parallel pipeline — L6_NBM shape-only scaffold)</strong></summary>

- Shape-only mirror of HRRR L6 (`cove_correction.py`) on the NBM cascade. t-only, scaffold shipped `ENABLED=False` so the parallel slot exists in the pair log / selector chain and enablement is a one-line flag flip once the fit against L5_NBM baseline lands.
- HRRR L6 has been disabled since 2026-07-01 after per-row Production data exposed both cove branches as double-counting L2's waterfront-weighted Kalman blend. Whether the same double-count applies to NBM's L2 is a separate investigation; until then L6_NBM stays dormant.
- New `weather_collector/processors/l6_nbm.py` (regime × wind-octant × hour cove Δ°F — no-op today) + `analysis/l6_nbm_fit.py` stub (fits `(sb_active × octant)` and `hour_local` means from pair-log `error_l3_nbm` for t; 14-day exponential decay, 30-day retention, MIN_PAIRS_PER_BIN=20).
- `forecast_snapshot.py` — L6_NBM stamp block after L5_NBM. Uses `wd_l3_nbm` per lead + heuristic `sb_active` (sea breeze fires 13-18 EDT with S-half wind). Branch gated on `_L6_NBM_ENABLED`, so today nothing is stamped.
- Selector substitution walks `t → l6_nbm > l3_nbm` (t skips L4_NBM + L5_NBM, matching HRRR t which skips L4/L5).
- `forecast_error_log.py` layer list gains `l6_nbm` in both branches so `forecast_l6_nbm` / `error_l6_nbm` will land in the pair log once the module is enabled.
- `l1_selector_fit._nbm_prod_error` chain now walks `error_l6_nbm > error_l5_nbm > error_l4_nbm > error_l3_nbm`.
- Curated JSON stub `weather_collector/data/l6_nbm_cove_curated.json` created with empty `delta_by_octant` / `hour_delta_sb_off` tables.

</details>

<details>
<summary><strong>v0.6.452 • August 21, 2026 (NBM parallel pipeline — L5_NBM shadow-live)</strong></summary>

- Mirror of HRRR L5 (regime × hour_of_day solar bias) on the NBM cascade. sr-only, applied to `sr_l3_nbm` (sr skips L4_NBM by design — sr not in L4_NBM_FIELDS).
- New `weather_collector/processors/l5_nbm.py` applier + `analysis/l5_nbm_recompute_biases_hourly.py` fitter. Fit reads pair-log sr rows with `forecast_l3_nbm`, bias = `forecast_l3_nbm − observed` indexed by (regime × hour_local), 30-day retention, MIN_CELL_N=30 per cell with regime-overall fallback when n≥50. Sun-up gate at SUN_UP_THRESHOLD=50 W/m² (mirrors HRRR L5).
- `forecast_snapshot.py` — L5_NBM stamp after L4_NBM block. Uses current-tick synoptic regime (same source HRRR L5 uses via `_wdp_state_curr`); per-lead sun-up gated on `sr_raw_nbm`. Identity fall-through when regime unknown or curated cell unfit.
- Selector substitution now picks deepest available NBM layer: `sr_l5_nbm > sr_l3_nbm`, `cc/ch_l4_nbm > l3_nbm`, else `l3_nbm`.
- `forecast_error_log.py` layer list gains `l5_nbm` in both branches so `forecast_l5_nbm` / `error_l5_nbm` land in the pair log.
- `l1_selector_fit._nbm_prod_error` walks `error_l5_nbm > error_l4_nbm > error_l3_nbm`.
- Curated JSON: all hour cells null, only `se_flow` fallback populated (+286 W/m², n=71) — table warms as more `forecast_l3_nbm` sr rows accumulate.

</details>

<details>
<summary><strong>v0.6.451 • August 21, 2026 (NBM parallel pipeline — L4_NBM shadow-live)</strong></summary>

- Mirror of HRRR L4 diurnal residual on the NBM cascade. New `weather_collector/processors/l4_nbm.py` applier + `analysis/l4_nbm_fit.py` fitter, scoped to `L4_NBM_FIELDS = ("cc", "ch")` (mirrors HRRR `L4_FIELDS`). Applier reads `l4_nbm_curated.json`, exposes `l4_nbm_correction(field, hour_of_day)`; forecast_snapshot stamps `{f}_l4_nbm = {f}_l3_nbm − correction` per hour right after the L3_NBM block.
- Fitter is recency-weighted (TAU_DAYS=14, retention 30 days) over `error_l3_nbm`, per (field, hour-of-day) 24-bin, publishes when n≥20 per bin.
- `forecast_error_log.py` layer list gains `l4_nbm` in both branches so per-layer `forecast_l4_nbm` / `error_l4_nbm` land in the pair log.
- `l1_selector_fit._nbm_prod_error` now prefers `error_l4_nbm` when the row carries it, falling back to `error_l3_nbm`.
- `forecast_snapshot`'s selector substitution reads the deepest available NBM-side layer: `{f}_l4_nbm` for cc/ch when populated, else `{f}_l3_nbm`.
- Curated JSON starts empty (all bins null); apply is identity fall-through until `l4_nbm_fit.py` warms up the bins. Digest sweep picks it up automatically (`analysis/*.py` discovery).

</details>

<details>
<summary><strong>v0.6.450 • August 21, 2026 (clamp percent fields to [0,100], sr to ≥0 in _round_for)</strong></summary>

- cc l3_nbm (and any other percent-field layer stamp) could push past 100 when the L3_NBM per-lead signed bias was subtracted from an already-high raw. `_round_for` in `forecast_snapshot.py` had no domain clamp — every layer array (`{f}_l1`, `{f}_l2_nbm`, `{f}_l3_nbm`, etc.) trusted the upstream value. Added domain clamps for the five percent fields (`pp`, `cc`, `cl`, `cm`, `ch`) to `[0, 100]` and `sr` to `≥ 0` at the single choke point, so every layer stamp is clean without touching each call site.

</details>

<details>
<summary><strong>v0.6.449 • August 20, 2026 (debug page — trim Recent activity to last 3 days)</strong></summary>

- Recent activity list had accumulated 11 days of entries (08-10 → 08-20). Trimmed to the most recent 3 (08-19 + 08-20). Older entries live in the changelog/session-log memory files.

</details>

<details>
<summary><strong>v0.6.448 • August 20, 2026 (debug page — restore "MAE data refreshed …" header stamp)</strong></summary>

- `renderPerFieldSnapshot` had an early return `if (!todayCells.length) return;` that fired whenever the `pf-today` column was empty — which has been the case since v0.6.439 removed that column from the DOM. That early return skipped the `mae_over_time.json` fetch entirely, so the header's `MAE data refreshed <ts>` stamp (which happens inside the fetch's `.then`) never fired and the label sat at the loading placeholder. Removed the early return; the fetch runs unconditionally, and the empty `todayCells.forEach` becomes a no-op.

</details>

<details>
<summary><strong>v0.6.447 • August 20, 2026 (debug page — stale-language sweep for post-v0.6.445 state)</strong></summary>

- Full-page sweep of `corrections_debug.html` to retire pre-arm language now that the L1 selector is LIVE. Removed "warming up · earliest arm ~2026-09-17 (Phase 4 selector)", "identity fall-through until per-lead bins clear n≥20", "not user-visible until Phase 4 selector arms", "Phase 4 selector — earliest arm date ~Wed 09-17". Updated version references from v0.6.436 (Phase 4 stub) to v0.6.445 (armed). Corrected in-scope field list on the L1-selector methodology block (was "5 fields: t/ws/wg/wd/h", now the full 9 NBM emits). Rewrote the L3_NBM fit-status tile subtitle from "warming up" to "LIVE — 373/384 cells filled". Rewrote the pipeline-architecture NBM-parallel entry from "shadow (Phase 1/2/3)" to "LIVE". Added a 2026-08-20 "today" entry to Recent activity with the v0.6.443-446 narrative.

</details>

<details>
<summary><strong>v0.6.446 • August 20, 2026 (debug page — Selector column in per-field pipeline architecture is now data-driven)</strong></summary>

- Ends the hardcoded-drift risk on the Selector column of the per-field pipeline architecture table. New JS block reads the same `l1_selector_table_curated.json` as the live selector table below and populates each of the 9 cells (t/h/ws/wg/dp/cc/ch/sr/wd) with the current per-band pick, grouping contiguous same-source bands into ranges (`HRRR 0-11h · NBM 12-47h`, `NBM all leads`, etc.). Falls back to "warming — see live table below" if the JSON is unreachable.

</details>

<details>
<summary><strong>v0.6.445 • August 20, 2026 (NBM backstamp shipped: L3_NBM bins fit + L1 selector flips 9 cells to NBM)</strong></summary>

- **`analysis/nbm_backstamp.py`** — new tool. Walks pair log, joins with the 2,455 backfilled NBM point extracts at `gs://myweather-data/nbm_backfill/`, reconstructs `l2_nbm = raw_nbm + (l2_hrrr − raw_hrrr)` using snapshotted HRRR forecast_l1/forecast_l2 (exact live Kalman delta at that tick), stamps `error_raw_nbm/error_l2_nbm/error_l3_nbm` (+ sin/cos for wd) on 237,143 historical rows. Two-pass mode: first pass fits L3 identity, second pass applies fitted L3 bias for honest Prod-vs-Prod. Writes to `~/.cache/myweather_nbm_backstamp/forecast_error_log_backstamped.jsonl`. Non-destructive to live pair log.
- **`weather_collector/data/l3_nbm_curated.json`** — fresh fit against backstamped log. **373/384 (field, lead) cells filled** (all 9 fields × 48 leads; only ch has 11 sparse leads). Was 0/192 before backstamp.
- **`weather_collector/data/l1_selector_table_curated.json`** — Prod-vs-Prod fit, 30-day window. **9 cells now pick NBM**: wg 12-23h (+5.7%), wg 24-47h (+8.9%), dp 6-11h (+16.1%), dp 12-23h (+18.4%), dp 24-47h (+23.2%), cc 0-5h (+9.7%), cc 6-11h (+9.7%), cc 12-23h (+19.6%), cc 24-47h (+17.7%). Router-scope ship-gate NBM lift = **+8.5% on n=74,528**. All other cells correctly stay HRRR (HRRR-side cascade wins t/ws/h/wd/ch/sr — chp specialist dominates ch, Lsr for sr, etc.).
- **Debug page**: L1 selector table and 🧮 NBM L3 fit-status tile pick up the new curated JSONs after cache-flush. Collector deploy (`make deploy-collector`) required to actually change user-facing wg/dp/cc values.

</details>

<details>
<summary><strong>v0.6.444 • August 20, 2026 (debug page — unify Selector-picks placeholder wording)</strong></summary>

- Follow-up to v0.6.443: dp/cc/ch/sr still said "pending first fit" (placeholder from v0.6.442), while t/h/ws/wg/wd said "warming — see live table below" (v0.6.443). Unified all 9 warming cells to the latter — same state deserves the same phrase, and it points readers to the live L1-selector table on the same page.

</details>

<details>
<summary><strong>v0.6.443 • August 20, 2026 (debug page — blank stale Selector-picks cells in per-field pipeline architecture)</strong></summary>

- Selector-picks column for t/h/ws/wg/wd in the "Per-field pipeline architecture" table showed hardcoded v0.6.432-router bands ("HRRR 0-11h · NBM 12-47h", "NBM all leads", etc.) that were left over from the pre-v0.6.440 router. Prod-vs-Prod selector (v0.6.440) replaced the router and currently falls through to all-HRRR while pair-log warms up, so those cells were contradicting the live L1-selector table below on the same page. Blanked to "warming — see live table below" (opacity 0.7) matching the pattern already used for dp/cc/ch/sr. Restore live-source strings when the chooser starts flipping cells post-backstamp.

</details>

<details>
<summary><strong>v0.6.440 • August 19, 2026 (NBM cascade expanded to 9 fields; L1 selector rewritten to compare Prod-per-source; scoreboard v2 rollup extended with per-cell drill-down and pipeline value-add framing)</strong></summary>

- **NBM cascade expanded — ch, sr, dp, cc added to `_L2_NBM_FIELDS` + `L3_NBM_FIELDS`.** `forecast_snapshot.py` now stamps `l2_nbm` + `l3_nbm` for all 9 fields NBM emits (t/ws/wd/wg/h + ch/sr/dp/cc). sr has no HRRR L2, so `l2_nbm_sr = raw_nbm` passthrough — honest identity when no L2 delta exists. `l3_nbm_curated.json` stub extended to 8 scalar fields + wd sin/cos.
- **L1 selector rewritten to compare Prod-per-source (not raw-per-source).** `analysis/l1_selector_fit.py` walks pair-log rows and computes HRRR-Prod (deepest applied HRRR-side layer via priority list: `dpbp/wsbp/wdp/clp/chp/l6/l5/l4/l3/l2/l1`) vs NBM-Prod (`error_l3_nbm`). Picks argmin per (field, band) subject to `n ≥ 200 AND lift ≥ 3%`. Fixes the Phase 4 v0.6.436 design flaw where selector picked NBM raw over HRRR raw for fields with deep HRRR-side cascade — for ch, HRRR-side (Lc + chp) hits 11.5 MAE while NBM raw is 19.4; raw comparison would have wrongly picked NBM and lost 8 MAE. Prod-vs-Prod comparison picks HRRR correctly.
- **First fit under new logic:** all cells fall through to HRRR because only ~5-6h of `error_l3_nbm` in pair log (Phase 3 shipped this morning). Selector is safe (no user output change from HRRR baseline) while pair log fills over the next 1-2 weeks.
- **Scoreboard v2 extended:**
  - Prod MAE now uses `error_{applied_layer}` per row (not top-level `error` which is L2 residual by legacy). Fixes previous under-reporting of Lc/chp/wdp/etc. contributions for cm/ch/wd/etc.
  - Best-public baseline uses argmin(HRRR, NBM) for in-scope fields; HRRR-only for out-of-scope. Fixes previous unfair -49% REGRESS on ch by comparing Prod to a source the selector couldn't pick.
  - Rollup gains: `n_fields_touched` vs `n_fields_all`, verdict counts (STRONG/GOOD/WATCH/REGRESS), per-cell drill-down (`largest_gain`/`largest_regression` per (field, band)), selector-confidence % of cells, halves-agreement % of fields, `mae_pct_of_hrrr` block (HRRR/NBM/best-chosen/Prod as ratio-of-HRRR).
  - Per-(field, band) cells emitted in `per_field_band` block for future drill-down UI.
- **Debug page — Tile 1 shape iterated multiple times this session, landed on OLD scoreboard's headline shape** (mean lift + median + all-fields + winning-fields counts). Retired the National Source Score tile (not diagnostic for Wyman Cove); added Cell drill-down tile (largest gain/regress per (field, band)). Colors on numbers instead of "green/amber/red" text labels.
- **Debug page — Pipeline column in per-field status table** rewritten to show HRRR-side cascade + NBM-side cascade for each field. ch/cc/sr/dp updated from "raw_nbm only (out of scope)" to "raw_nbm → l2_nbm → l3_nbm".
- **FIELD_LAYERS** on the accuracy chart config: ch/sr/dp/cc rows gain L2 (NBM) + L3 (NBM) entries so those layers plot on the chart.
- **`nbm_backfill_scoreboard.aggregate()`** extracted as reusable function (previously inline in `scoreboard()` printer).
- **Publisher CF gains `scoreboard_v2` in the PUBLISHERS list** — refits hourly at :00 UTC alongside `mae_over_time.py`.
- **Known-broken (afternoon cleanup queue):**
  - Selected column in Right Now table still uses majority-vote across bands — misleading for fields with mixed picks. Should either be deleted or replaced with per-band strip (H·H·N·N) or MAE of picked source.
  - `-39% MAE mean 7d` reflects real state (sr Prod is worse than raw NBM by 5×, dominating the arithmetic mean). Will fix as selector flips sr to NBM once pair-log accumulates `error_l3_nbm` for sr.
  - Style guide inconsistencies across tiles: mixed vocab (positive/negative lift vs STRONG/GOOD/WATCH vs green/amber/red), mixed separators (`/` for both windows and category counts).
  - Data-quality investigation of NBM sr (nighttime-only extract?) and NBM dp (implausibly good?) was resolved as "extract is healthy" but scoreboard v2's opportunity-gap column still shows misleading +100% for sr.

</details>

<details>
<summary><strong>v0.6.439 • August 19, 2026 (Debug page — pipeline-status table reshaped to complement scoreboard v2; numeric columns dropped, Pipeline column now shows HRRR + NBM cascades side-by-side, new Selector column)</strong></summary>

- **"Current pipeline state — per-field snapshot" reshaped and retitled to "Per-field pipeline architecture + status".** Companion role rather than redundant one: scoreboard v2 (above) carries the data-driven numeric MAE columns; this table carries the architecture + hand-curated narrative journal.
- **Columns changed:** Field | ~~Applied layers~~ Pipeline | ~~7d avg~~ | ~~24-hour~~ **Selector** | Status. Dropped the two numeric columns (7d/24h) — now shown in scoreboard v2 per-field row.
- **Pipeline column** shows two lines per cell: **HRRR:** current-side cascade (L1 → L2 → ... → specialists) and **NBM:** parallel-side cascade (raw_nbm → l2_nbm → l3_nbm + wdp_nbm) OR "raw_nbm only" (extracted, no L3_NBM stack) OR "not extracted" (NBM doesn't publish).
- **New Selector column** shows majority pick per field: NBM all leads (ws/wg/wd), HRRR 0-11h + NBM 12-47h (t), NBM 0-11h + HRRR 12-47h (h), HRRR (out of scope for fields with no NBM cascade). Colored blue for NBM picks, gray for HRRR — same convention as the 🎯 selector tile lower on the page.
- **Intro paragraph rewritten** to reflect the new companion-role framing.
- **renderPerFieldSnapshot()** kept but early-return check removed — function still populates the .pf-status status prefixes ("cc status loading…" spans in the Status column) and the narrative/audit blocks below the table.
- **No collector deploy needed** — pure frontend changes + scoreboard_v2.json already published in v0.6.438.

</details>

<details>
<summary><strong>v0.6.438 • August 19, 2026 (Scoreboard v2 SHIPPED — Prod vs best-public argmin(HRRR raw, NBM raw); 4 rollup tiles + per-field detail table; retires pre-Phase-4 "vs raw" framing)</strong></summary>

- **New publisher `analysis/scoreboard_v2.py`.** Reads pair log; emits `scoreboard_v2.json` to GCS with two windows (7d, 24h) × 14 fields. Per-field cell: HRRR raw MAE, NBM raw MAE, best_public (argmin), selector_pick, Prod MAE, lift_vs_best_public_pct, halves_a/b lift, halves_agree, n, confidence (HIGH/MED/LOW/NA), verdict (STRONG/GOOD/WATCH/REGRESS/NA). Rollup collapses to Section-1-4 summary: value_add_mean_pct, winning_fields green/amber/red, national_source_score (HRRR wins / NBM wins / insufficient), local_correction_value (does Prod add value on top of the selected source?), health confidence bucket counts.
- **Confidence thresholds (Q3 agreed with Joe):** HIGH = `|lift| ≥ 10% AND n ≥ 200 AND halves-agree`; MED = `|lift| ≥ 3% AND n ≥ 50`; LOW = below; NA = unavailable.
- **Verdict thresholds (Q4 defaults):** STRONG = `lift ≥ 10% AND halves-agree`; GOOD = `lift ≥ 3%`; REGRESS = `lift ≤ -3%`; WATCH = between.
- **Rollup exclusions** match the legacy scoreboard: `pp` (Brier), `pa/pr` (no MAE stack), `cc/dp` (derived — would double-count components).
- **Publisher CF wired.** `publisher/main.py` PUBLISHERS list gains `scoreboard_v2`; refits hourly alongside `mae_over_time.py` at `0 * * * *`.
- **Debug page — `renderScoreboardV2()` async fetch + render.** Replaces two pre-Phase-4 renderers: `#scorecard-banner` (top tiles) now shows 4 rollup tiles (value-add / national source score / local correction value / health); `#headlineBox` Right-Now table now shows per-field HRRR / NBM / Selected / Prod / lift / halves / n / confidence / verdict columns. Old `renderScorecardBanner` + `renderPerFieldSnapshot` marked deprecated but kept as dead code pending removal (the pf-snapshot table lower on the page still calls the latter for its numeric columns).
- **First fit surfaced 2 data-quality signals worth follow-up:** NBM `sr` raw MAE = 0.0 (nighttime-only extract; daytime sr not landing in extract or joiner). NBM `dp` raw MAE = 0.881 vs HRRR 2.875 (3× better, implausibly low — probable unit or coverage issue). Both are scoreboard doing its job — surfacing signals we didn't have visibility into pre-v2. Neither blocks the ship.
- **Session context:** the -37% value-add-mean over 7d is HONEST — pre-Phase-4 (all of last week), Prod was HRRR-cascade-only; NBM raw beats HRRR + corrections for many fields (esp. wg, wd, ch); the scoreboard correctly says "you weren't picking the winning source". As post-Phase-4 pair-log rows accumulate (Prod for wg/wd/etc. becomes NBM-cascade output ≈ NBM raw), value_add will trend toward 0 (identity to selected source) or positive (where corrections add lift).

</details>

<details>
<summary><strong>v0.6.437 • August 19, 2026 (Phase 4b — wdp NBM sibling wired; v0.6.432 L1 router retired; NBM cascade now inherits wdp coverage on cells the selector routes to NBM)</strong></summary>

- **v0.6.432 L1 router retired.** Deleted `weather_collector/processors/l1_router.py` + the `apply_l1_router(weather_data)` call in `collector.py`. Router was scope-limited by its NWS-gridpoint data source (3 fields: t/ws/wd @ leads ≥6h). Phase 4 selector (v0.6.436) supersedes on all counts: wider scope (5 fields including wg + h), stronger evidence base (30-day scoreboard vs router's 14-day), post-cascade application (all corrections apply first, selector picks last). Ship-gate met at +18.8% aggregate NBM lift on router-scope. No hypothetical dead-code retention — deleted cleanly per CLAUDE.md rule.
- **Router tile hidden on debug page.** `#sec-l1-router` block collapsed to `display:none` with a retirement comment; loader script no-ops on the null element. Keeps historical `l1r` pair-log rows readable via the accuracy chart's inert layer key until the 30-day pair-log retention window rolls it out.
- **Phase 4b — wdp NBM sibling.** `wd_persistence_gate.py` gains public helpers `should_fire_at(fc_regime, lead_h)` and `persistence_value(weather_data)` extracted from the existing gate logic. `forecast_snapshot.stamp()` reads state_curr + state_fc_by_lead + current wind_direction once outside the loop; inside the wd_l3_nbm computation block, applies the same predicted-transition persistence override to `wd_l3_nbm` that HRRR-side wdp applies to `hourly.wind_direction`. Stamps `wd_wdp_nbm_fired` for telemetry. Same curated table (`wd_persistence_gate_curated.json`), same 5 SHIP cells, same gate semantics — just applied to the NBM cascade output too, so cells the selector routes to NBM don't silently lose wdp's −2.7% MAE contribution.
- **Signature extended.** `append_forecast_snapshot(..., current=None)` — new arg so the snapshot can read the persistence source without pulling in the full `weather_data`. `collector.py` passes `weather_data.get("current")`.
- **Not built (deliberately deferred):**
  - `wg_residual_persistence_nbm` — HRRR-side is still `ENABLED=False`, shadow-only. Building the NBM sibling before the HRRR-side clears its 7-day gate is premature.
  - Specialists for fields the selector doesn't route (chp/clp/dpbp/L4/L5/L6) — N/A, those fields stay HRRR-side.
- **Architectural note.** Duplicated-specialist pattern (this ship) is the pragmatic path today. Long-term cleaner is source-agnostic specialists that run AFTER the selector — one specialist chain per field, applied to whichever value the selector picked. That's a Phase 7-ish refactor.

</details>

<details>
<summary><strong>v0.6.436 • August 19, 2026 (Option-1 Phase 4 SHIPPED — L1 selector arms; per-(field, lead-band) argmin(HRRR, NBM) picks user-visible forecast; first ship of user-facing NBM cascade output beyond the v0.6.432 router)</strong></summary>

- **Phase 4 — L1 selector LIVE.** New `weather_collector/processors/l1_selector.py` loads `weather_collector/data/l1_selector_table_curated.json` at import; exposes `pick_source(field, lead_h) -> "hrrr"|"nbm"`. `forecast_snapshot.stamp()` runs the selector after all NBM cascade stamping: for each hour × field, if `pick == "nbm"`, replaces the user-visible `{field}` value with `{field}_l3_nbm`. HRRR fall-through when the field/band is out of scope or the cell hasn't cleared its n/lift floors — safe default equal to pre-Phase-4 Prod behavior. Selector source stamped as `{field}_selector_source` in forecast log; pair-log joiner picks it up as `pair["selector_source"]` for per-row Prod attribution.
- **Phase 4 — Selector table fitter.** New `analysis/l1_selector_fit.py` reuses the `nbm_backfill_scoreboard.aggregate()` join (backfill + pair-log MAE evidence). Emits per-(field, lead-band) `{source, hrrr_mae, nbm_mae, lift_pct, n}`. Scope = `t / ws / wg / wd / h` (fields with L3_NBM coverage). Pick rule: NBM iff `n ≥ 200 AND lift_pct ≥ 3.0` (asymmetric threshold favors HRRR fall-through — safe default). Refits nightly; pair-log's `error_l3_nbm` will supersede backfill signal as bins warm up. Reproducible: `python3 -m analysis.l1_selector_fit`.
- **Initial table (2026-08-19 fit, window 30d, n up to 6,100/cell):**
  - **t:** HRRR at 0-11h (short-lead HRRR wins −15.8%/+2.3%), NBM at 12-47h (+9.8%/+16.5%)
  - **ws:** NBM at all leads (+11.2% to +22.7%) — expansion beyond router's leads-≥6h scope
  - **wg:** NBM at all leads (+39.1% to +48.2%) — largest expansion, wg wasn't in router
  - **wd:** NBM at all leads (+16.1% to +23.6%) — expansion to include 0-5h
  - **h:** NBM at 0-11h (+9.2% to +19.6%), HRRR at 12-47h (+1.4% within noise / −8.3% NBM hurts) — h is the ONE field where HRRR wins long-lead
- **Ship gate met.** Router-scope (t/ws/wd @ leads≥6h) selector-side aggregate NBM lift = **+18.8% on n=32,288**. Per plan: Phase 4 ship gate requires selector to deliver ≥90% of v0.6.432 router's measured long-lead lift. Selector delivers same or better across router's scope, plus expands to wg + short-lead ws/wd + short-lead h.
- **v0.6.432 router coexists during 14-day post-ship watch.** Rip-out follows once selector clears its watch clean. Coordination: for cells where router already picks NBM at L1, downstream HRRR-cascade output ≈ NBM cascade output (station-bias delta cancels), so selector's pick on those cells is a near-no-op that reaffirms router. For cells the router doesn't touch (wg, all fields at leads 0-5, h at 6-11h), selector delivers new user-facing NBM output.
- **Refactor.** `analysis/nbm_backfill_scoreboard.py` split — aggregation logic extracted to `aggregate()` function, printed scoreboard now a thin wrapper. Selector fitter imports `aggregate()` directly so both use the same join code and same window semantics.
- **Debug page — 🎯 selector tile ARMED.** Placeholder retired; now fetches `l1_selector_table_curated.json` and renders per-(field, lead-band) pick table (NBM cells highlighted blue, hover for raw HRRR/NBM MAE + n), fitted_at, ship-gate summary. Section header LIVE badge.
- **Cost audit fix (from same session).** Backfill CF Makefile spec downsized from 8vCPU/8GB to 2vCPU/4GB after tracing yesterday's ~$20 spend to Cloud Functions Gen2 compute at the over-provisioned spec. Backfill is I/O-bound (byte-range fetches from NBM S3), so cheaper spec doesn't hurt throughput. Per-invocation cost dropped ~$0.76 → ~$0.20.

</details>

<details>
<summary><strong>v0.6.435 • August 19, 2026 (Option-1 Phase 3 — L3_NBM fit + apply scaffolded; per-lead scalar bias for t/ws/wg/h + circular sin/cos bias for wd; debug page Phase 3 fit-status tile)</strong></summary>

- **Phase 3 — L3_NBM apply.** New `weather_collector/processors/l3_nbm.py` loads `weather_collector/data/l3_nbm_curated.json` at import; exposes `l3_nbm_bias(field, lead_h)` for scalar fields (t/ws/wg/h) and `l3_nbm_wd_components(lead_h)` for wd. Identity fall-through (0.0 / (0.0, 0.0)) until a bin clears the `min_pairs_per_lead` floor (default 20). `forecast_snapshot.stamp()` stamps `{field}_l3_nbm` inside the same NBM loop right after `_l2_nbm`: scalars subtract per-lead bias; wd uses circular `atan2(sin(l2_nbm_rad) − sin_corr, cos(l2_nbm_rad) − cos_corr)`. Shadow-only in Phase 3 (selector wiring is Phase 4).
- **Phase 3 — pair log picks up l3_nbm + per-layer sin/cos for wd.** `forecast_error_log.py` per-layer emit loop (both wd branch + main) adds `"l3_nbm"` → rows carry `forecast_l3_nbm` + `error_l3_nbm`. For wd rows, per-layer `error_sin_{lyr}` + `error_cos_{lyr}` are now emitted across every layer so the L3_NBM_wd fit consumes proper radian-space residuals (matching decay_fit's top-level wd_components path); future NBM cascades reuse the same signal.
- **Phase 3 — fitter.** New `analysis/l3_nbm_fit.py`: reads pair log, filters to `error_l2_nbm` (scalar) and `error_sin_l2_nbm`/`error_cos_l2_nbm` (wd) within 30-day window, weights by `exp(−age_days/14)`, publishes per-(field, lead) mean bias when `n ≥ 20`. Writes `weather_collector/data/l3_nbm_curated.json` in-place. Design decision (pair-log-only training, not backfill): matches training-serving parity because `l2_nbm` residuals depend on live station-bias Kalman state at time-of-obs — snapshotted only in the pair log. Backfill still funds L4_NBM diurnal work + independent-window audits.
- **Scope decision — wd included.** Initial scoping dropped wd (linear-mean circular residual pollutes with wraparound). Reversed because wd_nbm reaches user-visible output via the v0.6.432 L1 router at leads ≥6h — it's the L3_NBM field with the tightest closed loop to prod. Fit via sin/cos component branch mirrors HRRR-side `wd_components`.
- **Fitter picks up new layer.** `decay_fit.py` per-layer aggregation loop adds `l3_nbm`. `analysis/mae_over_time.py` `PERMISSIVE_LAYER_KEYS` adds `("l3_nbm", "error_l3_nbm")` so per-day rollup carries the new series.
- **Debug page — Phase 3 fit-status tile.** 🧮 new tile between Phase 0 infra and Phase 4 selector placeholder. Fetches `weather_collector/data/l3_nbm_curated.json`, shows fitted_at, in-window n_pairs, per-field filled/48 leads + pair counts (t/ws/wg/h + wd sin/cos row). `LAYER_STYLE` gains dashed `l3_nbm` (slightly deeper blue than `l2_nbm` to preserve raw→l2→l3 visual ordering). `FIELD_LAYERS` gains `L3 (NBM)` on t/ws/wg/h/**wd** tiles.
- **Debug page hygiene.** Phase 0 infra tile: fields-extracted list now includes `h` (was missing; corrected in Phase 2 re-audit); backfill target corrected `2,880 → 2,568` (107 days × 24). Phase 4 selector placeholder text refreshed to reflect Phase 3 scaffolded; cross-references the new fit-status tile.
- **Smoke test:** first fit against ~10h of pair-log data scanned 477K rows, kept 112 in window, published 0/192 scalar cells (all n<20 as expected during warmup), wd 0 pairs (per-layer sin/cos hasn't deployed yet — starts on next collector cycle after this deploy).
- **Not yet:** version bump + this changelog + commit + `make deploy-collector`. Backfill still running in background (started 04:45 EDT, 7 targeted gap slices, ~60min wall). L4_NBM diurnal + Phase 4 selector both blocked on L3_NBM window fill (rule-of-thumb ~2 weeks).

</details>

<details>
<summary><strong>v0.6.434 • August 18, 2026 (Option-1 Phase 2 — L2_nbm stamped in pair log for t/ws/wg/wd/h; debug page L2/L2_nbm overlay + selector placeholder; NBM extractor gains RH:2m)</strong></summary>

- **Phase 2 — L2_nbm plumbing.** `forecast_snapshot.py` gains `_L2_NBM_FIELDS = (t, ws, wd, wg, h)` and stamps `{field}_l2_nbm` per hour using `l2_nbm = raw_nbm + (l2_hrrr − raw_hrrr)`. Rationale (v1 approximation): station-derived corrections treated as model-agnostic — the delta L2 computed for HRRR is what the NBM cascade would also need. Refinable at Phase 5+ once station-vs-NBM bias data accumulates. `wd` uses signed circular delta wrapped into `[0, 360)`. Fields covered = intersection(L2-touched, NBM-emitted) minus derived (dp = Magnus, cc = Ccd). E2E synthetic test + first-tick prod verification: all 5 fields stamping cleanly.
- **Phase 2 — pair log picks up l2_nbm.** `forecast_error_log.py` per-layer emit loop (both wd branch + main) adds `"l2_nbm"` → rows carry `forecast_l2_nbm` + `error_l2_nbm`. Same forward-only migration pattern as `raw_nbm` in v0.6.433.
- **Phase 1 gap fix — RH:2m added to NBM extractor.** Full-inventory audit of `blend.tHHz.core.fFFF.co.grib2` (208 messages) turned up `RH:2 m above ground` at idx line 96. Missed in the initial 8-field extractor. Now 9 fields: t / dp / ws / wd / wg / sr / cc / ch / **h**. `_NBM_FIELDS` in `forecast_snapshot.py` mirrors. Same audit confirmed **no pressure** anywhere in the NBM CO grib (55 unique field:level combos, zero PRES/PRMSL/MSLP) — NBM's product is impact-weather-focused; pressure users go to raw HRRR/GFS. So `pr` joins `cl` and `cm` as HRRR-only forever (single-candidate selector). `pa` / `pp` extraction deferred pending unit audit.
- **Phase 2 debug page — L2/L2_nbm overlay.** `LAYER_STYLE` gains `raw_nbm` (dashed light blue, matches raw dash convention) and `l2_nbm` (dashed L2-blue). `FIELD_LAYERS` gains `raw_nbm` for all 9 NBM-emitted fields (t/dp/ws/wd/wg/sr/cc/ch/h) and `l2_nbm` for the 5 L2_nbm-covered ones (t/ws/wd/wg/h). Chart lines appear once the Fitter accumulates a day of data (`error_raw_nbm` / `error_l2_nbm` propagating through `per_layer_mae_by_lead`).
- **Phase 2 debug page — L1 selector placeholder tile.** 🎯 collapsed tile below the L1 router tile: "L1 selector — per (field, lead-band) source picker (not yet armed — Phase 4)". Design intent doc-string inside. Placeholder preserves layout so it doesn't jump when Phase 4 wires it live.
- **Fitter picks up new layers.** `decay_fit.py` per-layer aggregation loop adds `raw_nbm` + `l2_nbm`. `analysis/mae_over_time.py` `PERMISSIVE_LAYER_KEYS` adds `("raw_nbm", "error_raw_nbm")` + `("l2_nbm", "error_l2_nbm")` so daily-obs rollup carries both series once populated.
- **Deploys:** collector (Phase 2 stamping + h field consumption), nbm-ingester (h field extraction), nbm-backfill (h field extraction) all redeployed. Backfill round 3 in flight with `overwrite=1` so previously-written cycles get rewritten with 9-field schema.
- **Memory:** [[nbm-cloud-fields-finding]] corrected re: h field. [[pair-log-dual-source-schema]] scoreboard-lift design section added (Joe request PM — dual-baseline lift: Prod vs raw HRRR, Prod vs raw NBM, Prod vs best raw; Phase 4+ UI intent locked).

</details>

<details>
<summary><strong>v0.6.433 • August 18, 2026 (Option-1 Phase 0/1 — full parallel HRRR/NBM cascade foundation: NBM extractor + backfill CF + hourly ingester CF + raw_nbm stamped in pair log; plus v0.6.432 router-sweep polish)</strong></summary>

- **Option-1 architecture pivot (PM design session).** Decision to build full parallel HRRR/NBM cascades (per-source L1..L6, selector on finished L6 output) rather than the L1-seed router shipped as v0.6.432. Reason: router is a post-cascade override that fights the wrong residual model at routed cells — cheap and dishonest. Option 1 is the only design that never corrupts corrections. v0.6.432 stays running through Phase 4 (selector ship gate), then rips out. Full plan + phase-by-phase in `project_08_18_evening_handoff_build.md` memory.
- **Phase 0 — NBM extractor (new `weather_collector/fetchers/nbm_point.py`).** Fetches NBM CO 2.5km grib from `noaa-nbm-grib2-pds` public S3 by byte-range against the .idx sidecar (avoids full-file downloads), cfgrib-parses each message, extracts Wyman Cove point values. Fields emitted: t / dp / ws / wd / wg / sr / cc / ch (8 fields; unit conversions to app-native). Full-inventory grib audit resolved the 3× `TCDC:reserved` ambiguity: NCEP local level codes 195/196/197 have no defined meaning — **NBM CO does NOT publish cl/cm**, only cc (TCDC:surface) and ch (TCDC:high cloud layer). Selector will always pick HRRR for cl/cm (single-candidate forever). Memory: `project_nbm_cloud_fields_finding.md`.
- **Phase 0 — Backfill CF (new `nbm_backfill/`).** Deploy target `make deploy-nbm-backfill`. HTTP-triggered, params `start_date` / `num_days` / `cycles` / `leads` / `overwrite` / `parallel`. Writes one `nbm_backfill/YYYYMMDD_HH.json` blob per cycle to `myweather-data` (JSON payload = `{cycle, lat, lon, leads: {N: {field: value}}}`). Cycle-level ThreadPoolExecutor (default 8 concurrent cycles × 6 lead-fetches each). Resume-friendly (skip-if-exists unless overwrite=1). 3600s timeout, 8 vCPU, 8GB memory, max-instances=10. Currently running to populate 120-day archive; NBM AWS retention discovered to start ~2026-05-03 so effective coverage is ~107 days.
- **Phase 0 — Hourly ingester CF (new `nbm_ingester/`).** Deploy target `make deploy-nbm-ingester`. Runs on Cloud Scheduler `myweather-nbm-ingest-schedule` every hour at :45 UTC. Picks the freshest cycle in the T-2h..T-6h window (checks .idx availability at f047 as "fully published" proxy), extracts all 47 leads for 8 fields, writes `nbm_point_extract.json` to GCS. IAM: `myweather-collector` SA granted `roles/run.invoker` on the CF for the scheduled OIDC-token invocations.
- **Phase 1 — raw_nbm stamping in pair log (`forecast_snapshot.py` + `forecast_error_log.py` + `collector.py`).** Collector loads `nbm_point_extract.json` from GCS each tick (best-effort — missing blob is a no-op) and passes to `append_forecast_snapshot(nbm_extract=...)`. Snapshot builds a `lead_valid_utc` → field-values map, aligns each snapshot hour's local-ET timestamp to a UTC key, stamps `{field}_raw_nbm` for the 8 NBM-emitted fields. `_derive_applied_layer`'s `target_utc` computation hoisted out of the nws-specific branch since both nws and raw_nbm need it. `forecast_error_log.py` per-layer emit loops (both wd branch and main branch) now include `raw_nbm` → pair rows get `forecast_raw_nbm` + `error_raw_nbm`. Forward-only migration; legacy pair-log rows carry no `_raw_nbm` column and age out of the 30-day window naturally. Pair-log dual-source schema locked in memory: `project_pair_log_dual_source_schema.md`.
- **Phase 0 — Debug page tile.** New collapsed section immediately below the L1 router tile: 🏗️ "NBM parallel-cascade infra (Phase 0 build) — ingester + backfill status". Fetches `nbm_point_extract.json` from `data.wymancove.com`, renders latest cycle, cycle age, fetch age, `n_ok`/47 leads, and a lead-1 sample line (8 field values). Backfill coverage bar deferred (needs a manifest generator).
- **v0.6.432 router-sweep polish (bundled here).** `mae_over_time.py` adds `l1r` to `PERMISSIVE_LAYER_KEYS` so the daily rollup carries the router's own MAE series alongside raw/l2/l3/l4/l6 (independent of `applied_layer`-keyed `prod_real`). `corrections_debug.html` adds `l1r` (distinct cyan) to `LAYER_STYLE` + `FIELD_LAYERS` for t/ws/wd before `prod_real`; SHIP_EVENTS annotation for 2026-08-18. L1 router log line converted from `logging.info(...)` to `print(..., flush=True)` (same pattern as MEMPROBE pre-v0.6.414 — root logger drops INFO under Cloud Run's WARNING default).
- **Memory index compaction.** `MEMORY.md` rewritten one-line-per-entry, 19.8KB → 14.5KB. New `🎯 Subsumed by v0.6.432 router` section listing long-lead t/ws/wd investigations bypassed at ≥6h. Session logs pruned to recent-only. New READ-FIRST entry points for Phase 0 handoff + option-1 plan.
- **Root `requirements.txt` gains cfgrib + xarray + numpy** (needed by nbm_backfill + nbm_ingester CFs; not imported by collector or publisher so no bloat there beyond image size). cfgrib bundles eccodes via `ecmwflibs` — no system package needed.

</details>

<details>
<summary><strong>v0.6.432 • August 18, 2026 (L1 router — NWS/NBM at ≥6h leads for t/ws/wd; production wins retained at short lead)</strong></summary>

- **The finding that forced this ship (same day as v0.6.431 shipped the plumbing):** 14-day head-to-head between NBM (via S3 grib backfill) + HRRR (S3 grib backfill) vs. current production, n≈2100 rows per field per lead, halves-stable. **At leads ≥6h, NBM beats production by +6% to +24% MAE for t / dp / ws / wd / wg.** At leads 1-3h, production still wins for those fields (station-blend + wdp + wind_blend + short-lead corrections carry real signal that no external model matches). Cloud stack (cc / cl / cm / ch) vindicated — production wins by -13% to -161%. dp / cl / cm / ch investigations survive intact.
- **Ship — l1_router.py:** new processor. Runs AFTER decay_apply (cascade complete) and BEFORE forecast_snapshot. For each hour in `hourly.times` where lead ≥ `_MIN_LEAD_H=6`, mutates `hourly.corrected_temperature` / `wind_speed` / `wind_direction` to the NWS-gridpoint (NBM-derived) value with unit conversion (°C→°F, km/h→mph, deg unchanged). Preserves pre-router array as `<field>_pre_router` and per-hour attribution as `<field>_router_source` list (`prod` / `nws`). Falls through to cascade output when the NWS value is missing. Snapshot's L1 slot still reads `hourly.temperature` / `raw_wind_speed` / `raw_wind_direction` = raw model, so pair-log historical baseline is unchanged.
- **Excluded fields (phase 2 pending NBM grib ingester on GCF):** wg (biggest single win at 14-day, NBM +11-27% at leads ≥3h — no NWS-gridpoint counterpart), sr (NBM/HRRR +5-20% at ≥3h — no NWS-gridpoint counterpart), dp (derived from t + humidity via Magnus; needs coordinated override with routed t). Cloud stack (cc / cl / cm / ch) NOT routed — production wins those; nothing to fix.
- **What breaks and what doesn't:** cloud, pressure, precip, wg, sr investigations FULLY SURVIVE. Short-lead (1-3h) investigations for all fields SURVIVE. Long-lead correction layers for t / ws / wd that were fit against Open-Meteo residuals are BYPASSED at ≥6h — they don't fire under the router. Fitter will still emit their coefficients from historical data but they don't shape user-facing forecast at those leads.
- **Sources tab:** `fetch_all.py` now exposes `nws_gridpoints_meta` into `weather_data.sources` as key `nws_gridpoints`; `js/sources.js` `SOURCE_META` adds the row (name "NWS / NBM", description flags the router's role at leads ≥6h for t/ws/wd) and lists it in `CRITICAL_SOURCES` since the router now depends on it.
- **Debug-page + pair-log sweep (same version):** added `l1r` as a first-class pipeline layer. `forecast_snapshot.py` layers dict adds `l1r` slot for t / ws / wd (reads the post-router live array); the same file's `l4` / `l6` / `wdp` slots now read from `<field>_pre_router` fallback so `error_l4` / `error_l6` / `error_wdp` continue to score the CASCADE'S honest output even after the router overwrites the live array. `_derive_applied_layer` walk appends `"l1r"` at the end so applied-layer attribution correctly stamps `l1r` on routed hours. `forecast_error_log.py` per-layer emit loops (both wd branch and main) add `l1r`. `decay_fit.py` per_layer_mae_by_lead aggregation adds `l1r`. Frontend `obschart.js` `maeAt()` prefers `l1r` over `l4` so the 6h/24h accuracy tile shows what users actually saw, not the shadow cascade MAE.
- **Rollback:** set `_ROUTER_ENABLED = False` in `weather_collector/processors/l1_router.py` and re-deploy collector.
- Related: `project_nbm_hrrr_l1_triage.md` memory file — full 14-day per-(field, lead) scoreboard, damage assessment, phase 2 plan.

</details>

<details>
<summary><strong>v0.6.431 • August 18, 2026 (NWS gridpoint activated as forecast source — frame expansion begins)</strong></summary>

- **Frame audit outcome (overdue since 07-10):** correction stack has been at a local optimum for weeks. MAE flat, gate churn dominating ship list, 6-for-6 CLOSED MISS on 08-17 all from same failure class. Root cause: daily digest is a closed loop over the pair log, which contains only HRRR/GFS/Pirate — no periodic step asks "are we consuming the right inputs?" Discovery: **NWS gridpoint (NBM-derived official NWS forecast) has been fetched at every tick for months and used only for briefing narrative text — never as a forecast source, never in the pair log, never benchmarked against our HRRR/GFS/Pirate blend.**
- **Ship — NWS gridpoint plumbing:** `forecast_snapshot.py` now stamps `{short}_nws` per hour for t / dp / pp / ws / wd by aligning NWS gridpoint validTime intervals to our hourly grid and applying unit conversions (degC → F, km/h → mph). `forecast_error_log.py` extends the per-layer emit loop with "nws" so pair rows carry `forecast_nws` + `error_nws`. `decay_fit.py` extends per-layer MAE aggregation to include "nws" so standard reporting works. `collector.py` passes `weather_data["nws_gridpoints"]` into the snapshot writer.
- **What this unlocks:** starting with the next collector tick, every pair row that has an aligned NWS gridpoint value gets a forecast_nws + error_nws column. Within 24-72h enough data accumulates for a per-field NBM-vs-current-blend benchmark. If NBM wins on a field, promote it to L1 (or route per-field). Existing correction stack cascades on top unchanged.
- **Scope excluded:** h (no equivalent in gridpoint), cc/cl/cm/ch (no equivalent), sr (no equivalent), wg (would need separate gustSpeed handling), pa (unit choice for precip amount TBD). If the pilot works, expand.
- **What's on hold pending pilot outcome (2-3 weeks):** no new Stage 0 hypotheses inside the pair log, no new dynamic-gate migrations beyond items already in-flight (chp v0.6.421 walker, Ccd v0.6.429 walker), no debug-page sweeps except in response to real state changes. Daily sentries still run.
- Related: [[feedback_frame_exhaustion_watch]] (new), [[feedback_ship_count_by_impact_class]] (new), [[project_plan_pipeline_to_good]] rewritten with input-frame expansion on top.

</details>

<details>
<summary><strong>v0.6.430 • August 18, 2026 (Lc recent-bias gate — ch cleared per-field 7/7, ship)</strong></summary>

- `h_lc_recent_bias_gate.py` cleared **ch** per-field: 7/7 distinct days, PROMOTE streak 11. cl and cm remain CHURN (in and out of the promoted set) and stay out.
- Runtime already armed (`LC_RECENT_BIAS_GATE_ENABLED = True` since v0.6.413); this deploy just carries the updated `lc_recent_bias_gate.json` into the collector image so `fields_cleared: ["ch"]` takes effect in prod.
- Zero user-visible change today — all 3 ch cells have `gate_apply=True` right now (recent bias agrees with historical in sign+magnitude, or is thin). Value is the safety net: when a ch cell's recent bias flips or halves, prod suppresses the historical shift instead of applying a wrong-signed correction.
- Only clean signal in today's 155-script digest. Every other flip (`h_lc_ema_stage1_baseline` "LOOKBACK WINS", `h_lc_rolling_window` W=21d, `h_frontal_t_bias_stage0` promote→hold) is either leaky (obs-time-keyed feature build, same class as yesterday's 5 CLOSED MISS) or CHURN.

</details>

<details>
<summary><strong>v0.6.428 • August 17, 2026 (Lc gate rule direct-MAE — CLOSED MISS same-day, 3rd leakage catch of the session)</strong></summary>

- **Investigating why cm's per-field walker in `h_lc_recent_bias_gate.py` isn't clearing** (day 0/7 despite 4/7 recent PROMOTE days). Root cause identified: cm/50-80 today has recent bias +44.7 vs historical +42.8 (ratio 1.04, sign OK → gate says "on") but live shift produced holdout MAE 39.84 vs raw 30.40 (Lc HURTS by 31%). Bias-ratio proxy missed a case where signs and magnitudes match but recent obs pattern makes live's shift over-correct.
- **Proposed rule change:** replace sign+magnitude proxy with direct held-out MAE comparison — `gate_apply = m_live ≤ m_raw × 1.05`. New scripts `analysis/h_lc_gate_rule_stage0.py`, `h_lc_gate_rule_stage1.py`.
- **Stage 0 "HIT" (+8.8% cm) retracted — leakage.** Rule used m_live and m_raw computed on the HOLDOUT window both to DECIDE suppression AND to SCORE it. Same class as this morning's EMA obs-time-vs-run-time leakage and the h-predictor same-window halves check. Third instance of the pattern in one session.
- **Honest walk** (decision from recent 3d, disjoint holdout 3d for scoring): proposed rule makes ZERO different decisions from current at any of 7 cutoffs for cm/cl/ch, net −0.3% for cc. cm's walker churn is a real feature of cm's regime volatility (recent-3d bias doesn't predict next-3d MAE), not a bug in the gate rule. Fixing would require predictive features (leading indicators of regime change), not better use of past bias data.
- **Both scripts kept as artifacts** with retraction headers, per the [[project_lc_ema_kalman_fallback]] pattern. Serve as the honest-comparison harness for future gate-rule ideas.
- **Session pattern:** four same-day closes today, three from same leakage-class trap. Consider extracting an `analysis/_walkforward_honest.py` shared harness on the next instance. See [[project_lc_gate_rule_direct_mae]] memo.
- Analysis-only — no collector deploy.

</details>

<details>
<summary><strong>v0.6.427 • August 17, 2026 (cl h-predictor router — CLOSED MISS same-day, 3rd cl-correction architecture to fail this session)</strong></summary>

- **Stage 0 + Stage 1 for h_fc as a cl router.** Two new scripts (`analysis/h_cl_h_predictor_stage0.py`, `h_cl_h_predictor_stage1.py`). Motivated by the closed EMA workstream ([[project_lc_ema_kalman_fallback]]) — needed to test a "different feature space" for cl. Physical hypothesis: clouds form near saturation, so HRRR's own h forecast should predict its own cl accuracy.
- **Stage 0 HIT (real, no leakage).** Multi-field join on (run_time, obs_time, lead_h) between cl and h pair-log rows. Univariate: cl MAE spans 9.97 (h=0-40%) to 21.46 (h=92-100%), a 2.15× spread. Bivariate: (cl_fc bin × h_fc bin) shows disagreement cells (cl-wet + h-dry, or cl-dry + h-wet) have MAE 20.29 vs agreement cells 12.77 — **1.59× ratio, real structural signal**. The extreme cell (cl=95-100 predicted + h=60-75 predicted) has MAE 83, HRRR's internal inconsistency screaming.
- **Stage 1 MISS (halves-unstable).** Only one routing scheme in the (N × condition) sweep cleared the 2% SHIP floor: N=6h persistence lookback, fire only when (lead ≥ 12h AND disagreement). Overall +2.5% on 14d held-out — but **halves-stability catastrophically failed**: Half A −35.5%, Half B +34.3%. The +2.5% was averaging noise.
- **h-predictor on cm/ch/cc for completeness.** cm/ch have larger univariate spread than cl (3.37×, 2.45×) but neutral disagreement ratio (~1.0×) — high-h rows just have higher baseline MAE. cc has the 1.54× disagreement ratio but ships via Ccd (derived), so router would be moot. **Only cl has routable disagreement structure, and cl won't monetize it stably.**
- **Session pattern:** 3 cl-correction architectures failed today (Lc rolling-window MISS, EMA/Kalman MISS via leakage, h-predictor MISS via halves). cl may be genuinely beyond shift-table-family correction — the 07-30 `_FIELD_SKIP` is starting to read as the correct long-term answer, not a bandage. See [[project_cl_h_predictor]] memo for full closeout + [[project_plan_pipeline_to_good]] item 3 for updated status.
- Analysis-only — no collector deploy.

</details>

<details>
<summary><strong>v0.6.426 • August 17, 2026 (Lc EMA/Kalman fallback — CLOSED MISS same-day, honest sim exposes Stage 0 leakage)</strong></summary>

- **Stage 1a honest baseline check for the Lc EMA workstream.** New `analysis/h_lc_ema_stage1_baseline.py`. Compared EMA α=0.2 vs naive "mean residual over last N obs" lookback. Simple N=6 lookback beat EMA on 3/4 fields — red flag that the win wasn't from the exponential machinery. Then the leakage check: the obs-time-keyed shift lookup was giving corrections access to obs from up to 24h more recent than would be available at forecast issue-time.
- **Honest run-time-keyed sweep on cl:** every N ∈ {6h, 24h, 48h, 168h, 720h} HURTS cl at every lead band. Longer hurts more. Sim reproduces production Lc gains on cc (+27%), cm (+16%), ch (+58%), so it's validated — cl is uniquely broken. Shift-table architecture at any timescale is the wrong tool for cl's currently-unstable fit-target.
- **EMA/Kalman branch closed MISS.** Pipeline-to-good item 3 fallback path retired. cl un-skip is not achievable via any lookback variant; needs a different feature space (fc-trajectory, dew point depression, LCL height) or a persistence-of-obs specialist. See [[project_lc_ema_kalman_fallback]] memo for full closeout + meta-lessons on the two distinct leakage classes caught same-session.
- Header comment added to `h_lc_ema_stage0.py` noting the retraction. Scripts kept as artifacts + as the honest-comparison harness for future ideas.
- Analysis-only — no collector deploy.

</details>

<details>
<summary><strong>v0.6.425 • August 17, 2026 (Analysis truth-telling: pair-log `error` field sweep + Lc EMA/Kalman Stage 0)</strong></summary>

- **20-script analysis sweep — pair-log `error` field is L2, not production.** Morning triage on cm showed the field as CLEAN in `anomaly_detector` when real production was WATCH +32.6%. Root cause per [[feedback_top_level_forecast_is_l2]]: `error = forecast - obs` in the pair log uses the L2-value top-level `forecast` key (backward-compat for the Fitter). Analysis scripts treating `error` as production were silently reporting L2 residual instead.
  - New helper `analysis/_prod.py::prod_error(row)` — prefers `error_{applied_layer}`, falls back to `error_l4`, then top-level.
  - Batch 1 (production-visible metrics): `anomaly_detector`, `state_stratified_accuracy`, `regime_transition_audit`, `simulate_windows`, `dp_c1f_gate_stage1`.
  - Batch 2 (hypothesis Stage 0/1/2 + pressure_tendency + _run_bias_carryover): 15 files.
  - Left alone (correct usages): `decay_tau_tuning` (Fitter calibration exception), `mae_over_time` (already has `prod_real` path + wd L1_ONLY fallback).
  - **Post-fix verified:** anomaly_detector now shows cm WATCH +32.6%, cc drops to CLEAN (Ccd derivation catches it). Next digest run (08-18) picks this up automatically.
- **Lc EMA/Kalman fallback — Stage 0 HIT.** New `analysis/h_lc_ema_stage0.py`. Motivation: fixed-window rolling can't rescue cl (per [[project_lc_regime_conditional]] line 57). Simulate online EMA of `(fc_l4 - obs)` per (field, bin); two-phase per-obs_time processing avoids repeated-obs leakage. Result at α=0.2 on 14d held-out: cl beats raw L2 by **+33.5%** (halves A +13.3% / B +51.1%, STABLE ★), cc/cm/ch also STABLE ★ vs live prod. Advance to Stage 1: regime-slice halves, baseline-lookback compare, walkforward vs current pooled Lc. Retires the cl `_FIELD_SKIP` bandage if it clears. See [[project_lc_ema_kalman_fallback]].
- No collector deploy — analysis-only changes. Next digest run picks them up.

</details>

# v0.6.0 — Decay-correction milestone

<details>
<summary><strong>v0.6.424 • August 16, 2026 (Debug page sweep — clp fail, chp/Lsr gates seeded, MEMPROBE VmRSS, n&lt;100 rule)</strong></summary>

- **Debug page sweep** per Rule 5 (Debug Page is Canon). Today's ships (v0.6.417-423) + the clp walker FAIL + Joe's morning-red discussion needed to land on the page.
  - **Upcoming grid:** removed stale "Sat 08-16 clp Stage 3 flip" row; replaced with "Sat 08-23 Lsr recent-bias + chp cell gate earliest per-cell flip" + "clp deferred (08-16 walker FAIL min-J 0.250, fire set churned 7→3)."
  - **sr narrative:** updated the [[project_lsr_recent_bias_gate]] deferred-workstream pointer to reflect Stage 0/1 + Stage 3 wire OFF shipped 08-16 v0.6.420/421.
  - **Recent activity — 2026-08-16 entry:** title updated 2 ships → 4 ships. Afternoon block appended documenting v0.6.422 (pf-today fix), v0.6.423 (MEMPROBE /proc/self/status VmRSS switch), and the morning-red n&lt;100 rule ([[feedback_morning_red_n_floor]]) with the 4/4 discriminator experiment that motivated it.
- No collector deploy — descriptor-text edits only.

</details>

<details>
<summary><strong>v0.6.423 • August 16, 2026 (MEMPROBE now reads /proc/self/status VmRSS — ru_maxrss went weird today)</strong></summary>

- **`_rss_mib()` switched to `/proc/self/status` VmRSS on Linux**, with a `resource.getrusage` fallback for macOS dev. `ru_maxrss` had been reporting an implausible constant ~1.3 MiB across every tick and every instance today, despite yesterday's -00497 revision correctly reporting 47 → 854 MiB post-v0.6.415. Root cause of the change is unclear (nothing in the derivation moved between deploys), but `/proc/self/status VmRSS` gives actual current process RSS with no runtime interpretation and no lifetime-peak ambiguity — a cleaner primitive than `ru_maxrss` for per-tick memprobe.
- **Semantic change worth noting:** VmRSS is *current* RSS, not lifetime peak. That's actually more useful for the leak-hunt — we want to see what the process weighs per tick, not the high-water mark. Start/end deltas now represent real per-tick allocation, and start values across ticks on a warm instance show whether memory is climbing (leak) or returning to baseline (transient allocation).
- Data collection restart date is 2026-08-16 post-v0.6.423 deploy.

</details>

<details>
<summary><strong>v0.6.422 • August 16, 2026 (pf-today zero-baseline fix — pa was rendering "—" when clean)</strong></summary>

- **Per-field snapshot table's 24-hour column was rendering "—" for pa** instead of "0.0%" during clean windows. Cause: `if (rMae == null || rMae === 0)` treated a zero raw MAE as "no data" and short-circuited before checking prod. For pa specifically, `rMae === 0` is a legitimate value (no precip in the window, forecast said no precip, MAE=0) — not missing data.
- **Fix:** split the check. `rMae == null` → still "—" (genuinely missing). `rMae === 0` → keep computing prod, then branch: if `pMae === 0` too → render "0.0%" (both clean, contributes 0 to the overall mean); if `pMae > 0` → render `+<pMae> (raw=0)` in red (stack added error to a perfect raw, undefined %). Same latent bug lives in the `pf-status` 7-day span code path, not fired today because 7d rolling pa MAE is 0.0006 (tiny but non-zero); left alone until it fires.
- No collector deploy — corrections_debug.html JS-only edit.

</details>

<details>
<summary><strong>v0.6.421 • August 16, 2026 (chp dynamic gate Stage 0/1 + both Stage 3 wires shipped OFF)</strong></summary>

- **New `analysis/h_chp_cell_gate.py`** — retires the hand-typed `_CELL_SKIP` frozenset by making it dynamic. Reads today's `ch_persistence_gate_curated_vs_l6.json` (already regenerated daily by the existing preview script), decides per-cell "chp lost to L6 today?" using `delta_full_pct > +3%` (matches the vs_l6 script's own floor), appends to `.cache_chp_cell_gate_history.json`, and applies a conservative 7-day rule: `gate_apply = False` only if ALL 7 window days recorded a loss. Emits `weather_collector/data/chp_cell_gate.json`. Design differs from Lc/Lsr — chp is a substitution not a shift, so the gate is "recent chp-vs-L6 performance" rather than "recent bias direction agreement" — but the wire pattern and history semantics mirror the sibling gates.
- **Day 1/7 seeded.** Today's read: 13 cells register 'lose', 8 of them already in `_CELL_SKIP` (agreement with hand-typing), 2 static-skip cells actually WINNING today (se_flow/24-47 −5.4%, sea_breeze/24-47 −1.2% — the "parity precautionary" 08-13 adds now look over-cautious; gate will un-suppress them once history accumulates). 4 currently-LIVE cells losing: se_flow/6-11 (+28.7%), se_flow/12-23 (+10.2%), sea_breeze/6-11 (+6.3%), ne_flow/24-47 (+4.2%). Nothing cleared yet — walker at day 1/7, no cells suppressed.
- **`ch_persistence_gate.py` Stage 3 wire shipped OFF.** Adds `CHP_CELL_GATE_ENABLED = False` toggle + `_load_chp_gate()` + `_chp_gate_suppresses(regime, band)` + check inside `_cell_fires()` after the static `_CELL_SKIP` check. When flipped ON, dynamic gate becomes a superset of `_CELL_SKIP`; once dynamic consistently catches every static-skip cell, `_CELL_SKIP` retires. Same ship-ahead pattern as Lc v0.6.410 → v0.6.413.
- **`solar_correction.py` Stage 3 wire shipped OFF.** Adds `LSR_RECENT_BIAS_GATE_ENABLED = False` toggle + `_load_lsr_gate()` + `_lsr_gate_suppresses(regime, hour_local)` + check inside `compute_solar_correction()` after the `L5_SKIP_REGIMES` check. Runtime contract mirrors Lc's exactly: suppress iff ENABLED AND `"sr" in fields_cleared` AND `per_cell[regime][str(hour)].gate_apply is False`. Ship-ahead — v0.6.420 shipped the analysis script + runtime JSON yesterday morning; this ships the consumer OFF ahead of the per-field 7-day clearance.
- **Both wires verified inline** — module import + `_load_*_gate()` return non-empty gates today (both JSONs present), suppression helpers return False both with flag OFF and with flag ON (because gate histories have no cleared cells on day 1). No collector behavior change today; the wires are dormant hooks waiting for the flip.
- **Deployed** — collector redeploy required because runtime code changed even though behavior is unchanged; the wires need to be present when either flag flips.

</details>

<details>
<summary><strong>v0.6.420 • August 16, 2026 (Lsr recent-bias gate Stage 0/1 shipped — script only, no runtime change)</strong></summary>

- **Follow-on to v0.6.417 refit and [[project_lsr_recent_bias_gate]] opened yesterday.** This morning's digest showed sr per-field snapshot at +18.2% vs raw over the last 24h — yesterday's refit did not stop the bleed because the underlying raw sr bias flipped signs in 24h (raw −11.88 yesterday → +26.8 today). Another refit is the treadmill. Decision: leave L5 ENABLED=True (7 weeks of net-benefit vs 2 days of bad regime doesn't justify a kill switch), do NOT refit again, accelerate the gate build.
- **New `analysis/h_lsr_recent_bias_gate.py`** — mirrors `h_lc_recent_bias_gate.py`. Per-cell (regime × hour) gate: apply historical L5 shift only when recent-3d observed bias agrees with the historical bias in sign AND ≥50% in magnitude. Scored on a chronological 3d holdout with halves-strict Stage 1. Emits runtime table `weather_collector/data/lsr_recent_bias_gate.json` (schema mirrors `lc_recent_bias_gate.json`: per_cell decisions + fields_cleared + set_level_gate_clear + notes). Rolling 7-day gate history seeded today at `.cache_lsr_recent_bias_gate_history.json`.
- **Today's Stage 1 verdict: HOLD (safe but no gain).** Holdout window 08-13→08-15 predates today's regime flip so the gate has no signal to act on yet. One cell (sw_flow/11) correctly gated off — hist bias −428 vs recent −61 (ratio 0.14 << 0.5). Live-mode aggregates on this window: +31.6% vs raw pooled, gate would deliver +26.6% (−5pp cost to block sw_flow/11's occasional big win). When 08-16 obs land and roll into the holdout, sign-flip cells should surface.
- **Sign convention documented in-script** matching `solar_correction.py:272-273`: `bias = mean(fc − obs)`, `shift = −bias`. Belt-and-suspenders after this session's per-field snapshot sign-flip mistake ([[feedback_check_own_arithmetic]] — cross-file conventions vary).
- **Attribution frame:** uses `state_fc.regime_synoptic` (per-lead) rather than reconstructing issue-time regime. Matches how pair-log MAE is scored. Runtime consumer (Stage 3, not shipped) can pick issue-time or per-lead apply independently — gate decisions are cell-scoped either way.
- **Analysis-only change** — no collector code touched, no redeploy needed. Digest picks up the new script via the `analysis/*.py` convention. Day 1/7 seeded; earliest per-field clearance 2026-08-23. Stage 3 wire follows the same OFF-first pattern as Lc v0.6.413 → v0.6.417 flip.

</details>

<details>
<summary><strong>v0.6.419 • August 15, 2026 (Lc applicability descriptor honors _FIELD_SKIP — cc/cl no longer misreported as ENABLED)</strong></summary>

- **Bug fix in `cloud_saturation_correction.describe_applicability()`.** Live applicability_map was reporting `cc: ENABLED True. Cells for cc: 0-5: SHIP (shift +15.6); …` and `cl: ENABLED True. …` — misleading because both fields are in `_FIELD_SKIP` (cc since v0.6.390 2026-07-30 when Ccd took over cc derivation; cl since v0.6.389f 2026-07-30 when walk-forward showed cl broken under Lc). The descriptor read the global `ENABLED` flag but ignored per-field skips, so a reader of the applicability map would think Lc was actively shifting cc by −63.4 pts at the 95-100 bin.
- **Per-field skip reasons surfaced inline.** cc + cl now report `FIELD-SKIPPED` in both `fires_when` and `current_state`, with the skip reason (v0.6.390 Ccd takeover for cc; v0.6.389f walk-forward-broken for cl). Diagnostic cells still emitted at the end of `current_state` as "would apply if un-skipped: …" so the fit values remain visible for the parked [[project_lc_cl_unskip_investigation]] investigation. cm + ch descriptors unchanged.
- **Caught during today's applicability audit** (Joe asked "is the applicability section accurate?"). Real answer: mostly, except for this per-field skip gap. cc_from_derivation (Ccd) has no descriptor at all — separate small work item, not blocking.

</details>

<details>
<summary><strong>v0.6.418 • August 15, 2026 (pr L2 whitelist joins the 7-day streak walker)</strong></summary>

- **pr L2 gate now tracked by `whitelist_streak.py`** alongside chp/wdp/clp/wg_residual/dp_residual. Reason: today's `pr_l2_regime_lead_retro` cleared 2 new BOTH-WIN candidates (nw_flow/12-23h Δ+4.5%, sw_flow/12-23h Δ+2.6%) on top of the 2 shipped-live cells (nw_flow/{0-5h, 6-11h}). Session opened 2 dynamic-gate migration projects today, so shipping any expansion on a single day's read is exactly the pattern we're trying to escape. The walker provides the 7-day per-cell Jaccard≥0.8 stability check we don't get otherwise.
- **`pr_l2_regime_lead_retro.py` now emits `weather_collector/data/pr_l2_regime_curated.json`** in the walker's expected shape ({cells: {regime: {band: {verdict}}}}). Fire set (verdict=SHIP) = live SHIPPED_CELLS + today's BOTH-WIN candidates; everything else SKIP. Live cells always in the set so streak stability = "is the candidate set stable" without dropping live cells on days their halves-verify drifts.
- **Registry entry in `whitelist_streak.py`**: `"pr_l2"` with status LIVE. Day 1/7 seeded today with 4 fire cells; earliest clearance 2026-08-22. If streak holds, promote the 2 new candidates to `_PR_L2_FIRE_CELLS` in `corrected_hourly.py`. Analysis-side only — no collector redeploy needed.

</details>

<details>
<summary><strong>v0.6.417 • August 15, 2026 (L5 solar bias refit — stop the bleeding on sr regression)</strong></summary>

- **sr regression today** (Joe caught it observationally — "sr looking rough"). Confirmed via mae_over_time + per-(regime, band, day) pair-log walk: prod_real MAE 89.14 vs raw 80.97 last 24h (**+10%**), damage concentrated at short leads (0-5h +21.5%, 6-11h +28.8%) plus 24-47h (+10%). Bias flipped raw −11.88 → prod +38.48 — L5 added ~50 units in the wrong direction. Per-day trend: 08-14 was normal (−25.8%), today (08-15) flipped to +10.1% — today-only regression.
- **Root cause**: L5's `_BIAS_BY_REGIME_HOUR` static table was fitted historically when the model under-forecast sr in most regimes (large negative biases: nw_flow ~−130, se_flow ~−117, sea_breeze ~−104). Today the model flipped to over-forecasting in ne_flow (+285 bias!) and near-neutral in se_flow/sea_breeze. L5 blindly adds +100-125 W/m² anyway → amplifies error. Same failure mode as pre-08-15 Lc: static shift tables can't handle regime shifts.
- **Refit shipped** — `l5_recompute_biases_hourly.py` re-run on last 14d writes fresh `weather_collector/data/lsr_bias_table_curated.json` (processor auto-loads on next import). Key regime changes: **se_flow −117 → −60.7 (+56 units less over-correction)**, **sea_breeze −104 → −80.1 (+24 units less)**, sw_flow −138 → −146 (slightly deeper, matches recent bias), nw_flow tie, pre_frontal tie, ne_flow already `L5_SKIP_REGIMES` at issue-time (refit doesn't change ne_flow issue-time behavior; pair-log damage on ne_flow rows comes from forecasts issued in OTHER regimes that validate as ne_flow — structural quirk, not fixable by refit alone).
- **Architectural observation logged**: L5 skip is regime-at-issue (single tick value applied uniformly to all 48 leads) but pair-log scoring is `state_fc` regime-at-valid-time (per-lead). Deferred fix; needs dynamic recent-bias gate mirroring Lc. See [[project_lsr_recent_bias_gate]] (opened this ship as follow-on).
- **Not a code change** — only the curated JSON. But bundled with the collector redeploy so the new instance boots with the fresh table.

</details>

<details>
<summary><strong>v0.6.416 • August 15, 2026 (Debug page sweep — 4-ship day)</strong></summary>

- **Debug page sweep** per Rule 5 (Debug Page is Canon). Today's four ships changed enough state that the debug page had multiple stale references. Updated:
  - **Upcoming grid:** removed L6 Fix B row (closed UNCLEAN v0.6.412). Updated clp Stage 3 flip gate row for 08-16 to reflect today's day 6/7 status + n=5 fire set, and noted wg_residual + dp_residual also 6/7.
  - **Lc recent-bias gate section:** rewritten from "Stage 3 wire SHIPPED OFF · one-line flip on 08-15 clearance" → "SHIPPED ON 08-15 v0.6.413." Documents live no-op (0/3 ch bins gate_apply=False today) + 10:48 UTC telemetry verification + cl EMA/Kalman follow-on ([[project_lc_cl_unskip_investigation]]).
  - **C1 Stage 4 audit numbers:** three call-sites updated from "last HOLD 36.36%" → "last HOLD 65.00% (moved 57.14% → 65.00% on 08-15 re-cure)."
  - **Recent activity list:** added 2026-08-15 entry documenting all four ships + the two investigations that saved time by NOT acting (h WATCH mixture-shift, ch@6-11h sampling-luck). Bumped 08-14 tag "today" → "1 day ago."

</details>

<details>
<summary><strong>v0.6.415 • August 15, 2026 (MEMPROBE unit-bug fix — Linux branches were reversed)</strong></summary>

- **`_rss_mib()` branches swapped.** Verified live post-v0.6.414 deploy: 10:27 tick reported `start_rss=0.0 MiB`, 10:37 reported `start=0.8 MiB → end=1203.3 MiB` (delta +1202.5 MiB in 91s). Impossible values. Cause: the heuristic `return r / 1024 if r > 1_000_000 else r / 1024 / 1024` had macOS-bytes and Linux-kb branches reversed. Linux `ru_maxrss` returns kb (~800,000 for ~800 MiB RSS), which fails the `> 1_000_000` threshold → falls into the else → gets double-divided by 1024². Once memory crosses ~977 MiB, the kb value trips the threshold and hits the other (still-wrong) branch → looks like a huge jump. Fixed to `return r / 1024 / 1024 if r > 1_000_000 else r / 1024` — macOS bytes → MiB (÷1024²), Linux kb → MiB (÷1024).
- **Data collection restart date is now 2026-08-15 post-v0.6.415 deploy.** Everything before was garbage.

</details>

<details>
<summary><strong>v0.6.414 • August 15, 2026 (MEMPROBE actually emits now — silent no-op since 08-11 ship)</strong></summary>

- **MEMPROBE lines converted `logging.info` → `print(..., flush=True)`** in `weather_collector/collector.py` (lines 463 + 800). The 08-11 memory-probe telemetry ship never emitted a single line to Cloud Logging: the codebase has no `logging.basicConfig(...)` anywhere, so Python's root logger sat at default WARNING and silently dropped every INFO call. Verified by grepping Cloud Logging for the "Wyman Cove Weather" banner (also `logging.info`) — not one hit in a 5-day freshness window. Prints go straight to stderr → Cloud Logging.
- **Diagnostic thread:** Joe's memory nudge to "read MEMPROBE logs and follow up" had been stuck since 08-11 because there were literally no logs to read. Two weeks of "waiting on data" was masking a config bug.
- **Follow-on parked:** the broader logging-config gap (every other `logging.info` in the collector still drops silently — banner, decay fit timing, etc.) is a separate cleanup. Not doing it in this change because a global `basicConfig(level=INFO)` could balloon log volume across imported modules; needs a per-logger audit first.

</details>

<details>
<summary><strong>v0.6.413 • August 15, 2026 (Lc recent-bias gate FLIPPED ON — mechanism ships, standing plan item 3 closed)</strong></summary>

- **`LC_RECENT_BIAS_GATE_ENABLED = True`** in `weather_collector/processors/cloud_saturation_correction.py`. Standing plan item 3 closed: ch cleared its 7-day per-field streak today (7/7). Wire prep landed 08-14 v0.6.410; today is the one-line toggle.
- **Live impact today = no-op.** ch has 3 per-bin cells (0-5, 20-50, 50-80), all currently `gate_apply=True` (recent 3d bias tracks historical fit on sign + within magnitude 0.5× threshold on every bin). Gate suppresses **0 cells** on first tick. cl is `promoted_fields` but not yet `fields_cleared` (streak still building), so no suppression for cl either.
- **Why ship a no-op:** the gate is the self-healing mechanism for Lc drift. Every day it recomputes per-bin whether recent obs still match the historical fit and dynamically suppresses only cells currently wrong — the anti-scar-tissue counterpart to hand-curated `_CELL_SKIP` frozensets. Shipping it now means when a bin *does* drift (previously we'd hand-add a skip tuple), the gate demotes automatically and self-restores on recovery. Ship-ahead pattern (same as v0.6.407 runtime table + v0.6.410 wire prep).
- **Not a fix for today's ch@6-11h +372% Prod-vs-raw last-24h.** That's a sampling-luck window on n=60: Lc's bin-0-5 shift of +12.82 (fit over 2189 holdout) hit a 24h stretch where raw predicted ~0 clouds *and* obs actually were ~0. Gate would have to see the bin-level average drift (it hasn't), not a lucky window. Expected to self-heal as n accumulates.
- **Follow-on workstream opened:** [[project_chp_cell_skip_to_dynamic_gate]] — chp's `_CELL_SKIP` frozenset (grew 0 → 9 on 08-13 → 10 on 08-14) is the same hand-curated scar-tissue pattern the Lc gate replaces. Same design shape (per-cell rolling regression detector, dynamic suppress + self-restore) should apply to chp. Ranked below other in-flight work; opened here to prevent silent further growth of `_CELL_SKIP`.

</details>

<details>
<summary><strong>v0.6.412 • August 15, 2026 (L6 Fix B rolling gate — CLOSE UNCLEAN)</strong></summary>

- **L6 Fix B rolling gate CLOSED UNCLEAN.** 7-day watch opened 08-08 expired today. Final gate state: 8 distinct days, ship_days 4 / hold_days 4, `ship_bins` CHURN (6 bins flipped inside window: `sb_off|{03,04,06,07,10,11}`). Held-out +3.02% is real but the gate correctly refused to ship a churning shape — matches the 08-12 "high variance, working as designed" read. L2 Kalman already captures the microclimate signal; Fix B has nothing durable to add. Script keeps running as sentry; reopen only on ≥3 consecutive SHIP days with a stable `ship_bins` set.
- **Debug page:** removed L6 Fix B row from `OPEN_WATCHES` in `corrections_debug.html`. Staleness banner now empty (next stale gate is clp on 08-16).

</details>

<details>
<summary><strong>v0.6.411 • August 14, 2026 (L2 τ guardrail fix — post-mortem of today's t regression)</strong></summary>

- **t regression post-mortem** (Joe caught it observationally — "temp is uncharacteristically rough last 24h"). Confirmed via mae_over_time + last-48h per-(regime, band) pair-log walk: Prod-vs-raw last-24h **+9.2%** (was −1% to −3% for the prior week), all damage at **24-47h band: +19.3%**, worst regime nw_flow +14% (n=346). L2 was driving the damage (all layers past L2 read identically since t isn't in L3/L4/L6 fields). Root cause traced to **`l2_decay_history.json` entry at 2026-08-12T15:08**: fitter published `t_tau=inf` with held-out improvement **+0.04%** (noise-level). Two loader guardrails failed simultaneously — (a) `L2_GUARDRAIL_MIN_IMPROVEMENT_PCT = 0.0` accepted any barely-positive improvement, (b) the range-check on `fitted_tau < 1e8` **bypassed τ=inf entirely**. Result: 12h of forecasts issued 08-12T15:08 → 08-13T03:08 UTC with L2 fully non-decaying (correction at lead 30 = 100% instead of exp(-30/4) ≈ 0). Those forecasts validate 08-13/08-14 24-47h — exactly the damaged window we saw. Every fit since has been negative (-0.28% to -6.53%) and reverted to τ=4h, so damage will taper off naturally over the next ~48h as the poisoned forecasts age out.
- **Two guardrail fixes in `weather_collector/processors/corrected_hourly.py`.** (1) `L2_GUARDRAIL_MIN_IMPROVEMENT_PCT` raised from **0.0 → 0.5** — a signal-floor above noise. Historical fitted improvements sat between +0.15% and +0.55%, so 0.5% keeps only the clearer wins. (2) Removed the `fitted_tau < 1e8 and ...` bypass on the range check — τ=inf now gets the same `[0.25×, 4×]` sanity-range validation as any finite τ. Comment added at both sites naming the 08-14 incident.
- **Behavioral change to h**: fitted τ=inf held-out improvement is +0.36% (below new 0.5% floor) AND τ=inf is out of [60, 960]h range for h's default τ=240h — h now falls back to default τ=240h. Half-life ~7 days, docstring already called it "slow decay, bias persists" — very close to inf in practice. Acceptable trade of 0.36% MAE for guardrail robustness. t + pr already at default, no change.
- **Truth-table verified 6-way** against today's fitter output + the 08-12T15:08 incident row + one hypothetical legit accept + one hypothetical near-noise reject. All decisions match intent.

</details>

<details>
<summary><strong>v0.6.410 • August 14, 2026 (Stage 3 wire prep — Lc recent-bias gate ready for tomorrow's ch clearance)</strong></summary>

- **Standing-plan item 3 Stage 3 wire, shipped defensively OFF.** `weather_collector/processors/cloud_saturation_correction.py` now loads `weather_collector/data/lc_recent_bias_gate.json` (emitted by fitter v0.6.407) and — when `LC_RECENT_BIAS_GATE_ENABLED = True` — suppresses the historical Lc shift for cells where `field in fields_cleared` AND `per_cell[field][bin].gate_apply == False`. Runtime contract matches the JSON's `notes` field verbatim. New `_gate_suppresses(gate, field, bin_lab)` gate check + `cells_gate_suppressed` counter per field. `describe_applicability` names the gate state. Truth-table verified 5-way (disabled; enabled + empty cleared; enabled + cleared + apply=True; enabled + cleared + apply=False; back to disabled).
- **Toggle default False, ships today so tomorrow's ch clearance is a one-line flip + deploy.** Today's gate state: fields_cleared=[] (nothing cleared yet); ch streak 6/7 (earliest clear 2026-08-15), cm 0/7, cl 2/7. Even if flipped True right now the wire is a no-op because no field has cleared. Ship-ahead pattern same as v0.6.407 (runtime table shipped ahead of consumer).
- **New telemetry**: `weather_data["cloud_saturation_correction"]["recent_bias_gate"] = {enabled, gate_generated_at, fields_cleared}` + per-field `cells_gate_suppressed` count separate from `cells_demoted`.

</details>

<details>
<summary><strong>v0.6.409a • August 14, 2026 (debug page sweep for v0.6.409 + mid-sweep refactor to consume the existing cross_run_spread stamper)</strong></summary>

- **Debug page sweep for v0.6.409.** Session log entry added for 08-14 with all today's work. Correction Stack + Specialists + Post-ship watches updated to 10 `_CELL_SKIP` cells (was 9); new v0.6.409 post-ship watch entry through 08-28. ch row prose gets an 08-14 addition note for the pre_frontal/24-47 demote. Rolling date labels bumped: 08-13 → "1 day ago", 08-12 → "2 days ago", etc.
- **v0.6.409a mid-sweep refactor: confidence_layer consumes cross_run_spread stamper.** The sweep found that `weather_collector/processors/cross_run_spread.py` (v0.6.401g, 08-12) already stamps `weather_data["cross_run_spread"][field][vt] = {spread, xr_q, n}` per tick — 12h lookback, live-L1 inclusion, canonical semantics documented in the module. v0.6.409's `_c1_xr_per_band_field()` duplicated this less accurately (14-day forecast_log walk, no live-tick data). Refactored to read the stamper's output at each band's midpoint valid_time; deleted `_xr_quintile`, `_C1_XR_MIN_RUNS`, `_C1_XR_SNAP_KEY`, `_C1_XR_EDGES`, and the forecast_log loading (~70 lines dropped). Verified 14:27 tick post-redeploy: stamper produces 392 (field, vt) cells across 7 fields, confidence layer stamps 27 hits — semantics now match the stamper. Same failure family as [[feedback_analysis_tools_drift_from_runtime]], just on the writer side.

</details>

<details>
<summary><strong>v0.6.409 • August 14, 2026 (C1_xr cross-run spread wired + chp pre_frontal/24-47 demote + analysis-drift class fix)</strong></summary>

- **C1_xr — cross-run spread quintile marginal axis** (`weather_collector/processors/confidence_layer.py`, `analysis/c1_curate_confidence_table_v2.py`). Wires the axis unblocked today by `h_cross_run_spread_c1_stage2`'s PROMOTE (7 fields ORTHOGONAL to cluster_spread_q). Curator gates `by_xr_q` SHIP/MARGINAL to the ortho-promoted fields only (SHIP drops 206→109, only `[dp, h, pr, t, wd, wg, ws]`). Runtime `_c1_xr_per_band_field` computes live spread from `forecast_log.json` snapshots at each band's midpoint valid_time (≥3 runs required), bins via per-field edges from curated meta, composes a WIDEN/NARROW multiplier onto `displayed_mae` alongside C1h/C1d. New telemetry: per-cell `c1_xr` block, `live_axes.c1_xr_hits`, `gate_firing_log.record_firing("C1_xr", ...)`. C1 is still `ENABLED=False` — shadow-write only, verified 24 hits/tick on real data post-deploy.
- **chp pre_frontal/24-47 emergency demote** (`weather_collector/processors/ch_persistence_gate.py`). Extends v0.6.405's `_CELL_SKIP` with `("pre_frontal", "24-47")` — vs_l6 tool showed chp losing +101.59% to L6 baseline on this cell (biggest current chp loser). Nighttime target hours weren't covered by the existing diurnal skip window (10–18 local for `pre_frontal`), so the demote is required.
- **Analysis-drift class fix (3 sites, one pattern)** — see [[feedback_analysis_tools_drift_from_runtime]]. Analysis scripts on shipped targets now consult the processor state instead of just their curated JSON: (a) `h_ch_persistence_blend_stage2_vs_l6` subtracts processor `_CELL_SKIP` from `live_ship_set` — its WATCH count drops from "11 cells" to "2 cells" (worst sea_breeze/6-11 +1.74%, well below the +3% action floor); (b) `h_lc_rolling_window` imports `_FIELD_SKIP` and computes the verdict over runtime-active fields with a 5pp regressive-win guard — corrected verdict is SWITCH TO W=10d (real +4.6pp on ch, tied on cm), previously misled SWITCH TO W=3d (would have regressed ch by ~10pp); (c) `h_chp_midlead_regression` verdict text now labels its scope `STABLE-MIDLEAD-POOLED` and cites vs_l6 for the coverage it lacks (24-47h + per-cell damage).
- **KNOWN_LIVE_PIPELINES registry additions** (`analysis/runlog/build_executive_summary.py`). `h_wd_persistence_gate_stage1` + `h_wd_persistence_gate_stage2` added — Stage 3 wire shipped v0.6.382 2026-07-27 so today's fresh "STAGE 2 HIT — Move to Stage 3 wiring" verdict will auto-relabel STABLE. Same class of fix as the analysis-drift block above.

</details>

<details>
<summary><strong>v0.6.408a • August 13, 2026 (debug page sweep — v0.6.405 chp demote + v0.6.407 gate table + today's session log)</strong></summary>

- **Debug page sweep** (`corrections_debug.html`). Post-ship updates for today's 6 ships: ch row + What's-running list + Layers rollup all note the v0.6.405 chp emergency demote (9 mid/long-lead cells force-skipped via `_CELL_SKIP`). New Post-ship watch entry for chp v0.6.405 with 14-day window through 08-27. Recent-bias gate status updated with today's per-field streaks (ch 5/7, cm 3/7, cl 1/7 — cl newly PROMOTED) + v0.6.407 runtime table emit note. Session log entry added for 08-13 covering all 6 ships (v0.6.403–408); 08-12 rebranded from "today" to "1 day ago".

</details>

<details>
<summary><strong>v0.6.408 • August 13, 2026 (SHIP disqualifier scanner in exec summary)</strong></summary>

- **Per-ship disqualifier scanner** (`analysis/runlog/build_executive_summary.py`). New `ship_disqualifiers(name, verdict, current, log_dir)` runs three checks and appends `      ⚠ ...` lines directly under each SHIP-ELIGIBLE / STILL-CONFIRMING / NEW-CANDIDATES entry: (1) verdict text keywords THIN / UNSTABLE / CHURN / MARGINAL, (2) sibling `*_vs_l6` or `*_vs_l4` scripts in `hold` or `kill` bucket (WATCH etc.), (3) `walkforward_*_validator` PROPOSED CONFIG matching current live L3/L4 from `applied_layer_audit`. Motivated by 08-13 session review: four wrong ship reads in one morning, each because a disqualifier existed but was buried 3000 lines deep in the digest (THIN in same verdict line skimmed past, sibling vs_l6 WATCH verdict emitted no-verdict → no bucket → invisible, walkforward PROPOSED CONFIG matched live config verbatim). Smoke-tested on today's data: all three misses surface inline.

</details>

<details>
<summary><strong>v0.6.407 • August 13, 2026 (Stage 3 wire prep — recent-bias gate emits runtime table)</strong></summary>

- **h_lc_recent_bias_gate emits runtime table** (`analysis/h_lc_recent_bias_gate.py` → `weather_collector/data/lc_recent_bias_gate.json`). Per-cell gate decisions (`gate_apply`, `sign_ok`, `mag_ok`, `recent_bias`, `hist_bias`, `hist_shift`, `n_holdout`) now serialized alongside `promoted_fields` and `fields_cleared`. Runtime contract: `cloud_saturation_correction.py` must NOT apply the historical shift for `field in fields_cleared` AND `per_cell[field][bin].gate_apply == False`. All other cells (fields not cleared, or gate_apply True/None) use existing lc_correction_table behavior.
- **Prep for standing plan item 3 Stage 3 wire.** ch is currently day 5/7 per-field (earliest per-field clear 2026-08-15). Emitting the runtime table now means when ch clears, the collector has 2+ days of the table history ready to consume — no scramble on ship day. Today's table shows every cell gate_apply=True (recent bias tracks historical within ~20% on every ch bin), so shipping the wire today would be a no-op; the wire is defensive infrastructure for when bias drifts.

</details>

<details>
<summary><strong>v0.6.406 • August 13, 2026 (vs_l6 tools surface via WATCH verdict; digest bucketer picks it up)</strong></summary>

- **vs_l6 emits explicit verdict line** (`analysis/h_ch_persistence_blend_stage2_vs_l6.py`). Added `Verdict: WATCH — N live chp cell(s) lose to L6 baseline; worst {r}/{b} Δ={d:+.2f}%` (or `Verdict: CLEAN — ...` when no flips). Previously the tool wrote its ⚠ 9-cell warning as free text with no `Verdict:` prefix, so `build_executive_summary.py`'s bucketer couldn't classify it and the warning stayed buried in the per-script tail — exactly how the chp regression fixed in v0.6.405 went unremarked for 4 days.
- **Digest bucketer recognizes WATCH** (`analysis/runlog/build_executive_summary.py`). Added `"WATCH" in v` to the `hold` bucket keyword list. First run after this change routes vs_l6 through `no_verdict → hold` transition and surfaces it in "Changed verdicts". Same treatment applies to any other tool that emits `Verdict: WATCH — ...`.

</details>

<details>
<summary><strong>v0.6.405 • August 13, 2026 (chp emergency demote — 9 mid/long-lead cells losing to L6)</strong></summary>

- **chp emergency cell-skip** (`weather_collector/processors/ch_persistence_gate.py`). Added `_CELL_SKIP` frozenset with 9 (regime, lead_band) cells forced back to L4 regardless of curated verdict: calm/{12-23,24-47}, nw_flow/12-23, pre_frontal/12-23, se_flow/24-47, sea_breeze/{12-23,24-47}, sw_flow/{12-23,24-47}. Source: `h_ch_persistence_blend_stage2_vs_l6.txt` "9 live cell(s) flip → SKIP under L6 baseline" with Δ ranging +9.7% to +34.9% (parity cells se_flow/24-47 and sea_breeze/24-47 included precautionarily). Diagnosis: Prod-vs-L6 MAE gap on ch widened monotonically from +3.4 (08-06) to +12.7 (08-13) — chp shipped 07-19 v0.6.358 keeps forcing persistence-of-obs in cells where L6+Lc is materially better on 10-day held-out. Encoded in processor (not JSON) because the fitter regenerates the curated JSON daily and JSON edits would be transient. Prior watches [[project_ch_chp_regression_watch_08_07]] + [[project_ch_chp_midlead_band_watch_08_10]] closed clean 08-09/08-10 but the gap started widening after — new regression class in the same mid/long-lead bands. Reversibility: remove any tuple from `_CELL_SKIP` to re-enable.

</details>

<details>
<summary><strong>v0.6.404 • August 13, 2026 (walkforward Lc regime SHIP-set stability tracker)</strong></summary>

- **New analysis script** (`analysis/walkforward_lc_regime_ship_stability.py`). Companion gate for `walkforward_lc_regime.py`. Parses today's SHIP cell list out of `analysis/output/walkforward_lc_regime.txt`, appends to `.cache_walkforward_lc_regime_ship_history.json`, and reports a stability verdict (BUILDING / UNSTABLE / READY) over a 7-day window. Motivation: today's walkforward returned VERDICT PROMOTE +3.06% with 16 SHIP cells, but the Stage 1 `.cache_lc_regime_gate_history.json` ship count has drifted 92→50 over the past 2 weeks with big daily flips. Before wiring Stage 3, need to confirm the walk-forward-verified 16-cell set is itself time-stable across the same 7-day window. Retention 30d, window 7d — same shape as `h_lc_regime_stage1.py`'s gate. Day 1/7 seeded today (n=16). Earliest READY verdict: 2026-08-20.

</details>

<details>
<summary><strong>v0.6.403 • August 13, 2026 (GoMOFS fail-fast — stop the collector timeout cascade)</strong></summary>

- **GoMOFS walker fail-fast** (`weather_collector/fetchers/salem_water.py`). Per-request timeout dropped 30s → 8s and added a 30s wall-clock budget to `_fetch_gomofs_temp`. Root cause of the alert flood: NOAA `opendap.co-ops.nos.noaa.gov` has been down since 08-12 ~09:17 UTC, and the walker was iterating ~40 candidates × 30s = up to 20 min of blocking retries per tick, blowing through the fetcher timeout and killing the whole collector run every ~10 min. Fix causes the walker to bail after ~30s wall clock so the buoy 44013 fallback (already working — was returning 68.9°F but too late) runs and the tick completes cleanly.
- **`as_completed` outer-timeout handler** (`weather_collector/fetchers/fetch_parallel.py`). Wrapped the `for future in as_completed(..., timeout=AS_COMPLETED_TIMEOUT)` loop in `try/except TimeoutError`. Previously the per-future `TimeoutError` from `future.result(timeout=TASK_TIMEOUT)` was caught (line 72) but the outer `as_completed` timeout was not — when it fired (because a thread was stuck longer than 60s in a blocked HTTP call Python can't kill), the exception bubbled up uncaught and crashed the collector. Now any unfinished futures at the outer cap get marked as `as_completed_timeout` errors and the run continues.

</details>

<details>
<summary><strong>v0.6.402 • August 13, 2026 (pr L2 gate ordering fix — gate has never fired)</strong></summary>

- **Collector ordering fix** (`weather_collector/collector.py`). Moved `stamp_state` call to BEFORE `add_corrected_hourly_arrays`. The pr L2 regime gate shipped in v0.6.401 (08-10) reads `derived.state.regime_synoptic` to decide fires, but `stamp_state` (the writer for that field) ran ~115 lines later in the same tick. Result: `regime = None` every tick, guard `if regime is not None` short-circuited, **zero pr L2 cells have fired since ship**. Diagnosis via pair-log audit: 2,688 pr rows post-08-10 with 0 stamped `applied_layer=l2` (813× l1, 1,875× l3, all `l3` cases have `_post_l3 == raw` which only happens when live-apply skipped). `state_stamp` deps (current, pressure_trend_hpa_3h, hourly.wind_direction/speed/pressure/temp/time) all populated by line 226, safe to move up.
- **Debug page pr row updated** (`corrections_debug.html`). pr L2 status now notes "gate ordering bug fixed 08-13 v0.6.402" and reports the backstamp early read: gated-vs-raw −5.19% on 2,688 rows post-08-10 (nw_flow/0-5h Δ −43.6% n=223, nw_flow/6-11h Δ −21.9% n=221), matching Stage 1 A/B halves.
- **wdp watch closed clean** (`corrections_debug.html`). Removed stale "day X/14 closes 08-10 · 2d OVERDUE" text from the wd field-table row + What's-running list + Layers section. Watch was formally closed 08-11 in v0.6.401f (Δ −2.7% n=16,416) — the sweep just missed the wd row. Applied_layer stamp gap fix language reframed: mae_over_time's L1_ONLY_FIELDS workaround bypasses the stamp, so the debug-page metric was correct throughout; real impact was only in Fitter's `decay_corrections.json` fallback.

</details>

<details>
<summary><strong>v0.6.401j • August 12, 2026 (debug page staleness sweep)</strong></summary>

- **Debug page staleness sweep** (`corrections_debug.html`). Systematically walked the page for numbers that had drifted vs today's state. Cleared: C1h narrow-promote counter "4/7 · 9 SHIP" and C1d "1/7 · 5 SHIP" — both obsolete since these axes are in KNOWN_LIVE_PIPELINES (auto-suppressed in digest); replaced with "already live-stamping; user-visible band gate is C1 Stage 4" language. C1 Stage 4 audit rate 32.43% → 36.36% (today's read). Narrow-promote today counter updated: pre-frontal 6/7 (was 4/7). clp streak walker "day 1/7 · fire set n=7" → "day 3/7 · fire set n=4" in 4 places. Lc recent-bias gate bullet updated for the 08-12 per-field fix: ch streak 4/7, cm 2/7, ch clears earliest 08-15. Backlog C1h bullet updated to "already live-stamping". Recent Activity 08-12 entry extended with afternoon's work (standing plan sweep + wg L3 reinvestigation + wg L2 Stage 0 + this sweep).

</details>

<details>
<summary><strong>v0.6.401i • August 12, 2026 (item 1 KILL guard + item 3 gate fix + wg L3 reinvestigation)</strong></summary>

- **`h_h_dp_tau_refit` KILL supersession guard** (`analysis/h_h_dp_tau_refit.py`). Summary verdict downgraded to `KILL (supersession guard)` when per-field STAGE 0 PROMOTE would fire. h uses `_soft_ramp_factors(lead)` piecewise-linear (not exp(-lead/τ)); dp is Magnus-derived — adopting a τ-decay would revert the v0.6.390g CLOSED-CLEAN shape retune. Docstring rewritten to lead with supersession context. Per-field PROMOTE lines retained for sentry pattern.
- **`h_lc_recent_bias_gate` per-field clearance** (`analysis/h_lc_recent_bias_gate.py`). Set-level `stable` check was flagging new-field promotions as instability, resetting ch's day-4/7 streak when cm cleared halves for the first time today. Added per-field N-day streak tracking alongside the set-level check. ch clears earliest **2026-08-15** (streak 4/7 today), cm earliest 2026-08-17 (streak 2/7). Matches the standing plan's stated intent ("gate clears earliest 08-16 if ch stays promoted with no HOLD days"). Standing plan item 3 unblocked.
- **wg L3 SKIP_TABLE reinvestigated** (`corrections_debug.html`, new `project_wg_l2_windblend_cell_concern`). Earlier "4/7 cells regressing" flag was a measurement mix. Today's `h_wg_l3_regression_stage1` halves-verified numbers CONFIRM all 6 measurable SKIP cells (L3 vs L2 hurts by 5.9-28.4% on both halves). The 4 cells where top-of-stack was worse than raw L1 (calm 12-23/24-47, sea_breeze 6-11/24-47) are pointing at **wg L2 (wind_blend)** not the SKIP — since L3 is skipped, top-of-stack = L2. Removing the SKIP would compound damage. SKIP_TABLE watch closed CLEAN; opened new investigation for wg L2 wind_blend cell concern (deferred, not same-session).
- **Debug page changed-verdicts annotation** (`analysis/runlog/build_executive_summary.py`). Each Changed-verdicts line now shows `[prior_bucket→new_bucket]` — the mechanism at line 950 already gates on bucket transitions, so any `[X→X]` reads as a suppression bug.

</details>

<details>
<summary><strong>v0.6.401h • August 12, 2026 (debug page sweep — 401g stamper + flip-sweep closures)</strong></summary>

- **Debug page sweep** (`corrections_debug.html`). C1 layer bullet updated with 08-12 live-stamper ship (`weather_data["cross_run_spread"]` per-tick for 7 promoted fields; corrects yesterday's "requires a new forecast_history_log.json" note — `forecast_snapshot.py` was already accumulating the raw data). R&D frontal-t bias bullet replaced "wait 2-3 weekly reads" language with the new 7-day rolling gate wired into `h_frontal_t_bias_stage0.py` (day 1/7 seeded, ship_bands=[0-5h, 6-11h, 12-23h], earliest STAGE 1 CLEAR 2026-08-19). Post-ship watch for pr L2 v0.6.401 amended with 08-12 re-verify: retro flipped STAGE 1 SHIP → MIXED on non-shipped candidate cells while shipped nw_flow cells stayed both-halves-WIN with gain grown; script hardened with `SHIPPED_CELLS` awareness. Recent Activity: added 08-12 entry; shifted 08-11 to "yesterday" and 08-10 to "2 days ago"; trimmed 08-09 to CHANGELOG per rolling 3-day rule.

</details>

<details>
<summary><strong>v0.6.401g • August 12, 2026 (cross_run_spread live stamper)</strong></summary>

- **Live cross-run spread stamper** (`weather_collector/processors/cross_run_spread.py`, wired in `collector.py` before `stamp_confidence`). Reads `forecast_log.json` snapshots + this tick's live L1 values, groups by (field, valid_time), computes max−min across the last 12h of runs, buckets into Q1..Q5 using `xr_edges_by_field` from `c1_confidence_curated_v2.json`. Stamps `weather_data["cross_run_spread"] = {field: {vt: {spread, xr_q, n}}}`. Consumer-less today — `confidence_layer.py` untouched — running silently so we get a day of live logs to validate distribution/coverage before wiring the `by_xr_q` marginal multiplier. Corrects yesterday's v0.6.401f note: no new writer needed — `forecast_snapshot.py` was already accumulating the per-run L1 history that this reader consumes. See `project_cross_run_spread_c1_axis`.

</details>

<details>
<summary><strong>v0.6.401f • August 11, 2026 (debug page full sweep + 4-watch close/extend + Stage 3 c1 xr_q wire-up)</strong></summary>

- **Cross-run spread → C1 Stage 3 wired** (`analysis/c1_confidence_calibration_v2.py` + `c1_curate_confidence_table_v2.py`). New `by_xr_q` single-axis sub-table alongside existing `by_axes`. Per-field cross-run spread computed in a pre-pass (max−min of forecast across runs for each (field, valid_time), only vts with ≥3 runs contributing). TRAIN-fit quintile edges per field. 252 xr_q cells wired at n≥40; curator emits SHIP/MARGINAL/SKIP with the same classifier as `by_axes` — **214 SHIP (103 WIDEN / 111 NARROW), 18 MARGINAL, 20 SKIP** of 252. Non-breaking: `confidence_layer.py`'s 5-tuple lookup path is untouched. Stage 4 (live consumer) needs a new `forecast_history_log.json` so the collector can compute per-tick spread; long-lead-only wiring first to sidestep training-vs-live spread drift at short leads. See `project_cross_run_spread_c1_axis`.
- **Three hypothesis Stage 0/1 scripts + one Stage 2** (`analysis/`). `h_cross_run_spread_c1_stage2.py` PROMOTE 7/7 fields vs cluster_spread_q (Q5/Q1 |err| ratios 1.38–15.68); `h_depression_cloud_confidence_c1_stage2.py` NARROW PROMOTE — cl clean, ch confounded by cross-run spread; `h_windspeed_t_confidence_c1_stage1.py` REDUNDANT (2.11× in stable but 1.16× in transition — transition axis already captures it); `h_frontal_t_bias_stage0.py` HIT 3/4 bands (0-5h +1.94, 6-11h +2.74, 12-23h +1.06 SIGN_HOLDS; 24-47h SIGN_FLIPS); `h_sr_obs_recent_override_stage0.py` NO HIT pooled 4.58% but real fired-subset +23.5% on 77 non-Lsb fires.
- **Full debug-page sweep + 4-watch close/extend** (`corrections_debug.html`). Verified all four watches with post-ship pair-log checks. **wdp CLOSED CLEAN** (Δ −2.7% aggregate n=16,416, 07-31 outlier cells did not recur). **wind_blend BLEND_HOURS 24→4 ws-side CLOSED CLEAN** (post-fix 0-5h L2 −23.3%, 6-11h +4.2%, 12-23h +0.9%, 24-47h 0%; sibling wd-side closed as v0.6.401e). **wg L3 SKIP_TABLE WATCH EXTENDED** with regression flag — 4/7 SHIP cells hurting post-ship 14d (calm 12-23h +23%, calm 24-47h +12%, sea_breeze 6-11h +14%, sea_breeze 24-47h +8%; only calm 0-5h clearly winning at −43%; needs investigation). **ws L3 SKIP_TABLE** confirmed already in Archive as INERT (v0.6.397). Also: L3 stack description updated (ws no longer in L3_FIELDS); C1 layer bullet updated with by_xr_q Stage 3 note; calendar entries reflowed (past dates removed, HELD items surfaced); Recent Activity today entry added, 08-08 and 08-07 trimmed to CHANGELOG per rolling 3-day window.
- **Hypothesis backlog hygiene** (`memory/project_hypothesis_backlog.md`). Marked #6 as SHIPPED (was already dpbp v0.6.391) and #4 as SHIPPED (was already cluster_spread axis_2 live in c1_v2). Replaced 7-week-old "Closed today (2026-06-24)" block with compact recent-shipments line. Marine-layer entry rewritten to reflect dormant sentry-only state. Added #8 (sr obs-recent override), progressed #7 (frontal-t Stage 0 hit + watch), and HELD #2 (pre_front C1e — 16 ortho cells June → 2 SHIP today, n=3 passages).

</details>

<details>
<summary><strong>v0.6.401e • August 11, 2026 (close wd L2 blend watch CLEAN)</strong></summary>

- **wd L2 blend post-ship watch CLOSED CLEAN** (`corrections_debug.html`, `memory/project_wd_l2_blend.md`, `memory/MEMORY.md`). Watch (reset to 08-11 after v0.6.384 BLEND_HOURS 24→4 shrink) delivered design intent. `h_wd_l2_fire_rate.py` post-fix (obs_time ≥ 2026-07-28): 0-5h L2 35.44° vs L1 46.16° (−23% MAE, 65% fire, fired-subset −36%); 6-11h +0.3% (6% fire); 12-23h −0.3% (8% fire); 24-47h never fires (band ≥ BLEND_HOURS). Predicted MIXED → ADDS VALUE flip landed on schedule as pre-fix fossil damage aged out. OPEN_WATCHES entry removed; bullet relocated from active list to Archive → Post-ship watches with numbers.

</details>

<details>
<summary><strong>v0.6.401d • August 10, 2026 (debug page: staleness audit + watch countdowns + archive relocation)</strong></summary>

- **Staleness audit block** (`corrections_debug.html`). New red-bordered block above the "Right now" table lists any open watch whose expected close date has passed. Data source: hand-curated `OPEN_WATCHES` array in inline JS with `{name, closeDate, note}`. Hidden when nothing is overdue (today's state). Same anti-fossilization idea as the digest 🚨 TOP ALERTS block but for temporal drift instead of new sentry firings. Would have caught the 9 stale watches cleaned out of MEMORY.md this session.
- **Post-ship watch countdown enhancements** (`renderWatchDayCounters`). Existing `day X/N` counter now distinguishes three states: `day X/N · Nd left` (normal, gray), `day N/N · CLOSES TODAY` (amber, bold), `day X/N · Xd OVERDUE — resolve` (red, bold). Prior behavior stamped green "closed" once the window elapsed, misleadingly implying clean when the watch was just overdue and unresolved. Today's page: wdp shows amber CLOSES TODAY (07-27 + 14d = 08-10); Lc regime-conditional Stage 1 gate shows red 3d OVERDUE (07-31 + 7d = 08-07).
- **Archived post-ship watches moved into `#sec-archive`.** The inline "Post-ship watches — archived" collapsible under "What's improving" had been living next to its active sibling for weeks. Relocated into the existing Archive section as a `#sec-archive-post-ship` block right after the Archive intro, before "Recently ruled out." Left an in-place pointer link under the active watches for wayfinding. Follows the same convention as R&D → Archive: settled/closed items live in one place, not scattered inline next to live surfaces.

</details>

<details open>
<summary><strong>v0.6.401c • August 10, 2026 (state_fc_by_lead promoted to derived)</strong></summary>

- **Per-lead forecast regime canonicalized** (`weather_collector/processors/state_stamp.py`). New `derived.state_fc_by_lead` — array of `regime_synoptic` per hourly lead index, computed once per tick alongside the current-tick `derived.state.regime_synoptic`. Uses the same `classify_synoptic_regime` inputs as `forecast_error_log.py`'s state_fc construction (forecast wind_dir/speed/pressure/temp per lead + tick pressure_trend + local hour). `stamp_state` now logs `transitions=N` count. Publishes to GCS; visible to any consumer.
- **wd_persistence_gate refactor** (`weather_collector/processors/wd_persistence_gate.py`). Reads `derived.state_fc_by_lead` instead of computing per-lead regimes inline. Deletes `_fc_regime_for_lead` (~30 lines) and drops now-unused `classify_synoptic_regime` import. Behavior unchanged; smoke-tested against live GCS (state_curr=pre_frontal, 3 transitions detected at leads {9,39,42}, fires_by_band unchanged). Removes `per_lead_fc_regime` from telemetry (was writer-only; canonical read is now `derived.state_fc_by_lead`); adds `state_fc_source: "derived.state_fc_by_lead"` for provenance. Sets up any future consumer (UI regime-transition widening, other specialists) to read one canonical location instead of reaching into a specialist's telemetry blob.

</details>

<details>
<summary><strong>v0.6.401b • August 10, 2026 (whitelist streak walker generalized)</strong></summary>

- **Generalized whitelist streak walker** (`analysis/whitelist_streak.py`). Replaces the clp one-off from v0.6.401a with a registry-driven driver covering 5 cell-based gates: chp + wdp (LIVE) and clp + wg_residual + dp_residual (SHADOW). Each gate's effective fire set (SHIP + MARGIN, minus per-gate excluded regimes like frontal for chp/clp/wdp) archives to `analysis/output/{gate}_streak.json` idempotent by UTC date. Prints one PASS/FAIL/BUILDING line per gate. Same JACCARD_FLOOR=0.80 / STREAK_REQUIRED=7 as clp. Day 1/7 seeded for all gates. Closes the "no history to walk on flip day" gap for every in-flight persistence gate. Bias-persistence pair (dp_bias, ws_bias) uses a different curated shape and is not yet registered. Retired: `analysis/clp_whitelist_streak.py`.

</details>

<details>
<summary><strong>v0.6.401a • August 10, 2026 (clp whitelist streak walker)</strong></summary>

- **clp flip-gate infra** (`analysis/clp_whitelist_streak.py`, now retired in 401b). Prior 08-03 flip window was invalidated by curated JSON churn history not being persisted anywhere.

</details>

<details>
<summary><strong>v0.6.401 • August 10, 2026 (chp diurnal gate + pr L2 regime-gated SHIP)</strong></summary>

Two same-day live-layer changes from `project_ch_chp_midlead_band_watch_08_10` and `project_pr_l2_regime_flip_investigation_08_10` investigations.

- **chp diurnal gate** (`weather_collector/processors/ch_persistence_gate.py`). Added `_DIURNAL_SKIP_REGIMES = {nw_flow, pre_frontal}` and `_DIURNAL_SKIP_HOURS = [10, 18)` local. chp fire logic now checks `hourly.times[i]` per lead and suppresses on daytime valid hours in those regimes. 08-10 48h band-cut traced the 12-23h + 24-47h scoreboard regression to +20.51 chp_bias at 12-23h nw_flow daytime (n=78) and +4.25 at 24-47h pre_frontal daytime (n=91); nighttime cells in the same regimes remain strong wins (-6 to -26% vs raw). Physical: post-frontal cold-advection nights leave residual clouds that burn off by midday, and chp persists them into the daytime valid time. Diurnal skip count exposed as `ch_persistence_gate.diurnal_skips_by_band` for monitoring.
- **pr L2 SHIP with regime gate** (`weather_collector/processors/corrected_hourly.py`). Flipped pr from L2-disabled-everywhere to L2-applied-on-WIN-cells. `_PR_L2_FIRE_CELLS = {(nw_flow, 0-5), (nw_flow, 6-11)}` — the both-halves winners from `analysis/pr_l2_regime_lead_retro.py` 08-10 (Jaccard=0.50 STAGE 1 SHIP CANDIDATE, nw_flow/0-5h A +21.8%/B +41.6%, nw_flow/6-11h A +10.3%/B +13.1%). Shadow-write of `corrected_pressure_in_post_l2` remains unconditional so the retro can keep evaluating skip cells for future promotion. Regime source: current-tick state (proxy for short-lead fc regime, matches chp/wdp pattern). Retro's other pooled WINs (nw_flow/12-23h, pre_frontal/{0-5,6-11}, sw_flow/{0-5,6-11}) held pending 7-day gate agreement per feedback_whitelist_promotion_gate.
- **Scoreboard** (`corrections_debug.html:2916`). Dropped `pr` from `MAE_UNCORRECTED_FIELDS` — pr's overall MAE is no longer structural-zero vs raw once L2 applies on nw_flow WIN cells. Touched median now n=9 (was n=8).

</details>

<details>
<summary><strong>v0.6.400c • August 9, 2026</strong> (Overall MAE mean tile dp exclusion + debug-page Rule 5 sweep post-audit)</summary>

- `corrections_debug.html:3370` — `DERIVED = {cc, pp}` was missing `dp`, causing the "Overall MAE mean · 24-hour" tile to double-count dp (Magnus-derived from t+h). Comment on line 3382 already documented "cc/pp/dp aren't independent MAE-scorable fields" — code just didn't match. Fixed to `{cc, pp, dp}` matching `SCOREBOARD_EXCLUDE`. Modest but real: dp's small delta was slightly dragging the tile toward zero.
- **Debug-page Rule 5 sweep** after 08-09 audit + v0.6.400 ships. Updated:
  - wd row (line 909): replaced hand-typed "Day 8/14" counter with auto-populate `<span class="watch-day">`; added v0.6.400 collector fix note.
  - Persistence skill paragraph (line 1206): removed stale "Gate EXTENDED to 08-03 / Day 2/7"; added 08-09 clp Stage 2 rerun result (6 SHIP / 22 SKIP whitelist ready for flip); marked ch persistence gate watch CLOSED CLEAN 08-02; noted 08-09 mixture-check verdicts for cl/cm/t transition cells.
  - SPECIALIST_STACK JS comment (line 4035): removed stale "EXTENDED to 08-03" — updated to reflect Stage 2 flip-ready state.
  - Today's recent-activity entry: added AUDIT + PIPELINE frame with 7-chunk summary + v0.6.400 / 400b / 400c ships.
- Also v0.6.400b (analysis-only, not deployed): `analysis/mae_over_time.py` — added `if applied and fld not in L1_ONLY_FIELDS` guard so v0.6.400's applied_layer stamp for wd doesn't double-count with the L1_ONLY branch below.

</details>

<details>
<summary><strong>v0.6.400 • August 9, 2026 (wd applied_layer stamp fix — collector)</strong></summary>

- `weather_collector/processors/forecast_error_log.py` — the wd branch takes an early `continue` and had been skipping the applied_layer stamp block since v0.6.269, so every wd pair-log row was missing `applied_layer`. Consequence: wdp's firing cells (~3.5% of wd rows in the sample window, 762/21494) were invisible to `per_layer_mae_by_lead["wd"].production` and to the 07-27 wdp flip-gate metric. Direction of hidden bias unknown until fresh clean-data window accrues.
- Fix stamps applied_layer inside the wd branch before the early `continue`, matching the pattern the non-wd branch has always used.
- Found during silent-lie sweep (chunk 1 of 08-09 code+logic audit). Historic pair-log rows stay missing the field; clean data starts on next Cloud Function tick.

</details>

<details>
<summary><strong>v0.6.399a • August 9, 2026 (scoreboard MAE_UNCORRECTED_FIELDS adds cl)</strong></summary>

- `corrections_debug.html` — added `cl` to `MAE_UNCORRECTED_FIELDS` in the scorecard header. cl's only MAE correction is the L2 hourly[0] blend at lead 0, and the scoreboard averages leads 1-47 (deliberate). Counting cl in the touched median produced a structural +0.0% that dragged the median toward zero even when the correction stack was doing its job. Before: touched median = -1.6% (n=9). After: touched median = ~-3% (n=8).
- The main "MAE median · 7-day" line (scoredRows, uses only derived exclusion) still counts cl + pa + pr and thus still reads -0.8% today. That's the wider "myweather vs raw across everything" story; touched is the "correction stack effectiveness" story. Split intentional.

</details>

<details>
<summary><strong>v0.6.399 • August 9, 2026 (Lc recent-bias gate — 7-day rolling gate tracker)</strong></summary>

- Pipeline-to-good plan item #3 progress. `h_lc_recent_bias_gate.py` now appends each run's Stage 1 verdict to `.cache_lc_recent_bias_gate_history.json` and prints a rolling 7-day gate summary (mirrors the `_append_gate_history` shape used by `h_lc_regime_stage1` and `l6_fix_b_refit`).
- Gate mechanics: promoted-field set must stay stable for 7 distinct days with no HOLD days and ≥1 promoted field. Gate-clear enables Stage 3 wire.
- Also dropped cc from the gate's CLOUD_FIELDS — cc is derived from cl/cm/ch via Ccd and never carries its own Lc shift ([[project_cc_derived_field]]). Prior versions of the script were meaninglessly evaluating cc.
- Today's day 1/7: ch = STAGE 1 PROMOTE, cl = HOLD-safe, cm = insufficient data. Verdict line now includes the rolling-gate day counter so the digest surfaces progress without hand-tracking.
- No production code touched. Stage 3 (adding the gate to actual Lc application) waits for gate-clear.

</details>

<details>
<summary><strong>v0.6.398 • August 9, 2026 (fossil-window bug class CLOSED via rolling helper)</strong></summary>

- New `analysis/_windows.py` with `rolling_windows(recent_days=15, prior_days=15)` returning a `Windows` NamedTuple of A/B/FULL date-string bounds anchored at midnight-today.
- 14 fossil-prone analysis scripts migrated to the helper: `h_ch_persistence_blend{,_stage2,_stage2_vs_l6}`, `h_cl_persistence_blend{,_stage2}`, `h_dp_residual_persistence_stage2`, `h_full_regime_sweep`, `h_l3_asymmetric_stage1`, `h_t_l2_regression_stage1`, `h_wd_persistence_gate_stage{1,2}`, `h_wg_l3_regression_stage1`, `h_wg_residual_persistence_stage2`, `h_ws_l3_regression_stage1`. Hardcoded `WIN_A_LO/HI` / `WIN_B_LO/HI` / `WIN_FULL_LO/HI` string literals removed everywhere; windows now roll automatically. `h_ch_persistence_blend_stage2_vs_l6` keeps its 5d/5d shape.
- The `stale_window_audit` in `build_executive_summary.py` was already correct — needed no change. Once literals were gone from `WIN_*` assignments, tomorrow's digest reports "no fossil-window suspects."
- Root cause: manual slide ritual repeated 07-19, 07-22, 07-28, 08-01, 08-06, 08-08. Each slide was mechanical; the code should have done it.

</details>

<details>
<summary><strong>v0.6.397a • August 8, 2026 (debug page Rule 5 sweep after morning's ships)</strong></summary>

- `corrections_debug.html` sweep after v0.6.396 + v0.6.397 collector ships. Updates: (1) L3_FIELDS list drops `ws`; L4 skip cells for cc listed; C1h SHIP set refreshed to today's cells (t/24-47h in, t/12-23h out). (2) ws L3 asymmetric-skip block marked INERT (ws no longer in L3). (3) ws routing row: L3 lead-decay removed. (4) Post-ship watches restructured into "active" + collapsed "archived" sections — keeps the memory, tightens visible surface. (5) Backward-looking calendar entries (today/yesterday/etc.) removed from the dashboard column; Engineering log / Recent activity now owns chronology. (6) Recent activity slid to 08-06 → 08-08 rolling 3-day window; 08-05 trimmed to CHANGELOG.
- Version bump letter (`a`) per convention: follow-on debug-page tweak after two substantive collector ships earlier today.

</details>

<details>
<summary><strong>v0.6.397 • August 8, 2026 (walkforward L3/L4: drop ws from L3, add 6 skip cells)</strong></summary>

- `walkforward_l3l4_validator` cleared 7-day gate. Two changes to `decay_apply.py`:
  - **Drop ws from L3_FIELDS.** Pooled ws L3 impact is +0.1% fc / +0.6% obs (noise) after the existing ne_flow + sea_breeze skips. The strip candidacy queued 2026-07-04 finally passes. `("ws", "l3")` SKIP_TABLE entries left in place but now inert.
  - **Add 6 SKIP cells.** wg L3 sea_breeze 12-23h (-8.9%). cc L4 nw_flow 0-5 (-43.3%), nw_flow 12-23 (-8.0%), pre_frontal 0-5 (-20.1%), pre_frontal 6-11 (-19.7%), pre_frontal 12-23 (-12.1%). cc L4 only helps at longer leads in these regimes; short/mid leads regress and are now skipped.
- No new fields entered L3/L4. L4_FIELDS unchanged (ch, cc).

</details>

<details>
<summary><strong>v0.6.396 • August 8, 2026 (C1h narrow-promote: 9 SHIP cells cleared 7-day gate)</strong></summary>

- C1h (trend-direction confidence axis) narrow-promote gate cleared 10/7 days. `c1h_curated.json` refreshed with 9 SHIP cells — all WIDEN. Cloud fields at 12-47h see 80–239% premium when the hourly forecast trends vs stays flat; t/24-47h widens +11%. Point forecasts unchanged; only the ± confidence band moves.
- SHIP cells: t/24-47h, cc/12-23h, cc/24-47h, cl/12-23h, cl/24-47h, cm/12-23h, cm/24-47h, ch/12-23h, ch/24-47h.
- Axis machinery live since v0.6.316; this is a curated-table refresh, no code change.

</details>

<details>
<summary><strong>v0.6.395j • August 7, 2026 (degraded-mode: show WU-station Production value, not em-dash)</strong></summary>

- Bug fix in the current-tick correction table: when the pipeline is in fallback mode (HRRR/GFS unavailable), the Production column for t/h was rendering `—` even though the value exists (sourced from WU stations via `hyperlocal.corrected_temp`). The front-end has always shown this value in the main app; the debug table was misrepresenting the data as missing.
- Now shows the real value with a `(stations only)` suffix + tooltip: "Sourced directly from WU stations — no HRRR/GFS bias correction applied this tick." Raw Model column still correctly reads `unavailable`, Correction column still `—` (can't compute correction without a raw baseline).
- Discovered while investigating a HRRR/GFS outage this evening — user asked "where does the temperature the front-end is showing come from, and why isn't it in the debug table?" Answer: same source (`hourly.temperature[0]`), and the debug table had a rendering bug that hid it.

</details>

<details>
<summary><strong>v0.6.395i • August 7, 2026 ("paused" → "unavailable" on the t/h fallback row)</strong></summary>

- Current-tick correction table now shows `unavailable` (with tooltip: "Raw model (HRRR/GFS) did not respond this tick; L2 station-bias correction can't compute without it.") instead of `paused` for t and h when the pipeline is in fallback mode. "Paused" implied intent — the actual state is upstream failure, so the word was misleading.

</details>

<details>
<summary><strong>v0.6.395h • August 7, 2026 (header timestamps unified: MM-DD HH:MM ET, 24h)</strong></summary>

- Header freshness stamps (fitted, decay applied, MAE data refreshed) all render as `MM-DD HH:MM ET` via new `fmtET()` helper. No more mixed ISO-with-Z, ISO-without-Z, and ambiguous local strings — one shape everywhere.
- 24-hour clock, no am/pm. Zone always ET regardless of viewer's timezone (values come from GCS on cross-timezone reads).

</details>

<details>
<summary><strong>v0.6.395g • August 7, 2026 (topline freshness stamp; dropped page tagline)</strong></summary>

- Header topline gets a `MAE data refreshed <timestamp>` line, populated from `mae_over_time.json`'s `generated_at`. Ticks forward hourly with the publisher Cloud Function. Answers "how fresh is what I'm looking at?" without scrolling to the per-field snapshot audit label.
- Dropped the `Layer-by-layer anatomy…` page tagline to make room. Header now: title → correction-machinery meta (fitted / decay / corrections / weather) → data-freshness meta (MAE refresh time).

</details>

<details>
<summary><strong>v0.6.395f • August 7, 2026 (publisher Cloud Function live; debug page narrative updated)</strong></summary>

- New `myweather-publisher` Cloud Function deployed to us-east1, hourly Cloud Scheduler cron (`0 * * * *`). Runs the 6 dashboard-data publishers (`mae_over_time`, `gate_firing_rollup`, `h_persistence_skill`, `h_pp_platt_calibration`, `h_pp_bin_calibration`, `pp_brier_reliability`) and pushes fresh JSON to `gs://myweather-data/` on every hour. Removes the daily-manual-digest dependency for the debug page's 24h/7d MAE cells and the accuracy-over-time chart. Digest stays as-is for experiments; this only takes over the production publisher role.
- Per-field snapshot topline updated: both 7-day and 24-hour cells now read from `mae_over_time.json` (unified since v0.6.391). Header narrative corrected to describe the new hourly refresh cadence.
- Accuracy-over-time chart meta-line: "refreshed by daily digest" → "refreshed hourly by publisher Cloud Function."
- First live cloud run 22:31 UTC 2026-08-07, all 6 publishers OK, total 3m 42s runtime, 2GB memory (was 1GB, OOM'd on pair-log aggregation). Free-tier cost ~16% of compute budget at hourly cadence.

</details>

<details>
<summary><strong>v0.6.395e • August 7, 2026 (debug-page sweep — h L2 watch closed clean; sr Lsb Day 1 red-flag)</strong></summary>

- **h L2 shape re-tune 7-day watch closed CLEAN.** Shipped v0.6.390g 07-31 (H_SOFT_RAMP_FLOOR 0.4→0.1, H_SOFT_RAMP_END 24→10). Close read: layer-shape sentry green at all bands, h pair-log ΔMAE −28.3%. Post-ship watches entry recolored green, watch-day counter retired.
- **sr Lsb Day 1 red-flag surfaced** (v0.6.394, flipped 08-05). 08-06 per-day `prod_real` MAE 86.14 vs raw MAE 66.73 (−29%). L5-applied daylight hours 09–14 carry prod_bias +160 to +320 W/m². Matches [[project_sr_lsb_flip_gate]] hour-13 primary watch point + halves-B recency-weak secondary. No code change today — holding for one more tick. Recent Activity + calendar note the trigger; next-step is per-hour SHIP filter (drop hours 13/15/16) in `sr_sea_breeze_lsr_refit_stage2.py`, two more days regressing → revert `ENABLED=True`.
- **Recent activity + calendar rolled forward.** 08-04 entry trimmed to CHANGELOG. wsbp status updated ("as of 08-07"). Stale chp watch-close narrative ("closes today (08-02)") corrected to past-tense.

</details>

<details>
<summary><strong>v0.6.395d • August 6, 2026 (revert v0.6.395c native-units suffix)</strong></summary>

- Reverted the `(1.9°F)` / `(2.5mph)` / etc. suffix added by v0.6.395c to per-field snapshot cells. Mixed units confused the reader — the % delta answers "how much better than raw?" but the native-unit absolute doesn't cleanly answer "how good is the forecast?" in a comparable unit. Real design for surfacing forecast-quality-in-comparable-units still open — likely a skill score vs climatology (unitless %), TBD.
- pp cell (v0.6.395b) unchanged — that one is pp-specific and honest (Brier value has no meaningful % delta since Prod == L1 exactly for pp).

</details>

<details>
<summary><strong>v0.6.395c • August 6, 2026 (per-field snapshot cells show absolute Prod value alongside % delta) — REVERTED in v0.6.395d</strong></summary>

- Delta-vs-raw alone doesn't tell users if a −15% correction moved `t` 2.0°F→1.7°F (perceptible) or `ws` 6.2→5.9 mph (invisible). Cross-field rank order by user-visible improvement often differs from rank by %.
- Cells now render `−15.2% (1.7°F)` — % delta plus absolute Prod value in native units (parenthetical). Same UI pattern as v0.6.395b pp Brier cell. Applied to both 7-day (`pf-mae`) and 24-hour (`pf-today`) columns.
- Units: t/dp = °F; ws/wg = mph; h/cc/cl/cm/ch = % (0 decimals); wd = ° (0 decimals); sr = W/m² (0 decimals); pr = inHg (3 decimals); pa = in (3 decimals). pp keeps raw Brier value from v0.6.395b.
- Motivation from discussion: "make a forecast better than Raw" is the stated objective — measured well by % delta. But *how much better in real units* has been invisible on the debug page. This surfaces that dimension without changing the ranking, which stays keyed to % delta (the goal metric).

</details>

<details>
<summary><strong>v0.6.395b • August 6, 2026 (pp cell shows raw Brier, not meaningless MAE % delta)</strong></summary>

- Per-field snapshot cells for pp (both 7-day and 24h columns) previously showed "0.0% (Brier)" — a delta vs raw that's always exactly 0 because nothing in the live stack touches pp's forecast value (verified: `raw.brier == prod_real.brier == 660.48` in mae_over_time.json). Reads as "correction stack is neutral" when the accurate read is "MAE-delta is the wrong metric here — check the score itself."
- Fix: when `data-brier="1"` on a cell, render the raw Brier value directly (e.g. `660.48 Brier (L1 only)`). If a corrected layer ever diverges from raw, suffix auto-flips to `(Δ−X.XX)`. Baseline anchor now, meaningful delta later when pp Platt frontal×6-11h Stage 3 wires. Zero maintenance on flip.
- Same infra could extend to pa cell (`data-brier` not set today; pa has no L2+, no shipped correction, no queued Stage 3 candidate). Not applied here to keep the change scoped to pp; pa stays on MAE-delta 0.0% until a correction candidate surfaces.

</details>

<details>
<summary><strong>v0.6.395a • August 6, 2026 (debug page Rule 5 sweep for v0.6.395)</strong></summary>

- Recent activity: added 08-06 entry (v0.6.395 c1 re-curate + fossil-window slides + wsbp status + h L2 closing clean); rolled 08-05 → yesterday, 08-04 → 2 days ago; trimmed 08-02/08-03 to CHANGELOG per 3-day rolling window.
- Calendar: added Thu 08-06 · today (v0.6.395); Wed 08-05 → yesterday; Tue 08-04 → 2 days ago; Fri 08-07 · tomorrow updated to reflect layer-shape sentry now clean.
- Blocked/ongoing: wsbp entry updated — calm regime n=25 in 48h state (up from 0 on 08-04), 24h antecedent n=12 (need ≥20).

</details>

<details>
<summary><strong>v0.6.395 • August 6, 2026 (c1 confidence re-curate + fossil-window slides)</strong></summary>

- **c1 re-curate** (`c1_confidence_curated.json` + `c1_confidence_curated_v2.json`): `c1_calibration_audit` flipped PASS → HOLD (pass rate 52.6% < 75% threshold). wd 12-23h + 24-47h flagged DRIFTED. Re-ran `c1_confidence_calibration.py` (+ v2) + `c1_curate_confidence_table.py` (+ v2) per the audit's own next-step guidance. Result: pass rate 52.6% → 66.7%. wd cells CALIBRATED after re-cut; cl 12-23h + cm 12-23h remain DRIFTED but that's the cloud-difficulty week per `raw_difficulty_index` (5 cloud fields harder than 90d baseline) — not something more re-cutting will fix. Legacy cell count: 15 SHIP / 4 MARGINAL / 37 SKIP → 14 SHIP / 6 MARGINAL / 36 SKIP.
- **Fossil-window slides (+4d)**: three analysis scripts flagged by digest sentry as `max window date 2026-08-02 (4d behind today)` — WIN_ constants advanced +4d. `h_ws_l3_regression_stage1.py` (A 07-18→08-02 → 07-22→08-06), `h_wg_l3_regression_stage1.py` (same shape), `h_ch_persistence_blend_stage2_vs_l6.py` (A 07-27→08-02 → 07-31→08-06). All re-ran clean. Per `[[feedback_fossil_windows]]` — stale windows produce fossil verdicts.

</details>

<details>
<summary><strong>v0.6.394b • August 5, 2026 (applicability_map fix — dpbp/wsbp descriptors return correct schema shape)</strong></summary>

- **Bug found during 394a debug-sweep audit:** `dp_bias_persistence.describe_applicability()` and `ws_bias_persistence.describe_applicability()` returned the wrong shape — flat dict with `enabled`/`gate_summary`/`action` keys instead of the schema's `category` + `fields:[{fires_when, gated_by, current_state}]` wrapper. Result: applicability map on debug page rendered both rows with empty category and empty current_state despite dpbp being LIVE for 24h and wsbp being live-shadow. Silent-lie — the "at-a-glance" pipeline view claimed no info on two specialists.
- **Fix:** rewrote both `describe_applicability()` to match the `ch_persistence_gate` shape (which was the working template). ENABLED-True path emits "adding +X°F / subtracting min(prev_bias, cap)"; ENABLED-False path emits "telemetry-only (shadow write); would…". Focus regimes rendered from `_params()` — no hardcoded values, so future param changes propagate automatically.
- **Post-deploy verified:** live payload at 13:57 UTC shows `category=specialist` + populated `current_state` for both. dpbp reads "ENABLED True; adding +2.0°F"; wsbp reads "ENABLED False; telemetry-only, would subtract min(prev_bias, 3.0)."
- **Class of bug:** describe_applicability() has no schema-coverage test. Silent shape breakage is the class of failure this file exists to prevent — descriptor coverage in `tests/` is a follow-up worth adding (assert every module's return value has `layer_id`, `category`, `fields[]` with `current_state`).

</details>

<details>
<summary><strong>v0.6.394a • August 5, 2026 (debug page Rule 5 sweep — sr Lsb LIVE, C1h in stack + watches, calendar/Recent Activity roll, stale verdict-pending copy)</strong></summary>

- **sr row updated for Lsb flip** — replaces the "flip HELD, re-check 08-05" copy with LIVE stamp, Stage 2 numbers, post-deploy applied=True verification, watch points (hour 13, halves B).
- **"What's running" stack gains Lsb + dpbp + C1h** — three LIVE additions previously missing from the pipeline-at-a-glance list. chp watch-close flipped from "through 08-02" to "closed clean 08-02."
- **Calendar rewrite** — 08-05 becomes today (4 ships, cl-fossil no-action), 08-04 becomes yesterday, 08-03 becomes 2 days ago, removed stale future entries for 08-05 (past) and 08-06 (Lc Stage 1 gate — action no longer clear). Added dpbp 08-18 + Lsb 08-19 watch-close rows. Retired C1h from ongoing (just shipped). Corrected pre-frontal from "4/7 (2 SHIP)" to "2/7 (2 SHIP)" and n=7 passages / 7% join to today's 4 passages / 9% join.
- **Post-ship watches gain Lsb + C1h Stage 3 ship entries** — both auto-populate day X/14 via existing `watch-day` spans.
- **Recent Activity: added today (v0.6.393/393a/393b/394), shifted 08-04→yesterday, 08-03→2 days ago, retired 08-02 to changelog** per rolling 3-day window.
- **"verdict pending re-read" copy** on three long-closed gates (dp residual persistence, clp, chp full-shape refinement, cl row's clp descriptor) — all sat on the fossil windows that got slid this morning. Replaced with "awaiting post-fossil-slide re-cut (windows advanced 08-05 v0.6.393b — next digest is first trustworthy read)" so the reason for the delay is legible.
- **ws L3 REPLACEMENT stale copy** — "re-eval ~07-31" replaced with "low-priority to reopen" reflecting that BLEND_HOURS 24→4 (07-28) resolved the root long-lead regression this REPLACEMENT was meant to address.
- **Lsr sr row** — removed "Today's vs-raw = 0% because Lsr skips calm regime (today's state_curr)" (state_curr changes tick-to-tick, was misleading as a static claim). Added 08-04 bias-table refresh note.

</details>

<details>
<summary><strong>v0.6.394 • August 5, 2026 (Lsb flipped ENABLED=True — sr sea_breeze cc-gated Lsr override goes live)</strong></summary>

- **Lsb (sr_sea_breeze_lsr_override.py) flipped ENABLED=True.** Fresh 7-day gate on the narrowed cc<25 shape cleared: 7/7 daily PROMOTE verdicts (07-30 → 08-05) from `sr_sea_breeze_lsr_refit_stage2.py`. Today's Stage 2 (n_test=1,838): pooled Δ +11.34%, halves +23.9%/+4.0% (both ≥ 0), lead-band all 4 SHIP, cc-bin 0-25 +44.6% (n=718, halves +49%/+34%). Per-hour: 5 SHIP (12, 14, 17, 18, 19), 3 SKIP (13, 15, 16). Curated table is `weather_collector/data/sr_sea_breeze_lsr_curated.json` (unchanged shape — runtime reads hourly_bias_wm2 + cc_gate, ignores `enabled` field which is informational).
- **Watch points for 14-day post-ship gate:**
  - Hour 13 SKIP on test set (bias +16.49 W/m² still applied). If sr Last-24h drags, curator needs a per-hour SHIP filter — cheap follow-on.
  - Halves B +4% is notably weaker than halves A +24%. Recency-weaker signal, not a blocker. If halves B stays weak past 08-12, revisit narrowing further.
- **Wire path unchanged.** Override is on the confidence-layer/apply side; Lsr base bias (`solar_correction.py`) continues to run for non-sea_breeze regimes. Skip regimes for base Lsr (ne_flow, calm) remain in place.

</details>

<details>
<summary><strong>v0.6.393b • August 5, 2026 (analysis fossil-window slide — 11 h_* scripts +4d)</strong></summary>

- **Batch WIN_ slide across 11 analysis scripts.** Digest sentry flagged max window date 08-01 across `h_ch_persistence_blend`, `h_ch_persistence_blend_stage2`, `h_cl_persistence_blend`, `h_cl_persistence_blend_stage2`, `h_dp_residual_persistence_stage2`, `h_full_regime_sweep`, `h_l3_asymmetric_stage1`, `h_t_l2_regression_stage1`, `h_wd_persistence_gate_stage1`, `h_wd_persistence_gate_stage2`, `h_wg_residual_persistence_stage2`. Slid uniformly +4d: WIN_A 07-17→08-01 becomes 07-21→08-05; WIN_B 07-02→07-17 becomes 07-06→07-21; WIN_FULL 07-02→08-01 becomes 07-06→08-05. Halves-agreement layout preserved (2×15d, non-overlapping). Spot-verified on `h_ch_persistence_blend`: SHIP verdict holds under new window, all 7 winning regimes still ★, higher n (26k vs prior). Any 7-day streak or gate-cleared verdict on these scripts before tomorrow's digest is now trustworthy.

</details>

<details>
<summary><strong>v0.6.393a • August 5, 2026 (scoreboard: touched-fields mean/median line)</strong></summary>

- **Touched-fields aggregate on the Overall vs raw tile** (`corrections_debug.html`). Joe flagged the mean/median gap this morning (−12.9% mean vs −0.9% median on 7d MAE). Root cause: 3 fields (pa, pr, plus pp which is Brier-only) have no MAE-affecting layer, so prod ≡ raw by construction — three exact 0.00% entries pull both aggregates toward zero and land the median in a run of zeros. Added `MAE_UNCORRECTED_FIELDS = {pa, pr}` (pp already routed to `brierRows`). New sub-tile below existing median: "MAE mean · touched (n=9) · median X%" with an "excludes pa/pr (no MAE stack) + cc/dp (derived)" caveat. All-fields mean/median stay as-is — the top line answers "myweather vs raw across everything", the touched line answers "how much lift the correction stack actually produces." Both shown so a single number can't mislead either direction.

</details>

<details>
<summary><strong>v0.6.393 • August 5, 2026 (C1h narrow-promote Stage 3 ship — 9 SHIP cells commit + co-axis gate refresh)</strong></summary>

- **C1h curated table committed** (`weather_collector/data/c1h_curated.json`). Stage 3 gate cleared 7/7 days (oldest match 07-30). Ship set: 9 SHIP cells (cc 12-23h & 24-47h, cl 12-23h & 24-47h, cm 12-23h & 24-47h, ch 12-23h & 24-47h, t 12-23h). Diff vs previously shipped: cc/6-11h, ch/6-11h, cm/6-11h demoted SHIP WIDEN → SKIP (sample floor — n_fires 538–660, curator MIN_N=1000). t/24-47h demoted MARGINAL WIDEN → SKIP (magnitude floor +1.08%). t/12-23h flipped MARGINAL WIDEN → SHIP NARROW (−10.7%). Halves check across 3 rolling 7d windows: −14.3% / −0.1% / −17.4% — NARROW stable in 2 of 3, old WIDEN reading was the mid-July outlier.
- **`_C1H_CO_AXIS_GATE` refreshed** (`confidence_layer.py`). Two entries had stale `always_skip:True` (REDUND both under prior ortho eval); today's `h_c1h_orthogonality` puts both at AMBIG both. Lifted to `require_c1f_off + require_c1e_off` — C1h fires on its residual signal only when neither incumbent axis is active: ch/24-47h and t/12-23h.
- **Scope:** narrow-promote only. No changes to the multi-axis v2 join or to the marginal premium application in `_c1h_fires_per_band_field`. The v0.6.316 wiring shell is unchanged; this commit is data + gate.

</details>

<details>
<summary><strong>v0.6.392 • August 4, 2026 (raw-difficulty index — "did the model improve, or was the weather easier?")</strong></summary>

- **New audit signal in the per-field snapshot label.** `analysis/mae_over_time.py` emits a `raw_difficulty_index` block: per-field ratio of trailing-7d raw MAE ÷ trailing-90d reference raw MAE (this week excluded from the reference). Ratio > 1.0 = the raw model itself struggled more than usual this week; < 1.0 = easier week. Debug page audit label now shows the mean ratio plus the three hardest and three easiest fields.
- **Why:** aggregate weekly correction lift can move because the model got better or because the weather got easier — the two are indistinguishable without a correction-independent difficulty reference. Persistence skill was the closest existing signal but persistence difficulty is itself weather-dependent (stable ridges make persistence excellent, fronts make it terrible), so it's not an external reference. Raw MAE is. First-run today: mean 1.04× (basically flat) hides bimodal spread — cloud fields +18 to +67% harder than 90d normal (pa 1.67×, cm 1.62×, pp 1.29×, ch 1.19×, cl 1.18×), thermo fields 23-43% easier (dp 0.57×, h 0.62×, wd 0.66×, t 0.77×). Cloudy-and-mild week. Per-field normalization prevents unit mixing (can't average °F with W/m²).
- **Scope:** just the third line of the framework Joe outlined — observed lift is already in the top table, standardized lift is deferred. The raw-difficulty ratio alone answers the confounding question: when a weekly aggregate moves, the reader can tell at a glance whether the raw baseline moved with it.

</details>

<details>
<summary><strong>v0.6.391 • August 4, 2026 (4 substantive ships + debug page sweep)</strong></summary>

- **Ccd saturation guard** (`cc_from_derivation.py`). cc losing +9.8% Last-24h despite cl/cm/ch all winning. Last-24h pair-log bucket by (regime × obs_cc bin) traces the entire loss to obs bin 95-100 (n=235 across pre_frontal/se_flow/sea_breeze/sw_flow): raw MAE ~2, Ccd MAE ~30 (+1000%+). Root cause: cm's Lc has bias +26.9 → −10.0 (over-corrected 10 pts), ch bias +40.7 → +12.8. `max(cl_l6, cm_l6, ch_l6)` sits in the 60-80s when obs is 100. Fix: `SAT_THRESHOLD = 90.0` — if raw cc ≥ 90, keep raw. Ccd still owns clear/partly-cloudy tail (bin 5-20: n=480, −45% MAE). Same shape as v0.6.389g cc/95-100 Lc skip (now a no-op since cc no longer runs Lc). Telemetry: `sat_holds` count in `cc_from_derivation` per-tick block.

- **Lsr bias table drift fix** (`solar_correction.py` + `analysis/l5_recompute_biases_hourly.py`). sr Last-24h +10.1% traced to `_BIAS_BY_REGIME_HOUR` being hardcoded at v0.6.248 ship (2026-06-28) and never refreshed. Diff vs today's fitter: 47 cells with |Δ| ≥ 50 W/m², frontal regime had 8 live entries with 0 fresh support (fitter dropped it). Multiple cells sign-flipped; sw_flow/16 moved −170 → +136 (Δ +306 W/m²). Structural fix: fitter now writes `weather_collector/data/lsr_bias_table_curated.json`; `solar_correction.py` loads that JSON at import time and overrides embedded dicts when present. Embedded dicts remain as canonical fallback. Same pattern as `lc_correction_table.json`. `_BIAS_TABLE_SOURCE` + `_BIAS_TABLE_GENERATED_AT` exposed at module level for audit. Retires the manual-sync drift class per `[[feedback_curated_json_daily_drift]]`.

- **dpbp flipped ENABLED=True** (`dp_bias_persistence.py`). First antecedent-error specialist LIVE. Shipped 07-28 v0.6.387 ENABLED=False; 7-day gate cleared. Stage 1 halves-verified: pre_frontal +17.2% (halves +21.6/+12.0), nw_flow +14.5% (+15.6/+13.8), sw_flow +14.6% (+6.1/+17.9). Pooled dp MAE 3.108 → 2.808. Fires when regime ∈ focus AND lead ≥ 6h AND prev_24h_dp_bias < −1.5°F → +2.0°F. Preflight verified: code unchanged since ship, params match Stage 2, shadow write firing +2.0°F per lead in nw_flow (38 leads this tick), dp Last-24h at −3.2% healthy baseline. Preflight gap flagged: `corrected_dew_point_shadow_dpbp` not stamped in pair log — same infra gap likely at chp/wdp flip. Follow-up: give dpbp the v0.6.382p treatment (stamp shadow key to error log) for future measurable pre-flip gates.

- **wg L3 SKIP_TABLE +3 cells** (`decay_apply.py`). 08-04 re-cut clears the two 07-28 held cells plus one new: calm/24-47 (n=1744, pooled +45.2%, halves +4.3/+53.1), sea_breeze/24-47 (n=2298, +31.1%, +4.0/+45.0), frontal/12-23 (n=443, +8.8%, +13.2/+4.5 — NEW). A halves on the 24-47 pair drifted 7→4 but still above 3% floor; pooled damage +45%/+31% justifies shipping now with demote-on-A-negative watch at next re-cut. Live table now 7 cells.

- **Debug page sweep.** Today tile Mon 08-03 → Tue 08-04. Recent Activity: added 08-04 (4 ships) and 08-03 (v0.6.390v/w/x/y). Trimmed 08-01 and earlier to changelog per rolling 3-day window. Layer status updated: dpbp (LIVE), wsbp (HELD — calm regime n=0 in shadow week), Ccd (SAT_THRESHOLD guard), wg L3 (4 → 7 cells).

- **Metric provenance — 7-day cut unified, narrative auto-populated, audit label added.** Review flagged two different 7-day numbers on the debug page (top per-field table vs narrative), both labeled the same, from different sources. Top table was reading `tsDoc.per_layer_mae_by_lead` as unweighted mean of leads 1-47; narrative was hand-typed and stale. Four-part fix:
  - `analysis/mae_over_time.py` now emits a `last_7d` block (parallel to `last_24h`) — n-weighted rollup across the trailing 7 calendar days from the per-day merged series, using `sum(mae_d * n_d) / sum(n_d)`. Single canonical 7d cut for the whole page.
  - `renderPerFieldSnapshot` in the debug page now overrides pf-mae cells from `mot.last_7d` inside the same fetch that populates pf-today from `mot.last_24h`. Same source, same aggregation — the two columns in a row are always comparable.
  - Hand-typed narrative at old line 914 replaced with an auto-populated container that bins fields by 7-day performance from the same `last_7d` source. No more stale prose.
  - Audit label under the section: source file, window, aggregation method, refresh timestamp — one small line per section as the reviewer suggested.
- **PROD_PRIORITY + _prodKey + _applied gap fix.** dpbp had just shipped ENABLED=True but wasn't in any of the priority chains — fallback would silently pick `l4` for dp when `prod_real` was missing. Added dpbp (dp) and wsbp (ws, kept for post-flip continuity). Both `_prodKey` implementations in the file now match.
- **`tests/test_prod_key_coverage.py` — new metric-plumbing test.** Discovers ENABLED specialists from `weather_collector/processors/`, extracts PROD_PRIORITY / _prodKey / _applied from `corrections_debug.html`, asserts every ENABLED specialist is in every priority chain that touches its field(s). Sibling of `test_layer_tuple_sanity.py`; same class of silent-lie prevention. Runs in the existing pytest suite (19 → 23 passing).

- **Deferrals.** wsbp HELD (calm regime n=0 in 7-day shadow-log window — preflight step 1 fails). Lsb HELD 24h post-Lsr change for clean attribution.

- **build.py regex fix.** `id="appVersion"` regex was `[a-z]?` (single optional lowercase); doubled-letter suffixes would silently fail to update `version.json`. Widened to `[a-z]*`. Not needed after this renumber but kept — same class of silent failure.

</details>


<details>
<summary><strong>v0.6.390y • August 3, 2026 (h_persistence_skill.py Prod-forecast reconstruction fix — third silent-lie metric bug in a week)</strong></summary>

- **`h_persistence_skill.py` was scoring L2 as "Production" for every field.** The `mae_prod` accumulator read the top-level `forecast` field, which is L2-semantic by design (`forecast_snapshot.py:246-249` — the Fitter needs raw errors to calibrate decay coefficients so the top-level key stays at L2). For ch this meant the Prod line was really L1 — chp's actual 0-error contributions were invisible. Sample confirmation: an applied_layer=chp row had `forecast_chp=6.0, error_chp=0.0` (perfect) but `forecast=0.0, error=-6.0` (L1's raw error), and the script scored the -6.0.
- **Fix:** reconstruct production forecast from `forecast_{applied_layer}` when the stamp is present; fall back to forecast_l4, then top-level. Effect on Prod-vs-L4 skill deltas: **ch −1.06 → +0.09** (chp actually helps, not hurts), cm −0.10 → +0.08, cc/wg deltas collapse to zero (no specialist active for the scored rows).
- **Same class as v0.6.390j (shadow-write applied_layer trap), v0.6.390o (cl backfill), and v0.6.390p (wd L1_ONLY field routing trap).** All four were "the metric is looking at the wrong layer's error." Broader sweep needed — likely other analysis scripts read top-level `error` as Production.

</details>

<details>
<summary><strong>v0.6.390x • August 3, 2026 (debug page Recent Activity refreshed for 08-03; path updated post-rename)</strong></summary>

- Recent Activity moved "today" marker to Mon 08-03 with the 94-row residual backfill + `.skip.py` rename. Prior 08-02 entry demoted, path reference updated to the renamed script.

</details>

<details>
<summary><strong>v0.6.390w • August 3, 2026 (cl applied_layer poison backfilled; retire backfill from daily digest)</strong></summary>

- **Backfilled 94 poisoned cl applied_layer stamps in the pair log** (clp→l1, 0 unresolved) and uploaded the corrected log to GCS. The v0.6.390j guard stopped new poison at write time; this backfill cleans the residue so the 7d field-skip sanity alert can roll off.
- **Renamed `analysis/backfill_cl_applied_layer.py` → `.skip.py`** so `run_digest.sh` stops calling it every morning. It's one-shot maintenance, not a daily analysis — the digest was FAILing it with "pass --dry-run or --apply" on every run.

</details>

<details>
<summary><strong>v0.6.390r • August 2, 2026 (scoreboard: add rolling 24h sub-line to Biggest gain / regression / worst-cell tiles)</strong></summary>

- **Full 7d + 24h symmetry across the scoreboard.** Only the Overall-mean tile had a 24h read; Biggest gain, Biggest field regression, and Worst cell tiles were 7d-only. Adding 24h subs makes the whole banner readable at both cadences: 7d catches sustained drift, 24h catches fresh single-day movements the 7d smooths over.
- **`analysis/mae_over_time.py` emits `last_24h_bands`.** Per (field, band, layer) MAE/RMSE/bias/brier — same shape as `last_24h` but split across bands (0-5h, 6-11h, 12-23h, 24-47h) so the Worst-cell tile renders a 24h read at the same band-granularity as its 7d read. Uses lead_h from each pair-log row; MIN_N floor = max(10, MIN_N_PER_DAY/20) to keep bands visible.
- **Debug page — three new sub-tiles.** Added `tile-best-24h`, `tile-worst-24h`, `tile-worst-band-24h` under each existing 7d tile. Populated in the same async fetch that fills the per-field "last 24h" column. SCOREBOARD_EXCLUDE = {cc, pp, dp} (matches DERIVED_FIELDS exclusion from the mean).

</details>

<details>
<summary><strong>v0.6.390q • August 2, 2026 (KPI tile static text "today" → "last 24h" to match column rename)</strong></summary>

- Static initial-state HTML for the Overall MAE-mean tile still said "MAE mean · today"; JS updated it to "last 24h (Nf)" after mae_over_time loaded, so users saw "today" flash briefly. Now consistent everywhere.

</details>

<details>
<summary><strong>v0.6.390p • August 2, 2026 (per-field snapshot: "today" → rolling "last 24h" — always contains a full diurnal cycle)</strong></summary>

- **Root fix for morning-easy bias in per-field snapshot.** Calendar-day "today" column at 7am contained ~7h of overnight data (cool, calm, stable), so every field looked artificially good in the AM and everything's numbers shifted through the day as the sample filled. Never a fair scoreboard read until end-of-day, at which point it flipped to "yesterday" the next morning. Rolling 24h always contains a full diurnal cycle and is a matched comparison to the 7d column.
- **`analysis/mae_over_time.py` emits `last_24h` aggregate.** Per (field, layer) MAE/RMSE/bias/brier over rows with `obs_time >= now − 24h`. MIN_N floor = max(30, MIN_N_PER_DAY/5) — thin windows still filtered. Payload gains top-level `last_24h` dict + `last_24h_window_start_utc`.
- **Debug page column re-wired.** Header renamed "today" → "last 24h" with new title-attr. `renderPerFieldSnapshot()` reads `mot.last_24h[field][layer]` directly instead of walking `series[field][layer][day]` for most-recent-obs-day. Removed the per-day walk that stripped the day-suffix (no longer applicable). Overall tile updated to "MAE mean · last 24h".
- **First honest read (2026-08-02 12:47 UTC window start):** every stack-carrying field either winning or flat vs raw. h -9.1% (retune v0.6.390g landing hard), ws -6.0% (wind_blend BLEND_HOURS=4 landing), wg -23%, cm -62%, ch -68%. pp/pa/pr flat as designed. cl/wd/t small consistent wins.

</details>

<details>
<summary><strong>v0.6.390o • August 2, 2026 (cl applied_layer poison backfill + L1_ONLY routing fix for wd + full debug-page sweep)</strong></summary>

- **cl applied_layer poison backfilled (`analysis/backfill_cl_applied_layer.py` NEW).** cl regression sentry had been screaming +67% for days despite production actually tracking raw. Root cause: pair-log rows 07-27 → 08-01 were stamped `applied_layer=clp` or `l6` due to the pre-v0.6.390j shadow-write bug, making `mae_over_time.prod_real` (which reads `error_{applied}`) pull phantom shadow errors instead of the real production error. Fixed forward by v0.6.390j guards, but historical rows kept poisoning trailing metrics. One-shot backfill script mirrors `_derive_applied_layer` logic on per-row errors to re-stamp cl rows (5,779 → l1, 55 → l2, 0 unresolved). Rebuilt `mae_over_time.json` with `MERGE_REFRESH_DAYS=10` and re-uploaded corrected pair log to GCS. cl now reads 7/7 wins over 7 days, −1.1% vs raw. Regression sentry: all fields clean.
- **L1_ONLY field routing trap fixed (`analysis/mae_over_time.py`).** `mae_over_time.py`'s L1_ONLY branch was routing top-level `error` (which is L2-view since `fc = wd_l2` per forecast_snapshot) into the `raw` bucket for wd. Result: raw == l2 identically on every day for 13 days since v0.6.368a shipped wind_blend, hiding wd's L2+wdp contributions in every field-health scoreboard. Fix: prefer `error_l1` (present since v0.6.368a); fall back to `error` only for pre-v0.6.368a rows. Also emits inline `prod_real` for L1_ONLY fields from the deepest specialist (L1_ONLY doesn't get applied_layer stamping). Real wd picture surfaced: L2 −2 to −5% vs raw most days, wdp adds another 0-4%. 07-31 outlier: calm/24-47 wdp +72%, sea_breeze/0-5h wdp +109% — real gate misfires now visible. New memory `feedback_l1_only_field_routing_trap` requires this audit on any new correction for an L1_ONLY field.
- **Fossil windows slid** on `h_wg_l3_regression_stage1.py`, `h_ws_l3_regression_stage1.py`, `h_ch_persistence_blend_stage2_vs_l6.py` — all had WIN_A_HI stuck at 07-28, flagged as fossils in this morning's digest. Slid forward 5 days.
- **Debug page — full Rule 5 sweep.** "What's being evaluated next" calendar had "Thu 07-30 · today" stuck as today (3 days stale) — rewrote calendar block with correct dates and today's actual context. Bumped Recent activity today-label 08-01→08-02, demoted 07-31 "yesterday"→"2 days ago". Updated ~15 day counters in Post-ship watches (h L2 retune 0/7→2/7, Lc regime 1/7→3/7, chp closes-today flag, wdp 2/14→6/14, Lsb/dpbp/wsbp 1/7→5/7, wind_blend/wg L3/ws L3 2-cell 1/14→5/14). Rewrote per-field snapshot narratives for h (honest "red 7d +2.8%, direction favorable but hasn't earned green"), cl (post-backfill 7/7 wins), ch (day 14/14 closes today), wd (L2+wdp real picture noted). Rewrote bottom summary line: clean green/red/marginal buckets, no cherry-picked daily numbers.

</details>

<details>
<summary><strong>v0.6.390n • August 1, 2026 (debug page sweep — Recent activity block for today's 4 ships)</strong></summary>

- Added Recent activity entry for 2026-08-01 covering v0.6.390j/k/l/m (applied_layer fix, layer-tuple test, recent-bias sensor, action-list at top, fossil-window cleanup, dpp HOLD).
- Demoted 07-30 date label from "yesterday" → "2 days ago"; 07-31 → "yesterday". Stale-refs checker clean.

</details>

<details>
<summary><strong>v0.6.390m • August 1, 2026 (fossil-window cleanup — 11 h_ scripts slid 9d forward)</strong></summary>

- **11 h_ scripts slid forward.** Windows updated: `WIN_A = 2026-07-17 → 2026-08-01`, `WIN_B = 2026-07-02 → 2026-07-17`, `WIN_FULL = 2026-07-02 → 2026-08-01`. Prior windows were 07-08 → 07-23 (9 days behind today), flagged as fossil-window suspects in the digest since 07-31. Scripts: `h_ch_persistence_blend[.py, _stage2.py]`, `h_cl_persistence_blend[.py, _stage2.py]`, `h_dp_residual_persistence_stage2.py`, `h_full_regime_sweep.py`, `h_l3_asymmetric_stage1.py`, `h_t_l2_regression_stage1.py`, `h_wd_persistence_gate_stage1[.py, _stage2.py]`, `h_wg_residual_persistence_stage2.py`.
- **Verdicts now trust-worthy again.** Any 7-day streak or gate-clear on these scripts was previously a re-read of the same stale data. Tomorrow's digest will produce halves-verified reads over post-07-25 regime shift + full recent HRRR-drift period.
- **Left for tomorrow:** 3 scripts still 4d behind (`h_ch_persistence_blend_stage2_vs_l6`, `h_wg_l3_regression_stage1`, `h_ws_l3_regression_stage1`) — under the 3-day fossil threshold but marginal. Slide when they next roll fully out.

</details>

<details>
<summary><strong>v0.6.390l • August 1, 2026 (digest action-list at top — highest-severity sentry alerts mirrored above executive summary)</strong></summary>

- **Action list at digest top.** New `action_list` block ahead of `EXECUTIVE SUMMARY` mirrors the highest-severity alerts from the three sentries below: SUSTAINED FIRE from `regression_sentry`, τ-suspect ★ from `layer_shape_sentry`, and any FIELD_SKIP divergence from `field_skip_sanity_check`. Caps at 5 lines to prevent domination. Empty when nothing fires — no visual noise on clean days. Solves the "buried alerts" complaint driving plan-item-#5 in the pipeline-to-good plan: sentries were computed but sat below stale-windows and ship-eligible sections in the digest.
- **No new signal.** This is a priority-reorder of existing outputs. Same alerts still appear in their original sentry sections below.

</details>

<details>
<summary><strong>v0.6.390k • August 1, 2026 (layer-tuple sanity test + recent-bias-gate Stage 0 sensor)</strong></summary>

- **Layer-tuple sanity test (`tests/test_layer_tuple_sanity.py`).** Two assertions run under pytest: (1) the layer tuple walked by `forecast_snapshot._derive_applied_layer` must equal the tuple emitted by `forecast_error_log` per-layer loop — any drift means applied_layer gets stamped to a layer with no matching `error_` column, or vice versa; (2) every specialist in the walk (post-l6: chp, clp, wdp) must have an ENABLED guard in `_derive_applied_layer` — enforces the v0.6.390j prevention pattern for future specialists. Would have caught v0.6.390c's wdp-missing-from-tuple silent bug and v0.6.390j's clp-shadow-mislabel bug at commit time. Runs in 0.6s.
- **Recent-bias gate Stage 0 sensor (`analysis/h_lc_recent_bias_gate.py`).** Attempted architectural fix for cl bleeding: keep the lc_fit shift table but only apply per-cell when the past-3-day observed bias still agrees in sign AND ≥50% magnitude with the historical trained bias. Stage 0 pooled looked promising for cc (+5.9%). Stage 1 halves-strict killed the promote — half B (recovery days) showed the live shift was actually correct while the gate stayed off from lagged recent-bias measurement. HOLD, not shipping. Script stays as a standing daily digest sensor — recent-vs-historical divergence table per (field, bin) is a useful drift signal even without gate action. Cl root-cause remains open; next attempt should try an asymmetric gate (fast-off on divergence, fast-on when recent re-agrees) or shorter recent window.

</details>

<details>
<summary><strong>v0.6.390j • August 1, 2026 (applied_layer stamp gated on specialist ENABLED — fixes cl snapshot showing clp shadow as production)</strong></summary>

- **Bug.** cl's per-field snapshot cells (7d avg + today) went red overnight — 7d "vs raw" ~+50%, today +83%. Real cl production is essentially = raw (Lc is field-skipped on cl since v0.6.389f), so both cells should track flat-vs-raw. Root cause: `forecast_snapshot.py:_derive_applied_layer` walked `("l1"…"l6","chp","clp","wdp")` unconditionally, and `cl_persistence_gate.py:204` writes `cloud_cover_low_shadow_clp` regardless of ENABLED (per v0.6.382p flip-gate visibility fix). Whenever the shadow value differed from l6 the walk stamped `applied_layer=clp` — poisoning Fitter's `per_layer_mae_by_lead[cl].production` (7d cell) and `mae_over_time[cl].prod_real` (today cell). Same class of bug lurked for chp and wdp but both are ENABLED=True so their stamps were legitimate.
- **Fix.** Skip specialist keys in the walk when the corresponding module is `ENABLED=False`. Three-line guard inside `_derive_applied_layer` reading `cl_persistence_gate.ENABLED`, `ch_persistence_gate.ENABLED`, `wd_persistence_gate.ENABLED`. Shadow arrays still written unconditionally so the flip-gate keeps its evaluation signal. When any of those specialists flip ENABLED=True the guard automatically re-includes them — no coordination needed with the ship commit.
- **Recovery.** Fix takes effect on new pair-log rows and forecast snapshots. Existing poisoned stamps in `mae_over_time.json` roll off over the trailing 7-day window (fully clean ~08-08). Today cell should flip green within one Fitter cycle after collector deploy.
- **Prevention.** Added `field_skip_sanity_check()` to digest — for any field in `cloud_saturation_correction._FIELD_SKIP` (excluding derived fields like cc), 7d trailing `prod_real` must equal `raw` within ±5%. Divergence = applied_layer stamp bug. Would have caught the clp mislabel on day 1 instead of day 5. Currently fires on cl (+56.3%) as expected; clears within 7d after collector deploy as poisoned rows roll off.

</details>

<details>
<summary><strong>v0.6.390d • July 30, 2026 (layer-shape sentry — τ-suspect + per-band production-vs-raw alerts in digest)</strong></summary>

- **Layer-shape sentry added to digest.** New `layer_shape_sentry()` in `build_executive_summary.py`. Complements the daily regression_sentry — which fires only when a field's day-total Prod-vs-Raw ≥+15% for 2 days. That failed to catch h, whose day-total stayed under threshold while L2 was helping short-lead (−18%) and hurting long-lead (+11-13%). Reads `time_series_diagnostic.json` per-lead MAE arrays; for each field's production layer, checks all four lead bands (0-5h / 6-11h / 12-23h / 24-47h) with n ≥ 100 per band.
- **Two alert classes.** (1) Per-band ⚠ — production hurts raw by ≥+10% at any band, with n and layer/band named. (2) τ-suspect ★ — production HELPS at 0-5h (≤ −5%) AND HURTS at any later band (≥ +5%). Classic "decay time-constant too long" signature — bias signal that's real at short lead gets kept alive too far into the horizon. τ-suspects head the sentry section because they're the most actionable (shorten τ or add lead-band SKIP).
- **Retro-fire on current data.** First run catches: **h/production** (τ-suspect, −20/+11/+12/+9), **dp/production** (τ-suspect, −28/+7/+8, new finding), **wd/production @ 6-11h +43%** (new finding, missed because today-cell was broken pre-v0.6.390c), plus recovering-from-ship noise on cc/cl/ws (expected — trailing window still contains pre-fix days). Both τ-suspects warrant τ-refit investigation as their own Stage 0 → Stage 1 workstreams.
- **Fetches tsDoc via `analysis._cache.cached_path`** with 6h max age — same pattern as h_cc_derivation and other analysis scripts that pull GCS data. Silent on missing file (diagnostic, not blocking). Runs after regression_sentry, before persistence-skill watch.

</details>

<details>
<summary><strong>v0.6.390c • July 30, 2026 (Overall today tile + wd today fix + per-field prod-priority fallback)</strong></summary>

- **Overall today tile.** New line in the "Overall vs raw" scorecard tile: shows mean of independent fields' today Prod-vs-Raw (cc + pp excluded). Populated by `renderPerFieldSnapshot()` from the same per-field today data it reads for the table below. Answers "how bad is today really" at a glance — the 7d avg number is trailing and hides fresh damage. Renders below RMSE mean, above MAE median. Field count shown ("Xf") so you know the denominator.
- **wd today cell fix — root cause.** `forecast_error_log.py:245` iterated over `("l1", "l2", ..., "chp", "clp")` when writing per-layer errors — `wdp` was missed when wdp shipped 07-27. So wd pair-log rows had `applied_layer="wdp"` on gate-firing ticks but no `error_wdp` column, and `mae_over_time.py`'s `prod_real` accumulator (`prod_real_buckets` keyed on `applied_layer` + `error_{applied}`) skipped every wd row. wd showed "no data" in the today column even though wdp/l2 series in mae_over_time were populating fine. Added `"wdp"` to the tuple. New pair-log rows now carry `error_wdp` (circular diff); `prod_real` for wd will start populating on tomorrow's digest as `mae_over_time.py` re-runs.
- **Frontend fallback for the transition.** Rather than wait for the digest to backfill, `renderPerFieldSnapshot()` now walks a per-field production-layer priority list — prefers `prod_real`, falls back to specialists (chp/clp/wdp), then l6/l5/l4/l3/l2/l1, finally raw. Whichever exists deepest for the most-recent day wins. Cell tags the fallback layer in parentheses `(wdp)` at low opacity so you can tell when it's not using prod_real. Mirrors `renderScorecardBanner`'s `_prodKey` logic. wd will render today from `wdp` series immediately even before the digest backfill lands.

</details>

<details>
<summary><strong>v0.6.390b • July 30, 2026 (per-field snapshot gains 'today' column alongside 7-day)</strong></summary>

- **'today' column added to per-field snapshot.** v0.6.390a wired the "vs raw" column live but that source (`tsDoc.per_layer_mae_by_lead`) is a rolling 7-day trailing average — it'll show cl at +65% for another 3-5 days as the 07-28/29/30 damage rolls off, hiding whether today's field-kill is actually working. New "today" column reads the most-recent-obs-day Prod-vs-Raw from `mae_over_time.json` (same series the regression sentry uses). Together the two columns answer both questions on the same row: "did we ship something bad today" (today col) and "is the pipeline healthy on average" (7d col). Table header renamed "vs raw" → "7d avg"; new "today" column between it and Status. Each row gains `<td class="pf-today" data-field="<k>">`; `renderPerFieldSnapshot()` extends with an async fetch of mae_over_time.json + populate logic. Cell shows pct and MM-DD of the day being read.

</details>

<details>
<summary><strong>v0.6.390a • July 30, 2026 (per-field snapshot wired live + debug page Rule 5 sweep for v0.6.390)</strong></summary>

- **Per-field snapshot table wired live.** The "Current pipeline state — per-field snapshot" table's "vs raw" column had been hand-edited static text — went stale between debug-page sweeps and hid real events (cl went catastrophic 07-28 → 07-30 but the snapshot cell still read "−0.2% flat pre-Lc" for days). Every field's percentage cell now has `class="pf-mae" data-field="<key>"`; new `renderPerFieldSnapshot(tsDoc, wxDoc)` reads the same `tsDoc.per_layer_mae_by_lead` the scoreboard reads, computes `_avg1to47(prod) vs _avg1to47(l1)`, and populates each cell with matching color logic (green ≤ −0.5%, orange within ±0.5%, red ≥ +0.5%). pp cell uses `data-brier="1"` to read the Brier doc instead. Called after `renderScorecardBanner` on every load.
- **Debug page Rule 5 sweep for v0.6.390.** Post-ship watches — Lc intervention entry rewritten to reflect cl+cc both in `_FIELD_SKIP` (was cl only + cc bandages); Ccd 7-day gate marked CLEARED EARLY with new watch triggers going forward; Calendar 08-06 Ccd flip check marked cleared early. Correction stack list — Lc description now "cm/ch only; cl + cc BOTH OFF"; Ccd description now "LIVE ENABLED=True". Correction stack routine list bullet updated. Recent activity — today's session summary bumped to 10 ships, v0.6.390 entry added at top with full architectural context. Per-field snapshot Status column for cc/cl/h rewritten. Stable-wins summary line rewritten with fresh categorization (Stable wins / Regressing / Killed-or-retired). Applied-layers column for cc updated to show Lc struck out and Ccd substituted; cl also shows Lc struck out.

</details>

<details>
<summary><strong>v0.6.390 • July 30, 2026 (Ccd flip early — cc retired from Lc, cc excluded from scoreboard aggregate)</strong></summary>

- **Ccd flipped ENABLED=True** in `weather_collector/processors/cc_from_derivation.py`. Six days ahead of the originally-planned 08-06 gate. Rerun of `h_cc_derivation.py` against post-cl-field-kill data reconfirmed the +8.48% pooled MAE win vs current production cc (halves +11.4% / +5.8%, both positive, 6/10 regimes win). The 7-day gate was normal caution; the math is a 20-line `max()` and the evidence base is 123K held-out quads over 30 days. Flip is warranted.
- **cc retired from Lc entirely.** `_FIELD_SKIP` in `cloud_saturation_correction.py` gains `"cc"` alongside `"cl"`. All three cc entries removed from `_CELL_SKIP` (moot post-Ccd since Ccd overwrites `hourly.cloud_cover` after Lc runs). cc is now a derived field: `max(cl_l6, cm_l6, ch_l6)` for ~85% of ticks, Pirate fallback for `SKIP_REGIMES = {"se_flow", "unknown"}`.
- **Why this needed to happen.** cc is HRRR's own internal combine of cl/cm/ch. Running Lc on cc in parallel with running Lc on the three components was double-correction from Lc's original ship weeks ago. The +8.5% Ccd win is what that architectural mistake has been costing us on average; this week's Lc collapse (cl+cc both breaking together) is what it cost us in the worst case.
- **Scoreboard fix.** cc excluded from `meanPct` / `medianPct` / `winningRows` / `regressingRows` / `flatRows` / `best` / `worst` / `worstBand` in `corrections_debug.html`'s accuracy card. Introduced `DERIVED_FIELDS = new Set(["cc"])` and derived-aware filters. cc still renders as an informational line below the tiles ("Derived (not in mean): cc +X%") so its error stays visible without distorting the headline. Including cc in an aggregate that also fully weights cl/cm/ch was double-counting the cloud stack — user-facing scorecard now reflects independent forecast quantities only. `winning fields` denominator will drop by 1 as a result.
- **Deferred.** dp is technically the same shape (dp = Magnus(corrected t, corrected h), derived from tracked components) but its numbers are small (−2.4%) and dpbp/dprp specialists in flight would add independent additive corrections. Not touching dp today.

</details>

<details>
<summary><strong>v0.6.389k • July 30, 2026 (debug page Rule 5 sweep — catch page up to v0.6.389i regression sentry + v0.6.389j Ccd)</strong></summary>

- **Debug page catch-up sweep.** v0.6.389h swept the page for the emergency Lc intervention sites (v0.6.389c-g). This commit extends the sweep to v0.6.389i + v0.6.389j which shipped after that sweep. Sites updated: today's Recent activity entry ship count 5 → 8 + full entries added for v0.6.389j (Ccd) and v0.6.389i (regression sentry); Post-ship watches gained a Ccd 7-day live-shadow gate entry (day 0/7 through 08-06); Calendar gained a Thu 08-06 entry for the Ccd flip check (co-located with the MLC anomaly-detector COLLAPSE suppression expiry); Correction stack routine list bullet + full description list gained Ccd rows. No collector code changes.

</details>

<details>
<summary><strong>v0.6.389j • July 30, 2026 (Ccd — cc from-derivation Stage 3 wire ENABLED=False + h_cc_derivation diagnostic)</strong></summary>

- **Analysis — h_cc_derivation (`analysis/h_cc_derivation.py` NEW).** Architectural question raised by Joe: why is cc corrected independently from a Pirate feed when it could be derived from the Lc-corrected cl/cm/ch? Joins per-(run_time, lead_h) rows across all 4 cloud fields, compares current-production cc against derived random-overlap (`1 - Π(1-x/100)`) and derived max-overlap (`max`). Held-out on 123,050 joined quads (obs 07-01 → 07-30). **VERDICT: PROMOTE** — derived-max beats current-production cc by **+8.5% pooled MAE**, +5.8% halves-averaged, wins in 6/9 real regimes. Loses in se_flow (−6.5%, n=22,803) and marginal-loss in unknown/calm. Wins scale with lead: 0-5h +1.5%, 6-11h +6.2%, 12-23h +8.2%, 24-47h +10.3%. Halves-stable (+11.4% A / +5.8% B).
- **Physical read on why max wins.** METAR total sky cover at KBOS/KBVY reports the coverage of the highest layer that reaches broken/overcast, which correlates more with max than with random-independent union. Random-overlap over-estimates when layers are actually stacked in the same column (common in stratiform regimes). Max is closer to how the human/ceilometer observer classifies "total cloud."
- **Ccd processor (`weather_collector/processors/cc_from_derivation.py` NEW).** Runs LAST in the cloud pipeline — after Lc, after chp/clp. Reads the final `hourly.cloud_cover_low / _mid / _high` arrays (post-Lc for cm/ch; raw for cl since cl is in `_FIELD_SKIP`) and computes `derived_cc = max(cl, cm, ch)` per lead. Regimes in `SKIP_REGIMES = {"se_flow", "unknown"}` fall back to Pirate cc. When ENABLED, mutates `hourly.cloud_cover` in place and preserves original as `hourly.cloud_cover_pirate_raw` for attribution. When ENABLED=False (this ship), stamps `weather_data["cc_from_derivation"]` telemetry with `derived` array + `would_fire` flag for the 7-day gate. Wired into `collector.py` after `stamp_cloud_saturation_correction`.
- **Ship discipline.** ENABLED=False first, 7-day gate on SHIP-set + halves stability. Earliest flip 2026-08-06. Unlike most Stage 3 wires this one already has walk-forward-caliber held-out evidence (h_cc_derivation) rather than just Stage 1 halves, but the 7-day live-shadow gate still applies to catch runtime differences from the offline test (e.g. the `hourly.cloud_cover_low` that Ccd reads is bit-different from the pair-log-recorded `forecast_l6` because Lc runs at forecast issue time before some downstream corrections that don't touch cc directly but might touch the layer arrays).
- **Bonus interaction with today's cl kill.** Ccd is robust to cl being off Lc. When cl_raw feeds the derivation, cm_lc + ch_lc still carry the signal — the derived cc doesn't need cl to be corrected. When Ccd flips ENABLED=True on 08-06 the user-visible cc will look clean even while cl remains off Lc; the emergency `_CELL_SKIP` entries for cc (95-100 universal, ne_flow demotes) become moot because cc no longer gets Pirate + Lc applied.

</details>

<details>
<summary><strong>v0.6.389i • July 30, 2026 (regression sentry in digest — Prod-vs-Raw daily trajectory headline alert)</strong></summary>

- **Digest — regression sentry (`build_executive_summary.py`).** Fires as a headline alert when a field's daily Prod MAE exceeds daily Raw MAE by ≥ 15% for ≥ 2 consecutive days. Reads `mae_over_time.json`'s per-day `prod_real` (or `prod` fallback) + `raw` series over the last 5 days; scans the trailing contiguous run; fires ★ when latest day is ≥ 100%, ⚠ otherwise. Threshold + lookback tunable at module top (`REGRESSION_SENTRY_THRESHOLD_PCT` / `_MIN_DAYS` / `_LOOKBACK_DAYS`). Placed before the persistence-skill and pair-log anomaly sections in the exec summary because "we made a field worse than untouched HRRR for N consecutive days" is more directly actionable than distribution-shift signals — the sentry names the field and the trajectory, not just "something moved."
- **Retro test on today's data:** would have fired **cl** (3-day trajectory +23% → +121% → +659%, worst +659.5%) and **cc** (2-day trajectory +163% → +514%, worst +513.8%). Both are today's Lc emergency intervention targets. On the actual timeline: cl first crossed +15% on 07-28. With the sentry in place, the 07-30 06:01 EDT digest (looking at 07-28 + 07-29 data) would have fired ★ — ~24 hours earlier than the accuracy-card visual catch that triggered today's investigation. See prior v0.6.389d-g for what today's ships did with that time.
- **What it does NOT do:** point at which layer to demote. It names the field + trajectory; you still have to open the per-field per-lead table + mae_over_time detail chart to identify the offending layer. But cutting the "which field is bleeding right now" question from a visual scan to a headline line is where the time savings live.

</details>

<details>
<summary><strong>v0.6.389h • July 30, 2026 (debug page Rule 5 sweep — Lc emergency intervention sites)</strong></summary>

- **Debug page — Rule 5 sweep** to catch the page up to today's 5-ship Lc intervention (v0.6.389c-g). Sites updated: Recent activity today's block replaced with 5-item entry list covering v0.6.389c-g + top-line summary of the Overall Prod-vs-Raw compression diagnosis; yesterday label bumped 07-27 → 07-29; Calendar Thu 07-30 rewritten from routine C1 Stage 4 re-audit to the emergency-intervention story; Fri 07-31 Lc 14-day watch marked as UNCLEAN close (two live-layer interventions during the watch means routine close is moot); Post-ship watches Lc entry rewritten with the field-kill / bin-skip / regime-demote state + reversibility note + walk-forward evidence; new Lc regime-conditional Stage 1 gate entry (day 1/7 through 08-06) with caveat that walk-forward validator already showed the naive 92-cell SHIP set is over-generalized; Lc layer section header SHIP surface rewritten (cl OFF, cc partial, cm/ch unchanged); Lc engineering status now leads with today's diagnosis + reference to [[project_lc_regime_conditional]], prior 07-17 flip block preserved but demoted; correction stack row + L4-stack cloud saturation line + routine-stack list bullet all reflect the split state (cm/ch full, cc partial, cl off). No collector code changes.

</details>

<details>
<summary><strong>v0.6.389g • July 30, 2026 (Lc bin-skip for cc/95-100 + rolling-window diagnostic — no window fixes cl, cc/95-100 is the acute cc bleed)</strong></summary>

- **Analysis — rolling-window diagnostic (`analysis/h_lc_rolling_window.py` NEW).** Sweeps fit windows W ∈ {3, 5, 7, 10, 14, 21, all} days, refits pooled Lc on each, evaluates on the last 3d held-out. Answers "does a shorter fit window recover cl?" **Verdict: NULL** — no window makes cl beat raw. Best cl window is W=3d at −3.7% vs raw. Longer windows compound the damage (W=14d = −101% vs raw). **Also exposes cc broken on last 3d** under every window (best W=7d at −25.5%). cm best W=14d +44.6%. ch best "all" +50.2%. The shift-table architecture can't handle the recent HRRR bias shift with any window length — cl+cc need something adaptive (EMA/Kalman shift tracker) or per-bin gate-when-recent-bias-small logic. cm/ch survive across windows and stay live.
- **cc/95-100 bin-skip (`cloud_saturation_correction.py`).** Diagnosed the specific cc bleed on 07-30: 99% of cc forecasts landed in the 95-100 bin (heavy overcast), obs matched, but Lc's −58 shift dragged corrected cc from 90→32 → error 53. Same architecture failure as cl but bin-concentrated. Rather than field-kill cc entirely (would give up cc/0-5, cc/50-80, cc/80-95 which mostly help), added `("cc", "95-100")` to `_CELL_SKIP` — universal-regime bin demote. Left cc/0-5 (shift +13, still helps most days), cc/50-80 (−27), and cc/80-95 (−30, still SKIP-Δ under Stage 0 but not clearly harmful).
- **Refactor: `_REGIME_SKIP` → `_CELL_SKIP`** unified frozenset supporting both `(field, bin)` shape (universal) and `(field, regime, bin)` shape (regime-conditional). `_shift_for` checks both before honoring the curated SHIP verdict. Telemetry key renamed `regime_skip_cells` → `cell_skip` and now lists both shapes. cc/ne_flow/50-80 and cc/ne_flow/80-95 from v0.6.389d retained as regime-conditional demotes.
- **Current Lc SHIP surface** (after this commit):
  - cl: fully off Lc (`_FIELD_SKIP`)
  - cc: 0-5 (all regimes), 50-80 (all regimes except ne_flow), 80-95 (all regimes except ne_flow)
  - cm: unchanged from live table (all SHIP bins fire in all regimes)
  - ch: unchanged from live table

</details>

<details>
<summary><strong>v0.6.389f • July 30, 2026 (Lc field-kill for cl + walk-forward validator — held-out data says pooled AND regime-conditional both hurt cl)</strong></summary>

- **Analysis — walk-forward validator (`analysis/walkforward_lc_regime.py` NEW).** Forks the walkforward_l3l4_validator pattern for Lc. Single train/test obs_time split (train pre-07-20, test 07-20→07-30). Fits BOTH regime-conditional and pooled tables on train, evaluates both on held-out. Motivation: 7-day Stage 2 walk-forward gate is process discipline; we already have ~30d of pair log, so we can answer the stronger held-out MAE question now instead of waiting a week. **Result:** VERDICT: FLAT overall (-1.55%) — regime-Lc does NOT clearly beat pooled Lc on held-out. Field-level: cc +0.63%, cl **-6.73%**, cm -0.22%, ch +0.28%. Per-cell: 22 SHIP (regime beats pool ≥3%), 21 SKIP-regime (regime loses ≥3%), 98 flat, 49 thin. Stage 1's 92-cell SHIP set is over-generalized; only 22 cells actually help on held-out. Output at `analysis/output/walkforward_lc_regime.txt`.
- **Critical finding on cl.** Walk-forward exposes: pooled Lc hurts cl by **-22.15% vs raw** on held-out; regime-conditional hurts it MORE (-30.37% vs raw). Neither shift-table architecture fits cl's recent distribution. Not a bug in the fit — the architecture itself doesn't work for cl right now. Distinct from cc/cm/ch which all benefit from pooled Lc (+5.3% / +34.7% / +36.3% vs raw held-out).
- **Field-level Lc kill (`cloud_saturation_correction.py`).** `_FIELD_SKIP = frozenset({"cl"})` gates cl out of Lc entirely at the field-loop level in `stamp_cloud_saturation_correction`. cl hourly array is left untouched; `per_field.cl.field_skipped=True` in telemetry so debug page / Fitter can distinguish "gated off" from "no cells fired." `_REGIME_SKIP` cleaned up — 2 cl entries removed as redundant (cl now off at field level). cc's 2 ne_flow demote cells retained since cc still gets pooled Lc. **Reversibility:** removing `"cl"` from `_FIELD_SKIP` re-enables cl Lc — no data loss, no schema change. cl is held out until the fit stabilizes or the architecture is redesigned (candidate: rolling shorter-lookback fit, or shrinkage on the shift magnitudes).

</details>

<details>
<summary><strong>v0.6.389e • July 30, 2026 (Stage 1 halves-strict regime-conditional Lc — candidate curated table + 7-day gate start)</strong></summary>

- **Analysis — Stage 1 fit (`analysis/h_lc_regime_stage1.py` NEW).** Halves-strict version of Stage 0 — both halves must improve by ≥ HALVES_MIN_PCT (not just positive). Chronological halves-split by `obs_time` so recent-anomaly contamination shows up as B < A. Emits `analysis/output/lc_regime_curated_stage1.json` structured for Stage 3 apply-side wiring: `cells[field][regime][bin]` primary + `pooled_fallback[field][bin]` for THIN regime cells. Also emits gate history file `.cache_lc_regime_gate_history.json` with 30-day retention + 7-day flip window (same shape as `.cache_lc_gate_history.json`).
- **First read: VERDICT: STAGE 1 PROMOTE — 92 SHIP cells across 4 fields** (cc:22, cl:29, cm:22, ch:19). Stage 0 had 95 ★ candidates; the stricter halves criterion dropped 3 borderline cells. Pooled fallback SHIP set (15 cells) matches the live `lc_correction_table.json` exactly by construction, giving Stage 3 a clean pooled backstop when a regime cell is THIN. Day 1/7 of the walk-forward Stage 2 stability gate.
- **Next steps (not shipped this commit):** Stage 2 = watch SHIP-set stability across 7 daily digests. Stage 3 = extend `cloud_saturation_correction.py` to read curated regime table with pooled fallback, ENABLED=False first. 7-day live-layer flip gate after that. Emergency `_REGIME_SKIP` frozenset from v0.6.389d gets removed at Stage 3 flip.

</details>

<details>
<summary><strong>v0.6.389d • July 30, 2026 (Lc emergency regime demote — 4 ne_flow cells forced SKIP + Stage 0 regime × bin sweep)</strong></summary>

- **Analysis — Stage 0 sweep (`analysis/h_lc_regime_stage0.py` NEW).** Forks `lc_fit.py` fitting logic to bin by `(field, regime, bin)` instead of pooled `(field, bin)`. VERDICT: SIGNAL — **95 ★ cells across all 4 cloud fields** (cc/cl/cm/ch) pass MIN_N=200, |bias|≥5pp, Δ MAE ≥ 4%, both halves positive. Divergence table surfaces 33 cells where pooled-live shift differs from regime-conditional shift by ≥8pp. Signal is time-stable (13/204 cells halves-diverge). Motivation: cl+cc broke 07-28→30 (raw cl MAE 7.29 → Lc-corrected 56.96 on 07-30, 8× worse). Root cause: pooled Lc is regime-blind; ne_flow gets over-corrected by 22-26pp at overcast bins while calm/sw_flow get under-corrected by 30-38pp at 95-100. Justifies Stage 1 workup (regime-conditional Lc fit + halves-verified curated table + Stage 3 wire + 7-day flip gate). See `analysis/output/h_lc_regime_stage0.txt`.
- **Emergency demote (`cloud_saturation_correction.py`).** Same pattern as v0.6.382t chp emergency demote — bandage while Stage 1 builds. Added `_REGIME_SKIP` frozenset of 4 (field, regime, bin) tuples where pooled Lc over-corrects by ≥22pp for ne_flow: `cl/ne_flow/80-95` (live −61, regime −35), `cl/ne_flow/95-100` (live −58, regime −32 + HALVES-DIVERGE), `cc/ne_flow/50-80` (live −27, regime −3 — SKIP-mag verdict), `cc/ne_flow/80-95` (live −30, regime −8 — SKIP-Δ verdict). `_shift_for` extended to take `regime` and return `demoted=True` when the cell hits the skip set; `stamp_cloud_saturation_correction` reads `derived.state.regime_synoptic` at apply time and forces shift=0 for those cells. `per_field` telemetry gains a `cells_demoted` counter alongside `cells_fired`. Debug page + Fitter attribution untouched (demote reads as natural SKIP in the pair log's `error_l6` accumulator). Bandage lifts when Stage 1 curated table + apply-side regime lookup lands — the `_REGIME_SKIP` frozenset gets removed then.

</details>

<details>
<summary><strong>v0.6.389c • July 30, 2026 (digest registry — h_ws_blend_hours_sweep auto-relabeled STABLE)</strong></summary>

- **Analysis — `build_executive_summary.py` `KNOWN_LIVE_PIPELINES`.** Added `h_ws_blend_hours_sweep` entry pointing at `wind_blend.py:78` `BLEND_HOURS=4` (shipped v0.6.384 07-28). Script's daily `VERDICT: SHIP — BLEND_HOURS=4 clears gate` was surfacing under "New candidates (aggregate-only tools — cross-cut required before shipping)" in this morning's digest despite the constant already being live for 2 days. Registry entry relabels to `STABLE — wind_blend BLEND_HOURS constant already live since v0.6.384`. Caught during 07-30 morning digest review — same pattern as the 07-28 `l5_solar_analysis` backstop.

</details>

<details>
<summary><strong>v0.6.389b • July 29, 2026 (live-empty fossil guard — narrow-promote walker + Lc gate_clear stop reporting "GATE CLEARED" for empty SHIP sets)</strong></summary>

- **Analysis — narrow-promote walker (`build_executive_summary.py`).** The 4-gate walker (C1H_SHIP_CELLS, C1D_SHIP_CELLS, PRE_FRONTAL_SHIP_CELLS, H_L4_ADD_CANDIDATES) treats empty-vs-empty as a Jaccard match (line 1037-1038, deliberate — "consistent zero SHIP for N days is a legitimate stable state"). Downstream this rendered as `✓ GATE CLEARED (8/7 days) · 0 SHIP cells today`, which reads as ship-ready to a casual reader. Triggered a manual DECLINE on 07-26 when Claude noticed the mismatch. Fix: differentiate the two outcomes when count ≥ gate — `✓ GATE CLEARED (...) — ready to ship N cells` if `n_cells_today > 0`, else `⚫ STABLE-EMPTY (...) — nothing to ship`. Only PRE_FRONTAL_SHIP_CELLS and H_L4_ADD_CANDIDATES use `allow_empty=True` (C1H/C1D return `None` on empty and skip); both are now protected. See [[feedback_fossil_windows]].
- **Analysis — Lc gate_clear (`lc_fit.py:300`).** Same live-empty fossil pattern: `stable = len(cells_changed) == 0` returns True for both stable-non-empty and stable-empty windows. Fix: `gate_clear` now additionally requires `len(current_ship) > 0`. Vestigial for now since Lc is already ENABLED=True 07-17, but fixes for symmetry with the walker fix and to protect against future re-arming logic.
- **Sweep checked, NOT vulnerable:** `decay_tau_tuning.py` (short-circuits on `big_wins == 0` before streak logic), `build_executive_summary.py:698` SHIP-ELIGIBLE walker (bounded by promote-bucket entry; scripts already in promote have non-empty verdicts by construction), `divergence_report.py _streak_for` (only fires on DISAGREE; empty-vs-empty is AGREE and skips streak entirely).

</details>

<details>
<summary><strong>v0.6.389a • July 29, 2026 (debug page freshness sweep — v0.6.389 backfill + day counter cleanup + C1 Stage 4 status resync)</strong></summary>

- **Debug page — Rule 5 freshness sweep.** Sweeping `corrections_debug.html` against MEMORY and code state surfaced multiple stale sites where the same information was displayed with different day counts in different sections (a systemic problem — day counters get updated in some blocks during version bumps and not others). Fixed 6 sites plus one missing ship entry + one factually-wrong C1 note:
  - **Missing:** v0.6.389 pr L2 shadow-wire was absent from Recent Ships entirely (deployed 07-29, no debug page entry). Added a full PIPELINE bullet + bumped today's ship count.
  - **Factually wrong:** C1 Stage 4 line claimed "cm has cleared, cl now DEGRADED" — today's mixture check shows cm/0-5h [transition] b3 is still DEGRADED +42% (holding since 07-28), cl/6-11h [transition] b3 escalated +137→+217% one-day. Rewrote to reflect today's real state and the 07-29 REJECTION of the joint cl/cm correction hypothesis (cl has no live correction stack; cm corrections are stable improvers; drift is raw-HRRR-side and fitter absorbs via c1 confidence bands).
  - **Day counter drift:** clp Day 0/7 → Day 2/7 (2 sites), wdp Day 0/14 → Day 2/14 (1 site), chp Day 9/14 → Day 11/14 (1 site).
  - **wd L2 blend watch window:** was showing "Day 10/14 through 08-03" (original 07-20 ship). Watch was reset by v0.6.384 07-28 BLEND_HOURS 24→4 collateral fix — updated to "Day 2/14 through 08-11" with post-fix day-1 verify note.
- **Persistence-skill MIXED verdict for wd noted as FOSSIL** in the wd L2 blend watch line (referenced [[project_wd_l2_blend]]).

</details>

<details>
<summary><strong>v0.6.389 • July 29, 2026 (pr L2 shadow-wire — apply stays disabled but pair log now carries a measurable pr_l2 for regime × lead re-cut)</strong></summary>

- **Collector — pr L2 shadow-wire.** L2 additive bias for pressure was disabled 2026-07-01 (v0.6.276) on a pooled Production-vs-raw read of −2.4%. That decision predates skip-table architecture (v0.6.279), regime-gate-first discipline (formalized ~07-11), and the `l2_regime_lead_analysis.py` cross-cut machinery. A 2026-07-29 retro (`analysis/pr_l2_regime_lead_retro.py`, on pre-07-01 pair-log rows where `pr_l2 ≠ pr_l1`) finds the kill was regime-blind: **6 (regime × lead) cells win at n≥200** — sea_breeze/0-5h +26.7% (n=220), pre_frontal/0-5h +26.1% (n=233), calm/6-11h +14.2% (n=396), ne_flow/12-23h +9.2% (n=271), sea_breeze/12-23h +7.2% (n=467), ne_flow/24-47h +3.3% (n=270). Losses concentrated in westerly dry offshore flow (nw/sw/se) which dominated the pooled n. Physical story is consistent — L2 helps in onshore / marine / transition regimes where station consensus carries real signal, hurts where station consensus reflects terrain gradients not present at the Beverly grid point. This ship **does not re-enable L2**: `corrected_pressure_in ≡ raw_pressure_in` still, `pr_applied` stays `l1`. What changes: `corrected_hourly.py` now computes the L2-corrected pressure array (K=1, τ from `_load_l2_taus` guardrails) and stamps `corrected_pressure_in_post_l2` directly. `decay_apply.py`'s post-Layer-2 snapshot now preserves any pre-written `_post_l2` key rather than unconditionally overwriting with the live array — general shadow-key improvement, currently only pr uses it. Pair log will carry a real `pr_l2` distinct from `pr_l1` starting next tick, enabling a ~2-week fresh-data re-cut of the regime × lead analysis. Companion memory: `project_pr_l2_regime_gate_opportunity.md`. Shadow write is unconditional per [[feedback_persistence_gate_shadow_write]].

</details>

<details>
<summary><strong>v0.6.388b • July 29, 2026 (RIGHT NOW color-neutral + arrows, run_digest.sh classifier patch, day-1 wind_blend verify + Rule 5 sweep)</strong></summary>

- **Debug page — "Right now — what the pipeline is doing" table.** The Correction column no longer color-codes cells green/red based on sign. Elsewhere on the page green/yellow/red carry a good/neutral/bad meaning; in this table sign is direction, not quality (e.g. −4 pts cloud low is not "bad"). Rows now render neutral (default text color) and use ↑ / ↓ arrows in place of + / − to indicate direction. Single-function change in `renderHeadlineBox._fmtDelta` (corrections_debug.html).
- **Digest infra — `run_digest.sh` FAIL classifier.** 4 scripts marked FAIL(1) with empty tail on the 07-29 morning digest despite exiting 0 in re-run. Fallback grep at line 43 only recognized column-0 `VERDICT` / `Verdict` / `→` / `RESULT:` markers; scripts that emit indented verdicts + a non-zero exit path fell through to FAIL. Patched anchor to `^[[:space:]]*(...)` so indented verdicts still count.
- **Rule 5 sweep** — advanced day counters across post-ship watches (Lc 12→13/14, chp 10→11/14, wd L2 / ws L3 asym 9→10/14, wdp 0→2/14, Lsb 0→1/7, 07-28 ships 0→1/14 or 1/7), clp gate day 0→2/7, dp residual day 3→5/7. **ws narrative updated** in "Currently correcting" summary (line 899): pre-fix "+5.3% open regression" replaced with post-fix reality — day-1 mae_over_time read for wind_blend fix came in at ws Prod −2.5% vs raw (first negative day in 2 weeks). **wind_blend post-ship watch** (v0.6.384) updated with day-1 verify result. **Recent activity** — added 07-29 "today" entry (this ship + digest classifier patch + digest triage session), demoted 07-28 to "yesterday".

</details>

<details>
<summary><strong>v0.6.388a • July 28, 2026 (debug page sweep for the 4 post-reboot ships + h_dewpoint_depression_stability.py checked into analysis/)</strong></summary>

- **Debug page sweep** (Rule 5) for the 4 post-reboot ships (v0.6.385/386/387/388). Recent activity: "today" summary updated to 9 ships (was 5), 4 new bullets for post-reboot ships with DISCOVERY/PIPELINE badges. Post-ship watches: 4 new entries — wg L3 4-cell 14d, ws L3 2-cell 14d, dpbp 7d flip gate, wsbp 7d flip gate — all through 08-04 or 08-11. Calendar Tue 08-04 expanded from Lsb-only to four items (Lsb narrowed-gate flip, dpbp flip, wsbp flip, wg L3 24-47 re-cut on held cells) with pointers to preflight_dpbp / preflight_wsbp memories. Per-field sections: dp row now mentions dpbp Stage 3 wire; ws row updated with L3 SKIP extension + wsbp new specialist; wg row mentions v0.6.385 flat SKIP shipping (4 cells) plus 08-04 held-cell re-cut.
- **New analysis script** `analysis/h_dewpoint_depression_stability.py` (Stage 0b direction-stability probe used in the backlog #6 investigation) checked in. Companion to `h_dewpoint_depression.py`; splits pair-log window into 4 non-overlapping 8-day chunks + per-regime attribution classification; answers "does DP-DOMINANT classification hold across chunks or is the pooled verdict a lucky-mix?" Verdict from 07-28 run: all 4 regimes MIXED or UNSTABLE → per-day probe + antecedent probe unlocked the shippable design that became v0.6.387 dpbp.

</details>

<details>
<summary><strong>v0.6.388 • July 28, 2026 (ws bias-persistence gate — Stage 3 wired ENABLED=False; sibling of dpbp, second antecedent-error-based correction, ships calm regime only)</strong></summary>

- **Collector — new specialist `ws_bias_persistence.py`.** Second antecedent-error-based gate, cloned from v0.6.387's dp_bias_persistence architecture. Fires when previous-24h regime-mean ws bias (`forecast_l1 - observed`, from rolling 48h GCS state) is above +1.0 mph for the calm regime, subtracting `-min(prev_bias, 3.0)` from `hourly.wind_speed` at leads ≥ 6 (wind_blend already covers 0-3). Stage 0 antecedent probe: pooled ws lag-1 r=+0.470; per-regime calm +0.706 (strong), ne_flow +0.649 (strong), pre_frontal/nw_flow/sw_flow moderate 0.40-0.43. Stage 1 halves-verified: **only calm ships** (pooled +11.07%, halves A +13.35 / B +10.33, fires 38% consistently across pooled + both halves). ne_flow was Stage 1 SHIP by numbers (+10.91% pooled) but recent-half had 0 fires because ne_flow's over-forecast bias faded mid-window — the verdict rested entirely on the older half, so dropped from ship. Under-forecast regimes (nw_flow, pre_frontal, sw_flow) HURT the same correction — the antecedent pattern is only tractable when the model systematically OVER-forecasts (the pooled positive bias is a stable systematic error; pooled negative bias is intermittent event-driven, and a fixed antecedent over-corrects on quiet days). Correction is SIGN-INVERTED from prev-bias (subtract, not add) — architectural difference from dpbp which adds a fixed +2.0°F. New GCS state `ws_bias_antecedent_state.json` mirrors dpbp's rolling pattern. Shadow-write unconditional (`hourly.wind_speed_shadow_wsbp`). Preserve-before-mutate (`wind_speed_pre_wsbp`). Non-negative wind clamp applied. ENABLED=False; **7-day flip gate through 2026-08-04**. Runs after dpbp in the pipeline; also updated collector.py + descriptor loop.

</details>

<details>
<summary><strong>v0.6.387 • July 28, 2026 (dp bias-persistence gate — Stage 3 wired ENABLED=False; new specialist, first antecedent-error-based correction in the stack)</strong></summary>

- **Collector — new specialist `dp_bias_persistence.py`.** First correction in the stack that gates on an **antecedent-error** signal (previous 24 hours of `forecast_l1 - observed` dp bias per regime) rather than a current-state variable. Cleared backlog #6 attribution watch with rolling per-regime rolling-window walkforward: aggregate DP-DOMINANT verdict fails on 8-day chunks (all 3 candidate regimes MIXED or UNSTABLE per `h_dewpoint_depression_stability.py`), but the underlying signal is real (per-day dp under-forecast fires on 57-67% of days, driven by ~week-scale moist events like the 07-12 → 07-16 streak). Antecedent lag-1 Pearson r=+0.583 makes the persistence-of-error gate tractable. Stage 1 halves-verified across all 3 focus regimes at trig=−1.5°F / corr=+2.0°F / lead≥6h: pre_frontal +17.23% (A +21.59 / B +11.99), nw_flow +14.51% (A +15.64 / B +13.83), sw_flow +14.62% (A +6.05 / B +17.90). Pooled dp MAE 3.108°F → 2.808°F. Stage 2 sweep across {−1.0..−2.0} × {+1.0..+2.5} shows monotonic positive surface; conservative center of grid shipped. 0-5h leads DAMAGED by the fixed add (already close-to-obs via station_bias L2) — MIN_LEAD=6 hard-coded in the gate. New GCS state `dp_bias_antecedent_state.json` (rolling 48h, ~50KB) is updated each tick with the current-hour (fc_l1 - obs, regime) sample; specialist reads prev-24h aggregate per regime on the next tick. Bootstrap: first ~24h post-deploy the state is warming and the gate stays silent. Shadow-write invariant honored (`corrected_dew_point_shadow_dpbp` unconditional per [[feedback_persistence_gate_shadow_write]] — wdp and clp were both bit by ENABLED-gated shadow arrays leaving the 7-day gate blind). Preserve-before-mutate honored (`corrected_dew_point_pre_dpbp`). ENABLED=False; **7-day live-layer flip gate through 2026-08-04**. Runs after `dp_residual_persistence` in the pipeline (dprp itself ENABLED=False, so passthrough today). Also updated `weather_collector/collector.py` to wire the stamp + descriptor.

</details>

<details>
<summary><strong>v0.6.386 • July 28, 2026 (ws L3 SKIP_TABLE — 2 long-lead transition cells added)</strong></summary>

- **Collector — `decay_apply.py` `SKIP_TABLE[("ws", "l3")]` extended with 2 cells.** ws L3 skip-table Stage 1 re-cut on fresh windows (06-28 → 07-28) surfaces two clean-halves SKIP cells at long leads in transition regimes: `frontal 24-47` (+5.8%, n=987, halves +4.7/+9.4) and `pre_frontal 24-47` (+8.0%, n=9268, halves +3.4/+11.6). Notable: **all 8 unshipped 07-14 Stage 1 SKIP cells (calm all bands, nw_flow 24-47, sea_breeze 6-11+24-47, unknown 6-11+12-23+24-47) have vanished from the SKIP set on fresh data** — best explanation is that the v0.6.370 ws L3 asymmetric SKIP table (26 fc-bin cells) already covers most of that damage; what Stage 1 measures now is residual L3 damage AFTER asymmetric SKIP has done its work. Existing 2 entries (`ne_flow 0-48`, `sea_breeze 0-12`) left in place — they may be partially stale (fresh data shows `ne_flow 24-47: −5.45%` L3 actively HELPS) but SKIP is fail-safe: removing L3 where it might help is a small opportunity cost, not damage. Analysis window updated in `h_ws_l3_regression_stage1.py`.

</details>

<details>
<summary><strong>v0.6.385 • July 28, 2026 (wg L3 SKIP_TABLE — 4 clean-halves cells wired)</strong></summary>

- **Collector — `decay_apply.py` `SKIP_TABLE[("wg", "l3")]` added with 4 cells.** wg L3 skip-table Stage 1 re-cut on fresh windows (06-28 → 07-28) confirms 6 halves-verified SKIP cells; shipping the 4 with clean halves-stability, holding the 2 with wide halves-spread (calm 24-47 and sea_breeze 24-47 both show A=+7% vs B=+50% — recent-half signal fading — held for another 7-day re-cut). Shipped cells: `calm 0-5` (+9.4%, halves +5.3/+10.0), `calm 12-23` (+40.0%, halves +44.3/+39.4), `ne_flow 6-11` (+11.8%, halves +6.2/+12.7), `sea_breeze 6-11` (+5.6%, halves +8.0/+4.8). Composition partially shifted from the 07-14 Stage 1 verdict: calm 6-11 fell to THIN (n=156), sea_breeze 0-5 fell to MARGIN, unknown 24-47 reclassified to PERSISTENCE_TERRITORY; new arrivals ne_flow 6-11 and sea_breeze 6-11 both cleanly halves-verified. Original 07-14 ship gate long past (07-21 target). Analysis window updated in `h_wg_l3_regression_stage1.py` (2-week slide forward). Fail-safe unchanged: any lookup miss → apply normally, so L3 stays ON wherever the table doesn't say OFF.

</details>

<details>
<summary><strong>v0.6.384 • July 28, 2026 (wind_blend BLEND_HOURS 24 → 4 — kills ws +30% Prod-vs-Raw regression)</strong></summary>

- **Collector — `wind_blend.py:78` `BLEND_HOURS` shrunk from 24 → 4.** Root-cause fix for the ws +30.5% WORSE-than-raw production regression that has been running for 2 weeks (positive every day, ≥+20% worse for 4 days consecutive). Discovered via `mae_over_time.json` cross-cut (per-field Prod-vs-Raw) then confirmed via `time_series_diagnostic.json` per-lead: L2 wins at lead 1 (−21% vs raw 2.01) but catastrophically loses at leads 3-16 (+40% to +85%). L3 was bit-identical to L2 (the shipped SKIP additive infrastructure was attacking the wrong layer). Physical read: observed current wind at KBVY has more variance than the next-few-hour average wind — bleeding a point-in-time observation into a 24h horizon imports gustiness/turbulence/calm-variable noise onto a smoothed model signal. New `analysis/h_ws_blend_hours_sweep.py` sweeps {1, 2, 3, 4, 6, 8, 12, 24} on 7-day window; back-solves observed_current per run from low-lead L1/L2 pair, simulates alternative BLEND_HOURS per lead, halves-stability check. Result: **BLEND_HOURS=4 wins at +14.72% pooled MAE improvement, halves +8.4% / +22.4% (both positive), every lead-band improves** (0-5 +23%, 6-11 +43%, 12-23 +13%, 24-47 +0%). One-constant edit, no config file. Preserves the lead-1 win, kills the lead-3-onward drag. **Skipping the pre-flip 7-day gate** because (a) sweep used a 7-day window with halves-stability already checked, (b) halves are both positive, (c) current production actively hurts ws by 30% every day — the cost of another week under the broken shape outweighs additional gate reads. **14-day post-ship watch** replaces the pre-flip gate: any of the 4 lead-bands regressing worse than v0.6.384 baseline once n ≥ 100 per band; overall ws MAE drifting back above raw. Collector deployed same commit.

</details>

<details>
<summary><strong>v0.6.383c • July 28, 2026 (debug page sweep for today's 3 ships)</strong></summary>

- **Debug page — post-ship Rule 5 sweep for v0.6.383, 383a, 383b.** Recent activity: today's 07-28 header split into "today" + yesterday roll-back to "07-27"; four new day-entry bullets for the 3 ships plus the Lsb-narrowing narrative (DISCOVERY / DISCOVERY / DASHBOARD / INFRA badge mix). sr section (line ~1533, Engineering status): Lsb narrative rewritten from HOLD/HELD language to the narrowed-gate PROMOTE story — cc gate simplified in prose to `cc < 25`, "overcast half retired" callout with the −17.6% regression and physical reason, 07-28 pooled +31.5%/halves +43.8%/+22.7% results, fresh 7-day gate through 08-04, shortwave shadow-log infrastructure preserved. sr row in RIGHT NOW pipeline table (line ~882) mirrored to the same narrowed-gate wording. Post-ship watches: new Lsb 7-day flip gate entry (day 0/7 through 08-04) inserted right after wdp. Calendar: new "Tue 08-04" entry for the Lsb narrowed-gate flip check. No changes to day-counters (already auto-refreshed by prior touch) or the R&D active-candidate count (dp attribution finding lives in backlog, not R&D list).

</details>

<details>
<summary><strong>v0.6.383b • July 28, 2026 (Lsb gate narrowed — overcast half retired, clear-sky half PROMOTES)</strong></summary>

- **Collector + analysis — Lsb (sr sea_breeze cc-gated Lsr override) gate narrowed from `(cc < 25) OR (cc >= 75)` → `cc < 25` only.** 07-28 halves re-run of the original two-sided gate went MARGINAL on both Stage 1 (pooled +16.75% but halves 1/2) and Stage 2 (pooled clean but 75-100 cc-bin regressed −17.6% halves +6%/−23%, and 12-23h + 6-11h lead-bands SKIP). Root cause was the overcast half of the physical hypothesis ("model misses thick attenuation in cc≥75") — data says model attenuation is actually fine or over-corrected, so the intervention hurt on that half and dragged pooled numbers down. Clear-sky half (0-25 cc-bin) held robustly: pooled +35.8%, halves +33%/+40%, n=969. Retired the overcast branch; kept the clear-sky branch. `analysis/sr_sea_breeze_lsr_refit_stage2.py` — `CC_HI` removed, `cc_gated()` simplified to `cc < CC_LO`, docstring rewritten with the narrowing rationale, output JSON schema simplified (`cc_gate.rule` replaces `cc_gate.hi`). `weather_collector/processors/sr_sea_breeze_lsr_override.py` — `_CC_HI` removed from module state and `_load_curated()` fallback signature, `_cc_gated()` simplified, `describe_applicability()` and telemetry `note` updated for the narrowed shape. `ENABLED=False` held (fresh 7-day gate 07-28 → 08-04 on the narrowed shape — no live-layer flip on same-day re-derivation per gate discipline). Shortwave shadow-log infrastructure stays alive; underpins future sr L2 work once unit mismatch resolves (see project_sr_unit_mismatch). Re-run of Stage 2 with narrowed gate: **PROMOTE — pooled +31.50%, halves +43.78%/+22.69% (both above +10% ship gate), 4/4 lead-bands SHIP.** Hour 13 remains an outlier (−43% on n=145, halves −160%/+24%, small-sample fit instability) but the pooled/lead-band metrics dominate and net is strongly positive.

</details>

<details>
<summary><strong>v0.6.383a • July 28, 2026 (h_dewpoint_depression — t/dp attribution extension)</strong></summary>

- **Analysis — extend `h_dewpoint_depression.py` with per-regime t-bias + dp-bias attribution split.** Clears the 2026-06-24 promotion-gate blocker on `project_hypothesis_backlog` #6 that has been sitting for 5 weeks ("Promote when t/dp attribution is clear AND signal holds"). Depression bias = t_bias − dp_bias by construction, so the new attribution table classifies each regime as T-DOMINANT / DP-DOMINANT / BOTH-COMPOUND / BOTH-CANCEL / NOISE. Reader rule from docstring: dp-side correction candidates only ship on DP-DOMINANT regimes; T-DOMINANT would just mask t-bias. First real read: **3 DP-DOMINANT ★-magnitude regimes** with a consistent ~−2°F dp under-forecast — pre_frontal (t +0.54, dp −2.14, n=19,621), nw_flow (t +0.27, dp −2.20, n=45,589), sw_flow (t −0.49, dp −2.34, n=20,034). Total n across DP-DOMINANT ★ regimes = 85k. Frontal is BOTH-COMPOUND (t +1.47, dp −1.63) — model imagines warmer/drier post-frontal airmass than shows up. sea_breeze / ne_flow / se_flow all BOTH-CANCEL (t and dp both under-forecast similar amounts, depression bias small). Physical read: model systematically under-predicts moisture (dp too low) in shear/turbulent-mixing regimes. Promotion still gated on direction-stability check per project_hypothesis_backlog #6 07-28 update — this is one read, need 2-3 weekly re-runs before Stage 1 wire. Script now emits `VERDICT: DP-DOMINANT ★-magnitude regimes eligible for dp-correction Stage 1 workup: pre_frontal, nw_flow, sw_flow.` so tomorrow's digest picks up the classification as a verdict line.

</details>

<details>
<summary><strong>v0.6.383 • July 28, 2026 (digest hygiene — sr L2 false-positive suppression + l5_solar registry)</strong></summary>

- **Analysis — sr L2 candidate re-surfaced in digest → analysis scripts patched to suppress.** Tuesday-morning digest triage rediscovered the same sr L2 ship candidate that got investigated and re-scoped 2026-07-06 (see [[project_sr_unit_mismatch]]). `l2_lead_decay_fit.py` recommended sr τ=120h (+4.5% MAE held-out); `l2_regime_lead_analysis.py` running stale τ=24h proposed a skip-table; `h_full_regime_sweep.py` surfaced 9 sr-L2 ADD candidates. Verified sr has **no L2 wired in production** — `station_bias.py` covers only t/h/pr, `DEFAULT_L2_TAUS` has t/h/pr only, `direct_radiation_post_l2` array has no writer, pair-log spot check (20k rows) shows `forecast_l2 == forecast_l1` bit-identical for sr. The +4.5% signal is fitting the direct-vs-shortwave unit gap (model `direct_radiation` vs Tempest `solar_wm2` total shortwave), not real station-consensus hyperlocal signal. Naive L2 wiring would re-encode the unit gap into a new correction layer — exactly the trap Lsr's old regime bias fell into pre-2026-07-06. Two script patches to prevent re-triage next session: (1) `analysis/l2_regime_lead_analysis.py` — TAU_H 24 → 120 (from `l2_lead_decay_fit.py` current recommendation), docstring rewritten with ⚠ blocker header, verdict emit line now reads "⚠ DO NOT SHIP: blocked by unit mismatch (see project_sr_unit_mismatch)" instead of "Safe to wire into l2_decay.json." Re-cut at τ=120h confirmed 0 losses (2 WIN, 30 flat) — clean at the numeric level but blocked at the semantic level. (2) `analysis/h_full_regime_sweep.py` — 5-line filter in `emit()` add-candidate branch suppresses sr L2 ADD candidates with comment pointing at project_sr_unit_mismatch. Rollup went `21 SKIP + 10 ADD` → `21 SKIP + 1 ADD` (remaining ADD is sr/L4/pre_frontal 6-11h — legit L4-level signal, not unit-mismatch contaminated). Do not re-open sr L2 as a candidate until the Lsb (`sr_sea_breeze_lsr_override.py`) shortwave-refit chain resolves.
- **Analysis — `l5_solar_analysis` false-positive → registry backstop.** `build_executive_summary.py` `KNOWN_LIVE_PIPELINES` gained an entry for `l5_solar_analysis`. Script has been emitting "VERDICT: SHIP — flip solar_correction.ENABLED = True" every daily digest, but `solar_correction.py:46` has `ENABLED = True` since v0.6.248 (2026-06-28). Same class of registry gap as the v0.6.376 backstops shipped 07-23 (see [[project_already_live_backstops]]). Tomorrow's digest will auto-relabel this script's verdict to STABLE instead of surfacing it as SHIP-eligible. Verified with local `relabel_stable_recheck()` call.

</details>

<details>
<summary><strong>v0.6.382u • July 27, 2026 (debug page sweep)</strong></summary>

- **Debug page sweep** for v0.6.382q–t evening ships. Calendar Wed 07-28 chp mid-lead re-check → RESOLVED (ad-hoc script pre-built + ran + demote applied same evening). Post-ship-watches ch persistence gate + per-field-snapshot ch row + Still-open-watches ch persistence gate + Persistence-skill narrative + pipeline stack `chp` bullet all refreshed for 14 SHIP / 8 MARGIN / 13 SKIP / 2 THIN rollup and the emergency-demote history. What's-improving gains two new cards: pp frontal × 6-11h Platt (Stage 1 SHIP, wire earliest ~08-03) + chp full-shape refinement (5-cell L6-baseline SHIP set adoption, day 1/7 gate). Active-candidate count 8 → 10. pp per-field snapshot row updated to reflect first shippable pp correction found (no longer "no open work"). Recent activity day-header captures all four evenings.

</details>

<details>
<summary><strong>v0.6.382t • July 27, 2026 (emergency demote)</strong></summary>

- **Collector — chp emergency demote of 6 clear-regression cells.** Same-evening surgical response to the L6-baseline finding from v0.6.382s. Six cells materially regressing ch vs Lc alone (all n≥100 in the 10-day post-Lc window, both halves worse than Lc, Δ ≥ +28% MAE) flipped SHIP/MARGIN → SKIP in `weather_collector/data/ch_persistence_gate_curated.json`: `sw_flow/24-47` (+59%), `sw_flow/12-23` (+38%), `sea_breeze/24-47` (+37%), `pre_frontal/24-47` (+32%), `se_flow/6-11` (+29%), `ne_flow/12-23` (+28%). These cells now fall back to Lc-corrected ch instead of firing chp. Chp rollup: was 19 SHIP / 9 MARGIN / 7 SKIP / 2 THIN → now 14 SHIP / 8 MARGIN / 13 SKIP / 2 THIN. `emergency_demotes` block appended to the curated JSON for audit trail. **Full-shape adoption of the 5-cell L6-baseline SHIP set** (which would additionally demote 5 more halves-disagreement/small-magnitude cells) **still under the normal 7-day live-layer change gate** — this ship targets only the unambiguous regressions. Not touching the shipped Stage 2 script (h_ch_persistence_blend_stage2.py stays authoritative until the full-shape decision).

</details>

<details>
<summary><strong>v0.6.382s • July 27, 2026 (evening 3)</strong></summary>

- **Analysis — chp Stage 2 REBUILT vs `forecast_l6` baseline. Honest SHIP set collapses 28 live cells → 5 real cells + 3 by-design-frontal artifacts.** Follow-through on the evening-2 ESCALATE finding from `h_chp_midlead_regression.py`. New `analysis/h_ch_persistence_blend_stage2_vs_l6.py` (fork of shipped Stage 2 — original stays authoritative and untouched). Uses `forecast_l6` (Lc-corrected L4) as baseline instead of `forecast_l4`; post-Lc-flip window only (07-17 → 07-27, 10 days); MIN_N_CELL relaxed 200 → 100. **Real SHIP under L6**: calm/0-5 (−70%), pre_frontal/0-5 (−41%), sw_flow/0-5 (−30%), se_flow/0-5 (−26%), ne_flow/6-11 (−17%). **11 live cells flip → SKIP** (chp materially loses vs Lc, worst sw_flow/24-47 +59%, sea_breeze/24-47 +37%, pre_frontal/24-47 +32%). 6 live cells go THIN in the 10-day window. Pattern: chp's real value is 0-5h short-lead across 4 regimes + ne_flow/6-11 — an 8x tighter footprint than currently live. Preview written to `weather_collector/data/ch_persistence_gate_curated_vs_l6.json`; **live curated JSON UNTOUCHED**. Ship path: 7-day live-layer change gate confirming this shape + Joe's approval. Same class of bug as [[project_cc_sat_correction]] 07-20 kill.
- **Analysis — pp frontal × 6-11h Stage 1 → SHIP. First shippable pp correction found.** Follow-through on the evening-2 frontal MARGINAL_DRIFT finding from `h_pp_platt_by_regime.py`. New `analysis/h_pp_frontal_platt_stage1.py` tests four variants inside frontal-only population: pooled free, pooled fixed b=0.6 (per pooled slope-stability finding), per-band free, per-band fixed b=0.6. Fixing b=0.6 closes the drift the free fit couldn't (recalibration SHAPE is stationary, LEVEL drifts with base rate). **`band_6-11_fix` hits SHIP**: Brier lift −28.56% / −18.73%, |Δa|=0.20 (well inside 0.5 gate), n=292. Ceiling from evening-1 (~5% Reliability pooled) doesn't apply here because frontal-6-11h subpopulation has a fundamentally different (more consistently under-forecasting) calibration than pooled. **Design that Stage 3 would wire**: apply `σ(a_t + 0.6·logit(raw))` only when `state_fc.regime_synoptic == "frontal" AND lead_h ∈ [6, 11]`; refit `a_t` on rolling 30-day frontal-6-11h window (Fitter cadence). **Stage 2 next**: walk-forward evaluation to confirm halves-SHIP wasn't window-lucky. n=292 is tight; want 3-5 more frontal passages before wiring.
- **Debug page — pp Brier reliability panel subheader + Recent activity refreshed for both findings.**

</details>

<details>
<summary><strong>v0.6.382r • July 27, 2026 (evening — extended session)</strong></summary>

- **Collector — `pirate_l1_log.json` per-tick logging shipped.** New processor `weather_collector/processors/pirate_l1_log.py` cloned from `forecast_spread_log.py` template; extended `fetchers/pirate_weather.py` to extract `hourly_precip_probability` (previously fetched implicitly but unused); wired into `collector.py` right after the GFS spread snapshot. 14-day retention on GCS. Follow-through on the v0.6.382q source-blend HOLD: HRRR + GFS pp are near-collinear at 0-48h because both post-process from the same NCEP soup; Pirate (IBM/DarkSky-adjacent) is a genuinely independent model layer. Data starts accruing next collector tick; earliest 3-source pp blend re-test 2026-08-10 (14-day retention window fill).
- **Analysis — `h_chp_midlead_regression.py` pre-built for 07-28 Calendar; already fires ESCALATE against live data.** Ad-hoc per-lead chp-vs-forecast_l6 MAE script pre-built ahead of tomorrow's conditional trigger (aggregate persistence-skill Δ moves outside [−1.2, −0.7]). Ran against current pair log: Lc alone beats chp at every 6-20h lead (n=176-186 per lead). Six leads (10-15h) exceed the escalation trigger; peak lead 12 = +30.1% (chp MAE 16.37 vs L6 MAE 12.59). The aggregate Δ ≈ −1.03 was masking the mid-lead regression because chp still wins big at 1-5h — pooled hides the shape. Per project_chp_midlead_regression_watch escalation playbook: rebuild `h_ch_persistence_blend_stage2.py` with `forecast_l6` as baseline instead of `forecast_l4`; re-derive SHIP/SKIP per (regime × lead_band); demote cells that flip. **Not executed tonight** — Joe's call whether to escalate now vs wait for tomorrow's digest confirmation.
- **Analysis — `h_pp_platt_by_regime.py` Stage 0 HOLD; frontal is the one positive sub-signal.** Regime-conditional Platt fits inside each `state_fc.regime_synoptic` bucket (booked in project_pp_recalibration_session for "when Reliability-attack candidates get revisited, focus on making the intercept robust to base-rate shifts"). Aggregate weighted-by-n WORSE by +21% / +25% — pooled non-stationarity was different miscalibration signs across regimes canceling out. **Frontal MARGINAL_DRIFT** (both halves improve Brier −15.49% / −15.60%; well above 5% ship gate; |Δa|=0.66 exceeds 0.5 stability gate → drift-classified). Every other regime gets worse with recalibration. Calm blew up numerically (b → 2726; likely zero rainy hours in one half, ridge-damping doesn't rescue class-imbalance). Design seed for a frontal-only pp recalibration.
- **Debug page — pp Brier reliability panel subheader now names all 5 Stage 0 candidates** + the frontal sub-finding; Recent activity Mon 07-27 gets three new evening-2 bullets.

</details>

<details>
<summary><strong>v0.6.382q • July 27, 2026 (evening)</strong></summary>

- **Collector — clp 7-day flip gate EXTENDED 07-31 → 08-03.** Follow-through on v0.6.382p (PM): the shadow-write bug fix produced its first real clp shadow data starting today's next collector tick, but only 4 daily reads would exist between fix-deploy and the scheduled 07-31 close. Extended to 08-03 for a full 7 daily reads of newly-valid data. Updated `cl_persistence_gate.py` ENABLED-line comment; refreshed 4 debug-page sites (per-field snapshot, What's-improving card, stack-status pointer, persistence-skill narrative) + JS SPECIALIST_STACK comment; added Calendar 08-03 line; synced TODO + cl-persistence-investigation memory.
- **Collector — `persistence_gate_base.py` helper module extracted.** New `weather_collector/processors/persistence_gate_base.py` factoring out the boilerplate shared by chp / clp / wdp (LEAD_BANDS, table load/cache, applicability descriptor, telemetry envelope, gate_firing_log, and — critically — the unconditional shadow-write from v0.6.382p). `SpecialistSpec` dataclass + `run_specialist(spec, weather_data)` handles both concrete shapes: `post_obs_bypass_context` for chp / clp (regime = state_curr, same all leads); `predicted_transition_context_factory(fc_regime_for_lead_fn)` for wdp (fc_regime per-lead, fires only on predicted transition). Shadow-write invariant is baked in — future clones cannot regress the v0.6.382p bug. chp / clp / wdp NOT migrated today (mid-watch on all three; no-churn rule); helper is documented for the next specialist (wgp / dpp / ...) as a one-liner registration. Refactor of the three existing specialists is booked as follow-up once their post-ship watches close.
- **Analysis — `h_pp_source_blend.py` Stage 0 HOLD. GFS pp is non-informative given HRRR pp at 0-48h.** Booked from PM pp recalibration session as the attack-Resolution-term candidate (after three attack-Reliability-term candidates all HOLD'd against a Reliability component that's only ~5% of total Brier). Two blend forms: (1) weighted α · HRRR + (1−α) · GFS via golden-section search over α ∈ [0, 1] — half A picked α=0.89, half B picked α=1.00, Brier Δ = 0.00% both halves; (2) logistic σ(a + b_H · logit(H) + b_G · logit(G)) via Newton (with ridge damping added after the un-ridged fit blew up on collinear features — same class as PM's Kalman-Newton hang trap). Ridge-stabilized read: half A→B −2.94% (below 5% ship gate), half B→A pathological. Overall HOLD. Physical finding: HRRR and GFS pp are near-collinear at the 0-48h horizon — both models post-process from the same NCEP soup and share recent-obs assimilation. Follow-up would need historical Pirate pp logging (Pirate is fetched live per tick but not written to a rolling log) — separate ship task. Provisional stance: pp = L1-only is the physics floor absent new signal. 23,232 pair-log rows joined across 07-13 → 07-27 (14-day GFS log retention window); 119k pair-log pp rows outside the GFS-log time window unjoined. Debug page pp Brier reliability panel subheader now names all four Stage 0 candidates + verdicts.

</details>

<details>
<summary><strong>v0.6.382p • July 27, 2026</strong></summary>

- **Collector — persistence-gate specialists now write unconditional shadow arrays (fixes wdp shadow-week invisibility + clp flip-gate blindness).** Structural bug in the wdp/clp/chp template: all three modules gated ALL hourly-array writes behind `if ENABLED and persist_val is not None:`, so during Stage 3 ENABLED=False the shadow "would apply" values only landed in the per-tick telemetry blob `weather_data["<specname>_persistence_gate"]` — which gets overwritten every collector tick and never reaches the snapshot writer or pair log. Consequence: the entire 07-20 → 07-27 wdp shadow week produced ZERO pair-log-visible data (0 of 145k wd rows have `forecast_wdp`); today's wdp flip was made based on Stage 2 preview + preflight drift verification only, not Stage 3 shadow verification. Same bug in clp today: 7-day flip gate through 07-31 evaluating against zero real shadow data (7,704 of 145k cl rows have `forecast_clp`, but every one is byte-identical to `forecast_l6` — snapshot fallback duplicates, not real shadow rows). chp had the same bug but ENABLED=True since 07-19 masks it. **Fix**: `wd_persistence_gate.py`, `cl_persistence_gate.py`, `ch_persistence_gate.py` now write `hourly[HOURLY_KEY + "_shadow_<name>"]` unconditionally with the would-apply values (persist_val on fire cells, arr[i] on skips). ENABLED=True path additionally does the in-place `hourly[HOURLY_KEY]` overwrite as before (reusing the same shadow array — shadow == live in the ENABLED case). `forecast_snapshot.py` slots for chp/clp/wdp now prefer the shadow key over the live-array fallback so shadow-week rows carry distinct forecast values. No behavior change for currently-live specialists (chp / wdp — shadow == live); real behavior fix for clp (its flip-gate evaluation window through 07-31 now starts producing real forecast_clp ≠ forecast_l6 rows from next collector tick forward). Also written: `feedback_persistence_gate_shadow_write` — preflight-style memory so future persistence-gate specialists (wgp / dpp / etc. clone-of-template) don't inherit the bug. Verification recipe added: grep pair-log for rows where `forecast_<specname> != forecast_l4` (or immediate-upstream layer) one tick after deploy; zero survivors = broken. Class family: [[feedback_streak_infra_dormancy]] + [[feedback_stated_intent_vs_code_behavior]] (module docstrings said "still stamps telemetry when ENABLED=False" — technically true but misleading, telemetry blob is not a consumer surface).

</details>

<details>
<summary><strong>v0.6.382o • July 27, 2026</strong></summary>

- **Debug page — D1 Drill-down retired.** User confirmed they never looked at it. Rather than keep a scope-restricted (t/h/dp only) version of a section nobody uses, cut it. Removed: `<details id="sec-drill">` HTML block, `.drill-controls` + `.drill-chart-wrap` CSS (~35 lines), `DRILL_LAYERS` / `_drillCharts` / `_drillState` state, `_drillRender` + `_drillSetupControls` renderers (~150 lines JS), main-flow init call. **Kept:** `_drillComputeSeries` — the per-field L1/L2/L3/L4 series compute function is still consumed by the L2 raw-model curves section, so it stays with an updated docstring noting the back-out is dishonest for fields with specialists / skip tables (that section only reads .l2 for fields where it's still faithful anyway). Updated two lingering references: L1 raw-model section's caption ("dotted line that appears in the drill-down above" → just "raw model forecast per field"); regime-classifier note in Lsr section ("Production Stack box, drill-down D1, R2, R6" → "Production Stack box, R2"). Net ~190 lines removed.

</details>

<details>
<summary><strong>v0.6.382n • July 27, 2026</strong></summary>

- **R0 extended from L3/L4 audit to full per-layer + specialist audit.** Fitter already emits `per_layer_mae_by_lead[field]` with `l5` (Lsr), `l6` (Lc), `chp`, `clp`, `wdp`, and a real `production` bucket (`decay_fit.py:1174-1207`) — R0 just wasn't reading it. Renderer now adds two columns: **Specialists** (chained per-field per SPECIALIST_STACK map: Lsr→sr, Lc→cc/cl/cm/ch, chp→ch, clp→cl [Stage 3 off], wdp→wd; each rung's Δ compares to the previous rung, not to L4) and **Production** (real per-row MAE aggregated from applied_layer stamps). ⚠ banner rule extended to specialists: enabled specialist losing to prev-rung by >3% in any band fires suspect; disabled specialist that would win by >3% fires missed (doubles as a post-ship-watch signal for Stage 3 wired ENABLED=False candidates). Section title renamed R0. Per-layer audit (was "L3/L4 audit" — stale by 3 months). Purpose shift: R0 was originally a promotion gate for L3_FIELDS / L4_FIELDS (superseded by Stage 3 curated JSON + 7-day flip gate); the extension gives it a new job as post-ship-watch dashboard where one glance shows whether each live specialist is still beating its layer-below. Second win: independent defense-in-depth against feedback_streak_infra_dormancy-class failures (a specialist gate becoming stale but still computing). Lt for `t` intentionally omitted from SPECIALIST_STACK — the correction returns 0.0 (telemetry experiment only per v0.6.382i reclassification). SPECIALIST_STACK is a hardcoded map for now; when a specialist's enabled state changes (Stage 3 flip → live), search for SPECIALIST_STACK in the file and flip its `enabled` bit. No backend changes.

</details>

<details>
<summary><strong>v0.6.382m • July 27, 2026</strong></summary>

- **Debug page — D1 Drill-down scope-restricted to t/h/dp.** D1's model (raw → +L2 → +L3 → +L4) is stale: the shipped `weather_data.json` values now include Lc (07-17), chp (07-19), wdp (07-27), Lsr, and per-field skip tables (ws hardcode + asymmetric, wg asymmetric, L3 skips). D1 reconstructs L3 and L2 by *reverse-subtracting* diurnal + decay from the final shipped value, so on fields that carry specialist corrections beyond L4 the reconstructed "L2" and "L3" lines silently include Lc/chp/wdp on top of them — mislabeled hybrids, not real L2 or real L3. On fields with skip tables, D1 also draws a phantom L3 correction on cells that L3 actually skipped. The teaching value went negative because a user learning from D1 today gets the wrong mental model. Fix: `_drillSetupControls` filters the field checklist to `{t, h, dp}` — the three fields where the back-out is still faithful (no specialist, no skip table beyond L2). Summary line updated to explain the scope and point users to per-field sections for the specialist fields. Full-stack drill-down that walks pair-log `applied_layer` stamps queued as a rewrite; kept simple option (c) rather than retiring D1 outright because the L1→L2→L3→L4 story IS still how t/h/dp work and the teaching hook is genuinely useful there.

</details>

<details>
<summary><strong>v0.6.382l • July 27, 2026</strong></summary>

- **pp Platt (logistic) recalibration halves test — HOLD, but discovery: the miscalibration shape is stationary, only the level drifts.** New `analysis/h_pp_platt_calibration.py` (Stage 0 corrective test #2 after bin-lift came back HOLD). Fits `calibrated_p = σ(a + b · logit(raw_p))` via Newton-Raphson on binary log-loss, halves the pair log, applies each half's fit to the other, ships to GCS as `h_pp_platt_calibration.json`. First-run: **halves diverge on Brier (+6.56% / +10.45% — both WORSE held-out)** so verdict is HOLD, but the fit-parameter breakdown is diagnostic: **slope b is stable across halves (0.628 vs 0.569, |Δb|=0.06) while intercept a drifts massively (+0.107 vs −0.818, |Δa|=0.93)**. That means raw HRRR pp miscalibration is separable — the SHAPE (overconfidence at extremes, underconfidence in middle bins) is a stationary invariant of the model; the LEVEL just tracks whatever the recent base rate happens to be. Neither pooled bin-lift nor static Platt can ever ship pooled, but a two-component recalibration — b fitted offline from a long window, a floating on a Kalman-style rolling recent-obs-vs-pred window — should. Same infrastructure pattern L2 already uses for the mesonet bias fields. That's now the next Stage 1 candidate for pp (`pp_kalman_recalibrate.py`, not yet scaffolded). The Platt halves-test stays in the digest as an early-warning: if b ever drifts more than ±0.15 across halves we'll know the stationarity assumption broke and re-open the shape question.

</details>

<details>
<summary><strong>v0.6.382k • July 27, 2026</strong></summary>

- **pp Brier reliability + halves-mode calibration — verdict machinery, GCS publish, debug page surface; first-run outcome: HOLD (do not ship).** Closes the 07-21 measurement-gap loop that had left `pp_brier_reliability.py` running descriptively in the digest for 6 days with no promotion track. Three pieces. (1) **pp_brier_reliability.py rewired**: removed the retracted "rendering bug" section (Production=L1 for pp is by-design since L3 pp was dropped 07-04, not a bug per [[project_pp_brier_reliability]] retraction); added a proper `VERDICT:` line that emits either `STAGE0_OPEN pp_bin_lift_calibration` (with weighted bias + worst-bin gap) or `CLEAN`; added GCS upload → `data.wymancove.com/pp_brier_reliability.json`. The Stage 0 trigger fires on either high weighted bias OR a large gap (≥15pp) in a well-populated bin (n≥500) — the 0-10 bin holds ~80% of pp rows and is near-perfectly calibrated, so weighted-mean-only would suppress a real mid-range signal like bin 30-40 at −28.7pp on n=1,422. (2) **New `analysis/h_pp_bin_calibration.py`** — halves-mode Stage 0 corrective test. Sorts pair-log rows by obs_time, splits 50/50, fits per-decile lift table on each half (obs_freq − pred_freq), applies to the other half's raw fc, scores Brier vs raw baseline. Ship gate: both halves improve Brier ≥5% AND ≥7 of 10 bins agree in sign. GCS-published as `h_pp_bin_calibration.json`. (3) **Debug page surface** — new collapsible block right after per-field snapshot table shows today's raw reliability table + halves test verdict with color-coded gap coloring (green <5pp, amber 5-15pp, red >15pp). Renderer `renderPpBrierReliability` fetches both JSONs; header pill shows STAGE0_OPEN/CLEAN state + worst-bin gap at a glance.
- **First-run finding — HOLD, do not ship**. Reliability decomposition confirms the aggregate signal: raw HRRR pp under-forecasts (weighted bias −3.54pp; bin 30-40 predicted 34.5% → observed 63.2%, gap −28.7pp on n=1,422). But the halves test flunks: both halves get WORSE Brier when the other half's lift table is applied held-out (+6.46% and +0.87%; 8/10 bin-signs agree but magnitudes are unstable — 40-50 flips +25.5pp → −5.6pp, 70-80 flips +4.4pp → −45.2pp). Root cause visible in the halves raw Brier: half A raw = 0.103, half B raw = 0.031 — half B was a ~3× drier window. The pooled bias is real but non-stationary; the lift you fit last month makes this month's Brier worse. Same failure class as the L3-for-pp attempt (helped MAE, hurt Brier — signal doesn't transfer). Next candidate would be regime-conditional bin-lift tables (fit per state_fc so base rate stays comparable across halves within a regime), booked but not scheduled.

</details>

<details>
<summary><strong>v0.6.382j • July 27, 2026</strong></summary>

- **Debug page — pp row headline/snapshot number consistency.** The scorecard headline's Brier-scored tile has been reading `pp 0.0%` (correct: L3 pp was dropped 2026-07-04, so live pp production = L1 = raw, delta = 0), but the per-field snapshot's vs-raw column just said "Brier-evaluated" with no number — and the Status cell led with "Brier-evaluated" then quoted "CALIBRATED +8.4% vs raw, BSS +0.126" from the v0.6.335 Phase 3 decomposition, which is an offline analysis measurement, not the live production number. Reader had to know both facts to reconcile the two views. Fix: vs-raw column now reads `0.0% (Brier; L1=raw)` to match the headline exactly, and Status cell rewritten to lead with "L1 only in production, no open work" + explicit note that live Brier = raw Brier (matches the 0.0% headline tile) + explicit "separate offline Phase 3 decomposition" framing for the +8.4% number so the two numbers are no longer mistakable for each other.

</details>

<details>
<summary><strong>v0.6.382i • July 27, 2026</strong></summary>

- **Debug page — "What's running" completeness, wg row wording, R&D subheading collapsibility, per-field snapshot template.** Four items. (1) **"What's running" stack list now includes chp + wdp** as their own bullets alongside Lsr and Lc, matching the existing precedent for how specialists appear in the stack (the block was already mixing architectural layers L2/L3/L4 with specialists Lsr/Lc, so this just extends the pattern to the two live specialists that had been missing). Also updated the Lsr bullet's Lt note from "retired 07-13" to "reclassified as telemetry experiment 07-27" for consistency with the R&D reclassification below. (2) **wg row in per-field snapshot rewritten to lead with what's live.** Old phrasing ("Two independent gates pending; both HELD") conflated "held" with "nothing wg-shaped is running," which is false — the asymmetric wg SKIP table has been LIVE since 07-20 v0.6.366 with 48 cells. New wording: "Stable win vs raw; existing asymmetric wg SKIP table is LIVE. Two additional gates HELD 07-27: 12-cell L3 skip-table extension and wg residual persistence gate — residual gate blocked 07-26 by h_wg_residual_persistence_stage1 flipping PROMOTE → MARGINAL." (3) **R&D four subheadings (Diagnostics / Tools / Candidates / Experiments) now collapsible `<details>` groups** with the h3 as the summary chevron — matches the same folding UX as their children (R0, D1, F1, R2 under Diagnostics; S1, B1 under Tools; C1 + Backlog under Candidates; E1 + E2 under Experiments). Stage 0 explorations converted from bare `<h4>+<ul>` into a proper `<details class="research-subsection" id="stage0-explorations">` block (id E1) so it visually matches S1/B1/C1. Lt reclassified from "[RETIRED LAYER]" to "E2. Lt — Cove microclimate telemetry probe" — "retired" was the wrong word since <code>compute_cove_correction()</code> still runs each tick and <code>cove_gradient_log.json</code> is still appending; it's an active telemetry experiment with a dormant correction, not a retired layer. (4) **Per-field snapshot rewritten as consistent state → reason → next-action template.** Rows updated: t (added "no open work" + telemetry reclassification), h (led with "Stable win; h/l4 narrow-add HELD"), ws (led with "additive LIVE; hardcode-REPLACEMENT HELD"), cl (led with "Lc LIVE; clp flip gate open"), pp (added "no dated re-check"), pa (added "no open work" + tightened τ history), wd (led with "L2 + wdp both LIVE" + moved chronology into supporting clause). Each row now reads as current state up front, reason clause, then next action or explicit "no open work" — cuts the changelog drift that had been accreting.

</details>

<details>
<summary><strong>v0.6.382h • July 27, 2026</strong></summary>

- **Debug page — R&D 3-way regroup + RIGHT NOW right-column fix + Engineering meta-line delete.** Three items. (1) **R&D reorganized from 2-way (Diagnostics / Candidates) to 3-way (Diagnostics / Tools / Candidates).** Joe flagged that Diagnostics held 2 items that weren't diagnostics (G1 gated candidates + S1/B1 evaluation tools) and Candidates held 1 shipped item (R6 → C1a). New split: **Diagnostics** = audit views of live behavior (R0 L3/L4 audit, D1 drill-down, F1 frontal passages, R2 state-stratified accuracy); **Tools** = candidate-evaluation instruments (S1 shadow tuner, B1 backtest sweep); **Candidates** = in-flight hypotheses (C1 stack status + Backlog + Experiments Stage 0 sub-section). Joe's follow-up: since all Stage 3 candidates are gated by definition (that's what Stage 3 means), the G1 "Gated correction candidates" label was redundant — renamed to "C1 confidence stack — status" and moved under Candidates. R6 standalone section deleted; content absorbed into C1 stack card ("C1a shipped as regime-transition axis, was R6") + S1 Tools description ("surfaces the live conditional_audits.r6 C1a-transition verdict"). Group A framing tightened to just the individual-axis architecture note since stack-level status now lives in the C1 stack card above. Section subtitles added ("Diagnostics — audit live behavior", "Tools — evaluate candidates before promotion", "Candidates — in-flight hypotheses (Stage 3 = wired ENABLED=False by definition)"). Also updated F1's description to note the 3 live consumers (PWA card + C1e + 10 analysis scripts). (2) **RIGHT NOW pipeline table right-column label styling fix.** The `.hb-corr-table td:first-child` CSS applied muted-grey + left-align to the actual first cell in each row; the right column's Field cell was the 5th <code>&lt;td&gt;</code>, so it didn't match that selector and inherited default text color. Fix: <code>_rowCells(r, isRight)</code> now emits inline <code>text-align:left;color:var(--muted)</code> on the right-column label td alongside the existing border-left divider. Right and left column labels now visually match. (3) **Engineering updates meta-line deleted.** Was: "Per-field snapshot lives above under Current state. Recent changes tracked in the Recent activity section (not repeated here)." That only made sense to readers who knew the old format where the per-field snapshot lived under Engineering — new readers just saw an orphan pointer. Deleted outright.

</details>

<details>
<summary><strong>v0.6.382g • July 27, 2026</strong></summary>

- **Debug page — R&D + Archive full sweep.** Two goals: (1) content in the right section, (2) condense verbose prose. Placement fixes: G1 gated-candidates C1 mega-paragraph compressed (duplicated Lc + Group A C1h content) → 2-line summary + pointer to Stage 4 status; Backlog "Correction candidates in flight" table (12-row duplicate of What's improving at top of page) deleted entirely, replaced with a one-line pointer to Current state; Group B marine-layer 1500-char paragraph reduced to 3 lines with pointer to Archive (settled 07-16 as "hold indefinitely" — Archive already carries the full history); Group D shipped items (wd L2, joiner, K-taper, cc→L4, Lc, dp depression) compressed from 5 verbose paragraphs to 6 one-liners each with cross-refs to their layer sections; Stage 0 Experiments list trimmed from 14 items to 7 genuinely-open ones (promoted → Stage 1+, killed by orthogonality, and settled-null items moved to Archive framing as single source of truth). Condensations: R0/D1/S1/B1/F1 diagnostics preambles ("What this is:" paragraphs) tightened to 1 sentence each; R2/R6 preambles condensed; Group A C1 axes (B/C/F/E/H) collapsed from 5 verbose bullets to 5 one-line entries; Group A framing paragraph (dated 06-20 history) compressed to 2 lines; Group C (Wind-direction sector + Sea-breeze onset/decay) tightened; Backlog framing paragraph compressed; Archive preamble tightened. Character-count reduction across R&D+Archive: ~40-50%. Text-only; no JS changes.

</details>

<details>
<summary><strong>v0.6.382f • July 27, 2026</strong></summary>

- **Per-band tables — "Production" column header shortened to "Prod" to fix overflow.** Joe flagged the Production column's right-side border rendering as clipped/missing on the ch and wd cards. Initial diagnosis was `border-collapse: collapse` clipping the outermost cell border, and I added an `inset -1.5px 0 0` box-shadow backstop. Wrong root cause — a zoom-out screenshot showed the "Production" header text was literally being truncated on multiple cards ("Producti…"), meaning the whole column was overflowing the accuracy-card container. The border wasn't broken; the column was pushed past the card's right edge. Fix: `renderAccuracySection` at line 3530 now emits `<th>Prod</th>` instead of `<th>Production</th>` (matches the chart legend + the RIGHT NOW pipeline table's terminology; ~50% column-width reduction). Reverted the box-shadow backstop since it was papering over the wrong problem. Title tooltip on the `<th>` preserves the full "Production" context for hover users.

</details>

<details>
<summary><strong>v0.6.382e • July 27, 2026</strong></summary>

- **Debug page — Recent activity condensation.** Three edits. (1) Badge legend collapsed from 5 lines (badge + description each) to a single "Badges:" line with color chips only — after 1-2 exposures the badges are self-explanatory. (2) Today's 3 DASHBOARD entries for v0.6.382a/b/c/d consolidated into one summary line pointing to CHANGELOG for detail. The individual granularity was useful in-session but adds noise to the rolling activity feed once the work is done. Kept as one line: multi-pass 07-27 debug page cleanup (post-ship refresh + compression pass + per-field snapshot move + R&D staleness fixes + Open-arch trim + Retired sub-box delete + RIGHT NOW 2-column split + 2 feedback memories). (3) Deleted the hidden HTML comment block preserving the trimmed 07-24 → 07-21 items (28 lines of dead source; CHANGELOG carries the full text). Recent activity render now: compact 1-line legend, then today (2 items) + Sun (3 items) + Sat (3 items) + Live-layer change gate + Still open watches reference blocks. ~40 lines out of source, ~6 lines out of render.

</details>

<details>
<summary><strong>v0.6.382d • July 27, 2026</strong></summary>

- **Debug page — Open arch cleanup + Engineering trim + RIGHT NOW table split into 2 columns.** Three edits. (1) **Open architectural questions** — 11 items reduced to 2 genuinely open (L2-as-observation-only + tight-τ cloud bias propagation Stage 1 candidate) plus a one-line pointer for 6 settled items (SKIP_TABLE architecture / Lt Fix B / per-field τ lesson / scorecard banner / C1e / per-row applied-layer stamping / per-lead Brier for PP / dp L4 skip-table). Full details live in git log + CHANGELOG. Cut ~110 lines. (2) **Engineering "Retired" sub-box deleted** — the Archive section (line ~1860) already carries the full retired-ideas list with per-item rationales, and the nav bar already links to Archive. The Engineering sub-box was a one-liner summary + pointer, redundant with both. (3) **Open architectural questions defaults to `open`** — matches Production stack + Built-not-applied for consistency (previously 2-of-4 sub-boxes were open by default, causing asymmetric on-load state). Engineering meta-line trimmed from "Last curated: ... · per-field snapshot lives above ... · click any sub-box header to collapse it, or use the toggle below" to just "Per-field snapshot lives above under Current state. Recent changes tracked in Recent activity (not repeated here)". (4) **RIGHT NOW pipeline table split into 2 columns** with correcting-first partition. Old: 14-row vertical table with ~40% horizontal whitespace between the 4 columns. New: `thead` doubled to 8 columns with a subtle border-left divider between the two halves; `renderHeadlineBox` partitions rows into `[correcting, quiet]` preserving canonical order within each group, then pair-renders `col-1[i]` + `col-2[i]` per row. Today's snapshot: col-1 = t/h/dp/ws/wg/cc/cm (7 correcting), col-2 = wd/cl/ch/sr/pp/pa/pr (7 quiet); halves vertical space. Partition-only chosen over sort-by-magnitude because unit heterogeneity (%pts vs mph vs °F vs W/m²) makes raw-magnitude ranking misleading, and the eye already handles "big vs small correction" within col-1 via visual scan. On slow days (few corrections), col-2 fills with more quiet fields from the remaining canonical set — lopsided-but-honest.

</details>

<details>
<summary><strong>v0.6.382c • July 27, 2026</strong></summary>

- **Debug page — per-field snapshot moved to Current state; 3 stale rows fixed.** The "Current pipeline state" per-field table was under Engineering updates ("where we are") but the top-of-page section is literally called Current state — the granular per-field table is the answer to "what's the state of every field right now," so it belongs at the top of Current state, before the tri-column What's running / improving / evaluated grid. Moved verbatim, with three staleness fixes on the way: **h row** — "Retest 07-26+" → "07-26 retest declined (Jaccard walker cleared 8/7 but 0 SHIP cells today, live-empty fossil pattern); retest 08-02+"; **dp row** — added dp_residual_persistence Stage 3 wire (v0.6.380, day 3/7, 8 SHIP + 2 MARGIN long-lead cells, ENABLED=False through 08-01); **cl row** — retired `cl_persistence_short_lead` reference replaced with successor clp (Stage 3 wired 07-24 v0.6.379 ENABLED=False, 12 SHIP / 8 MARGIN / 16 SKIP, day 4/7 through 07-31). Also updated stale date "2026-07-23" in summary → "per-field snapshot" (undated, since table itself carries the version/date context). Engineering updates meta-line now points readers up to the Current state block. Rows tightened to remove sub-paragraphs already covered elsewhere. Text-only.

</details>

<details>
<summary><strong>v0.6.382b • July 27, 2026</strong></summary>

- **Debug page — readability + R&D staleness sweep.** Follow-on to v0.6.382a's post-ship sweep. Three passes: (1) **Compression** — cut "Upcoming decisions" sub-box in Engineering (~60 lines; Calendar covers it); compressed Production stack specialist bullets from paragraphs to one-liners with cross-refs to layer sections / Post-ship / What's improving; consolidated "What's improving" (chp/Lc/wdp cut — they're shipped, not improving; ws L3 REPLACEMENT rewritten to lead with the pending flip; 4 remaining cards compressed from 3-row bullet/description/arrow to 2-row); tightened Recent activity 07-27 entries + Calendar Wed 07-28/Thu 07-30 entries + course-of-action framing paragraph. (2) **R&D staleness fixes** — C1 Stage 4 audit numbers refreshed (32.43% HOLD, C1h 14/7 CLEARED, C1d 3/7, next 07-30); R2 preamble Lt "dormant since 07-01" → "retired 07-13 v0.6.329"; per-octant ws L2 table row 07-17 read-1/3 (2 REAL) → 07-24 read-2/3 (4 REAL, NE + W promoted from WATCH); pre-frontal cloud widening 07-04 MIXED (2 ortho) → 07-22 v0.6.372b matched-regime fix PROMOTE (7 SHIP); dp depression regime nor_easter watch tagged dormant (retire if not resurfacing by 08-05); G1 gated-candidates preamble replaced stale Lc-as-example with current 3 gated candidates (clp / wg residual / dp residual); Backlog framing rewritten from "Stage 1 candidates (curated text, not yet running)" to "Stage 0-2 pre-wire pipeline" acknowledging ~5 rows are running scripts. (3) **Stale wdp / 07-27 sweep** — line 849 top alert badge, line 1265 open-arch skip-table question ws "still deferred until 07-27" → HELD, wg L3 skip-table extension row "Earliest ship 07-27" → HELD paired with wg residual persistence. **Session totals across v0.6.382a + v0.6.382b: ~230 fewer lines, ~30 stale references fixed, no lost information.** Text-only; no JS logic changes. Two new feedback memories written: [[feedback_rd_sweep_on_verdict_change]] (sweep R&D on ship-time, not just top-of-page counters) + [[feedback_shipped_items_leave_backlog]] (Stage 3+ candidates exit Backlog entirely; update preamble examples referencing the just-flipped candidate).

</details>

<details>
<summary><strong>v0.6.382a • July 27, 2026</strong></summary>

- **Debug page — v0.6.382 post-ship sweep.** Rule 5 sweep for the wdp flip. **Recent activity:** rolled to 07-27 (Mon) with PIPELINE v0.6.382 + DASHBOARD sweep entries; added missing INFRA v0.6.381 walkforward SKIP-aware fix to 07-26 items; trimmed 07-24 → 07-21 dated day entries per rolling 3-day window (preserved in HTML comment for one cycle). **Calendar:** removed the 3 resolved Mon 07-27 rows (wdp ✓ shipped; wg residual persistence + ws L3 REPLACEMENT both HELD per 07-26 triage). **Post-ship watches:** added wdp day 0/14 through 08-10 (both the top-of-page block and the Still-open-watches block); fixed the wg persistence-skill note that claimed "Both 07-27 ships … verify post-flip" — neither wg ship happened. **wd persistence gate section:** header + narrative rewritten from `⚙ Stage 2 preview, ENABLED=False, day 4/7` to `✓ FLIPPED v0.6.382` with post-deploy verify details. **wg residual persistence gate section:** rewritten to `07-27 flip HELD; awaiting Stage 1 recovery` (Stage 1 flipped PROMOTE → MARGINAL 07-26). **ws L3 asymmetric section:** REPLACEMENT `deferred to 07-27` → `HELD 07-27 (Jaccard 0.75), re-eval ~07-31`. **RIGHT NOW status matrix / in-flight table / Upcoming decisions:** all Mon 07-27 rows updated with SHIPPED / HELD outcomes; three "Earliest ship 07-27" or "deferred to 07-27" strings across the wg L3 / ws L3 / wg residual rows updated. **Course-of-action framing:** rewritten from "4 flips clustering at 07-27, largest since Lc if all clear" to the actual triage outcome (1 shipped, 3 HELD). **Meta-line:** Last-curated stamp advanced to 2026-07-27. Alert badge at top updated. Not localhost-tested (text-only edits to existing block structures; no JS logic changes).

</details>

<details>
<summary><strong>v0.6.382 • July 27, 2026</strong></summary>

- **wd persistence gate — FLIPPED ENABLED=True.** After 7-day narrow-promote gate cleared (Jaccard 1.0 across 5 committed daily reads 07-20 → 07-26, SHIP set bit-stable at {calm/12-23, calm/24-47, pre_frontal/0-5, se_flow/0-5, sw_flow/0-5}). Bypasses L1/L2 with persistence-of-obs when state predicts a regime transition inside the SHIP whitelist. Expected lifts: −26% sw_flow 0-5, −20% calm 24-47, −12% se_flow 0-5. Executed the 07-21 preflight (`docs/preflight/wdp_ship_patches.md`) verbatim: SITE 1 collector.py wire + `_da_wdpg` in applicability tuple; SITE 2 forecast_snapshot.py wd layers dict (l2/l3/l4 = `wind_direction_pre_wd_gate`, wdp = `wind_direction`); SITE 3 `_derive_applied_layer` walks wdp + wd skip removed so wd participates in per-row applied_layer stamping; SITE 4 forecast_error_log.py wd-branch tuple extended with wdp for circular error_wdp emission; SITE 5 decay_fit.py accumulator + emission loops (2 sites) extended with wdp; SITE 6 corrections_debug.html 5 sub-sites (`_layerApplied` wdp branch, LAYER_LINES entry, LAYER_STYLE entry yellow-green `rgba(180,210,90,1)`, FIELD_LAYERS.wd rewrite adding wdp + prod_real isProd, SHIP_EVENTS.wd new entry); SITE 7 mae_over_time.py PERMISSIVE_LAYER_KEYS + L1_ONLY branch wdp emission. Pre-gate key handling verified: module only stashes `hourly.wind_direction_pre_wd_gate` inside ENABLED branch, so Site 2's `.get(pre_gate, wind_direction)` fallback covers no-op path. First ~3 days the prod_real line will fall back to L2 until n≥3 days per `MIN_DAYS_FOR_LEGEND` (same as chp did 07-19 → 07-22). 14-day post-ship watch through 08-10. Third concrete persistence specialist post-flip (chp/clp/wdp) → shared `persistence_specialist(field, gate_table, obs_source, fallback_key, math=)` helper extraction on deck per [[project_todo]] P4 item 10.

</details>

<details>
<summary><strong>v0.6.380c–v0.6.381 • July 26, 2026</strong></summary>

* **v0.6.380c — 07-25 calendar sweep + walkforward SKIP-blind diagnosis.** Debug page ~15 edits. Closed chp mid-lead re-check (aggregate persistence-skill Δ stable at −1.03, deferred to 07-28); C1 Stage 4 re-audit (HOLD-again 32.43%, cl now DEGRADED at 12-23h + 6-11h replacing cleared cm — same failure pattern different cell, next re-audit 07-30); h/L4 07-26 retest declined (Jaccard walker 8/7 but 0 SHIP cells — live-empty fossil pattern, retest 08-02+). Discovered `walkforward_l3l4_validator.py`'s `drop {wg,ws}` divergence-report signal was spurious: SKIP_TABLE-blind, ignoring asymmetric fc-bin SKIP infrastructure shipped v0.6.366 (wg) / v0.6.370 (ws additive). wg has huge WINS (+30.9% ne_flow/24-47, +21.1% se_flow/24-47) AND huge LOSSES (−41.4% calm/24-47) that cancel to +0.4% aggregate, but asymmetric SKIP already skips the loss cells in production so the aggregate compares against a pre-asymmetric baseline that no longer exists. Filed [[feedback_walkforward_skip_table_blind]]. Near-miss avoided: almost wrote a HOLD recommendation for ws L3 REPLACEMENT citing "drop ws" signal — real HOLD reason is Jaccard 0.75, not tool artifact.

* **v0.6.381 — walkforward validator SKIP-aware structural fix.** Imports `_should_skip` + `_should_skip_asymmetric` from `decay_apply.py`; preprocesses each pair-log row's L3/L4 predictions with production SKIP logic before MAE aggregation. Uses `forecast_l1` as raw fc for asymmetric quartile lookup. Default is skip-aware; `--ignore-skip-table` flag restores old behavior for A/B checks. Post-fix verify: wg L3 flipped `ENT/off/+1.1%` → `SHIP/+3.1% fc / +2.6% obs` matching production. ws L3 stays `off/-0.3%` — honest signal that ws L3 aggregate is genuinely marginal beyond the 26 asymmetric SKIP cells; production keeps ws because per-cell surgical wins matter. Tomorrow's divergence report shows AGREE on wg (spurious drop removed).

</details>

<details>
<summary><strong>v0.6.380b • July 25, 2026</strong></summary>

- **Debug page — Recent activity verbosity sweep.** Tightened all 17 badged narrative bodies (07-21 → 07-25). Cut instrumentation framing ("Morning digest flagged…", "post-deploy…", "for the reader"), dropped restated cell counts already visible in cards below, collapsed pre-key + commit-hash + trailing-feedback-link trivia, replaced "sanity clamp |correction|" → "clamp |Δ|". Every fact preserved: version numbers, dates, cell counts, verdicts, delta percentages, file paths, all `[[memory-links]]`. Target was ~40% cut; actual ranges from 20% (short items like l2_lead_decay_fit guard) to 50% (long items like v0.6.371 real-per-row Prod). Scope: badged item bodies in Recent activity only. Day-summary lines, still-open watches list, legend, and layer cards untouched.

</details>

<details>
<summary><strong>v0.6.380a • July 25, 2026</strong></summary>

- **Debug page — Recent-activity category badges + RIGHT NOW dp row.** (1) **Badge taxonomy regularization.** Recent activity was mixing 4 distinct work types (correction shipping, new signals/measurements, tooling/backstops, debug page updates) under one green `SHIP` badge. Split into: **`PIPELINE`** (green `#4ad29a` — correction stack changes: Stage 3 wires, flips, retires), **`DISCOVERY`** (coral `#e0a070` — new signals/measurements/verdict changes: h_ scripts, halves re-runs, orthogonality reads), **`INFRA`** (cool grey `#7090a0` — tooling/backstops/registries: digest scaffolding, allowlists, script bugfixes), **`DASHBOARD`** (purple `#a89ce0` — retained; debug page updates), **`PREFLIGHT`** (blue `#8fa5c4` — retained; pre-mortem docs/checklists). Legend added at top of Recent activity block. Backfilled 9 previously-`SHIP`-labeled items 07-21 → 07-23 to the correct category (5 INFRA, 3 DISCOVERY, 1 DASHBOARD). Broke out 07-24 (Fri) into 6 badged items (was single day-summary line): INFRA v0.6.378 · PIPELINE v0.6.379 · DASHBOARD v0.6.379a · DASHBOARD v0.6.379b · DISCOVERY sr Lsb HOLD · DISCOVERY h_ws_octant. Broke out 07-25 (today) into 3 badged items: PIPELINE v0.6.380 · INFRA gate_firing_rollup allowlist · DASHBOARD v0.6.380a (this entry). Scope: Recent activity only — Engineering updates section left with existing `SHIP` badges (already summarized in CHANGELOG; if useful over the next week, retrofit later). (2) **RIGHT NOW pipeline table — dp row added.** The correction-stack table under "RIGHT NOW — WHAT THE PIPELINE IS DOING" showed 13 fields (t, h, ws, wg, wd, cc, cl, cm, ch, sr, pp, pa, pr) but skipped dp since inception. dp is first-class in the correction stack (raw `hourly.dew_point` → L1 → L2 Kalman → L3 skip-table → L4 additive gate) and just got a specialist (dp_residual_persistence v0.6.380) — the omission stood out on this morning's screenshot. Added "Dew point (dp)" row between Humidity and Wind speed. Reads raw `hourly.dew_point` and corrected `hourly.corrected_dew_point`; delta auto-computes via existing `_fmtDelta` (no bias passthrough needed — dp isn't in the Kalman bias emit). Verified live values on GCS: raw 51.9°F → corrected 56.2°F → +4.3°F correction. See [[feedback_debug_page_canon]].

</details>

<details>
<summary><strong>v0.6.380 • July 25, 2026</strong></summary>

- **dp residual persistence — Stage 3 wire (ENABLED=False).** New `weather_collector/processors/dp_residual_persistence.py` cloned from `wg_residual_persistence.py`: reads `hourly.corrected_dew_point_post_l2` stashed by decay_apply, adds fitted per-clock-hour L2 residual mean, replaces post-L3 dp in SHIP/MARGIN cells. Stage 2 preview (2026-07-22) gate shape: 8 SHIP long-lead cells (frontal 12-47h, nw_flow 24-47h, pre_frontal 12-47h, sw_flow 6-47h) + 2 MARGIN + 26 SKIP short-lead cells. Sanity clamp `_MAX_ABS_CORRECTION_F = 10.0` (Stage 2 hour_of_day fit range is |≤3.15|°F — clamp is a data-pathology guard). Wired in `collector.py` after wg_residual_persistence in the specialist stack; describe_applicability added to the layers list. Preserve-before-mutate pre-key `corrected_dew_point_post_l3_pre_dprp` per feedback_preserve_before_mutate. Same 7-day live-layer flip gate as wg/cl/ch; ENABLED=True earliest 2026-08-01. `KNOWN_LIVE_PIPELINES` registry entry added for `h_dp_residual_persistence_stage2` in the same commit per v0.6.378 lesson. `gate_firing_rollup` EXPECTED_DORMANT_OPERATORS entry added so Day-0 telemetry doesn't fire a spurious UNEXPECTED alert. Not localhost-tested (collector-side, no UI change).

</details>

<details>
<summary><strong>v0.6.379b • July 24, 2026</strong></summary>

- **Debug page — Calendar + Upcoming decisions Fri 07-24 sweep + Recent activity rollover.** Removed 3 stale Fri 07-24 rows from Calendar block (line 934-939) + 2 stale Fri 07-24 rows from Upcoming decisions block (line 1201-1215) — all three were outcomes today, not upcoming. **clp regime-gate variant re-audit:** superseded by v0.6.379 Stage 3 wire (bigger scope than the entry proposed — full regime × lead_band, not narrow 3-regime). **sr Lsb Stage 3 halves re-run:** ran in digest, verdict HOLD (pooled +7.34%, halves +24.1% / −1.6%, halves diverged &gt; ±5pp gate) — stays ENABLED=False. **h_ws_octant_bias re-read 2/3:** ran in digest, verdict 4 REAL octants (NE +0.81, E +1.71, SW −0.80, W −0.92 mph) — up from 07-17's 2 REAL + 2 WATCH (NE and W promoted from WATCH). Signal strengthening. Read #3 due 07-31. **Recent activity:** rolled 07-23 from "today" to "(Thu)"; added 2026-07-24 (Fri) as today with the 3-ship summary + the sr Lsb HOLD + h_ws_octant 4-REAL outcomes. Not localhost-tested (text-only edits to existing block structure). Not a full Rule 5 sweep — day counters and other blocks are the fitter's job via build.py SHIP_EVENTS auto-refresh (v0.6.376 fix #3), which touched what it needed to during the v0.6.379 build.

</details>

<details>
<summary><strong>v0.6.379a • July 24, 2026</strong></summary>

- **Debug page — cl_persistence_gate Rule 5 sweep + 7-day flip gate counter.** Follow-on to v0.6.379's Stage 3 wire. Added "Day 1/7 today" counter to the Stage 3 gated card (line 1883). Updated the Persistence-skill narrative (line 1332) — was still describing the retired short-lead gate at "day 7/7 HOLD"; rewritten to describe the successor gate with 12/8/16/1 rollup + 7-day flip gate day 1/7 through 07-31. Updated the section-D framing paragraph (line 1886) — was still saying "cl narrow persistence HELD (halves-mixed 4/9 regimes)"; rewritten to note the wire + flip gate. Cannot localhost-test this session; changes are pure text updates in existing cards / narrative paragraphs, no JS logic or card layout changed. Memory index also refreshed: [[project_cl_persistence_investigation]] marked RESOLVED, [[project_clp_regime_gate_opportunity]] marked SUPERSEDED, MEMORY.md moved both from "Active watches" to reflect settled state, [[project_todo]] refreshed with v0.6.379 status + new clp day-1/7 counter entry.

</details>

<details>
<summary><strong>v0.6.379 • July 24, 2026</strong></summary>

- **cl persistence gate — Stage 3 wire; retires cl_persistence_short_lead.** New `weather_collector/processors/cl_persistence_gate.py` mirrors `ch_persistence_gate.py`: regime × lead_band conditioned persistence bypass, `_cell_fires` accepts SHIP+MARGIN, `frontal` always falls to baseline by contract, ENABLED=False pending 7-day live-layer flip gate. Wired in `collector.py` after Lc (same bias-reintroduction rationale as chp — Lc for cl was fit against L1 so applying it on top of persistence would re-introduce bias). Persistence source priority: `cloud_l2_meta.obs_mean` → `hourly[0].cloud_cover_low` → no-op. Reads the halves-verified Stage 2 preview table at `weather_collector/data/cl_persistence_gate_curated.json` (shipped v0.6.378). **Retired** `cl_persistence_short_lead.py` (shipped 2026-07-13 v0.6.330): the narrow shape hypothesis (all 9 regimes at 0-5h only) was disproven by the halves-verified Stage 2 re-run — persistence wins BEYOND 0-5h in calm/se_flow/unknown all-leads + nw_flow 24-47h, and LOSES at sea_breeze 0-5h. The 07-19 halves-verified re-run that the narrow gate was waiting for is what v0.6.378's `h_cl_persistence_blend_stage2.py` delivered. Schema mismatch caught during wiring: short-lead read `cell.status` + `"0-5h"` band names; Stage 2 preview writes `cell.verdict` + `"0-5"`. With cl_persistence_short_lead ENABLED=False no user-visible break, but contract had shifted. **Comment/reference updates:** `forecast_snapshot.py` clp slot comment, `forecast_error_log.py` layer loop comment, `analysis/mae_over_time.py` PERMISSIVE_LAYER_KEYS comment, `analysis/gate_firing_rollup.py` EXPECTED_DORMANT_OPERATORS entry (key renamed to `cl_persistence_gate` + reason updated), `corrections_debug.html` Stage 3 gated card (line 1883) rewritten to reflect retire + successor + Stage 2 rollup + new 07-31 flip window, plus 3 JS comments (LAYER_LINES, FIELD_LAYERS, _layerApplied filter). Historical CHANGELOG/preflight-doc references to `cl_persistence_short_lead` intentionally not touched (history). **KNOWN_LIVE_PIPELINES registry entries added in same commit** per today's lesson (v0.6.378): `h_cl_persistence_blend` + `h_cl_persistence_blend_stage2` now relabel to STABLE. Verified: post-registration digest re-run surfaces `h_cl_persistence_blend` in Auto-relabeled STABLE alongside the chp/C1h/C1d/Lc entries. Whitelist gate shape (per Stage 2 preview): 16 persist cells covering calm all-leads + se_flow all-leads + unknown all-leads + short-lead across sw_flow/ne_flow/nw_flow/pre_frontal + specific mid/long-lead nw_flow-24-47/pre_frontal-6-11. Smoke tested: `describe_applicability()` returns 12 SHIP / 8 MARGIN / 16 SKIP / 1 THIN; `stamp_cl_persistence_gate` on synthetic se_flow row fires 41 leads (0-5 + 12-47) and skips 6 leads (6-11, matches Stage 2 SKIP). SHIP_EVENTS not added yet (gate is ENABLED=False; 14-day post-ship watch begins on flip).

</details>

<details>
<summary><strong>v0.6.378 • July 24, 2026</strong></summary>

- **KNOWN_LIVE_PIPELINES registry backfill + h_cl_persistence_blend Stage 2 preview.** Morning triage recommended shipping C1h (13 SHIP cells today). C1h has been live since v0.6.316 (2026-07-10) — exact "propose already-done work" failure class the v0.6.376 backstop was written to prevent. Root cause: seeded the registry with the single class case (`h_l3_asymmetric_stage1`) and treated the seed as the finished fix. Every other live pipeline emitted its action-verb verdict un-relabeled. **Backfill:** added `h_c1h_orthogonality` (C1h, v0.6.316), `h_cloud_disagreement_orthogonality` (C1d, Stage 3 07-08), `h_ch_persistence_blend` + `_stage2` (chp, v0.6.358), `lc_fit` (Lc, v0.6.354). Deliberately NOT registered: `walkforward_l3l4_validator` (composite — L4 half live but L3 half proposes real drop of wg/ws; registering would suppress the drop signal); `h_precip_fc_orthogonality` and `cluster_spread_*` (already emit their own STABLE self-check). Verified: post-backfill re-run moved four scripts from SHIP-ELIGIBLE / Changed verdicts into `Auto-relabeled STABLE`. SHIP-ELIGIBLE now correctly shows only pre_front (THIN-blocked), wind_shift (MIXED), walkforward (L3 drop still gated 2/7). Rule going forward codified in [[project_already_live_backstops]]: register in the same commit as the ship. **Stage 2 preview shipped:** `analysis/h_cl_persistence_blend_stage2.py` mirrors the ch template. cl uses `frontal→baseline` (cl has no L4), else persistence. Rollup: 12 SHIP / 8 MARGIN / 16 SKIP / 1 THIN of 37 judged. Script emits BOTH gate shapes for comparison: blacklist (persistence default, list SKIPs — 17 rules) vs whitelist (baseline default, list SHIPs — 16 rules). Whitelist wins by 1 and reads as a coherent story (calm all-leads + se_flow all-leads + unknown all-leads + everyone-at-0-5h); shorter_shape recorded as "whitelist" in the curated JSON. Frontal MARGIN cells excluded from whitelist because gate contract forces frontal→baseline (gate_mae == base_mae by construction, definitional artifact not a persistence signal). Files: `analysis/output/h_cl_persistence_blend_stage2.txt`, `weather_collector/data/cl_persistence_gate_curated.json` (preview only, not wired). Runlist auto-discovers `analysis/*.py` so it runs on next digest with no additional wiring. Stage 3 (write `cl_persistence_gate.py` processor + curated reader + debug page card + ENABLED=False + 7-day gate) deferred to its own session. **Bundled:** morning digest's daily fitter refresh (15 curated JSONs + 2 gate-history caches, most re-serialization drift; genuine cell-set shifts on `cm_l3_asymmetric`, `wg_residual_persistence`, `ws_l3_skip_table` from fresh day of data) — precedent v0.6.377b.

</details>

<details>
<summary><strong>v0.6.377a • July 23, 2026</strong></summary>

- **Debug page — 🔵 What's being evaluated next Calendar block: full rewrite.** Miss from v0.6.375b's "full-page cleanup" claim. That commit rewrote the sibling **Upcoming decisions** block but left the **Calendar** block untouched with 10+ past-dated entries (Sun 07-19, Mon 07-20, Tue 07-21, Wed 07-22) still labeled as "next." Rewrote to future-only: Fri 07-24 (sr Lsb halves + clp regime-gate + h_ws_octant re-read 2), Sat 07-25 (chp mid-lead re-check + C1 Stage 4 re-audit), Sun 07-26 (h/l4 narrow-add retest earliest), Mon 07-27 (wg residual persistence + ws L3 REPLACEMENT + wdp flip), Fri 07-31 (Lc watch closes + h_ws_octant re-read 3), ongoing (C1h GATE CLEARED + C1d 3/7), blocked (h_hsf + h_pre_front THIN). Rechecked entire page for other stale-date content (grepped `Sun 07-19|Mon 07-20|Tue 07-21|Wed 07-22|watch begins today|flipping today|streak restarts today`) — no remaining past-date labels outside the historical DASHBOARD narrative entries in Recent activity.

</details>

<details>
<summary><strong>v0.6.377 • July 23, 2026</strong></summary>

- **Fix (4) — cross-script contradiction registry.** Same failure family as v0.6.376's KNOWN_LIVE_PIPELINES (propose action from one script's verdict without cross-checking), different manifestation. Class case: ch persistence gate — `h_ch_persistence_blend` says SHIP with 15-30% regime wins, `h_persistence_skill` says ch Prod −1.32 BEHIND. Both readings are real (blend uses fresh windows; persistence-skill scans full pair log including pre-flip Lc-only rows). A morning read of only one produces a wrong action. New `TARGET_SCRIPT_GROUPS` registry in `build_executive_summary.py` — `{target: {target_desc, scripts, resolution_note}}`. New `cross_script_contradictions(current)` scans registered targets; if scripts on the same target have MORE THAN ONE non-info bucket (info skipped so STABLE re-checks don't false-positive), emits a `⚠ CROSS-SCRIPT CONTRADICTIONS` section right after Auto-relabeled STABLE, listing each script's bucket + short verdict + a resolution_note explaining the "expected" disagreement + when to actually worry. Verified live: seeded with the chp case; today's digest now surfaces the contradiction at the top with the pair-log-lagging-indicator resolution note pointing to [[project_chp_midlead_regression_watch]]. Design note: don't over-register — a busy contradictions section becomes noise. Only register targets where the disagreement is common enough that a fresh morning read would miss the second script. [[project_already_live_backstops]] updated with the fix-(4) section documenting where to add entries.

</details>

<details>
<summary><strong>v0.6.376 • July 23, 2026</strong></summary>

- **Structural fixes for the "propose work that's already done" failure mode.** Six prior instances documented in memory ([[feedback_stated_intent_vs_code_behavior]] + [[project_07_18_session]]): scripts that emit action verbs (SHIP/PROMOTE/IMPLEMENT/"Move to Stage N") for pipelines already live pollute the morning digest, and I read the verdict as-is and propose the action. Rule exists ("any script emitting PROMOTE/KILL/SHIP/RETIRE needs an 'already live?' check") but lives in on-demand memory that doesn't auto-inject when I read a digest. Three machine-enforced structural fixes so the class dies:
  - **(1) Emitting-script self-check** — v0.6.375 already fixed today's case: `h_l3_asymmetric_stage1.py` verdict text rewritten from "STAGE 1 HIT — Move to Stage 2 wiring" to "LIVE — table wired since v0.6.366/370" (bucket() classifies LIVE as info, not promote). Preferred pattern per `h_precip_fc_orthogonality.py` STABLE re-check. Each script that emits action verbs for a live target should get this treatment.
  - **(2) Digest-side backstop** — `analysis/runlog/build_executive_summary.py` gets a `KNOWN_LIVE_PIPELINES` registry (script_name → {target, since_version, since_date}) and a `relabel_stable_recheck()` step in the verdict pipeline. When a registered script emits an action-verb verdict, the digest auto-relabels to `STABLE — <target> already live since <version> (<date>). Re-check pass. Original: <original verdict>`. `bucket()` now checks for STABLE BEFORE SHIP/PROMOTE so the "Original:" tail doesn't accidentally re-bucket as promote. New "Auto-relabeled STABLE" section in the exec summary shows what got suppressed — no silent hiding. Seeded with `h_l3_asymmetric_stage1` (belt-and-suspenders with the script-level fix in (1)). Add entries here whenever a live-layer change ships.
  - **(3) Debug page auto-refresh** — separate class (day-counter drift, not action-verb drift). `build.py` gets a `SHIP_EVENTS` registry (version, ship_date, watch_days) and `_refresh_debug_page()` step that advances every "day N/14" counter on lines mentioning the corresponding version string. Uses "day 1 = ship day" convention (matches prior changelog usage). Proximity-limited regex (~140 char window after version anchor) so lines mentioning multiple events don't get cross-clobbered. Also bumps the "Last curated:" banner to today. Seeded with the four active watches: Lc (v0.6.355, 07-17), chp (v0.6.358, 07-19), wd L2 (v0.6.368a, 07-20), ws L3 asymmetric (v0.6.370, 07-20). Every `python3 build.py` now auto-advances 16 counter sites across the page. Kills the "Rule 5 sweep drift" I hit every ~4 days.
- **Verified live:** re-ran build.py — counters correctly advanced Lc 6→7/14, chp 4→5/14, wd L2 3→4/14, ws L3 asym 3→4/14. Second run: no-op (idempotent). Retroactively normalized the v0.6.375a DASHBOARD entry to match the day-1-is-ship-day convention. This is the fix I should have built after the 07-18 session; deferred cost was ~1 wrongly-proposed action per morning for a week.

</details>

<details>
<summary><strong>v0.6.375b • July 23, 2026</strong></summary>

- **Debug page full-page cleanup — stale content pass.** Follow-on to v0.6.375a. **Current pipeline state:** header date 07-21 → 07-23; Lc row watch counter → day 6/14 through 07-31. **Production stack cards:** Lc/chp/wg residual persistence/cl persistence/wd persistence all counters and prose refreshed to reflect current state — chp card now carries the mid-lead regression sub-watch link + 07-23 persistence-skill lagging-indicator note; cl card reframed from "day 7/7 but not flipping today" to "OFF permanently" with regime-gated variant hint per [[project_clp_regime_gate_opportunity]]; wg residual counter 1/7 → 3/7; wd persistence gate counter 1/7 → 4/7. **C1 confidence card:** axis list expanded to include C1d (07-08 Stage 3) and C1h (v0.6.316 07-10, gate CLEARED 14/7 today); added note distinguishing per-cell stamp-time firing (live) from downstream user-visible widening (ENABLED=False). **Pre-frontal cloud widening card:** reframed as blocked-on-population (n=8 passages, THIN); references shared THIN blocker with h_hsf per [[project_c1e_hsf_kill_investigation]]. **Upcoming decisions section:** entire block rewritten. Removed all answered items (Thu 07-16 ws L3 strip, Fri 07-17 Lc flip, Sat 07-18 C1 Stage 4 defer, Sun 07-19 ch persistence gate, Sun 07-19 cl persistence, Sun 07-19 h/l4 narrow-add, Sun 07-19 pre-frontal, Tue 07-21 wg residual persistence) per the section's own "outcomes move to Recent activity" rule. Added forward-looking items: Fri 07-24 sr Lsb halves re-run, Fri 07-24 clp regime-gate re-audit, Sat 07-25 chp mid-lead 6-20h regression re-check, Sat 07-25 C1 Stage 4 + calibration audit, Mon 07-27 wg residual persistence flip, Mon 07-27 ws L3 hardcode-REPLACEMENT, Mon 07-27 wdp flip, Fri 07-31 h_ws_octant_bias re-read (3 of 3), Blocked-on-population catch-all (h_hsf + h_pre_front THIN). **Post-ship watches list:** Lc 5/14 → 6/14, chp 3/14 → 5/14 (+ regression sub-watch), wd L2 2/14 → 4/14, ws L3 asymmetric 2/14 → 4/14. **Watch-counter blocks throughout:** C1h 12/7 → 14/7, C1d 1/7 → 3/7. **Lsr "Where we are":** stale 07-07 investigation update rewritten to 07-23 state (Lsb Stage 3 wired 07-17 as unit-mismatch resolution, halves re-run 07-24 gates the flip, LSR_ENABLED divergence bug fixed 07-20 v0.6.365).

</details>

<details>
<summary><strong>v0.6.375a • July 23, 2026</strong></summary>

- **Debug page Rule 5 sweep for v0.6.374/375 + calendar / counter refresh.** Rolled Recent activity to 07-23 (added 07-22 entries promoted from CHANGELOG covering v0.6.372a-d + v0.6.373; demoted 07-21 from "today"; rolled 07-20 and 07-19 blocks off to trimmed line). Advanced 14-day watch counters: Lc day 6/14 (07-17 ship, watch through 07-31), chp day 5/14 (07-19 ship, watch through 08-02), wd L2 day 4/14 (07-20 v0.6.368a hotfix, watch through 08-03), ws L3 asymmetric day 4/14 (07-20 v0.6.370, watch through 08-03). wg residual persistence counter advanced day 1/7 → 3/7 (new baseline started 07-21). Added chp link to [[project_chp_midlead_regression_watch]] with 07-23 note that persistence-skill Prod −1.32 is a lagging pair-log-window indicator, not a live regression. Last-curated banner bumped 07-21 v0.6.371a → 07-23 v0.6.375a.

</details>

<details>
<summary><strong>v0.6.375 • July 23, 2026</strong></summary>

- **h_l3_asymmetric_stage1.py — stale-text cleanup.** Verdict line said "Move to Stage 2 wiring (extend SKIP_TABLE with fc-bin dimension)" and JSON `notes` field said "Stage 1 preview. Not wired to production." Both are false since v0.6.366 (wg) / v0.6.370 (ws) — decay_apply.py has `_load_asymmetric_table` + `_should_skip_asymmetric` + `_fc_bin` and calls them in the L3 apply loop; both `wg_l3_asymmetric_skip_curated.json` and `ws_l3_asymmetric_skip_curated.json` are read live. Rewrote verdict to "LIVE — table wired since v0.6.366/370" and rewrote `notes` to describe live semantics + additive-on-top-of-existing-SKIP_TABLE behavior. Also refreshed [[project_l3_asymmetric_fc_bin]] memory to mark Stage 2 wiring DONE. Current cells: wg 37 SKIP, ws 25 SKIP (down from 48+44 at Stage 1 07-20; some cells demoted to KEEP/MARGIN as windows accumulated). Per [[feedback_stated_intent_vs_code_behavior]].

</details>

<details>
<summary><strong>v0.6.374 • July 23, 2026</strong></summary>

- **Fossil-window slide across 13 analysis scripts + digest re-run refresh.** Morning digest flagged 13 scripts with WIN_ constants anchored at 2026-07-19 (4 days behind today), risking fossil re-reads per [[feedback_fossil_windows]]. Slid WIN_A/B/FULL forward 4 days on `h_ch_persistence_blend{,_stage2}`, `h_cl_linear_ramp_stage2`, `h_cl_persistence_blend`, `h_dp_residual_persistence_stage2`, `h_full_regime_sweep`, `h_l3_asymmetric_stage1`, `h_t_l2_regression_stage1`, `h_wd_persistence_gate_stage1{,2}`, `h_wg_l3_regression_stage1`, `h_wg_residual_persistence_stage2`, `h_ws_l3_regression_stage1`. New windows: A=[07-08→07-23], B=[06-23→07-08], FULL=[06-23→07-23]. Re-ran digest — all fossil warnings cleared; SHIP-eligible set unchanged (h_cloud_disagreement_orthogonality, h_pre_front_orthogonality, h_wind_shift_rate_orthogonality, walkforward_l3l4_validator); prior "Changed verdicts" (cluster_spread_orthogonality, h_dp_residual_persistence_stage1) both stabilized under fresh windows. **C1h narrow-promote gate confirmed CLEARED 14/7** — no code change (C1h already live since 2026-07-10 per confidence_layer.py:80 + `_C1H_CO_AXIS_GATE` whitelist), curated tables regenerated with fresh premium %'s. `c1h_curated.json` had 2 cosmetic verdict shifts in the `t` field (24-47h SHIP→SKIP, 12-23h MARGINAL→SKIP) — both were `always_skip: True` in the ortho gate and never fired. All other L2/L3/L4/C1 curated tables refreshed as part of the digest run (`c1_confidence_curated{,_v2}`, `c1d_curated`, `ch_persistence_gate_curated`, `cm_l3_asymmetric_skip_curated`, `dp_residual_persistence_curated`, `h_l4_add_candidates`, `lc_correction_table`, `pre_frontal_curated`, `sr_sea_breeze_lsr_curated`, `t_l2_skip_table_curated`, `wd_persistence_gate_curated`, `wg_l3_asymmetric_skip_curated`, `wg_l3_skip_table_curated`, `wg_residual_persistence_curated`, `ws_l3_asymmetric_skip_curated`, `ws_l3_skip_table_curated`).

</details>

<details>
<summary><strong>v0.6.373 • July 22, 2026</strong></summary>

- **Digest self-triage infrastructure — three structural fixes to `build_executive_summary.py` addressing the "morning digest keeps producing flip-worthy conclusions" pattern.** Motivated by today's session: h_hsf KILL diagnosed as artifact then walked back, r5_cove SHIP proposed as new work when r5_audit had already answered it 200 lines later in the same digest, MLC ★ COLLAPSE surfaced as fresh alert despite being a known-settled 06-30 seasonal signal.
  - **(1) Suppress-until registry** (`weather_collector/data/digest_suppress.json`). Entries `{tool, signal, suppress_until, reason, memory_ref}`. `check_suppression(tool, signal, verdict)` returns matching active entry. `marine_layer_anomaly_summary()` now returns `(line, suppression_or_None)`. When matched, alert routes to a new **"Suppressed (known — see memory; do not re-triage)"** section with reason + expiry + memory_ref visible instead of the top-of-digest alert slot. Seeded with MLC COLLAPSE suppression through 2026-08-06 (matches the anomaly detector's 21d baseline window rolling past the 06-30 break).
  - **(2) Companion-tool resolution** (`COMPANION_PAIRS` dict). Registered `r5_cove_analysis → r5_audit`, `h_dp_residual_persistence_stage1 → h_dp_residual_persistence_stage2`, `h_wg_residual_persistence_stage1 → h_wg_residual_persistence_stage2`. When both ran in the same digest, "New candidates" emits `RESOLVED SHIP/HOLD/KILL per <step2>` instead of listing Step 1 alone — kills the "aggregate says SHIP, cross-cut says HOLD, digest treats it as a task for the reader" pattern.
  - **(3) Population tags on thin-window-sensitive scripts.** `h_hsf_orthogonality.py` and `h_pre_front_orthogonality.py` now embed `[n=N passages, X% join → THIN|OK]` inline on the verdict line (THIN when passages < 15). Digest's existing verdict extractor picks it up automatically — no digest-side change needed. Verified today's runs: h_hsf `→ KILL ... [n=8 passages, 26% join → THIN]`, h_pre_front `→ PROMOTE ... [n=8 passages, 23% join → THIN]`. This makes the thin-population caveat impossible to miss in morning triage instead of a fact one has to remember to check.
  - **Combined effect:** tomorrow's morning digest is meaningfully more self-triaging. MLC won't re-alert until 08-06. r5_cove will emit as RESOLVED HOLD alongside r5_audit's verdict. h_hsf's THIN tag makes the passage count impossible to overlook when reading a KILL/PROMOTE claim. See [[feedback_check_contamination_before_acting]], [[feedback_measure_against_live_stack_baseline]].

</details>

<details>
<summary><strong>v0.6.372d • July 22, 2026</strong></summary>

- **dp residual persistence — Stage 2 preview scaffolded, 8 SHIP / 2 MARGIN / 26 SKIP / 1 THIN.** Digest AM promoted `h_dp_residual_persistence_stage1` from STAGE 1 MARGINAL (07-21 halves sign-flip) to STAGE 1 PROMOTE (test +11.14% MAE, 4/6 regime WIN, halves both positive at +3.81% / +4.74%). Natural next step per [[feedback_hypothesis_promotion_pipeline]] is Stage 2 per-cell verification with halves-stability requirement. New script `analysis/h_dp_residual_persistence_stage2.py` — copy-and-swap from `h_wg_residual_persistence_stage2.py` (identical machinery, FIELD="dp", output paths + units updated). Same windows as wg (WIN_A 07-04→07-19, WIN_B 06-19→07-04, FULL 06-19→07-19); MIN_N_CELL=200, MAE_IMPROVE_FLOOR_PCT=3.0. **Clean cluster: all 8 SHIP cells at 6-47h leads; zero SHIP at 0-5h across all 9 regimes** (prior-day-at-hour residual too coarse for short-lead dp — matches physical intuition). Best cells sw_flow 24-47h (−18.46%), sw_flow 12-23h (−16.87%), frontal 24-47h (−14.09%), sw_flow 6-11h (−12.03%), pre_frontal 24-47h (−10.73%). MARGIN: nw_flow 12-23h, se_flow 12-23h. Emitted `weather_collector/data/dp_residual_persistence_curated.json` as preview only — NOT wired to production. Next: Stage 3 processor on the wg_residual_persistence template with ENABLED=False (not today). Full details in `project_dp_residual_persistence` memory.

</details>

<details>
<summary><strong>v0.6.372c • July 22, 2026</strong></summary>

- **r5_cove_analysis SHIP verdict changed to PATTERN-STABLE — cross-cut resolution (RESOLVED HOLD).** Digest AM showed `r5_cove_analysis` VERDICT: SHIP + "flip cove_correction.ENABLED = True", listed under "aggregate-only tools — cross-cut required." Traced to two-tool disagreement: `r5_cove_analysis.py` is Step 1 (measurement stability on the raw gradient log), `r5_audit.py` is Step 2 (held-out MAE cross-cut vs L4) — same digest showed r5_audit HOLD at every regime × band cell: **R5+L4 = baseline +0.00% on 92,828 held-out pairs, R5-alone is worse everywhere (−0.22% to −33.68%).** L2 station weighting already absorbs 100% of the gradient signal — matches [[project_l6_l2_double_counting_hypothesis]] and the dormant state of `cove_correction.py` (both branches disabled 07-01, top-level flag OFF since 07-03). Changed r5_cove_analysis.py verdict wording so the aggregate PASS on the raw gradient no longer claims "flip cove_correction.ENABLED = True" as a ship decision it isn't equipped to make — the new PATTERN-STABLE line explicitly defers to r5_audit and cites the L2 double-count. Should stop the digest's "changed verdicts" section from re-flagging this as a fresh SHIP flip in future runs.

</details>

<details>
<summary><strong>v0.6.372b • July 22, 2026</strong></summary>

- **Ported matched-regime baseline fix to `h_pre_front_orthogonality.py` — PROMOTE holds, SHIP set drifts 5→7.** Same-shape fix as v0.6.372a: sums keyed by regime as 6th dimension (previously 5-dim `(field, band, A, B, C)`), `matched_ratio(pre_filter, base_filter)` helper computes per-regime pre/base ratios with MIN_N_REG=30 and aggregates as weighted mean weighted by `min(n_pre, n_base)`, cell needs ≥2 regimes contributing. Ran on same 8-passage window: **vs C1a 8 ORTHO / 14 REDUND / 2 CONFOUND / 8 AMBIG; vs C1e 8 ORTHO / 14 REDUND / 10 AMBIG; overall 16 orthogonal → PROMOTE holds.** Regenerated `weather_collector/data/pre_frontal_curated.json` — SHIP cells went 5 → **7**: `ch 0-5h`, `ch 6-11h`, `cl 12-23h`, `cl 24-47h`, `cm 6-11h`, `cm 12-23h`, `cm 24-47h` (new adds: cl 12-23h, cl 24-47h). **Opposite outcome from h_hsf** (where the fix left the KILL standing) — pre-frontal really is orthogonal to both C1a and C1e. `corrections_debug.html` line 897 updated (5→7 SHIP + Jaccard-reset note). **Foreseeable side effect:** Jaccard 5/7 = 0.71 &lt; 0.8 threshold → narrow-promote gate walker for pre-frontal restarts at 1/7 tomorrow (was 1/7 today on the pre-fix set). Earliest Stage 3 wire is now 07-29 on the new 7-cell baseline. Note: `h_c1h_orthogonality.py` uses a similar pattern (vs C1f and vs C1e) and likely deserves the same fix eventually — deferred, since C1h ships freely on `cl × 3 bands` which was consistent under matched-regime for cl in both scripts today.

</details>

<details>
<summary><strong>v0.6.372a • July 22, 2026</strong></summary>

- **h_hsf_orthogonality matched-regime baseline fix — KILL survives, morning artifact claim walked back.** After v0.6.372 diagnosed the AM KILL as a global-baseline Simpson's-paradox artifact, implemented the matched-regime fix (`analysis/h_hsf_orthogonality.py` — sums keyed by regime as 5th dimension; `matched_ratio()` computes per-regime post/baseline ratios with MIN_N_REG=30 and aggregates as weighted mean weighted by `min(n_post, n_base)`; 2-regime minimum for a cell to score). Re-ran on the same 8-passage window: **32 REDUND / 1 ORTHO / 3 AMBIG (was 33/2/1). KILL survives the fix.** Only `cl 24-47h` stays firmly ORTHO (2.18× stable, 2.03× trans, 7 regimes contributing) as genuine independent signal from C1a. `cl 6-11h` flipped 0.90×→1.70× AMBIG (regime-mixing WAS masking signal on that one cell). All other 33 cells REDUND in both views. `corrections_debug.html` line 949 updated from "SUSPENDED — window artifact, NOT real reversal" to "KILL survives matched-regime fix" — morning "not real" language was wrong given the stronger evidence now on record. `project_c1e_hsf_kill_investigation.md` extended with the fix result + revised re-audit trigger (unwire C1e except for cl 24-47h ONLY if matched-regime KILL still fires at ≥15 passages; do NOT unwire preemptively). C1e stays wired for now — thin passage count (8) still argues against acting.

</details>

<details>
<summary><strong>v0.6.372 • July 22, 2026</strong></summary>

- **hsf narrow-cl watch SUSPENDED — window artifact, not real KILL.** 07-22 digest flipped `h_hsf_orthogonality` PROMOTE→KILL (33 REDUND / 2 ORTHO / 1 AMBIG, "just C1a re-skinned"). Traced to data: only 8 frontal passages in the 30-day window (all clustered 07-07→07-21), 26% pair-log join rate (74% of pairs pre-date the passage log's earliest event), most post/baseline ratios inverted (`post < baseline` — e.g. ch 0-5h post/baseline 0.30×). In a sea-breeze-dominated summer window, "baseline" mixes elevated-error regimes while "post" happens to catch cleaner-than-typical cold-front-cleared airmasses, so the script's `post/baseline ≥ 1.30` verdict rule inverts for artifact reasons — same failure shape as the 07-21 pp_brier retraction (30-day window mixing states). Also ruled out Lc-absorption theory: pair-log `error` field carries L1 semantics per <code>feedback_measure_against_live_stack_baseline</code>, unchanged by Lc 07-17 ship. Verified C1e is load-bearing before considering any unwiring: `c1_confidence_curated_v2.json`'s `by_axes` table has 47 five-tuple keys `spread_q::pt_label::trans::c1f::hsf_group` and `confidence_layer.py::stamp_confidence` composes the 5-tuple axis_key on every tick, falling through to legacy fallback when hsf is None. **Call: C1e stays wired. `corrections_debug.html` line 949 patched — hsf narrow-cl watch flipped from "day 1/7" to "SUSPENDED 07-22" with the artifact reasoning so today's KILL doesn't fossilize as a real reversal.** Retest trigger: passage count in window ≥ 15 OR after `h_hsf_orthogonality.py` gets a matched-regime-baseline fix (added to the hypothesis backlog's new Method-fix section; same pattern likely applies to `h_pre_front_orthogonality.py`).

</details>

<details>
<summary><strong>v0.6.371b • July 21, 2026</strong></summary>

- **wd L2 line missing on accuracy-over-time chart — L1_ONLY branch fix.** `analysis/mae_over_time.py:51` classifies `L1_ONLY_FIELDS = {"wd"}` — correct pre-07-20, but v0.6.368a shipped the wd L2 blend and v0.6.367 wired the joiner to emit `error_l2` for wd. `compute_fresh_rollup` was still routing wd through the L1_ONLY branch that only reads the top-level `error` field — never touched `error_l2`. Data existed in the pair log; the accumulator ignored it. Compounding: `FIELD_LAYERS.wd` had l2 as isProd (v0.6.371 left wd alone since pre-wdp wd has no applied_layer stamps → no prod_real), so without l2 data neither L2 nor Prod line rendered. Fix: extend the L1_ONLY branch to also emit L2 for wd when `error_l2` is present (5 lines). Verified locally: wd.l2 now populates n=2 days (07-20 + 07-21, matching v0.6.368a ship). `layersForField` needs ≥3 non-null days to render, so the L2 line appears on the debug page starting the 07-22 digest run. Post-wdp on 07-27, `error_wdp` gets added to the same branch per <code>docs/preflight/wdp_ship_patches.md</code> Site 7 (option (a)) — prod_real for wd starts populating then.

</details>

<details>
<summary><strong>v0.6.371a • July 21, 2026</strong></summary>

- **Debug page Rule 5 sweep for v0.6.371 + 07-21 calendar/counter refresh.** Rolled Recent activity to 07-21 (07-20 demoted from "today"; 07-18/17/16/15 rolled off to CHANGELOG per the rolling 3-day window rule). Added the 07-21 day header + 4 entries: v0.6.371 (real per-row Prod trajectory), l2_lead_decay_fit ZeroDivisionError guard, wdp ship pre-mortem doc, this sweep. Advanced 14-day post-ship watch counters across the "Post-ship watches" block: Lc 4/14→5/14 through 07-31, chp 2/14→3/14 through 08-02, wd L2 blend 1/14→2/14 through 08-03, ws L3 asymmetric additive 1/14→2/14 through 08-03. Updated "07-21 flip earliest" language to 07-27 across ~10 sites: wg residual persistence (07-20 evening re-run: 10 SHIP / 4 MARGIN / 22 SKIP; Jaccard 0.45 vs 07-14 forced 07-21 flip HOLD; new 10-cell baseline day 1/7 today), wg L3 skip-table (same 7-window promotion gate), ws L3 hardcode-REPLACEMENT (additive already live 07-20 v0.6.370; replacement still deferred). Tue 07-21 calendar column boxes updated to reflect actual outcomes (v0.6.371 SHIPPED + 3 flips HELD to 07-27). Added new "Mon 07-27 — wdp flip?" Upcoming decision. Advanced C1h/C1d language: Jaccard walker v0.6.362 reports C1h GATE CLEARED 12/7 days, C1d 1/7; earliest ship for both still gated on C1 Stage 4 07-25 re-check. Pipeline state header advanced 2026-07-20 → 2026-07-21. Live-layer gate wg residual line advanced day 6/7 → day 1/7 on new baseline. No code changes this bump.

</details>

<details>
<summary><strong>v0.6.371 • July 21, 2026</strong></summary>

- **Real per-row Prod trajectory for accuracy-over-time chart — closes the v0.6.370a honesty gap.** Backend: `analysis/mae_over_time.py` gains a `prod_real` accumulator that reads `error_{applied_layer}` per pair-log row (parallel to `decay_fit.py:712-729` for per-band tables). Emits `series[field]["prod_real"][day] = {n, mae, rmse, bias, brier}` whenever the day's applied-layer sample clears the same `MIN_N_PER_DAY=200` gate as strict layers. Independent of the STRICT completeness gate — contributes even on rows that lack `error_l2/l3/l4`, as long as `applied_layer` is stamped. Pre-v0.6.269 rows without stamps are skipped; they age out of the 30-day pair log by 07-31. Frontend: `corrections_debug.html` LAYER_STYLE gains a `prod_real` entry (yellow #e0d472, width 2.0 to visually own the "final applied" line); FIELD_LAYERS swaps `isProd:true` from specialists (Lsr on sr; Lc on cc/cm; chp on ch; clp on cl) and from the old `"prod"` key (t/h/dp/ws/wg/pp/pr/pa) over to `prod_real`. Specialists demote to intermediate width (1.25) — still visible on the chart as gate-fired-only lines, useful for isolating each specialist's per-lead lift during 14-day watches. `wd` is intentionally left alone this ship — no applied_layer stamps until wdp ships 07-27 (preflight enumerates the wd swap at that ship). Old `"prod"` key still emitted for backward-compat; frontend ignores it. Section 5.1 two-lenses text restored to the truthful "both views ARE real per-row aggregates" phrasing (was softened in v0.6.370a). Accuracy-over-time meta-note updated with the v0.6.371 provenance. Post-ship verification: run `python3 analysis/mae_over_time.py` locally, confirm `series[fld]["prod_real"]` populates on 12+ non-wd fields, load debug page and verify the Prod line is DIFFERENT from the specialist line on cc/cl/sr/cm/ch (specialist averages gate-fired-only, prod_real averages every applied_layer stamp). For always-fires specialists (Lc on cc/cm) Prod should ≈ Lc — correctness check.

</details>

<details>
<summary><strong>v0.6.370a • July 20, 2026</strong></summary>

- **Debug page Rule 5 sweep for v0.6.369 + v0.6.370.** Seven edits across `corrections_debug.html`: (a) **Recent activity 07-20** — counter bumped "7 ships + 2 dashboards + 1 kill" → "9 ships + 2 dashboards + 1 kill"; appended v0.6.368b, v0.6.369, v0.6.370 with one-line summaries (chp/clp first honest reads and ws 40-net-new SKIPs). (b) **L3 asymmetric fc-bin candidate header** — status chip updated to "wg WIRED + LIVE 07-20 v0.6.366 · ws WIRED ADDITIVE 07-20 v0.6.370 · cm null (0 SKIP cells)". (c) **L3 asymmetric ws-deferred block** — rewritten to describe additive wire done (v0.6.370) + hardcode-replacement still deferred until 07-27; explains why additive is safe (apply loop checks old hardcode first at decay_apply.py:641, only reaches asymmetric at line 646 if hardcode didn't fire). (d) **L3 asymmetric ws swap-in earliest-ship entry** — retitled from "ws swap-in" to "ws hardcode REPLACEMENT" to distinguish from the additive wire that just landed. (e) **Historical v0.6.366 SHIP entry** — appended in-place update pointing to v0.6.370. (f) **Applicability map L3/L3-skip bullet (line 1293)** — describes wg wired + ws wired additively + cm no-op; distinguishes additive wire from hardcode-replacement. (g) **Per-row applied-layer-stamping bullet (line 1299)** — added v0.6.369 addendum describing accumulator/emission loops extended to (l1..l6, chp, clp) + LAYER_LINES + _layerApplied changes; included the first honest chp/clp numbers vs Lc. (h) **Two-lenses layer-summary at line 1317** — softened false claim; the per-band tables' Production IS a real per-row aggregate (correct today), but the over-time chart's "prod" series is still `error_l4` bucketed with specialist-as-Prod overlay — real per-row Prod for over-time is a v0.6.371 ship (planned tomorrow: adds `prod_real` series to `mae_over_time.json`). No code changes this bump.

</details>

<details>
<summary><strong>v0.6.370 • July 20, 2026</strong></summary>

- **ws L3 asymmetric fc-bin SKIP wired — additive.** `_ASYMMETRIC_SKIP_PATHS` in `decay_apply.py:148` gains `("ws", "l3") → ws_l3_asymmetric_skip_curated.json`. Wire is **additive on top of** the existing hardcoded `SKIP_TABLE[("ws", "l3")] = [("ne_flow", 0, 48), ("sea_breeze", 0, 12)]` — the apply loop checks `_should_skip` (regime × lead_band) first at line 641 and only reaches `_should_skip_asymmetric` at line 646 if the old table did not fire. So the old hardcode always wins where they'd overlap; asymmetric only adds skips in *other* regimes/bands. Not the live-layer flip [[feedback_whitelist_promotion_gate]] governs — that would be REPLACING the old hardcode with asymmetric-only rules (could re-enable L3 in currently-skipped cells); deferred until 07-27 window-7. Curated JSON: 44 SKIP (regime, band, fc_quartile) cells from the 07-20 08:40 Stage 1 run. Overlap with the old ws hardcode blocks 4 → **40 net-new SKIP firings**, distributed 23 at lead-band 24-47, 15 at 12-23, 2 at 6-11. Concentrated at long leads where [[project_ws_l3_long_lead_regression]] flagged L3 as +20-31% worse than L2 — asymmetric fc-bin is now surgically excising those cells based on regime × fc quartile. Also: cm is **not wired** — Stage 1 emitted 0 SKIP cells for cm (fc-bin split produces no stable-halves L3 losers under the +3% hurt floor). Curated JSON exists but the map entry would be a no-op. Post-ship watch: 14-day per-lead-band MAE on ws through 2026-08-03; expected lift is at 12-47h where the new skips concentrate. Revert path: delete the `("ws", "l3")` entry from `_ASYMMETRIC_SKIP_PATHS`; behavior returns to pre-v0.6.370.

</details>

<details>
<summary><strong>v0.6.369 • July 20, 2026</strong></summary>

- **chp / clp per-layer attribution wiring — 3-site fix.** Both post-Lc persistence specialists (chp on ch, LIVE 2026-07-19 v0.6.358; clp on cl, LIVE 2026-07-19 v0.6.361) were silently absorbed into the Production series because the Fitter's per-layer accumulator and emission loops iterated only `("l1"..."l6")`. Pair rows carried `error_chp` and `error_clp` (via forecast_error_log.py v0.6.361) but nothing summed them; the debug page's `LAYER_LINES` and `_layerApplied()` didn't recognize the keys either. Production reflected chp/clp correctly via applied_layer stamping (decay_fit.py:712-729) — but there was no way to *see* chp's isolated per-lead lift during the 14-day watch. Exact [[feedback_specialist_attribution_wiring]] pattern; caught on day 2 of the chp watch. Fixes: (a) `decay_fit.py:685` accumulator loop extended to include chp/clp — no-ops harmlessly on non-owner rows since `error_chp`/`error_clp` are None there. (b) `decay_fit.py:1162` emission loop extended to same set — irrelevant fields emit all-None arrays, matching how l5/l6 already work for non-owner fields. (c) `corrections_debug.html:3443` — LAYER_LINES gains chp (green #4ad29a) + clp (light green #8cd278) entries. (d) `corrections_debug.html:3407-3425` — `_layerApplied()` adds `chp → ch` and `clp → cl` branches, mirroring how l5→sr and l6→cloud-fields already filter. First honest ch-persistence 14-day-watch read (with isolated chp series) lands after the next Fitter run.

</details>

<details>
<summary><strong>v0.6.368b • July 20, 2026</strong></summary>

- **Debug page Rule 5 sweep for v0.6.367 + v0.6.368/368a.** Updates across `corrections_debug.html`: (a) **wd pipeline row** — L1 → "L1 + L2 (wind_blend circular)"; description flipped from "raw HRRR only" to "L2 shipped 07-20 v0.6.368a" with first-tick verify numbers. (b) **wd persistence gate candidate block** — reframed from "first-ever wd correction" to "second wd correction candidate" (L2 already ships short-lead; persistence gate targets long-lead regime-transitions). Wiring status updated: wd first-class in anomaly_detector + h_persistence_skill + accuracy chart + mae_over_time + Fitter per-layer (v0.6.365b/d + v0.6.367); L2 blend live (v0.6.368a); remaining item is applied_layer stamping for the specialist flip. (c) **L2 Applicability table wd row** — flipped from "N/A — circular field, L2's linear math doesn't apply" to "SHIPPED — circular unit-vector blend solves the wrap-around." (d) **FIELD_LAYERS accuracy chart config** — wd goes from `raw-only isProd` to `[raw, l2 isProd]`. (e) **Group D refinements** — added two new entries: wd L2 (v0.6.368/368a) and joiner per-layer wd errors (v0.6.367). (f) **Recent activity 07-20** — count updated to "7 ships + 2 dashboards + 1 kill"; three new SHIP entries appended (v0.6.367, v0.6.368, v0.6.368a). (g) **Post-ship watches** — added wd L2 watch through 08-03, calling out the calm-floor guard as the most likely failure mode. (h) **L2 lead-decay chart** (`renderL2LeadDecay`) — line label updated from "Wind / Gust (linear 0–24h)" → "Wind speed / gust / dir (linear 0–24h)"; description note added explaining wd uses circular sin/cos on the same ramp. wd was already on the correct curve (same wind_blend code path) but the labels didn't reflect it. (i) **Last-curated stamp** advanced to v0.6.368b.

</details>

<details>
<summary><strong>v0.6.368a • July 20, 2026</strong></summary>

- **wd L2 blend hotfix — wrong field key.** v0.6.368 read `cur.get("wind_dir")` in `wind_blend.py` — but `weather_data["current"]` stores the field as `wind_direction` (see line 311 setter: `current["wind_direction"] = ...`). Confused with `obs_temp_log` where the column is named `wind_dir`. Result: `observed_dir` was always None post-deploy → `blend_dir` False → blend never fired → raw_wind_direction == wind_direction across all leads. Fixed by using the correct key. Re-verified against production-shaped data (raw=[166,146,...], obs=207) → blend produces [207,205,202,199,197,194] as expected.

</details>

<details>
<summary><strong>v0.6.368 • July 20, 2026</strong></summary>

- **wd added to L2 — circular unit-vector blend in `wind_blend.py`.** Same architecture as ws/wg L2 (linear decay-blend of current obs into first `BLEND_HOURS=24` of hourly fc), but circular math: convert both obs wd and fc wd to `(sin, cos)`, weighted unit-vector average, `atan2` back to degrees, wrap to `[0, 360)`. Linear weighted-average would produce garbage on wraparound (avg of 350° + 10° = 180° instead of 0°). Calm-floor guard `WIND_DIR_MIN_SPEED = 3.0 mph` skips cells where both obs and fc wind speed are below the floor — direction is physically undefined at calm speeds and blending would inject junk. Consensus obs wd (`weather_data["current"]["wind_dir"]`) has been collected/stored for months; this ship just wires it into the pipeline side of L2. Post-blend `raw_wind_direction` preserved for the debug page's Raw baseline. Also updated `forecast_snapshot.py`'s wd layers map — `l2` was hardcoded to `raw_wind_direction` (correct pre-v0.6.368, wrong now); flipped to `hourly["wind_direction"]` so the Fitter's `per_layer_mae_by_lead["wd"]["l2"]` starts measuring the blended value against ground truth. Verified via 6 unit tests (wraparound, decay taper, calm floor both-directions, no-obs no-op, raw preservation, opposing-direction full-obs-weight).

</details>

<details>
<summary><strong>v0.6.367 • July 20, 2026</strong></summary>

- **Fitter now emits real per-layer wd MAE/RMSE/bias — wd appears in WINNING FIELDS tile.** The joiner was writing wd pairs on a dedicated code path (`forecast_error_log.py:184-206`) that produced `error` + `error_sin` + `error_cos` but skipped the per-layer loop that every other field ran, so `error_l1`..`error_l4` were absent. Downstream the Fitter saw those as `None` and left `per_layer_mae_by_lead["wd"]` all-null; the debug page's WINNING FIELDS scorecard silently dropped wd via its `if (rawMae == null) continue` filter. Fixed by adding the layer loop inside the wd branch using `_circular_diff_deg` (circular angular diff, wrap-aware) for the per-layer errors. wd has no correction layers today so error_l1..error_l4 are all identical circular diffs → Prod = raw → wd will land in the ○ flat row of the scorecard (correct — "no attempt made"). Once `wd_persistence_gate` flips (~07-27) or any future L2/L3/L4 wd correction lands, a real Δ will surface automatically. Frontend requires no change — the tile picks wd up as soon as the Fitter's next cycle (03:07 or 15:07 EDT) has enough post-fix pairs to clear the n≥30 floor.

</details>

<details>
<summary><strong>v0.6.366a • July 20, 2026</strong></summary>

- **Debug page Rule 5 sweep for v0.6.366.** Targeted updates across `corrections_debug.html`: (a) **Gate candidates block** — L3 asymmetric fc-bin skip row flipped Stage 1 preview → SHIPPED for wg (green border, ✓ WIRED + LIVE 07-20 v0.6.366, 48 SKIP cells, first-tick verify note); ws sub-note explains blanket-vs-asymmetric conflict deferring the swap to 07-27. (b) **Calendar Mon 07-27** entry rewritten from "L3 asymmetric earliest ship, blocked on refactor" → "ws swap-in earliest ship, wg already live." (c) **Recent activity 07-20** — daily summary count updated to "4 ships + 1 dashboard + 1 kill", v0.6.366 added to list; new SHIP entry describes the wiring, ws deferral rationale, and first-tick verify. (d) **Open architectural questions** — SKIP_TABLE architecture description extended with v0.6.366 fc-bin dimension clause. (e) **Last-curated** stamp advanced 07-20 v0.6.365c → v0.6.366.

</details>

<details>
<summary><strong>v0.6.366 • July 20, 2026</strong></summary>

- **L3 asymmetric fc-bin skip machinery — wg wired.** Extends `decay_apply.py`'s `SKIP_TABLE` with a per-cell fc-magnitude dimension. Stage 1 analysis (07-20 `h_l3_asymmetric_stage1.py`) showed L3 is a mean-bias subtraction that helps on over-forecast rows (high raw fc) and hurts on under-forecast rows (low raw fc); splitting fc into per-(regime, band) quartiles isolates 92 SKIP cells across wg + ws where L3 stably loses. **This ship wires the machinery for wg only (48 SKIP cells).** New `_should_skip_asymmetric()` reads `weather_collector/data/wg_l3_asymmetric_skip_curated.json` and looks up (regime, band, fc-bin) using `hourly["raw_wind_gusts"]` (preserved by `wind_blend.py` before decay). Fail-safe: missing raw fc, unknown regime, or no cuts for cell → do not skip; never turns L3 OFF where the existing hardcoded `SKIP_TABLE` said ON. `decay_meta.skip_table_l3_asymmetric_cells_skipped` counter added for the debug page. `describe_applicability()` extended to name `SKIP_TABLE_ASYMMETRIC` in the wg entry. **ws deferred** — its two existing blanket entries (`ne_flow` all, `sea_breeze 0-11`) disagree with the newer asymmetric grid at exactly those cells (asymmetric says KEEP where hardcoded says SKIP). Replacing them is a live-layer flip that needs the standing 7-window whitelist promotion gate; earliest swap-in 07-27 once the streak clears.

</details>

<details>
<summary><strong>v0.6.365d • July 20, 2026</strong></summary>

- **wd field promotion — accuracy chart + pipeline table.** Followed on 07-20 v0.6.365b's promotion of wd in the analysis scripts by making wd visible on the debug page's user-facing views. (a) **Current pipeline state table** — added a wd row: raw HRRR only today (no L2/L3/L4), circular MAE 61°, with in-flight persistence-gate candidate context (5 SHIP + 1 MARGIN cells, earliest flip 07-27). Header date advanced 07-19 → 07-20. (b) **Accuracy chart** — added wd to `FIELD_LABELS` (dropdown label "Wind direction (°)") and `FIELD_LAYERS` (raw-only, marked isProd — placeholder for the future specialist layer). (c) **`analysis/mae_over_time.py`** — added wd to `FIELDS` + new `L1_ONLY_FIELDS = {"wd"}` path that routes the pair log's top-level `error` field (already circular-angular for wd) to the "raw" layer. Re-ran the script; published JSON now carries 14 fields (was 13), 35 days total, wd data available for the chart. (d) **L2 Applicability table** — added a wd row with N/A verdict (circular field; L2's linear additive math doesn't apply; would need sin/cos vector-mean to make sense).

</details>

<details>
<summary><strong>v0.6.365c • July 20, 2026</strong></summary>

- **Debug page Rule 5 sweep for today's ships.** Targeted updates across `corrections_debug.html` (not a rewrite): (a) **LSR RETIRE-vs-AGREE puzzle resolved.** Removed the "investigation queued" language across two sites (course-of-action list + Lsr layer's Open watch note); replaced with the resolution — divergence-report claim was sourced from `l5_solar_analysis` (candidate script, not live gate), fixed in v0.6.365 by routing through the live Fitter cycle gate history. (b) **Added wd persistence gate candidate block** under Gate candidates — Stage 2 preview + processor drafted 07-20, ENABLED=False, day 1/7, 5 SHIP + 1 MARGIN cells with composed-gate MAE reductions −4% to −26%. (c) **Added L3 asymmetric fc-bin candidate block** — Stage 1 preview 07-20, 92 SKIP cells across wg + ws, wiring blocked on `decay_apply.py` SKIP_TABLE fc-bin refactor. (d) **Calendar** — added Mon 07-27 entries for wd persistence gate + L3 asymmetric earliest-flip. (e) **Recent activity** — 07-19 rolled off "today", 07-20 added with 3 SHIP + 1 KILL entries (v0.6.365 / .365a / .365b). Last-curated stamp advanced to 07-20 v0.6.365c.

</details>

<details>
<summary><strong>v0.6.365b • July 20, 2026</strong></summary>

- **Promote `wd` to first-class field in anomaly_detector + h_persistence_skill.** Both scripts previously excluded wd because it's circular (359° and 1° are 2° apart, not 358°) and linear-MAE math produces nonsense. Now wd is in the field roster with a `CIRCULAR_FIELDS = {"wd"}` guard: linear fc_mean / quartile bin-shift triggers are skipped (they'd false-fire on wraparound), while MAE + bias-shift use the pair log's already-circular `error` field. h_persistence_skill uses `angular_diff` for wd err computation. Two useful signals now show: (a) anomaly_detector: wd MAE 61°→48° (−21.7%) verdict CLEAN. (b) h_persistence_skill: **wd 0-5h BEHIND** (persistence 50° beats L1 56°), 6-47h ADDS VALUE — meta-confirmation that yesterday's wd_persistence_gate targets the right band. Prep work for shipping the gate 6 days from now when the 7-day narrow-promote counter clears. Remaining wd-promotion touchpoints (mae_over_time, applied_layer_audit, decay_tau_tuning) skipped for now — most either don't apply to wd until it has correction layers, or need larger per-script refactors.

</details>

<details>
<summary><strong>v0.6.365a • July 20, 2026</strong></summary>

- **cc-sat correction killed same-day + cleanup.** The 80-SHIP-cell finding from v0.6.365 was 80% a rediscovery of Lc. The Stage 1 script measured Δ against the pair log's top-level `forecast` field, which carries L1 semantics for cloud fields even after Lc shipped 07-17. Real bias post-Lc on the same rows: ch +5pp, cm +7pp, cl −29pp (Lc slightly over-corrects). Regime-conditional cl alternative failed halves check (Δ swings 14-57pp across the 06-30 mixture seam) — Lc's fc_cl-binned approach wins on all-time training data. Deleted `analysis/h_rh_saturation_stage1.py` and the three orphan `<field>_cc_sat_correction_curated.json` files. Saved lesson to memory as [[feedback_measure_against_live_stack_baseline]]: when measuring a NEW candidate correction's gain, use the highest currently-applied layer's `forecast_lN` key as baseline, not the flat `forecast` field. Prevention checklist banked. One narrow survivor flagged for future work: pre_frontal 0-5 cl (fog-during-front-approach pattern where Lc under-corrects due to fc_cl bin misclassification).

</details>

<details>
<summary><strong>v0.6.365 • July 20, 2026</strong></summary>

- **Divergence report LSR bug fix + three novel Stage 1 findings.** (a) **Fix:** LSR_ENABLED claim in `build_executive_summary.py:787` was sourced from `l5_solar_analysis` verdict — a script that tests a CANDIDATE regime-only refinement, not the live hourly Lsr. Its HOLD verdict was falsely rendered as "READY to disable" in the divergence table for months while the live Fitter emitted SHIP every 12h. Fixed by routing `_claim_lsr_enabled()` through `.cache_l5_gate_history.json` (the same source the trajectory renderer uses). See [[feedback_divergence_claim_mismatch]]. (b) **wd persistence gate — Stage 1 + Stage 2 with predicted-transition fire signal.** `state_curr.regime != state_fc.regime[lead]` at forecast time triggers persistence-of-obs override. 5 SHIP + 1 MARGIN cells, halves-verified. Overall composed-gate MAE reductions −4% to **−26%** (sw_flow 0-5). Signal precision 60% / recall 81%. Processor `wd_persistence_gate.py` drafted ENABLED=False, awaiting 7-day narrow-promote gate. (c) **L3 asymmetric fc-bin skip.** Hypothesis: L3 is a mean-bias subtraction, helps when raw fc is above training mean (Q3-Q4), hurts below (Q1-Q2). Confirmed with monotone gradient: wg 73%→45%→21%→6% SKIP concentration; ws 52%→9%; cm 0 (gap too small). **92 SKIP cells** across wg + ws. Wiring requires extending `decay_apply.py` SKIP_TABLE to accept an fc_bin dimension. (d) **CC-saturation additive correction.** At `state_fc.cloud_cover ≥ 80%` (proxy for RH-saturation since state_fc lacks humidity), model over-predicts individual layer forecasts by 50-70pp on average. Additive Δ correction gets **+40-79% MAE reduction**, cross-fit halves-stable. **80 SHIP cells** across cl (19) / cm (29) / ch (32 — every non-THIN cell). Magnitude is huge; sanity-check pending. All four new analysis scripts (`h_wd_persistence_gate_stage1/2.py`, `h_l3_asymmetric_stage1.py`, `h_rh_saturation_stage1.py`) auto-run in tomorrow's digest via `run_digest.sh`.

</details>

<details>
<summary><strong>v0.6.364 • July 19, 2026</strong></summary>

- **SHIP-ELIGIBLE surfaces sustained promotes, not just today's bucket transitions.** Previously the SHIP-ELIGIBLE section iterated `promotes_new` (scripts that flipped INTO promote bucket today). A ship-resolution script that transitioned days or weeks ago and stayed in promote bucket never re-entered `promotes_new` and thus never surfaced in ship-eligible even after clearing the 7-day streak + multi-tool gate. Same class of brittleness as v0.6.362's exact-match cell-set walker but on the script-level walker. Fix: iterate `all_promote_ship_res` (all promote-bucket ship-resolution scripts) instead. **Four sustained signals surface today for the first time:** `h_cloud_disagreement_orthogonality` (C1d) at 16/7 days, `h_pre_front_orthogonality` at 23/7 days, `walkforward_l3l4_validator` at 25/7 days (all three cleared and gated on other conditions — Stage 4 audit, cell-set stability, dropping wg/ws — so none auto-flip), plus `h_wind_shift_rate_orthogonality` at 6/7 days now visible in "still confirming." Pattern reinforces [[feedback_streak_walker_robustness]]: streak walkers built on transition-only detection miss sustained signals.

</details>

<details>
<summary><strong>v0.6.363 • July 19, 2026</strong></summary>

- **decay_tau_tuning: extend to pp + document that the pp override is inert.** Answering the "shouldn't we extend the tuner before concluding we can't measure it?" question. Added `pp` to `FIELDS` in `analysis/decay_tau_tuning.py` with a label + rationale comment. First measurement: pp best-τ = 7 wins +13.7% vs τ=14 among decay options — but **raw baseline (7.391 MAE) beats every decay-τ option (best τ=7 = 9.924, +34% worse than raw)**. Any decay-τ bias correction hurts pp on MAE. Verified this is a moot finding for production: `decay_apply.py:76-80` excludes pp from L3_FIELDS and L4_FIELDS, `L3_BRIER_FIELDS = {"pp"}` is only an audit-suppression flag, and pair-log rows confirm `applied_layer:"l1"` for pp. So `TAU_DAYS_BY_FIELD["pp"] = 28` in `decay_fit.py` is INERT — it only affects the Fitter's reported per_layer_mae for pp (analysis/reporting), not user-visible forecasts. Annotated the config entry accordingly rather than removing it. The lasting value: pp is now permanently measured in the daily digest, so any future proposal to actually APPLY bias correction to pp will be gated by "does the tuner say correction helps vs baseline?" — currently no.

</details>

<details>
<summary><strong>v0.6.362a • July 19, 2026</strong></summary>

- **Correction: pp τ=28 override has been unvalidated since 2026-06-21, not a "revert candidate."** Earlier I told Joe tomorrow's list included a "pp τ=28 revert check" — that was a misread. The `decay_tau_tuning.py` summary I quoted was for pa (precip amount), not pp (precip probability). Reviewed the tuner: `FIELDS = ["t", "dp", "h", "ws", "wg", "cc", "sr", "pr", "pa"]` at line 45 — **pp is excluded entirely** because it's Brier-native rather than MAE-decay-fit. So `TAU_DAYS_BY_FIELD["pp"] = 28` has been shipped for ~30 days without a single daily re-validation. Not a bug per se (the tuner design predates the pp override) but a latent gap worth naming. Booked to 07-20 as an open question: extend the tuner with a pp-specific Brier-decomposition τ scan, accept the fire-and-forget config, or revert on the argument "we can't measure it, don't trust it." Debug page and project_todo memory corrected accordingly.

</details>

<details>
<summary><strong>v0.6.362 • July 19, 2026</strong></summary>

- **Jaccard-similarity streak walker — uncorks C1h + C1d GATE CLEARED (hidden by exact-match for 10 days).** Replaces `build_executive_summary.py`'s exact-identity claim comparison (`c == today_claim`) with Jaccard similarity ≥ 0.8. Fixes the brittleness that caused three false readings today: h/l4 fossil catch (Jaccard = 0 → correctly resets), pre-frontal same-day 5-cell shuffle with 2 changed cells (Jaccard = 3/7 ≈ 0.43 → correctly stays reset), and — the smoke-test win — **C1h and C1d both flip from ⏳ 5/7 and 1/7 to ✓ GATE CLEARED (10/7 days each, oldest match 2026-07-10-14:21)**. The "in-window SHIP-set churn" reports since 07-10 were single-cell borderline drift the exact-match walker was penalising; both axes have been structurally stable the whole time. Threshold picked at 0.8 to allow single-cell drift in a 5-6 cell set (Jaccard ≥ 0.83) but not two-cell drift (Jaccard ≤ 0.6). Also documented `_claim_match()` helper with in-file rationale. Debug page counter sites updated across 4 locations (C1h + C1d tri-column narrow-promote sections + upcoming-decisions rows). No collector effects — analysis-side only.

</details>

<details>
<summary><strong>v0.6.361a • July 19, 2026</strong></summary>

- **Debug-page calendar: 07-20 booked (streak-counter robustness pass) + cl linear-ramp / hsf watches added.** Post-analysis debug-page patch. Three findings today (h/l4 fossil catch, pre-frontal same-day reset 7/7 → 1/7, hsf verdict oscillation PROMOTE↔KILL↔PROMOTE) all trace to `build_executive_summary.py`'s streak walker requiring exact cell-identity match on borderline classifications. Booked as v0.6.362 for tomorrow: switch to Jaccard similarity ≥ 0.8 (preserves fossil detection while tolerating single-cell drift). Also added two new tracked hypotheses to Monday: cl linear-ramp Stage 2 watch day 1/7 (STRONG on refreshed windows, 15 SHIP cells at τ=36 — different mechanism from cl_persistence_short_lead; potentially supersedes it), and hsf narrow-cl watch day 1/7 (only cl bands ORTHOGONAL vs C1a; narrow C1e-for-cl signal, not broad). Debug-page-only patch.

</details>

<details>
<summary><strong>v0.6.361 • July 19, 2026</strong></summary>

- **Pair-log schema extension for post-Lc specialists (ch_persistence_gate, cl_persistence).** Ship 2 of the accuracy-chart attribution work started in v0.6.360. Splits the currently-mixed Lc/persistence signal into two distinct lines. Backend changes: (1) `forecast_snapshot.py` — for ch/cl, the `l6` slot now points at `<field>_post_lc` with fallback to live (attributes Lc's output alone); added new `chp` (ch) and `clp` (cl) slots pointing at the live final (post-persistence). `_derive_applied_layer` walks the new specialist slots so `applied_layer` correctly stamps `chp`/`clp` on cells where the persistence gate fires. (2) `forecast_error_log.py` — iterates `("l1","l2","l3","l4","l5","l6","chp","clp")` when emitting per-layer error columns to the pair log. (3) `analysis/mae_over_time.py` — extends `PERMISSIVE_LAYER_KEYS` with `("chp","error_chp")` and `("clp","error_clp")`. (4) Frontend `corrections_debug.html` — extends `FIELD_LAYERS` and `LAYER_STYLE`; ch legend now specifies `Raw / L2 / L3 / L4 / Lc / ch-persist`, cl gets `Raw / L2 / Lc / cl-persist` (dormant → filtered out until it flips). `layersForField()` gained an isProd-promotion fallback so if the config's isProd layer got filtered out for insufficient coverage, the last remaining non-raw layer is promoted (rolling-mean overlay stays attached). Pair-log columns start accumulating today; specialist lines will appear on the chart around 2026-07-22 (once ≥3 days of coverage clear). No effect on non-cloud fields.

</details>

<details>
<summary><strong>v0.6.360 • July 19, 2026</strong></summary>

- **Accuracy over time chart: dynamic legend + specialist labels.** Two-part change. (1) `analysis/mae_over_time.py`: added permissive-mode aggregation for `l5` (Lsr, sr only) and `l6` (Lc for cc/cl/cm/ch; Lt for t) — these specialists contribute to per-layer MAE independently rather than dropping the pair when absent. Preserves the strict-comparability guarantee on raw/l2/l3/prod (all four required per pair). Regenerated `mae_over_time.json`: sr has 22 days of Lsr coverage; cc/cl/cm/ch have 2 days of Lc (since 07-17); t has 24 days of Lt (dormant). (2) Frontend `corrections_debug.html` chart refactor: replaced the fixed 4-line legend (Raw/L2/L3/Prod) with per-field `FIELD_LAYERS` config using specialist labels — sr shows "Raw / Lsr", cc shows "Raw / L2 / L4 / Lc", pa shows "Raw / Prod" only, etc. Legend also filters out any layer with fewer than 3 days of data in the payload (prevents dangling 1-2 point lines for layers just after ship). Rolling 7-day-mean overlays now attach to Raw and the field-specific `isProd:true` layer instead of always "prod." Ship-date annotation added for ch persistence LIVE 07-19. **Not yet visible:** post-Lc specialists (ch_persistence_gate, cl_persistence, wg_residual_persistence, Lsb) are still absorbed into the Lc line — the pair-log schema extension needed to attribute them separately ships next as v0.6.361+.

</details>

<details>
<summary><strong>v0.6.359a • July 19, 2026</strong></summary>

- **Post-digest-rerun debug page patch: cl HOLD + hsf discovery + pre-frontal reset.** Full digest rerun after v0.6.359 revealed three items that changed the story. (1) **cl narrow persistence gate HOLD.** Refreshed `h_cl_persistence_blend` (post-window-slide): "mixed — regime_gate doesn't cleanly beat baseline on halves check." Only 4/9 regimes SHIP at 0-5h (se_flow, ne_flow, calm, unknown). Design gate requires all 9 → OFF permanently per the 07-13 criterion. Updated ~7 sites in the debug page: earlier "flip candidate now" claims from v0.6.358a were premature (based on the sibling `h_cl_linear_ramp_stage2`'s STRONG verdict, but that's a different mechanism — linear ramp, not persistence blend). Linear ramp is worth separate Stage 2 investigation. (2) **NEW candidate: hsf (hours-since-front).** `h_hsf_orthogonality` flipped KILL → PROMOTE: "hours-since-front is independent of C1a AND C1e." hsf was killed 06-27 as C1a re-skin; the ortho check now disagrees. Streak 1/7 today; needs 6 more days of PROMOTE, then Stage 1. Added to course-of-action framing. (3) **Pre-frontal streak reset.** Narrow-promote counter went 7/7 CLEARED at 05:52 → 1/7 at 09:01 rerun despite still 5 SHIP cells — cell identity drifted between runs (borderline churn, not fossil). Streak restarts.

</details>

<details>
<summary><strong>v0.6.359 • July 19, 2026</strong></summary>

- **Digest stale-window guard (structural fossil-window fix).** New `stale_window_audit()` in `analysis/runlog/build_executive_summary.py` scans every `analysis/*.py` for date literals in `WIN_*` assignments; any script whose max window-date is more than 3 days behind today is flagged in a `⚠ STALE ANALYSIS WINDOWS` section at the top of DIGEST.txt exec summary, above SHIP-ELIGIBLE. This is the structural counterpart to yesterday's v0.6.358 fossil-window sweep: the ad-hoc slide caught 8 scripts by hand; this guard catches any future hardcoded date literals automatically, before a 7-day streak on stale data becomes a ship signal. First run immediately caught a 9th fossil I missed in the manual sweep — `h_cl_persistence_blend.py` — which was also slid to 07-19 windows. Post-slide the audit reports 0 stale scripts. See `[[feedback_fossil_windows]]`.

</details>

<details>
<summary><strong>v0.6.358a • July 19, 2026</strong></summary>

- **Debug page Rule 5 sweep to 07-19.** Full-page grep + update after v0.6.358 ship. ch persistence gate rows across ~10 sites: ENABLED=False · day 7/7 CLEARED → FLIPPED 07-19 · 14-day watch through 08-02, with the refreshed gate shape (27 SHIP, sw_flow/24-47 promoted). h/l4 narrow-add rows across ~5 sites: "on rails, day 6/7" → FOSSIL CAUGHT (streak reset 1/7, retest 07-26+). Counter advances 07-18 → 07-19: C1h day 5/7 (14 SHIP), C1d day 1/7 reset again (14 SHIP), pre-frontal 7/7 CLEARED, wg residual day 6/7, cl persistence day 7/7. Candidates table refreshed with post-shift SKIP-cell counts (ws L3 9, wg L3 12, wg residual 8 SHIP, cl linear ramp 15 SHIP STRONG). pa τ Applicability description updated with the revert. Recent activity 07-18 rolled off "today"; new v0.6.358 + v0.6.358a rows added. Course-of-action framing updated to reflect ch persistence LIVE + h/l4 held.

</details>

<details>
<summary><strong>v0.6.358 • July 19, 2026</strong></summary>

- **ch persistence gate LIVE + pa τ revert + fossil-window sweep.** Three coupled ships. (1) `ch_persistence_gate.ENABLED = True` — 7-day gate cleared and the refreshed-window rerun (26,543-row sw_flow/24-47 flipped SKIP→SHIP; calm/24-47 flipped SHIP→SKIP) held SHIP: 27 SHIP cells, regime_gate FULL MAE −29.53%, halves A −17.84% / B −37.61%, persist-only −30.51% LANDMARK still standing. Live gate shape now matches refreshed data, not this morning's stale digest. (2) `decay_fit.TAU_DAYS_BY_FIELD["pa"]` reverted (removed) — today's `decay_tau_tuning` verdict flipped IMPLEMENT → KEEP τ=14 GLOBAL with pa at only +0.9% vs τ=14 (was +5.9% yesterday), matching the 07-02 ws revert precedent: two consecutive reads disagreed at the ship threshold → original SHIP was noise. pa flags pp (+3.2%, also below floor) for next τ-audit day. (3) Fossil-window sweep: 8 analysis scripts had windows hardcoded to end 2026-07-11 (`h_ch_persistence_blend[_stage2].py`, `h_wg_residual_persistence_stage2.py`, `h_wg_l3_regression_stage1.py`, `h_ws_l3_regression_stage1.py`, `h_t_l2_regression_stage1.py`, `h_cl_linear_ramp_stage2.py`, `h_full_regime_sweep.py`). Slid all 8 windows forward to 07-19; the 7/7 divergence-report streaks had been reading a fossilized SHIP verdict for 8 days without ever testing against the MLC-collapse / cc-cluster distribution shift. Refresh caught one fossil: **h/l4 narrow-add collapsed from ✓ CLEARED (7/7, 2 SHIP cells) to ⏳ 1/7 (0 SHIP cells)** — would have shipped a garbage gate today. 07-21 candidates (wg L3, ws L3, wg residual persistence, cl linear ramp) all still ship on refreshed data with shifted/expanded gate shapes; cl linear ramp verdict got stronger MODERATE → STRONG (11 → 15 SHIP cells). Digest-side stale-window audit (a preventive guard so this can't recur silently) is deferred to v0.6.359.

</details>

<details>
<summary><strong>v0.6.357a • July 18, 2026</strong></summary>

- **Debug page Rule 5 sweep to 07-18 + h Stage 1 preview + digest cleanup.** Debug page updated across ~20 sites: (1) pa τ history + chart annotation + technical description reflect today's 42 → 7 drop; (2) C1 Stage 4 07-18 answered DEFERRED to 07-25 (cm mixture-check still DEGRADED); "re-audit 07-18" refs → 07-25 everywhere; (3) all narrow-promote + wired-gate counters advanced 07-16 → 07-18 (ch persistence day 7/7 CLEARED, wg residual day 5/7, cl persistence day 6/7, h/l4 narrow-add day 6/7, pre-frontal day 6/7, C1h day 4/7, C1d day 1/7 reset again with 13 SHIP cells); (4) walkforward "drop ws" now 9/7 (still HELD in favor of skip-table 07-21); (5) tide_hypothesis path updated to `.skip.py`; (6) Recent activity row added for today's ships. Added new analysis script `h_h_residual_persistence_stage1.py` (Stage 0 hit for h; Stage 1 preview MARGINAL — halves-fragile like wg).

</details>

<details>
<summary><strong>v0.6.357 • July 18, 2026</strong></summary>

- **Per-field decay τ: pa dropped 42 → 7.** `decay_tau_tuning` verdict IMPLEMENT PER-FIELD τ — pa gains +5.9% held-out MAE vs τ=14 at best τ=7, confirmed by 8/3 consecutive daily reads (streak gate cleared). Updated `decay_fit.py` `TAU_DAYS_BY_FIELD["pa"]` accordingly. Noted in the code comment that pa's best-τ has swung 28→42→7 across three reads and the streak gates set membership, not the specific τ value; re-validate weekly. Also removed the retired `tide_hypothesis.py` from the digest run list (renamed to `.skip.py`) — settled prior, NOAA data-source failure was generating a spurious FAIL each digest.

</details>

<details>
<summary><strong>v0.6.356c • July 17, 2026</strong></summary>


- **Correction-candidates table: drop shipped rows + reorder Stage 0 → Stage 3 + sr Engineering row updated.** Follow-on to v0.6.356b feedback: the 5 shipped (Stage 4 LIVE) rows are already documented in their own layer sections and Group D refinements, so leaving them in the candidates table was noise. Removed. Table now shows in-flight only: 6 Stage 3 gated + 4 Stage 1 + 1 Stage 0, ordered from earliest stage to latest so what's still open surfaces first. Section header clarifies Stage 4 items live elsewhere. Also updated the sr row in the Current-pipeline-state table (Engineering section): was "Unit-mismatch open · Shortwave shadow-log regime-specific," now reads "Unit-mismatch addressed, not yet live" with the Lsb Stage 3 wiring context — the sandbox stamps candidates but ENABLED=False, so production sr is still Lsr-on-direct-radiation until the 07-24 halves re-run gates the flip.

</details>

<details>
<summary><strong>v0.6.356b • July 17, 2026</strong></summary>

- **Correction-candidates table: Stage column + stage-ordered rows + sr Lsb row added + cl persistence Stage 3 status corrected + per-octant ws L2 07-17 result.** Section header "Stage 1 candidates" was stale — table always held candidates at every pipeline stage. Added a first "Stage" column with 4·LIVE (green) / 3·gated (yellow) / 2 (light orange) / 1 (light orange) / 0 (brown) labels; reordered rows top-down by stage so what's shipping surfaces above what's exploring. Added a stage-key legend to the section intro. **New row:** sr sea_breeze Lsb (Stage 3, shipped 07-17 v0.6.354, halves re-run 07-24). **Row corrected:** cl persistence gate (narrow) row was still labeled Stage 1+2 explored / HOLD — actually Stage 3 shipped 07-13 v0.6.330 in `cl_persistence_short_lead.py`, ENABLED=False, flip decision 07-19. **Row updated:** per-octant ws L2 additive now carries today's 07-17 re-read 1-of-3 verdict (⚠ SUGGESTIVE, 2 REAL + 2 WATCH + 4 flat). Footer summary re-counted: 5 Stage 4 live + 6 Stage 3 gated + 4 Stage 1 + 1 Stage 0.

</details>

<details>
<summary><strong>v0.6.356a • July 17, 2026</strong></summary>

- **Accuracy-over-time metric dropdown: disable Brier for non-pp fields + calendar reorder + h_ws_octant_bias 07-17 result.** (1) Metric dropdown on the accuracy-over-time chart now grays out the "Brier (for pp)" option whenever the selected field isn't pp — previously the option stayed selectable and picking it silently kicked back to the prior metric. Applied on load + on field change. (2) Calendar entry for Fri 07-17 h_ws_octant_bias re-read advanced to Fri 07-24 (re-read 2 of 3) with today's verdict inline: ⚠ SUGGESTIVE — 2 REAL octants (E +1.84 mph, S +0.99 mph HRRR over-forecast), 2 WATCH (NE, SW calm-flip), 4 flat; not enough across-octants signal to justify per-octant L2 correction yet. Re-anchored chronologically between Wed 07-22 and Fri 07-31.

</details>

<details>
<summary><strong>v0.6.356 • July 17, 2026</strong></summary>

- **Lc attribution wiring + debug-page Lc layer section + full-page sweep.** Same-day follow-on to v0.6.355 after noticing Lc wasn't rendering as its own layer column on cc/cl/cm/ch per-band tables — the same silent-attribution class of bug the Lsr v0.6.249 fix documented. Six coordinated edits: (1) `forecast_snapshot.py` now reads `l4` from `<field>_post_l4` (the pre-Lc snapshot Lc already preserves in `cloud_saturation_correction.py:168-170`) and exposes a new `l6` key holding the post-Lc value, mirroring how Lsr rides `l5` for sr. Applies to cc, cl, cm, ch. (2) Joiner + Fitter needed no changes — both already iterate `l1..l6`. (3) Frontend `_layerApplied` for `l6` now returns true for cc/cl/cm/ch (was `false`; l6 was Lt-only, Lt retired 07-13). (4) `LAYER_LINES` l6 entry relabeled "Cloud saturation (Lc)" with new pink color. (5) Badge row for cc/cl/cm/ch gains `Lc ✓ saturation`. (6) Lc promoted from the R&D "gated candidates" subsection into its own top-level layer section `sec-lc` between Lsr and Research, mirroring Lsr's five-block structure (What it does · Applicability · Live state widget · Engineering status · Developer notes). TOC updated. R&D `gated-candidates` retitled to C1-only; JS `renderGatedCandidatesSection` renamed to `renderLcLiveState`, target div `#lc-live-state`. Full-page sweep — updated Still-Open Watches, tri-column Current-state (Stack + What's-improving + Calendar chronologically ordered with 07-31 watch-close), Upcoming decisions Fri 07-17 marked ANSWERED, Stage 1 candidates table Lc row promoted to SHIPPED, Group A Stage 1 discovery description rewritten as SHIPPED history, accuracy-section layer-labels list adds Lc entry and corrects "Diurnal (L4) final line for every field except sr" → "Final line for t/dp/h/ws/wg/pp." First Fitter cycle after deploy (03:07 EDT) populates `per_layer_mae_by_lead[<field>].l6` and the Lc column starts rendering.

</details>

<details>
<summary><strong>v0.6.355 • July 17, 2026</strong></summary>

- **Lc FLIPPED to ENABLED=True — cloud saturation-unbiasing goes live for cc/cl/cm/ch.** One-line flip in `weather_collector/processors/cloud_saturation_correction.py:29`. Preconditions verified from this morning's fresh digest: `lc_fit` gate_clear=True (07-10 rolled out of the 7-day window today), SHIP set = 16 cells identical for 7 consecutive days (07-11 → 07-17, same set: cc 0-5/50-80/80-95/95-100; cl/cm/ch 20-50/50-80/80-95/95-100), divergence report LC_ENABLED READY (8/7 days), no cc/cl/cm/ch ANOMALY (cc/cl/cm on WATCH but only for forecast-mean distribution shifts, not MAE degradation — MAE is actually improving on those fields). Rule 5 sweep: removed `Lc` from `DISABLED_OPERATORS` in `corrections_debug.html` and `EXPECTED_DORMANT_OPERATORS` in `analysis/gate_firing_rollup.py`; added `Lc ENABLED` entries to the debug page's `SHIP_EVENTS` map for cc/cl/cm/ch (ship-date annotations on the accuracy-over-time chart); updated every applied-layers pipeline description in the Current-state table to append `→ Lc`; rewrote the applicability-map Lc bullet + live Lc widget copy + Still-Open Watches + Active-Candidates footer to reflect the flip. Recent activity 07-14 block trimmed to CHANGELOG per rolling 3-day rule; today's 07-17 entries added. 14-day post-ship watch begins today — biggest predicted lifts: cl 80-95 −55%, cl 95-100 −47%, ch 50-80 −37%. Watch trigger: any ch/cl/cm/cc cell flipping COLLAPSE in the anomaly detector within 14 days.

</details>

<details>
<summary><strong>v0.6.354 • July 17, 2026</strong></summary>

- **Joiner snapshot dedup + curl cache + sr sea_breeze Lsb Stage 3 wired ENABLED=False.** Four things bundled after a stalled morning digest exposed compounding issues. (1) **Joiner snapshot-side dedup** in `weather_collector/processors/forecast_error_log.py:285` — the pair log had grown to 2.5 GB because 6 snapshots per run hour (:07/:17/:27/:37/:47/:57) all cache the same underlying HRRR output and pair against the same obs, producing 6 identical rows differing only in `run_time`. Verified: every `(obs_time, field, lead_h)` triple appeared exactly 6× in the file. Fix keeps only the earliest snapshot per run-hour before pairing; pair-log volume should drop to ~400 MB as the 30-day retention rolls, and Fitter `n`'s stop being inflated by 6× (CIs tight by √6 ≈ 2.5×). Deployed at the 06:37 tick. (2) **`analysis/_cache.py` swap from urllib to curl.** `urllib.request.urlopen` stalls at ~40 MB on large Cloudflare-fronted composite GCS objects (caught this morning when the digest hung 25 min at the anomaly detector). `curl` handles the same fetch at ~24 MB/s. Same atomic `.tmp` → replace, same `MYWEATHER_REFRESH=1` honored. (3) **sr sea_breeze Lsr refit Stage 2 script** at `analysis/sr_sea_breeze_lsr_refit_stage2.py`. Follows the Stage 1 PROMOTE (+43.7% pooled) with a cross-cut that showed the win was cloud-conditional inside sea_breeze — cc 0-25 SHIP (+25.1%), cc 25-50 SKIP (-44.2%), cc 50-75 SKIP (-42.8%), cc 75-100 MARGIN (+34.3%). Stage 2 gates the intervention to (cc < 25) OR (cc >= 75) and re-verifies: pooled Δ +25.27%, halves +29.0% / +21.5%, lead-band 3 SHIP + 1 MARGIN + 0 SKIP → **PROMOTE**. (4) **Stage 3 wiring** at `weather_collector/processors/sr_sea_breeze_lsr_override.py`, hooked into `collector.py` after `stamp_solar_correction`. New operator **Lsb** (Lsr sea_breeze). Reads the curated bias table + cc gate from `data/sr_sea_breeze_lsr_curated.json`. When ENABLED, overrides `direct_radiation` with `shortwave_radiation − bias(hod)` on cc-gated sea_breeze cells and preserves the pre-override array as `direct_radiation_pre_sb`. Records to `gate_firing_log` as Lsb; describes itself into the applicability map. **ENABLED=False** — flip after 07-24 weekly Sun re-read confirms halves stability.

</details>

<details>
<summary><strong>v0.6.353l • July 16, 2026</strong></summary>

- **Accuracy over time: sparkline grid + Current-state section promoted + Safari reload-with-hash fix.** Three chunks bundled: (1) Added a per-field sparkline grid below the detail chart inside the accuracy-over-time section — 13 mini-charts (~190×80 each) showing Raw + Prod rolling 7-day means; click any panel to focus the detail chart above on that field; reacts to the metric selector. Sparklines auto-skip fields without enough history. (2) Promoted the "Current state — what's running · improving · being evaluated" tri-column band to an `h2.section` with id `sec-current-state` matching the visual + collapse behavior of Recent activity / Engineering updates / Forecast accuracy. Removed the old orphan wrapping `<section id="tri-column-band">` + inner `<details>`. Per-band tables inside Forecast Accuracy also promoted to `<details open id="sec-per-band">` for symmetry with the accuracy-over-time details. (3) Fixed a 3-layer Safari reload-with-hash bug that manifested as R&D auto-expanding on Cmd-R: added `history.scrollRestoration = "manual"` to stop Safari's default scroll-to-hash on reload; added an `{expandAllInner: false}` opt on `openSectionByHash`'s load-time call so the aggressive "expand every inner `<details>`" only fires on live TOC clicks; and on reload only (`performance.navigation type === "reload"`), strip the URL hash via `history.replaceState` before any DOM parses so CSS `:target` never matches and the flash animation doesn't fire. Preserves hash behavior for fresh navigation (shared links, cross-page). Chrome unaffected because it already uses scroll restoration.

</details>

<details>
<summary><strong>v0.6.353k • July 16, 2026</strong></summary>

- **Move orphaned metric-framework explainer into Forecast Accuracy section.** v0.6.353j moved the accuracy-over-time chart into the Accuracy section but left the "How we measure whether the forecast is good — the metric framework" `<details>` block behind, stranded between the tri-column band and the Recent Activity section with no context for what it was explaining. Joe caught it. Moved the block to sit right below the section intro (collapsed by default; open to see per-field observed sources, MAE/RMSE/bias/Brier definitions, measurement gaps like persistence skill and Brier reliability decomp). Reader flow now: intro → optional metric definitions → accuracy-over-time chart → per-band tables intro → per-field tables.

</details>

<details>
<summary><strong>v0.6.353j • July 16, 2026</strong></summary>

- **Accuracy-over-time chart moved into the Forecast Accuracy section.** Was a standalone collapsible right after the tri-column band; now lives at the top of the Forecast Accuracy section as the first view. Reframed the section intro as "Two lenses on the same question": (1) over-time trajectory = drift detector, is Prod moving? (2) per-field per-band tables = shipping-decision granularity, where in the horizon is each layer helping. Chart is `<details open>` so it's visible by default. `#sec-mae-over-time` anchor preserved so prior links still resolve. Also refreshed the chart's descriptor paragraph — mentions L2/L3 series, rolling-mean overlays, ship-date annotations, and the retention-independent accumulating history (was still saying "pair log holds ~30 days" which became misleading after v0.6.353h).

</details>

<details>
<summary><strong>v0.6.353i • July 16, 2026</strong></summary>

- **Accuracy-over-time chart: 7-day rolling mean overlays on Raw and Prod.** Chose rolling mean over linear regression (no functional assumption) and only overlay on Raw + Prod (not L2/L3) to avoid 8-line noise — the reader watches Raw ↔ Prod for drift. Complements the ship-date annotations: if a ship's effect is sustained the rolling mean bends within a week; if it reverts, mean stays flat. Rendered thicker (4px) with 0.35 alpha so daily line stays visually dominant. Kicks in once at least 4 non-null points in the trailing 7-day window are available (skips the first few days after a fresh dataset appears). Frontend-only change; no schema or analysis-script update needed since the daily values are already in the payload.

</details>

<details>
<summary><strong>v0.6.353h • July 16, 2026</strong></summary>

- **Accuracy-over-time chart: persistent history so x-axis grows past pair-log retention.** Pair log capped at 30 days by `decay_fit.py::RETENTION_DAYS`, so a re-aggregate-from-scratch view maxes out there. Rewrote `analysis/mae_over_time.py` to (1) fetch the prior `mae_over_time.json` from GCS, (2) recompute per-day rollup from the current pair log, (3) merge: overwrite the last `MERGE_REFRESH_DAYS=3` days (still-live cells may add pairs mid-day), preserve older days already recorded (their pair-log rows may have been pruned since). Storage math kept honest: each (day × field × layer) cell is ~90 bytes → ~5 KB/day → ~1.8 MB/year. Today's file at 31 days is 256 KB. First merge run: 1456 kept from prior, 156 overwritten (last 3 days), 0 new. Chart's x-axis is now retention-independent — grows one day at a time indefinitely, capped by nothing except GCS storage (trivial for years). Codifies the "always be mindful of data volume" principle by putting the storage math and knobs (MIN_N_PER_DAY, MERGE_REFRESH_DAYS) at the top of the script for future readers.

</details>

<details>
<summary><strong>v0.6.353g • July 16, 2026</strong></summary>

- **Debug page Rule 5 sweep — Stage 4 refresh after refined-primary + multi-axis-fix.** After v0.6.353e (refined view → primary) and v0.6.353f (silent 15-day multi-axis stratification bug fix), the debug page still described Stage 4 with 07-11 numbers and "legacy ship" framing. Grep + edit pass caught 6 stale spots: (1) calendar Sat 07-18 entry dropped "legacy" and noted refined + fix; (2) Still-open watches Stage 4 line rewritten with today's numbers (legacy MIXED 26/3/12, multi-axis NOT READY 195/139/320/143 +216); (3) Applied-layer table cc Status column updated to note the refined promotion + multi-axis fix; (4) C1 Applicability map bullet: replaced "HOLD at 61.54%" with today's dual-axis status; (5) Upcoming decisions Q/E/D block: reframed as refined-view-primary, both axes must pass, added the multi-axis-new-baseline caveat; (6) C1 confidence layer detail paragraph (~line 1671): updated the "Latest (07-11 refined)" numbers to today's dual-axis picture and added the silent-bug-caught narrative for future readers.

</details>

<details>
<summary><strong>v0.6.353f • July 16, 2026</strong></summary>

- **Stage 4 audit multi-axis: fix silent 15-day dead-stratification bug.** After v0.6.353e promoted the mixture-normalized refined view to primary, noticed the multi-axis was reporting 1013 cells all n=0 (INSUFFICIENT). Investigation: on 2026-07-01 v0.6.272, `c1_confidence_calibration_v2.py` extended the axis_key format from 4 parts (`sq::pt::slot::c1f`) to 5 parts (`sq::pt::slot::c1f::hsf`) when C1e (hours-since-front) shipped end-to-end. The curated ship-cells were emitted with 5-part keys; `c1_stage4_audit.py::stratify()` was never updated and kept building 4-part accumulator keys. Every ship-cell lookup missed → all cells reported n=0 → all INSUFFICIENT. **The multi-axis Stage 4 audit has been effectively dead for 15 days** — nobody caught it because the legacy axis (t/dp/h/... single-axis view) kept producing plausible-looking numbers. Fix: added `_load_frontal_passages()` and `_hsf_group()` mirroring the calibration script, extended axis_key to 5 parts. First real read: **195 PASS / 139 WATCH / 320 FAIL / 143 INSUFFICIENT / +216 excluded (as metric-artifact)** — refined verdict NOT READY, which is now genuine signal instead of "our stratifier is broken." Motivation to investigate came from #4 elevating refined view — the raw broken numbers were visible in the primary block instead of hidden. Illustrates why the earlier "trust refined" split-view design was masking a real bug: any downstream metric that reported the multi_axis result was reporting infrastructure failure, not calibration state.

</details>

<details>
<summary><strong>v0.6.353e • July 16, 2026</strong></summary>

- **Stage 4 audit: promote mixture-normalized refined view to primary.** The TODO queued 07-09 called for a mixture-normalized drift metric. The refined-view infrastructure landed the same day but stayed buried — printed third, and the raw legacy metric was still the top-line verdict downstream. This commit finishes the promotion: (a) `c1_stage4_audit.py` prints refined FIRST for both legacy_axis and multi_axis (labeled PRIMARY), then legacy view (labeled `[legacy — not authoritative]`); (b) closes with a pinned `Verdict: <refined_rec>` line so `extract_verdict()` in the digest exec summary picks refined instead of legacy; (c) JSON gets a new top-level `primary` field (source = `multi_axis.refined` when present, else `legacy_axis.refined`) so downstream code reads `primary.recommendation` — legacy `legacy_axis.recommendation` and `multi_axis.recommendation` retained for backward compat. Today's read shows the impact: legacy said `NOT READY — drift exceeds tolerance on majority of cells` (20 PASS / 23 WATCH / 15 FAIL), refined said `MIXED — most cells stable but tail unstable; hold` (27 PASS / 4 WATCH / 10 FAIL / +17 excluded as metric-artifact). Same underlying data; refined controls for near-zero-calib, mixture drift, and unsigned-improvement artifacts that inflate the legacy metric. Memory `project_stage4_audit_metric_limitation` updated with the "codified in-script" note. Full TODO item closed.

</details>

<details>
<summary><strong>v0.6.353d • July 16, 2026</strong></summary>

- **Makefile cleanup — remove dead `make analyze` target + `_combined.txt` bundle.** Both were added 06-04 (v0.6.13 era) as a "run every analysis + concat to one file for upload" convenience. Fully superseded 07-09 when the digest pipeline (`analysis/runlog/run_digest.sh` + `build_executive_summary.py`) shipped — produces a structured DIGEST.txt with executive summary, pass/fail table, per-script verdicts, and streak counters that the raw concat never had. No script, doc, memory, or recent commit references `_combined.txt` (grep-verified). `make analyze` gone; `make visualize` kept (chart generation + open-dir UX not covered by run_digest.sh). Left a pointer comment in the Makefile explaining the removal + steering readers to run_digest.sh.

</details>

<details>
<summary><strong>v0.6.353c • July 16, 2026</strong></summary>

- **sr sea_breeze Lsr refit Stage 1 — PROMOTE.** New `analysis/sr_sea_breeze_lsr_refit_stage1.py`. Follow-on to 07-11 confound diagnostic that found sea_breeze has +83.6 W/m² matched-cc bin bias in total_shortwave (Cause B evidence). Method: for sea_breeze sr rows, split 60/40 by obs date, fit per-local-hour signed bias of `(forecast_shortwave − observed)` on train, test intervention vs baseline (current Prod post-Lsr on direct_radiation). First read: n=3,548 total, held-out **baseline MAE 137.93 → intervention MAE 77.64 (+43.71%)**. Halves check A→B +26.55% / B→A +38.58% — both confirm. Ship gate: PROMOTE. Fit shows overall bias +67.60 matches confound direction — real overshoot. Caveats logged: small sample (3 test days), high underlying variance between halves (baseline MAE 298 vs 131 — one hotter half), only 7 hours populated in bias table. **Next:** Stage 2 = full per (regime × hour) cross-cut across all regimes + multi-week stability check. If Stage 2 holds, Stage 3 wires a shortwave-source fallback for winning regimes. Auto-picked up by daily digest via `analysis/*.py` glob. Memory `project_sr_unit_mismatch.md` updated with Stage 1 outcome.

</details>

<details>
<summary><strong>v0.6.353b • July 16, 2026</strong></summary>

- **Rule 5 automation — `scripts/check_stale_refs.py` + `make check-stale`.** Converts today's failure mode (v0.6.352c missed 10+ stale refs, needed v0.6.352d re-sweep) into a mechanical check. Grep-scans `corrections_debug.html` for predictive-tense date refs: day counters `(MM-DD)`, `as of MM-DD`, `HOLD until MM-DD`, `earliest ship/flip MM-DD`. Exits 1 on any hit older than 2 days. Historical mentions (`shipped 07-12`, session narratives, changelog dates) deliberately left alone — only rots-with-time refs are flagged. `feedback_debug_page_canon.md` memory extended with automation note. Verified: passes today, catches 17 refs when simulated at 2026-07-20. Runs manually today; wiring into pre-commit / build.py deferred pending Joe's call.

</details>

<details>
<summary><strong>v0.6.353a • July 16, 2026</strong></summary>

- **Accuracy-over-time chart v2: L2/L3 layers + Brier + ship-date annotations.** Three follow-ons landed in one pass. (1) `analysis/mae_over_time.py` now emits all four layers (Raw / L2 / L3 / Prod) instead of just Raw/Prod — chart shows the intermediate layers so you can see which layer moved the needle (e.g., wg's L2 shoulder vs L3 shoulder vs Prod, or t's flat L2=L3=Prod confirming t is at ceiling). Also emits Brier = mean(err²) per (day × field × layer) alongside MAE/RMSE/bias. (2) Frontend chart adds `Brier (for pp)` as a metric option; auto-switches to Brier when pp is selected (and back to MAE for other fields). (3) Per-field ship-date annotations drawn as vertical dashed amber lines with rotated labels — ws 07-06 (L3 skip-table firing after 4-day silent dormancy — the big visible move), sr 07-06 (Lsr correction firing after bug fixes), t 07-13 (Lt retired), pa 07-13 (τ 28→42), pp 07-04 (dropped from L3), cm 07-04 (HRRR cm anomaly onset, a data event not a ship but affects trajectory). Dormant ships (ENABLED=False) deliberately not annotated since they don't move Production. Implemented as a Chart.js `afterDatasetsDraw` plugin, no new CDN. Fixed `datetime.utcnow()` deprecation warning in the analysis script while I was in there.

</details>

<details>
<summary><strong>v0.6.353 • July 16, 2026</strong></summary>

- **Accuracy over time — new chart card on debug page.** New `analysis/mae_over_time.py` aggregates `forecast_error_log.jsonl` per (obs_day × field × layer), emitting per-day MAE + RMSE + bias for Raw and Prod. Publishes `mae_over_time.json` to GCS (same pattern as `h_persistence_skill.py`). Auto-picked up by the daily digest via `analysis/*.py` glob. Filter: min 200 pairs/day to skip noise-thin cells. New collapsible section 📈 "Accuracy over time" placed right after the tri-column band (self-contained IIFE at end of script block, uses existing Chart.js 4.4.4 CDN). Field dropdown + metric dropdown (MAE / RMSE / signed bias), one Chart.js line canvas comparing Raw (dashed grey) vs Prod (solid green) over the last ~30 days. First read: 2,814,904 pair rows → 31 days × 13 fields. Fills the gap the 2-window anomaly detector doesn't cover — surfaces gradual drift and lets you visually verify that a recent ship actually moved the needle. Next iteration if useful: add L2/L3 series, pp Brier variant, ship-date annotations. Half-day estimate landed in ~1 hour.

</details>

<details>
<summary><strong>v0.6.352e • July 16, 2026</strong></summary>

- **Debug page top-line: prepend live deployed version.** Joe wants to see at a glance whether the live page matches the latest ship — added a fetch of `version.json?_=<ts>` (cache-busted, same pattern as `js/version_check.js`) to `renderMeta()` and prepended `<strong id="meta-version">…</strong> · ` to the tagline. Placeholder shows `…` until fetch resolves, then swaps to `v0.6.352e` (or `?` on error). Sits before `fitted … · N pairs · decay applied … · corrections · weather`.

</details>

<details>
<summary><strong>v0.6.352d • July 16, 2026</strong></summary>

- **Rule 5 full-page sweep after v0.6.352c missed 10+ stale refs.** Joe caught the v0.6.352c "tri-column only" sweep as insufficient — Rule 5 (transition-invalidation) says grep the ENTIRE page. This commit does that: (a) `h/l4 narrow-add` in Applicability map advanced day 2/7 → day 4/7, refined to name both SHIP cells (calm/0-5h + calm/12-23h) and earliest flip 07-19; (b) L3 Applicability map bullet reframed — walkforward "drop ws" gate cleared 7/7 today, but HELD in favor of 07-21 skip-table per `production_whatif` evidence (`ws_L3_skip` −10.6% overall matches wholesale `L2_ws_drop` −10.7%); (c) Lc Applicability map bullet rewritten around two-gates-per-layer split — earliest flip 07-17 (not 07-18); (d) Upcoming decisions Q/E/D block: "Thu 07-16 — ws L3 strip" marked answered (HOLD → skip-table); Lc entry reframed to Fri 07-17; ch persistence counter day 5/7; h/l4 narrow-add updated to Sun 07-19 covering both cells with on-rails evidence; pre-frontal day 4/7; wg residual day 3/7; (e) C1h/C1d prose in confidence layer description advanced to 07-16 numbers (C1h 2/7 with 14 SHIP, C1d 1/7 with 12 SHIP reset); (f) Stage 1 candidates table ch persistence + wg residual rows advanced; (g) live Lc widget's inline gate-note template literal rewritten (was "day 4/7 as of 07-13 · Anomaly-week HOLD until 07-18"); (h) Recent activity block re-trimmed to rolling 3-day window (today + 2 prior — 07-13/07-12/07-11 moved to changelog reference); today 07-16 and yesterday 07-15 entries added; (i) Current pipeline state header + "Last curated" advanced to 07-16 v0.6.352d; h status row updated with h/l4 on-rails detail; (j) Still-open watches added Lc earliest-flip 07-17 entry, advanced counters on wg residual/ch persistence/cl persistence. See [[feedback_debug_page_canon]] Rule 5.

</details>

<details>
<summary><strong>v0.6.352c • July 16, 2026</strong></summary>

- **Tri-column band sweep — Running/Improving/Evaluating brought current to 07-16.** Debug page tri-column at the top-of-fold was 2 days stale across ~15 spots. Updated: (a) Production vs raw dropped the stale sr suppression-window line and rewrote the ws regression as a 24-47h vacuum flagged for the 07-21 stack. (b) 8 active Stage 1+3 candidates (was mis-labeled "11") — all day-counters advanced to 07-16 values: ch persistence day 5/7, cl persistence day 4/7, wg residual day 3/7, C1h 2/7 (14 SHIP cells), C1d 1/7 (12 SHIP cells, reset), pre-frontal 4/7. (c) Lc entry rewritten to reflect today's two-gates-per-layer split — divergence-report 7/7 but `lc_fit` gate_clear=False; earliest flip is tomorrow 07-17 when 07-10 rolls out of the fitter's window (was previously "HOLD until 07-18" which conflated anomaly-hold with gate-math). (d) Calendar rebuilt: past 07-16 entry removed, 07-17 Lc flip + h_ws_octant_bias added, 07-19 h/l4 narrow-add added (SHIP set stable 4 days), 07-22 C1h/C1d earliest ship added. (e) Frozen section replaced Lsr/sr entries (all cleared 07-10/07-11) with MLC dormancy (indefinite) + MLC seasonal redesign (needs autumn data). (f) Post-ship watches replaced 2 stale Lsr entries with wg persistence-skill thin-margin watch (verify 07-22 whether 24-47h skill_prod moves after the 07-21 stack) and Lt retirement 2-window stability check.

</details>

<details>
<summary><strong>v0.6.352b • July 16, 2026</strong></summary>

- **MLC collapse diagnosed — real break 06-30, pre-HRRR, stratum-local; hold indefinitely.** New `analysis/marine_layer_collapse_diagnostic.py` recomputes the NE-flow-morning cc in-bin signed bias fresh per obs day (independent of Fitter's cumulative aggregation): +42.7 (06-28) → +16.6 (06-30) → +3.9 (07-05) → never above +5 after. The 07-07 "cliff" `marine_layer_anomaly.py` reported was the growing cumulative window catching up to the older shift, not the actual break. Split at 07-04 (cm HRRR-anomaly onset): in-bin Δ = −48.6 vs out-of-bin Δ = −5.0 (9.8× ratio) — stratum-local, not cc-wide, and pre-HRRR. Companion cl signal weakens same week (marine_layer_cl_stage1 W29 −2.98 vs +12/+22/+17/+13 W25–W28). Diagnosis: likely seasonal marine-layer weakening as SST warms into July; will not re-arm when cm HRRR anomaly clears — different event. Debug page MLC bullets (Built-not-applied + hypothesis-backlog) updated with the real trajectory and diagnosis; redesign candidate flagged as time-of-year gating on the MLC bin.

</details>

<details>
<summary><strong>v0.6.352a • July 15, 2026</strong></summary>

- **Lt conflict — divergence-report rationale updated + retirement holds.** `l6_fix_b_refit.py` flipped HOLD → SHIP (held-out +0.29% → +1.34%) after a 2-day window roll on essentially identical training data (154,498/47,823 → 154,698/47,716). Panel B refit table is unchanged from the 07-13 retirement read — same 7 SHIP bins overnight, same means. Mechanism argument for retirement (L2's Kalman blend absorbs the signal per-tick, static delta double-counts) unchanged, so **retirement holds** pending 2-window stability on 07-16 + 07-17. Fixed the internally-contradictory comment + note in `analysis/runlog/divergence_report.py` around the LT_ENABLED row: was still saying "will always AGREE with LT_ENABLED=False" while the row was rendering GATE CLEARED (3/2) READY. New text acknowledges the SHIP verdict and states the watch. `_claim:LT_ENABLED=true` has actually been firing continuously since 07-13 T11:53 — retirement was correctly made on mechanism, not on the immediate script number. Bundled with today's routine curated-table refreshes from the analysis pipeline (c1/c1d/c1h/ch/lc/pre-frontal/t/wg/ws/wg-residual + gate-history caches).

</details>

<details>
<summary><strong>v0.6.352 • July 15, 2026</strong></summary>

- **Alerts card: consolidate same-event alerts + agency-name acronyms.** Wyman Cove was showing three near-identical "Air Quality Alert" cards this morning — same title, description truncated before the disambiguator, looked like a rendering bug but was three genuine NWS-relayed MA DEP alerts (two Fine Particulates with different expiries, one Ground Level Ozone). Fix in `buildWatchRows()` (js/briefing.js): group `s.alerts` by `event`; single-alert case unchanged; multi-alert same-event case renders one row with each alert's first sentence on its own line (`<br>`-joined). Also added an `agencyAcronyms` map applied to detail text — "Massachusetts Department of Environmental Protection" → "MA DEP", plus MEMA, MA DPH, NHC, SPC, WPC, NWS, USCG, USGS, EPA, FEMA, and NH DES / RI DEM / ME DEP for neighboring states whose plumes could reach us. Ordered longest-first so longer names beat any shorter substring. Adding future issuers is a one-line insert. No dedupe — every alert still appears; only visual layout consolidates.

</details>

<details>
<summary><strong>v0.6.351f • July 14, 2026</strong></summary>

- **Rule 5 broader sweep — 4 more stale reference-section refs across today's transitions.** After v0.6.351e caught Lt-specific staleness, ran Rule 5 grep across ALL of today's transitions (ch landmark, ws L3 Stage 1, wg L3 Stage 1, t L2 Stage 1) and found four more stale references in persistent reference sections: (1) Production stack card L3 bullet had "ws strip candidacy: day 4/7 (07-13)" — updated to day 5/7 (07-14) with pointer to today's Stage 1 halves-verified answer; (2) Persistence-skill framework bullet had "ch persistence gate ... day 2/7" and "ch Prod −1.08 vs L4-alone −0.29" — updated to day 3/7 (07-14), landmark-answered note, current Prod −1.10 / L4 −0.30; (3) Specialists card Lc bullet had "day 4/7 (07-13)" — updated to day 5/7 (07-14); (4) C1h/C1d confidence layer prose had "Earliest ship 07-16" — updated to reflect today's SHIP-set reset pushing earliest to 07-21. Recent activity chronological entries kept as-was (historical narrative is correct even when superseded).

</details>

<details>
<summary><strong>v0.6.351e • July 14, 2026</strong></summary>

- **Rule 5 sweep — Lt stale-reference cleanup found by grep.** Immediately after codifying the new "transition-invalidation sweep" rule (Rule 5 in `feedback_debug_page_canon.md` memory), ran the rule on the debug page and it caught six more stale Lt references I missed in earlier sweeps: (1) R&D cove-gradient section prose still called Lt "dormant 2026-07-01 v0.6.276" and mentioned "eventual Fix B"; (2) HTML comment above the R&D block still said "Fix B path back"; (3) live-widget label showed "DORMANT since 2026-07-01 v0.6.276" and prose about "eventual Fix B"; (4) `_layerApplied()` JS comment described Lt as "dormant since"; (5) `renderLtLiveState()` docstring said "Lt is dormant"; (6) `ADDRESSED` table comment for `t` said "until Fix B ships." All six updated to reflect Lt retired 07-13 v0.6.329 after Fix B refit failed +1% ship gate. Also updated the `t` addressed-table comment with the 07-14 v0.6.351d ceiling verdict — future readers see the current state, not a promise from a plan that already ran and failed. Direct validation that Rule 5's grep-then-fix-every-hit discipline was needed.

</details>

<details>
<summary><strong>v0.6.351d • July 14, 2026</strong></summary>

- **t L2 skip-table Stage 1 preview — clean null.** New `analysis/h_t_l2_regression_stage1.py`. Prompted by the "Winning fields" panel showing t as ✗ (Production doesn't beat raw). Halves-verified per (regime × lead_band): **0 SKIP / 6 MARGIN / 30 KEEP / 1 THIN**. L2 clearly HELPS at short leads (0-5h: sw_flow −30%, calm −24%, nw_flow −21%, pre_frontal −18%, se_flow −16%, sea_breeze −10%). L2 is FLAT at 6-11h + 12-23h + 24-47h across every regime (most cells within ±2%). 6 MARGIN cells all under the +3% floor. The pooled "Production ≈ raw" state comes from L2 saving 20-30% at short leads being canceled by many long-lead cells each adding tiny +1-2% noise; volume-weighted they roughly cancel, but no single cell has extractable damage. **Verdict: t is at ceiling** under the (regime × lead_band) slicing. Raw HRRR is genuinely good at temperature at this coordinate; L2 provides big short-lead wins that dilute across the full pool. This is a confirmed-at-ceiling result, not a "we could try harder" — Stage 1 answered the question.
- **Lt section rewrite (already pushed earlier in the session as its own commit).** [DORMANT LAYER] → [RETIRED LAYER]. "Path back — Fix B" replaced with "Fix B tried 07-13, failed +0.29% held-out." Reactivation criterion documented. Archive cross-reference + outer HTML comment updated.

</details>

<details>
<summary><strong>v0.6.351c • July 14, 2026</strong></summary>

- **ws L3 skip-table Stage 1 preview + debug page category-tag redesign.** New `analysis/h_ws_l3_regression_stage1.py` (mirror of today's wg L3 Stage 1). Halves-verified per (regime × lead_band): **10 SKIP cells** — calm all 4 bands (+25/60/76/73%), nw_flow 24-47 (+29% both halves positive — validates the "just skip nw_flow" intuition per-cell), sea_breeze 6-11 (already skipped v0.6.279) + 24-47 (new), unknown 6-11 + 12-23 + 24-47. 20 KEEP, 4 MARGIN, 1 THIN, 2 PERSISTENCE_TERRITORY. Key architectural learning: nw_flow doesn't lose broadly — just at 24-47h; other nw_flow bands KEEP. A whole-regime `("nw_flow", 0, 48)` skip would have been too coarse and killed L3 on 3 regime-bands where it helps. Proposed merged skip table: `SKIP_TABLE[("ws","l3")] = [("ne_flow",0,48), ("sea_breeze",0,12), ("calm",1,48), ("nw_flow",24,48), ("sea_breeze",24,48), ("unknown",6,48)]`. After all skips, L3 still fires on ~77% of ws rows. Not wired; 7-day streak + halves stability. Earliest ship 07-21 — would dissolve the walkforward "drop ws" flat-drop verdict by removing pooled damage without sacrificing L3 wins in frontal/pre_frontal/se_flow/sw_flow at short leads.
- **Debug page — Recent activity category tags.** Replaced leading ✓/★ symbols with category prefix tags (DISCOVERY / INFRASTRUCTURE / DASHBOARD / PIPELINE) in the rolling 3-day Recent activity block. Muted small-caps colored tags for scan-ability without visual noise. DISCOVERY = Stage 0/1 findings, landmark investigations. INFRASTRUCTURE = tooling, gates, scripts wired to digest, script bugfixes. DASHBOARD = debug page / briefing / PWA UI changes. PIPELINE = Stage 3 wires, ENABLED flips, live-layer changes to the forecast. Bundled-scope entries (v0.6.351b was Discovery + Infrastructure) use primary category with secondary noted in prose.

</details>

<details>
<summary><strong>v0.6.351b • July 14, 2026</strong></summary>

- **Lt stale-gate cleanup + wg L3 skip-table Stage 1 preview.** Two housekeeping items.
  - **Divergence report — LT_ENABLED row.** Was reading verdict from `r5_cove_analysis` (older tool, still says SHIP against L1 which is not the operative baseline), producing `LT_ENABLED=False / script wants True / GATE CLEARED (2/2)` every daily digest — a recurring false-positive since Lt was retired 07-13 via Fix B. Switched the row to read from `l6_fix_b_refit` (the authoritative retirement decision, HOLD +0.29% below +1% gate). Row now shows AGREE. Digest summary went from "1 gate-cleared" to "0 gate-cleared."
  - **wg L3 skip-table Stage 1 preview** — new `analysis/h_wg_l3_regression_stage1.py`. Follow-on to Stage 0 (v0.6.339, 07-13) which flagged 10-11 wg L3 regression cells. Halves-verified verdict per (regime × lead_band) on the same 30d window/halves as ch persistence gate Stage 2. Result: **6 SKIP cells** (calm all 4 bands +25/60/76/73%; sea_breeze 0-5 +4.6%; unknown 24-47 +35%), 20 KEEP, 2 MARGIN, 1 THIN, and **8 PERSISTENCE_TERRITORY** cells that belong to today's wg residual persistence gate discussion instead (5 of the 6 wg persistence gate SHIP cells match here — correct disaggregation between two independent interventions). Proposed skip-table extension: `SKIP_TABLE[("wg", "l3")] = [("calm", 1, 48), ("sea_breeze", 1, 6), ("unknown", 24, 48)]`. Not wired — needs 7-day streak per whitelist-promotion-gate + weekly halves stability. Script auto-runs in nightly digest.

</details>

<details>
<summary><strong>v0.6.351a • July 14, 2026</strong></summary>

- **ch persistence LANDMARK answered — keep the shipped gate.** Today's `h_ch_persistence_blend.py` flagged "persistence-only ALSO beats baseline on halves — consider pulling ch from L3+L4 entirely." Investigated the head-to-head: regime_gate 19.092 pooled MAE vs persist_only 19.119 (0.14% relative, tied in noise). Half A persist wins by 0.05 MAE; half B gate wins by 0.13 MAE. Gate's per-cell halves-stability enforcement is doing real work — `pre_frontal/24-47` (n=11,611) is +5.07% loss for persist_only that the gate hedges by falling back to L4; halves-unstable cells (ne_flow/24-47, nw_flow/6-11+24-47, sw_flow/6-11+12-23+24-47) get the same L4 hedge under the gate. Landmark's "consider" clause was ambiguous — it meant persist_only ALSO clears halves-vs-baseline, not that it beats the shipped gate. Do NOT rip out ch from L3+L4; shipped-dormant gate is the right architecture and 07-19 flip proceeds as planned. Bonus finding: today's Stage 2 re-fit shows SHIP set flexed 22→24 SHIP (one previously-SKIP cell now SHIPs) — safer direction but the 07-19 stability check will register a formal change; flip decision includes whether to flex the gate to include the new SHIP cell if its halves are stable on 07-19 re-fit.

</details>

<details>
<summary><strong>v0.6.351 • July 14, 2026</strong></summary>

- **wg residual persistence Stage 3 wired ENABLED=False.** Stage 1 (07-13, window=14d) held +16.54% pooled MAE improvement on held-out with 6/7 regimes WIN + both halves positive; refit today at wider audit granularity as Stage 2 preview (`analysis/h_wg_residual_persistence_stage2.py`). Per-cell (regime × lead_band) verdict: 6 SHIP / 0 MARGIN / 30 SKIP / 1 THIN (37 judged). All 6 SHIP cells are long-lead (12-23h and 24-47h) in flow regimes — `frontal 24-47` (−49.01%), `pre_frontal 24-47` (−29.12%), `se_flow 12-23` (−18.92%), `se_flow 24-47` (−32.22%), `sw_flow 12-23` (−23.29%), `sw_flow 24-47` (−25.29%). Every short-lead (0-5h, 6-11h) cell SKIPs in every regime — L2's Kalman blend already tracks recent obs, so a 14-day residual mean re-adds stale bias at close-in leads. Stage 1's pooled win was carried by the massive n at long leads (sw_flow 24-47 alone: 23,812 rows). Second consecutive gate this month where the regime-gate-first frame ([[feedback_regime_gate_first]]) converts a mixed-pooled finding into a clean per-cell ship map; ch persistence 07-12 was the first. Stage 2 script emits a 24-slot per-clock-hour L2-residual correction (mean over last 14d from most recent pair-log date) into `wg_residual_persistence_curated.json` alongside the cell verdicts; processor reads both. New processor `wg_residual_persistence.py` mirrors the ch persistence gate shape: reads `hourly.wind_gusts_post_l2` + curated JSON, replaces `hourly.wind_gusts` in SHIP cells with `fc_l2 + hour_of_day_correction`, preserves pre-gate array as `hourly.wind_gusts_post_l3_pre_wgrp` for attribution, stamps telemetry + gate_firing_log. Placed AFTER decay_apply so it overrides L3's wg output. `ENABLED=False`; earliest flip after 7 daily reads with SHIP-set stability (2026-07-21).

</details>

<details>
<summary><strong>v0.6.350a • July 13, 2026</strong></summary>

- **v0.6.350 fix: fill in Production column for RMSE + bias rows.** The redesign shipped with "—" placeholder in the Production column for the RMSE and bias sub-rows, on the theory that hybrid-Production was MAE-only. Wrong — `per_layer_rmse_by_lead` and `per_layer_bias_by_lead` both publish a populated `production` key (48 values per field, done by `decay_fit.py` alongside the per-layer arrays). Read directly from `data.production` for the RMSE + bias Production cells so the column fills correctly. Also dropped the now-incorrect "no Production column" caveat from the intro prose.

</details>

<details>
<summary><strong>v0.6.350 • July 13, 2026</strong></summary>

- **Accuracy section redesign — kill charts, one combined table per card.** Joe raised that the section had become "a lot less useful" after v0.6.340 added RMSE + bias companion tables (chart + 3 tables per card = wall of vertical space). Discussion surfaced the real root cause: charts USED to be useful when they showed each layer's individual contribution, but two mid-summer changes ate that value — (1) v0.6.340's `_layersFor()` filter dropped inactive layer lines (correct fix for lots of stacked identical lines, but robbed the chart of its per-layer visual story) and (2) the thick Production line added earlier dominates the eye. Redesign: each card now renders a single band-table with rows grouped as (band × metric) — 5 bands (0-5h / 6-11h / 12-23h / 24-47h / ALL) × 3 metric rows (MAE primary, RMSE + bias as visually secondary sub-rows). Same information density, roughly half the vertical footprint, and the eye lands directly on the tables where every actionable decision is made anyway. Killed `_buildBandTable` + `_buildMetricTable` + the entire `new Chart(...)` block; replaced with `_buildCombinedTable`. pp-Brier cards still render Brier-only (no MAE/RMSE/bias companion story to tell for probabilistic forecasts). Intro prose rewritten — dropped the "colored lines" paragraph and legend explanation, added per-metric usage notes (MAE = primary L3/L4 whitelist metric; RMSE = watch for band where RMSE jumps proportionally more than MAE = occasional big misses; bias = signed drift). Design note added to the intro explaining why the charts are gone.

</details>

<details>
<summary><strong>v0.6.349 • July 13, 2026</strong></summary>

- **project-todo memory sweep — 8 stale entries closed.** Motivated by the discovery that "gate-firing table" (v0.6.345) and "retire * migration" (v0.6.346) were both actionable-now items whose implementations already shipped days-to-weeks earlier — same class of drift. Sweep results: (1) **Frozen bucket:** `sr → L4` and `Lsr skip regime changes` marked "not before 07-10" — contamination lifted 07-10, both unblocked. `h → L4 promotion` clarified to distinguish the full-h unblock from the narrower `h/l4/calm/12-23h` streak counter shipped 07-13. (2) **Post-ship watches:** Lsr 14-day watch self-lifted 07-10; v0.6.310+311 skip-table firing verification completed (ws Prod 25.7% → 5.3%, matches production_whatif prediction); v0.6.291 raw-baseline verifier extended indefinitely. (3) **Measurement framework roadmap:** Phase 2 persistence baseline follow-ons all shipped (scorecard integration v0.6.328, Prod-vs-L4 v0.6.336, ch persistence gate v0.6.327, cl short-lead gate v0.6.330); Phase 3 pp Brier decomposition SHIPPED v0.6.335 (BSS +0.126); Debug page accuracy-section rewrite SHIPPED v0.6.340. (4) **Actionable now:** `sr shortwave-vs-cc confound` and `h_c1h_orthogonality.py` both closed — first reads done 07-11 and 07-10 respectively. (5) **ws structural residual:** unblocked now that skip-table window filled 07-13; direction pointer added toward octant-bias additive story. Net effect: fewer than 5 real items remain in the "Actionable now" and "Longer horizon" buckets, and every item that's still there is actually pending work.

</details>

<details>
<summary><strong>v0.6.348 • July 13, 2026</strong></summary>

- **MLC collapse diagnosis: not the cm anomaly, separate event at 07-07.** Segmented the marine_layer_watch time series by window to test the "same as cm HRRR shift?" hypothesis. Per-window in-bin bias: pre-anomaly (06-22→07-04) +37.01, cm-anomaly-window (07-04→07-07) +33.02, cliff (07-07→07-10) +13.80, post-cliff (07-10→07-14) +8.85. **MLC held ~+33 through the entire 07-04→07-07 cm-anomaly window** before collapsing on 07-07 — three days after the cm shift began. If the same HRRR upstream change caused both, they'd move together. They didn't. Also: in_bin_n grew (3734 → 4217) — so not stratum-shrink; there are actually MORE NE-flow-morning pairs recently and they're just genuinely less biased. Something in NE-morning cc physics changed sharply on 07-07. Best remaining hypotheses: mid-summer seasonal drop in NE-flow inversions, or an HRRR NE-morning boundary condition shift distinct from cm. Debug page + memory updated with narrower diagnosis; MLC.ENABLED stays False indefinitely; re-engage flip criterion only if in_bias recovers to +25+ within 3 weeks.

</details>

<details>
<summary><strong>v0.6.347 • July 13, 2026</strong></summary>

- **Marine-layer stratum bias-collapse detector + COLLAPSE finding.** Investigating the "flip target mid-July if trend holds" TODO surfaced that the trend did NOT hold — the MLC in-bin signal has been collapsing since 07-07. New `analysis/marine_layer_anomaly.py` reads `marine_layer_watch.json` (per-tick fit output) and compares recent-7d vs baseline-21d mean of `in_bin_signed_bias`. Three verdicts: COLLAPSE (|Δ|≥15 AND recent<15), DECAY (|Δ|≥10 AND recent<baseline), STABLE. **First run flags COLLAPSE:** baseline +36.27 → recent +10.97 (Δ −25.29); out-of-bin control flat (+10.67 → +11.09), confirming this isn't a global cc shift. Also wired into `build_executive_summary.py` alongside the pair-log anomaly detector so future collapses/decays surface at exec-summary altitude in the daily digest. Debug page MLC entry rewritten to reflect the collapse; project-todo memory refreshed. **Decision:** MLC.ENABLED stays False; flipping now would over-correct cc by ~+25pp inside the gate. Two candidate causes to investigate: same 07-04 HRRR anomaly window as cm, or a mid-summer seasonal drop in NE-flow inversions.

</details>

<details>
<summary><strong>v0.6.346 • July 13, 2026</strong></summary>

- **Retire "*" migration language on the accuracy section.** Three stale bits from the 07-01 → 07-08 per-row-stamping migration cleaned out: (1) MAE band-table tooltip's fallback text no longer says "Per-row stamping shipped 2026-07-01; 7-day window fully fills 2026-07-08" — replaced with "Thin-sample fallback only — protects against noisy per-lead averages." Reframes the sub-floor path as an ongoing safety net, not a migration artifact. (2) "Current pipeline state" table intro dropped the "entries flagged 'in flight' are cases where today's deploy hasn't propagated" caveat — no cell has been flagged in-flight for over a week, and the deploy-propagation framing was migration-specific. Now: "Production numbers are real per-row aggregates over the rolling 7-day window." (3) Engineering-updates per-row-stamping entry dropped "; 7-day window fully filled 2026-07-08" and the "The `*` marker auto-drops per-card at ≥40/48 leads covered" line — reframed the thin-sample fallback in the same "rare-lead safety net, not a migration artifact" language. **Left unchanged:** the `realCovered >= 40 ? "" : "*"` conditional in the chart code (safety net if we ever drop back below the floor) + all n≥30 min-sample floor language (real ongoing noise guard, per project-todo instruction).

</details>

<details>
<summary><strong>v0.6.345 • July 13, 2026</strong></summary>

- **gate_firing_rollup EXPECTED_DORMANT allowlist refresh.** The dormancy audit shipped 07-09 v0.6.318 was flagging 4 operators + 4 cells as ⚠ UNEXPECTED that are actually designed dormant. Extended `EXPECTED_DORMANT_OPERATORS` in `analysis/gate_firing_rollup.py` to cover post-v0.6.318 ships: `ch_persistence_gate` (v0.6.327, ENABLED=False awaiting 7-day gate) and `cl_persistence_short_lead` (v0.6.330, ENABLED=False awaiting halves-verified re-run). Refreshed `Lt` entry from "dormant pending Fix B" to "retired 07-13." Added new `EXPECTED_DORMANT_CELLS` allowlist (keyed on operator × field × regime triples) covering the 4 designed skips: L3/ws/ne_flow (SKIP_TABLE v0.6.279), Lsr/sr/ne_flow + calm (v0.6.280), C1h/ch/ne_flow (co-axis ortho gate v0.6.321). Re-ran + published to GCS: `⚠ UNEXPECTED: none` — signal-rich bucket, no more false positives to filter through. project-todo memory refreshed (the whole "build the table" entry was stale — it's been live since 07-09).

</details>

<details>
<summary><strong>v0.6.344 • July 13, 2026</strong></summary>

- **wg residual-persistence Stage 1 first read — MARGINAL.** Ran `analysis/h_wg_residual_persistence_stage1.py` end-of-session (202,321 rows, 152,517 train / 49,804 test). Bigger window wins on aggregate: **window=14d, MAE +17.04%**, RMSE +14.92% held-out (vs the naive 2-day rolling mean's +6.13%). L2-alone and Production give identical numbers — confirms no L3 interference (wg not in `L3_FIELDS`). **Two red flags block promotion:** (1) per-regime cross-cut — 5 regimes WIN (se_flow +28.38%, sw_flow +22.71%, pre_frontal +18.89%, nw_flow +18.06%, ne_flow +7.95%) but **`calm` LOSES −71.29%** (n=1,221) and `unknown` −2.24%; regime gate mandatory. (2) Halves check FAILS — first half (6/13→6/24) +18.44%, second half (6/24→7/05) +0.49%; effect real but window-to-window unstable. Verdict per script: MARGINAL, re-run in 3 days. Path forward stays Stage 2 (exp-decay τ + regime gate skip calm/unknown) + Stage 3 wire-up, held pending 07-16 halves-stable read. Debug page updated: Recent activity extended through v0.6.344, new wg residual-persistence watch row (day 1/7), wg state-table status column reflects both open threads, new Upcoming decisions entry Thu 07-16. Memory [[wg-residual-persistence]] refreshed with grid + regime + halves numbers.

</details>

<details>
<summary><strong>v0.6.343 • July 13, 2026</strong></summary>

- **wg residual-persistence Stage 1 preview script queued.** Follow-on to v0.6.342 Stage 0 hit (wg MAE −6.13% held-out). New `analysis/h_wg_residual_persistence_stage1.py` runs a grid search over window ∈ {1, 2, 3, 5, 7, 14} days × baseline ∈ {L2-alone, Production (post-L3)}, then a per-regime cross-cut of the best combo (state_fc.regime_synoptic), then halves-check within training. Verdict rule: STAGE 1 PROMOTE if best combo hits ≥1% MAE on held-out AND wins > loses on regime cut AND both training halves show ≥0.5% improvement. Auto-picks-up in tomorrow's digest — first real read 07-14 AM. Written but not run this session (Bash classifier was blocked during finalization; script is syntax-verified). Also written to memory: [[wg-residual-persistence]] captures the finding + Stage 1/2/3 path.

</details>

<details>
<summary><strong>v0.6.342 • July 13, 2026</strong></summary>

- **Novel finding: wg short-term residual persistence — Stage 0 hit.** New `analysis/h_daily_residual_persistence.py` tests whether yesterday's mean (obs − L2_forecast) at hour H predicts today's at hour H. Question: does L4's 21-day averaging window smooth over real 1-3 day drift? Answer per field: **wg is a genuine hit.** Simulated a rolling 2-day mean-L2-residual correction at same clock hour, held-out on last 7 days: **wg MAE −6.13%** (2.638 → 2.475) and **RMSE −7.41%** (7.598 → 7.035). Every other field regressed with this naive correction (t/dp/h already have L4 catching the same signal; cloud fields' 2-day rolling means are too noisy). wg wins because (a) no L4 diurnal correction competes, (b) wind gust has strong day-to-day persistence — windy days follow windy days — that L2's Kalman doesn't fully track, and (c) autocorrelation is broadly distributed across hours. Autocorrelation numbers also strong for t (afternoon cluster 14/15/16/19/22h all ρ_1 ≥ 0.3) and dp (nighttime cluster 21-23h, 00-01h ρ_1 ≥ 0.3) but their L4 already handles it. Path forward: Stage 1 wg-specific "recent drift" correction — per (regime × hour) tuned rolling window, likely 3-5 days with Kalman-like weighting instead of naive mean. Projected +5-7% MAE win on wg is real signal, comparable magnitude to the ch persistence gate impact.

</details>

<details>
<summary><strong>v0.6.341 • July 13, 2026</strong></summary>

- **Three UI cleanups on the top of the page.** (1) Scorecard "What this measures" prose wrapped in a `<details>` so it's collapsible — was always-visible, took vertical real estate below the metric grid. (2) Tri-column band (What's running / improving / evaluated) wrapped in a `<details open>` collapsible with a single "Current state" summary. Full state still visible by default; one click hides it if the reader only wants scorecard + accuracy chart. (3) **Status column added to the Current pipeline state table** with per-field one-liner summaries — e.g., `ws: Open regression. Walkforward L3 drop day 4/7. Earliest strip 07-16.` and `ch: Best-performing field vs raw — but persistence-skill Prod −1.08 vs L4-alone −0.29 (v0.6.336): L3 doing damage. ch persistence gate pending (day 2/7, flip 07-19).` and `wg: Stable win vs raw, but v0.6.339 Stage 0 diagnostic: L3 regresses in 10 cells (calm all bands +23-77%; unknown +22-38%).` One-line status per field surfaces the interesting story without expanding the "Applied layers" column into prose. Applied-layers cells trimmed to just the stack list, status story moves right.

</details>

<details>
<summary><strong>v0.6.340 • July 13, 2026</strong></summary>

- **Forecast Accuracy chart rewrite — only-applied layers + RMSE + bias tables.** Two long-standing issues fixed together: (1) most cards showed 4-5 chart lines stacked on top of each other because inactive layer arrays equal the previous applied layer's — visual noise for zero signal. Now `_layersFor()` filters to only-applied layers (L1 always, then only those with `_layerApplied()` true) — so temperature renders Raw + L2 + Production, wg renders Raw + L2 + L3 + Production, pa renders just Raw + Production. Same filter runs on the MAE band table columns. (2) MAE-only view missed occasional big misses (which show in RMSE) and systematic drift (which shows in signed bias). New `_buildMetricTable()` renders RMSE + bias companion tables below the MAE table for each card, using `tsDoc.per_layer_rmse_by_lead` and `tsDoc.per_layer_bias_by_lead`. Same "only-applied layers" filter applies. PP-Brier cards skip these — Brier already carries the second view. Bias table shows signed values with + prefix for positive to make sign obvious; near-zero cells get the "best" tint. Bias uses one extra decimal place so small drifts are visible. Also: Lt badge updated "off (dormant)" → "retired" (title tooltip gives the Fix B rationale). Section-intro prose rewritten to match — dropped the "colored lines are population-level diagnostics" caveat since inactive lines no longer render, and added the RMSE-catches-big-misses / bias-catches-drift framing.

</details>

<details>
<summary><strong>v0.6.339d • July 13, 2026</strong></summary>

- **Live Lc widget gate-note updated.** The JS render for the Lc card (used in a dev/preview embed) still carried a 07-10 gate-note explaining that a "day 1/7 as of 07-04" text had been aspirational. That whole caveat was time-boxed to the 07-10 audit and is no longer useful; replaced with the current state: "day 4/7 as of 07-13; anomaly-week HOLD until 07-18 window roll."

</details>

<details>
<summary><strong>v0.6.339c • July 13, 2026</strong></summary>

- **Second-pass debug page sweep — residual stale counter refs.** Found five more stale references that the first-pass regex missed: (1) "C1h + C1d earliest ship (both at day 1/7 07-12)" → 2/7 as of 07-13; (2) "Pre-frontal Stage 3 — narrow-promote counter cleared 7/7 (day 1/7 today)" — the "cleared 7/7" phrasing contradicted the day-1/7 counter and was rewritten to describe the 07-13 SHIP-set reset; (3) "ch persistence gate shipped 07-12 (ENABLED=False, day 1/7)" in the metric-framework blurb → 2/7 + Prod-vs-L4 corroboration pointer; (4) ch persistence gate under Production stack list: 7-day gate day 1/7 → 2/7; (5) L3 methodology paragraph still described pa's τ as 28d — updated to τ=42d per today's v0.6.334 bump.

</details>

<details>
<summary><strong>v0.6.339b • July 13, 2026</strong></summary>

- **Debug page reorg — Recent activity moved to its own top-level section + today's ships consolidated.** Two structural changes: **(1)** the "Recent activity" collapsible was previously nested inside "Engineering updates" — an odd hierarchy since it's more of a change log than a state snapshot. Moved to a new `<h2 id="sec-recent">` section directly above `#sec-status`, with a matching nav link between "Back" and "Engineering updates." **(2)** Today's 07-13 block collapsed from 10 individual version bullets into 7 theme groups: Lt retirement (v0.6.329 + 329a); cl gate wire (v0.6.330); measurement framework (v0.6.335 / 336 / 337); watch infrastructure (v0.6.331 / 332 / 333); pa τ (v0.6.334); wg L3 Stage 0 (v0.6.339); debug page sweeps (v0.6.338 / 338a / 339a). Same information density, half the visual footprint. Also cleaned two stale "Upcoming decisions" entries: the ch persistence gate line advanced day 1 → 2/7 (plus a Prod-vs-L4 corroboration pointer); the "h → L4 re-frozen" line rewritten to reflect that v0.6.331 streak counter now backs the flip criterion (7-day gate, day 2/7, earliest 07-18).

</details>

<details>
<summary><strong>v0.6.339a • July 13, 2026</strong></summary>

- **Debug page sweep — trim stale prose in Engineering updates.** Header curation stamp advanced 07-12 v0.6.327a → 07-13 v0.6.339. Table date advanced 07-12 → 07-13. Trimmed verbose descriptors: t row "Lt both branches disabled 2026-07-01 v0.6.276" → "Lt retired 07-13"; ws row dropped the "silent-failure fix v0.6.310+311" backstory (7 days old, window has settled) — now just says "L3 skip table: ne_flow all + sea_breeze 0-11h" + "L3 drop candidacy day 4/7"; sr row collapsed the multi-paragraph unit-mismatch investigation into a one-line pointer with the shortwave shadow-log key finding preserved. Bottom summary rewritten: dropped 07-08 "In flight" line entirely (closed 5 days ago), added the 07-13 wg L3 Stage-0 finding. Recent activity block: 07-10 (Fri) entries dropped (outside the stated 3-day rolling window; already in CHANGELOG.md) — replaced with a one-line pointer. Net delta: ~14 lines trimmed from the state table + ~7 lines from Recent activity.

</details>

<details>
<summary><strong>v0.6.339 • July 13, 2026</strong></summary>

- **wg L3 regression diagnostic — Stage 0 finding.** Follow-on to today's v0.6.336 result (wg Prod persistence skill −0.09 vs L4-alone +0.10 = a 19pp drag through the L3 step). New `analysis/h_wg_l3_regression.py` compares per-row L2 forecast (pre-L3) to L3 forecast (Production for wg — top-level `forecast`) against persistence per (regime × lead_band). Verdict rule: L3 HURTS if MAE_L3 > MAE_L2 by ≥3% AND L2 already beats persistence. **First read: 10 HURT cells / 36 judged** — all in a coherent physical pattern: **`calm` regime blown across every band** (+23%, +62%, +77%, +73%), **`unknown` regime across 3 bands** (+22 to +38%), **sea_breeze/6-11h + sea_breeze/24-47h, ne_flow/6-11h**. Fits the same architecture as the ws L3 skip table (ne_flow all + sea_breeze 0-11h): narrow whitelist / broad skip-table extension, ship where L3 wins (18 HELPS cells including frontal all bands + pre_frontal 24-47h at −22%). NOT shippable today — this is Stage 0. Needs 3-day confirmation streak per [[feedback-hypothesis-promotion-pipeline]] before Stage 1. Explains why v0.6.336 flagged wg L3 as damaging: `calm` alone (14,591 rows in 7d) accounts for most of the pooled skill drop.

</details>

<details>
<summary><strong>v0.6.338a • July 13, 2026</strong></summary>

- **Two prose cleanups on the accuracy section.** Dropped the "the `*` marker on the Production line auto-drops... satisfied since 2026-07-08" clause — the auto-drop already fired 5 days ago (chart code at line 3388 still handles the star conditionally, unchanged). Dropped "Lt only for t" from the population-diagnostics blurb — Lt retired 07-13, no Lt line drawn anymore. HTML parse-clean.

</details>

<details>
<summary><strong>v0.6.338 • July 13, 2026</strong></summary>

- **Debug page sweep after 7-ship session.** Counters advanced from 07-12 baselines to 07-13: ch persistence gate 1/7 → 2/7 (with a new note referencing the v0.6.336 Prod-vs-L4 corroboration); Lc 3/7 → 4/7; C1h + C1d Stage 3 counters 1/7 → 2/7; ws L3 strip 3/7 → 4/7 (bulk `day 3/7 (07-12)` and `day 3/7 as of 07-12` replaced with `day 4/7 (07-13)` / `day 4/7 as of 07-13`); pre-frontal Stage 3 wire-up eligibility note updated to reflect today's 1/7 reset (SHIP-set changed vs yesterday). Added "Recent activity" entries for the 7 ships from this session (v0.6.331 through v0.6.337). HTML parse-verified; served-page verified via local http.server. Following [[feedback_debug_page_canon]] — page IS source of truth, must skim after every ship.

</details>

<details>
<summary><strong>v0.6.337 • July 13, 2026</strong></summary>

- **Production-vs-L4 persistence skill delta surfaced at exec-summary altitude.** v0.6.336 added the numbers to `h_persistence_skill.json` and printed a supplemental line in the log tail — buried. Now `persistence_skill_watch()` in `analysis/runlog/build_executive_summary.py` returns a third list (`prod_delta_lines`) of every field where `|skill_prod − skill_l4| ≥ 0.02`. Rendered as a sub-block "Production vs L4 delta (L3 + specialists visibly moving persistence skill)" right under the at-risk lines. Direction markers: `→` when Production improves, `↓` when Production hurts. Today's read: 4 fields ↓ (ch −0.79, wg −0.19, cc −0.10, cm −0.04) + 1 field → (pp +0.14). Snapshot format extended to carry `skill_prod_mae_pooled` alongside `skill_l4_mae_pooled`, so tomorrow's regression detection catches Production-side flips too.

</details>

<details>
<summary><strong>v0.6.336 • July 13, 2026</strong></summary>

- **persistence-skill: recompute vs per-row Production alongside L4.** Phase 2 follow-on (ii) from measurement roadmap. `h_persistence_skill.py` now accumulates `ae_prod`/`se_prod` from the pair log's top-level `forecast` field (target_hour[short] — what users actually saw, including L3+specialists), and computes `skill_prod_mae`/`skill_prod_rmse` per cell + `skill_prod_mae_pooled` per field in the JSON. New "Production vs L4 delta" line appended after the main verdict flags any field where |skill_prod − skill_l4| ≥ 0.02 (specialists actually moving the number). **Today's first read surfaces two real findings:** (1) **ch is L4 −0.29 → Prod −1.08** — the ch pipeline (L3 firing + L4) is 3.7× worse against persistence than L4 alone. Confirms the ch persistence gate wired 07-12 is targeting the right layer; the L3 contribution is doing damage. (2) **wg L4 +0.10 → Prod −0.09** — wg L3 pushes wg from marginal-positive persistence skill to negative. Also cc goes +0.13 → +0.03 (L3 costs cc skill) and pp goes +0.18 → +0.32 (calibrator helps). Backward-compatible — existing `skill_l4_mae_pooled` key untouched, so persistence-skill watch (v0.6.332) snapshot continues to compare against L4.

</details>

<details>
<summary><strong>v0.6.335 • July 13, 2026</strong></summary>

- **pp Brier decomposition — Phase 3 of measurement framework.** New `analysis/pp_brier_decomposition.py` splits pp aggregate Brier into the three canonical components: **Reliability** (Σ (fc − obs_freq)² per bin — calibration), **Resolution** (Σ (obs_freq − obs_bar)² — discrimination), and **Uncertainty** (obs_bar × (1 − obs_bar) — climatology). Runs per lead band (0-5h / 6-11h / 12-23h / 24-47h) and pooled, for both raw (forecast_l1) and corrected (post-Fitter forecast) stages. Reports **Brier Skill Score vs climatology** = 1 − Brier/Uncertainty. Verdict rule: CALIBRATED if corrected Reliability improves and Resolution doesn't drop; MIXED if calibrator over-shrinks toward base rate; NOT CALIBRATED if Reliability worsened. Emits per-bin calibration gap table (`fc_mean − obs_freq`) — the diagnostic for finding "when we say X%, does it actually happen X% of the time." Today's first read: pooled corrected Reliability 0.01438 vs raw 0.01570 → **CALIBRATED, +8.4% better** (Δ Brier −0.00704). BSS +0.126 vs climatology. **New diagnostic finding:** systematic under-forecasting at moderate probabilities — when corrected says 30-40%, obs freq is 66% (gap −0.31); when corrected says 40-50%, obs freq is 66% (gap −0.22). Calibrator is well-calibrated at extremes but too conservative in the middle. Not immediately actionable — logged as a Stage 0 signal for a possible narrower calibration lookup in future.

</details>

<details>
<summary><strong>v0.6.334 • July 13, 2026</strong></summary>

- **Per-field τ bump for pa: 28 → 42.** `decay_tau_tuning.py` today's read: pa gains +5.5% MAE vs τ=14 at best-τ=42, confirmed by 3-consecutive-daily-read streak (the anti-noise gate that killed the July 1 ws τ=7 ship). Updated `TAU_DAYS_BY_FIELD["pa"]` in `weather_collector/processors/decay_fit.py`. Fitter runs once a day, so the change takes effect at the next `decay_fit` pass. Sits alongside the already-tuned `pp: 28` (from 06-21).

</details>

<details>
<summary><strong>v0.6.333 • July 13, 2026</strong></summary>

- **Pair-log anomaly detector shipped.** New `analysis/anomaly_detector.py` reads `forecast_error_log.jsonl` and compares two adjacent windows per field — last 7 days (recent) vs prior 21 days (baseline) — flagging fields whose forecast-value distribution has moved past threshold. Motivated by the 2026-07-11 cm Stage 4 flip (project_cm_stage4_degradation): between 06-27→07-04 and 07-04→07-11, cm HRRR forecast mean shifted 16% → 47% and MAE 15 → 33 — a boundary-condition-level change Stage 4's mixture check treated as one signal. Per-field metrics: forecast mean shift in σ-units (relative to baseline std), MAE % change, signed-bias shift, max quartile-bin population shift in pp. Verdict rule: **ANOMALY** if MAE > +50% AND (|Δfc_mean| > 1σ OR bias shift > 3σ_err); **WATCH** if MAE > +30% OR |Δfc_mean| > 1σ OR max bin frac Δ > 15pp; **CLEAN** otherwise; **THIN** if < 500 pairs in either window. Wired into digest exec summary: new "Pair-log anomaly alerts" block sits right after persistence-skill watch, one line per non-CLEAN field. Today's first read: 0 ANOMALY / 1 WATCH (pr, driven by 24.7pp precip-rate bin shift — expected given precip rate distributions are heavy-tailed) / 12 CLEAN. cm has recovered — recent MAE 23.2 vs baseline 26.7 — matches the "cause (b) transient weather" branch predicted in the cm-stage4-degradation memo.

</details>

<details>
<summary><strong>v0.6.332 • July 13, 2026</strong></summary>

- **Persistence-skill post-ship watch wired.** New `persistence_skill_watch()` in `analysis/runlog/build_executive_summary.py` compares today's `h_persistence_skill.json` per-field verdicts (ADDS VALUE / MIXED / NO SKILL) against a snapshot of last run's, stored at `analysis/output/runlog/persistence_skill_snapshot.json`. Two alert types emitted in the executive summary: (1) **regression** — field was ADDS VALUE last run and isn't today, and (2) **at-risk** — currently ADDS VALUE but pooled skill `< 0.20` (thin margin, could slip). Snapshot is overwritten on every run so tomorrow's digest compares against today. Motivation: `ws` in today's digest is +0.16 pooled — one bad run below `+0.10` and it drops from ADDS VALUE to MIXED silently. Watch surfaces those flips at exec-summary altitude next to post-ship 14-day alerts. First run after this ships will emit "no regressions" (seeds the snapshot); regressions caught starting the next digest.

</details>

<details>
<summary><strong>v0.6.331 • July 13, 2026</strong></summary>

- **h/l4 narrow-add streak counter wired — infrastructure for 07-18 ship candidate.** `h_full_regime_sweep.py` now emits `weather_collector/data/h_l4_add_candidates.json` alongside its text report, listing every h/l4 cell that cleared the halves-check ADD-candidate bar (both halves ≥3% delta, currently OFF). `analysis/runlog/claims.py` reads that JSON via existing `_claim_marginal_ship_cells` (schema matches c1h/c1d/pre_frontal — same `cells[key][band].status` shape); `analysis/runlog/build_executive_summary.py` registers `H_L4_ADD_CANDIDATES: ("h/l4 narrow-add", 7)` in `_NARROW_PROMOTE_GATES` and `_claim_source`. Digest's "Narrow-promote gates" block will now show a 4th line tracking the h/l4 ADD-candidate set. Refactor: `emit()` now returns `(text, add_candidates)` tuple so `main()` doesn't re-derive the list — single source of truth for the halves-check logic. Current 07-13 finding: **h/l4/calm/12-23h** (A_Δ=+5.0% n=704, B_Δ=+11.2% n=750, impact 5,893) plus **h/l4/calm/0-5h** (A=+3.8% B=+3.8%) — two-tool AGREE only on 12-23h per `l4_regime_lead_analysis` cross-check. Day 2/7 in the streak; earliest live-layer flip 07-18 pending 5 more agreeing daily digest reads. Ship-day code change (deferred to 07-18): add `"h"` to `L4_FIELDS` + narrow whitelist entry to `decay_apply.py` so h/l4 only fires in calm/12-23h.

</details>

<details>
<summary><strong>v0.6.330 • July 13, 2026</strong></summary>

- **cl persistence short-lead gate Stage 3 wired (ENABLED=False) — pre-emptive ship for 07-19 flip decision.** Saves a Sunday-morning scramble if the halves-verified re-run confirms the 07-12 finding. New processor `weather_collector/processors/cl_persistence_short_lead.py` mirrors ch_persistence_gate structure with narrow architecture: replaces `cloud_cover_low` with persistence-of-obs at leads 0-5h in **all 9 regimes**; longer bands SKIP by design (Stage 2 halves-check 07-12 diverged from HRRR anomaly window contamination; only 0-5h SHIPs cleanly). 9 SHIP cells / 36 in `weather_collector/data/cl_persistence_gate_curated.json`. Persistence source priority: `cloud_l2_meta.obs_mean` (pure KBOS+KBVY pre-Kalman) → `hourly[0].cloud_cover_low` fallback → no-op. Runs AFTER Lc (same bias-reintroduction rationale as ch gate — Lc's shift was fit against L4, would re-introduce bias on persistence). Applicability_map descriptor wired; gate_firing_log records fires/skips per tick. Sanity-tested inline: sw_flow synthetic fires 5 leads at 0-5h + 42 skips elsewhere; unknown regime falls back to hourly[0] correctly. Debug page updated in 4 places: Production stack Specialists list (new cl gate row), Still open watches (new day-1/7 counter), What's-improving (Stage 3 wired ✓), Upcoming decisions Sun 07-19 (was "ship or nothing?" → now "flip ENABLED?"), Recent activity 07-13 entry. If 07-19 halves-verified re-run confirms all 9 regimes still SHIP at 0-5h in a clean window, flip ENABLED=True. Otherwise gate stays OFF permanently.

</details>

<details>
<summary><strong>v0.6.329a • July 13, 2026</strong></summary>

- **Debug page — Lt out of Production stack list entirely.** Joe caught that the previous ship left an inline "RETIRED — moved to Retired below" pointer in the Production stack Specialists list. That's noise once Lt is fully retired. Removed the line; Lt now appears only in the Retired list (with the updated rationale from v0.6.329) and in a single top-of-page compact reference. "What's shipped" list at the top of the page: "Lt dormant" → "Lt retired 07-13 (Fix B held-out +0.29%)".

</details>

<details>
<summary><strong>v0.6.329 • July 13, 2026</strong></summary>

- **Lt Fix B answered — retired.** Ran `analysis/l6_fix_b_refit.py` on 202,321 pair rows (154k train / 47k held-out). Held-out MAE improvement **+0.29%** — well below the +1.0% ship gate. Panel B (sb_off × hour-of-day) looked like a real overnight cove-cooling signal on training (00-06h mean residual +0.9 to +2.1°F, 7 SHIP bins), but the wins dissolve out-of-sample. Panel A (sb_on × octant) came back with 0 SHIP bins entirely — the warming-branch signal was largely a fitting-against-raw-L1 artifact. **Mechanism:** L2's Kalman blend re-fits per-tick based on obs-vs-model bias and absorbs the same microclimate signal dynamically — a static hourly cove table would be adding a delta L2 already added. Net wash on held-out. Closes the 12-day "dormant pending Fix B refit" thread going back to 07-01. Lt permanently retired (both branches, ENABLED=False). Debug page updated: Built-not-applied entry moved to Retired with rationale; R&D queue Fix B entry closed; Microclimate line reworded to "retired" (was "until Fix B ships"); Recent activity 07-13 entry added. Memory: `project_lt_fix_b_answered.md`. Reinforces the persistence-skill picture from 07-12 — t is +0.68 pooled skill (one of the strongest fields), because L2's Kalman blend is doing more work than we thought.

</details>

<details>
<summary><strong>v0.6.328d • July 12, 2026</strong></summary>

- **Pre-frontal narrow-promote counter wired — closes the last aspirational-text gap.** After v0.6.320-323's silent-dormancy audit wired real counters for L3 drop-ws, LC_ENABLED, C1h + C1d, pre-frontal was the one remaining "no counter wired" gate — flagged explicitly on the debug page as "same aspirational-text pattern as C1h/C1d/LC pre-v0.6.323." `analysis/h_pre_front_orthogonality.py` now captures per-cell verdicts from both check loops (vs C1a, vs C1e) and emits `weather_collector/data/pre_frontal_curated.json` at end of run: `cells[field][band] = {status: SHIP iff ORTHOGONAL on BOTH checks else SKIP}`. First read today: 5 SHIP cells — ch 0-5h, ch 12-23h, cl 24-47h, cm 12-23h, cm 24-47h. `claims._claim_marginal_ship_cells` extended with `allow_empty=True` (returns `[]` not `None` when SHIP set is empty — legitimate stable state to track for a sparse axis like pre-frontal, unlike C1h/C1d where empty means the curator hasn't run yet). New `PRE_FRONTAL_SHIP_CELLS` claim + `pre-frontal` narrow-promote gate registered in `build_executive_summary._NARROW_PROMOTE_GATES`. Day 1/7 today; earliest Stage 3 wire-up 2026-07-19. Debug page updated: What's-improving Pre-frontal block flipped from "no counter wired" to "counter wired ✓"; Upcoming decisions replaced "infrastructure gap" entry with a real 07-19 wire-up Q/E/D; calendar gained 07-19 Pre-frontal entry.

</details>

<details>
<summary><strong>v0.6.328c • July 12, 2026</strong></summary>

- **Upcoming decisions block — rewritten current-forward.** Joe caught that the block was 90% stale: 07-03 "h + sr to L4" FROZEN entry was superseded 07-11 (re-frozen after halves-check), 07-04 C1 Stage 4 "re-check ~07-11" already happened + blocked, 07-04 raw-baseline verifier was already shipped, 07-06 pp/ws L3 drop was already decided ("don't drop wholesale"), 07-10 outcome was materialized, plus an explicitly-labeled "superseded above" block and a "Lsr post-ship watch through 07-10" note that had auto-lifted. Replaced with 8 actually-upcoming Q/E/D entries: Thu 07-16 ws L3 strip, Fri 07-17 ws octant re-read 1/3, Sat 07-18 C1 Stage 4 + Lc anomaly HOLD, Sun 07-19 ch persistence gate flip + cl narrow gate, h→L4 un-freeze eligibility, pre-frontal counter infra gap, and the Wyman Cove Swim Index product idea (kept — no date). Summary caption clarifies "forward-only; outcomes move to Recent activity" so the block doesn't accumulate history again.

</details>

<details>
<summary><strong>v0.6.328b • July 12, 2026</strong></summary>

- **Digest exec summary — persistence-skill verdict line surfaces pooled shape.** The prior verdict line said "5 ADDS VALUE, 4 MIXED, 3 NO SKILL" and hid that only ch is a real loss while cm's NO SKILL label is misleading. `h_persistence_skill.py` now computes n-weighted pooled skill_L4_MAE per field and emits: "Verdict: 5 ADD, 4 MIXED, 3 NO SKILL — genuine loss: ch (−0.26) — strict-NO-SKILL but positive pooled: cm (+0.14)." Fields within ±0.05 of zero pooled (cl at −0.017) are ties, not flagged as losses either way. Line stays under `extract_verdict()`'s 140-char cap so `analysis/runlog/build_executive_summary.py` picks it up cleanly.

</details>

<details>
<summary><strong>v0.6.328a • July 12, 2026</strong></summary>

- **Persistence-skill line — show pooled skill per field.** The "3 NO SKILL" verdict label was hiding shape — cm has +0.14 pooled skill (positive) but got the NO SKILL label because one lead band is BEHIND, tripping the strict "≥3 bands ADD, no BEHIND" rule. Only ch (−0.26) is genuinely losing pooled. Scorecard "vs Persistence" line now shows the pooled skill_L4_MAE next to each field slug (n-weighted across bands), sorted best-first within each verdict bucket. Verdict rule unchanged. NO SKILL row footer reframed: "strict verdict; only negative pooled numbers are genuine losses."

</details>

<details>
<summary><strong>v0.6.328 • July 12, 2026</strong></summary>

- **Persistence-skill → scorecard integration.** Closes the "shipped 2026-07-11 (`h_persistence_skill.py`) — awaits scorecard integration" gap that the scorecard prose has been advertising. `analysis/h_persistence_skill.py` now emits an enriched JSON with a per-field summary block (verdict + n-weighted pooled skill_l4_mae + band counts) and a top-line rollup (5 ADD / 4 MIXED / 3 NO SKILL), and publishes it to `gs://myweather-data/persistence_skill.json`. Debug page fetches `persistence_skill.json` alongside `time_series_diagnostic.json` and renders a "vs Persistence" line beneath the scorecard grid (`renderScorecardBanner` now takes a third `persistDoc` argument): 5/12 add value, 4 mixed, 3 no skill, with the ADD / MIXED / NO SKILL field lists. Scorecard prose measurement-gaps sentence rewritten — no longer says "awaits scorecard integration."

</details>

<details>
<summary><strong>v0.6.327c • July 12, 2026</strong></summary>

- **cl persistence investigation — Stage 1+2 explored, HOLD.** New `analysis/h_cl_persistence_blend.py` + `analysis/h_cl_linear_ramp_stage2.py`. cl does NOT have ch's regime shape: regime_gate + persist_only halves diverge (Δ_A −14% / Δ_B +13-15%, anomaly-inflated); linear_ramp τ scan monotonic-with-τ (no natural sweet spot); per-regime shows cloudy-active regimes (se_flow/calm/unknown, ~32% volume) want persistence while clear-flow regimes (sw_flow with tiny base MAE + nw_flow/pre_frontal/ne_flow/sea_breeze/frontal, ~68% volume) want L1 baseline. Stage 2 at τ=36 per (regime × lead_band): 20 SHIP / 2 MARGIN / 14 SKIP / 1 THIN; the 12-23h band is a graveyard (7 of 9 regimes SKIP). **Real signal: 0-5h narrow persistence gate — all 9 regimes SHIP at 0-5h.** Deferred: re-verify 2026-07-19 post-anomaly. If halves converge and 0-5h SHIPs hold, ship narrow `cl_persistence_short_lead.py` (all regimes, no skip table, leads ≤ 5h only). Otherwise cl gets no gate. Debug page updated: recent activity 07-12 entry, What's-improving panel new cl block, calendar 07-19 cl re-verify entry, hypothesis backlog table new NEW row. Memory saved: `project_cl_persistence_investigation.md`.

</details>

<details>
<summary><strong>v0.6.327b • July 12, 2026</strong></summary>

- **Debug page stale-date + counter pass + collapse-all toggle.** Joe caught "Last curated: 2026-07-10" + "Current pipeline state — 2026-07-09" — updated both to 2026-07-12. Live counters updated to current values: ws L3 strip day 2→3/7, Lc gate day 2→3/7, C1h + C1d narrow-promote streaks explicitly noted as day 1/7 today after SHIP-set instability reset (14 SHIP cells today for C1h vs 15 at ship; 12 vs 13+1 for C1d) — earliest flip pushed to 07-18. What's-improving panel: ch persistence gate added as new entry; C1h/C1d aspirational-history text replaced with current-state values. Calendar rewritten around today's forward view (07-15 cl Stage 1, 07-16 ws L3, 07-17 ws octant, 07-18 C1 Stage 4 + Lc window + C1h/C1d earliest, 07-19 ch persistence gate flip). Collapse-all / Expand-all toggle button added above the 4-card stack grid (Production stack, Built-not-applied, Retired, Upcoming decisions, Open architectural).

</details>

<details>
<summary><strong>v0.6.327a • July 12, 2026</strong></summary>

- **Debug page updated for v0.6.327 ship.** Recent activity block: added 07-12 (Sun) entry for ch persistence gate + landmark thread parked note; moved misplaced 07-11 entry into a proper 07-11 (Sat) block; trimmed stale 07-09 + 07-08 entries per rolling 3-day window. Still open watches: added ch persistence gate 7-day counter (day 1/7, earliest 07-19). Production stack Specialists: added ch persistence gate row. Scorecard measurement-gaps prose: ch response line now points at the shipped gate. Hypothesis backlog table: new SHIPPED row for ch persistence gate; active-candidates summary updated (3 → 4 Stage 3-gated; framing pointed at 07-19 as next flip candidate).

</details>

<details>
<summary><strong>v0.6.327 • July 12, 2026</strong></summary>

- **ch persistence gate Stage 2 preview + Stage 3 wired (ENABLED=False).** Follow-on to Sunday digest ship candidate. New `analysis/h_ch_persistence_blend_stage2.py` runs per-(regime × lead_band) halves-verified split of Joe's regime-gate design. Verdict: **22 SHIP / 6 MARGIN / 8 SKIP / 1 THIN** of 37 cells. SKIP concentration exposed by halves check — sw_flow long-lead (3 of 4 bands flip signs between halves), pre_frontal/24-47h loses full window +9.6%. Clean gate would have regressed real volume; cell-conditioned gate ships only where verified. New processor `weather_collector/processors/ch_persistence_gate.py` reads curated JSON, runs after Lc, replaces `hourly.cloud_cover_high` with persistence-of-obs on firing cells. Persistence source: `cloud_l2_meta.obs_mean` (pure KBOS+KBVY blend, pre-Kalman) with `hourly[0]` fallback. `frontal` regime always uses L4 by design. Telemetry stamped every tick; applicability_map contribution wired. Flip ENABLED=True only after 7-day live-layer change gate + no halves-flip in weekly re-reads.

</details>

<details>
<summary><strong>v0.6.326 • July 11, 2026</strong></summary>

- **Phase 2 persistence-skill baseline shipped.** New `analysis/h_persistence_skill.py`. 12 fields, MAE + RMSE + skill vs L1/L4. Results: 6 fields ADD VALUE (t/dp/h/pr/ws/sr), 3 MIXED (wg/cc/pp), 3 NO SKILL (cl/cm/ch). ch loses to persistence at every band despite L3+L4.
- **ch regime-gate design verified.** New `analysis/h_ch_persistence_blend.py`. Halves-check confirmed: L4 for `frontal` regime, persistence elsewhere → −19.6% pooled ch MAE. Only Joe-inspired regime-gate cleared halves stability.
- **Full regime-gate sweep tool.** New `analysis/h_full_regime_sweep.py`. Comprehensive halves-check across every (field, layer, regime, lead_band). 11 SKIP + 2 ADD candidates surfaced; halves-agreement mandatory.
- **Regime-gate-first framework codified.** Default framing for heterogeneous findings: gate ON where wins, OFF elsewhere — ship. Split-halves stability check codified as pre-ship gate (stronger than "wait 7 days"). Three noise patterns documented (recent-anomaly, older-residue-dominated, oscillation).
- **`production_whatif.py` bug caught + fixed.** Was evaluating regime-based skip cells on `state_obs`; live `decay_apply.py` uses `state_fc`. wg calm/24-47h flipped +42.8% → −62.9% under correct axis. Live shipped gates always used state_fc so behave correctly; only production_whatif estimates were biased.
- **Stage 4 refined view updated.** 27/1/2 → 26/0/9 after single-day window roll. 8 of 9 FAILs are cm × every band × difficulty key. Diagnosed as HRRR mid-cloud distribution shift 07-04→07-11 (mean cm forecast 16% → 47%), not a pipeline bug. Legacy ship BLOCKED; re-audit 07-18.
- **Lc anomaly-week HOLD.** Per-bin bias check on 07-04→07-11 window: cc 50-80/80-95 would over-correct 20-23pp; cl mid-high 11-30pp; cm 50-80 would under-correct 13pp. Do NOT flip ENABLED=True until 07-18 window roll + refit.
- **Gate-firing rollup — expected-dormant allowlist.** `analysis/gate_firing_rollup.py` now distinguishes ⚠ UNEXPECTED from ✓ EXPECTED (Lc/Lt/MLC gate-pending; C1h/t designed dormant). Silent dormancy still surfaces if it happens.
- **Debug page prose condensation pass.** ~15 sections rewritten tight (info retained, verbosity cut 30-70% each). C1 confidence layer block, R0 audit description, R2 state-stratified, Lc + dp Stage 1 candidates, retired archive, recent activity, live-layer gate, open watches.
- **Debug page canon updates.** Stage 4 numbers (26/0/9 + cm anomaly), h → L4 re-freeze reason (halves-check), persistence-skill script referenced (integration pending), Lc anomaly-week HOLD caveat added.

</details>

<details>
<summary><strong>v0.6.325a • July 10, 2026</strong></summary>

- **Debug page prose sweep — measurement framework.** Joe pushed back that v0.6.325 shipped only the scorecard tile logic, not the reader-facing rewrite he'd asked for ("write up the debug page so it talks about the right stuff"). Owned the miss, did the prose pass. Added a new collapsible <strong>"How we measure whether the forecast is good — the metric framework"</strong> section between the priority scoreboard and Engineering Updates. Covers: the core comparison shape (same pairs, same observations, same target), what "observed" means per field (mesonet Kalman blend for t/dp/h/ws/wg/pr, KBOS+KBVY METAR mean for cloud, Tempest median for sr, max WU gauges for pa, binary for pp), the three side-by-side metrics (MAE = typical error, RMSE = weights big misses, bias = systematic drift), why pp uses Brier not MAE, and the honest list of what's not yet measured (skill vs persistence, skill vs climatology, pp reliability decomposition). Explicit historical wording caveat: section descriptions written before v0.6.325 reference MAE as if it were the only measure — read them with the RMSE + bias context now available. <em>Accuracy section prose</em>: added metric caveat noting the L2-additive-bias fields (dp/h/ws/wg) have a 3-7pp gap between MAE improvement and RMSE improvement — the corrections occasionally add error on days when the raw model was already near-perfect. <em>Stage 4 audit prose</em>: added caveat that this scores drift on MAE only and would tell a different story on RMSE or on a raw-MAE-quartile-conditioned distribution (the difficulty lens exists but Stage 4 doesn't use it in its verdict yet). <em>State-stratified section prose</em>: similar caveat about MAE-only ranking. No code changes.

</details>

<details open>
<summary><strong>v0.6.325 • July 10, 2026</strong></summary>

- **Scorecard now measures what real weather models measure.** Joe pushed on whether the current MAE-only headline is honest ("beats raw by 9% on average" — is that the right question?). Walked through what NWS and ECMWF actually publish for forecast verification: MAE, RMSE, bias, sample counts, skill scores vs reference forecasts (persistence + climatology), Brier + reliability for probabilistic. We were doing MAE and Brier (for pp) — legit but incomplete. Phase 1 ships the trivially-computable additions:
  - <strong>RMSE</strong> — root of mean squared error. Same shape as MAE but weights big misses more. If RMSE is worse than MAE, the pipeline occasionally has blow-ups it hides in typical-day averages. Fitter (`decay_fit.py`) now accumulates <code>per_layer_sq</code> and <code>per_field_prod_sq</code> alongside the abs-error sums; emits <code>per_layer_rmse_by_lead</code> in <code>time_series_diagnostic.json</code>. First read against the current 200k pair sample: wg MAE −33% but RMSE only −26% (7pp gap — meaningful), dp/h similarly deflated 3pp under RMSE, pp MAE +20% but RMSE −3% (23pp difference — MAE is the wrong metric for pp, hence why we use Brier natively).
  - <strong>Bias</strong> — signed mean error (positive = over-forecast, negative = under-forecast). Already computed per-layer in the Fitter as <code>per_layer_bias_by_lead</code>; now also computed per Production row via <code>per_field_prod_signed</code>. Systematic drift MAE hides.
  - <strong>Scorecard banner rewritten.</strong> "Overall vs raw" tile now shows MAE mean, RMSE mean, MAE median. Biggest gain / regression tiles show MAE% (primary) with RMSE% and bias as compact secondary lines. Reader-facing prose explains what each metric answers, credits the local-network observations against which everything is scored, and honestly names what's not yet measured (persistence skill, pp reliability decomposition — "real gaps vs. an NWS-style verification report").
- **What did NOT change:** the underlying MAE math or comparison target. Production still compared to raw HRRR/GFS on the same pairs, against the same local-network observations. The pipeline itself is unchanged. Only the SCORECARD framing added the two metrics NWS/ECMWF also report.
- **Phase 2 (not in this ship, next session):** persistence baseline — for each pair-log row, look up obs at run_time (available in <code>obs_temp_log.json</code>) and score the forecast against "what would have happened if I just said 'same as it is now.'" Answers the "is the pipeline actually adding value at short lead where persistence is a strong baseline" question. Real work; ~2-3 hours; needs a pair-log join + a persistence-forecast column added to pair rows going forward.
- Phase 3 (later): pp Brier reliability decomposition. Phase 4 (optional): climatology baseline.

</details>

<details open>
<summary><strong>v0.6.324a • July 10, 2026</strong></summary>

- **Bug fix in v0.6.324 odometer — Production was wrong for 6 of 12 fields.** The pair log's `forecast` field is captured at pair-log time. For L2-additive-bias fields (dp/h/t/ws/wg/pr) L2 has already run so `forecast == forecast_l4`; but for fields where the correction runs LATER (cc/cl/cm/ch under L3/L4, sr under Lsr, pa) `forecast == forecast_l1` (raw). Caught by Joe with a direct question ("I only care whether my forecast beats raw — am I wrong?") that made me spot-check what `forecast` actually meant. Fix: `fc_prod = forecast_l4 or forecast_l3 or forecast_l2 or forecast_l1 or forecast` — matches how state_stratified_accuracy computes Production. Deleted + rebuilt <code>production_regime_trajectory.jsonl</code> from scratch. Corrected per-field 28-day Production %-vs-raw picture: wg −35%, ch −33%, ws −17%, dp −16%, cc −8%, h −7%, cm −5%, t −2%, sr −1% (contaminated), pr −0.6%, cl −0.1% (no corrections in pipeline), pa 0% (no corrections), pp +20% worse (pre-drop L3 rot; expect shrinking as post-drop rows fill). The earlier v0.6.324 changelog's claim that cloud fields showed "small per-day variance, consistent aggregate benefit" survived — that language was accurate for what happens IF the correction is measured correctly. What was WRONG was the star-flagged/flat distinction for cloud fields specifically. The L2-additive-bias family finding (dp/h/ws/wg show large Q1-Q4 difficulty variation) is unchanged because `forecast` did equal `forecast_l4` for those. c1_stage4_difficulty_lens.py already used the deepest-layer lookup, so its earlier "weather-confound vs REAL DRIFT" findings stand.

</details>

<details open>
<summary><strong>v0.6.324 • July 10, 2026</strong></summary>

- **`production_regime_trajectory.py` — the odometer.** New daily-digest script that computes per-(day × regime × field) Production % vs raw and appends to <code>analysis/output/production_regime_trajectory.jsonl</code>. Answers "are we actually improving, or has the weather been favorable?" — a question the aggregate Production %-vs-raw scorecard can't answer because it's regime-blind. Bootstrapped 28 days of retroactive history on first run (2,225 rows across 9 regimes × 12 fields × the last month). <strong>First read already surfaced a real finding:</strong> aggregate dp shows Production −20% better than raw, but per-regime the pipeline is HURTING dp by +21% to +40% in every regime observed (pre_frontal, se_flow, sw_flow, sea_breeze). Simpson's paradox — favorable regime mixture is hiding a real problem. Same shape shows on ws (aggregate +5.8%, per-regime +7% to +22% in every moderate+ wind direction except sea_breeze). Validates the ws-octant Stage 0 finding from earlier today: the ws structural residual isn't distributed uniformly across regimes. Idempotent on the (day, regime, field) key — safe to re-run; LAG_DAYS=2 lets late-arriving pair rows land before a day's number is frozen. WINDOW_DAYS=30. MIN_N_PER_CELL=30. Debug page telemetry consumer for regime-shift charts pending — this ship is the data layer only.

</details>

<details open>
<summary><strong>v0.6.323a • July 10, 2026</strong></summary>

- **Debug page canon sweep after v0.6.323 counters ship.** Every "day N/7" gate reference on the page was carrying pre-v0.6.323 aspirational numbers (LC "day 1/7 as of 07-04", C1h "day 2/7", C1d "day 5/7", ws L3 "day 8/7", pre-frontal "day 5/7"). Swept the whole page: "Last curated" bumped to v0.6.323. Priority scoreboard (top block): all four gate rows now note the counter is real and started at day 1/7 today; pre-frontal explicitly marked "no counter wired" (no Stage 3 curated table to walk yet). Calendar block: 07-10 rows retired — sr clean read pushed to 07-11 (window closes tonight), ws L3 strip pushed to 07-16, LC/C1h/C1d rows added for 07-16, ws-octant weekly re-read added for 07-17. Correction-stack narrative (L3 lead-decay row + Lc row): "earliest ship 07-10" swapped to 07-16 with the streak-infra reference. Historical timeline block (07-10 outcome): rewrote the "sr clean + ws L3 strip earliest ship" bullet to state what actually happened (sr suppression closes tonight; ws L3 strip didn't ship because the gate was fiction). C1 confidence section (G1 gated candidates): noted the C1h + C1d narrow-promote counters wired in v0.6.323. Recent activity: added v0.6.323 entry summarizing all three counter fixes + false alarms owned + C1 gate-firing coverage. Also fixed a JS-rendered hardcoded "day 1/7 as of 2026-07-04" caption in the Lc live-state block. No code changes — canon only.

</details>

<details open>
<summary><strong>v0.6.323 • July 10, 2026</strong></summary>

- **Silent-dormancy audit — three more gaps closed, ripple from v0.6.320.** Following the v0.6.320 streak-infra fix, ran a co-owner audit of every "day N/7 gate" mentioned in memory + on the debug page to check which had real counters behind them. Three had none — all aspirational text.
  - <strong>LC_ENABLED counter (Fix 1).</strong> The 7-day Lc live-layer-change gate had no <code>_claim:LC_ENABLED</code> writer in <code>digest_history.jsonl</code>. Divergence report rendered "GATED 1/?" literally — the "?" was because there was no gate. Same silent-dormancy class as the L3/L4 wedge. Wired <code>_claim_lc_enabled()</code> in <code>claims.py</code>, added <code>LC_ENABLED: 7</code> to <code>GATES</code> in <code>divergence_report.py</code>, added to the dormancy-guard <code>_claim_source</code> dict. Divergence now shows "GATED 1/7 (6 to go)" backed by a real streak walker.
  - <strong>C1h + C1d narrow-promote gate counters (Fix 2).</strong> Both marginal-axis Stage 3 tables had "day N/7 narrow-promote gate" text on the debug page (C1h "day 2/7", C1d "day 5/7") with no counter behind them. Wired <code>_claim_marginal_ship_cells()</code> in <code>claims.py</code> — reads sorted SHIP-cell list from <code>c1h_curated.json</code> / <code>c1d_curated.json</code>; new "Narrow-promote gates (C1 marginal-axis Stage 3)" section in the digest exec summary walks history for consecutive-day matches. Both start at 1/7 today — the "5/7" and "2/7" numbers were fiction. Earliest C1d ship pushed 07-11 → 07-16; earliest C1h ship stays 07-16.
  - <strong>Post-ship 14-day watch (Fix 3) — false alarm on me.</strong> Grepped for it, thought it didn't exist, wrote up a "watch script needed" recommendation. Actually wired in <code>build_executive_summary.py</code> since forever, ran this morning showing "• none" + the two Lsr suppression entries. Owning the miss.
- <strong>Frontal events log stale — also false alarm on me.</strong> Flagged the 2-day gap as broken; actually correct behavior (<code>_append_event</code> only writes on new detected events; last front was sea_breeze 07-07T21:37, hsf_group=baseline correctly reflects >24h post).
- <strong>C1 gate-firing log coverage.</strong> <code>confidence_layer.py</code> now calls <code>gate_firing_log.record_firing()</code> for C1h + C1d per tick (regime = obs regime). C1h counts fires + coax_gated skips per field; C1d counts fires per field when live σ ≥ Q3. C1e stays as a lookup-axis (contributes to multi_hits, not a marginal premium). Closes the "did the C1h cl-cells actually fire when they should have?" question for the next 7-day rollup.

</details>

<details open>
<summary><strong>v0.6.322a • July 10, 2026</strong></summary>

- **Debug canon refresh for today's three ships.** "Last curated" bumped to v0.6.322. Recent activity block rotated: today's four entries (v0.6.320 streak-infra fix, v0.6.321 C1h ortho gate, v0.6.322 ws-octant Stage 0, and the read-side confirmations for C1h ortho + verdict-language guards + applied-layer audit second live tick) added at the top; 07-07 entries rotated out per the rolling 3-day retention rule. C1 confidence section (G1 gated candidates) updated: retracted the v0.6.316 "⚠ Scope note: broader than narrow-promote scope" caveat that today's v0.6.321 co-axis ortho gate resolved; Stage 4 latest read updated to the 07-09 refined view (27 PASS / 1 WATCH / 2 FAIL / MIXED). Stage 1 candidates rolling table: C1h row updated to reflect wired ortho gate; new "Per-octant ws L2 additive" row added under NEW candidates with the 3-weekly-re-read gate; header count 5 → 7 active. Group A C1h Stage 1 section rewritten to summarize the ortho verdicts + wired gate in place of the old scope caveat. No functional code changes — canon only.

</details>

<details open>
<summary><strong>v0.6.322 • July 10, 2026</strong></summary>

- **`h_ws_octant_bias.py` — Stage 0 diagnostic for direction-conditional raw ws bias.** Bins raw ws forecast error (signed) by observed wind octant × lead band, with an `obs ≥ 5 mph` "moderate+" subset that filters out calm-wind wd noise. First read (07-10) surfaced a real signal: HRRR **over-forecasts moderate+ ws by +0.9 to +1.9 mph on SW/S/E/NE octants, near-zero on NW/N/W**. Story matches Marblehead geometry — SW/S/E winds cross land/town on final approach so friction reduces obs below HRRR's open-water expectation; NW/N/W come across water in the last stretch so HRRR is right. NE +0.91 mph doesn't fit the simple friction story — possible Salem Neck / Beverly peninsula partial blockage or Salem Sound channel effects. **Queued as Stage 1 candidate**, not fast-tracked: three weekly re-reads (07-17, 07-24, 07-31) to confirm sign-stability, a regime cross-cut to rule out `sw_flow`-regime confounding, and NE-outlier resolution before writing Stage 1. Directly targets the queued "ws structural residual" investigation (~+17-20% MAE vs raw after full targeted package). Current ws L2 is per-octant-max → median blend with no additive component, so this signal passes through untouched. Script picked up automatically by `run_digest.sh` for the weekly cadence.

</details>

<details open>
<summary><strong>v0.6.321 • July 10, 2026</strong></summary>

- **C1h per-cell co-axis ortho gate.** `h_c1h_orthogonality.py` first read (07-10) passed the overall PROMOTE gate (11 orthogonal cells / 30 judged), but per-cell only cl × 3 bands are ortho to BOTH C1f (precip_fc > 0.01 in band) and C1e (post-frontal < 24h). The remaining 12 SHIP cells in `c1h_curated.json` are wholly-or-partially-redundant with one or both incumbent axes — firing them when the co-axis was on would double-widen the confidence band without adding independent signal. Rather than pruning the curated table (loses signal when the co-axis is off), added an in-code per-cell gate in `confidence_layer.py`: cl fires freely, cc cells suppressed when C1e is on (cc 24-47h also suppressed when C1f is on), cm cells suppressed when C1f is on, ch 6-11h/12-23h suppressed when either is on, and ch 24-47h + t × 3 bands (REDUND to both) never fire. Also: `_c1h_fires_per_band_field` now returns a new `"coax_gated"` state (distinct from `"flat"`) so gate suppressions are visible in the confidence telemetry; fails closed on any unlisted (field, band) so a future c1h_curate promotion can't silently add a cell without a matching ortho verdict. Verified live in this tick — ch 24-47h and t × 3 report `coax_gated`, cl × 3 fires freely, remaining cells report `flat` (trend didn't cross this tick; gate-conditional paths verify next time C1f or C1e is on).

</details>

<details open>
<summary><strong>v0.6.320 • July 10, 2026</strong></summary>

- **Digest streak-infra dormancy fix.** The L3-drop-ws whitelist streak had been wedged at 0/7 for **7 consecutive days** (07-04 → 07-10) because every morning digest wrote `_claim:L3_FIELDS: null` into `digest_history.jsonl` even while the source `walkforward_l3l4_validator` verdict was populated in the same row. Root cause: `analysis/runlog/claims.py::_claim_walkforward()` reads the .log via a stdout-redirect from bash `>`, subject to Python's block-buffered stdout at child-exit. `analysis/runlog/divergence_report.py::claim_from_walkforward()` was a byte-for-byte duplicate of the same parser and succeeded in the same digest run seconds later — one path wedged the streak while the other displayed the correct verdict every morning. Same silent-dormancy class as the applied-layer audit (v0.6.317) and gate-firing log (v0.6.318), but the streak infrastructure had no equivalent guard. Fix: (1) `claims.py` falls back to `walkforward_l3l4_summary.txt` (direct `with open("w")` — deterministic flush) if the .log regex misses; (2) `divergence_report.py` imports the one canonical impl from `claims.py`, killing the duplicate; (3) `build_executive_summary.py` dormancy-guards the null-claim-with-populated-source-verdict case (skip write + WARN to stderr instead of poisoning the streak); (4) `_streak_for` filters today by UTC date rather than `rows[:-1]` — safe against skipped writes.

</details>

<details open>
<summary><strong>v0.6.319f • July 9, 2026</strong></summary>

- **Section 2e "Post-aggregate-bias forecast" marked as engineering view (pre-clamp).** The grid of per-field cards under that heading renders values *after* L2 bias offset but *before* downstream layer clamping (`FIELD_BOUNDS` in `decay_apply.py`), so cloud cover can legitimately show 121%, precip probability −6%, precip amount −0.025 in — physically impossible outputs that are correct as diagnostic intermediates but could be mistaken for user forecasts. Header now reads "…engineering view (pre-clamp)" and a highlighted caveat block above the grid explains what these values mean, with the redirect: if any of these look wrong for user display, check the L3 / L4 / clamp path, not this section.

</details>

<details open>
<summary><strong>v0.6.319e • July 9, 2026</strong></summary>

- **Gate-firing frequency default view: summary-first, detail expandable.** The Runtime firing subsection was rendering the full per-(operator × field × regime) table by default — verbose when everything is healthy. Restructured to lead with a compact 5-row summary block:
  - <em>Operators monitored: N</em> (with operator list)
  - <em>Field × operator pairs: N</em>
  - <em>Skip-table cells firing: N</em> (with total skip event count)
  - <em>Dormancy flags: N ✓/⚠</em> (silent-dormancy candidates from the rollup)
  - <em>Fires while disabled: N ✓/⚠</em> (fires reported for Lt / Lc / MLC, all `ENABLED=False` — nonzero would mean the code path executed despite the gate being off)
  Two rightmost checks show green ✓ when 0, red ⚠ when nonzero. Per-cell table moved into a `<details>` block with a "Per-cell detail — N rows" summary line. Dormancy detail block only renders when there are flags to show. Same JSON payload, cleaner default hierarchy.

</details>

<details open>
<summary><strong>v0.6.319d • July 9, 2026</strong></summary>

- **Recent activity block bumped for afternoon ships.** Consolidated the four verdict-language fixes (v0.6.316e / v0.6.318d / v0.6.319b) into a single "4th instance in 3 days" bullet; added new bullets for v0.6.318f→v0.6.319 (Applicability map merge + full column populate + ranked-opportunities excluded block) and v0.6.319c (dp depression frontal branch closed / nor_easter watch opened). "Last curated" bumped to 07-09 v0.6.319c.

</details>

<details open>
<summary><strong>v0.6.319c • July 9, 2026</strong></summary>

- **dp depression regime — frontal branch closed, nor_easter watch opened.** Today's `h_dewpoint_depression.py` confirmed the frontal signal fell below the 1.5°F action floor: −2.19 → −1.98 → −1.51 → **−0.87°F** across four reads. Branch retired; Stage 1 candidacy on frontal-dp-depression closed. Meanwhile, `nor_easter` surfaced at +3.79°F ★ — passes the magnitude floor but n=279 (nor_easters are rare, sample won't grow fast). New watch: 3 consecutive reads with n growing AND |bias| holding above 1.5°F before Stage 2 curation. sw_flow softened +1.40 → +0.95⚠ (into watch band). Updates: (1) Stage 1 candidate card on debug page, (2) hypothesis tracking table row, (3) `project_todo.md` item 3.

</details>

<details open>
<summary><strong>v0.6.319b • July 9, 2026</strong></summary>

- **Fix `simulate_windows.py` R6 verdict wording.** Digest was reporting "R6: all 7 cutoffs agree → SHIP → PROMOTE" which read as a new-candidate promotion signal. But R6 (regime-transition penalty) was pivoted from would-be bias correction to confidence axis **C1a** on 2026-06-19 v0.6.141 per `project_c1_pivot_to_confidence`. The signal is already live in `confidence_layer.py:104` — today's SHIP verdict is a health-check pass on C1a, not a Stage 1→2 promotion. Added an `ALREADY_SHIPPED_AS` map so R6's SHIP now prints as "→ STABLE (R6 signal already live as C1a — Regime transition (confidence axis, live since v0.6.141 2026-06-19); this is a health check pass)". HOLD would print as "REGRESSION WATCH" (underlying signal weakened). Extensible — future hypotheses that get repurposed to other architectural slots go into the map instead of being retagged one by one.
- **Fourth instance of "stated intent vs code behavior" today.** Divergence-reporter regex (07-07), scorecard-Brier folding (07-07), wind-shift-rate ortho=0 (07-09 AM), precip_fc live-axis (07-09 PM), simulate_windows R6 (07-09 PM). Bright-line rule now codified in the memory: any script that outputs an action verb like "PROMOTE" / "KILL" / "SHIP" / "RETIRE" needs an "already live?" check against production before its verdict is trustworthy.

</details>

<details open>
<summary><strong>v0.6.319a • July 9, 2026</strong></summary>

- **"Current pipeline state" summary block date bumped 2026-07-07 → 2026-07-09.** The date on the collapsible one-glance summary was 2 days stale — someone updated the numbers during yesterday's + today's canon sweeps but missed the summary header. Table data itself is fresh (t −1.1%, pr 0%, ws +5.3% per 07-08 v0.6.316d refresh + 07-09 v0.6.318e ws update).

</details>

<details open>
<summary><strong>v0.6.319 • July 9, 2026</strong></summary>

Three related debug-page cleanups bundled after the deploy-verify cycle:

- **`decay_apply.py::describe_applicability()` populates `gated_by` + `current_state`** for L3 and L4 fields. Previously the descriptor emitted only `field` and `fires_when`, so the applicability map's "gated by" and "current state" columns fell back to em-dashes for every L3/L4 row — visually noisy and inconsistent with Lsr/MLC/Lc/Lt which populate all four columns. New behavior: `gated_by = "L3_FIELDS"` (or `"L3_FIELDS + SKIP_TABLE"` when the field has skip cells), `current_state = "firing at every lead"` (or `"firing except in skip cells (see 'applies when')"` for skip-cell fields). Same for L4. Deploy verified 11:47 tick.
- **L2 hand-curated `gated by` column populated across the board**. Previously every L2 row showed em-dash under "gated by" — the semantically-correct-but-unhelpful state for the always-on rows. Filled in: t/dp/h → `always on`; h adds `(K-taper 1.0 → 0.4 by lead 24h)`; pr → `disabled at module level` (row was already updated for `current_state`); cc → `always on (needs KBOS or KBVY at current hour)`; cl/cm/ch → `always on (derives from cc)`; ws/wg → `always on (direct-selection, not additive)`; sr/pp/pa → `n/a — no obs network`.
- **C1 confidence-layer axis rows now inherit layer-level gate.** `describe_applicability()` in `confidence_layer.py` populates `gated_by = "ENABLED"` and `current_state = "ENABLED False — ..."` at the *layer* level (top of the block), but per-axis rows in the `axes` array were showing em-dashes because the renderer only looked at row-level fields. Renderer updated to fall back to layer-level values when the row-level ones are missing — semantic inheritance, no data duplication needed. All 7 C1 axis rows (C1a, C1f, pt_bin, cluster_spread, C1e, C1h, C1d) now show the shared ENABLED gate + "ENABLED False" state.
- **Ranked opportunities table (state-stratified section)**: addressed rows no longer occupy top-10 slots. Previously the top-10 rendered mixed addressed + unaddressed with addressed rows dimmed to `opacity:0.5` and tagged — 40% of the visible slate was non-actionable (all 4 sr dimensions rank at the top by raw spread). New behavior: filter addressed rows out first, then slice to 10 actionable. Original ranks are preserved in the `#` column so readers still see position jumps. Addressed rows moved to a collapsible `<details>` block below the table with per-field explanation (`sr → Lsr shipped 2026-06-28 v0.6.248...`). Regression watch preserved: if a shipped correction fails, its spread stays high AND its per-layer MAE drifts — the addressed block still shows the spread, so nothing is invisible. Accuracy-section intro blurb rewritten to describe the new behavior.

</details>

<details open>
<summary><strong>v0.6.318f • July 9, 2026</strong></summary>

- **Merge Gate-firing frequency into the Applicability map section.** Two lenses on the same object — Applicability = "what's *configured* to fire and under what gates" (static), Runtime firing = "what's *actually* firing per operator × field × regime" (7-day rolling). Neither is complete alone: applicability alone hides silent dormancy; firing alone doesn't tell you what SHOULD have fired. Section header renamed from "Applicability map — what corrections trigger, and why" to "Applicability map — what corrections trigger, why, and when they actually fire". Intro block updated to describe the two-lens split. The standalone `<h2 id="sec-gate-firing">` deleted; its content moved to a bordered sub-block right after the dynamic applicability blocks. TOC "Gate firing" entry removed — one anchor now covers both lenses. Yesterday's recent-activity Phase-(c) bullet updated to reflect the merge.

</details>

<details open>
<summary><strong>v0.6.318e • July 9, 2026</strong></summary>

- **Debug page canon sweep — rotate Recent activity window + refresh accuracy blurb.** "Last curated" bumped to 07-09 v0.6.318d. New "2026-07-09 (Thu) — today" section added with 6 thematic bullets covering today's 9 commits: Fitter preflight (v0.6.317), Stage 4 refined view + non-precip subset + mixture check (v0.6.316e, v0.6.317a), cl marine-layer Stage 1 sanity check (negative), gate-firing log three-phase pipeline (v0.6.318, .318a, .318b), verdict-language fixes (v0.6.316e, v0.6.318d), dead L6/Cove UI cleanup (v0.6.318c). "2026-07-08 (Wed) — today" marker rotated to just "(Wed)". "2026-07-06 (Mon)" section trimmed per the rolling 3-day window rule (4 entries → CHANGELOG). "Still open watches" C1 lines updated: calibration audit pass rate refreshed to today's 63.64%; Stage 4 line rewritten to reflect the refined-view MIXED (27/1/2) with real DEGRADED = 2 cells (ws/24-47h transition + cl/12-23h stable). Accuracy section blurb refreshed — <code>ws</code> now +5.3% down from +25.7% pre-skip-table (still an open regression per Stage 4), t and pr in-flight language removed (both landed 07-08).

</details>

<details open>
<summary><strong>v0.6.318d • July 9, 2026</strong></summary>

- **Fix `h_precip_fc_orthogonality.py` verdict wording** — the ≥8-orthogonal-cells branch was printing "→ PROMOTE: precip_fc is independent…" which made today's digest surface C1f as a new candidate needing action. But C1f (precip_fc>0) has been a live confidence axis since v0.6.215 on 2026-06-24 — this script is a stability re-check against the newer C1e axis (shipped 07-01), not a candidate for promotion. Reworded all three branches (PROMOTE / KILL / MIXED) to acknowledge the axis is already live: "→ STABLE" for the re-check-pass branch, "→ REGRESSION WATCH" for the redundant-heavy branch, and MIXED gets a "watch for verdict stability" caveat. Same "stated intent vs code behavior" pattern documented this morning on `h_wind_shift_rate_orthogonality`; extended note in the `feedback_stated_intent_vs_code_behavior` memory.

</details>

<details open>
<summary><strong>v0.6.318c • July 9, 2026</strong></summary>

- **Delete dead L6/Cove UI code from `corrections_debug.html` (213 lines).** `loadL6()` + `renderL6Live` + `renderL6Tables` + `renderL6History` + `renderL6MAE` + `COVE_DELTA_BY_OCTANT` + `COVE_HOUR_DELTA_SB_OFF` all wrote to DOM element IDs (`grid-l6-live`, `status-l6-live`) that no longer exist in the file — the Lt live-state UI section was removed when Lt went dormant on 2026-07-01, but the JS wasn't cleaned up. Result was a console error on every page load: `TypeError: null is not an object (evaluating 'grid.innerHTML = …')` inside `renderL6Live` line 5533. Deleting the entire orphaned block gets rid of the error and removes stale cove lookup tables that hadn't been synced to `cove_correction.py` in weeks. Lt still has its "[DORMANT LAYER]" R&D section on the debug page — that section is untouched; it reads its own `<div id="lt-live-state">` from `renderLtLiveState()`, which is unrelated to the deleted L6 code.

</details>

<details open>
<summary><strong>v0.6.318b • July 9, 2026</strong></summary>

- **Gate-firing frequency — Phase (c): debug page render.** New section on `corrections_debug.html` adjacent to the Applicability map (`#sec-gate-firing`, TOC entry "Gate firing"). Fetches `https://data.wymancove.com/gate_firing_rollup.json`, renders a table of operator × field × regime with fires / skips / ticks / rate-per-tick columns. Dormancy flags block at the top surfaces (a) operators that never fired, (b) operator+field pairs that never fired across any regime, (c) ★ silent-dormancy candidates — cells where the operator ran ≥5 ticks in that regime with 0 fires. That last class is the exact signature that hid the ws L3 skip-table dormancy for 4 days after v0.6.279; catching it in the log is the point.
- **`analysis/gate_firing_rollup.py`** now also publishes to GCS (`upload_json` from `weather_collector.gcs_io`) so the debug page can fetch the artifact via `data.wymancove.com`. Digest cron on Joe's Mac has the necessary gcloud auth; failure is silent — the local `analysis/output/gate_firing_rollup.json` still lands.

Together with v0.6.318 + v0.6.318a, the full three-phase gate-firing pipeline is now operational: Phase (a) per-tick logging → Phase (b) 7-day rollup with dormancy flags → Phase (c) debug-page surface. Complements the applied-layer audit (v0.6.317) — audit is static config coherence, rollup is runtime firing visibility.

</details>

<details open>
<summary><strong>v0.6.318a • July 9, 2026</strong></summary>

- **Gate-firing log — extended to Lsr, MLC, Lc, Lt + Phase (b) rollup.** Each of the four specialist correctors now emits a per-tick firing row alongside L3/L4. Semantics per operator:
  - **Lsr** (`solar_correction.py`): `fires` = leads where compute_solar_correction returned a non-zero delta (sun up, non-skip regime, table hit); `skips` = leads where sun was up + regime was in `L5_SKIP_REGIMES` (would-have-fired-but-suppressed). ENABLED=True; expect real fire counts on daytime ticks.
  - **MLC** (`marine_layer_correction.py`): `fires` = 0 (ENABLED=False); `skips` = `len(per_lead)` (gated-off would-have-fired count). Records even when weather_data has no cc array so the rollup can distinguish "MLC didn't run" from "MLC ran with 0 fires."
  - **Lc** (`cloud_saturation_correction.py`): `fires` = 0 per field (ENABLED=False); `skips` = per-field `cells_fired` count. First live tick showed cc=44/cl=18/cm=20/ch=38 — the would-fire volume that made this a high-impact ship candidate.
  - **Lt** (`cove_correction.py`): `fires` = 0 (ENABLED=False + both branches return 0.0); `skips` = 0 (nothing to suppress since compute returns 0). Presence of the row confirms Lt runs each tick, absence of fires confirms the dormant state.
- **`analysis/gate_firing_rollup.py`** — Phase (b) 7-day rollup writer. Reads `gate_firing_log.jsonl` from GCS, aggregates by (operator, field, regime), computes per-tick fire rate, and emits `analysis/output/gate_firing_rollup.json` with `dormancy_flags` (`operators_never_fired`, `operator_field_pairs_never_fired`, `operator_field_regime_never_fired_with_nonzero_ticks`). Nightly digest picks it up automatically via `analysis/*.py` loop.
- **Phase (c) — debug page render adjacent to Applicability map — queued** for a follow-up session once a few days of log accumulate.

Deploy verified 10:38 local — first post-deploy tick emitted all 6 expected operator rows (L3, L4, Lsr, MLC, Lc, Lt) with correct fire/skip counts.

</details>

<details open>
<summary><strong>v0.6.318 • July 9, 2026</strong></summary>

- **Gate-firing log — Phase (a): collector-side counters.** New `weather_collector/processors/gate_firing_log.py` provides `record_firing(operator, regime, by_field, leads)` (module-level tick buffer) and `flush_to_gcs()` (append via GCS compose, same pattern as `forecast_error_log`). `decay_apply.py` now tracks per-field `fires` and `skips` counts through the L3 and L4 loops and calls `record_firing` after each pass. `collector.py` flushes the buffer at end of every tick after the weather_data upload. Failsafe: any GCS error logs + drops the buffer, does not affect the already-published weather_data. **First tick after deploy (09:57 local):** `gate_firing_log.jsonl` created with 2 rows — L3 pre_frontal (ws/wg/cm/ch all 48 fires 0 skips), L4 pre_frontal (cc/ch same). Ready for the `ne_flow` / short-lead `sea_breeze` ticks where the skip table will populate `skips` counts. **Phase (b) — 7-day rollup writer to `gate_firing_freq.json` — queued.** **Phase (c) — debug page render adjacent to Applicability map — queued.** Definition of "fired" = correction actually mutated the array (not "would have applied"); the log distinguishes real firing from silent dormancy of the class that hid ws L3 for 4 days after v0.6.279.

</details>

<details open>
<summary><strong>v0.6.317a • July 9, 2026</strong></summary>

Analysis-side bundle from the afternoon Stage 4 rework — three linked pieces:

- **`analysis/c1_stage4_mixture_check.py` — new.** Per-cell forecast-value quartile stratification for Stage 4 FAILs. Classifies each cell DEGRADED (any populous bin signed-drift ≥ +40% → real cell-level degradation) / IMPROVED (all populous bins ≤ 0% → recent MAE ≤ calib, model got better) / SAFE (all ≤ +25% → mixture drift, within-bin stable) / PARTIAL / SKIP (metric-artifact fields: pp, pa, wd) / THIN. Exposes `refine_verdicts()` as a shared function so the standalone CLI and the main audit both use the same logic.
- **`analysis/c1_stage4_audit.py` — refined view integrated.** After primary classification, every FAIL and WATCH cell runs through the mixture check; a `refined` block with counts + recommendation + per-cell results lands in stdout and JSON alongside the raw view. Today's numbers: raw 18 PASS / 11 WATCH / 13 FAIL → NOT READY; refined 27 PASS / 1 WATCH / 2 FAIL / +12 excluded as metric-artifact → MIXED (pass rate 90%, FAIL rate 6.7% — just above the 5% READY cap). Real DEGRADED cells surfaced: ws/24-47h transition (three wind bins degrading, corroborates ws L3 strip candidate), cl/12-23h stable (b1 low-forecast bin MAE nearly doubled). Documented in `project_stage4_audit_metric_limitation` as the third-blowup-mode fix (unsigned improvement reading as failure) landing alongside the mixture and near-zero-calib fixes.
- **`analysis/marine_layer_cl_stage1.py` — new.** Stage 1 sanity check for a candidate cl marine-layer analog, prompted by the cl/12-23h stable DEGRADED verdict. Tested two triggers (regime=nw_flow, and wd 270-360°) × three hour buckets. Result: **the cl over-forecast at night+eve is regime-agnostic** — nw_flow-active and nw_flow-inactive both show +17 pp signed bias, so this is a diurnal pattern, not a marine-layer pattern. Weekly trend shows the bias fading fast (W25=+20 → W28=+2), so it's likely a transient. Adds cl → L4 (diurnal correction) as a Stage 1 candidate to re-read weekly through W29-W31 before promotion decision.

No live-pipeline changes; all three files are analysis-only. Nightly digest auto-picks up `marine_layer_cl_stage1` on next run; `c1_stage4_mixture_check` runs as a shared module import from the main audit but is also runnable as a standalone.

</details>

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

- **Engineering-updates subsections now collapsable.** The two title-blocks under "Engineering updates — where we are" ("Current pipeline state" and "Recent activity — rolling 3-day window") were plain `<div>`s while the cards below (Production stack, Built not applied, Retired, Upcoming decisions) already used `<details open>`. Converted both to `<details>` with `<summary>` headers matching the existing card pattern. Meta-line already read "click any sub-box header to collapse it" — the affordance now works everywhere it claimed to.

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

