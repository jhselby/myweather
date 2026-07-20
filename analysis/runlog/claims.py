"""Shared translators that turn a script's verdict into a production-claim.

A "claim" is what the script's evidence is asking production to look like —
mirrors the shape returned by divergence_report.probe_production(). Used by
both the divergence report (today's snapshot) and the history-aware streak
counter (consistency over N reads).
"""
import ast
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LOG_DIR = HERE.parent / "output" / "runlog"
L5_GATE_HISTORY_CACHE = REPO / ".cache_l5_gate_history.json"
# walkforward writes this file directly via `with open(..., "w")` — flushes and
# closes deterministically, unlike the stdout-redirected .log which is subject
# to Python's block-buffered stdout behavior when the child process exits mid-
# flush. The .log path stays as first-try (canonical for other consumers), the
# .txt path is the belt-and-suspenders fallback for the "null claim written on
# every digest run since 07-04" wedge.
SUMMARY_PATH = LOG_DIR.parent / "walkforward_l3l4_summary.txt"


def _claim_walkforward():
    """Extract L3/L4 sets from the most recent walkforward run's summary."""
    m3 = m4 = None
    for path in (LOG_DIR / "walkforward_l3l4_validator.log", SUMMARY_PATH):
        if not path.exists():
            continue
        txt = path.read_text()
        if m3 is None:
            m3 = re.search(r"L3_FIELDS\s*=\s*(\{[^}]*\})", txt)
        if m4 is None:
            m4 = re.search(r"L4_FIELDS\s*=\s*(\{[^}]*\})", txt)
        if m3 and m4:
            break
    if m3 is None and m4 is None:
        return None
    try:
        l3 = ast.literal_eval(m3.group(1)) if m3 else None
        l4 = ast.literal_eval(m4.group(1)) if m4 else None
    except Exception:
        return None
    return {"L3_FIELDS": l3, "L4_FIELDS": l4}


def _claim_bool_ship(verdict):
    if verdict is None:
        return None
    v = verdict.upper()
    if "HOLD" in v or "CLOSE" in v or "RETIRE" in v:
        return False
    if "SHIP" in v:
        return True
    return None


def _claim_marginal_ship_cells(curated_json_name: str, allow_empty: bool = False):
    """Read a marginal-axis curated table (c1h_curated.json / c1d_curated.json /
    pre_frontal_curated.json) and return the sorted list of SHIP cells as
    [[field, band], ...]. Used to track the "N-day narrow-promote gate" — the
    axis is ready to flip when the SHIP scope has been stable for N consecutive
    daily digest reads. Returns None if the file can't be read.

    `allow_empty=True` lets an empty SHIP set count as a valid claim (returned
    as `[]` rather than None). Use this for axes where "no SHIP cells" is a
    legitimate stable state to track (e.g., pre-frontal starts empty and might
    stay that way for weeks). The default False matches C1h/C1d, where an
    empty SHIP set means the curated table hasn't been generated yet.
    """
    path = HERE.parents[1] / "weather_collector" / "data" / curated_json_name
    if not path.exists():
        return None
    try:
        doc = json.load(open(path))
    except Exception:
        return None
    cells = doc.get("cells") or {}
    ship = []
    for field, bands in cells.items():
        for band, cell in bands.items():
            if cell.get("status") == "SHIP":
                ship.append([field, band])
    if ship:
        return sorted(ship)
    return [] if allow_empty else None


def _claim_lsr_enabled():
    """Derive live-Lsr claim from the Fitter's per-cycle gate history.

    The live Lsr uses `_BIAS_BY_HOUR_REGIME` (hourly × regime lookup) and
    emits SHIP/HOLD/insufficient_data verdicts per 12h Fitter cycle to
    l5_gate_history.json — that is the authoritative live-gate signal.
    Prior implementation read `l5_solar_analysis` (which tests a CANDIDATE
    regime-only lookup, not the live layer); its HOLD verdict caused the
    divergence report to falsely claim "READY to disable live Lsr" while
    the live gate was 100% SHIP for months. Fixed 2026-07-20.

    Day-rollup mirrors `divergence_report._l5_trajectory_state`: a day
    counts as SHIP only if every cycle that day was SHIP. Latest 7 days
    all SHIP → True (keep on). ≥7 non-SHIP days → False (retire). Anything
    else → None (mixed history, no clean claim).
    """
    if not L5_GATE_HISTORY_CACHE.exists():
        return None
    try:
        hist = json.loads(L5_GATE_HISTORY_CACHE.read_text())
    except Exception:
        return None
    entries = hist.get("entries") or []
    if not entries:
        return None
    from collections import defaultdict
    by_day = defaultdict(list)
    for e in entries:
        day = (e.get("fitted_at") or "")[:10]
        if day:
            by_day[day].append((e.get("verdict") or "").upper())
    latest_days = sorted(by_day)[-7:]
    if len(latest_days) < 7:
        return None
    ship_days = sum(1 for d in latest_days if all(v == "SHIP" for v in by_day[d]))
    hold_days = sum(1 for d in latest_days
                    if not all(v == "SHIP" for v in by_day[d])
                    and not any(v == "INSUFFICIENT_DATA" for v in by_day[d]))
    if ship_days == 7:
        return True
    if hold_days == 7:
        return False
    return None


def _claim_lc_enabled(verdict):
    """lc_fit emits 'Verdict: FIT — N SHIP cell(s) ready to wire into Lc.'
    when the pair-log has SHIP cells, otherwise 'Verdict: HOLD — no cells...'.
    Matches the semantics divergence_report.py uses when displaying LC_ENABLED.
    """
    if verdict is None:
        return None
    v = verdict.upper()
    if "FIT" in v and "SHIP" in v:
        return True
    if "HOLD" in v:
        return False
    return None


def compute_claims(state: dict) -> dict:
    """Return today's production-claims keyed by the same field names that
    `divergence_report.probe_production` returns. Values may be None.

    `state` is the digest_state.json structure: {script_name: {verdict, bucket}}.
    """
    claims = {}
    wf = _claim_walkforward()
    if wf:
        claims["L3_FIELDS"] = wf.get("L3_FIELDS")
        claims["L4_FIELDS"] = wf.get("L4_FIELDS")
    claims["LSR_ENABLED"] = _claim_lsr_enabled()
    v = state.get("r5_cove_analysis", {}).get("verdict")
    claims["LT_ENABLED"] = _claim_bool_ship(v)
    # LC_ENABLED added 2026-07-10 — the 7-day live-layer change gate on Lc was
    # aspirational text in memory until now (no claim writer, so no streak).
    # Same silent-dormancy class as the L3/L4 wedge caught this morning; the
    # gate has been "day 1/? · flip after 7 daily reads agree" for the
    # entire Lc code-shipped-but-gated-OFF window.
    v = state.get("lc_fit", {}).get("verdict")
    claims["LC_ENABLED"] = _claim_lc_enabled(v)
    # C1H_SHIP_CELLS + C1D_SHIP_CELLS — 7-day narrow-promote gates for the
    # marginal-axis Stage 3 tables. Same aspirational-text situation as
    # LC_ENABLED: memory + debug page have showed "day N/7" for weeks
    # without any counter behind them. Streak walker treats the sorted
    # SHIP-cell list as a claim; consecutive days with identical set
    # advance the gate.
    claims["C1H_SHIP_CELLS"] = _claim_marginal_ship_cells("c1h_curated.json")
    claims["C1D_SHIP_CELLS"] = _claim_marginal_ship_cells("c1d_curated.json")
    # PRE_FRONTAL_SHIP_CELLS — 7-day narrow-promote gate for pre-frontal
    # widening. Wired 2026-07-12 v0.6.328d — closes the last aspirational
    # "no counter wired" gate flagged on the debug page. SHIP cells come
    # from h_pre_front_orthogonality.py (cell is SHIP iff ORTHOGONAL vs
    # both C1a AND C1e). Empty list is meaningful — "consistent zero SHIP
    # for 7 days" is a legitimate stable state, so we return [] (not None)
    # when the table exists but no cells qualify.
    claims["PRE_FRONTAL_SHIP_CELLS"] = _claim_marginal_ship_cells(
        "pre_frontal_curated.json", allow_empty=True
    )
    # H_L4_ADD_CANDIDATES — 7-day live-layer change gate for the h/l4 narrow
    # add finding (h/l4/calm/12-23h found 07-12 + 07-13, day 2/7 on 07-13).
    # SHIP cells come from h_full_regime_sweep.py's ADD-candidate emit. Empty
    # list is meaningful — "no new add candidates" is a legitimate stable
    # state to track.
    claims["H_L4_ADD_CANDIDATES"] = _claim_marginal_ship_cells(
        "h_l4_add_candidates.json", allow_empty=True
    )
    return claims


def claim_eq(a, b):
    """Equality that treats sets as unordered."""
    if isinstance(a, (set, list, tuple)) and isinstance(b, (set, list, tuple)):
        return set(a) == set(b)
    return a == b
