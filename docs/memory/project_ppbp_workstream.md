---
name: project-ppbp-workstream
description: "ppbp = pp bias-persistence specialist workstream. Sibling of dpbp (LIVE) and wsbp (Stage 3 wired, HELD). Antecedent-error correction on precipitation probability. Stage 0 built + ran 2026-08-06 → PROMOTE for frontal regime only (lag-1 r=+0.434, mean_bias=−0.106pp). nw_flow persistent-but-small (r=+0.656, bias only 5pp). Stage 1 halves-verify queued but not built. Key context: pp has +43.5% BSS vs climatology (real signal) but only 1.2% Reliability = tiny calibration budget → fixed-effect corrections all HOLDing. Antecedent-error is the mechanism most likely to fit inside 1.2% without breaking on halves. Caveat: frontal is rare, ppbp fires infrequently, low-frequency correction even if it works."
metadata: 
  node_type: memory
  type: project
  originSessionId: 57d4089d-4089-4ad5-a9a4-2ee10689764d
  modified: 2026-08-06T17:32:40.354Z
---

# ppbp — pp bias-persistence specialist

## Origin story

After all fixed-effect pp corrections HOLDed (see `[[project_pp_recalibration_session]]`), thesis is that antecedent-error correction may work where fixed-effect can't. Same pattern that delivered `[[project_dpbp_live]]` LIVE 2026-08-04.

## Feasibility (Stage 0, built + run 2026-08-06)

Script: `analysis/h_pp_bias_persistence_stage0.py`

Gates: lag-1 daily bias autocorrelation r ≥ 0.35 AND |mean_daily_bias| ≥ 0.10.

Result:

| Regime | n_days | mean_bias | \|mean\| | lag-1 r | n_pairs | verdict |
|--------|--------|-----------|---------|---------|---------|---------|
| **frontal** | 18 | **−0.106** | **0.106** | **+0.434** | 11 | PROMOTE ★ |
| nw_flow | 22 | −0.052 | 0.052 | +0.656 | 16 | persistent-but-small |
| sea_breeze | 25 | −0.072 | 0.072 | +0.265 | 19 | skip |
| pre_frontal | 31 | −0.068 | 0.068 | +0.161 | 30 | skip |
| ne_flow | 17 | −0.057 | 0.057 | +0.243 | 12 | skip |
| sw_flow | 29 | −0.026 | 0.026 | +0.238 | 27 | skip |
| calm | 21 | +0.016 | 0.016 | −0.104 | 15 | skip |
| se_flow | 29 | +0.001 | 0.001 | −0.117 | 26 | skip |

**Overall verdict: PROMOTE** — frontal regime meets both gates.

Notes:
- 6 of 8 regimes show negative bias (systematic under-forecast of rain). Matches per-bin decomposition from `pp_brier_decomposition.py` (fc 24% → obs 59% at mid-probability bins).
- **frontal is where fixed-effect Platt found signal that flipped HOLD** — two independent mechanisms converge on the same regime.
- **nw_flow** would qualify if MEAN_BIAS_PROMOTE were lowered to 0.05 — worth revisiting if Stage 1 succeeds on frontal.

## Stage plan (mirror dpbp)

- **Stage 0** — feasibility check → PROMOTE for frontal. ✓ DONE 2026-08-06.
- **Stage 1** — halves-verify Brier lift on frontal. Fit trigger threshold + cap on half A, score on half B, both halves ≥ +3% Brier lift = SHIP. NOT BUILT.
- **Stage 2** — walk-forward preview. Confirms Stage 1 wasn't halves-lucky. NOT BUILT.
- **Stage 3** — wire ENABLED=False. Copy `dp_bias_persistence.py` → `pp_bias_persistence.py`. 7-day live-shadow gate. NOT BUILT.

## Design parameters (defaults to iterate on)

| Param | Default | Notes |
|---|---|---|
| `STATE_WINDOW_HOURS` | 48 | Longer than dpbp's 48 — pp obs is sparser |
| `ANTECEDENT_WINDOW_HOURS` | 24 | Bias measured over last 24h |
| `MIN_N_ANTECEDENT` | 30 | Per-regime event count needed to fire |
| `DEFAULT_TRIGGER_THRESHOLD` | 0.10 | 10 percentage points bias to fire |
| `DEFAULT_CORRECTION_CAP` | 0.20 | 20pp max correction magnitude |
| `DEFAULT_MIN_LEAD` | 6 | Skip nowcasts (0-5h) |
| `DEFAULT_FOCUS_REGIMES` | `("frontal",)` | Discovered by Stage 0 |

## Caveats worth remembering

- **Small budget**: Reliability = 0.012 pooled (1.2% of pp Brier) is the theoretical calibration ceiling. Any correction must land inside that. Antecedent-error only fires when observable persistent bias exists, so doesn't need to be right on average — only right when it fires.
- **Frontal is rare**: ppbp would only fire during frontal passages (few per week). Low-frequency correction even if it works.
- **Thin sample**: n=11 lag pairs on frontal is thin. Stage 1 will also be sample-constrained.
- **n=226 flip pattern**: `h_pp_frontal_platt_stage1` had n=292 as SHIP, dropped to n=226 as HOLD. If pair-log frontal count is drifting down, this whole workstream's data foundation is eroding — not just ppbp.

## Related

- `[[project_pp_recalibration_session]]` — 5 fixed-effect Stage 0 HOLDs + `h_pp_frontal_platt_stage1` SHIP-flipped-HOLD.
- `[[project_dpbp_live]]` — sibling specialist, template.
- `[[preflight_wsbp]]` — sibling specialist, Stage 3 wired, HELD on calm-regime data.
- `[[project_pp_brier_reliability]]` — measurement framework.
- `[[project_mrms_radar_potential]]` — alternative avenue if calibration path stalls entirely.
