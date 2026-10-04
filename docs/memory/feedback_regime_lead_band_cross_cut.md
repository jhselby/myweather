---
name: feedback-regime-lead-band-cross-cut
description: "Always run a (regime × lead_band) cross-cut before acting on any walk-forward drop recommendation. The flat-drop verdict consistently hides regime-specific weakness that a per-(field, regime, lead_band) whitelist would save."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 19e46001-b953-40c1-a522-231781ec1562
---

Before acting on any walk-forward validator drop recommendation (`drop X from L3_FIELDS` or `drop X from L4_FIELDS`), run the (regime × lead_band) cross-cut on that field with `analysis/l3_regime_lead_analysis.py` or `analysis/l4_regime_lead_analysis.py`. Treat the walk-forward verdict as a question, not an answer.

**Why:** Pattern documented across four fields in a single session (2026-06-29):
- **ws L3** flat-drop verdict — actual issue was calm-wind cell (-19% to -69% MAE when forecast wind <3 mph); WINS everywhere else.
- **wg L3** flat-drop verdict — same calm-wind cell, same shape (-30% to -51% when fc_ws <3 mph).
- **cc L4** drop-cc gate at 5/7 — actual issue was frontal regime at 6-11h, 12-23h, 24-47h plus ne_flow at 0-5h; WIN or flat in every other (regime, lead_band) cell.
- **cm L3** 06-24 all-windows-OFF verdict — actual picture is clear WIN at long leads (7 WIN / 1 flat at 24-47h) with regime-specific losses at frontal × short-mid leads.

Each time the flat-drop would have killed wins in most regimes to fix a regime-specific weakness in one. The walk-forward validator's per-field aggregate is too coarse for layer drop decisions; the (regime, lead_band) cross-cut is necessary, not optional.

**How to apply:**
1. When any walk-forward gate counter reaches 5/7 or higher in the drop direction (close to clearing), run the corresponding `l3_` or `l4_regime_lead_analysis` script *before* the gate clears.
2. If the analysis shows the loss concentrates in specific (regime, lead_band) cells while the rest WIN/flat, propose a per-(field, regime, lead_band) whitelist instead of acting on the flat drop. Open question goes to the debug page's "Open architectural questions."
3. If the analysis shows the field is broken across all cells, the flat drop is correct — let the gate clear.
4. The bar for proposing a per-(regime, lead_band) gate isn't "the loss exists" — it's "the loss is concentrated AND the wins elsewhere are large enough to keep."

**Implementation:** A per-(field, regime, lead_band) skip table in `decay_apply.py` (analog to the v0.6.252 calm-wind gate, but conditioned on observed regime + lead band instead of forecast wind speed) is the natural next architectural step. Deferred to post-2026-06-30 because it's a larger commit than the calm-wind gate.

Related: [[project-walkforward-l3l4-validator]], [[project-ws-l3-long-lead-regression]], [[feedback-whitelist-promotion-gate]].
