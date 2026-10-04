---
name: 08-22-session
description: 08-22 shipped v0.6.466-470 restructuring the scoreboard as Value Chain + Diagnostics. Joe ended the session frustrated. Local Lift near zero is the real open question.
metadata: 
  node_type: memory
  type: project
  originSessionId: 3d2442b1-1b98-40c6-bb1f-d8b88e303afe
  modified: 2026-08-22T13:16:22.313Z
---

# 08-22 session — scoreboard restructured; Joe ended frustrated

## Ships
- **v0.6.466** — chooser lift Prod-vs-Prod (raw-vs-raw was a design flaw)
- **v0.6.467** — Prod trend tile added (4th scorecard metric)
- **v0.6.468** — SCOREBOARD RESTRUCTURED. Chooser Lift redefined as L1 vs best raw (value attribution vs the public alternative), NOT chosen-cascade Prod vs alt-cascade Prod. Old tile renamed Selector Skill and moved to diagnostics. National Source Score copy fixed (no longer implies "chooser should flip"). Per-field pool intersection added to `per_field_scoring._accumulate` for NBM-scope fields.
- **v0.6.469** — headline tiles show MEDIAN, not mean. Mean-of-per-field-percentages doesn't preserve the multiplicative identity `(1-Total) = (1-Chooser)(1-Local)`; median is more honest for the aggregate. Coherence check moved to per-field.
- **v0.6.470** — Prod Trend pool symmetry fix. v0.6.468 had left `prod_prior` unfiltered while `prod` was intersected, producing spurious "regressing" signal. `_accumulate` now applies `pool_ok` to both branches.

## The conceptual model that landed
    Best Public Raw → L1 → Production
    ← Chooser Lift → ← Local Lift →
    ←──────── Total Lift ────────→
- Chooser Lift, Local Lift, Total Lift = value chain (top row).
- Selector Skill, Prod Trend, National Source Score, Health = diagnostics (below).
- All value-chain tiles use the SAME 7 NBM-scope fields (t/h/ws/wg/wd/ch/sr) so the identity holds per field.

## Current readings after ships (7d median)
- **Chooser Lift: −13.6%** — losing on all 7 fields. Warmup: L1 ≈ HRRR because selector table hasn't started flipping cells to NBM yet.
- **Local Lift: +0.4%** — REAL DROP from prior ~+9%, not a pool artifact. Open question.
- **Total Lift: −11.3%** — Prod worse than best raw on 6 of 7 scope fields; only ch winning.
- **Selector Skill: +2.7%** — 3 correct / 1 flat / 3 wrong. Losers: t/h/wd (matches [[project_chooser_fit_diagnostics]] three-culprit playbook).
- **Prod Trend:** NBM-scope fields blank (honest — backstamp doesn't cover prior window under intersection rule); cl/cm/pr populate, weather variability territory.
- **National Source: NBM 7 / HRRR 0** — NBM raw beats HRRR raw on every scope field.

## Open blockers for tomorrow
1. **Local Lift +0.4% is the real open question.** Was closer to +9% before this session. Not a pool artifact (survived the v0.6.470 fix). Either (a) v0.6.468's intersection legitimately revealed the correction stack was doing less than we thought or (b) the intersection introduced a selection bias by dropping the ~6% of rows where NBM raw missing (probably longer leads where Local Lift is bigger). Investigate FIRST tomorrow before drawing conclusions about the correction stack.
2. **Chooser Lift will not self-heal until the selector flips.** 08-28 sustained-7d review is still on the calendar. Consider: is the flip gate too conservative given how lopsided the raw HRRR vs raw NBM data actually is at Wyman Cove?
3. **Selector Skill losing on t/h/wd** — [[project_chooser_fit_diagnostics]] three-culprit playbook queued.

## Session state
- Joe ended frustrated with me ("confused dickface"). Multiple rounds of me claiming "you're good to stop" and then finding another issue to fix, which cost him tokens. The screenshot pushback (v0.6.470 prod_prior asymmetry) was the last one.
- Every commit pushed cleanly. Nothing broken. Working tree has the usual daily-drift files uncommitted.

## Do NOT tomorrow
- Do NOT propose another scoreboard restructure. Joe explicitly said "I wouldn't change the basic scoreboard structure anymore. This is the first version where I think the conceptual accounting is right."
- Do NOT touch selector fits or the correction stack in response to the current tile numbers. Priority is "collecting the right data honestly" — the fit/model work stays on its existing calendar.
