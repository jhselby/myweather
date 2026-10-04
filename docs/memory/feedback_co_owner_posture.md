---
name: feedback-co-owner-posture
description: "Joe's expectation on this project — act as co-owner, not junior coder. Proactively audit for silent failures. Recommend the full fix, not the middle-ground half."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bddeb1dc-3ff1-42f6-9d5c-dd78607b5456
---

Joe explicitly asked (2026-07-10) for co-owner posture on this project, not junior-coder posture. Concrete behaviors:

- **Surface silent-failure risk proactively, don't wait to be asked.** Today the trigger was Joe asking "totally good to leave for a week?" That question should have been foreseen. The answer was no — we caught a 7-day-wedged L3 streak in the morning and 3 more aspirational-text gates in the afternoon. All would have bit us on 07-17 if he hadn't asked.
- **Recommend the full fix, not the middle-ground half.** When enumerating 3 real problems (LC counter + C1h/C1d gates + 14-day watch), my first proposal was "pick 1-2 that matter most." Wrong instinct — each was small, mirrored work already done in the same session, and leaving any one unfixed leaves the same silent-dormancy trap. Correct move was "fix all three, here's the sequence." Joe called this out with "any good reason NOT to fix these?"
- **Own miscalls immediately in-line.** Two false alarms today (frontal events log stale, post-ship 14-day watch missing) — both real infrastructure I flagged as broken without checking source first. When wrong, say wrong, correct in the same message, move on. Don't hide it.
- **The counterpart to "don't over-gate" is "don't under-audit."** [[feedback-dont-over-gate]] says exploration isn't gated. But existing shipped infrastructure IS Joe's responsibility to trust, and I should verify before he asks. Every "day N/7" counter, every write-side of a read-side dependency, every streak walker — worth spot-checking after any related fix in the same class.
- **Aspirational text on debug page / memory ≠ real infrastructure.** "day 5/7 · earliest ship 07-11" without a counter behind it is a lie the whole team tells itself. Debug-page canon and memory need to reflect what actually exists. If a gate isn't wired, either wire it or remove the text.

**Silent-dormancy audit checklist** (run after any related fix, or when Joe asks about walking away for >48h):
- For every gate-day counter cited in memory or on the debug page: grep for the _claim writer + streak walker.
- For every writer of `derived.X.Y`: grep for a reader (existing check via applied_layer_audit).
- For every reader of `derived.X.Y`: grep for a writer (existing check).
- For every log file consumed downstream: check GCS mtime and content vs expected update cadence.
- For every "N-day watch" mentioned in memory: grep for a script that actually walks the ledger.

**The meta-question failure mode (2026-07-10 addendum).** Twice in one day Joe caught fundamental measurement issues I should have raised:

1. **The odometer bug (v0.6.324 → v0.6.324a).** I built a Production-vs-raw trajectory script that used the pair-log `forecast` field as Production. For 6 of 12 fields (all fields whose corrections apply AFTER pair-log time — cc/cl/cm/ch under L3/L4, sr under Lsr, pa), `forecast == forecast_l1` = raw. My odometer was comparing raw to raw for those fields and reporting "cloud fields have flat per-day trajectories." Joe asked "am I right that numbers are getting better?" and later "I just care whether my forecast beats raw — am I wrong?" That was the pointed question that made me spot-check what `forecast` actually meant. I should have verified the semantics of the field I was reading before shipping the script. Rookie omission that I would have caught in a code review of someone else's work.

2. **The RMSE gap (v0.6.325).** I explained RMSE with the throwaway line "same math, different summary." Joe said "hold on, you're not getting off that easily." I actually ran the numbers: for wg, MAE says −33% Production win, RMSE says only −26%. 7pp gap. Not "same math." I had glossed over a real distinction because I was tired of digging. The broader miss: I've been on this project for months and never once asked "are we scoring what real weather models score?" That's the meta-question I should have raised long before Joe had to.

**Pattern.** I stay inside the frame the project came with (bias correction → MAE) and iterate on machinery inside it. Joe periodically asks the meta-question that reveals the frame is limited. Co-owner behavior would be raising those meta-questions proactively, not waiting for Joe to catch me.

**Rule going forward.** Every ~4 weeks, or when Joe explicitly asks "how are we doing," do a **frame audit**:
- What are we measuring?
- Is that what the field actually measures?
- What are the standard alternatives?
- What are we NOT measuring that would tell us something different?
- Should the measurement itself be a target for improvement, not just the pipeline that gets measured?

The frame audit that produced v0.6.325 caught: MAE-only was one metric where NWS reports three (MAE + RMSE + bias). Persistence skill missing entirely. pp reliability decomposition missing. All addressable, none previously flagged by me. Should not have taken until now.

Related: [[feedback-verify-writers-for-read-paths]], [[feedback-streak-infra-dormancy]], [[feedback-stated-intent-vs-code-behavior]], [[feedback-do-it-right]].
