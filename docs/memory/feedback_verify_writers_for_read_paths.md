---
name: verify-writers-for-read-paths
description: "Before shipping any code that gates on `derived.X.Y` or similar shared-state reads, `grep` the codebase for a WRITER of that path. Multiple readers with no writer is a silent-failure pattern."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 09a24dea-6790-4fe1-9293-8d6805d4b598
---

Before shipping any conditional logic that reads from a shared-state path
like `weather_data["derived"]["state"]["regime_synoptic"]`, `grep` for
the WRITER of that path. If there's no writer, the reader always gets
None and downstream logic silently fail-safes.

**The general shape:** a "gate" or "state" is codified in prose or code
that reads it, but nothing actually WRITES the values the gate depends
on. Reader gets None / empty / default, fail-safe kicks in, the gate is
declared "passing" or "day N/7" or "waiting for next tick" by hand-count,
and no dated evidence exists to back the claim.

**Why (case 1 — the origin):** 2026-07-06 discovery — the L3/L4 skip
table shipped v0.6.279 on 2026-07-02 was silently non-functional for 4
days. Every read of `derived.state.regime_synoptic` returned None
because no writer existed (one processor worked around it with inline
classification, another didn't). `_should_skip()` fail-safed to False
on every row → ws L3 continued applying in ne_flow / sea_breeze cells
despite the skip table being populated. Users ate the +25.7% ws
Production regression for four days because "shipped" ≠ "firing."

**Why (case 2 — Lc gate history):** 2026-07-08 discovery — the Lc
7-day live-layer change gate was prose-codified on 07-04 ("day 1/? of
7-day gate; earliest ship 07-11"). The nightly digest DID run
`analysis/lc_fit.py` daily (picked up by the `for f in analysis/*.py`
loop), but no code persisted per-run verdicts anywhere — only the
latest verdict lived in `digest_state.json`. The "day 5/7 by hand
count" on 07-08 was fiction: zero dated evidence existed for it.
Cost was small this time (caught before the flip), but the pattern
was identical: a gate whose validity depends on dated data with no
writer producing that data. Fix: added append-only history writer +
7-day rolling summary printer to `lc_fit.py`, mirroring L5's
`.cache_l5_gate_history.json` pattern.

**How to apply:**
- When adding a new consumer of `derived.X`, `state.X`, or any similar
  cross-processor shared path, run `grep -rn '"X":\s*' src/` (or the
  language-appropriate equivalent) and confirm a writer exists.
- When shipping a conditional (skip table, threshold, gate), immediately
  verify the counter fires on the first post-deploy tick. If the counter
  stays at 0, treat that as a failure signal, not "no traffic yet."
- Consumer code with a `.get("X") or default` fallback is polite but
  hides the missing-writer bug. Log a warning at least once per tick
  when reading an expected-populated path returns None.
- When codifying a time-based gate ("day N/7", "≥7 consecutive daily
  reads agree"), before trusting a hand-counted "day 5/7" claim, ask:
  where is the dated evidence stored? If the only artifact is the
  latest run's verdict (no per-run history file, no timestamped log),
  the gate isn't machine-enforced — it's a story. Fix by building the
  writer, not by trusting the count.

Related: [[feedback_check_contamination_before_acting]] — same family
of "verify the assumption behind the alert, don't just act on it."
