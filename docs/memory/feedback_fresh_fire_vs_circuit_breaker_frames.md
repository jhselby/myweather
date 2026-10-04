---
name: feedback-fresh-fire-vs-circuit-breaker-frames
description: "Fresh-fire lucky-baseline and mechanism-verified circuit-breaker are two DIFFERENT frames for how to respond to sentry fires. Easy to conflate — costly to conflate. Discipline: check n and mechanism-specificity before defaulting to 'wait it out'."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 393ff97d-5dfc-493b-a2fb-a7e2f400b4b7
  modified: 2026-09-29T13:27:22.686Z
---

# Fresh-fire vs circuit-breaker — two frames for sentry fires

**Rule.** When a sentry fires, classify which of these two frames applies BEFORE recommending action:

- **Fresh-fire lucky-baseline artifact.** Sentry percentage swings driven by one anomaly day + tiny baseline denominators. Signature: 3d n very small vs 7d, daily raw MAE distribution shows one outlier day near zero, per-obs-day dig confirms. **Response:** hold, no action, waits out the window. Applying an emergency skip here overfits to noise.
- **Mechanism-verified circuit-breaker case.** Sentry is measuring a real, direction-verified loss on a real sample. Signature: known layer, known regime, known direction, multi-day worsening trend, n above skip-threshold, per-layer breakdown confirms the specific correction is the culprit. **Response:** ship the bypass now. The formal 14d+50d walkforward gate cannot promptly validate a brand-new regime — waiting means eating the loss for weeks.

**Why:** [09-29 session] applied fresh-fire discipline to sr × nor_easter × L3_nbm. ChatGPT-review correctly reframed it. The signals were:
- Known layer (l3_nbm), known regime (nor_easter), known direction (raw+L2 clean, L3 corrupts)
- Two consecutive days worsening (Δ +7.6pp on 09-28 → Δ +54.8pp on 09-29)
- n grown 39 → 220 (above the skip-threshold used for formal walkforward proposals)
- Per-layer breakdown: raw_nbm 5.6-15 W/m² clean, L2 ≡ raw_nbm, L3 inflates

That is NOT the shape of a lucky-baseline artifact. That is a real correction failing on a real (if new) sample. Shipped v0.7.11 same day as circuit-breaker.

Same session, cc FRESH FIRE (3d +2374% vs 7d −34%) WAS a lucky-baseline artifact — 3 consecutive all-clear days (09-26/27/28) with raw MAE ≈ 0 blew up the percentage math on tiny denominators. Held correctly.

**How to apply:**

Ask 3 questions before deciding hold vs ship:

1. **Is the 3d n tiny compared to the 7d/30d n?** If yes and baseline daily values are near zero, LEAN fresh-fire.
2. **Do we know the specific mechanism (layer, regime, direction)?** If yes and per-layer breakdown confirms the culprit, LEAN circuit-breaker.
3. **Is the loss above the skip-threshold (typically n≥200, |lift|≥3-5%)?** If yes AND (2) is yes, LEAN circuit-breaker.

A new regime (like nor_easter starting ~09-26) makes fresh-fire discipline structurally wrong — the formal 14d+50d gate can't accumulate 50d on something that just started. Circuit-breaker is the right tool for known-mechanism new-regime losses; formal gate remains authoritative for anything with older sample.

Circuit-breakers must ship with:
- Explicit temporary framing in the curated JSON note
- A re-review date (2 weeks is a reasonable default)
- A history-log entry with the reason
- One-JSON-edit reversal path

**Precedents:**
- v0.6.622 (2026-09-14) wd.se_flow/0-5h — same shape (regime-specific L3 loss, ship-first-verify-later, cleared cleanly in follow-up walkforward)
- v0.7.11 (2026-09-29) sr × nor_easter × 12-23h + 24-47h — new addition documented above

## Related
- [[feedback_fresh_fire_lucky_baseline_artifact]] — the fresh-fire discipline; this rule sharpens when it does NOT apply
- [[project_09_29_session]] — origin
- [[project_09_28_session]] — cited fresh-fire discipline correctly for sr at n=39 (one day earlier); at n=220 two days later, the frame changed
