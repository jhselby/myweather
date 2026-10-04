---
name: clp-regime-gate-opportunity
description: "SUPERSEDED 2026-07-24 v0.6.379. 07-21 proposed 3-regime narrow gate {se_flow, calm, unknown} pending Jaccard-stable cell set. What actually shipped: broader halves-verified regime × lead_band gate (12 SHIP + 8 MARGIN + 16 SKIP + 1 THIN) — persistence wins beyond 0-5h in the 3 regimes named here plus nw_flow 24-47h + short leads across most flow regimes. See [[project_cl_persistence_investigation]] for full resolution. History below kept for context."
metadata: 
  node_type: memory
  type: project
  originSessionId: 0a14e1f9-f87a-464e-846e-dcdd5c525ad4
  modified: 2026-07-24T15:58:35.201Z
---

## Resolution 2026-07-24 v0.6.379

The 07-21 proposal was directionally right — regime-gate first — but scoped narrower than the data supported. Halves-verified Stage 2 preview (`h_cl_persistence_blend_stage2.py`) showed persistence wins BEYOND 0-5h in the three regimes named here (calm/se_flow/unknown all-leads) plus nw_flow 24-47h, and wins at 0-5h across sw_flow/ne_flow/nw_flow/pre_frontal too. Shape shipped as regime × lead_band mirroring chp, not narrow 0-5h. cl_persistence_short_lead retired. See [[project_cl_persistence_investigation]] resolution note.

## Original proposal (2026-07-21, superseded)

## The finding

Tuesday 2026-07-21 15:08 EDT Fitter (`time_series_diagnostic.json`)
shows `clp` (cl_persistence_short_lead specialist attribution) delivering
dramatically at short lead:

| Lead | Lc n | Lc MAE | clp n | clp MAE | Δ % |
|------|------|--------|-------|---------|-----|
| 0 | 100 | 7.65 | 50 | **2.06** | **−73%** |
| 1 | 99 | 10.16 | 49 | **4.57** | **−55%** |
| 2 | 98 | 9.82 | 48 | 3.96 | −60% |
| 3 | 97 | 9.91 | 47 | 3.38 | −66% |

clp attribution reads what cl_persistence_short_lead WOULD write if it
were live — the module still stamps telemetry when ENABLED=False so the
Fitter can score it. Sample n=47-50 per lead is thin but the effect
size (−55 to −73% MAE) is far above the noise floor.

## Why clp is currently ENABLED=False

Per [[project_07_19_session]] and [[project_cl_persistence_investigation]]:

- Stage 3 wired 2026-07-13 v0.6.330 as pre-emptive ship, ENABLED=False.
- Design gate: 0-5h persistence in **all 9 regimes** SHIP (that's the
  cl-specific narrow-architecture assumption at ship time).
- 07-19 refreshed-window re-run of `h_cl_persistence_blend`: **halves-mixed**
  — only 4/9 regimes SHIP at 0-5h (se_flow, ne_flow, calm, unknown).
  Design gate said "all 9" → gate stays OFF permanently per the 07-13
  criterion.
- Sibling `h_cl_linear_ramp_stage2` DID go STRONG (15 SHIP cells at
  τ=36) — different mechanism, tracked as separate P3 item in
  [[project_todo]].

## Why the design gate is too strict

The "all 9 regimes SHIP" gate was set at ship time before the refreshed
windows saw the HRRR cm anomaly roll through. The current post-anomaly
picture:

- 4 regimes DO SHIP at 0-5h (se_flow, ne_flow, calm, unknown).
- 5 regimes don't (unclear from 07-19 notes which specifically).
- Aggregate MAE across ALL 9 regimes shows clp winning by −55 to −73%.

That aggregate win means either (a) the 4 SHIP regimes are dominant by
sample size and their wins swamp the losses, or (b) the 5 "not SHIP"
regimes are close-to-flat rather than strong losses. Either way, a
**regime-gated variant** (SHIP where wins, SKIP where doesn't) captures
the win without the risk.

That's the exact pattern per [[feedback_regime_gate_first]] that has
already unlocked:

- ch persistence gate (LIVE 07-19 v0.6.358, 27 SHIP cells).
- wg residual persistence gate (Stage 3, ENABLED=False, 10 SHIP on new
  07-20 baseline, ship 07-27 earliest).
- L3 asymmetric fc-bin (wg wired live 07-20 v0.6.366; ws additive
  07-20 v0.6.370; hardcode-REPLACEMENT 07-27 earliest).

Applying regime-gate first to cl_persistence_short_lead is the natural
next step.

## Action

**07-21 PM re-audit outcome (done in-session):** re-ran
`h_cl_persistence_blend` on 30-day refreshed windows. Per-regime cut:

- **WIN (3 regimes):** se_flow −22.0% (n=37,782), calm −44.2%
  (n=8,745), unknown −28.2% (n=3,707).
- **LOSE (5 regimes):** ne_flow +19.8%, sea_breeze +16.3%, nw_flow
  +19.9%, pre_frontal +32.1%, sw_flow +34.2%.
- flat: frontal 0.0%.

Regime-gate approach is confirmed the right architecture: SHIP where
wins, SKIP where doesn't. Fitter clp telemetry (−73% lead 0, −55% lead 1)
is the weighted average of the 3 WIN regimes on the rows where clp
attribution fires — not fake, just narrower than the gross reading
suggested.

**BUT SHIP set has shifted week-over-week:**

- 07-19: {se_flow, ne_flow, calm, unknown} (4 regimes)
- 07-21: {se_flow, calm, unknown} (3 regimes) — ne_flow flipped WIN → LOSE
- Jaccard 3/4 = **0.75 < 0.8 stability threshold** per
  [[feedback_streak_walker_robustness]].

Cell-set drift disqualifies same-week flip per the 7-window promotion
gate. **Day 1 of new 3-regime baseline today.** Earliest flip on new
baseline: **07-27** (coincidentally aligns with the wdp + ws + wg
triple ship day).

**Next steps:**

1. Track daily via `h_cl_persistence_blend` in the digest — cell-set
   agreement over 07-22 → 07-26.
2. If 3-regime SHIP set (`se_flow`, `calm`, `unknown`) holds Jaccard
   ≥ 0.8 across 6+ daily reads, convert `cl_persistence_short_lead.py`
   from all-9-or-nothing to per-regime SHIP set:
   ```python
   SHIP_REGIMES = frozenset({"se_flow", "calm", "unknown"})
   ```
3. Flip ENABLED=True as v0.6.374 (or higher, depending on 07-27
   triple-ship spacing).
4. 14-day post-ship watch through 08-10; trigger = clp series drifting
   toward Lc in the 3 SHIP regimes.

**Expected lift** on the SHIP regimes: same magnitude as chp gets on
its SHIP cells — MAE −40 to −70% at 0-5h. On non-SHIP regimes: no
change (falls back to Lc).

**Risk:** cl_persistence_short_lead is narrow (0-5h only). Regime-gated
narrow gate has less surface area than ch persistence gate (which spans
all 4 lead bands). Less signal to work with; per-regime SHIP verdict is
sample-limited (~500-2000 pairs per regime × band).

**Gate before ship:** halves-check per regime per lead-band. Standard
Stage 2 halves-verified promotion per [[feedback_whitelist_promotion_gate]].

## Related

- [[project_cl_persistence_investigation]] — original narrow-architecture
  design + halves-mixed HOLD.
- [[feedback_regime_gate_first]] — the meta-pattern this applies.
- [[feedback_whitelist_promotion_gate]] — the halves-verified promotion
  standard.
- [[project_ch_persistence_gate_ship]] — the sibling that shipped 07-19
  after regime-gate refactor.
- [[project_todo]] P3 items — added as re-check task 07-24.
