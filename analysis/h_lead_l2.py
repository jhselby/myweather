"""Stage 0 — Lead-time × L2 efficacy.

Question: L2 (mesonet bias) is applied with the same Kalman gain K across all
48 forecast leads. But the mesonet observes RIGHT NOW; that signal should
help more at lead 0 (when "right now" still resembles the forecast hour) and
less at lead 24+ (when the weather will have evolved). Does L2 efficacy
actually decay with lead, suggesting K should taper?

Method: per (field, lead band), measure |error_l1| vs |error_l2|. Compute
L2 improvement % per band. If improvement degrades from band 0-5h → 24-47h
by ≥10pp, lead-conditional K is a real opportunity.

Fields: t, h, ws, wg, pr (where L2 is applied).
"""
import os, sys, json, argparse
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
L2_FIELDS = {"t", "h", "ws", "wg", "pr"}
BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]

ap = argparse.ArgumentParser()
ap.add_argument("--cutoff", default=None, help="window end (UTC), e.g. 2026-06-15")
ap.add_argument("--window-days", type=int, default=7)
args = ap.parse_args()

end_dt = datetime.fromisoformat(args.cutoff) if args.cutoff else datetime.utcnow()
start_dt = end_dt - timedelta(days=args.window_days)
start_iso = start_dt.strftime("%Y-%m-%dT%H:%M")
end_iso = end_dt.strftime("%Y-%m-%dT%H:%M")
print(f"Window: {start_iso} → {end_iso}\n")

# (field, band) -> [n, sum|e1|, sum|e2|]
sums = defaultdict(lambda: [0, 0.0, 0.0])

def _band(lead):
    for label, lo, hi in BANDS:
        if lo <= lead < hi:
            return label
    return None

with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in L2_FIELDS:
            continue
        ot = r.get("obs_time") or ""
        if not (start_iso <= ot < end_iso):
            continue
        lead = r.get("lead_h")
        if lead is None:
            continue
        band = _band(int(lead))
        if band is None:
            continue
        e1 = r.get("error_l1"); e2 = r.get("error_l2")
        if e1 is None or e2 is None:
            continue
        s = sums[(f, band)]
        s[0] += 1
        s[1] += abs(e1)
        s[2] += abs(e2)

print(f"{'field':<6} {'band':<7} {'n':>9} {'|L1|':>8} {'|L2|':>8} {'Δ%':>7}")
print("-" * 50)
for f in sorted(L2_FIELDS):
    band_gains = {}
    for label, lo, hi in BANDS:
        n, e1, e2 = sums.get((f, label), (0, 0.0, 0.0))
        if n < 200:
            continue
        m1 = e1/n; m2 = e2/n
        d = (m1 - m2) / m1 * 100 if m1 > 0 else 0
        band_gains[label] = d
        print(f"{f:<6} {label:<7} {n:>9,} {m1:>8.3f} {m2:>8.3f} {d:>6.1f}%")
    if "0-5h" in band_gains and "24-47h" in band_gains:
        drop = band_gains["0-5h"] - band_gains["24-47h"]
        verdict = "★ L2 DECAYS" if drop >= 10 else ("flat" if abs(drop) < 5 else "modest decay")
        print(f"  → near-far Δ (0-5h vs 24-47h): {drop:+.1f}pp  {verdict}")
    print()
