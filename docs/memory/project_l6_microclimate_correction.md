---
name: l6-microclimate-correction
description: L6 — Microclimate correction (temperature). Shipped 2026-06-26 v0.6.231; per-lead application v0.6.237. The first layer in the stack trained on a within-network spatial differential (waterfront vs inland stations) rather than aggregate forecast error. Cove-temperature-only. Live monitoring via l6_gate_history.json with 7-day rolling keep-gate.
metadata: 
  node_type: memory
  type: project
  originSessionId: a8f5db73-5a54-4321-a927-279049b8212d
---

## What it does

A small Δ°F added to `corrected_temperature` based on the **waterfront-vs-inland spatial gradient** at the cove. For each forecast lead `i`, looks up Δ from one of two tables keyed by the projected regime at lead `i`:

- **sb-active branch**: `(wind_octant)` — fires when sea breeze is on. Captures peninsula-lee heating: S-half winds (S/SE/SW) push marine air across ~2 mi of sun-heated Marblehead before reaching the cove. Δ = +1.1 to +2.0 °F.
- **sb-off branch**: `(hour_of_day)` — fires when sea breeze is off. Captures the morning marine-cooling trough. Cool pool over Salem Sound persists while inland warms. Δ ranges +0.5 °F overnight → −3.7 °F at 12:00 → recovery through 17:00.

## Architecture

**Module:** `weather_collector/processors/cove_correction.py`, `ENABLED = True` since v0.6.231.

**Pipeline placement (collector.py):** runs *after* `apply_decay_corrections` (L3/L4) and *before* `sync_current_from_hourly_corrected`. Genuinely the last layer in the temperature stack. Originally placed inside `build_weather_data` (before L3/L4 ran); v0.6.232 fix moved it to the correct position.

**Per-lead application (v0.6.237):** for each lead `i`, reads `hourly.wind_direction[i]`, parses local hour from `hourly.times[i]`, computes heuristic `sb_active` (= hour ∈ [13, 18] ∧ S-half wind octant), looks up Δ from the appropriate table, applies to `hourly.corrected_temperature[i]`. Prior implementation applied the current-tick Δ uniformly to all 48 leads — wrong by 3–5 °F at distant leads when the table swing crossed zero. The heuristic sb_active is coarser than the live detector but is the only thing we have for forecast hours.

**Snapshot:** `corrected_temperature_post_l4` is captured as `t_l4` (pre-cove) and `corrected_temperature` as `t_l6` (post-cove). `forecast_snapshot.py` writes both into each tick's snapshot. Pair-log writer iterates `(l1, l2, l3, l4, l6)` and emits `error_l6` only for `t` rows.

**Fitter (decay_fit.py):**
- Aggregates l6 into `per_layer_mae_by_lead.t.l6` for the Forecast Accuracy chart's L6 line.
- Filters pair rows with `run_time < L6_VALID_FROM = "2026-06-26T17:19"` out of L6 aggregation. Filter ages out naturally ~2026-07-03; can be removed then.
- L6 audit: every cycle, paired (L4 vs L4+L6) MAE on temperature rows past the filter. SHIP if L6 beats L4 by ≥2%, HOLD otherwise. Min pairs: 100. Written to `conditional_audits.l6` and `l6_gate_history.json` with 7-day rolling gate (`_compute_l6_gate_7d`).

**Manual Fitter trigger:** `?fit=1` query param on the collector HTTP endpoint short-circuits the normal tick and runs the Fitter once. Used to force rebuilds outside 03:07 / 15:07 EDT windows after an L6 implementation change.

## Debug page

- **Layer 6 section** (`sec-layer6` anchor) with 6a Live correction (current regime + Δ + per-lead summary), 6b Lookup tables (APPLIED badge on the active branch — sb-active or sb-off), 6c Waterfront-vs-inland Δ history from `cove_gradient_log.json`, 6d cove-specific MAE evaluation (L4 only vs L4+L6, anchored to `L6_ENABLED_AT = "2026-06-26T17:19"`).
- **Forecast Accuracy chart** — temperature card includes an L6 column in the band table and a green L6 line on the chart. `_layersFor()` filters L6 out of every non-`t` card.
- **Temperature card badges:** `L6 ✓ microclimate` green badge alongside L2/L3/L4. Other fields don't render an L6 badge.
- **S1 audit table:** L6 column alongside L5 and R6. Latest panel has an "L6 microclimate (ENABLED)" row with verdict, MAE numbers, improvement %, and the trailing 7-day keep-gate status.

## Gate semantics

Since L6 is already shipped, the conditional audit asks "is L6 still earning its place?" rather than "should we ship?". A 7-day HOLD-dominant window would be grounds to flip `ENABLED = False`. Same shape as L5's gate but with reversed action.

## Lookup tables (current values, 12-day refit, n=1,732)

**sb-active branch** (Δ°F by wind octant):
- S: +1.5, SE: +2.0, SW: +1.1 (only S-half octants populated)

**sb-off branch** (Δ°F by local hour, 24h):
- 00–05: +0.1 to +0.5 (overnight near-zero)
- 06–08: −0.2 to −0.9 (lead-in to morning cooling)
- 09–14: −1.6 to −3.7 (peak cooling; 12:00 deepest at −3.7)
- 15–18: −1.9 to −0.3 (afternoon recovery)
- 19–23: +0.1 to +0.5 (evening / night near-zero)

Refresh process: rerun `analysis/r5_cove_analysis.py`. Lookup tables also hard-coded in `corrections_debug.html` JS (for the 6b display) — keep in sync manually.

## Distinct from retired R5

R5 was a **global** cove cross-current correction integrated into the L1/L2 fitter — retired 2026-06-17 (verdict HOLD, made cove temp 20–22% worse because L2's waterfront-weighted station blend already captured the signal). L6 is a separate **module-scoped** correction applied to `corrected_temperature` only (not fed back into the fitter as training signal). Different scope, different mechanism.

## First real verdict (2026-06-27 03:07 EDT Fitter)

`HOLD`, improvement_pct **−7.88%**, n_pairs=301. L4+L6 averaged 7.88% worse than L4 alone on the post-VALID rows.

Caveat: only ~12h of post-deploy rows; short-lead-heavy. **Not grounds to revert** (7d gate semantics). Watch next 2–3 cycles. Persistent negative improvement → flip `ENABLED = False`.

The Forecast Accuracy chart's apparent L6 win (ALL 0.73 vs L4 1.92) was misleading: L4 column averaged over the full 7d window, L6 column only over the ~12h post-VALID slice. Different row sets, plotted side-by-side. Fixed v0.6.244 by emitting a paired-L4 series (`per_layer_mae_by_lead.t.l4_paired_l6`) accumulated only on rows where `error_l6` is present. Chart now renders a dashed "Diurnal (paired with L6)" line on the t card only — the honest baseline for comparing to L6. Self-retires once L6 has full 7d (~2026-07-03) when paired and unpaired L4 columns converge. See [[project-06-27-session]].

## What's queued

- **2026-07-03:** remove the `L6_VALID_FROM` filter from `decay_fit.py` once the broken-uniform-Δ pair rows age out of the 7-day Fitter window. Also drop the `l4_paired_l6` series + LAYER_LINES entry — full-window data makes it redundant.
- **Ongoing:** watch `conditional_audits.l6.gate_7d` — if it goes HOLD-dominant over a 7-day window, flip `ENABLED = False`. The S1 row + Forecast Accuracy chart red banner will catch this.
- **Open question (not today):** the heuristic `_sb_active_forecast` is coarse. If L6 misses the actual sb-on/off transition by an hour, the wrong table fires. Could be tightened with a more thermal-gradient-aware proxy. Watch the audit for systematic bias before refining.

Related: [[project-06-26-session]], [[project-correction-stack]], [[feedback-debug-page-canon]].
