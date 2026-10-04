---
name: project-l2-as-observation-only
description: "Architectural experiment to consider — remove L2 from the forecast pipeline entirely; keep L2 only as the training target for L3/L4/L5. Proposed by Joe 2026-06-17 after a week of \"L2 already does the work\" observations."
metadata: 
  node_type: memory
  type: project
  originSessionId: 4a8831ed-d0ae-48ad-9c90-349a29eadd94
  modified: 2026-07-20T18:36:51.027Z
---

## The proposal

Today's pipeline: **L1 → L2 → L3 → L4 → L5(future)**. L2 applies the mesonet bias correction to the forecast at runtime.

Proposed pipeline: **L1 → L3 → L4 → L5**. L2 still runs as a separate process to produce a network-blended observation, but that observation is used ONLY as the "truth" when training L3/L4/L5. No L2 correction is applied to the forecast itself.

## Why Joe proposed it

Throughout the 06-13 to 06-17 audit work, the recurring conclusion was that L2 already captures signals the new layers were trying to learn. Most explicitly: the R5 cove-correction Step 2 audit (2026-06-16) showed L2's station-weighting already pulls the cove forecast toward the waterfront Tempests, so layering R5 on top double-counted and made things worse. The same pattern shows up in why temperature isn't in L3 or L4 — L2 already handles temp; the per-lead and per-hour bias signals aren't worth correcting against.

If L2 is doing the spatial / station-network job, the proposal asks: what if it ONLY did that as a denoising filter on the training target, and let L3/L4/L5 (the per-lead, per-hour, per-regime lookups) do the actual forecast correction? Single source of correction, simpler architecture, easier to audit.

## What L2 currently does that the lookup layers can't

L2 captures two distinct signals at runtime:

1. **Spatial signal** — cove vs inland differences via the 1/distance² × elevation station weighting. The lookup layers could learn this given enough data; L2 just does it via geometry directly.
2. **Real-time anomaly signal** — "today is 2°F colder than the regime average, and the network just observed it." This is what L2 does that NO lookup layer can replicate. Lookups learn historical averages; L2 reads live network state.

Removing L2 from the forecast pipeline keeps #1 (via L3/L4/L5 learning from L2-blend training data) and **loses #2**.

## What's at stake — what we'd gain and lose

**Gain:**
- Single source of correction. Easier to reason about, audit, debug.
- Cleaner training signal for L3/L4/L5: L2-blend has averaged-out sensor noise; single-Tempest training target has measurement noise that the lookup layers currently try to learn (or fail to learn anything from).
- Robustness when stations fail. Lookups are offline; current L2 degrades when network is sparse.
- L2's per-lead τ decay means L2 is essentially gone at long leads anyway (τ_t=4h means by lead 24 it's ~0). So at long leads, the pipeline is already effectively L1 → L3 → L4. The proposal makes this consistent for short leads too.

**Lose:**
- Real-time anomaly correction at short leads. Today temperature gets ~17% MAE reduction at 0-5h from L2 (per the live accuracy chart). Most of that is catching short-term anomalies the model missed; lookups can't replicate this.
- Wind correction at short leads. L2 doesn't just bias-correct wind — it SELECTS the median of waterfront stations as the wind value. Pure lookup can't replicate "what the station network says right now."
- A real-time signal channel for catching ANY non-systematic deviation (heat wave, sudden front, model anomaly).

## How to actually decide

This is empirical, not theoretical. Build both pipelines side-by-side on the same pair log and compare held-out MAE per field per lead band. The audit pattern + shadow tuner infrastructure built this week supports this kind of experiment cleanly:

1. Add a new training mode to L3/L4/L5 that uses L2-blend as the observation instead of single-sensor.
2. Compute the alternate L3'/L4'/L5' correction values from this training.
3. Stamp a "shadow forecast" (L1 + L3' + L4' + L5') on weather_data per tick, alongside the production forecast.
4. Joiner adds a paired error column for the shadow forecast.
5. Held-out MAE audit compares production vs shadow over a few weeks.

Estimated effort: ~full day to build the alternate path, then a few weeks of accumulating shadow forecast data, then the audit reads off whether the proposal helps or hurts.

## 07-20 revisit — SETTLED (do not reopen)

Joe revisited during wd L2 work. Reconfirmed:
1. Removing L2 from the pipeline would hurt user forecast. Wind especially — L2 catches the current gust; no lookup layer can synthesize "the model was wrong RIGHT NOW and we know from a sensor."
2. Temp/humidity on anomalous days (heat waves, front passages) also need L2's real-time channel; L3/L4 per-lead averages can't recover it.
3. Pressure MIGHT be replaceable by L3 alone, but that's the only field.

**The real "cheating" is not L2-in-pipeline, it's the shared obs source.**
`daily_extremes._gather_current_observation` writes obs_temp_log using:
- L2-corrected values for t/h/wind/pressure (`hyp.get("corrected_*")`) — deliberate per line 101-106 comment; using raw model values here would make L3 try to undo L1
- Direct station consensus for cc/cl/cm/ch (`_blend(kbvy, kbos)`), solar (median Tempest), precip (max WU) — genuinely decoupled

So today: SOME fields are already decoupled; the ones that AREN'T are coupled for a specific documented reason (May 31 incident). Full decoupling requires solving the May 31 issue first.

**Verdict:** L2-in-pipeline stays. Full decoupling is a bigger project than "just remove L2." Reopen only if wd corrections start showing signs of L2-coupling bite (e.g., wd_persistence_gate MAE reductions look suspiciously large in Fitter but user-visible improvement doesn't match). See [[wd_l2_blend]] post-ship watch triggers.

## How to apply

- **Don't act on this today.** Joe surfaced it during a "I'm out over my skis" reflection on 06-17. The L2-as-observation question is intellectually live but not operationally urgent.
- **When revisiting:** first compute `mean(single_sensor − L2_blend)` over the last month from cached pair log. If they track within ±0.5°F most of the time, switching training targets is mostly noise reduction (low risk, low reward). If they diverge systematically (e.g., the cove Tempest reads persistently warmer than the network), this is a bigger architectural choice with real consequences for forecast-vs-thermometer alignment.
- **Sequence after the L5 / R4 / walk-forward decisions are settled (post-06-22).** Those date-gated decisions are committed; this is the next-tier architectural question.
- **Don't conflate with what's been said about L2 capturing other layers' work.** That observation is true for the SPATIAL component of L2, not the real-time anomaly component. Both exist; both matter.

## Related

- [[project-r5-two-step-plan]] — R5's HOLD verdict was the most direct evidence that L2 captures signals other layers would otherwise learn (just for spatial cove vs inland delta).
- [[project-correction-stack]] — the current 4-layer model that this proposal would restructure.
- [[feedback-best-way-first]] — Joe wants the right architecture eventually; this is the kind of question worth holding open even if it's not today's work.
