---
name: project-hypothesis-backlog
description: "Stage 1 hypothesis backlog — 08-11 hygiene pass. Active: 5 numbered items (1,2,3,5,6,7,8; #4 SHIPPED). Marine-layer dormant per MLC diagnosis. Framing rule unchanged: C1 axes by default, bias layers only when L2/L4 overlap is ruled out."
metadata: 
  node_type: memory
  type: project
  originSessionId: a933ef0e-f53e-46b4-802a-0d1b833732d0
  modified: 2026-08-17T14:06:03.543Z
---

## Framing (unchanged from 2026-06-20)

Most candidates fold into C1 as orthogonal confidence axes, not standalone correction layers. Bias candidates need to demonstrate they're not double-counting L2/L4 first.

**Why:** C1 (originally numbered L6 — renamed 2026-06-21) is now at v3 with 4 axes (transition, cluster spread, pressure tendency, c1f). Multi-axis confidence aggregation is its growth path. Adding more bias layers post-C1 raises the "isn't this just a noisier L4?" question every time.

**How to apply:** When evaluating future hypothesis candidates, default-classify them as C1-axis-extension vs L3/L4-style-bias before scoping a script. Bias candidates need to demonstrate they're not double-counting L2/L4 first.

## Method-fix backlog (added 2026-07-22)

- **`h_hsf_orthogonality.py` — matched-regime baseline.** Current script compares post-frontal MAE to global baseline MAE. In regime-imbalanced windows (like a sea-breeze-dominated summer), baseline mixes elevated-error regimes and post-frontal mixes cleaner cold-front-cleared airmasses, so post/baseline ratios invert and the verdict flips KILL for artifact reasons. Fix: pair each post-frontal (field, band) sample against baseline samples in the same synoptic regime. See [[project_c1e_hsf_kill_investigation]] and [[feedback_measure_against_live_stack_baseline]]. Same fix pattern likely applies to `h_pre_front_orthogonality.py` and any other ortho script that uses a global-baseline denominator.

## Stage 1 queue — 6 active candidates (post 2026-06-24)

**TIER 2 — stability proof needed before architectural commitment:**

1. **Cloud saturation-unbiasing** (Group D). cl 95-100% has -57.5pp bias (was -63.4 on 06-23); cc/cm/ch all show 31-55pp ceiling biases. Direction-stable across 2 reads. Genuinely new architecture — no existing layer conditions on forecast value. Manual re-run: `analysis/h_cloud_floor_ceiling.py` weekly. Promote if cl 95-100 stays ≤-50pp across 3 weekly reads.

2. **C1e bidirectional (time-relative-to-front)** — **HELD 08-11 hygiene pass.** Fresh `h_pre_front_orthogonality.py` re-run collapsed from 16 ortho cells (June read) to **2 SHIP cells** (`ch 24-47h`, `cl 24-47h`). Footer: `[n=3 passages, 7% join → THIN]` — only 3 frontal passages in the window, most cells have `vs_c1a: None` from thin data. Signal likely a spring-thunderstorm-season artifact; mid-August has few fronts. Re-run in autumn when front cadence returns.

3. **cm → L4 ride-along** (borderline). 06-23: +2.7%. 06-24: +3.0%. Sits at the 3% ship floor edge. Single-line edit to `L4_FIELDS` when it clears 2 consecutive reads ≥3%.

4. ~~**KBOS-vs-KBVY cloud disagreement / cluster_spread persistent logger**~~ — **SHIPPED**. Persistent logger built (`cluster_spread_log.json`), axis_2 (`cluster_spread_q`) live in `c1_confidence_calibration_v2.py` since 2026-06-20. Cross-run spread (a distinct intra-model spread signal) also cleared Stages 0-3 on 08-11 and sits ready for Stage 4 wiring — see [[project_cross_run_spread_c1_axis]].

**TIER 3 — need more evidence:**

5. **C1h trend-direction widening** (Group A). cl rising +999% but n only 194. Direction-stable across 2 reads but small-n. Manual re-run: `h_trend_direction.py` over 30d window in 2-3 weeks. Promote if cl rising stays ≥+500% AND ortho vs C1f/C1e.

6. ~~**Regime-conditional dp depression**~~ — **SHIPPED** as `dpbp` v0.6.391 (08-04). Gate: pre_frontal/nw_flow/sw_flow + lead ≥ 6h + prev_24h_dp_bias < −1.5°F → +2°F. Pooled dp MAE 3.108 → 2.808. See [[project_dpbp_live]]. Original writeup below preserved for the attribution methodology.

  ~~Attribution gate CLEARED 2026-07-28 v0.6.383a~~ — extended `h_dewpoint_depression.py` with per-regime t-bias/dp-bias split. Three DP-DOMINANT ★ regimes surfaced with consistent ~−2°F dp under-forecast: **pre_frontal** (t +0.54, dp −2.14, n=19,621), **nw_flow** (t +0.27, dp −2.20, n=45,589), **sw_flow** (t −0.49, dp −2.34, n=20,034). Frontal is BOTH-COMPOUND (t +1.47, dp −1.63, n=2,232) — model imagines warmer/drier post-frontal than shows up. sea_breeze/ne_flow/se_flow all BOTH-CANCEL. Physical read: model under-predicts moisture in shear/turbulent-mixing regimes. **Still blocked on direction-stability watch** — 06-24 aggregate depression bias flipped signs in frontal/ne_flow/sea_breeze over 5 weeks; unknown whether the DP-DOMINANT attribution held across those flips or is a July-only pattern. Attribution is only 1 read as of 07-28. Next gate: weekly re-run for 2-3 weeks; if the 3 DP-DOMINANT regimes stay DP-DOMINANT ★, warrants Stage 1 (dp-side regime-conditional additive correction, +~2°F on dp forecast for pre_frontal/nw_flow/sw_flow). Do NOT wire on today's read alone. Script now emits `VERDICT: DP-DOMINANT ★-magnitude regimes eligible for dp-correction Stage 1 workup: pre_frontal, nw_flow, sw_flow.` so tomorrow's digest picks it up as a stable verdict line — track drift over 2-3 weekly reads before acting.

8. **sr cloud-disagreement / obs-recent override** (Group D — added 2026-08-11).

  **2026-08-17 update — 8a CLOSED MISS (re-tested).** Fresh run of `h_sr_obs_recent_override_stage0.py` on current data flips the previous near-hit to a clear miss: test pool lift −5.79% (was +4.58% on 08-11), fired-subset MAE 143.78 → 205.98 (−43% regression, was +23.5% lift on 08-11). Trigger sweep on today's test window: even the tightest usable trigger (500 W/m², only 8 fires) gives only +2.5% pool lift, still below 5% gate. Direction split: 74/75 fires are one-sided (obs_prev > fc, "fc predicting less sun than recent obs shows") and override HURTS by −63% on those. Physical: during recent wet regime, fc-under-obs pattern exists but doesn't PERSIST to next hour — same fast-regime-shift failure mode as [[project_cm_lc_wet_regime_watch]] and [[project_cl_h_predictor]].

  **Also caught: 8a script has run-time keying leakage.** `obs_prev = obs at (vt − 1h)` where vt = obs_time. For lead=6 forecasts, obs at vt−1h is 5h FUTURE relative to run_time R = vt − 6h. Real production doesn't have that obs. LEAD_MAX=6 in the current script, so leakage is up to 5h. Even the 08-11 "near-hit" was leakage-inflated. Honest reformulation would need `obs_prev = obs at (run_time − 1h)`, restricting to hours where that's actually recent-enough to be predictive (probably lead ≤ 1h only). Given today's ALL-FIRES-WRONG-DIRECTION result on wet regime, unlikely to survive an honest reformulation either.

  **8b (cloud-disagreement conditional) — TESTED SAME DAY, CLOSED MISS 2026-08-17.** Ran fast honest sweep restricted to lead≤1 (only leads where obs at T-1 is genuinely available at issue time R = T - lead). Override variant: test pool lift −47% at trigger 100 (many bad fires), −23% at trigger 200, near-zero at trigger 300+ where fires disappear. Additive variant needed cross-run join not built. Same "recent obs persists to next hour" premise as 8a and 4 other closed workstreams today; premise is broken in the current wet regime. Both 8a and 8b closed; treat the whole sr obs-recent-override branch as dead for this regime.

  **The meta-finding across all six 2026-08-17 closures:** any "recent obs predicts near future" architecture fails in fast-moving regimes. Future sr-side ideas should avoid this premise entirely — try structural features (regime classification without history), longer-horizon features (weekly patterns), or regime-change detection (turn corrections OFF during transitions).

  ~~08-11 near-hit description preserved:~~ 8a at trigger `|fc − obs_prev| > 200 W/m²` + midday 10-14 EDT: 77 held-out fires (91% outside Lsb slice), fired-subset MAE 230 → 176 (+23.5% lift, direction-stable vs train +16.6%), but pooled test lift only 4.58% (under 5% gate) because fires are 6% of rows.

  ~~Root of the sawtooth is 1-2 outlier hours per day~~ Root of the sawtooth is 1-2 outlier hours per day where fc cloud cover and observed sr disagree massively — e.g. 08-10-07 pre_frontal `(fc_sr=1144, obs_sr=502)`, 08-10-08 pre_frontal `(fc_sr=2, obs_sr=649)`, 08-10-10 pre_frontal `(fc_sr=0, obs_sr=796)`. Model says overcast, sky is clear (or vice versa); sr forecast tracks the wrong cloud state and errors are on the order of 500-800 W/m². Rolling 24h MAE stays elevated for ~24h as those hours age out, hence the sawtooth. Lsb (v0.6.394 LIVE) only fires on `sea_breeze + cc<25` and misses this fault mode entirely — Lsb is a "trust obs when we already know sky is clear" narrow override, whereas this catches "trust obs when fc cloud cover is wrong."

  Two candidate shapes:
  * **8a — obs-recent-sr floor/ceiling override.** At forecast time, if the last-hour observed sr contradicts fc sr by >X W/m² and the hour-of-day should be non-transitional (10:00–14:00 local, well past dawn/before dusk), lift/depress the next-N-hour fc sr toward a ramp from obs. Doesn't need cloud-forecast trust — uses obs as ground truth.
  * **8b — cloud-disagreement conditional.** Compute fc_cc_persistence and last-hour obs_sr. When obs_sr proves fc_cc is wrong (obs high, fc says overcast → clear; obs zero when it should be sunny → overcast), scale fc sr accordingly. Symmetric two-sided.

  8a is simpler and doesn't touch the cloud stack; 8b is more principled but requires a live cc-vs-obs-sr consistency check. Start with 8a.

  **Stage 0 gate**: build `analysis/h_sr_obs_recent_override.py` — for each sr row with lead ≤ 6h, compute (obs_sr_lag1, fc_sr_lead0). Bin by hour-of-day. When obs_lag1 - fc_lead0 exceeds Y W/m² at midday, does a naive override (`fc_sr := obs_lag1`) improve or hurt on held-out? If it improves and doesn't collapse into Lsb, promote to Stage 1.

  **Blockers before Stage 1**: (a) verify the sawtooth pattern persists over ≥7 days (not just 08-09 to 08-11); (b) verify fault mode is symmetric — both fc-high-obs-low AND fc-low-obs-high — else 8a is one-sided; (c) confirm Lsb non-overlap (this fires in non-sea_breeze regimes or when cc>25). **Priority**: LOW-MED — sr is not a top-of-scoreboard field but the sawtooth is user-noticed.

7. **Frontal-conditional t over-forecast bias** (Group D — added 2026-07-28). **08-11 progressed to STAGE 0 HIT + direction-stability watch.** `analysis/h_frontal_t_bias_stage0.py` on 45d: 3/4 bands SIGN_HOLDS (0-5h +1.94, 6-11h +2.74, 12-23h +1.06). 24-47h SIGN_FLIPS (A +4.01 / B −0.29 — could be seasonal or small-n). Half A concentrates in one frontal event 07-13/16 — need 2-3 weekly reads with fresh fronts to confirm cross-event stability before scoping `frontal_t_bias.py` specialist. Original spec preserved below.

  ~~Companion to #6~~ — the frontal-cell BOTH-COMPOUND read from `h_dewpoint_depression.py` v0.6.383a shows the model over-forecasts t by +1.47°F in frontal AND under-forecasts dp by −1.63°F, both contributing to a dep bias of +3.11 (largest of any regime). If #6's dp-side Stage 1 lands, it fixes the −1.63 dp half but leaves the +1.47 t half untouched. Physical read: model imagines a warmer post-frontal airmass than shows up (front weaker than modeled or timing off, so we're comparing model-post-front to obs-still-pre-front). **Context vs Lt retirement**: Lt Fix B was retired 07-13 at +0.29% held-out (below +1.0% ship gate) — but Lt was a GENERAL t-bias correction. A frontal-conditional t correction attacks a different signal: frontal is a rare regime (n=2,232 over 5 weeks) where the model systematically over-forecasts. General t-bias averages this out with all-regime noise; conditioning on frontal exposes it. **Stage 0 gate**: build `analysis/h_frontal_t_bias.py` (fork of `h_dewpoint_depression.py` t-side only) — per-lead breakdown of frontal t_bias, direction-stability across weekly reads, cross-check with `h_pre_frontal.py` to distinguish frontal vs pre-frontal signal. **Blockers before Stage 1**: (a) n=2,232 is small — per-lead-band count is ~500-700 per band, may not be enough for a lead-decay fit; (b) direction-stability watch — need to confirm the +1.47°F doesn't sign-flip on weekly re-runs the way the compound dep bias did across June-July; (c) ship dp-side (#6) first — else attribution stays entangled. **Ship shape (if it clears)**: regime-conditional t additive at frontal only, magnitude ~−1.47°F on the forecast t. Wire as a `frontal_t_bias.py` specialist, ENABLED=False first, 7-day gate. Do NOT extend Lt's existing table — that's the "regime-conditional Lt refit" architecture that has already tested weakly and is architecturally deferred. **Priority**: LOW until #6 clears its direction-stability watch; then #7 becomes the follow-on. If #6 washes out, #7 is dead too (attribution rests on same script).

## Carrying over

- **Marine-layer / harbor inversion correction** — `marine_layer_correction.py` still `ENABLED=False` as of 08-11. Weekly re-read plan from June (06-28/07-05/07-12) never converted to a ship. Went dormant. Active surveillance is now `analysis/marine_layer_anomaly.py` daily sentry only (STABLE 08-10 last check). Real state lives in [[project_mlc_diagnosis]] — "future ★ = new signal" pattern; no scheduled action here unless the sentry flips.
- **Clear-night radiational cooling** — Q3 candidate. Not started.
- **Group E — Briefing-side use of confidence** — three sub-tasks: (1) add precip rate/total to C1 table (needs weeks of data); (2) extend briefing builder; (3) prompt rules for hedge language. Independent of C1 ENABLED flip.

## Recent shipments (see individual project files for post-ship state)

C1f precip_fc>0 (v0.6.215) · cc → L4 (v0.6.214) · Humidity K-taper (v0.6.218) · cluster_spread axis (v0.6.220-ish) · dp regime-conditional additive (dpbp v0.6.391) · Lc regime-conditional · pr L2 regime-gated (v0.6.401) · chp diurnal gate (v0.6.401) · cross_run_spread axis Stage 3 (08-11).

KILLED via orthogonality: wind_shift_rate (C1a in disguise), C1g fog axis (C1f/cc-sat in disguise), windspeed→t as c1 axis (transition in disguise, 08-11).

## Joe's framing rule (unchanged)

"I'd avoid adding more raw bias layers unless the 7-window audit is very clean. A lot of these should probably become confidence layers, not correction layers."

## Today's discipline lesson (added 2026-06-24)

Two Tier-2 candidates passed Stage 0 magnitude tests and both failed orthogonality the same day. The Stage 0 → ortho → debug-page-update → kill-or-ship loop is the gate that prevents redundant signal shipping. See [[feedback-orthogonality-gate]] for the convention.

Related: [[project-c1-pivot-to-confidence]], [[project-todo]], [[project-correction-stack]], [[project-stage4-audit]], [[project-06-24-session]], [[feedback-hypothesis-promotion-pipeline]], [[feedback-orthogonality-gate]], [[feedback-debug-page-canon]].
