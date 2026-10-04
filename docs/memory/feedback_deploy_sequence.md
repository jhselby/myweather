---
name: feedback-deploy-sequence
description: "Strict order for shipping a coupled collector+frontend change — deploy first, verify GCS, then push"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 43ac5ed4-a539-4e44-be37-7cbc5fe435f9
---

When a change touches both the collector and the frontend, the order is:

1. `make deploy-collector`
2. Wait for the **next scheduled tick** (every 10 min on :07s) to run successfully
3. Verify the new field/behavior in `weather_data.json` on GCS
4. Only THEN `git push` the frontend

**Why:** if the collector deploy fails or the new data path crashes, the frontend goes live first and renders against either stale or broken data. Joe sees a half-shipped feature on his iPhone before we know whether the backend works. Verifying GCS first is a one-tick latency hit; pushing prematurely is a real bug.

**How to apply:** after `make deploy-collector` returns, do NOT immediately commit/push. Wait for a tick (or `curl` weather_data.json and confirm the new field is populated), then push.

CLAUDE.md §8 already states this ("deploy collector first if both changed, then verify GCS data, then commit frontend") — this memory exists because I violated it on v0.6.70 (2026-06-11) by pushing right after the deploy without waiting for verification.

**Rule generalizes to collector-only ships too.** 2026-07-09 v0.6.317: I pushed a Fitter-preflight change to GitHub *before* deploy, treating "no frontend change" as "no verification gate." Joe reiterated the rule applies whenever collector code changes: deploy → wait for tick → verify no errors → THEN push. Reason: if the deploy crashes, the code on GitHub says one thing and prod is running the older version, which forces either a manual revert or the assumption that the next attempted deploy will succeed. Better to prove the new code runs before publishing "this is what's live."

**How to apply (updated 2026-07-09):** any time the change touches `weather_collector/`, the sequence is deploy → wait one tick (10 min on the :07s) → check logs clean → THEN `git push`. Frontend-only + analysis-only changes are exempt (no runtime deploy to verify against). If unsure whether a file counts as collector code, err toward "wait" — a 10-minute delay costs nothing; a stale-GitHub-vs-prod-mismatch costs debugging time later.

Related: [[feedback-build-workflow]], [[feedback-do-it-right]]
