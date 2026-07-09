"""Multi-window simulation for the Stage 1 → Stage 2 promotion gate.

For each of the last 7 daily cutoffs, computes verdicts on the 7-day trailing
window ending at that cutoff. Three hypotheses tracked simultaneously in a
single pair-log pass:

  • L5 — regime-conditional solar correction (uses compute_solar_correction)
  • R5 — cove temperature delta (uses compute_cove_correction + cove log)
  • R6 — regime-transition penalty (stable vs transition MAE by field × band)

Promotion gate: a hypothesis is "stable" only if all 7 cutoff verdicts agree
(all SHIP or all HOLD; any flicker = stay at Stage 1). This is the test the
L5 SHIP/HOLD ambiguity revealed we need.

Usage:
  python3 -m analysis.simulate_windows
  MYWEATHER_REFRESH=1 python3 -m analysis.simulate_windows   # force fresh
"""
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path, CACHE_DIR

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from weather_collector.processors.solar_correction import compute_solar_correction, SUN_UP_THRESHOLD
from weather_collector.processors.cove_correction import compute_cove_correction

ERROR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
COVE_LOG_URL  = "https://data.wymancove.com/cove_gradient_log.json"

N_CUTOFFS = 7        # number of trailing daily cutoffs
WINDOW_DAYS = 7      # window size in days, ending at each cutoff

# Verdict thresholds — same as the production audits.
L5_OVERALL_SHIP_PCT = 5.0    # ≥ 5% overall MAE drop
L5_REGIME_SHIP_PCT  = 3.0    # ≥ 3% drop per regime
L5_REGIMES_NEEDED   = 5      # ≥ 5 of 8 regimes improving
R5_SHIP_PCT         = 1.0    # ≥ 1% improvement on baseline
R5_MIN_PAIRS        = 200
R6_PENALTY_PCT      = 10.0   # ≥ 10% transition penalty
R6_MIN_PER_BUCKET   = 200
R6_MIN_FLAGGED      = 10     # at least 10 buckets must trip

BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]

HOUR_KEY_LEN = 13  # len("2026-06-16T15")


def _band_for(lead_h):
    for label, lo, hi in BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def _print_cache_age():
    path = CACHE_DIR / ERROR_LOG_URL.rsplit("/", 1)[-1]
    if not path.exists():
        return
    age_h = (time.time() - path.stat().st_mtime) / 3600
    size_mb = path.stat().st_size / (1024 * 1024)
    age_str = f"{int(age_h * 60)}m ago" if age_h < 1 else f"{age_h:.1f}h ago"
    print(f"📦 pair log: cached {age_str} ({size_mb:.0f} MB)")
    if age_h > 24:
        print("   ⚠ stale — re-run with MYWEATHER_REFRESH=1 for decision-grade output")


def _load_cove_conditions():
    """Return dict: 'YYYY-MM-DDTHH' → (wind_dir_deg, sb_active, hour_local)."""
    print("Loading cove conditions...")
    doc = json.load(open(cached_path(COVE_LOG_URL)))
    out = {}
    for e in (doc.get("entries") or []):
        ts = e.get("ts") or ""
        if len(ts) < HOUR_KEY_LEN:
            continue
        key = ts[:HOUR_KEY_LEN]
        out[key] = (e.get("wind_dir_deg"), bool(e.get("sb_active")), e.get("hour_local"))
    print(f"  {len(out):,} hour-keyed cove condition entries")
    return out


def main():
    print("=" * 78)
    print("Simulate-windows: 7 trailing daily cutoffs × 7-day windows")
    print("=" * 78)

    path = cached_path(ERROR_LOG_URL)
    _print_cache_age()
    cove = _load_cove_conditions()

    today = datetime.utcnow().date()
    # Cutoffs: oldest first → newest. cutoffs[0] = 6 days ago, cutoffs[-1] = today.
    cutoffs = [today - timedelta(days=N_CUTOFFS - 1 - i) for i in range(N_CUTOFFS)]
    print(f"Cutoffs: {cutoffs[0].isoformat()} → {cutoffs[-1].isoformat()}  ({N_CUTOFFS} windows)\n")

    # Per-cutoff accumulators:
    # L5: regime → [sum_base, sum_l5, n]   (regime-keyed)
    # R5: bucket "all" → [sum_base, sum_r5, n]
    # R6: (field, band, is_transition) → [sum_abs_err, n]
    L5 = [defaultdict(lambda: [0.0, 0.0, 0]) for _ in range(N_CUTOFFS)]
    R5 = [defaultdict(lambda: [0.0, 0.0, 0]) for _ in range(N_CUTOFFS)]
    R6 = [defaultdict(lambda: [0.0, 0]) for _ in range(N_CUTOFFS)]

    scanned = 0
    used = 0

    with open(path) as f:
        for line in f:
            scanned += 1
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            obs_time = p.get("obs_time") or ""
            if len(obs_time) < 10:
                continue
            try:
                obs_date = datetime.strptime(obs_time[:10], "%Y-%m-%d").date()
            except ValueError:
                continue

            # Which cutoffs include this pair? Pair belongs to cutoff c if
            # c - WINDOW_DAYS <= obs_date <= c. Pre-compute the index range.
            applicable = [i for i, c in enumerate(cutoffs)
                          if (c - timedelta(days=WINDOW_DAYS)) <= obs_date <= c]
            if not applicable:
                continue

            sfc = p.get("state_fc") or {}
            sob = p.get("state_obs") or {}
            field = p.get("field")
            lead = p.get("lead_h")
            band = _band_for(lead) if lead is not None else None

            # ---- R6 (regime transition) — needs both regimes + final error ----
            rfc = sfc.get("regime_synoptic")
            rob = sob.get("regime_synoptic")
            err = p.get("error")
            if rfc and rob and field and band and err is not None:
                is_trans = (rfc != rob)
                key = (field, band, is_trans)
                for i in applicable:
                    R6[i][key][0] += abs(err)
                    R6[i][key][1] += 1
                used += 1

            # ---- L5 (solar) — solar field, lead ≥ 1, sun up, regime_fc present ----
            err_l4 = p.get("error_l4")
            forecast_l1 = p.get("forecast_l1")
            if (field == "sr" and lead is not None and lead >= 1
                    and err_l4 is not None and forecast_l1 is not None
                    and rfc and forecast_l1 >= SUN_UP_THRESHOLD):
                hour_local = sfc.get("hour_local")
                delta = compute_solar_correction(rfc, forecast_l1, hour_local)
                base = abs(err_l4)
                with_l5 = abs(err_l4 + delta)
                for i in applicable:
                    L5[i][rfc][0] += base
                    L5[i][rfc][1] += with_l5
                    L5[i][rfc][2] += 1

            # ---- R5 (cove) — temp field, has cove conditions matching obs hour ----
            err_l4_t = p.get("error_l4")
            if field == "t" and err_l4_t is not None:
                key = obs_time[:HOUR_KEY_LEN]
                cond = cove.get(key)
                if cond:
                    wind_dir, sb_active, hour_local = cond
                    if wind_dir is not None and hour_local is not None:
                        delta = compute_cove_correction(wind_dir, sb_active, hour_local)
                        base = abs(err_l4_t)
                        with_r5 = abs(err_l4_t + delta)
                        for i in applicable:
                            R5[i]["all"][0] += base
                            R5[i]["all"][1] += with_r5
                            R5[i]["all"][2] += 1

    print(f"Scanned {scanned:,} pairs · contributed to at least one window: {used:,}\n")

    # ─── Compute verdicts per cutoff ─────────────────────────────────────────

    def l5_verdict(acc):
        # acc: regime → [base, with_l5, n]
        # Per-cell verdict: aggregate wins hide per-regime damage, so ship
        # requires overall + ≥5 regimes winning + NO regime losing ≥3%. The
        # loss-check catches the failure mode that pre-ship-gate was blind to
        # in the June 28 L5 ship (ne_flow +32% worse showed up post-ship;
        # the aggregate cleared the gate cleanly).
        total_b = sum(v[0] for v in acc.values())
        total_l5 = sum(v[1] for v in acc.values())
        total_n = sum(v[2] for v in acc.values())
        if total_n < 1000:
            return ("INSUF", 0.0, 0, 0, total_n)
        overall_pct = 100.0 * (total_b - total_l5) / total_b if total_b else 0.0
        regimes_winning = 0
        regimes_losing  = 0
        losing_regimes = []
        for r, (b, l5_, n) in acc.items():
            if n < 100 or b == 0:
                continue
            pct = 100.0 * (b - l5_) / b
            if pct >= L5_REGIME_SHIP_PCT:
                regimes_winning += 1
            elif pct <= -L5_REGIME_SHIP_PCT:
                regimes_losing += 1
                losing_regimes.append((r, pct))
        ship = (overall_pct >= L5_OVERALL_SHIP_PCT
                and regimes_winning >= L5_REGIMES_NEEDED
                and regimes_losing == 0)
        return ("SHIP" if ship else "HOLD", overall_pct, regimes_winning, regimes_losing, total_n)

    def r5_verdict(acc):
        b, w, n = acc.get("all", [0, 0, 0])
        if n < R5_MIN_PAIRS:
            return ("INSUF", 0.0, n)
        pct = 100.0 * (b - w) / b if b else 0.0
        return ("SHIP" if pct >= R5_SHIP_PCT else "HOLD", pct, n)

    def r6_verdict(acc):
        # Count buckets with ≥10% penalty AND both sides ≥ MIN.
        flagged = 0
        evaluated = 0
        for field in {k[0] for k in acc.keys()}:
            for band, _, _ in BANDS:
                s = acc.get((field, band, False), [0, 0])
                t = acc.get((field, band, True),  [0, 0])
                if s[1] < R6_MIN_PER_BUCKET or t[1] < R6_MIN_PER_BUCKET:
                    continue
                evaluated += 1
                mae_s = s[0] / s[1]
                mae_t = t[0] / t[1]
                if mae_s > 0 and 100.0 * (mae_t - mae_s) / mae_s >= R6_PENALTY_PCT:
                    flagged += 1
        return ("SHIP" if flagged >= R6_MIN_FLAGGED else "HOLD", flagged, evaluated)

    # ─── Render ──────────────────────────────────────────────────────────────

    print(f"{'Cutoff':<14} {'L5':<32} {'R5':<24} {'R6':<24}")
    print("-" * 96)
    l5_verdicts, r5_verdicts, r6_verdicts = [], [], []
    for i, c in enumerate(cutoffs):
        v_l5, pct_l5, reg_l5, loss_l5, n_l5 = l5_verdict(L5[i])
        v_r5, pct_r5, n_r5 = r5_verdict(R5[i])
        v_r6, flag_r6, ev_r6 = r6_verdict(R6[i])
        l5_verdicts.append(v_l5)
        r5_verdicts.append(v_r5)
        r6_verdicts.append(v_r6)
        l5_str = f"{v_l5}  {pct_l5:+5.1f}%  {reg_l5}W/{loss_l5}L/8r  n={n_l5:,}"
        r5_str = f"{v_r5}  {pct_r5:+5.1f}%  n={n_r5:,}"
        r6_str = f"{v_r6}  {flag_r6}/{ev_r6} buckets"
        print(f"{c.isoformat():<14} {l5_str:<32} {r5_str:<24} {r6_str:<24}")

    # ─── Agreement summary ───────────────────────────────────────────────────

    # Hypotheses whose signal is already shipped in a different form. The
    # simulate_windows Stage 1 check is still valuable — it's a health readout
    # for the axis/layer that DID ship — but "PROMOTE" is the wrong verb since
    # promoting again would double-count. See feedback_stated_intent_vs_code_behavior.
    ALREADY_SHIPPED_AS = {
        # R6 (regime-transition penalty) pivoted from would-be bias correction
        # to confidence axis C1a on 2026-06-19 v0.6.141. The transition signal
        # is live via confidence_layer.py C1a; promoting R6 as a bias
        # correction would either duplicate C1a or reverse the pivot decision.
        "R6": "C1a — Regime transition (confidence axis, live since v0.6.141 2026-06-19)",
    }

    print()
    print("=" * 96)
    print("PROMOTION-GATE VERDICT (7-window agreement required for Stage 1 → Stage 2):")
    print()
    for name, verdicts in [("L5", l5_verdicts), ("R5", r5_verdicts), ("R6", r6_verdicts)]:
        unique = set(verdicts)
        shipped_as = ALREADY_SHIPPED_AS.get(name)
        if len(unique) == 1:
            v = next(iter(unique))
            if shipped_as:
                # Live axis / layer already ships this signal. Reinterpret SHIP
                # as a health check pass; HOLD as a regression warning.
                if v == "SHIP":
                    print(f"  {name}: all 7 cutoffs agree → SHIP    → STABLE "
                          f"({name} signal already live as {shipped_as}; this is a health check pass)")
                elif v == "HOLD":
                    print(f"  {name}: all 7 cutoffs agree → HOLD    → REGRESSION WATCH "
                          f"({name} signal already live as {shipped_as}; underlying signal weakened)")
                else:
                    print(f"  {name}: all 7 cutoffs agree → {v}    → INSUF "
                          f"({name} signal already live as {shipped_as})")
            else:
                status = "PROMOTE" if v == "SHIP" else "RETIRE" if v == "HOLD" else "INSUF"
                print(f"  {name}: all 7 cutoffs agree → {v}    → {status}")
        else:
            counts = {v: verdicts.count(v) for v in unique}
            counts_str = ", ".join(f"{v}={n}" for v, n in counts.items())
            note = f" ({name} signal already live as {shipped_as})" if shipped_as else ""
            print(f"  {name}: FLICKER ({counts_str})    → stay at Stage 1; do not promote{note}")


if __name__ == "__main__":
    main()
