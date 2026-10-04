---
name: project-l6-l2-double-counting-hypothesis
description: "2026-06-29 — L6 production audit shows 5 consecutive HOLD verdicts (improvement_pct -23% to -74%, n=13k) despite the lookup-table direction being correct. ORIGINAL hypothesis (L2 Kalman blend already pulls cove temp → L6 double-counts) REJECTED 2026-06-30 by `analysis/l6_l2_double_counting.py`. Real cause: L1 itself is systematically cold-biased ~2.25°F on cove rows; L2 barely changes that (cover% +3.7); L6's COOLING branch then pours cooling on an already-cold baseline. Cooling Δs ≥ 2°F take baseline ME -2.93 → -6.07 (MAE doubles). Warming Δs are neutral-to-helpful."
metadata: 
  node_type: memory
  type: project
  originSessionId: 19e46001-b953-40c1-a522-231781ec1562
---

## 2026-06-30 UPDATE — original hypothesis rejected

Ran `analysis/l6_l2_double_counting.py` on 19,975 t pairs where L6 fired. The double-counting hypothesis below assumed L2's mesonet blend was doing most of the cove pull, which would make L6's additional Δ an over-correction. **Data says L2 only erases 3.7% of L1's MAE on cove-temperature rows.** L2 barely touches the bias. So L6 isn't double-counting anything — L1 is just cold (ME -2.27°F), L2 stays cold (ME -2.09°F), and L6 then makes it worse asymmetrically depending on the sign of the applied Δ.

The clean finding is in section [C], stratifying by signed applied Δ = forecast_l6 − forecast_l2:

| applied Δ | n | ME L2 | ME L6 | MAE L2 | MAE L6 | L6 marginal |
|---|---:|---:|---:|---:|---:|---:|
| Δ ≤ −2.0 (large cool) | 3,284 | −2.93 | **−6.07** | 3.52 | **6.16** | **−74.9 %** |
| −2.0 < Δ ≤ −0.5 (mid cool) | 3,528 | −2.93 | −4.34 | 3.55 | 4.61 | −29.9 % |
| −0.5 < Δ < +0.5 (small)  | 9,114 | −1.74 | −1.61 | 2.20 | 2.13 | +3.3 % |
| +0.5 ≤ Δ < +2.0 (mid warm) | 2,434 | −1.85 | −0.99 | 2.60 | 2.34 | **+10.1 %** |
| Δ ≥ +2.0 (large warm)  | 1,615 | −0.87 | +1.13 | 2.54 | 2.59 | −2.0 % |

All the damage is on the cooling side. The cove_correction.py cooling branch is the `sb_active=False` branch with the hour-of-day-modulated table (HOUR_MOD_OFFSHORE) — negative Δ°F values 09–16 EDT under offshore flow. Applied to a baseline that's already cold by 2.9°F, it doubles the error.

Sanity check (section [D]): L2 == L4 for every one of the 19,975 t pairs (exact match), confirming the production audit's "L4 vs L4+L6" comparison IS a "L2 vs L2+L6" comparison for temperature. No confusion in the audit framing.

## Why the original hypothesis was wrong

The reasoning was: "L2 uses many WU stations near the cove, so it must already pull toward cove obs." Two problems with that reasoning, both now clear from the data:
1. **L2's Kalman blend is conservative** — it adds station observations as a small posterior correction to the model prior, not a large pull. Headline MAE improvement L1→L2 is only ~3.7% on cove rows. That's the actual measured size of L2's correction, not the imagined "most of the work."
2. **L1's cold bias on cove rows is structural, not random.** Mean signed error is −2.25°F across 16k+ rows. HRRR underforecasts cove temperature systematically — likely a microclimate effect L1 has no representation of. L2 doesn't fix structural model bias; that's what L6 was supposed to do.

## What L6 should be doing

L6's intent — "apply a cove-microclimate Δ on top of the baseline" — is still right. The lookup table just has the wrong sign relationship to the baseline. The (waterfront_obs − inland_obs) gradient says "cove is cooler than inland 09–16 EDT under offshore flow." But L1's baseline isn't at "inland temperature" — it's already 2–3°F colder than cove truth. So the gradient table's offshore cooling, applied as an additive Δ, walks away from truth.

## Two viable fixes (kill vs surgical)

**Option A — kill the cooling branch only.** The warming branch (sb_active=True, sea-breeze positive Δ) is at worst neutral. The cooling branch (sb_active=False, hour-modulated offshore cooling) is causing all the damage. Disabling HOUR_MOD_OFFSHORE (or zeroing it out) keeps the productive part of L6 and stops the bleeding immediately. Tiny code change in `cove_correction.py`.

**Option B — refit the entire lookup against (cove_truth − L2_forecast_at_cove) instead of (waterfront_obs − inland_obs).** Step 2 of the original TODO. Larger change, requires regenerating the table from pair-log history. The right long-term answer.

A is the right Stage 1 action this week; B is the right Stage 4 plan. Don't lose this distinction.

## Status

- Diagnostic complete. Original hypothesis rejected. New diagnosis confirmed.
- L6 still HELD not disabled, but moved from "investigating" to "kill cooling branch on next ship day."
- Verdict reads in `l6_gate_history.json` will continue to be HOLD until either A or B ships — those reads are now expected to be HOLD, not informative.

## Original hypothesis (now superseded) — kept below for context

## The puzzle

## The puzzle

Two L6 audits are reporting opposite-looking things, and reconciling them is the open question.

**r5_cove_analysis (the gradient audit):** verdict went SHIP × 7 → HOLD × 2 over 2026-06-22 through 2026-06-29. Today's verdict (2026-06-29 morning digest):
- Sea-breeze warming regime: PASS, mean Δ = +1.69°F, n=353
- Morning offshore cooling regime: FAIL, mean Δ = -0.67°F (threshold < -1.0°F), n=285

This audit reads the `cove_gradient_log.json` and asks "does the spatial gradient between cove and inland stations exist?" The answer is yes for sea-breeze, weak for morning offshore.

**L6 production audit (the paired-MAE audit, added v0.6.240):** 5 consecutive HOLD verdicts since 2026-06-27, improvement_pct ranging -23.73% to -73.76%, n_pairs growing 1,453 → 13,136. Today's two Fitter cycles (2026-06-29T03:08 and 15:08): -23.73% and -29.52%.

This audit compares paired |error_l4| vs |error_l6| on the t card. For temperature, L3 and L4 are off (T not in L3_FIELDS or L4_FIELDS), so `error_l4` is actually the error of the L2-only forecast. The audit is honest: **L2+L6 has worse MAE than L2 alone by a wide margin across all regimes that have fired.**

## The reframe (caught 2026-06-29 by Joe pushing back)

I initially recommended disabling L6 based on the production audit alone. Joe pushed back with two correct observations:
1. L4 is off for T, so the audit baseline is L2, not L4.
2. The lookup table direction is correct — under SE wind / sb_active / hour 16, the table says +2.0°F (matches the r5_cove_analysis sea-breeze gradient of +1.69°F).

So the puzzle isn't "L6 is firing the wrong direction." The puzzle is "L6 is firing the right direction and still making things worse."

## The hypothesis (untested, but the load-bearing explanation)

**L2 already does most of the cove pulling.** L2's Kalman blend uses ~31 WU stations + Tempest + KBOS + KBVY. Some of those stations are physically near the cove (Tempest Willow Rd, Tempest Neptune Rd, KMAMARBL cluster). The mesonet aggregate already pulls the forecast toward cove-observed temperatures.

If L2 is already doing 80%+ of the cove correction, then L6's full-gradient +2.0°F at SE/sb-active is ADDED on top of a forecast L2 has already pulled warm. Double-counting. The applied L6 Δ should be **(cove-true gradient) − (what L2 was already going to do)**, not the raw cove-true gradient.

This would explain:
- The cove gradient is real (r5_cove_analysis sees it in the per-station log).
- L6's direction is right (matches the gradient).
- L6 still makes things worse (L2 was already getting most of the benefit).

## The likely root cause

The L6 lookup table was computed off `cove_gradient_log.json`, which is the **observed** delta between waterfront and inland stations. It does NOT account for what L2's Kalman blend already does with that information.

If the lookup table was built as "waterfront obs - inland obs," it captures the FULL gradient. But L2 already moves the forecast partway across that gradient (toward whichever direction has more authoritative stations near the cove). L6 then adds the full gradient again. Hence double-counting.

The fix shape, if the hypothesis holds: **rebuild the lookup table against the L2-corrected forecast, not against raw L1.** The Δ in the table should be (cove obs - L2 forecast at the cove), not (cove obs - inland obs).

## Status: HELD, not disabled

Even though the production audit is screaming, we're not disabling L6 today because:
1. The directional signal is right.
2. The diagnosis above is a hypothesis, not a confirmed root cause.
3. Disabling pre-emptively would lose the existing infrastructure when a refit (not a kill) is likely the right fix.

## Investigation TODO (post-2026-06-30)

1. **Measure L2's cove contribution.** Pick a sample of recent pair rows where L6 fired. Compare `temperature_l1` (raw HRRR) vs `temperature_l2` (post-L2) vs the observed truth. If L2's MAE on cove-observed truth is much smaller than L1's, L2 is doing most of the cove work — confirms the hypothesis.
2. **Rebuild the L6 lookup table off post-L2 forecasts.** Treat `cove_gradient_log.json` only as the ground-truth side; pair each entry with the L2 forecast at that same time and recompute the Δ table as (truth - L2_fc) stratified by regime.
3. **Re-run the production audit** with the refit table. If improvement_pct flips positive, the hypothesis was right and L6 ships with the new table. If it stays negative, the issue is something else and disabling becomes the right move.
4. **As a side check, verify how `cove_gradient_log.json` is computed today.** If it's currently (waterfront_obs - inland_obs), that's the bug — should be (waterfront_obs - L2_at_waterfront).

## What's NOT broken

- L2 is doing its job.
- The cove gradient signal exists and matches physical intuition (peninsula-lee heating under SE flow; marine cooling under morning offshore).
- The L6 production audit infrastructure (`l6_gate_history.json`, the v0.6.240 paired-MAE audit) is working exactly as designed — surfacing a real problem that wouldn't have shown up in the gradient audit alone.

## Lesson for future specialists

When building a field-specific specialist that corrects toward an observed truth, the lookup table must be computed against the **upstream layer's output**, not the raw model. Otherwise the specialist double-counts whatever the upstream layer already does. Codify this in the implementation pattern when the specialists refactor lands.

Related: [[project-l6-microclimate-correction]] (architecture), [[project-correction-stack]] (L2 mesonet blend description), [[project-applicability-map-design]] (the refactor that will document layer ordering + interactions cleanly), [[feedback-debug-page-canon]].

## 2026-07-01 UPDATE — warming branch may itself be net-negative

First real per-row Production data (from applied-layer stamping shipped v0.6.269) shows T's L6 warming branch is also net-negative on the ~30% of rows it fires. See [[project-l6-warming-branch-watch]] for the numbers and the 2026-07-08 watch window. The 06-30 fix (kill cooling branch, keep warming) may only be Fix A of two — Fix B (refit lookup against L2-corrected baseline) may be required for the remaining branch too.

The lesson from this document ("build the lookup against the upstream layer's output, not the raw model") applies equally to the warming branch. If the 07-08 read confirms, the whole L6 lookup needs to be refit against L2 baseline, both branches. Not a hypothetical anymore.
