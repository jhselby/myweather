---
name: project-h-regime-bias-watch-08-16
description: h fc distribution collapsed dry during 08-09→08-16 heat pattern (anomaly WATCH); dp WATCH is downstream. Per-field snapshot confirms h stack STILL BEATS raw — low urgency.
metadata: 
  node_type: memory
  type: project
  originSessionId: a6e2e89d-6a50-4a50-bc32-488c71d9b000
  modified: 2026-08-16T10:09:04.389Z
---

Opened 2026-08-16 from Sunday digest triage.

**Signature (anomaly_detector.json, 21d baseline vs 7d recent):**
- h: fc_μ 76 → 61 (Δ -14.9%, -0.85σ), bias -0.32 → -4.94, MAE +9.9%, recent bin distribution [50%, 39%, 10%, 1%] — half of recent fc in the driest quartile
- dp (derived from t + h via Magnus): bias -0.58 → -2.63°F, MAE +40% — inherited entirely from h; no independent forecast to fix
- t: CLEAN, running slightly warm as expected during the heat pattern

**Per-field snapshot (08-16): h reads −9.6% 7d / −7.2% 24h — meaning h stack is BEATING raw by that margin.**
(Convention verified in `corrections_debug.html:3369` — `pct = (prod - raw) / raw * 100`, green when ≤ -0.5%. Negative = production better than raw. See [[feedback_check_own_arithmetic]] — initially mis-read the sign as "degrading"; Joe corrected.)

**Why:** Model (HRRR/GFS) predicting drier air aloft during mid-August ridge; observed air is muggier than fc. h's L-stack is still net-beneficial vs raw, so this is a **fc-distribution regime shift** (baseline window didn't capture this pattern) not a corrector-chasing-wrong-target problem like [[project_lc_recent_bias_gate]] / [[project_lsr_recent_bias_gate]].

**How to apply:**
- Do NOT chase dp — dp is derived from h; no dp-side fix exists.
- Do NOT scope an h recent-bias gate yet — the L-stack is still winning vs raw. This is not the same failure mode as Lc/Lsr.
- Next digest (08-17): check whether h stays WATCH. Expected outcome: reverts to CLEAN once the ridge breaks and the recent-7d window rolls forward past this pattern.
- Escalate only if: h per-field snapshot flips positive (stack starts hurting) OR h stays on WATCH >14 days (regime shift is permanent, baseline needs re-fit).

**Watch closes:** 2026-08-23 (7 days), or sooner if h anomaly clears next digest.
