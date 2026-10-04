---
name: 07-13-session
description: "07-13 Mon MEGA-marathon — 27 ships across two threads (v0.6.329 → 350a). Lt retired. cl persistence Stage 3 wired. Watch/detector/counter infrastructure. pa τ deploy. pp Brier Phase 3. wg L3 Stage 0: 10 HURT cells. Debug page chart rewritten then LATER killed entirely (v0.6.350: one combined MAE/RMSE/bias table per card, no chart). Status column on Current pipeline state. TWO NOVEL FINDS: (1) wg short-term residual persistence — MAE -6.13% held-out (v0.6.342); Stage 1 first read MARGINAL (pooled +17.04% but calm regime -71.29% + halves unstable); (2) MLC in-bin bias COLLAPSE at 07-07 — baseline +37 → recent +4.47 (v0.6.347); diagnosis rules out cm HRRR anomaly as cause. New tool: marine_layer_anomaly.py (stratum 2-window detector). Massive TODO sweep — 8+ stale entries closed (gate-firing table already shipped v0.6.318; * migration language retired; sr/L4 + Lsr skip regime contamination lifted 07-10; Phase 3 Brier + accuracy-chart rewrite shipped)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 5d8d6cee-65cf-4a8f-b3d2-fa890136f897
---

## Ships (19+ across two threads)

**Thread 1 (other session):**
1. **v0.6.329** — Lt Fix B answered → retired. Refit against L2 held-out +0.29% (below +1.0% gate). See [[lt-fix-b-answered]].
2. **v0.6.329a** — Debug page: Lt out of Production stack list entirely.
3. **v0.6.330** — cl persistence short-lead gate Stage 3 wired (ENABLED=False, day 1/7). Narrow: 0-5h all 9 regimes. Earliest flip 07-19.

**Thread 2 (this session):**
4. **v0.6.331** — h/l4 narrow-add streak counter. Fixed a live bug in `h_full_regime_sweep.py::main()` (undefined `LAYER_ON_FIELDS`, wrong tuple unpack). Emits `weather_collector/data/h_l4_add_candidates.json`; 4th `_NARROW_PROMOTE_GATES` entry. Day 2/7; earliest flip 07-18.
5. **v0.6.332** — persistence-skill post-ship watch. Compares today's h_persistence_skill.json vs snapshot; alerts on ADDS VALUE → MIXED regressions + at-risk (pooled skill < +0.20). Today: **ws +0.16 at-risk**.
6. **v0.6.333** — pair-log anomaly detector. `analysis/anomaly_detector.py` compares 7d recent vs 21d baseline per field. Today: **cm has recovered** (Recent MAE 23.2 vs baseline 26.7), confirming transient-weather branch in [[cm-stage4-degradation]].
7. **v0.6.334** — pa per-field τ 28 → 42. Confirmed 3/3 streak, +5.5% MAE vs τ=14 at best-τ=42. **Deployed collector rev 00432-hod**.
8. **v0.6.335** — pp Brier decomposition (Phase 3). Reliability / Resolution / Uncertainty per band. Today: CALIBRATED +8.4%, BSS +0.126. **Under-forecast at fc 30-50%** (obs freq 66% when corrected says 30-40%).
9. **v0.6.336** — persistence-skill vs per-row Production alongside L4 (Phase 2 follow-on). Backward-compatible; adds skill_prod_mae_pooled per field. **Two real findings on first read: ch Prod −1.08 vs L4-alone −0.29 (L3 damage on ch); wg Prod −0.09 vs L4 +0.10 (wg L3 similarly costly).**
10. **v0.6.337** — Prod-vs-L4 delta surfaced at exec-summary altitude. New sub-block under at-risk lines with direction markers.
11. **v0.6.338** — Debug page sweep: counter advances 07-12 → 07-13, 7 new Recent activity entries.
12. **v0.6.338a** — Prose sweep: retired stale Production* + Lt-line references.
13. **v0.6.339** — **wg L3 Stage 0 diagnostic**: 10 HURT cells (calm all bands +23-77%; unknown 3 bands +22-38%; sea_breeze 6-11h + 24-47h; ne_flow 6-11h). Same skip-table architecture as ws L3.
14. **v0.6.339a** — Second-pass sweep: L3 methodology paragraph updated pa τ 28d → 42d.
15. **v0.6.339b** — **Debug page reorg**: Recent activity moved to own `<h2 id="sec-recent">` above sec-status. Today's 10 ship bullets consolidated into 7 theme groups.
16. **v0.6.339c** — Third-pass sweep: 5 residual stale counter refs.
17. **v0.6.339d** — Live Lc widget gate-note updated.
18. **v0.6.340** — **Forecast Accuracy chart rewrite**: only-applied layers in chart + MAE table (no more stacked identical lines). **RMSE + bias companion tables per card**, using per_layer_rmse_by_lead / per_layer_bias_by_lead. PP-Brier cards skip these. Lt badge "off (dormant)" → "retired".
19. **v0.6.341** — **UI cleanups**: "What this measures" wrapped in `<details>` (collapsible). Tri-column band wrapped in "Current state" `<details open>`. **Status column added to Current pipeline state table** with per-field one-liner summaries (open regression / best-performing / stable win / etc.).
20. **v0.6.342** — **NOVEL FIND: wg short-term residual persistence.** New `analysis/h_daily_residual_persistence.py` tests whether yesterday's mean (obs − L2_fc) at hour H predicts today's at hour H. Result: **wg is a Stage 0 hit — rolling 2-day mean-residual correction: MAE −6.13% (2.638 → 2.475), RMSE −7.41% (7.598 → 7.035) held-out on 49,804 test rows.** Every other field regresses (t/dp/h already have L4 catching this signal; clouds too noisy). wg wins because no L4 competes + wind gust has strong day-to-day persistence not tracked by L2's Kalman.

**In-progress (not run this session):**
- `analysis/h_wg_residual_persistence_stage1.py` written — grid search over window ∈ {1, 2, 3, 5, 7, 14} × baselines {L2, Production}, per-regime cross-cut, halves check. Bash classifier was blocked; script auto-picks-up in tomorrow's digest.

**Thread 3 (evening extension, same-day continuation):**

21. **v0.6.343** — Stage 1 preview script committed (`analysis/h_wg_residual_persistence_stage1.py`).
22. **v0.6.344** — **wg residual-persistence Stage 1 first read: MARGINAL.** Ran grid end-of-session. Best combo window=14d L2-alone → pooled MAE +17.04% / RMSE +14.92% held-out. BUT: (a) per-regime cross-cut — calm regime LOSES −71.29% (n=1,221), unknown −2.24%; 5 regimes WIN (se_flow +28.38%, sw_flow +22.71%, pre_frontal +18.89%, nw_flow +18.06%, ne_flow +7.95%). (b) Halves check FAILS: first half +18.44%, second half +0.49%. Also confirmed L2-alone ≡ Production (wg not in L3_FIELDS). Verdict rule fires MARGINAL — re-run 07-16 after 3-day training roll. Regime gate mandatory before wire-up.
23. **v0.6.344a** — Debug page: wg summary line extended with residual persistence in Current pipeline state.
24. **v0.6.345** — **gate_firing_rollup EXPECTED_DORMANT allowlist refresh.** Discovered gate-firing table TODO was already shipped v0.6.318 (07-09). Real gap: allowlist stale for post-v0.6.318 ships. Added `ch_persistence_gate` + `cl_persistence_short_lead` to EXPECTED_DORMANT_OPERATORS; refreshed Lt "dormant pending Fix B" → "retired"; new EXPECTED_DORMANT_CELLS allowlist covers 4 designed skip cells (L3/ws/ne_flow SKIP_TABLE, Lsr/sr in ne_flow + calm, C1h/ch/ne_flow co-axis gate). Result: `⚠ UNEXPECTED: none`.
25. **v0.6.346** — **Retire "*" migration language.** Three stale bits from the 07-01 → 07-08 per-row-stamping migration cleaned: MAE band-table tooltip fallback text, "Current pipeline state" intro's "in flight" caveat, Engineering-updates per-row-stamping bullet. Chart-code `*` conditional kept as safety fallback; n≥30 rationale preserved.
26. **v0.6.347** — **NEW TOOL + FINDING: marine-layer stratum bias-collapse detector.** New `analysis/marine_layer_anomaly.py` reads `marine_layer_watch.json` and does the same 2-window comparison as anomaly_detector.py but against the stratum's own bias time series. **First run flags COLLAPSE:** baseline 21d in-bin bias +36.27 → recent 7d +10.97 (Δ −25.29); out-of-bin control (rest of cc pairs) flat +10.67 → +11.09. Wired into `build_executive_summary.py` so future collapses surface at exec-summary altitude. MLC.ENABLED stays False — flipping now would over-correct cc by ~+25pp inside the gate.
27. **v0.6.348** — **MLC collapse diagnosis: separate 07-07 event, NOT the cm HRRR anomaly.** Segmented time series: pre-anomaly (06-22→07-04) +37.01, cm-anomaly-window (07-04→07-07) +33.02, cliff (07-07→07-10) +13.80, post-cliff (07-10→07-14) +8.85. MLC held ~+33 through the entire cm-anomaly window then fell sharply on 07-07 — 3 days after cm's shift. If same HRRR upstream caused both, they'd move together. They didn't. Also: in_bin_n grew 3734 → 4217, so not stratum-shrink — more NE-morning pairs, less biased per pair. Best remaining hypotheses: seasonal mid-summer NE-flow inversion drop, or a distinct HRRR NE-morning boundary shift. Hold OFF indefinitely; re-engage flip criterion if in_bias recovers to +25+ within 3 weeks.
28. **v0.6.349** — **project-todo memory sweep: 8+ stale entries closed.** Same drift class as gate-firing (v0.6.345) — items marked "actionable now" or "not before DATE" whose implementations had already shipped. Closed: `sr → L4` + `Lsr skip regime changes` (contamination lifted 07-10); Lsr 14-day watch self-lifted; v0.6.310+311 skip-table firing verified (ws Prod 25.7% → 5.3% matches production_whatif prediction); Phase 3 pp Brier SHIPPED v0.6.335; Debug page accuracy-section rewrite SHIPPED v0.6.340; `sr shortwave-vs-cc confound` + `h_c1h_orthogonality` both first-read done; ws structural residual unblocked (skip-table window filled 07-13). Net: fewer than 5 real items remain across Actionable+Longer horizon.
29. **v0.6.350** — **Accuracy section redesign: kill charts, one combined table per card.** Joe raised the section had become "a lot less useful" after v0.6.340's RMSE + bias companion tables (chart + 3 tables = wall of vertical space). Diagnosis: charts USED to be useful when they showed each layer's individual contribution, but two changes ate that value — (1) v0.6.340's `_layersFor()` filter dropped inactive layer lines (correct fix, but killed per-layer visual story), (2) the thick Production line dominates the eye. Killed `_buildBandTable` + `_buildMetricTable` + entire `new Chart(...)` block; replaced with `_buildCombinedTable` — 5 bands × 3 metric rows (MAE primary + RMSE + bias as dimmer sub-rows underneath). Net: −207 / +120 lines; roughly half vertical footprint per card. pp-Brier cards still render Brier-only. Intro prose rewritten.
30. **v0.6.350a** — **Fix: fill Production column for RMSE + bias rows.** Shipped v0.6.350 with "—" placeholder on the theory that hybrid Production was MAE-only. Wrong — `per_layer_rmse_by_lead` and `per_layer_bias_by_lead` both publish populated `production` keys. Read `data.production` directly. Also dropped the now-incorrect "no Production column" caveat from intro prose.

## NOVEL: wg short-term residual persistence (v0.6.342)

**Hypothesis:** L4 (diurnal) averages hour-of-day bias over ~21 days. If the true bias drifts on a 1-3 day timescale (regime shifts, air-mass changes), L4 smooths it out and we leave signal on the table.

**Test:** for each field × obs_hour (0-23 local), aggregate L2 residual = obs − L2_forecast by obs_date. Compute lag-1/2/3 day autocorrelation of this per-hour time series. If ρ_1 > 0.3 for an hour, yesterday's residual predicts today's.

**Simulation:** for each row, subtract mean signed L2-residual over prior N days at same (field, hour). Held-out on last 7 days.

**Result table:**

| field | MAE base | MAE corr | ΔMAE% | RMSE base | RMSE corr | ΔRMSE% |
|---|---:|---:|---:|---:|---:|---:|
| **wg** | 2.638 | 2.475 | **−6.13%** ★ | 7.598 | 7.035 | **−7.41%** |
| t | 1.967 | 2.058 | −4.65% ⚠ | 2.565 | 2.666 | −3.95% |
| dp | 2.326 | 2.652 | −14.0% ⚠ | 3.044 | 3.382 | −11.1% |
| h | 6.924 | 7.751 | −11.9% ⚠ | 8.903 | 9.707 | −9.0% |
| ws | 2.638 | 2.993 | −13.5% ⚠ | 3.493 | 3.784 | −8.4% |
| pr, cc, cl, cm, ch, sr | all regressed | | | | | |

**Why wg specifically wins:**
1. No L4 diurnal competes (L4_FIELDS = {ch, cc}, wg isn't there).
2. Wind gust has strong day-to-day persistence not tracked by L2's Kalman.
3. Autocorrelation broadly distributed across hours (not one narrow band).

**Interesting side finding:** t and dp DO have real autocorrelation, but L4 already catches it:
- t afternoon cluster: 14/15/16/19/22h all ρ_1 ≥ 0.3
- dp nighttime cluster: 21-23h and 00-01h ρ_1 ≥ 0.3

Confirms L4 is doing its job on t/dp.

**Actionability:** wg-specific Stage 1 → Stage 2 → Stage 3 promotion pipeline. Path:
1. Stage 1 (already written, needs run): tune window ∈ {1,2,3,5,7,14} × baseline ∈ {L2, Prod}, per-regime cross-cut, halves-verify.
2. Stage 2: exponential-decay τ weighting (Kalman-like) instead of naive mean.
3. Stage 3: wire as a new correction layer or extend L2 with a per-hour residual accumulator.

**Comparable magnitude:** ch persistence gate wired 07-12 → projects ~20% MAE improvement on ch. wg residual → projects ~6% on wg. Different fields, similar impact class.

## wg L3 Stage 0 investigation (v0.6.339)

New `analysis/h_wg_l3_regression.py` broke the v0.6.336 19pp Prod-vs-L4 skill drag down to per (regime × lead_band). **10 HURT cells / 36 judged**:

- **`calm` regime, all 4 bands**: +23% / +62% / +77% / +73% MAE post-L3
- **`unknown` regime, 3 bands**: +22% to +38%
- **sea_breeze 6-11h + 24-47h**: +4.4%, +15.2%
- **ne_flow 6-11h**: +5.5%

`calm` alone (14,591 rows in 7d) accounts for most of the pooled drag. Fits the same skip-table architecture as ws L3 (ne_flow all + sea_breeze 0-11h). Not shippable today — Stage 0, needs 3-day streak per [[feedback-hypothesis-promotion-pipeline]].

## Two real findings from v0.6.336

- **ch: L4 −0.29 → Prod −1.08.** ch pipeline is 3.7× worse against persistence than L4 alone. Corroborates [[ch-persistence-gate-ship]] direction — L3 doing damage on ch, not just L4.
- **wg: L4 +0.10 → Prod −0.09.** wg L3 pushes wg from marginal-positive to negative persistence skill. Cross-refs the 07-16 walkforward drop decision.
- Smaller: cc +0.13 → +0.03 (L3 costs cc); pp +0.18 → +0.32 (calibrator helps).

## Debug page architectural changes (07-13 session)

**Chart rewrite (v0.6.340):**
- `_layersFor()` now filters to only-applied layers (L1 always, then only those with `_layerApplied()` true). Prior version showed stacked identical lines because inactive-layer arrays equal the previous applied layer's.
- New `_buildMetricTable()` renders RMSE + bias companion tables below the MAE table, using `tsDoc.per_layer_rmse_by_lead` and `tsDoc.per_layer_bias_by_lead`. Same only-applied filter.
- PP-Brier cards skip the RMSE/bias tables (Brier already carries the second view).

**UI cleanups (v0.6.341):**
- Scorecard "What this measures" → collapsible `<details>`.
- Tri-column band (What's running / improving / evaluated) → collapsible `<details open>` with "Current state" summary.
- **Status column added to Current pipeline state table.** Each field gets a one-liner: e.g. "ws: Open regression. Walkforward L3 drop day 4/7." / "ch: Best-performing field vs raw — but persistence-skill Prod −1.08 vs L4-alone −0.29 (v0.6.336). ch persistence gate pending (day 2/7, flip 07-19)." / "wg: Stable win vs raw, but v0.6.339 Stage 0: L3 regresses in 10 cells (calm all bands +23-77%)."

**Reorg (v0.6.339b):** Recent activity extracted from inside sec-status into its own `<h2 id="sec-recent">` above sec-status. Today's 10 individual ship bullets consolidated into 7 theme groups.

## Forward calendar (unchanged from 07-12 update, plus wg residual candidate)

- **Thu 07-16:** ws L3 strip earliest ship (day 4/7 → 7/7). Also: wg residual Stage 1 halves-verify if streak clears.
- **Fri 07-17:** `h_ws_octant_bias` first weekly re-read (1 of 3).
- **Sat 07-18:** C1 Stage 4 next window; Lc anomaly HOLD opens; C1h + C1d earliest; **h/l4/calm/12-23h ADD-candidate flip decision (streak day 2/7 today).**
- **Sun 07-19:** ch persistence gate flip; cl narrow-gate flip; pre-frontal Stage 3 wire-up.

## New Stage 0 candidates queued (07-13)

- **wg L3 skip-table extension** — 10 HURT cells (calm all + unknown 3 + sea_breeze 6-11h/24-47h + ne_flow 6-11h). Auto-picked up by digest; needs 3-day confirmation streak.
- **wg residual-persistence correction** — Stage 0 MAE −6.13% held-out. Stage 1 first read v0.6.344 MARGINAL: pooled +17.04% (window=14d) but calm regime −71.29% + halves unstable. Re-run 07-16.
- **pp Brier under-forecast at fc 30-50%** — obs freq 66% at 30-40% forecast bin. Future narrower calibration lookup.

## NEW FINDING: MLC in-bin bias COLLAPSE (v0.6.347/348)

Investigating the "flip mid-July if trend holds" TODO surfaced that the trend did NOT hold — the MLC in-bin signal has been collapsing since 07-07.

**Segmented time series (in_bin_signed_bias by window):**

| window | n_entries | in_bias | out_bias (control) | in_bin_n |
|---|---:|---:|---:|---:|
| Pre-anomaly 06-22→07-04 | 26 | +37.01 | +10.55 | 3734 |
| cm-anomaly window 07-04→07-07 | 6 | +33.02 | +11.16 | 3969 |
| **Cliff 07-07→07-10** | 6 | **+13.80** | +10.39 | 4256 |
| Post-cliff 07-10→07-14 | 8 | **+8.85** | +11.61 | 4217 |

**Key observations:**
1. MLC held +33 through the entire 07-04→07-07 cm HRRR-anomaly window — so cm's cause is NOT MLC's cause. Two separate events.
2. Sharp cliff on 07-07, not gradual — points to a distinct discrete change (HRRR update or regime frequency shift), not slow seasonal drift.
3. `in_bin_n` GREW (3734 → 4217) — NOT stratum shrinkage. More NE-flow-morning pairs recently, less biased per pair. Genuine physics change.
4. Out-of-bin control (rest of cc pairs) flat throughout — global cc bias fine. Stratum-specific effect.

**Verdict:** MLC.ENABLED stays False indefinitely. Flipping now would over-correct cc by ~+25pp inside the gate. Re-engage flip criterion only if in_bias recovers to +25+ within 3 weeks. See [[project-todo]].

## NEW TOOL: analysis/marine_layer_anomaly.py (v0.6.347)

Companion to `anomaly_detector.py`. Global detector operates on all pair rows per field; this one targets the ~3%-of-cc stratum where MLC lives. Reads `marine_layer_watch.json` (per-tick fit output published to GCS by decay_fit.py), compares recent-7d vs baseline-21d mean of `in_bin_signed_bias`. Three verdicts: COLLAPSE (|Δ|≥15 AND recent<15), DECAY (|Δ|≥10 AND recent<baseline), STABLE.

Wired into `build_executive_summary.py::marine_layer_anomaly_summary()` alongside `anomaly_detector_summary()` so COLLAPSE/DECAY surface at exec-summary altitude in the daily digest.

**Same pattern applies elsewhere:** any correction whose Stage 2/2.5 watch publishes a stratum bias time series can get the same 2-window collapse detector as a 10-line script. Candidates for later: cove-microclimate stratum (dormant), potential regime-specific Lsr strata.

## Accuracy section redesign meta-lesson (v0.6.350)

**Pattern:** the section had been drifting from useful to less-useful across recent ships and I hadn't noticed. Joe surfaced it in one line ("less useful"). Reasoning together traced two specific proximate causes (only-applied-layers filter + thick Production line) that individually were correct decisions but combined destroyed the chart's remaining value.

**Meta-lesson:** individual improvements can compose into a regression. Each v0.6.269→v0.6.340 change to the accuracy section was defensible in isolation. The cumulative effect wasn't. Rule of thumb worth codifying: **when a section has accumulated ~5+ changes across recent months, do a "read it fresh" pass and ask if the SECTION still earns its screen real estate** — not just whether the individual pieces are still correct.

Also captured: killing established UI is scary but usually the right move. The chart had been on the page for months. Deleting it after ~30 min of analysis is right, not premature — the question isn't "should this be here?" but "does it earn its space against the tables next to it?" and if not, cut.

## Related

- [[07-12-session]] — yesterday's marathon (8 ships).
- [[lt-fix-b-answered]] — Lt retirement rationale.
- [[persistence-skill-baseline]] — Phase 2 baseline (07-11). Updated with 07-13 Prod-vs-L4 findings.
- [[ch-persistence-gate-ship]] — Stage 3 wire (07-12). v0.6.336 findings reinforce it.
- [[cm-stage4-degradation]] — anomaly detector confirms recovery branch.
- [[project-todo]] — updated after this session.
