---
name: verify-completeness-claims
description: "When claiming a page-wide or repo-wide cleanup, RUN the grep before saying done. Don't summarize what I did from memory — verify against what was asked. v0.6.375b claimed 'full-page cleanup' but missed the sibling Calendar block; Joe caught it in v0.6.377a."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ff24db72-19f0-4e42-bdde-769e1f1f38b6
  modified: 2026-07-23T18:28:15.690Z
---

# Verify completeness claims with a grep, not from memory

## The rule

Before shipping any commit that claims page-wide, repo-wide, or otherwise-comprehensive cleanup: **run the verification grep and paste the results into the commit message or the reply to Joe.** Never summarize what I did from memory and infer that it was complete.

**Why:** Machine verification catches what my summary misses. My working memory of "what I touched" is unreliable — I'll skip a sibling block, forget a section, or conflate "I edited X" with "X is now clean."

**How to apply:**

Before saying "done," "clean," "up to date," "everything," "full cleanup," etc., ask: *what grep would prove that claim?* Then run it. If the grep finds hits, either fix them or explicitly caveat the summary.

Examples of "should have run a grep" claims:
- "The whole debug page is now up to date" → `grep -nE "past-date-pattern" corrections_debug.html`
- "All layer sections refreshed" → `grep -nE "day [0-9]+/14" corrections_debug.html` before and after, count sites
- "Recent activity rolled to today" → `grep -nE "2026-07-(1[0-9]|20|21|22)" corrections_debug.html` should return only the trimmed line + historical DASHBOARD narrative
- "Watch counters advanced everywhere" → same grep pattern, count matches

## The incident (v0.6.375b → v0.6.377a)

v0.6.375b commit message claimed: *"Upcoming decisions section: full rewrite. Removed 8 answered items. Added 9 forward-looking items."* The end-of-turn summary claimed the whole `sec-status` was covered.

Actual state: the **Upcoming decisions** `<details>` block was rewritten. Its **sibling Calendar block** in the SAME `🔵 What's being evaluated next` section still had 10+ past-dated entries labeled as "next" (Sun 07-19, Mon 07-20, Tue 07-21, Wed 07-22, "Sun 07-19 (tonight)"). Joe caught it hours later — *"the section has entries whose dates are in the past."*

Root cause: I summarized "what I intended to fix" as "what got fixed," never verified with a grep. When Joe told me *"make sure the entire page is up to date to avoid confusion,"* I responded to the spirit but never ran the completeness check the instruction implied.

Same class as [[feedback_stated_intent_vs_code_behavior]] but the doc-vs-code disagreement is INTERNAL: my summary disagrees with the actual state, no external script involved.

## The fix

- **Before any "page is up to date" claim:** grep for the pattern that would falsify it. Include the grep result (0 hits, or the surviving lines) in the commit message.
- **After any user instruction that says "make sure X"**: pause and articulate what grep would prove X. Run it. Then act.
- **In end-of-turn summaries:** distinguish "I touched these files/sections" from "these are complete." Only claim the latter after verification.

## Related

- [[project_already_live_backstops]] — same failure family (act on claim without verifying against reality); different manifestation (memory vs code, verdict vs applied state, summary vs actual work).
- [[feedback_stated_intent_vs_code_behavior]] — the doc-vs-code variant of the same class.
