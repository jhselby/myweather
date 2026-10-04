---
name: project-c1e-hsf-kill-investigation
description: "07-22 h_hsf_orthogonality flipped PROMOTE→KILL. Diagnosed as window-mixture artifact, NOT real. C1e stays wired; script needs matched-regime baseline fix."
metadata: 
  node_type: memory
  type: project
  originSessionId: d3790481-8229-42a6-9301-f39add0e302a
  modified: 2026-09-08T16:01:29.896Z
---

# h_hsf orthogonality KILL — window artifact, not real

**07-22 digest** flipped h_hsf_orthogonality from PROMOTE (07-01, shipped as C1e in confidence_layer.py 5-tuple axis_key) → KILL (33 REDUNDANT / 2 ORTHOGONAL / 1 AMBIGUOUS). Verdict text: "just C1a re-skinned."

**Root cause of the flip: window-mixture artifact, NOT contamination from Lc, NOT a real reversal.**

Evidence (from `analysis/output/runlog/h_hsf_orthogonality.log`):

1. Only **8 frontal passages** in the 30-day window (2026-07-07 → 2026-07-21). "post" bucket ≈ 8 events × 24h × leads = ~1.5K–7K pairs per (field, band). Small event population, clustered in one 2-week span.
2. Pair-log join rate **622,639 / 2,429,782 = 26%**. Everything before 07-07 has no known-passage history, so ~74% of pairs can't be classified.
3. Most `post/baseline` ratios are **< 1.0** — post-frontal error is LOWER than baseline. This is inverted from the 07-01 evidence (h_hours_since_front showed ch +253%, cc +94%, cm +60% inflation).
4. Interpretation: sea-breeze-dominated summer "baseline" is unusually noisy (cloud/wind field errors elevated); the 8 cold-front-cleared airmasses in "post" are cleaner than typical. So baseline > post in this window, which the script logic reads as REDUNDANT.

**Failure shape: same as [[project_pp_brier_reliability]] retraction** — 30-day window mixing states makes signal invert. See [[feedback_measure_against_live_stack_baseline]].

## Action

- **Do NOT unwire C1e.** Curated_v2 by_axes table has 47 cells fit on 5-tuple `spread_q::pt_label::trans::c1f::hsf_group`. Unwiring requires full refit + re-curate, and there's no valid signal to justify it.
- **Script method fix (backlog):** `analysis/h_hsf_orthogonality.py` should compare post-frontal error to a **matched-regime baseline** (baseline pairs in same synoptic regime as post pairs), not global baseline. Otherwise KILL verdict is unstable across seasonal regime shifts.
- **Revisit trigger:** re-audit when frontal passage count in window ≥ 15, OR after next major season change. If KILL persists in a matched-baseline redo, then unwind.
- **Rule 5 sweep:** debug page section on C1e / hsf needs a "07-22 KILL claim under investigation — window artifact, C1e stays live" flag so the KILL doesn't fossilize as a real reversal.

## Why: measured over live-stack baseline caveat

Pair log's `error` field carries L1 semantics ([[feedback_measure_against_live_stack_baseline]]). So the KILL is NOT Lc absorption — Lc doesn't move pair-log error values. The Lc-absorption hypothesis was ruled out by tracing the script's data source.

## How to apply

- When h_hsf reappears in a digest with a flipped verdict, check passage count first. `< 15 passages` = thin population; interpret with caution.
- Same pattern (regime-mixing in the baseline denominator) will bite any orthogonality script that uses global baseline in a regime-imbalanced window. Matched-regime fix pattern lives in `h_hsf_orthogonality.py` as of v0.6.372a — port to `h_pre_front_orthogonality.py` next.

## 07-22 UPDATE — matched-regime fix implemented (v0.6.372a), KILL survives

**Ran the matched-regime baseline fix on the same 8-passage window today. Result: 32 REDUND / 1 ORTHO / 3 AMBIG (was 33/2/1). The KILL survives the fix — Simpson's-paradox was not the load-bearing artifact.**

Cell-level moves that matter:
- **cl 24-47h**: 1.77× → **2.18× ORTHO** (strengthened, 7 regimes contributing). Genuine independent signal from C1a.
- **cl 12-23h**: 1.42× ORTHO → 1.37× AMBIG (just below the 1.30 threshold).
- **cl 6-11h**: 0.90× REDUND → **1.70× AMBIG** — the one cell where global-baseline mixing WAS masking real signal. Post-fix reveals it as a possible signal, not a redundancy.
- All other 33 cells: essentially unchanged; REDUND in both views.

**Revised read:** the morning "it's a window artifact" call was largely wrong. The KILL is more credible than yesterday's memory implied. `cl 24-47h` alone would justify a narrow C1e-restricted-to-cl-long-lead axis. Thin-n (8 passages) still argues against acting immediately.

**Revised re-audit trigger:** when passage count in window ≥ 15 AND matched-regime KILL still fires, unwire C1e except for cl 24-47h (and possibly cl 12-23h + cl 6-11h if their AMBIG resolves ORTHO with more n). Do NOT unwire preemptively.

## 09-08 re-fire — still THIN, still gated on passage count

Today's digest re-fired `h_hsf_orthogonality → KILL: hours-since-front is just C1a re-skinned` with `n=2 passages, 30% join → THIN`. Passage count actually **regressed** vs 07-22's n=8 — small window rotation. Verdict remains gated on the ≥15 passage trigger above; DO NOT unwire. hsf remains genuinely wired at `weather_collector/processors/confidence_layer.py:464` as C1e axis (5-tuple `spread_q::pt::trans::c1f::hsf_group` keys); retirement would be confidence-layer refactor + curator changes + walkforward gate. Session 09-08 triaged this and deferred as "real refactor, not housekeeping" — matches this memo's do-not-unwire-preemptively rule.

