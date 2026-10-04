---
name: git-log-before-metric-diagnosis
description: "Before diagnosing why a scoring/metric tile reads red (or looks wrong), run `git log --oneline -10` on the repo. Recent commits often name the exact issue in their message. Skipping this step causes hours of wrong-turn diagnostics on a problem the last commit already documented."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 39396d72-ba15-4563-b4ac-84d727899d4e
  modified: 2026-09-07T23:43:18.394Z
---

# Rule

**Before you diagnose why a metric tile is red, wrong, or "seems off," run `git log --oneline -10` (or read the top few commit messages from session-start context). Recent commits often literally name the problem in their subject line.**

Specific case this applies to: any tile on the debug page (Selector Skill, Pipeline Lift, Total Lift, Health), any per-field metric from `per_field_scoring.json` or `scoreboard_v2.json`, any sentry HOT, any "the number looks weird" observation.

## Why

**Real incident, 2026-09-07 session:** opened on "the selector is still terrible" and spent the first several turns wrong-diagnosing — invented a pick-then-correct architecture that doesn't match the codebase (both cascades run in parallel), read `sel_h`/`sel_n`/`total` columns as if they were the router's job (they're a decomposition against raws that the router doesn't compare against), fabricated a "L2_NBM damage on 6 of 9 fields" hypothesis that a follow-up audit showed was wrong on 4 of 5 fields. Joe caught each mistake and pushed back.

The correct first move was one command:
```
git log --oneline -10
```
The top commit was `9adf2b4 v0.6.554: fix per_field_scoring NBM fallback — Selector Skill card was mislabeling picks post-L3_NBM kills`. That one line said everything: Selector Skill was being misreported by a scorer bug, the fix existed in the repo, and the real question was whether the fix was reaching production. Total investigation time from that starting point: 5 minutes. Total time actually spent by taking the wrong path: several hours.

The commit message is the recent-diagnostic index. It's in every session-start context by default (top 5 commits). Not using it is choosing to re-derive from scratch what someone (often me, the day before) already documented.

## How to apply

1. **Session start on a scoring/metric question:** first tool call is `git log --oneline -10` (or scroll session-start context for the recent commits). Read every subject line. If any commit in the last few days mentions the metric or file the question concerns, read that commit message in full BEFORE opening the target file.

2. **Mid-session redirect on a scoring question:** same rule. If Joe pushes back with "no, look at X" and X is a metric-semantics claim, run `git log --oneline -10` on the file that computes X before formulating a response.

3. **Applies specifically to:** anything reading from `analysis/*.py` output, anything reading GCS-hosted JSON files, any tile on the debug page, any sentry verdict, any "was this number right yesterday" question.

4. **Does NOT apply to:** questions about live weather forecast content (that's data flow, not code state), collector uptime questions (check `gcloud functions logs`, not git), UI/frontend visual questions.

Related: [[feedback_refresh_current_state_before_defending]] (same failure mode, different domain) · [[feedback_check_own_arithmetic]] (metric-semantics-specific) · [[feedback_analysis_tools_drift_from_runtime]] (why the scorer bug happened in the first place).
