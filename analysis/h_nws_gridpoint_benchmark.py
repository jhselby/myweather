"""NBM/NWS-gridpoint vs current stack — head-to-head benchmark.

Reads the pair log (which since v0.6.431 stamps `forecast_nws` + `error_nws`
alongside forecast_l1/l2/l3/l4 for t, dp, pp, ws, wd). Reports per-field
per-lead MAE for NWS vs each existing layer, with halves-stability check.

Decision criteria per field:
  - PROMOTE: mae_nws < mae_l1 by ≥3% pooled AND both halves same-sign AND
             mae_nws < production_mae by ≥2% pooled
  - HOLD:    directionally positive but doesn't clear thresholds
  - KILL:    mae_nws ≥ mae_l1 pooled (NBM isn't helping vs. our raw baseline)

Run:
    python3 -m analysis.h_nws_gridpoint_benchmark
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path
from _prod import prod_error

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ("t", "dp", "pp", "ws", "wd")
MIN_N_FIELD = 100
PROMOTE_L1_MARGIN_PCT = 3.0
PROMOTE_PROD_MARGIN_PCT = 2.0


def _abs(e):
    return abs(float(e)) if e is not None else None


def main():
    # (field) -> list of (obs_time, |e_nws|, |e_l1|, |e_prod|)
    by_field = defaultdict(list)
    n_with_nws = 0
    n_total = 0

    with open(cached_path(URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            f = r.get("field")
            if f not in FIELDS:
                continue
            n_total += 1
            e_nws = r.get("error_nws")
            if e_nws is None:
                continue
            e_l1 = r.get("error_l1")
            e_prod = prod_error(r)
            if e_l1 is None or e_prod is None:
                continue
            ot = r.get("obs_time") or ""
            if len(ot) < 13:
                continue
            n_with_nws += 1
            by_field[f].append((ot, abs(float(e_nws)), abs(float(e_l1)), abs(float(e_prod))))

    print("h_nws_gridpoint_benchmark — NBM/NWS-gridpoint vs current stack")
    print("⚠ 08-31 caveat: prod stack already routes dp/wg/wd/cc to NBM at ≥6h")
    print("  via l1_selector.py (uses direct-NBM, not NWS-gridpoint). Any 'promote' verdict")
    print("  here is measuring NWS-gridpoint against a selector-routed baseline, not raw HRRR.")
    print(f"pair log rows scanned: {n_total:,}   with error_nws non-null: {n_with_nws:,}")
    if n_with_nws == 0:
        print()
        print("NO NWS-STAMPED ROWS YET. Waiting for post-v0.6.431 (2026-08-18 14:10 UTC)")
        print("collector ticks to accumulate paired rows. Re-run in 24-72h.")
        return

    print()
    print(f"{'field':<6} {'n':>7}  {'MAE_nws':>8}  {'MAE_l1':>8}  {'MAE_prod':>9}  "
          f"{'Δ_l1%':>7}  {'Δ_prod%':>8}  verdict")
    print("-" * 90)

    verdicts = {}
    for f in FIELDS:
        rows = by_field.get(f, [])
        n = len(rows)
        if n < MIN_N_FIELD:
            print(f"  {f:<4}  {n:>7}  {'thin':>8}")
            verdicts[f] = "THIN"
            continue
        rows.sort(key=lambda x: x[0])
        mae_nws = sum(r[1] for r in rows) / n
        mae_l1 = sum(r[2] for r in rows) / n
        mae_prod = sum(r[3] for r in rows) / n

        d_l1 = (mae_l1 - mae_nws) / mae_l1 * 100 if mae_l1 > 0 else 0.0
        d_prod = (mae_prod - mae_nws) / mae_prod * 100 if mae_prod > 0 else 0.0

        # Halves stability
        mid = n // 2
        a, b = rows[:mid], rows[mid:]
        mae_nws_a = sum(r[1] for r in a) / len(a) if a else 0.0
        mae_l1_a = sum(r[2] for r in a) / len(a) if a else 0.0
        mae_nws_b = sum(r[1] for r in b) / len(b) if b else 0.0
        mae_l1_b = sum(r[2] for r in b) / len(b) if b else 0.0
        d_a = (mae_l1_a - mae_nws_a) / mae_l1_a * 100 if mae_l1_a > 0 else 0.0
        d_b = (mae_l1_b - mae_nws_b) / mae_l1_b * 100 if mae_l1_b > 0 else 0.0
        halves_same_sign = (d_a > 0 and d_b > 0) or (d_a < 0 and d_b < 0)

        if d_l1 >= PROMOTE_L1_MARGIN_PCT and d_prod >= PROMOTE_PROD_MARGIN_PCT and halves_same_sign:
            verdict = "PROMOTE"
        elif d_l1 < 0 and d_prod < 0:
            verdict = "KILL"
        elif d_l1 > 0:
            verdict = f"HOLD (A={d_a:+.1f} B={d_b:+.1f})"
        else:
            verdict = "KILL"
        verdicts[f] = verdict
        print(f"  {f:<4}  {n:>7}  {mae_nws:>8.3f}  {mae_l1:>8.3f}  {mae_prod:>9.3f}  "
              f"{d_l1:>+6.1f}%  {d_prod:>+7.1f}%  {verdict}")

    print()
    print("VERDICT SUMMARY:")
    for f, v in verdicts.items():
        print(f"  {f}: {v}")

    n_promote = sum(1 for v in verdicts.values() if v == "PROMOTE")
    n_kill = sum(1 for v in verdicts.values() if v.startswith("KILL"))
    print()
    if n_promote >= 2:
        print(f"→ SHIP CANDIDATE: {n_promote} fields promote. Route those fields through "
              f"NWS-gridpoint as L1 (or add as router). Existing stack cascades unchanged.")
    elif n_promote >= 1:
        print(f"→ NARROW PROMOTE: {n_promote} field(s) promote. Consider per-field routing.")
    elif n_kill == len(FIELDS):
        print(f"→ KILL: NWS-gridpoint underperforms current L1 across all fields. Retire the "
              f"nws plumbing (revert v0.6.431 or leave dormant).")
    else:
        print(f"→ HOLD: no field cleared PROMOTE thresholds. Re-run in 3-5 days as more data "
              f"accumulates. If still HOLD after 14d, kill or narrow scope.")


if __name__ == "__main__":
    main()
