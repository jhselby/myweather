---
name: 09-14-queued-investigations
description: "Three investigations queued out of 09-14's session for future single-focus sessions. Each has enough context to start cold. h/production τ-suspect (biggest live signal), cc/0-5h narrow-promote into C1d, ch/24-47h C1a-conditional recalibration."
metadata: 
  node_type: memory
  type: project
  originSessionId: c656ec98-2726-4d09-8e93-674722e5843d
  modified: 2026-09-14T16:27:01.094Z
---

# 09-14 queued investigations — pick one per fresh session

Three items surfaced 09-14 that need dedicated sessions. Each has enough context here to start without re-loading a full day's investigation.

## 1. h/production τ-suspect — ✅ SHIPPED v0.6.618 (2026-09-14 PM)

**Resolution:** neither Path A (shorten τ) nor Path B (band SKIP) — Path C from `h_l2_shape_sweep`: `H_SOFT_RAMP_FLOOR 0.1→0.4`, `H_SOFT_RAMP_END 10→24` in `weather_collector/processors/corrected_hourly.py`. Sweep was STAGE 1 PROMOTE, 7/7 days, single stable pick, halves-stable (A +6.99% / B +10.39% at 24-47h). Under the new shape every band is positive vs raw: 0-5h +48.22%, 6-11h +11.10%, 12-23h +2.72%, 24-47h +1.46%. The τ-suspect 24-47h hurt was an *under-correction* residual (old floor=0.1 killed the correction by lead 10), not over-correction. **Watch:** re-read layer-shape sentry in ~7 days — expect ★ h/production τ-suspect to clear. If it doesn't, the interpretation was wrong and we should revisit Path B.

## 1. (original brief, preserved for reference) h/production τ-suspect — LARGEST LIVE SIGNAL

**What the digest says:**
> ★ h/production τ-suspect: helps 0-5h (−43.7%) but hurts 24-47h +6.6%. Classic 'decay time-constant too long' signature — shorten τ or add lead-band SKIP.

Source: layer-shape sentry, top-alert of 09-14 digest. Real live-shape signal on the production h stack.

**Companion tool state:** `decay_tau_tuning` verdict HOLD — 2 fields at ≥5% MAE improvement threshold today (dp, h), but only 1/3 consecutive daily reads agree on this set. 5% threshold is noise-adjacent. Digest quote:
> "ws τ=7 shipped 07-01 and reverted 07-02 for exactly this reason. No ship until streak clears."

**Two intervention paths, roughly equal cost:**

- **Path A: shorten τ.** Global tuning knob change. Higher payoff (production-wide effect) but historical revert risk documented (ws τ=7 on 07-01 → reverted 07-02).
- **Path B: lead-band SKIP.** Narrower shape — turn off h L2 at 24-47h band only. Lower payoff, safer.

**How to open the session:**
1. Read `analysis/decay_tau_tuning_summary.txt` — see per-τ MAE curve for h.
2. Cross-check against per-band pair-log: is the 24-47h hurt uniform across regimes, or concentrated in one? A regime-concentrated hurt points to lead-band × regime SKIP, not global τ.
3. If Path A path is chosen: need halves-stability + regime-cross-cut before shipping. Do NOT ship on a single-read HOLD.
4. Related: [[project_wyman_cove_hrrr_l1_biases]] documents HRRR bias context that may explain the 24-47h drag.

**Success criterion:** ship a real intervention that flips the layer-shape sentry from ★ τ-suspect to clean, OR determine the signal is a regime-transient and no-op.

---

## 2. cc/0-5h narrow-promote into C1d — ✅ RESOLVED no-op with watch (2026-09-14 PM)

**Resolution:** no-op. See [[project_cc_0_5h_c1d_watch]]. Cell is uniquely orthogonal (only cell clean on both C1a AND C1e axes across 20 tests) with premium +137.92% WIDEN, but n_low=736/n_high=582 vs SAMPLE_FLOOR=1000 and only 1 day of signal + no halves + no rolling stability. Shipping would break the pipeline discipline that paid off in v0.6.618 this morning. **Watch date: 2026-10-05** — if standard SAMPLE_FLOOR hasn't auto-promoted by then (structural undersampling), revisit with a NARROW_SHIP tier or per-cell capped premium.

## 2. (original brief, preserved for reference) cc/0-5h narrow-promote into C1d — queued from v0.6.616

**Finding source:** [[project_c1d_kill_scope_artifact_09_14]] — investigating the C1d KILL verdict at MIN_N=50 surfaced cc/0-5h as **clean ORTHOGONAL on both axes**:
- vs C1a: 2.57× (no-trans) / 2.82× (trans)
- vs C1e: 2.57× (no-front) / 3.38× (post-front)

C1d's curated table has cc/0-5h with premium +137.92% but currently not SHIPping (status=None). The +137% may have been too noisy under the strict curator rules; the ratios themselves are clean at n_low=1675 / n_high=1126.

**How to open the session:**
1. Read `weather_collector/data/c1d_curated.json` for the full cc/0-5h row (premium, n, halves).
2. Read `analysis/c1d_curate.py` for the SHIP/SKIP gate rules — what floor is cc/0-5h failing?
3. Consider whether a narrow-cell SHIP addition is appropriate — a narrower premium (say, capped at some magnitude) with an orthogonality-verified footnote.
4. Check halves-stability on cc/0-5h before shipping. C1d Stage 2 curation is where this decision belongs.

**Success criterion:** decide whether cc/0-5h enters C1d SHIP list, and either ship the SHIP or document why not.

---

## 3. ch/24-47h C1a-conditional recalibration — queued from v0.6.616

**Finding source:** [[project_c1d_kill_scope_artifact_09_14]] — ch/24-47h has live C1d premium NARROW −16.4% (HIGH-σ → narrower band), but observed post-front σH/σL = **3.20×** (HIGH-σ has 3.2× MORE error, direction should be WIDEN there). Under baseline (no-front, no-trans) the ratio is 0.93× (mild NARROW). The pooled premium is being dragged by two conflicting sub-regimes.

**What this suggests:** C1d for ch/24-47h needs C1a-conditional (or C1e-conditional) split — two premium values, one for baseline state, one for post-front state.

**How to open the session:**
1. Look at how the c1_confidence_curated_v2.json multi-axis table works — it already supports axis combinations via `by_axes`. C1d × C1e joint cells may already be the right slot.
2. Consider whether a stand-alone C1d × C1e cell (e.g., "ch/24-47h × C1e=True" as a widening premium) makes sense alongside the existing ch/24-47h C1d NARROW.
3. Sample thin under post-front — verify n before proposing.
4. Test path: shadow-write a C1a-conditional variant, measure counterfactual displayed-band accuracy over 7 days.

**Success criterion:** decide whether to split ch/24-47h's C1d cell into two conditional cells, and either ship the split or document why the pooled premium remains best.

---

## Session hygiene

- Each of these is a 1–2 hour focus session. Do NOT bundle two of them in one sitting; the C1d work in particular has multiple moving parts (curated JSON schema, confidence_layer.py wire, orthogonality axis stack) that reward single-context focus.
- Load `feedback_digest_triage_discipline` before starting — the new step 6 (check test scope on KILL verdicts) applies to any orthogonality re-run in path 2 or 3.
- All three have runtime implications. Ship shape: shadow-first (ENABLED=False or equivalent), measure over 7 days, then flip.

## Related

- [[project_09_14_session]] — the day this list was extracted from.
- [[project_c1d_kill_scope_artifact_09_14]] — evidence base for items 2 and 3.
- [[feedback_digest_triage_discipline]] — updated with step 6 during item's parent session.
- [[project_wyman_cove_hrrr_l1_biases]] — HRRR bias context for item 1.
