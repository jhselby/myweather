---
name: project-10-10-session
description: "10-10 morning triage. Refitter 04:30 clean; new learned sr cell frontal/24-47 (n=478). t/production@12-23 sentry is a 7d window — rolls off ~10-14, not 10-10. cc Stage 0 edge reversal deepened (4d -53.7%). nbm_walkforward 'l3_nbm ADD wd' is a validator false divergence (wd is live via the circular branch)."
metadata:
  node_type: memory
  type: project
  originSessionId: e0e28537-09d0-459b-9a87-65bb62fa2659
  modified: 2026-10-10T11:14:09.320Z
---

# 10-10 session (morning triage)

- **Refitter 08:30Z** (rev `00005-qez`): all tables published. Learned sr cells now `frontal/24-47` (NEW, n=478, held-out A +19.0% / B +21.6%, thinnest live cell), `ne_flow/12-23`, `se_flow/12-23`. `nw_flow/12-23` + `/24-47` STABLE in the fit but held off by LIVE_DEMOTED. Selector table: 4 overrides, 0 pick changes.
- **t/production@12-23h +13.3% (n=1958):** same stale-override tail as [[project_10_08_session]]. Pair log by obs day: loss is all 10-06 (+44.7%, 252 NBM rows) and 10-07 (+48.8%, 269 NBM rows); 10-08 +2.2%, 10-09/10-10 served == raw (all HRRR). The layer-shape sentry reads `time_series_diagnostic.json` with `window_days: 7`, so the 10-08 "rolls off by 10-10" applied to the 3d fresh fire only. This line clears ~10-14/15. No action.
- **cc derived-max Stage 0:** overall PROMOTE +45.5% still carried by 09-26..10-02; last 4d −53.7% (n=247), last 7d −24.5% (n=1125). Reversal deepened from 10-09. Do not advance.
- **chp cloud gate:** 11 cells off. `pre_frontal/6-11` still 6/7 lose (today +41.3%) — win day not aged out yet.
- **Override walkforward day 5:** override FLAT −0.3%, daily refresh +1.1%, 14d-stale −2.6%. Supports the daily cloud refit.
- **wdp calm/12-23:** unchanged from 10-09 (n=429 both days, −18.0%, half B +13.7%).
- **Blender dp:** 10-09's `pre_frontal/24-47` STABLE day 1 → UNSTABLE today. Stage 1 HOLD.
- **lsr_recent_bias sr:** PROMOTE, streak 1/7, CHURN. Hold.
- **wg nor_easter/12-23 skip ADD CONFIRMED:** halves −0.00/−10.90, third time with a degenerate half A (10-03, 10-09). Do not ship.
- **nbm_walkforward "l3_nbm: ADD wd":** false divergence. `nbm_walkforward_validator.LIVE_WHITELIST["l3_nbm"]` is built from the scalar `L3_NBM_FIELDS = ("wg","ch","sr")`; wd l3_nbm is live through `l3_nbm_wd_components` (forecast_snapshot.py:908). "DROP wg" is wg aggregate +0.8% < 2% bar (09-14 precedent: no action).
- Pair-log anomaly alerts fire WATCH on 10 fields (dp +44%, pr +34%, h +20%) while the regression sentry is clean — not dug into.

## Shipped
- **v0.7.39** (`305a88b3`): `nbm_walkforward_validator` LIVE_WHITELIST l3_nbm now includes wd. Divergence line reads `DROP wg` only.
- **v0.7.40** (`90785610`): `l1_selector_fit_by_regime` + `l1_selector_fit_3way` label rows with `_cache.RegimeRuntime`. New `RegimeRuntime.prime(paths)` pre-pass. **Why:** the live pair log writes wd second-to-last in each tick (order t,ws,wg,h,dp,pr,cc,sr,pa,cl,cm,ch,wd,pp), so streaming observe+get fell back to synoptic on 64–87% of rows. Primed: 0.3–1.2%. v2/v5 read the backstamped GCS file and weren't affected (0 / 1.4% fallback). Any new streaming consumer of `pair_log_paths()` must call `prime()`.
- Refitter deployed and run 19:30Z, 10/10 published. Live by-regime overrides (cloud, 8): dp ne_flow/12-23 nbm, dp sw_flow/12-23 nws, h ne_flow/12-23 nbm, h ne_flow/24-47 nbm, h sw_flow/0-5 hrrr, h sw_flow/6-11 hrrr, t frontal/24-47 nws, ws frontal/24-47 hrrr. Walker history mixes synoptic- and runtime-labeled days until ~10-12.
- **v0.7.41** (`73363ef6`): both by-regime fitters now fit `nor_easter` + `stagnant_high` (were folded into `unknown`, which the runtime never looks up). First fit flags t/stagnant_high/0-5 nbm, sr/stagnant_high/24-47 hrrr, NWS on dp/stagnant_high/24-47, ws/nor_easter/12-23 + 24-47, pp/nor_easter/12-23 (n 78–215). None live until the walker's 3-day gate (~10-13 at the earliest, weather permitting).
- Refitter redeployed + run 23:00Z, 10/10 published. Live overrides now 5: h ne_flow/12-23 nbm, h ne_flow/24-47 nbm, h sw_flow/6-11 hrrr, dp sw_flow/12-23 nws, ws frontal/24-47 hrrr. The three that left since 19:30 are NOT from v0.7.41: t/frontal/24-47 nws (30d window roll, n 637→622, h1 6.3→2.1% < 3%), dp/ne_flow/12-23 (masked — 23:00 selector refit flipped pooled dp/12-23 hrrr→nbm), h/sw_flow/0-5 (h1 flipped to +16%).
- **Tick verify 19:07 EDT (23:07Z):** every hour where a live cell applies fired `regime_override` with the right source (h/sw_flow/6-11 → hrrr leads 7–10, h/ne_flow/24-47 → nbm leads 29, 43). Per-hour stamps live in `gs://myweather-data/forecast_log.json` (`snapshots[-1].hours[i]`: `regime_runtime`, `{f}_selector_source`, `{f}_selector_mechanism`), not weather_data.json.
- Collector logs show `PWS error: Expecting value` every tick since at least 03:07Z 10-10, plus intermittent Open-Meteo 429s on the 10/25/50mi cloud pulls — predate today's ships, not investigated.
- Next in the migration: blender fitter + `l1_static_blend_shadow_verify`, then wdp.
- **v0.7.42** (`134d71df`): the four blender tools (`l1_blender_stage1`, `l1_blender_retro_score`, `l1_blender_shadow_verify`, `l1_static_blend_shadow_verify`) on primed `RegimeRuntime`. Static verify: live cells h/nw_flow/24-47 +49.7% (n7 608), h/sw_flow/24-47 +22.7% (n7 1,116); 87 applied rows had been scored in non-live h/calm/24-47; curated 13/6/1/0 → 14/5/1/0, h/nw_flow/12-23 still KILL (shadow). Per-obs Stage 1 STABLE h calm/24-47, h pre_frontal/6-11, dp calm/24-47 were label artifacts. Shadow verify t/se_flow/24-47 SHIP-READY → HOLD. Running static verify locally publishes to `gs://myweather-data/l1_static_blend_shadow_verify.json` (debug page).
- **v0.7.43** (`abb52eea`, collector deployed 02:43Z 10-11): one per-lead regime label. `state_stamp.runtime_regime_by_lead()` writes `derived.regime_runtime_by_lead` (after decay_apply, before wdp, collector.py ~703); wdp, wdp_nbm, selector and blender all read it (snapshot falls back to its inline classify only if the array is missing). Offline it matched the snapshot's stamped `regime_runtime` 48/48; first live tick 02:47Z: snapshot == array 48/48, wdp `state_fc_source` = `derived.regime_runtime_by_lead`, old `state_fc_by_lead` differed on 5/48 leads (ne_flow vs nor_easter), selector overrides still firing. Old wdp label: raw arrays, no cloud cover, `hourly["time"]` typo (key is `times`) → never sea_breeze.
- wdp tools on RegimeRuntime: live cell `calm/12-23` n 430 → 267, composed −18.0% → −22.7%, halves −45.3/+33.6 (was −28.4/+13.7). Stage 2 still HOLD; live wdp table (frozen in repo) unchanged. Watch: calm/12-23 now fires less often; half B already loses.
- `state_fc_by_lead` is still computed in state_stamp (and logs `transitions=`) but has no runtime consumer now — removable later, typo included.
- regime_runtime migration is DONE for selector walker, learned fitters, blender, wdp.
- **v0.7.44** (`git log` — learned features; collector 02:57Z + refitter 02:58Z 10-11, refit run 03:00Z): runtime `_build_learned_features` reads wd/ws/cl/sr from the snapshot entry (signature now `(field, i, ims_i, valid_hour_local, derived, cross_run_spread, times, entry)`); v5 solar = sr row's `forecast_l2` joined on (run_time, valid_time) (410,920/416,215 rows). **Why:** `state_fc.solar_wm2` is post-swap — NBM terminal when sr routed NBM — so it encoded the selector's own pick; runtime never saw that value. Same-data result: sr `frontal/24-47` (A +19.0 → −0.9) and `ne_flow/12-23` (A 8.6 vs B 17.6) were riding it and dropped; live learned cells now **`sr/ne_flow/6-11` + `sr/se_flow/12-23`**. 03:17Z tick: se_flow/12-23 firing `learned_gbm` on 12 leads (probs 0.06–0.76).
- Still misaligned (not live): t/h v2b see pre-swap ws/wd at runtime vs post-swap state_fc in training; xr_spread = pair-log cross-run max−min in fitters vs `cross_run_spread` module at runtime.
- 03:07Z 10-11 tick was an Open-Meteo outage (HRRR, GFS fallback, GFS 7-day all timed out; stale hourly with UTC times) → regime_runtime None on every lead that tick. Not a code bug; 03:17Z healthy.

## Carry-forward (next session)
- ~10-11: ch router re-read (pull cells losing to always-HRRR at n≥150, see [[project_10_04_session]]).
- 10-13: TEMPORARY nor_easter skip reviews — wd l3_nbm v0.7.24, sr bypass v0.7.11.
- ~10-13: by-regime walker nor_easter/stagnant_high cells reach the 3-day gate; check which go live.
- Watch wdp calm/12-23 (half B loses on runtime labels).
- ~10-24: backstamp prune.
- Optional: delete dead `state_fc_by_lead` in state_stamp; align t/h v2b features + xr_spread definition before any t/h learned cell goes live.
- Uninvestigated: PWS "Expecting value" every tick, Open-Meteo 429s, pair-log anomaly WATCH on 10 fields.
