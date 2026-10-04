---
name: pr-l2-regime-flip-investigation-08-10
description: "08-10 CLOSED same-day — flip was data-window not τ-artifact. pr L2 shipped gated on nw_flow/{0-5,6-11} at v0.6.401. 08-12 re-verified: both shipped cells still both-halves-WIN, retro flip is on non-shipped candidates only."
metadata:
  node_type: memory
  type: project
  originSessionId: b8058893-d7b5-4544-a4d3-9f9dee94eef7
  modified: 2026-08-12T13:52:28.614Z
---

# 08-12 UPDATE (retro flip verified non-issue)

Digest flagged `pr_l2_regime_lead_retro` STAGE 1 SHIP → MIXED (Jaccard 0.50 → 0.25). Investigated: **flip is entirely on non-shipped candidate cells; live gate is healthy.**

**Shipped cells (nw_flow/{0-5h, 6-11h}) today:**
- nw_flow/0-5h: pooled +33.5% n=761; halves A +25.1%/n=306, B +37.8%/n=455 — BOTH-WIN, gain grew.
- nw_flow/6-11h: pooled +11.2% n=695; halves A +11.8%/n=277, B +10.7%/n=418 — BOTH-WIN, stable.

**What moved:** candidate cells (pre_frontal/{0-5,6-11}, sw_flow/{0-5,6-11}, nw_flow/12-23h). Half B (08-05→08-12) is nw_flow-dominated so only nw_flow cells qualify in both halves. Predicted by original 08-10 "regime-window drift" concern. pre_frontal/12-23h FLIPS (A +4.4% → B −8.2%) — not a ship candidate anyway.

**Candidate-only Jaccard = 0.00.** No non-shipped cell cleared halves this run. Hold signal on new candidates; no action on live SKIP_TABLE.

**Script hardened (v0.6.401g follow-up).** `analysis/pr_l2_regime_lead_retro.py` now carries `SHIPPED_CELLS = {(nw_flow, 0-5h), (nw_flow, 6-11h)}` and emits a SHIPPED CELLS STATUS block (per-cell pooled + halves + ✓ HEALTHY / ⚠ AT RISK) plus a candidate-only Jaccard before the main verdict. Future flips distinguish live-gate degradation from candidate churn on sight. If `_PR_L2_FIRE_CELLS` grows, add matching entries to the constant.

**How to apply on the next flip:** read the SHIPPED CELLS STATUS block first. If all shipped healthy AND candidate Jaccard < 0.5, close without opening a session investigation (like today). Only escalate if a shipped cell shows ⚠ AT RISK or candidate Jaccard clears 0.5.

---

# RESOLUTION (08-10, same-day close, shipped v0.6.401)

- **Live τ was 8h, not 3h as this memory originally feared.** Downloaded `l2_decay.json` from GCS: `tau_hours.pr = 8` (adopted from fitter, held-out +0.03% vs default τ=12h). Guardrails at [0.25×, 4×] of default (12h) kept the adopted τ close to default. τ=8h and τ=12h behave nearly identically over the relevant leads.
- **Pair log's `forecast_l2` for pr in August contains 8,596 rows with real live-shadow values** (not pre-07-01 legacy). Confirmed by month-count. So today's `pr_l2_regime_lead_retro` verdict IS testing live shadow behavior.
- **The 07-29 vs 08-10 flip was data-window drift, not τ-artifact.** 07-29 read used pre-07-01 mid-June data (~5 days). 08-10 read uses 07-29→08-10 shadow (~2 weeks). Halves A (~07-29→08-04) and B (~08-04→08-10) BOTH show nw_flow winning at 0-5h and 6-11h with n>250/half. Not a single-weather-event artifact; a durable signal in the current shadow window.
- **Shipped v0.6.401** (`weather_collector/processors/corrected_hourly.py`): `_PR_L2_FIRE_CELLS = {(nw_flow, 0-5), (nw_flow, 6-11)}`. Conservative first ship — only both-halves-verified cells. Pooled-only WINs (nw_flow/12-23h, pre_frontal/{0-5,6-11}, sw_flow/{0-5,6-11}) held pending 7-day gate agreement. Shadow-write (`corrected_pressure_in_post_l2`) remains unconditional so future retros can still evaluate skip cells.
- **Scoreboard update** (`corrections_debug.html`): pr dropped from `MAE_UNCORRECTED_FIELDS`. Touched median n=8 → n=9.
- **Related resolution**: [[project_pr_l2_regime_gate_opportunity]] "Re-cut ~08-12" watch is satisfied ahead of schedule.

# ORIGINAL INVESTIGATION (superseded)

**07-29 read** ([[project_pr_l2_regime_gate_opportunity]]):
- Jaccard(A,B) = 0.00
- WIN cells: sea_breeze/0-5h (+26.7%), pre_frontal/0-5h (+26.1%), calm/6-11h, ne_flow/12-23h, sea_breeze/12-23h, ne_flow/24-47h
- **nw_flow LOSES 0-5h, 6-11h, 12-23h** (attributed to terrain-induced pressure gradients not applying at the Beverly grid point)
- sw_flow LOSES all four bands

**08-10 read** (today):
- Jaccard(A,B) = 0.50 — STAGE 1 SHIP CANDIDATE
- Both-halves WIN cells: **nw_flow/0-5h** (A +21.8%/nA=284, B +41.6%/nB=311), **nw_flow/6-11h** (A +10.3%/nA=250, B +13.1%/nB=292)
- Pooled WINS: nw_flow/0-5h/6-11h/12-23h, pre_frontal/0-5h/6-11h, sw_flow/0-5h/6-11h
- Only overlap with 07-29 WINs: pre_frontal/0-5h

nw_flow flipped from "biggest loser, blamed on terrain physics" to "both-halves winner." That's a 180° physical-story change in ~12 days. Ship recommendation from the retro is real but the flip needs explanation first.

# Why not ship today

Two plausible drivers, need to distinguish:

1. **Regime-window drift.** August nw_flow may be dominated by different sub-conditions than late-July nw_flow. If so, the flip is real signal for current regime state, and the SKIP_TABLE approach still works — but the "terrain physics" story in the 07-29 memory is either wrong or was itself windowing-artifact.
2. **τ mismatch.** Retro tests K=1, τ=12h. Live shadow uses fitted τ=3.0h (per [[project_pr_l2_regime_gate_opportunity]] and `_load_l2_taus` guardrails). Different τ → different cells win. If today's WIN cells only win at τ=12h and not τ=3h, the retro isn't testing what the live shadow would actually apply.

Shipping without resolving which driver is in play risks whipsawing the SKIP_TABLE per [[feedback_capitulating_to_pushback]].

# The better test we already have

Shadow-wire live since v0.6.389 (2026-07-29). ~2 weeks of `corrected_pressure_in_post_l2` vs `raw_pressure_in` in the pair log by 08-11. That's a live-behavior comparison of the actual τ=3h shadow, not a τ=12h retro. If nw_flow cells beat raw in the shadow window, ship. If they don't, the retro flip is retro-only artifact and we close.

# Action for 08-11

1. Read shadow-wire pair-log deltas for pr, grouped by regime × lead band, from 07-29 forward.
2. If nw_flow/0-5h and nw_flow/6-11h show shadow beating raw ≥ +5% at n≥200 → ship pr L2 with SKIP_TABLE excluding today's pooled LOSS cells (per retro recommendation). Update [[project_pr_l2_regime_gate_opportunity]] with the resolution.
3. If shadow shows those cells flat or losing → the 08-10 retro flip was τ-artifact. Close this investigation, note the resolution, leave shadow running.
4. If shadow is n-thin (< 200/cell) → wait one more week, re-run this test 08-18.

# How to apply

Read this on 08-11 morning triage alongside `project_ch_chp_midlead_band_watch_08_10`. Both were opened same day. Both need one day of fresh signal to resolve.

Related: [[project_pr_l2_regime_gate_opportunity]], [[feedback_pooled_n_time_thin]], [[feedback_capitulating_to_pushback]], [[feedback_asymmetric_gates_hide_signal]].
