---
name: project-09-26-session
description: "2026-09-26 Sat morning digest — one big ship, v0.7.5 router-as-authority live (ch via ims-threshold, sr via GBM). Killed the 10-02 fresh-corpus gate as over-cautious. First tick clean 10:57 UTC."
metadata: 
  node_type: memory
  type: project
  modified: 2026-09-26T11:02:12.708Z
  originSessionId: b263e9cd-d969-4acf-add7-b0c4f9f5625c
---

# 2026-09-26 (Sat) — v0.7.5 router-as-authority ship

## What we shipped

One commit, `f053c88e`: [[project_router_as_authority_pivot]] LIVE.

- `_IMS_SELECTOR_CELLS` refreshed to the 10-cell ims-threshold refit table. `IMS_SELECTOR_SHADOW_ENABLED = True`.
- `l1_learned_selector_curated.json` populated with 5 sr STABLE GBM cells from v5 sweep (ch cells stripped). `LEARNED_SELECTOR_SHADOW_ENABLED = True`.
- v0.7.5 index.html/version.json/sw.js.
- Backup at `weather_collector/data/l1_learned_selector_curated.json.pre-v0.7.5.bak`.

Deploy 10:53:12 UTC, first tick 10:57:02 UTC clean.

## Morning digest read

Selector Skill tile: **7d VC +36% median / +31% mean (green), 24h VC −33% / −100% (red).** 0 winning, 4 flat (h, ws, ch, sr), 3 losing (t, wg, wd) on 24h.

Attribution panel: Routing −6.3% (7d) / −8.3% (24h) — routing subtracts skill; Cascade +18.9% / +23.5% covers it; Total +12.6% / +15.2% green.

**Diagnosis** — 24h ws win rate collapsed 60% → 22% (n=767). h 55% → 42%. wg 54% → 44%. Real regime-shift event, not variance. But the ships in the queue (ch via ims-threshold, sr via GBM) don't touch ws/h/wg — they target ch/sr, which are already fine today.

**Decision** — don't chase the 24h tile. Ship the pivot the last 3 days of work has been building toward. The 7d selector is winning; today is one bad regime day.

## Killing the 10-02 gate

Prior plan blocked ship on 7d fresh corpus after the 09-24 backstamp fix. Realized mid-conversation:

1. Halves-stable A/B is the exact gate that caught 09-24's stale-fit (11 of 13 blender cells failed). v5 STABLE cells passed it. Same guard, no calendar wait needed.
2. v5 sweep ran 09-25, post the 09-24 backstamp appender going live. Corpus was fresh at fit time.

The 10-02 date was over-caution. Shipped 6 days early.

## Session shape

User directive was "co-owner, push forward, stop grinding the digest." First pass I proposed a split ship (ch today, sr on 10-02) — user pushed back: "what about all the stuff we've been working on the last few days." Retracted the split, shipped the whole pivot.

**Lesson** — the split-ship reflex was fear of the 10-02 gate. If the fit-time gate is the real safety net, calendar buffers on top of it are noise. Push against my own hedging when the mechanism is already there.

## Watches / clock-watches

- **10-03**: first 7d pair-log after v0.7.5. ch VC should push toward >+70; sr should climb from +38%. If either regresses on halves-stable, rollback = one flag flip back to False.
- **~11-04**: selector recency override Chk 3 (was armed 09-11).
- The [[project_09_25_session]] schedule (~10-02 router ship) is complete — retire the calendar entry.

## Non-ships (deliberate)

- Didn't touch ws/h/wg/t despite them being 24h losers. That's regime noise on small n; the 7d signal is fine.
- Didn't re-curate the blender (still frozenset() apply after v0.7.3 rollback). Its 2-3 real cells wait for their own halves-stable refit — not on the critical path.

## Related

- [[project_router_as_authority_pivot]] — updated with ship record.
- [[project_09_25_session]] — pre-ship state.
- [[project_l1_blender_stale_fit_audit]] — the incident that established the halves-stable safety-net.
