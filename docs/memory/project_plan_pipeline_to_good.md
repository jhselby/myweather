---
name: plan-pipeline-to-good
description: "Roadmap from 'flat MAE' (post-2026-08-18 frame audit) to 'good.' Item 0 is input-frame expansion (NWS gridpoint pilot shipped v0.6.431 08-18). Original items 1-7 renumbered as items 1-4 (terminal), 5 (deferred), 6-7 (in-flight walkers). Nudge if any in-progress sits >7 days."
metadata: 
  node_type: memory
  type: project
  originSessionId: ee3022f3-1d0e-4e93-abfb-dbc558df1928
  modified: 2026-08-18T14:12:08.714Z
---

# Pipeline-to-good plan

**Rewritten 2026-08-18** after 6-week frame-exhaustion audit surfaced that the daily digest was a closed loop over the pair log (HRRR/GFS/Pirate only). MAE flat for weeks, 6-for-6 CLOSED MISS on 08-17, plus discovery that NWS gridpoint (NBM-derived official NWS forecast) had been fetched at every tick for months and used only for briefing narrative. Not in the pair log. Not benchmarked.

**Originally written 2026-07-30.** Joe's standing instruction: "write it to a plan so we don't lose track. keep me on it." Surface at session start if no other work is queued; nudge on items sitting >7 days.

## Item 0 — Input frame expansion (TOP PRIORITY, IN-FLIGHT)

**Why this is on top:** the original items 1-7 all sat inside a frame where the input was HRRR + GFS + Pirate. That frame is exhausted per [[feedback_frame_exhaustion_watch]]. Skill gains from here require either better inputs or genuinely new architectural classes of correction (not more shift-table variants). Input expansion is the highest-EV lever.

### 0a. NWS gridpoint (NBM-derived) — plumbing SHIPPED 2026-08-18 v0.6.431
- **State:** [in-flight — data accumulating since 2026-08-18 14:10 UTC. Benchmark decision earliest 2026-08-21 with 72h of pair rows; full 7-day comparison 2026-08-25.]
- **What shipped:** `forecast_snapshot.py` stamps `{short}_nws` per hour for t / dp / pp / ws / wd, aligning NWS gridpoint validTime intervals to hourly grid with unit conversions. `forecast_error_log.py` emits `forecast_nws` + `error_nws` per pair row. `decay_fit.py` includes "nws" in per-layer MAE aggregation.
- **Next action:** in ~72h, write `analysis/h_nws_gridpoint_benchmark.py` that pools pair rows with `forecast_nws` non-null, computes per-field MAE + persistence-skill for NWS-gridpoint alone vs current-blend L1 vs each specialist layer. Compare halves-stability. If NWS-gridpoint wins on ≥2 fields with halves-stability, promote to L1 as replacement or per-field router.
- **Decision criteria:** ship if `mae_nws < mae_l1 - 3%` on ≥2 fields with A/B halves same-sign. Hold if noisy or split. Kill if NWS-gridpoint underperforms current L1 on all fields.
- **Blockers:** need 72h of data accumulation (waiting).

### 0b. MRMS radar for near-term precip — SCOPED 2026-08-06, DEFERRED (revisit after 0a)
- **State:** [deferred — reopen after 0a decision]. Historical note: [[project_mrms_radar_potential]] scoped Aug 6, deferred pending frame-audit clarity. Now that frame audit is done and 0a is the pilot, revisit MRMS as second input-expansion candidate if 0a ships.
- **Why:** short-lead precip is the field where user-visible mistakes hurt most (missed shower, false alarm). Current pp/pa forecasts are HRRR-derived and often blind to actively falling precip that MRMS radar shows in real time.

### 0c. HRRRE ensemble spread — NOT SCOPED
- **State:** [not-started]. Consideration: HRRR is one deterministic run; HRRRE is the ensemble which gives us spread information we currently synthesize from `cross_run_spread`. Native ensemble spread may be better signal. Revisit after 0a and 0b.

## Items 1-4 — TERMINAL (do-not-reopen unless architecture changes)

### 1. h + dp τ refit — CLOSED [KILL supersession guard] 2026-08-12
- [closed: 2026-08-12 v0.6.401i]. Guard caps verdict at KILL. h uses `_soft_ramp_factors(lead)`, dp is Magnus-derived. Reopen only if the guard is deliberately edited out.
- Details: [[project_h_dp_tau_refit]]

### 2. wd @ 6-11h field-walk — DEFERRED 2026-08-10 (Joe: leave it alone)
- [deferred: 2026-08-10]. Remaining lever is a UI design decision Joe consciously punted. Reopen only if Joe raises wd UI.
- Details: [[project_wd_transition_penalty_investigated]]

### 3. cl root-cause fix — LC RECENT-BIAS GATE SHIPPED 2026-08-15 v0.6.413; cl itself remains unfixed
- [shipped mechanism 2026-08-15 v0.6.413, refreshed 2026-08-18 v0.6.430]. `LC_RECENT_BIAS_GATE_ENABLED = True`. ch cleared per-field 7/7 (streak 11). cl and cm still CHURN. **cl not rescued** — three architectural attempts (EMA/Kalman, h-predictor router, direct-MAE gate rule) all CLOSED MISS 2026-08-17. Emerging conclusion: cl is beyond shift-table-family correction for HRRR/KBVY. **Input-frame expansion (Item 0) is the next real attempt at cl** — NWS gridpoint may have a per-cell cl bias correction we don't.
- Details: [[project_lc_regime_conditional]] · [[project_lc_ema_kalman_fallback]] (closed MISS) · [[project_cl_h_predictor]] (closed MISS) · [[project_lc_gate_rule_direct_mae]] (closed MISS)

### 4. Layer-tuple sanity test — SHIPPED 2026-08-04 v0.6.390k
- [shipped]. `tests/test_layer_tuple_sanity.py` + `test_prod_key_coverage.py`. 6 tests. Follow-on v0.6.391 added Ccd + dpbp coverage.

### 5. Digest action-list at the top — SHIPPED 2026-08-04 v0.6.390k
- [shipped]. `build_executive_summary.py:959-981` prepends 🚨 TOP ALERTS block above EXECUTIVE SUMMARY.

## Items 6-7 — BACKGROUND WALKERS (in-flight, no attention needed)

Both are anti-scar-tissue dynamic-gate migrations. Ship neutral by design (replace hand-typed skip tables with dynamic gates). Complete on their walkers; do not proactively push.

### 6. chp `_CELL_SKIP` → dynamic gate — [in-flight: day 3/7 walker]
- [in-flight: 2026-08-16 v0.6.421 Stage 0/1 script + Stage 3 wire OFF shipped, day 3/7 walker today]
- Workstream: [[project_chp_cell_skip_to_dynamic_gate]]
- Flips ENABLED=True automatically when its walker clears

### 7. Ccd `FORMULA` → dynamic per-cell gate — [in-flight: day 1/7 walker]
- [in-flight: 2026-08-17 opened + 2026-08-18 v0.6.429 Stage 3 wire OFF + day 1/7 walker seeded]
- Workstream: [[project_cc_combine_walker]]
- Flips ENABLED=True automatically when its walker clears

## Items 8+ — RESERVED for post-Item-0 expansion

- 8. C1 Stage 4 (confidence-band widening in the UI) — deferred, higher-priority after Item 0 decision
- 9. Structural regime-change detection (turn corrections OFF during transitions) — mentioned in [[project_08_17_session]] design implications, not scoped

## What NOT to do (2026-08-18 onward, until Item 0a settles)

- No new Stage 0 hypotheses inside the pair log (frame-exhausted, per [[feedback_frame_exhaustion_watch]])
- No new dynamic-gate migrations beyond items 6 and 7 (in-flight, letting complete)
- No debug-page sweeps except in response to real state changes
- No refactors of the existing correction stack until we know whether NWS-gridpoint changes L1

Explicit non-goals prevent the treadmill that dominated the past 6 weeks.

## Session-start check

When opening a session, before responding to the first substantive prompt:
1. Read this file
2. Read [[project_correction_stack]]
3. Read the most-recent `project_MM_DD_session.md`
4. Scan MEMORY.md "Active watches / open work"
5. Check [[feedback_frame_exhaustion_watch]] triggers

If Item 0a is still in-flight and it's been ≥72h since deploy (2026-08-18 14:10 UTC), run the benchmark script and surface the decision. Otherwise, sentry-only day.

## Related

- [[feedback_frame_exhaustion_watch]] — the mechanism this rewrite responds to
- [[feedback_ship_count_by_impact_class]] — measure whether Item 0a actually ships skill
- [[feedback_session_start_load_project_state]] — how to consume this plan
- [[project_correction_stack]] — layer-by-layer state, stays valid as base for Item 0 additions
