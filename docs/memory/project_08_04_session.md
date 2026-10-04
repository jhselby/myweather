---
name: project-08-04-session
description: "2026-08-04 session. 5 substantive ships + 1 debug page tweak (v0.6.391/391a/... consolidated into v0.6.391 after renumber, then v0.6.392 + v0.6.392a). Ccd sat guard, Lsr curated JSON, dpbp flip, wg L3 +3 cells, metric provenance overhaul, raw-difficulty index. Deferred: wsbp (calm regime n=0), Lsb (24h attribution buffer post-Lsr)."
metadata: 
  node_type: memory
  type: project
  originSessionId: d49c29ee-d186-4c2d-9b3a-2ab60600aff6
  modified: 2026-08-05T01:03:00.072Z
---

# 2026-08-04 session summary

## Ships (in order)

1. **Ccd saturation guard** (`cc_from_derivation.py`, `SAT_THRESHOLD = 90.0`). cc losing +9.8% Last-24h despite cl/cm/ch all winning. Traced entire loss to obs bin 95-100 (n=235 across pre_frontal/se_flow/sea_breeze/sw_flow): raw MAE ~2, Ccd MAE ~30 (+1000%+). Root cause: cm's Lc has bias +26.9 → −10.0 (over-corrected by 10 pts), ch bias +40.7 → +12.8. `max(cl_l6, cm_l6, ch_l6)` undershoots METAR total sky cover at overcast. Guard: if raw cc ≥ 90, keep raw. Ccd still owns clear/partly-cloudy tail (bin 5-20: n=480, −45%). Same shape as v0.6.389g cc/95-100 Lc skip; finding surfaces one layer up in Ccd.

2. **Lsr bias table drift fix** (`solar_correction.py` + `analysis/l5_recompute_biases_hourly.py`). sr Last-24h +10.1% traced to `_BIAS_BY_REGIME_HOUR` being hardcoded at v0.6.248 ship (2026-06-28) and never refreshed. Diff vs today's fitter: 47 cells with |Δ|≥50 W/m², frontal regime had 8 live entries with 0 fresh support (fitter dropped it). Multiple cells sign-flipped; sw_flow/16 moved −170 → +136 (Δ +306 W/m²). Structural fix: fitter now writes `weather_collector/data/lsr_bias_table_curated.json`; `solar_correction.py` loads at import time. Same pattern as `lc_correction_table.json`. Retires manual-sync drift class per `[[feedback_curated_json_daily_drift]]`.

3. **dpbp flipped ENABLED=True** (`dp_bias_persistence.py`). First antecedent-error specialist LIVE. 7-day gate cleared. Preflight verified: code unchanged since 07-28 ship, params match Stage 2, shadow write firing +2.0°F per lead in nw_flow (38 leads at flip tick). Preflight gap flagged: dpbp shadow key not stamped in pair log — same infra gap likely at chp/wdp flip. Follow-up: give dpbp the v0.6.382p treatment (stamp shadow key to error log) for future measurable pre-flip gates.

4. **wg L3 SKIP_TABLE +3 cells** (`decay_apply.py`). 08-04 re-cut cleared: calm/24-47 (n=1744, pooled +45.2%, halves +4.3/+53.1), sea_breeze/24-47 (n=2298, +31.1%, halves +4.0/+45.0), frontal/12-23 (n=443, +8.8%, halves +13.2/+4.5 NEW). Two 24-47 cells were held from 07-28; A halves drifted 7→4 but still above 3% floor, pooled damage +45%/+31% justifies shipping now with demote-on-A-negative watch at next re-cut. Live table now 7 cells.

5. **Metric provenance overhaul (v0.6.391 bundle)**. External review flagged two different "7-day" numbers on debug page (top per-field table vs narrative). Fix:
   - `analysis/mae_over_time.py` emits `last_7d` block (n-weighted 7d parallel to `last_24h`)
   - Top per-field snapshot table now sources both 7d and 24h from `mae_over_time.json` in one fetch
   - Hand-typed narrative replaced with auto-populated bins from same source
   - Per-section audit label (source, window, method, refresh time)
   - PROD_PRIORITY + _prodKey + _applied: added dpbp/wsbp entries (dpbp just flipped LIVE but wasn't in any priority chain — silent-lie hazard)
   - New `tests/test_prod_key_coverage.py` (4 tests, discovers ENABLED specialists from processors/ and asserts every priority chain covers them)
   - See `[[project_metric_provenance_v0391]]`

6. **Raw-difficulty index (v0.6.392)**. `analysis/mae_over_time.py` emits `raw_difficulty_index` block: per-field ratio of trailing-7d raw MAE ÷ trailing-90d reference (7d excluded from reference). Debug page audit label shows mean + top-3 hardest + top-3 easiest. First-run today: mean 1.04× (flat) hides bimodal spread — cloud fields +18 to +67% harder than 90d normal (pa 1.67×, cm 1.62×, pp 1.29×, ch 1.19×, cl 1.18×), thermo fields 23-43% easier (dp 0.57×, h 0.62×, wd 0.66×, t 0.77×). Cloudy-and-mild week. See `[[project_raw_difficulty_index]]`.

7. **v0.6.392a — direction-neutral audit label**. "discount weekly correction lift accordingly" was directionally wrong for the >1.0 case (fixed-effect corrections show smaller % on hard weeks). Replaced with "interpret weekly correction gains in that context." See `[[feedback_audit_label_direction_neutral]]`.

## Deferrals

- **wsbp flip HELD** — preflight step 1 fails: calm regime n=0 in 7-day shadow-log window. Wait for calm regime to appear (typical: overnight ridge) then re-check.
- **Lsb flip HELD** — 24h attribution buffer after Lsr table refresh. `sr_sea_breeze_lsr_refit_stage2` says PROMOTE (pooled +11.4%, halves +43.8/+22.7%). Ship tomorrow if Lsr settles clean.

## Process lessons captured

- `[[feedback_version_bump_convention]]` — numbers for substantive, letters ONLY for follow-on debug page tweaks. Never invent `aa`/`ab` when running out of single letters (means you were mis-labeling for weeks).
- `[[feedback_debug_page_full_sweep]]` — "sweep the debug page" = complete update. Half-assed is worse than not doing it. Say so if the timing is wrong.
- `[[feedback_metric_provenance_labels]]` — every metric traces to source/window/method/refresh. Two same-name-different-value metrics is the worst failure mode.
- `[[feedback_audit_label_direction_neutral]]` — name confounds, don't prescribe direction unless the math forces it.

## Follow-ups queued

- **dpbp pair-log stamp gap** (`[[project_top_level_forecast_sweep]]` sibling): stamp `corrected_dew_point_shadow_dpbp` to error log so future ENABLED=False→True flips have measurable pre-flip gates. Would have unblocked today's preflight step 2.
- **Lsb flip 08-05** if Lsr settles clean.
- **wsbp re-check** when calm regime accumulates in shadow window.
- **h L2 retune watch closes 08-07** — verify τ-suspect signature at 6-11h/12-23h compresses toward 0.
- **C1h narrow-promote 6/7** — clears tomorrow if window stays clean.
- **Standardized-lift Phase 2-4** — deferred; raw-difficulty index alone was judged sufficient for now. Revisit if a specific decision gets fooled by weather-mix.

## Evening — debug page cleanup arc (v0.6.392b → 392f)

Joe surfaced a per-field snapshot cell reading cl +45.7% (7d) while the scoreboard showed cl in the "5 flat" bucket. Investigation:

- Both views are 7-day (Fitter `TIMESERIES_DAYS=7`; `mae_over_time.last_7d` is trailing 7d). No window mismatch.
- Aggregation differs: scoreboard averages per-lead MAE arithmetically with n≥30 per-lead floor + fallback to `_prodKey(f)` approx; 7d cell pools raw pair-log rows n-weighted keyed on applied_layer stamp.
- For cl in this window: prod_real MAE 33.14 vs raw 22.75 = +45.7% honest damage from 07-28 → 31 (Lc pre-kill + clp-stamp pre-v0.6.390j guard). Backfill on 08-02 was conservative and left clp-stamped rows unchanged where error genuinely matched clp (Lc actively wrong on those days).
- Note that said "cl now green −1.1%" on the debug page was hand-typed on 08-02 when the pf-mae cell was still reading tsDoc; today's v0.6.391 flipped that cell to `mot.last_7d`, exposing damage that was diluted before. Cell rolls to zero by ~08-07 as poison days age out.

**Root of drift class:** any hand-typed percentage or day counter in prose ages badly. New pattern: auto-populate spans from the same data source as adjacent cells. See `[[feedback_narrative_prose_auto_populate]]`.

### Ships

- **v0.6.392b** — `pf-status` span replaces "cl now green −1.1%" prefix. Populated from `mot.last_7d.cl` via same priority walk as the pf-mae cell. Pattern generalizes.
- **v0.6.392c** — scan-all sparkline grid falls back to `prod_real` when `prod` is absent so L1_ONLY fields (wd) render green line + MAE label like the others.
- **v0.6.392d** — tile labels keep FIELD_LABELS units ("Wind speed (mph) MAE 2.5" not just "Wind speed MAE 2.5").
- **v0.6.392e** — swept all per-field snapshot status prefixes: h/cc/cm converted to `pf-status` spans; ch/wd/cl/sr surgical prose fixes (dates, day counts, held vs closed, added today's wg L3 +3 cells to wg row).
- **v0.6.392f** — post-ship watch cleanup:
  - Retired 5 closed-clean/permanent items: chp 14-day (07-19→08-02), ws L3 asymm SKIP (07-20→08-03), Lsb 7-day flip gate (07-28→08-04 held), Lt retirement 2-window (07-16), v0.6.291 raw-baseline verifier (permanent infra).
  - New `watch-day` span pattern: `<span class="watch-day" data-shipped="YYYY-MM-DD" data-window="N">` auto-fills "day X/N" (or "closed Nd watch (day X)" past window). Applied to h L2 retune, Lc regime-cond Stage 1, wd L2 blend, wdp, wind_blend, wg L3 (2 watches), ws L3.
  - Fixed 2 R&D-drilldown mentions of clp/chp still saying "closes tomorrow" 08-03.

### Deferred (evening additions)

- **Reconcile scoreboard aggregation with 7d cell**: currently the scoreboard's `_prodArr` per-lead n≥30 floor + fallback to `_prodKey` approximation silently reads _FIELD_SKIP cl as flat. Options: (a) give scoreboard a pooled aggregate too, (b) drop the floor's silent fallback and show "insufficient data" when production sparse. Not urgent — cl 7d cell rolls to zero by ~08-07.
- **Backfill scope decision**: current `backfill_cl_applied_layer.skip.py` only rewrites rows where `error` matches a lower layer's error. Conservative and correct — those days really did ship damage. But means prod_real for 07-28→31 will always read poisoned. If we ever want prod_real to reflect "what the current code would produce" instead of "what actually shipped," we need a separate `prod_current` metric. Do NOT extend the backfill to rewrite history.

## Health snapshot end-of-session

Per `raw_difficulty_index`, this week was cloudy-and-mild — 5 cloud fields significantly harder than 90d baseline, 4 thermo fields significantly easier. Explains a lot of the recent per-field variance we've been chasing.

Per `last_7d` (n=7104 each): h −2.7%, ws −2.0%, cc +12.4%, sr −2.6%, dp −4.9%, ch −71.2%. cc's number will drop next week as the Ccd sat guard's post-deploy window enters the 7d rollup.
