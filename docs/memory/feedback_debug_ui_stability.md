---
name: feedback-debug-ui-stability
description: "Don't add pending/unstable diagnostics to the debug page's Research section. R3 is for committed state, not for in-flight hypotheses. Established 2026-06-08."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 43ac5ed4-a539-4e44-be37-7cbc5fe435f9
---

## Rule

The debug page's Research & Diagnostics section is for **live, stable** diagnostics that reflect what the corrections are *doing right now*. It is **not** the place to surface in-flight hypothesis tests, walk-forward validators, or dismissed hypotheses awaiting re-evaluation.

## Why

If a panel shows `L3_ENABLED = {ws, wg, ch, cm}` today, `{ws, wg, ch}` on 06-15, and something else on 06-22, Joe has to remember which version is the live one. That creates noise instead of signal. The discipline of v0.6.46–v0.6.50 was to *tighten* R3 — re-bloating it with pending or dismissed items immediately afterward undoes that work.

R3 should answer "what is the correction stack doing?", not "what might it do?".

## How to apply

- **One-shot hypothesis scripts** (`derived_humidity.py`, `walkforward_l3l4_validator.py`, `pop_calibration.py`, etc.): run manually, write to `analysis/output/`, don't wire into the page unless and until they become committed state.
- **A diagnostic earns a panel only after**: (a) the underlying decision has been made and committed to source, OR (b) two consecutive re-runs of the script agree on a stable result with an active live story.
- **Dismissed hypotheses do not get UI real estate.** They go in the Discarded section of memory or the TODO doc.
- **"Automation — we won't have to remember to re-run it" is not a sufficient justification** for putting an unstable result on the page. The cost of running one command on a specific date is smaller than the cost of UI integration plus the ongoing visual noise.

## Established by

- 2026-06-08 session: rejected wiring `derived_humidity.py` into R section live ("just re-run on 06-22").
- Same session: rejected wiring `walkforward_l3l4_validator.py` output into R section until config is committed to `decay_apply.py`.

Related: [[project-walkforward-l3l4-validator]], [[project-06-08-to-06-22-plan]].
