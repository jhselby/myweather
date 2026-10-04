---
name: project-walkforward-l3l4-validator
description: Walk-forward held-out MAE validator for L3/L4 on/off decisions per field. Built 2026-06-08 in advance of R0 audit maturity (~2026-06-15) and R2 confirmation (~2026-06-22).
metadata: 
  node_type: memory
  type: project
  originSessionId: 43ac5ed4-a539-4e44-be37-7cbc5fe435f9
---

## What it is

`analysis/walkforward_l3l4_validator.py` — produces per-field recommendations for which of 12 fields should have L3 (decay correction) and L4 (diurnal correction) enabled. Output goes to `analysis/output/walkforward_l3l4_summary.txt`.

## Design choices baked in

- **3 enable states, not 4.** Since v0.6.34, L4 is fit on L3 residual, so (L3=off, L4=on) isn't a real production path — the L4 coefficients would be invalid against an L2 baseline. States are (off,off) → use forecast_l2, (on,off) → forecast_l3, (on,on) → forecast_l4.
- **2% minimum-relative-win threshold.** Each enabled layer must beat the simpler state by ≥2% MAE to earn its keep. Prevents picking noise-level wins.
- **Does not refit L3/L4.** Reads currently-deployed `forecast_l3` and `forecast_l4` from the pair log. Measures how the live coefficients held up on held-out test rows.

## First-run result (2026-06-08, 879K test pairs)

```
L3_ENABLED = {'ws', 'wg', 'ch', 'cm'}
L4_ENABLED = {'ws', 'wg', 'ch'}
```

Confirms the v0.6.40 finding (L3 beats L2 on wind everywhere) and the layer 3/4 over-correcting watch (L3 net-negative for 8 of 12 fields, including solar +28% worse with L3 on). Humidity borderline (L3 wins by 1.7%, below threshold).

## When to act on this

**Why:** the validator runs on currently-live coefficients. R0 audit's 30-day rolling window doesn't fully reflect the post-v0.6.45 whitelist until ~2026-06-15, and these results will shift as the window absorbs cleaner data.

**How to apply:** re-run on 2026-06-15 and again on 2026-06-22. If the per-field recommendation is stable across both runs, drop the generated `L3_ENABLED` / `L4_ENABLED` config into `decay_apply.py`. If it flips between runs, the signal isn't ready and the cull decision waits.

## 2026-06-24 read (4th formal)

Triple-window run (2d/5d/10d) on cache fresh as of 06-24 09:33.
- 2d (11,075 test rows): L3={wg,ch}, L4={ch}
- 5d:                    L3={wg,ch}, L4={ch}
- 10d:                   L3={ws,wg,ch}, L4={ch}

**Cross-window stability (today):**
- L3 ch, L3 wg, L4 ch: ON at all 3 windows. Stable, keep.
- L3 ws: ON only at 10d (off at 2d/5d). Still flickers — same 2d-fragility story as 06-22, but 5d now agrees with 2d. Watch.
- L3 cm: OFF at all 3 windows. First all-windows-OFF read (06-22 was on at 5d). Weakened.
- L3 pp: OFF at all 3 windows. First formal read for pp.
- L4 cc: OFF at all 3 windows. First read since v0.6.221 added it (06-24).

**No drops shipped.** cm/pp/cc each have ONE consistent cross-window OFF read. Promotion/demotion gate requires multi-read confirmation. Re-run on **2026-06-29**; if cm/pp/cc still off at all windows, that's two reads and the drop conversation opens.

ws stays on the watch list — 2d/5d disagree with 10d, still 2d-window fragility hypothesis.

## 2026-06-22 read (3rd formal)

Default 2d run: L3={ch,cm}, L4={ch} — ws and wg dropped from L3 (L3 made ws +57% worse, wg +13% worse vs L2-only on 10,754 test rows). Disagrees with 06-08 and 06-18.

**Diagnostic sweep at wider windows revealed the 2d collapse was window-artifact:**
- 5d window (31,089 rows): L3={ws,wg,ch,cm}, L4={ch} — ws -19%, wg -33% (L3 wins)
- 10d window (64,542 rows): L3={ws,wg,ch}, L4={ch} — ws -26%, wg -35% (L3 wins decisively)

Today's 2d test window happened to land on a regime where L2 already had wind dialed in and L3's residual bias was net-noise. Real signal at 5d/10d agrees with prior reads — **L3 ws/wg should stay on.** No whitelist edit.

**Stable across all 3 reads + diagnostic windows:** ch L3+L4, cm L3 (10d flickers off; marginal). **Wind L4 dead** at all windows (ties L3-alone). 06-18 and 06-22 agree on L4 wind out → 2 consecutive reads, still below 7-window gate.

**Default test window discussion:** the 2d default is too sensitive to regime artifacts on small n. Consider raising default to 5d for next read (06-29) or running 2d+5d+10d as a triplet diagnostic by default.

Related: [[project-layer34-watch]], [[project-correction-stack]], [[project-todo]], [[project-l2-extension-assessment]].
