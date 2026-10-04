---
name: read-uncommitted-diffs-before-shipping
description: "At session start, if git status shows uncommitted docs/debug/changelog/memos, Read the diff before shipping downstream work. Uncommitted files from prior sessions often contain caveats that would prevent premature ships."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9ae209fb-f72d-4e86-b7b4-23bca1282ee6
  modified: 2026-09-01T11:49:38.047Z
---

At session start, if `git status` shows uncommitted files in **docs, debug page, changelog, memory-adjacent notes** (`corrections_debug.html`, `docs/CHANGELOG.md`, `weather_collector/*.md`, etc.), **`git diff` them before shipping anything that depends on the same subject matter.** Uncommitted work from the previous session's evening often contains caveats or 7-day watch entries that would prevent a premature ship.

**Why:** 2026-09-01 session shipped v0.6.534 (L1 by-regime walker) on top of a diagnostic. Yesterday's uncommitted `corrections_debug.html` contained an explicit 09-07 calendar entry: "diagnostic 30d window is 96% pre-refit, masked signal likely the same pre-refit-baseline artifact class. Re-run 09-07; if signal survives extend runtime, otherwise close as no-residual." Missing that caveat caused a same-session supersede (v0.6.535) with a `NOT_BEFORE_DATE` guard bolted on after the fact. Earliest wire flip pushed 09-08 → 09-14. The diff was in front of me at session start (`git status` in the environment block showed `M corrections_debug.html`) and I skipped over it as "existing dirty state, ignore."

**How to apply:**
- At session start, scan `git status` output for uncommitted files. `.cache_*.json`, `weather_collector/data/*_curated.json`, `weather_collector/data/*_gate.json` — safe to ignore; those regenerate daily and always show dirty.
- **Not safe to ignore:** `corrections_debug.html`, `docs/CHANGELOG.md`, `README.md`, `CLAUDE.md`, anything in `.claude/`, session log files, memo files, planning docs. Read those diffs before treating them as noise.
- If shipping work whose subject matter overlaps an uncommitted diff, read the diff first even if the diff looks small. Yesterday-me may have known something today-me doesn't.

Related: [[feedback_verify_completeness_claims]], [[feedback_check_contamination_before_acting]], [[feedback_search_before_proposing]].
