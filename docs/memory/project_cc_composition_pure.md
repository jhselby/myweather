---
name: cc-composition-pure
description: "h_cc_composition_pure.py (2026-07-31 v0.6.390h+) measures Ccd formula error using OBSERVED cl/cm/ch (strips cascade). Finding: max wins 9/10 regimes with pure MAE 1.6 pts, bias -1.6 (systematic under-report vs METAR total sky cover). 2 orders of magnitude smaller than cascade error, so cc stays out of scoreboard mean today. Threshold for re-inclusion: composition MAE ≥3 pts (would justify separate scoreboard line, not cc-in-mean)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 434af779-9797-4cea-bd88-1e0939ffeef0
  modified: 2026-07-31T15:42:31.217Z
---

# cc pure composition analysis

## Purpose

Isolates cc's error source #2 (formula choice) from source #1 (cascade damage from cl/cm/ch corrections). Answers: given perfect component values, does our composition formula reproduce METAR total sky cover?

Applies each candidate formula (max, random, max_random) to OBSERVED cl/cm/ch (not corrected), compares to observed cc. Result is independent of cl/cm/ch correction quality.

## Findings (first run, 2026-07-31, n=123,317 obs quads)

**Overall pure composition MAE:**
- **max: 1.615 (bias −1.615)** ← current LIVE formula
- random: 4.452 (bias +3.636)
- max_random: 3.952 (bias +2.262)

max under-reports total sky cover vs METAR by ~1.6 pts on average. Physically sensible — METAR observers count ANY cloud in ANY layer, not just max coverage per octet.

**Per regime (n≥100):** max wins in 9/10 regimes. Only nor_easter (n=241, small) has random winning by tiny margin (0.882 vs 1.295).

## Why this matters for scoreboard framing

cc's error against observed has TWO sources:
- **Cascade** — cl/cm/ch correction damage propagates through Ccd. Redundant with component scoring (double-counting if cc goes in mean).
- **Composition** — formula choice vs METAR methodology. INDEPENDENT of cl/cm/ch quality.

My initial "keep cc out of mean" argument only covered cascade. Composition IS a real independent quantity. Joe pushed back — correctly. This script measures the composition part.

**But magnitude decides the action.** cc's daily damage vs raw is 20-155% during a cl bleed (all cascade). Pure composition error is 1.6 pts (~5% of obs magnitude, 33). Adding cc to the scoreboard mean today would drown a 1.6-pt signal in cascade noise. Not worth its own line.

**Threshold for revisiting:** composition MAE ≥3 pts in any regime OR overall. At that point, add a **separate scoreboard line "cc composition"** — do NOT reintroduce cc-in-mean (would still double-count cascade).

## The −1.6 bias is a standing tuning opportunity

max() systematically under-reports vs METAR by ~1.6 pts consistently across regimes. Trivial fix (add 1.6 to every Ccd output) OR partial max/random blend would close it. Return would be ~5% improvement on a signal drowned by cascade — not worth chasing today. Documented so future-us doesn't rediscover.

## Standing daily check

`h_cc_composition_pure.py` will re-run daily in the digest. If a regime-conditional composition ever produces ≥3-pt improvement on pure composition MAE, that's the trigger to (a) update `cc_from_derivation.py` with regime→formula lookup and (b) add scoreboard line.

## Related

- [[project_cc_derived_field]] — architectural framing (derived-with-tunable-composition)
- [[project_cc_blend_tuner]] — Stage 0 tuner using CORRECTED components (measures full error, not pure composition)
- [[project_07_31_session]] — session where Joe pushed the framing question
