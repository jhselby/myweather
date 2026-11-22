# Plan: the Wyman Cove Mesonet, one fixed truth, and the Model front page

Rewritten 2026-11-22 after a conversation with Joe that replaced the first draft. This is the working plan. A fresh session should be able to start from it without any other context. **Verified** = checked in code or data on 11-22. Anything not marked is a step to do, not a fact.

## 1. The goal, in one paragraph

This project is mostly for Joe. The question he wants answered is: *is my forecast for the Cove better than what a person reads on weather.gov, and is it improving?* Answering that needs one fixed, honest truth. Today the truth is partly the model (see §3), so we do not know whether we are winning: on temperature we lead weather.gov by 16% against URMA but trail by 1.5% against our stations. The pages follow from that. The **Mesonet** turns about 27 backyard stations into one honest "now at the Cove" value, says how it got there and how good that value is, and becomes the truth. The **Model** page opens with a short front section (the question, the method, the score, the trend) above the **Notebook** (today's debug page). Both are built for Joe first and made clear enough to show a curious visitor.

## 2. What Joe agreed (11-22)

1. **Two separate jobs.** The Mesonet observes; the Model forecasts. The Model may use station readings from up to the moment the forecast is issued. It never grades itself on a truth that contains the forecast.
2. **The Mesonet has a model, but no forecast in it.** Combining stations takes a statistical method (weights, trimming, per-station siting corrections, distance). That method may use only station readings and fixed facts about the stations. HRRR, NBM, ECMWF, weather.gov and URMA are **not inputs**. They appear **beside** the Mesonet value on the page as cross-checks.
3. **One number per field** is both the snapshot on the page and the grading truth. There is no second "current conditions" value.
4. **Where the stations cannot say** (thin coverage, or a field the stations do not measure), the page says so. For a field the stations do not measure, it shows another source, labelled as not from the Mesonet. It never fills in from the forecast.
5. **Pages:** `/mesonet` stands alone. `/model` = a short front section with the **Notebook** (the current debug page) underneath, on the same URL. The Notebook grades on the same fixed truth as the front section; numbers on any older truth are labelled or moved to the archive section.
6. **Order:** Mesonet and its validation → fix the truth and rescore the history → `/model` front section → retrain on the clean truth → app move and landing page last.

## 3. Facts the plan rests on (verified 11-22 unless noted)

- **Combining the stations:** `weather_collector/processors/hyperlocal.py` `build_hyperlocal_data`. It applies a per-station correction, takes a trimmed weighted mean by octant, and gets `weighted_bias` = station consensus − model.
  - `station_temp = model_t + weighted_bias`. The model term cancels, so this is the **stations-only** value: the Mesonet temperature already exists. Likewise `station_humidity`.
  - `corrected_temp = model_t + K * weighted_bias`, with K = 0.4 / 0.65 / 0.9 (`_kalman_gain`). This is the **model-contaminated** value. It becomes the pair log's `observed` for t/h/dp/ws/wg.
- **Per-station corrections:** `weather_collector/processors/station_bias.py`. Each station's offset is measured against the **leave-one-out consensus of the other stations**, split day and night, for temp, humidity and pressure. **No forecast is involved.** This was open in the first draft; it is now closed.
- **Truth columns:** the pair log has carried `observed_stations` for t/h/dp/ws/wg since 2026-11-02 18:07 (`forecast_error_log.py` ~272-281). `analysis/_truth.py` converts a row between the two truths. `analysis/truth_compare.py` builds the scorecard.
- **Station archive:** `gs://myweather-data/station_readings/YYYY-MM-DD.json` since 2026-11-08 (Tempest, with offsets). WU hourly rows are in `wu_readings_hourly/` (`scripts/wu_backfill.py`).
- **Scripts that already exist and should be reused, not rewritten:**
  - `analysis/l2_loo_score.py`: leave-one-station-out scoring on the archive.
  - `analysis/mesonet_vs_urma.py`: station groups against URMA, leave-one-day-out offsets; URMA's own error at the Cove is ~0.4-0.55 F.
  - `analysis/mesonet_bench.py`: a 6-47h benchmark on network-median truth. It notes that at 6h+ the stations are not an input to the forecast, so grading there is not circular.
  - `analysis/mesonet_cadence_replay.py`, `analysis/h_mesonet_conf.py`.
- **`mesonet.json`** (repo root) is written by `build.py` through `scripts/mesonet_state.py`. It is **static between builds**, so it is not live.
- **Live data:** `weather_data.json` on GCS (`hyperlocal`, `tempest.stations`, `current`).
- **Hosting:** GitHub Pages from `main` at wymancove.com (CNAME). A push is the deploy.
  - Assumed, verify: Pages serves `mesonet.html` at `/mesonet`.
- **Debug page:** `corrections_debug.html`, about 10,950 lines. Its front sections are `#sec-conditions`, `#sec-mesonet` (draft, in WIP 60a489d2), `#sec-front`, `#sec-whats-new` and `#sec-how`.
  - `index.html:1586` links to it, and `build.py:318` reads it.
  - `tests/test_prod_key_coverage.py` parses it.
  - `js/corrections.js:237` builds a link to it.
- **weather.gov:** gridpoint BOX/76,97 publishes `relativeHumidity`, `windGust`, `skyCover` and `quantitativePrecipitation`. We stamp only t, dp, pp, ws, wd (`forecast_snapshot.py` 52-55, 836-856).
- **Coverage:** octant counts on 11-22 were N2 NE2 E4 SE2 S3 SW2 W0 NW2. **No west stations.**
- **Wind:** backyard anemometers read 0.2-0.4x open-air wind. Wind was put on URMA truth on 11-20, with Joe's ok.

## 4. Rules for every session on this plan

- Start: `git status`, read this file, and read memory `project_11_22_session`. Run the morning digest per CLAUDE.md §0a, capped. This plan is the work item after it; record it in `analysis/runlog/selector_open_work.txt`.
- **Conversation mode:** when Joe asks a question, answer it. Do not edit.
- **Truth:** choose it by the rule in Step 3.1, set in advance. Never choose it by which result looks better.
- **Visual changes:** serve over LAN (`python3 -m http.server 8799 --bind 192.168.1.21` from the repo) and give Joe the URL **before** asking to push.
- Every shipped change gets a version bump in the `index.html` pill, a `docs/CHANGELOG.md` entry at the top, `python3 build.py` (version.json) and the `sw.js` `CACHE_VERSION`.
- Ask before every push. Collector deploys are production, so get Joe's yes for each one.
- One heavy analysis job at a time; the server is shared, with about 16 GB of RAM.
- At the end of each step, update this file: tick the step and write the result in one line under it.

## 5. Steps

### Step 0. Settle what is already committed locally
- Two commits are unpushed: `dd6a25fc` (the selector_open_work line) and `60a489d2` (WIP v0.7.129).
  - 60a489d2 contains: the debug-page staleness sweep, the draft `#sec-mesonet` section, a scorecard with the vs-raw-NBM column removed, and the first draft of this plan.
- Its scorecard still uses the old truth mix (t on URMA, the rest on stations). Step 3 replaces that.
- **Action:** show Joe the LAN preview. If he approves, push both commits as they are; the staleness fixes are worth having now. On the page, label the scorecard truth as "interim, being replaced". Do not polish the draft Mesonet section; Step 2 supersedes it.
- [x] done 11-22: pushed 39da0c82..91b06010 on Joe's yes.

### Step 1. Validate the Mesonet (read-only; nothing served changes)
Output: `analysis/mesonet_validation.py`, writing `analysis/mesonet_validation.json`. Reuse the scripts in §3.

1.1 **Define the Mesonet value for each field** in one table, from code:
- t: `station_temp`
- h: `station_humidity`
- dp: from station t and h (verify how it is computed today)
- pr: station pressure (verify the field)
- ws / wg: stations' wind, marked weak
- rain: verify whether Tempest rain is logged
- sr: verify whether Tempest solar radiation is logged
- Fields the stations do not measure, with the source the page will show for each: cc (URMA / KBVY METAR), visibility and fog (KBVY), wd (verify)

1.2 **Held-out accuracy:** for each tick and station, estimate that station from the others (the `l2_loo_score.py` method, all stations, no forecast). Report MAE per field, split day / night and by octant. This is the "how well do the stations agree" number. It shows precision, not accuracy.

1.3 **Independent cross-checks:** Mesonet against URMA (`mesonet_vs_urma.py`), against KBVY, and buoy 44013 water/air where relevant. Report the mean difference (bias) and the MAE, by hour of day. The question is whether the network as a whole runs warm or cold, which held-out stations cannot reveal because they share sensor types.

1.4 **Coverage:** for each tick, the number of stations and octants. Set the "low coverage" threshold from 1.2: the station count below which the held-out error jumps.

1.5 **The 0.4 gain question (record only):** does `station_temp` or `corrected_temp` track the held-out stations and URMA better? This informs Step 4; do not change K here.

1.6 Write the window on every number ("11-08 to <date>, autumn only").

**Decision at the end of Step 1:** for each field, does the Mesonet qualify as truth? It qualifies if the held-out MAE is small relative to forecast errors and the network bias against URMA/KBVY is small. If t or h does not qualify, stop and recalibrate before Step 3. Write the verdict per field here.

**Rule, fixed 11-22 before any Step 1 score was computed** (thresholds from `analysis/output/truth_compare.json`, 2-47h, 11-02..11-22):
- A. Precision: held-out (leave-one-station-out) MAE ≤ 0.5 × served forecast MAE on station truth. t ≤ 1.18 F, h ≤ 3.0 %, dp ≤ 0.81 F.
- B. Accuracy: |mean(Mesonet − URMA)| over the window ≤ the served forecast's lead over the bar, in the field's units, so a truth bias alone cannot flip a verdict. t ≤ 0.36 F (weather.gov 2.28 − served 1.91, URMA), dp ≤ 0.12 F (1.87 − 1.75, URMA), h ≤ 3.6 % (vs raw NBM, no weather.gov h yet; URMA h from TMP+DPT).
- Both A and B must pass. KBVY and the hour-of-day bias are reported, not gated (KBVY sits 6 mi inland).
- ws / wg: reported only; they stay on URMA (11-20 decision, §3.1). pr, rain, sr: reported only (not on the scorecard as station-truth fields).
- [x] measured 11-22 (`analysis/mesonet_validation.py` → `analysis/mesonet_validation.json`; 11-08..11-22, 2,013 ticks, 336 hours, 15-17 Tempest stations every tick):
  - **t: does not qualify.** Held-out 0.96 F (passes A). Mesonet − URMA +0.61 F (fails B, bar 0.36): +1.0..+1.3 F every night hour, ~0 midday. vs KBVY +4 F at night, ~0 midday (KBVY is an inland airport, so it is colder at night).
  - **h: qualifies.** Held-out 2.7 % (A ≤ 3.0); Mesonet − URMA −3.4 % (B ≤ 3.6, narrow).
  - **dp: does not qualify.** Held-out 0.84 F (A ≤ 0.81, narrow fail); Mesonet − URMA −0.72 F, drier by ~1.2 F in daytime (B ≤ 0.12).
  - pr: held-out 0.01 inHg, KBVY bias 0.00. ws / wg: 4 / 8 mph below URMA (sheltered, as known; stay on URMA). sr: held-out 50 W/m² daytime.
  - Coverage: never below 15 stations in the window, so the low-coverage threshold cannot be set from data (held-out 1.10 F at 15 vs 0.95 F at 16). Worst octant S (1.53 F); still no west stations.
  - 1.5 (record only): corrected_temp tracks URMA better than station_temp (0.74 vs 0.82 F MAE), but corrected_temp contains the model and URMA is model-based, so this is not independent.
  - Found and fixed: `l2_loo_score.nets()` (also used by `mesonet_bench.py`) added `off_t` instead of subtracting it; the earlier LOO / bench numbers were on wrong-sign offsets (~0.17 F level, wider spread).
  - Open question before Step 3: is the night +1 F real Cove warmth (water, houses) that URMA's 2.5 km grid smooths, or a shared sensor/siting warm bias the held-out test cannot see?
  - Follow-up 11-22 (raw readings, 11-08..11-22): 13 of 17 stations run warmer than URMA at night (−1.2..+2.6 F); the warmest are the most water-surrounded (Marblehead Neck, Neptune Rd, Front St), the coldest the most inland (Manton Rd). Joe: the Cove sits below "the Cliffs"; **Neptune Rd (0.4 mi, waterfront) is on his side, Baldwin Rd is not.** Neptune Rd raw − Mesonet: night +0.7 F, midday −1.4 F; − URMA: +1.7 / −1.6 F. A damped daily swing (waterfront), no cold pooling. Joe's own station KMAMARBL124 has 4 archived hours (WU calls off since 11-08).

1.7 **Cove adjustment (agreed with Joe 11-22): shadow only.** The Mesonet averages Marblehead, and each station's offset aligns it to that average, so the Cove's own pattern is removed. Candidate: Cove value = Mesonet + adjustment by ET hour of day, measured as Neptune Rd raw − Mesonet on prior days (stations only, no forecast). Score it leave-one-day-out against Neptune Rd. Decide only after Joe's station or more weeks confirm it (one sensor, two weeks, one season). t stays on URMA, labelled, until then.
- [x] shadow measured 11-22 (`cove_adjustment_shadow` in mesonet_validation.json; walk-forward, 12 scored days, 278 hours): Mesonet vs Neptune Rd MAE 1.07 F → adjusted 0.74 F. Night bias −0.66 → −0.13 F, midday +1.40 → +0.09 F. Not served, not truth. Re-read with more weeks and with Joe's station if it comes back.

### Step 2. The `/mesonet` page
- New file `mesonet.html` (verify the `/mesonet` URL on Pages after the first push). Standalone: its own styles and no app shell, matching the theme tokens.
- **Top:** a map of the stations (re-use the debug page front map code from v0.7.113) and the current Mesonet value per field, with the time.
- **Per field:** the Mesonet value, then **beside it** URMA, KBVY, the buoy (where relevant), and what HRRR/NBM said for this hour. Each is labelled as a cross-check, not an input.
- **"How we got this":**
  - stations used and trimmed
  - each station's correction (day and night) and weight
  - a short paragraph on the method: per-station offset against the other stations, a trimmed weighted mean by octant, no forecast
- **"How good is it":** the numbers from Step 1 with their window.
- **Honesty markers:** wind is marked weak (show URMA/KBVY wind prominently). Fields the stations do not measure are labelled with their source. Low coverage gets a visible flag.
- **Data:** live values from `weather_data.json` on GCS. Validation scores from a file the page can fetch. Start with `analysis/mesonet_validation.json` copied to the repo root by `build.py`, like `mesonet.json`. Move the scoring into the publisher (cloud) once it is stable, so the page stays current without a build.
- Remove `#sec-mesonet` from the debug page and replace it with a one-line link to `/mesonet`.
- Link `/mesonet` from the app's footer next to the debug link.
- LAN preview, then ask to push. Version bump.
- [ ] done

### Step 3. Fix the truth once and rescore the history
3.1 **The truth rule, set before looking at scores:**
- A field whose Mesonet value qualified in Step 1 is graded on the Mesonet: `observed_stations`.
- Wind (ws/wg) is graded on URMA (the 11-20 decision stands; the stations are too sheltered).
- A field the stations do not measure keeps its current named truth (cc on URMA; rain on hour totals; sr and wd as today).
- Each scorecard row names its truth. Write the final table here.

3.2 **Circularity at short leads:** at 0-5h the forecast uses current station readings (L2). Grade those leads leave-one-station-out (the `l2_loo_score.py` method). At 6-47h, grade directly on the Mesonet; stations are not an input there (`mesonet_bench.py` note).

3.3 Change `analysis/truth_compare.py` so the scorecard (`#sec-front` and the digest) uses 3.1 and 3.2. Also the daily history: `truth_compare_daily_history.json` and the publisher.

3.4 **Rescore the history:** rebuild the daily history on the new truth. Station-truth fields start 2026-11-02, the first `observed_stations` row; label the chart's start. Wind and cloud keep URMA history back to 08-25.

3.5 **Make the Notebook consistent:**
- Every section on the debug page that grades on `observed` either switches to the fixed truth or is labelled "old truth (model-blended)".
- Archive it if it no longer matters.
- Include the sentries that fire on the old truth (the h/dp FRESH FIRE noise on 11-22).

3.6 **weather.gov stamp for h / wg / cc / pa:**
- Add the four fields to `forecast_snapshot.py` (52-55, 836-856) and to the pair log as `*_nws`.
- **Collector deploy: ask Joe first.**
- After about 14 days of rows, the scorecard compares those four against weather.gov instead of NBM. Until then, label them "vs NBM (weather.gov not yet recorded)".
- Do this as early as Joe approves, because the clock only starts at deploy.
- 3.6 DONE 11-22 (v0.7.130): deployed 18:14Z; the 13:18 tick stamped h/wg/cc/pa_nws on 48/48 hours. QPF is spread evenly over its validTime block (mm → in/h). ~14 days of rows ≈ 12-06.
- [ ] done

### Step 4. `/model` front section and the Notebook
- Rename `corrections_debug.html` to `model.html`. Leave `corrections_debug.html` as a small redirect page (meta refresh plus a link) so old bookmarks work. Update the four references in §3 and the tests.
- **Front section** (cut down from `#sec-front`): exactly four things:
  1. **The question:** "Is this forecast for Wyman Cove better than weather.gov?"
  2. **The method in one picture:** the forecasts (HRRR / NBM / ECMWF) → adjustments (L2-L4, blends) → the selector picks a source per field and lead → the served forecast; the Mesonet provides the truth.
  3. **The score:** one row per field, with our lead over weather.gov (or NBM where weather.gov is not yet recorded), the truth named and the window.
  4. **The trend:** the Stack health chart on the fixed truth.
- Below it, a heading **"Notebook"**, then everything else as it is. L2 is labelled "the link from the Mesonet".
- Version bump. LAN preview, then ask to push.
- [ ] done

### Step 5. Retrain on the clean truth (changes the served forecast)
- Refit L2 and the blends (t_urmab, ws_urmab, wg_urmab and the rest) and the selector against the Step 3 truth via `analysis/_truth.py`. Self-refitting tables must refit in the cloud refitter, not the digest.
- Also test the K question from 1.5 here, through `analysis/ship_rule.py` on holdout days.
- Ship each change only if it passes `ship_rule`. One field at a time; shadow first where the stack supports it.
- Keep the dates already scheduled (ws/wg serve decision ~11-27; t_urmab ship_rule). If they fall before Step 3 is done, decide them on the current truth and say so.
- [ ] done

### Step 6. Move the app to `/app` and add a landing page (last)
- Not scoped yet. It touches paths, the service-worker scope, `manifest.json`, `build.py` and the PWA install. Joe accepts re-adding the home-screen icon.
- The landing page `/` gets three links: app, mesonet, model.
- Scope it in its own session before touching any file.
- [ ] done

### Step 7. Event scoring (separate track, not started)
- Fog, sea breeze, and rain vs snow, scored as hits, misses and false alarms against KBVY/METAR events.
- [ ] not started

## 6. What would change this plan
- Step 1 finds a Mesonet field biased against URMA/KBVY by more than the forecast's lead over weather.gov: recalibrate that field before it becomes truth.
- Step 1 finds the held-out error too large to grade with (above roughly half the forecast MAE at 6h): that field keeps its URMA truth, labelled.
- Joe changes any agreed item in §2: update §2 first, then the steps.
