"""
Ad-hoc per-lead chp vs Lc regression re-check — booked in Calendar for
2026-07-28, deferred from 07-25 when aggregate persistence-skill Δ came
back stable at −1.03 (no escalation trigger). If tomorrow's digest moves
the aggregate Δ outside [−1.2, −0.7], this script fires as the granular
diagnosis. See [[project_chp_midlead_regression_watch]].

Method:
  1. Load pair-log ch rows post-2026-07-19 (chp ship date v0.6.358).
     Both `forecast_l6` (Lc-corrected) and `forecast_chp` must be present
     — chp attribution wiring shipped v0.6.369 07-20, so realistically
     use rows from 07-20 onward. Filter aims to isolate the live-stack
     signal (per [[feedback_measure_against_live_stack_baseline]]).
  2. For each lead 6-20h (the suspected regression band): compute MAE
     of forecast_l6 and forecast_chp against observed, and Δ = (chp − l6) / l6.
  3. Emit per-lead table + verdict.

Escalation trigger (per project_chp_midlead_regression_watch.md):
  ESCALATE if any 6-20h lead has n ≥ 100 AND (chp MAE − l6 MAE) / l6 MAE
  ≥ +20% (chp materially worse than Lc alone on this lead).

Escalation action (documented, not executed here):
  Rebuild h_ch_persistence_blend_stage2.py with forecast_l6 as baseline
  instead of forecast_l4; re-derive SHIP/SKIP per (regime × lead_band);
  cells that were SHIP under L4 baseline but flip SKIP under L6 baseline
  are the mid-lead false-positives that need demotion.

Run:
    python3 analysis/h_chp_midlead_regression.py

Output:
    analysis/output/h_chp_midlead_regression.txt
    analysis/output/h_chp_midlead_regression.json
"""
import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_chp_midlead_regression.txt")
OUT_JSON = os.path.join(SCRIPT_DIR, "output", "h_chp_midlead_regression.json")

FIELD = "ch"
CHP_SHIP_DATE = "2026-07-19T00:00"  # v0.6.358 wire — filter earlier rows
CHP_ATTRIB_DATE = "2026-07-20T00:00"  # v0.6.369 attribution wiring landed
LEAD_LO = 6
LEAD_HI = 20
ESCALATE_N = 100
ESCALATE_PCT = 20.0


def load_rows():
    rows = []
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            obs = r.get("observed")
            fc_l6 = r.get("forecast_l6")
            fc_chp = r.get("forecast_chp")
            lead = r.get("lead_h")
            ts = r.get("obs_time")
            if obs is None or fc_l6 is None or fc_chp is None or lead is None or ts is None:
                continue
            if ts < CHP_ATTRIB_DATE:
                continue
            lead = int(lead)
            if not (LEAD_LO <= lead <= LEAD_HI):
                continue
            rows.append({
                "ts": ts,
                "obs": float(obs),
                "l6": float(fc_l6),
                "chp": float(fc_chp),
                "lead": lead,
            })
    return rows


def per_lead_stats(rows):
    by_lead = {}
    for r in rows:
        b = by_lead.setdefault(r["lead"], {"n": 0, "sum_abs_l6": 0.0, "sum_abs_chp": 0.0})
        b["n"] += 1
        b["sum_abs_l6"] += abs(r["l6"] - r["obs"])
        b["sum_abs_chp"] += abs(r["chp"] - r["obs"])
    out = []
    for lead in sorted(by_lead):
        b = by_lead[lead]
        if b["n"] == 0:
            continue
        mae_l6 = b["sum_abs_l6"] / b["n"]
        mae_chp = b["sum_abs_chp"] / b["n"]
        delta_pct = None
        if mae_l6 > 0:
            delta_pct = (mae_chp - mae_l6) / mae_l6 * 100.0
        out.append({
            "lead": lead,
            "n": b["n"],
            "mae_l6": mae_l6,
            "mae_chp": mae_chp,
            "delta_pct": delta_pct,
            "chp_wins": mae_chp < mae_l6,
        })
    return out


def _fires_escalation(per_lead):
    hits = []
    for row in per_lead:
        n = row["n"]
        d = row["delta_pct"]
        if n is not None and n >= ESCALATE_N and d is not None and d >= ESCALATE_PCT:
            hits.append(row)
    return hits


def main():
    rows = load_rows()
    if not rows:
        print(f"No ch rows in pair log at lead {LEAD_LO}-{LEAD_HI}h with "
              f"forecast_l6 + forecast_chp populated + obs_time ≥ {CHP_ATTRIB_DATE}. "
              f"Check pair log freshness (`MYWEATHER_REFRESH=1`?).", file=sys.stderr)
        return 1

    per_lead = per_lead_stats(rows)
    hits = _fires_escalation(per_lead)

    lines = []
    def emit(s=""):
        print(s)
        lines.append(s)

    emit("=" * 100)
    emit("chp mid-lead regression re-check — ad-hoc per-lead vs Lc")
    emit("=" * 100)
    emit(f"Rows: {len(rows):,} ch pairs at lead {LEAD_LO}-{LEAD_HI}h; "
         f"post-{CHP_ATTRIB_DATE} (chp attribution wiring). "
         f"Trigger: n ≥ {ESCALATE_N} AND (chp − l6) / l6 ≥ +{ESCALATE_PCT:.0f}%.")
    emit("")
    emit(f"  {'lead':>4}  {'n':>6}  {'MAE_l6':>8}  {'MAE_chp':>8}  {'Δ%':>7}  winner")
    emit(f"  {'----':>4}  {'------':>6}  {'--------':>8}  {'--------':>8}  {'-------':>7}  ------")
    for row in per_lead:
        d = row["delta_pct"]
        d_str = f"{d:+.1f}%" if d is not None else "n/a"
        winner = "chp" if row["chp_wins"] else "l6"
        emit(f"  {row['lead']:>4d}  {row['n']:>6d}  {row['mae_l6']:>8.3f}  "
             f"{row['mae_chp']:>8.3f}  {d_str:>7}  {winner}")
    emit("")

    if hits:
        verdict = "ESCALATE"
        rationale = (f"{len(hits)} lead(s) hit the escalation trigger "
                     f"(n ≥ {ESCALATE_N} AND Δ ≥ +{ESCALATE_PCT:.0f}%): "
                     + ", ".join(f"lead {h['lead']} n={h['n']} Δ={h['delta_pct']:+.1f}%"
                                 for h in hits) + ".")
    else:
        # Report the worst offender for context even when not escalating.
        worst = None
        for row in per_lead:
            if row["delta_pct"] is not None and (worst is None or row["delta_pct"] > worst["delta_pct"]):
                worst = row
        if worst and worst["delta_pct"] > 0:
            verdict = "STABLE"
            rationale = (f"no lead hits the escalation trigger. Worst mid-lead: "
                         f"lead {worst['lead']} n={worst['n']} Δ={worst['delta_pct']:+.1f}% "
                         f"(chp {'behind' if worst['delta_pct'] > 0 else 'ahead'} of Lc "
                         f"— below the +{ESCALATE_PCT:.0f}% action floor).")
        else:
            verdict = "STABLE"
            rationale = "chp beats Lc across all 6-20h leads with sample; no regression signal."

    emit("=" * 100)
    emit(f"→ {verdict}: {rationale}")
    emit(f"VERDICT: {verdict} chp_midlead_regression "
         f"leads={len(per_lead)} hits={len(hits)} rows={len(rows)}")
    emit("=" * 100)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"forecast_error_log.jsonl (field={FIELD}, post-{CHP_ATTRIB_DATE})",
        "n_rows": len(rows),
        "lead_range": [LEAD_LO, LEAD_HI],
        "escalation_gate": {"n_min": ESCALATE_N, "delta_pct_min": ESCALATE_PCT},
        "per_lead": per_lead,
        "hits": hits,
        "verdict": {
            "state": verdict,
            "candidate": "chp_midlead_regression",
            "rationale": rationale,
        },
    }

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
