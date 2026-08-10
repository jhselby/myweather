"""
Stage 0 — Cloud bias persistence: does the model-vs-METAR cloud disagreement
at lead 0 predict the cloud forecast error at lead N?

Context (2026-06-30):
  cloud_obs_blend.blend_metar_cloud_into_hourly() mutates hourly[0] only —
  it's an obs override for the current-hour value cards display, NOT
  propagated as an L2 bias across the 48h forecast window. The
  Wyman_Cove_Engineering_TODO_Combined.txt item asks whether to promote it
  to a full per-lead L2 (apply bias = obs - raw_hrrr across all leads, with
  or without τ-decay).

  Promotion only earns its keep if a lead-0 disagreement predicts the
  forecast error at later leads — i.e. the bias is sticky enough that
  shifting future leads in the same direction reduces error. If the
  disagreement is noise (mean-reverts inside an hour), propagating it just
  injects error at non-zero leads.

Method:
  For each cloud field (cc, cl, cm, ch), stream the pair log and group rows
  by (run_time, field). For each (run, field) group we have rows at many
  leads sharing the same run.

  At lead_h == 0 (or the smallest lead in the group), bias_obs_minus_raw =
  observed - forecast_l1. (forecast_l1 is the raw HRRR; observed is the
  KBOS+KBVY blended METAR truth that the joiner uses.)

  For each later lead N in the same group, error_l1[N] = forecast_l1[N] -
  observed[N]. (Sign convention: positive error = forecast over-predicts.)

  Hypothesis: corr(bias[run, lead_0], error_l1[run, lead_N]) is positive
  and meaningful. Interpretation: when raw model under-predicts cloud now,
  it also under-predicts at lead N → propagating the bias helps.

  Report Pearson + Spearman correlations per (field, lead_N), with n and
  the implied L2-propagation MAE delta.

  Ship gate (from the TODO + page note): correlation ≥0.30 at lead 6h AND
  ≥0.15 at lead 12h on cc. If yes → promote to full L2 with τ_cc fit. If
  no → formalize hourly[0]-only as the right thing and stop calling the
  current behavior a half-built L2.

Caveats:
  - Only rows where forecast_l1 and observed are both present count.
  - Older pair-log rows don't carry forecast_l1; those are skipped silently.
  - Aggregating across all run_times treats every run as an independent
    draw — autocorrelation within a day inflates n; the correlation
    estimate is still unbiased, but confidence is a bit looser than the
    plain n suggests. Adequate for a ship-gate decision.
"""
import json
import math
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from _cache import cached_path  # noqa: E402

PAIR_LOG_URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "h_cloud_bias_persistence.txt")

CLOUD_FIELDS = ("cc", "cl", "cm", "ch")
# Lead N values at which we want corr(bias[lead_0], error_l1[lead_N]).
TARGET_LEADS = (1, 2, 3, 6, 9, 12, 18, 24, 36, 47)
# Ship gate: drives the decision.
SHIP_GATE_AT_6H = 0.30
SHIP_GATE_AT_12H = 0.15
MIN_N_PER_LEAD = 200


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sxx = syy = 0.0
    for x, y in zip(xs, ys):
        dx = x - mx
        dy = y - my
        sxy += dx * dy
        sxx += dx * dx
        syy += dy * dy
    denom = math.sqrt(sxx * syy)
    return sxy / denom if denom > 0 else None


def spearman(xs, ys):
    """Pearson on ranks. Ties get average rank."""
    n = len(xs)
    if n < 2:
        return None

    def ranks(vs):
        order = sorted(range(n), key=lambda i: vs[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vs[order[j + 1]] == vs[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1  # 1-indexed average rank
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    return pearson(ranks(xs), ranks(ys))


def main():
    print("=" * 86)
    print("STAGE 0 — Cloud bias persistence: corr(bias[lead_0], error_l1[lead_N])")
    print("=" * 86)
    print(f"\nShip gate: ρ ≥ {SHIP_GATE_AT_6H} at lead 6h AND ρ ≥ {SHIP_GATE_AT_12H} at lead 12h on cc.\n")

    # group[run_time][field] -> {lead_h: (forecast_l1, observed)}
    group = defaultdict(lambda: defaultdict(dict))
    n_total = n_kept = n_skipped_old = 0

    print("[1/3] Streaming pair log…")
    with open(cached_path(PAIR_LOG_URL), "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            n_total += 1
            field = r.get("field")
            if field not in CLOUD_FIELDS:
                continue
            fc_l1 = r.get("forecast_l1")
            obs = r.get("observed")
            lead = r.get("lead_h")
            run = r.get("run_time")
            if fc_l1 is None or obs is None or lead is None or run is None:
                n_skipped_old += 1
                continue
            group[run][field][lead] = (fc_l1, obs)
            n_kept += 1

    print(f"  total rows: {n_total:,} · cloud rows kept: {n_kept:,} · old-schema skipped: {n_skipped_old:,}")
    print(f"  distinct runs: {len(group):,}")

    print("\n[2/3] Per-(field, lead_N): pair lead-0 bias with lead-N error_l1\n")

    summary = {}  # field -> {lead_N: (pearson, spearman, n)}
    for field in CLOUD_FIELDS:
        per_lead_pairs = defaultdict(lambda: ([], []))  # lead_N -> (bias_arr, err_arr)
        for run, fmap in group.items():
            field_leads = fmap.get(field) or {}
            if 0 not in field_leads:
                continue
            fc0, obs0 = field_leads[0]
            bias0 = obs0 - fc0  # observed minus raw forecast at lead 0
            for lead_n in TARGET_LEADS:
                if lead_n == 0:
                    continue
                if lead_n not in field_leads:
                    continue
                fcN, obsN = field_leads[lead_n]
                errN = fcN - obsN  # signed forecast error at lead N
                xs, ys = per_lead_pairs[lead_n]
                xs.append(bias0)
                ys.append(errN)

        summary[field] = {}
        print(f"  [{field}]")
        print(f"  {'lead_N':>6}  {'n':>7}  {'pearson':>8}  {'spearman':>9}  verdict")
        print(f"  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*9}  {'-'*30}")
        for lead_n in TARGET_LEADS:
            if lead_n == 0:
                continue
            xs, ys = per_lead_pairs[lead_n]
            n = len(xs)
            p = pearson(xs, ys) if n >= MIN_N_PER_LEAD else None
            s = spearman(xs, ys) if n >= MIN_N_PER_LEAD else None
            summary[field][lead_n] = (p, s, n)
            if n < MIN_N_PER_LEAD:
                verdict = f"thin (n<{MIN_N_PER_LEAD})"
                p_str = s_str = "—"
            else:
                # Sign convention: under-predict at lead_0 means bias0 > 0
                # (obs > fc → bias is positive). If model under-predicts at
                # lead_N too, errN < 0 (fc < obs → errN is negative). So
                # under-prediction at 0 should pair with errN < 0 → negative
                # correlation when bias and error are signed this way.
                # Persistence = NEGATIVE Pearson. Flip sign for the gate
                # check so positive numbers = "sticky bias, helpful to propagate."
                p_signed = -p if p is not None else None
                s_signed = -s if s is not None else None
                p_str = f"{p_signed:+.3f}"
                s_str = f"{s_signed:+.3f}"
                # Gate check applies only to cc.
                gate_mark = ""
                if field == "cc":
                    if lead_n == 6:
                        gate_mark = f"  [gate ≥{SHIP_GATE_AT_6H:+.2f}] " + (
                            "✓ PASS" if p_signed >= SHIP_GATE_AT_6H else "✗ FAIL"
                        )
                    elif lead_n == 12:
                        gate_mark = f"  [gate ≥{SHIP_GATE_AT_12H:+.2f}] " + (
                            "✓ PASS" if p_signed >= SHIP_GATE_AT_12H else "✗ FAIL"
                        )
                if p_signed is None:
                    verdict = "—" + gate_mark
                elif p_signed >= 0.50:
                    verdict = "strong" + gate_mark
                elif p_signed >= 0.30:
                    verdict = "moderate" + gate_mark
                elif p_signed >= 0.15:
                    verdict = "weak" + gate_mark
                elif p_signed >= 0:
                    verdict = "near-zero" + gate_mark
                else:
                    verdict = "inverted (propagation would hurt)" + gate_mark
            print(f"  {lead_n:>6}  {n:>7,}  {p_str:>8}  {s_str:>9}  {verdict}")
        print()

    # ──────────── Final verdict (cc only — that's the directive's scope) ────────────
    print("[3/3] Ship-gate verdict (cc):\n")
    cc = summary.get("cc") or {}
    p6 = cc.get(6, (None,))[0]
    p12 = cc.get(12, (None,))[0]
    if p6 is None or p12 is None:
        print("  Insufficient data at lead 6h or 12h — re-run after the pair log fills.")
    else:
        p6s = -p6
        p12s = -p12
        gate6 = p6s >= SHIP_GATE_AT_6H
        gate12 = p12s >= SHIP_GATE_AT_12H
        print(f"  cc lead 6h:  ρ = {p6s:+.3f}  (gate ≥ {SHIP_GATE_AT_6H:+.2f})  {'✓ PASS' if gate6 else '✗ FAIL'}")
        print(f"  cc lead 12h: ρ = {p12s:+.3f}  (gate ≥ {SHIP_GATE_AT_12H:+.2f})  {'✓ PASS' if gate12 else '✗ FAIL'}")
        if gate6 and gate12:
            print("\n  → SHIP: promote KBOS+KBVY cloud blend to per-lead L2 with τ_cc fit.")
        else:
            print("\n  → HOLD: bias does not persist enough to justify per-lead propagation.")
            print("     Formalize hourly[0]-only as the intentional behavior; stop calling it half-built L2.")


if __name__ == "__main__":
    main()
