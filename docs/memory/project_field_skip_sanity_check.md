---
name: field-skip-sanity-check
description: IMPLEMENTED — digest diagnostic for _FIELD_SKIP fields whose prod_real diverges from raw. Lives at build_executive_summary.py:770. cc exempt (Ccd-derived); cl reads clean at -1.4% (below 5% threshold).
metadata: 
  node_type: memory
  type: project
  originSessionId: 8936b8c9-2577-4ecc-9d6b-6658da634b60
  modified: 2026-08-09T14:14:59.137Z
---

**Status: IMPLEMENTED and clean (verified 2026-08-09 during audit chunk 2).**

Lives at `analysis/runlog/build_executive_summary.py:770` (`field_skip_sanity_check()`). Constants at lines 766-767:
- `FIELD_SKIP_DIVERGENCE_PCT = 5.0`
- `FIELD_SKIP_DERIVED_EXEMPT = frozenset({"cc"})` — cc is Ccd-derived, prod ≠ raw by design

Current `_FIELD_SKIP = {"cc", "cl"}` in `weather_collector/processors/cloud_saturation_correction.py:61`.

**08-09 sanity read on trailing 7d (from live `mae_over_time.json`):**
- cc: -37.7% divergence → EXEMPT (Ccd composition legit)
- cl: -1.4% divergence → CLEAN (below 5% threshold; consistent with L2 hourly[0] blend at lead 0 being cl's only correction)

**Original motivation preserved:** 08-01 v0.6.390j fix — clp shadow was stamped as applied_layer for cl for 5 days (07-27 → 08-01) while cl was `_FIELD_SKIP`'d on Lc. This check catches that bug class on day 1.

Related: [[feedback_shadow_write_applied_layer_trap]], [[project_wd_applied_layer_stamp_fix]].
