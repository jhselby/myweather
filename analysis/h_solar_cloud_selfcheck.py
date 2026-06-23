"""Stage 0 — state_fc.solar_wm2 × cloud MAE.

The model forecasts its own solar value. High solar = model expects clear sky.
Low solar = model expects clouds. Stratifying cloud-field MAE by model's
expected solar tells us if the model is over-confident when it thinks clear
(when it expects clear sky, is it actually right? or systematically missing
late-day clouds?).
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
CLOUD_FIELDS = ["cc", "cl", "cm", "ch"]

sums = defaultdict(lambda: [0, 0.0])
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        f = r.get("field")
        if f not in CLOUD_FIELDS:
            continue
        sw = (r.get("state_fc") or {}).get("solar_wm2")
        if sw is None:
            continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None:
            continue
        # Skip night (solar = 0)
        if sw < 50:
            sb = "night (<50)"
        elif sw < 200:
            sb = "dim (50-200)"
        elif sw < 500:
            sb = "mid (200-500)"
        elif sw < 800:
            sb = "bright (500-800)"
        else:
            sb = "blazing (≥800)"
        s = sums[(f, sb)]
        s[0] += 1; s[1] += abs(err)

ORDER = ["night (<50)", "dim (50-200)", "mid (200-500)", "bright (500-800)", "blazing (≥800)"]
print(f"{'field':<5} {'solar_fc':<20} {'n':>8} {'|err|':>8}")
print("-" * 50)
for f in CLOUD_FIELDS:
    rows = []
    for sb in ORDER:
        n, e = sums.get((f, sb), (0, 0.0))
        if n < 200:
            continue
        rows.append((sb, n, e/n))
    for sb, n, m in rows:
        print(f"{f:<5} {sb:<20} {n:>8,} {m:>8.3f}")
    if len(rows) >= 3:
        maes = [r[2] for r in rows]
        spread = (max(maes) - min(maes))/min(maes)*100 if min(maes) > 0 else 0
        # Compare brightest vs night
        bright = next((m for sb,n,m in rows if "blazing" in sb or "bright" in sb), None)
        night  = next((m for sb,n,m in rows if "night" in sb), None)
        verdict = ""
        if bright and night:
            ratio = bright/night
            if ratio > 1.5: verdict = "★ MODEL OVERCONFIDENT WHEN BRIGHT"
            elif ratio > 1.2: verdict = "⚠ mild"
            else: verdict = "flat"
        print(f"  → {f} spread: {spread:.1f}%, bright/night ratio: "
              f"{bright/night if bright and night else 0:.2f}×  {verdict}\n")
