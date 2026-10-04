---
name: t-l2-ceiling
description: "07-14 v0.6.351d Stage 1 preview — CLEAN NULL. t L2 skip-table halves-verified: 0 SKIP / 6 MARGIN / 30 KEEP / 1 THIN. L2 saves 20-30% at short leads (0-5h) in every regime; is flat within ±2% at all longer leads. No cell has extractable damage. VERDICT: t is at ceiling under the (regime × lead_band) slicing. Raw HRRR is genuinely good at temperature at this coordinate; L2 provides big short-lead wins that dilute across the full pool to net ~+0.03°F noise. Any future t improvement requires a materially different signal source (not more of the same L2/Lt cove-microclimate work, which failed Fix B on 07-13). Confirmed-at-ceiling result, not a 'try harder' prompt."
metadata: 
  node_type: memory
  type: project
  originSessionId: 74becc06-fe2f-4d6a-af5c-9236cb08ecdd
---

## The question

Joe: "T is one of our weakest performing fields." (07-14 chat, pointing at the Winning fields panel that marks t with ✗ because Production ≥ raw.)

My initial pushback (that T is strong on absolute MAE + persistence skill) was wrong under the framing Joe was using. Winning fields = "does Production beat raw?" — under that lens, t Production ~1.90°F ≥ raw ~1.87°F, so t is a loser. L2 adds ~0.03°F noise pooled.

**Path back candidates offered:**
1. L2 skip table for t — halves-verify per-cell where L2 hurts.
2. Lt regime-skip halves-verified — unexhausted path back to Lt.
3. Accept ceiling.

Joe chose option 1. Stage 1 answered decisively.

## Stage 1 verdict (07-14, MIN_N_CELL=200, floor=3.0%)

**0 SKIP / 6 MARGIN / 30 KEEP / 1 THIN / 0 PERSISTENCE_TERRITORY.**

**L2 clearly HELPS at short leads (0-5h):**
- sw_flow −29.94%
- calm −23.74%
- nw_flow −21.00%
- pre_frontal −17.65%
- se_flow −15.76%
- sea_breeze −9.72%
- unknown −12.57%
- ne_flow −9.03%
- frontal −11.23%

**L2 is FLAT elsewhere.** All longer-lead cells within ±2% for most regimes.

**6 MARGIN cells** (all under +3% floor):
- nw_flow 12-23 (+1.26%)
- nw_flow 24-47 (+0.28%)
- sea_breeze 24-47 (+0.81%)
- sw_flow 12-23 (+3.88% — halves +8.16 / +0.06 disqualifying)
- sw_flow 24-47 (+1.93%)
- unknown 6-11 (+1.01%)

## Why "Production ≈ raw" pooled despite big short-lead wins

Math: L2 saves 20-30% at 0-5h (small n per regime — say 1-6k rows each) but adds tiny +1-2% at longer leads (5-25k rows per regime). Volume-weighted:
- 0-5h total ~25k rows × 20% saved = 5k MAE-units saved
- 12-47h total ~150k rows × 1-2% added = 1500-3000 MAE-units added
- Net: still positive but small, gets diluted in the full pool

Aggregate Production ≈ raw is real but no single cell has extractable damage above the halves-stable +3% floor.

## Ceiling verdict

Under the (regime × lead_band) slicing we use for skip tables, t is at ceiling. Options exhausted:
- L2 skip table → NO (this Stage 1 answered it)
- Lt regime-skip → likely also NO (Lt fits the same short-lead space where L2 already helps; both use same station data; Lt already failed Fix B 07-13 held-out at +0.29%)
- New specialist / different signal source → possible in principle but no concrete candidate

Any future t improvement requires a materially different intervention — not more of the same L2/Lt cove-microclimate work.

## Related history

- [[Lt-fix-b-answered]] — Lt retirement 07-13 after Fix B refit against L2 baseline failed +0.29% held-out. Same story: L2's Kalman blend already dynamically absorbs the microclimate signal.
- [[07-14-session]] — parent session.
- [[feedback-regime-gate-first]] — the frame; here it correctly returned "no per-cell extraction available."

## Don't re-litigate

Future-Claude reading this: if a future digest read prompts "should we investigate t more?" — the answer for the L2/Lt/cove-microclimate family of interventions is NO, we did this per-cell in July. New investigation only if a materially different signal source appears (not just refit of same station data).
