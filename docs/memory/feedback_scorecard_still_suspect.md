---
name: scorecard-still-suspect
description: Joe left 2026-08-22 session unconvinced the 4-tile scorecard is measuring the right thing. Wild swings between adjacent publisher runs deepened the doubt. Do not assume the design is correct.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a5f6d3e2-3ab8-43f2-8697-4381ee8e9c0b
  modified: 2026-08-22T12:27:25.778Z
---

At end of 2026-08-22 session, Joe was NOT convinced the debug page's 4-tile scorecard (Chooser lift · Local lift · Total result · Prod trend) is measuring the right thing. Two specific concerns he raised and I did not fully resolve:

1. **Aggregate mismatch he couldn't reconcile.** Chooser +2.8% avg 7d + Local +9.6% avg 7d, but Total losing on 6 fields. I explained field-level correlation (chooser losing at t/h/ws/wd; total losing at the same 4 plus 2 marginal HRRR-only). He accepted the mechanics but not the framing — his summary: *"if the chooser is doing a good job and the local stack is doing a good job, it doesn't make sense that overall we're not doing a good job."*
2. **Wild swings between publisher runs.** Between the ~07:10 forced refresh and the 08:00 Scheduler tick, numbers moved dramatically. I attributed 24h to small-n variance + weather regime dominance. He was unsatisfied — *"those wild swings make me think we're doing it wrong."*

**Why:** Two open questions from a builder who is right to be skeptical when the metrics don't tell a coherent story.

**How to apply:** When picking this back up:
- Do NOT open by defending the design. Come at it fresh.
- Pull a raw pair-log sample and verify `chooser_vs_prod_pct` is computed correctly at the row level — is `_nbm_prod_error` walking the right key priority? Is the paired-row logic in `_accumulate` correct for the `chosen_prod`/`alt_prod` buckets?
- Test whether adjacent publisher runs really produce Weber-Fechner-level swings on the 24h line, or whether there's a stale-cache/mid-hour cutoff issue producing artifacts. Compare two runs 15 minutes apart; if they swing hard, something's mechanically wrong beyond weather noise.
- Consider whether the four-tile decomposition is genuinely orthogonal or whether Chooser and Local are entangled in a way that makes their sum not compose to Total. Prove it either way with concrete numbers.
- Consider whether an ABSOLUTE Prod MAE line chart (30d, per field) would be a more trustworthy scoreboard than four ratio tiles. Joe reasons in absolute MAE naturally.

The four-tile design ([[08-22-session]]) may be correct. It may not. Verify before defending.

Related: [[feedback_selector_prod_vs_prod]] (v0.6.440 rule that motivated the Prod-vs-Prod chooser lift rewrite), [[project_chooser_fit_diagnostics]] (why chooser is losing at t/h/ws/wd).
