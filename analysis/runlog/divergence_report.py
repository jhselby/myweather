#!/usr/bin/env python3
"""Compare today's analysis-script verdicts to actual production state.

Surfaces cases where the live evidence (latest script verdict) and shipped
state disagree. For each mapped script:
  - production_state: what's live in code (read directly from source files).
  - script_wants:     what today's verdict implies.
  - status:           AGREE / DISAGREE / UNKNOWN.

This is the "today" snapshot. The history-aware version (streak-of-N reads
against the gate threshold) is a follow-up once digest_history.jsonl has
enough rows.

Run: python3 analysis/output/runlog/divergence_report.py
"""
import ast
import json
import re
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LOG_DIR = HERE.parent / "output" / "runlog"
STATE_PATH = LOG_DIR / "digest_state.json"
HISTORY_PATH = LOG_DIR / "digest_history.jsonl"

# Per-key promotion gate: how many consecutive matching claims a script
# needs to publish before the disagreement counts as actionable.
GATES = {
    "L3_FIELDS": 7,   # whitelist-promotion-gate
    "L4_FIELDS": 7,
    "LSR_ENABLED": 7,  # L5 trajectory gate
    "LT_ENABLED": 2,  # post-build confirmation reads; first one in hand
}


L5_GATE_HISTORY_URL = "https://data.wymancove.com/l5_gate_history.json"
L5_GATE_HISTORY_CACHE = REPO / ".cache_l5_gate_history.json"  # local cache path
L5_GATE_WINDOW_DAYS = 7  # mirror weather_collector.processors.decay_fit


def _fetch_l5_gate_history():
    """Fetch the live L5 gate history from data.wymancove.com.

    Tiny file (~few KB), no caching needed — but we tolerate fetch failure
    by falling back to the on-disk cache.
    """
    try:
        req = urllib.request.Request(
            L5_GATE_HISTORY_URL, headers={"User-Agent": "myweather-divergence/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
        L5_GATE_HISTORY_CACHE.write_bytes(data)
        return json.loads(data)
    except Exception:
        if L5_GATE_HISTORY_CACHE.exists():
            try:
                return json.loads(L5_GATE_HISTORY_CACHE.read_bytes())
            except Exception:
                return None
        return None


def _l5_trajectory_state():
    """Return (ship_days, hold_days, total_days, streak_ship, gate_clear)
    from the live L5 gate history, or None if unavailable.

    Day-rollup mirrors decay_fit._compute_l5_gate_7d: a day counts as SHIP
    only if every Fitter cycle that day was SHIP. Gate clears when
    7 SHIP days with 0 HOLD and 0 insufficient_data.
    """
    hist = _fetch_l5_gate_history()
    if not hist:
        return None
    entries = hist.get("entries", [])
    if not entries:
        return None
    # Trim to the trailing window the live code uses.
    entries_sorted = sorted(entries, key=lambda e: e.get("fitted_at", ""))
    if len(entries_sorted) > 100:
        entries_sorted = entries_sorted[-100:]
    # Day rollup over the last 7 days of entries we have.
    from collections import defaultdict
    by_day = defaultdict(list)
    for e in entries_sorted:
        day = e.get("fitted_at", "")[:10]
        if day:
            by_day[day].append(e.get("verdict", ""))
    # Take the latest 7 unique days.
    latest_days = sorted(by_day)[-L5_GATE_WINDOW_DAYS:]
    ship = hold = insuff = 0
    for d in latest_days:
        verdicts = by_day[d]
        if all(v == "SHIP" for v in verdicts):
            ship += 1
        elif any(v == "insufficient_data" for v in verdicts):
            insuff += 1
        else:
            hold += 1
    # Streak of trailing SHIP entries (cycle-level, not day-level).
    streak = 0
    for e in reversed(entries_sorted):
        if e.get("verdict") == "SHIP":
            streak += 1
        else:
            break
    gate_clear = (len(latest_days) >= L5_GATE_WINDOW_DAYS
                  and hold == 0 and insuff == 0)
    return {
        "ship_days": ship,
        "hold_days": hold,
        "insufficient_days": insuff,
        "total_days": len(latest_days),
        "streak_cycles": streak,
        "gate_clear": gate_clear,
    }


def _streak_for(key, today_claim):
    """Walk digest_history.jsonl backward; count consecutive prior runs
    whose claim for `key` equaled `today_claim`. Excludes today's run.

    Returns (streak_count, oldest_matching_run_at).
    """
    if not HISTORY_PATH.exists() or today_claim is None:
        return 0, None
    rows = []
    needle = f'"_claim:{key}"'
    with HISTORY_PATH.open() as f:
        for line in f:
            if needle not in line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        return 0, None
    # Group by calendar day and keep one row per day (the latest run that day).
    # Multiple digest runs on the same day collapse into one "read" so that
    # re-running on cached data doesn't falsely advance the streak — the gate
    # is designed around independent reads on different days.
    rows.sort(key=lambda r: r["run_at"])
    per_day = {}
    for r in rows:
        day = r["run_at"][:10]
        per_day[day] = r  # later runs overwrite earlier ones for the same day
    rows = sorted(per_day.values(), key=lambda r: r["run_at"])

    today_norm = sorted(today_claim) if isinstance(today_claim, (list, set, tuple)) else today_claim
    streak = 0
    oldest = None
    for r in reversed(rows[:-1]):  # skip today's row
        c = r.get("claim")
        c_norm = sorted(c) if isinstance(c, list) else c
        if c_norm == today_norm:
            streak += 1
            oldest = r["run_at"]
        else:
            break
    return streak, oldest


# ──────────────────────── production-state probes ─────────────────────────

def read_const(path: Path, name: str):
    """Eval a top-level `NAME = <literal>` assignment from a source file."""
    src = path.read_text()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except (ValueError, SyntaxError):
                        return None
    return None


def probe_production():
    decay = REPO / "weather_collector/processors/decay_apply.py"
    solar = REPO / "weather_collector/processors/solar_correction.py"
    cove = REPO / "weather_collector/processors/cove_correction.py"
    marine = REPO / "weather_collector/processors/marine_layer_correction.py"
    hourly = REPO / "weather_collector/processors/corrected_hourly.py"
    cloud_sat = REPO / "weather_collector/processors/cloud_saturation_correction.py"

    return {
        "L3_FIELDS": read_const(decay, "L3_FIELDS"),
        "L4_FIELDS": read_const(decay, "L4_FIELDS"),
        "LSR_ENABLED": read_const(solar, "ENABLED"),
        "LT_ENABLED": read_const(cove, "ENABLED"),
        "LC_ENABLED": read_const(cloud_sat, "ENABLED") if cloud_sat.exists() else None,
        "MARINE_ENABLED": read_const(marine, "ENABLED") if marine.exists() else None,
        "L2_TAUS": read_const(hourly, "DEFAULT_L2_TAUS"),
    }


# ─────────────────── script-verdict → production-claim ────────────────────

def claim_from_walkforward(verdict: str):
    """walkforward_l3l4_validator's last log emits two `L3_ENABLED` and
    `L4_ENABLED` lines we can scrape from the underlying log file."""
    log = LOG_DIR / "walkforward_l3l4_validator.log"
    if not log.exists():
        return None
    txt = log.read_text()
    m3 = re.search(r"L3_ENABLED\s*=\s*(\{[^}]*\})", txt)
    m4 = re.search(r"L4_ENABLED\s*=\s*(\{[^}]*\})", txt)
    try:
        l3 = ast.literal_eval(m3.group(1)) if m3 else None
        l4 = ast.literal_eval(m4.group(1)) if m4 else None
    except Exception:
        return None
    return {"L3_FIELDS": l3, "L4_FIELDS": l4}


def claim_bool_ship(verdict: str) -> bool | None:
    if verdict is None:
        return None
    v = verdict.upper()
    if "SHIP" in v and "→ SHIP" not in v[:8]:  # avoid header lines
        return True
    if "HOLD" in v or "CLOSE" in v or "RETIRE" in v:
        return False
    if "SHIP" in v:
        return True
    return None


# ─────────────────────────── report builder ───────────────────────────────

def main():
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    prod = probe_production()

    rows = []  # (label, production, script_wants, status, notes)

    # L3 / L4 whitelist (walkforward)
    wf = state.get("walkforward_l3l4_validator", {}).get("verdict")
    wants = claim_from_walkforward(wf) if wf else None
    if wants:
        for k in ("L3_FIELDS", "L4_FIELDS"):
            p, w = prod.get(k), wants.get(k)
            if p is None or w is None:
                status = "UNKNOWN"
                notes = ""
            elif set(p) == set(w):
                status = "AGREE"
                notes = ""
            else:
                status = "DISAGREE"
                drop = sorted(set(p) - set(w))
                add = sorted(set(w) - set(p))
                bits = []
                if drop: bits.append(f"drop {','.join(drop)}")
                if add:  bits.append(f"add {','.join(add)}")
                notes = "; ".join(bits)
            rows.append((k, p, w, status, notes))

    # L5 solar
    v = state.get("l5_solar_analysis", {}).get("verdict")
    wants_bool = claim_bool_ship(v)
    p = prod.get("LSR_ENABLED")
    if wants_bool is None:
        rows.append(("LSR_ENABLED", p, None, "UNKNOWN", "verdict didn't classify"))
    else:
        status = "AGREE" if p == wants_bool else "DISAGREE"
        rows.append(("LSR_ENABLED", p, wants_bool, status, ""))

    # Cove
    v = state.get("r5_cove_analysis", {}).get("verdict")
    wants_bool = claim_bool_ship(v)
    p = prod.get("LT_ENABLED")
    if wants_bool is None:
        rows.append(("LT_ENABLED", p, None, "UNKNOWN", "verdict didn't classify"))
    else:
        status = "AGREE" if p == wants_bool else "DISAGREE"
        rows.append(("LT_ENABLED", p, wants_bool, status, ""))

    # Lc — cloud saturation-unbiasing. lc_fit.py emits "Verdict: FIT — N SHIP
    # cell(s) ready to wire into Lc." when the pair-log has SHIP cells,
    # otherwise "Verdict: HOLD — no cells cleared the SHIP gate." The 7-day
    # live-layer change gate lives in the exec summary, not here; this row
    # just surfaces whether production ENABLED matches what the fit says
    # would work if wired.
    v = state.get("lc_fit", {}).get("verdict")
    p = prod.get("LC_ENABLED")
    if v is None:
        rows.append(("LC_ENABLED", p, None, "UNKNOWN", "lc_fit hasn't reported"))
    else:
        wants_bool = True if "FIT" in v.upper() and "SHIP" in v.upper() else (False if "HOLD" in v.upper() else None)
        if wants_bool is None:
            rows.append(("LC_ENABLED", p, None, "UNKNOWN", "verdict didn't classify"))
        elif p == wants_bool:
            rows.append(("LC_ENABLED", p, wants_bool, "AGREE", ""))
        else:
            # DISAGREE means "fit says ship-ready, production not enabled."
            # Note the 7-day gate so a reader doesn't think we're stalling.
            rows.append(("LC_ENABLED", p, wants_bool, "DISAGREE", "7-day live-layer gate — flip after 7 daily reads agree"))

    # Marine layer — stage1+stage2 don't print a clean VERDICT line yet.
    # Skip for today; surface as TODO.

    # ── render ──
    print("=" * 78)
    print("DIVERGENCE REPORT — production vs latest script verdict")
    print("=" * 78)
    print()
    print(f"  {'KEY':<14} {'PRODUCTION':<20} {'SCRIPT WANTS':<20} {'STATUS':<8} STREAK")
    print("  " + "-" * 88)
    # L5 has its own Fitter-cycle trajectory tracker — use that instead of
    # the freshly-started divergence streak for the LSR_ENABLED row.
    l5_traj = _l5_trajectory_state()

    def _direction(p, w):
        """↑ = production should enable/grow, ↓ = production should disable/shrink."""
        if isinstance(p, bool) and isinstance(w, bool):
            return "↑" if (w and not p) else "↓"
        if isinstance(p, (set, list, tuple, frozenset)) and isinstance(w, (set, list, tuple, frozenset)):
            return "↓" if len(set(w)) <= len(set(p)) else "↑"
        return "·"

    final_statuses = []
    for k, p, w, status, notes in rows:
        p_s = str(p) if p is not None else "—"
        w_s = str(w) if w is not None else "—"
        if len(p_s) > 19: p_s = p_s[:18] + "…"
        if len(w_s) > 19: w_s = w_s[:18] + "…"
        if status == "DISAGREE":
            if k == "LSR_ENABLED" and l5_traj is not None:
                if l5_traj["gate_clear"]:
                    streak_s = (f"GATE CLEARED ({l5_traj['ship_days']}/"
                                f"{L5_GATE_WINDOW_DAYS} ship days)")
                    status = "READY"
                else:
                    streak_s = (f"{l5_traj['ship_days']}/{L5_GATE_WINDOW_DAYS} "
                                f"ship days · {l5_traj['hold_days']} hold · "
                                f"{l5_traj['streak_cycles']}-cycle SHIP streak")
                    status = "GATED"
            else:
                streak, _oldest = _streak_for(k, w)
                count = streak + 1  # today's run itself counts as one read
                gate = GATES.get(k)
                if gate is not None and count >= gate:
                    streak_s = f"GATE CLEARED ({count}/{gate})"
                    status = "READY"
                elif gate is not None:
                    streak_s = f"{count}/{gate} ({gate - count} to go)"
                    status = "GATED"
                else:
                    streak_s = f"{count}/?"
                    status = "GATED"
        else:
            streak_s = "—"

        # Icon: ✓ agree, ⏳ gated, ↑/↓ ready (with direction), ✗ unknown.
        if status == "AGREE":
            icon = "✓"
        elif status == "GATED":
            icon = "⏳"
        elif status == "READY":
            icon = _direction(p, w)  # ↑ or ↓
        else:
            icon = "✗"

        final_statuses.append(status)
        line = f"{icon} {k:<14} {p_s:<20} {w_s:<20} {status:<8} {streak_s}"
        if notes:
            line += f"   ({notes})"
        print(line)
    print()
    n_gated = sum(1 for s in final_statuses if s == "GATED")
    n_ready = sum(1 for s in final_statuses if s == "READY")
    n_unk = sum(1 for s in final_statuses if s == "UNKNOWN")
    n_ok = sum(1 for s in final_statuses if s == "AGREE")
    print(f"Summary: {n_ready} gate-cleared, {n_gated} gated, "
          f"{n_unk} unknown, {n_ok} aligned.")


if __name__ == "__main__":
    main()
