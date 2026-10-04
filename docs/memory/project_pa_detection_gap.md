---
name: pa-detection-gap
description: "2026-07-29 CLOSED: pa is L1-forever earned. Two shippable-looking findings (0-5h detection blend, regime-gated) both killed by halves + regime×halves cross-cut. Residual 6-11h intensity win too modest to justify specialist cost."
metadata: 
  node_type: memory
  type: project
  originSessionId: 73429c93-7451-4383-be7a-18cb78ea6325
  modified: 2026-07-29T13:57:25.240Z
---

# pa Detection Investigation (2026-07-29) — CLOSED

Ran the first-ever `analysis/h_pa_persistence_skill.py` (new). pa was L1-only with no active work; question was "can we do anything with the data we have?"

**Path taken (halves discipline throughout, per [[feedback_pooled_n_time_thin]]):**

1. **Pooled read** flagged a striking finding — 0-5h detection Brier skill = −0.065; model under-forecasts rain occurrence at 2.9% vs 10% observed base rate. Framed as classic HRRR nowcast startup drift, high-leverage correction candidate.

2. **Halves-verification killed the anchor.** Split at obs-time row-count median (halves: 06-29→07-09 vs 07-09→07-29):
   - 0-5h detection: A = −0.254, B = +0.331. 58-point swing between halves of comparable n.
   - 6-11h detection: BOTH-WIN (+0.171 / +0.448) — survives ✓
   - 12-23h detection: BOTH-WIN (+0.454 / +0.422) — survives ✓
   - 24-47h detection: BOTH-WIN (+0.573 / +0.344) — survives ✓
   - Rain-subset skill: only **6-11h** BOTH-WIN (+0.209 / +0.139); other bands weaken A→B.
   - Verdict flipped from "0-5h detection blend is highest-leverage" to "the anchor doesn't hold."

3. **Git log check** to rule out pipeline artifact: three pa τ changes in window (07-13 bump, 07-18 drop, 07-19 revert), but pa τ affects decay_fit aging, not L1 forecast values. `DEFAULT_L2_TAUS = {t, h, pr}` — pa not in L2. v0.6.310+311 (07-06) landed before the halves split so both halves have consistent metadata. **No pipeline explanation. Flip is weather.**

4. **Regime × halves for 0-5h detection.** Regime distribution shift confirmed (nw_flow 33→40%, pre_frontal 13→18%, sea_breeze 10→6%, ne_flow 7→3%). But per-regime skill FLIPPED within the same regime:
   - **nw_flow: A −0.896 → B +0.388** (persistence crushed model in A, opposite in B)
   - **pre_frontal: A −1.053 → B +0.505** (same story, even bigger flip)
   - No regime with persistence-beats-model in BOTH halves → no GATE-ON candidate exists at current resolution.
   - se_flow, sw_flow model-wins in both halves; sea_breeze marginal.

**Interpretation.** pa 0-5h detection is bimodal at a resolution finer than `regime_synoptic`. Same regime label, opposite direction across a 3-week gap. Likely subregime effect (moist vs dry pre-frontal, stratiform vs convective nw_flow, event-specific mesoscale). Our regime taxonomy can't tag it.

**pa status closed:**
- **0-5h detection blend: KILLED** — no gate-ON shape survives halves at regime resolution.
- **6-11h rain-subset intensity: ADDS VALUE, quiet-shippable-eventually.** Halves both positive (+0.209 / +0.139), n_rain=1,692 pooled. Real but modest — ~15-20% MAE gain on rain-only subset at one band. Doesn't justify architectural specialist cost for a hobby PWA. Park until it comes up naturally with a bigger design refactor.
- **12-47h detection: model reliably wins**, both halves. No work needed.
- **Rain intensity generally: fundamentally noisy.** pa τ has swung 28→42→7 across three fitter reads; this is symptomatic of that same noise floor.

**Why this closure is stronger than the previous "pa is L1, no open work" default.** The old status was an assumption. The new status is an *earned* verdict — two shippable-looking findings both tested and killed by proper measurement, plus a physical resolution ceiling identified. Future revisit should require either (a) a subregime taxonomy (moist / dry event splits, stratiform / convective), or (b) a materially better verification dataset (rain-gauge network, radar precip).

**If the project ever builds subregime tagging**, pa 0-5h detection is worth re-running — the persistence-crushes-model behavior in some nw_flow / pre_frontal events IS real, we just can't gate on it today.

Scripts:
- `analysis/h_pa_persistence_skill.py` (persistence skill baseline + halves + regime × halves)
- Output: `analysis/output/h_pa_persistence_skill.txt` (2026-07-29 read)
