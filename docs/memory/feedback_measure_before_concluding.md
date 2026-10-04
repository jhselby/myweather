---
name: feedback-measure-before-concluding
description: "When the answer is \"we can't measure it,\" the first move is to try to measure it. Reaching for \"accept fire-and-forget\" or \"revert on principle\" before attempting the measurement is a shortcut past the actual work."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: af17d512-4939-4875-aa25-7dc730a23e19
  modified: 2026-07-19T22:43:59.117Z
---

When a question is "should we change X?" and the honest response is "we can't measure whether X is right," the correct first move is **try to measure it**. Reaching for "accept fire-and-forget" or "revert on the argument we can't measure it" before attempting the measurement skips the actual work.

**Why:** 2026-07-19 evening. I told Joe that `TAU_DAYS_BY_FIELD["pp"] = 28` had been unvalidated since 06-21 ship, and framed the options as (a) extend the tuner, (b) accept, (c) revert. I was leaning toward (c) — "safe but blind." Joe pushed back: "shouldn't we extend the tuner before concluding we can't measure it?" One-line change (add `pp` to `FIELDS` in `decay_tau_tuning.py`), one rerun, and we had a real signal — pp best-τ = 7 wins +13.7% vs τ=14 among decay options, but raw baseline beats every decay-τ option by 34%. That signal is more valuable than the choice between (a)/(b)/(c) I was ready to make blind.

**How to apply:**
- If the answer to "how do we validate X?" is "we don't have a tool for that," check whether the missing tool is one line or one function away before concluding we can't measure it.
- If the answer is "the tool exists but excludes this field/case," check the exclusion. Sometimes the exclusion was a hangover from an earlier design and the field belongs in scope now.
- Only conclude "we can't measure it" after a genuine attempt — and even then, "what would it take to measure it?" is a better question than accepting the gap.
- Related: [[feedback_check_contamination_before_acting]] (verify state before shipping), [[feedback_verify_writers_for_read_paths]] (grep for writers before trusting readers).
