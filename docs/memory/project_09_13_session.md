---
name: project-09-13-session
description: 2026-09-13 Sun full-day session — 6 ships across two arcs. Morning L1 3-way + wg skip + dp NWS scouts. Afternoon 24h per-field table → dug into t 24h -43.8% Total Lift → identified HRRR PBL morning-heating overshoot in stagnant clear-air → shipped stagnant_high regime label + named routing gate.
metadata: 
  node_type: memory
  type: project
  originSessionId: 9277b164-2f74-4598-b5f9-c405a8e15a79
  modified: 2026-09-13T16:29:52.741Z
---

# 2026-09-13 (Sun) session

## Ships (6 total, 4 collector deploys, 1 publisher deploy)

### Morning arc
- **v0.6.601** — L1 selector 3-way walker+runtime (HRRR/NBM/NWS). Walker adds NWS as 3rd direction; runtime `pick_source()` returns "nws" with `entry[f"{f}_nws"]` swap. dp gated at wire via `_NWS_FIELDS_WIRE_ELIGIBLE = {t, ws, wd, pp}` pending option B design. Today 3 dp cells cleared escalation but fall through to pool (nbm). Zero non-dp NWS cells cleared → runtime wire is a no-op today by design. Fires the moment any t/ws/wd/pp cell clears.
- **v0.6.602** — `l3_nbm.wg.nw_flow/12-23h` skip cell added. Two-window CONFIRMED: 14d n=472 lift −3.8%, 50d n=1,545 lift −5.0% halves −8.87/−1.86.
- **Morning scouts (no ship):**
  - dp NWS coherence: option A (t-agreement gate) DEAD — destroys lift. Option D as originally conceived is NO-OP for users (frontend reads `hourly.corrected_dew_point` from decay_apply, not forecast_snapshot). Real user impact requires option B at hourly-array level. DEFERRED pending option B design. See [[project_nws_dp_coherence_wire]].
  - cloud_delta + solar_delta Stage 1 orthogonality: neither general C1 axis (both HOLD-MIXED). Strong narrow pockets — cloud_delta on cc/cl/cm/dp/wd 0-5h, solar_delta on sr/cm/h 0-5h. Belongs in C1 marginal-axis narrow-ship pool. Curation deferred.

### Afternoon arc — diagnostic-driven ship chain
- **v0.6.603** — Recent Activity entry rewrite (was 2 ships → now 6, morning + afternoon narrative).
- **v0.6.604** — 24h Per-field diagnostic companion table added to debug page directly below the existing 7d table. `renderPerFieldDiagnostic()` parameterized on (windowKey, tbodyId, tfootId); called twice on page load. Difficulty column always sources `raw_difficulty_ratio` from the 7d block (it's inherently 7d-computed as 7d raw MAE / 90d ref).
- **v0.6.605** — `stagnant_high` regime label added to `classify_synoptic_regime()`. Thresholds: `ws<5 mph AND cc<0.40 AND |pt_3h|<0.5 hPa`. Checked before frontal/calm so light-wind + clear + steady-pressure states get their own bin instead of miscoding as se_flow/nw_flow/calm. Wire-through in forecast_error_log.py (both fc + obs) and solar_correction.py's live-regime classify path. Stamp-only ship — zero routing change; walker consumes automatically.
- **v0.6.606** — HRRR PBL morning-overshoot named routing gate. `l1_selector.pick_source()` gains optional hour_local kwarg + a gate: `field=="t" AND regime=="stagnant_high" AND hour_local ∈ {4,5,6,7,8}` (EDT) → return "nbm". Highest precedence. Reversible via `HRRR_PBL_MORNING_OVERSHOOT_KILL`. forecast_snapshot.py passes `_chp_valid_hour_local(times, i)` into the selector.

## Key diagnostic findings (afternoon)

### t 24h Total Lift −43.8% root cause
By-hour breakdown of t pair-log errors on 09-13:

| UTC hour | Local EDT | HRRR MAE | HRRR bias | NBM MAE |
|---|---|---|---|---|
| 09 | 05 | 2.74 | +2.48 | 0.67 |
| 10 | 06 | 3.40 | +3.13 | 0.62 |
| 11 | 07 | 2.49 | +2.28 | 0.59 |

Classic HRRR boundary-layer PBL-mixing overshoot in stagnant clear-air. Under clear skies + light wind + strong overnight radiational cooling, HRRR's PBL scheme mixes down aloft warm air too aggressively as the sun rises. NBM's climatological blend sidesteps this failure mode.

Prior 6d se_flow t data showed NBM was actually WORSE than HRRR at short-lead (1.49 vs 1.06); today is a complete flip on the specific morning-heating hours only. So this is a **narrow hour-of-day failure**, not a broad regime shift.

**Why:** [[project_wyman_cove_hrrr_l1_biases]] already documented HRRR biases at Wyman Cove; this session added the specific morning-heating × stagnant sub-pattern to the known-failure-mode set.

**How to apply:** when Total Lift on t regresses hard and by-hour data shows clustering at UTC 09-11 with positive bias, that's this pattern. The v0.6.606 named gate handles it going forward; if the pattern re-emerges after the walker prunes the gate, check whether the walker's stagnant_high × t × 0-5 cell has back-slid.

### Stagnant_high axis — field-by-field
Retroactive pair-log sweep at `ws<5 & cc<0.4 & |pt_3h|<0.5` (~2% of rows):

| Field | Verdict | Detail |
|---|---|---|
| ws | Ship — clear NBM signal | +16.6% stag vs +3.7% non-stag; robust across every threshold |
| sr | Ship at tight | +35.4% stag vs +13.8% non-stag; sweet spot at 4<0.3<0.5 (+50%) |
| wg | Modest | +38.7% vs +33.6%; baseline non-stag lift already large |
| t | NOT this axis | Non-monotonic across thresholds; the failure is hour-of-day × stagnancy, not stagnancy alone |
| ch | REVERSE (route HRRR) | −46.1% vs +34.6%; cirrus in stagnant clear-air is HRRR's strength |
| cc, h, dp, wd | No signal | Stagnant/non-stag lift indistinguishable |

**Why:** stagnant_high is real but not universal. A blanket "route to NBM in stag" rule would destroy ch. The walker's per-cell mechanism handles this correctly — it routes stag×ws to NBM, stag×ch to HRRR, ignores fields where the axis doesn't matter. Just what the by-regime walker was designed for.

**How to apply:** when adding a new regime axis, ALWAYS field-sweep before assuming universal benefit. My initial "route to NBM in stag" framing was wrong; the sweep caught it before shipping.

## Afternoon reversals (own-mistakes worth remembering)

1. **Over-scoped the "24h chart" request.** User asked for a 24h version of a per-field diagnostic table. I built a 24h Stack Health aggregate chart instead — wrong section, wrong shape. Ripped it out including the producer schema change (`last_48h_hourly` bucket in `mae_over_time.py`) and re-shipped correctly as the per-field table. See [[feedback_stated_intent_vs_code_behavior]] — the user's intent was legible from context; I over-interpreted.

2. **Wrong claim about dp surfaceability.** I told the user "yes, the 24h table would have surfaced dp" — wrong. dp is derived (Magnus of t and h) and explicitly omitted from the diagnostic table by design (`DERIVED_MARKER = { dp: "¹", cc: "²" }` at corrections_debug.html:4684). Caught before user acted on the claim. See [[feedback_verify_completeness_claims]].

3. **Attempted to defend "no real-time raw-quality awareness."** User pushed back with "which don't have real-time raw-quality awareness?" I hedged then verified — runtime selector IS pure static lookup (correct), but the fitter has a 7-day recency override (I'd omitted). Corrected before the user built assumptions on the incomplete claim.

## Post-ship watches (afternoon)
- First stagnant_high pair-log rows on next joiner write (~16:07 UTC on ship day).
- t 24h Total Lift trends toward zero as morning-hour rows use NBM.
- selector_picks for t stagnant_high should show NBM dominant in EDT 04-08 window.
- Walker `stagnant_high × t × 0-5` cell clears wire → remove HRRR PBL named gate.
- Stag × ws + stag × sr cells expected to escalation-wire earliest given retroactive lift magnitude.
- Stag × ch reverse-direction cell (HRRR-wire) — 3-day gate more likely than escalation.

## Session lessons
- **Build the diagnostic first, then the fix.** The 24h table surfaced the regression, the by-hour dig identified the mechanism, and both landed same-session with real understanding not a guess. Would have been much worse to ship a routing gate without knowing the mechanism.
- **"Would X have surfaced Y" claims need code-check.** I got the dp caveat wrong initially by intuition.
- **Field-sweep before regime-axis claims.** A regime axis that helps one field can destroy another (ch here). The walker handles field-specificity, but we need field-specificity in the analysis too — don't assume "route to NBM in this regime" is universal.
- **Reversibility matters.** v0.6.606's `HRRR_PBL_MORNING_OVERSHOOT_KILL` flag is a one-line rollback. Named gate is the right shape when the axis is real but the walker will take days to catch up.
