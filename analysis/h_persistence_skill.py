"""Phase 2 — Persistence skill baseline for the correction stack.

The industry-standard reference forecast for short-lead weather is
"persistence": the observation at run_time IS the forecast for every
lead. If the pipeline can't beat persistence at short leads, it's not
actually adding value — it's just wrapping noise around a stronger
baseline. NWS and ECMWF publish skill scores against persistence
(and climatology) as first-order sanity checks; MyWeather has never
had one before today.

The question this answers per field per lead:
  "Does the pipeline beat 'same as now'?"

Method:
  Persistence forecast for a pair row (run_time=R, valid_time=V, lead=L,
  observed=Ob(V)) is Ob(R). Ob(R) is the *observed* value at run_time.
  We reconstruct it from the pair log itself: any pair row with
  valid_time=R gives us Ob(R), regardless of which lead produced it.

  Build a per-field index {valid_time -> observed}. Then for every pair
  row, look up persistence_forecast = index[field][run_time]. Score it
  against actual Ob(V). Accumulate MAE + RMSE per (field, lead_band)
  for persistence, L1 (raw HRRR), and L4 (post-stack, Production proxy
  for the 10 non-specialist fields — sr and t differ from Production
  by their specialist correction; note in verdict).

Skill score:
  skill = 1 - pipeline_MAE / persistence_MAE
    > 0  → pipeline beats persistence (adding value)
    = 0  → tied
    < 0  → persistence wins (pipeline is worse than "same as now")

  Same formula on RMSE.

Verdict per (field, band):
  ★ ADDS VALUE      skill ≥ +0.10 on both MAE AND RMSE
  ⚠ MARGINAL        skill 0 to +0.10
  ★ BEHIND          skill < 0 → persistence beats pipeline

Overall verdict per field (all leads pooled):
  ★ ADDS VALUE   ≥3 of 4 bands ADDS VALUE, none BEHIND
  ⚠ MIXED        1-2 bands ADDS VALUE OR any BEHIND
  ★ NO SKILL     0 bands ADDS VALUE

Design notes:
  - wd (wind direction) excluded — circular metric; skill score formula
    only makes sense for scalar fields.
  - Uses forecast_l4 as pipeline proxy. For sr and t, actual Production
    includes Lsr / Lt specialist corrections applied after L4; both
    specialists are documented in memory as regime-conditional. Report
    L4 numbers with a note.
  - Skip lead=0 (persistence is trivially perfect at lead=0).
  - Match scorecard band definitions: 0-5h / 6-11h / 12-23h / 24-47h.
    "0-5h" band excludes lead=0.
"""
import os, sys, json, math
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "output", "h_persistence_skill_summary.txt")
OUT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "output", "h_persistence_skill.json")

FIELDS = ["t", "dp", "h", "pr", "ws", "wg", "cc", "cl", "cm", "ch", "sr", "pp"]
BANDS = [(1, 6, "0-5h"), (6, 12, "6-11h"), (12, 24, "12-23h"), (24, 48, "24-47h")]
MIN_N_PER_CELL = 200


def band_of(lead):
    for lo, hi, lab in BANDS:
        if lo <= lead < hi:
            return lab
    return None


def hour_floor(ts):
    """'2026-06-11T03:17' -> '2026-06-11T03:00'. Pair-log valid_times are
    on-the-hour; run_times are :07/:17/:27... 10-min-offset. Floor for
    obs-index lookup."""
    if ts is None or len(ts) < 16:
        return None
    return ts[:14] + "00"


def compute():
    path = cached_path(URL)

    # Pass 1: build per-field {valid_time -> observed} index.
    # Multiple pair rows can share the same (field, valid_time) — they
    # all agree on the obs (obs is obs; different leads' forecasts vary,
    # but obs at a given moment is one value). Take the first-seen.
    print("[1/3] Building obs index from pair log...", file=sys.stderr)
    obs_ts = defaultdict(dict)
    n_rows = 0
    with open(path, "rb") as fh:
        for raw in fh:
            n_rows += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            f = r.get("field")
            if f not in FIELDS:
                continue
            vt = r.get("valid_time")
            ob = r.get("observed")
            if vt is None or ob is None:
                continue
            if vt not in obs_ts[f]:
                obs_ts[f][vt] = ob
    print(f"    scanned {n_rows:,} pair rows; obs index sizes: "
          + ", ".join(f"{f}={len(obs_ts[f]):,}" for f in FIELDS),
          file=sys.stderr)

    # Pass 2: score each pair row against persistence + L1 + L4.
    print("[2/3] Scoring pair rows vs persistence baseline...", file=sys.stderr)
    # accum[(field, band)] = dict of counters
    accum = defaultdict(lambda: {"n": 0,
                                 "ae_pers": 0.0, "se_pers": 0.0,
                                 "ae_l1": 0.0,   "se_l1": 0.0,
                                 "ae_l4": 0.0,   "se_l4": 0.0})
    n_joined = 0
    n_orphan = 0
    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            f = r.get("field")
            if f not in FIELDS:
                continue
            lead = r.get("lead_h")
            if lead is None:
                continue
            try:
                lead = int(lead)
            except Exception:
                continue
            if lead <= 0 or lead > 47:
                continue
            band = band_of(lead)
            if band is None:
                continue
            rt = r.get("run_time")
            ob = r.get("observed")
            fc1 = r.get("forecast_l1")
            fc4 = r.get("forecast_l4")
            if rt is None or ob is None or fc1 is None or fc4 is None:
                continue
            persist = obs_ts[f].get(hour_floor(rt))
            if persist is None:
                n_orphan += 1
                continue
            n_joined += 1
            a = accum[(f, band)]
            a["n"] += 1
            e_p = persist - ob
            e_1 = fc1 - ob
            e_4 = fc4 - ob
            a["ae_pers"] += abs(e_p)
            a["se_pers"] += e_p * e_p
            a["ae_l1"]   += abs(e_1)
            a["se_l1"]   += e_1 * e_1
            a["ae_l4"]   += abs(e_4)
            a["se_l4"]   += e_4 * e_4

    print(f"    joined {n_joined:,} rows to persistence baseline; "
          f"{n_orphan:,} orphans (no obs at run_time)", file=sys.stderr)

    # Pass 3: reduce + emit.
    print("[3/3] Writing outputs...", file=sys.stderr)
    per_cell = {}          # per (field, band) results
    for (f, band), a in accum.items():
        n = a["n"]
        if n < MIN_N_PER_CELL:
            continue
        mae_p = a["ae_pers"] / n
        rmse_p = math.sqrt(a["se_pers"] / n)
        mae_1 = a["ae_l1"] / n
        rmse_1 = math.sqrt(a["se_l1"] / n)
        mae_4 = a["ae_l4"] / n
        rmse_4 = math.sqrt(a["se_l4"] / n)
        skill_l1_mae = 1 - mae_1 / mae_p if mae_p > 0 else None
        skill_l1_rmse = 1 - rmse_1 / rmse_p if rmse_p > 0 else None
        skill_l4_mae = 1 - mae_4 / mae_p if mae_p > 0 else None
        skill_l4_rmse = 1 - rmse_4 / rmse_p if rmse_p > 0 else None
        per_cell[(f, band)] = {
            "n": n,
            "mae_persist": round(mae_p, 3),
            "rmse_persist": round(rmse_p, 3),
            "mae_l1": round(mae_1, 3),
            "rmse_l1": round(rmse_1, 3),
            "mae_l4": round(mae_4, 3),
            "rmse_l4": round(rmse_4, 3),
            "skill_l1_mae": round(skill_l1_mae, 3) if skill_l1_mae is not None else None,
            "skill_l1_rmse": round(skill_l1_rmse, 3) if skill_l1_rmse is not None else None,
            "skill_l4_mae": round(skill_l4_mae, 3) if skill_l4_mae is not None else None,
            "skill_l4_rmse": round(skill_l4_rmse, 3) if skill_l4_rmse is not None else None,
        }

    return per_cell


def verdict_cell(cell):
    """★ ADDS VALUE / ⚠ MARGINAL / ★ BEHIND per (field, band) based on L4 skill."""
    s_mae = cell.get("skill_l4_mae")
    s_rmse = cell.get("skill_l4_rmse")
    if s_mae is None or s_rmse is None:
        return "insufficient"
    if s_mae >= 0.10 and s_rmse >= 0.10:
        return "ADDS VALUE"
    if s_mae < 0 or s_rmse < 0:
        return "BEHIND"
    return "MARGINAL"


def verdict_field(cells_by_band):
    """★ ADDS VALUE / ⚠ MIXED / ★ NO SKILL per field across bands."""
    verdicts = [verdict_cell(c) for c in cells_by_band.values()]
    n_add = sum(1 for v in verdicts if v == "ADDS VALUE")
    n_beh = sum(1 for v in verdicts if v == "BEHIND")
    if n_add >= 3 and n_beh == 0:
        return "ADDS VALUE"
    if n_add == 0:
        return "NO SKILL"
    return "MIXED"


def emit(per_cell):
    lines = []
    lines.append("=" * 84)
    lines.append("PERSISTENCE SKILL BASELINE — pipeline (L1 raw + L4 pre-specialist) vs 'same as now'")
    lines.append("=" * 84)
    lines.append("")
    lines.append("Skill = 1 - pipeline_metric / persistence_metric.")
    lines.append("Positive skill = pipeline beats persistence.")
    lines.append("Verdict per (field, band) uses L4 skill on BOTH MAE and RMSE:")
    lines.append("  ★ ADDS VALUE  — L4 skill ≥ +0.10 on BOTH MAE and RMSE")
    lines.append("  ⚠ MARGINAL    — L4 skill 0 to +0.10")
    lines.append("  ★ BEHIND      — L4 skill < 0 (persistence beats pipeline)")
    lines.append("")
    lines.append("Note: L4 = pre-specialist stack. For sr (Lsr) and t (Lt) the actual")
    lines.append("Production differs; both specialists are regime-conditional so per-field")
    lines.append("Production skill would generally be somewhat better than L4 shown here.")
    lines.append("")

    # Per-field, per-band table
    hdr = (f"{'field':<6}{'band':<8}{'n':>10}"
           f"{'MAE_pers':>10}{'MAE_L1':>10}{'MAE_L4':>10}"
           f"{'skill_L1_MAE':>14}{'skill_L4_MAE':>14}"
           f"{'skill_L4_RMSE':>15}  verdict")
    lines.append(hdr)
    lines.append("-" * len(hdr))

    field_verdicts = {}
    for f in FIELDS:
        band_cells = {}
        for lo, hi, band in BANDS:
            cell = per_cell.get((f, band))
            if cell is None:
                continue
            band_cells[band] = cell
            v = verdict_cell(cell)
            flag = ""
            if v == "ADDS VALUE":
                flag = "★ ADDS VALUE"
            elif v == "BEHIND":
                flag = "★ BEHIND"
            elif v == "MARGINAL":
                flag = "⚠ MARGINAL"
            s1m = cell["skill_l1_mae"]
            s4m = cell["skill_l4_mae"]
            s4r = cell["skill_l4_rmse"]
            lines.append(
                f"{f:<6}{band:<8}{cell['n']:>10,}"
                f"{cell['mae_persist']:>10.3f}{cell['mae_l1']:>10.3f}{cell['mae_l4']:>10.3f}"
                f"{s1m if s1m is not None else 0:>+14.3f}"
                f"{s4m if s4m is not None else 0:>+14.3f}"
                f"{s4r if s4r is not None else 0:>+15.3f}"
                f"  {flag}"
            )
        if band_cells:
            field_verdicts[f] = verdict_field(band_cells)
            lines.append("")

    lines.append("=" * 84)
    lines.append("PER-FIELD OVERALL VERDICTS (all leads pooled by band)")
    lines.append("=" * 84)
    for f in FIELDS:
        if f in field_verdicts:
            v = field_verdicts[f]
            flag = "★" if v == "ADDS VALUE" else ("★" if v == "NO SKILL" else "⚠")
            lines.append(f"  {f:<6}  {flag} {v}")

    # Verdict line for the digest parser
    n_add = sum(1 for v in field_verdicts.values() if v == "ADDS VALUE")
    n_mix = sum(1 for v in field_verdicts.values() if v == "MIXED")
    n_no  = sum(1 for v in field_verdicts.values() if v == "NO SKILL")
    lines.append("")
    lines.append(f"Verdict: {n_add} ADDS VALUE, {n_mix} MIXED, {n_no} NO SKILL "
                 f"(of {len(field_verdicts)} fields with sufficient data).")

    return "\n".join(lines)


def main():
    per_cell = compute()
    text = emit(per_cell)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    # JSON with flat cells for downstream (scorecard consumption)
    flat = [{"field": f, "band": b, **v} for (f, b), v in per_cell.items()]
    with open(OUT_JSON, "w") as fh:
        json.dump({"cells": flat}, fh, indent=2)
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    print(f"wrote {OUT_JSON}", file=sys.stderr)


if __name__ == "__main__":
    main()
