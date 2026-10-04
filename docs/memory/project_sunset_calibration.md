---
name: project-sunset-calibration
description: Ground-truth sunset calibration data points for scorer validation
metadata: 
  node_type: memory
  type: project
  originSessionId: c9cc788c-7e2c-4dda-a103-6ef46064d3b8
---

## ⚠ INVALIDATED 2026-06-14 — DO NOT USE PRIOR DATA POINTS

On 2026-06-14 the sunset azimuth bug was found in `sunset_directional.py:40`. The code was sampling clouds at the wrong azimuth for the entire history below: error was 0° at equinox, growing to ~60° at solstices. For June 14: code returned 239° (WSW) when actual sunset azimuth is 303° (WNW).

**This invalidates every calibration data point below.** The cloud-cover, PW, and humidity values being compared to the user's photo evidence weren't from the patch of sky where the sun actually set. The PW haze factor shipped in v0.6.71 was tuned against this bad data; we don't yet know whether PW penalty is even directionally correct.

**The scoring algorithm geometry is fine** — clear horizon + heavy mid/high + dry air → spectacular is sound physics. The bug was strictly in which patch of sky the algorithm was being fed. Re-calibration starts with sunsets observed after v0.6.76. The PW factor was left in place but should be re-evaluated once we have 3-4 clean data points (post-fix Spectacular calls that bust, or non-Spectacular calls that come true).

The historical entries below are preserved for context but should not be used as evidence for tuning decisions.

---

## June 14, 2026 — First post-fix data point: Spectacular call, no sunset actual

**Prediction**: rawScore 87 / 100 → "Spectacular" at azimuth 303° (the fix landed earlier that day).

**Actual**: clouds to the west never cleared, remained cloudy through and past sunset window. No visible sunset.

**Inputs at 20:00 EDT (from corrected 303° sample point):**
- low cloud at 50mi: 0% (model)
- mid cloud at 25mi: 100%
- high cloud at 25mi: 94%
- PW: 29.3mm (under the 30mm penalty threshold)
- hum at 25mi: 41%

**Diagnosis (1 data point — don't tune yet):** the model's "low = 0%" assumption was wrong, OR the dense mid+high deck never thinned enough at the western horizon for the sun to underlight from below. The scorer assumed a clear-horizon-under-thick-deck geometry that the actual atmosphere didn't deliver. The Spectacular setup requires *both* clearance at the horizon AND a canvas overhead — we had the canvas without the clearance.

**Possible refinements to consider AFTER 3+ data points accumulate:**
1. Tighten "clear horizon" check beyond low_cloud_50mi=0. Could add a mid-cloud-at-50mi term — if mid at 50mi is also 100%, the sun has to punch through 50mi of altostratus to reach the horizon, not just be unobstructed at low levels.
2. The current logic assumes low_cloud forecast is reliable; this point suggests HRRR may overcall "clear" low cloud when there's actually a continuous deck masking it.

**How to apply**: this is data point #1 post-fix. The scorer overcall pattern needs 3+ data points to be confident. Do not retune from this single observation. Keep logging clean ground-truth-paired predictions until we have enough to identify a systematic bias.

---

## June 12, 2026 — [INVALID — bad azimuth] Post-v0.6.71 patch under-called by TWO tiers (predicted Good, actual Spectacular)

**Result**: Scorer's final tick predicted "Good" (rawScore 53). Actual outcome (verified by Joe's photo timeline at 20:07, 20:21, 20:26, 20:42 EDT): late-stage afterglow KEPT ESCALATING — by 20:42 (21 min after sunset) the sky was fire-red across the horizon with pink-bellied mid clouds and dramatic high cloud structure. That's solidly **Spectacular**, not Good. Scorer under-called by **two tiers**.

Without the PW penalty rawScore would have been ~80 → "Spectacular" (correct). With penalty, 53 → "Good" (two tiers too low). **The penalty as currently shipped overshoots significantly when the canvas is strong.**

**Updated read across the three data points:**
- PW 49mm (June 10): Dud — penalty would have correctly demoted Spectacular → Good
- PW 44mm (June 11): Dud — same
- PW 43mm (June 12): **Spectacular** — penalty incorrectly demoted to Good

The pattern: high PW does NOT uniformly mean dud. It means *some* dampening, but a strong canvas (high25 > 80% + clear horizon) can carry colors right through the haze. Two days were canvas-weak + hazy = dud. One day was canvas-strong + hazy = Spectacular. The single multiplicative PW factor can't distinguish those cases.

**Refinement to test (DO NOT SHIP YET):** make PW penalty *canvas-conditional*:
```
canvas_quality = clamp((high25 - 50) / 30, 0, 1) * clamp(1 - horizonLow/20, 0, 1)
pwFactor_eff = pwFactor + (1 - pwFactor) * canvas_quality
```
- Strong canvas (high25=95, horizonLow=5): canvas_quality ≈ 0.9, pwFactor_eff ≈ 0.97 (almost no penalty)
- Weak canvas (high25=30, horizonLow=40): canvas_quality = 0, pwFactor_eff = pwFactor (full penalty)
- Today's conditions (high25=94, horizonLow≈6): canvas_quality ≈ 0.97, pwFactor_eff ≈ 0.99 → rawScore stays near 80 → "Spectacular" ✓
- June 10/11 dud conditions (PW 44-49, modest canvas): canvas_quality lower, penalty still applies → "Good" ✓

**How to apply:** wait for ONE more strong-canvas-high-PW day to confirm the conditional pattern before shipping. If next miss is also "Spectacular under-called when high canvas + high PW," refinement is justified. If next high-PW day is canvas-weak and accurately predicted Good/Fair, the simple penalty is still doing its job.

**Conditions at sunset window (~20:21 EDT):**
- precip_water_mm: 43mm at 25mi (vs 49 on June 10 dud, 44 on June 11 dud)
- cloud_low at 50mi: 0% (clear horizon)
- cloud_mid at 25mi: ~26% (small but real canvas)
- cloud_high at 25mi: 95% (big high-cloud canvas)
- humidity: 56% (not dry, not blocking)
- pwFactor applied: 0.662 (34% knockdown — meaningful but not catastrophic)

**Diurnal label trajectory through the day:**
- Morning prediction: "Spectacular" raw, demoted to "Good" by v0.6.71 PW patch ✓
- 6:00pm: "Poor" (model briefly forecast 93% low cloud at 50mi at sunset hour — turned out wrong)
- 7:30pm: "Fair" (model refreshed, conditions improved)
- 7:57pm: "Good" (final refresh found the truth as sunset approached)
- 8:21pm actual: Good-to-Very-Good ✓

**Lesson — DO NOT lock the score early.** Joe and I almost shipped a "freeze at sunset-minus-60min" patch to fix the late-window bounce. Today proved that would have been wrong — the late refresh is the model finding the truth, not introducing noise. Trust the latest tick.

**PW penalty calibration confirmed at 43mm range.** Three data points now:
- PW 49mm (June 10): dud — penalty correctly demoted Spectacular → Good range (but pre-patch said Spectacular)
- PW 44mm (June 11): dud — same
- PW 43mm (June 12): Good-to-Very-Good — penalty correctly LEFT some color in (0.66 factor not 0.33)

The slope `(pwat-30)/40` at 43mm yields 0.34 knockdown = right answer at this range. Don't retune without a fourth opposing data point.

## June 10, 2026 — [INVALID — bad azimuth] "Spectacular" prediction, dud actual

**Result**: App predicted "Spectacular" in the morning forecast; actual sunset was a dud (Joe's ground truth).

**Forecast context**: Hot late-spring day, sea breeze active through afternoon (land 81.5°F / water 59.4°F, 22.1°F land–water gradient), wind SSW 7 mph. Briefing called for upper 80s today → 90 tomorrow. No precip in 48h horizon (max POP 25%).

**Why it's load-bearing**: First documented over-prediction since the v0.5.x sunset scorer launched. Pattern to investigate when next looking at the scorer: hot stagnant days with sea-breeze regime may favor haze/low-level moisture that the cloud-cover-only scorer doesn't see. Specific conditions at the 20:14 EDT sunset weren't captured at the time — if a miss repeats on a similar hot/sea-breeze day, capture full atmospheric state (PW, cloud arrays at 10/25/50mi, dew-point spread, observed_sky τ near sunset) for a real diagnosis.

**Diagnosis (captured same-day):** `precip_water_mm = 49.1` at sunset hour (20:00 EDT). That's solidly in "tropical/muggy" territory (35–50mm range washes out sunset colors via Mie scattering). Forecast PW stayed 44–49mm through the entire afternoon and tomorrow morning. The current scorer in `js/sunset.js` does NOT use PW at all — it uses `hum25` (humidity at 25mi) and only deflates above 70% via `humFactor = 1 - max(0, hum25-70)/90`. With clear horizon (low10=2%) and some mid/high cloud, the scorer pushed past 75 → "Spectacular." High PW = tropical air mass = milky/hazy sky that the scorer is blind to.

**Hypothesis (don't ship off one data point):** add a PW-based haze penalty to the scorer. Rough sketch: `pwFactor = 1 - max(0, pw_mm - 30)/40` clamped to [0.3, 1.0] — at PW=30 no penalty, PW=40 = 0.75×, PW=50 = 0.5×. Apply multiplicatively alongside `humFactor`. Would have cut today's score by ~50%, likely landing in "Fair"/"Good" range.

**How to apply**: Don't ship the PW haze fix off one data point. Wait for a second miss in similar conditions (high PW + clear horizon → over-predicted Spectacular). Two same-shape misses with the same diagnostic = real failure mode worth fixing. If a Spectacular prediction with PW < 30mm turns out a dud, the hypothesis is wrong.

## May 28, 2026 — [INVALID — bad azimuth] Post-frontal clearing sunset

**Result**: App scored "Good" — user confirmed correct.

**Conditions at sunset (20:11 EDT, azimuth 241.2° WSW):**
- 10mi cloud cover: 36% at 19:00, dropping to 0% at 20:00
- 25mi cloud cover: 0% (completely clear)
- 50mi cloud cover: 0% (completely clear)
- Post-frontal dry air advection; low cloud deck with gap at horizon, darker clouds above

**Why it lit up:** Low cloud gap at horizon allowed direct sunlight through. Dark clouds above were lit from underneath as sun set. Classic post-frontal geometry.

**Pattern to preserve:** Low local cloud cover (0–36%) dropping toward sunset + clear at 25mi+ + post-frontal dry air = reliable "Good" even when overhead clouds look threatening.
