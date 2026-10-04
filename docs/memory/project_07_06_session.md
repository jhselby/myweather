---
name: 07-06-session
description: "The day sr unit-mismatch, silent skip-table dormancy, and classifier coverage gap were all found and fixed. Four collector ships (v0.6.308 → v0.6.311) chained from an investigation into a spurious sr L2 ship candidate."
metadata: 
  node_type: memory
  type: project
  originSessionId: 09a24dea-6790-4fe1-9293-8d6805d4b598
---

Started as an investigation into the digest's "IMPLEMENT L2 LEAD-DECAY — sr +2.9%" changed verdict. Ended with three unrelated real bugs found by pulling the thread.

**Ship chain (v0.6.308 → v0.6.311):**

- **v0.6.308** — Started fetching `shortwave_radiation` + `diffuse_radiation` from Open-Meteo alongside `direct_radiation`. Root discovery: model `direct_radiation` is direct-beam only; Tempest `solar_radiation_wm2` is total shortwave (direct + diffuse). Lsr has been fitting the definitional unit gap on top of any real regime signal. Explains why Lsr tanks ne_flow + calm (variable cloud → the gap swings hardest there). See [[feedback_preserve_before_mutate]] category for how this compounds.
- **v0.6.309** — Shadow-log model shortwave + diffuse on every sr pair row via `forecast_snapshot.py` (stamps `sr_sw`/`sr_diffuse`) + `forecast_error_log.py` (propagates as `forecast_shortwave`/`forecast_diffuse`). New `analysis/sr_shortwave_bias.py` quantifies the unit gap per regime. ETA meaningful read: ~2026-07-07 evening once 24h of daytime pairs accumulate.
- **v0.6.310** — Populate `derived.state` every tick. **The L3/L4 skip table shipped v0.6.279 on 2026-07-02 had never fired since ship day.** Every consumer (`decay_apply`, `solar_correction`, `backtest_snapshot`, `confidence_layer`, `state_stratified`) read `derived.state.regime_synoptic`, but nothing wrote it. `solar_correction.py` worked around it via inline classification (line 255-269); `decay_apply.py:461` did not — `_should_skip()` fail-safed to False on every row. Result: ws L3 still applied in ne_flow all bands + sea_breeze 0-11h despite skip cells being populated. Four days of the +25.7% ws Production regression continued unfixed. Fix: new `processors/state_stamp.py::stamp_state()` runs after `preserve_raw_forecast_arrays`, before `stamp_solar_correction` / `apply_decay_corrections`. Populates `regime_synoptic`, `regime_flow`, `wind_dir`, `wind_speed`, `wind_octant`, `cloud_cover`.
- **v0.6.311** — 10° coverage gap in `classify_synoptic_regime`. Post-v0.6.310 tick still showed `regime_synoptic: null` on wind_dir=84.4°. Branches were `[30, 80)` NE, `[90, 200)` SE — leaving `[80, 90)` uncovered. Every easterly wind in that 10° window has returned None since the classifier was written (pair-log + live tick). Fix: extend NE to `[30, 90)`. Verified first-tick post-fix on sea_breeze regime: `skip_table_l3_cells_skipped: 12` — the ws L3 sea_breeze 0-11h cell finally firing.

**Reversed decisions (walked back correctly under new evidence):**

The initial ship recommendation for `sr τ=24h L2 lead-decay` was wrong. Investigation revealed:
- `analysis/l2_lead_decay_fit.py` iterates all 12 fields but the production `decay_fit.py:L2_TAU_FIELDS = ("t", "h", "pr", "ws", "wg")` — sr not present.
- `solar_correction.py:212` says "no L2/L3/L4 apply to sr".
- The 4,449 sr pair rows with nonzero `forecast_l2 - forecast_l1` = L5's fingerprint (stamp_solar_correction runs BEFORE the `_post_l2` snapshot at `decay_apply.py:453`).
- Chart's "Aggregate bias (L2)" column for sr shows L5's contribution mislabeled as L2.
- Backed out `sr_L2_decay` scenario I had added to `production_whatif.py`.

Reversed correctly: the accuracy chart showed nonzero L2 values for sr, which turned out to be L5's fingerprint — not evidence of a real L2 mechanism. Held position on "don't ship" through Joe's pushback because the evidence supported it.

**Open follow-ups:**

- `analysis/l2_lead_decay_fit.py` still iterates all 12 fields; should mirror `decay_fit.py:L2_TAU_FIELDS` to prevent future spurious "ship candidates" for fields with no L2 mechanism.
- Pipeline-order bug: `stamp_solar_correction` runs before `apply_decay_corrections`'s `_post_l2` snapshot, so `direct_radiation_post_l2` captures L5-corrected values. Cosmetic (chart label mismatch); low priority.
- sr L2 station-bias infrastructure could be built from 18/19 Tempest sr sensors. Deferred until unit-mismatch resolves — build L2 the naive way now and it spends its budget correcting the direct-vs-total gap rather than real station bias.

**Debug page canon refresh (post-ship):**
- Current pipeline state header 07-04 → 07-06
- ws row: skip table finally firing note
- sr row: unit-mismatch investigation open
- Open regression paragraph: dormant→firing narrative
- Skip table architectural entry: SHIPPED → actually firing story
- "Where we are" Lsr section: sr unit-mismatch investigation flagged
