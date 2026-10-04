---
name: project-07-30-afternoon-handoff
description: "Handoff between 07-30 AM/midday marathon session and afternoon session. AM session was 9 ships (v0.6.389c-k) all on the Lc/cc architectural failure. Afternoon session picks up with everything reversible, all changes reflected in code+debug+memory, one live-shadow gate on the clock (Ccd through 08-06), watch is the regression sentry."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6c13f0ec-2762-47f1-aab5-a15c48f08029
  modified: 2026-07-30T15:45:58.106Z
---

# Afternoon session pickup — 2026-07-30 EOD

## Session state at handoff

**9 ships this session (v0.6.389c through v0.6.389k), 4 collector deploys.** All reversible by single-line frozenset / ENABLED-flag edits. Every step evidence-based. Memory + debug page + changelog all synchronized to reality as of commit 8fac18b + `v0.6.389k` frontend push.

**Version pill:** v0.6.389k
**Last collector deploy:** revision at 2026-07-30 13:51 UTC (Ccd Stage 3 wire)

## What's live right now

**Lc split-state (v0.6.389d-g emergency intervention):**
- **cl fully off Lc** via `_FIELD_SKIP = frozenset({"cl"})` in `cloud_saturation_correction.py`
- **cc partial:** `_CELL_SKIP` bin-kills cc/95-100 (universal) + cc/ne_flow/50-80 + cc/ne_flow/80-95 (regime-conditional)
- **cm/ch unchanged** — pooled Lc firing at all SHIP bins, all regimes
- Reversibility: single-line edits to `_FIELD_SKIP` / `_CELL_SKIP` frozensets

**Ccd Stage 3 wire (v0.6.389j) — ENABLED=False + telemetry:**
- New processor `cc_from_derivation.py` runs LAST in cloud pipeline after Lc
- Computes `derived_cc = max(cl_l6, cm_l6, ch_l6)` per lead
- SKIP_REGIMES = {"se_flow", "unknown"} → Pirate cc fallback
- Stamps `weather_data["cc_from_derivation"]` every tick with `derived` array + `would_fire` flag
- Held-out evidence (`h_cc_derivation.py`): +8.5% pooled MAE vs current cc, +5.8% halves-averaged
- **7-day live-shadow gate — day 0/7 through 2026-08-06**

**Regression sentry (v0.6.389i) — live in digest:**
- New `regression_sentry()` in `build_executive_summary.py`
- Fires when any field's daily Prod > Raw by ≥15% for ≥2 consecutive days
- Placed BEFORE persistence-skill + anomaly-detector sections
- Retro fires today: cl (3d +23% → +121% → +659%), cc (2d +163% → +514%)
- Tomorrow morning's 06:01 EDT digest will fire these until the daily gap closes

## What to watch

**Priority 1: does today's intervention work?**
- Tomorrow's 06:01 EDT digest should still fire cl + cc in the sentry (2-3d trajectory)
- **08-01 or 08-02:** cl should stop firing (cl_prod = cl_raw = 0% delta). If it doesn't, something else is wrong.
- **08-03:** cc should stop firing if the cc/95-100 bin-skip is enough. If cc keeps firing, escalate to full cc field-kill.
- Accuracy card Overall MAE mean should read −8% to −10% by 07-31 EOD. Fully back to ~−13% baseline by 08-06 as bad days roll off.

**Priority 2: Ccd 7-day shadow gate**
- Daily `h_cc_derivation.py` re-runs will update the pooled + halves + regime numbers as post-fix data enters the window
- Gate criteria for the 08-06 flip: pooled Δ ≥ +5% AND both halves ≥ +3% AND ≥ 6 regimes SHIP across 7 daily reads
- On flip: `ENABLED=True` in `cc_from_derivation.py` AND simultaneously retire cc's `_CELL_SKIP` entries in same commit — both in `cloud_saturation_correction.py`
- The `_CELL_SKIP` entries become moot because Ccd overwrites cc entirely; leaving them wouldn't hurt but is dead code

**Other pre-existing gates unaffected by today's work:**
- clp Stage 3 flip gate: day 4/7 through 2026-08-03
- Lsb narrowed-gate flip: day 3/7 through 2026-08-04
- dpbp / wsbp flip gates: day 3/7 through 2026-08-04
- wg L3 24-47 re-cut: 08-04
- Lc regime-conditional Stage 1 gate: day 1/7 through 08-06 (superseded conceptually by Ccd for cc, but still tracked for cm/ch)
- wd L2 post-fix watch: through 08-11
- wind_blend BLEND_HOURS watch: through 08-11

## Deferred / unresolved

**cl root cause not fixed.** cl field-kill stops today's bleeding but doesn't fix cl's Lc shift-table architectural failure. If cl's distribution normalizes on its own we may never need to fix it. If it doesn't:
- Candidate 1: EMA/Kalman shift tracker (same pattern as `station_bias.py`)
- Candidate 2: Recent-bias gate on existing lc_fit table
- Both multi-day workstreams

**Ccd formula choice.** Picked `max` because it beat `random` on this test set (+8.5% vs +5.1%). Physical argument favors max (METAR reports max-layer coverage). But if obs sources change (different METAR blend, ceilometer data), winning formula might flip. Not a risk today, worth remembering.

**Debug page has no dedicated Ccd section.** Lc has its own full section (~line 1585 of corrections_debug.html). Ccd doesn't — it's mentioned in Post-ship watches + correction stack list only. Fine for shadow phase; on 08-06 flip should probably add a small Ccd section.

## Fresh session AM read

Start here: [[project_07_30_session]] for the full arc; [[project_lc_regime_conditional]] for the Lc/Ccd state; [[project_todo]] for pre-existing pipeline work.

**First thing to check tomorrow AM:** does today's 06:01 EDT digest fire the regression sentry on cl + cc? If yes, sentry is working as designed. If cl doesn't fire, the field-kill is broken. If cc doesn't fire, either the bandages worked (unlikely on 1 day of data) or the sentry is misreading — verify with `h_lc_rolling_window.py`'s per-day trajectory.

**First thing to check when Ccd shadow data arrives:** run `h_cc_derivation.py` on the newer data. Does the +8.5% lift hold? Do regime SHIP counts stay stable?

## Cheat-sheet — files touched this session

- `weather_collector/processors/cloud_saturation_correction.py` — `_FIELD_SKIP`, `_CELL_SKIP` frozensets, `_shift_for` + `stamp_cloud_saturation_correction` extensions
- `weather_collector/processors/cc_from_derivation.py` — NEW
- `weather_collector/collector.py` — wired Ccd call after Lc
- `analysis/runlog/build_executive_summary.py` — `regression_sentry()`, `KNOWN_LIVE_PIPELINES` entry for `h_ws_blend_hours_sweep`
- `analysis/h_lc_regime_stage0.py` — NEW
- `analysis/h_lc_regime_stage1.py` — NEW
- `analysis/walkforward_lc_regime.py` — NEW
- `analysis/h_lc_rolling_window.py` — NEW
- `analysis/h_cc_derivation.py` — NEW
- `corrections_debug.html` — Rule 5 sweeps in v0.6.389h + v0.6.389k
- `.cache_lc_regime_gate_history.json` — NEW (Stage 1 gate history)
- Various curated JSONs uncommitted (daily fitter drift, not intentional ships)

## Reversal shortlist (if any single change today needs to be undone)

- `_FIELD_SKIP` cl kill: remove `"cl"` from the frozenset in `cloud_saturation_correction.py`
- cc/95-100 bin-kill: remove `("cc", "95-100")` from `_CELL_SKIP`
- cc/ne_flow demotes: remove `("cc", "ne_flow", "50-80")` and `("cc", "ne_flow", "80-95")` from `_CELL_SKIP`
- Ccd wire: `ENABLED = False` is already the shipped state; remove `stamp_cc_from_derivation(weather_data)` from `collector.py` to unwire fully
- Regression sentry: comment out the `sentry_lines = regression_sentry()` block in `build_executive_summary.py`
- Registry entry (v0.6.389c): remove `h_ws_blend_hours_sweep` from `KNOWN_LIVE_PIPELINES`

## Related

- [[project_07_30_session]] — full session log
- [[project_lc_regime_conditional]] — Lc + Ccd pipeline state
- [[feedback_ratio_over_absolute]] — design principle behind the sentry
- [[feedback_scorecard_banner_shape]] — clarification on the debug page banner
- [[project_lc_flip_outcome]] — the 07-17 flip this session partially unwound
- [[project_mlc_diagnosis]] — architectural cousin (same regime-blind bias failure pattern)
