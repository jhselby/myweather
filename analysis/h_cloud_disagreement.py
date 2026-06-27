"""
Hypothesis: does KBOS-vs-KBVY inter-source σ (the cloud-blend's bias_std_cc
at snapshot run time) predict cloud-field forecast |error|?

If alive → ship as C1d, a 4th axis in the confidence layer.

Wiring (built 2026-06-27, v0.6.247):
  cloud_obs_blend.py stamps derived["cloud_inter_source_sigma"] from the
  KBOS+KBVY cc bias_std at L2 blend time. forecast_snapshot.py copies it
  onto every snap_entry. forecast_error_log.py attaches it to every pair
  row (top-level field, not in state_fc).

Method:
  1. Stream pair log; keep rows with field in {cc, cl, cm, ch} that carry
     cloud_inter_source_sigma (post-v0.6.247 rows only).
  2. Bin rows by σ quartile (Q1 = low disagreement, Q4 = high).
  3. Per (field, lead_band, quartile) compute MAE on |error|.
  4. Verdict:
       SMOKE_ALIVE if any (field, band) shows MAE_Q4 / MAE_Q1 >= 1.20
         with n_Q1 >= 200 and n_Q4 >= 200.
       INSUFFICIENT if total post-wiring rows < 5000 (need ~7d to accumulate).
       SMOKE_DEAD otherwise.
  5. Orthogonality is the second-stage question (vs C1a/C1e) — kicked to
     a follow-up h_cloud_disagreement_orthogonality.py once smoke is alive.
"""
import json
import os
import sys
from collections import defaultdict
from statistics import median

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "h_cloud_disagreement.txt")

FIELDS = ("cc", "cl", "cm", "ch")
LEAD_BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]
MIN_TOTAL_ROWS = 5000  # below this, report INSUFFICIENT


def lead_band(lead_h):
    for label, lo, hi in LEAD_BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def quartile_bounds(values):
    s = sorted(values)
    n = len(s)
    return (s[n // 4], median(s), s[(3 * n) // 4])


def main():
    print("=" * 72)
    print("H_CLOUD_DISAGREEMENT — KBOS-vs-KBVY σ predicts cloud-field |error|?")
    print("=" * 72)

    print("\n[1/3] Streaming pair log, filtering to cloud fields with σ...")
    pair_log_path = cached_path(PAIR_LOG_URL)

    sigmas = []
    rows = []  # (field, lead_band, abs_err, sigma)
    n_total = n_with_sigma = n_cloud = 0
    with open(pair_log_path) as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue
            n_total += 1
            field = row.get("field")
            if field not in FIELDS:
                continue
            n_cloud += 1
            sigma = row.get("cloud_inter_source_sigma")
            if sigma is None:
                continue
            err = row.get("error")
            lead_h = row.get("lead_h")
            if err is None or lead_h is None:
                continue
            band = lead_band(lead_h)
            if band is None:
                continue
            n_with_sigma += 1
            sigmas.append(float(sigma))
            rows.append((field, band, abs(float(err)), float(sigma)))

    print(f"  total pair rows: {n_total}")
    print(f"  cloud-field rows: {n_cloud}")
    print(f"  with cloud_inter_source_sigma: {n_with_sigma}")

    if n_with_sigma < MIN_TOTAL_ROWS:
        print(f"\nVerdict: INSUFFICIENT — need >={MIN_TOTAL_ROWS} post-wiring rows, have {n_with_sigma}.")
        print("Re-run after ~7 days of pair-log accumulation (~2026-07-04).")
        _write_output(f"INSUFFICIENT — {n_with_sigma}/{MIN_TOTAL_ROWS} rows")
        return 0

    print("\n[2/3] σ distribution + quartile cuts...")
    q1_cut, med_cut, q3_cut = quartile_bounds(sigmas)
    print(f"  σ quartiles: Q1≤{q1_cut:.2f}, median={med_cut:.2f}, Q3≥{q3_cut:.2f}")

    agg = defaultdict(list)  # (field, band, bin) -> [|err|]
    for field, band, abs_err, sigma in rows:
        if sigma <= q1_cut:
            agg[(field, band, "Q1_low")].append(abs_err)
        elif sigma >= q3_cut:
            agg[(field, band, "Q4_high")].append(abs_err)

    print("\n[3/3] Per (field, lead_band) MAE Q1 vs Q4:")
    print(f"  {'field':<5} {'band':<8} {'Q1_n':>6} {'Q1_mae':>8} "
          f"{'Q4_n':>6} {'Q4_mae':>8} {'ratio':>7} {'verdict':<14}")
    smoke_alive = False
    lines = []
    for field in FIELDS:
        for band_label, _, _ in LEAD_BANDS:
            q1 = agg.get((field, band_label, "Q1_low"), [])
            q4 = agg.get((field, band_label, "Q4_high"), [])
            n1, n4 = len(q1), len(q4)
            if n1 < 50 or n4 < 50:
                row = f"  {field:<5} {band_label:<8} {n1:>6} {'—':>8} {n4:>6} {'—':>8} {'—':>7} {'thin':<14}"
            else:
                m1 = sum(q1) / n1
                m4 = sum(q4) / n4
                ratio = m4 / m1 if m1 > 0 else float("inf")
                if ratio >= 1.20 and n1 >= 200 and n4 >= 200:
                    verdict = "SMOKE_ALIVE"
                    smoke_alive = True
                elif ratio >= 1.10:
                    verdict = "hint"
                else:
                    verdict = "flat"
                row = (f"  {field:<5} {band_label:<8} {n1:>6} {m1:>8.3f} "
                       f"{n4:>6} {m4:>8.3f} {ratio:>7.2f} {verdict:<14}")
            print(row)
            lines.append(row)

    print("\n" + "=" * 72)
    if smoke_alive:
        msg = ("VERDICT: SMOKE_ALIVE — at least one cloud (field, band) shows "
               "MAE in highest-σ quartile ≥1.2x MAE in lowest-σ quartile. "
               "Recommendation: write h_cloud_disagreement_orthogonality.py "
               "to check independence vs C1a/C1e, then promote to C1d.")
    else:
        msg = ("VERDICT: SMOKE_DEAD — no cloud (field, band) shows ratio ≥1.2. "
               "Inter-source σ doesn't predict cloud-field error at this n. "
               "Recommendation: shelve C1d candidate.")
    print(msg)
    print("=" * 72)
    _write_output("\n".join(lines) + "\n\n" + msg)
    return 0


def _write_output(body):
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write(body + "\n")


if __name__ == "__main__":
    sys.exit(main())
