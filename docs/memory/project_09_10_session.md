---
name: project-09-10-session
description: "2026-09-10 (Thu) — 6 ships (v0.6.577-580 + 580a/b). Two-tool-agreement cc L3_NBM kill + wg pre_frontal REMOVE (second harvest of the two-window verdict), then a massive debug page overhaul: Stack Health trajectory chart added at top of Current State (real compounding-over-time chart, denominator FIXED at 90d raw baseline so weather is absorbed), killed sec-status H2, moved Recent activity + Forecast accuracy into their proper homes, aggressively trimmed the per-field Status column, and shipped mobile fixes + iOS SW updateViaCache fix."
metadata:
  node_type: memory
  type: project
  originSessionId: session_01ARP7jjvgjxAXoiwzd4tY52
  modified: 2026-09-10T18:41:37.220Z
---

# 09-10 Thu — 6 ships, big page reorg, aggregate-trend chart

## Ships in order

- **v0.6.577** — cc dropped from `L3_NBM_FIELDS` (now `("wg", "ch", "sr")`). Two-tool agreement: sentry HOT on cc.l3_nbm (help +9.4% sustained → −8.3% fresh, Δ +17.7pp with sign flip) + walkforward independently proposed DROP cc same day. Scoreboard corroborated (per_field cc corr −13.1%, nbm raw 20.17 → prod 22.82). Same shape as sr.l5_nbm 08-25 kill. cc was already out of L4_NBM_FIELDS since v0.6.563 (09-08); L3 was the last NBM cascade layer touching cc. `KILLED_LAYERS` seeded with `("cc", "l3_nbm"): "2026-09-10"`. Deploy 10:55 UTC, revision 00557-gox.
- **v0.6.578** — `skip_table_nbm_curated.json`: `l3_nbm.wg` cell `["pre_frontal", 6, 12]` removed. Table 14 → 13 cells. **First single-cell REMOVE under the two-window verdict shipped v0.6.574** — cleared both 14d fresh (n=282, +4.64%) AND 50d long (n=1,046, +4.69%). Halves-stable on both. Deploy 12:30 UTC.
- **v0.6.579** — debug page sweep (Recent Activity roll to 09-10 today, NBM cascade line refreshed with today's kills, skip-table count 14 → 13).
- **v0.6.580** — massive debug page overhaul. See "Debug page overhaul" below.
- **v0.6.580a** — mobile scoreboard: `.sb-num-row` gets `flex-direction: column` on ≤640px so 24-HOUR stacks below 7-DAY instead of trying to fit inline.
- **v0.6.580b** — SW registration gets `updateViaCache: 'none'` so iOS re-fetches `sw.js` on every update check instead of HTTP-caching it for 24h.

## Stack Health trajectory chart — the real product of this session

New compact aggregate chart at the top of Current State (`#sec-stack-health`). Per-obs-day cross-field median + mean + P25–P75 band of `(1 − prod_MAE / raw_MAE_90d_ref) × 100`, plotted with 7d rolling overlays, a red-dashed linear trendline, and numbered orange-circle ship-event annotations at the top of vertical dashed lines with a numbered legend below.

**Denominator is FIXED at each field's 90d raw MAE ref** (from `raw_difficulty_index.per_field`, same source as the Difficulty column shipped 09-09 v0.6.576). This is the whole point: a lift-ratio where numerator and denominator co-move (daily raw baseline) stays flat by design when Prod tracks weather. Fixed 90d ref means the ratio moves only when Prod moves — real stack quality trend, not weather noise.

**Key finding** — I initially called the 3-month history "flat" and framed it as "our stack is stable but not compounding." Joe pushed back on the chart. Re-reading: 7d rolling median trended **~10-15% (June)** → **~20-25% (September)**. That's **~+1pp/week of aggregate lift added by shipping**. The stack IS compounding. Retracted the "flat" claim mid-conversation. Same class as [[feedback_refresh_current_state_before_defending]].

**Y-range control**: Auto (smart, centered on median-of-smoothed-median with 1.8× spread padding, clamped ±10 to ±40pp half-span) + Free. Numeric ±X presets were shipped then dropped per Joe — "just Auto and Free is all we need."

**Ship-event annotations** — curated under the rule "≥2 fields OR structural cascade change" (single-field ships belong on the per-field chart's SHIP_EVENTS, not the aggregate). Went back to the start of the data window (06-16). 8 events total: 06-16 L2 τ fitter train/test guardrail (5 L2 fields), 07-17 Lc, 08-18 L1 router, 08-19 selector armed, 08-20 selector cascade→NBM (cc/wg/dp), 08-26 NBM native L2 parity (8 fields), 09-05 h+ch NBM kills (2 fields), 09-10 cc+wg NBM cleanup (2 fields).

**Also lives inside** the full Accuracy over time section as one of the field-selector options (was default there for one iteration, then dropped — Joe: "just this one graph, right? The other over-times stay where they are"). Bottom Accuracy over time is now per-field-only again (default Temperature).

## Debug page overhaul (v0.6.580)

Beyond the Stack Health chart, this ship reorganized the whole above-the-fold portion of `corrections_debug.html`:

- **Killed the `sec-status` "Engineering updates — where we are" H2 entirely.** ~90% duplicated What's Running. Unique content — MLC sandbox + L2-as-observation-only + tight-τ cloud bias propagation across leads 1-3h — moved to a new "🧪 Architectural backlog" sub-block at the bottom of "What's being evaluated next." TOC entry + inline `#sec-status` cross-refs cleaned.
- **Recent activity moved from standalone H2 into Current State** as a sibling collapsible details block. It's project narrative (like What's running, What's improving, What's being evaluated), not data.
- **Forecast accuracy moved from top-level H2 into Research & Diagnostics** as a diagnostic sub-item. It's not primary-read content; belongs with the R- and F-tagged audits. Anchor `#sec-accuracy` preserved via inline `<a id>` at new location; TOC entry + one internal cross-reference still resolve.
- **All Current State sub-sections now use matching collapsible `<details open>` styling** (Stack health, Per-field diagnostic, Per-field pipeline architecture, What's running · improving · being evaluated next, Recent activity). Previously Per-field diagnostic + Per-field pipeline architecture weren't consistently wrapped. Emojis (📈, 🟢🟡🔵) stripped from titles and the two 🟢s in the Guards list.
- **Aggressive Status-column trim in Per-field pipeline architecture table.** Was 13 journal-style cells averaging ~800 bytes each with July-back ship dates and closed-watch history. Now 1-2 sentences per field: current state + open work only. Pipeline · HRRR / Pipeline · NBM columns untouched (real reference value). Total: ~13KB → ~2KB. See [[feedback_status_column_current_state_only]] class of guidance.
- **What's being evaluated next — Upcoming grid rewrite** to today's forward calendar (Thu 09-11 walker read, Sun 09-14 sr sentries clear, Mon 09-15 cm DROP + KILLED prune) + Backlog block (12d walkforward ADD proposals rescore, ADDED_LAYERS registry mirror, NBM sea-breeze specialist gated on stack-health trajectory).
- **Current state H2 subtitle "— what's running · improving · being evaluated" deleted** — inaccurate after all the sub-sections were added.
- **Mid-page divider "Details for each cell live in the sections below · Accuracy · Research & Diagnostics" deleted** — noise.

## Mobile fixes (v0.6.580, .580a)

`@media (max-width: 640px)`, desktop untouched:

- **TOC** gets `flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none` — single horizontally-scrollable row instead of 5 wrap rows.
- **Scoreboard 24-HOUR row** — the second `.sb-num-group` was rendering side-by-side with 7-DAY, causing the "24 HOUR" label to fall inline with the 7-DAY MEAN number. Fix landed in two steps: (1) reset border-left + padding-left + margin-left + margin-top:14px on the second group — didn't force wrap; (2) added `flex-direction: column` to `.sb-num-row` so window groups stack cleanly.

## iOS PWA cache trap (v0.6.580b)

Joe reported PWA stuck on v0.6.579 even after killing and reopening. Root cause: SW registration didn't specify `updateViaCache: 'none'`, so iOS Safari HTTP-cached the `sw.js` file itself for up to 24h. Reopening the PWA re-fetched the SAME cached sw.js which still thought CACHE_VERSION was v0.6.579.

Fix: `navigator.serviceWorker.register('/myweather/sw.js', { updateViaCache: 'none' })`. From now on `reg.update()` (fires every 30 min + on page load) does a network fetch of sw.js and picks up CACHE_VERSION bumps immediately.

Effect on Joe today: fix ships forward but the current stuck state persists — the browser is still using the pre-fix registration. Break-out options: (1) delete + reinstall PWA icon from Safari (surefire, ~30s), (2) Settings → Safari → Advanced → Website Data → remove wymancove data, (3) wait ~24h for HTTP TTL. **After any one of those**, future version bumps propagate within 30 min without manual action.

## Lessons captured

- **Percent-lift charts of a stable stack look flat by design.** When numerator (Prod MAE) and denominator (Raw MAE) co-move with weather, the ratio has no signal. The instructive metric is `prod / fixed-baseline`, not `1 − prod / daily-raw`. The 90d raw ref pulls this apart. See [[feedback_fixed_denominator_reveals_trend]] class.
- **My chart-flat critique was wrong; Joe was right.** Called the aggregate trend "flat 3 months" from a glance at the smoothed line; the actual data was +1pp/week compounding. Fell into the same class as [[feedback_refresh_current_state_before_defending]] — looked at the shape, described a narrative that felt right, missed the actual signal in the data. Retracted after Joe pushed back.
- **Sequential regex replacement over shared HTML** — my first Status-column trim matched `<code>ch</code>` at line 1466 (in a scorecard tile, first occurrence in the doc) instead of the per-field table's ch row (line 2041). Non-anchored `.*?` non-greedy expansion picked up the wrong Status td. Fix: anchor each field's row-match with the row's full "Field column" text (e.g. `<code>ch</code> high cloud`) so the regex can't wander. Rule: when replacing per-item cells in a big HTML doc, anchor the pattern to something unique within the row, not just to a token that occurs elsewhere.
- **iOS Safari HTTP-caches sw.js for up to 24h by default.** Without `updateViaCache: 'none'` at registration time, SW updates can be arbitrarily delayed. Ship this option in every new PWA project going forward. See [[feedback_sw_updateViaCache_none]] class.
- **Killed sections whose only reason to exist was history.** The whole Engineering updates H2 was 3 unique bullets (MLC, L2-as-observation, tight-τ cloud bias) buried under ~90% duplicate What's Running content. Moving those 3 bullets into "What's being evaluated next" as an Architectural backlog block preserved the value and cut noise. Rule: a section whose unique content fits in 3 bullets doesn't need its own H2.
- **Cascade-line + scoreboard state annotations need to move with the ships.** Both were updated to reflect today's cc drop + wg REMOVE within the same session. Rule: any ship that changes cascade shape needs the debug page's cascade-summary line updated in the same session, not deferred to a sweep.

## Watches carried forward for tomorrow

- **09-11 (Fri)** — L1 by-regime walker first cell-wire read under the loosened gate (day 3/3). ws/nw_flow/12-23 most likely to clear first (n_today=228 on 09-08).
- **09-14 (Sun)** — sr.l5_nbm HOT + sr.l3_nbm WATCH sentries clear as 09-04 pre-add sustained-window data ages out.
- **09-15 (Mon)** — L3 DROP cm walkforward streak clears if 7/7 holds (day 2/7 today).
- **09-15 (Mon)** — KILLED_LAYERS registry prunable: 09-05 entries (ch/chp_nbm + h/l3_nbm) both windows post-date the kill.
- **~09-17** — cc.l3_nbm KILLED verdict ages out (registry seeded 09-10 today, needs 7d sustained + 3d fresh past the kill).
- **7d watch on today's ships** — cc NBM-path prod MAE from 22.82 → toward 20.17 (nbm raw); scoreboard cc corr from −13.1% → toward 0. wg pre_frontal 6-11h lift in the fresh window.
- **Stack health trajectory** — is the +1pp/week compounding rate sustained after this week's ships, or does it plateau? Plateau = trigger the NBM sea-breeze specialist workstream.

## Related

- [[project_09_09_evening_session]] — Difficulty column (raw_difficulty_ratio) shipped yesterday; same `raw_difficulty_index` payload feeds today's Stack Health trajectory chart. Cross-check: 7d ÷ 90d ratio in the diagnostic table matches the aggregate chart's denominator source.
- [[project_09_09_session]] — v0.6.572 symmetric REMOVE audit that shipped yesterday; today's v0.6.578 is its first single-cell REMOVE under the two-window verdict.
- [[project_cc_l3_nbm_watch_09_08]] — the standing cc.l3_nbm 24h REGRESS watch that resolved today into a full-field kill.
- [[feedback_baseline_is_user_default]] — Stack Health uses each field's user-default raw as the 90d baseline (raw_nbm for NBM-scope, raw for HRRR-only), consistent with per_field_scoring.best_raw and scoreboard_v2.
- [[feedback_metric_provenance_labels]] — chart title carries the formula in-line: "Prod vs 90d-ref raw (%, ↑ = beating baseline)".
- [[feedback_audit_label_direction_neutral]] — related but different; direction-neutral is the Difficulty column, aggregate Stack Health is direction-loaded (↑ = better).
