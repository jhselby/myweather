---
name: lc-gate-rule-direct-mae
description: "CLOSED MISS 2026-08-17 same-day. Proposed replacing recent-bias gate's bias-ratio suppression rule with direct held-out MAE comparison. Stage 0 showed +8.8% cm gain — leaked (decision used same holdout window as scoring). Honest walk (decision from recent 3d, score on disjoint holdout 3d) shows the proposed rule makes ZERO different decisions from current at any of 7 cutoffs for cm/cl/ch and net −0.3% for cc. cm's walker churn is a real feature of cm's regime volatility (recent-3d bias doesn't predict next-3d MAE well), not a bug in the gate rule. Current bias-ratio gate is doing about as well as any recent-history-based rule can."
metadata: 
  node_type: memory
  type: project
  originSessionId: 32832742-5efb-4b02-a23b-3cd645f9da4d
  modified: 2026-08-17T13:58:05.926Z
---

# Direct-MAE gate rule for recent-bias gate — CLOSED MISS

**Status:** [closed: 2026-08-17 same-day, MISS]. Third leakage catch of the session.

## Origin

Investigating why cm's per-field walker in `h_lc_recent_bias_gate.py` isn't clearing (day 0/7 despite 4/7 recent PROMOTE days). Root cause identified: cm/50-80 had recent bias +44.7 vs historical +42.8 (ratio 1.04, sign OK → gate says "on") but live shift produced holdout MAE 39.84 vs raw 30.40 (Lc HURTS by 31%). Bias-ratio proxy missed a case where signs and magnitudes match but the specific recent obs pattern makes live's shift over-correct.

Hypothesis: replace the sign+magnitude proxy with a direct held-out MAE comparison: `gate_apply = m_live ≤ m_raw × margin`. If applying live's shift makes holdout MAE worse, suppress.

## Stage 0 (`analysis/h_lc_gate_rule_stage0.py`) — LEAKY

Ran on current data (holdout = last 3 days). Reported:

| field | current gate | proposed gate | prop vs cur |
|---|---|---|---|
| cc | 28.55 | 28.27 | +1.0% |
| cl | 31.69 | 31.69 | 0.0% |
| **cm** | **39.88** | **36.34** | **+8.8%** |
| ch | 13.46 | 13.46 | 0.0% |

**Verdict "STAGE 0 HIT" retracted** — the rule uses m_live and m_raw computed on the HOLDOUT window both to decide suppression AND to score it. Peeking at the answer, just like the h-predictor Stage 0 obs-time-vs-run-time leakage from earlier this session ([[project_lc_ema_kalman_fallback]] meta-lesson).

## Stage 1 (`analysis/h_lc_gate_rule_stage1.py`) — ALSO LEAKY

Walked 7 daily cutoffs but still used the same holdout for decision + scoring at each cutoff. Same leakage class, showed "STABLE ★" for cc/cm, "NEUTRAL" for cl/ch. Retraction header added.

## Honest walk — the real answer

Fixed: at each cutoff, use RECENT window (3d pre-holdout) for the decision, disjoint HOLDOUT window (last 3d up to cutoff) for scoring. Direct-MAE rule now: `gate_apply = m_live_on_recent ≤ m_raw_on_recent × 1.05`.

7-cutoff walk results:

| field | wins | losses | ties | avg Δ vs current |
|---|---|---|---|---|
| cc | 1 | 2 | 4 | −0.3% |
| cl | 0 | 0 | 7 | 0.0% |
| **cm** | **0** | **0** | **7** | **0.0%** (−0.1% at latest cutoff) |
| ch | 0 | 0 | 7 | 0.0% |

**Proposed rule makes zero different decisions from the current rule for cm at any cutoff in the honest walk.** The +8.8% "win" was entirely from allowing the decision to use the scoring window.

## What this actually reveals about cm

cm 50-80 today has live losing by 31% on the last 3 days. If we look at the 3 days BEFORE that (recent window), live was helping. So a rule using recent-3d to predict next-3d says "keep live" — same as current. The regime shift happens FASTER than the 3-day window can react.

**cm's walker churn is a real feature of cm's regime volatility, not a bug in the gate rule.** Any rule based on 3-day recent history will miss same-day regime shifts. Fixing this would require either:
- A shorter window (but then noise dominates)
- Predictive features (not "recent bias" but "leading indicators of regime change")
- Faster refit cadence at the specialist level (but the walker already refits daily)

## What we kept

Both Stage 0 and Stage 1 scripts kept with retraction headers, per the [[project_lc_ema_kalman_fallback]] precedent. They document the investigation and serve as the honest-harness for future gate-rule ideas.

## Session pattern — leakage as recurring failure mode

Four same-day closes today, three from leakage-catch-and-correct:

1. **EMA/Kalman fallback** ([[project_lc_ema_kalman_fallback]]) — obs-time-vs-run-time leakage in the shift lookup.
2. **h-predictor router** ([[project_cl_h_predictor]]) — same-window decision + scoring in the halves check.
3. **Gate-rule direct-MAE** (this workstream) — same-window decision + scoring in the Stage 0/1.

**The honest run-time-keyed walkforward is the only thing that keeps us honest.** Any Stage 0 signal that uses holdout data for its own decision is suspect. Design rule: for any future pair-log-based hypothesis, split decision-data from scoring-data explicitly BEFORE writing the script, not after the first "HIT" appears.

Consider making this into `analysis/_walkforward_honest.py` as a shared harness — three instances of the same trap in one session is a strong signal that the pattern should be captured in shared code.

## Related

- [[project_lc_ema_kalman_fallback]] — same-session closed workstream, first leakage instance.
- [[project_cl_h_predictor]] — same-session closed workstream, second leakage instance.
- [[feedback_check_contamination_before_acting]] — the class of failure this session illustrates.
- [[feedback_hypothesis_promotion_pipeline]] — the discipline that caught all three.
- [[project_cm_lc_wet_regime_watch]] — cm's underlying instability is what the walker is correctly failing to react to.
