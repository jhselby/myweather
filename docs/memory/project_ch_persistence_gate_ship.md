---
name: ch-persistence-gate-ship
description: 07-12 v0.6.327 shipped ch persistence gate Stage 3 (ENABLED=False). FLIPPED 07-19 v0.6.358. **07-27 v0.6.382t emergency demote of 6 clear-regression cells** after L6-baseline Stage 2 rebuild ([[project_chp_midlead_regression_watch]]) showed Stage 2 was measured against forecast_l4 (pre-Lc baseline) — post-Lc-flip the honest baseline is forecast_l6, and the honest SHIP set is 5 real cells not 28. Rollup 19/9/7/2 → 14/8/13/2. Full-shape refinement to the 5-cell L6-baseline SHIP set pending 7-day live-layer change gate (day 1/7 as of 07-28).
metadata: 
  node_type: memory
  type: project
  originSessionId: 01566fb8-1905-4804-8e7a-7cd634f42cee
  modified: 2026-07-28T10:37:32.114Z
---

Shipped 2026-07-12 v0.6.327 as ENABLED=False. Follow-on to [[project_ch_persistence_gap]] and [[project_persistence_skill_baseline]].

**Design:** For ch, when regime != frontal AND (regime, lead_band) verdict is SHIP or MARGIN, replace L4/Lc-corrected `hourly.cloud_cover_high` with persistence-of-obs (flat carry of joined ch obs at forecast issue time). SKIP cells + frontal fall back to L4.

**Stage 2 preview verdicts (h_ch_persistence_blend_stage2.py, 30d window, halves-verified):**
- 22 SHIP / 6 MARGIN / 8 SKIP / 1 THIN of 37 judged cells.
- SKIP concentration: sw_flow 6-11/12-23/24-47 (3 of 4 bands sign-flip between halves), pre_frontal/24-47 (+9.6% full-window loss, n=11,983), nw_flow 6-11 + 24-47, ne_flow/24-47, sea_breeze/12-23.
- MARGIN cells (fire at runtime): nw_flow/12-23, unknown/12-23 + 4 frontal no-ops.

**Why cell-conditioned instead of clean gate:** Pooled Stage 1 said ~20% pooled MAE improvement. Halves check on Stage 2 revealed that "clean gate everywhere except frontal" would have regressed real volume — pre_frontal/24-47 alone is n=11,983 with +9.6% loss. sw_flow halves sign-flips (Δ_A -35% / Δ_B +19%) are the exact recency-dependent failure mode the halves gate is designed to catch. See [[feedback_regime_gate_first]].

**Persistence source at runtime (priority order):**
1. `cloud_l2_meta.fields_applied[cloud_cover_high].obs_mean` — pure KBOS+KBVY blended obs, pre-Kalman shrinkage. Matches Stage 1 semantic.
2. `hourly[0].cloud_cover_high` — Kalman-blended value (deviates from pure obs only when K<1).
3. If neither, gate is a no-op that tick.

**Files:**
- Processor: `weather_collector/processors/ch_persistence_gate.py`
- Curated table: `weather_collector/data/ch_persistence_gate_curated.json`
- Stage 2 preview script: `analysis/h_ch_persistence_blend_stage2.py`
- Wired in `collector.py` AFTER `cloud_saturation_correction` (Lc). Ordering rationale: Lc's per-bin shift was fit against L4-corrected ch; applying it on top of persistence would re-introduce bias.

**Live-layer flip criteria (per [[feedback_whitelist_promotion_gate]]):**
- 7-day agreement on the SHIP/SKIP cell set (weekly Sunday re-run of Stage 2).
- No new halves-sign flips in previously-SHIP cells.
- If any SHIP cell degrades to SKIP mid-window, cell moves to SKIP list (fall back to L4), gate stays ENABLED for the rest.

**First-tick verification (07-12 nw_flow):** 5 fires 0-5 (SHIP), 12 fires 12-23 (MARGIN), 0 fires 6-11 (SKIP), 0 fires 24-47 (SKIP). Matches Stage 2 preview exactly. Applicability_map descriptor wired and rendering.

**Landmark thread — persistence-only vs regime_gate — RESOLVED 07-14:** Stage 1 flagged that persistence-only ALSO beats baseline on halves pooled. Full head-to-head on today's 30d window:

| scenario | Half A MAE | Half B MAE | Full MAE |
|---|---:|---:|---:|
| baseline (L4) | 20.181 | 31.387 | 25.155 |
| regime_gate (shipped) | 15.046 | 24.161 | **19.092** |
| persist_only (global) | 14.993 | 24.288 | **19.119** |

**Pooled tied within noise** (0.14% relative, 0.027 MAE). Persist_only wins half A by 0.05 MAE; gate wins half B by 0.13 MAE. **Keep the shipped gate.** Rationale: (a) the gate has per-cell halves-stability enforcement — persist_only doesn't, so cells like pre_frontal/24-47 (n=11,611, persist_only LOSES to L4 by +5.07% pooled) get L4 fallback under the gate but degrade under persist_only; (b) halves-unstable cells (ne_flow/24-47, nw_flow/6-11+24-47, sw_flow/6-11+12-23+24-47) get L4 fallback under gate — persist_only accepts the instability; (c) frontal (n=4,631) uses L4 by design in the gate, and persist_only would use persistence with no direct evidence it beats L4 there. Landmark's "consider pulling ch from L3+L4 entirely" was misleading — the "consider" clause only meant persist_only ALSO clears halves-vs-baseline, not that it beats the gate. Do NOT rip out ch from L3+L4; the shipped gate is the right architecture and 07-19 flip proceeds as planned.

Related: [[project_ch_persistence_gap]], [[project_persistence_skill_baseline]] (ch = "NO SKILL" at every band despite L3+L4).

**07-13 corroborating evidence (v0.6.336):** Added Production-vs-L4 persistence skill computation to `h_persistence_skill.py`. First read: **ch L4-only skill = −0.29, Prod skill = −1.08.** The ch pipeline (L3 firing + L4) is 3.7× worse against persistence than L4 alone. This is quantitative confirmation that L3's contribution on ch is doing damage, not just L4 being wrong. Strengthens the case for the gate flip at 07-19 — going persistence-first for ch in non-frontal cells removes both the L3 and L4 stack damage in those cells at once.

**07-14 SHIP-set flex (informational, non-blocking):** Weekly Stage 2 re-fit today shows 24 SHIP / 5 MARGIN / 7 SKIP / 1 THIN (was 22 SHIP / 6 MARGIN / 8 SKIP at 07-12 ship). One previously-SKIP cell now SHIPs. This is a change in the safer direction (more cells benefit from persistence) but a formal SHIP-set change nonetheless — the 07-19 stability check will register it. Decision at flip time: if the changed cell has stable halves in today's fit (verify then), flex the gate to include it and flip. If halves are unstable, hold that cell at SKIP and flip the rest.

**Similar candidates worth checking next:** cl and cm are the other "NO SKILL" fields from persistence baseline. Same regime-gated approach likely applies. Queue for a future Sunday digest.

---

**07-19 v0.6.358 FLIPPED to ENABLED=True.** 27 SHIP / 6 MARGIN / 3 SKIP / 1 THIN on refreshed windows (up from 22/6/8/1 on stale). Live gate shape: sw_flow/24-47 promoted SKIP→SHIP (n=26,543, biggest ch bucket); calm/24-47 demoted SHIP→SKIP. 14-day post-ship watch through 08-02.

**07-20 v0.6.369 — chp per-layer attribution wired.** Day 2 of the 14-day watch. Discovered that `decay_fit.py:685` per-layer accumulator loop iterated only `("l1"..."l6")` — no `chp`. Pair rows carried `error_chp` (via v0.6.361 forecast_error_log), Production series consumed it correctly via applied_layer stamping (decay_fit.py:712-729), but chp was invisible as its own per-lead MAE series in tsd. `LAYER_LINES` + `_layerApplied` in corrections_debug.html also missing chp/clp branches. Fixed at 4 sites: decay_fit.py:685 + :1162 loops extended to include chp/clp; LAYER_LINES gained chp (#4ad29a green) + clp (#8cd278 light green) entries; `_layerApplied` gained `chp→ch` and `clp→cl` filter branches. Same [[feedback_specialist_attribution_wiring]] pattern — third catch of the "silent absorption into another layer's aggregate" bug (after Lsr v0.6.249 and Lc v0.6.355→356).

**First honest chp reads post-fix (n=25-30/lead, day 2 of 14 — small sample, wide CIs, but pattern unambiguous):**

| lead | chp MAE | Lc MAE | Δ % |
|-----:|--------:|-------:|----:|
| 0 | 9.4 | 9.9 | −5% |
| 1 | 2.4 | 12.4 | **−81%** |
| 2 | 4.9 | 11.3 | **−56%** |
| 3 | 7.7 | 13.1 | **−42%** |
| 4 | 10.2 | 12.4 | −18% |
| 5 | 12.8 | 12.4 | +3% |

chp fades around lead 5-6 as the persistence prior loses grip (expected — high cloud autocorr timescale runs out). Compellingly matches the Stage 2 predicted regime-conditional lifts. Verdict-quality reads land around day 7 (07-26).

**Watch operational check going forward:** per-band accuracy tables on the debug page for ch now show a real chp column alongside l1..l6. Watch for chp series drifting up toward Lc's line (would indicate the persistence prior weakening) OR sample n staying flat lead-by-lead (would indicate gate stopped firing). Weekly Sunday Stage 2 re-run continues to govern the SHIP cell set.
