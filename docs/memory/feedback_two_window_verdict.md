---
name: feedback-two-window-verdict
description: "For any gate that fits statistics on recent data, require it to clear on BOTH a fresh short window AND a robustness long window before acting. Short catches freshness (real regime shifts); long catches noise and premature ships."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9f584257-df4f-41a9-b227-c4bdf632ea0a
  modified: 2026-09-09T17:08:52.156Z
---

# Two-window verdict for time-window-sensitive gates

**Rule:** any gate that fits statistics on recent pair-log data and produces an action verdict should score on BOTH a short fresh window AND a long robustness window. The action fires only when both clear the same gate. A short-window-only clear becomes a WATCH verdict — visible in the digest but not proposed for action.

**Why:** short windows respond to recent regime shifts (good — a stalled bias correction should stop hurting the moment obs stop matching it). But short windows also amplify noise (bad — a coin-flip run of favorable rows looks like a real earn-back). Long windows dampen noise but lag on genuine shifts. Neither alone is enough. Requiring both to clear is the AND of "the signal is real recently" and "the signal has structural support in the longer window."

**How to apply:**
- Skip-table audits (ADD proposals or REMOVE proposals).
- Whitelist promotion gates (walker verdicts).
- Sentry HOT/WATCH classifications.
- Any decay-τ refit that samples the last N days.
- Any regime-conditional refit that fits and applies on rolling data.

**How NOT to apply:**
- Kill decisions that are already-known catastrophic (a HOT layer hurting +50% doesn't need a 50d cross-check to kill).
- Structural changes (adding a new axis to the confidence layer) — not a statistical gate.

**Documented incident:** [[project_09_09_session]] — v0.6.573 shipped 7 REMOVE candidates from the NBM skip-table audit on 14d evidence. 50d cross-check surfaced 2 that failed the longer window; both reverted in v0.6.574 same session. Two-window verdict formalized in `analysis/nbm_skip_earning_audit.py` — REMOVE now requires both 14d fresh + 50d long, WATCH is 14d-only signal.

**Pattern extension:** the WATCH verdict itself is worth carrying — it surfaces "something's moving on this cell recently that doesn't yet hold up on longer data." Repeated WATCH days on the same cell suggest a real shift; a single WATCH day is regime-transient. Some future walker (currently unbuilt) could gate on N consecutive WATCH → REMOVE promotion.

Related: [[feedback_streak_walker_robustness]] · [[feedback_measure_before_concluding]] · [[feedback_fossil_windows]] · [[feedback_pooled_n_time_thin]].
