"""Persistence skill baseline for pa (precipitation amount, in/hr).

pa was excluded from `h_persistence_skill.py` because MAE on a zero-inflated
field is dominated by the ~90% of hours with no rain — persistence hits zero,
model hits zero, both "look right," and the pooled skill number tells you
nothing about whether the model is actually useful when it matters.

This script fixes that with a decomposition:
  Section A — Pooled skill (all hours): comparable to what other fields see.
              Report but caveat with base rates.
  Section B — Rain-observed subset (obs > 0): does the model beat 'same as
              current rain rate' for the ~5-10% of hours that actually rain?
              This is the user-facing question.
  Section C — Detection Brier score: binary(fc>0) vs binary(obs>0) — is the
              model right about WHETHER it will rain? Reuses the calibration
              framing pp Platt built on.
  Section D — Verdict per band + overall.

Persistence definition (same as h_persistence_skill.py):
  persistence_forecast(lead L, run R) = observed(R)
  We reconstruct observed(R) from the pair log's own valid_time → observed
  index (any row with valid_time=R gives us obs at R, regardless of the
  lead that produced it).

pa is L1-only in production (no L2/L3/L4 wired — see project_correction_stack).
So we compare L1 vs persistence only; no L4 diff to report.

Verdict per band:
  Uses the *rain-observed subset* MAE (Section B) as the primary signal —
  that's the user-value question. Base-rate-heavy pooled skill (Section A)
  reported for context.

  ★ ADDS VALUE     rain-subset skill ≥ +0.10 (model materially beats
                   persistence when it's actually raining)
  ⚠ MARGINAL       rain-subset skill 0 to +0.10
  ★ BEHIND         rain-subset skill < 0 (persistence beats model on rain hours)

Overall verdict:
  ★ ADDS VALUE   ≥3 of 4 bands ADDS VALUE, none BEHIND
  ⚠ MIXED        1-2 bands ADDS VALUE OR any BEHIND
  ★ NO SKILL     0 bands ADDS VALUE

Runs as part of the digest (analysis/*.py glob picks it up); emits a single
"Verdict:" line for the exec-summary extractor.
"""
import os
import sys
import json
import math
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path  # noqa: E402

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
OUT_TXT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "output", "h_pa_persistence_skill.txt")

FIELD = "pa"
BANDS = [(1, 6, "0-5h"), (6, 12, "6-11h"), (12, 24, "12-23h"), (24, 48, "24-47h")]
MIN_N_PER_CELL = 200
MIN_N_RAIN_SUBSET = 30  # rain hours are rare — lower floor for rain-only cells
RAIN_THRESHOLD = 0.001  # in/hr — anything above sensor noise counts as "rain"


def band_of(lead):
    for lo, hi, lab in BANDS:
        if lo <= lead < hi:
            return lab
    return None


def hour_floor(ts):
    if ts is None or len(ts) < 16:
        return None
    return ts[:14] + "00"


def compute():
    path = cached_path(URL)

    # Pass 1: pa obs index
    print("[1/3] Building pa obs index...", file=sys.stderr)
    obs_ts = {}
    n_rows = 0
    with open(path, "rb") as fh:
        for raw in fh:
            n_rows += 1
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            vt = r.get("valid_time")
            ob = r.get("observed")
            if vt is None or ob is None:
                continue
            if vt not in obs_ts:
                obs_ts[vt] = float(ob)
    print(f"    scanned {n_rows:,} pair rows; pa obs index size: {len(obs_ts):,}",
          file=sys.stderr)

    # Pass 2: accumulate per-band counters
    #   Pooled:   n, sum_ae_pers, sum_ae_l1, sum_se_pers, sum_se_l1
    #   Rain:     same, but only rows where observed > threshold
    #   Detect:   n, brier_pers, brier_l1, hit_obs, hit_l1, hit_pers
    print("[2/3] Scoring pa vs persistence, split by all/rain/detect...",
          file=sys.stderr)

    def zeros():
        return {"n": 0,
                "ae_p": 0.0, "ae_l1": 0.0, "se_p": 0.0, "se_l1": 0.0,
                "n_rain": 0,
                "ae_p_r": 0.0, "ae_l1_r": 0.0, "se_p_r": 0.0, "se_l1_r": 0.0,
                "brier_p": 0.0, "brier_l1": 0.0,
                "obs_pos": 0, "l1_pos": 0, "pers_pos": 0}
    accum = defaultdict(zeros)
    n_joined = n_orphan = 0
    with open(path, "rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("field") != FIELD:
                continue
            lead = r.get("lead_h")
            if lead is None:
                continue
            try:
                lead = int(lead)
            except Exception:
                continue
            if lead <= 0 or lead > 47:
                continue
            band = band_of(lead)
            if band is None:
                continue
            rt = r.get("run_time")
            ob = r.get("observed")
            fc_l1 = r.get("forecast_l1", r.get("forecast"))
            if rt is None or ob is None or fc_l1 is None:
                continue
            persist = obs_ts.get(hour_floor(rt))
            if persist is None:
                n_orphan += 1
                continue
            n_joined += 1

            ob = float(ob)
            fc_l1 = float(fc_l1)
            persist = float(persist)

            a = accum[band]
            a["n"] += 1
            e_p = persist - ob
            e_1 = fc_l1 - ob
            a["ae_p"] += abs(e_p)
            a["ae_l1"] += abs(e_1)
            a["se_p"] += e_p * e_p
            a["se_l1"] += e_1 * e_1

            # Detection: binary(fc>threshold) vs binary(obs>threshold)
            b_obs = 1.0 if ob > RAIN_THRESHOLD else 0.0
            b_l1 = 1.0 if fc_l1 > RAIN_THRESHOLD else 0.0
            b_p = 1.0 if persist > RAIN_THRESHOLD else 0.0
            a["brier_p"] += (b_p - b_obs) ** 2
            a["brier_l1"] += (b_l1 - b_obs) ** 2
            a["obs_pos"] += int(b_obs)
            a["l1_pos"] += int(b_l1)
            a["pers_pos"] += int(b_p)

            # Rain-observed subset
            if b_obs:
                a["n_rain"] += 1
                a["ae_p_r"] += abs(e_p)
                a["ae_l1_r"] += abs(e_1)
                a["se_p_r"] += e_p * e_p
                a["se_l1_r"] += e_1 * e_1

    print(f"    joined {n_joined:,} rows; {n_orphan:,} orphans (no obs at run_time)",
          file=sys.stderr)

    # Pass 3: reduce
    per_band = {}
    for band, a in accum.items():
        n = a["n"]
        if n < MIN_N_PER_CELL:
            continue
        cell = {
            "n": n,
            "n_rain": a["n_rain"],
            "obs_rain_rate": round(a["obs_pos"] / n, 3) if n else None,
            "l1_rain_rate": round(a["l1_pos"] / n, 3) if n else None,
            "pers_rain_rate": round(a["pers_pos"] / n, 3) if n else None,
            "mae_p": round(a["ae_p"] / n, 5),
            "mae_l1": round(a["ae_l1"] / n, 5),
            "rmse_p": round(math.sqrt(a["se_p"] / n), 5),
            "rmse_l1": round(math.sqrt(a["se_l1"] / n), 5),
            "brier_p": round(a["brier_p"] / n, 4),
            "brier_l1": round(a["brier_l1"] / n, 4),
        }
        cell["skill_l1_mae_pooled"] = (round(1 - cell["mae_l1"] / cell["mae_p"], 3)
                                       if cell["mae_p"] > 0 else None)
        cell["skill_l1_brier"] = (round(1 - cell["brier_l1"] / cell["brier_p"], 3)
                                  if cell["brier_p"] > 0 else None)
        if a["n_rain"] >= MIN_N_RAIN_SUBSET:
            cell["mae_p_rain"] = round(a["ae_p_r"] / a["n_rain"], 4)
            cell["mae_l1_rain"] = round(a["ae_l1_r"] / a["n_rain"], 4)
            cell["skill_l1_mae_rain"] = (
                round(1 - cell["mae_l1_rain"] / cell["mae_p_rain"], 3)
                if cell["mae_p_rain"] > 0 else None
            )
        else:
            cell["mae_p_rain"] = None
            cell["mae_l1_rain"] = None
            cell["skill_l1_mae_rain"] = None
        per_band[band] = cell
    return per_band


def verdict_cell(cell):
    """Primary signal is rain-subset skill. Fall back to pooled only when
    rain n is too thin (rare in the 24-47h band where rain events accumulate)."""
    s = cell.get("skill_l1_mae_rain")
    if s is None:
        return "insufficient-rain"
    if s >= 0.10:
        return "ADDS VALUE"
    if s < 0:
        return "BEHIND"
    return "MARGINAL"


def verdict_field(per_band):
    verdicts = [verdict_cell(c) for c in per_band.values()]
    n_add = sum(1 for v in verdicts if v == "ADDS VALUE")
    n_beh = sum(1 for v in verdicts if v == "BEHIND")
    n_ins = sum(1 for v in verdicts if v == "insufficient-rain")
    if n_add >= 3 and n_beh == 0:
        return "ADDS VALUE"
    if n_add == 0 and n_ins == len(verdicts):
        return "INSUFFICIENT DATA"
    if n_add == 0:
        return "NO SKILL"
    return "MIXED"


def emit(per_band):
    L = []

    def w(s=""):
        L.append(s)

    w("=" * 96)
    w("pa (precipitation amount) — PERSISTENCE SKILL BASELINE")
    w("=" * 96)
    w("")
    w("pa was skipped in h_persistence_skill.py because zero-mass dominates pooled MAE.")
    w("This script splits: (A) pooled MAE, (B) rain-observed-subset MAE (obs > "
      f"{RAIN_THRESHOLD} in/hr),")
    w("(C) detection Brier — binary(fc>0) vs binary(obs>0). Primary verdict uses (B).")
    w("")

    # Section A — pooled + base rates
    w("=" * 96)
    w("[A] POOLED (all hours) + BASE RATES")
    w("=" * 96)
    hdr = (f"{'band':<8}{'n':>8}{'n_rain':>8}{'obs_%rain':>11}{'l1_%rain':>11}"
           f"{'pers_%rain':>11}{'MAE_pers':>10}{'MAE_L1':>10}{'skill_L1':>10}")
    w(hdr)
    w("-" * len(hdr))
    for _, _, band in BANDS:
        c = per_band.get(band)
        if not c:
            continue
        w(f"{band:<8}{c['n']:>8,}{c['n_rain']:>8,}"
          f"{c['obs_rain_rate']*100:>10.1f}%{c['l1_rain_rate']*100:>10.1f}%"
          f"{c['pers_rain_rate']*100:>10.1f}%"
          f"{c['mae_p']:>10.5f}{c['mae_l1']:>10.5f}"
          f"{c['skill_l1_mae_pooled']:>+10.3f}")
    w("")
    w("  Reading: 'obs_%rain' is base rate — fraction of hours with observed > threshold.")
    w("  Pooled skill is what other fields see; heavily dominated by no-rain hours.")

    # Section B — rain-observed subset (primary)
    w("")
    w("=" * 96)
    w("[B] RAIN-OBSERVED SUBSET (obs > threshold) — PRIMARY VALUE QUESTION")
    w("=" * 96)
    hdr = (f"{'band':<8}{'n_rain':>8}{'MAE_pers':>11}{'MAE_L1':>11}"
           f"{'skill_L1':>11}  verdict")
    w(hdr)
    w("-" * len(hdr))
    for _, _, band in BANDS:
        c = per_band.get(band)
        if not c:
            continue
        v = verdict_cell(c)
        flag = ""
        if v == "ADDS VALUE":
            flag = "★ ADDS VALUE"
        elif v == "BEHIND":
            flag = "★ BEHIND"
        elif v == "MARGINAL":
            flag = "⚠ MARGINAL"
        else:
            flag = f"— (n_rain={c['n_rain']} < {MIN_N_RAIN_SUBSET})"
        mp = c["mae_p_rain"]
        ml = c["mae_l1_rain"]
        sk = c["skill_l1_mae_rain"]
        if mp is None:
            w(f"{band:<8}{c['n_rain']:>8,}{'—':>11}{'—':>11}{'—':>11}  {flag}")
        else:
            w(f"{band:<8}{c['n_rain']:>8,}{mp:>11.4f}{ml:>11.4f}"
              f"{sk:>+11.3f}  {flag}")

    # Section C — detection Brier
    w("")
    w("=" * 96)
    w(f"[C] DETECTION BRIER — binary(fc > {RAIN_THRESHOLD}) vs binary(obs > "
      f"{RAIN_THRESHOLD})")
    w("=" * 96)
    hdr = (f"{'band':<8}{'n':>8}{'Brier_pers':>13}{'Brier_L1':>11}"
           f"{'skill_L1':>11}")
    w(hdr)
    w("-" * len(hdr))
    for _, _, band in BANDS:
        c = per_band.get(band)
        if not c:
            continue
        w(f"{band:<8}{c['n']:>8,}{c['brier_p']:>13.4f}{c['brier_l1']:>11.4f}"
          f"{c['skill_l1_brier']:>+11.3f}")
    w("")
    w("  Reading: negative skill means persistence detects rain/no-rain better")
    w("  than the model. This is the 'will it rain at all' question, separate")
    w("  from 'how much' (Section B).")

    # Verdict
    w("")
    w("=" * 96)
    w("VERDICT")
    w("=" * 96)
    field_v = verdict_field(per_band)
    n_add = sum(1 for _, _, b in BANDS
                if b in per_band and verdict_cell(per_band[b]) == "ADDS VALUE")
    n_beh = sum(1 for _, _, b in BANDS
                if b in per_band and verdict_cell(per_band[b]) == "BEHIND")
    n_mar = sum(1 for _, _, b in BANDS
                if b in per_band and verdict_cell(per_band[b]) == "MARGINAL")
    n_ins = sum(1 for _, _, b in BANDS
                if b in per_band and verdict_cell(per_band[b]) == "insufficient-rain")

    # Pooled rain-subset skill weighted by n_rain
    num = den = 0.0
    for _, _, b in BANDS:
        c = per_band.get(b)
        if not c or c.get("mae_p_rain") is None:
            continue
        num += c["mae_l1_rain"] * c["n_rain"]
        den += c["mae_p_rain"] * c["n_rain"]
    pooled_rain_skill = (1 - num / den) if den > 0 else None

    parts = [
        f"pa: {n_add} ADDS VALUE / {n_mar} MARGINAL / {n_beh} BEHIND / {n_ins} insufficient",
        f"overall {field_v}",
    ]
    if pooled_rain_skill is not None:
        parts.append(f"n-weighted rain-subset skill {pooled_rain_skill:+.3f}")
    line = "Verdict: " + " — ".join(parts) + "."
    if len(line) > 140:
        line = line[:137] + "..."
    w(line)

    return "\n".join(L)


def main():
    per_band = compute()
    if not per_band:
        print("Verdict: pa — no bands met MIN_N_PER_CELL floor. Insufficient data.")
        return 1
    text = emit(per_band)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
