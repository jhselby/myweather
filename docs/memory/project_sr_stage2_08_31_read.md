---
name: sr-stage2-08-31-read
description: "08-31 sr sea_breeze Lsr shortwave Stage 2 re-run with 6+ weeks accumulated data: VERDICT HOLD pooled (-0.22%), but hours 17-18 concentrate a clean narrow ship signal (+25.9% on 244 firing rows, halves 2/2 both cells). Cause B strongly confirmed for sea_breeze (matched-bin +86); pre_frontal has shifted toward Cause A (matched +16, big-miss +47) — likely permanent-defer."
metadata: 
  node_type: memory
  type: project
  originSessionId: 132ee303-a10d-41fa-9c87-55f062f955a8
  modified: 2026-09-01T10:53:46.857Z
---

# sr sea_breeze Lsr shortwave — 08-31 re-read

Re-ran `analysis/sr_sea_breeze_lsr_refit_stage2.py`, `sr_sea_breeze_lsr_refit_stage1.py`, and `sr_shortwave_cc_confound.py` with post-08-12 accumulated data.

## Stage 2 verdict: HOLD

- Test n=956 sea_breeze rows (2026-08-16 → 08-29). Intervention gated cc<25 fires on 302 rows (32%).
- Pooled Δ **-0.22%**, halves A -0.60% / B +0.27%. Fails 5% floor.
- Per-hour: hour 17 SHIP +21.9% (halves +17/+26, n=125); hour 18 SHIP +31.7% (halves +27/+36, n=119). Everything else SKIP.
- Per-lead-band: all 4 SKIP.
- The 07-16 Stage 1 +43.71% ship was noise on a 3-day test. 07-28 read had already dropped to MARGINAL (halves 1/2). Today's read confirms: signal narrows to a 2-hour valid-time window, not a broad regime effect.

## Cause-A/B update from confound diagnostic

**sea_breeze (n=2,033, was 2,017 on 07-11):**
- matched (|Δcc|<10) n=437, mean signed err_sw **+86.47** (was +83.63 on 07-11 with n=825)
- All 4 cc bins run +75 to +91. Cause B **strongly confirmed** — flat positive bias regardless of cloud match.

**pre_frontal (n=5,636, was 5,064 on 07-11):**
- matched **+16.16** (was +14.07, still small)
- small-miss +19, big-miss **+47**, severe +27
- Interpretation shifts toward **Cause A** — big cloud errors drive the overshoot, not a raw shortwave bias. Likely permanent-defer for pre_frontal Lsr refit.

## Narrow ship candidate (not today)

**sea_breeze × cc<25 × hour ∈ {17, 18}:**
- Firing rows n=244. Firing-only base MAE 75.91 → intervention 56.22 = **+25.9%**. Halves clean on both cells.
- Pooled on all sea_breeze rows: only +3.6% because 74% of rows are no-op.
- Not shippable under current Stage 2 gate (needs pooled ≥5%). Would need either:
  - (a) Stage-2b variant that measures lift only on firing rows (~244 n), narrower ship gate
  - (b) Wait 2-4 more weeks for the cell to prove stability, then evaluate at Stage 3 wire-in with narrower cc/hour cells only

## 09-01 re-read

Numbers essentially unchanged from 08-31: pooled Δ -1.18% HOLD, hours 17 SHIP +25.3% (halves +19/+32, n=123), hour 18 SHIP +37.2% (halves +41/+35, n=112). Same story, slightly larger test window.

**New fact:** `sr_sea_breeze_lsr_refit_stage1` flipped **promote→kill** in the 09-01 digest (was PROMOTE 08-31). The pooled Stage 1 base is unstable day-over-day. This raises the bar for narrow-ship: cannot build a Stage 2b narrow-firing walker on top of a Stage 1 that's flipping verdicts. Wait for Stage 1 to hold either PROMOTE or KILL for at least 3 consecutive reads before considering the narrow-ship infrastructure work.

## Blocker status

Three downstream sr candidates remain blocked (see [[project_sr_unit_mismatch]]):
- `l2_lead_decay_fit`, `l2_regime_lead_analysis`, `sr_sea_breeze_lsr_refit_stage1` — all measure against contaminated substrate. No change.

## How to apply

- Do **not** ship sr Lsr override today. Stage 2's own verdict = HOLD is correct.
- Re-read hours 17-18 SHIP cells in 2-4 weeks. If they stay clean, build Stage 2b (firing-only gate) or advance to Stage 3 with cc/hour explicit cells.
- pre_frontal Lsr refit: mark deferred → permanent-defer pending stronger Cause-B signal.

Related: [[project_sr_unit_mismatch]], [[project_08_31_session]].
