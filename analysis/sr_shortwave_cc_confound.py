"""
Diagnostic: is the sr total-shortwave overshoot in pre_frontal/sea_breeze
regimes driven by (A) cloud-cover forecast miss surfacing through solar,
or (B) a real Open-Meteo diffuse/aerosol modeling gap?

Context (2026-07-07):
  sr_shortwave_bias.py first read (n=1,200, day 1 of v0.6.309 shadow log)
  showed that on total-shortwave terms the model OVER-forecasts sr in
  pre_frontal (+11.84 W/m² signed) and sea_breeze (+168.58) — the opposite
  of the direct-beam under-forecast the pair log had been reporting.

  Two candidate causes:
    A. Model under-forecasts cc in these regimes (known bias: sea-breeze
       marine layer, pre-frontal stratus). Its total_shortwave then
       mechanically overshoots because it's computing insolation through
       cleaner skies than reality. Not an sr modeling bug — a cc miss
       surfacing through sr.
    B. Even at matched cloud cover, HRRR/GFS over-predicts diffuse in
       marine humid airmasses (aerosol / water-vapor absorption gap).
       This would justify a new sr-specific correction.

Method:
  Join each sr shadow-log row to the paired cc row at the same
  (run_at, valid_at). Stratify sr signed error by |cc_fc − cc_obs|
  magnitude bins. If overshoot concentrates on cc-miss rows (|Δcc|>25),
  Cause A dominates. If it persists at matched cc (|Δcc|<10), Cause B.

Data readiness:
  sr shadow log started 2026-07-06 (v0.6.309). First real read ~2026-07-11
  once ≥5 days of daytime rows accumulate. Script prints an INSUFFICIENT
  banner and exits early if the two regimes-of-interest have <300 rows
  each.

Run:
  python3 analysis/sr_shortwave_cc_confound.py
"""
import json
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "sr_shortwave_cc_confound.txt")

REGIMES_OF_INTEREST = ("pre_frontal", "sea_breeze")
CC_BINS = (
    ("matched (|Δcc|<10)",   0, 10),
    ("small miss (10-25)",  10, 25),
    ("big miss (25-50)",    25, 50),
    ("severe miss (≥50)",   50, 10_000),
)
MIN_ROWS_PER_REGIME = 300


def _bin_label(cc_err_abs: float) -> str:
    for label, lo, hi in CC_BINS:
        if lo <= cc_err_abs < hi:
            return label
    return CC_BINS[-1][0]


def main():
    print("=" * 88)
    print("sr shortwave overshoot — confound check vs cc forecast error")
    print("=" * 88)
    print()
    print("[1/2] Building cc lookup by (run_time, valid_time)...")

    cc_by_key = {}  # (run_time, valid_time) -> (cc_fc, cc_obs)
    n_total = n_cc = 0
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            n_total += 1
            if r.get("field") != "cc":
                continue
            fc = r.get("forecast_l1")
            obs = r.get("observed")
            run_time = r.get("run_time")
            valid_time = r.get("valid_time")
            if fc is None or obs is None or run_time is None or valid_time is None:
                continue
            n_cc += 1
            cc_by_key[(run_time, valid_time)] = (float(fc), float(obs))

    print(f"  pair rows scanned:     {n_total:,}")
    print(f"  cc rows indexed:       {n_cc:,}")
    print()
    print("[2/2] Joining sr shadow rows to cc, stratifying...")

    # regime -> cc_bin_label -> [n, sum signed_err_sw, sum |err_sw|]
    strat = defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0.0]))
    regime_totals = defaultdict(lambda: [0, 0.0, 0.0])
    n_sr = n_sr_with_sw = n_sr_joined = 0

    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != "sr":
                continue
            n_sr += 1
            fc_sw = r.get("forecast_shortwave")
            obs = r.get("observed")
            if fc_sw is None or obs is None:
                continue
            n_sr_with_sw += 1
            key = (r.get("run_time"), r.get("valid_time"))
            paired_cc = cc_by_key.get(key)
            if paired_cc is None:
                continue
            n_sr_joined += 1

            regime = (r.get("state_obs") or {}).get("regime_synoptic") or "unknown"
            if regime not in REGIMES_OF_INTEREST:
                continue

            err_sw = float(fc_sw) - float(obs)
            cc_fc, cc_obs = paired_cc
            cc_err_abs = abs(cc_fc - cc_obs)
            label = _bin_label(cc_err_abs)

            for cell in (strat[regime][label], regime_totals[regime]):
                cell[0] += 1
                cell[1] += err_sw
                cell[2] += abs(err_sw)

    print(f"  sr rows:                                        {n_sr:,}")
    print(f"  sr rows with forecast_shortwave (v0.6.309+):    {n_sr_with_sw:,}")
    print(f"  sr rows joined to a cc row (same run/valid):    {n_sr_joined:,}")
    print()

    lines = []

    def emit(s):
        print(s)
        lines.append(s)

    thin_regimes = [
        rg for rg in REGIMES_OF_INTEREST
        if regime_totals[rg][0] < MIN_ROWS_PER_REGIME
    ]
    if thin_regimes:
        emit("=" * 88)
        emit(f"INSUFFICIENT DATA — regimes below {MIN_ROWS_PER_REGIME} rows:")
        for rg in thin_regimes:
            emit(f"  {rg:<14} n={regime_totals[rg][0]:,}")
        emit("")
        emit("v0.6.309 shadow log started 2026-07-06. Re-run once the daytime")
        emit("pair rows fill in — first meaningful read expected ~2026-07-11.")
        emit("=" * 88)
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        with open(OUTPUT_PATH, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\nWrote {OUTPUT_PATH}")
        return 0

    for regime in REGIMES_OF_INTEREST:
        emit("=" * 88)
        emit(f"Regime: {regime}   (n={regime_totals[regime][0]:,})")
        emit("=" * 88)
        emit(f"  {'|Δcc| bin':<24} {'n':>7}  "
             f"{'mean signed err_sw':>20} {'MAE_sw':>10}")
        emit("  " + "-" * 66)
        for label, _lo, _hi in CC_BINS:
            n, ssum, absum = strat[regime][label]
            if n == 0:
                emit(f"  {label:<24} {n:>7}  {'—':>20} {'—':>10}")
                continue
            m_signed = ssum / n
            m_abs = absum / n
            emit(f"  {label:<24} {n:>7,}  "
                 f"{m_signed:>+20.2f} {m_abs:>10.2f}")
        emit("")

    emit("Interpretation:")
    emit("  If mean signed err_sw is near zero in the |Δcc|<10 bin but positive")
    emit("  and large in the big/severe-miss bins, the overshoot is a cc-miss")
    emit("  confound (Cause A). No new sr correction warranted — invest in cc.")
    emit("")
    emit("  If mean signed err_sw stays positive across all cc bins including")
    emit("  matched, the model over-predicts total shortwave even at correct")
    emit("  cloud cover (Cause B). Justifies logging as a new sr hypothesis")
    emit("  for a regime-conditional Lsr refit against shortwave.")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
