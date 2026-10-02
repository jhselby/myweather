"""v0.7.6 L1 static blender — shadow-verify.

Distinct from `l1_blender_shadow_verify.py`, which scores the v0.7.0 terminal
blender (`{f}_blend_shadow` stamp, `forecast_blend`, per-cell ω̄). This one
scores the v0.7.6 L1-seat static blender (`{f}_l1_blend_shadow` stamp,
universal ω per field, bypass-cascade). See project_l1_static_blend_v076.

Reads:
  - pair log (forecast_error_log_backstamped.jsonl via _cache) for rows
    carrying `{f}_l1_blend_shadow` on covered (field, regime, band) cells.
  - curated table (weather_collector/data/l1_static_blend_curated.json)
    for the universal ω per field and covered cell list.

Per curated cell, over rolling 7d and 30d windows:
  n            — rows where the shadow stamp fired for this cell
  served_MAE   — MAE of the served forecast (pair['error']) = current
                 production stack (cascade+selector). ω=0 baseline.
  blend_MAE    — MAE of the L1-blend shadow forecast vs observed.
  l1_MAE       — HRRR-side raw L1 baseline (ω=1 endpoint).
  raw_nbm_MAE  — NBM-side raw baseline (ω=0 endpoint of the blend, not served).
  lift_vs_served_pct — 100 · (served_MAE − blend_MAE) / served_MAE
  halves_A / halves_B — chronological split of the 7d window; each reports
                 its own served/blend/lift so we can require BOTH halves
                 stable before flipping ENABLED (the same discipline that
                 caught the 09-24 stale-fit incident).

Per-cell verdict:
  SHIP-READY — n7 ≥ MIN_N_7D, both halves lift ≥ MIN_LIFT_PCT (halves-stable),
               7d overall lift ≥ MIN_LIFT_PCT
  HOLD       — cleared 7d lift but one half fails, or n insufficient, or
               lift positive but below floor
  KILL       — 7d lift ≤ NEG_KILL_PCT AND n7 ≥ MIN_N_7D (blend hurts)
  THIN       — n7 == 0

Per-field rollup:
  reports SHIP-READY count / covered-cells count. v0.7.7 flip-decision is
  human — a strong field-rollup here (e.g. 8/10 SHIP-READY) is the signal.

Run:
    python3 analysis/l1_static_blend_shadow_verify.py
Emits:
    analysis/output/l1_static_blend_shadow_verify.txt
    analysis/output/l1_static_blend_shadow_verify.json
    (uploads to gs://myweather-data/l1_static_blend_shadow_verify.json)
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CURATED_PATH = REPO / "weather_collector" / "data" / "l1_static_blend_curated.json"
# The shadow stamp writes `forecast_l1` and `forecast_raw_nbm` inline on the
# same row as `l1_blend_shadow`, so no NBM backstamp is required — use the
# fresh local raw pair-log directly. (The GCS backstamped log is behind by
# several days as of 2026-09-27; see project_backstamp_stale_09_24.)
RAW_PAIR_LOG = Path.home() / ".cache" / "myweather" / "forecast_error_log.jsonl"
OUT_TXT = HERE / "output" / "l1_static_blend_shadow_verify.txt"
OUT_JSON = HERE / "output" / "l1_static_blend_shadow_verify.json"

# Pair-log emits the shadow stamp WITHOUT the `{field}_` prefix on
# per-field rows (forecast_snapshot writes `entry[f"{f}_l1_blend_shadow"]`
# but the per-field row-writer strips the field prefix). Grep the pair
# log for the literal key `l1_blend_shadow` to confirm.
SHADOW_STAMP_KEY = "l1_blend_shadow"

BANDS = [("0-5", 0, 6), ("6-11", 6, 12), ("12-23", 12, 24), ("24-47", 24, 48)]

# Verdict thresholds. Match the fit-time gate (5% MAE lift) but drop the
# min_n from the fit's 400 rows/cell — 7d live pair-log is a fraction of
# that. Set the floor at 100 rows/cell/7d and keep 5% as the stability bar.
MIN_N_7D = 100
MIN_LIFT_PCT = 5.0
NEG_KILL_PCT = -3.0


def _band_for(lead_h):
    for name, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return name
    return None


def load_curated():
    """Return {field: {'omega': float, 'cells': set((regime, band))}}."""
    with open(CURATED_PATH) as fh:
        data = json.load(fh)
    fields = data.get("fields") or {}
    out = {}
    for f, spec in fields.items():
        omega = spec.get("omega")
        cells = spec.get("cells") or []
        if omega is None or not cells:
            continue
        out[f] = {
            "omega": float(omega),
            "cells": set((c[0], c[1]) for c in cells if len(c) == 2),
        }
    return out


def parse_time(ts):
    if not ts:
        return None
    ts = ts.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(ts[:19], fmt)
        except ValueError:
            continue
    return None


def scan_pair_log(curated):
    """Yield (field, regime, band, obs_time, row) tuples for shadow-stamped rows.

    Buckets by the (regime, band) recorded in the pair-log's state_fc — this
    is what a retro-score would see, and matches what the mae_over_time and
    scorecard pipelines already use. NOTE: forecast_snapshot passes its own
    per-lead regime to blend_l1 for the stamp decision, which may differ
    from the state_stamp regime later written to the row; that means some
    stamped rows land in cells NOT in the curated table. Scoring them
    anyway is the honest read of "when the runtime applied blend, did it
    beat served?" — an ENABLED=True flip would carry the same drift.
    """
    covered_fields = set(curated.keys())
    if not RAW_PAIR_LOG.exists():
        print(f"pair log not found at {RAW_PAIR_LOG} — nothing to verify", file=sys.stderr)
        return
    with open(RAW_PAIR_LOG) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            fld = r.get("field")
            if fld not in covered_fields:
                continue
            if SHADOW_STAMP_KEY not in r:
                continue
            lh = r.get("lead_h")
            if lh is None:
                continue
            band = _band_for(int(lh))
            if band is None:
                continue
            regime = (r.get("state_fc") or {}).get("regime_synoptic")
            if regime is None:
                continue
            key = (fld, regime, band)
            obs_t = parse_time(r.get("obs_time")) or parse_time(r.get("valid_time"))
            if obs_t is None:
                continue
            yield key, obs_t, r


def _abs_err(fc, obs):
    if fc is None or obs is None:
        return None
    try:
        return abs(float(fc) - float(obs))
    except (TypeError, ValueError):
        return None


def mean(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return sum(xs) / len(xs)


# v0.7.21 — runtime source-depth chains, mirroring forecast_snapshot's
# "deepest available NBM layer wins" apply block. Used ONLY to rebuild the
# served counterfactual on rows where the blend actually applied.
_NBM_CHAIN = {
    "wd": ("wdp_nbm", "l3_nbm", "l2_nbm", "raw_nbm"),
    "ch": ("chp_nbm", "l4_nbm", "l3_nbm", "l2_nbm", "raw_nbm"),
    "t":  ("l6_nbm", "l2_nbm", "raw_nbm"),
    "sr": ("l5_nbm", "l2_nbm", "raw_nbm"),
    "cc": ("l4_nbm", "l3_nbm", "l2_nbm", "raw_nbm"),
    "wg": ("l3_nbm", "l2_nbm", "raw_nbm"),
    "h":  ("l3_nbm", "l2_nbm", "raw_nbm"),
    "dp": ("l2_nbm", "raw_nbm"),
    "ws": ("l2_nbm", "raw_nbm"),
}
_HRRR_CHAIN = ("l6", "l4", "l3", "l2", "l1")


def counterfactual_served_err(r, field):
    """|error| of what WOULD have been served had the blend not applied.

    Once a cell is live (v0.7.20 flipped h/nw_flow/24-47), row['error'] IS
    the blend's own error — every shadow-stamped row in that cell is also an
    applied row, so scoring blend vs row['error'] compares the blend against
    itself and yields exactly 0% lift. A SHIP-READY cell would silently read
    HOLD the day after it shipped.

    The honest baseline is the layer the selector would have served, which
    v0.7.21 preserves as `preempted_source_shadow`. Returns None when that
    stamp is absent (any applied row logged before v0.7.21) so the caller can
    exclude the row rather than mis-score it.
    """
    pre = r.get("preempted_source_shadow")
    if not pre:
        return None
    # "nws" is not wire-eligible for h/dp (_NWS_FIELDS_WIRE_ELIGIBLE is
    # t/ws/wd/pp), so anything that isn't an NBM pick served the HRRR side.
    chain = _NBM_CHAIN.get(field, ("l2_nbm", "raw_nbm")) if pre == "nbm" else _HRRR_CHAIN
    for lyr in chain:
        e = r.get(f"error_{lyr}")
        if e is None:
            continue
        try:
            return abs(float(e))
        except (TypeError, ValueError):
            continue
    return None


def score(rows, field):
    """Return per-window stats for a bag of rows in one cell.

    served_mae   — the served baseline. For rows where the blend did NOT
                   apply this is row['error'] (cascade+selector output). For
                   rows where it DID apply, row['error'] is the blend itself,
                   so the counterfactual is rebuilt from the pre-empted
                   source instead. See counterfactual_served_err.
    blend_mae    — |{f}_l1_blend_shadow − observed|
    l1_mae       — |forecast_l1 − observed|
    raw_nbm_mae  — |forecast_raw_nbm − observed|

    Applied rows with no reconstructable counterfactual are dropped from the
    cell entirely (not just from served_mae) so all four series keep the same
    population; the count surfaces as n_excluded_no_counterfactual.
    """
    if not rows:
        return {"n": 0}
    stamp_key = SHADOW_STAMP_KEY
    served_errs = []
    blend_errs = []
    l1_errs = []
    nbm_errs = []
    n_scored = 0
    n_applied = 0
    n_excluded = 0
    for r in rows:
        obs = r.get("observed")
        if r.get("applied_layer") == "l1_blend":
            n_applied += 1
            served_e = counterfactual_served_err(r, field)
            if served_e is None:
                n_excluded += 1
                continue
        else:
            served_e = r.get("error")
            if served_e is not None:
                try:
                    served_e = abs(float(served_e))
                except (TypeError, ValueError):
                    served_e = None
        n_scored += 1
        if served_e is not None:
            served_errs.append(served_e)
        b = _abs_err(r.get(stamp_key), obs)
        if b is not None:
            blend_errs.append(b)
        l = _abs_err(r.get("forecast_l1"), obs)
        if l is not None:
            l1_errs.append(l)
        n = _abs_err(r.get("forecast_raw_nbm"), obs)
        if n is not None:
            nbm_errs.append(n)
    served_mae = mean(served_errs)
    blend_mae = mean(blend_errs)
    l1_mae = mean(l1_errs)
    nbm_mae = mean(nbm_errs)
    lift = None
    if served_mae and served_mae > 0 and blend_mae is not None:
        lift = 100.0 * (served_mae - blend_mae) / served_mae
    return {
        "n": n_scored,
        "n_applied_rows": n_applied,
        "n_excluded_no_counterfactual": n_excluded,
        "served_baseline": "counterfactual" if n_applied else "served",
        "served_mae": served_mae,
        "blend_mae": blend_mae,
        "l1_mae": l1_mae,
        "raw_nbm_mae": nbm_mae,
        "lift_vs_served_pct": lift,
    }


def halves_split(rows_sorted):
    """Chronological A/B halves — earliest half first, latest half second."""
    if len(rows_sorted) < 2:
        return [], []
    mid = len(rows_sorted) // 2
    return rows_sorted[:mid], rows_sorted[mid:]


def verdict_for(s7, half_a, half_b):
    n = s7.get("n", 0)
    lift = s7.get("lift_vs_served_pct")
    if n == 0:
        return "THIN"
    if lift is not None and lift <= NEG_KILL_PCT and n >= MIN_N_7D:
        return "KILL"
    if n < MIN_N_7D:
        return "HOLD"
    if lift is None or lift < MIN_LIFT_PCT:
        return "HOLD"
    la = half_a.get("lift_vs_served_pct")
    lb = half_b.get("lift_vs_served_pct")
    if la is None or lb is None:
        return "HOLD"
    if la < MIN_LIFT_PCT or lb < MIN_LIFT_PCT:
        return "HOLD"
    return "SHIP-READY"


def main():
    curated = load_curated()
    if not curated:
        print("no curated cells — nothing to verify")
        return
    total_cells = sum(len(spec["cells"]) for spec in curated.values())
    print(f"Loaded curated table: {len(curated)} field(s), {total_cells} cell(s).")
    for f, spec in curated.items():
        print(f"  {f}: ω={spec['omega']:.2f}  cells={len(spec['cells'])}")

    now = datetime.utcnow()
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)
    by_cell_7d = defaultdict(list)
    by_cell_30d = defaultdict(list)
    times_7d = defaultdict(list)

    n_scanned = 0
    for key, obs_t, row in scan_pair_log(curated):
        n_scanned += 1
        if obs_t >= cutoff_30d:
            by_cell_30d[key].append(row)
            if obs_t >= cutoff_7d:
                by_cell_7d[key].append(row)
                times_7d[key].append(obs_t)

    n7_total = sum(len(v) for v in by_cell_7d.values())
    n30_total = sum(len(v) for v in by_cell_30d.values())
    print(f"Scanned {n_scanned:,} l1_blend_shadow-stamped rows total; "
          f"{n7_total:,} in last 7d, {n30_total:,} in last 30d.")

    out_rows = []
    header = (f"{'field':<5}{'regime':<14}{'band':<8}"
              f"{'n7':>5}{'n30':>7}  "
              f"{'served':>8}{'blend':>8}{'l1':>7}{'nbm':>7}{'lift%':>8}  "
              f"{'A_lift':>8}{'B_lift':>8}  verdict")
    print("\n" + "=" * len(header))
    print(header)
    print("-" * len(header))

    tally = {"SHIP-READY": 0, "HOLD": 0, "KILL": 0, "THIN": 0}
    tally_curated = {"SHIP-READY": 0, "HOLD": 0, "KILL": 0, "THIN": 0}
    tally_offcurated = {"SHIP-READY": 0, "HOLD": 0, "KILL": 0, "THIN": 0}
    field_tally = defaultdict(lambda: {"SHIP-READY": 0, "HOLD": 0, "KILL": 0, "THIN": 0})

    # Report every cell that either (a) has stamped rows in the last 30d
    # OR (b) is in the curated table (so a THIN row is visible even if
    # its regime never occurred in the window).
    curated_keys = set()
    for f, spec in curated.items():
        for (r, b) in spec["cells"]:
            curated_keys.add((f, r, b))
    seen_keys = set(by_cell_30d.keys()) | set(by_cell_7d.keys()) | curated_keys

    off_table_hits = 0
    for key in sorted(seen_keys):
        field, regime, band = key
        rows7 = by_cell_7d.get(key, [])
        rows30 = by_cell_30d.get(key, [])
        paired = sorted(zip(times_7d.get(key, []), rows7), key=lambda t: t[0])
        rows7_sorted = [r for _, r in paired]
        s7 = score(rows7_sorted, field)
        s30 = score(rows30, field)
        a_rows, b_rows = halves_split(rows7_sorted)
        sA = score(a_rows, field)
        sB = score(b_rows, field)
        v = verdict_for(s7, sA, sB)
        tally[v] += 1
        if key in curated_keys:
            tally_curated[v] += 1
        else:
            tally_offcurated[v] += 1
        field_tally[field][v] += 1
        curated_mark = "" if key in curated_keys else " *"
        if key not in curated_keys and s7.get("n", 0) > 0:
            off_table_hits += 1
        print(f"{field:<5}{regime:<14}{band:<8}"
              f"{s7.get('n',0):>5}{s30.get('n',0):>7}  "
              f"{(s7.get('served_mae') or 0):>8.3f}"
              f"{(s7.get('blend_mae') or 0):>8.3f}"
              f"{(s7.get('l1_mae') or 0):>7.3f}"
              f"{(s7.get('raw_nbm_mae') or 0):>7.3f}"
              f"{(s7.get('lift_vs_served_pct') or 0):>+8.2f}  "
              f"{(sA.get('lift_vs_served_pct') or 0):>+8.2f}"
              f"{(sB.get('lift_vs_served_pct') or 0):>+8.2f}  "
              f"{v}{curated_mark}")
        out_rows.append({
            "field": field, "regime": regime, "band": band,
            "verdict": v,
            "in_curated_table": key in curated_keys,
            "omega": curated[field]["omega"],
            "n_7d": s7.get("n"), "n_30d": s30.get("n"),
            "served_mae_7d": s7.get("served_mae"),
            "blend_mae_7d": s7.get("blend_mae"),
            "l1_mae_7d": s7.get("l1_mae"),
            "raw_nbm_mae_7d": s7.get("raw_nbm_mae"),
            "lift_vs_served_pct_7d": s7.get("lift_vs_served_pct"),
            "lift_vs_served_pct_30d": s30.get("lift_vs_served_pct"),
            "halves_A_lift_pct": sA.get("lift_vs_served_pct"),
            "halves_B_lift_pct": sB.get("lift_vs_served_pct"),
            "halves_A_n": sA.get("n"),
            "halves_B_n": sB.get("n"),
            # v0.7.21 — provenance of the served baseline. "counterfactual"
            # means this cell has live applied rows whose served value IS the
            # blend, so the baseline was rebuilt from preempted_source_shadow
            # rather than read off row['error'].
            "served_baseline_7d": s7.get("served_baseline"),
            "n_applied_rows_7d": s7.get("n_applied_rows"),
            "n_excluded_no_counterfactual_7d": s7.get("n_excluded_no_counterfactual"),
        })

    print("=" * len(header))
    _applied_cells = [r for r in out_rows if (r.get("n_applied_rows_7d") or 0) > 0]
    if _applied_cells:
        print("  v0.7.21 live-apply cells — served baseline is the rebuilt "
              "counterfactual, not row['error']:")
        for r in _applied_cells:
            print(f"    {r['field']}/{r['regime']}/{r['band']}: "
                  f"{r['n_applied_rows_7d']} applied row(s), "
                  f"{r['n_excluded_no_counterfactual_7d']} excluded "
                  f"(no preempted_source_shadow — logged pre-v0.7.21)")
    if off_table_hits:
        print(f"  (* = cell has stamped rows but is NOT in curated table — "
              f"forecast_snapshot's runtime regime differs from state_stamp's; "
              f"{off_table_hits} such cells)")
    print()
    print("Per-field rollup:")
    for f in sorted(field_tally.keys()):
        ft = field_tally[f]
        total_f = sum(ft.values())
        print(f"  {f}: {ft['SHIP-READY']}/{total_f} SHIP-READY  "
              f"({ft['HOLD']} hold, {ft['KILL']} kill, {ft['THIN']} thin)")
    print()
    tc = tally_curated; to = tally_offcurated
    n_off = sum(to.values())
    summary_curated = (f"Verdict (curated cells, n={total_cells}): "
                       f"{tc['SHIP-READY']} SHIP-READY / {tc['HOLD']} HOLD / "
                       f"{tc['KILL']} KILL / {tc['THIN']} THIN")
    summary_off = (f"Verdict (off-curated stamped, n={n_off}): "
                   f"{to['SHIP-READY']} SHIP-READY / {to['HOLD']} HOLD / "
                   f"{to['KILL']} KILL / {to['THIN']} THIN"
                   f"  (regime disagreement or new-regime carve-outs)")
    summary = summary_curated
    print(summary_curated)
    if n_off:
        print(summary_off)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_n_7d": MIN_N_7D,
        "min_lift_pct": MIN_LIFT_PCT,
        "neg_kill_pct": NEG_KILL_PCT,
        "field_omega": {f: spec["omega"] for f, spec in curated.items()},
        "tally": tally,
        "tally_curated": tally_curated,
        "tally_offcurated": tally_offcurated,
        "per_field_tally": dict(field_tally),
        "cells": out_rows,
        "n_scanned": n_scanned,
        "n_7d_total": n7_total,
        "n_30d_total": n30_total,
        "off_curated_table_hits": off_table_hits,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2)
    with open(OUT_TXT, "w") as fh:
        fh.write(summary + "\n")
        for f in sorted(field_tally.keys()):
            ft = field_tally[f]
            total_f = sum(ft.values())
            fh.write(f"  {f}: {ft['SHIP-READY']}/{total_f} SHIP-READY  "
                     f"({ft['HOLD']} hold, {ft['KILL']} kill, {ft['THIN']} thin)\n")
        fh.write(f"Scanned {n_scanned} l1_blend_shadow rows total\n")
    print(f"\nwrote {OUT_JSON}")
    print(f"wrote {OUT_TXT}")

    try:
        from weather_collector.gcs_io import upload_json  # noqa: E402
        upload_json(payload,
                    "l1_static_blend_shadow_verify.json",
                    "l1_static_blend_shadow_verify.json")
        print("  ✓ Published to gs://myweather-data/l1_static_blend_shadow_verify.json")
    except Exception as e:
        print(f"  ⚠ GCS upload skipped ({type(e).__name__}: {e}) — local file still written")


if __name__ == "__main__":
    main()
