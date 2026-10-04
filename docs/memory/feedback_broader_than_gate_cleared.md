---
name: broader-than-gate-cleared
description: "\"Nothing to do today\" ≠ \"no gates cleared today.\" When triage says no ship, enumerate broader project-advancing categories before declaring the day noop: unbuilt infra queued behind future gates, known-unshipped signals, uncommitted work, investigations of anomalies not on any gate, refactor triggers, debug page discipline."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9ae209fb-f72d-4e86-b7b4-23bca1282ee6
  modified: 2026-09-01T11:50:04.275Z
---

Do not treat "no gates cleared today" as equivalent to "nothing to do today." Joe pushed back twice on 09-01 with "literally nothing else to push this project forward? Think outside of the box" — each time there was real high-value work. Narrow framing costs sessions.

**Why:** 2026-09-01 session — after the morning digest triage cleared zero gates and I said "hands-off Tuesday," Joe pushed. Broader look surfaced: (1) the L1 by-regime walker that had been queued for a week and could be built today, (2) the uncommitted `corrections_debug.html` needing commit, (3) `h_cc_combine_walker` HOLD needing a wired-vs-orphan check, (4) `walkforward_lc_regime_ship_stability` UNSTABLE watch, (5) pair-log pp -72% investigation. The walker got shipped (with a same-session correction — see [[feedback_read_uncommitted_diffs_before_shipping]]). Two rounds of user pushback to unlock what should have been the default framing.

**How to apply:** when digest triage says "no gates cleared," before saying "noop day," enumerate:

1. **Infra queued behind future gates.** Is there a walker, harness, router extension, or curator script that a gate clearance will demand, that no one has built yet? Build it now; when the gate clears the ship is one-line. (v0.6.529 walkers were built this way. v0.6.534 walker was built this way. h Stage 3 processor v0.6.530 was pre-staged this way.)
2. **Known-unshipped signals — walker outputs that never get consumed.** For each `*_walker.json` or `*_gate.json` in `weather_collector/data/`, grep the processors dir for a reader. Orphan walker outputs are common failure mode; the walker fires daily, gate clears, but no runtime consumes it because the router extension was deferred and forgotten.
3. **Uncommitted work.** `git status` sweep — anything in docs/debug/changelog/memory needs to be read + committed. See [[feedback_read_uncommitted_diffs_before_shipping]].
4. **Investigations of anomalies not on any gate.** Pair-log distribution shifts, layer-shape sentries, Brier-only fields (pp/pa) where the MAE view will never audit-fail but shape shifts can still signal breakage.
5. **Refactor triggers.** Third clone of a ~200+ line script fires the extraction trigger (v0.6.522/524/532 all followed this rule).
6. **Debug page discipline.** [[feedback_debug_page_full_sweep]] — every ship gets a matching entry; last-3-days narrative shift each day.
7. **Memory maintenance.** MEMORY.md compaction when >17KB.

Only after enumerating these categories can "genuinely nothing" hold. Even then, tell Joe what categories you checked, so he can push back on any specific one instead of the whole framing.

Related: [[feedback_answer_direct_first]] (still — surface the categories before the narrative), [[feedback_stop_after_minimum_ship]] (still — don't scope-creep once picked), [[feedback_do_it_right]], [[feedback_best_way_first]].
