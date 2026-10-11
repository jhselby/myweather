---
name: total-lift-baseline-moves
description: "Scoreboard Total Lift is vs NBM raw; a bad NBM week raises lift while our absolute MAE gets worse. Read absolute prod MAE + chooser_vs_prod before crediting mechanisms."
metadata:
  type: feedback
---

When Total Lift (scoreboard, `per_field_scoring.json`) jumps, check the baseline before crediting the selector, blender or stack. Total Lift = (NBM raw − prod) / NBM raw for NBM-scope fields, so a week where NBM degrades (10-04..10-10: NBM h break, 10-10 front) lifts the number even when our own MAE rises.

**Why:** 10-11 Joe asked whether the better scoreboard was the router + blender. Weekly replay: t/h/wd/sr lift rose 6–22 pts while prod MAE got worse on all four (h 3.6→6.2); baseline rose faster (h 4.1→9.3). Selector and blender did earn the extra lift, but only against a degraded baseline. See [[project_10_11_session]].

**How to apply:** report Total Lift together with absolute prod MAE, the baseline MAE, and `chooser_vs_prod_pct`. To get weekly history, replay `per_field_scoring._accumulate` on a truncated pair log (the scorer has no end-date arg; the published file is a single rolling snapshot). Complements [[ratio-over-absolute-for-fast-metrics]]: a ratio cancels weather only when the baseline's difficulty moves with ours.
