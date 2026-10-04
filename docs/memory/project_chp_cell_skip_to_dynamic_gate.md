---
name: project_chp_cell_skip_to_dynamic_gate
description: "chp's _CELL_SKIP frozenset is hand-curated scar tissue (grew 0→9→10 in 2 days). Replace with a per-cell rolling regression detector on the same design as the Lc recent-bias gate — dynamic suppress + self-restore, no more hand-added skip tuples."
metadata: 
  node_type: memory
  type: project
  originSessionId: de85e7c6-dd3f-479b-af80-317414027d77
  modified: 2026-08-25T11:58:25.370Z
---

**STATUS 2026-08-25: CLOSED CLEAN — HOLD.** Walker at day 8/7 distinct dates; verdict HOLD — no cell has cleared the 7-day all-lose gate. Dynamic gate ran its full window without proposing any additional cells to auto-skip beyond the hand-typed `_CELL_SKIP` (10 cells since 08-14 v0.6.409). Hand-typed set continues to carry the work. Removed from `corrections_debug.html::OPEN_WATCHES`. Reopen only if a new regression cluster appears and hand-adding tuples becomes churn again.

# Opened 2026-08-15 v0.6.413

**Problem.** `weather_collector/processors/ch_persistence_gate.py::_CELL_SKIP` is a hand-typed frozenset of `(regime, lead_band)` tuples force-demoted from chp to L4. It has grown:
- 2026-08-13 v0.6.405: 0 → **9** (calm/{12-23,24-47}, nw_flow/12-23, pre_frontal/12-23, se_flow/24-47, sea_breeze/{12-23,24-47}, sw_flow/{12-23,24-47})
- 2026-08-14 v0.6.409: 9 → **10** (pre_frontal/24-47)
- No entry has ever been removed. There is no mechanism to remove one.

At ~25% of chp's applicability universe, this is significant coverage loss and it accumulates monotonically. Every "emergency demote" is Joe/Claude reading `h_ch_persistence_blend_stage2_vs_l6` output and hand-typing a tuple. Zero self-healing.

**Why:** Joe flagged the pattern on 08-15 — "if we keep adding into the skip table to help avoid errors, we're also reducing the potential value of the whole model." Correct — every static skip is scar tissue that never heals when the underlying cell recovers.

**How to apply:** Mirror the [[project_lc_regime_conditional]] gate design on chp:
- Analysis: extend `h_ch_persistence_blend_stage2_vs_l6.py` (or a sibling) to emit `weather_collector/data/chp_cell_gate.json` daily with per-cell `gate_apply` decisions — recent-window chp-vs-L6 Δ ≤ +Xpp (threshold TBD, mirror gate_ratio=0.5 conceptually).
- Runtime: `ch_persistence_gate.py` reads the JSON at import, wraps `_CELL_SKIP` in a helper that checks the dynamic gate. When dynamic gate says "suppress", the cell demotes; when "apply", chp fires normally.
- Ship-ahead pattern (same as v0.6.407/v0.6.410 for Lc): runtime consumer ships first with `ENABLED=False`, gate table starts building, flip after per-cell 7-day streak on at least one cell.
- Migration: `_CELL_SKIP` frozenset stays as belt-and-suspenders until the gate has cleared a full window, then retire in favor of dynamic-only.

**Do NOT** add another tuple to `_CELL_SKIP` while this workstream is open — it validates the exact pattern we're trying to retire. Only exception: a fresh outright regression >+50% Prod-vs-L6 that can't wait for the gate to be built.

## 2026-08-16 v0.6.421 — Stage 0/1 script + Stage 3 wire (OFF)

- **New `analysis/h_chp_cell_gate.py`** — reads `ch_persistence_gate_curated_vs_l6.json` daily, per-cell decision "chp lost to L6 today?" (delta_full_pct > +3%), appends to `.cache_chp_cell_gate_history.json`, per-cell 7-day gate rule (conservative: gate_apply=False only if ALL 7 days are 'lose'). Emits `weather_collector/data/chp_cell_gate.json`.
- **Day 1/7 seeded 2026-08-16.** Today's read: 13 cells register 'lose', 8 already in `_CELL_SKIP` (agreement with hand-typing), 2 static-skip cells actually WINNING today (se_flow/24-47 −5.4%, sea_breeze/24-47 −1.2% — the "parity precautionary" 08-13 adds now look over-cautious). 4 LIVE cells currently losing: se_flow/6-11 (+28.7%), se_flow/12-23 (+10.2%), sea_breeze/6-11 (+6.3%), ne_flow/24-47 (+4.2%). Nothing cleared yet (correct on day 1).
- **Stage 3 wire shipped OFF** — `ch_persistence_gate.py` gains `CHP_CELL_GATE_ENABLED = False` toggle + `_load_chp_gate()` + `_chp_gate_suppresses()` + gate check inside `_cell_fires()` after `_CELL_SKIP`. Same OFF-first pattern as Lc v0.6.410 → v0.6.413. Flip once per-cell 7-day clearance accumulates.
- **Retirement path**: once dynamic gate consistently catches every `_CELL_SKIP` cell (JSON `static_cell_skip_overlap.both` >= current `_CELL_SKIP` set), retire `_CELL_SKIP` frozenset.

**Sibling context:**
- [[project_lc_regime_conditional]] — successful precedent (recent-bias gate SHIPPED 08-15 v0.6.413)
- [[project_ch_chp_regression_watch_08_13]] — the watch that keeps triggering the hand-adds
- [[feedback_dont_over_gate]] — the general principle
