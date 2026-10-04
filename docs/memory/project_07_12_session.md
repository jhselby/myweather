---
name: 07-12-session
description: Sun 07-12 marathon (8 ships v0.6.327 → v0.6.328d). Landmark — ch persistence gate live-dormant; cl investigation reveals different regime shape; persistence-skill scorecard integration (5/12 add; only ch genuinely behind pooled); pre-frontal counter wired (closes silent-dormancy audit arc).
metadata: 
  node_type: memory
  type: project
  originSessionId: 01566fb8-1905-4804-8e7a-7cd634f42cee
---

## Ships (in order)

1. **v0.6.327** — ch persistence gate Stage 2 preview + Stage 3 wired (ENABLED=False). Cell-conditioned per (regime × lead_band): 22 SHIP / 6 MARGIN / 8 SKIP / 1 THIN. See [[project_ch_persistence_gate_ship]].
2. **v0.6.327a** — debug page updated for ch ship.
3. **v0.6.327b** — debug page stale-date + counter pass + collapse-all toggle for the 5-card stack grid.
4. **v0.6.327c** — cl investigation + debug page cl entries. See [[project_cl_persistence_investigation]].
5. **v0.6.328** — persistence-skill scorecard integration. `analysis/h_persistence_skill.py` publishes `persistence_skill.json` to GCS with per-field summary; scorecard banner renders a new "vs Persistence" line.
6. **v0.6.328a** — persistence-skill line shows pooled skill_L4_MAE per field (after Joe caught that "3 NO SKILL" label was hiding cm's positive pooled skill).
7. **v0.6.328b** — digest exec summary persistence-skill verdict line surfaces pooled shape ("genuine loss: ch (−0.26) — strict-NO-SKILL but positive pooled: cm (+0.14)").
8. **v0.6.328c** — Upcoming decisions block rewritten forward-only (was 90% stale, entries from 07-03/04/06/10).
9. **v0.6.328d** — pre-frontal narrow-promote counter wired. Closes the last aspirational-text gap from the v0.6.320-323 silent-dormancy audit.

## The three big findings of the day

**1. ch persistence gate works — cell-conditioned, not clean.** Halves-check on Stage 2 preview exposed 8 SKIP cells the pooled Stage 1 hid — sw_flow long-lead sign flips + pre_frontal/24-47h +9.6% loss. Clean-gate would have regressed 20% of judged volume. Cell-conditioned ships only where verified. First-tick nw_flow matches preview exactly.

**2. cl is NOT ch — different regime shape.** Cloudy-active regimes {se_flow, calm, unknown} (~32% volume) want persistence; clear-flow regimes {sw_flow with tiny base MAE + nw_flow / pre_frontal / ne_flow / sea_breeze / frontal} (~68% volume) want L1 baseline. linear_ramp τ scan monotonic-with-τ (red flag, no natural sweet spot). Real signal: 0-5h narrow persistence gate (all 9 regimes SHIP at 0-5h). HOLD pending 07-19 post-anomaly re-verify.

**3. Persistence skill honest read: 5 clean wins, 5 partial, 1 tie, 1 real loss.** The "3 NO SKILL" label was hiding shape:
- ADD: pr (+0.79), sr (+0.69), t (+0.68), h (+0.51), ws (+0.16)
- MIXED: dp (+0.34), pp (+0.18), cc (+0.14), wg (+0.10)
- NO SKILL by strict verdict but **cm has +0.14 pooled skill** — 1 BEHIND band tripped the rule
- cl is essentially tie (−0.02)
- **ch is the only genuine loss (−0.26)** — which is exactly the field we shipped the persistence gate for today.

## What's live but dormant (all ENABLED=False, waiting on 7-day gates)

- **ch persistence gate** (v0.6.327) — day 1/7 (as of 07-12). Earliest flip **07-19**. Weekly Sun re-run of `h_ch_persistence_blend_stage2.py` governs SHIP/SKIP cell-set stability.
- **Lc cloud saturation** (v0.6.298) — day 3/7 (07-12). Earliest flip 07-16 but **anomaly-week HOLD until 07-18** (per-bin check on 07-04→07-11 anomaly shows overcorrections).
- **C1h + C1d marginal-axis Stage 3** (v0.6.316) — day 1/7 each (07-12; SHIP-set instability reset from 07-10). Earliest 07-18.
- **pre-frontal narrow-promote** (v0.6.328d) — day 1/7 (07-12). Earliest Stage 3 wire-up **07-19**. Today's SHIP set: ch 0-5h, ch 12-23h, cl 24-47h, cm 12-23h, cm 24-47h.
- **Lt** — dormant both branches disabled 06-30 + 07-01; awaiting Fix B refit.
- **Marine-layer cc** — sandbox stamps every tick, ENABLED=False.

## Divergence gates as of 07-12 digest

- L3 drop-ws: **day 3/7** (real counter after v0.6.320 fix). Earliest 07-16.
- LC_ENABLED: **day 3/7**. Earliest 07-16 (but anomaly HOLD to 07-18).
- LSR_ENABLED, LT_ENABLED: aligned (no gate).

## What to watch in this week's digests

- Every daily digest re-runs the same scripts. Look for:
  - Persistence-skill verdict line — has any ADD field slipped to MIXED (or worse)? Especially watch ws (only +0.16 pooled, thin margin).
  - Narrow-promote gates advancing without SHIP-set changes.
  - Halves check on ch persistence gate — any new sign-flip in a SHIP cell demotes to SKIP.

## Blocked until 07-18

- C1 Stage 4 legacy ship next window (cm anomaly rolls out).
- Lc flip.
- h → L4 re-verify (7 of 12 WIN cells flipped 07-11 due to anomaly).
- cm exploration (do not start Stage 1 until anomaly rolls out).

## Blocked until 07-19

- ch persistence gate flip decision.
- cl narrow-gate ship decision.
- Pre-frontal Stage 3 wire-up decision.

## New infra shipped today (structural, not tuning)

- Debug page "collapse all" toggle on the 5-card stack grid.
- Debug page "Upcoming decisions" is now forward-only (caption says outcomes move to Recent activity).
- `_claim_marginal_ship_cells` extended with `allow_empty=True` for axes where empty SHIP is a legitimate stable state.
- `persistence_skill.json` published to GCS on every digest run (new data feed for the frontend).
- Persistence-skill verdict line now surfaces pooled shape (dynamic — auto-updates if fields flip sign).

## Related memory

- [[project_ch_persistence_gate_ship]] — full ch story.
- [[project_cl_persistence_investigation]] — full cl story.
- [[project_persistence_skill_baseline]] — the 07-11 baseline that started this.
- [[feedback_regime_gate_first]] — the framework this day used.
- [[project_todo]] — top-level TODO (needs its own refresh after this session).
