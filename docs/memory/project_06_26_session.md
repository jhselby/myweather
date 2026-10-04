---
name: 06-26-session
description: "Friday 2026-06-26 marathon — L6 microclimate correction shipped through three iterations (initial v0.6.231, ordering fix v0.6.232, per-lead application v0.6.237), Fitter audit + S1 column wired (v0.6.240), debug page L6 visibility pass + consistent naming convention, status section restructured. Many small UI polishes. Discovered + queued the ws L3 long-lead regression."
metadata: 
  node_type: memory
  type: project
  originSessionId: a8f5db73-5a54-4321-a927-279049b8212d
---

## Headline ship

**L6 — Microclimate correction (temperature)**, the cove-specific regime-conditional Δ°F layer, shipped in production today (v0.6.231 → final v0.6.241 with all polishes). Cleared the 2-read confirmation gate (06-25 SHIP + 06-26 SHIP on `r5_cove_analysis.py`, both regime tests PASS).

L6 is the first layer in the stack trained on a *within-network spatial differential* (waterfront stations Willow Rd + Neptune Rd vs inland-network median) rather than aggregate forecast-vs-obs error. Two physical regimes: cove warms a few °F under S/SE/SW sea-breeze (peninsula-lee heating), cools a few °F during 09–16 EDT when the sea breeze is inactive (peak −3.7 °F around noon — cool marine pool over Salem Sound). Architecture detail in [[project-l6-microclimate-correction]].

## Three iterations to ship correctly

1. **Initial v0.6.231 (~08:00 EDT):** flipped `cove_correction.ENABLED = True`. Module already wired into the collector pipeline.

2. **Ordering fix v0.6.232 (later morning):** discovered the cove stamp was called from *inside* `build_weather_data` BEFORE `apply_decay_corrections` ran. The cove Δ was being silently absorbed into the L2 column, with L3 and L4 stacking on top of the cove-modified L2. Moved `stamp_cove_correction` to after decay_apply so cove is genuinely the last layer. Snapshot now distinguishes `t_l4` (pre-cove) from `t_l6` (post-cove); pair-log writer captures `error_l6` for temperature rows; Fitter aggregates l6 into `per_layer_mae_by_lead`. Forecast Accuracy chart got an L6 column/line for the temperature card.

3. **Per-lead application v0.6.237 (afternoon):** observed the first L6 chart line and it looked terrible. Diagnosed: `stamp_cove_correction` was applying the **current-tick** Δ uniformly to all 48 forecast leads — wrong by 3–5 °F at distant leads when the table swing crossed zero (e.g. applying noon's −3.7 °F to a midnight lead). Fix: per-lead projection — each forecast lead gets the Δ for its own projected regime (forecast `wind_direction[i]`, parsed local hour from `times[i]`, heuristic `sb_active` = hour ∈ [13,18] ∧ S-half wind). New `weather_data.cove_correction.per_lead_delta_summary` block (min/max/mean) so the debug page shows the spread.

4. **Fitter filter v0.6.238:** the broken-impl pair rows from window (06-26 08:00 → 17:19 EDT) sit in the Fitter's 7-day rolling pair-log window for a week. Added an `L6_VALID_FROM = "2026-06-26T17:19"` filter so `error_l6` from those rows is excluded from `per_layer_mae_by_lead.t.l6` aggregation. Filter is a temporary guard — can be removed ~2026-07-03 when the bad rows age out naturally.

## L6 monitoring infrastructure

- **`?fit=1` collector bypass (v0.6.238):** short-circuits the normal tick and runs the Decay-Fitter once. For forcing rebuilds outside the 03:07 / 15:07 EDT windows. Used today to land the first clean L6 Fitter cycle right after the per-lead deploy.

- **L6 conditional audit (v0.6.240):** mirrors L5's audit shape — every Fitter cycle compares paired (L4 vs L4+L6) MAE on cove temperature rows that pass the L6-valid-from filter, emits SHIP/HOLD verdict, writes to `l6_gate_history.json` with 7-day rolling gate. Since L6 is shipped, gate semantics flipped from "should we ship?" → "is L6 still earning its place?" 7-day HOLD-dominant would be grounds to revert `cove_correction.ENABLED`.
  - SHIP threshold: L6 beats L4 MAE by ≥2%. Min pairs: 100.
  - Surfaced in S1 audit table as a new L6 column + a Latest-panel row.
  - First Fitter cycle landed `insufficient_data` (n=4, need ≥100). Real SHIP/HOLD verdicts start once ~6 hours of post-deploy pair rows accumulate.

- **Debug page L6 section** (6a Live correction, 6b Lookup tables with APPLIED badge on the active branch, 6c Waterfront-vs-inland Δ history from `cove_gradient_log.json`, 6d cove-specific MAE evaluation L4 vs L4+L6 anchored to 17:19 EDT deploy timestamp).

## Where L6 lives

- Module: `weather_collector/processors/cove_correction.py` (`ENABLED = True` as of v0.6.231)
- Collector hook: `weather_collector/collector.py:464+` (after `apply_decay_corrections`, before `sync_current_from_hourly_corrected`)
- Snapshot: `weather_collector/processors/forecast_snapshot.py` — `t` layer dict includes `l4` (pre-cove) and `l6` (post-cove) fields
- Pair-log writer: `weather_collector/processors/forecast_error_log.py` — iterates `(l1,l2,l3,l4,l6)`, captures `error_l6` for `t` rows
- Fitter: `weather_collector/processors/decay_fit.py` — L6 valid-from filter, L6 audit verdict, `_compute_l6_gate_7d`, `l6_gate_history.json`
- Frontend chart: `corrections_debug.html` — `LAYER_LINES` includes `l6`, `_layersFor()` filters L6 to t-only, `_buildBadges` shows `L6 ✓ microclimate` on the t card

## Discovered + queued — not acted on

**ws L3 long-lead regression.** Per-lead MAE chart shows wind speed (ws) L3 makes things +20–31% worse at leads 18-47h, while wind gust (wg) L3 helps −15 to −22% over the same band. The walkforward L3/L4 validator's per-field aggregate hides this — ws comes out as "L3 on" at 10d windows because short-lead near-neutrality + long-lead damage averages out. Per [[project-ws-l3-long-lead-regression]]: first add per-band rollup to walkforward output (06-29 prep), then either drop ws from L3 or wire per-(field, lead_band) whitelist in `decay_apply.py`. Queued, not today's work.

## Naming convention codified

Layers now follow a parallel `LN — <structure> correction` pattern across all debug-page text:
- L1 — Raw model (baseline; not a correction)
- L2 — Aggregate-bias correction
- L3 — Lead-decay correction
- L4 — Diurnal correction
- L5 — Synoptic-regime correction (solar)
- L6 — Microclimate correction (temperature)

L1 is the only asymmetric one — it's the baseline, not a correction. Field scope parenthetical (`(solar)`, `(temperature)`) flags layers that don't apply universally. The whole app is cove-only so "cove" is implicit and dropped from layer names.

## Analysis tooling (v0.6.225–v0.6.229)

Single-command digest pipeline at `analysis/runlog/run_digest.sh`:
- Runs all 63 analysis scripts.
- Writes `analysis/output/DIGEST.txt` with executive summary (deltas vs prior run), divergence report (production vs latest verdicts with streak counters against per-key promotion gates), pass/fail table, per-script verdicts + tail context.
- `digest_history.jsonl` accumulates per-script verdicts + structured claims; streak counter dedupes by calendar day so re-running on cached data doesn't falsely advance the gate.
- `divergence_report.py` reads L5's live trajectory from `l5_gate_history.json` instead of fresh-history streak; other layers use the dedup'd streak.
- Walk-forward L3/L4 default cutoff raised from 2d → 10d (2d window is regime-fragile per the 06-22 diagnostic memory).
- Scripts can be parked by renaming `*.py` → `*.py.skip` (or any name with `.skip` in it).

Cache cost: ~$0.20 per fresh-data digest run (1.5 GB pair log dominates). 12h cache TTL — multiple runs within a window cost $0.

## Other UI polishes

- Wind card (Weather tab): C1 ± suffix removed from collapsed-preview numbers (still on the expanded chart).
- "Since last curation" box readability + print stylesheet fix.
- Debug-page L3 sections 3a + 3b gained APPLIED / diagnostic badge parity with 3c.
- Status section restructured: outer `<h2 class="section" id="sec-status">` matches Layer section styling and inherits click-to-collapse; six sub-boxes are individually collapsible (Production stack / Gated off / Next scheduled decisions default open; Stage 2 audits / Retired / Open architectural questions default closed).
- New L6 chip on the TOC strip.
- L6 ✓ microclimate badge on the temperature card.
- Methodology accordion lead-in updated to acknowledge L6 (drops "four lines" stale claim).
- Multiple data refreshes throughout: L5 trajectory 5/7 SHIP / 0 HOLD / 8-cycle SHIP streak; cove section split between retired global R5 and current L6; one-line summary lists C1f axis + L6.

## Today's calendar-gated reads (all done via digest)

- **Walk-forward cc/cl L3/L4 inclusion under KBVY-blended obs:** ✓ done. cc: off_off (drop candidate, 1/7 reads — cc just shipped 06-24); cl/cm/ch aligned with production. Confirmation 07-03.
- **C1 calibration audit:** ✓ done. Both single-axis and multi-axis verdict HOLD. Single-axis 46.34% pass rate (need ≥75%). Multi-axis DEFERRED — 0 of 454 cells have sufficient data; cluster_spread_log only goes back to 06-20. First multi-axis audit ETA 2026-07-04. Do not flip `confidence_layer.ENABLED = True`.
- **KBOS-vs-KBVY cloud disagreement smoke test:** ✓ done. VERDICT: SMOKE_ALIVE. wg short-leads + dp 0-23h show clear high-vs-low spread quartile ratios. Re-audit at n=7d ~2026-06-27.

## What ships next

- **06-27 (Sat):** cluster-spread re-audit; tomorrow morning's L6 audit cycle should have n≥100 and a real SHIP/HOLD verdict.
- **06-28 (Sun):** marine layer weekly Stage 2 re-read.
- **06-29 (Mon):** walk-forward L3/L4 #4 + Stage 1 batch re-read. First multi-read gate-readiness check on cc-drop-from-L4.
- **07-01 (Wed):** cove second confirming read — gate already cleared today; this just reinforces.
- **07-03 (Fri):** confirmation read on cc/cl L3/L4 inclusion under blended obs. L6 valid-from filter can be removed after this date (broken-impl rows aged out).
- **07-04 (Sat):** first multi-axis C1 Stage 4 audit (after cluster_spread_log reaches into calib window).
- **07-12 (Sun):** marine layer weekly Stage 3 promotion review window.

## Lessons preserved

- **Verify actual pipeline ordering before assuming layer placement.** I assumed L6 was the last layer because the module's docstring said so. The call site put it inside `build_weather_data` BEFORE `apply_decay_corrections`. Three hours of confused L6-vs-L4 chart numbers traced back to this. Always grep the call sites in `collector.py`, don't trust the module-internal narrative.
- **Per-field aggregation hides per-band regressions** — see [[project-ws-l3-long-lead-regression]].
- **Single-tick application of a regime-conditional Δ is wrong at long leads.** L6's initial implementation applied today's noon Δ to tomorrow's midnight forecast. HRRR gives us 48 hours of forecast wind direction — use it. Per-lead projection is the right shape for any regime-conditional layer.
- **Don't refit biases mid-trajectory** still standing from yesterday's session ([[feedback-read-inline-rules-before-editing]]). Today's L6 work respected this; only the cove lookup got refit, not the L5 solar trajectory.

## Related memories

- [[project-l6-microclimate-correction]] — L6 layer architecture, files, audit gate
- [[project-ws-l3-long-lead-regression]] — queued L3 per-band work
- [[project-l5-trajectory]] — refreshed end-of-session to 5/7 SHIP, 8-cycle streak
- [[project-walkforward-l3l4-validator]] — 06-26 read was the 5th formal; 10d new default
- [[feedback-read-inline-rules-before-editing]] — yesterday's lesson, applied today
- [[feedback-debug-page-canon]] — debug page is source of truth; every Stage 2 ship must skim
- [[project-correction-stack]] — the canonical "what does the pipeline do" reference
