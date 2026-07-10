"""Read `production_regime_trajectory.jsonl` and report Production %-vs-raw
stratified by raw-MAE difficulty quartile.

The odometer alone doesn't answer "is the pipeline getting better?" because
Production %-vs-raw for L2-additive-bias fields (dp, h, ws, wg) is a strong
function of the raw-MAE distribution. On low-raw-MAE days the correction
adds bias-noise the model didn't need; on high-raw-MAE days it hits its
target. Aggregate can look like it's moving when only the weather has moved.

Fix: bucket each (day, regime, field) cell into a raw-MAE quartile using
per-(regime, field) cuts derived from the 28-day rolling window; then
report Production % vs raw per quartile. A cleaner trajectory statement
becomes possible: "In Q3+Q4 difficulty on dp/pre_frontal, Production
%-vs-raw has trended from X to Y over the past 30 days."

Output:
  Stdout — per (field, regime) block showing per-quartile Production %-vs-raw
  and a "diff between hard-and-easy days" column.
  analysis/output/production_trajectory_by_difficulty.txt — same, saved.

Run:
  python3 analysis/production_trajectory_by_difficulty.py
"""
import os
import sys
import json
import statistics
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IN_PATH = os.path.join(SCRIPT_DIR, "output", "production_regime_trajectory.jsonl")
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "production_trajectory_by_difficulty.txt")

# Fields worth flagging as strongly-difficulty-conditioned (from 2026-07-10
# noise-vs-signal check — the L2-additive-bias family). Not a filter; just
# the fields we call out with ★ in the output.
STRONGLY_CONDITIONED = {"dp", "h", "ws", "wg"}


def load_rows():
    rows = []
    if not os.path.exists(IN_PATH):
        return rows
    with open(IN_PATH) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(r)
    return rows


def compute_cuts(rows):
    """Per (regime, field), compute the 25/50/75 raw-MAE percentiles across
    all rows. Cells with raw_mae below Q1 → 'Q1 (easy)'; Q1..Q2 → 'Q2';
    Q2..Q3 → 'Q3'; ≥Q3 → 'Q4 (hard)'.
    """
    by_key = defaultdict(list)
    for r in rows:
        by_key[(r["regime"], r["field"])].append(r["mae_raw"])
    cuts = {}
    for k, vals in by_key.items():
        if len(vals) < 4:
            continue
        vs = sorted(vals)
        n = len(vs)
        q1 = vs[n // 4]
        q2 = vs[n // 2]
        q3 = vs[(3 * n) // 4]
        cuts[k] = (q1, q2, q3)
    return cuts


def bucket_of(mae_raw, cuts):
    q1, q2, q3 = cuts
    if mae_raw < q1:
        return "Q1"
    if mae_raw < q2:
        return "Q2"
    if mae_raw < q3:
        return "Q3"
    return "Q4"


def report(rows, cuts, out_lines):
    """For each (field, regime), print per-quartile Production % vs raw.
    n-weighted mean of prod_pct_vs_raw across cells falling in each quartile.
    """
    # (field, regime, quartile) -> [n_cells, sum_n, sum_prod_pct * sum_n]
    agg = defaultdict(lambda: [0, 0, 0.0])
    for r in rows:
        key = (r["regime"], r["field"])
        if key not in cuts:
            continue
        q = bucket_of(r["mae_raw"], cuts[key])
        a = agg[(r["field"], r["regime"], q)]
        a[0] += 1
        a[1] += r["n_pairs"]
        a[2] += r["prod_pct_vs_raw"] * r["n_pairs"]

    def emit(s):
        print(s)
        out_lines.append(s)

    emit("Production %-vs-raw stratified by raw-MAE quartile per (regime, field)")
    emit("Q1 = easy days (raw MAE small); Q4 = hard days (raw MAE large)")
    emit("prod_pct is n-weighted mean across day-cells in that quartile")
    emit("Δ = Q4 − Q1: how much more the correction helps on hard days than easy")
    emit("★ = field with strong noise-vs-signal signature (L2 additive bias)")
    emit("")

    # One block per field, regimes as rows
    fields = sorted({f for (f, _, _) in agg.keys()})
    for field in fields:
        star = "★" if field in STRONGLY_CONDITIONED else " "
        emit(f"{star} {field}")
        emit(f"  {'regime':<14} {'Q1 prod%':>9} {'Q2 prod%':>9} "
             f"{'Q3 prod%':>9} {'Q4 prod%':>9} {'ΔQ4-Q1':>9}   n_cells (Q1/Q2/Q3/Q4)")
        # Get regimes present for this field
        regimes = sorted({r for (f, r, _) in agg.keys() if f == field})
        for regime in regimes:
            row_vals = {}
            row_ns = {}
            for q in ("Q1", "Q2", "Q3", "Q4"):
                a = agg.get((field, regime, q))
                if a and a[1] > 0:
                    row_vals[q] = a[2] / a[1]
                    row_ns[q] = a[0]
                else:
                    row_vals[q] = None
                    row_ns[q] = 0
            def fmt(v):
                return f"{v:>+9.2f}" if v is not None else f"{'—':>9}"
            q1v = row_vals["Q1"]
            q4v = row_vals["Q4"]
            diff_s = f"{q4v - q1v:>+9.2f}" if (q1v is not None and q4v is not None) else f"{'—':>9}"
            n_str = f"{row_ns['Q1']}/{row_ns['Q2']}/{row_ns['Q3']}/{row_ns['Q4']}"
            emit(f"  {regime:<14} {fmt(q1v)} {fmt(row_vals['Q2'])} "
                 f"{fmt(row_vals['Q3'])} {fmt(q4v)} {diff_s}   {n_str}")
        emit("")


def main():
    rows = load_rows()
    if len(rows) < 20:
        print(f"Insufficient rows in {IN_PATH} — run production_regime_trajectory.py first.")
        return 1
    cuts = compute_cuts(rows)
    out_lines = []
    report(rows, cuts, out_lines)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(out_lines) + "\n")
    print(f"\nwrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
