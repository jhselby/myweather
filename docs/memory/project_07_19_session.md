---
name: project-07-19-session
description: Sun 07-19. v0.6.358 ch persistence LIVE + pa τ revert + 8-script fossil-window sweep. v0.6.358a debug page Rule 5 sweep. Caught h/l4 narrow-add fossil that would have shipped garbage. Digest stale-window guard deferred to v0.6.359.
metadata: 
  node_type: memory
  type: project
  originSessionId: af17d512-4939-4875-aa25-7dc730a23e19
  modified: 2026-07-19T13:33:47.208Z
---

Sunday 2026-07-19. Two ships, one caught fossil.

**v0.6.358** — three coupled changes:
1. `ch_persistence_gate.ENABLED = True` (07-12 wired → LIVE 07-19). Refreshed-window Stage 2 rerun: 27 SHIP / 6 MARGIN / 3 SKIP / 1 THIN of 37 (was 22/6/8/1 on stale windows). Live gate shape: sw_flow/24-47 promoted SKIP→SHIP (n=26,543, biggest ch bucket); calm/24-47 demoted SHIP→SKIP. Regime_gate FULL MAE −29.53%, halves A −17.84% / B −37.61%. persist-only LANDMARK still standing. 14-day watch through 08-02.
2. `TAU_DAYS_BY_FIELD["pa"]` removed (revert to global τ=14). Today's `decay_tau_tuning`: pa +0.9% vs τ=14 (was +5.9% yesterday when v0.6.357 shipped pa=7). Same fact pattern as 07-02 ws revert. `pp: 28` is also below the 5% floor now (+3.2%, was +11.1% on 06-21) — flagged for next τ-audit day, not reverted (needs its own multi-read history).
3. Fossil-window sweep. Slid 8 analysis scripts' windows forward 8 days (06-11→07-11 → 06-19→07-19): `h_ch_persistence_blend[_stage2].py`, `h_wg_residual_persistence_stage2.py`, `h_wg_l3_regression_stage1.py`, `h_ws_l3_regression_stage1.py`, `h_t_l2_regression_stage1.py`, `h_cl_linear_ramp_stage2.py`, `h_full_regime_sweep.py`. Refresh caught a fossil: **h/l4 narrow-add** collapsed from ✓ CLEARED (7/7, 2 SHIP cells, "on rails 6 days") to ⏳ 1/7 (0 SHIP cells). Would have shipped a broken gate. New reusable lesson [[feedback_fossil_windows]].

**07-21 candidates all survived refresh with shifted/expanded shapes:**
- ws L3 skip-table: 9 SKIP cells (was 10); different regime set
- wg L3 skip-table: 12 SKIP cells (was 6); adds all sea_breeze bands + frontal/12-23 + ne_flow/6-11 + unknown/6-11+12-23
- wg residual persistence: 8 SHIP (was 6); adds se_flow 6-11 + 12-23 + unknown 24-47
- cl linear ramp: MODERATE → STRONG (11 → 15 SHIP cells) — flip candidate now, day 7/7

**v0.6.358a** — debug page Rule 5 sweep. Updated ch persistence gate rows across ~10 sites; h/l4 narrow-add across ~5 sites; counter advances 07-18 → 07-19; candidates table refreshed; pa τ history + Applicability description updated with the revert.

**Verdict flips in today's digest** (all consistent with above):
- decay_tau_tuning: IMPLEMENT → KEEP τ=14 GLOBAL (drove pa revert)
- r5_cove_analysis: SHIP → HOLD (cove already dormant, no action)
- sr_sea_breeze_lsr_refit_stage2: PROMOTE → MARGINAL (blocked LSR_ENABLED flip today)
- pressure_tendency_stage2 / cluster_spread_orthogonality: PROMOTE → STABLE (cleanup)

**Held today** (didn't ship despite gates cleared):
- LSR_ENABLED → False (gate cleared 7/7) — Stage 2 refit flipped to MARGINAL same run; killing Lsr would lose the +17.4% sea_breeze intervention that `sr_shortwave_bias` still shows. Investigate before killing.
- h/l4 narrow-add — fossil caught.

**Anomaly detector still lit:** 10 WATCH + MLC in-bin bias COLLAPSE (+30.57 → +4.78). Cloud fields in real distribution shift. The 14-day ch persistence watch has to account for this.

**v0.6.359** (shipped later same day) — digest stale-window guard. `stale_window_audit()` in `build_executive_summary.py` scans every `analysis/*.py` for date literals in `WIN_*` assignments; any script whose max window-date is >3d behind today is flagged in a `⚠ STALE ANALYSIS WINDOWS` section at the top of DIGEST.txt exec summary. First run caught a 9th fossil the manual sweep missed: `h_cl_persistence_blend.py`. Slid its windows to 06-19→07-19; post-slide audit reports 0 stale scripts.

**Post-digest-rerun findings (v0.6.359a):**
- **cl narrow persistence — HOLD, not shipping.** Refreshed `h_cl_persistence_blend` verdict: "mixed — regime_gate doesn't cleanly beat baseline on halves check." Only 4/9 regimes SHIP at 0-5h (se_flow, ne_flow, calm, unknown); design gate requires all 9 → gate stays OFF permanently per the 07-13 criterion. Sibling `h_cl_linear_ramp_stage2` DID flip MODERATE → STRONG (15 SHIP cells at τ=36) — different mechanism (linear ramp, not persistence blend), worth separate Stage 2 investigation but not shipping now.
- **NEW candidate: hsf (hours-since-front)**. `h_hsf_orthogonality` flipped KILL → PROMOTE on refreshed digest: "hours-since-front is independent of C1a and C1e." hsf was killed 06-27 as C1a re-skin — the ortho check now disagrees. Streak 1/7 today; needs 6 more days of PROMOTE, then Stage 1 wire-up.
- **Pre-frontal streak reset**: 7/7 CLEARED at 05:52 → 1/7 at 09:01 rerun, still 5 SHIP cells but cell identity drifted. Normal borderline churn (not a fossil concern). Streak restarts.

**Ships summary for 07-19:** v0.6.358 (ch LIVE + pa revert + fossil sweep) + v0.6.358a (Rule 5 sweep) + v0.6.359 (stale-window guard) + v0.6.359a (cl HOLD + hsf discovery + pre-frontal reset notes).

Delete this memory after 2026-07-26 (once h/l4 retest happens and the ch 14-day watch is halfway through).
