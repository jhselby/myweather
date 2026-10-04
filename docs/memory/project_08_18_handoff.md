---
name: 08-18-handoff
description: "HANDOFF — 2026-08-18 session ran out of tokens mid-workstream. NEXT SESSION MUST DO THE WORK ENUMERATED BELOW without re-litigating decisions. Joe has explicitly stated he does not want to have this conversation again. This is a directive, not a plan to negotiate."
metadata: 
  node_type: memory
  type: project
  originSessionId: 23b5871a-fdee-47f7-9ac1-9e9135a084ab
  modified: 2026-08-18T15:35:13.491Z
---

# 08-18 handoff — read this FIRST at session start

Joe has explicitly directed that the next session **just do the work**, not re-litigate the decisions from today's session. Every decision below is settled by 2026-08-18 session unless it turns up empirically wrong when the code runs. Do not re-ask, do not re-verify posture, do not offer menus.

## What's settled from today's session

1. **Frame audit is done.** 6-week correction-stack plateau diagnosed as symptom of daily digest being a closed loop over the pair log. Full context in [[feedback_frame_exhaustion_watch]] and [[project_plan_pipeline_to_good]] (rewritten today with Item 0 = input-frame expansion).
2. **v0.6.431 is shipped and deployed** (commit 459a4da, deployed to `myweather-collector-00505-ded` — actually revision advanced past 505 by now). Adds NWS gridpoint (NBM-derived) values to snapshot as `{short}_nws` for t/dp/pp/ws/wd. Pair log now emits `forecast_nws` + `error_nws`. Decay-fit aggregates NWS in `per_layer_mae_by_lead`.
3. **Prior AI consultations (ChatGPT, Gemini) + human forecaster consensus landed on HRRR** as the raw source. Joe surfaced this late in the session. **The NBM-may-beat-HRRR narrative I ran for hours was overconfident.** Realistic outcome from the benchmark is likely middle-of-the-road, not a full reset. Do not repeat the "retire 70% of the stack" story unless data supports it.
4. **Persistence gates (chp / clp / dpbp / wdp) are structurally orthogonal to NBM** — they use recent obs, NBM does not. Do not include these in any retirement list on duplication grounds.
5. **Confidence layer (C1) machinery is orthogonal to NBM.** Not in scope for retirement.
6. **Wyman-Cove-specific specialists** (mesonet L2, Lsb sea-breeze, marine layer detector, buoy blends, GoMOFS water temp) exploit signal NBM structurally cannot access. Not in scope for retirement.

## What Joe wants done in the next session — DO NOT ASK, JUST DO

### Task 1: Install grib parser + validate

```
# Try in order until one works:
pip3 install --user xarray cfgrib eccodes         # cleanest for macOS
# OR
brew install wgrib2                                # fallback if pip route fails
# OR
pip3 install --user pygrib                         # last resort — needs system libgrib_api / libeccodes
```

Validate by pulling one NBM file and extracting a single value at Wyman Cove lat/lon. Wyman Cove coordinates: **LAT / LON in `weather_collector/config.py`** (do not hardcode — read from config).

NBM file URL pattern (confirmed accessible today):
```
https://noaa-nbm-grib2-pds.s3.amazonaws.com/blend.YYYYMMDD/HH/core/blend.tHHz.core.fLLL.co.grib2
```
Where HH = run hour, fLLL = lead in hours (001-036 hourly, then 3-hourly to 192).

### Task 2: Read actual NBM documentation

Before writing any retirement plan or asserting what NBM does internally, verify:
- NBM v4.x methodology paper (NOAA MDL) — does NBM apply per-cell diurnal bias correction? Per-cell lead-time-varying bias?
- NBM field coverage table — what fields does raw NBM expose that NWS gridpoint API filters out? (Especially cc/cl/cm/ch, sr, wg, pa.)
- NBM's handling of coastal grid cells — is there documented weakness at land-water boundaries?

Do this reading before speaking. Every "NBM does X" claim from 2026-08-18 was speculation; the next session must ground each claim in the actual docs.

### Task 3: Historical NBM backfill + benchmark

1. Pull 7 days of hourly NBM runs from AWS for Wyman Cove grid cell (~168 runs × 48 leads × 5-7 fields; extract one grid cell only, do not download full grib content into RAM — use `xarray.open_dataset` with `backend_kwargs={"filter_by_keys": {...}}` for lazy extraction, or use grib subset service).
2. For each existing pair-log row (`obs_time`, `run_time`, `field`), look up the NBM forecast issued at that `run_time` (or nearest prior) with valid time covering `obs_time`. Store as new `forecast_nws_hist` field per row (do NOT overwrite the live `forecast_nws` that v0.6.431 is stamping forward — keep them distinct so we can compare live-fetch NWS-gridpoint vs. historical-raw-NBM).
3. Enrich existing pair log with these historical values in a side-cache (don't rewrite the pair log itself).
4. Run `analysis/h_nws_gridpoint_benchmark.py` (already written today) — extend it to handle both the live `forecast_nws` and the backfilled `forecast_nws_hist`.
5. Report per-field: NBM alone vs raw HRRR (L1) vs full stack (Production). Halves stability check per the script.

### Task 4: Present the numbers, then propose action

Only after Tasks 1-3 produce actual numbers:
- If NBM crushes HRRR on multiple fields → propose the L1 router (route those fields through NBM).
- If NBM ties or loses → the frame-audit narrative was overreach; the plateau is HRRR-ceiling not baseline error. Say so directly.
- If NBM wins on 1-2 fields → narrow router, keep most of the stack.

DO NOT propose a full stack retirement. DO NOT propose 70%-of-work retirement. Numbers decide, per-field.

## Behavioral rules for the next session (Joe's explicit today)

1. **Session start: load project state proactively.** Read [[feedback_session_start_load_project_state]] + [[project_correction_stack]] + [[project_plan_pipeline_to_good]] + most recent session log + `ls weather_collector/fetchers/` BEFORE responding to the first substantive prompt.
2. **No menus.** [[feedback_no_choice_menus]] + [[feedback_stop_after_minimum_ship]]. Pick and execute.
3. **Verify before asserting.** Every code claim from an actual `grep` or `Read`, not a comment or plausibility. [[feedback_check_contamination_before_acting]] + CLAUDE.md #4. The 2026-08-18 L4 error (called it "regime × lead_band" from a SKIP-table comment; it's actually diurnal hour-of-day) is the paradigm case. Same failure mode also produced the "regime change is untried" error and the "NBM does per-cell diurnal correction" over-claim.
4. **Frame-exhaustion watch is now live** ([[feedback_frame_exhaustion_watch]]). Check triggers at session start.
5. **Ship count by impact class** ([[feedback_ship_count_by_impact_class]]). Categorize honestly. Do not count today's v0.6.430 (no-op safety net) or v0.6.430a/b (debug page text) as skill ships.
6. **Digest review must include debug page** ([[feedback_digest_review_includes_debug_page]]). Staleness banner lives there, not in `DIGEST.txt`.

## Do NOT waste tokens on the next session by

- Re-asking what fields matter to Joe (answered: all 14, treated equally; primary horizon 48h, secondary 10d)
- Re-verifying that hobby frame applies (settled, [[project_hobby_vs_product]])
- Re-litigating whether the frame audit was needed (it was; also unrelated to whether NBM specifically wins)
- Re-explaining what NBM is or arguing that HRRR "should" be replaced without the benchmark numbers
- Offering "want me to X?" trailers after any action

## What's live and safe to leave alone

- Chp / cc combine walkers running on their 7-day gates (background)
- dpbp watch CLOSED CLEAN 08-18 (settled)
- Lc recent-bias gate armed for ch (v0.6.430)
- v0.6.431 forward accumulation of NWS gridpoint values

## Related — must-read handoff context

- [[project_plan_pipeline_to_good]] — rewritten today with Item 0a at top
- [[feedback_frame_exhaustion_watch]] — the pattern being watched for
- [[feedback_ship_count_by_impact_class]] — the categorization to enforce
- [[feedback_session_start_load_project_state]] — the session-start ritual
- [[feedback_stop_after_minimum_ship]] — the anti-bait rule
- [[feedback_digest_review_includes_debug_page]] — the staleness read
- [[project_dp_is_derived_no_dp_work]] — dp architectural stance
- [[project_correction_stack]] — layer-by-layer inventory
- [[feedback_co_owner_posture]] — co-owner behavior, not intern posture
- CLAUDE.md — project-wide rules, especially #4 (verify) #7 (don't invent) #12 (don't flip-flop)

## Explicit user directive at session end

Joe said: "DO it all stop wasting my time. Your job is to answer the question we're asking. Cue that up for a new session and don't forget anything we've discussed here."

The next session's job is Task 1 → Task 2 → Task 3 → Task 4. Do the work. Report numbers. Propose action grounded in numbers, not narrative.
