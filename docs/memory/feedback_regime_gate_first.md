---
name: regime-gate-first
description: "When a finding shows heterogeneous effect across regimes (works in some, not others), the DEFAULT recommendation is to gate it ON in the winning regimes and OFF elsewhere — NOT to call it flat/mixed/hold. The applicability-map + skip-table architecture (v0.6.260 + v0.6.279) exists precisely for this. Codified 07-11 after Joe pushed on repeated instances of me framing heterogeneous findings as 'regime-conditional, hold' when the sharp play was 'regime-gate, ship.'"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2bd018ca-98b4-4343-badc-7b405cae24be
---

## The rule

Whenever an analysis surfaces a heterogeneous per-regime effect — "works in A, B, C but not D, E, F" — the DEFAULT recommendation is:

> **Gate ON in A, B, C. Gate OFF in D, E, F. Ship.**

NOT any of these framings I've defaulted to:
- "flat / mixed"
- "regime-conditional, hold"
- "kill; doesn't work universally"
- "propose per-lead / per-cell blend instead"
- "wait for more data before shipping"

**Why:** This is a project with (a) a shipped applicability map (v0.6.260) that already documents per-regime applicability across every module, and (b) a shipped skip-table architecture (v0.6.279) that already implements per-(field, regime, lead_band) apply/skip decisions in decay_apply.py and elsewhere. The framework exists specifically to ship regime-gated corrections. Framing a heterogeneous finding as "hold pending universal validation" ignores the framework the project has already built.

**How to apply:**

- When a Stage 0 / Stage 1 script prints per-regime results, look at both signs of the ledger: winning regimes (candidates for gate-ON), losing regimes (candidates for gate-OFF). Recommend the gate design.
- When an existing correction is diagnosed as net-negative overall, ask "in which regimes is it still net-positive?" before recommending disable. That's a candidate for gate-OFF-except-those.
- When walking back a shipped hypothesis (e.g., "unit swap makes pre_frontal + sea_breeze worse"), do NOT frame as "hold whole fix chain." Frame as: "flip the gate — the swap was universal, make it regime-gated to only-nw_flow (or whatever the winners are)."
- The rule survives even for negative findings. "L4 loses to persistence on ch in 8 of 9 regimes" → "gate L4 OFF for ch in those 8, keep in frontal." Not "ch is broken; investigate further."

## Legitimate exceptions (don't force-fit)

1. **Orthogonality kills where the losing axis is captured by another axis in every regime.** C1g vs C1f + cc-saturation (69/72 redundant) is a global kill — there's no regime where C1g adds signal beyond what C1f already does. Regime-gating C1g would be futile.
2. **True structural dead-ends.** If a correction *inverts* sign across regimes with no consistent axis to gate on (not: some regimes win + some lose; but: same regime wins on Tuesday and loses on Wednesday), gating it produces noise.
3. **Sample too thin to identify winning regimes.** If every per-regime cell is n<200, the "winning regimes" verdict is noise. Wait for data.
4. **Multi-tool-agreed kills stay killed.** If a decision to disable/drop was reached by ≥2 independent tools agreeing (typical pattern: h_regime_* + walkforward + production_whatif + Brier/some field-specific validator), regime-gating shouldn't re-open it. Multi-tool agreement IS the anti-overfitting defense. Revisiting a multi-tool kill with a single per-regime slice is exactly the kind of noise-hunting this project's promotion pipeline is designed to prevent.

But when the finding is "works in [named regime set] but not [named regime set]" with enough n in each AND the kill was single-tool or the finding was never shipped — that's the applicability map's happy path. Ship it gated.

## Anti-overfitting promotion gates for regime-gated ships

Regime-gate-first is the **default framing** of a heterogeneous finding, not a **fast-track to ship**. Promotion gates for a regime-gated Stage 2 ship are the same rigor as any other Stage 2, plus a couple of regime-specific defenses. All must clear:

**Standard Stage 2 gates (unchanged):**
- Cell-level WIN verdict from the source tool (l3_regime_lead_analysis / l4_regime_lead_analysis / equivalent — these already have 3%-ish thresholds baked in per-cell; don't layer a further 5% requirement, that over-strict-filters cell wins the tool has already validated).
- Orthogonality check if the axis is genuinely new; regime-gating on the existing `regime_synoptic` axis skips this.
- 7-day whitelist promotion gate (per [[feedback-whitelist-promotion-gate]]).
- `production_whatif.py` preview showing net-positive Production impact under the proposed gate (any real improvement above rounding noise — 0.5% pooled or better on the affected field). Small pooled improvements are still ship-worthy when the code change is config-only and un-blocks a queued candidate.

**Additional gates specific to regime-gating:**
- **Minimum n per regime cell: 1,000** for Stage 2 ship. 500-999 = Tier 2 (Stage 1 restart, accumulate). <500 = keep in Stage 1.
- **Physical mechanism required.** Articulate WHY the regime is different. "L4 wins in frontal because HRRR captures synoptic-tied cloud dynamics" is a mechanism. "L4 wins in Tuesdays" is not. No mechanism → likely fitting noise → not Tier 1.
- **Cap on gate granularity.** Regime-only OR regime × lead-band. Never regime × lead × hour × field-value-bin × whatever. Add axes only when the added axis has independent motivation.
- **Split-halves stability check.** **Standard pre-ship gate.** Split the well-stamped pair-log window into two disjoint halves (typically 15-day / 15-day of the most recent 30 days with `state_fc.regime_synoptic` stamped). Recompute the per-cell WIN/LOSE verdicts on each half. Require the winning cells to hold WIN status in BOTH halves. This is stronger than "wait 7 days" because it exercises actual signal stability, not calendar time — verifiable from data on hand. Codified 07-11 evening after this exact test killed both proposed h → L4 and cc L4-skip ships (7 of 12 h WIN cells flipped between halves; both cc LOSE cells flipped).
- **Halves-instability diagnostic — three noise patterns to recognize:**
  1. **Recent-anomaly contamination.** Recent half systematically worse than prior half across many candidates → upstream anomaly (e.g., the 07-04 → 07-11 HRRR mid-cloud shift documented in [[project-cm-stage4-degradation]]). PENDING; re-verify after anomaly clears.
  2. **Older-residue-dominated aggregate.** Pooled `l*_regime_lead_analysis` verdict labels a cell WIN or LOSE, but neither halves agrees — both halves show a different sign. Means the aggregate label is dominated by data OLDER than either half. Not signal for shipping. NOT a candidate.
  3. **High-variance oscillation.** Same regime × band cell oscillates between big WIN and big LOSE across successive halves. Regime-conditional signal is unstable — probably reflects the specific weather that occurred in each window, not a stable underlying pattern. NOT a candidate.
  Only cells that hold their WIN/LOSE label with matching sign in BOTH halves clear the check. This is a *stronger* filter than "wait 7 days" and applies to both adding new gates AND adding skip cells to existing corrections.
- **Asymmetry check.** MAE gained by gating ON in winning regimes must meaningfully exceed noise from gating OFF in losing regimes. If both are within ±3% → below noise floor, don't ship.

## Sweep triage — three tiers

When sweeping closed/killed findings with the regime-gate lens:

- **Tier 1 (act ASAP):** Clears every gate above. Data ready. Preview via production_whatif; ship next available window.
- **Tier 2 (Stage 1 restart):** Signal shape present but fails one gate (typically n or stability windows). Queue as Stage 1 candidate to accumulate data.
- **Tier 3 (stays killed / not-a-candidate):** No per-regime data available, or multi-tool-agreed kill, or fails physical-mechanism gate, or fails standard Stage 2 rigor. No re-open action.

## Origin

07-11 session pattern. In one afternoon I framed at least 4 heterogeneous findings as "hold / mixed / regime-conditional" when the sharp play was "regime-gate + ship":

1. sr_confound first read → "sea_breeze shows Cause B; pre_frontal ambiguous; hold." Correct: nw_flow already beats shortwave-swap per prior memory. Gate the swap ON in nw_flow now.
2. wind_shift_rate flipped KILL → MIXED (1 ortho / 36). I noted noise. Correct: which regime is the 1 orthogonal cell? Gate there.
3. dp depression frontal branch closed for "below floor." Correct: nor_easter is +3.79★. Gate ON only in nor_easter.
4. ch persistence gap — proposed per-lead persistence-blend. Correct (Joe caught it): only `frontal` beats persistence; gate L4 ON for frontal, use persistence for the other 8 regimes. Estimated ~20% ch MAE improvement.

Joe: "you've done this all day — this X only works in A,B,C regimes, and you've never once said, great, gate it on only in those cases."

## Cross-refs

Related: [[project-applicability-map-design]] (the framework this rule leans on), [[feedback-regime-lead-band-cross-cut]] (regime slicing convention), [[project-correction-stack]] (where skip tables live), [[feedback-hypothesis-promotion-pipeline]] (Stage 2 = ship gated when signal is clean), [[feedback-do-it-right]] (fix the root, don't add process; here the root is my default framing).
