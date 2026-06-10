# MyWeather Session Handoff — 2026-06-08 EOD

Paste this into a new session as the first message, or have the new Claude read it via `Read /Users/josephselby/Documents/myweather/HANDOFF.md`.

---

Currently live: **v0.6.51** (commit `031066a`).

## Today's work (already shipped)

- **v0.6.51**: L2 lead-decay documented in debug page. New sec 2d chart (`exp(-lead/τ)` for t/h/pr from `weather_data.l2_decay_meta.tau_hours`, wind/gust linear 0–24h ramp, flat reference for the rest). Placed before 2e (post-mesonet grid) to match pipeline order. L2 prose updated, R3d τ-tuning disambiguated, header meta de-cluttered (was "L3/L4 per-field (v0.6.45) · L3: ch, cm, pp, wg, ws · L4: ch", now just "decay applied {ts}"), Research & Diagnostics intro div removed.
- **v0.6.50**: removed R3e POP entry from Discarded (POP is live in L3, was contradictory).
- **v0.6.46–v0.6.49** (earlier today): R0 audit table, R2 state-stratified promoted to live, Fitter cadence 4×→2×/day, dead-hypothesis gating with `RUN_TIDE_TRACKING = False`, POP re-added to L3 with `L3_BRIER_FIELDS = {"pp"}` exception.

## Primary next-session task

**Extend L2 station-network bias to fields that currently pass through.**

Context: the v0.6.44 L2 lead-decay fit (`analysis/l2_lead_decay_fit.py`) only covered t/h/pr because those are the only fields with an additive-bias term in `hyperlocal.py` / `corrected_hourly.py`. dp/cc/sr/cl/cm/ch/pp/pa pass through L2 untouched. Joe asked "why not do the work to fit those?" — answer: there's no bias term to apply a τ multiplier to; you have to build the bias term first.

Field-by-field viability:

- **dp (dew point)**: derived from corrected_t + corrected_h via Magnus. No separate bias needed — inherits t/h fits. **Skip.**
- **sr (solar radiation)**: a handful of WU stations have pyranometers. R2 state-stratified flagged Solar × flow regime as the #1 opportunity (120 W/m² spread between regime bins), so highest-value field to chase. But probably needs the regime-conditional L5 path, not L2 additive. **Investigate first** — count how many of the 81 active stations report `solar_radiation`. If <5, not worth L2 build; defer to L5 work.
- **pa (precip amount)**: many WU stations have rain gauges. Spatial averaging is tricky (0.3" at one station / 0.0" at another isn't bias, it's the precip pattern). **Possible but design-heavy** — would need a different aggregation than octant signed-mean.
- **cc, cl, cm, ch (clouds)**: WU PWS don't have ceilometers. Only KBVY ASOS reports sky; one station ≠ a network. **Skip.**
- **pp (POP)**: probability, not measurable per-station. **Skip.**
- **ws, wg (wind, gust)**: not really "the others." Have L2 today via direct-selection with a hardcoded linear 0–24h blend, not additive bias. `decay_fit.py`'s `L2_TAU_FIELDS = ("t", "h", "pr", "ws", "wg")` suggests intent to fit them; the τ result for ws/wg is computed but unused. **Consider** switching wind L2 from direct-selection to additive bias to consume the fitted τ — architectural change, separate question.

**Suggested order to discuss tomorrow:**
1. **sr station coverage check** — single grep on a recent `weather_data.json` to count stations publishing solar. If too few, dismiss L2 path; sr signal goes through R2 / future L5 instead.
2. **ws/wg additive-bias question** — read what `decay_fit.py` is producing for ws/wg τ today (it's computed but not consumed). If the fit lands near linear-24h, the hardcoded ramp is fine; if it diverges, there's signal being thrown away. Compare against held-out MAE.
3. **pa** — only after the easier wins are decided. Lowest priority because aggregation design is non-trivial.

## Date-triggered watching tasks (no immediate action)

- **~2026-06-11**: check GCP bill, confirm v0.6.47 cost trim bent the trajectory down (was 615% MoM jump).
- **~2026-06-15**: R0 audit table becomes trustworthy (30-day rolling window starts including post-v0.6.45 pairs). Scan for ⚠ flags on enabled layers.
- **~2026-06-22**: R0 + R2 magnitudes confirmation with post-v0.6.44 data. If Solar × flow regime spread holds at ~120 W/m², green-light Phase 1 (L5 regime correction, append-style not insert).
- **~2026-06-22**: re-run `analysis/derived_humidity.py` with post-L2-fix data. Moderate concern the hypothesis was discarded too soon.

## Stale memory to revisit

- `project_layer34_watch.md` predates v0.6.45 whitelist and v0.6.51 L2 documentation. Update or retire once R0 audit stabilizes (~2026-06-15).

## Anti-rules (from CLAUDE.md, do not violate)

- `git push`. Never `--force-with-lease`. Pipeline is GCS now, GitHub Actions does nothing.
- Repo lives at `~/Documents/myweather`. Container files are ephemeral.
- macOS `sed -i ''` (the empty string is mandatory).
- Test on localhost before pushing frontend changes (was relaxed today only because Joe explicitly said "push it" on a small read-only-style documentation change).
- Joe's questions are usually probing, not disagreement — hold position under questioning unless new info arrives. Documented capitulation failure mode.
- One terminal command at a time when expecting output back.
- Don't suggest `make run-collector` when next scheduled run is within 10 min.
