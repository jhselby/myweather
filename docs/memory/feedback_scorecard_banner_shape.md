---
name: scorecard-banner-only-shows-biggest
description: "The debug-page scorecard banner (top of corrections_debug.html) is a 5-tile SUMMARY: Overall/Winning/BestGain/BiggestRegression/WorstCell. It does NOT render per-field tiles for every field. Field values quoted from prose narratives don't render anywhere unless they're the winning/losing outlier."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6c13f0ec-2762-47f1-aab5-a15c48f08029
  modified: 2026-08-02T13:01:07.734Z
---

The `#scorecard-banner` element at the top of corrections_debug.html renders exactly 5 tiles: (1) Overall vs raw — mean MAE + RMSE + median; (2) Winning fields — count + ✓/✗/○ labels; (3) Biggest gain (single best field); (4) Biggest field regression (single worst field); (5) Worst cell (field@band). Each tile shows both a **7d** primary line AND a **last 24h** secondary line (v0.6.390r) — 7d catches sustained drift, 24h catches fresh single-day movements the 7d smooths over. Per-field breakdown is NOT rendered here. That's what the per-field pipeline table below is for. Renderer: `renderScorecardBanner()` in the debug page's `<script>` block, ~line 2787; 24h sub-tiles filled by the same async fetch inside `renderPerFieldSnapshot()` that populates the per-field "last 24h" column.

**Why:** 2026-07-30, when Joe asked where a `+15.9%` value I'd cited in prose was rendered on the page, I sent him hunting through the scorecard tiles. It never was rendered — the value was in narrative text I wrote into a post-ship-watch entry, quoted from that day's live data. Even if it had been today's ws value, the banner wouldn't show ws unless ws was the *worst* regression that day. cl at +31.5% held the "Biggest field regression" tile; ws at +15% was implied only in the `✗ ws h cl wd` line under Winning Fields. Joe correctly called this out — the search was a waste.

**How to apply:**
- When quoting per-field percentages in prose (recent activity, post-ship watches, calendar entries), don't tell Joe or myself to "look at the scorecard tile" for that value — the banner will show cl or whoever is worst, not the arbitrary field cited.
- To see a per-field value on the live page, direct Joe to (a) the per-field pipeline table (the "Right now — what the pipeline is doing" section), or (b) the mae_over_time detail chart with the field selector set to that field.
- When writing debug page narrative that cites a specific field percentage, mark it as "as of DATE" so it's clear the number is a point-in-time snapshot, not something live-rendered elsewhere.
- Renderer confirmation: search corrections_debug.html for `id="scorecard-banner"` (element definition) and `renderScorecardBanner` (populate function). Nothing between those wires per-field tiles.

**Related:**
- [[feedback_debug_page_canon]] — the debug page IS truth; when it drifts from reality, sweep it. But the truth is what the page renders, not what its prose sentences quote.
