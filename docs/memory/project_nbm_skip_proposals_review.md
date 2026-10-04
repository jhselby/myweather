---
name: nbm-skip-proposals-review
description: "Scheduled review of NBM walkforward's 44 per-regime skip proposals — wait until sustained-7d window is fully post-backstamp (2026-08-28), then curate durable cells into skip_table_nbm_curated.json."
metadata: 
  node_type: memory
  type: project
  originSessionId: 3686728f-c756-4644-9af6-ccbb2487150d
  modified: 2026-08-21T23:57:55.402Z
---

# NBM skip-proposals review — schedule 2026-08-28

**Context:** As of 2026-08-21 v0.6.462, `analysis/nbm_walkforward_validator.py`'s regime cross-cut is emitting 44 actionable per-regime SKIP proposals across L3_NBM (readable in the digest's "NBM skip-table proposals" block or `analysis/output/nbm_walkforward.json`). Curated `skip_table_nbm_curated.json` stays empty by design — proposals are advisory only.

**Why waiting:** L3_NBM was refit on live-only rows starting 2026-08-19, so today's proposals are based on ~2 days of post-refit data. Some cells (dp 0-5h at -104% to -125%) are almost certainly warmup artifacts, not durable behavior. The walkforward's sustained-7d window is fully post-backstamp on **2026-08-28** (backstamp shipped 08-19 → 7d + 1d buffer).

**How to apply:** On 2026-08-28, re-read the digest's "NBM skip-table proposals" block. Cells that appear on BOTH the 08-21 list and the 08-28 list (with similar magnitude) are durable and can be curated into `weather_collector/data/skip_table_nbm_curated.json`. Cells that shrink or vanish were warmup noise. `skip_table_nbm.py` reloads on module import, so a collector redeploy after edit is the ship step. Also update `_FITTED_AT` in the curated JSON to today's date.

**Runtime hook:** `weather_collector/processors/skip_table_nbm.should_skip()` reads the curated JSON at import; every NBM apply block in `forecast_snapshot.py` gates on it. A skip fires → the layer stamp is not written → selector's deepest-layer walk falls back naturally.

**Related:** [[nbm-structural-completion-plan]], [[08-21-evening-handoff]].
