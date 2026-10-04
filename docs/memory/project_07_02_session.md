---
name: project-07-02-session
description: "2026-07-02 — the day the audit framework caught up with reality. Per-row applied-layer stamping + retro backfill exposed that L6 warming + pr L2 additive + ws corrections were all net-negative vs raw at the population level, even though each passed its original marginal ship gate. Fixes shipped: L6 both branches disabled (v0.6.276), pr L2 disabled (v0.6.276), skip-table architecture live (v0.6.279) with ws L3 cells populated, L5 skip regimes ne_flow+calm (v0.6.280), ws τ=7 reverted after 07-02 digest flip. Canon page brought fully up to date (v0.6.282). Framework insight codified: primary ship gate is Production-vs-raw, not per-layer marginal MAE."
metadata: 
  node_type: memory
  type: project
  originSessionId: 56248ef4-af78-48a9-998a-163e8a07965d
---

## The framework insight

The old ship gate (walkforward, simulate_windows, various regime scripts) all tested **marginal correctness** — "layer X improves MAE vs layer X-1 at the population level." This is a local correctness test.

**The gate we should have been using**: "Production improves MAE vs raw L1 at the population level, per field, with no regime cell inverting." This is the global test.

Some layers passed local but fail global:
- **L6 warming branch** — passed its own r5_cove_analysis gate against raw baseline. But L2's Kalman blend for T is dominated by waterfront Tempests (Willow Rd, Neptune Rd at ~0.1-0.2 mi from the cove) — L2 already carries "waterfront bias." L6 adds MORE waterfront warming = double-counting. On the ~30% of rows where L6 fires, MAE is ~40% worse than L2 alone.
- **pr L2 additive** — K=1 (full strength) additive bias. Station consensus after altitude offsets is noisier than the raw model. Making pr Production +2.4% worse than raw.
- **ws L3** — L3 wins in most regimes (calm +15% to +44%!) but LOSES catastrophically in ne_flow (all bands, -5% to -9%) and short-lead sea_breeze (-9.5% to -15.2%). Population-level SHIP hides this.

## What made the framework insight possible

**v0.6.269 per-row applied-layer stamping.** Every pair-log row carries `applied_layer` (which layer's forecast was the user-visible one). `forecast_snapshot._derive_applied_layer()` walks L1→L6 arrays and picks the deepest layer whose value changed at each (field, lead) — every gate today is deterministic at forecast-build time so equality walk is exact.

**v0.6.275 retro backfill.** Fitter reconstructs `applied_layer` from `error_l1..l6` for pre-v0.6.269 pair-log rows via the same equality walk. Instead of waiting 7 days for the window to fill with stamped rows, Production numbers materialize immediately from the full 7-day pair-log window.

**v0.6.269 + v0.6.275 together = real per-row Production MAE.** This is what let us diagnose L6 warming, pr L2, and ws L3 in one Fitter cycle instead of waiting weeks.

## Tools shipped this session

- **`analysis/production_whatif.py`** — replays the 7-day pair log under alternate applied-layer choices. Every future ship goes through this preview BEFORE deploying. Interventions modeled: L6_warming_off, L2_ws_drop, L2_pr_drop, ws_L3_skip, sr_L5_skip, all_targeted. Extensible per intervention. Also handles counterfactuals correctly (dropping earlier layer while keeping later — additive-correction property).

- **Skip-table architecture in `decay_apply.py`** (v0.6.279). `SKIP_TABLE = {(field, layer): [(regime, lead_lo, lead_hi), ...]}` dict. `_should_skip()` helper checks each row before applying the correction. Fail-safe: missing regime → apply normally. Uses current-tick `state.regime_synoptic` across all leads (MVP approximation; per-lead regime classification refinement queued).

- **`solar_correction.L5_SKIP_REGIMES = {"ne_flow", "calm"}`** (v0.6.280). Same shape, for L5.

## What shipped (v0.6.263 → v0.6.282, spanning 06-30 evening → 07-02)

Full details in canon page's Since-last-curation block. Highlights:

- v0.6.263-266: TODO-driven UX pass on debug page.
- v0.6.267-269: CALM_GATE kill (code), per-lead Brier PP, per-row applied-layer stamping.
- v0.6.270-273: scorecard banner, C1 curated tables re-run, ws τ=7 (later reverted), C1e telemetry + wire-up, canon-page refresh, hybrid Production frontend.
- v0.6.274-275: n≥30 min-sample floor for hybrid Production, Fitter retro backfill.
- v0.6.276: **L6 warming branch disabled + pr L2 additive dropped.**
- v0.6.277-278: canon truth patch + L6 section moved to Archive as first dormant-layer entry.
- v0.6.279: **Skip-table architecture** + ws τ=7 revert.
- v0.6.280: **L5 skip regimes** (ne_flow, calm) + production_whatif extension.
- v0.6.281-282: canon page catch-up.

## Ships still open / in flight

- **Fitter window fills 07-05 → 07-08.** T, pr, sr, ws Production numbers will converge to whatif predictions over this period. Framework validation criterion: if reality diverges from prediction by >±3pp on any field, investigate.
- **L6 Fix B** (refit lookup against L2-corrected baseline) — real research, not queued for a date. cove_gradient_log.json still writes per tick for eventual input.
- **ws remains structurally worse than raw** even under the full targeted package (~+17-20% projected). Deeper investigation needed — some HRRR wind property this site can't correct.
- **h + sr → L4** — walkforward now recommends L4_ENABLED = {h, cc, sr, ch}. Do NOT ship wholesale; preview via production_whatif and run regime cross-cut first (sr especially — L5 already applies).
- **CHANGELOG catch-up** (docs/CHANGELOG.md) — 19 versions behind (v0.6.263 → v0.6.282). Deferred repeatedly.

## Categorization of the ~70 analysis scripts

Done as a classification pass 2026-07-02 evening — see canon page or the digest for the full breakdown. Summary:
- **Bucket 1 (re-audit under Production-vs-raw):** 5 items. Most notably `decay_tau_tuning` (flipped verdict), `l5_solar_analysis` (regime hides in aggregate).
- **Bucket 2 (light check on orthogonality-based decisions):** 4 items. `h_cloud_disagreement_orthogonality` had a 2-day flip — kills OK but methodology worth reviewing.
- **Bucket 3 (trust as-is):** 60 items. Absence-of-signal kills, data-limitation flags, calibration-metric C1 axes, settled tunings.

**Not a house of cards.** 5 items need re-audit; 60 hold under the new framework.

## Lesson

The audit framework we had for a month was locally right and globally wrong. Once we built the machinery to measure globally (per-row applied-layer stamping + retro backfill + production_whatif), the truth was visible in one Fitter cycle. Some things we shipped hurt users. Some things we killed were actually valid. **The pipeline isn't broken; the previous measurement infrastructure was inadequate.** Now it isn't.

See [[project-07-01-session]] for the Day 1 half of the story (from the retro-backfill and hybrid-render pattern). This memo is Day 2 (the fixes and the framework).

## Evening addendum — canon-page sweep + a real pipeline-order bug

**v0.6.278–v0.6.284: canon-page hygiene.** After Joe caught two stale spots I had claimed were "fully current," did a systematic grep-based sweep (L6/L5/warming/cooling/sb_*/v0.6.25X terms). Produced a 12-item list, knocked out all 12. Key lesson: **do not claim "fully current" without a systematic sweep** — my self-assessment of freshness was wrong twice in one afternoon. Sweep + list + explicit ask before "current" claim is the correct pattern going forward.

Categories fixed in the sweep:
- L6 dormant-state references (Production Stack line, R2 "addressed" tag, Cove card header, cove-gradient description, Fix B queue entry, L6 line in accuracy chart legend)
- L5 skip-regime coverage (Production Stack line, L5 section summary, applicability sub-block, L5 vs L4 audit note, accuracy-chart footer, `SOLAR_CORRECTION_ENABLED` constant name correction — actual name is just `ENABLED`)
- C1 axes staleness (Group A intro said "four shipped" now says "five"; long-form C1e Stage 1 backlog entry rewritten as SHIPPED; Stage 1 rolling table C1e row moved to SHIPPED; active-candidates summary line dropped C1e from active list; Stage 0 explorations reference updated)

**v0.6.285: fixed a real pipeline-order bug — same class, this one had been live for ~1 week.**

Joe screenshot caught SR Production line = Raw line exactly, with L5 line meaningfully lower. Debugging exposed that `raw_direct_radiation` was being captured INSIDE `apply_decay_corrections` (`collector.py:459`), but `stamp_solar_correction` (`collector.py:322`) runs BEFORE that. So `raw_direct_radiation` captured the L5-corrected value, not raw HRRR.

Evidence from live snapshot (pre-fix daytime tick):
```
Lead  sr_l1   sr_l4   sr_l5
  0    341    406    341     ← l1 == l5 (both post-L5); l4 is actual raw HRRR
  1    208    273    208
 15    191    256    191
 20    741    806    741
```

`sr_l1 == sr_l5` at every daytime lead. `sr_l4` (labeled "post-L4") was actually the true raw HRRR value. L5 was subtracting a delta from raw to get to the user-visible value, but the "raw" label was pointing at the corrected value, not the raw.

Impact:
- **User-visible forecast**: unaffected. `direct_radiation` is still post-L5 as intended.
- **Debug page "Raw model" line for sr**: showed L5-corrected values. That's why Production = Raw in the chart — both were post-L5, so error_l1 ≈ error_l5 on new pair rows.
- **Production accumulator on sr**: couldn't cleanly show L5's real benefit because the "raw" baseline was polluted. L5 chart line (78 vs raw 94.5) survived because OLD pair rows (from before L5 shipped) still had proper raw HRRR in `forecast_l1`.
- **Bug age**: since L5 shipped 2026-06-28 v0.6.248. A full week.

Fix (`v0.6.285`):
- New `preserve_raw_forecast_arrays()` helper in `decay_apply.py` (extracted from the inline block).
- `collector.py:322-ish` now calls it BEFORE `stamp_solar_correction`.
- `apply_decay_corrections` still calls it too (guarded by `dst not in hourly`, so idempotent no-op).
- Covers: `precipitation_probability`, `cloud_cover`, `direct_radiation`, `precipitation`, `cloud_cover_low/mid/high`, `wind_direction`.

Other fields checked in the same sweep, all clean:
- `cc`/`cl`/`cm`/`ch`: `cloud_obs_blend.py:88` does its own preserve BEFORE its `hourly[0]` mutation at line 103. Safe.
- `pp`/`pa`/`wd`/`t`/`dp`/`h`/`ws`/`wg`: nothing mutates pre-decay_apply.
- Marine layer sandbox: currently ENABLED=False. If flipped on, `preserve_raw_forecast_arrays` at v0.6.285's call site runs first, so safe.

**Verification pending.** Fix deployed evening 2026-07-02. Deploy landed at 23:07 = nighttime local. At night, `raw_solar_now = 0` → `compute_solar_correction` returns 0.0 → L5 is a no-op → snapshot output is indistinguishable between fixed and buggy pipelines. **First real verification window: ~06:15 local 2026-07-03**, first daytime post-deploy snapshot. Signal: if `sr_l1 = sr_l4` (both raw HRRR) AND `sr_l5 != sr_l1` (L5 applied a delta), fix is confirmed. If `sr_l1 = sr_l5` and `sr_l4` differs, fix didn't land.

Post-verification: 7-day pair-log window fills 2026-07-03 → 2026-07-10. sr Production number should drift toward the L5 aggregate (~78 W/m² MAE vs raw ~94 W/m² MAE) as more post-fix pair rows accumulate. Full clean read expected ~2026-07-10.

**Class of bug worth remembering**: correction that mutates a shared array BEFORE that array's raw copy is preserved will silently pollute downstream accuracy metrics. **Pattern to guard against**: any new correction layer needs to either (a) run AFTER `preserve_raw_forecast_arrays`, or (b) do its own preserve inline (like `cloud_obs_blend` already does), or (c) add its target array to `preserve_raw_forecast_arrays`. Audit any new correction against this at ship time.

Related:
- [[feedback-calm-gate-wrong-intervention]] — same pattern (marginal-vs-global), predicted this class of finding
- [[feedback-regime-lead-band-cross-cut]] — always run this before acting on population-level ship
- [[project-l6-warming-branch-watch]] — this note's watch resolved; L6 both branches now off
- [[project-l6-l2-double-counting-hypothesis]] — the L6-specific mechanism
- [[feedback-hybrid-transition-pattern]] — the rendering pattern for rolling-window-fill migrations
