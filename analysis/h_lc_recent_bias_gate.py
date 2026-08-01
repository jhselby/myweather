#!/usr/bin/env python3
"""Stage 0: recent-bias gate on the existing lc_fit shift table.

The problem [[project_lc_regime_conditional]]: Lc's shift table trains on
~30d of pair-log data. When upstream HRRR bias shifts direction (as
happened for cl around 2026-07-25), the trained shift keeps applying the
OLD direction until enough new data outweighs the old. Result: cl went
catastrophic 07-28 → 07-30. Fully off Lc since v0.6.389f.

The rolling-window sweep (`h_lc_rolling_window.py`) showed no window
length fixes cl — shifts swing wildly across windows. This gate takes
a different approach: keep the historical shift table AS IS, but only
apply it per-cell when RECENT observed bias still agrees.

Gate rule (per cell):
  * historical shift is a SHIP cell in current live lc_correction_table
  * sign(recent_bias) == sign(historical_mean_bias)
  * |recent_bias| >= GATE_RATIO * |historical_mean_bias|
  → apply historical shift. Else pass through (no shift).

Recent-bias window: last RECENT_DAYS days IMMEDIATELY BEFORE the
held-out score window (no data leakage).

Score: last HOLDOUT_DAYS days, held-out MAE per cell for:
  (a) 'raw'   — no correction
  (b) 'live'  — always-apply historical shift (current production for cm/ch;
                what production WOULD do for cl/cc if _FIELD_SKIP were empty)
  (c) 'gate'  — recent-bias-gated apply

Verdict per field:
  Stage 0 PROMOTE if (c) beats (a) pooled AND does not lose to (b) by more
  than TOLERANCE_PCT. That means the gate captures the win without
  making things worse than always-apply on days when the shift still works.

Run:
    python3 -m analysis.h_lc_recent_bias_gate
    MYWEATHER_REFRESH=1 python3 -m analysis.h_lc_recent_bias_gate
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis._cache import cached_path

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
LIVE_TABLE_PATH = Path(__file__).resolve().parent.parent / "weather_collector" / "data" / "lc_correction_table.json"

CLOUD_FIELDS = ["cc", "cl", "cm", "ch"]
BINS = [(0,5,"0-5"), (5,20,"5-20"), (20,50,"20-50"),
        (50,80,"50-80"), (80,95,"80-95"), (95,100.01,"95-100")]

RECENT_DAYS = 3
HOLDOUT_DAYS = 3
GATE_RATIO = 0.5
TOLERANCE_PCT = 5.0
MIN_N_CELL = 30


def bin_of(v):
    for lo, hi, lab in BINS:
        if lo <= v < hi:
            return lab
    return None


def load_fc(r):
    return (r.get("forecast_l4") or r.get("forecast_l3")
            or r.get("forecast_l2") or r.get("forecast_l1"))


def main():
    live = json.loads(LIVE_TABLE_PATH.read_text())["cells"]

    # Bucket pair-log rows by (obs_date, field, bin). obs_time is ISO string.
    rows = defaultdict(list)
    print(f"reading {PAIR_LOG_URL}")
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            field = r.get("field")
            if field not in CLOUD_FIELDS:
                continue
            fc = load_fc(r)
            obs = r.get("observed")
            ot = r.get("obs_time")
            if fc is None or obs is None or not ot:
                continue
            b = bin_of(float(fc))
            if b is None:
                continue
            day = ot[:10]
            rows[(day, field, b)].append((float(fc), float(obs)))

    # Determine windows from the actual data (most-recent day = today).
    all_days = sorted({k[0] for k in rows.keys()})
    if len(all_days) < RECENT_DAYS + HOLDOUT_DAYS:
        print(f"insufficient days: {len(all_days)} < {RECENT_DAYS + HOLDOUT_DAYS}")
        return
    holdout_days = all_days[-HOLDOUT_DAYS:]
    recent_days  = all_days[-(HOLDOUT_DAYS + RECENT_DAYS):-HOLDOUT_DAYS]
    print(f"recent window ({RECENT_DAYS}d): {recent_days[0]} → {recent_days[-1]}")
    print(f"holdout ({HOLDOUT_DAYS}d):      {holdout_days[0]} → {holdout_days[-1]}")
    print()

    # Recent-window mean bias per (field, bin).
    recent_bias = {}
    for field in CLOUD_FIELDS:
        for lo, hi, lab in BINS:
            key = (field, lab)
            pairs = []
            for d in recent_days:
                pairs.extend(rows.get((d, field, lab), []))
            if len(pairs) < MIN_N_CELL:
                continue
            recent_bias[key] = sum(fc - obs for fc, obs in pairs) / len(pairs)

    # Held-out score per (field, bin) × {raw, live, gate}.
    def mae(pairs, shift):
        if not pairs: return None
        return sum(abs(max(0.0, min(100.0, fc + shift)) - obs) for fc, obs in pairs) / len(pairs)

    print(f"{'field':<6} {'bin':<8} {'n':>6} {'hist_bias':>10} {'recent':>8} "
          f"{'ratio':>6} {'sign':>5} {'gate?':>6}  "
          f"{'MAE_raw':>8} {'MAE_live':>9} {'MAE_gate':>9}  {'live%':>7} {'gate%':>7}")
    print("-" * 128)

    field_agg = {f: {"n": 0, "raw": 0.0, "live": 0.0, "gate": 0.0} for f in CLOUD_FIELDS}
    gated_off_cells = defaultdict(list)  # field -> [bin]

    for field in CLOUD_FIELDS:
        for lo, hi, lab in BINS:
            key = (field, lab)
            cell = live.get(field, {}).get(lab)
            if not cell or cell.get("verdict") not in ("SHIP", "MARGINAL"):
                continue
            hist_bias = cell["mean_bias"]
            hist_shift = cell["shift"]
            recent = recent_bias.get(key)

            holdout = []
            for d in holdout_days:
                holdout.extend(rows.get((d, field, lab), []))
            n = len(holdout)
            if n < MIN_N_CELL:
                continue

            m_raw  = mae(holdout, 0.0)
            m_live = mae(holdout, hist_shift)

            # Gate decision.
            if recent is None:
                gate_apply = True  # THIN recent → default to live behavior
                gate_reason = "thin"
            else:
                sign_ok = (recent > 0 and hist_bias > 0) or (recent < 0 and hist_bias < 0)
                mag_ok  = abs(recent) >= GATE_RATIO * abs(hist_bias)
                gate_apply = sign_ok and mag_ok
                gate_reason = "on" if gate_apply else ("sign" if not sign_ok else "mag")
                if not gate_apply:
                    gated_off_cells[field].append(lab)
            m_gate = mae(holdout, hist_shift if gate_apply else 0.0)

            live_pct = 100.0 * (m_raw - m_live) / m_raw if m_raw > 0 else 0.0
            gate_pct = 100.0 * (m_raw - m_gate) / m_raw if m_raw > 0 else 0.0

            recent_s = f"{recent:+.1f}" if recent is not None else "n/a"
            ratio_s  = f"{abs(recent)/abs(hist_bias):.2f}" if recent is not None and hist_bias != 0 else "n/a"
            sign_s   = ("+" if (recent or 0) >= 0 else "-") if recent is not None else "?"
            print(f"{field:<6} {lab:<8} {n:>6} {hist_bias:>+10.1f} {recent_s:>8} "
                  f"{ratio_s:>6} {sign_s:>5} {gate_reason:>6}  "
                  f"{m_raw:>8.2f} {m_live:>9.2f} {m_gate:>9.2f}  {live_pct:>+6.1f}% {gate_pct:>+6.1f}%")

            field_agg[field]["n"] += n
            field_agg[field]["raw"]  += m_raw  * n
            field_agg[field]["live"] += m_live * n
            field_agg[field]["gate"] += m_gate * n

    print()
    print("=" * 128)
    print("FIELD POOLED (weighted by n across shipped cells):")
    print("=" * 128)
    print(f"{'field':<6} {'n':>7} {'MAE_raw':>8} {'MAE_live':>9} {'MAE_gate':>9}  "
          f"{'live%':>7} {'gate%':>7} {'gate−live':>10}  gated_off_bins")
    print("-" * 128)
    verdicts = []
    for field in CLOUD_FIELDS:
        a = field_agg[field]
        if a["n"] == 0: continue
        r = a["raw"] / a["n"]; l = a["live"] / a["n"]; g = a["gate"] / a["n"]
        live_pct = 100.0 * (r - l) / r if r > 0 else 0.0
        gate_pct = 100.0 * (r - g) / r if r > 0 else 0.0
        delta    = gate_pct - live_pct
        goff = ",".join(gated_off_cells.get(field, [])) or "-"
        print(f"{field:<6} {a['n']:>7} {r:>8.2f} {l:>9.2f} {g:>9.2f}  "
              f"{live_pct:>+6.1f}% {gate_pct:>+6.1f}% {delta:>+9.2f}pp  {goff}")

        # Verdict:
        if gate_pct > 0 and (live_pct <= 0 or gate_pct >= live_pct - TOLERANCE_PCT):
            verdicts.append(f"{field}: PROMOTE (gate {gate_pct:+.1f}% vs live {live_pct:+.1f}%)")
        else:
            verdicts.append(f"{field}: HOLD (gate {gate_pct:+.1f}% vs live {live_pct:+.1f}%)")

    print()
    print("=" * 128)
    print("STAGE 0 VERDICT:")
    print("=" * 128)
    for v in verdicts:
        print(f"  {v}")

    # ================================================================
    # Stage 1: halves-strict re-fit. Split held-out chronologically.
    # Gate must beat live on BOTH halves independently AND not lose to
    # raw on either half. Guards against a single-day dominating the
    # pooled result.
    # ================================================================
    print()
    print("=" * 128)
    print("STAGE 1 — HALVES-STRICT (chronological split of the holdout window)")
    print("=" * 128)
    mid = len(holdout_days) // 2 or 1
    half_a = holdout_days[:mid]
    half_b = holdout_days[mid:]
    print(f"half A: {half_a[0]} → {half_a[-1]}    half B: {half_b[0]} → {half_b[-1]}")
    print()

    def score_half(days_subset):
        agg = {f: {"n": 0, "raw": 0.0, "live": 0.0, "gate": 0.0} for f in CLOUD_FIELDS}
        for field in CLOUD_FIELDS:
            for lo, hi, lab in BINS:
                key = (field, lab)
                cell = live.get(field, {}).get(lab)
                if not cell or cell.get("verdict") not in ("SHIP", "MARGINAL"):
                    continue
                hist_bias = cell["mean_bias"]; hist_shift = cell["shift"]
                recent = recent_bias.get(key)
                pairs = []
                for d in days_subset:
                    pairs.extend(rows.get((d, field, lab), []))
                n = len(pairs)
                if n < MIN_N_CELL:
                    continue
                m_raw = mae(pairs, 0.0); m_live = mae(pairs, hist_shift)
                if recent is None:
                    gate_apply = True
                else:
                    sign_ok = (recent > 0 and hist_bias > 0) or (recent < 0 and hist_bias < 0)
                    mag_ok  = abs(recent) >= GATE_RATIO * abs(hist_bias)
                    gate_apply = sign_ok and mag_ok
                m_gate = mae(pairs, hist_shift if gate_apply else 0.0)
                agg[field]["n"] += n
                agg[field]["raw"]  += m_raw  * n
                agg[field]["live"] += m_live * n
                agg[field]["gate"] += m_gate * n
        out = {}
        for f, a in agg.items():
            if a["n"] == 0: continue
            r = a["raw"]/a["n"]; l = a["live"]/a["n"]; g = a["gate"]/a["n"]
            out[f] = {
                "n": a["n"],
                "raw_pct":  0.0,
                "live_pct": 100.0*(r-l)/r if r>0 else 0.0,
                "gate_pct": 100.0*(r-g)/r if r>0 else 0.0,
                "gate_beats_raw": g <= r,
            }
        return out

    a_scores = score_half(half_a)
    b_scores = score_half(half_b)

    print(f"{'field':<6} {'n_A':>6} {'A_live%':>8} {'A_gate%':>8}    "
          f"{'n_B':>6} {'B_live%':>8} {'B_gate%':>8}    verdict")
    print("-" * 100)
    stage1 = []
    for f in CLOUD_FIELDS:
        a = a_scores.get(f); b = b_scores.get(f)
        if not a or not b:
            print(f"{f:<6}  insufficient halves data")
            continue
        # Halves-strict: gate must not-lose-to-raw on BOTH halves, and
        # gate must be >= live on both halves (either both benefit or
        # both are equal, no half where gate is materially worse).
        raw_safe = a["gate_beats_raw"] and b["gate_beats_raw"]
        beats_live_A = a["gate_pct"] >= a["live_pct"] - TOLERANCE_PCT
        beats_live_B = b["gate_pct"] >= b["live_pct"] - TOLERANCE_PCT
        if raw_safe and beats_live_A and beats_live_B and (a["gate_pct"] > 0 or b["gate_pct"] > 0):
            v = "STAGE 1 PROMOTE"
        elif raw_safe:
            v = "HOLD (safe but no gain)"
        else:
            v = "FAIL (loses to raw on a half)"
        stage1.append((f, v))
        print(f"{f:<6} {a['n']:>6} {a['live_pct']:>+7.1f}% {a['gate_pct']:>+7.1f}%    "
              f"{b['n']:>6} {b['live_pct']:>+7.1f}% {b['gate_pct']:>+7.1f}%    {v}")

    print()
    print("=" * 128)
    print("STAGE 1 VERDICT:")
    print("=" * 128)
    for f, v in stage1:
        print(f"  {f}: {v}")


if __name__ == "__main__":
    main()
