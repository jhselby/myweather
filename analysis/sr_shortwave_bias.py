"""
Diagnostic: how much of Lsr's regime bias is really the direct-vs-shortwave
unit gap?

Context (2026-07-06):
  Tempest station `solar_radiation_wm2` measures TOTAL shortwave (direct +
  diffuse). Model `direct_radiation` is direct-beam only. Pair rows for sr
  compare Tempest total against forecast_l1 = direct — the difference is
  dominated by the definitional gap, not a real forecast error.

  v0.6.309 shipped shadow-logging model `shortwave_radiation` and
  `diffuse_radiation` on every sr pair row (`forecast_shortwave`,
  `forecast_diffuse`). This script quantifies:

    1. |observed − forecast_direct|     — what the pair log currently reports
    2. |observed − forecast_shortwave|  — apples-to-apples (both totals)
    3. Per-regime breakdown of both

  If (2) is materially smaller than (1) in every regime — especially the
  regimes where Lsr misbehaves (ne_flow, calm) — that confirms Lsr has
  been fitting the unit gap. From there, the fix chain is: switch sr
  forecast to shortwave, refit Lsr against the clean baseline, expect
  most regime bias to collapse.

Run:
  python3 analysis/sr_shortwave_bias.py
"""
import json
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "sr_shortwave_bias.txt")


def main():
    print("=" * 88)
    print("sr — direct-beam vs total-shortwave forecast bias against Tempest obs")
    print("=" * 88)
    print()
    print("Streaming pair log...")

    # (regime) -> [n, sum|err_direct|, sum|err_sw|, sum signed_err_direct,
    #              sum signed_err_sw]
    by_regime = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0])
    overall = [0, 0.0, 0.0, 0.0, 0.0]

    n_total = n_sr = n_with_sw = n_matched = 0
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            n_total += 1
            if r.get("field") != "sr":
                continue
            n_sr += 1
            fc_direct = r.get("forecast_l1")
            fc_sw = r.get("forecast_shortwave")
            obs = r.get("observed")
            if fc_direct is None or obs is None:
                continue
            if fc_sw is None:
                # Old pair rows from before v0.6.309 — no shadow log yet.
                continue
            n_with_sw += 1
            n_matched += 1
            err_direct = float(fc_direct) - float(obs)
            err_sw = float(fc_sw) - float(obs)
            so = r.get("state_obs") or {}
            regime = so.get("regime_synoptic") or "unknown"

            for cell in (by_regime[regime], overall):
                cell[0] += 1
                cell[1] += abs(err_direct)
                cell[2] += abs(err_sw)
                cell[3] += err_direct
                cell[4] += err_sw

    print(f"  total pair rows scanned:              {n_total:,}")
    print(f"  sr rows:                              {n_sr:,}")
    print(f"  sr rows with shadow shortwave (v0.6.309+): {n_with_sw:,}")
    print()

    if n_matched < 100:
        msg = ("Not enough sr rows carry `forecast_shortwave` yet — "
               "v0.6.309 only started stamping today. Re-run after a "
               "few hours of daytime ticks accumulate (say 500+ pairs).")
        print(msg)
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        with open(OUTPUT_PATH, "w") as f:
            f.write(msg + "\n")
        return 0

    lines = []

    def emit(s):
        print(s)
        lines.append(s)

    emit("=" * 88)
    emit("MAE (unsigned) and mean signed bias per regime — model minus Tempest")
    emit("=" * 88)
    emit(f"  {'regime':<14} {'n':>7}  "
         f"{'|direct−obs|':>13} {'|sw−obs|':>10} {'|Δ|%':>7}  "
         f"{'direct bias':>12} {'sw bias':>10}")
    emit("  " + "-" * 82)

    def _row(label, cell):
        n, s_ad, s_asw, s_sd, s_ssw = cell
        if n == 0:
            return
        m_ad = s_ad / n
        m_asw = s_asw / n
        m_sd = s_sd / n
        m_ssw = s_ssw / n
        delta_pct = (m_ad - m_asw) / m_ad * 100 if m_ad > 0 else 0.0
        emit(f"  {label:<14} {n:>7,}  "
             f"{m_ad:>13.2f} {m_asw:>10.2f} {delta_pct:>6.1f}%  "
             f"{m_sd:>+12.2f} {m_ssw:>+10.2f}")

    for regime in sorted(by_regime.keys()):
        _row(regime, by_regime[regime])
    emit("  " + "-" * 82)
    _row("OVERALL", overall)

    emit("")
    emit("Reading:")
    emit("  |Δ|% > 0 means shortwave MAE < direct-beam MAE — the unit gap")
    emit("  was inflating the pair-log 'error' for that regime.")
    emit("  Signed bias sign flips (direct negative → shortwave positive) mean")
    emit("  the model was under-forecasting on direct-beam terms because it")
    emit("  ignored the diffuse component; on shortwave terms it may be closer")
    emit("  to unbiased.")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
