"""Stage 1 — walk 7 daily cutoffs of the direct-MAE gate rule.

CLOSED MISS 2026-08-17 same-day. See project_lc_gate_rule_direct_mae memory.
This Stage 1 walk uses the SAME holdout window for both the decision and
the scoring at each cutoff — same leakage class as the Stage 0. Honest walk
(inline in the memory) uses recent-3d for decision + disjoint holdout-3d
for scoring, and finds the proposed rule makes zero different decisions
from the current bias-ratio rule at any cutoff. Kept as an artifact.


For each of the last 7 daily cutoffs (each pretending "today" was that day),
compute the field-level pool MAE under both the current bias-ratio rule and
the proposed direct-MAE rule. Verdict per field:
  - STABLE if proposed rule ≥ current rule on every cutoff (never loses)
  - MIXED if proposed sometimes wins, sometimes loses (compare cutoff signs)
  - UNSTABLE if proposed loses on multiple cutoffs

Ship criterion: STABLE (or MIXED with clear net win) on the field(s) that
Stage 0 identified as winners (cm today).

Run:
    python3 -m analysis.h_lc_gate_rule_stage1
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
LIVE_TABLE_PATH = os.path.join(os.path.dirname(SCRIPT_DIR),
                               "weather_collector", "data", "lc_correction_table.json")
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_lc_gate_rule_stage1.txt")

CLOUD_FIELDS = ["cc", "cl", "cm", "ch"]
BINS = [(0, 5, "0-5"), (5, 20, "5-20"), (20, 50, "20-50"),
        (50, 80, "50-80"), (80, 95, "80-95"), (95, 100.01, "95-100")]

N_CUTOFFS = 7
RECENT_DAYS = 3
HOLDOUT_DAYS = 3
MIN_N_CELL = 30
GATE_RATIO = 0.5
MARGIN = 1.05


def bin_of(v):
    for lo, hi, lab in BINS:
        if lo <= v < hi:
            return lab
    return None


def load_fc(r):
    return (r.get("forecast_l4") or r.get("forecast_l3")
            or r.get("forecast_l2") or r.get("forecast_l1"))


def mae(pairs, shift):
    if not pairs:
        return None
    return sum(abs(max(0.0, min(100.0, fc + shift)) - obs) for fc, obs in pairs) / len(pairs)


def score_cutoff(all_days, cutoff_idx, live, rows_by_day):
    """Score both rules given that 'today' is all_days[cutoff_idx].
    Returns {field: {"raw", "live", "cur", "prop", "n"}}. None if insufficient
    days before cutoff."""
    if cutoff_idx < RECENT_DAYS + HOLDOUT_DAYS:
        return None
    holdout_days = all_days[cutoff_idx - HOLDOUT_DAYS + 1: cutoff_idx + 1]
    recent_days = all_days[cutoff_idx - HOLDOUT_DAYS - RECENT_DAYS + 1: cutoff_idx - HOLDOUT_DAYS + 1]

    per_field = {f: {"n": 0, "raw": 0.0, "live": 0.0,
                     "gate_cur": 0.0, "gate_prop": 0.0} for f in CLOUD_FIELDS}
    for field in CLOUD_FIELDS:
        for lo, hi, lab in BINS:
            cell = live.get(field, {}).get(lab)
            if not cell or not isinstance(cell, dict):
                continue
            if cell.get("verdict") not in ("SHIP", "MARGINAL"):
                continue
            hist_bias = cell["mean_bias"]
            hist_shift = cell["shift"]
            pairs_recent = []
            for d in recent_days:
                pairs_recent.extend(rows_by_day.get((d, field, lab), []))
            recent = (sum(fc - obs for fc, obs in pairs_recent) / len(pairs_recent)
                      if len(pairs_recent) >= MIN_N_CELL else None)
            pairs_hold = []
            for d in holdout_days:
                pairs_hold.extend(rows_by_day.get((d, field, lab), []))
            n = len(pairs_hold)
            if n < MIN_N_CELL:
                continue
            m_raw = mae(pairs_hold, 0.0)
            m_live = mae(pairs_hold, hist_shift)
            if recent is None:
                cur_apply = True
            else:
                sign_ok = (recent > 0 and hist_bias > 0) or (recent < 0 and hist_bias < 0)
                mag_ok = abs(recent) >= GATE_RATIO * abs(hist_bias)
                cur_apply = sign_ok and mag_ok
            prop_apply = m_live <= m_raw * MARGIN
            m_cur = m_live if cur_apply else m_raw
            m_prop = m_live if prop_apply else m_raw
            per_field[field]["n"] += n
            per_field[field]["raw"] += m_raw * n
            per_field[field]["live"] += m_live * n
            per_field[field]["gate_cur"] += m_cur * n
            per_field[field]["gate_prop"] += m_prop * n
    return per_field


def main():
    live = json.loads(open(LIVE_TABLE_PATH).read())["cells"]
    rows_by_day = defaultdict(list)
    with open(cached_path(PAIR_LOG_URL)) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            fld = r.get("field")
            if fld not in CLOUD_FIELDS: continue
            fc = load_fc(r); obs = r.get("observed"); ot = r.get("obs_time")
            if fc is None or obs is None or not ot: continue
            b = bin_of(float(fc))
            if b is None: continue
            rows_by_day[(ot[:10], fld, b)].append((float(fc), float(obs)))
    all_days = sorted({k[0] for k in rows_by_day.keys()})

    lines = []
    def p(s): lines.append(s); print(s)

    p(f"h_lc_gate_rule_stage1 — walk {N_CUTOFFS} daily cutoffs, current vs proposed rule")
    p(f"Pair-log days: {all_days[0]} → {all_days[-1]}  ({len(all_days)} days)")
    p(f"Margin={MARGIN} · recent={RECENT_DAYS}d · holdout={HOLDOUT_DAYS}d · min_n={MIN_N_CELL}")
    p("")

    # Take the last N_CUTOFFS days (each is a distinct "today")
    cutoff_indices = list(range(max(0, len(all_days) - N_CUTOFFS), len(all_days)))
    cutoff_labels = [all_days[i] for i in cutoff_indices]

    # Score at each cutoff
    by_cutoff = {}  # label -> per_field
    for i, lab in zip(cutoff_indices, cutoff_labels):
        by_cutoff[lab] = score_cutoff(all_days, i, live, rows_by_day)

    for field in CLOUD_FIELDS:
        p(f"\n=== {field} ===")
        p(f"  {'cutoff':<12}{'n':>6}{'raw':>8}{'live':>8}{'cur_gate':>10}{'prop_gate':>11}"
          f"{'cur vs raw':>12}{'prop vs raw':>13}{'prop vs cur':>13}")
        gains = []
        for lab in cutoff_labels:
            pf = by_cutoff.get(lab)
            if pf is None:
                p(f"  {lab:<12}insufficient history")
                continue
            a = pf[field]
            if a["n"] == 0:
                p(f"  {lab:<12}(no eligible cells)")
                continue
            raw = a["raw"]/a["n"]; live_p = a["live"]/a["n"]
            cur = a["gate_cur"]/a["n"]; prop = a["gate_prop"]/a["n"]
            cvr = 100*(raw-cur)/raw if raw else 0
            pvr = 100*(raw-prop)/raw if raw else 0
            pvc = 100*(cur-prop)/cur if cur else 0
            gains.append(pvc)
            p(f"  {lab:<12}{a['n']:>6}{raw:>8.2f}{live_p:>8.2f}{cur:>10.2f}{prop:>11.2f}"
              f"{cvr:>+11.1f}%{pvr:>+12.1f}%{pvc:>+12.1f}%")
        if not gains:
            continue
        n_pos = sum(1 for g in gains if g > 0)
        n_neg = sum(1 for g in gains if g < -0.5)
        avg = sum(gains)/len(gains)
        if n_neg == 0 and n_pos > 0:
            v = f"STABLE ★ — proposed rule beats current on {n_pos}/{len(gains)} cutoffs, avg {avg:+.1f}%, never loses"
        elif n_neg == 0:
            v = f"NEUTRAL — rule never differs on {field} in the walk window"
        elif n_pos > n_neg:
            v = f"MIXED-POS — {n_pos} wins / {n_neg} losses, avg {avg:+.1f}%"
        else:
            v = f"UNSTABLE — {n_neg} losses / {n_pos} wins, avg {avg:+.1f}%"
        p(f"  Verdict: {v}")

    p("")
    p(f"=" * 90)
    p(f"SHIP GATE: is the proposed rule STABLE ★ (or NEUTRAL) on every field?")
    p(f"  If yes → ship the rule change to h_lc_recent_bias_gate.py.")
    p(f"  If UNSTABLE on any field → tune MARGIN or fall back to hybrid rule.")

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    p(f"\nwrote {OUT_TXT}")


if __name__ == "__main__":
    main()
