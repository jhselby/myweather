---
name: layer-shape-sentry
description: Layer-shape sentry in digest (v0.6.390d 2026-07-30). Fires per-band ⚠ when production layer hurts raw by ≥+10% at any lead band; fires τ-suspect ★ when production helps at 0-5h AND hurts at any later band. Complements regression_sentry which only sees day-totals.
metadata: 
  node_type: memory
  type: project
  originSessionId: ee3022f3-1d0e-4e93-abfb-dbc558df1928
  modified: 2026-07-30T23:07:12.460Z
---

# Layer-shape sentry

**Ship:** v0.6.390d 2026-07-30. Motivation: h L2 helped at 0-5h (−18%) and hurt at 6-47h (+11-13%) for 5+ days but daily-total Prod-vs-Raw stayed under regression_sentry's +15% threshold. Joe caught it manually asking "what's happened to h." The instrument set had a gap.

## What it fires on

Two alert classes, ranked τ-suspect first (most actionable):

1. **τ-suspect ★** — production layer HELPS at 0-5h (delta ≤ −5%) AND HURTS at any later band (delta ≥ +5%). Classic "decay time-constant too long" signature: bias signal is real at short lead but the fitter keeps it alive too far into the horizon. Fix is shortening τ or adding a lead-band SKIP.
2. **Per-band ⚠** — production hurts raw by ≥+10% at any band (n ≥ 100). Broader catch-all; τ-suspect is a subset that also gets flagged here.

## Where

`analysis/runlog/build_executive_summary.py`:
- Constants: `LAYER_SHAPE_THRESHOLD_PCT = 10.0`, `LAYER_SHAPE_MIN_N_PER_BAND = 100`, `LAYER_SHAPE_TAU_HELP_PCT = -5.0`, `LAYER_SHAPE_TAU_HURT_PCT = +5.0`.
- Function: `layer_shape_sentry()`. Reads tsDoc from GCS via `analysis._cache.cached_path` (6h max age); silent on missing file.
- Wired into digest output after `regression_sentry()`, before `persistence_skill_watch()`.

## What it doesn't do

- Doesn't distinguish "actively broken" from "recovering from a ship" — a field with a trailing 7-day window still containing pre-fix days will fire until the window rolls over. Currently cc/cl/ws all firing for this reason. Would benefit from a `KNOWN_HEALING_UNTIL` allowlist keyed by (field, layer, band, date) — not implemented yet.
- Doesn't fire day-over-day. Reads the current tsDoc snapshot only. That's fine for "is this broken now" but doesn't tell you when a break started. Combine with mae_over_time chart or regression_sentry for temporal reads.
- Doesn't cover intermediate layers (L2 when L4 is applied, etc.) — only the production layer. Intermediate-layer breakage doesn't affect user-facing output.

## Related
- [[project_lc_regime_conditional]] — the crisis that motivated all daily-instrument work this week
- [[feedback_ratio_over_absolute]] — same principle: honest signal ratio, not absolute noise
- Regression sentry (v0.6.389i) — daily-total Prod-vs-Raw ≥+15% for 2 days; this sentry's per-band complement.
