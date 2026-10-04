---
name: project-07-09-session
description: "2026-07-09 marathon — 18 commits. Full applied-layer audit + gate-firing log pipeline (Phases a/b/c). Stage 4 audit gets 'refined view' with mixture check + signed-drift + skip classes (metric-artifact fields excluded). 4 verdict-language fixes in same class (stated intent vs code behavior — bright-line rule codified). dp depression frontal branch closed. cl marine-layer hypothesis walked back. Debug page canon fully current."
metadata:
  node_type: memory
  type: project
  originSessionId: 8fe63d4c-d77f-4710-b151-c944929681e9
---

## Session arc

Started 07-09 morning to close the "wire yesterday's `applied_layer_audit` into Fitter preflight" follow-up. Cascaded into a full audit + logging pipeline, Stage 4 mixture check, hypothesis housekeeping, and canon sweep. 18 commits, three deploy cycles.

## Shipped (18 commits, v0.6.317 → v0.6.319f)

**Static config coherence:**
- **v0.6.317** — `applied_layer_audit` wired to Fitter preflight. Audit code refactored from `analysis/` into `weather_collector/processors/applied_layer_audit.py::run_audit()`; `decay_fit.py` calls it at the top of every Fitter tick. On any failure, refuses to publish new `decay_corrections.json` — previous corrections stay in place. Same CLI wrapper still runs in nightly digest. **First live exercise 07-09 15:07 PASSED** — `decay_corrections.json` republished at 19:11:52Z with `fitted_at: 2026-07-09T15:07`, n_pairs 2.8M. Fitter scorecard that tick: Overall −9.0% mean / −7.1% median, 8/10 winning, ch −46% biggest gain, ws +5.8% sole real regression (pp Brier +9.7% expected post-drop), worst cell ws@6-11h +13.9% (corroborates tomorrow's L3 strip).

**Runtime firing visibility (gate-firing log, three phases + UI restructure):**
- **v0.6.318** — Phase (a): `weather_collector/processors/gate_firing_log.py`. Per-tick per-operator × field × regime `fires` + `skips` buffered in memory, flushed to `gs://myweather-data/gate_firing_log.jsonl` at end of tick via GCS compose. L3/L4 instrumented.
- **v0.6.318a** — Phase (a) extended to Lsr, MLC, Lc, Lt (6 rows per tick). Semantics: `fires` = correction actually mutated a value; `skips` = would-fire cells suppressed by skip table or ENABLED=False gate. Phase (b) rollup writer (`analysis/gate_firing_rollup.py`) with 7-day window + dormancy flags shipped same commit.
- **v0.6.318b** — Phase (c): debug-page render section adjacent to Applicability map.
- **v0.6.318f** — merged Gate-firing frequency INTO the Applicability map section (two lenses on the same object: config vs runtime). One `<h2>`, one anchor.
- **v0.6.319e** — restructured default render: summary block (Operators / Field × op pairs / Skip-table cells firing / Dormancy flags / Fires while disabled) leads; per-cell table moved into `<details>`. Two rightmost rows (dormancy + fires-while-disabled) show green ✓ when 0, red ⚠ when nonzero.

**Together with the applied-layer audit, closes both halves of the silent-dormancy class:** audit = static config coherence (does the writer for every declared read exist?); gate-firing log = runtime firing visibility (are the configured cells actually firing?). See [[feedback-verify-writers-for-read-paths]].

**Stage 4 audit rework:**
- **v0.6.316e** — non-precip subset audit shipped (`SUBSET_EXCLUDE_FIELDS = {"pp", "pa"}`). First read morning showed legacy 15/10/7 NOT READY; cm/0-5h +78% top drifter.
- **v0.6.317a** — mixture check + signed-drift + skip-class integration. `c1_stage4_mixture_check.py` classifies FAIL and WATCH cells DEGRADED/IMPROVED/SAFE/PARTIAL/SKIP/THIN via forecast-value quartile stratification. `c1_stage4_audit.py` runs the check on every FAIL and WATCH, produces a `refined` view alongside the raw. Today's refined: **27 PASS / 1 WATCH / 2 FAIL / +12 excluded → MIXED** (raw was NOT READY). Real DEGRADED: `ws/24-47h transition` (3 wind bins degrading; corroborates tomorrow's ws L3 strip) and `cl/12-23h stable` (b1 low-forecast bin doubled).
- **Third Stage 4 metric limitation identified + fixed same day:** unsigned improvement reading as failure. 3 cells (sr/12-23h, sr/6-11h, cl/24-47h) had recent MAE *lower* than calib but were being counted as FAILs because `|Δ|/calib` is unsigned. Documented in [[project-stage4-audit-metric-limitation]] alongside the existing pp/pa near-zero-calib blowup + the newly-fixed mixture-drift class.

**Verdict-language fixes — 4 instances in 3 days:**

Same class of failure now codified in [[feedback-stated-intent-vs-code-behavior]]:

1. `h_wind_shift_rate_orthogonality` (v0.6.316e) — added `ortho == 0 → KILL` guard; "MIXED: 0 ortho / 36 total. Narrow promote or hold" made no sense with zero orthogonal cells.
2. `h_precip_fc_orthogonality` (v0.6.318d) — script was printing "→ PROMOTE" but C1f (precip_fc>0) has been a live confidence axis since v0.6.215 on 06-24. Reworded to "→ STABLE (axis live since 2026-06-24)".
3. `simulate_windows.py` (v0.6.319b) — R6 verdict was "PROMOTE" but R6 pivoted to confidence axis C1a on 06-19. Added `ALREADY_SHIPPED_AS` map so SHIP prints as STABLE (health check pass), HOLD as REGRESSION WATCH.

**Bright-line rule now in the memory:** any script emitting PROMOTE / KILL / SHIP / RETIRE needs an "already live?" check against production before its verdict is trustworthy.

**Debug page canon:**
- Applicability map + Gate-firing merged, section renamed "…what corrections trigger, why, **and when they actually fire**"
- L2 hand-curated `gated by` column filled across all rows ("always on" for most; "disabled at module level" for pr; "n/a — no obs network" for sr/pp/pa)
- L2 pr row's `current_state: applies` corrected to "disabled" (was stale since 07-01)
- L3/L4 descriptors now populate `gated_by` + `current_state` from `describe_applicability()`
- C1 axis rows inherit layer-level ENABLED gate via renderer fallback
- Ranked opportunities table filters addressed rows (sr → Lsr) out of top-10 by default; moved to collapsible block
- Section 2e "Post-aggregate-bias forecast" marked as "engineering view (pre-clamp)" with an amber caveat block — cc 121%, pp −6%, pa −0.025 in are pre-clamp diagnostic values, not user forecasts
- 213 lines of orphaned L6/Cove UI code deleted (v0.6.318c) — was throwing `TypeError` on every page load because `grid-l6-live` element didn't exist
- Recent activity block rotated twice; 07-06 entries trimmed per rolling 3-day window

## Hypothesis housekeeping

- **dp depression frontal branch: closed 2026-07-09.** Trajectory −2.19 → −1.98 → −1.51 → **−0.87°F** — below the 1.5°F action floor. Branch retired.
- **dp depression nor_easter branch: watch opened.** +3.79°F ★ but n=279 (nor_easters are rare — sample won't grow fast). Gate: 3 consecutive reads with n growing AND |bias| holding above 1.5°F.
- **cl marine-layer hypothesis walked back.** Stage 1 sanity check (`marine_layer_cl_stage1.py`) tested whether cl/12-23h DEGRADED cell was a nw_flow marine-layer analog. Result: the cl over-forecast at night+eve is regime-agnostic (nw_flow-active +17.16 pp; -inactive +17.17 pp — identical). Weekly trend fading (W25=+20 → W28=+2). Transient atmospheric, not structural. **Added cl → L4 diurnal correction** as a new Stage 1 candidate (item 6 in project_todo).
- **cm/0-5h drift disproven as cell-level** (mixture drift explains ~90%). Was the top non-precip drifter this morning; investigation showed forecast-cm distribution shifted 4× more toward 95-100 bin in recent window; within-bin MAEs stable.

## Rules codified

- **[[feedback-deploy-sequence]]** generalized to collector-only ships too. Prior rule was "if collector + frontend both change, deploy first." Today expanded: whenever `weather_collector/` touches, deploy → wait one tick → verify → then push. Frontend-only and analysis-only exempt.
- **[[project-collector-schedule]]** — Fitter runs **twice daily at 03:07 AND 15:07**, not once. Any Fitter-gated verification fires twice per day; first exercise after a mid-day deploy is 15:07 same day, not next morning.
- **[[feedback-stated-intent-vs-code-behavior]]** bright-line rule (see above).

## Follow-ups queued

- **cl → L4 diurnal correction** — weekly re-read via `marine_layer_cl_stage1.py`. If W29–W31 stabilize at magnitude > ±5 pp, promote to Stage 2.
- **Nor_easter dp watch** — 3-read gate with n≥500 target.
- **Saturday 07-11 Stage 4 re-check** — using refined view, decide whether to SKIP the 2 real DEGRADED cells (ws/24-47h transition + cl/12-23h stable) and flip legacy C1 axis, or hold.
- **Tomorrow 07-10** — ws L3 strip earliest ship (day 8/7 gate), sr clean read (Lsr contamination window closes).
- **L2 gate-firing instrumentation NOT queued.** Reviewed with Joe today: L2 has no skip cells / ENABLED gates per field — no dormancy surface. Instrumenting would just log "fired every lead every tick." Explicit non-goal now.

## Related

[[project-todo]], [[feedback-stated-intent-vs-code-behavior]], [[project-stage4-audit-metric-limitation]], [[feedback-deploy-sequence]], [[project-collector-schedule]], [[feedback-verify-writers-for-read-paths]], [[project-c1-pivot-to-confidence]], [[project-marine-layer-cl-hypothesis]], [[project-07-08-session]], [[project-07-07-session]].
