---
name: check-contamination-before-acting
description: "Before recommending action on any post-ship watch alert (⚠ in digest), check the debug page for a known-contamination note. Never propose skip-list changes, kills, or ships based on a verdict Joe has already ruled contaminated."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 41c1038a-66f9-4fc2-8e7c-d972bc30587d
---

Before recommending ANY action on a post-ship watch alert:
1. Read `corrections_debug.html` for a note on the alerted script (search "Ongoing through" / "self-resolves" / "contaminated" / "don't act on").
2. Check `analysis/runlog/shipped_ledger.jsonl` for a `suppress_until` field.
3. If either says "don't act until date X" — HOLD. The correct output is either silence or "we're waiting on X."

**Why:** On 2026-07-05 the morning digest fired the l5_solar_analysis watch alert. The debug page (line 1083) already said don't act on it until 2026-07-10 because the raw_direct_radiation pollution + per-lead scalar bugs (fixed 07-03) contaminated the 7-day window. I ignored the note and recommended adding frontal + pre_frontal to `L5_SKIP_REGIMES`. Joe caught it. Exactly the "moving goalposts on sr" pattern he's been calling out for weeks — post-ship gate said HOLD because of a bug, and I turned that HOLD into "kill more regimes" without checking whether the HOLD was trustworthy.

**How to apply:** For every ⚠ in the digest executive summary, do the check FIRST. Never lead with a proposed action. Lead with: "digest shows ⚠ X. Debug page says [contamination note / no note]. Suppress-until [date / none]." Only then propose action, and only if no suppression is active.

Related: [[feedback_do_it_right]] — structural fix (suppress_until in ledger + digest honors it) shipped 2026-07-05 so future contaminated alerts self-suppress without requiring me to remember the rule.
