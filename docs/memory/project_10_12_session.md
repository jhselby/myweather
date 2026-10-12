---
name: project-10-12-session
description: "10-12 morning triage, no ships. Digest 211/211, nothing ship-eligible. sr FRESH FIRE (3d +33.7%) = NBM source miss on 10-11 (raw_nbm 79.4 vs HRRR l1 33.7) with selector routing ~70% of sr rows to NBM; stack layers still help. One-day event, wait."
metadata:
  type: project
---

# 10-12 session (morning triage)

## Digest (05:46 run, 211/211 pass), no ship-eligible items
- **sr FRESH FIRE** (7d +3.8%, 3d +33.7%). Pair-log daily MAE: 10-11 raw_nbm 79.4 / l3_nbm 67.3 / HRRR l1 33.7 / prod_real 62.7; 10-08 was a smaller all-source bad day (raw_nbm 67.6, l1 71.6). The NBM source missed on 10-11, and the selector sends ~70% of sr rows to the NBM path (stamped `l5_nbm`, which is disabled and passes l3_nbm through unchanged). l3_nbm beats raw_nbm every day, so the correction stack is not the cause. Same shape as the 09-30 h NBM break. Fresh-fire frame ([[feedback_fresh_fire_vs_circuit_breaker_frames]]): wait. Recheck 10-13/10-14; act only if NBM sr keeps losing to HRRR by 2x on multiple days.
- `l3_nbm wg calm 12-23/24-47` skip proposals (−92%/−101%) are cells already in `skip_table_nbm_curated.json`. They are not new.
- Known/repeat: h τ-suspect 24-47 +6.0% ([[feedback_tau_suspect_can_be_selector_artifact]]); t/production@12-23 +10.6% (stale-override tail, clears ~10-14); wg nor_easter/12-23 ADD (degenerate half A −0.00, 5th time); sr.l5_nbm HOT (layer disabled); chp_nbm/wdp_nbm DROP (THIN).
- Churners, no action: lsr_recent_bias sr NULL→PROMOTE "CHURN"; l2_lead_decay sr KEEP→IMPLEMENT (the sister tool says it is blocked by the sr unit mismatch); walkforward L3 drop wg 1/7.
- Pair-log anomaly: dp now ANOMALY +64.8% (was WATCH +48.8% on 10-11). Still not investigated.

## Carry-forward
Unchanged from [[project_10_11_session]]: 10-13 nor_easter skip reviews (wd l3_nbm v0.7.24, sr bypass v0.7.11), ~10-14 t sentry, ~10-18 ch nw_flow/24-47, ~10-24 backstamp prune. Add: sr fresh-fire recheck 10-13.

## dp ANOMALY dig (Joe asked)
- Anomaly detector windows: recent 7d vs prior 21d, prod_error. dp MAE 1.98→3.27; obs dp mean fell ~11°F (dry post-frontal air, seasonal). HRRR raw dp got worst (week 4.2–5.1).
- 77% of the week's dp rows route to `l2_nbm`. On those rows served 3.49 vs raw NBM dp 2.65 (baseline 1.62 vs 1.48).
- dp `l2_nbm` = Magnus(NBM t + L2 t-bias, NBM h + L2 h-bias) (`forecast_snapshot.py:345-411`). Counterfactual split on l2_nbm rows, week: M(raw t, raw h) 3.69 → M(L2 t, L2 h) 3.51, so **the L2 corrections help and are not the cause**. NBM's native dewpoint 2.66 beats Magnus(NBM's own t, h) by 28% (baseline 1.58 vs 1.85).
- **Root: NBM h is inconsistent with NBM's own t+dp.** RH(NBM t, NBM native dp) beats NBM raw h by +18.4/+12.4/+12.6/+8.4% across the half-months 08-B..10-A (stable). By band: 12-23 and 24-47 +17% at baseline, +9.5% this week; 0-5 neutral, 6-11 +6% base / −6% week. Explains part of the 09-30 "h NBM break".
- Not shipped. Next step: a Stage 0 that feeds derived NBM h through the live h NBM stack (native L2 + l3_nbm refit) and scores served h AND dp by regime×band with halves, plus selector interaction. This fixes dp through h, per [[project_dp_is_derived_no_dp_work]]. Related to NWS Option B in [[project_nws_dp_coherence_wire]].
- Also trimmed MEMORY.md 31.5→16.3KB; older session links moved to `reference_session_index.md`.

## Stage 0 built: `analysis/h_nbm_h_from_dp_stage0.py` (v0.7.46, analysis only)
- Rebuilds the live NBM h path on h = RH(NBM t, NBM dp): native L2 ramp (reconstruction residual 0.099, K median 0.92 from lead-0 rows) plus the blender (w_h 0.44). dp on l2_nbm rows = Magnus(l2_nbm t, new h). HRRR-served rows are unchanged.
- 30d read (09-12..10-12): served h on NBM-path rows 5.22→4.65 (**+11.0%**), all rows +6.9%; served dp on l2_nbm rows 2.12→1.62 (**+23.6%**). **PROMOTE: 7 cells halves-stable** (ne_flow/24-47, nw_flow/6-11, nw_flow/12-23, pre_frontal/12-23, pre_frontal/24-47, se_flow/6-11, sw_flow/6-11). dp lift positive in every non-THIN cell. Selector winner flips HRRR→NBM in 9 cells, so a ship needs the selector refit (the cloud refitter would pick that up once the pair log carries the new h).
- **Weak spot: the last 8 days are only +2.9% on h** (dp still +32%). 10-06 −20% and 10-10 −23%: NBM t ran 1.5–4°F cold, so RH from it came out 6–10 points too humid. Arm B (RH from served t) lost overall (h +3.9%, dp +11%) and did not fix those days. Kept in the report as a comparison column.
- 0-5h derived raw is worse (−4.6%); L2 anchoring absorbs most of it (served 0-5 is roughly flat).
- Next: let the digest run it daily (auto-picked). A ship would be shadow-first (stamp `h_raw_nbm_derived` in the snapshot) so the selector and l3_nbm fitters can see it. Do not ship on the 30d number while the last week is near flat.

## v0.7.47 — briefing fixes (Groq 404 item from 10-11)
- Logs 10-11..10-12: 10 gpt-oss headlines REJECTED by the present-tense rain check, 8 of them forecasts ("rain arriving this evening", "Rain returning this evening"). "arrives" is not a substring of "arriving", and "evening" was not a future marker. Added arriving/returning/returns/moving in/evening/afternoon/overnight. Tested on the logged headlines: the 4 forecast headlines pass, and the 3 present-tense ones still reject.
- Every rejection fell through to `llama-3.3-70b-versatile`, which has returned 404 on every call since 09-12 (first logged 404 is 09-12 22:57Z). Groq's deprecations page still lists the model as active, so the cause is likely project or model access on Joe's Groq account. The waterfall now logs the response body (`resp.text[:300]`) instead of raising. Next failure will name the cause.
- Auto mode denied reading the GROQ_API_KEY secret (credential exploration), so the model list was not checked. Joe can check model permissions in the Groq console.
- Info-level collector logs do not show in `gcloud logging read` (only warnings/errors), so a success rate for the briefing could not be computed.
- Deployed 13:29Z. Ticks 13:37..14:38 clean (72–85s), only the known PWS error and one NWS alerts 500 (13:57Z, upstream). Fresh gpt-oss briefings were accepted at 13:37Z and 14:17Z, but neither mentioned rain, so the validator fix is **not yet exercised**. Successful briefings do not appear in `gcloud functions logs read`; check `briefing.model` / `cached_at` in `https://data.wymancove.com/weather_data.json` instead.

## Carry-forward (next session, 10-13)
1. **Briefing verify:** on the first headline that mentions upcoming rain (rain forecast for 10-13 afternoon), confirm it passes and no longer falls through. If Groq llama is called, read the newly logged 404 body.
2. **Groq model access (Joe):** run `curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $(gcloud secrets versions access latest --secret=groq-api-key)" | python3 -m json.tool | grep '"id"'`. If llama-3.3-70b-versatile is missing, enable it in the Groq console or swap `GROQ_MODELS[1]` in `briefing_ai.py`.
3. **TEMPORARY nor_easter skip reviews:** wd l3_nbm (v0.7.24) and sr bypass (v0.7.11).
4. **sr fresh-fire recheck:** act only if NBM sr keeps losing to HRRR by ~2x on several days.
5. **h_nbm_h_from_dp_stage0:** read the digest line daily. Watch whether the last-week h gain recovers from +2.9%; shadow-stamp design only if it does.
6. By-regime walker nor_easter cells reach the 3-day gate (cloud refitter owns them).
- Later: ~10-14 t/production@12-23 clears · ~10-18 ch router nw_flow/24-47 re-read · ~10-24 backstamp prune · ~11-04 selector override.
