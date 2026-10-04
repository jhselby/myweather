---
name: cc-derived-field
description: "cc is derived-with-tunable-composition as of 2026-07-31 (nuance added v0.6.390e). Retired from Lc, no independent L1/L2/L3/L4 corrections ever, composition owned by Ccd (currently max(cl_l6,cm_l6,ch_l6), may become regime-conditional if h_cc_blend_formula tuner surfaces halves-stable wins). **08-04 v0.6.391 Ccd saturation guard:** if raw cc ≥ 90, keep raw (skip derivation) — fixes overcast-tail case where cm/ch Lc over-corrects and drags max composite below METAR total sky cover. cc still measured daily. Excluded from Overall scoreboard aggregate. Do not re-add cc to Lc or to the scoreboard mean."
metadata: 
  node_type: memory
  type: project
  originSessionId: ee3022f3-1d0e-4e93-abfb-dbc558df1928
  modified: 2026-08-04T14:56:28.429Z
---

# cc is derived-with-tunable-composition — not an independent forecast quantity, not a frozen derivation

**Decision dates:**
- 2026-07-30 v0.6.390 — Ccd flipped, cc retired from Lc, excluded from scoreboard aggregate
- 2026-07-31 v0.6.390e — architectural nuance added: cc is derived-with-**tunable-composition** (not purely derived)

**The three-position framing (settled 2026-07-31):**
1. ❌ **cc as independent field** — L1/L2/L3/L4/Lc corrections on cc alongside cl/cm/ch. Double-counts the cloud stack because HRRR's raw cc IS max(raw cl, raw cm, raw ch) — verified 20/20 in raw data 2026-07-31. This was the pre-v0.6.390 architecture that broke on 07-30.
2. ❌ **cc as purely derived / frozen** — cc = fixed formula(cl_l6, cm_l6, ch_l6), never scored, no daily measurement. Forecloses any tuning of the composition formula.
3. ✅ **cc as derived-with-tunable-composition** — no L1/L2/L3/L4/Lc corrections of its own, Ccd owns composition, composition itself may be regime-conditional. cc still measured daily as (a) input to the composition tuner, (b) drift detector once a composition is chosen.

**Current composition (2026-07-31 Stage 0 verdict):** `max(cl_l6, cm_l6, ch_l6)` in ALL regimes. `h_cc_blend_formula.py` Stage 0 tuner found max wins in 8/10 regimes; only non-max signals were frontal (+4.3% for random, but halves UNSTABLE A=−2%/B=+8%) and nor_easter (+30.9% but one-sided data, halves A=8/B=233). One clean per-cell candidate to carry forward: pre_frontal/0-5h random +3.5% at n=2,115. Re-check tuner ~08-07.

**What it means:**
- cc is in `_FIELD_SKIP` alongside cl in `weather_collector/processors/cloud_saturation_correction.py`. Lc doesn't touch cc.
- Ccd (`cc_from_derivation.py`, `ENABLED=True`) runs LAST in the cloud pipeline. Overwrites `hourly.cloud_cover` with `max(cl_l6, cm_l6, ch_l6)` for ~85% of ticks; falls back to Pirate cc for `SKIP_REGIMES = {"se_flow", "unknown"}`.
- cc excluded from Overall MAE mean / RMSE mean / median / best / worst / worst-cell / winning-count in `corrections_debug.html`'s accuracy card. Filter is `DERIVED_FIELDS = new Set(["cc"])` around line 2884. cc renders as informational "Derived (not in mean)" row below the tiles.

**Why:** cc is HRRR's own internal combine of cl/cm/ch. Running Lc on cc in parallel with Lc on the three components was double-correction from Lc's original ship weeks ago. The +8.5% Ccd win on 123K held-out quads is what that architectural mistake was costing us on average; 2026-07-30's Lc collapse (cl+cc both catastrophic together) is what it cost us in the worst case. cc double-count also inflated the scoreboard's Overall MAE — Joe's primary daily instrument — making the pipeline look better on cloud-heavy days and worse on cloud-broken days than it actually was.

**How to apply:**
- **Do not re-add cc to `_FIELD_SKIP`'s complement or to `CLOUD_FIELDS` Lc application.** Adding cc back means both HRRR's internal combine AND our shift-table run against cc → same double-count returns.
- **Do not re-add cc to the scoreboard aggregate.** cc's error is mechanically a function of cl/cm/ch's errors (Ccd is `max()` of those three) — counting it in the mean triple-weights the cloud stack.
- **On any new independent-vs-derived question:** cc, dp are the two "derived from other tracked fields" fields today. dp = Magnus(corrected t, corrected h) — 100% derivative but small numerically. If dp acquires an independent additive specialist (dpbp/dprp both in flight, gates 08-04 / 08-01), it becomes semi-independent again.
- **Ccd fallback regimes are important.** SKIP_REGIMES = {"se_flow", "unknown"} because Ccd's `max` under-performed vs Pirate cc + Lc in those regimes on held-out. Don't remove these without re-running `h_cc_derivation.py`.
- **Reversibility:** `ENABLED = False` in `cc_from_derivation.py` disables Ccd (falls back to whatever Lc's `_FIELD_SKIP` says for cc). Removing `"cc"` from `_FIELD_SKIP` re-enables cc's own Lc path. Both reversals need to happen together — one without the other leaves cc uncorrected.

## Related

- [[project_lc_regime_conditional]] — the crisis that forced Ccd's early flip
- [[project_cc_is_blend_of_clchcm]] — the architectural observation that made Ccd inevitable
- [[feedback_per_field_snapshot_live]] — the debug-page wiring that surfaces cc's current status
- [[feedback_ratio_over_absolute]] — same "surface honest daily signal" principle as the regression sentry
