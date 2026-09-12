"""Stage 0 — direct held-out MAE as the recent-bias gate suppression rule.

CLOSED MISS 2026-08-17 same-day. See project_lc_gate_rule_direct_mae memory.
The Stage 0 "+8.8% cm" verdict below is inflated by leakage — the rule uses
holdout MAE both to DECIDE suppression AND to SCORE it, so of course the
direct-MAE rule "wins" when we let it peek at the answer. Honest Stage 1
walk (h_lc_gate_rule_stage1.py, retracted note there too) uses recent-3d
for decision + disjoint holdout-3d for scoring, and the proposed rule
makes the same decisions as the current bias-ratio rule at every cutoff.
cm's walker churn is a real feature of cm's regime volatility, not a bug
in the gate rule. Script kept as an artifact + as the honest-harness for
future gate-rule ideas.


Current gate rule in `h_lc_recent_bias_gate.py`:
  gate_apply = sign_ok AND (|recent_bias| >= 0.5 * |historical_bias|)

Where sign_ok = recent and historical bias have same sign, and the magnitude
check is a proxy for "recent bias still matches the historical fit's premise."
Fails silently when signs match and magnitudes are close but the SPECIFIC
recent obs pattern makes live's shift over-correct — a case the ratio can't
see. Concrete failure this morning: cm/50-80 had hist_bias +42.8, recent
+44.7 (ratio 1.04, sign OK → gate says "on"), but live shift produced
holdout MAE 39.84 vs raw 30.40 (Lc HURTS by 31%). Same for cm/95-100 which
defaulted to "on" because recent was thin.

Proposed rule:
  gate_apply = m_live <= m_raw * MARGIN

Where m_raw and m_live are the actual held-out MAE on the last HOLDOUT_DAYS
of the pair log for this (field, bin), computed EXACTLY as the walker
already does (lines 166-167 of h_lc_recent_bias_gate.py). If applying live's
shift makes holdout MAE worse, suppress. Simpler, direct, no bias-magnitude
proxy.

Verdict:
  STAGE 0 HIT — proposed rule beats current on ≥1 field pool by ≥ FIELD_WIN_PCT
                AND doesn't lose to current on any other field by ≥ FIELD_LOSS_PCT.
  MISS        — otherwise.

Run:
    python3 -m analysis.h_lc_gate_rule_stage0
"""
import json
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
LIVE_TABLE_PATH = os.path.join(os.path.dirname(SCRIPT_DIR),
                               "weather_collector", "data", "lc_correction_table.json")
OUT_TXT = os.path.join(SCRIPT_DIR, "output", "h_lc_gate_rule_stage0.txt")

CLOUD_FIELDS = ["cc", "cl", "cm", "ch"]
BINS = [(0, 5, "0-5"), (5, 20, "5-20"), (20, 50, "20-50"),
        (50, 80, "50-80"), (80, 95, "80-95"), (95, 100.01, "95-100")]

RECENT_DAYS = 3     # match walker
HOLDOUT_DAYS = 3    # match walker
MIN_N_CELL = 30     # match walker
GATE_RATIO = 0.5    # match walker (current-rule threshold)
MARGIN = 1.05       # proposed-rule margin: suppress if m_live > m_raw × MARGIN

FIELD_WIN_PCT = 2.0
FIELD_LOSS_PCT = 1.0


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


def main():
    live = json.loads(open(LIVE_TABLE_PATH).read())["cells"]

    rows = defaultdict(list)
    with open(cached_path(PAIR_LOG_URL)) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            fld = r.get("field")
            if fld not in CLOUD_FIELDS:
                continue
            fc = load_fc(r)
            obs = r.get("observed")
            ot = r.get("obs_time")
            if fc is None or obs is None or not ot:
                continue
            b = bin_of(float(fc))
            if b is None:
                continue
            rows[(ot[:10], fld, b)].append((float(fc), float(obs)))

    all_days = sorted({k[0] for k in rows.keys()})
    if len(all_days) < RECENT_DAYS + HOLDOUT_DAYS:
        print(f"insufficient days: {len(all_days)}")
        return
    holdout_days = all_days[-HOLDOUT_DAYS:]
    recent_days = all_days[-(HOLDOUT_DAYS + RECENT_DAYS):-HOLDOUT_DAYS]

    lines = []
    def p(s): lines.append(s); print(s)

    p(f"h_lc_gate_rule_stage0 — direct-MAE gate rule vs current bias-ratio rule")
    p(f"Recent window: {recent_days[0]} → {recent_days[-1]}   Holdout: {holdout_days[0]} → {holdout_days[-1]}")
    p(f"Current rule: gate_apply = sign_ok AND |recent| >= {GATE_RATIO} × |hist|")
    p(f"Proposed rule: gate_apply = m_live <= m_raw × {MARGIN}")
    p("")
    p(f"{'field':<6}{'bin':<10}{'n':>6}{'hist_bias':>10}{'recent':>8}"
      f"{'m_raw':>8}{'m_live':>8}{'cur':>6}{'prop':>6}{'note':>16}")
    p("-" * 84)

    per_field = {f: {"n": 0, "raw": 0.0, "live": 0.0,
                     "gate_cur": 0.0, "gate_prop": 0.0,
                     "flips": 0} for f in CLOUD_FIELDS}
    disagreements = []

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
                pairs_recent.extend(rows.get((d, field, lab), []))
            recent = (sum(fc - obs for fc, obs in pairs_recent) / len(pairs_recent)
                      if len(pairs_recent) >= MIN_N_CELL else None)

            pairs_hold = []
            for d in holdout_days:
                pairs_hold.extend(rows.get((d, field, lab), []))
            n = len(pairs_hold)
            if n < MIN_N_CELL:
                continue

            m_raw = mae(pairs_hold, 0.0)
            m_live = mae(pairs_hold, hist_shift)

            # Current rule
            if recent is None:
                cur_apply = True
                cur_reason = "thin"
            else:
                sign_ok = (recent > 0 and hist_bias > 0) or (recent < 0 and hist_bias < 0)
                mag_ok = abs(recent) >= GATE_RATIO * abs(hist_bias)
                cur_apply = sign_ok and mag_ok
                cur_reason = ("on" if cur_apply else
                              ("sign" if not sign_ok else "mag"))

            # Proposed rule
            prop_apply = m_live <= m_raw * MARGIN
            prop_reason = "on" if prop_apply else "mae"

            m_gate_cur = m_live if cur_apply else m_raw
            m_gate_prop = m_live if prop_apply else m_raw

            flip = "" if cur_apply == prop_apply else ("CUR→OFF" if not prop_apply else "OFF→ON")
            if flip:
                disagreements.append((field, lab, cur_apply, prop_apply, m_raw, m_live, n))

            recent_s = f"{recent:+.1f}" if recent is not None else "n/a"
            p(f"{field:<6}{lab:<10}{n:>6}{hist_bias:>+10.1f}{recent_s:>8}"
              f"{m_raw:>8.2f}{m_live:>8.2f}{cur_reason:>6}{prop_reason:>6}{flip:>16}")

            per_field[field]["n"] += n
            per_field[field]["raw"] += m_raw * n
            per_field[field]["live"] += m_live * n
            per_field[field]["gate_cur"] += m_gate_cur * n
            per_field[field]["gate_prop"] += m_gate_prop * n
            if flip:
                per_field[field]["flips"] += 1

    p("")
    p(f"FIELD POOLED (weighted by n):")
    p(f"{'field':<6}{'n':>7}{'raw':>8}{'live':>8}{'cur':>8}{'prop':>8}"
      f"{'cur vs raw':>12}{'prop vs raw':>13}{'prop vs cur':>13}{'flips':>7}")
    p("-" * 90)
    field_verdicts = []
    for field in CLOUD_FIELDS:
        a = per_field[field]
        if a["n"] == 0:
            continue
        raw = a["raw"] / a["n"]
        live_p = a["live"] / a["n"]
        cur = a["gate_cur"] / a["n"]
        prop = a["gate_prop"] / a["n"]
        cvr = 100 * (raw - cur) / raw if raw else 0
        pvr = 100 * (raw - prop) / raw if raw else 0
        pvc = 100 * (cur - prop) / cur if cur else 0
        p(f"{field:<6}{a['n']:>7}{raw:>8.2f}{live_p:>8.2f}{cur:>8.2f}{prop:>8.2f}"
          f"{cvr:>+11.1f}%{pvr:>+12.1f}%{pvc:>+12.1f}%{a['flips']:>7}")
        field_verdicts.append((field, pvc, cvr, pvr))
    p("")

    # Verdict
    wins = [f for f, pvc, _, _ in field_verdicts if pvc >= FIELD_WIN_PCT]
    losses = [f for f, pvc, _, _ in field_verdicts if pvc <= -FIELD_LOSS_PCT]
    if wins and not losses:
        p(f"VERDICT: STAGE 0 HIT — proposed direct-MAE rule wins on {wins} "
          f"(≥{FIELD_WIN_PCT}% vs current) with no field losing (≥{FIELD_LOSS_PCT}%). "
          f"Advance to Stage 1: walk 7 daily cutoffs to confirm rule is stable, "
          f"not just today-lucky.")
    elif wins and losses:
        p(f"VERDICT: MIXED — proposed rule wins on {wins} but loses on {losses}. "
          f"Consider field-conditional rule or margin sweep.")
    else:
        p(f"VERDICT: MISS — proposed rule doesn't materially beat current rule. "
          f"Current bias-ratio gate is fine as-is.")

    if disagreements:
        p("")
        p(f"Cell disagreements (n={len(disagreements)}) — where the two rules differ:")
        for f, b, cur, prop, mr, ml, n in disagreements:
            direction = "current keeps, proposed suppresses" if not prop else "current suppresses, proposed keeps"
            p(f"  {f}/{b}  {direction}   m_raw={mr:.2f}  m_live={ml:.2f}  n={n}")

    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    p(f"\nwrote {OUT_TXT}")


if __name__ == "__main__":
    main()
