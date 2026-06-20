"""
Orthogonality check: is cluster-spread signal additive to L6's existing
R6 regime-transition signal, or redundant with it?

Background: cluster_spread_smoketest.py returned 18/20 (field, band)
combinations SMOKE_ALIVE with Q4/Q1 MAE ratios up to 3.14×. If those
high-spread ticks are the same ticks where state_fc.regime_synoptic
!= state_obs.regime_synoptic (R6's transition signal), then L6 already
captures it — cluster-spread is redundant, not orthogonal.

Method:
  1. Build same per-tick spread table as smoke test (temp delta std
     across Marblehead / Salem / Swampscott cluster medians).
  2. Stream pair log, filter to 2-day overlap window.
  3. For each pair entry, tag with:
       spread_quartile : Q1_low | Q4_high | mid (mid discarded)
       transition      : True if state_fc.regime_synoptic != state_obs.regime_synoptic
  4. Cross-tab MAE by (field, lead_band, spread_quartile, transition).
  5. For each (field, band): does Q4/Q1 ratio hold *within* the
     transition=False subset? If yes → orthogonal. If ratio collapses
     to ~1.0 on transition=False → redundant with R6.

Verdict per (field, band):
  ORTHOGONAL    — Q4/Q1 ratio >= 1.20 within transition=False AND
                  within transition=True. Cluster-spread is a separate signal.
  REDUNDANT     — Q4/Q1 ratio drops below 1.10 within transition=False.
                  All apparent inflation is just R6 in disguise.
  CONFOUNDED    — Q4/Q1 only inflated within transition=True. Cluster-spread
                  acts as a transition-amplifier, not an independent axis.
  THIN          — Insufficient sample in one or more subsets.

Overall: PROMOTE if ≥3 (field, band) ORTHOGONAL. KILL if ≥80% REDUNDANT.
Else AMBIGUOUS — needs the persistent logger + 7-day data for cleaner read.
"""
import json
import os
import sys
from collections import defaultdict
from statistics import median, pstdev

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
STATION_HISTORY_URL = "https://data.wymancove.com/station_history.json"

CLUSTERS = ("KMAMARBL", "KMASALEM", "KMASWAMP")
FIELDS_TO_TEST = ("t", "h", "ws", "wg", "dp")
LEAD_BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]


def _cluster_of(sid):
    for c in CLUSTERS:
        if sid.startswith(c):
            return c
    return None


def _tick_key(ts_iso):
    return ts_iso[:16]


def _shift_tick(tick_iso_min, delta_min):
    from datetime import datetime, timedelta
    dt = datetime.strptime(tick_iso_min, "%Y-%m-%dT%H:%M")
    return (dt + timedelta(minutes=delta_min)).strftime("%Y-%m-%dT%H:%M")


def build_spread_table(station_history):
    by_tick = defaultdict(lambda: defaultdict(list))
    for sid, readings in station_history.items():
        cluster = _cluster_of(sid)
        if not cluster:
            continue
        for r in readings:
            ts = r.get("ts")
            v = r.get("delta")
            if ts is None or v is None:
                continue
            by_tick[_tick_key(ts)][cluster].append(v)
    spread_by_tick = {}
    for tick, clusters in by_tick.items():
        medians = [median(vs) for vs in clusters.values() if vs]
        if len(medians) < 2:
            continue
        spread_by_tick[tick] = pstdev(medians)
    return spread_by_tick


def quartile_thresholds(values):
    s = sorted(values)
    n = len(s)
    return s[n // 4], s[(3 * n) // 4]


def lead_band(lead_h):
    for label, lo, hi in LEAD_BANDS:
        if lo <= lead_h < hi:
            return label
    return None


def main():
    print("=" * 78)
    print("CLUSTER-SPREAD × R6-TRANSITION ORTHOGONALITY CHECK")
    print("=" * 78)

    print("\n[1/4] Loading station_history.json + building spread table...")
    sh_path = cached_path(STATION_HISTORY_URL)
    with open(sh_path) as f:
        station_history = json.load(f)
    spread_t = build_spread_table(station_history)
    q1, q4 = quartile_thresholds(list(spread_t.values()))
    ticks_sorted = sorted(spread_t.keys())
    min_tick, max_tick = ticks_sorted[0], ticks_sorted[-1]
    print(f"  {len(spread_t)} ticks, Q1≤{q1:.3f}, Q4≥{q4:.3f} °F, "
          f"window {min_tick} → {max_tick}")

    print("\n[2/4] Streaming pair log, joining spread × transition...")
    pair_log_path = cached_path(PAIR_LOG_URL)

    # agg[(field, band, quartile, transition_str)] -> list of |error|
    agg = defaultdict(list)
    # Also count tick distribution
    transition_hits = {"Q1_low": {"T": 0, "S": 0}, "Q4_high": {"T": 0, "S": 0}}

    with open(pair_log_path) as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue
            obs_time = row.get("obs_time")
            if obs_time is None:
                continue
            tick = obs_time[:16]
            if tick < min_tick or tick > max_tick:
                continue
            field = row.get("field")
            if field not in FIELDS_TO_TEST:
                continue
            err = row.get("error")
            lead_h = row.get("lead_h")
            if err is None or lead_h is None:
                continue
            band = lead_band(lead_h)
            if band is None:
                continue
            spread = spread_t.get(tick)
            if spread is None:
                for d in (10, -10, 20, -20):
                    cand = _shift_tick(tick, d)
                    if cand in spread_t:
                        spread = spread_t[cand]
                        break
            if spread is None:
                continue
            if spread <= q1:
                bin_label = "Q1_low"
            elif spread >= q4:
                bin_label = "Q4_high"
            else:
                continue
            state_fc = row.get("state_fc") or {}
            state_obs = row.get("state_obs") or {}
            fc_reg = state_fc.get("regime_synoptic")
            obs_reg = state_obs.get("regime_synoptic")
            if fc_reg is None or obs_reg is None:
                continue
            trans = "T" if fc_reg != obs_reg else "S"
            agg[(field, band, bin_label, trans)].append(abs(err))
            transition_hits[bin_label][trans] += 1

    print(f"  done. pair rows joined: {sum(len(v) for v in agg.values()):,}")

    # Co-occurrence summary
    q1_total = transition_hits["Q1_low"]["T"] + transition_hits["Q1_low"]["S"]
    q4_total = transition_hits["Q4_high"]["T"] + transition_hits["Q4_high"]["S"]
    if q1_total and q4_total:
        p_trans_q1 = transition_hits["Q1_low"]["T"] / q1_total
        p_trans_q4 = transition_hits["Q4_high"]["T"] / q4_total
        print(f"\n  P(transition | Q1_low spread)  = {p_trans_q1:.1%}  "
              f"(n={q1_total:,})")
        print(f"  P(transition | Q4_high spread) = {p_trans_q4:.1%}  "
              f"(n={q4_total:,})")
        print(f"  delta = {(p_trans_q4 - p_trans_q1)*100:+.1f} pct points")
        if p_trans_q4 - p_trans_q1 > 0.3:
            print("  → high spread strongly co-occurs with R6 transition; "
                  "watch for redundancy below.")
        elif p_trans_q4 - p_trans_q1 < 0.1:
            print("  → spread and transition are roughly independent; "
                  "expect ORTHOGONAL verdicts.")

    print("\n[3/4] Per-(field, band) MAE Q1 vs Q4 split by R6 transition flag:")
    print(f"  {'field':<5} {'band':<8} "
          f"{'S_Q1_n':>7} {'S_Q1':>7} {'S_Q4_n':>7} {'S_Q4':>7} {'S_r':>6} "
          f"{'T_Q1_n':>7} {'T_Q1':>7} {'T_Q4_n':>7} {'T_Q4':>7} {'T_r':>6} "
          f"{'verdict':<11}")

    counts = {"ORTHOGONAL": 0, "REDUNDANT": 0, "CONFOUNDED": 0,
              "THIN": 0, "AMBIGUOUS": 0}

    def _mae(items):
        return (sum(items) / len(items)) if items else None

    def _safe_ratio(a, b):
        if a is None or b is None or b <= 0:
            return None
        return a / b

    for field in FIELDS_TO_TEST:
        for band_label, _, _ in LEAD_BANDS:
            sq1 = agg.get((field, band_label, "Q1_low", "S"), [])
            sq4 = agg.get((field, band_label, "Q4_high", "S"), [])
            tq1 = agg.get((field, band_label, "Q1_low", "T"), [])
            tq4 = agg.get((field, band_label, "Q4_high", "T"), [])
            sq1_n, sq4_n, tq1_n, tq4_n = len(sq1), len(sq4), len(tq1), len(tq4)
            sq1_mae = _mae(sq1)
            sq4_mae = _mae(sq4)
            tq1_mae = _mae(tq1)
            tq4_mae = _mae(tq4)
            s_ratio = _safe_ratio(sq4_mae, sq1_mae)
            t_ratio = _safe_ratio(tq4_mae, tq1_mae)

            # Verdict logic
            min_subset = min(sq1_n, sq4_n)
            if min_subset < 50:
                verdict = "THIN"
            else:
                stable_inflated = s_ratio is not None and s_ratio >= 1.20
                stable_flat = s_ratio is not None and s_ratio < 1.10
                trans_inflated = (t_ratio is not None and t_ratio >= 1.20
                                  and tq1_n >= 50 and tq4_n >= 50)
                if stable_inflated:
                    verdict = "ORTHOGONAL"
                elif stable_flat and trans_inflated:
                    verdict = "CONFOUNDED"
                elif stable_flat:
                    verdict = "REDUNDANT"
                else:
                    verdict = "AMBIGUOUS"
            counts[verdict] += 1

            def fmt(x, w=7, p=3):
                return (f"{x:>{w}.{p}f}" if x is not None else f"{'—':>{w}}")

            print(f"  {field:<5} {band_label:<8} "
                  f"{sq1_n:>7} {fmt(sq1_mae)} {sq4_n:>7} {fmt(sq4_mae)} "
                  f"{fmt(s_ratio, 6, 2)} "
                  f"{tq1_n:>7} {fmt(tq1_mae)} {tq4_n:>7} {fmt(tq4_mae)} "
                  f"{fmt(t_ratio, 6, 2)} {verdict:<11}")

    print("\n[4/4] Overall verdict:")
    print(f"  ORTHOGONAL: {counts['ORTHOGONAL']}, "
          f"CONFOUNDED: {counts['CONFOUNDED']}, "
          f"REDUNDANT: {counts['REDUNDANT']}, "
          f"AMBIGUOUS: {counts['AMBIGUOUS']}, "
          f"THIN: {counts['THIN']}")
    print()
    total_judgeable = sum(counts[k] for k in ("ORTHOGONAL", "CONFOUNDED",
                                              "REDUNDANT", "AMBIGUOUS"))
    if counts["ORTHOGONAL"] >= 3:
        print("  → SHIP PERSISTENT LOGGER: cluster-spread is genuinely additive to R6.")
    elif total_judgeable and counts["REDUNDANT"] / max(total_judgeable, 1) >= 0.8:
        print("  → KILL: cluster-spread is mostly redundant with R6 transition signal.")
    elif counts["CONFOUNDED"] > counts["ORTHOGONAL"]:
        print("  → AMBIGUOUS but leaning confound: spread amplifies R6 rather than")
        print("    being independent of it. Persistent logger could still be useful")
        print("    as a magnitude proxy for R6, but not as a new axis. Decide later.")
    else:
        print("  → AMBIGUOUS: 2-day window too thin for clean read. Ship persistent")
        print("    logger and re-evaluate at n=7+ days.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
