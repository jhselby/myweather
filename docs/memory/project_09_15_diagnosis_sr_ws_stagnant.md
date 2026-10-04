---
name: project-09-15-diagnosis-sr-ws-stagnant
description: "09-15 afternoon diagnosis of \"fresh sr + ws routing losses\" flagged in end-of-day feedback — sr was a stale-publisher artifact (fixed v0.6.628), ws is fresh nw_flow not stagnant_high, no ship warranted"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7c67af40-e0a0-4177-b868-d4878915ab22
  modified: 2026-09-15T22:00:44.737Z
---

Ran per the end-of-day recommendation ("diagnose fresh solar + wind-speed routing losses, verify whether stagnant_high is responsible, watch whether humidity continues healing"). Also did the debug page consistency sweep first (v0.6.633, five items).

**sr — no fresh routing loss.**
- 24h: routing +47.9%, cascade −7.3%, net +40.5%. All 4 bands positive (28-91% lift).
- 7d: total +20.4%, routing +11%, cascade +9.4%.
- 12h had 144 rows but all MAE=0 (night hours in local cache).
- Selector picks HRRR 757/759 in 24h — correct (HRRR raw 26.3 vs NBM raw 50.5).
- **The "catastrophic sr 12h" from yesterday's read was the stale-publisher artifact** — publisher was 2 days behind, blanking the 12h per-field diagnostic table. Fixed by 09-15 v0.6.628 (`make deploy-publisher` at 14:00:58 UTC). No routing intervention needed. No stagnant_high×sr gate to consider.

**ws — fresh routing loss confirmed, driver is nw_flow (not stagnant_high).**
- 12h: total −13.0% (routing −19.4%, cascade +6.4%). NBM raw 1.855 vs HRRR raw 2.211 — NBM 16% better this fresh window.
- Selector picks split 96 HRRR / 84 NBM at 12h; letting HRRR win where recent-window says NBM.
- Per-band: 0-5h +28.7% winning, **6-11h −38.0%**, **12-23h −46.3%**, 24-47h flat (no L2 firing).
- **Regime split at affected bands: 100% nw_flow** (bands 0-5, 6-11, 12-23 all nw_flow; 24-47 had the mix — stag+pre_front+frontal — but zero lift there anyway).
- Pooled selector table (fitted 10:28 UTC 09-15): ws/nw_flow at 6-11h/12-23h is 30d HRRR-favored (−4.1% / −3.6% lift) with recent-7d essentially neutral (−0.53% / −1.2%). Fresh 12h is a regime-specific short-window flip the pool hasn't seen.
- By-regime walker has zero ws/nw_flow cells today. Only surfaced cells: calm/12-23/nbm and calm/6-11/nbm (sum_n 9/13, way below 60 gate), plus sea_breeze/24-47/hrrr already cleared. Escalation clause needs |lift|≥20% AND n≥500 same-day; affected bands have ~48 rows each.

**Why:** fresh (<24h), nw_flow-specific, sample thin — below both the 3-day gate AND the escalation clause. Walker will catch it tomorrow/Thursday if it persists; self-heals if the regime shifts.

**How to apply:** if end-of-day 12h read shows a "fresh routing loss" and (a) the affected bands are 100% one regime, (b) that regime is nw_flow / calm / sw_flow (not stagnant_high), (c) sample is < escalation-clause n, and (d) the walker has no cell on that regime yet — do NOT ship a named gate. Wait 1-2 daily walker reads. Stagnant_high×ws was retroactively +16.6% NBM lift but stag rate is ~2% of rows; fresh ws routing losses in a nw_flow window are NOT the stag pattern.

**stagnant_high walker first read is 09-16** (day 3/3 of the v0.6.605 stamps). Sample was ~2% of 24h pair-log rows today (212/8001) — matching Joe's prediction, but too thin for cell candidates yet on ws/sr.

**h fresh fire status:** 12h routing collapse −57.9% with cascade compensating +46.7%. Consistent with the 09-13/14 legacy-stamp story already tracked in the dp/h clock-watch. Watch 09-17 for HEALING.

**No new ship warranted from this diagnosis.**

Related: [[project_09_15_session]] (main session recap, v0.6.633 debug page sweep), [[feedback_prod_real_vs_replay_divergence]] (used indirectly — the h routing/cascade split reads like a runtime-stamp issue not a corrections-quality issue), [[project_frontal_detector_health_09_14]].
