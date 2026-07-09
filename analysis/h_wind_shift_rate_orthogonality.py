"""Orthogonality: |Δwd_3h| ≥ 80° (rotating wind, wind_shift_rate Stage 0)
vs C1a (regime-transition flag). Gate for promoting wind_shift_rate to
a new C1 axis vs killing it as captured by C1a.

Stage 0 (h_wind_shift_rate.py 2026-06-24) showed ch +33%, cm +24%,
cc +15% MAE elevation in the rotating-wind ≥80° class. C1a (regime
transition: state_fc.regime != state_obs.regime) might already
capture this — windshifts and regime transitions co-occur.

Method: stratify each (field, band) by (rotating ≥80° flag × C1a
transition flag). Compute MAE per cell. If rotating-class MAE
elevation persists within the C1a=False (stable) subset, the axes
are orthogonal and wind_shift_rate adds independent signal.
"""
import os, sys, json
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cached_path

URL = "https://data.wymancove.com/forecast_error_log.jsonl"
FIELDS = ("t", "h", "ws", "wg", "cc", "cl", "cm", "ch", "pa")
BANDS = [("0-5h", 0, 6), ("6-11h", 6, 12), ("12-23h", 12, 24), ("24-47h", 24, 48)]


def lead_band(lh):
    for lab, lo, hi in BANDS:
        if lo <= lh < hi:
            return lab
    return None


def circ_diff(a, b):
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


# Build obs wd index by minute key, plus collect non-wd pairs to score.
wd_by_time = {}
pair_rows = []
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except json.JSONDecodeError:
            continue
        f = r.get("field")
        ot = r.get("obs_time")
        if f == "wd":
            obs = r.get("observed")
            if ot and obs is not None:
                wd_by_time[ot[:16]] = obs
            continue
        if f not in FIELDS:
            continue
        lead = r.get("lead_h")
        if lead is None:
            continue
        band = lead_band(int(lead))
        if not band:
            continue
        err = r.get("error_l4") if r.get("error_l4") is not None else r.get("error_l1")
        if err is None:
            continue
        sf = r.get("state_fc") or {}
        so = r.get("state_obs") or {}
        rfc = sf.get("regime_synoptic")
        rob = so.get("regime_synoptic")
        if not rfc or not rob:
            continue
        pair_rows.append((ot, f, band, abs(err), rfc != rob))


def rotating_class(ot_iso):
    """Return True if |Δwd over prior 3h| ≥ 80°. None when wd missing."""
    try:
        dt = datetime.fromisoformat(ot_iso[:19])
    except (TypeError, ValueError):
        return None
    prev = (dt - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    cur = dt.strftime("%Y-%m-%dT%H:%M")
    wd_prev = wd_by_time.get(prev)
    wd_cur = wd_by_time.get(cur)
    if wd_prev is None or wd_cur is None:
        return None
    return circ_diff(wd_prev, wd_cur) >= 80


# (field, band, rotating, transition) -> [n, sum_abs_err]
sums = defaultdict(lambda: [0, 0.0])
for ot, f, band, abs_err, trans in pair_rows:
    rot = rotating_class(ot)
    if rot is None:
        continue
    cell = sums[(f, band, rot, trans)]
    cell[0] += 1
    cell[1] += abs_err


def cell(f, band, rot, trans):
    n, e = sums.get((f, band, rot, trans), (0, 0.0))
    return n, (e / n if n else 0)


print("|Δwd_3h| ≥ 80° × C1a (transition) orthogonality")
print(f"{'field':<5} {'band':<7} {'stable_rot/base':>16} {'trans_rot/base':>15}  verdict")
print("-" * 72)
verdicts = defaultdict(int)
for f in FIELDS:
    for lab, _, _ in BANDS:
        n_r_st, m_r_st = cell(f, lab, True,  False)
        n_b_st, m_b_st = cell(f, lab, False, False)
        n_r_tr, m_r_tr = cell(f, lab, True,  True)
        n_b_tr, m_b_tr = cell(f, lab, False, True)
        if min(n_r_st, n_b_st, n_r_tr, n_b_tr) < 80:
            continue
        r_st = m_r_st / m_b_st if m_b_st else 0
        r_tr = m_r_tr / m_b_tr if m_b_tr else 0
        if r_st >= 1.30 and r_tr >= 1.30:
            verdict = "ORTHOGONAL"
        elif r_st <= 1.10:
            verdict = "REDUNDANT"
        elif r_tr >= 1.30:
            verdict = "CONFOUNDED"
        else:
            verdict = "AMBIGUOUS"
        verdicts[verdict] += 1
        print(f"{f:<5} {lab:<7} {r_st:>15.2f}× {r_tr:>14.2f}×  {verdict}")
    print()

print(f"Overall: ORTHOGONAL: {verdicts['ORTHOGONAL']}, REDUNDANT: {verdicts['REDUNDANT']}, "
      f"CONFOUNDED: {verdicts['CONFOUNDED']}, AMBIGUOUS: {verdicts['AMBIGUOUS']}")
print()
total = sum(verdicts.values())
ortho = verdicts['ORTHOGONAL']
red = verdicts['REDUNDANT']
if ortho >= 6:
    print(f"→ PROMOTE: wind_shift_rate is independent of C1a ({ortho} ortho cells). "
          f"Ship as C1i axis on orthogonal cells only.")
elif ortho == 0:
    print(f"→ KILL: wind_shift_rate is captured by C1a "
          f"(0 orthogonal cells / {total} — nothing to narrow-promote).")
elif total and red / total >= 0.7:
    print("→ KILL: wind_shift_rate is captured by C1a (regime transition already covers it).")
else:
    print(f"→ MIXED: {ortho} ortho / {total} total. Narrow promote or hold.")
