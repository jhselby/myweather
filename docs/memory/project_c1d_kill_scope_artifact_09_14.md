---
name: c1d-kill-scope-artifact-09-14
description: "09-14 investigation of the C1d KILL digest verdict. Root finding: KILL is a test-scope artifact of MIN_N_PER_CELL=100, which limits the tool to 24-47h cells that all happen to be redundant. Relaxed n=30 test at all 4 bands: 20/32 redundant = 62.5%, below the 70% KILL threshold, verdict flips to MIXED. Also surfaces cc/0-5h as clean ORTHOGONAL (2.56×/2.82× on C1a, 2.56×/3.32× on C1e) — a signal a KILL would erase. Do NOT unwire C1d."
metadata: 
  node_type: memory
  type: project
  originSessionId: c656ec98-2726-4d09-8e93-674722e5843d
  modified: 2026-09-14T14:32:20.361Z
---

# C1d KILL — investigation, verdict fragile

## The digest signal

`h_cloud_disagreement_orthogonality` today emitted:

> → KILL C1d: signal captured by C1a/C1e (6/8 redundant).

Prior read (in memory): `MIXED: 2 orthogonal / 4 redundant / 2 other. Narrow promote on the orthogonal cells.` The verdict flipped week-over-week.

## Investigation

Tool's KILL threshold: `redundant ≥ 0.7 × total_cells`. Tool's per-cell n floor: `MIN_N_PER_CELL = 100`. At n≥100, only 24-47h cells clear the floor (4 fields × 2 axes = 8 tests).

Replicated at MIN_N=30 to include all 4 bands (scratchpad: `c1d_ortho_full.py`):

| MIN_N | Cells tested | ORTHO | REDUNDANT | CONFOUNDED | AMBIGUOUS | Redundant % | Verdict |
|---|---|---|---|---|---|---|---|
| 100 (default) | 8 | 0 | 6 | 1 | 1 | 75% | **KILL** |
| 30 (relaxed) | 32 | 2 | 20 | 2 | 8 | 62.5% | **MIXED** (below 70%) |

The KILL is scope-limited. At the default n floor the tool sees only cells that happen to all be redundant.

## Live C1d SHIP cells (5) vs the axes

| Cell | Live premium | vs C1a (no-trans / trans) | vs C1e (no-front / post-front) |
|---|---|---|---|
| cc/12-23h | NARROW −23.9% | 0.77× / 0.90× | 0.77× / 0.28× |
| cl/24-47h | NARROW −10.9% | 1.02× / 0.95× | 1.02× / 0.50× |
| cl/12-23h | NARROW −28.1% | 0.82× / 0.92× | 0.82× / 0.57× |
| ch/24-47h | NARROW −16.4% | 0.93× / 1.26× | 0.93× / 3.20× |
| ch/12-23h | WIDEN +25.3% | 1.17× / 1.34× | 1.17× / 0.20× |

All 5 SHIP cells produce ratios ≤1.20 in the baseline (C1a=False, C1e=False) state — that's the definition of REDUNDANT in the tool. The signals are captured by C1a's transition rule or C1e's post-frontal rule.

## Real find: `cc/0-5h` is ORTHOGONAL on both axes

At MIN_N=30:
- vs C1a: 2.56× (no-trans) / 2.82× (trans) — signal independent of C1a
- vs C1e: 2.56× (no-front) / 3.32× (post-front) — signal independent of C1e

cc/0-5h is NOT currently a C1d SHIP cell. A KILL would erase this real signal. `c1d_curated.json` shows cc/0-5h premium +137.92% but no SHIP status. The tool's curation gate at n≥1000 kept it out — could revisit for narrow-cell inclusion.

## `ch/24-47h` calibration flag

Live is NARROW −16.4% (HIGH-σ → narrower confidence band). But observed post-front ratio σH/σL = 3.20× (HIGH-σ has 3.2× MORE error, should WIDEN). The calibration is being dragged one way by baseline (0.93×) and the other by post-front (3.20×). C1a-conditional calibration might produce cleaner premiums per (band, C1a-state) instead of pooled.

## Recommendation

**Do NOT unwire C1d.** The KILL verdict is fragile:
- Scope-limited to 24-47h at default MIN_N.
- Relaxed n test surfaces 2 clean ORTHOGONAL cells + 2 CONFOUNDED cells.
- Would erase real signal at cc/0-5h.

## Follow-ups (queued, not today)

1. **Retune MIN_N in h_cloud_disagreement_orthogonality.py** to 50 or 60. At those thresholds all 4 bands clear on both axes without introducing noise from very thin sub-populations. Verdict would consistently show MIXED, not KILL — matches reality.
2. **cc/0-5h narrow-promote candidate.** Clean ORTHOGONAL signal (2.56× / 2.82× / 3.32×). Currently unshipped (premium +137.92% at n_low=1675/n_high=1126 — the +137% might be too noisy for SHIP under strict rules, but the ratios are clean).
3. **ch/24-47h re-calibration** as a C1a-conditional cell (or split into ch/24-47h × C1a-True and × C1a-False sub-cells). Current pooled premium may be miscalibrated because two regimes disagree in direction.

## How to apply

- On next digest read, if `h_cloud_disagreement_orthogonality` says KILL again, remember: scope artifact at MIN_N=100.
- Add to `feedback_digest_triage_discipline` a step: for KILL verdicts on live axes, verify the tool's test scope covers ALL live SHIP cells before treating it as actionable. This tool tests only cells that clear its own n floor — it can KILL an axis while being blind to the axis's live SHIP cells at other bands.

## Related

- [[feedback_digest_triage_discipline]] — the "check for companion tools" step. This is a similar class: check test scope vs live-target scope before acting on a KILL.
- [[feedback_pooled_n_time_thin]] — pooled n-large ≠ time-robust. Related but different — this is about scope-thin, not time-thin.
- `weather_collector/data/c1d_curated.json` — live SHIP list (5 cells).
- `weather_collector/processors/confidence_layer.py` — C1d wire.
- Analysis: `analysis/h_cloud_disagreement_orthogonality.py`, script under `scratchpad/c1d_ortho_full.py` for MIN_N=30 replication.
