---
name: project_07_17_session
description: "07-17 Fri marathon: Lc FLIPPED v0.6.355 + same-day Lc attribution wiring v0.6.356 + joiner 6× dedup fix + sr Lsb Stage 3 + h_ws_octant 07-17 SUGGESTIVE + candidates-table cleanup. 6 versions shipped."
metadata: 
  node_type: memory
  type: project
  originSessionId: 43be4b0e-1ee6-46ca-95b4-e8e62a53c216
---

**Fri 07-17 marathon** — 6 versions (v0.6.354 → v0.6.356c).

## v0.6.354 — Joiner snapshot dedup + curl cache + sr Lsb Stage 3 wired

Morning digest hung 25 min at `anomaly_detector` on a 40 MB urllib stall against the 2.5 GB pair log. Killed the hung download; curl-pulled the file at 24 MB/s. Digest completed 109/109 pass. Two fixes:

- **Joiner snapshot dedup** (`forecast_error_log.py:285`) — pair log had grown to 2.5 GB because 6 snapshots per run hour (:07/:17/…/:57) cache the same underlying HRRR output and pair against the same obs. Every `(obs_time, field, lead_h)` triple appeared exactly 6× in the file. Fix keeps only the earliest snapshot per run-hour. Pair-log volume drops to ~400 MB as the 30-day retention rolls. Fitter n's stop being inflated by 6× (CIs artificially tight by √6 ≈ 2.5×). Deployed at the 06:37 tick.
- **`analysis/_cache.py` urllib → curl** — see [[feedback_pair_log_download]].
- **sr sea_breeze Lsb Stage 2 PROMOTE** — Stage 1 (+43.7%) cross-cut showed the win was cloud-conditional inside sea_breeze: cc 0-25 SHIP (+25.1%), cc 25-50 SKIP (-44.2%), cc 50-75 SKIP (-42.8%), cc 75-100 MARGIN (+34.3%). Stage 2 gates (cc<25) OR (cc≥75): pooled +25.27%, halves +29.0%/+21.5%, lead-band 3 SHIP + 1 MARGIN + 0 SKIP. **PROMOTE.** Stage 3 wired at `sr_sea_breeze_lsr_override.py` as new operator **Lsb**, ENABLED=False. Halves re-run 07-24. Weekly Sun re-reads through 07-31.

## v0.6.355 — Lc FLIPPED

See [[project_lc_flip_outcome]]. Preconditions all cleared, first tick 113 cells fired. 14-day watch through 07-31.

## v0.6.356 — Lc attribution wiring (same-day catch)

After the flip Joe noticed the accuracy per-band table for cc/cl/cm/ch still showed only `L2 n/a · L3 off · L4 ✓`, no Lc column — the same silent-attribution class of bug Lsr's v0.6.249 fix documented. See [[feedback_specialist_attribution_wiring]] for the durable lesson. Six coordinated edits (backend + frontend). Lc promoted from R&D `gated-candidates` subsection into its own top-level layer section `sec-lc` between Lsr and Research, mirroring Lsr's 5-block structure. Verified on live snapshot post-deploy: cc_l4=0, cc_l6=16 (+16 pp shift), cc_applied=l6.

## v0.6.356a — Brier dropdown gate + calendar reorder + h_ws_octant 07-17

- Accuracy-over-time chart: Brier metric option now grays out when field ≠ pp (was silently kicking back to prior metric).
- Calendar re-anchored chronologically after my 07-31 Lc-watch-close addition drifted between 07-17 and 07-18.
- **h_ws_octant_bias 07-17 read: ⚠ SUGGESTIVE.** 2 REAL octants (E +1.84 mph, S +0.99 mph HRRR over-forecast), 2 WATCH (NE, SW calm-flip), 4 flat. Not enough across-octants signal to justify per-octant L2 additive correction yet. Re-read counter: 1 of 3 (07-17 ✓ · 07-24 · 07-31).

## v0.6.356b/c — Candidates table cleanup

Joe reviewed the debug page's "Stage 1 candidates" section (stale title — held items across all pipeline stages) and pushed two structural improvements:

- **356b**: added a Stage column, ordered rows by stage, added stage-key legend to the intro. Also picked up two stale-content fixes: **sr sea_breeze Lsb** row added (was only mentioned in the footer), **cl persistence gate** row corrected (was still labeled Stage 1+2 HOLD; actually Stage 3 shipped 07-13 v0.6.330 in `cl_persistence_short_lead.py`), **per-octant ws L2** row picked up today's 07-17 SUGGESTIVE read inline.
- **356c**: removed the 5 Stage 4 LIVE rows from the candidates table (Lc, C1f, K-taper, cc→L4, C1e) — already documented in their own layer sections + Group D refinements, so keeping them in the candidates table was noise. Table now shows in-flight only: 6 Stage 3 + 4 Stage 1 + 1 Stage 0, ordered earliest stage → latest. Fixed the sr Engineering row: was "Unit-mismatch open," updated to "Unit-mismatch addressed, not yet live" with Lsb Stage 3 context (sandbox stamps candidates but ENABLED=False, so production sr is still Lsr-on-direct-radiation until the 07-24 halves re-run gates the flip).

**Post-Fitter verification (15:08 EDT):** l6 populated on cc/cl/cm/ch as expected. First 4 leads have data (Lc only live ~3h at that point); leads 4-47 null until pair-log volume accumulates. Production line still ≈ L4 for cc/cl/cm/ch because most 7-day pairs are pre-flip — expect crossover to L6 over ~1 week as Lc-era pairs dominate the rolling window.

## What ships when

- **sr Lsb**: halves re-run 07-24; flip after weekly Sun re-reads confirm halves stability. Ship gate mirrors ch/wg/cl persistence pattern.
- **Lc 14-day watch closes 07-31.** Watch triggers documented in [[project_lc_flip_outcome]].
