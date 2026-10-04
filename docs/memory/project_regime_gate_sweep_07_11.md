---
name: regime-gate-sweep-07-11
description: "2026-07-11: full sweep of open/frozen/killed findings through the [[feedback-regime-gate-first]] lens. Three Tier 1 candidates ready for Stage 2 preview (h → L4 regime-gated, cc L4 skip-table extension, sr shortwave-swap gated nw_flow). Four Tier 2 candidates for Stage 1 accumulation. Six explicit Tier 3 stays-killed (multi-tool-agreed or global orthogonality). Two candidates (h → L4 and sr shortwave-swap) had been sitting frozen for weeks under the old 'conflict = hold' frame."
metadata: 
  node_type: memory
  type: project
  originSessionId: 2bd018ca-98b4-4343-badc-7b405cae24be
---

## UPDATE 3 — three more clean skip-table candidates via fc_ws axis + wg regime cut

Joe pushed to keep going, verified with same halves method:

**ws L3 by fc_ws bin — 3 stable skip candidates:**
- (fc_ws 0-3 calm, 0-5h): recent −4.4% (n=655), prior −17.3% (n=1,859) ★
- (fc_ws 0-3 calm, 12-23h): recent −31.2% (n=755), prior **−77.5%** (n=1,371) ★
- (fc_ws 0-3 calm, 24-47h): recent −25.2% (n=2,937), prior **−66.0%** (n=3,950) ★

**Mechanism (verified):** L3 is a per-lead additive constant. In calm wind, a +0.5 mph systematic bias against a 1 mph baseline is a 50% relative error. Same absolute bias is trivial at moderate wind. L3's constant-additive structure is structurally wrong for near-calm.

**Current ws skip cells check — no removals.** ne_flow all bands + sea_breeze 0-11h all show "mixed" halves. Recent 15d consistently says "keep skipping"; prior 15d occasionally shows L3 helping in them. Conservative: keep them all skipped. Anti-overfit protection in the removal direction — don't remove a shipped defense unless both halves clearly say safe.

**Measured Production impact via production_whatif:**
- ws Production: +4.1% → +3.5% vs raw (Δ −0.7pp)
- wg Production: no measurable change (single cell too small)
- Overall Production: −8.9% → −9.0% (Δ −0.1pp)

**Honest note:** my back-of-envelope estimate was 3-5% pooled ws improvement; measured is 0.6%. Reason — the recent half's cell wins (25% cell-level MAE) are smaller than prior half (66%), and the effective L4/Production stack recovery is less dramatic than the L2-vs-L3 delta suggests.

**Tuesday ship candidate confirmed:**
1. Add `WS_FCWS_SKIP_CELLS` structure + `_ws_l3_skip_fcws()` gate in decay_apply.py.
2. Add `WG_SKIP_CELLS = [("sea_breeze", 6, 12)]` + `_wg_l3_skip()` gate.
3. Version bump v0.6.326 (or whatever next available).

## UPDATE 2 — one clean skip-table candidate survives from the "already-shipped LOSE cells" pass

After Joe caught that we hadn't looked at CURRENTLY-ON corrections for LOSE cells worth skipping (as opposed to only new gates to turn ON), swept L3 LOSE cells for wg and ws. Halves check killed all but one:

**Clean candidate: `wg L3` skip in `sea_breeze/6-11h`.**
- Recent 15d: L3 hurts wg by −12.6% (n=719). Prior 15d: L3 hurts by −2.0% (n=679). Both halves show LOSE, matching signs.
- Projected pooled wg improvement: ~0.2% (small). Config-only change to wg's L3 skip-table (currently empty).
- Recommend: standalone Tuesday config ship.

**Failed candidates (do not ship, per split-halves check):**
- wg L3 se_flow/6-11h — pooled Δ −11.7%, but both halves show L3 helping (+10.1%, +27.5%). Older-residue-dominated aggregate.
- wg L3 ne_flow/6-11h — A −7.6%, B +31.1%. High-variance oscillation.
- ws L3 sw_flow/0-5h — pooled −3.4%, both halves flat/positive. Older-residue.
- ws L3 nw_flow/12-23h — pooled −7.1%, both halves flat/positive. Older-residue.
- Several others in same category.

Not halves-checked yet:
- ws L3 by fc_ws bins (calm-wind losses at −12.7% and −38%). Different axis structure.
- CURRENT ws skip-table cells (ne_flow all + sea_breeze 0-11h) — check if any should be REMOVED because they're now WINNING under halves check.

## UPDATE 1 07-11 evening — split-halves stability check killed both L4 Tier 1s

Joe asked "aren't these decisions based on data we already have and can verify?" — sharp catch. Ran the split-halves stability test (recent 15d vs prior 15d, both within the well-stamped window). **Result: neither h → L4 add nor cc L4 skip clears the check.**

- **h → L4:** 7 of 12 WIN cells FLIPPED between halves. Recent half systematically worse than prior half (ne_flow/6-11h: A +2.9%, B +37.3%; calm/24-47h: A +1.9%, B +8.8%; etc.). The full-30d verdict looks clean because it AVERAGES the anomalous week with prior weeks.
- **cc L4 skip:** pre_frontal/0-5h shows A_Δ=−8.4% B_Δ=+0.3% (LOSE signal only in recent). ne_flow/0-5h shows A_Δ=+8.9% B_Δ=+0.2% — the cell I proposed to skip is actually the biggest cc-helper in the recent half.

**Same story as [[project-cm-stage4-degradation]]:** the 2026-07-04 → 2026-07-11 HRRR mid-cloud distribution anomaly is contaminating multiple regime analyses simultaneously. Full-30d averages look stable; halved windows reveal the contamination.

**Revised tiering:**
- **T1a (h → L4)** → **PENDING** — do not ship. Re-verify after 07-18 Stage 4 window rolls the anomalous week out.
- **T1b (cc L4 skip)** → **PENDING** — same reason.
- **T1c (sr shortwave nw_flow)** → **still viable** — the underlying Cause A/B analysis is mechanism-driven (matched-bin bias), not a per-cell WIN/LOSE label; less likely contaminated by HRRR mid-cloud drift. Run halves check separately with the shadow-log data.

**Codification win:** the split-halves check is now the standard pre-ship stability gate in [[feedback-regime-gate-first]]. Stronger than "wait 7 days" — exercises actual signal stability, verifiable from data on hand. Two frozen items ([[h → L4 promotion]] and sr shortwave-swap) now stay frozen for a different reason (HRRR anomaly contamination) but with a clean process for un-freezing (halves-agreement).

---

## Original Tier 1 write-up (pre-halves-check)

**T1a. `h` → L4_FIELDS with regime-gate + skip-table.**
- Data: `l4_regime_lead_analysis` 07-11 → h is **12 WIN / 20 flat / 0 L4 LOSES** across (regime × lead_band).
- Winning cells (n≥1000): ne_flow/0-5h +6.7% (n=1,198), ne_flow/6-11h +4.9% (n=1,273), se_flow/6-11h +5.2% (n=3,755), plus several more mid-lead cells (need to enumerate from full script output).
- Ship as: add "h" to L4_FIELDS + skip-table entries for every flat/thin cell (so it only fires in winners).
- Un-freezes the memory-noted "h → L4 promotion (frozen) — walkforward SHIP vs l4_regime_lead_analysis KILL disagree." Under regime-gate frame the disagreement IS the answer.
- Physical mechanism: humidity has regime-dependent diurnal variance; L4's per-hour correction lands cleanly in the winning regimes and adds noise elsewhere.
- Standard promotion gates: verify 7-day whitelist agreement, run production_whatif preview.

**T1b. `cc` L4 skip-table extension (cc already shipped in L4_FIELDS).**
- Data: `l4_regime_lead_analysis` 07-11 → cc **23 WIN / 7 flat / 2 L4 LOSES**.
- Losing cells to add to skip: ne_flow/0-5h −3.6% (n=1,197), pre_frontal/0-5h −4.4% (n=2,675). Also on fc_ws cut: 15-25 strong 12-23h −42.5% (n=1,097).
- Physical mechanism: strong-wind + short-lead = storm-adjacent; diurnal correction is the wrong shape there.
- Standard promotion gates as above.

**T1c. `sr` shortwave-swap gated ON in nw_flow only.**
- This has been sitting on hold **for a week** as "fix chain on hold pending Cause A/B" — that was the old-frame error.
- Memory: nw_flow with the shortwave-swap gives −55% MAE at first shadow-log read (n=82 on 07-07). Pre_frontal + sea_breeze go the other way (Cause A/B analysis for those).
- Under regime-gate frame: ship the swap gated ON in nw_flow now. Cause A/B resolution is only needed for the losing regimes' future refit — not blocking on the winning regime.
- Caveat: n=82 is thin. First-order action: verify the current shadow-log has now accumulated ≥1,000 nw_flow rows (07-11 vs 07-07); if yes → Stage 2 preview; if no → wait 1 week and re-verify. This is Tier 1 shape, potentially Tier 2 gate on n.
- Fastest to advance because shadow log is already accumulating.

## Tier 2 — Stage 1 restart / accumulate

**T2a. `dp` → L4_FIELDS, frontal-only gate.** 3 WIN cells all in `frontal` regime (0-5h +3.1% n=529, 6-11h +11.8% n=550, 12-23h +9.0% n=1,133). n hovers 500-1100 (borderline). Verify stability across last 2 walkforward windows; if agrees, promote to T1.

**T2b. `wind_shift_rate` → new C1 axis, gated ch/0-5h only.** Today: 1 ORTHOGONAL cell / 36 (ch/0-5h). Very narrow gate. Base signal in `h_wind_shift_rate`: rotating (≥80°) → ch MAE +33% penalty. Wait for 3-read stability before building the axis.

**T2c. `dp` nor_easter branch.** +3.79★ signed bias standing (n=279). Small n. Weekly n growth per existing plan.

**T2d. `ch` persistence regime-gate (Joe's insight from this session).** Design is Tier 1 shape (projected ~20% ch MAE improvement) but path is: build `h_ch_persistence_blend.py` first, preview via production_whatif, then Stage 2. One validation cycle away.

## Tier 3 — stays killed (do NOT re-open)

Explicitly per multi-tool-agreement rule or global-orthogonality-kill rule:

- **pp L3** — Brier + production_whatif + h_regime_l3 + walkforward all agreed 07-04.
- **CALM_GATE** — already replaced with correct ws L3 skip regimes {ne_flow all bands + sea_breeze 0-11h}.
- **ws τ=7** — global τ decision, no regime signal to gate on.
- **L6 warming branch** — 7-day retro backfill was net-negative across regimes.
- **L6 cooling branch** — was already regime-gated (sb_off + offshore) when killed on top of that.
- **C1g** — 69/72 REDUNDANT vs C1f + cc-saturation *in every regime*.
- **R3, R4, R5 (retired)** — historical.

## Meta-findings

- **Two Tier 1 candidates had been frozen for weeks** under the old frame. h → L4 promotion has been frozen since walkforward disagreed with l4_regime_lead_analysis. sr shortwave-swap has been on hold since 07-07. Both had the regime-gate answer sitting in the data; both go Tier 1 today.
- **Skip-table architecture is under-used relative to what the analyses have already identified.** cc's LOSE cells (ne_flow/0-5h + pre_frontal/0-5h) have been sitting in `l4_regime_lead_analysis` output the entire time cc has been in L4_FIELDS. Nobody promoted them to skip-table entries.
- **Rule for future stated in [[feedback-regime-gate-first]]:** whenever an analysis says "X wins in some regimes and loses in others," the default recommendation is a skip-table entry for the losers, not "hold pending universal validation."

## Immediate follow-on actions

1. **Run production_whatif with proposed Tier 1 gates** to preview Production impact. This is the ship gate.
2. **Verify last-2-walkforward-window stability** on each Tier 1 candidate (07-04 → 07-11 vs 07-05 → 07-11 rolling).
3. **Check current sr shortwave shadow log nw_flow n** — decide if it's Stage 2 ready or Tier 2 (accumulate).
4. **Un-freeze h → L4** in project_todo.md and hypothesis backlog memory.

## Cross-refs

Related: [[feedback-regime-gate-first]] (the rule this sweep applies), [[feedback-whitelist-promotion-gate]] (the promotion criteria), [[project-todo]] (needs updating), [[project-applicability-map-design]] (the shipped framework this leans on), [[project-persistence-skill-baseline]] (today's other big ship), [[project-ch-persistence-gap]] (Joe's insight that started this discussion).
