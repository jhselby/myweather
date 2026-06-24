"""Orthogonality: C1g (state_obs.humidity ≥ 95, fog regime) vs C1f
(state_fc.precip_in > 0) AND vs cc-saturation (state_fc.cloud_cover ≥ 95).

Stage 0 (h_rh_saturation.py 2026-06-23 & 06-24) showed C1g elevates
cm +134%, ch +149%, cl saturating +67% MAE. Gate before Stage 2: check
the elevation persists within precip_fc==0 subset (independent of C1f)
AND within cc_fc<95 subset (independent of cc-saturation, which already
gets handled by the cloud floor/ceiling Stage 1 candidate).

If RH≥95 elevation collapses when precip_fc==0, C1g is just a noisier
restatement of C1f and gets killed. If it collapses when cc_fc<95, it's
a restatement of cc-saturation (already a Stage 1 candidate).
"""
import os, sys, json
from collections import defaultdict
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


# axes: G = obs_humidity >= 95 (C1g), F = precip_fc > 0 (C1f),
# S = cc_fc >= 95 (cc-saturation)
sums = defaultdict(lambda: [0, 0.0])
with open(cached_path(URL), "rb") as fh:
    for raw in fh:
        try:
            r = json.loads(raw)
        except json.JSONDecodeError:
            continue
        f = r.get("field")
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
        obs_h = so.get("humidity")
        precip_fc = sf.get("precip_in")
        cc_fc = sf.get("cloud_cover")
        if obs_h is None or precip_fc is None or cc_fc is None:
            continue
        G = obs_h >= 95
        F = precip_fc > 0.01
        S = cc_fc >= 95
        sums[(f, band, G, F, S)][0] += 1
        sums[(f, band, G, F, S)][1] += abs(err)


def cell(f, band, G, F, S):
    n, e = sums.get((f, band, G, F, S), (0, 0.0))
    return n, (e / n if n else 0)


def cell_marginalize_S(f, band, G, F):
    """(G, F) cell summing across both S values."""
    n_total = 0
    e_total = 0.0
    for S in (False, True):
        n, e = sums.get((f, band, G, F, S), (0, 0.0))
        n_total += n
        e_total += e * n  # un-divide so we can pool
    return n_total, (e_total / n_total if n_total else 0)


def cell_marginalize_F(f, band, G, S):
    """(G, S) cell summing across both F values."""
    n_total = 0
    e_total = 0.0
    for F in (False, True):
        n, e = sums.get((f, band, G, F, S), (0, 0.0))
        n_total += n
        e_total += e * n
    return n_total, (e_total / n_total if n_total else 0)


def verdict_label(r_clear, r_co):
    """Verdict from (ratio_in_clear_subset, ratio_in_co_subset).
    ORTHOGONAL: both ≥1.30 → C1g elevates in both subsets (independent).
    REDUNDANT: clear-subset ratio ≤1.10 (C1g signal vanishes when other axis off).
    CONFOUNDED: only the co-subset shows elevation.
    """
    if r_clear >= 1.30 and r_co >= 1.30:
        return "ORTHOGONAL"
    if r_clear <= 1.10:
        return "REDUNDANT"
    if r_co >= 1.30:
        return "CONFOUNDED"
    return "AMBIGUOUS"


def run_check(label, cell_fn):
    """cell_fn(field, band, G, axis_state_True_or_False) -> (n, mae)."""
    print(f"C1g (obs_humidity ≥ 95) × {label} orthogonality")
    print(f"{'field':<5} {'band':<7} {'off:G/¬G':>13} {'on:G/¬G':>12}  verdict")
    print("-" * 60)
    counts = defaultdict(int)
    for f in FIELDS:
        for lab, _, _ in BANDS:
            n_off_g, m_off_g = cell_fn(f, lab, True,  False)
            n_off_b, m_off_b = cell_fn(f, lab, False, False)
            n_on_g,  m_on_g  = cell_fn(f, lab, True,  True)
            n_on_b,  m_on_b  = cell_fn(f, lab, False, True)
            if min(n_off_g, n_off_b, n_on_g, n_on_b) < 80:
                continue
            r_off = m_off_g / m_off_b if m_off_b else 0
            r_on  = m_on_g / m_on_b if m_on_b else 0
            verdict = verdict_label(r_off, r_on)
            counts[verdict] += 1
            print(f"{f:<5} {lab:<7} {r_off:>12.2f}× {r_on:>11.2f}×  {verdict}")
        print()
    total = sum(counts.values())
    print(f"vs {label}: ORTHOGONAL: {counts['ORTHOGONAL']}, REDUNDANT: {counts['REDUNDANT']}, "
          f"CONFOUNDED: {counts['CONFOUNDED']}, AMBIGUOUS: {counts['AMBIGUOUS']}\n")
    return counts


# vs C1f: marginalize across S, stratify by (G, F).
v_f = run_check(
    "C1f (precip_fc > 0)",
    lambda f, lab, G, F_state: cell_marginalize_S(f, lab, G, F_state),
)

# vs cc-saturation: marginalize across F, stratify by (G, S).
v_s = run_check(
    "cc-saturation (cc_fc ≥ 95)",
    lambda f, lab, G, S_state: cell_marginalize_F(f, lab, G, S_state),
)

ortho = v_f["ORTHOGONAL"] + v_s["ORTHOGONAL"]
red = v_f["REDUNDANT"] + v_s["REDUNDANT"]
total = sum(v_f.values()) + sum(v_s.values())

if ortho >= 8:
    print(f"→ PROMOTE C1g: independent of both C1f and cc-saturation "
          f"({ortho} orthogonal cells of {total}). Ship as 5th axis.")
elif total and red / total >= 0.6:
    print(f"→ KILL C1g: signal captured by C1f and/or cc-saturation "
          f"({red}/{total} redundant).")
else:
    print(f"→ MIXED: {ortho} ortho / {total} total. Narrow promote or hold.")
