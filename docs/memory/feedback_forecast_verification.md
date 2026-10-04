---
name: feedback-forecast-verification
description: "How real weather models score forecasts. What we measure, what we don't yet measure, and why the distinction matters. Codified 2026-07-10 after Joe pushed on \"am I actually just measuring the wrong thing.\""
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bddeb1dc-3ff1-42f6-9d5c-dd78607b5456
---

## What real weather forecast verification looks like (NWS, ECMWF, all major NWP centers)

For **continuous variables** (temp, wind, humidity, pressure, dewpoint):
- **MAE** (Mean Absolute Error) — typical error size
- **RMSE** (Root Mean Squared Error) — same shape but weights big misses more; catches occasional blow-ups MAE softens
- **Bias / ME** — signed mean error; systematic drift over/under
- **Sample count** — n per cell for confidence

For **probabilistic forecasts** (POP, severe wx probability):
- **Brier score** — mean of (forecast − obs)² in probability space
- **Reliability decomposition** — Brier = Reliability − Resolution + Uncertainty
- Reliability specifically: when we say 30% chance, does it happen 30% of the time?

For **categorical / threshold events** (rain yes/no, aviation categories, severe wx):
- **POD** (probability of detection / hit rate)
- **FAR** (false alarm ratio)
- **CSI / Threat Score / HSS / ETS**
- Bias score (event fraction over/under-forecast)

**Skill scores** — the crucial framing that distinguishes "measuring an error" from "measuring value":
- **Persistence skill** — how much better than "same as it is right now"? Critical at short lead (0-6h) where persistence is a strong baseline.
- **Climatology skill** — how much better than "average for this time of year"? Meaningful at long lead.
- **Model skill** — how much better than raw/previous model? What we've been measuring.

## What THIS project has been measuring, honestly

**Current (as of 2026-07-10 v0.6.325):**
- MAE per field per layer (correct math, standard metric) ✓
- Bias per layer (computed, was displayed only in dim subtext) ✓
- RMSE per layer + Production (added v0.6.325; appears in scorecard next Fitter tick 07-11 03:07) ✓
- Brier score for pp (correct — right metric for a probabilistic field) ✓
- Skill vs raw model (this is what "Production −9%" means: 9% less MAE than raw HRRR/GFS) ✓
- Sample counts ✓

**What we have NOT been measuring** (real gaps vs. how real weather models get scored):
- Persistence skill — Phase 2 in the plan; requires joining pair-log rows with obs at run_time from obs_temp_log.json. ~2-3 hours of infrastructure work. Answers "does the pipeline beat 'same as it is now' at short lead?"
- Climatology skill — Phase 4 (optional); needs a climatology reference built from the pair-log history.
- pp Brier reliability decomposition — Phase 3; have aggregate Brier, don't have reliability + resolution decomposition. ~1-2 hours.
- Categorical / threshold scoring — not required for a general continuous-variable point forecast, but relevant if we introduce user-facing yes/no decisions ("safe to boat," "will rain in next 6h").

## What the two metrics disagree about (real data, 2026-07-10)

The L2-additive-bias family (dp, h, ws, wg) shows meaningful MAE-vs-RMSE gap:
- **wg**: MAE says −33%, RMSE says −26%. 7pp gap.
- **dp**: MAE −17%, RMSE −13%. 3pp gap.
- **h**: MAE −7%, RMSE −3%. 3pp gap.

Interpretation: these layers are averaged-bias corrections that occasionally add error on days when the raw model was already near-perfect. MAE treats those bad days like normal misses; RMSE penalizes them proportionally more.

**pp:** MAE says +20% WORSE (looks bad); RMSE says −3% BETTER (looks fine); Brier is what we actually use for pp because MAE isn't the right shape for a probability forecast. The 23pp gap between MAE and RMSE for pp is itself the tell that MAE was the wrong metric.

## Rules that fell out of this

1. **When a metric that "should" tell you something isn't behaving, ask which OTHER metric would tell you.** MAE-only sees averaged behavior; RMSE catches tails; bias catches drift. If Joe is asking "am I doing well" and only one number is in front of him, that's a framing risk.

2. **A single-number scorecard is a story, not a verdict.** For fields with L2-additive corrections, "Production beats raw by X% MAE" is honestly a 2-3pp inflation vs. the RMSE number. Not a fabrication — just a specific framing.

3. **Real weather scorecards report MAE AND RMSE AND bias.** Not one. When Joe asked "am I measuring what real weather models measure" the honest answer was "part of it." The gap was RMSE + bias in the scorecard, and persistence skill in the framework.

4. **Persistence is the un-glamorous but critical baseline.** At short lead, "same as now" beats a lot of clever things. If we can't beat persistence for temperature at lead 0-3h, no amount of L2/L3/L4 sophistication proves the pipeline is useful.

5. **"Observed" isn't ground truth — it's the local network's best estimate.** MAE is measured against a network-blended value, not against a physical thermometer at Wyman Cove specifically. L2's job is literally "align forecast to what the mesonet usually says" — a legitimate technology, but not the same as "align forecast to true atmosphere." Fair for what it measures; worth being honest about the framing.

## What tomorrow's scorecard should look like after 03:07 Fitter tick

Scorecard banner shows in the "Overall vs raw" tile:
- MAE mean (should be ~ −9%)
- RMSE mean (predicted ~ −7% based on tonight's hand-computation)
- MAE median

Biggest gain / biggest regression tiles show MAE% (primary), RMSE% (compact secondary), bias in field units (very compact tertiary).

If the RMSE mean is materially different from MAE mean (>2pp gap), the "biggest gain" story is probably wg — because wg has the biggest MAE-vs-RMSE gap on the whole board.

## Related

[[project-todo]], [[feedback-co-owner-posture]], [[project-07-10-session]], [[project-correction-stack]]
