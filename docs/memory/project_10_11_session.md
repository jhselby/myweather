---
name: project-10-11-session
description: "v0.7.45 shipped (ch router drops ne_flow/12-23). 10-11 morning triage + ch router re-read on post-event data (10-03..10-11, runtime labels): 5 HOLDING / 2 MARGINAL / 3 FAILING; ne_flow/12-23 and nw_flow/24-47 lose to always-HRRR at n>=150 but each loss sits on 1-2 days. se_flow cells recovered; Lc l6 now helps ch in se_flow."
metadata:
  node_type: memory
  type: project
  originSessionId: 28a06693-3312-4d78-b7c3-ee11ea186b2d
  modified: 2026-10-11T11:05:07.571Z
---

# 10-11 session (morning triage)

## Digest (06:40 run, 211/211 pass) — nothing actionable
- No SHIP-ELIGIBLE, no kills. t/production@12-23 is the 10-10 stale-override tail, clears ~10-14.
- New/changed: L3 add pr streak 1/7; lsr_recent_bias sr PROMOTE→NULL (was held); l2_lead_decay pr PROMOTE→KEEP FLAT; 3-way fit 12 NWS cells (walker gate owns it).
- Known artifacts: chp_nbm/wdp_nbm DROP (THIN, 08-28 hold), sr.l5_nbm HOT (layer disabled, stamps l3_nbm+0), h_chp_cell_gate "Stage 3 wire" (cloud gate is the mechanism), wg nor_easter/12-23 ADD (degenerate half A, 4th time).
- cc sat-guard Stage 0: overall +42.6% but last 4d −6.1%, last 7d −11.9%. Do not advance.
- Override walkforward day 6: FLAT −0.3 / +1.1 / −2.6 (same as 10-10).
- Local by-regime walker shows h/sw_flow/6-11 and ws/frontal/24-47 flipped; the 04:30 cloud refit owns the live set.
- Pair-log anomaly WATCH on 11 fields (dp +48.8%, pr +33%, wg +20%, h +19%, t +16%; clouds/pp/ws better). Not investigated.

## ch router (v0.7.5) re-read — scheduled item from [[project_10_04_session]]
Script: `scripts/ch_v075_live_verdict.py`, run via scratch wrapper with `RegimeRuntime` labels (the script itself still keys on `regime_synoptic`) and obs ≥ 10-03. n=2,904. All 10 cells: picked 10.94 vs always-HRRR 11.28 (+3.0%), vs inverse +11.3%. (10-04 read was +15.9% vs always-HRRR on event-heavy data.)
- HOLDING: pre_frontal 0-5/6-11/12-23, se_flow 6-11/24-47 (both se_flow cells were FAILING on 10-04).
- MARGINAL: ne_flow/0-5, se_flow/12-23 (−0.2% vs HRRR).
- FAILING: `ne_flow/12-23` (n=204, −4.3% vs HRRR; only 10-04 is informative, 10-03 ties), `nw_flow/24-47` (n=415, −18.3%; 10-03 win +12, 10-05 loss −14.6, 10-10 loss −5.6 on n=208), `sw_flow/12-23` (beats HRRR +5%, fails only vs always-NBM; router picks NBM 1%).
- The 10-04 rule "n≥150" is met by one day: rows cluster ~200/day/cell. Informative (non-tie) days per cell are 1–3.
- **Lc l6 in se_flow (10-04 open item):** post-event ladder l4→l6 is 17.34→11.67, 18.17→12.82, 20.95→9.80 — l6 helps. The 10-04 hurt was the 09-30..10-02 event.
- **SHIPPED v0.7.45** (`81b67de7`): `ch/ne_flow/12-23` removed from `_IMS_SELECTOR_CELLS`. Deployed rev `00619-vov` 11:10Z (Joe ran the deploy; auto mode blocked mine). Verified: post-deploy ne_flow/12-23 hours stamp `band_pool`/hrrr; 6 other ims cells still fire. Ticks clean (~87s, RSS ~930 MiB).
- `nw_flow/24-47` held — re-read ~10-18; pull if it still loses to always-HRRR on ≥4 informative (non-tie) days.
- New in logs: Groq/llama-3.3-70b briefing 404 (falls through to next provider). Not investigated.
- **PWS "Expecting value" every tick = KMAMARBL63 (Castle Hill) offline** (Joe confirmed on WU dashboard 10-11). Not a code bug; mesonet unaffected (11–23 stations/tick). `pws` is fallback-only — Sources card label is the only consumer. Closed.

## "Scoreboard better lately — router + blender?" (Joe, evening)
Replayed `per_field_scoring._accumulate/_compute_field` on four weekly windows (scratch script; the scorer has no end-date arg). Week ending 10-11 vs ending 10-04, Total Lift vs NBM raw: t +5.5→+11.3, h +11.2→+33.1, wd +0.8→+10.5, sr +3.0→+12.6; down: dp +0.2→−22.1, wg +7.9→+1.1, cm +54→+8, ch +46→+31.
- **Absolute prod MAE got WORSE on every gainer** (t 1.5→1.9, h 3.6→6.2, wd 32→41, sr 35→40). Lift rose because the baseline (NBM raw) got worse faster (h 4.1→9.3, wd 32→46, sr 36→45): NBM h break + the 10-10 front.
- Mechanism split for the gainers: t = selector (routing +2.0→+12.9; chooser prod-vs-prod +5.2→+10.0). h = routing +11.0, blender +8.2 pts (1,774 blend rows; ~0 before 10-02), other stack +14.0; chooser +9.0→+24.6. wd/sr = NBM-side correction stack (routing column is 0 for NBM-baseline fields by definition).
- Answer given: the router and blender do earn the extra lift, but only because NBM did worse this week; our own forecasts got worse in absolute terms. Read `chooser_vs_prod_pct` + absolute prod MAE alongside Total Lift.

## Carry-forward (next session)
- **10-13:** TEMPORARY nor_easter skip reviews — wd l3_nbm (v0.7.24) and sr bypass (v0.7.11).
- **~10-13:** by-regime walker nor_easter/stagnant_high cells reach the 3-day gate (cloud refit owns the live set).
- **~10-14:** `t/production@12-23h` layer-shape warning should clear (7d window).
- **~10-18:** ch router `nw_flow/24-47` re-read — `SINCE=2026-10-03` run of `scripts/ch_v075_live_verdict.py` with RegimeRuntime labels (the script still keys on `regime_synoptic`; port the wrapper change into the script if reused). Pull if it loses to always-HRRR on ≥4 informative days.
- **~10-24:** backstamp prune.
- Watch: wdp calm/12-23 half B; cc sat-guard reversal (do not advance).
- Uninvestigated, low priority: Groq briefing 404, Open-Meteo 429s on cloud pulls, pair-log anomaly WATCH on 11 fields, `ch.l3_nbm` NBM sentry WATCH (help +15.6% → +3.5%).
- Optional: delete dead `state_fc_by_lead`; align t/h v2b features + xr_spread before any t/h learned cell goes live.

