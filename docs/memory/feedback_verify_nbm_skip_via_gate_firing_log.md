---
name: feedback-verify-nbm-skip-via-gate-firing-log
description: "Verify NBM skip-table cells with gate_firing_log.jsonl (per-tick runtime regime + fires/skips per field), not the pair log. The NBM skip keys on the tick-level regime, which the pair log doesn't store; state_fc- or state_obs-keyed checks give false failures."
metadata:
  node_type: memory
  type: feedback
  modified: 2026-10-07T14:30:00.000Z
---

# Rule

To check that an NBM skip-table cell (`skip_table_nbm_curated.json`) actually fires, read
`https://data.wymancove.com/gate_firing_log.jsonl`: records with `operator = "L3_NBM"` (or L4_NBM, …)
carry the runtime `regime` for that tick and `by_field[f] = {fires, skips}`. A skipped regime × band
shows up as skips covering that band's leads on ticks with that regime.

Do NOT verify via the pair log's `applied_layer` keyed on `state_fc.regime_synoptic` or a regime
rebuilt from `state_obs`.

## Why

2026-10-07: `forecast_snapshot.py` calls `_should_skip_nbm(f, layer, _wdp_state_curr, i)`, and
`_wdp_state_curr = derived.state.regime_synoptic`, ONE regime per tick for all 48 leads. The pair log
has no field for it. Keyed on `state_fc`, the v0.7.24 cells showed zero post-deploy rows. Rebuilt from
`state_obs` at obs_time == run_time, cells skipped for weeks showed `l3_nbm` on ~half their rows, in
whole-run blocks, which is regime disagreement, not skip failure. `gate_firing_log` showed the truth in
one read: the 10-07 08:58 se_flow tick had wd fires 0 / skips 46 (new se_flow/24-47 cell firing).

## How to apply

- Any "verify skip cell X took effect": filter `gate_firing_log` to the operator, ticks after the deploy,
  `regime == X.regime`; compare skips to the cell's lead count. If no tick had that regime, the cell is
  **untested** (weather-pending), not failing.
- Same trap class as `lead_h` vs `lead_hours` and the `state_fc` regime key: a wrong key returns
  nothing and reads as evidence.

Related: [[project_10_07_session]] · [[feedback_shipped_flag_verify_effect]] · [[feedback_pair_log_error_field]]
