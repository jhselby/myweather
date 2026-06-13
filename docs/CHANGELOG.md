# v0.6.0 — Decay-correction milestone

## v0.6.74 • June 13, 2026
- **Frontal-passage detector + card.** Names the cause when the weather changes. New `frontal_log.py` captures per-tick Tempest obs (T, Td, P, wind) at the cove; new `frontal_detection.py` reads a 90-min rolling window each tick and classifies cold-front / warm-front / sea-breeze-front passages from three signals (dewpoint drop >8°F, wind direction shift >60°, pressure inflection). Requires 2-of-3 to declare a passage. Surfaces in three places: a hidden-when-quiet card (col-6) showing compact "Front Passing" or "Front Passed at 11:42 PM last night" with dewpoint Δ and wind shift; a line injected into the Gemini briefing prompt so morning copy can say "a cold front cleared things out overnight" instead of just listing new numbers; events log retained 14 days for the debug page (next slot). Card hides entirely when no passage detected (95% of the time). First useful read after the next real front passes.

## v0.6.73 • June 13, 2026
- **R5 reframed on the debug page after Joe pointed out the geography.** Original hypothesis ("waterfront cools during sea breeze") was backwards for this specific cove — Wyman Cove sits in the lee of the Marblehead peninsula on the dominant S/SE/SW sea breeze, so marine air crosses ~2 miles of sun-heated land before reaching the waterfront stations and arrives warmer than inland. Day-1 data (104 ticks) confirms: cove runs +3.4°F (S), +3.7°F (SE), +3.8°F (SW) warmer than inland under active sea breeze, flat under N/NE/E (wind not crossing peninsula). Diurnal curve under active sea breeze peaks at +5.6°F at 12:00 EDT and decays to −0.2°F by 19:00 — tracks solar surface flux. Debug page updated with reframed hypothesis, day-1 table, decision rule shifted from "land-water gap regression" to "wind-octant + hour-of-day conditional correction." Still holding for 7-day confirmation before shipping.

## v0.6.72 • June 12, 2026
- **Two new active hypotheses on the debug page + the loggers that feed them.** R4 (HRRR vs GFS spread as confidence signal): new `gfs_l1_log.json` captures raw GFS values per tick for the 0-48h window, joinable against HRRR L1 already in `forecast_log.json`. Hypothesis is that `|HRRR − GFS|` per hour predicts actual error magnitude — if it does, the spread becomes a free uncertainty number to feed Gemini hedge language and widen displayed intervals. R5 (cove gradient): new `cove_gradient_log.json` captures waterfront Tempest median (Willow, Neptune Rd), inland Tempest median (18 stations), ambient T, wind dir/speed, salem_water_temp_f, buoy water, and sb_active per tick. Hypothesis is that `delta_wf_inland = f(land_water_gap)` stratified by sea-breeze state. First meaningful read on both: ~2026-06-19 (7 days of accumulated ticks). Per the debug-UI stability rule, the section shows "collecting data" placeholders only — charts go in if and only if the regression confirms signal.

## v0.6.71 • June 12, 2026
- **Sunset scorer now penalizes high precipitable water — kills the "every morning Spectacular, every evening dud" failure mode.** Two confirming data points: June 10 (PW 49.1mm) and June 12 (PW 43.9mm) both predicted Spectacular by morning, both were duds. Mechanism: high column moisture washes out color regardless of how "clear" the sky reads to the transmissivity calc — sky stays milky-blue, no orange. Collector: added `precipitable_water` to the directional-cloud Open-Meteo fetch, exposed as `precip_water_mm` in each cloud array of `sunset_directional`. Frontend: scorer now averages PW over the sunset window the same way it averages cloud/humidity, applies a multiplicative `pwFactor = 1 − clamp((PW − 30) / 40, 0, 0.8)` — no penalty under 30mm, −35% at 44mm, capped at −80% by 70mm — and a hard label ceiling so muggy days can't get above Very Good (no Spectacular above 35mm PW, no Very Good above 50mm PW). Belt and suspenders. Holding the rule: ship after two consecutive misses with matching signature, not one.

## v0.6.70 • June 11, 2026
- **Thunderstorm risk now keys off the daytime CAPE peak, not the current value — Gemini stops missing pulse-storm setups.** Investigating a textbook NE pulse setup today (NWS "slight chance thunderstorms" 6pm–11pm, Pirate Weather CAPE peaking ~1,170 J/kg midday): the morning briefing was silent on storm risk. Root cause in `briefing_ai.py:283`: the gate is `severity == "watch" and cape_label not in ("", "Weak")`, but `cape_label` was computed off `cape_current` only. Current CAPE at 8:47am was 601 J/kg → "Weak" → line suppressed, even though peak was Moderate. (1) Added `cape_peak_label = _cape_label(cape_peak_value)` to `derived.thunderstorm` so the daytime peak gets a label of its own. (2) Expanded the "watch" severity trigger to also fire when peak ≥ 1000 J/kg even if current is below the 500 threshold — otherwise a hot afternoon setup reads as "clear" at sunrise. (3) Switched Gemini's prompt gate, the fallback briefing (`briefing.js:871`), the t-storm tile's "Risk Level" badge, and the expanded card's "Risk Level" row to use `cape_peak_label` (falling back to `cape_label` for old payloads). The CAPE-value row still shows current. Kept the "do NOT overstate, mention only briefly" hedge so Gemini doesn't over-correct into hype.

## v0.6.69 • June 11, 2026
- **GCS payloads now gzipped + compact JSON — ~85% smaller on the wire.** Investigating Joe's 15-second iPhone load this morning: response headers on `weather_data.json` showed `x-goog-stored-content-encoding: identity` with `content-length: 420872`. We were serving the main payload uncompressed every fetch — 420KB on cellular is real time. Also `json.dumps(data, indent=2)` was burning ~30% on whitespace. Fixed `gcs_io.upload_json` to (1) emit compact JSON via `separators=(",", ":")`, (2) gzip the payload before upload, (3) set `blob.content_encoding = "gzip"` so GCS serves with `Content-Encoding: gzip` and browsers + iOS Safari + the google-cloud-storage Python client transparently decompress. Applies to all 15+ GCS write paths (weather_data, briefing_cache, decay_corrections, obs_temp_log, etc.) — every read path uses `download_as_text()` which already handles compressed responses, so nothing else needed changing. Expected weather_data.json: ~420KB → ~50KB.

## v0.6.68 • June 11, 2026
- **Debug headline box: graceful degrade when the model is unavailable.** When Open-Meteo's GFS/HRRR is down (as it's been intermittently this morning), the collector falls back to using WU stations directly with no model-comparison bias — so `hyperlocal.weighted_bias` and `weighted_bias_humidity` aren't written at all. The new v0.6.66 headline box was honestly showing "—" + "vs raw model" but looked broken. Now detects degraded mode (`aggregation: fallback_*`, `note: ...unavailable...`, or both bias keys absent) and renders an explicit "paused — model unavailable — using stations directly" message. Also handles the case where `stations_total` is missing by falling back to `"N stations reporting"` instead of `"— stations reporting"`.

## v0.6.67 • June 11, 2026
- **Forecast-text indexer no longer crashes the collector on a partial cache fallback.** Six ERROR 500s overnight (07:47, 08:07, 08:17, 08:27, 09:17, 09:47 UTC) all traced to the same shape: Open-Meteo SSL flap (`SSL: UNEXPECTED_EOF_WHILE_READING`) took down HRRR + GFS-fallback + GFS-7day + directional-sky simultaneously; the cache fallback loaded a previous-tick `hourly` block that was shorter than the per-period indices `forecast_text.py:198` walks, producing `IndexError: list index out of range` → unhandled → 500 → scheduler error email. Fixed by guarding `_generate_period_forecast` with a `safe_len = min(len(arr))` across the seven arrays it actually indexes (temperature, apparent_temperature, wind_speed/gusts/direction, precipitation_probability, weather_code), trimming `period_indices` (and the matching `period_hours`) to that bound. If nothing usable survives, returns None and the caller skips that period — same behavior as the existing "no indices" path. Open-Meteo's outage was their problem; the unhandled crash on our side was a real hardening gap.

## v0.6.66 • June 10, 2026
- **Debug page: phone-friendly headline + plain-English summaries.** Two changes on `corrections_debug.html` aimed at making the pipeline anatomy legible to a reader on iPhone, not just a self-debug surface. (1) New "Right now — what the pipeline is doing" box at the top of the page: four stat cards (temp correction, humidity correction, confidence, briefing source) populated from `hyperlocal` + `briefing`. Mobile-first grid that stacks gracefully on narrow screens. Each correction value gets a plain-English sub-line ("model running cool — we warm it" / "model running dry — we add moisture"). (2) Each Layer section (Accuracy, L1, L2, L3, L4) now leads with a one-line plain-English summary of what the layer does. The existing technical wall of text (Kalman gain, τ, octant aggregation, lead-decay formulas) is folded into a collapsible `▸ How it works` toggle, defaulting closed. Reader gets the gist on first scroll; the math is one tap away for anyone curious. Lowest-cost iteration of the "make it readable on a phone" thread — more polish (table → card stacks, glossary chips, sticky nav) deferred.

## v0.6.65 • June 10, 2026
- **Debug page roster count now reads live, not static.** Layer 2 intro blurb still said "81-station local network" — a stale number from a bigger-roster era; current active is 66 (46 WU + 20 Tempest after the v0.6.64 cull). Replaced with `<span id="layer2NetworkCount">` that `renderLayer2Panel()` updates from `hyperlocal.stations_total` on every refresh. Self-corrects forever after future culls/adds.

## v0.6.64 • June 10, 2026
- **Cull 4 zombie WU stations, hide all culls from debug uptime panel.** KMAMARBL40, 61, 95, 114 had 0% uptime across the full 7-day station_uptime window (1002 fetch-fails each) — moved from `STATIONS` to `CULLED_STATIONS` in `wu_scraper_realtime.py`, same shape as the 2026-06-04 batch. Saves ~576 API calls/day and trues up the "X of Y stations" denominator. Culls are preserved in the `CULLED_STATIONS` list (not deleted) so they can be manually re-probed later if owners come back online. `station_uptime.py` now filters culled IDs out of the summary block it stamps into `hyperlocal.station_uptime` — the debug page's dead-count and mean-uptime are no longer polluted by stations we've deliberately stopped hitting (their on-disk log entries still age out naturally over 7 days).

## v0.6.63 • June 10, 2026
- **Corrections card now compares shade feels-like, not full sun.** The card was using `corrected_feels_like` (Steadman + direct solar — "standing on hot asphalt at noon"), which runs 15–25°F above air temp on clear days. Open-Meteo's `apparent_temperature` (the model side of the comparison) is shade-leaning — no aggressive solar term — so the displayed "bias" was actually the gap between two different physical quantities, not a real correction error. Switched the corrections card to compare against the shade number: NWS heat index when valid (T ≥ 80°F + RH ≥ 35%), else Australian apparent-temperature formula with solar=0 (mirrors the fallback in `feelslike.js`). Full-sun Steadman stays in the Feels Like card with its three-way air/shade/sun chart — that's the right home for it.

## v0.6.62 • June 10, 2026
- **Defang the sea-breeze Δ in the Gemini prompt.** First post-v0.6.61 briefing produced "the sea breeze is active, adding about 22 degrees to the current 82°F" — sea breezes cool the land, they don't heat it. The 22° was real (land 81.5°F − water 59.4°F = 22.1°F land–water gradient), but the prompt fed Gemini the cryptic `Sea breeze: Active — Δ+22.1°F, 7 mph from 195°` and it misread `Δ` as a temperature change applied by the breeze rather than the gradient that drives it. Same failure shape as the torrential incident: reaching for the wrong meaning of a real number. Fixed by replacing the compact reason string in `briefing_ai.py` with a verbose LLM-only form that names the values explicitly — "Land 81.5°F, water 59.4°F (land–water gap of 22.1°F drives the breeze — this gradient is NOT a temperature change). Wind 7 mph from SSW." Frontend sea-breeze card untouched; it still gets the compact Δ form from `sea_breeze.py`.

## v0.6.61 • June 10, 2026
- **Fence intensity words in the Gemini system prompt.** Added a rule barring upgraded precip adjectives: if the data line labels the storm "light," Gemini can't write "heavy," "downpour," "torrential," "deluge," "soaking," or "severe." "Torrential"/"deluge" only when the data line explicitly says "torrential"; "heavy"/"downpour" only when it says "heavy" or "torrential." Prose stays alive at temp 0.9 — the prompt fence shuts off the specific hallucination mode that triggered yesterday's torrential incident. `_validate_headline()` stays in place as the post-generation backstop; this is belt-and-suspenders.

## v0.6.60 • June 10, 2026
- **Full pipeline audit + precip unit bug fixed in three places (including un-doing v0.6.54's wrong fix).** Three-agent audit of the collector flow, correction stack, and derived/frontend layers. Verdict: the stack is sound — bias sign conventions consistent, no double-correction, pair-log has no circularity, lead-time math correct, all physics formulas correct (Magnus, Steadman, NWS heat index bounds, Haurwitz, 225 ft/°F cloud base), L3_FIELDS wd exclusion confirmed as deliberate whitelist (now documented in decay_apply.py). One real bug: `hourly.precipitation` has been in **inches** since the modular refactor (`OM_UNITS` requests `precipitation_unit="inch"`), but three readers divided it by 25.4 as if it were mm: **(1)** `briefing_ai.py` rain_inches — 48h rain total under-reported 25× since the briefing existed (a 1" storm read as 0.0" in the AI prompt); **(2)** `briefing_ai.py` peak_intensity — v0.6.54 added this division believing it fixed the "torrential" headlines; it actually broke a correct computation (real downpours would have read as drizzle). The torrential headlines were model hallucination, already handled by the v0.6.54 `_validate_headline()` + templated fallback; **(3)** `js/briefing.js` rainInches — frontend made the same mistake, which is why briefing rain totals always showed 0.0" (including the May 7 "why does it show 0 inches" incident — the answer then was incomplete). Survivors of the 25.4 sweep are all justified: `tempest.py` converts genuine mm at fetch.

## v0.6.59a • June 10, 2026
- **Forecast sky narrative now reads solar-derived cloud cover (forecast_text.py + current_derived.py).** Extension of v0.6.59: the same transmissivity trick that fixed the Right Now label now applies across the full 48h forecast horizon. `current_derived._forecast_sky_arrays` walks each forecast hour, computes solar elevation for that timestamp, builds Haurwitz clear-sky GHI for that elevation, and back-solves `(1 − direct_radiation/clearsky) × 100` into a cloud-cover percentage per hour. Catches the model contradicting itself — when HRRR forecasts 100% cloud_cover but its own radiation scheme says 600 W/m² is getting through (thin/high cloud), the narrative sees the radiation, not the cover number. `forecast_text.py` prefers `derived.forecast_cloud_cover_solar[i]` over `hourly.cloud_cover[i]` when present; nighttime hours stay None and fall back to model cloud_cover. Also writes `derived.forecast_sky_label[]` + `derived.forecast_transmissivity[]` for debug. Forecast SR error is ~80–150 W/m² across leads — noise on derived τ is ±0.10–0.17, which keeps the Clear/Hazy vs Cloudy/Overcast boundary right almost always (sufficient to fix the "today says overcast but it'll be sunny" narrative bug). Sharpens automatically once L5 regime-aware SR correction ships (~6/22).

## v0.6.59 • June 10, 2026
- **Observed-sky reconciliation (current_derived.py + right_now.js).** HRRR was reporting `cloud_cover: 100` / weather_code 3 (Overcast) while direct radiation at the surface was 396 W/m² and visibility was 73 mi — the actual sky was hazy/thin-cirrus, not overcast. The display believed the model because there's no station ground truth for cloud cover and Layer 2 doesn't apply to `cc`. Two-step fix: **(collector)** new `derived.observed_sky_label` backs out cloud cover from observed solar via Haurwitz clear-sky GHI: `τ = observed_solar / clearsky`, binned to Clear (τ≥0.80) / Hazy (0.55) / Partly Cloudy (0.35) / Mostly Cloudy (0.15) / Overcast (<0.15). Skipped when sun is below 10° — observed solar isn't a reliable sky signal at low angles. Also exposes `solar_transmissivity`, `solar_observed_wm2`, `solar_clearsky_wm2`, `solar_elevation_deg` for debugging. **(frontend)** Right Now card prefers `derived.observed_sky_label` over `weather_code` when present (non-precip days only); falls back to a `direct_radiation ≥ 250 W/m²` heuristic when the derived field is unavailable (sun too low or no observed solar source). Sky/Precip tile, condition label, and weather graphic all see the new label.

## v0.6.58a • June 9, 2026
- **Per-station detail accordions moved from bottom of Layer 2 to directly under 2a.** The "Per-station detail (map + Kalman offsets)" and "Per-station uptime" accordions had been sitting orphaned at the end of Layer 2, after 2e (post-mesonet output grid). They're conceptually about the same thing as 2a (the station network's geographic distribution) — the 2a description text already pointed to "the 2a accordion" for per-station offsets. Reordered so the structural story reads as: 2a coverage rose → per-station detail / uptime accordions (deeper drill-down on the same network) → 2b–2e (what the network's bias correction did this tick). Section now closes cleanly with the post-mesonet output grid before Layer 3 starts.

## v0.6.58 • June 9, 2026
- **L2 τ degenerate-fit guards added at both write and read sides.** When the pair log is starved of signal (today's OOMs and Open-Meteo 429s did exactly this), the Fitter's grid search collapses to the smallest τ in the grid for every field (0.5h) because every τ scores ~identically. Before today, that result clobbered `l2_decay.json` and the live forecast pipeline lost months of validated τ knowledge (Temperature 4h, Humidity 240h, Pressure 12h) in favor of effectively-L1 behavior at every lead. Two guards now in place: **(1)** `decay_fit.py` detects the all-fields-at-min-τ signature and refuses to write — previous good values stay in GCS — history file still gets the degenerate fit for forensics. **(2)** `corrected_hourly.py`'s loader also detects the signature; if a degenerate `l2_decay.json` is already in GCS (today's case), the loader treats it as missing and falls back to `DEFAULT_L2_TAUS` instead of applying 0.5h to every field. Belt + suspenders: the fitter shouldn't write garbage, but if it ever does (or has historically), the pipeline doesn't use it.

## v0.6.52–v0.6.57 • June 9, 2026

* **Briefing reliability + end-to-end audit.** Triggered by morning headlines reading "Cloudy Now" with sky=Clear (Groq hallucination) and "torrential downpours" on light-rain forecasts (unit bug). Fixed the immediate causes and audited the whole module so the next class-of-bug catches itself:
  - **mm/hr vs in/hr unit bug** in `briefing_ai.py:161` — raw Open-Meteo precip rate (mm/hr) was compared against thresholds intended as inches/hr, so 1.0 mm/hr (light rain) was being labeled "torrential" in the prompt and Gemini faithfully wrote "torrential downpours." Divided by 25.4 to convert to in/hr before the threshold check.
  - **Post-generation sanity check (`_validate_headline`).** Every LLM headline now compared to the structured data before shipping; rejects rain words when no rain expected, clear/sunny when cloud cover ≥75%, cloudy/overcast when ≤20%, "torrential"/"deluge" when data doesn't label it that. Conservative — only catches clear contradictions.
  - **Deterministic template fallback (`_templated_briefing`).** Last-resort headline from structured data when Gemini, Groq, and cached headline all fail or all get rejected. Boring but never wrong.
  - **Cache poisoning fix.** Groq output no longer overwrites the GCS cache (cache strictly holds the last validated Gemini headline). Gemini throttle no longer trips on Groq success (so Gemini can be retried on the very next collector run after a transient failure).
  - **Switched Gemini Flash → Flash Lite**, lowered Groq temperature 0.9 → 0.5, broadened the retry window from 503/429 to any 5xx + 429 (single 5s retry).
  - **Wind impact score exposed to the model** alongside the label, for internal severity judgment (existing rule against printing the number stays).
  - **Minor:** empty alert events filtered, thunderstorm distance string suppressed when distance is None or 0.

* **Collector resilience to upstream outages.** Three independent issues surfaced when Open-Meteo started 429-ing during peak hours and the Cloud Function started OOMing.
  - **Memory bump 1024 → 1536 MB.** Memory crashes had been firing every ~70 min since 06-07 (15h after v0.6.42's longer fitter snapshot read deployed). New ceiling gives 489 MiB headroom over today's peak; three consecutive clean runs since.
  - **Octant coverage panel no longer reads all zeros during forecast-model fallback.** When Open-Meteo (HRRR + GFS) is 429, `hyperlocal.py` falls back to a distance-weighted-mean branch that bypasses the L2 octant aggregation. That branch wasn't writing `octant_coverage`, so the debug panel saw `null`, rendered zeros across all eight sectors, and made it look like the entire station network had gone dark (when actually 57 stations were contributing). Fix: fallback branch now computes octant counts and writes `octant_coverage` / `octants_used` / `aggregation` ("fallback_distance_weighted"). An amber banner above the rose explains "Fallback mode active" so the cause is visible.
  - **Settings gear icon no longer lights up on transient source failures that the fallback chain covers.** Old rule lit the dot on any critical-source error — meaning every Open-Meteo 429 (which Pirate Weather covered) made the gear scream for ~10 min even though the data shown was fine. New rule: gear lights only on data staleness >25 min or briefing genuinely empty. Sources-panel dot keeps per-source red/green coloring for debug visibility.

* **Public-sharing prep.** Open Graph + Twitter Card meta tags on `index.html` so iMessage / Slack / X / WhatsApp / Instagram DMs all render a clean preview instead of a bare URL. `tab_nav.js` now honors `?tab=<name>` from the URL so the Instagram bio link `https://wymancove.com/?tab=briefing` lands directly on the Briefing tab regardless of the user's last-active tab.

## v0.6.51a • June 8, 2026
- **L2 lead-decay "Note" rewritten to match reality.** The v0.6.51 note framed "flat" for the eight untreated fields (dp, cc, sr, cl, cm, ch, pp, pa) as a *default pending a future refit*. Tonight's L2-extension investigation showed that framing is wrong — those fields already go through the fitter (`FIELDS` covers all twelve), but `applied_bias = forecast_l2 − forecast_l1 = 0` for every pair because L2 has no additive bias term for them, so the τ grid search is degenerate. The note now says: flat is *structural*, not pending; extending L2 here requires first building a station-network bias tracker per field; `sr` is the only viable candidate (Tempest 20/20 coverage), and even there the planned L5 regime correction is the better tool. The others lack the right sensors entirely. Cuts a misleading promissory line and replaces it with a working explanation of why those columns are flat.
- **build.py version regex fixed to accept letter suffixes.** `(v[\d.]+)` → `(v[\d.]+[a-z]?)`. Previously the regex truncated `v0.6.51a` to `v0.6.51` when writing `version.json`, which would silently break the PWA's update-detection (`version_check.js`) for any suffix release. Caught while shipping this very entry; would have bitten every future `a/b/c` bump.

## v0.6.51 • June 8, 2026
- **L2 lead-decay documented in the debug page.** The v0.6.44 per-field τ lead-decay (`bias_applied(lead) = current_bias × exp(-lead/τ_field)`, τ_t=4h, τ_h=240h, τ_pr=12h) was invisible from the Layer 2 panel — the prose described uniform application and never mentioned the decay. Added a sentence to L2's additive-bias paragraph and a new **2d. Lead-decay applied to L2 bias** subsection placed *before* the post-mesonet output grid (renumbered to 2e), matching the actual pipeline order. Live chart of `exp(-lead/τ)` over 48h for t/h/pr fed by `weather_data.l2_decay_meta.tau_hours`, plus the wind/gust linear 0–24h ramp and a flat reference for every other field. Y-axis is fraction of L2 contribution applied. Copy makes explicit that "flat" for the untested fields (dp, cc, sr, cl, cm, ch, pp, pa) is a *default*, not a winning grid-search candidate — a future refit could expand `L2_TAU_FIELDS` to cover them.
- **R3d τ tuning disambiguated.** The Discarded entry tested the Fitter's *recency-weighting* τ (how much old pairs count when fitting decay curves). Adjacent prose now distinguishes it from the L2 *lead-decay* τ added in v0.6.44 — two different knobs sharing a Greek letter, easy to confuse on skim.
- **Research & Diagnostics intro box removed.** The "Diagnostic only — these signals are tracked but not applied to the live forecast" subhead duplicated the h2 above it, and its secondary line still referenced tide as the active hypothesis (now in Discarded). Section header alone now.
- **Page header meta de-cluttered.** Was showing full enabled-field code lists (e.g. "L3: ch, cm, pp, wg, ws · L4: ch") plus a "(v0.6.45)" version tag, duplicating the banners under each Layer section — and singling out L3/L4 while ignoring L2 (which runs on every field) was misleading. Replaced with a plain freshness line: "decay applied {ts}". Per-layer enabled-field detail lives in the L3/L4 banners; L2 is universal.

## v0.6.50 • June 8, 2026
- **Removed R3e POP entry from Discarded.** With POP re-enabled in v0.6.49, the R3e entry was contradictory ("settled" in the Discarded section). POP is live, settled, and documented in the L3 banner. The Discarded section now contains only genuinely discarded hypotheses.

## v0.6.49 • June 8, 2026
- **POP re-added to L3 — the v0.6.45 audit discarded it with the wrong metric.** The v0.6.45 per-field whitelist used held-out MAE to decide which fields L3/L4 should run on. POP was flagged net-negative and removed. But POP is a *probabilistic* forecast and is properly evaluated by Brier score, not MAE — the original v0.6.20 calibration analysis (`analysis/pop_calibration.py`) showed the flat-additive correction cuts Brier from 783 → 745 (5% improvement). The MAE-based audit was correctly noticing that L3 hurts MAE on POP, but that's the price of better Brier calibration, not a regression. Between v0.6.45 and v0.6.49 we were shipping raw HRRR POP, which is measurably worse than corrected POP on the right metric. Fix: `pp` added back to `L3_FIELDS` in `decay_apply.py`. New `L3_BRIER_FIELDS = {"pp"}` set is published in `decay_meta.layer_3_brier_fields` so the R0 audit table tags POP rows with "[Brier]" and suppresses the MAE-based ⚠ rule for it.

## v0.6.48 • June 8, 2026
- **R2: State-stratified accuracy promoted to live active hypothesis.** Manual-only run of `analysis/state_stratified_accuracy.py` revealed huge regime-conditional spreads: Solar rad × flow regime = 120 W/m² across bins (vs 27 W/m² overall bias), four solar dimensions in the top 5 ranks (98–120 W/m² spread), Cloud cover at 14–17% across multiple dimensions. New module `weather_collector/processors/state_stratified.py` mirrors the analysis script's math (equal-weight, MIN_PAIRS_PER_BIN=20, six dimensions, MIN top-spread verdict threshold=1.0) and is fed in-loop by `decay_fit.py` alongside the recency-weighted accumulators. Publishes `state_stratified_accuracy.json` to GCS at every Fitter pass — per-field per-dimension tables + top-15 ranked opportunities + verdict line. Twice-daily cadence (matches the new Fitter schedule). Frontend renders the top-10 opportunities table + the #1 opportunity's per-bin breakdown (sorted worst → best, red/green bars vs overall MAE). Caveat surfaced in the card: magnitudes are from the 30-day rolling window mostly dominated by pre-v0.6.45 pairs; confirm headlines survive after ~2026-06-22.
- **Research & Diagnostics restructured into three labeled buckets** (`<h3>` subheaders): Diagnostics (R0 live audit, R1 drill-down teaching view), Active hypotheses (R2 state-stratified), Discarded hypotheses (R3 tide + derived humidity + τ tuning + POP). Renumbered titles inside the discarded section R3a–R3e; details element IDs preserved for back-link stability.

## v0.6.47 • June 8, 2026
- **GCP cost trim: Fitter 4×/day → 2×/day, dead-hypothesis tracking gated off.** Daily Fitter compute was driving a 615% MoM jump in GCP spend after the v0.6.42 timeout bump (300s → 540s) and v0.6.44c τ-refit pass. Cadence dropped to 03:07 + 15:07 EDT (post-overnight + mid-afternoon). The active build phase is over (L2 lead-decay shipped, L3/L4 per-field whitelist settled), so same-day refit is no longer required. **Dead hypotheses gated, code preserved:** `RUN_TIDE_TRACKING = False` in `decay_fit.py` skips the per-pair tide-phase accumulator, the tide-phase JSON + history upload, and the NOAA tide-elevation fetch for the time series — about 69 lines of compute + one HTTP request + two GCS writes per Fitter pass. Code remains in place; one-line flip revives it. **UI: new "R4. Discarded hypotheses" section** at the bottom of Research & Diagnostics — R1/R2 tide charts moved inside (showing the frozen final state), plus text-only writeups for R4c derived humidity (27k triples, equivalent), R4d τ-tuning (settled at 14d), and R4e POP calibration (flat-additive shipped v0.6.20). Each notes its analysis script in `analysis/`.

## v0.6.46 • June 8, 2026
- **R0 live audit table — is each layer earning its keep?** New research-section card on `corrections_debug.html` that recomputes the same L1→L4 average-MAE table that drove the v0.6.45 whitelist, live from the already-published `time_series_diagnostic.per_layer_mae_by_lead`. Average is over leads 1–47 (lead 0 excluded — circular by construction). Per field: shows MAE per layer, Δ vs the layer below (green ▼ = improvement, red ▲ = regression), and a `Live?` column reading `decay_meta.layer_3_fields` / `layer_4_fields`. When an enabled layer is currently regressing on its field, the cell flags `⚠`; a banner above the table summarizes "all clean" or "review needed." Pure-JS — no collector change, no new GCS file. Updates as soon as `time_series_diagnostic.json` republishes (every fit cycle, 4×/day). Frontend-only release.

## v0.6.45 • June 8, 2026
- **L3/L4 per-field whitelist (Phase 0 of the L3/L4 audit).** Replaces the global v0.6.44 pause with per-field gating based on held-out MAE from `time_series_diagnostic`. L3 enabled for `ws`, `wg`, `ch`, `cm` (clear wins vs L2: gusts +53%, wind speed +44%, high cloud +18%, mid cloud +5%); L4 enabled for `ch` only (the one field where L4 beats L3 cleanly). Everything else (`t`, `h`, `dp`, `sr`, `cc`, `cl`, `pa`, `pr`) stays disabled — L3/L4 were net-negative there because they were learning residuals from a flat-applied L2 bias; the L2 lead-decay fix from v0.6.44 fixed the input signal but the data hasn't accumulated yet to revalidate. `decay_apply.py` swaps `APPLY_LAYER_3/4` booleans for `L3_FIELDS` / `L4_FIELDS` sets; `decay_meta` publishes both as sorted lists. `_post_l2` / `_post_l3` snapshots still happen for every field so the per-layer MAE diagnostic continues to publish — disabled fields show L3 = L2 and L4 = L3 by construction. `per_field_24h` now only contains fields actually applied.
- **UI: corrections card + debug page reflect per-field state.** Home corrections card shows a unified +24h delta table: L2-only fields (`t`, `h`, `pr`) come from the L2-lead-decayed delta at lead 24h tagged with τ; L3-enabled fields (`ws`, `wg`, `ch`, `cm`, etc.) come from `per_field_24h` tagged "(L3)". Header right shows "L3 on: ws/wg/cm/ch". `corrections_debug.html` Layer 3 and Layer 4 banners updated to explain the audit framing and surface the live enabled-field list; chart labels drop the "(paused)" tags since pause is now field-specific.

## v0.6.44–v0.6.44c • June 8, 2026
- **L2 lead-decay shipped; L3/L4 paused; daily τ refit wired in.** Audit of held-out per-layer MAE showed L3 (decay) and L4 (diurnal) were net-negative on temperature, humidity, dew point, solar, low cloud, pressure, and precip amount — fitting residuals from a flat-applied L2 bias and learning the wrong thing as a result. New `analysis/l2_lead_decay_fit.py` fits a single τ per field via grid search on 73,510 train pairs: `bias_applied(lead) = current_bias × exp(-lead/τ)`. Held-out wins vs flat L2: t +5.1% (τ=4h), h +3.8% (τ=240h), pr +4.2% (τ=12h), dp +3.3% inherited. Wind speed/gust prefer τ=∞ (current flat behavior remains correct). Productionized: `corrected_hourly.py` applies bias × exp(-i/τ_field) per lead index; `DEFAULT_L2_TAUS = {t: 4, h: 240, pr: 12}` baked in with `l2_decay.json` GCS override path. L3 and L4 paused via `APPLY_LAYER_3 = False` / `APPLY_LAYER_4 = False` switches in `decay_apply.py` for ~14 days while the recency-weighted fitter rebuilds against correct-L2 residuals; `_post_l2`/`_post_l3` snapshots still publish so the per-layer MAE diagnostic continues to record.

- **Daily τ refit pass.** `decay_fit.py` extended with three new accumulators per (field, lead): `Σw·e_l1²`, `Σw·e_l1·bias`, `Σw·bias²`. Lets the grid search compute SSE(τ) = Σ_l [e2 + 2·exp(-l/τ)·eb + exp(-2l/τ)·b2] in O(48·15) per field after the pair-log pass. Fits τ for t, h, pr, ws, wg on the same recency-weighted window as L3/L4 (τ=14d). Publishes `l2_decay.json` to GCS with `tau_hours`, `n_pairs_per_field`, `sse_at_grid`; rolling 365d history at `l2_decay_history.json`. `corrected_hourly.py` loader prefers the GCS-published fit and falls back to `DEFAULT_L2_TAUS` if absent or thin (<500 pairs/field). Daily cadence chosen because τ describes a slow process (drivers: seasonal shift, station network changes, big synoptic regime shifts) and sub-daily refit only adds noise; same pair-log read as L3/L4 so marginal cost is zero.

- **UI: corrections card + accuracy chart labels reflect the pause.** When `decay_meta.layer_3_paused` is true, the home corrections card swaps "Forecast Decay Corrections" → "Forecast Corrections at +24h" and shows the actual L2-lead-decayed delta at lead 24h (computed from corrected vs raw hourly arrays), with each row tagged by its τ value — instead of the previous `per_field_24h` (what L3 *would* apply, not currently in the live forecast). `corrections_debug.html` Layer 3 and Layer 4 sections gain an amber paused banner; the "how accurate is it?" chart's legend relabels "+ Mesonet" → "+ Mesonet (final)" and "+ Decay" / "+ Diurnal" → "(paused)"; the drill-down preview legend matches. Header meta line shows "L3/L4 paused (v0.6.44) · L2 lead-decay only" when paused.

## v0.6.43 • June 8, 2026
- **Corrections card + debug page UI tweaks.** Hyperlocal corrections card: Feels Like row labeled `(full sun)` to make explicit that the corrected apparent-temperature uses the unshaded solar load (shade variant TBD). Forecast Decay Corrections subsection expanded from 6 → 10 fields — added Pressure, Cloud Cover, Solar Rad, Precip Rate; layer-specific cloud bands (cl/cm/ch) intentionally omitted as too technical for the home card. `corrections_debug.html` accuracy section heading reworded "is it actually working?" → "how accurate is it?". Sticky TOC bar gains a "← Back" chip as the first item that returns to `/` (index.html) — no in-page way to leave the debug view existed before.

## v0.6.42 • June 6, 2026
- **Fitter race-condition fix.** The Daily Fitter was failing on every recent run because it read `forecast_error_log.jsonl` directly from the live blob handle while the Joiner appended to that same file every 10 min via GCS compose. Reads of the ~800MB file took several minutes — long enough for the Joiner to replace the file mid-read, producing either a `Bytes stream is in unexpected state` desync error or a 404 on the pinned generation. Fix: server-side `copy_blob` to an immutable snapshot path `forecast_error_log_fitter_snapshot.jsonl` before the read, then stream from the snapshot. Snapshot is deleted after the main rewrite swap (or in the error path). Manual run verified — 1.99M pairs processed, all 14 fields fitted with sensible decay corrections. Also bumped the Cloud Function timeout from 300s → 540s (`Makefile`) since a clean Fitter pass on the current log size takes ~3 min and the collector has other work to do on the same invocation. Added an HTTP-status + body-excerpt diagnostic to the Briefing module's Gemini fallback path (`briefing_ai.py`) — confirmed the chronic Gemini failures are HTTP 429 quota exceeded (AI Studio free-tier limit, not GCP billing) with Groq fallback succeeding 100%.
- **Humidity now uses Kalman gain.** The temperature pipeline blends `model_t + K × weighted_bias` where K scales from 0.40 (sparse / scattered stations) to 0.90 (many stations agreeing tightly). Humidity was doing pure station-mean replacement of the model value — no confidence gating, so a few drifty hygrometers could swing `corrected_humidity` 20%+ in either direction. Extended the Kalman blending to humidity with a separate threshold function `_kalman_gain_humidity(n, std)` calibrated for the humidity % scale (thresholds `3.0` / `7.0` vs temp's `0.4` / `0.8` °F — hygrometers are noisier than thermistors, so analogous "tight" / "moderate" buckets land at different absolute numbers). Pressure intentionally skipped: 30-day Fitter shows pressure bias is essentially zero (`pa` corrections all `-0.001` across 48 lead bins), station consensus matches model after altitude normalization, so K would always be 0.9 and the visible effect would round to zero. New `hyperlocal` fields: `weighted_bias_humidity`, `bias_std_humidity`, `kalman_gain_humidity`, `stations_used_humidity`. `corrections_debug.html` Layer 3 panel now renders temp and humidity side-by-side (K, percentage trusted, weighted bias, applied bias, scatter, n stations); methodology note updated; per-station bias header stats add `Kalman gain (RH)` and `bias σ (RH)`.

## v0.6.41 • June 4, 2026
- **Layer 2 accordions now remember open/closed state across page refresh.** Both `#bias-details` ("Per-station detail") and `#uptime-details` ("Per-station uptime") accordions on `corrections_debug.html` lost their open state on every reload, forcing re-expansion every visit. Added `initBiasAccordions()` (mirrors the existing `initResearchAccordions` pattern but with a separate localStorage key `forecastPipelineBiasAccordionsOpen`) which restores the open state per `details.bias-accordion[id]` element on load and persists toggle changes. The existing map-invalidation handler on `#bias-details` continues to coexist — both toggle listeners fire on user interaction; the map-resize handler's `if (_biasMap)` guard prevents it firing prematurely when state is restored before render.

## v0.6.40 • June 4, 2026
- **Per-station uptime UI on debug page.** New accordion under Layer 2's "Per-station detail" section displays a sortable table of all tracked stations with `uptime_pct / n_success / n_attempts`. Color tiers: green ≥95%, amber 80-95%, red <80%, bold dark-red 0%. Header strip summarizes total stations, mean uptime, healthy/degraded/dead counts. Sort defaults to worst-first (ascending pct) so dead stations rise to the top. Data source: `hyperlocal.station_uptime` (7-day rolling window from `station_uptime.py`). Implementation: ~110 lines of JS (`_uptimeState`, `_uptimeTier`, `_renderUptimeTable`, `renderUptimeSection`) reusing the existing `offset-table` CSS pattern. Reveals what wasn't visible before — the new view immediately surfaced 23 dead stations (0% over 179 ticks) and prompted the cull below.
- **Cull 16 dead stations from the fetcher lists.** Direct API probes confirmed two distinct failure modes:
  - **10 WU stations return HTTP 204 (No Content)** every tick — station IDs are still valid in WU's directory (the `wunderground.com/hourly/...` page resolves) but the owners aren't uploading recent observations. Culled: `KMAMARBL89, KMAMARBL117, KMAMARBL118, KMAMARBL17, KMAMARBL26, KMAMARBL84, KMASALEM35, KMASALEM86, KMASALEM111, KMASWAMP28`.
  - **6 Tempest stations return partial obs records** through the developer API — only lightning + precip fields, with temp / wind / humidity blanked. The stations ARE online (full data visible on tempestwx.com) but the owners have restricted field-level sharing for API access. Useless for our mesonet bias correction which requires temp + wind. Culled: `28679 (Broadmere Way), 51384 (Memorial Dr), 72262 (Spray Ave), 85260 (Driftwood Rd), 100037 (Bass Rock Ln), 159204 (Marblehead)`.
  - Both fetcher files retain a `CULLED_STATIONS` / `CULLED_TEMPEST_STATIONS` constant beneath the active list — the cull list lives with the data so anyone editing the file sees what was removed and why. Easy to un-cull if a station comes back online.
  - **Effect:** total stations attempted per tick goes 86 → 70. The 16 culled stations will continue to appear in the uptime UI at 0% for ~7 days (the rolling window's retention) and then age out naturally — no GCS log cleanup needed.

## v0.6.39 • June 4, 2026
- **Prominent zero line on historical fits charts.** Sections 3c (decay history), 4a (diurnal history), and R1 (tide-phase history) on `corrections_debug.html` plot many overlaid grey-on-dark curves; the existing thin grid line at y=0 was hard to spot, making it ambiguous whether a field's bias started positive or negative — and therefore which direction "good evolution" (curves moving toward zero) actually looked like. Added a small inline Chart.js plugin `zeroLinePlugin` that draws a white 1.5px line at y=0 before the datasets render, with a bounds check so it's skipped when zero is outside the visible y-range. Wired into all three `build*HistoryChart` functions via the chart config's top-level `plugins: [zeroLinePlugin]`. The recency gradient (oldest pale grey → newest solid blue) was already in place; this fix just makes the reference baseline visible.

## v0.6.38 • June 4, 2026
- **Wind regime classifier shipped.** New module `weather_collector/processors/regime_classifier.py` exposes two orthogonal classifiers: `classify_flow_regime` (pure direction — n/ne/e/se/s/sw/w/nw/calm, 9 labels) and `classify_synoptic_regime` (coastal-flavored synoptic pattern — nw_flow/sw_flow/se_flow/ne_flow/sea_breeze/nor_easter/frontal/pre_frontal/calm, 9 labels). Both axes get stamped onto every pair (`state_fc.regime_flow` + `state_fc.regime_synoptic` for forecast-time state, `state_obs.regime_flow` + `state_obs.regime_synoptic` for observation-time state) inside `forecast_error_log.py` as the Joiner builds state metadata. Rule-based: sea_breeze requires SE-quadrant flow + summer afternoon hour + warm + light wind + steady pressure; nor_easter requires NE flow + low pressure + ≥12 mph; frontal/pre_frontal triggered by pressure trend. Pre-v0.6.38 pairs don't carry these keys and are silently skipped by downstream analytics. `analysis/state_stratified_accuracy.py` extended with both regime axes as the 5th and 6th stratification dimensions — re-run in ~1 week once regime-bearing pairs accumulate to see which regimes show the biggest forecast-error spread.

## v0.6.37 • June 4, 2026
- **Debug page browser tab title is now "Wyman Cove — Forecast Pipeline"** (was "MyWeather — Forecast Pipeline"). Project nickname is for the codebase, not the user-facing page.
- **Research-section subsections are now individually collapsible.** R1 (tide-phase curves) and R2 (error-vs-tide timeseries) on the Forecast Pipeline page were always-on under the Research h2, so opening that section dumped both charts at once. Wrapped each in a `<details class="research-subsection">` with closed default state and localStorage persistence (key: `forecastPipelineResearchOpen`). Matches the existing bias-accordion pattern but in the orange/amber research palette. New `initResearchAccordions()` wires the toggle persistence.
- **Two new analysis scripts** for hypothesis testing as data accumulates:
  - `analysis/state_stratified_accuracy.py` — slices forecast MAE by wind octant, wind speed, cloud cover, and pressure tendency to find which regime dimensions matter. First run: humidity-by-wind-direction shows 9.9% RH spread across octants (NW dry vs SE marine); temperature-by-wind-direction shows 3.8°F spread. Both are candidates for future regime-stratified correction.
  - `analysis/decay_tau_tuning.py` — walk-forward validation of τ ∈ {7,10,14,21,28} per field. First run verdict: KEEP τ=14 global (no field gains ≥5% vs τ=14). Caveat: the recent v0.6.34/35/36 changes mean current pair log mixes schemas; re-run in ~1 week for cleaner read.

## v0.6.36 • June 4, 2026
- **Fix: moisture derivation didn't run in fallback mode.** v0.6.35 added Magnus-derived corrected_humidity inside `apply_decay_corrections`, which runs BEFORE `apply_stale_fallbacks` in collector.main(). When an upstream fetch fails (e.g. today's Open-Meteo outage), `apply_stale_fallbacks` overwrites `weather_data["hourly"]` with the previous run's cached hourly array — which silently overwrote the derived corrected_humidity with the old independently-corrected value. Audit caught it: live corrected_humidity differed from Magnus(corrected_T, corrected_T_d) by 0.5–2.6% across every hour. Fix: factored the Magnus humidity + Steadman apparent_temp + absolute_humidity recompute into a standalone `recompute_derived_moisture_arrays(weather_data)` function in decay_apply.py. Called both inside `apply_decay_corrections` (fresh-data path) and from collector.main() immediately after `apply_stale_fallbacks` (cached-data path). Idempotent — safe to call multiple times. The (T, T_d, RH, AH) moisture quadruple now ships consistent whether the data is fresh or stale-cached.

## v0.6.35 • June 4, 2026
- **Humidity now derived from corrected (T, T_d) via Magnus.** Architectural consistency fix. apparent_temperature and absolute_humidity already derive from corrected T and corrected T_d so they stay internally consistent; humidity was the holdout — independently corrected through L2/L3/L4. Even though the offline analysis (`analysis/derived_humidity.py`) showed independent vs derived MAE were a wash (Δ ≈ 0% across all leads, n=1947 triples), individual point forecasts can disagree — heat index computed from (T_corrected, RH_corrected) wouldn't match heat index from (T_corrected, Magnus(T_corrected, T_d_corrected)). Fix: in `decay_apply.py`, after all L1-L4 corrections complete, overwrite `corrected_humidity[i]` with `_relative_humidity(corrected_temperature[i], corrected_dew_point[i])` via Magnus before recomputing apparent_temp and absolute_humidity. Independent L2/L3/L4 humidity corrections still run (visible in pair-log per-layer fields for diagnostic comparison) but the shipped value is derived. The full (T, T_d, RH, AH) moisture state now ships as one consistent quadruple. dp_l4 > t_l4 (unphysical) clamps RH to 100.

## v0.6.34 • June 4, 2026
- **Fix: Layer 4 diurnal was structurally over-correcting on most fields.** The 03:07 EDT fit on June 4 showed L4 MAE worse than L3 on temp/dp/h at 6h lead, and catastrophically worse on cloud cover (L4=14.44 vs L3=6.36, −130% vs raw). Root cause: the diurnal fit accumulated the legacy `error` field (= L2 residual, same signal Layer 3 was fit on). Layer 3 captured per-lead means; Layer 4 captured per-hour means; both latched onto the same hour-of-day bias signal. The mean-zero normalization on L4 was a partial hack to decouple them, but it only removes the grand mean — it can't decompose the lead × hour-of-day interaction when those are correlated (which they are for cloud cover, solar, wind). Fix in `decay_fit.py`: (1) accumulate diurnal sums from `error_l3` (L3 residual) instead of `error`; legacy pre-v0.6.25 pairs fall back to `error`. (2) Remove the mean-zero normalization — when fitting on L3 residuals, L3's contribution is already removed, so the raw per-hour mean is the correct adjustment. Simulated on the current 1.28M-pair log: L4 MAE drops 26–65% across every field (cc 12.79→4.43, sr 27.62→13.89, wg 2.94→1.56, t 2.33→1.60, dp 3.95→2.72). New corrections take effect at the next Fitter run (09:07 EDT today).

## v0.6.33a • June 3, 2026
- **Removed v0.6.33's past-observation overlay from drill-down charts.** Standalone past observations aren't diagnostic on their own — they're just "what the weather did," which isn't the drill-down's job. The drill-down's purpose is "preview the next 48h, see what each layer thinks." Past-forecast-vs-past-observation comparison belongs in the Accuracy section, which already does it statistically. Removed: x-axis past-extension (back to leads 0–47), the white observed-line dataset, the obs_temp_log fetch in load(), and the DRILL_OBS_KEY + _drillObsByHour helpers. Kept from v0.6.33: confidence band around L4 (±near-term MAE width) and the MAE annotation strip under each card. Both add the accuracy context the drill-down actually needs.

## v0.6.33 • June 3, 2026
- **Drill-down charts get three accuracy enhancements.** Same chart per field as before, but now with: (1) **Past-24h observation overlay** — solid white dots+line on the past portion of the x-axis showing the actual observed values from `obs_temp_log` for the last 24 hours (binned to nearest hour, closest entry per bin). X-axis extended from leads 0→47 to leads −24→+47. POP gets binary 0/100 obs from `precip_in > 0`. (2) **MAE annotation under each card** — small text strip showing "Near-term (6h) ±X · Day-ahead (24h) ±Y" sourced from `time_series_diagnostic.json::per_layer_mae_by_lead.l4` with `errors_by_lead` mean-of-abs fallback (same logic as Almanac accuracy block). (3) **Confidence band around L4 line** — translucent blue fill at ±near-term-MAE width, visually indicating the typical error envelope of the final forecast. Hidden from chart legend. New `DRILL_OBS_KEY` table maps field keys to obs_log field names. New `_drillObsByHour` helper buckets obs by integer hour offset. Chart tooltips now distinguish "Xh ago (observed)" from "+Xh (forecast)". Five `_drillRender()` call sites updated to thread `tsDoc` + `obsLog` through.

## v0.6.32a • June 3, 2026
- **Fix: 24h-ahead column was blank in the new Forecast accuracy block.** Cause: `per_layer_mae_by_lead.l4[24]` requires a snapshot taken 24h ago that has L4 captured, but v0.6.25b (which added L4 capture) deployed only ~10h ago. Lead-24 L4 data won't exist for another ~14h. Fix: `renderForecastAccuracy()` now falls back to the legacy `errors_by_lead` field (which exists on every pair going back the full 7d) when L4 is missing at a given lead — computes MAE as mean-of-abs of per-hour errors. Slightly conservative as a proxy for L4 (uses L2-stage forecast vs obs) but available immediately at all leads. Will switch back to L4 naturally as that data accumulates.

## v0.6.32 • June 3, 2026
- **Forecast accuracy block on the Almanac → Observed card.** Surfaces practical accuracy numbers to the main app for the first time. New `renderForecastAccuracy()` in `obschart.js` fetches `time_series_diagnostic.json::per_layer_mae_by_lead`, pulls Layer 4 (final corrected forecast) MAE for the 7-day rolling window at lead 6h ("6h ahead") and lead 24h ("24h ahead"), and renders a compact 3-column table under the obs chart for 7 fields: Temp, Wind, Gust, Humidity, Dew point, Pressure, Cloud. Format: `±1.2 °F`. Pulls in fresh data on each `buildObsChart()` call (i.e., every page load / refresh). 7-day window for stability; 6h/24h leads for "near-term vs day-ahead" framing. Source notes that lead 0 is intentionally skipped (circular comparison).

## v0.6.31 • June 3, 2026
- **Fix: exclude wind direction from diurnal fit.** The diurnal aggregator in `decay_fit.py` was applying its signed-mean-error logic to wind direction's angular-delta `error` field, producing nonsensical ±139° "diurnal corrections" by averaging across the 0°/360° wraparound. Currently saved from being applied by the accident that wd isn't in diurnal's TARGET_ARRAY, but the bogus values were sitting in `diurnal_corrections.json`. Added explicit `field != "wd"` check in the diurnal accumulator. Wind-direction Layer 4 (diurnal) needs its own sin/cos special-case (same as the decay one); deferred to a future version per v0.6.27 scope. Other two surfaced "bugs" (cloud diurnal ±53% and cloud L1=0 in per-layer chart) are NOT data quality issues — first may be real seasonal signal, second is a transition artifact from old snapshots aging out of the pair log.

## v0.6.30a • June 3, 2026
- **Fix: Forecast Pipeline link in settings drawer was invisible in light theme.** Was using `color:var(--accent)` which renders white-on-white in light mode. Switched to `color:var(--muted)` to match the sibling label styling (How It Works, Changelog, etc.); ↗ glyph still signals it's a link.

## v0.6.30 • June 3, 2026
- **Per-station uptime tracking** (foundation for future auto-cull). New `processors/station_uptime.py` writes a rolling 7-day per-station success/fail log to `station_uptime.json` in GCS. Each tick records whether every attempted WU + Tempest station returned usable data (WU = has `temperature_f`; Tempest = `valid` flag). A per-station summary (`{uptime_pct, n_attempts, n_success}`) is also stamped into `weather_data["hyperlocal"]["station_uptime"]` so the debug page can render uptime without an extra fetch. Auto-culling stays MANUAL for now — the data first needs a week to be meaningful before threshold decisions. Reads `STATIONS` from `wu_scraper_realtime.py` and `TEMPEST_STATIONS` from `tempest.py` to determine the attempted set.

## v0.6.29 • June 3, 2026
- **Conditional-state metadata stamped on every pair.** Foundation for Research-section hypothesis stratifications (e.g., "temp bias when wind is from NW vs SE", "humidity bias on sunny vs overcast days"). Each pair row in `forecast_error_log.jsonl` now carries two dicts: `state_fc` (forecast-side state at snapshot time, pulled from the snapshot's target_hour + snapshot-level metadata) and `state_obs` (observed-side state at obs time, pulled from `obs_temp_log`). Fields captured: wind_speed, wind_dir, solar_wm2, cloud_cover, cloud_low/mid/high, pressure_in, precip, plus pressure_trend_hpa_3h (forecast-side only, snapshot-level) and humidity/temp (obs-side only). `forecast_snapshot.py` now accepts a `derived=` arg to capture snapshot-level state (pressure trend) as snapshot metadata. Same value applied to every pair born from the same (snapshot, obs) join. The Fitter doesn't aggregate by these yet — they're logged for downstream conditional analyses. Starting log NOW means we don't lose the next week of data while debating the analysis design.

## v0.6.28 • June 3, 2026
- **AI briefing now gets cloud cover + pressure trend.** Gemini prompt had no idea whether it was sunny or overcast (clear gap — a 75° sunny day and a 75° overcast day read completely differently). Added two new optional prompt lines in `briefing_ai.py`: (a) **Sky** — current cloud % + 24h range when range > 25% (e.g., "Sky: 30% cloud now, ranges 0-90% next 24h"); steady-state phrasing when it's holding flat. (b) **Pressure trend** — when 3h trend ≥ ±1.5 hPa, includes a labeled trend with severity ("falling" → "FALLING FAST — storm signal — front likely incoming"). Skipped when steady. Both pull from already-corrected post-Layer-4 hourly data + the existing `derived.pressure_trend_hpa_3h`.

## v0.6.27a • June 3, 2026
- **Sanity cap on wind-direction correction.** v0.6.27 had no cap on the sin/cos correction magnitudes — with one pair in the log, lead-0 correction was (1.63, -1.14) which flipped wind direction by 170° (south wind → north wind). Added `WD_COMPONENT_CAP = 0.30` in `decay_apply.py` clamp on each sin/cos component before recombining via atan2. Max angular shift ≈ asin(0.3) ≈ 17° single-axis (~24° combined). Symmetric with the other fields' CAPS.

## v0.6.27 • June 3, 2026
- **Wind direction added as the 14th correction field — Layer 3 (decay) only, with proper circular math.** Wind direction is a circular variable (5° vs 355° = 10° apart, not 350°); standard signed-mean-error fitting breaks completely. Solution: fit corrections in **(sin, cos) component space**. (1) `forecast_snapshot.py` captures `wind_direction` per layer (l2=l1 and l4=l3 since wd has no mesonet or diurnal layer yet). (2) `forecast_error_log.py` special-cases wd: computes `error` as wrap-aware angular delta in [-180, 180] via new `_circular_diff_deg` helper, plus `error_sin` and `error_cos` as forecast-vs-observed component differences. Per-layer `error_lN` for wd also uses circular delta. (3) `decay_fit.py` adds `wd` to FIELDS and a parallel sin/cos accumulator (`wd_sin_sums/cos_sums/weights`) per lead bin. Outputs `corrections["wd_components"] = {"sin": [...48], "cos": [...48]}`. (4) `decay_apply.py` applies wd correction via `atan2`: `corrected_sin = sin(raw) − sin_corr`, same for cos, then `atan2(s, c)` recovers the corrected angle. Preserves `raw_wind_direction` before mutation. (5) Frontend FIELDS gets a wd entry; appears in Layer 1 raw grid, drill-down, and the per-layer accuracy chart with units in degrees. Layer 2 (mesonet vector blend) and Layer 4 (diurnal) for wd are explicitly NOT in v0.6.27 — start with decay, see if it earns its keep, add the others if data warrants.

## v0.6.26b • June 3, 2026
- **Collapsible top-level sections on the Forecast Pipeline page.** Click any `h2.section` heading to collapse/expand its content. ▾/▸ indicator shows state. Collapsed state persisted per section to `localStorage` (key `forecastPipelineCollapsed`) so the page remembers what you collapsed across refreshes. TOC links still work — heading stays visible; click to expand. With 13 fields × multi-section layout the page got long; this trims it back to whatever sections you actually want to see.

## v0.6.26a • June 3, 2026
- **Drill-down section reworked as multi-select.** Was "Single-field drill-down" with radio buttons. Now: rename to **"Drill-down"**, field selector is checkboxes (default: just temperature), each checked field gets its own chart (4-layer stack). Adds **"Clear all" button** for fast deselect. Play layer-build-up animation now applies in sync across every selected field's chart. Unit-mismatch problem solved by giving each field its own y-axis card rather than overlaying. With 13 fields now in the stack, this is the better navigation pattern.

## v0.6.26 • June 3, 2026
- **Correction stack expanded from 8 to 13 fields.** Five additions, all wired through Layers 3 (decay) + 4 (diurnal). No Layer 2 for these (no per-station-network bias path makes sense). All hooked into the per-layer MAE-by-lead chart on the diagnostic page.
  - **Solar radiation (`sr`)** — forecast: `hourly.direct_radiation` (HRRR, W/m²). Obs: median across Tempest stations' `solar_radiation_wm2` (skips shaded outliers via median). Cap ±300 W/m², bounds [0, 1400].
  - **Precipitation amount (`pa`)** — forecast: `hourly.precipitation` (HRRR, in/hr). Obs: MAX of WU stations' `precip_rate_in` (rain is patchy; one station in the cell is the right signal). Cap ±0.20 in/hr — strict because the field is sparse and noisy.
  - **Cloud cover low/mid/high (`cl`/`cm`/`ch`)** — forecast: `hourly.cloud_cover_low/mid/high` (HRRR, 0–100% each). Obs: parsed from KBOS METAR `clouds[]` array per layer altitude using FAA bands (low <6500ft, mid 6500–20000ft, high >20000ft); new helper `_metar_cloud_splits_pct` in `noaa.py`. Per-altitude bias drives fog/cloud-base accuracy independently of the total-cover metric.
- **Six file changes** to wire the 5 new fields: `obs_log.py` (new kwargs), `daily_extremes.py` (Tempest solar aggregation + WU precip max + KBOS cloud splits), `noaa.py` (METAR altitude parsing), `decay_fit.py::FIELDS`, `decay_apply.py` (TARGET_ARRAY/CAPS/ROUND_DIGITS/FIELD_BOUNDS + raw_* preservation), `forecast_snapshot.py` (4-layer capture for each), `forecast_error_log.py::FIELD_MAP`, `corrections_debug.html::FIELDS`. Per-layer pair data starts accumulating from this deploy; meaningful corrections after ~24h, full lead coverage after 48h.

## v0.6.25e • June 3, 2026
- **Docs catch-up:** `HOW_IT_WORKS.md` rewritten end-to-end for the v0.6.25 architecture — 81-station mesonet, 4-layer model (Raw / Mesonet / Decay / Diurnal), octant balancing, MAD outlier trimming, Kalman retune, per-station calibration, pressure + cloud as correction fields, every-6h Fitter cadence. `DATA_PIPELINE.md` got surgical updates to the framing block, temperature section (octant aggregation + new Kalman thresholds + outlier trimming), pressure section (Layer 3/4 now applied, not skipped), wind blend (per-octant max → median, not flat max), wind gust section (radius 1.5 → 2.5mi), plus a new Cloud Cover section. Docs were previously dated June 1 and described pre-v0.6.17 internals.

## v0.6.25d • June 3, 2026
- **Plain-English labels on Forecast Accuracy charts.** Card summary now reads "Average forecast error by lead time" (was "MAE vs lead"), y-axis "Average error (°F)" (was "MAE (°F)"), x-axis "Hours ahead of forecast" (was "lead (h)"). Same data, less jargon.

## v0.6.25c • June 3, 2026
- **Per-layer accuracy section reframed as MAE-vs-lead chart per field.** v0.6.25/25b aggregated only at lead 0 — which is the one lead where the comparison is circular (the "observation" is the same-moment mesonet, so L2 forecast = L2 obs ≈ 0 error by construction). Now aggregates at ALL 48 lead bins over the 7-day window. Frontend rewritten from 4-row table to per-field MAE-vs-lead chart with 4 lines overlaid (Raw model, +Mesonet, +Decay, +Diurnal final). The gap between gray dashed (raw) and blue (final) at each lead = how much our pipeline reduces error at that forecast horizon. Lead 0 still shows ~0 for L2; lead 1+ is meaningful signal. Backend: `decay_fit.py` now writes `per_layer_mae_by_lead`, `per_layer_bias_by_lead`, `per_layer_n_by_lead` (each field × layer × 48-bin array) to `time_series_diagnostic.json`.

## v0.6.25b • June 3, 2026
- **Fix:** v0.6.25 per-layer MAE table showed L1 + L4 populated but L2 + L3 empty. Cause: `append_forecast_snapshot` was called from inside `compute_daily_extremes` BEFORE `apply_decay_corrections` ran, so the `*_post_l2` / `*_post_l3` intermediate arrays (which decay_apply stamps as side-effects) didn't exist yet at snapshot time. Moved the snapshot call out of `daily_extremes.py` and into `collector.py` immediately AFTER `apply_decay_corrections`. Legacy top-level snapshot keys (`t`, `h`, etc.) now explicitly set to `*_l2` values (was implicitly L2 from pre-decay timing) so the Fitter's decay-correction calibration is unaffected by the timing change.

## v0.6.25a • June 3, 2026
- **Fitter cadence bumped from once-daily to every 6 hours** during active build phase. Gate in `collector.py` changed from `now_local.hour == 3` to `now_local.hour in (3, 9, 15, 21)` — fires at 03:07/09:07/15:07/21:07 EDT. Each Fitter pass is ~$0.0001 in compute (truly free) and the daily-only cadence was leaving newly-deployed correction fields (pressure, cloud, per-layer tracking) un-fitted until next 03:07. Revert to `hour == 3` once the stack stabilizes.

## v0.6.25 • June 3, 2026
- **Per-layer MAE tracking for the Forecast Accuracy section.** Was: one MAE per field (final post-Layer-4). Now: 4-row table per field showing MAE after each correction layer (Raw → +Mesonet → +Decay → +Diurnal), with % improvement vs prior layer next to each. Answers the highest-ROI question — which corrections actually earn their keep vs polish noise. Five-file pipeline change: (1) `decay_apply.py` snapshots intermediate hourly arrays as side effects — `corrected_*_post_l2` (= what corrected_hourly built, pre-decay) and `corrected_*_post_l3` (= after decay, pre-diurnal). (2) `forecast_snapshot.py` captures per-hour forecast values at all 4 layers (`t_l1`, `t_l2`, `t_l3`, `t_l4`, etc., plus derived dew-point per layer via Magnus). Backward-compat top-level keys still written. (3) `forecast_error_log.py` emits `forecast_lN` and `error_lN` fields per pair when the snapshot captured them. Pre-v0.6.25 pairs silently lack per-layer detail. (4) `decay_fit.py` aggregates per-(field, layer) MAE and bias in 24h and 7d windows at lead 0, writes to `time_series_diagnostic.json::per_layer_stats`. (5) `corrections_debug.html::renderAccuracySection` rewritten as the 4-row per-field table with delta percentages — green for improvement, amber for regression.
- **Live Forecast Pipeline link added to the settings drawer's "How It Works" area.** New row pointing to `corrections_debug.html` so users can jump from the main app to the live layer-by-layer diagnostic view.

## v0.6.24 • June 2, 2026
- **Per-octant outlier trimming in Layer 2 aggregation** to defend against busted-sensor reads in sparse octants. Before: each octant's weighted mean included every contributing station; a single +5°F sensor in a 4-station octant could pull the octant mean by ~1.25°F and the network bias by ~0.16°F. Now: within each octant we first compute the median + median-absolute-deviation (MAD), drop any station whose value is more than `OUTLIER_K * 1.4826 * MAD` from the median (k=3.5 → ~4°F threshold for temp at typical spread), then take the weighted mean of what's left. Critical choice: MAD instead of std for the threshold — std gets inflated by the very outlier we want to catch (a +5°F sensor near +0.5°F median pushes std past its own deviation, protecting itself), MAD is unaffected. Skipped when fewer than 3 stations in an octant (can't detect outliers with <3 samples). Same trimming applied to humidity and pressure per-octant aggregations. New `hyperlocal.outliers_trimmed` field stamped each tick; surfaced on the debug page octant panel as "Outliers trimmed this tick: N".

## v0.6.23a • June 2, 2026
- **Print/PDF styling:** added `@media print` block to `corrections_debug.html` so the page is readable when printed or saved to PDF. Flips background to white, text to dark, hides the sticky TOC (useless in print), keeps section accent bars but at darker color, gives accuracy/info panels and cards white backgrounds with gray borders, and applies dark-on-light styling to the octant rose, bias offsets table, and stats text. Canvas charts can't be flipped (they're rasterized with dark theme baked into the bitmap) — those stay dark in PDF, but the surrounding text is now legible.

## v0.6.23 • June 2, 2026
- **Retuned Kalman gain thresholds for the v0.6.17 octant-scatter `bias_std` metric.** The old `_kalman_gain` thresholds (`std<1.0 → 0.9`, `std<2.0 → 0.65`) were calibrated for the pre-v0.6.17 per-STATION scatter (~30 individual stations disagreeing). Under v0.6.17's per-OCTANT scatter (8 geographic means of stations), values are tighter by construction — averages of averages — so typical std lands in 0.3–1.0 range, which always tripped the old "high confidence" bucket and pushed K to 0.9. This was over-applying the network bias: today's K=0.9 with old thresholds vs K=0.65 with new (matches yesterday's same-conditions value). New thresholds: `std<0.4 → K=0.9`, `std<0.8 → K=0.65`, else K=0.4 — preserves the same approximate fraction of days in each confidence bucket as the original calibration. One-line fix in `hyperlocal.py`.

## v0.6.22a • June 2, 2026
- **Forecast pipeline section headings made prominent.** Previously a small uppercase muted-color label, which was easy to miss when jumping via the TOC. Now: large 21px high-contrast text, accent left-border bar, subtle gradient background. Plus a 1.2s `:target` flash animation so clicking a TOC chip visibly punches the destination heading. Research section gets an amber variant matching its TOC chip color.

## v0.6.22 • June 2, 2026
- **Cloud cover added as the 8th correction field.** Same Layer 3 (decay) + Layer 4 (diurnal) treatment as the rest, no Layer 2 (no station network reports cloud cover, only METAR stations do). Six file changes wire it through: (1) `noaa.py::fetch_kbos_obs` now parses the METAR `clouds[]` array via a new `_metar_cloud_cover_pct` helper that maps NWS sky-condition codes to percent (SKC/CLR=0, FEW=12, SCT=38, BKN=75, OVC=100, VV=100) and takes the maximum coverage across all reported layers (NWS total-sky-cover convention). (2) `daily_extremes.py::_gather_current_observation` now reads `kbos.cloud_cover_pct` as the cloud observation instead of the meaningless model `cur.cloud_cover` (which was just the forecast paired against itself, giving zero error — useless to fit). No fallback to model: when KBOS is down, obs_log omits the cloud field for that tick and the Joiner skips it. (3) `decay_fit.py` adds `"cc"` to FIELDS. (4) `decay_apply.py` adds `"cc"` to TARGET_ARRAY (mutates `hourly.cloud_cover` in place), CAPS (40% sanity cap — cloud varies enough that we shouldn't allow corrections that can flip clear↔overcast), ROUND_DIGITS (0), FIELD_BOUNDS (0–100%). Also preserves `raw_cloud_cover` before mutation (same pattern as wind/POP). (5) `forecast_snapshot.py` captures `cloud_cover` per hour as `"cc"`. (6) `forecast_error_log.py` adds `"cc" → "cloud_cover"` to FIELD_MAP. `corrections_debug.html` FIELDS gets an 8th entry; cloud uses 0-digit display + 25% "good" MAE threshold. Cloud observation is from KBOS (~15mi south, also coastal — better-than-KBVY proximity for marine-layer dynamics, though still imperfect for Wyman-specific microclimate). Layer 3/4 cloud corrections start at zero and need ~24h of pairs to populate.

## v0.6.21a • June 2, 2026
- **Fix:** v0.6.21 pressure wiring read `hourly["pressure_msl"]` but `normalize_hourly` (which runs before `add_corrected_hourly_arrays`) had already renamed the key to `pressure`. Result: `corrected_pressure_in` and `raw_pressure_in` arrays were empty in the payload even though `hyperlocal.bias_pressure_in` was correctly populated. One-line fix in `corrected_hourly.py` to read the post-normalize key.

## v0.6.21 • June 2, 2026
- **Pressure now flows through all 4 correction layers** (was only Layer 2 before, applied to a scalar `corrected_pressure_in` value — not the hourly forecast array). Six file changes wire pressure into the same pipeline as temp/humidity/wind/POP: (1) `hyperlocal.py` now writes `bias_pressure_in` (network mean − model, in inHg, octant-balanced like the others). (2) `corrected_hourly.py` builds two new hourly arrays — `raw_pressure_in` (model `pressure_msl` converted from hPa to inHg) and `corrected_pressure_in` (raw + Layer-2 bias). (3) `decay_apply.py` adds `"pr"` to TARGET_ARRAY / CAPS (0.30 inHg sanity cap) / ROUND_DIGITS (3) / FIELD_BOUNDS (25.0–32.0 inHg physical limits). (4) `decay_fit.py` adds `"pr"` to FIELDS so the daily Fitter computes per-lead and per-hour-of-day pressure correction curves. (5) `forecast_snapshot.py` captures `corrected_pressure_in` in each snapshot under the `"pr"` short key. (6) `forecast_error_log.py` adds `"pr" → "pressure_in"` to FIELD_MAP so the Joiner pairs forecast pressure against observed station pressure (both in inHg). `corrections_debug.html` FIELDS gets a 7th entry; drill-down, raw grid, mesonet grid, decay/diurnal grids, and forecast accuracy section all populate for pressure automatically (pressure-specific 3-digit rounding + 0.05 inHg "good" MAE threshold added). Layer 3 (decay) and Layer 4 (diurnal) corrections for pressure will start at zero and shrink toward the historical mean as the Fitter accumulates 24h+ of pressure pairs.

## v0.6.20 • June 2, 2026
- **POP correction reverted to flat-additive** (v0.6.5 → v0.6.19 used piecewise-scaled). Offline Brier-score analysis (`analysis/pop_calibration.py`, n=131,320 pp pairs) found the piecewise-scaled approach was barely better than no correction at all (Brier 768.9 vs raw 782.8), while the original flat-additive was meaningfully better (Brier 745.4). The "inflates clear-sky hours" concern that motivated the v0.6.5 piecewise change turned out to be over-cautious — the existing [0, 100] clamp in `FIELD_BOUNDS` already prevents pathological inflation, and per-lead corrections shrink toward zero where the model is reliable. POP now uses the same simple `final = raw - correction` as every other field. `POP_NOISE_FLOOR=2.0` constant removed.

## v0.6.19 • June 2, 2026
- **Debug page promoted to "Forecast pipeline":** four-part renovation. (1) **Renamed** from "Corrections debug" to "Forecast pipeline" — the page outgrew its dev-tool branding. New tagline under the H1 explains what it is. (2) **Sticky TOC navigation** at top of page with chips for Accuracy / Drill-down / L1 / L2 / L3 / L4 / Research — jumps land cleanly below the sticky bar via scroll-padding-top. Color-coded chips for Research (amber) and Accuracy (green). (3) **New "Forecast accuracy" section at top** answers the question the page was missing: IS the forecast actually working? Per-field cards show near-term MAE (last 24h at shortest available lead), 7d MAE, day-ahead MAE (lead 24h), and recent bias direction (over/under). Each card auto-flags good (≥ field threshold) vs poor with a checkmark or warning glyph. (4) **Tide research split out:** moved sub-sections 3d (tide-phase) and 3e (error vs tide elevation) from inside Layer 3 to a dedicated "Research — experimental signals" section at the bottom, renamed R1 and R2. Layer 3 now contains only the three applied-correction sub-sections (3a fitted, 3b live with-vs-without, 3c historical fits). Cleaner separation between "this layer is in production" vs "we're investigating this." Backend unchanged.

## v0.6.18 • June 2, 2026
- **Debug page restructured to 4-layer model:** the conceptual stack collapses old Layers 2 (network bias) and 3 (Kalman) into a single new Layer 2 called "Mesonet corrections" — Kalman gain was always a confidence scalar inside the mesonet pipeline, not a peer correction. Layers 3 (decay) and 4 (diurnal) are the renumbered old Layers 4 and 5. New Layer 2 has four sub-sections (2a octant coverage, 2b network bias estimate, 2c network confidence/Kalman, 2d post-mesonet forecast grid) plus the per-station map + Kalman-tracked offsets in a collapsed accordion. The drill-down chart drops to 4 lines (raw → +mesonet → +decay → +diurnal); the pre-K vs post-K split that used to be its own line is no longer cross-layer relevant — that internal detail stays inside Layer 2's own sub-panels. All sub-section labels renumbered (4a-e → 3a-e, 5a → 4a). Backend unchanged — pure frontend reshape of the existing data.

## v0.6.17a • June 2, 2026
- **Fix: station_bias.py wasn't updated for the 2.5mi expansion** — `_weight()` still had a `dist > 1.5` cap and required `elevation_ft` to be non-None for Tempest stations, so the 43 new stations were silently filtered out before getting Kalman-tracked offsets, meaning they wouldn't appear in the Layer 3 bias map or offsets table. Raised cap to 2.5mi (matching `hyperlocal.py`) and fall back to `elevation_ft = ELEVATION_FT` when missing (no elevation penalty), same as the hyperlocal fallback. Also relaxed the Tempest filter in `_build_station_list` to no longer require `elevation_ft`. After this deploys, new stations will start collecting Kalman state immediately, but the offsets table needs the 48h rolling window to populate meaningful per-station deltas — full population in ~2 days.

## v0.6.17 • June 2, 2026
- **Layer 2 station network: 2.5mi expansion + octant-balanced aggregation:** WU station list grew from 29 → 56 (added 27 mostly Salem-side stations); Tempest station list grew from 9 → 25 (added 16). Distance cap raised from 1.5mi to 2.5mi in both fetchers (`wu_scraper_realtime.py`, `tempest.py`) and in `hyperlocal.py`. Open-Elevation API used to populate elevations for the 21 new WU stations not previously in the hardcoded lookup. **The real math change:** `hyperlocal.py` no longer does a flat distance²-weighted mean across all stations — instead it groups stations by compass octant (8 sectors, N/NE/E/SE/S/SW/W/NW), computes a weighted bias per octant (still using dist² × exp(-elev_diff/30) within each sector), then takes an unweighted mean across non-empty octants. This prevents the dense Marblehead-side PWS cluster from dominating just because more stations happen to live there — a sparse Salem-side octant with 2 stations now contributes equally to the network bias as a dense Marblehead octant with 12. Same outputs (`weighted_bias`, `bias_humidity`, `corrected_pressure_in`), same downstream wiring through Layers 3/4/5 — internal aggregation only. Falls back to flat-weighted mean when fewer than 3 octants have data (rare at 2.5mi/81-station catchment). New `hyperlocal` fields: `aggregation` ("octant_balanced" vs "flat_fallback"), `octants_used` (count 0–8), `octant_coverage` (dict of label→station_count per octant). `bias_std` now measures geographic disagreement between octants (was per-station scatter) — this feeds Kalman gain in Layer 3, so K is now responsive to directional disagreement as well as station count.
- **Wind blend gets the same treatment:** `wind_blend.py`'s `select_observed_wind` was previously `max(candidates, key=gust)` — a pure max across all stations. A single Salem-ridge station seeing an exposure-specific gust spike would set Wyman's whole forecast wind. Now: tag each candidate with its octant (model/KBVY land in a neutral None bucket), take the max gust within each populated octant, then the MEDIAN across those octant maxes. Result: a gust seen by 1 station out of 81 won't survive (gets median-filtered out), but a genuinely regional gust visible in multiple octants does. Falls back to flat max when fewer than 3 octants have wind data. New `current.wind_aggregation` field documents which mode each tick used.
- **Debug page octant coverage panel:** new compact 3×3 compass-rose visualization under Layer 2 showing how many stations fed each octant this tick (red = empty/gap, amber = sparse/1 station, green = ok/≥2). Plus footer line showing which aggregation mode (octant_balanced vs flat_fallback) and the wind aggregation mode. Surfaces the geographic-coverage health of the network at a glance — if a sector goes dark, you see it immediately.

## v0.6.16 • June 2, 2026
- **Layer 3 (Kalman) now actually scales the hourly forecast bias, not just the Right-Now reading:** Caught while wiring v0.6.15's drill-down — `corrected_hourly.py` was applying the full `weighted_bias` to the 48h corrected_temperature array regardless of Kalman gain K, while `hyperlocal.py` was correctly applying `K * weighted_bias` only to the single Right-Now temp. Two places computing the same thing, with the forecast side ignoring the confidence throttling. Fixed by routing the hourly forecast through `K * weighted_bias` to match. Few stations or high station-to-station scatter → low K → forecast moves less toward the network reading, which is the whole point of the adaptive layer. User-visible impact: forecast temps will shift by `(1 - K) × weighted_bias` from yesterday's values (typically a few tenths to a degree); the new values are more conservative and more honest about network uncertainty. Humidity, wind, and POP not touched — they don't have Kalman scaling in the Right-Now flow either, so this matches existing scope. **Drill-down updated:** the per-field drill-down chart on `corrections_debug.html` now has a fifth layer line ("+ Layer 3, Kalman-scaled bias") between Layer 2 and Layer 4. For temperature the L2 and L3 lines visibly differ by factor K; for fields without Kalman scaling (humidity, wind, POP) the L2 and L3 lines overlap, which itself is informative. New Layer 3 info panel on the debug page surfaces the current K value, the un-scaled L2 temp bias, and the actually-applied L3 temp bias side-by-side.
- **Debug page polish:** (1) Layer 2 and Layer 3 now each have their own grid of 6 small per-field charts (raw dashed + post-layer-bias solid), matching the Layer 1 raw-model grid added in v0.6.15. Lets you see at a glance what the forecast looks like after each correction layer is applied — for temp, the L2 vs L3 shift is visibly different (full -3.14°F vs Kalman-scaled -2.04°F); for fields without bias the solid overlays the dashed. (2) The Layer 3 per-station bias map + offsets table are now wrapped in a collapsed `<details>` accordion (a CSS-styled native one, no JS framework); calls `_biasMap.invalidateSize()` on toggle so Leaflet tiles render correctly when expanded from a zero-size container. (3) Sections 4d (tide-phase curves) and 4e (error vs tide elevation) now display an explicit "Diagnostic only — not currently applied to the live forecast" callout box at the top of each, in an amber color to distinguish from the green-go applied sections. Was previously implicit; users now know these are research/exploration, not active corrections.

## v0.6.15 • June 2, 2026
- **`corrections_debug.html` reorganized by correction layer + single-field drill-down:** Page is now structured top-to-bottom by the actual correction stack — Layer 1 (Raw model) → Layer 2 (Station network bias) → Layer 3 (Adaptive Kalman calibration) → Layer 4 (Decay curves, with sub-sections 4a fitted curves, 4b live with/without, 4c historical fits, 4d tide-phase curves, 4e error vs tide elevation) → Layer 5 (Diurnal hour-of-day, sub-section 5a historical fits). Every existing chart kept; just regrouped under the layer that produces it. New "drill-down" section at the top: pick one field (radio buttons), then toggle which layers stack visibly (checkboxes for Raw, +Layer 2, +Layer 4, +Layer 5 = final). Play button animates the build-up — each layer fades in 0.9s apart so you can see the model start raw and watch each correction transform it into the live forecast. Layer 1 also gets its own per-field grid of raw-model curves for completeness. Layer 2 gets a compact info panel showing the actual bias values being applied right now (temp/humidity/wind/gust offsets, station count, Kalman gain). No backend changes — pure frontend reshape of the existing data.

## v0.6.14 • June 2, 2026
- **Layer 5 — diurnal (hour-of-day) correction:** New `diurnal_corrections.json` + `diurnal_corrections_history.json` (365-day retention) written daily by `decay_fit.py`. 24 bins, one per local hour. Same exponential-decay recency weighting as Layer 4. `decay_apply.py` now also subtracts the per-hour-of-day correction from each forecast hour based on that hour's local clock time (parsed from `hourly.times[i]`). Same physical bounds clamp (wind ≥ 0, humidity 0–100, etc.). New `decay_meta` fields: `diurnal_fitted_at`, `diurnal_cells_corrected`, `diurnal_cells_capped`. **Important math choice:** the per-hour values are normalized to be mean-zero across the 24 bins so they don't double-count the overall mean error (which Layer 4 already captures). Layer 5 contributes only the deviation-from-average diurnal cycle, not the bulk bias. New Section 7 on `corrections_debug.html` renders the diurnal curves stacked across days, same pattern as Section 5. Built because the offline `analysis/tide_hypothesis.py` revealed the diurnal signal is much stronger and cleaner than the tide signal — afternoon under-prediction of temperature (-3 to -5°F at lead 24h), wind speed/gust (+5-10 mph), humidity (+15%).

## v0.6.13 • June 2, 2026
- **Cloud Function memory bump 512MB → 1024MB to fix OOM on the daily Fitter tick:** Today's scheduled 03:07 EDT tick crashed with `'Memory limit of 488 MiB exceeded with 507 MiB used'`. The combination of the regular collector + the Fitter doing multi-lead time-series accumulation + the new NOAA tide fetch + history-file load/append pushed the function over its 512 MB ceiling. Bumped to 1024 MB in `Makefile`. Cost impact negligible (each tick is ~30s, function pricing scales with memory × time). Verified Fitter logic itself is fine — ran cleanly when triggered manually. The real test is tomorrow's scheduled 03:07 tick.

## v0.6.12 • June 1, 2026
- **Real NOAA tide heights in Section 6, replacing the M2 cosine approximation:** `decay_fit.py` now fetches hourly harmonic tide predictions from the NOAA Tides & Currents API for Salem station 8442645 covering the time-series window. The tide overlay in Section 6 now shows actual Salem tide heights (peak-to-peak ~9 ft on typical days, ~12 ft on spring tides) instead of the old single-harmonic M2 cosine which was capped at ±4 ft. Falls back to the M2 cosine if the NOAA fetch fails, with `tide_source` field in the JSON documenting which was used. Section 5's reference cosine (still M2-only since the x-axis is *phase* not time) had its amplitude bumped from 4 to 5 ft to better match Salem's actual M2 component. The pre-v0.6.12 amplitude was visibly wrong — Salem tides regularly exceed 4 ft each direction.

## v0.6.11 • June 1, 2026
- **Section 6 lead-time selector:** `time_series_diagnostic.json` now contains per-hour mean error for 8 leads (0, 6, 12, 18, 24, 30, 36, 42h) instead of just lead 18h, under a new `errors_by_lead` key. File grew from ~9 KB to ~70 KB. Section 6 of `corrections_debug.html` gets a dropdown above the chart grid: pick which lead to render. Default 18h (where the offline tide hypothesis analysis showed the cleanest signal). Switching leads is instant — all data is loaded with the page; the dropdown just toggles which slice the 6 charts render. Lets the user explore whether the tide pattern is lead-specific (visible only at one lead) or general (visible across multiple leads). Backward-compatible read of the old single-lead `errors` key in case any pre-v0.6.11 payloads are still around.

## v0.6.10 • June 1, 2026
- **Wind gust floor + 4-layer doc reframing + annual curve retention:** Three small but real fixes in one commit. (1) `decay_apply.py` now clamps the corrected forecast values to physical bounds per field (wind ≥ 0, humidity 0–100, POP 0–100; temperature/dew-point intentionally unbounded). Without this, a large negative-sign correction at low raw values could push wind gust to negative mph. (2) `decay_fit.py` retention for `decay_corrections_history.json` and `tide_phase_corrections_history.json` extended from 30 days to 365 days so we can eventually watch curves evolve across a full annual cycle. Storage cost is ~3 MB/year per file — trivial. (3) `HOW_IT_WORKS.md`, `DATA_PIPELINE.md`, and `README.md` doc reframing from a 3-layer model (station bias / wind blend / decay) to a cleaner 4-layer model (raw model / station corrections including wind blend / adaptive station calibration / decay), separating the data-quality calibration step from the correction-application step. Wind blend is now correctly framed as a sub-method of Layer 2 rather than its own layer.

## v0.6.9 • June 1, 2026
- **Section 5 gets tide-elevation reference; Section 6 stays alongside:** Section 5's per-field phase-binned charts on `corrections_debug.html` now include a single gray reference cosine showing tide elevation across the M2 cycle (Salem M2 amplitude ~4ft, anchored to the reference high tide). Makes the x-axis interpretable at a glance: if the error lines bump up where the tide line bottoms out (around hour 6 since high tide = low tide), the bias tracks the tide. Section 6 (clock-time x-axis, error vs tide elevation over the last 7 days) stays alongside as the intuitive time-domain view. Two views of the same question — Section 5 is statistically rigorous (phase-binned, multiple days stacked), Section 6 is directly readable (do two squiggles oscillate together in real time). If both show the signal, it's robust.

## v0.6.8 • June 1, 2026
- **Section 6 — error vs tide elevation over time:** `processors/decay_fit.py` now also writes `time_series_diagnostic.json` — for each hour in the last 7 days, mean forecast error per field at lead 18h (the lead where the tide signal was strongest in `analysis/tide_hypothesis.py`) plus the approximate M2 tide elevation at that hour (single-component cosine model, Salem amplitude ~4ft). New Section 6 on `corrections_debug.html` renders this as 6 charts — one per field — with clock time on the x-axis, forecast error on the left y-axis, and tide elevation overlaid on the right y-axis. Read it as "do the two squiggles oscillate together?" — yes = tide drives the error, no = no signal at this lead/field. Complements Section 5 (the same question, statistically rigorous via phase-binning).

## v0.6.7 • June 1, 2026
- **Tide-phase decay curves + Section 5 historical watcher:** `processors/decay_fit.py` now also bins each pair by tide phase (12 bins across the M2 cycle of 12.4206h, anchored to a hardcoded Salem reference high tide) alongside the existing lead-h binning. Writes `tide_phase_corrections.json` and appends to `tide_phase_corrections_history.json` (30-day rolling) on every Fitter run. New Section 5 on `corrections_debug.html` renders one chart per field showing the historical tide-phase curves stacked, oldest pale gray → newest solid blue. The point of the historical view is the time-evolution test: stable curves across days → tide is the real driver; curves that drift across days → it's diurnal masquerading (because tide phase shifts ~50 min/day vs the 24h solar clock, so a clock-time pattern bins differently each day in tide-phase space). First fit shows clear humps at low-tide bins for wind speed (+3.8 mph) and gust (+9.3 mph), matching the lead-18h finding from `analysis/tide_hypothesis.py`. POP shows a dramatic −34% at the just-past-low-tide bin. Watching these stack over the next week will tell us if the patterns are physically real or alignment artifacts.

## v0.6.6 • June 1, 2026
- **POP reliability-diagram analysis script:** New standalone `analysis/pop_calibration.py` — same pattern as the tide-hypothesis script. Downloads `forecast_error_log.jsonl` + `decay_corrections.json`, replays every `pp` pair through three correction strategies (raw model / flat additive / piecewise scaled), bins resulting "corrected POP" against observed rain frequency, and renders a reliability diagram with Brier scores. CLI flag `--tau` tunes the noise floor for the scaled strategy. First run on ~80k pp pairs showed scaled is well-calibrated bin-by-bin but Brier-loses to flat because flat's aggressive mid-range boost partly compensates for a real ~25-point under-prediction the model has in the 30–60% range. Path forward when we have more post-storm data: tune T per data, or build proper isotonic regression.

## v0.6.5 • June 1, 2026
- **Piecewise-linear POP correction scaling:** `processors/decay_apply.py` no longer applies the flat additive POP decay correction. Previously, a fitted POP correction of −15% would push a raw 0% (clear sky) forecast to 15% corrected — claiming a 15% rain chance on what the model thinks is a definitely-clear hour. New formula scales the applied correction by the raw value: `applied = POP_NOISE_FLOOR + (raw_correction − POP_NOISE_FLOOR) × R/100`. At R=0 → applied ≈ POP_NOISE_FLOOR (= 2, a small "you don't know nothing" floor — and the clamp to [0,100] usually drops corrected back to 0). At R=100 → full raw correction applies. Linear in between. Only POP is scaled; temp/humidity/dew-point/wind/gust still use flat additive (no zero-floor problem there). Stopgap until we add proper isotonic regression or logistic POP calibration, which would learn the actual reliability curve from data. Bumping POP_NOISE_FLOOR to tune the noise-floor admission as we get post-storm data.

## v0.6.4 • June 1, 2026
- **Joiner emits pairs every tick, not just at top of hour:** `processors/forecast_error_log.py::_generate_new_pairs` dropped the `hour_key >= current_hour_iso` gate that held back obs from the in-progress hour. Pairs now flow into `forecast_error_log.jsonl` every 10-min tick instead of in hourly batches. Pairs are per-obs (not per-hour-aggregate), so emitting immediately is semantically identical to waiting — just smoother data flow. Compose appends jump from ~24/day to ~144/day; still well under the 5,300-component ceiling because the daily Fitter flatten resets it. The watermark in `forecast_error_state.json` now advances within the current hour instead of getting stuck at the prior hour's last obs. Pre-v0.6.4 the "wait for completed hour" rule was a vestigial state-machine simplification, not a correctness requirement.

## v0.6.3 • June 1, 2026
- **Section 4 age-color legend:** Each historical-curves card on `corrections_debug.html` Section 4 now has a small gradient-bar legend between the title and the chart — pale gray (oldest fit) → bold blue (newest), with the oldest and newest `fitted_at` timestamps labeled at the ends and a "hover line for date" hint at the right. Makes the color encoding readable without needing to know the rule.

## v0.6.2 • June 1, 2026
- **Decay-curve evolution watcher (history file + Section 4):** `decay_fit.py` now also appends each fit to `decay_corrections_history.json` in GCS — 30-day rolling, each entry is a full snapshot of that fit (fitted_at, n_pairs, weighting, corrections, n_samples). Storage cost is fractions of a cent per year. New Section 4 on `corrections_debug.html` ("Decay curves over time") renders one chart per field showing all historical fits stacked, color-gradient from pale gray (oldest) to solid blue (newest). Hover any line to see its fitted_at timestamp. Pairs naturally with the v0.6.1 recency-weighting — over the next 1–2 weeks you'll be able to watch the curves drift as nor'easter pairs age out and the post-fix humidity pairs gain weight.

## v0.6.1 • June 1, 2026
- **Recency-weighted Fitter (exponential decay, τ=14d):** `processors/decay_fit.py` now weights each pair by `exp(-age_days / 14)` instead of uniform 30-day window. Fresh pairs full weight; 10-day-old pairs ~half weight; 30-day-old pairs ~12%. Lets the fit track seasonal transitions (spring→summer is happening now) and recover faster from upstream data-quality changes (e.g. the May 31 humidity-bug fix in `obs_log.py` will dilute its contaminated pairs faster). Bin mean = `Σ(error × w) / Σw`. `n_samples` in output stays as unweighted raw counts for display. New `weighting` block in `decay_corrections.json` documents the parameters. Updated `docs/HOW_IT_WORKS.md` and `docs/DATA_PIPELINE.md` Piece-3 sections to match.

## v0.6.0 • May 31, 2026
- **Milestone bump** marking the completion of the full three-layer correction pipeline. The headline addition across the 0.5 series is the new Layer 3 (lead-time decay correction) system: a four-piece pipeline (Logger → Joiner → Fitter → Apply) that measures the model's own past forecast errors at every lead hour, fits a per-(field, lead_h) residual daily, and subtracts it from the user-facing 48-hour forecast each tick. Temperature, humidity, dew point, wind, gust, and precipitation probability are all now lead-time corrected with per-field sanity caps. Companion tooling: combined corrections debug page (`corrections_debug.html`) with fitted curves, live forecast with vs without decay, and a per-station bias map; PWA Corrections-card section showing the +24h adjustment per field; offline tide-cycle hypothesis tool (`analysis/tide_hypothesis.py`) with diurnal-control stratification; complete docs sweep (`HOW_IT_WORKS`, `README`, `DATA_PIPELINE`, `CLAUDE_RULES`); humidity-contamination bug found and fixed. Detailed per-version notes for everything in this milestone are below in the v0.5.229–v0.5.244 block.

---

## v0.5.229–v0.5.244 • May 31, 2026
* **obs_temp_log humidity fix — store station-corrected, not raw model (v0.5.244):** `_gather_current_observation` in `daily_extremes.py` was passing `cur.get("humidity")` (raw HRRR model) to `obs_log.py`. The Joiner then paired the snapshot's `corrected_humidity` (= raw + Kalman bias) against this raw "observed" value, so the Fitter saw the bias itself as "error" and Piece 4's decay correction effectively undid Layer 1 — humidity at lead 0 was getting +10% bias added and ~9% decay subtracted, netting ~0 change. Fix: pass `hyp.get("corrected_humidity")` (station-network value, falls back to `cur.humidity` if missing). Matches how `corrected_temp` is sourced two lines above. Dew point in obs_log re-derives from `corrected_temp` + `humidity` via Magnus, so it now uses two consistent corrected inputs instead of the mixed pair. Verified at the 20:27 EDT tick: `obs_temp_log` humidity entry = 96.6 (matches `hyperlocal.corrected_humidity`) where the previous tick stored 87 (raw). Dew point jumped from 50.1 to 53.4°F at the same tick, expected — magnus now consistent. Decay correction for humidity will drift toward the real residual over the next ~2 weeks as new corrected pairs dilute the contaminated ones in the rolling pair-log window.
* **Docs sweep + Chart.js version sync (v0.5.243):** `README.md` updated — "Cloud Run service" → "Cloud Functions (Gen 2)", "ECMWF 10-day" → "GFS 7-day", "29 stations" → "up to 29", processor list rewritten to group by correction layer (Layer 1 / Layer 3 decay / derived scores / helpers), added pointer to `corrections_debug.html` and `analysis/`. `docs/CLAUDE_RULES.md` re-synced with the root `CLAUDE.md` (was missing rules #11, #12, and the localhost-testing addition to #8). `docs/DATA_PIPELINE.md` got a new "DECAY PIPELINE (LAYER 3)" section detailing all four pieces, marked Improvements #1 and #2 as RESOLVED in v0.5.235, fixed the actively-wrong "Decay: NONE — Same bias applied to all 48 hours" claim in the Temperature forecast section, updated humidity forecast section to mention Layer 3, and refreshed the Correction Status Matrix to show Layer 3 columns. `corrections_debug.html` bumped Chart.js 4.4.1 → 4.4.4 to match `index.html`.
* **HOW_IT_WORKS rewrite (v0.5.242):** Total rewrite of `docs/HOW_IT_WORKS.md`. Replaces the implicit "single bias correction" model with the actual three-layer pipeline (station-network bias / wind blend / lead-time decay correction). New section explaining the decay-curve pipeline as four pieces (Logger / Joiner / Fitter / Apply). Updated source list (Open-Meteo HRRR+GFS, Pirate Weather, WU, Tempest, KBVY, KBOS, NWS gridpoints, GoMOFS, NOAA tides, eBird, Gemini with Groq fallback). New sections for fog/sea-breeze/thunderstorm detectors, tides, pressure trend, dock-day score, hair-day score. Removed the now-false "flat bias across all 48 hours" claim. Added pointers to the corrections debug page and the live data URL.
* **Station bias map on corrections debug page (v0.5.241):** Section 3 gets a Leaflet map above the table. One colored circle marker per station (with both lat/lng and a temp offset available), colored on a diverging hue scale (cool blue for stations that under-read, warm red for over-read, neutral gray near zero, clamped to ±3°F). Wyman Cove marked with a white-bordered dot at `42.5014, -70.8750`. Click any marker for popup with station_id, distance, and temp/day/night offsets. Legend in bottom-right. Map auto-fits to include all plotted stations + Wyman Cove. Tile layer is OpenStreetMap (free, no key). Spatial pattern visible at a glance — e.g., consistent warm-side bias clustering in one direction would point to a microclimate effect the Kalman tracker is already correcting.
* **Tempest distances in corrections-debug bias table (v0.5.240):** The new distance column was only checking `wu_stations.stations[]` and missing Tempest stations entirely (9 of 11 "blanks" were Tempests). Now also looks up `tempest.stations[].distance_mi`. Remaining blanks (~2) are genuine — WU stations the bias tracker has from the 48h history that didn't return data this tick.
* **Station distance column on corrections debug page (v0.5.239):** Section 3 (per-station bias) gets a new "Dist (mi)" column, populated from `weather_data.wu_stations.stations[].distance_mi`. Default sort is now distance ascending (nearest first) instead of |temp| descending. Click any column header to sort by it — distance/station sort ascending by raw value, bias columns still sort descending by magnitude. Stations without a distance match (e.g., Tempest stations) show "—" and sink to the bottom.
* **Tide vs diurnal stratification in analysis script (v0.5.238):** Extended `analysis/tide_hypothesis.py` to also bin errors by hour-of-day alongside tide phase, plus a stratified diagnostic. Per-field figure now shows two rows × 5 leads: top row = error vs M2 tide phase (existing), bottom row = error vs local hour-of-day (new). Side-by-side comparison surfaces whether a "tide" pattern is actually just diurnal aliasing (12.42h tide period vs 12h half-diurnal solar). New companion figure `stratified_<field>.png` per field: tide-phase error plotted as separate lines for each of 4 hour-of-day strata (night / morning / afternoon / evening). If all 4 lines share the same shape → tide is the real driver. If they differ wildly → diurnal is.
* **Tide-cycle hypothesis analysis script (v0.5.237):** New standalone `analysis/tide_hypothesis.py` — pure offline analysis, touches no app code. Downloads `forecast_log.json` (4 days of corrected 48h snapshots) and NOAA harmonic tide predictions for Salem (station 8442645). Synthesizes forecast-vs-observed pairs by treating each snapshot's `lead_h=0` entry as the "observation" for its run hour (extends usable obs span to ~99h vs the ~28h currently in the live pair log). Bins errors by M2 tide phase (12.42h period, 12 bins) at the observation time and renders one PNG per field showing mean error per phase bin across 5 leads (6/12/18/24/36h). First run produced 121,354 pairs spanning 8 tide cycles; preliminary signals visible in wind/gust and humidity at mid-leads but tide vs diurnal still confounded.
* **Corrections card decay section + combined corrections debug page (v0.5.236):** Weather-tab Corrections card gets a new "Forecast Decay Corrections ▾" collapsible below the existing Station Calibration Offsets, mirroring its style. Header line shows applied/fitted timestamps and cells-corrected count; mini-table shows the per-field correction at +24h lead (the most actionable forecast horizon); footer links to the full debug page. `decay_apply.py` now stashes `per_field_24h` in `decay_meta` so the PWA doesn't need a separate fetch. `wind_blend.py` snapshots `raw_wind_speed`/`raw_wind_gusts` before its in-place mutation, and `decay_apply.py` snapshots `raw_precipitation_probability` before its mutation — gives downstream (debug page) access to raw-model values for the three fields that get mutated in place. `decay_debug.html` renamed to `corrections_debug.html` (`git mv` preserves history); page title/h1 updated; Section 2 charts now show a third dotted "raw model" line (computed in JS via a port of `magnus_dew_point_f` for dew point, the others read straight from the new `raw_*` arrays); new Section 3 renders a sortable per-station bias-offset table covering all 34 stations across temp / temp_day / temp_night / humidity / pressure (the existing card shows only the top 8 temp offsets), plus a header stats panel with weighted_bias, kalman_gain, bias_std, and the KBVY anchor.
* **Decay-curve Apply + live-forecast debug view (v0.5.235):** New `processors/decay_apply.py` reads `decay_corrections.json` each tick and subtracts the per-(field, lead_h) mean error from the hourly arrays (`corrected_temperature`, `corrected_humidity`, `corrected_dew_point`, `wind_speed`, `wind_gusts`, `precipitation_probability`) — runs after `trim_hourly_to_current_hour` so array index == lead_h, and after the forecast snapshot is logged so the Fitter's residual stays a fair measurement. Sanity caps per field (5°F / 5°F / 20% / 10mph / 15mph / 25%) prevent any pathological future fit from blowing up the forecast. Falls back to a clean no-op if the corrections file is missing, malformed, or stale (>7 days old). After applying corrections, recomputes `corrected_apparent_temperature` and `corrected_absolute_humidity` from the now-corrected base values so derived arrays stay self-consistent. Stamps `weather_data["decay_meta"]` with `fitted_at`, `applied_at`, `cells_corrected`, `cells_capped` so the debug page can show whether decay was actually applied to the live payload. Debug page extended with a second section ("Live forecast — with vs without decay correction"): one chart per field overlaying the live forecast against the reverse-derived alternative line, with labels that adapt depending on the `decay_meta` state.
* **Decay-curve debug page (v0.5.234):** New standalone `decay_debug.html` (not linked from the PWA) fetches `decay_corrections.json` from GCS and renders one Chart.js line chart per field (6 total) showing mean error vs `lead_h`, with sample counts as a faint bar overlay on a secondary axis. Shows fitted-at timestamp, total pair count, and per-field |mean| summary. Renders an empty state if `decay_corrections.json` doesn't exist yet.
* **Decay-curve Fitter (v0.5.233):** New `processors/decay_fit.py` reads `forecast_error_log.jsonl` once a day (gated on the 03:X7 tick in `collector.main()`), computes mean signed error per `(field, lead_h)` bin across all 6 fields × 48 lead bins, and writes `decay_corrections.json` to GCS. Same pass also prunes the input to a 30-day rolling window and rewrites it as a single non-composed blob — resets the GCS compose component count back to 1 (Joiner's compose-append would hit the 5,300-component ceiling around day 36 without this). Streaming I/O via `blob.open` keeps memory bounded regardless of file size (~1.3 GB at steady state). Fitter call placed after the main `weather_data.json` upload so a slow Fitter cannot delay the user-facing payload. Piece 3 of 4 in the decay model; Piece 4 (Apply) waits for ≥1 week of fitted data.
* **Forecast-error Joiner (v0.5.232):** New `processors/forecast_error_log.py` pairs every 10-min obs entry against each `forecast_log.json` snapshot that predicted its hour, appending one row per `(obs × snapshot × field)` to `forecast_error_log.jsonl` via GCS compose (constant per-tick cost regardless of file size). Watermark tracked in `forecast_error_state.json`. First run produced 243,648 pairs across 6 fields. Foundation for the decay-curve fitter.
* **Collector refactor (v0.5.231):** AI briefing wiring tail moved from `collector.main()` into `briefing_ai.py` as `apply_briefing_to_weather_data(data)` (handles the try/cached_at/sources["gemini"] dance + failure path). Hourly-array trim block extracted into a new `processors/hourly_trim.py` as `trim_hourly_to_current_hour(data)`. collector.py 406 → 380 lines. Verified live by 8:57 run.
* **Frontend split (v0.5.230):** tab navigation extracted from `app-main.js` into `js/tab_nav.js` — `showTab` + swipe-nav IIFE + bottom-tab-bar sync wrapper + tab-restore IIFE, all four pieces moved together so the existing wrap-then-call execution order is preserved. app-main.js 983 → 835 lines.
* **Docs cleanup (v0.5.229):** stripped 23 stale code-line-number references from `DATA_PIPELINE.md` (most had been wrong for months — they pointed into `app-main.js` line 3787 etc., which hasn't existed since the file was split). Doc now uses file paths only as navigation; new note explains why. Updated stale version header. Also fixed the "Frontend" line in `CLAUDE.md` + `docs/CLAUDE_RULES.md` to reflect the modular `js/*.js` structure instead of just naming two files.

## v0.5.201–v0.5.228 • May 30, 2026
* **Frontend split (v0.5.228):** theme + pressure-unit helpers (~95 lines: `setTheme`, `applyTheme`, `updateSettingBtns`, `isLight`, `chartTextColor`, `chartGridColor`, `hpaToInhg`, `fmtPressure`, `rerenderPressure`, on-load IIFE) extracted into `js/theme.js`. app-main.js 1,071 → 983 lines — under 1,000 for the first time.
* **Frontend split (v0.5.227):** formatting helpers (`fmtLocal`, `fmtRelAge`, `toCompass`) extracted from `app-main.js` into `js/format.js`. Pure functions, no DOM or state. Loaded before app-main.js so they stay globally available. app-main.js 1,095 → 1,071 lines.
* **Frontend split (v0.5.226):** Right Now card render (~320 lines — every visible field, from big temperature and thermometer mercury through lifestyle scores) extracted from `app-main.js` into `js/right_now.js` as `renderRightNow(data)`. Done in 6 incremental chunks with localhost verification between each. app-main.js 1,416 → 1,095 lines.
* **Frontend split (v0.5.224–v0.5.225):** pressure-alarm + storm-mode logic (~60 lines) extracted into `js/alarms.js` as `renderPressureAlarm(data)` + `renderStormMode(data)`; NWS alerts panel + TEST-alert filter (~40 lines) extracted into `js/alerts.js` as `renderAlerts(data)`. app-main.js 1,513 → 1,416 lines.
* **Tooling fix (v0.5.223):** version pill was missed in the v0.5.222 commit due to an Edit ordering error; this commit catches it up.
* **Frontend split (v0.5.221–v0.5.222):** version-update detection + refresh-on-return (~78 lines) extracted into `js/version_check.js`; pull-to-refresh gesture (~64 lines) extracted into `js/pull_refresh.js`. app-main.js 1,654 → 1,513 lines.
* **Docs (v0.5.220):** consolidated same-day entries in `CHANGELOG.md` — May 27, May 28, and today's entries each collapsed into a single range header with concise themed bullets, matching the established format for earlier dates.
* **Right Now click-throughs (v0.5.215):** tapping a value field in the expanded Right Now card now navigates to the matching detail card; tapping outside the detail returns you to Right Now. Modal's `outsideHandler` was eating the synthetic click on the sibling target — fix dismisses the source's modal state before navigating.
* **Frontend dedup (v0.5.215–v0.5.217):** seven hyperlocal-link click handlers → one `wireHyperlocalLink()` helper; seven dimmed-suffix span literals → one `dim()` helper; twelve weather-art SVG conditionals → `WEATHER_GRAPHICS` lookup table with a `matchWeatherType()` precedence helper.
* **Collector formula consolidation (v0.5.201):** Magnus dew-point (4 copies) and Steadman feels-like (2 copies) collapsed into `utils.py` helpers.
* **Collector cleanup (v0.5.202):** 8 mid-function `pytz`/`datetime` imports hoisted; `_obs_log` initialized up front so the `NameError` catch goes away; unused `now_utc` removed.
* **Collector module extractions (v0.5.203–v0.5.214, v0.5.218–v0.5.219):** carved out of `collector.py` into focused modules — `wind_blend`, `corrected_hourly`, `gcs_io`, `obs_log`, `forecast_snapshot`, `daily_extremes`, `current_derived`, `fog_metrics`, `hourly_7day`, `normalize`, `stale_cache`, `fetch_parallel`, `fetch_all`. `concurrent.futures` and 16 now-unused fetcher imports removed. collector.py 1,653 → 406 lines (−76%). Zero behavior change throughout.

## v0.5.197–v0.5.200 • May 28, 2026
* **Collector:** obs_temp_log now records observed precip rate from WU rain gauges (replaces forecast model precip); WU aggregate also includes `precip_rate_in` and `precip_today_in` from station network. Earlier in the day: obs_temp_log added observed humidity and dew point (Magnus formula from temp + RH).
* **Forecast snapshots:** Each hourly entry now includes dew point (`dp`) and precipitation probability (`pp`) — enables POP calibration and dew point decay analysis alongside temp/wind.
* **Settings drawer:** "Data generated" always shows relative time ("just now", "5m ago") — previously switched to absolute time when a background refresh fired while the drawer was open.

## v0.5.190–v0.5.196 • May 27, 2026
* **Outside card (Lifestyle tab):** New card scoring current outdoor conditions — rain, wind, comfort (dew point), UV (hidden when unavailable) — with overall label (Great/Good/Fair/Poor/Stay inside), per-factor bars, and best-window hint when current conditions are poor. Pollen and AQI placeholders for future additions.
* **Forecast snapshot logger:** Collector now writes `forecast_log.json` to GCS each run — 48h corrected temp, humidity, wind speed, gusts — rolling 14-day window. Foundation for decay curve calibration.
* **UV in Watch For:** Briefing Watch For section now shows UV index when today's peak is ≥ 6 (high or above) — dimmed at 6–7, orange at 8–10, red at 11+. Hidden on low-UV days.
* **Watch For links:** UV and Heat stress rows now navigate to the Outside card on the Lifestyle tab when tapped.
* **Watch For layout fix:** Wrapped rows in brief-rows container so thin item dividers and thick section separator render correctly; UV label no longer dimmed.
* **UV Watch For time gate:** UV warning now only appears when UV ≥ 6 hours remain today — hides after the UV window has passed (e.g. evenings).
* **Briefing prompt fix:** Groq/Gemini no longer append "no change since last update" when forecast is stable — prior forecast is only mentioned when something shifted meaningfully.

## v0.5.184–v0.5.189 • May 23–26, 2026
* **Sunset scorer: horizon low cloud fix:** 50mi low cloud now weighted 60% in penalty calculation — a blocked distant horizon correctly scores Fair/Poor even when local sky is clear. Canvas bonus (mid/high cloud) only activates when the distant horizon is actually clear enough to back-light it.
* **Heat stress in Watch For:** WBGT computed from corrected wet bulb, temperature, and solar radiation — appears in briefing Watch For section when peak daytime WBGT ≥ 80°F, with Caution/Moderate/High risk labels
* **Rain intensity in briefing context:** Peak rain rate (in/hr) and label (drizzle/light/moderate/heavy/torrential) now included in Gemini/Groq precip context line
* **Sky & Precip chart intensity shading:** Rain bars shade from pale blue (drizzle) to dark blue (heavy) by hourly precipitation rate — intensity visible at a glance
* **Obs chart pressure smoothing:** 9-point moving average applied before scaling — eliminates staircase artifact from 0.01 inHg sensor quantization
* **Obs chart sky background:** Per-column cloud-cover gradient (same logic as 48h forecast) — collector now writes cloud_cover to obs log each run; x-axis label spacing fixed to prevent overlap near chart start
* **Sunset scorer: high cirrus fix:** highBonus cap now scales from 0.30→0.55 as horizon clears — high cirrus with a clear horizon correctly scores Very Good instead of Fair (ground-truth: May 26 dramatic cirrus sunset)
* **Collector crash fix:** forecast_text.py returns None when daily high/low are None — prevents TypeError during upstream Open-Meteo outages

## v0.5.182–v0.5.183 • May 22, 2026
* **Obs chart fixes:** Wind line changed to purple, dew point to vivid blue — distinct from teal gust bars; x-axis day label always shown at chart start; 6h tick labels now fire on entries at :07 instead of requiring exact :00
* **Almanac card previews:** Today card now shows Sunrise/Sunset times and daylight hours (was reading wrong data path); Frost Log now shows last freeze date, days since, and season freeze-day count (was reading nonexistent field)

## v0.5.171–v0.5.181 • May 21, 2026
* **Observed history chart:** New full-width card at the bottom of the Almanac tab showing past 24h of 10-minute observed readings — temp (orange), dew point (blue dashed), pressure trend (gray scaled), wind (teal dashed), and peak gust (teal bars). Data bar on hover shows temp, dew point, pressure, wind/gust, and wind impact label
* **Obs log redesign:** Collector now records a snapshot every 10 minutes (instead of one entry per hour) and keeps 24 hours of history. Each entry includes temp, precip, gust, wind speed, wind direction, dew point, and pressure
* **Wind impact in obs data bar:** Uses the real `combinedWindImpact` + `worryLevel` functions (with site-specific exposure table) to show impact label per reading when direction is available
* **Fog card atmospheric context:** Cloud base (~X,XXX ft), freezing level (X,XXX ft), and precipitable water (X.X mm) displayed as tiles above the fog card footnote
* **Low cloud cover in fog model:** HRRR `cloud_cover_low` feeds fog probability — +10% at ≥90% low cloud, +5% at ≥70%, −8% below 20%
* **Freezing level in precip type:** `freezinglevel_height` from HRRR overrides wet-bulb classification — >5,000 ft + wb>30 → rain; <1,500 ft + wb<33 → snow
* **PWAT in briefing:** Precipitable water ≥25mm logged in Gemini/Groq context when thunderstorms are active or on watch — "heavy rainfall rates likely with any storm"
* **Cloudflare Worker proxy:** `data.wymancove.com` proxies GCS bucket — fixes data loading in Firefox Focus and DuckDuckGo which block `storage.googleapis.com`
* **counter.dev analytics:** Replaced Microsoft Clarity (blocked by Safari ITP, useless for iOS PWA users) with counter.dev — privacy-friendly, works on iOS Safari
* **Sunset scoring fix:** Mid/high cloud with clear horizon now scores correctly — 0% low + 100% mid scores Spectacular instead of Poor. Low cloud is the blocker; mid/high cloud is the color canvas
* **Dead close button cleanup:** Removed 23 hidden `card-close-btn` elements from all cards and dead querySelector logic from ui.js

## v0.5.169–v0.5.170 • May 21, 2026
* **Briefing historical context:** Yesterday's high, precip total, and peak gust now logged in `obs_temp_log.json` and passed to Gemini/Groq prompt — model can frame today relative to yesterday without a hard rule (e.g., "sharp cooldown after yesterday's heat")
* **Groq model upgrade:** Fallback briefing model upgraded from `llama-3.1-8b-instant` to `llama-3.3-70b-versatile` for better prompt compliance (temperature ranges, no hallucinated context)
* **Stat box lining numerals:** `font-variant-numeric: lining-nums` on briefing stat values — fixes old-style figure misalignment where "7" sat visually lower than "8" in Playfair Display
* **Sky text font race fix:** Sky condition fit-sizing re-runs after `document.fonts.ready` — fixes stale small size on cold cache when Playfair loads after initial measurement
* **Source error labels:** Raw Python exception strings parsed to readable labels ("Connection reset", "429 Rate limited", "404 Not found", etc.)
* **Settings alert dot:** Now only lights for critical source failures (GFS, HRRR, WU, Pirate Weather, NWS Alerts, both briefing models down) — KBVY, KBOS, eBird, buoy, tides fail silently

## v0.5.159–v0.5.168 • May 20, 2026
* **Groq fallback (briefing):** Groq API (`llama-3.1-8b-instant`) added as fallback briefing generator when Gemini is unavailable; model tagged on every saved briefing; Sources card shows Gemini/Groq with active/standby indicator and age
* **Gemini no-redundancy rule:** Prompt now instructs model to ensure headline and subheadline carry different information — headline sets the story, subheadline adds detail
* **Briefing stale indicator:** Dim italic "headline from Xh ago" shown below headline when briefing is >90 minutes old
* **Corrections card bias:** Display now shows actual applied delta (corrected − model) rather than raw weighted_bias, correctly reflecting the Kalman-scaled correction
* **Wind briefing row:** Reformatted to "Light winds at the cove (9 mph NW, gusts 23)" — concise and location-specific
* **Birds briefing row:** "X species spotted nearby · Last 48h" format
* **Briefing lifestyle rows:** Numeric scores removed; label-only display (e.g., "Good hair day" not "Good hair day (78/100)")
* **Terminology audit:** mph spacing fixed throughout; MPH→mph; °F symbol normalized; Peak Impact, Risk Level, Last 48h capitalization corrected

## v0.5.145–v0.5.158 • May 19, 2026
* **Thunderstorm card:** New weather tab card with severity status (Clear/Watch/Active/Severe), CAPE current + 12h peak, color-coded hourly CAPE bar chart, lightning count and closest distance; click-through from Watch For rows and alert drawer
* **Thunderstorm detector (collector):** `processors/thunderstorm.py` computes severity from Tempest lightning (MAX across 9 stations, not sum) and Pirate Weather CAPE; `sky_override` sets condition to "Thunderstorm" or "Severe Thunderstorm" when active
* **Thunderstorm in alert drawer:** Watch/Active/Severe states appear in Active Alerts modal with click-through to thunderstorm card; alert badge dot lights up
* **Watch For ordering:** Lightning/thunderstorm row moved before precip bar so NWS alerts are never split by rain
* **Lightning count fix:** Was summing across 9 Tempest stations (9× inflation); corrected to MAX
* **Wind chart observed override:** Current hour substituted with hyperlocal observed speed/direction so chart reflects actual conditions during convective events (forecast direction can be wrong)
* **Gemini rain hallucination fix:** Explicit "No significant rain expected" signal sent when max POP < 20%, preventing stale storm context from carrying forward
* **CAPE chart:** Height increased 160→200px; layout padding added to prevent x-axis labels overlapping footnote; footnote top margin added for breathing room
* **Card close button artifact:** `.card-close-btn` default changed to `display:none` to fix flash on collapse
* **Fog dissipation timing:** Collector computes `fog_dissipation_hour` from 18h hourly fog probability; expanded fog card shows "Expected to clear by Xpm"; collapsed tile front shows "Clears by Xpm" when risk ≥20%
* **Fog card text color:** Dissipation line inherits card text color instead of hardcoded rgba(255,255,255,0.7) — readable in both light and dark mode
* **Briefing stat boxes:** Now/High/Sky boxes in briefing header click through to their respective cards
* **Settings relative times:** Data generated and code loaded times shown as relative ("3 min ago") instead of absolute timestamps
* **Feels Like consistency:** Briefing heat index row uses `der.heat_index` (Kalman-corrected) for display; shade AT falls back to JS computation if collector value missing
* **Heat index threshold:** Lowered RH threshold 40→35% so heat index activates in more conditions; Tonight briefing row click-through added; feelslike badge fallback improved
* **Update-reload loop fix:** Version check suppressed for 30s after an update-triggered reload to prevent infinite reload loop
* **Feels Like chart:** Three distinct lines — In shade (AT formula, solar=0), Full sun (AT + direct_radiation), Air temp; legend updated; "In shade" replaces "Feels Like" label for clarity
* **Gemini briefing:** Switched to gemini-2.5-flash (flash-lite returned 503); maxOutputTokens 200→2048 to accommodate thinking token overhead; in-memory backoff prevents retry storm on failure
* **Pirate Weather cloud cover fallback:** Sky/Precip card no longer goes blank when Open-Meteo HRRR is down; collector injects Pirate Weather 48h cloud cover as fallback

## v0.5.125–v0.5.144 • May 15, 2026
* Tab bar icons repositioned to sit flush above the home indicator on iOS (align-items: flex-start, safe-area bottom padding corrected)
* Lifestyle tab tab bar height normalized: min-height 100svh on all tab views prevents short-content tabs from rendering the fixed bar differently
* iOS tap highlight flash and long-press callout suppressed globally
* Tab button taps now animate with the same directional slide as swipe navigation
* Tab icon spring-bounce animation on tap
* Red alert dot appears on Briefing tab icon when active weather alerts are present
* Scroll position remembered per tab — returning to a tab restores where you left off
* Card body fades in on open (short slide + opacity animation)
* Pull-to-refresh: drag down from top of any tab to reload weather data; arrow indicator fades in and flips when past threshold
* Fixed tab bar jumping on page load: removed redundant showTab call that triggered iOS URL bar flash on every refresh
* Pull-to-refresh indicator refined: CSS border spinner replaces arc indicator; fixed position, light mode color, and tab bar jump on load
* Stale-while-revalidate: cached weather data rendered immediately on load from localStorage before network fetch completes; schema version guard prevents restoring incompatible data
* 10-day forecast: precip probability bar per row (filled by PoP%); wind label shown when Breezy or worse; fixed POP extraction to read field directly from collector output; fixed row alignment (fixed-width % column, flex-start to prevent tall rows shifting temps)
* Text selection (long-press menu) disabled globally for native app feel
* Sunset scoring algorithm improved: forward-weighted time window [0.15, 0.50, 0.35] so clearing trends aren't buried; low cloud color contribution term (partial low clouds catch horizon light from below); humidity penalty eased above 70% for coastal air
* Wine-scale scoring applied to sunset, hair day, and beach day: display = 50 + 50×(raw/100)^0.6 — compresses the floor, spreads meaningful variance into 75–100 range, matching user expectations from wine/school-grade scoring
* Beach day wind display: was showing "kt", corrected to mph
* Briefing tab lifestyle rows: switched to label-based color mapping for sunset, hair, and beach day (rgba passthrough was incompatible with the cm color-class map)
* Design pass: background deepened to navy (#0d1525); card opacity, blur, and border increased for better panel definition; tab bar active color changed from iOS blue (#0a84ff) to ocean teal (#3BAABD); briefing headline bumped 1.8→2rem; card border radius 18→22px; tile labels slightly more readable

## v0.5.122–v0.5.124 • May 14, 2026
* SVG tab icons replace emoji tabs across all four tabs
* Wind card tile redesigned: split compass/speed layout
* PWA manifest updated for wymancove.com custom domain
* Move notice banner added for users still on old GitHub Pages URL (only shown from jhselby.github.io)
* iOS card close bug fixed: tapping outside an expanded card now closes it without opening the card behind it; switched from backdrop click listener to document-level capture-phase touchstart/click handlers
* Corrections card moved from Lifestyle tab to bottom of Weather tab (col-6); collapsed tile shows station count and confidence level
* Birds card collapsed tile now shows "last 48 hrs" label

## v0.5.102–v0.5.121 • May 13, 2026
* Tempest stations expanded from 3 to 9 within ~1.5mi of Wyman Cove
* WU station list trimmed from 36 to 29 (removed 7 confirmed out-of-range stations)
* Station denominator now counts all attempted stations (29 WU + 9 Tempest = 38), not just responders
* Adaptive bias correction: new station_bias.py tracks per-station chronic offsets for temp, humidity, and pressure using leave-one-out consensus over a 48h rolling window; MIN_READINGS=6 before offset applied
* Temperature diurnal split: separate day/night bias offsets (7am–7pm ET boundary); captures sensors whose drift varies across the day
* Kalman gain blend: corrected_temp = model + K × weighted_bias; K = 0.90/0.65/0.40 based on station count and agreement; model contributes when stations disagree
* KBVY temp logged as external calibration anchor: kbvy_temp_f and kbvy_local_delta in hyperlocal output every run
* Tempest stations shown in Settings → Sources card
* Version update detection: refresh button dot lights up when a new deploy is available; polls version.json every 5 min
* Fixed version dot always showing (DOM timing bug — appVersion not yet in DOM at script execution time)
* Added How It Works prose doc to Settings → Under the Hood
* Corrections card extracted to js/corrections.js; per-station adaptive bias offsets table (tap to expand, top 8 by magnitude, warm=red/cold=blue); KBVY anchor line in expanded card
* Lightning alerts from Tempest network: Watch For row + Active Alerts modal when ≥3 strikes/hr or ≥1 strike within 20 km; badge lights standalone; red if close, orange if distant
* Wind compass tile: wind lull (min across Tempest stations) added below sustained speed; gusts top / sustained center / lull bottom layout
* Wind rendering extracted to js/wind.js (renderWindTile, renderWindImpactCollapsed, renderWindChart, renderWindRisk, initWindPills, buildWindChart)
* Tempest hardware wet bulb replaces Stull formula for corrected_wet_bulb (fallback retained)
* Fix: Next rain day label suppressed when minutely shows rain within 60 min
* Extract renderSun/renderMoon/renderSolarSystem to js/sky.js; renderSources to js/sources.js; renderBirds to js/birds.js; radar functions to js/radar.js; renderTides/buildTideChart to js/tides.js; renderFrostTracker to js/frost.js; renderSunsetQuality to js/sunset.js; renderHairDay to js/hair.js; renderDockDay to js/dock.js; renderBriefing to js/briefing.js; buildTempPrecipChart to js/tempchart.js; renderForecast to js/forecast.js; renderTodayAlmanac to js/almanac.js; renderSeaBreezeDetail to js/seabreeze.js; renderFeelsLikeCard/renderFogDetail to js/feelslike.js; populateCollapsedPreviews to js/previews.js; card toggle/nav helpers to js/ui.js; settings/alert/precip modals to js/modals.js
* app-main.js: 5,900 → 1,449 lines
* NWS Extreme/Severe alerts now headline over active rain in briefing priority
* Fog: advection fog now fires correctly when dew point spread is large (was dead code path)
* Sea breeze: minimum land/sea differential raised 3°F → 5°F; hard vetoes for offshore wind and winds >15 mph
* Wind blend: stale observations (>20 min) excluded from Tempest and WU candidates; direction sourced from best fresh waterfront Tempest station
* Watch For: red border/background for Extreme/Severe alerts; fog and sea breeze rows dimmed as informational
* Briefing dateline: data age ("3m ago") shown right-aligned
* Schema version check: app stops rendering and prompts refresh on mismatch
* Tab: Hyperlocal renamed to Lifestyle
* Settings: opening one accordion closes the others
* Collector: all print() replaced with logging.info/warning/error across 16 files
* Tests: 17 passing tests added for fog, wet bulb, and sea breeze processors

## v0.5.100–v0.5.101 • May 12, 2026
* Fix data refresh on Mac: add window focus listener alongside visibilitychange so Cmd+Tab back to browser triggers a reload (visibilitychange alone only fires on tab switches)
* Fix sunset score too low: clear-sky branch no longer requires low humidity (humid clear nights were scoring 1)
* Raise low-cloud overcast cutoff from 60% to 75% (patchy boundary-layer clouds were hardcoding "Poor"/10)

## v0.5.86–v0.5.99 • May 10, 2026
* WeatherFlow Tempest integration: fetches 3 public stations within 0.4mi of Wyman Cove (Willow Rd, Driftwood Rd, Neptune Rd) via tempestwx.com web API
* Tempest stations wired into hyperlocal temperature bias calculation and wind max-selection alongside WU stations
* Tempest humidity preferred over WU aggregate for corrected_humidity (closer, fresher)
* Corrections card now shows 27/32 stations (30 WU + 2 valid Tempest)
* Fixed UnboundLocalError in build_weather_data: datetime local variable shadowed by conditional imports
* Gemini fallback model updated from deprecated gemini-1.5-flash-8b to gemini-2.0-flash-lite

## v0.5.68–v0.5.85 • May 9, 2026
* Wet bulb and precip type classification (rain/snow/sleet/freezing rain) now fully corrected: both wet_bulb.py and precip_surface.py use corrected_temperature and corrected_humidity arrays throughout
* Updated DATA_PIPELINE.md: corrected stale placeholder/bug notes for wind speed, wet bulb, and feels-like; removed duplicate AI Briefing section
* build.py no longer creates index.html.backup on each run; deleted stale backup file
* Bias confidence indicator: shows correction amount and confidence level (Moderate=yellow, Low=red) below Feels Like when stations disagree; hidden when High confidence
* Removed dead NWS text forecast code: fetch_nws_forecast() from nws.py, renderNWSForecast() and nwsToggleExpand() from app-main.js, disabled collector references — replaced by forecast_text.py since v0.5.41
* Wind exposure table now single source of truth: collector embeds it in weather_data.json, frontend reads and updates from data on each load; JS fallback retained for offline/stale data
* Briefing click-throughs: Almanac rows (Sun, Tide, Moon) and Watch For rows now tap through to their detail cards
* Fixed fog+temperature double-period punctuation in forecast text
* Gemini briefing falls back to gemini-1.5-flash-8b on 429; both models configurable via env vars
* Briefing interval check now has in-memory guard (survives GCS failures; max-instances=1)
* Gemini briefing now receives previous headline as context; can note forecast shifts in subheadline
* Stale data indicator threshold raised from 20 to 25 minutes (fires only after 2+ missed collector runs)
* Briefing third stat changed from 48h rain to current conditions (sky text)
* All conditions displays now use weather_description (HRRR model) with condition_override (KBVY) as fallback
* Wind arrow redesigned: single line + arrowhead SVG; switched to SVG rotate() attribute to fix broken rotation in macOS PWA (WKWebView CSS transform-origin bug)
* Watch For storm flags: title now derives from most specific flag (freezing rain > snow > heavy rain > mixed > gusts > system > pressure)
* Watch For detail line now visible inline below alert/flag title without requiring a tap
* Precip flag no longer fires for rain on the surface — only for snow, sleet, freezing rain, and mixed
* Fixed collector crash: removed leftover forecast_data parameter; fixed missing WIND_EXPOSURE_TABLE import
* Fixed ReferenceError: conditions stat rendering placed before const cur declaration

## v0.5.66–v0.5.67 • May 8, 2026
* Exposure-aware wind narratives in forecast text ("Calm at the cove despite..." / "Windy at the cove...")
* Added wind_worry_score, wind_worry_label, wind_exposure_factor to forecast periods
* Removed "toward morning" noise from night lows; removed false-precision temp timing on GFS days
* Suppressed contradictory sky descriptions during heavy precip
* Days 8–10 now include ECMWF sky condition and gust data
* Fixed UnboundLocalError from shadowed datetime import; fixed "VRB" wind direction crashes

## v0.5.64–v0.5.65 • May 7, 2026
* Frontend fallbacks for Fog and Wind Impact tiles when GFS current data unavailable
* Collector fallback: HRRR hourly[0] for fog when GFS fails
* Briefing rain stat shows three states: "No rain", "Trace" (POP ≥ 40% but zero accumulation), or inches
* TODAY section: High / Low row shows full temp range without scrolling
* Forecast text now always prefers corrected data; fixed false "Chance of rain" from GFS fallthrough
* 10-day rain icons now driven by corrected data upstream

## v0.5.54–v0.5.62c • May 6, 2026
* **Rain Stat (v0.5.62)**
  * Shows "Trace" instead of 0" when precip is measurable but rounds to zero
  * Trace stat correctly sized (1.8rem) and vertically centered
  * brief-stat cells flex-centered for consistent alignment
* **Briefing Tab Restructure (v0.5.61)**
  * WATCH FOR floats to top (below stats) when active; static HTML order replaces runtime DOM reordering
  * New ALMANAC section (sun rise/set, next tide, moon phase) split out from TODAY
  * Fog and rain rows removed from TODAY — covered exclusively by WATCH FOR
  * "No alerts" quiet note suppressed — WATCH FOR div simply empty when inactive
  * Separator line spacing normalized between WATCH FOR and TODAY
* **Briefing Tab Improvements**
  * Storm alerts (pressure/trough/wind/precip signals) now appear in Watch For section
  * Precip mini bar in Watch For when rain is imminent — taps to open full precip modal
  * Watch For moves above Lifestyle whenever it has any content
  * Tonight section now shows detailed forecast text from forecast_text.py
  * Rain stat label clarified to "rain · next 48h"
* **Gemini Briefing Prompt**
  * Wind Impact score reframed as authoritative hyperlocal measure; numeric score stripped from payload
  * Gemini decides when to mention contrast with regional forecast
  * Cloud Function max-instances=1 — prevents concurrent execution and 429 rate limit collisions
* **Feels Like / Apparent Temperature**
  * Implemented Steadman radiation formula using Open-Meteo direct_radiation (cloud-attenuated)
  * Radiation formula used when direct_radiation > 0; falls back to shade formula when overcast/night
  * Q = direct_radiation × 0.17; applied to both current feels-like and 48h hourly array
* **Wind Compass**
  * Arrow tail made full opacity and extended; tail dot removed for cleaner direction reading
* **Collector / Data Pipeline**
  * Sunset directional cloud fetches reduced from 5 days to 3 — eliminates Open-Meteo 429 errors
  * direct_radiation added to HRRR hourly pipeline (replaced shortwave_radiation)

## v0.5.43–v0.5.53 • May 5, 2026
* **Feels Like Overhaul**
  * Replaced piecewise NWS wind chill / heat index with continuous Steadman shade formula
  * Eliminates 50–80°F dead zone; collector computes corrected_apparent_temperature for all 48h
  * Feels-like chart reads from collector (single source of truth); Wind Chill / Heat Index labels removed
* **Water Temperature**
  * Now sourced from GoMOFS (Gulf of Maine Operational Forecast System), grid point Salem Channel (~1.5mi)
  * Buoy 44013 retained as fallback; ocean card and Beach Day scoring both updated
* **Briefing Tab**
  * Watch For: alerts move above Lifestyle; alert rows simplified, tap to open modal
  * Gemini prompt rewritten — geographic context, exposure table, conditional data, token reduction
  * Precip threshold: <20% POP = no mention; 20–30% minor; 40%+ featured
* **Collector Cleanup**
  * Corrected hourly dew point, absolute humidity, wet bulb all computed in collector
  * Dead JS functions removed: calculateWetBulb, dewPointF, absHumidity, dockWindScore
  * Dead tempBias parameter removed from forecast renderers
  * Settings modal resets subsections on close
* **Beach Day**
  * Now uses combinedWindImpact (exposure model) instead of custom dockWindScore

## v0.5.42 • May 3, 2026
* Fixed 13 broken HTML attributes where `class` was inside `style` — elements now get proper theme-aware colors in light mode
* Fixed settings theme buttons not syncing active state (wrong IDs)
* Fixed precip badge lighting up without probability check — now matches modal's ≥30% threshold
* Renamed "Swim Float" card to "Beach Day"
* Redesigned wind compass arrow — full-length through center with gap for speed number, extends past circle, bolder styling
* Removed dead code: `toggleSettings()`, `toggleMenu()`, `toggleMenuSection()`, duplicate `updateForecastSelection()` call, test comment
* Removed hidden meta-row, rewired timestamps to settings modal directly

## v0.5.41 • May 2, 2026
* **Meteorological Audit — 7 fixes across precipitation, forecast, and resilience**
  * Surface precip type (wet bulb) now used everywhere instead of 850mb column type
  * 850mb override catches all frozen/mixed types when surface temp > 40°F
  * Fixed precip_surface.py dead code — never returned "rain"
  * Fixed HRRR/GFS handoff dropping Monday from 7-day forecast
  * Days 8-10 forecasts now use temp-based precip type
  * 7-day GFS data now gets wet bulb and surface precip processing
* **Processor Improvements**
  * Sea breeze uses corrected hyperlocal temp for land/water differential
  * Added advection fog detection (warm moist air over cold water) — primary coastal fog type
  * fog.py now returns fog_type (radiation vs advection)
* **GFS Failure Resilience**
  * Hyperlocal temp correction works when GFS model temp unavailable (uses WU station weighted average)
  * Briefing AI falls back to cache when current temp missing/zero (prevents 0°F briefings)
* **Frontend**
  * Active weather alert shows both surface and column precip types
  * App returns to briefing tab after 5+ minutes away; always opens on briefing
  * Sunset quality score smoothed with 3-hour averaging window (reduces model wobble)

## v0.5.33 • May 1, 2026
* **Tile & Briefing Fixes**
  * Beach/hair day tiles switch to tomorrow at sunset (was hardcoded 6 PM)
  * Fixed briefing sunset score reading from wrong data source
  * Fixed "undefined (undefined/100)" when sunset score unavailable
  * Fixed swim float card showing wrong day after 8 PM EDT
  * Fixed tide calendar grouping using UTC dates

## v0.5.25–v0.5.28 • April 30, 2026
* **Briefing Polish**
  * Tomorrow scores (sunset, beach, hair) display correctly after civil dusk
  * Clickthrough navigation for all "(tomorrow)" rows
  * Rain rows suppressed when accumulation is 0"
  * Next-hour rain indicator triggers on any precip intensity
* **Collector**
  * Switched Gemini from deprecated 2.0-flash-lite to 2.5-flash-lite
  * Added missing `import re` to fetcher files
  * Temperature ranges sent to Gemini to prevent hallucinated exact temps
* **Overhead**
  * Zoomed out to capture BOS approach traffic
  * Plane info overlays map instead of pushing content down

## v0.5.19 • April 29, 2026
* **Bug Fixes & AI Briefing**
  * Fixed wind impact constant mismatch between frontend and backend
  * Guarded precip_850mb against missing hourly key
  * AI prevented from saying "no rain in sight" when rain is imminent
  * Pirate Weather minutely precip signal added to briefing
  * Cloud Function secured with OIDC auth
  * Data Sources moved to settings with health status dots
  * Lazy-load overhead.js on card tap

## v0.5.17–v0.5.17c • April 27–28, 2026
* **Single Source of Truth for Temperatures**
  * Collector computes `derived.today_high/low` from observed past + corrected forecast
  * Observed temp log (`obs_temp_log.json`) tracks hourly corrected readings
  * All display paths read from `derived` — eliminated 6+ redundant bias computations
  * Corrected dew point and feels-like computed once in collector
  * Forecast text uses derived high/low
* **Gemini Briefing Discipline**
  * Wind impact score is authoritative; raw speed demoted to context
  * Tomorrow high/low sent to prevent invented temperatures
  * Test alert filtering in frontend and Gemini input
* **Infrastructure**
  * Open-Meteo calls sequential (rate-limit sensitive); non-OM calls parallelized

## v0.5.0–v0.5.15 • April 25–26, 2026
* **Briefing Tab — AI-Powered Weather Briefing**
  * New first tab: Gemini headline + subheadline, stat boxes, conditional data rows
  * Template fallback when AI unavailable
  * Cross-card navigation: tap any row to open its detail card
  * Lifestyle section: sunset, beach day, hair day scores
  * Watch For section: wind impact, frost risk, fog, sea breeze alerts
  * Sun/tide/moon/birds rows
  * Wind chill and heat index display
* **PWA Install Prompt**
  * iOS action sheet style; Android native beforeinstallprompt
* **Settings**
  * Changelog, data pipeline, licenses behind "Nerd Stuff" toggle
  * Bird hotspot links open in OpenStreetMap

## v0.4.78–v0.4.82 • April 21–24, 2026
* **Hair Day — Hair Type Selector**
  * Four profiles: Straight, Wavy, Curly, Coily with tuned AH curves and wind thresholds
  * Wind scoring added (10% weight) using first-bad-hour logic
  * Restyle opportunity detection
* **Birds Card**
  * eBird sightings grouped by hotspot, sorted by distance
  * Notable species highlighted; clickable links to eBird and maps
* **Tab Reorganization**
  * Weather tab: objective data and forecasts
  * Hyperlocal tab: derived scores and curated metrics
  * Feels Like, Fog, Sea Breeze moved to Weather tab
* **Sea Breeze Fix**
  * 0% likelihood no longer shows as "No data"
  * Collapsed tile shows actual wind direction

## v0.4.65–v0.4.77 • April 20–21, 2026
* **Hair Day Card**
  * Scoring based on Absolute Humidity with inverted-U curve (sweet spot 4-5 g/m³)
  * Morning-weighted aggregation; precip type matters (snow/freezing rain penalized more)
* **Card Modal System**
  * Fixed-position modal with backdrop, max-height with internal scroll
  * Measured header/tab bar heights for correct positioning
  * Tap backdrop or Escape to dismiss
* **Pirate Weather Next Hour**
  * Fixed false triggers on raw intensity when probability is 0%
  * Always-visible header badges with colored dot for active state
* **UI Polish**
  * Card open animation smoothed (removed bouncy overshoot)
  * Dead top tab nav HTML removed
  * Right Now card lifestyle scores show /100 format

## v0.4.50–v0.4.61 • April 18–20, 2026
* **Pirate Weather Integration**
  * Minutely precip, solar irradiance, CAPE
  * Next-hour rain badge with 60-bar chart and plain-language summary
* **Feels Like Card**
  * 48-hour Chart.js line chart with hover data bar
* **Sunset Headline**
  * Plain-English summary above day grid
* **Infrastructure**
  * GCS migration: collector on Cloud Functions + Cloud Scheduler
  * weather_data.json served from GCS bucket
  * Stale page indicator (gear/refresh turn red when data >2h old)

## v0.4.34–v0.4.48 • April 12–18, 2026
* **Corrected Values Audit**
  * All display paths use corrected temp, humidity, wind, pressure, dew point
  * Forecast temperatures corrected for today and tomorrow
* **UI/Native App Polish**
  * Fixed header with frosted glass effect
  * Storm alerts consolidated into badge modal
  * Swipe-down to dismiss settings and alert modals
  * Gradient backgrounds persist into expanded cards
* **Scoring Refinements**
  * Dock Day: below 50°F scores 0, thresholds raised
  * All scores unified to 1-100 scale
* **Station Network**
  * Expanded from 15 to 36 WU stations

## v0.4.0–v0.4.33 • March 31 – April 12, 2026
* **Comprehensive Hyperlocal Correction System**
  * All derived values use corrected data (wet bulb, feels like, dew point, precip type)
  * Wind gust corrections blended into 48h forecast with 24h decay
  * Tab reorganization: Wind and Radar tabs removed, Hyperlocal Corrections tab created
* **Collapsible Tile System**
  * All cards converted to col-6 tiles expanding to modal overlays
  * Preview data in collapsed state; localStorage persistence
* **NEXRAD Radar**
  * Switched from RainViewer to IEM NEXRAD WMS (5-min updates, 2h history)
* **Chart Redesign**
  * Sky conditions as per-column background gradients
  * Precip bars colored by type; 6-hour x-axis ticks
* **iOS-Style Bottom Tab Bar**
  * Frosted glass nav, swipe between tabs
  * Settings as slide-up modal sheet
* **Moon Phase**
  * Canvas-rendered moon replacing emoji
* **Tides Card**
  * 3-column calendar layout with next-tide indicator

## v0.3.1–v0.3.18 • March 21–30, 2026
* **Forecast Text Generator**
  * NWS NBM gridpoint integration for temperature overrides
  * 850mb precipitation type classifier
  * Wet bulb temperature display
  * Morning/afternoon cloud split for sky narratives
* **Wind System**
  * Wind chart redesign (time horizontal, speed vertical, worry zones)
  * Max(KBVY, WU) for current conditions; observed wind blended into forecast
  * Wind exposure thresholds tuned for waterfront
* **Overhead Tab**
  * Live aircraft tracker with Mapbox map
  * Route validation, private aircraft detection, selected plane highlighting
* **48-Hour Chart**
  * Sky condition bars, touch-action fixes, consolidated data bar

## v0.2.0–v0.2.77 • February – March 18, 2026
* **Modular Collector Refactor**
  * Split monolithic collector.py into fetchers/ and processors/ packages
  * Processors: fog, frost, hyperlocal, pressure, sea breeze, trough, wet bulb, wind risk
  * KBOS/KBVY migrated to Aviation Weather API; buoy wind data added
* **Smart Hyperlocal Corrections**
  * Distance + elevation weighted bias from WU stations
  * Quality filtering: stale data rejection and outlier detection
* **Sea Breeze Detector**
  * Terrain-based wind exposure table from contour map analysis
  * Wind impact cards with forward-looking peak windows
* **Core Features**
  * 10-day forecast with NWS integration
  * Gust & sustained wind impact cards
  * Frost & freeze tracker
  * Dock Day Score with tide-window scoring
  * Sunset Quality forecast
  * RainViewer radar
  * Light/dark/system theme toggle
  * Mobile responsive layout

## v0.1.0 • Late 2025
* **Initial Build**
  * Multi-model weather (GFS, HRRR, ECMWF via Open-Meteo), tides, buoy, NWS alerts
  * Multi-tab layout (Weather / Wind / Almanac / Radar / Sources)
  * KBOS / KBVY / PWS observed conditions
