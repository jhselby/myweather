# Plan: split the Wyman Cove Mesonet from the Model, and grade on one honest truth

Written 2026-11-22 after a long design discussion with Joe. Nothing here is built except the first draft of a Mesonet section on the debug page (uncommitted, v0.7.129). Claims are marked **verified** (checked this session against live data or code) or **assumed**.

## 1. What is wrong with the presentation today

1. **One page does two jobs.** `corrections_debug.html` (about 10,950 lines) mixes observation (the station network, L2, current conditions, the "observed" truth) with prediction (L1 to Lc, the selector, the scorecard). A reader cannot tell what is measured and what is predicted.
2. **The scorecard grades rows on different truths**, so rows cannot be compared, and the truth moves the answer a lot (**verified**, truth_compare 11-22, 2-47 h):
   - temperature vs weather.gov: -1.5% on our stations, +16% on URMA
   - dew point vs weather.gov: +22% on stations, +6% to +9% on URMA
   - gusts vs raw NBM: +25% on stations, -21% on URMA
   - The swing is larger than most gains we work on.
3. **The truth is partly the model.** The logged "observed" is the stations pulled toward the model (gain 0.4 / 0.65 / 0.9; 40 to 90% station). Grading a forecast against it flatters the model, and training on it passed the model's cold bias down (served t ran 2-3 F cold until t_urmab). The station-only truth (`observed_stations`, gain 1) has been logged since 11-02 but is not the main target. (**verified** in the 11-02 audit notes; not re-read in code this session.)
4. **The bar is misdescribed.** The page says weather.gov "does not carry" humidity, gusts, cloud cover and rain amount. It does publish them (**verified** live, gridpoint BOX/76,97: `relativeHumidity`, `windGust`, `skyCover`, `quantitativePrecipitation`). Our collector stamps only t, dp, pp, ws, wd (`forecast_snapshot.py` 52-55, 836-856). Four rows are therefore compared to NBM, not to what a person reads. Sunshine is not on the feed.
5. **The scorecard shows more than the question needs.** The question is: how does our forecast compare with one other forecast, against one stated truth. It carried a second comparison (vs raw NBM), bars, prose notes and invented truth labels.
6. **Nothing says how good the observation layer is.** No held-out error, no uncertainty, and I do not know what the per-station offsets were fitted against. Live example (**verified**): the mesonet temperature is 54.5, the stations read 56.3, the model says 53.3, and the blend takes 40% of the 3.0 degree gap.
7. **Local events are not scored as events.** Fog, sea breeze, rain vs snow and wet bulb are not on the scorecard. Average error over all hours hides them.

## 2. Target

- **Two modules with one interface.** The **Mesonet** estimates conditions at the Cove now (stations, with a model prior where stations are thin) and reports how good that is. The **Model** predicts the future from it. The Model never feeds back into the Mesonet.
- **Grading truth** = the station-only estimate, with no model in it, labelled per row. URMA, KBVY and the buoy are cross-checks, not inputs. Fields with no station truth (sunshine, rain, cloud layers, wind direction) stay on their own labelled truth.
- **Scorecard** = one number per field: our lead over the comparison, the comparison named, the truth named. Comparison = weather.gov wherever we stamp it.
- **Pages** (wymancove.com): `/` landing with three links; `/app`; `/mesonet`; `/model` (the current debug page). The old debug URL redirects to `/model`. L2 is labelled on `/model` as the link from the Mesonet.

## 3. Work, in order

| # | Phase | Changes served forecast? | Notes |
|---|---|---|---|
| 0 | Settle and commit the v0.7.129 debug sweep; LAN preview first, then ask to push | No | Needs Joe's call on the scorecard truth per row |
| 1 | `/mesonet` page, grown from the section already drafted: now vs stations vs model, per-field source, station health, a short "how it is built" | No | Same live feed, no collector change |
| 2 | Validate the Mesonet (read-only): fixed held-out stations, leave-one-out error, comparison with KBVY / URMA / buoy 44013, find what the offsets were fitted against, check whether the Tempest history API gives past data | No | Fills the "How good is it" box |
| 3 | Scorecard truth rule and one-number table; stamp weather.gov h / wg / cc / pa in the collector | No (additive stamp) | Collector deploy is production; about 2 weeks of rows before those four rows can use the real bar |
| 4 | Rename the debug page to `/model`, label L2 as the link, redirect the old URL | No | Digest and sentries unchanged |
| 5 | Retrain L2 and the blends on the clean truth | **Yes** | Only through `ship_rule` on holdout days |
| 6 | Move the app to `/app`, add the landing page | No | Joe accepts re-adding the home-screen icon. Touches paths, sw scope, manifest, build.py; not yet scoped |
| 7 | Separate track: score events (fog, sea breeze, rain vs snow) as hits and misses | No | Not started |

## 4. Fresh analysis: are we looking at this correctly?

This section tests the plan's own assumptions. It is deliberately adversarial.

**A. "Station-only observation is the right truth."** Partly. For a product about one spot, a local observation is the right target. But:
- Weather.gov and NBM predict a 2.5 km cell; a point truth scores them on sub-grid variability they were never trying to predict. Our edge partly measures "the Cove differs from the cell". That is the point of the product, but it should be said and not presented as pure skill.
- Sensor bias is unknown (consumer sensors, backyard exposure). Station agreement shows consistency, not accuracy. Wind is the worst case (stations read 0.2 to 0.4x of open-air wind; one waterfront anemometer, correlation 0.35 with URMA wind). **Wind likely needs a different truth.**
- Only about two weeks of per-station history exist (**verified**: archive since 11-08), one autumn slice. Any "validated" claim must carry its window.

**B. "The Mesonet is independent of the Model."** Mostly, but:
- The Mesonet uses a model prior, and L2 feeds the forecast. Independence holds only if grading uses stations that never feed the estimate or L2.
- Spatial coverage is uneven (**verified**: octant counts N2 NE2 E4 SE2 S3 SW2 W0 NW2). Holding stations out costs coverage, and the west octant already has none.

**C. "The Kalman blend is right for current conditions."** Standard method, but the live numbers suggest it may under-trust the stations. A gain of 0.4 with a station spread of only 0.9 F looks low when 17 of 19 stations agree. **Hypothesis, untested:** the fixed gain is too conservative for the nowcast. Test on held-out stations before changing anything.

**D. "One truth for the whole scorecard."** Not achievable. Sunshine, rain, cloud layers and wind direction have no station truth. The honest version is one stated truth per row, with one rule for choosing it made in advance. Any rule keyed to the score, flattering or not, is cherry-picking.

**E. "The page is the problem."** Only partly. The restructure makes the logic clear, but the substantive fixes are (i) stop grading and training on a model-contaminated truth, (ii) compare to the real bar. A new page does not improve any forecast, and CLAUDE.md puts selector work first. Phase 5 is where forecast gains could come from; the rest is measurement and clarity, and should be time-boxed.

**F. "A fused URMA and stations analysis would be better."** Unproven. The two agree to about 0.4 to 0.55 F on temperature. Fusion also imports URMA's tie to NBM. Keep it as a later option, only if stations-only proves too noisy.

**G. Calibrating my own reliability.** In this session I repeated an unchecked claim (weather.gov "does not carry"), flip-flopped on which truth was fairer, and shipped a confusing second column. Treat unverified items above as open until checked.

**What would change this plan:** if the held-out test shows the stations-only estimate tracks KBVY / URMA poorly, phase 3 pauses and calibration comes first. If the offsets turn out to be fitted against URMA or the model, the "independent truth" claim needs rewording.

## 5. Decisions needed from Joe

1. Approve the target and the phase order.
2. The truth rule for the scorecard, set once (stations-only where it exists, labelled).
3. Go-ahead for the collector stamp of weather.gov h / wg / cc / pa (production deploy).
4. Wind: accept a separate truth for wind and gusts?
5. Whether to hold phase 6 (app move) until the rest is done.
