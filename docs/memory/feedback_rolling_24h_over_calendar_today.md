---
name: rolling-24h-over-calendar-today
description: "Any scoreboard metric that reads \"today\" of a diurnal-cycle-dependent process (temp / cloud / wind / anything the sun drives) should default to rolling last-24h, not calendar-day-so-far. Calendar today at 7am is 7h of overnight-only data (cool/calm/stable = easy for every field). Rolling 24h always contains one complete diurnal cycle. Symmetric with 7d (which is also rolling)."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 49547252-cd8d-4eff-b0cf-640d7facf514
  modified: 2026-08-02T13:01:30.961Z
---

**Rule:** For any forecast-accuracy metric that surfaces a "today" or "current" number in a dashboard, aggregate as **rolling last-24h** (obs_time >= now − 24h), not calendar-day-so-far. Rename the column/tile accordingly ("last 24h", not "today").

**Why:** 2026-08-02, the per-field snapshot's "today" column was reading calendar-day-of-obs from `mae_over_time.json`. At 7am it contained only 7 hours of overnight data — cool, calm, stable conditions across every field. Every field looked good; every field's number shifted through the day as the sample filled. Never a fair scoreboard read until end-of-day, at which point the day flipped to "yesterday" the next morning. Joe caught this: "shouldn't today be last 24h so there's always a complete diurnal cycle in there?" — yes.

**How to apply:**
1. **Emit rolling-24h aggregates in whatever produces the JSON** (for us: `analysis/mae_over_time.py` `compute_fresh_rollup` — cutoff = `now − 24h`, MIN_N floor = max(30, MIN_N_PER_DAY / 5)). Emit at both field-level (`last_24h[field][layer]`) and band-level (`last_24h_bands[field][band][layer]`) — the band-level is needed for any worst-cell-style tile.
2. **Render side-by-side with 7d, never in place of it.** Both cadences on the same tile — 7d catches sustained drift, 24h catches fresh single-day movements the 7d smooths over. Symmetry across all tiles: if 7d has it, 24h should too.
3. **When the 24h window has no field regressing (all winning), show a wins-state message like "✓ no field regressing" in green — not "—".** A dash reads as missing data; an explicit win statement reads as truth. Same for "no cell regressing" on band-level tiles.
4. **When the 24h data lags the 7d source** (e.g., our Fitter runs 03:07 + 15:07 UTC, but `mae_over_time.py` runs with the morning digest), the 7d card can be stale after a data-fix while 24h is fresh. Not a bug; explain it inline. Wait for next Fitter tick unless something's actively blocked on the 7d refresh.

**Related:**
- [[feedback_scorecard_banner_shape]] — banner tile inventory (now includes 7d + 24h stacked on each tile since v0.6.390r).
- [[feedback_per_field_snapshot_live]] — the per-field snapshot table also has "7d" + "last 24h" columns; same source (mae_over_time.json's `last_24h`).
- [[feedback_ratio_over_absolute]] — sentry canonical: ratio-vs-baseline metrics beat absolute MAE for catching regressions early. Rolling 24h is the natural short-window pair for a 7d baseline.
