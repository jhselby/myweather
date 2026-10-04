---
name: lc-ema-kalman-fallback
description: "CLOSED MISS 2026-08-17 same-day. Stage 0 HIT (+33.5% cl vs raw) was leakage — obs-time-keyed simulation gave the shift access to obs from up to 24h more recent than would be available at issue-time. Stage 1a baseline compare exposed it: honest run-time-keyed lookback HURTS cl at every N ∈ {6h, 24h, 48h, 168h, 720h} and at every lead-band. Same honest simulation reproduces production Lc gains on cc (+27%), cm (+16%), ch (+58%), so the sim is right — cl's fit-target is genuinely unstable and no window shape rescues it. EMA/Kalman branch DEAD for cl. Any future cl un-skip needs a different feature space (not fc-bin) or a persistence-of-obs shape like clp."
metadata: 
  node_type: memory
  type: project
  originSessionId: 32832742-5efb-4b02-a23b-3cd645f9da4d
  modified: 2026-09-02T14:24:08.015Z
---

# EMA/Kalman shift tracker as Lc fallback — CLOSED MISS

## 2026-09-02 update: Stage 1a script was itself leaky, renamed `.skip.py`

`h_lc_ema_stage1_baseline.py` was retained after 08-17 as "the honest gate future ideas must clear." On 2026-09-02 it flipped `info→promote` in the digest with a LOOKBACK verdict (ship simple N=6 rolling mean over EMA). Review of the script (v0.6.536 session) found it batches by `obs_time` and applies a shift built from prior obs_times up to `ot` — the forecast was issued at `ot - lead_h`, so obs from `[ot - lead_h, ot]` are peek-ahead. **Same leakage class this memo retracted 08-17.** The "honest run-time-keyed" claim in the docstring of `h_lc_ema_stage0.py` was aspirational — never actually made honest.

**Action taken v0.6.536:** renamed to `analysis/h_lc_ema_stage1_baseline.skip.py` per [[feedback_analysis_skip_naming]]. Kept in-tree as investigation artifact; drops it out of the digest so a future promote flip can't trigger a ship on leaky numbers. Docstring of `h_lc_ema_stage0.py` updated to remove the false "honest" claim.

**Related verified honest:** `h_cl_h_predictor_stage1.py` docstring cross-references "same two-phase per-obs_time processing" but implementation is actually run-time-keyed for the persistence source (`_persistence_mean(rt_iso, n_hours)` at line 134, window `[rt - n_hours, rt)`). Cleared 2026-09-02 same session. Today's MISS -5.1% verdict is honest.

If someone proposes another shift-table variant, the gate it must clear is now a **run-time-keyed** simulation — not the old Stage 1a script. Building that gate honest is a prerequisite of any Lc EMA/Kalman/lookback revival.


**Status:** [closed: 2026-08-17 same-day, MISS]. Stage 0 "HIT" retracted after Stage 1a baseline sanity check exposed leakage in the simulation. cl is not rescueable by any lookback-shape architecture. Honest simulation confirms cc/cm/ch's current Lc gains, so the sim is validated — cl really is uniquely broken.

## What actually happened

Stage 0 (`analysis/h_lc_ema_stage0.py`) reported α=0.2 EMA beats raw L2 by +33.5% for cl on 14d held-out. Halves-stable. Every Lc-eligible field STABLE ★.

Stage 1a (`analysis/h_lc_ema_stage1_baseline.py`) compared EMA against naive "mean residual over last N obs" lookback. Simple N=6 lookback beat EMA on 3/4 fields — a huge red flag that the win wasn't from the exponential machinery but from any kind of recent bias tracking. Both keyed off `obs_time`.

Then the leakage check: for a forecast issued at run_time R = obs_time T - lead_h, the shift should use only obs strictly before R, not before T. My sim used before-T. For 24-47h leads that's 24-47h of future-relative-to-issue obs. **The +33% was inflated by peeking at obs unavailable at forecast time.**

Honest run-time-keyed sweep on cl (all lead bands):

| N (lookback hrs) | 0-5h | 6-11h | 12-23h | 24-47h |
|---|---|---|---|---|
| 6 | −10.3% | −18.4% | −31.7% | −34.9% |
| 24 | −29.6% | −15.4% | −22.2% | −18.0% |
| 48 | −34.2% | −16.3% | −16.9% | −5.9% |
| 168 (7d) | −61.4% | −38.5% | −32.9% | −25.5% |
| 720 (30d) | −68.6% | −42.3% | −36.5% | −27.3% |

Every cell hurts. Longer lookback hurts more.

**Same honest simulation on cc/cm/ch (validation that the sim isn't broken globally):**

| field | N=24h | N=168h | N=720h |
|---|---|---|---|
| cc | +26.9% | +27.1% | +27.6% |
| cm | +15.6% | +17.8% | +19.6% |
| ch | +57.7% | +61.9% | +63.0% |
| **cl** | **−19.8%** | **−32.0%** | **−35.0%** |

Simulation reproduces production Lc behavior for cc/cm/ch. cl is genuinely the outlier.

## Interpretation

cl's HRRR forecast bias for any given (bin) is NOT stationary at any timescale we can measure. Recent history predicts future bias in the WRONG direction. The 07-30 fit-broke episode wasn't a one-time shift; it's ongoing instability.

The shift-table architecture (of any window shape — fixed, EMA, Kalman, rolling-N) requires the assumption that "recent bias is predictive of near-future bias." cl violates this assumption. This is a different problem than "the fit is stale" — it's "the fit target is fundamentally unstable."

## What this means for the pipeline-to-good plan

Pipeline-to-good item 3 called out EMA/Kalman as the cl-rescue fallback (after the recent-bias gate proved insufficient). **That fallback is now closed as MISS.** cl un-skip is not achievable via shift-table variations at any timescale.

Remaining options for cl:
1. **Accept cl stays in `_FIELD_SKIP` indefinitely** (current state, working since 07-30).
2. **A completely different feature space** — not fc-bin. Maybe fc-trajectory over last N hours, dew point depression, LCL height, satellite-observed low-cloud presence. All are Stage 0 investigations.
3. **A persistence-of-obs specialist for cl** — same shape as chp/wdp/clp. clp already exists but Stage 3 walker is FAIL (min-J 0.167 per today's digest). Reviving clp would require a different gate design.
4. **Retire cl as a first-class forecast field** — surface only in the derived `cc = max(cl, cm, ch)` pipeline (Ccd already does this for cc; cl itself may just be too noisy to correct).

Options 2 and 3 are new Stage 0 workstreams. Option 4 is a product decision. Not open today.

## What we kept

The Stage 0 + Stage 1a scripts (`h_lc_ema_stage0.py`, `h_lc_ema_stage1_baseline.py`) stay in the repo as artifacts of the investigation and as the honest test for future ideas. If someone proposes another shift-table variant, Stage 1a's honest run-time-keyed lookback comparison is the gate it must clear.

## Related

- [[project_lc_regime_conditional]] — regime-conditional Lc also HURTS cl (Stage 3 walkforward showed reg-HURTS-MORE than pooled for cl). Consistent with today's finding: no shift-table shape works for cl.
- [[project_lc_cl_unskip_investigation]] — can now close as "won't fix under this architecture."
- [[project_plan_pipeline_to_good]] item 3 — update to reflect closed-MISS fallback branch.
- [[feedback_hypothesis_promotion_pipeline]] — Stage 1a saved days of Stage 2/3 work; this is the pipeline doing its job.
- [[feedback_check_contamination_before_acting]] — leakage-via-repeated-obs and obs-time-vs-run-time keying are contamination classes to watch for in every future walk-forward script.

## Meta-lesson

Two same-session reversals of "STAGE 0 HIT" verdicts driven by simulation leakage:
1. Naive per-row EMA update → collapses to persistence (fixed with two-phase per-obs_time)
2. Obs-time-keyed shift lookup → peeks at obs unavailable at issue-time (fixed with run-time keying)

For any future EMA/lookback/Kalman-style script over the pair log, the honest gate is:
- Shift must be computable strictly from data with obs_time ≤ run_time
- Per-obs_time batching before EMA/lookback updates
- Sanity check against a simple lookback baseline BEFORE celebrating

Consider making these into a shared harness under `analysis/_walkforward_honest.py` if a third instance of this pattern shows up.
