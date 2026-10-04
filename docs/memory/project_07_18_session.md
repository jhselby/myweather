---
name: project-07-18-session
description: "Sat 07-18 quiet-day session. v0.6.357 shipped pa τ=42→7 (per-field decay) + digest cleanup (tide_hypothesis retired, pressure_tendency + cluster_spread stale PROMOTE verdicts fixed to STABLE re-check)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 36fb9e26-1fb0-4ebe-8ddf-99f1fed2e7ba
---

Quiet Saturday between Fri 07-17 marathon and Sun 07-19 gate landings (pre-frontal, h/l4 narrow-add, ch persistence, cl persistence all decide 07-19).

**Shipped:** v0.6.357
- `decay_fit.py` `TAU_DAYS_BY_FIELD["pa"] = 7` (was 42). decay_tau_tuning verdict IMPLEMENT PER-FIELD τ, +5.9% held-out vs τ=14, 8/3 streak. Ties to [[tau-streak-gate-limits]] — pa has now swung 28→42→7 across 3 reads.
- Retired `tide_hypothesis.py` → `.skip.py` (settled prior, NOAA data-source FAIL was spurious signal).
- Fixed 3 stale digest verdicts that read as "new candidate" but the axis is already live:
  - `pressure_tendency_stage2.py` PROMOTE → STABLE (axis_3 in c1_confidence_calibration_v2 since 2026-06-20)
  - `cluster_spread_smoketest.py` "ship persistent logger" → STABLE (logger live since 2026-06-20)
  - `cluster_spread_orthogonality.py` "SHIP PERSISTENT LOGGER" → STABLE

**Why:** Both stale verdicts were spamming the "New candidates" section of the digest daily. Ties to [[feedback_section_cruft_accretion]] pattern applied to individual scripts — a PROMOTE verdict that never gets acted on because it was already acted on months ago is dead text, not a signal.

**How to apply:** When a digest verdict says "PROMOTE / SHIP / next step: X" and the "next step" is something already live, use the STABLE re-check pattern from `h_precip_fc_orthogonality.py`. Prevents future sessions from mis-flagging it as actionable.

**Not shipped today:** Nothing else. Gates cleared today (drop ws L3, Lsr OFF) are both misleading walk-forward-vs-regime-cross-cut cases — see [[feedback_regime_lead_band_cross_cut]]. sr sea_breeze Lsr Stage 2 PROMOTE is a re-confirm of the already-shipped-disabled Lsb specialist ([[project_07_17_session]]); halves re-run gates the flip on 07-24. Stage 4 refined view NOT READY today (cm anomaly still contaminating calib window); re-check 07-25.
