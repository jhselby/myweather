---
name: cl-persistence-investigation
description: "07-12 cl investigation. RESOLVED 2026-07-24 v0.6.379 by cl_persistence_gate Stage 3 wire (12 SHIP + 8 MARGIN + 16 SKIP + 1 THIN regime × lead_band gate). Narrow 0-5h-all-9-regimes hypothesis disproven; broader halves-verified gate ships. 7-day flip gate EXTENDED from 07-31 to 08-03 on 2026-07-27 after shadow-write bug fix v0.6.382p — pre-fix gate was reading zero real data. History below kept for context."
metadata: 
  node_type: memory
  type: project
  originSessionId: 01566fb8-1905-4804-8e7a-7cd634f42cee
  modified: 2026-08-16T10:48:08.580Z
---

## Flip-gate walker seeded 2026-08-10 v0.6.401a→b

Prior 08-03 flip window was invalidated because the curated JSON is overwritten in place daily — no history existed to verify the 7-day Jaccard ≥ 0.80 requirement per [[feedback_whitelist_promotion_gate]] + [[feedback_streak_walker_robustness]]. Generalized `analysis/whitelist_streak.py` (v0.6.401b, was clp one-off in 401a) walks the registry of 5 cell-based gates (chp, clp, wdp, wg_residual, dp_residual) and archives each effective fire set to `analysis/output/{gate}_streak.json`, idempotent by UTC date. Reports pairwise Jaccard vs latest day over trailing 7 per gate. Day 1/7 seeded 08-10: clp fire set n=7 = `{calm/0-5, ne_flow/0-5, ne_flow/6-11, ne_flow/12-23, nw_flow/0-5, pre_frontal/0-5, sea_breeze/0-5}`.

**2026-08-16 flip-decision day — WALKER FAIL, no flip.** Today's read: SHADOW, n_fire=3, min-J 0.250 < 0.80 threshold. Fire set churned dramatically over the 7-day window — worst diff cells: calm/0-5, calm/12-23, ne_flow/0-5, ne_flow/6-11. Same class of instability the walker exists to catch. `ENABLED = False` remains. Walker continues running daily; a future digest that reports STATUS: PASS reopens the flip decision. No new watch date — walker is self-tickling.

## Resolution 2026-07-24 v0.6.379

`weather_collector/processors/cl_persistence_gate.py` shipped ENABLED=False. Regime × lead_band conditioned gate mirroring chp. Halves-verified Stage 2 preview (`h_cl_persistence_blend_stage2.py`) delivered the halves-verified read this memory was waiting for: **narrow-shape disproven** — persistence wins BEYOND 0-5h in calm/se_flow/unknown all-leads + nw_flow 24-47h, and LOSES at sea_breeze 0-5h. `cl_persistence_short_lead.py` retired same commit. 7-day live-layer flip gate opens today. **EXTENDED to 2026-08-03** on 2026-07-27 after v0.6.382p fixed the persistence-gate shadow-write bug — pre-fix, `if ENABLED and persist_val is not None:` guarded ALL hourly writes, so the 07-24 → 07-27 shadow window produced zero pair-log-visible data (7,704 forecast_clp rows byte-identical to forecast_l6 fallback). Real shadow data starts 07-28; 7 daily reads through 08-03. See [[feedback_persistence_gate_shadow_write]]. See [[project_already_live_backstops]] resolution note; both `h_cl_persistence_blend` + `h_cl_persistence_blend_stage2` registered in KNOWN_LIVE_PIPELINES same commit per today's lesson.

## Original investigation (2026-07-12)

Explored 2026-07-12 the same afternoon we shipped ch persistence gate v0.6.327. Follow-on to [[project_persistence_skill_baseline]] which put cl in the NO SKILL bucket alongside ch and cm. Hypothesis: does ch's regime-gate shape (L4 for `frontal`, persistence else) replicate for cl?

**Answer: no. cl has a different shape and no clean single-scenario ship.**

## Scripts
- `analysis/h_cl_persistence_blend.py` — Stage 1 halves-check (regime_gate + persist_only + linear_ramp scenarios). Structure mirrors [[project_ch_persistence_gate_ship]] Stage 1.
- `analysis/h_cl_linear_ramp_stage2.py` — Stage 2 preview after Stage 1 flagged linear_ramp as sole halves-passing scenario. τ scan {12,18,24,36} + per (regime × lead_band).

## Key findings

**Stage 1 verdicts (pooled, halves-verified):**
- regime_gate: HOLD (Δ_A −14%, Δ_B +13% — halves diverge)
- persist_only: HOLD (Δ_A −14.1%, Δ_B +14.8% — halves diverge)
- linear_ramp τ=24: SHIP CANDIDATE (Δ_A −8.3%, Δ_B −3.8%, full −6.4%)

**Per-regime for regime_gate exposed cl's real structure:**
- Persistence wins: se_flow (−28%, n=45k), calm (−47%, n=12k), unknown (−32%, n=4k). ~32% of volume.
- **Baseline wins: sw_flow (+34%, n=51k), pre_frontal (+17%, n=24k), ne_flow (+15%, n=14k), sea_breeze (+12%, n=9k), nw_flow (+8%, n=26k), frontal (+32%, n=5k).** ~68% of volume.
- Physical read: cloudy-active regimes want persistence; clear-flow regimes (sw_flow etc.) want L1 baseline because base MAE is already tiny (~8-14) and persistence carries transient cl obs into false errors.

**Stage 2 τ scan showed monotonic improvement with τ:**
- τ=12 → full −4.1%
- τ=18 → full −5.4%
- τ=24 → full −6.4%
- τ=36 → full −8.7% (Δ_B −3.27%, right at the halves floor)
- Monotonic-with-τ is a red flag: it says "as much persistence as we can get away with." Not a natural sweet spot. τ=∞ = pure persistence, which we know fails halves.

**Stage 2 per (regime × lead_band) at τ=36: 20 SHIP / 2 MARGIN / 14 SKIP / 1 THIN.**
- Wins concentrated in short leads: **0-5h ships in all 9 regimes.** This is the physically-real, halves-consistent signal.
- Middle leads are a graveyard: 12-23h SKIPs in 7 of 9 regimes.
- sw_flow SKIPs everywhere except 0-5 (tiny base MAE nowhere for persistence to help).
- Many SKIPs are halves-flip (recent anomaly inflates persistence advantage).

## Honest Ship Architecture (post-verification)

**The narrow ship** — `weather_collector/processors/cl_persistence_short_lead.py`:
- Replace `cloud_cover_low` with persistence-of-obs (KBOS+KBVY blended obs at forecast issue time, flat carry) ONLY at leads ≤ 5h. All 9 regimes. No skip table needed.
- Captures ~30% of the pooled MAE win at a fraction of the ch-gate risk.
- Simpler than ch (no regime carve-out, no per-cell verdicts).

**NOT recommended:**
- Full linear_ramp with τ=36: confounded verdict.
- Regime-carve-out gate {se_flow, calm, unknown} → persist: fails halves stability (Δ_A/Δ_B diverge sharply).
- Add cl to L2 lead-decay with single τ: same monotonic-τ problem, no natural τ emerges.
- Per (regime × lead_band) blend weights: too much architecture for the signal size.

## Confidence caveats

- **Recent 15d half is inside the 07-04→07-11 HRRR cloud-distribution anomaly window** (same anomaly that re-froze h→L4 and blocked C1 Stage 4). Persistence naturally looks better in that window because baseline is worse. Prior half (pre-anomaly) is a cleaner signal.
- Even in the "cleaner" prior half, regime_gate + persist_only LOSE. So the recent-half wins are anomaly-inflated, not just anomaly-flavored.
- Post-anomaly (07-18+): re-run `h_cl_persistence_blend.py` AND `h_cl_linear_ramp_stage2.py`. If linear_ramp Δ_B stays negative and 0-5h SHIP cells stay SHIP, the narrow ship is real. If not, cl is genuinely different and gets no gate.

## Cadence
- Both scripts auto-picked-up by the daily digest (they follow the `analysis/h_*.py` convention).
- Next Sunday's digest (07-19) will re-emit both against a mostly-post-anomaly window.
- Ship decision earliest 07-19 morning based on that read. Do NOT ship on any interim daily read; halves stability requires the anomaly to have fully rolled out of both halves.

## Related
- [[project_ch_persistence_gate_ship]] — the successful sibling, different regime shape.
- [[project_persistence_skill_baseline]] — the source finding that flagged cl/cm/ch as NO SKILL.
- [[feedback_regime_gate_first]] — the framework this investigation used.
- [[feedback_state_fc_vs_state_obs]] — both scripts correctly use state_fc.
- cm is the untested third NO-SKILL cloud field. Likely different shape again given cm is dominated by the current HRRR anomaly. Wait until at least 07-18 to test cm.
