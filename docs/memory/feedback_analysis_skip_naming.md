---
name: feedback-analysis-skip-naming
description: "One-shot maintenance scripts in analysis/ must be named `<name>.skip.py` or the daily digest will FAIL them every morning."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b5cc4ed2-5f65-4bf9-8d07-bd839cb57caa
  modified: 2026-08-03T11:44:39.960Z
---

Any one-shot maintenance script (backfills, one-time cleanups, migrations) added under `analysis/` must be named `<name>.skip.py` — not `<name>.py`.

**Why:** `analysis/runlog/run_digest.sh` iterates `analysis/*.py` every morning and runs each via `python3 -m analysis.<name>`. Its only exclusion is a `case "$name" in *.skip*)` pattern. A maintenance script that requires `--dry-run` or `--apply` (like `backfill_cl_applied_layer.py`) will exit non-zero on the no-arg invocation and squat in the digest's "Needs attention" list every day until renamed. Documented after v0.6.390w, when the 08-02 backfill script sat in FAIL(2) for a full day.

**How to apply:** name backfills/migrations `<what>.skip.py` from the moment you create them. Related but distinct from [[feedback_shadow_write_applied_layer_trap]] (which is about live-code guards); this one is about tooling hygiene.
