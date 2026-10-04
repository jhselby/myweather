---
name: 07-11-session
description: "Landmark session. Phase 2 persistence-skill baseline shipped. Regime-gate-first + split-halves stability check codified as framework. state_fc/state_obs bug in production_whatif caught + fixed. cm Stage 4 blowup diagnosed as HRRR distribution shift, not pipeline bug. ch persistence gap → Joe's regime-gate design (L4 frontal / persistence elsewhere) halves-verified for −19.6% pooled ch MAE. Full regime-gate sweep tool built. Debug page prose condensation pass. Lc anomaly-week HOLD. Shipped v0.6.326 end of session."
metadata: 
  node_type: memory
  type: project
  originSessionId: 2bd018ca-98b4-4343-badc-7b405cae24be
---

## Ship of the day

**v0.6.326** — persistence-skill baseline + regime-gate framework + halves-check pre-ship gate + debug page condensation.

## Arc of the session

Started with morning digest read on Saturday. C1 Stage 4 was supposed to be the day's ship (legacy axis with 2 SKIPs → 96.4% READY per yesterday's plan). Digest showed refined view flipped **27/1/2 → 26/0/9** overnight after single-day window roll.

**8 of 9 refined FAILs are cm × every band × difficulty key.** Post-mixture-check → real drift not weather-mixture. Diagnosed by joining pair log to Stage 4 windows: HRRR started forecasting mid-cloud dramatically higher this past week — mean cm forecast 16% → 47%, b3 (75-100%) fc bin +193% population, signed bias +1.4% → +21.3%. Diffuse across every regime + every lead band → structural HRRR-side shift, not our pipeline. Legacy ship BLOCKED; re-audit 07-18 window roll.

Turned to Phase 2 persistence-skill (Joe's "have to measure right before improving" priority from 07-10). Built `h_persistence_skill.py`. **First-ever persistence-skill audit for the project.** obs_temp_log 24h retention is useless for multi-day audit; built {(field, valid_time) → obs} index from pair log itself. Result: 6 fields ADD VALUE (t/dp/h/pr/ws/sr), 3 MIXED (wg/cc/pp), 3 NO SKILL (cl/cm/ch).

**Landmark**: ch loses to persistence at every lead band despite L3+L4 both firing. L1 → L4 improves 20-45% at every regime, but HRRR ch at this site has a hard MAE floor around 25 while persistence rides the diurnal echo down to ~8 at lead 1 / ~22 at long lead.

Sliced ch by regime: **only `frontal` beats persistence** (+0.058 skill, n=4,705). 8 of 9 regimes L4 BEHIND. I proposed a per-lead persistence blend. Joe caught the shape: *"only frontal works — gate it on there only, off elsewhere."* Estimated ~20% pooled ch MAE improvement.

Codified [[feedback-regime-gate-first]]: when a finding works in some regimes and not others, DEFAULT to "gate ON where wins, OFF elsewhere, ship" — NOT "flat/mixed/hold." The applicability map + skip-table architecture exist for exactly this.

Joe then pushed the discussion: *"you've done this all day — X only works in A,B,C regimes, and you've never once said 'great, gate it on only in those cases'."* Sharp catch on repeat framing bug. Named specific cases from earlier in the day: sr_confound (memory says nw_flow benefits, held anyway), cm Stage 4 (called "diffuse," never asked "in which regime is calibration still fine?"), dp depression nor_easter (small n → hold, never framed as "gate ON only there"), ch persistence gap (proposed per-lead blend when regime-gate was cleaner).

## Overfitting discussion + anti-overfit gates

Before running any sweep, Joe insisted on discussing overfitting risk. Real concerns: multiple comparisons (~1,260 potential cells at α=0.05 → 63 false positives), in-sample selection, small-n cells, regime classifier noise, correlated weather artifacts, regime × lead × hour spiral.

Codified anti-overfit promotion gates:
- Minimum n per regime cell: 1,000 (500-999 = Tier 2, <500 = Stage 1)
- Physical mechanism required (mechanism, not just correlation)
- Cap on gate granularity (regime OR regime × lead-band, not multi-axis spirals)
- **Split-halves stability check** — codified as standard pre-ship gate, stronger than "wait 7 days"
- Asymmetry check (≥3% both halves)
- Multi-tool-agreed kills stay killed

## Regime-gate sweep — first pass

Swept open/frozen/killed findings through the lens. Three Tier 1 identified, four Tier 2, six Tier 3 explicit stays-killed. Two frozen items (h → L4, sr shortwave-swap) had regime-gate answers sitting in data for weeks.

## Split-halves stability check — killed most of them

Joe asked: *"aren't these decisions based on data we already have and can verify?"* Sharp. The 7-day gate is for walkforward wobble; for large-n regime cells the right check is halves-agreement across disjoint 15-day windows.

Ran it. **Killed both L4 Tier 1 candidates:**
- h → L4 add: 7 of 12 WIN cells FLIPPED between halves. Recent half systematically worse — same HRRR cm anomaly contamination.
- cc L4 skip: pre_frontal/0-5h A_Δ=−8.4% B_Δ=+0.3% (LOSE only in recent). ne_flow/0-5h A_Δ=+8.9% B_Δ=+0.2% (cell I proposed to skip is actually helping most this week).

**The verification killed the ship, and that was the right outcome.** Framework caught what would have been shipped regressions.

Codified three noise patterns in [[feedback-regime-gate-first]]:
1. Recent-anomaly contamination (all fail recent-worse-than-prior)
2. Older-residue-dominated aggregate (both halves disagree with pooled label)
3. High-variance oscillation (successive halves flip sign chaotically)

## Second pass — LOSE cells for currently-on corrections

Joe pushed: *"aren't there some honest ones? Everything we have on can't be right for all regimes."* Sharp. Swept `l3_regime_lead_analysis` LOSE cells for wg + ws L3 (both currently on).

Halves check killed most:
- wg L3 se_flow/6-11h: pooled loss −11.7%, but both halves show L3 HELPING (+10, +27). Older-residue.
- wg L3 ne_flow/6-11h: A −7.6%, B +31.1%. Oscillation.
- ws L3 sw_flow/0-5h: pooled −3.4%, both halves flat/positive. Older-residue.
- ws L3 nw_flow/12-23h: pooled −7.1%, both halves flat/positive. Older-residue.

**One survivor:** wg L3 sea_breeze/6-11h. Recent −12.6%, prior −2.0%. Both agree LOSE. Mechanism verified: L2 bias direction flips sign between halves (recent −0.49, prior +0.96 mph); L3 applies constant −1.5-2 mph correction regardless; correctly reduces over-forecast one week, compounds under-forecast the next.

## Third pass — ws L3 by fc_ws + current-skip removal check

Sliced ws L3 by forecast wind speed bins (state_fc — decidable at forecast time). **Three stable LOSE candidates:**
- fc_ws 0-3 calm / 0-5h: recent −4.4%, prior −17.3%
- fc_ws 0-3 calm / 12-23h: recent −31.2%, prior **−77.5%**
- fc_ws 0-3 calm / 24-47h: recent −25.2%, prior **−66.0%**

Mechanism clear: L3's per-lead additive constant is structurally wrong for near-calm winds where a small absolute bias (0.5 mph) is huge relative to the baseline (1 mph).

Also checked CURRENT ws skip cells (ne_flow all + sea_breeze 0-11h) for removal candidates: no clear removes. All show "mixed" halves — recent half still says keep skipping. Conservative call: keep them.

## state_fc vs state_obs bug — the day's most valuable finding

Ran the ws + wg skip candidates through `production_whatif.py` for pooled Production impact preview. wg L3 skip in sea_breeze/6-11h showed **wg getting WORSE** (Δ +1.9pp). Contradiction with halves check.

Direct pair-log check on wg calm/24-47h recent 15d:
- **state_obs = calm**: L3 helps wg **+42.8%** (matches l3_regime_lead_analysis pooled)
- **state_fc = calm**: L3 hurts wg **−62.9%** (my halves check)

Same time window, same cell name, opposite verdict. **Different populations** — the overlap between "obs was calm" and "forecast said calm" is far from 100%. When forecast calm but obs wasn't, L3's calm-conditioned correction misfires catastrophically.

**Bug:** production_whatif was reading `state_obs.regime_synoptic` for regime-based skip evaluation. **Live `decay_apply.py` uses `state_fc`** (line 87 comment, line 470 code — state read from derived.state which is stamped from state_fc).

Fixed all 5 skip functions in production_whatif (`_ws_l3_skip`, `_sr_l5_skip`, `_cc_l4_skip`, `_wg_l3_skip`, `_ws_l3_skip_extra`) to use state_fc.

**Direction flipped for wg skip:** recomputed Production, wg went from getting worse to **wg −17.7% → −18.4% (Δ −0.7pp better)**. Same skip cells, correct axis, correct sign.

Codified [[feedback-state-fc-vs-state-obs]]: any analysis simulating a live gate must slice on the same axis the live code uses.

**Implications named honestly:**
- Live shipped ws L3 + sr L5 skips: behave correctly (always used state_fc).
- Only production_whatif ESTIMATES of shipped-skip impact were biased.
- Every Production impact number I quoted today for regime-based skips before this fix had biased-axis magnitude, some the wrong sign.

## Full regime-gate sweep tool

Built `h_full_regime_sweep.py` — comprehensive halves-check across every (field × layer × regime × lead_band). **11 SKIP + 2 ADD candidates cleared halves check** with correct axis.

Top skip candidates by impact:
1. wg L3 calm/24-47h (−62.8% / −52.2%)
2. ws L3 calm/24-47h (−25.2% / −66.0%)
3. h L2 ne_flow/24-47h (−12.2% / −29.1%) — **NEW**, requires L2 code path change
4. ws L3 nw_flow/24-47h (−9.5% / −11.2%) — new regime skip
5-11. wg L3 calm bands, ws L3 calm bands, h L2 ne_flow bands, dp L2 ne_flow/6-11h

ADD candidates:
- h L4 calm/12-23h — resurrected from broader kill as narrow candidate
- pr L2 sea_breeze/0-5h — CONTAMINATED (pr L2 was disabled 07-01 mid-window)

## ch regime-gate — LANDMARK ship candidate

Wrote `h_ch_persistence_blend.py`. Tested Joe's design vs 3 alternatives (persistence-only, linear ramp) with halves-check discipline.

**Result:** regime_gate cleared ★ SHIP on both halves:
- Recent 15d: Δ −27.9% MAE
- Prior 15d: Δ −14.1% MAE
- Full 30d: **−19.6% pooled ch MAE**

Per-regime: every non-frontal regime shows −7% to −31% improvement; frontal unchanged (L4 kept). Landmark within landmark: persist_only is essentially tied with regime_gate (20.66 vs 20.62 MAE) — even in frontal, L4 barely beats persistence.

**Implementation:** requires new module (`ch_persistence_gate.py`) that overrides forecast values with obs at run_time. Larger scope than skip-table config — shadow-log-first pattern recommended before flipping ENABLED.

## Lc anomaly-week HOLD

Joe asked what to do about the state-stratified "top actionable opportunity: Cloud cover × cloud cover (obs)" — Lc's job, already queued.

Checked whether Lc's fit table would work under the HRRR anomaly week. **It wouldn't:**
- cc 50-80 / 80-95: shift table would OVER-correct by 20-23pp
- cl mid-high bins: OVER-correct 11-30pp
- cm 50-80: UNDER-correct by 13pp

Bias magnitudes dropped materially between calib and anomaly windows; shift table trained on calib is stale for anomaly correlations. Added HOLD-until-07-18 caveat to Lc's gate description on debug page.

## Debug page canon

Full stale-spot sweep + condensation pass:
- Stage 4 numbers 26/0/9 + cm anomaly cause + 07-18 re-audit
- h → L4 re-freeze reason (halves-check contamination)
- Persistence-skill baseline referenced (2 "not yet built" → shipped)
- Lc anomaly-week HOLD (2 spots)
- Recent activity: today's entry added
- Prose condensation across ~15 sections: core comparison, metrics, retired list, skip-table architecture, L2 methodology, R0 audit description, C1 confidence layer block (massive), R2 state-stratified, Lc + dp Stage 1 candidates, retired archive, recent activity, live-layer gate, open watches, production stack (L3/Lsr/Lt/Lc lines). Info retained; verbosity cut 30-70% per block.

## gate_firing_rollup expected-dormant allowlist

Small structural improvement: distinguish ⚠ UNEXPECTED (silent dormancy candidates, action needed) from ✓ EXPECTED (waiting on gate / designed dormant). Lc/Lt/MLC in operators; C1h/t in pairs. Before: 4 items all flagged ⚠, 0 actionable. After: 0 unexpected, 4 expected with inline reasons.

## Not shipped (queued for later)

- **ch persistence gate module** — Tuesday scope with shadow-log first; ~20% pooled ch MAE prize
- **h L2 ne_flow skip** (3 cells) — architecture change to Kalman filter code path
- **dp L2 ne_flow/6-11h skip** — same code path
- **h → L4 add, calm/12-23h narrow** — needs L4 architecture change
- **ws L3 skip config-only ships** — WS_FCWS_SKIP_CELLS + regime cells; small pooled improvement, verified stable
- **wg L3 skip config-only ships** — calm all bands + sea_breeze/6-11h; small but real

Tuesday shipping candidate: bundle the ws + wg L3 config-only skips together. Production impact ~−0.6pp ws + no measurable wg = ~−0.1pp overall. Small but honest.

## Ship of the day

**v0.6.326** committed + pushed. Contents:
- 3 new analysis scripts
- production_whatif bug fix + new scenarios
- gate_firing_rollup EXPECTED_DORMANT
- corrections_debug.html Stage 4 updates + prose condensation

## Framework wins that outlast today's ships

1. **Regime-gate-first** as default framing rule (had been reflexively defaulting to "flat/hold" on heterogeneous findings for months)
2. **Split-halves stability** as pre-ship gate (stronger than "wait 7 days" and verifiable now, not later)
3. **Three noise patterns** to recognize in pooled analyses (recent-anomaly, older-residue-dominated, oscillation)
4. **state_fc vs state_obs** rule: any live-gate simulation must slice on the axis the live code uses
5. **Anti-overfit promotion criteria** for regime-gated ships (min n=1000, physical mechanism, granularity cap, halves agreement, asymmetry check, multi-tool-agreed kills stay killed)
6. **Persistence baseline** as reference for measurement framework — real skill gap now measurable per field per lead

## Honest self-corrections during the day

- Initial per-lead persistence blend for ch was over-engineered; Joe caught the regime-gate framing
- Initial "5% per-cell magnitude" rule was over-strict; source tool's WIN threshold sufficient
- Back-of-envelope "3-5% pooled ws improvement" was wrong; measured 0.6% (10× smaller)
- Initial framing of many "regime-conditional" findings as "hold" was systematically wrong
- Initial full-sweep did state_fc-based halves correctly BUT the production_whatif validation used wrong axis — spotted only after mismatch between halves-check and production_whatif verdicts

## Cross-refs

Related: [[project-persistence-skill-baseline]], [[project-ch-persistence-gap]], [[project-cm-stage4-degradation]], [[project-regime-gate-sweep-07-11]], [[feedback-regime-gate-first]], [[feedback-state-fc-vs-state-obs]], [[project-sr-unit-mismatch]], [[project-todo]], [[project-07-10-session]], [[feedback-forecast-verification]], [[feedback-co-owner-posture]].
