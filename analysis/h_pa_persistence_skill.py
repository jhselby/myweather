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
  Section D — HALVES-VERIFICATION: split L1/persistence rows by obs_time at
              row-count median, run Section B + Section C independently on
              each half. Answers: is the pooled finding stable across the
              window, or fitting one weather regime? Per feedback_pooled_n_time_thin
              — the pr L2 retro pooled 6 WIN cells, halves flipped it to 0.
  Section E — Verdict per band + overall.

Persistence definition (same as h_persistence_skill.py):
  persistence_forecast(lead L, run R) = observed(R)
  We reconstruct observed(R) from the pair log's own valid_time → observed
  index (any row with valid_time=R gives us obs at R, regardless of the
  lead that produced it).

pa is L1-only in production (no L2/L3/L4 wired — see project_correction_stack).
So we compare L1 vs persistence only; no L4 diff to report.

Verdict per band (from Section B):
  ★ ADDS VALUE     rain-subset skill ≥ +0.10
  ⚠ MARGINAL       rain-subset skill 0 to +0.10
  ★ BEHIND         rain-subset skill < 0

Overall verdict:
  ★ ADDS VALUE   ≥3 of 4 bands ADDS VALUE, none BEHIND
  ⚠ MIXED        1-2 bands ADDS VALUE OR any BEHIND
  ★ NO SKILL     0 bands ADDS VALUE

Seasonal caveat: halves split by obs_time. Early half is typically earlier
summer (more convective, spotty spatial, short-duration events), late half
is later summer / early fall (more stratiform, mixed tropical). A cell that
flips A→B in pa may be a seasonal regime shift rather than a single-window
artifact — reported side-by-side but not auto-classified.

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
MIN_N_RAIN_SUBSET = 30
RAIN_THRESHOLD = 0.001


def band_of(lead):
    for lo, hi, lab in BANDS:
        if lo <= lead < hi:
            return lab
    return None


def hour_floor(ts):
    if ts is None or len(ts) < 16:
        return None
    return ts[:14] + "00"


def collect_rows():
    """Stream pair log, return (rows, obs_index_size). Each row is a tuple:
    (obs_time, band, e_p, e_1, b_obs, b_l1, b_p)."""
    path = cached_path(URL)

    # Pass 1: obs index
    print("[1/2] Building pa obs index...", file=sys.stderr)
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

    # Pass 2: collect per-row
    print("[2/2] Streaming pa rows...", file=sys.stderr)
    rows = []
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
            obs_time = r.get("obs_time") or r.get("valid_time") or ""
            so = r.get("state_obs") or {}
            regime = so.get("regime_synoptic") or "unknown"
            ob = float(ob)
            fc_l1 = float(fc_l1)
            persist = float(persist)
            e_p = persist - ob
            e_1 = fc_l1 - ob
            b_obs = 1.0 if ob > RAIN_THRESHOLD else 0.0
            b_l1 = 1.0 if fc_l1 > RAIN_THRESHOLD else 0.0
            b_p = 1.0 if persist > RAIN_THRESHOLD else 0.0
            rows.append((obs_time, band, e_p, e_1, b_obs, b_l1, b_p, lead, regime))
            n_joined += 1
    print(f"    joined {n_joined:,} rows; {n_orphan:,} orphans", file=sys.stderr)
    return rows, len(obs_ts)


def aggregate(rows):
    """Compute per-band cell dict from a row subset."""
    def zeros():
        return {"n": 0,
                "ae_p": 0.0, "ae_l1": 0.0, "se_p": 0.0, "se_l1": 0.0,
                "n_rain": 0,
                "ae_p_r": 0.0, "ae_l1_r": 0.0,
                "brier_p": 0.0, "brier_l1": 0.0,
                "obs_pos": 0, "l1_pos": 0, "pers_pos": 0}
    accum = defaultdict(zeros)
    for row in rows:
        _obs_time, band, e_p, e_1, b_obs, b_l1, b_p = row[:7]
        a = accum[band]
        a["n"] += 1
        a["ae_p"] += abs(e_p)
        a["ae_l1"] += abs(e_1)
        a["se_p"] += e_p * e_p
        a["se_l1"] += e_1 * e_1
        a["brier_p"] += (b_p - b_obs) ** 2
        a["brier_l1"] += (b_l1 - b_obs) ** 2
        a["obs_pos"] += int(b_obs)
        a["l1_pos"] += int(b_l1)
        a["pers_pos"] += int(b_p)
        if b_obs:
            a["n_rain"] += 1
            a["ae_p_r"] += abs(e_p)
            a["ae_l1_r"] += abs(e_1)

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
    if cell is None:
        return "no-cell"
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


def _fmt_skill(v):
    return f"{v:+.3f}" if v is not None else "—"


def regime_halves_detection_0_5(half_a_rows, half_b_rows, min_n=100):
    """Regime × halves detection Brier for 0-5h band only.
    Returns (dist_a, dist_b, per_regime) where per_regime[regime] is
    (nA, brier_p_A, brier_l1_A, skill_A, nB, brier_p_B, brier_l1_B, skill_B)."""
    def aggreg(rows_subset):
        by_regime = defaultdict(lambda: [0, 0.0, 0.0])
        for row in rows_subset:
            _obs_time, band, _e_p, _e_1, b_obs, b_l1, b_p, lead, regime = row
            if band != "0-5h":
                continue
            r = by_regime[regime]
            r[0] += 1
            r[1] += (b_p - b_obs) ** 2
            r[2] += (b_l1 - b_obs) ** 2
        return by_regime

    a = aggreg(half_a_rows)
    b = aggreg(half_b_rows)

    n_a_total = sum(v[0] for v in a.values())
    n_b_total = sum(v[0] for v in b.values())
    dist_a = {reg: (v[0], v[0] / n_a_total if n_a_total else 0.0)
              for reg, v in a.items()}
    dist_b = {reg: (v[0], v[0] / n_b_total if n_b_total else 0.0)
              for reg, v in b.items()}

    per_regime = {}
    for reg in sorted(set(a.keys()) | set(b.keys())):
        av = a.get(reg, [0, 0.0, 0.0])
        bv = b.get(reg, [0, 0.0, 0.0])
        nA, brp_A, brl1_A = av
        nB, brp_B, brl1_B = bv
        skill_A = ((1 - (brl1_A / nA) / (brp_A / nA)) if (nA and brp_A > 0) else None)
        skill_B = ((1 - (brl1_B / nB) / (brp_B / nB)) if (nB and brp_B > 0) else None)
        # Only include if BOTH halves meet the floor
        if nA >= min_n and nB >= min_n:
            per_regime[reg] = {
                "nA": nA, "brier_p_A": brp_A / nA, "brier_l1_A": brl1_A / nA,
                "skill_A": skill_A,
                "nB": nB, "brier_p_B": brp_B / nB, "brier_l1_B": brl1_B / nB,
                "skill_B": skill_B,
            }
    return dist_a, dist_b, per_regime, n_a_total, n_b_total


def emit(pooled, half_a, half_b, a_range, b_range,
         reg_dist_a, reg_dist_b, reg_per, reg_nA, reg_nB):
    L = []

    def w(s=""):
        L.append(s)

    w("=" * 96)
    w("pa (precipitation amount) — PERSISTENCE SKILL BASELINE + HALVES-VERIFICATION")
    w("=" * 96)
    w("")
    w("pa was skipped in h_persistence_skill.py because zero-mass dominates pooled MAE.")
    w("This script splits: (A) pooled MAE, (B) rain-observed-subset MAE (obs > "
      f"{RAIN_THRESHOLD} in/hr),")
    w("(C) detection Brier — binary(fc>0) vs binary(obs>0). Primary verdict uses (B).")
    w("Section D re-runs (B) + (C) independently on obs-time halves per")
    w("feedback_pooled_n_time_thin.")
    w("")

    # --- Section A: pooled + base rates
    w("=" * 96)
    w("[A] POOLED (all hours) + BASE RATES")
    w("=" * 96)
    hdr = (f"{'band':<8}{'n':>8}{'n_rain':>8}{'obs_%rain':>11}{'l1_%rain':>11}"
           f"{'pers_%rain':>11}{'MAE_pers':>10}{'MAE_L1':>10}{'skill_L1':>10}")
    w(hdr)
    w("-" * len(hdr))
    for _, _, band in BANDS:
        c = pooled.get(band)
        if not c:
            continue
        w(f"{band:<8}{c['n']:>8,}{c['n_rain']:>8,}"
          f"{c['obs_rain_rate']*100:>10.1f}%{c['l1_rain_rate']*100:>10.1f}%"
          f"{c['pers_rain_rate']*100:>10.1f}%"
          f"{c['mae_p']:>10.5f}{c['mae_l1']:>10.5f}"
          f"{c['skill_l1_mae_pooled']:>+10.3f}")
    w("")
    w("  Reading: 'obs_%rain' is base rate. Pooled skill is dominated by no-rain hours.")

    # --- Section B: rain-observed subset
    w("")
    w("=" * 96)
    w("[B] RAIN-OBSERVED SUBSET (obs > threshold) — PRIMARY VALUE QUESTION (pooled)")
    w("=" * 96)
    hdr = (f"{'band':<8}{'n_rain':>8}{'MAE_pers':>11}{'MAE_L1':>11}"
           f"{'skill_L1':>11}  verdict")
    w(hdr)
    w("-" * len(hdr))
    for _, _, band in BANDS:
        c = pooled.get(band)
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

    # --- Section C: detection Brier
    w("")
    w("=" * 96)
    w(f"[C] DETECTION BRIER — binary(fc > {RAIN_THRESHOLD}) vs binary(obs > "
      f"{RAIN_THRESHOLD}) (pooled)")
    w("=" * 96)
    hdr = (f"{'band':<8}{'n':>8}{'Brier_pers':>13}{'Brier_L1':>11}"
           f"{'skill_L1':>11}")
    w(hdr)
    w("-" * len(hdr))
    for _, _, band in BANDS:
        c = pooled.get(band)
        if not c:
            continue
        w(f"{band:<8}{c['n']:>8,}{c['brier_p']:>13.4f}{c['brier_l1']:>11.4f}"
          f"{c['skill_l1_brier']:>+11.3f}")
    w("")
    w("  Negative skill = persistence detects rain/no-rain better than the model.")

    # --- Section D: halves-verification
    w("")
    w("=" * 96)
    w("[D] HALVES-VERIFICATION — split at obs_time row-count median")
    w("=" * 96)
    w(f"  half A: {a_range[0]} → {a_range[1]}")
    w(f"  half B: {b_range[0]} → {b_range[1]}")
    w("  Seasonal caveat: early-summer (convective) vs late-summer (stratiform).")
    w("  A→B flip in pa may be genuine regime shift, not artifact — inspect.")
    w("")

    # D.1 — rain-subset skill A vs B per band
    w("  RAIN-SUBSET skill (primary verdict signal) — A vs B:")
    hdr = (f"    {'band':<8}{'nA_rain':>10}{'skill_A':>10}{'verdict_A':<14}"
           f"{'nB_rain':>10}{'skill_B':>10}{'verdict_B':<14}  stability")
    w(hdr)
    w("    " + "-" * (len(hdr) - 4))
    n_stable_wins = 0
    for _, _, band in BANDS:
        ca = half_a.get(band)
        cb = half_b.get(band)
        va = verdict_cell(ca)
        vb = verdict_cell(cb)
        nA_r = ca["n_rain"] if ca else 0
        nB_r = cb["n_rain"] if cb else 0
        sA = ca.get("skill_l1_mae_rain") if ca else None
        sB = cb.get("skill_l1_mae_rain") if cb else None
        # Stability classification
        if va == "insufficient-rain" or vb == "insufficient-rain" \
                or va == "no-cell" or vb == "no-cell":
            stability = "thin"
        elif va == "ADDS VALUE" and vb == "ADDS VALUE":
            stability = "★ BOTH-WIN"
            n_stable_wins += 1
        elif (va == "ADDS VALUE" and vb == "BEHIND") or \
                (vb == "ADDS VALUE" and va == "BEHIND"):
            stability = "☠ FLIPS"
        elif va == vb:
            stability = "consistent"
        else:
            stability = "mixed"
        w(f"    {band:<8}{nA_r:>10,}{_fmt_skill(sA):>10}{va:<14}"
          f"{nB_r:>10,}{_fmt_skill(sB):>10}{vb:<14}  {stability}")

    # D.2 — detection Brier A vs B (this is the main finding — must survive halves)
    w("")
    w("  DETECTION BRIER skill (short-lead is the primary finding) — A vs B:")
    hdr = (f"    {'band':<8}{'nA':>10}{'B-skill_A':>12}{'nB':>10}"
           f"{'B-skill_B':>12}  stability")
    w(hdr)
    w("    " + "-" * (len(hdr) - 4))
    n_det_stable_wins = 0
    n_det_stable_losses = 0
    for _, _, band in BANDS:
        ca = half_a.get(band)
        cb = half_b.get(band)
        if not ca or not cb:
            continue
        sA = ca.get("skill_l1_brier")
        sB = ca.get("skill_l1_brier")
        # bug avoided: use each half's own value
        sA = ca.get("skill_l1_brier")
        sB = cb.get("skill_l1_brier")
        if sA is None or sB is None:
            stability = "thin"
        elif sA < 0 and sB < 0:
            stability = "★ BOTH-LOSE (persistence wins in both halves)"
            n_det_stable_losses += 1
        elif sA >= 0.1 and sB >= 0.1:
            stability = "★ BOTH-WIN"
            n_det_stable_wins += 1
        elif (sA < 0 and sB > 0.05) or (sB < 0 and sA > 0.05):
            stability = "☠ FLIPS"
        else:
            stability = "consistent-directional"
        w(f"    {band:<8}{ca['n']:>10,}{_fmt_skill(sA):>12}"
          f"{cb['n']:>10,}{_fmt_skill(sB):>12}  {stability}")

    # --- Section E: regime × halves for 0-5h detection (the anchor question)
    w("")
    w("=" * 96)
    w("[E] REGIME × HALVES — 0-5h DETECTION BRIER (does the A/B flip map to a regime split?)")
    w("=" * 96)
    w("")
    w(f"  0-5h row counts: A={reg_nA:,}, B={reg_nB:,}")
    w("")
    w("  Regime distribution shift A → B (fraction of 0-5h rows):")
    all_regs = sorted(set(reg_dist_a.keys()) | set(reg_dist_b.keys()))
    hdr = f"    {'regime':<14}{'nA':>8}{'%A':>8}{'nB':>8}{'%B':>8}{'Δ%':>8}"
    w(hdr)
    w("    " + "-" * (len(hdr) - 4))
    for reg in all_regs:
        nA, pA = reg_dist_a.get(reg, (0, 0.0))
        nB, pB = reg_dist_b.get(reg, (0, 0.0))
        w(f"    {reg:<14}{nA:>8,}{pA*100:>7.1f}%{nB:>8,}{pB*100:>7.1f}%"
          f"{(pB-pA)*100:>+7.1f}%")
    w("")
    w("  Per-regime detection Brier skill (only regimes with n≥100 in BOTH halves):")
    if not reg_per:
        w("    — no regime meets n≥100 in both halves; can't judge regime split.")
    else:
        hdr = (f"    {'regime':<14}{'nA':>7}{'skill_A':>10}"
               f"{'nB':>7}{'skill_B':>10}  status")
        w(hdr)
        w("    " + "-" * (len(hdr) - 4))
        gate_on = []       # both halves negative → persistence wins, obs-blend needed
        gate_off = []      # both halves positive → model wins, leave alone
        flips = []         # A/B opposite sign
        marginal = []      # same-sign but small |skill|
        for reg in sorted(reg_per.keys()):
            r = reg_per[reg]
            sA = r["skill_A"]
            sB = r["skill_B"]
            if sA is None or sB is None:
                status = "thin"
            elif sA < -0.05 and sB < -0.05:
                status = "★ GATE-ON candidate (persistence beats model in BOTH halves)"
                gate_on.append((reg, sA, sB))
            elif sA > 0.05 and sB > 0.05:
                status = "★ GATE-OFF (model beats persistence in both halves)"
                gate_off.append((reg, sA, sB))
            elif (sA < -0.05 and sB > 0.05) or (sB < -0.05 and sA > 0.05):
                status = "☠ FLIPS (opposite sign across halves)"
                flips.append((reg, sA, sB))
            else:
                status = "marginal"
                marginal.append((reg, sA, sB))
            w(f"    {reg:<14}{r['nA']:>7,}{_fmt_skill(sA):>10}"
              f"{r['nB']:>7,}{_fmt_skill(sB):>10}  {status}")

    # Interpretation summary
    w("")
    if reg_per:
        if gate_on and not flips:
            w(f"  → GATE-ON-WHERE-WINS shape identified: pa 0-5h detection blend")
            w(f"    should fire for regime(s) {[r for r, _, _ in gate_on]}. Both halves")
            w(f"    agree persistence beats model in those regimes.")
        elif flips:
            w(f"  → REGIME × HALVES also FLIPS: regime(s) {[r for r, _, _ in flips]} show")
            w(f"    opposite-sign detection skill across halves. The A→B pooled flip is")
            w(f"    NOT explained by regime distribution alone; there's a finer split we're")
            w(f"    not capturing. pa 0-5h detection is L1-forever at current resolution.")
        elif gate_off and not gate_on:
            w(f"  → ALL REGIMES model-wins in both halves. The pooled −0.065 was fitting a")
            w(f"    thin-regime tail that doesn't repeat. Close the door on pa 0-5h detection.")
        else:
            w(f"  → Mixed / underpowered. Regime × halves doesn't cleanly explain the flip.")

    # --- Section F: verdict
    w("")
    w("=" * 96)
    w("VERDICT")
    w("=" * 96)
    field_v = verdict_field(pooled)
    n_add = sum(1 for _, _, b in BANDS
                if b in pooled and verdict_cell(pooled[b]) == "ADDS VALUE")
    n_beh = sum(1 for _, _, b in BANDS
                if b in pooled and verdict_cell(pooled[b]) == "BEHIND")
    n_mar = sum(1 for _, _, b in BANDS
                if b in pooled and verdict_cell(pooled[b]) == "MARGINAL")
    n_ins = sum(1 for _, _, b in BANDS
                if b in pooled and verdict_cell(pooled[b]) == "insufficient-rain")

    num = den = 0.0
    for _, _, b in BANDS:
        c = pooled.get(b)
        if not c or c.get("mae_p_rain") is None:
            continue
        num += c["mae_l1_rain"] * c["n_rain"]
        den += c["mae_p_rain"] * c["n_rain"]
    pooled_rain_skill = (1 - num / den) if den > 0 else None

    # Detection-loss halves stability at 0-5h — the anchor finding
    ca_05 = half_a.get("0-5h")
    cb_05 = half_b.get("0-5h")
    det_0_5_A = ca_05.get("skill_l1_brier") if ca_05 else None
    det_0_5_B = cb_05.get("skill_l1_brier") if cb_05 else None
    det_short_confirmed = (det_0_5_A is not None and det_0_5_B is not None
                           and det_0_5_A < 0 and det_0_5_B < 0)

    parts = [
        f"pa: {n_add} ADDS / {n_mar} MARG / {n_beh} BEHIND (rain-subset, pooled)",
        f"overall {field_v}",
    ]
    if pooled_rain_skill is not None:
        parts.append(f"n-weighted rain skill {pooled_rain_skill:+.3f}")
    if det_0_5_A is not None and det_0_5_B is not None:
        det_status = ("CONFIRMED" if det_short_confirmed
                      else ("FLIPS" if (det_0_5_A < 0) != (det_0_5_B < 0)
                            else "MIXED"))
        parts.append(f"0-5h detection loss halves: {det_status} "
                     f"(A {det_0_5_A:+.2f}, B {det_0_5_B:+.2f})")
    line = "Verdict: " + " — ".join(parts) + "."
    if len(line) > 200:
        line = line[:197] + "..."
    w(line)

    return "\n".join(L)


def main():
    rows, obs_idx_n = collect_rows()
    if not rows:
        print("Verdict: pa — no rows joined. Insufficient data.")
        return 1

    pooled = aggregate(rows)
    if not pooled:
        print("Verdict: pa — no band met MIN_N_PER_CELL floor.")
        return 1

    rows_sorted = sorted(rows, key=lambda r: r[0])
    mid = len(rows_sorted) // 2
    half_a_rows = rows_sorted[:mid]
    half_b_rows = rows_sorted[mid:]
    a_range = (half_a_rows[0][0][:10], half_a_rows[-1][0][:10]) if half_a_rows else ("", "")
    b_range = (half_b_rows[0][0][:10], half_b_rows[-1][0][:10]) if half_b_rows else ("", "")
    half_a = aggregate(half_a_rows)
    half_b = aggregate(half_b_rows)

    reg_dist_a, reg_dist_b, reg_per, reg_nA, reg_nB = regime_halves_detection_0_5(
        half_a_rows, half_b_rows)

    text = emit(pooled, half_a, half_b, a_range, b_range,
                reg_dist_a, reg_dist_b, reg_per, reg_nA, reg_nB)
    print(text)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w") as fh:
        fh.write(text + "\n")
    print(f"\nwrote {OUT_TXT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
