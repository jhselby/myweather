---
name: 07-07-session
description: "Tuesday marathon. 6 debug-page versions (v0.6.312→315a) shipped scorecard honesty overhaul, \"Right now\" all-fields correction table, Production cell coloring, canon refresh, collapsable subsections, broken-banner deletion. 3 analysis pieces (divergence-reporter regex fix, sr shortwave-vs-cc confound diagnostic queued for 07-11, h_c1h_orthogonality PROMOTE). Landmark 15:07 Fitter — ws +25.7% → +2.3% (v0.6.310+311 skip table firing) + t/pr resolved via 06-30/07-01 window fill. Tuesday-cadence pattern confirmed."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6bb3eadf-bcbe-4bab-ba53-c02b00010f53
---

## Big-picture takeaways

**The Tuesday cadence pattern is now confirmed and documented.** See [[tuesday-cadence]]. Joe's Claude weekly limit resets Tuesday → Tuesdays are heavy ship days → the following Tuesday's 15:07 Fitter is the first read where the prior Tuesday's rolling-window contributions have aged out. Today confirmed with 3 fields: t, pr, dp all traced back to 06-30/07-01 ships (Lt-off, pr-L2-off). First hypothesis for any surprise Tuesday Fitter shift is exactly-7-days-prior in the git log.

**Stated-intent vs code-behavior drift caught twice today.** See [[stated-intent-vs-code-behavior]]. Both silent-failure fixes today (divergence reporter's L3_ENABLED/L4_FIELDS regex, scorecard's "pp excluded" footer note vs pp being folded into meanPct) had the same shape: documentation stated one thing, code did another. Nobody would notice by reading either in isolation. Adds to [[verify-writers-for-read-paths]] as a related silent-failure class.

## 15:07 Fitter — landmark cycle

| Field | Before | Today | Story |
|---|---|---|---|
| ws | +25.7% | +2.3% | Skip table firing (v0.6.310+311 fix from 07-06 evening) doing exactly what production_whatif predicted |
| t | +9.3% | +0.3% | Lt-off rows (v0.6.276, 07-01) aged out ahead of schedule |
| pr | +2.6% | +1.3% | pr-L2-off rows (v0.6.276, 07-01) aging out |
| dp | −6.1% | −20.3% | Cleaner t propagating through Magnus derivation + rain-day station uniformity |
| h | −2.3% | −5.6% | Similar cascade |
| ch | −45.5% | stable star |
| cc | −14.7% | −15.1% | stable |
| wg | −15.5% | −13.1% | stable |
| cm | −6.8% | −6.9% | stable |
| sr | 0% | −1.2% | marginal |
| pp | Brier +41.8% (in-flight) | Window still filling from 07-04 drop; resolves by 07-11 |

**Bottom line:** ws is no longer an open regression. That closes out the 4-day silent-dormancy hunt from earlier this week.

## Debug page overhaul

### Scorecard honesty (v0.6.312-315a)
- **Winning-fields denominator excludes flat** (7/10 · 2 flat instead of 7/13). Rationale: `pa` (uncorrected) and `cl` (correction only@lead 0 which the 1-47h average excludes) shouldn't count against the pipeline. Codified in comment.
- **pp Brier pulled to its own line for Overall/median/biggest-gain/worst-regression tiles.** Was folded in despite the footer note saying "pp excluded." Now separate `brierRows` array; MAE and Brier stay in their own units.
- **Median shown alongside mean in Overall tile.** Robust to tiny-denominator amplification (pressure raw MAE ~0.019 → any small change reads as huge %). When mean and median diverge, that gap IS the "concentrated wins vs broad wins" signal.
- **pp Brier counted in Winning tally** (v0.6.315a). Winning-count is categorical yes/no — well-defined regardless of scoring rule. Only numeric magnitudes need to stay same-unit.

### "Right now" box → all-fields correction table (v0.6.315)
- Was 4-tile grid (Temp / Humidity / Confidence / Briefing) — 2 field tiles duplicated the pipeline state table below, 2 ops-status tiles were unrelated.
- Now 13-row table: Field / Raw model / Production / Correction for every field with raw+corrected data at hourly[0]. Fills a gap: no other section shows composed current-tick corrections in one view.
- Field labels carry symbol in parens (`Temperature (t)`, `Wind speed (ws)`) → teaches vocabulary the scorecard uses.
- Correction column uses `pts` for %-valued fields (h, cc/cl/cm/ch, pp) not `%` → unambiguous vs "+57%" reading as 1.57× multiplier.
- Scorecard moved above headline box (headline-at-top convention).
- Confidence + Briefing dropped to compact ops footer.

### Production cell color-coding (v0.6.313)
- Per-band Production cells now compare to same-band Raw (L1): green if better by >0.5%, red if worse by >0.5%, white if flat. Threshold matches scorecard's `FLAT_EPS` so per-band coloring and scorecard's flat bucket agree.

### Canon sweep + housekeeping
- Recent activity rolling window rotated (07-04 falls off, 07-07 populated with 7 items)
- sr Lsr snapshot rewritten with first-read outcome (regime-specific; nw_flow benefits, pre_frontal/sea_breeze show shortwave worse)
- Engineering-updates subsections made collapsable via `<details>` (matches card pattern)
- Broken L3/L4 applicability banners deleted (unconditional `.hidden = false`; static "state changed" body with no diff)
- Scorecard footer note updated ("pp shown separately" not "pp excluded")

## Analysis ships

### Divergence-reporter regex fix
- Was greping `L3_ENABLED = {...}` / `L4_ENABLED = {...}` but walkforward emits `L3_FIELDS` / `L4_FIELDS`. Both keys silently fell into UNKNOWN status in every digest since the walkforward output was renamed.
- After fix: L3 wants to drop ws,wg (day 1/7), L4 wants to add sr (day 1/7 but frozen by Lsr contamination until 07-10).

### sr_shortwave_cc_confound.py — queued
- Joins each sr shadow-log row to paired cc row at same (run_time, valid_time). Stratifies sr signed error by |Δcc| bins. If overshoot concentrates on cc-miss rows (|Δcc|>25), Cause A dominates → invest in cc, not sr. If overshoot persists at matched cc (|Δcc|<10), Cause B → new regime-conditional sr correction.
- INSUFFICIENT until pre_frontal + sea_breeze each have 300+ rows; first real read ~2026-07-11.

### h_c1h_orthogonality.py — PROMOTE
- Two-pass over pair log; computes trend-direction axis H = |fc[L] − fc[L−6]| > per-field threshold; cross-tabs by (field × band × H × C1f × C1e).
- Result: **10 orthogonal cells / 29 judged → PROMOTE narrow scope {cc, cl, cm}.** cm ortho all 3 bands vs C1f; cl ortho all 3 bands vs C1e with up to 6.00× at 6-11h; cc ortho at 6-11h. ch ambiguous, t redundant — excluded.
- Now on 7-day narrow-promote gate: day 1/7. Earliest ship 2026-07-14. Also gated on C1 flip (Stage 4 NOT READY).
- Debug page updated: tri-column card, long-form Stage 1 bullet, rolling table row all reflect ortho passed.

## sr shortwave shadow-log first read (partial disconfirmation)

n=1,200, day 1 of v0.6.309 shadow logging. Result did NOT match "unit-mismatch collapses Lsr's regime bias everywhere" hypothesis. Direction is regime-specific:
- **nw_flow:** shortwave MAE −55% (unit fix pays off here)
- **pre_frontal, sea_breeze, unknown:** shortwave MAE *worse*; bias flips direction from direct-under (−3, −100, −275 W/m²) to shortwave-over (+12, +169, +367 W/m²)

Signals a real over-forecast in Open-Meteo's total shortwave in cloudy/marine regimes on top of the definitional gap. Prior "switch to shortwave + refit Lsr" fix chain is on hold pending Cause A (cc-miss surfacing through sr) vs Cause B (real Open-Meteo diffuse/aerosol gap) resolution. See [[sr-unit-mismatch]] updated.

## Marblehead geography note

Discussed marine-layer correction mechanism. Corrected my geographic errors twice: Wyman Cove is on the inner (NW) side of Marblehead peninsula facing Salem Harbor. Marblehead-proper is to the NE (with air-crossing-land implications); narrow N-NNE slice (~10-20° azimuth) has direct water fetch across Salem Harbor. Confirmed the marine-layer correction gate is DATA-driven not geographic (Stage 2 analysis found the [45°, 105°) × 4-9 EDT cell empirically). Not to be confused with the wind-impact exposure table used in front-end worry-index scoring — those are two separate systems.

## Related and next

- C1h now in [[project-hypothesis-backlog]] narrow-promote gate track
- sr investigation updated in [[sr-unit-mismatch]]
- Tuesday cadence codified in [[tuesday-cadence]]
- Silent-failure feedback in [[stated-intent-vs-code-behavior]]
- TODO refreshed tonight; next drift starts tomorrow
- Tomorrow (07-08): T Production convergence check + retire `*` migration language once Production window fills
- 07-10: sr clean read + Lsr skip regime re-audit + ws/wg L3 strip earliest ship + Lsr contamination suppression lifts
- 07-11: C1 Stage 4 multi-axis re-check + sr confound first real read
