---
name: project-nws-dp-coherence-wire
description: "dp gated out of NWS wire in v0.6.601. 09-13 scouts: option A DEAD (t-agreement gate destroys lift on biggest cell); option D as originally conceived is a NO-OP for user-visible dp — frontend reads hourly.corrected_dew_point not forecast_snapshot.entry['dp'], so snapshot-level routing only fixes pair-log attribution. Real user win requires routing at the hourly-array level (option B territory: touches decay_apply's _ensure_derived_moisture_consistency, cascades to inverse-Magnus h override + AH + feels-like). Deferred 09-13 pending proper option B design. Real wins vs live-prod are LARGER than fitter suggested (+41-45% at 2 cells vs +23-29% raw). Cell dp/nw_flow/0-5 is a fitter-vs-raw artifact — flat vs live-prod, would not ship."
metadata: 
  node_type: memory
  type: project
  originSessionId: 45cfd381-3cb4-4d5d-bfc4-10e1c2ebd46b
  modified: 2026-09-13T12:25:06.044Z
---

# NWS dp routing — coherence follow-on

## State as of 2026-09-13 (v0.6.601)

The L1 selector 3-way walker and runtime are live. Runtime allowlist
`_NWS_FIELDS_WIRE_ELIGIBLE = {t, ws, wd, pp}` — dp intentionally excluded
at `weather_collector/processors/l1_selector.py`. The walker still tracks
dp: today's 3 cleared NWS cells are all dp (see description), and they
appear in `weather_collector/data/l1_selector_by_regime_walker.json`
under `cells_cleared_for_wire_nws`. The gate strips them at wire-time,
not at diagnostic-time.

**Why:** dp is derived — `corrected_hourly.py:264` and
`forecast_snapshot.py:296/652` both compute `dp = Magnus(t, h)`. If the
NWS branch swaps `entry["dp"] = entry["dp_nws"]` while `entry["t"]` and
`entry["h"]` remain the HRRR/NBM walker's picks, the shown (t, h, dp)
triple stops being thermodynamically consistent — h=70% at t=68°F implies
dp≈58°F, so shipping NWS dp≈60°F alongside those creates a row where the
three values don't agree. Yesterday's v0.6.600 changelog flagged this as
tomorrow's work. [[project_dp_is_derived_no_dp_work]] is the standing rule.

**Payoff being deferred:** dp/nw_flow/12-23 alone is ~975°F-days/month of
error saved by escalation-clause math in [[project_09_12_session]] — real.

## Two coherence-aware wire paths

**Option A — NWS-t agreement gate.** Only route dp to NWS when NWS's own
t forecast for that hour agrees with our selected t within some tolerance
(e.g., |t_nws − t_selected| ≤ 1°F). Preserves the (t, h, dp) triple by
declining the swap when NWS's temperature model disagrees with ours;
Magnus stays consistent because NWS dp only fires alongside compatible t.
Cost: coverage drops when NWS-t diverges (exactly the disagreement cases
where dp routing might matter most).

**Option B — back-derive h from (t_selected, dp_nws) via inverse Magnus.**
Compute h = 100 · e_sat(dp_nws) / e_sat(t_selected) and overwrite
`entry["h"]` alongside `entry["dp"]`. Triple stays consistent by
construction, but means the h walker's pick gets silently overridden
whenever the dp NWS wire fires — arguably contradicts the h routing path
and could interact badly with the h L2/L3 layers, h residual persistence
work, and the derived cc pipeline (cc = Ccd(cl, cm, ch), which reads h
in some Lc paths).

**Rejected — Option C: route t and h to NWS too, whenever dp routes.**
Contradicts the point of per-field routing (t and h haven't cleared NWS)
and would ship a synthetic triple the fitter never validated.

## 09-13 empirical scout result — option A DEAD, option D LIVE

Ran `analysis/scout_nws_dp_coherence.py` — full output at
`analysis/output/scout_nws_dp_coherence.txt`. Headline numbers:

**Baseline lifts vs LIVE PRODUCTION (not raw sources — fitter used raw):**
- dp/nw_flow/0-5: **-0.09%** (FLAT — L2-corrected dp already matches NWS)
- dp/nw_flow/12-23: **+45.45%** (bigger than fitter's +29.3%)
- dp/pre_frontal/12-23: **+41.85%** (bigger than fitter's +23.6%)

**Option A (NWS-t agreement gate) sweep on the biggest cell:**
| tol_F | coverage | lift% | Δ vs baseline |
|-------|----------|-------|---------------|
| 0.5   | 24.6%    | +33.2% | -12.3pp       |
| 1.0   | 41.7%    | +37.2% | -8.2pp        |
| 2.0   | 66.6%    | +38.3% | -7.1pp        |
| inf   | 100%     | +45.5% | 0             |

Tighter gates uniformly LOSE lift. NWS's dp advantage correlates WITH
NWS-t/selected-t disagreement, not against. Option A protects against a
mechanism (Magnus consistency) that isn't the source of the win — the win
comes from NWS's independent moisture modeling being right on rows where
our temperature is wrong.

## Surviving options after 09-13 frontend-consumer audit

**Option D as originally conceived — NO-OP for users.** Deeper audit
after option A was killed: the forecast_snapshot's `entry["dp"]` is
purely a pair-log/scoring surface. Frontend NEVER reads it:
- `js/hair.js`, `js/outdoor.js` read `hourly.corrected_dew_point`
- `js/feelslike.js`, `js/corrections.js` read `derived.corrected_dew_point`
- `js/obschart.js` reads OBS log `entries[].dew_point_f`
- `js/frontal.js` reads OBS-derived frontal event dp_drop
- Zero references to `forecast_snapshot` or `snapshot.hours` in js/
- Grep confirmed 2026-09-13

So swapping `entry["dp"] = entry["dp_nws"]` at snapshot time only fixes
pair-log attribution — the user's displayed dp stays Magnus-derived from
`hourly.corrected_t` and `hourly.corrected_h`.

**Option D-lite (pair-log-only ship) — offered 09-13, deferred (b).**
Small scoring win, zero UX risk, but not worth a Sunday ship without the
option B design conversation to inform it.

**Option B (inverse-Magnus h back-derivation at the HOURLY ARRAY level)
— the real path for user impact.** To improve user-visible dp, route NWS
at `decay_apply.recompute_derived_moisture_arrays` (or its sibling
`_ensure_derived_moisture_consistency`) for the affected leads. That
function currently enforces `corrected_humidity = inverse_Magnus(
corrected_t, corrected_dp)` after any correction. If corrected_dp gets
swapped to NWS for cells 2 and 3, corrected_humidity gets silently
overwritten to whatever value is consistent with (t_selected, dp_nws).
Cascades to:
- `corrected_absolute_humidity` (recomputed via _absolute_humidity)
- `corrected_apparent_temperature` (recomputed via steadman_feels_like_f)
- h walker/L2/L3 corrections effectively bypassed on those leads
- cc = Ccd(cl, cm, ch) via any Lc paths that consume h
- dp_residual_persistence gate assumptions

**Option A — dead.**

## Next steps when option B design is scoped

1. Decide the cascade contract: when dp routes NWS at the hourly-array
   level, do t and h stay HRRR/NBM-walker while corrected_humidity gets
   inverse-Magnus'd? Or does h stay authoritative and dp gets forced back
   to Magnus (defeating the routing)? Or does the entire (t, h, dp)
   triple route as a coherent block (requires t and h to also clear NWS,
   which they haven't)?
2. Audit h workstream implications: h L2/L3 corrections, h residual
   persistence, cross_run_spread h axis, cc = Ccd(cl, cm, ch) reads.
3. Fitter change: 3-way fitter needs a live-prod baseline column to
   filter fitter-vs-raw artifacts like cell dp/nw_flow/0-5.
4. Post-ship watch: pair-log dp MAE at the 2 cells; user-visible dp/h/AH
   distribution shift; corrected_apparent_temperature stability; h walker
   didn't quietly break; frontal detector remains OBS-log-driven.

## What NOT to do

- Do NOT ship the pair-log-only D swap in isolation — it would drift the
  pair-log's `forecast` field away from what the user actually saw, so
  scoring analysis stops being about live production. That's a category
  of bug this repo has caught before (see [[feedback_pair_log_error_field]]).
- Do NOT flip `_NWS_FIELDS_WIRE_ELIGIBLE` to add dp without also
  routing at the hourly array — the walker's cleared-cells wouldn't
  reach the user, and the pair log would misattribute.

## Related

- [[project_09_12_session]] — session that produced the 3-way fitter and
  the escalation clause math that made dp/nw_flow/12-23 a wire candidate.
- [[project_09_13_session]] — v0.6.601 walker+runtime ship with dp gated.
- [[project_dp_is_derived_no_dp_work]] — the standing rule dp lives under.
- [[feedback_stated_intent_vs_code_behavior]] — the class of bug (routing
  applied to a derived field getting overwritten downstream) this gate
  prevents.
