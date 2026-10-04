---
name: pair-log-error-field
description: "SUPERSEDED by [[feedback_top_level_forecast_is_l2]] on 2026-08-03. The unsuffixed `error` field is L2 residual, NOT production. Kept for the raw-baseline-vs-`error` warning at the bottom, which is still correct in its own right (use `error_l1` when the intent is raw HRRR)."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 434af779-9797-4cea-bd88-1e0939ffeef0
  modified: 2026-08-17T12:04:42.449Z
---

**SUPERSEDED 2026-08-03 by [[feedback_top_level_forecast_is_l2]].** This memo said `error` = production residual. That was wrong (or became wrong when snapshot's backward-compat convention was clarified). Reality: top-level `forecast` = L2 value by design; `error` = L2 residual. Real production must be reconstructed from `error_{applied_layer}` via `analysis/_prod.py::prod_error`. On 2026-08-17 a sweep converted 20 analysis scripts to the correct pattern; this old memo misled the morning triage that opened that session.

Kept because the "use `error_l1` when the baseline is raw HRRR" advice below is still correct in its own right. Read this note as: L2 residual, not production residual, not L1 residual — three different things. If you're testing a proposed correction, pick the right baseline explicitly.

---

## Original text (WRONG about `error` semantics; kept for the raw-baseline warning)

The pair log's unsuffixed `error` field is production residual, not L1 raw residual.

**Why:** From `weather_collector/processors/forecast_error_log.py:229`:
```
"error": round(forecast - obs_f, 3),
```
where `forecast` is `target_hour.get(short)` — the top-level applied value the user actually sees. That's PRODUCTION.

Per-layer errors ARE explicitly suffixed: `error_l1`, `error_l2`, `error_l3`, `error_l4`, `error_l5`, `error_l6`, `error_chp`, `error_clp`, `error_wdp` (set at forecast_error_log.py:252).

**How to apply:**
- For walk-forward decay-fit tests where the baseline is meant to be raw HRRR: use `error_l1`.
- For a walk-forward test where the baseline is what production shipped: use `error`.
- Confusion between the two silently changes the question being asked. Symptom: "all τs hurt vs baseline" when actually the corrections you're testing are being applied ON TOP of production's existing corrections.

**How I hit it (2026-07-31):** wrote `h_h_dp_tau_refit.py` v1 with `err = row.get("error")`. Got puzzling result — every τ made things worse. Joe pushed back correctly. Switched to `error_l1`. Fresh (correct) result changed the conclusion. See [[project_07_31_session]] for full sequence.

**Referenceable check:** any walk-forward decay-fit script cloned from `decay_tau_tuning.py` — that script uses `error` (which is production residual). If cloning for L4 fit vs raw, swap to `error_l1`. If cloning for L4 fit vs current production, `error` is right — but say so explicitly in the docstring.

## Related

- [[project_07_31_session]] — the session log
- [[project_h_l2_shape_retune]] — the investigation this trap slowed down
- [[feedback_verify_writers_for_read_paths]] — same class of failure
