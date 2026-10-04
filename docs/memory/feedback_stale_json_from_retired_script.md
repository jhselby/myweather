---
name: feedback-stale-json-from-retired-script
description: Retiring an analysis script to .skip.py without deleting or updating its output JSON leaves the digest reading a frozen verdict and re-flagging it every day. Check for downstream JSON readers before retiring.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b8058893-d7b5-4544-a4d3-9f9dee94eef7
  modified: 2026-08-10T14:21:34.804Z
---

# Rule

**Before retiring an analysis script to `.skip.py`, check whether its output JSON is read by another tool.** If so, either:
1. Keep the script running (it's a live sentry, not truly retirable), OR
2. Delete the stale JSON along with the retirement, OR
3. Update the reader to check the JSON's `generated_at` and suppress if stale.

Otherwise the downstream reader will emit the same frozen verdict daily and users will treat it as fresh signal.

## Why

08-10 traced the digest's "★ MLC in-bin bias: DECAY" alert to `marine_layer_anomaly.json` dated 2026-07-31 — 10 days stale. The script `marine_layer_anomaly.py` had been retired to `.py.skip` (older suffix convention). The digest's `marine_layer_anomaly_summary()` in `build_executive_summary.py` doesn't check file freshness; it just reads whatever's on disk. Result: same "★ DECAY" alert every morning digest for 10 days without a real underlying signal.

Fresh run showed verdict was actually STABLE.

## How to apply

- Before running `git mv analysis/foo.py analysis/foo.skip.py`, grep for the output JSON: `grep -r "foo.json\|foo.txt" analysis/ weather_collector/`.
- If a reader consumes the output, that script is functionally a live sentry — don't retire it, or delete its output alongside.
- Trigger phrases: "retire this script", "no reopen path", "dead-verdict for weeks". All fire this check.

## Sister principle

Any parent-memory that says "watch for future ★ = new signal" (e.g. [[project_mlc_diagnosis]]) requires the sentry to actually run. Retiring the sentry defeats the watch. Cross-check parent memory when picking retirement candidates.

Related: [[feedback_digest_triage_discipline]], [[feedback_analysis_skip_naming]], [[project_mlc_diagnosis]].
