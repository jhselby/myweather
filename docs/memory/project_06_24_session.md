---
name: project-06-24-session
description: "2026-06-24 marathon — 5 Stage 2 ships (cc→L4, C1f, h K-taper), 2 same-day orthogonality kills (wind_shift_rate, C1g), Stage 4 audit infra built. Pipeline: 10 → 6 active Stage 1 candidates."
metadata: 
  node_type: memory
  type: project
  originSessionId: a933ef0e-f53e-46b4-802a-0d1b833732d0
---

## Headline

Single-day marathon. v0.6.213 → v0.6.220 (8 versions, all deployed and verified). Three Stage 2 promotions, two same-day orthogonality kills, one piece of audit infrastructure, one new debug-page convention.

## What shipped to production

| Version | Change | File |
|---|---|---|
| v0.6.213 | Stage 1 batch re-run; 4 new Stage 0 scripts (wind_shift_rate, mesonet_conf, persistence, lightning_proximity) | analysis/ + debug page |
| v0.6.214 | **cc added to L4_FIELDS** | `weather_collector/processors/decay_apply.py:70` |
| v0.6.215 | **C1f precip_fc>0 wired as 4th confidence-layer axis** (v3 table) | `analysis/c1_confidence_calibration_v2.py` + `weather_collector/processors/confidence_layer.py` |
| v0.6.216 | Stage 4 audit infra + wind_shift_rate killed | `analysis/c1_stage4_audit.py` + `analysis/h_wind_shift_rate_orthogonality.py` |
| v0.6.217 | C1g killed | `analysis/h_c1g_orthogonality.py` |
| v0.6.218 | **Humidity K-taper (soft_ramp 1.0 → 0.4)** | `weather_collector/processors/corrected_hourly.py` (new `_soft_ramp_factors()` helper) |
| v0.6.219 | Debug page cleanup (stale count + dup fragment) | corrections_debug.html |
| v0.6.220 | "Since last curation" block at top of debug page | corrections_debug.html |

## What the discipline produced

Two Tier-2 candidates that passed Stage 0 magnitude tests both failed orthogonality:
- **wind_shift_rate**: Stage 0 showed rotating ≥80° class elevates cm/ch +24-33% MAE. Ortho check: 1 ortho / 22 redundant / 2 confounded / 11 ambiguous vs C1a. C1a (regime transition) already captures the signal — wind shifts and regime transitions co-occur. See [[feedback-orthogonality-gate]].
- **C1g (RH ≥95% fog)**: Stage 0 showed cm +134%, ch +149%. Ortho check vs C1f + cc-saturation: 1 ortho / 69 redundant. The elevation was sampling-driven — fog co-occurs heavily with rain forecast and high-cc forecast. In F=False/S=False subsets fog rows actually have *smaller* MAE than non-fog (ratio 0.02–0.25× on cl/cm/ch).

## Stage 4 audit infra (deferred verdict)

Built `analysis/c1_stage4_audit.py`. Two views: legacy single-axis cells (transition × stable) and multi-axis (Q × pt × trans × c1f).

- **Legacy axis (62 SHIP cells): NOT READY.** 17 PASS / 20 WATCH / 25 FAIL. FAILs dominated by pp (Brier-evaluated, MAE is the wrong yardstick) and pa (precip amount, bursty). Non-precip subset would likely pass cleanly — one-line filter follow-up worth running soon.
- **Multi-axis (296 SHIP cells): DEFERRED until ~2026-07-04.** `cluster_spread_log.json` only goes back to 06-20 (~4 days); audit needs 14d to reach back into calib window. See [[project-stage4-audit]].

## Operational lessons hit live

- **Don't use raw `urllib.request.urlopen` for ad-hoc probes either.** Joe caught me running two diagnostic scripts (day-count + cluster_spread range check) with raw urllib instead of `cached_path` — two extra pair-log streams (~70MB each) charged to GCS egress. Reinforced in [[feedback-analysis-cache]].
- **GitHub Pages deploys are serial.** Three back-to-back pushes (.218, .219, .220) caused the Pages deploy queue to lock on the in-progress .218. Required manually re-running the failed workflow to unstick. Future: bundle related ships into one push, or wait for prior deploy to land before pushing the next.

## State at end of day

- **Stage 1 pipeline: 6 active candidates** (was 10 this morning). Remaining: Cloud saturation-unbiasing (Tier 2), C1e bidirectional (Tier 2→3? weakened today), C1h trend-direction (Tier 3), dp depression regime (Tier 3), cm→L4 ride-along (borderline), KBOS-vs-KBVY gated 06-26.
- **Correction stack v0.6.218 live:** L1 → L2 → L3 → L4. L2 humidity uses soft_ramp (1.0 → 0.4 across leads 0-24, floor 0.4 thereafter); t and pr stay flat exp-decay. L3 whitelist `{ws, wg, ch, cm, pp}`. **L4 whitelist now `{ch, cc}`** (cc added today). cm rides along as borderline candidate.
- **C1 confidence layer: v3 (4-axis), ENABLED=False.** Curated v3 table: 296 SHIP / 42 MARGINAL / 1048 SKIP across 39 axis-keys. Live `multi_hits` ~53/56 cells per tick when axis matches.

## Monitor (7-day window)

- cc L4 vs L3 MAE on live audit table. Revert if <3%.
- h L4 vs L3 MAE on live audit table. Revert if <3%.

## Next dates

- **2026-06-26 (Fri):** KBOS-vs-KBVY cloud disagreement first read (7 days of dual-source data).
- **2026-06-29 (Mon):** Walk-forward L3/L4 #4 + Stage 1 weekly re-reads (cloud saturation, C1e if more frontal passages, C1h, dp depression).
- **2026-07-04 (Sat):** Stage 4 multi-axis audit becomes possible (cluster_spread log reaches 14d).
- **Weekly Sun morning (06-28, 07-05, 07-12):** Marine-layer Stage 2 re-read.

Related: [[project-todo]], [[project-hypothesis-backlog]], [[project-correction-stack]], [[project-c1-pivot-to-confidence]], [[project-stage4-audit]], [[feedback-orthogonality-gate]], [[feedback-debug-page-canon]].
