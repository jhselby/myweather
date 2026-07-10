"""Stage 0 — can we predict raw MAE at forecast time?

Hypothesis (2026-07-10): L2-additive-bias correction (dp/h/ws/wg) HURTS on
easy days (low raw MAE) and HELPS on hard days (high raw MAE). If we can
predict "easy vs hard" at forecast time using signals we already stamp,
we can gate L2 conditionally — apply on predicted-hard cells, skip on
predicted-easy cells — and recover the wasted correction on easy days.

The critical piece is "at forecast time." We can't observe raw MAE at
forecast time; we need proxies that correlate with it.

Candidate proxies, all already stamped per tick (7 axes of C1 + forecast
value itself + observed wind speed):
  - C1a: regime_fc != regime_obs → transition
  - C1c: pressure_trend_hpa_3h binned (falling_fast / falling / flat / rising)
  - C1f: precip_fc > 0
  - forecast value magnitude (extreme forecast → wider error?)
  - forecast wind speed (chaotic conditions → wider error?)

For each field × each predictor, this script:
  1. Bins pair-log rows by the predictor's value
  2. Computes mean |L1 raw error| per bin
  3. Computes the "elevation ratio": max_bin_mae / min_bin_mae
  4. Also computes Production help (mae_raw - mae_prod) per bin
  5. Reports whether the correction ACTUALLY does more work on high-raw bins
     — that's the confirmatory test: predictor separates raw-difficulty AND
     the pipeline exploits the separation.

Verdict per (field, predictor):
  ★ REAL      — elevation ratio ≥ 1.5 AND Production help_hi ≥ 1.5× help_lo
  ⚠ SUGGESTIVE — elevation ratio ≥ 1.3 OR help separates but ratio doesn't
  flat        — no signal

If a predictor comes out ★ for an L2-additive field, that's an actionable
gate candidate — Stage 1 would be to test the (predictor, field, bin)
skip-table configuration.

Run:
  python3 analysis/h_raw_error_predictors.py
"""
import os
import sys
import json
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(os.path.dirname(__file__), "output",
                       "h_raw_error_predictors.txt")

L2_ADDITIVE_FIELDS = {"dp", "h", "ws", "wg"}  # the noise-vs-signal family
# All fields worth checking. Predictors may separate hard/easy differently
# per field so cast a wide net.
FIELDS = ("t", "dp", "h", "cc", "cl", "cm", "ch", "ws", "wg", "sr", "pp", "pa", "pr")

MIN_N_PER_BIN = 500
REAL_ELEVATION_RATIO = 1.5
REAL_HELP_RATIO = 1.5
WATCH_ELEVATION_RATIO = 1.3


def _pt_bin(pt):
    """Pressure-tendency bins — mirror confidence_layer's PT_BINS."""
    if pt is None:
        return None
    if pt < -1.0: return "falling_fast"
    if pt < -0.3: return "falling"
    if pt < 0.3:  return "flat"
    return "rising"


def _fc_magnitude_bin(field, fc):
    """Quartile of forecast value per field. Cached quartile cuts from
    a single pass over the log. To keep this a one-shot script, hardcode
    reasonable per-field cuts learned from the state_stratified data;
    slightly wrong quartile cuts won't invalidate the qualitative finding."""
    if fc is None:
        return None
    cuts = {
        "t":  (55.0, 65.0, 75.0),
        "dp": (45.0, 55.0, 65.0),
        "h":  (50.0, 70.0, 85.0),
        "cc": (5.0, 30.0, 70.0),
        "cl": (2.0, 15.0, 50.0),
        "cm": (2.0, 15.0, 50.0),
        "ch": (2.0, 20.0, 55.0),
        "ws": (3.0, 7.0, 12.0),
        "wg": (5.0, 12.0, 20.0),
        "sr": (0.0, 100.0, 500.0),
        "pp": (2.0, 20.0, 60.0),
        "pa": (0.0001, 0.01, 0.1),
        "pr": (29.8, 29.95, 30.1),
    }.get(field)
    if not cuts:
        return None
    if fc < cuts[0]: return "Q1"
    if fc < cuts[1]: return "Q2"
    if fc < cuts[2]: return "Q3"
    return "Q4"


def _wind_bin(ws):
    if ws is None:
        return None
    if ws < 3: return "calm (<3)"
    if ws < 8: return "light (3-8)"
    if ws < 15: return "mod (8-15)"
    return "strong (≥15)"


# Predictors: (name, get_bin(row) → label|None)
PREDICTORS = [
    ("C1a-transition",   lambda r: "trans" if (r.get("state_fc", {}).get("regime_synoptic") != r.get("state_obs", {}).get("regime_synoptic")) else "stable"),
    ("C1c-pt-bin",       lambda r: _pt_bin(r.get("state_fc", {}).get("pressure_trend_hpa_3h"))),
    ("C1f-precip_fc",    lambda r: "p1" if (r.get("state_fc", {}).get("precip_in") or 0) > 0 else "p0"),
    ("fc-magnitude-Q",   lambda r: _fc_magnitude_bin(r.get("field"), r.get("forecast_l1"))),
    ("fc-wind-bin",      lambda r: _wind_bin(r.get("state_fc", {}).get("wind_speed"))),
    ("regime_synoptic",  lambda r: r.get("state_fc", {}).get("regime_synoptic")),
]


def main():
    # (field, predictor_name, bin) -> [n, sum|raw_err|, sum|prod_err|]
    accs = defaultdict(lambda: [0, 0.0, 0.0])
    rows_scanned = 0
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for line in fh:
            rows_scanned += 1
            try:
                r = json.loads(line)
            except Exception:
                continue
            field = r.get("field")
            if field not in FIELDS:
                continue
            fc_l1 = r.get("forecast_l1")
            fc_prod = (r.get("forecast_l4") or r.get("forecast_l3")
                       or r.get("forecast_l2") or r.get("forecast_l1"))
            obs = r.get("observed")
            if fc_l1 is None or fc_prod is None or obs is None:
                continue
            try:
                err_raw = abs(float(fc_l1) - float(obs))
                err_prod = abs(float(fc_prod) - float(obs))
            except (TypeError, ValueError):
                continue
            for pname, pfn in PREDICTORS:
                b = pfn(r)
                if b is None:
                    continue
                a = accs[(field, pname, b)]
                a[0] += 1
                a[1] += err_raw
                a[2] += err_prod

    print(f"rows scanned: {rows_scanned:,}")
    print()

    out_lines = []
    def emit(s):
        print(s); out_lines.append(s)

    emit(f"h_raw_error_predictors — can forecast-time signals predict raw MAE?")
    emit(f"For each field × predictor: raw MAE per bin, Production help per bin.")
    emit(f"★ = separates raw AND correction exploits it (elevation ≥{REAL_ELEVATION_RATIO}× AND help_hi/help_lo ≥ {REAL_HELP_RATIO}×)")
    emit(f"⚠ = separates but weakly (elevation ≥{WATCH_ELEVATION_RATIO}×)")
    emit(f"L2* = field with strong L2-additive-bias character — the gate candidates")
    emit("")

    for field in FIELDS:
        l2_flag = "L2*" if field in L2_ADDITIVE_FIELDS else "   "
        emit(f"{l2_flag} {field}")
        for pname, _ in PREDICTORS:
            # Collect all bins for this (field, pname)
            bins = []
            for (f, p, b), (n, sr, sp) in accs.items():
                if f == field and p == pname and n >= MIN_N_PER_BIN:
                    mae_raw = sr / n
                    mae_prod = sp / n
                    help_pp = mae_raw - mae_prod  # positive = Production better than raw
                    bins.append((b, n, mae_raw, mae_prod, help_pp))
            if len(bins) < 2:
                continue
            bins.sort(key=lambda x: x[2])  # sort by raw MAE ascending
            lo = bins[0]
            hi = bins[-1]
            elevation_ratio = hi[2] / lo[2] if lo[2] > 0 else 0
            help_lo = lo[4]
            help_hi = hi[4]
            help_ratio = (help_hi / help_lo) if help_lo > 0 else (float("inf") if help_hi > 0 else 0)
            # Verdict
            if elevation_ratio >= REAL_ELEVATION_RATIO and help_ratio >= REAL_HELP_RATIO:
                tag = "★ REAL"
            elif elevation_ratio >= WATCH_ELEVATION_RATIO:
                tag = "⚠"
            else:
                tag = ""
            emit(f"  {pname:<22} n_bins={len(bins)}   raw_lo={lo[2]:.3f} ({lo[0]}, n={lo[1]:,})   "
                 f"raw_hi={hi[2]:.3f} ({hi[0]}, n={hi[1]:,})   "
                 f"elev={elevation_ratio:.2f}×   help_lo={help_lo:+.3f}   help_hi={help_hi:+.3f}   "
                 f"help_ratio={help_ratio:.2f}×  {tag}")
        emit("")

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(out_lines) + "\n")
    print(f"wrote {OUT_TXT}")


if __name__ == "__main__":
    main()
