---
name: feedback-redeploy-only-for-runtime-behavior
description: "Redeploy the collector only when actual runtime behavior changes — stamp_* or compute_* logic, forecast values, thresholds. Pure describe_applicability() or telemetry-text tweaks don't need a deploy; the change surfaces on the next natural instance cycle."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9a1f61c0-0486-4626-81ae-ca4da37e80cb
  modified: 2026-08-15T22:35:35.866Z
---

Don't reflexively `make deploy-collector` every time a `weather_collector/processors/*.py` file changes. Pause and ask: does this change the collector's runtime behavior (stamp values, forecast arrays, decision gates), or is it descriptor-text only (`describe_applicability()`, telemetry log strings, docstring)?

**Why**: identified 2026-08-15 v0.6.419. Fixed the Lc applicability descriptor to honor `_FIELD_SKIP` for cc + cl. Change was pure text in `describe_applicability()` — no forecast value changes, no gate logic changes, only what the debug page renders under "Applicability map." Deployed anyway. Joe caught it: "why did we need a deploy?" Answer: didn't. The change would have taken effect at the next natural Cloud Function instance cycle (idle timeout, cold start, or next legitimate deploy).

**How to apply**:

- **Redeploy** when: `stamp_*` output changes (forecast arrays, decision gates, applied-layer stamps), thresholds/tables the pipeline consumes, `ENABLED` flags flipped, `_CELL_SKIP` / `_FIELD_SKIP` / `_PR_L2_FIRE_CELLS` etc. mutated, module-level constants read at import that matter for forecasts, new curated JSON files that get bundled with the deploy (JSON alone auto-loads on next instance start; but if you want it *now*, redeploy).
- **Do NOT redeploy** when: `describe_applicability()` text only, docstrings, log message wording, comments. These populate the debug page but don't touch forecasts. Just commit + push; the change surfaces at the next instance cycle (usually within a few hours on Cloud Functions Gen 2 with `max_instances=1`).

If unsure, ask: "does the collector produce a numerically different `weather_data.json` next tick with this change?" If no → skip the deploy.

**Related**:
- [[project_publisher_cloud_function]] — publisher is a separate Cloud Function; same reasoning applies for its Python edits.
- MyWeather deploy sequence in CLAUDE.md — the general "collector-first if both changed" ordering still holds; this rule just says "not every collector edit needs to be in that sequence."
