---
name: feedback-machine-only-fixes-invalid
description: "A fix that only works on Joe's machine is not a valid fix unless explicitly framed as temporary. Solutions must be durable across any machine running the digest."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 59e82d06-cdfb-4ebe-9ff9-4ea3ac9e7b83
  modified: 2026-08-21T16:33:51.890Z
---

# Machine-only fixes are invalid unless temporary

When proposing a fix, if the only workable option requires state that lives on Joe's local machine (a file in `~/.cache/`, an env var in his personal cron, a symlink he set up manually), that is **not a valid solution.** Say so and design something durable.

**Why:** Joe recorded this 08-21 evening. Context: I proposed a "quick alternative" of setting `MYWEATHER_PAIR_LOG=~/.cache/.../backstamped.jsonl` in his daily digest cron to feed backstamped data into `l1_selector_fit`. He rejected: *"A solution that only works on my machine is not a valid solition to anything unless temporary."*

The correct fix in that case was to upload the backstamped file to GCS (`gs://myweather-data/forecast_error_log_backstamped.jsonl`) and add a `pair_log_paths()` helper in `analysis/_cache.py` that returns both live + backstamp paths — so any machine running the digest sees the same state.

**How to apply:**
- Before proposing a fix, ask: "does this work on any machine that clones the repo and runs the digest?"
- If the answer is no, the fix belongs on GCS, in the repo, or in a shared config — not in a local cache or a personal cron.
- Local-only is acceptable **only** when framed explicitly as temporary (bridge until the durable fix ships, or one-time bootstrap that the digest can regenerate on demand).
- Never present a machine-only path as one of two equally valid options — it isn't.

Related: [[nbm-structural-completion-plan]] (context of the incident), [[feedback-analysis-cache]] (durable data-cache pattern).
