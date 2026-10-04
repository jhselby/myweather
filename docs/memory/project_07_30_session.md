---
name: project-07-30-session
description: "Thursday 2026-07-30 session. Diagnosed Overall Prod-vs-Raw compression (−13% → −5.2% over one week) as an Lc architectural failure on cl+cc, not aggregation math. 7 ships (v0.6.389c-i), 3 collector deploys. Marquee: (a) cl fully off Lc via _FIELD_SKIP after walk-forward showed both pooled and regime-conditional shift tables hurt cl by 22-30% vs raw on held-out. (b) cc/95-100 universal bin-skip + cc/ne_flow regime demotes after rolling-window sweep showed no fit window recovers cl or cc on last 3d. (c) Regression sentry added to digest — headline alert when any field's Prod-vs-Raw > 15% for ≥2 consecutive days. (d) Debug page Rule 5 sweep. Full pipeline state in [[project_lc_regime_conditional]]."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6c13f0ec-2762-47f1-aab5-a15c48f08029
  modified: 2026-07-30T13:51:39.851Z
---

## Session shape

Started as a digest triage. Joe pushed back on my initial digest read (I over-called pre-frontal narrow-promote as ship-eligible when debug page canon says it's blocked on THIN n=8 passages). Second digest read was clean. Then Joe surfaced Overall MAE compression (−13% → −5.2% over a week, cl +31.5% regression on the accuracy card) and the rest of the day was Lc emergency work.

## Ships (7 in a chain)

| commit | version | scope |
|---|---|---|
| 55abdea | v0.6.389c | digest registry — `h_ws_blend_hours_sweep` auto-relabeled STABLE (backstop for the wind_blend BLEND_HOURS=4 already-live pattern) |
| 19fc890 | v0.6.389d | Lc emergency regime demote (4 ne_flow cells) + Stage 0 sweep `h_lc_regime_stage0.py` (95 ★ cells) |
| f447d9f | v0.6.389e | Stage 1 halves-strict fit `h_lc_regime_stage1.py` (92 SHIP cells, walk-forward gate day 1/7) |
| 31b0edd | v0.6.389f | cl field-kill `_FIELD_SKIP={"cl"}` + walk-forward validator `walkforward_lc_regime.py` (verdict FLAT, cl broken under both shift-table shapes) |
| 553d625 | v0.6.389g | cc/95-100 universal bin-skip + rolling-window diagnostic `h_lc_rolling_window.py` (verdict NULL — no window fixes cl). Refactored `_REGIME_SKIP` → unified `_CELL_SKIP` supporting both (field, bin) and (field, regime, bin) shapes |
| 7bdba1f | v0.6.389h | Debug page Rule 5 sweep — recent activity today, calendar Thu 07-30, post-ship watches Lc entry, Lc layer section engineering status, correction stack row, cl+cc field rows |
| 5e48c3d | v0.6.389i | Regression sentry in `build_executive_summary.py` — headline alert when any field's daily Prod > Raw by ≥15% for ≥2 consecutive days. Retro on today's data fires cl (3d, +23→+121→+659%) and cc (2d, +163→+514%) |
| 8fac18b | v0.6.389j | Ccd — cc from-derivation (`cc_from_derivation.py` NEW, wired in collector.py after Lc). Retires cc's whole Lc surface. `h_cc_derivation.py` on 123,050 held-out quads: derived-max beats current cc by +8.5% pooled, +5.8% halves-averaged, wins 6/9 regimes. ENABLED=False, 7-day gate, earliest flip 08-06. On flip, cc emergency `_CELL_SKIP` entries retired |

## Diagnostic chain

1. **Joe raised Overall MAE compression** — accuracy card −5.2% MAE mean vs ~−13% a week ago; cl +31.5% biggest field regression tile.
2. **First hypothesis (mine, WRONG):** pre-frontal narrow-promote gate cleared, ship-eligible. Debug page correction: n=8 passages THIN, blocked.
3. **Trajectory pull via `mae_over_time.json`:** cl RAW MAE 7.29 on 07-30 vs l6 56.96 (8× worse). Same on cc (raw 7.21 → l6 44.23). Both broke starting 07-28.
4. **Stage 0 regime × bin sweep:** SIGNAL — 95 ★ cells. Divergence table: 33 cells where pooled shift diverges from regime-conditional by ≥8pp. ne_flow systematically over-corrected by 22-26pp.
5. **Emergency demote** (v0.6.389d) — 4 ne_flow cells forced SKIP as a bandage.
6. **Stage 1 halves-strict fit** (v0.6.389e) — 92 SHIP cells across 4 fields, gate day 1/7. Joe pushed back on waiting 7 days when we already have data → walk-forward.
7. **Walk-forward validator** (v0.6.389f) — train pre-07-20 / test 07-20→30. **VERDICT: FLAT (−1.55%).** cl broken under BOTH pooled (−22.15%) AND regime-conditional (−30.37%). Only 22 of Stage 1's 92 SHIP cells actually beat pooled on held-out. Concluded: cl needs to come off entirely.
8. **cl field-kill** — `_FIELD_SKIP={"cl"}` short-circuits the per-lead loop.
9. **Joe on cc:** "but cm and ch winning field, leave in place?" Correct — cm/ch stayed live throughout.
10. **Rolling-window diagnostic** (v0.6.389g) — sweep W ∈ {3, 5, 7, 10, 14, 21, all} days. Verdict NULL: no window recovers cl (best W=3d still −3.7%). Also exposed cc broken on last 3d under every window.
11. **cc bandage — bin-skip, not field-kill.** Diagnosed cc bleed as bin-concentrated: 07-30 forecast was 99% at cc/95-100, obs matched at overcast, Lc's −58 shift dragged 90→32 → err ~53. Added `("cc", "95-100")` to universal `_CELL_SKIP`. cc/0-5, cc/50-80, cc/80-95 (outside ne_flow) still fire pooled Lc.
12. **Debug page sweep** (v0.6.389h) — corrections_debug.html caught up to the split state.
13. **Joe question — should I have seen this earlier?** Yes, ~24h. Chart showed the divergence starting 07-28. Nothing framed it as "Prod hurts vs Raw" though.
14. **Regression sentry** (v0.6.389i) — headline alert filling exactly that gap. Uses ratio (Prod-vs-Raw), not absolute — so weather noise cancels. 2-day minimum stops single-day blips from triggering triage. See [[feedback_ratio_over_absolute]].

## Current live Lc state

- **cl:** fully off Lc via `_FIELD_SKIP`
- **cc:** ships at 0-5 (all regimes), 50-80 + 80-95 (all regimes except ne_flow), 95-100 KILLED universally
- **cm:** unchanged from live table (20-50 / 50-80 / 80-95 / 95-100, all regimes)
- **ch:** unchanged from live table (20-50 / 50-80 / 80-95, all regimes)

All bandages reversible via single-line frozenset edits in `cloud_saturation_correction.py`.

## Architectural next step (unshipped, multi-day workstream)

The shift-table architecture can't distinguish "model over-forecasts overcast" from "model correctly forecasts overcast." Candidates:
1. **EMA/Kalman shift tracker** — same pattern as `station_bias.py`. Bias updates each tick with exponential decay. Naturally shrinks when recent bias flattens.
2. **Recent-bias gate on existing lc_fit table** — apply the fit shift only if the past-7d bias in that (field, bin) still agrees with the historical fit in sign and magnitude. Bolt-on, smaller surface.

Meanwhile cm+ch keep delivering +40-50% MAE gains via pooled Lc.

## Post-ship recovery timeline

Card's Overall MAE mean shows −5.2% today (dragged down by cl+cc). With today's fixes:
- **07-31 EOD:** clean day. Card should read −8 to −10%.
- **08-03 EOD:** 07-28 (first bad day) rolls off 7d window. Card creeps to −12%.
- **08-06 EOD:** 07-28/29/30 all rolled off. Card back at ~−13%.

**Watch the regression sentry as the leading indicator.** cl should stop firing 08-01 or 08-02 (cl_prod = cl_raw). cc might fire another day or two. If cc keeps firing past 08-03, escalate to full field-kill.

## Pre-existing gates unaffected

- **clp Stage 3 gate** day 4/7 through 08-03 — cl Lc kill doesn't affect clp (clp runs after Lc and now sees raw cl).
- **Lsb narrowed-gate** day 3/7 through 08-04 — sr, unrelated.
- **dpbp / wsbp** flip gates through 08-04.
- **wd L2 blend** watch through 08-11.

## Related

- [[project_lc_regime_conditional]] — full pipeline state, updated in-session
- [[feedback_ratio_over_absolute]] — architectural principle from the regression sentry design
- [[project_lc_flip_outcome]] — the 07-17 flip this session partially unwound
- [[project_mlc_diagnosis]] — same regime-blind bias-layer failure pattern
