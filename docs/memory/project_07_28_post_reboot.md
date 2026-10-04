---
name: project-07-28-post-reboot
description: "07-28 post-reboot continuation. **4 ships** (v0.6.385 wg L3 SKIP_TABLE 4 cells, v0.6.386 ws L3 SKIP_TABLE 2 cells, **v0.6.387 dp_bias_persistence specialist ENABLED=False — first antecedent-error-based gate in the stack**, **v0.6.388 ws_bias_persistence specialist ENABLED=False — sibling, calm regime only**), 4 commits, 4 collector deploys (one hot-fix). Marquee findings: (1) flat-Stage-1 SKIP verdicts from 07-14 have largely evaporated on fresh data because the v0.6.370 asymmetric SKIP table (26 fc-bin cells) already absorbed most of that damage. (2) Backlog #6 (dp under-forecast attribution) resolved with clean investigation → v0.6.387 dp specialist ships pooled MAE 3.108→2.808. (3) **Antecedent-error-based gate is a NEW correction sub-pattern in this codebase.** It generalizes: pp antecedent probe = NULL (pp bias doesn't persist, per-regime r near 0 for pre_frontal/sea_breeze); ws antecedent probe = PARTIAL (pooled r=+0.470; only calm regime Stage 1 SHIPS; under-forecast regimes HURT). Pattern only works when model has stable systematic bias in one direction — event-driven regimes (like pp precip, or ws under-forecast from gust misses) don't fit. Ship discipline: 4-of-6 wg cells wired (2 held); all 2 ws cells wired; dpbp 3 regimes + wsbp 1 regime ENABLED=False with 7-day flip gates through 08-04."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9463fe7b-3db7-4c49-86b6-9979ab35e0e0
  modified: 2026-07-28T18:00:31.587Z
---

## Ships in this arc

### v0.6.385 — wg L3 SKIP_TABLE (4 clean-halves cells)

Stage 1 re-cut of `h_wg_l3_regression_stage1.py` on 06-28 → 07-28 windows.

**6 SKIP cells surfaced**, 4 shipped with clean halves-stability, 2 held for 7-day re-cut (wide-halves-spread, recent fading).

Shipped:
- `calm 0-5`: n=760, Δ +9.4% (halves +5.3/+10.0)
- `calm 12-23`: n=707, Δ +40.0% (halves +44.3/+39.4)
- `ne_flow 6-11`: n=1,538, Δ +11.8% (halves +6.2/+12.7) — NEW cell not in 07-14 set
- `sea_breeze 6-11`: n=865, Δ +5.6% (halves +8.0/+4.8) — NEW cell not in 07-14 set

Held (re-cut ~08-04):
- `calm 24-47`: n=3,253, Δ +49.9% pooled, halves A=+7.1 / B=+55.5 (recent fading)
- `sea_breeze 24-47`: n=2,904, Δ +40.8% pooled, halves A=+6.5 / B=+45.9 (recent fading)

Composition shifts from 07-14 Stage 1:
- ❌ calm 6-11 → THIN (n dropped from populous to 156)
- ❌ sea_breeze 0-5 → MARGIN (+2.72%)
- ❌ unknown 24-47 → PERSISTENCE_TERRITORY

Live verification (16:17Z sea_breeze regime tick): `decay_meta.skip_table_l3_cells_skipped` went 12 → 23 confirming new wg cells fire.

### v0.6.386 — ws L3 SKIP_TABLE (2 long-lead transition cells)

Stage 1 re-cut of `h_ws_l3_regression_stage1.py` on 06-28 → 07-28 windows.

**Only 2 SKIP cells qualify**, both clean halves:
- `frontal 24-47`: n=987, Δ +5.8% (halves +4.7/+9.4)
- `pre_frontal 24-47`: n=9,268, Δ +8.0% (halves +3.4/+11.6)

Both shipped.

## Marquee finding — the asymmetric SKIP absorption

**8 of 10 unshipped SKIP cells from the 07-14 ws Stage 1 verdict have vanished from the SKIP set on fresh data:**
- calm 0-5 was +25% → now +2.64% KEEP
- calm 12-23 was +76% → now PERSISTENCE_TERRITORY
- calm 24-47 was +73% → now PERSISTENCE_TERRITORY
- nw_flow 24-47 was +29% → now +2.15% KEEP
- sea_breeze 6-11 was +9.5% → now +2.21% KEEP
- sea_breeze 24-47 was ~+40% → +20% pooled but recent-half only +2.76% (MARGIN, dying)
- unknown 6-11/12-23/24-47 → all MARGIN (below floor or halves-unstable)

**Best explanation:** the v0.6.370 ws L3 asymmetric SKIP table (26 fc-bin cells, shipped 07-20) already covers most of the calm/sea_breeze/unknown damage. What Stage 1 now measures is RESIDUAL L3 damage after asymmetric SKIP has done its work. The "10 SKIP cells / only 2 wired" narrative from 07-14 was partially closed by the 07-20 asymmetric ship, not left open as pure debt.

**Implication for future Stage 1 re-cuts:** don't propose to demote / rewire based on comparing fresh Stage 1 to a pre-asymmetric-SKIP Stage 1. The layers are now composed. The correct evaluation is (a) does fresh Stage 1 find NEW cells to add? (b) do EXISTING flat-SKIP entries still hurt at their measured leads?

**Existing ws SKIP_TABLE entries potentially stale:** fresh data shows `ne_flow 24-47: −5.45%` (L3 actively HELPS at that band). The `ne_flow 0-48` entry is thus at least partially over-scoped. Not corrected this session — SKIP is fail-safe (removing L3 where it might help is opportunity cost, not damage). Flagged for future cleanup pass.

## Also this session — earlier

### cm investigation (pre-ships) — session-close narrative mismatch

Detailed in [[project_cm_investigation_07_28]]. Prior session-close claimed "cm losing lift for 5 days" + "cm L4 mixture-check DEGRADED at 12-23h + 6-11h." Both wrong:
- mae_over_time recent low lift = low-raw-error artifact, not degradation
- Fresh mixture-check surfaces exactly ONE cm cell DEGRADED: cm/0-5h [transition] bin 3 (+45%, n=313)
- cl shows same-shape degradation at same regime/bin (same n rows) — joint cl/cm hypothesis for 07-30+ re-check

### wind_blend v0.6.384 verification

Verified v0.6.384 (BLEND_HOURS=4) live in production: `wind_blend.py:86 BLEND_HOURS = 4`, collector deployed 13:08Z pre-session-reboot. Local pair-log cache pre-deploy so no measurable signal yet — meaningful check is tomorrow's digest per session-close ledger.

## v0.6.387 — dp bias-persistence gate (Stage 3 SHIP, ENABLED=False)

**First antecedent-error-based gate in the stack.** All prior persistence gates fire on current-state variables (regime + lead + fc value); this one fires on the previous 24 hours of `forecast_l1 - observed` dp bias per regime.

### The investigation arc (all one session)

1. **Backlog #6 direction-stability check** (`h_dewpoint_depression_stability.py`) — 8-day chunk split of the 3 candidate DP-DOMINANT regimes from v0.6.383a. All 3 regimes came back MIXED or UNSTABLE (attribution flipped between DP-DOMINANT / NOISE / T-DOMINANT / BOTH-COMPOUND across chunks). Would have HOLD'd backlog #6 on this alone.

2. **Per-day distribution probe** — showed 57-67% of days in each candidate regime had dp_bias < −1°F, only 3-4% had > +1°F. The pooled bias is broad-based, not outlier-driven. The 8-day chunks that failed direction-stability were catching clusters of quieter days that diluted or flipped the mean.

3. **Antecedent lag-1 correlation probe** — pooled daily dp_bias lag-1 Pearson r = **+0.583**. Multi-day streaks visible (07-13 → 07-16 in pre_frontal; 06-27 → 07-02 in sw_flow). Event-onset first-day NOT antecedent-predictable, but days 2+ of every streak are.

4. **Stage 1 walkforward** (`dp_bias_persistence_stage1.py`) — halves-verified. Trigger: prev-day dp_bias < TRIGGER_THRESHOLD. Fire: +CORRECTION°F. Initial (trig=−1.5, corr=+2.0, all leads): pooled +8.57%, pre_frontal SHIP +14.95, nw_flow SHIP +11.88, sw_flow SHIP +12.47. Per-cell: 0-5h leads DAMAGED −20 to −33% (fixed add over-corrects rows already close-to-obs via L2). Refit lead≥6: pooled +9.63%, all 3 regimes SHIP with both halves positive.

5. **Stage 2 sweep** (`dp_bias_persistence_stage2.py`) — TRIGGER × CORRECTION grid across {−1.0..−2.0} × {+1.0..+2.5}. Every combo SHIPS for every regime; surface is monotonic (looser trigger + bigger correction = more gain). No pathological over-fit local optima. Conservative center of grid shipped (trig=−1.5, corr=+2.0).

### Ship-shape locked

- Gate: `regime_obs ∈ {pre_frontal, nw_flow, sw_flow} AND lead ≥ 6h AND prev_24h_dp_bias(regime, from L1) < -1.5°F` with `n_antecedent >= 20`
- Fire: +2.0°F to `hourly.corrected_dew_point`
- Rolling state: GCS `dp_bias_antecedent_state.json`, 48h window, ~50KB, per-tick sample append + prune
- Bootstrap: first ~24h post-deploy the state is warming and the gate stays silent regardless of ENABLED
- Shadow-write invariant honored (`corrected_dew_point_shadow_dpbp` unconditional)
- Preserve-before-mutate honored (`corrected_dew_point_pre_dpbp`)
- Runs AFTER `dp_residual_persistence` (composes on top; dprp itself ENABLED=False)
- ENABLED=False. 7-day live-layer flip gate through **2026-08-04**.

### Live verification (post-deploy tick 17:27:18Z)

- Deploy hot-fix needed: original placement referenced `_gcs` (scope was `build_weather_data` at line 221; my stamp lives in `main()` scope at line 603). Fixed by calling `get_client()` at the callsite.
- Post-fix tick clean, dpbp telemetry envelope present, shadow + pre-gate arrays written.
- Antecedent map correctly empty on first tick (`n=0` per regime); current regime `sea_breeze` is not in focus set.

### Files touched

- new: `weather_collector/processors/dp_bias_persistence.py`
- new: `weather_collector/data/dp_bias_persistence_curated.json`
- edit: `weather_collector/collector.py` — stamp wire post-dprp + descriptor import/loop
- new: `analysis/h_dewpoint_depression_stability.py` (Stage 0b — chunk stability probe)
- scratch: `dp_per_day.py`, `dp_leadband_stability.py`, `dp_antecedent_probe.py`, `dp_bias_persistence_stage1.py`, `dp_bias_persistence_stage2.py` (Stage 0/1/2 probes)

### Preflight for 2026-08-04 flip

See [[preflight_dpbp]] for the flip-day preflight-drift verify.

## v0.6.388 — ws bias-persistence gate (Stage 3 SHIP, ENABLED=False, calm only)

Sibling of dpbp — cloned architecture with sign inversion.

### Investigation

1. **Stage 0 probe** (`ws_antecedent_probe.py`) — pooled lag-1 r=+0.470 (moderate). Per-regime: **calm +0.706 (strong), ne_flow +0.649 (strong)**, pre_frontal/nw_flow/sw_flow moderate (0.40-0.43), se_flow/sea_breeze weak (0.27-0.33).

2. **Stage 1 walkforward** (`ws_bias_persistence_stage1.py`) — only 2 regimes SHIP by pooled+halves numbers: **calm +11.07% (A +13.35 / B +10.33)** and ne_flow +10.91% (A **+0.00** / B +11.24). Under-forecast regimes NEGATIVE: nw_flow −11.29%, pre_frontal −1.47%, sw_flow −6.93%.

### Dropped from ship — ne_flow

ne_flow's A half had **0 fires** — the SHIP verdict rests entirely on the older half. Underlying: ne_flow's pooled +1.58 mph over-forecast is driven by a small number of dominant "over-forecast" days early in the window; recent ne_flow days trend NEGATIVE (under-forecast). The regime has drifted, and the antecedent trigger stopped firing. Fragile verdict — held.

### Under-forecast regimes fail

nw_flow / pre_frontal / sw_flow all show consistent −0.8 to −1.1 mph pooled under-forecast bias and moderate lag-1 r, but the antecedent correction HURTS. Physical read: over-forecast is a stable systematic error (model reads wind that isn't there — subtracting works). Under-forecast is event-driven (missed gusts, missed pickups) — a constant "yesterday's negative bias" over-corrects on quiet days.

**Key generalization insight:** the antecedent-error pattern only ships when the model has a stable systematic bias in one direction. Event-driven bias (like pp precip, or ws under-forecast) doesn't fit.

### Ship-shape locked

- Gate: `regime_obs == "calm" AND lead >= 6h AND prev_24h_ws_bias > +1.0 mph` with `n_antecedent >= 20`
- Fire: subtract `min(prev_bias, 3.0)` mph from `hourly.wind_speed`
- Non-negative wind clamp applied (correction can't push below 0)
- Rolling state: GCS `ws_bias_antecedent_state.json`
- Shadow-write unconditional (`hourly.wind_speed_shadow_wsbp`)
- Preserve-before-mutate (`hourly.wind_speed_pre_wsbp`)
- Runs AFTER dpbp in pipeline
- ENABLED=False. 7-day flip gate through **2026-08-04**.

### Live verification (post-deploy tick 17:57:13Z)

- Telemetry envelope present. Current regime `pre_frontal` (not in focus set) → 0 eligible fires. Antecedent map empty n=0 (state just seeded).

### Files touched

- new: `weather_collector/processors/ws_bias_persistence.py`
- new: `weather_collector/data/ws_bias_persistence_curated.json`
- edit: `weather_collector/collector.py` — stamp wire + descriptor import + descriptor loop
- scratch: `ws_antecedent_probe.py`, `ws_bias_persistence_stage1.py`

### Preflight for 2026-08-04 flip

See [[preflight_wsbp]] for the flip-day preflight-drift verify. Note: since only calm regime ships, the flip pre-check should also confirm calm regime has appeared ≥ once in the shadow-log week; if it hasn't (unusual but possible), the gate hasn't been observed firing at all.

## Related

- [[project_ws_l3_skip_table]] — updated with 07-28 re-cut
- [[project_wg_l3_skip_table]] — updated with 07-28 re-cut
- [[project_ws_l3_long_lead_regression]] — asymmetric SKIP absorption is the mechanism that closed most of this
- [[project_cm_investigation_07_28]] — earlier in same session
- [[project_07_28_session]] — the pre-reboot session
- [[feedback_verify_completeness_claims]] — cm session-close mismatch reinforced this
