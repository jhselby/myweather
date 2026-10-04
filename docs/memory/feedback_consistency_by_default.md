---
name: consistency-by-default
description: "Do the same thing the same way, always. When two variants exist for no reason, that's never good — even if the specific format doesn't matter, the inconsistency does. If format choice is arbitrary, pick one and use it everywhere."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d5b3b340-bcb5-4198-bf9b-651541917300
  modified: 2026-08-07T22:45:56.483Z
---

# Rule

Consistency isn't a nice-to-have. Whenever the same *kind* of thing is rendered, formatted, named, or computed in multiple places, use ONE shape. If the specific shape is arbitrary (timestamp format, delta sign convention, unit suffix, label wording), pick one and apply it uniformly — don't leave two variants in place because "either works."

**Why:** Joe called this out 2026-08-07 after v0.6.395h fixed only the 3 header timestamps but left other on-page timestamps in mixed formats (ISO-with-Z, ISO-without-Z, `en-US toLocaleString` short-month, hand-typed dates). Direct quote: "The lack of consistency is unacceptable. Sometimes I might not care how something is done, but if it's done differently for no reason that's never a good thing." Inconsistency signals sloppiness even when neither form is wrong; a reader has to re-learn each surface, and the page reads amateur.

**How to apply:**
- On any change that touches formatting, wording, unit rendering, or aggregation method: grep the codebase for other sites doing the same thing. If they differ, unify them in the same commit (or explicitly flag why you're not).
- When introducing a helper (`fmtET`, `pct(x)`, etc.), don't stop at the caller you needed it for — route existing callers through it too. A helper that only serves one call site is half a helper.
- If shipping a scoped fix, say so explicitly and leave a follow-up in memory / debug page — never let inconsistency accrete silently.
- When two formats DO have a reason to differ (ET clock time vs raw UTC log line, e.g.), the difference should be obvious to the reader and worth explaining in a comment.

Related: [[feedback_debug_page_full_sweep]] (half-assed sweeps are worse than none), [[feedback_metric_provenance_labels]] (unified source/window/method labels).
