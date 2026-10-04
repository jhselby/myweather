---
name: feedback-shipped-items-leave-backlog
description: "When a candidate hits Stage 3 (wired, ENABLED=False) or Stage 4 (shipped live), it leaves the R&D Backlog entirely. Its detail lives in the layer section (for shipped) or Post-ship watches / What's improving (for wired-gated). Backlog holds only Stage 0-2 pre-wire hypotheses. Prevents preamble examples from going stale."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 222946da-f295-4807-baf0-368c6663308b
  modified: 2026-07-27T13:01:14.777Z
---

When a candidate hits Stage 3 (wired, ENABLED=False) or Stage 4 (shipped ENABLED=True), it exits the R&D Backlog entirely. The detail lives in its layer section (for shipped: Lc layer, ch persistence gate, wd persistence gate) or in Post-ship watches / What's improving (for wired-gated: clp, wg residual persistence, dp residual persistence). Backlog should only hold Stage 0-2 pre-wire ideas.

**Why:** The 2026-07-27 R&D sweep found the G1 gated-candidates preamble still using Lc as its "example of a Stage 3 ENABLED=False candidate that stamps every tick" — but Lc flipped to ENABLED=True on 07-17. The example became confusing after ~2 weeks. Same pattern showed up in the Backlog framing paragraph: "Stage 1 candidates (curated text, not yet running)" was written when the section was purely text, but ~5 rows in the table below are now marked "🟢 Auto (daily digest)" — those are running scripts, not backlog. Mixing "backlog" (idea-stage) with "running" (Stage 1+) in the same section confuses the promotion pipeline. The example-going-stale problem is symmetric on the other end: once a candidate ships, keeping its detailed backlog entry means we're maintaining the same content in two places (the layer section AND the backlog), and the backlog copy always loses.

**How to apply:** At Stage 3 wire, move the Backlog entry to a one-line "shipped as [layer/gate]; see [section]" pointer OR delete it outright. At Stage 4 flip, delete the pointer too (the layer section is now canonical). Update any preamble example that references the just-flipped candidate — pick a currently-gated one (there are usually 2-3 in flight). Framing text ("Stage 0-2 pre-wire pipeline") should stay accurate to what's actually in the section, not what was there when the framing was originally written. Companion rule: [[feedback_rd_sweep_on_verdict_change]] — both fire at ship-time.
