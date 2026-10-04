---
name: 07-27-pm-session
description: "2026-07-27 Mon PM session, v0.6.382i → 382p (8 versions, one commit 96d049d). Two shipped structural findings: (1) pp Brier recalibration ceiling at ~5% — three halves-tests all HOLD, slope-stability discovered; (2) persistence-gate shadow-write bug — wdp shadow week silently empty, clp flip gate through 07-31 was blind, both now fixed. Also: D1 Drill-down retired; R0 audit extended to specialists; debug page wg/pp/D1 hygiene. Collector deployed by user; frontend pushed."
metadata: 
  node_type: memory
  type: project
  originSessionId: 0ee657df-54d0-435a-bbf2-1a02cf3244b5
  modified: 2026-07-27T22:11:05.859Z
---

# 07-27 PM Session — v0.6.382i → 382p

Followed on from morning 07-27 session (v0.6.382 wdp flip + 8 debug-page passes → v0.6.382h). Session commit: **96d049d**.

## Ships

| Ver | Change |
|---|---|
| i | wg row rewording + R&D subheading collapsibility + per-field snapshot state→reason→next template |
| j | pp headline/snapshot number consistency (0.0% Brier live = raw) |
| k | pp Brier reliability rewired (verdict machinery + GCS upload); new `h_pp_bin_calibration.py` (halves HOLD) |
| l | new `h_pp_platt_calibration.py` (2-param logistic halves HOLD) — discovery: slope stationary |
| m | D1 Drill-down scope-restricted to t/h/dp (later reverted → retired outright) |
| n | R0 extended from L3/L4 audit to per-layer + specialist audit (Lsr/Lc/chp/clp/wdp + real Production) |
| o | D1 Drill-down retired (~190 lines gone) |
| p | **Structural fix**: persistence-gate ENABLED-guard shadow-write bug in wdp/clp/chp |

## Key findings (durable — new session should know)

### 1. pp recalibration is at its ceiling — see [[project_pp_recalibration_session]]

Three halves-mode Stage 0 corrective tests ran, ALL HOLD:
- `h_pp_bin_calibration.py` — per-decile lift table (fit A / score B: +6.46%; fit B / score A: +0.87%)
- `h_pp_platt_calibration.py` — 2-param `σ(a + b·logit(p))` (fit A / score B: +6.56%; fit B / score A: +10.45%)
- `h_pp_kalman_recalibrate.py` — fixed b + rolling-window a_t across 24h/72h/168h windows (all HOLD)

Root cause: pp Brier ≈ 0.086 with **Reliability component ≈ 0.005 (~5% of total)**. Even perfect recalibration can only cut Brier by ~5%, and halves-inconsistency in the LEVEL burns more than that per attempt. Uncertainty + Resolution dominate.

**Discovery worth keeping**: Platt SLOPE is stable across halves (|Δb|=0.06 well under threshold); only INTERCEPT drifts with base rate. So the miscalibration shape is a stationary invariant of raw HRRR pp — it just doesn't ship pooled.

**Next candidate booked**: `h_pp_source_blend.py` — HRRR + Pirate + GFS pp blend attacks the Resolution term (larger attackable surface than Reliability). All three sources already fetched; no new instrumentation. If blend also fails, accept pp = L1-only as the physics floor.

### 2. Persistence-gate shadow-write bug — see [[feedback_persistence_gate_shadow_write]]

wdp/clp/chp all had `if ENABLED and persist_val is not None:` guarding ALL hourly-array writes. During Stage 3 ENABLED=False, shadow values only landed in per-tick telemetry blob (`weather_data["<name>_persistence_gate"]`) which no downstream consumer reads.

**Impact**:
- wdp: entire 07-20 → 07-27 shadow week produced ZERO pair-log-visible data. Today's flip (v0.6.382) was made on Stage 2 preview + preflight only, NOT Stage 3 shadow verification. We thought it was.
- clp: 7-day flip gate through 07-31 was evaluating against zero real shadow data (7,704 forecast_clp rows all byte-identical to forecast_l6 fallback duplicates).
- chp: same bug but ENABLED=True since 07-19 masks it post-ship.

**Fix (v0.6.382p, deployed by user 07-27 PM)**: all three files now write `hourly[HOURLY_KEY + "_shadow_<name>"]` unconditionally; snapshot writer prefers shadow key over live-array fallback. clp flip-gate through 07-31 now generates real shadow data from next collector tick forward.

**Class family**: [[feedback_streak_infra_dormancy]] + [[feedback_stated_intent_vs_code_behavior]] + [[feedback_verify_writers_for_read_paths]] (mirror image — grep for CONSUMER before shipping a writer).

## Debug page — other changes

- **R0**: renamed from "L3/L4 audit" to "Per-layer audit". Added Specialists column (chained Lc → chp/clp/wdp per SPECIALIST_STACK hardcoded map) + real Production column. ⚠ banners extended to specialists. Purpose shift: from L3/L4 promotion gate (superseded by Stage 3 flip machinery) to post-ship-watch dashboard.
- **D1 Drill-down retired**: user never looked at it + reconstruction had gone stale post-Lc/chp/wdp/skip-tables. `_drillComputeSeries` kept because L2 raw-model section still reads it.
- **wg row** (per-field snapshot): now leads with "existing asymmetric wg SKIP table is LIVE" — old wording conflated "held" with "nothing wg-shaped running."
- **R&D subheadings**: Diagnostics / Tools / Candidates / Experiments now collapsible `<details>` groups. Stage 0 explorations promoted to first-class `<details id="stage0-explorations">` (E1). Lt reclassified from "[RETIRED LAYER]" to "E2. Lt — Cove microclimate telemetry probe" — the correction returns 0.0 but the gradient log still appends daily.
- **pp Brier reliability panel** (under per-field snapshot): renders live reliability decomposition + halves-verdict card with color-coded gap coloring.
- **Per-field snapshot template**: rewrote t/h/ws/cl/pp/pa/wd rows to state→reason→next; each row now leads with current state, then why, then next action or explicit "no open work."

## Post-ship watches active

- wdp: Day 0/14 through 08-10. Real data starts from today's flip forward (shadow week produced nothing). First reads on 0-5h bands (pre_frontal/se_flow/sw_flow) land tonight; 12-23h calm tomorrow AM; 24-47h calm day 2-3.
- clp: 7-day flip gate through 07-31 — now producing real shadow data (post-deploy) but only for 4 days before decision. Recommend extending gate to give the newly-fixed shadow write a full 7 days before flipping.
- All other watches unchanged from 07-27 AM session.

## Files touched this session

**Analysis (4):**
- `analysis/pp_brier_reliability.py` (rewired)
- `analysis/h_pp_bin_calibration.py` (new)
- `analysis/h_pp_platt_calibration.py` (new)
- `analysis/h_pp_kalman_recalibrate.py` (new)

**Collector (4):**
- `weather_collector/processors/wd_persistence_gate.py`
- `weather_collector/processors/cl_persistence_gate.py`
- `weather_collector/processors/ch_persistence_gate.py`
- `weather_collector/processors/forecast_snapshot.py`

**Frontend (5):**
- `corrections_debug.html`
- `index.html`
- `docs/CHANGELOG.md`
- `sw.js`, `version.json` (build.py)

## Related

- [[project_pp_recalibration_session]] — deep-dive on the pp session, next-candidate design
- [[feedback_persistence_gate_shadow_write]] — preflight-style rule for future persistence-gate specialists
- [[project_wd_persistence_gate]] — wdp status; needs update noting shadow week was silently empty
- [[project_cl_persistence_investigation]] — clp Stage 3 flip gate through 07-31; needs update noting the gate was reading zero real data pre-fix
