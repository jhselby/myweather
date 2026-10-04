---
name: persistence-skill-baseline
description: "2026-07-11: Phase 2 measurement framework shipped — h_persistence_skill.py. First-ever persistence-skill audit for the project. Answers 'does the pipeline beat same-as-now.' 6 fields ADD VALUE (t/dp/h/pr/ws/sr), 3 MIXED (wg/cc/pp), 3 NO SKILL (cl/cm/ch). ch failure is the biggest surprise — currently in both L3 and L4 but still behind persistence at every band. cl uses raw L1 only, persistence beats it at short leads. cm result corroborates today's Stage 4 blowup."
metadata: 
  node_type: memory
  type: project
  originSessionId: 2bd018ca-98b4-4343-badc-7b405cae24be
---

## What shipped

`analysis/h_persistence_skill.py`. First-ever persistence-skill audit. Answers Joe's 07-10 "have to measure right before improving" question: does the pipeline beat 'same as now.'

**Method:** builds `{field, valid_time → observed}` index from pair log itself (obs_temp_log.json retention is only 24h, useless for multi-day audit). For each pair row, persistence_forecast = obs at `hour_floor(run_time)` in that index. Score persistence vs L1 (raw HRRR) and L4 (pipeline pre-specialist) MAE + RMSE per (field, lead_band). Skill = 1 − pipeline/persistence.

**Coverage:** ~193k joined rows per field. Cell n counts 20k-97k.

## Headline result

| verdict | count | fields |
|---|---:|---|
| ★ ADDS VALUE | 6 | t, dp, h, pr, ws, sr |
| ⚠ MIXED | 3 | wg, cc, pp |
| ★ NO SKILL | 3 | cl, cm, ch |

Verdict per (field, band): ADDS VALUE = L4 skill ≥ +0.10 on both MAE and RMSE; MARGINAL = skill 0 to +0.10; BEHIND = skill < 0.

## Key findings

**ch (high cloud) — pipeline BEHIND persistence at every lead.** ch is currently in BOTH L3_FIELDS and L4_FIELDS — 2 layers applied — and persistence beats it by −0.16 to −0.91 skill across bands. L4 improves ch over L1 substantially (44 → 26 MAE at 24-47h) but persistence baseline is 22 → still 4 pts better. Signal: L3/L4 doing something real but not enough to clear "same as now."

**cl (low cloud) — L4=L1 (no correction), persistence beats raw at 0-5h/6-11h.** cl isn't in any correction set. Adding persistence-blend at short lead (or L3/L4 with strong regime gating) would be an easy win.

**cm (mid cloud) — corroborates today's Stage 4 blowup.** MARGINAL/BEHIND at every band. This week's HRRR distribution shift on cm (mean fc 16 → 47%) hits persistence-skill too — cm has been marginal for a while, this week made it worse.

**t (temperature) — skill L4_MAE +0.62 to +0.73** across all bands. Pipeline crushes persistence. Not surprising (L2 additive bias + Kalman does exactly this job).

**dp 0-5h — skill +0.02 MAE.** L4 MAE 1.68 ≈ persistence MAE 1.71. L4 essentially reproduces persistence at short lead — L2 anchoring to obs works as intended.

**sr skill +0.53 to +0.77** across all bands. Solar has strong diurnal so persistence should be a weak baseline; still, pipeline wins big.

## Caveats

- L4 shown, not full Production. For **sr** (Lsr) and **t** (Lt) actual Production applies specialist corrections after L4. Lsr is regime-conditional; Lt is dormant. Real Production skill = L4 skill for the 10 non-specialist fields; slightly different for sr (Production ≠ L4) and t (Production = L4 with Lt dormant).
- Persistence baseline at 24h-cycle leads (24, 48) is diurnal-aligned so numerically strong for diurnally-driven fields. Standard convention (NWS uses same). Averaged across the 24-47h band the alignment averages out.
- `hour_floor()` on run_time introduces up to 60-min slop between "persistence forecast issued" and actual run_time. Fine for a first read; a 10-min-resolution obs_log would sharpen it.

## Follow-on status (as of 07-13)

- **Phase 3 pp Brier reliability decomposition — SHIPPED 07-13 v0.6.335.** New `analysis/pp_brier_decomposition.py`. Verdict CALIBRATED +8.4%; per-bin gap shows systematic under-forecast at 30-50% probability bins (fc 30-40% → obs freq 66%).
- **Production-not-L4 skill — SHIPPED 07-13 v0.6.336.** `h_persistence_skill.py` now computes skill vs the pair log's top-level `forecast` field (post-L3, post-specialists) alongside L4. Backward-compatible — L4 keys unchanged. **Two surprising findings on first read:**
  - **ch: L4 −0.29 → Prod −1.08.** The ch pipeline is 3.7× worse against persistence than L4 alone. **L3 for ch is doing damage**, not just L4. Corroborates the [[ch-persistence-gate-ship]] direction — persistence-first for ch across most regimes is right.
  - **wg: L4 +0.10 → Prod −0.09.** wg L3 pushes wg from marginal-positive persistence skill to negative — cross-refs the standing L3 drop-wg question (walkforward wants {wg, ch, cm} = current − ws).
  - cc: L4 +0.13 → Prod +0.03 (L3 costs cc skill, partial).
  - pp: L4 +0.18 → Prod +0.32 (calibrator meaningfully helps).
- **ch investigation → structural fix.** 07-11 [[ch-persistence-gap]] and 07-12 [[ch-persistence-gate-ship]] answered this: regime-cell-conditioned persistence gate, ENABLED=False, day 1/7. Flip decision 07-19.
- **cl short-lead persistence-blend → wired.** 07-13 v0.6.330 shipped `cl_persistence_short_lead.py` Stage 3 (ENABLED=False, day 1/7). Narrow: 0-5h all 9 regimes SHIP.
- **Persistence-skill columns on debug-page scorecard.** Wired 07-12 v0.6.328a as a scorecard-banner "vs Persistence" line (see [[07-12-session]]).
- **Persistence-skill post-ship watch — SHIPPED 07-13 v0.6.332.** Regression + at-risk alerts in digest exec summary. Today flags **ws +0.16** as at-risk.

## Cross-refs

Related: [[forecast-verification]] (measurement framework), [[07-10-session]] (Joe's "measure right" framing), [[project-cm-stage4-degradation]] (today's cm story), [[project-hypothesis-backlog]], [[project-todo]].
