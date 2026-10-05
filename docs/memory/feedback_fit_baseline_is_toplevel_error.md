---
name: feedback-fit-baseline-is-toplevel-error
description: "The v5 classifier and ims-threshold refit score picks against top-level `error` (L2 residual). For ch/cc/cl/cm, L2 == L1, so every fit-time 'lift vs served' on those fields is a lift vs RAW L1 and includes the whole L3/L4 cascade. Quote the router's honest lift vs always-HRRR (error_l4), not the fit-time number."
metadata:
  node_type: memory
  type: feedback
  modified: 2026-10-05T00:00:00.000Z
---

# Rule

Any "lift vs served" printed by a fitter that reads `err_served = r.get("error")` is a lift vs the **L2 residual**, not vs what users saw. Scripts affected (verified in code 10-04): `analysis/l1_selector_per_obs_classifier_stage1_v5.py` (`build_features`, `served_mae`) and `analysis/l1_selector_ims_threshold_refit.py` (imports `served_mae`/`build_features` from v5). Other Category-B fitters that reuse `build_features` inherit it (not individually checked).

For ch, cc, cl, cm there is no L2 correction, so L2 == L1 and the baseline is raw HRRR. The fit compares `error_l4` (HRRR cascade) / `error_l3_nbm` against raw L1, so the L3/L4 (and Lc/chp) corrections show up as "router lift".

# Why (10-04, v0.7.5 ch verdict)

Fit-time lift claimed +37% to +76% per ch cell. Live scoring on `prod_error()` split it:
- vs raw L1: +65.5% overall (cells +16.8% to +95%). Comparable to the fit-time range, because it is the same comparison.
- vs always-HRRR (`error_l4`): **+15.9%**. This is the router's own contribution.
- vs the source it did not pick: +29.8%.
Sanity check that exposed it: on HRRR-picked rows the `l2` ladder value (23.89) equalled the "served" value (23.89) to two decimals.

# How to apply

- When a fit or retro reports a lift, find its baseline column first. If it is top-level `error` / `served_mae`, restate the lift against the real counterfactual (`error_l4` for the HRRR side, or `prod_error()` for what users saw).
- For router/selector value, compare against always-HRRR and the unchosen source, not against raw L1.
- New analysis scripts: `from analysis._prod import prod_error`; never use top-level `error` as production.
- Do not re-fit the existing cells on this finding alone. The cells still beat always-HRRR in aggregate. It changes how the lift is quoted and how failing cells are judged.

Related: [[feedback_top_level_forecast_is_l2]] · [[feedback_pair_log_error_field]] · [[feedback_measure_against_live_stack_baseline]] · [[project_10_04_session]] · [[project_router_as_authority_pivot]]
