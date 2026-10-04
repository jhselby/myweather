---
name: debug-page-is-canon
description: corrections_debug.html is the canonical source of truth for the correction-stack state. Two non-negotiable conventions for any hypothesis/audit work.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a933ef0e-f53e-46b4-802a-0d1b833732d0
---

corrections_debug.html is the canonical source of truth for the correction-stack state. Anything that lives only in memory, changelog, or scripts but not on the debug page is invisible — and therefore effectively doesn't exist for purposes of decision-making in future sessions.

**Why:** Joe explicitly said "I want that page to be the canon" (2026-06-23). Memory and changelog accumulate sediment that no one reads. The debug page IS read — by Joe, by visitors, and by future-Claude as the starting reference.

**How to apply — two non-negotiable rules:**

1. **Every Stage 1+ candidate on the page must carry an explicit wired-state badge.** Use plain text labels right next to the candidate name:
   - `🟢 Auto-wired` — runs in Fitter or collector every cycle/tick, no manual intervention needed
   - `⚫ Manual` — Stage 0 script only, decisions wait on hand-invoked `analysis/h_*.py` runs
   - `🟡 Hybrid` — partially auto-wired (e.g., stamp lives but verdict still requires manual replay)
   - `🔒 Gated off` — built, deployed, ENABLED=False

   Don't bury the wired state in narrative. Put it at the top of the entry so it's findable on skim.

2. **When a manual is run, update the debug page entry with the new numbers + date stamp.** Don't just commit the result to memory or a one-time changelog mention. Find the relevant Stage 1 / Stage 0 entry on the page and:
   - Update the headline numbers (% gain, n, magnitudes)
   - Add or update a `Last manual run: YYYY-MM-DD` stamp
   - Note if anything moved (e.g., "magnitude tightened from +5.0% to +4.2% on 06-29 read")

The discipline mirrors how production Stage 2 audits work — every Fitter cycle their numbers refresh on the page. Manual runs should follow the same hygiene; the only difference is the human in the loop.

3. **"Since last curation" block sits at the top of the Status drawer.** Added 2026-06-24 v0.6.220 per Joe's request. Every curation rewrites this block to show the diff against the prior state — what shipped, killed, weakened, or built. Glyph palette: `✓` shipped, `✗` killed, `↺` weakened, `⚙` infrastructure. Pattern: bulleted list of one-liners with code spans for the file/version. Goal: at-a-glance status without scrolling the whole page. The block goes between the `Last curated:` stamp and the `One-line summary:` line.

4. **Skim-check after every Stage 2 ship.** Walking the page top-to-bottom catches stale references that didn't update with the ship. Example: when cc → L4 shipped (v0.6.214), the page-1 summary still read "L4 whitelist: ch only" — Joe caught it on the read-through and we fixed it in v0.6.221. Add a "did the page-1 summary still match this ship?" pass to every Stage 2 commit.

5. **Transition-invalidation sweep — grep every mention.** When a hypothesis/layer/gate transitions status (dormant → retired, HOLD → shipped, MARGINAL → ship, ship → reverted, Stage N → Stage N+1), the debug page's deep reference sections describe PLANS that become factually wrong the moment the plan executes. Top-summary sweeps miss them. **Rule:** in the same commit that ships the transition, run `grep -n "<old-status-keyword>" corrections_debug.html` and update every hit. Specifically:
   - **Layer retirement** (e.g., Lt): grep for `dormant`, `path back`, the specific plan-text (`Fix B`, `refit against L2`, etc.), the old status badge (`[DORMANT LAYER]`).
   - **Ship promotion** (Stage 2 → Stage 3): grep for `pending X-day gate`, `earliest ship YYYY-MM-DD`, `Stage 2 preview` mentioning the just-shipped candidate.
   - **Verdict flip** (HOLD → SHIP or KEEP → SKIP): grep for the old verdict text.
   - **Skip cell / whitelist change**: grep for the old cell list — the SHIPPED-status table, the specialists list, and any per-layer detail section may all quote it.
   - **Failed refit / dead-end**: grep for `path back`, `future work`, `queued for` — anything promising a next step that just got answered "no."

   **Why:** codified 2026-07-14 after Joe caught the [DORMANT LAYER] Lt section still saying "Path back — Fix B" a full day after Fix B was run (07-13 v0.6.329) and Lt was retired. Every debug-page sweep in the interim only touched the top summary sections (Recent activity, calendar, SHIPPED table, top widget); the deep R&D subsection ~1800 lines down was assumed to be static reference content and skipped. It wasn't static — it described a plan that had executed and failed. Joe read the page fresh and got misled into thinking Fix B was still ahead of us.

   **How to apply concretely:** at the end of any ship commit that changes state, before final `git commit`, run:
   ```
   grep -n "<keyword-from-invalidated-plan>" corrections_debug.html
   ```
   and address every hit. A shipped ch persistence gate flip means grep for "day N/7" mentioning ch. A retirement means grep for "dormant pending X." A killed hypothesis means grep for the old "path back" text. Zero remaining hits = clean sweep.

   **Automation (2026-07-16):** `scripts/check_stale_refs.py` (or `make check-stale`) grep-checks the debug page for stale predictive-tense refs — day counters `(MM-DD)`, `as of MM-DD`, `HOLD until MM-DD`, `earliest ship/flip MM-DD`. Exits 1 on any date > 2 days old. Historical refs (`shipped 07-12`, session narratives) deliberately left alone. Codified after v0.6.352c missed 10+ refs and required a v0.6.352d re-sweep — Joe pushed back after I did the tri-column only. Run this before pushing any debug-page commit involving date/counter refs; it turns the manual-discipline Rule 5 into a mechanical check.

**Related:** [[feedback-hypothesis-promotion-pipeline]] (the 4-stage gate this all rides on), [[feedback-section-cruft-accretion]] (the visual-redesign cousin — when SECTIONS need rewriting for cumulative-cruft reasons; this rule is the factual-staleness cousin), [[project-todo]] (the work that gets scheduled around manual re-runs), [[feedback-orthogonality-gate]] (the same-day discipline that produces the candidates that go on the page).
