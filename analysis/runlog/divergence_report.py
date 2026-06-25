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
    "L5_ENABLED": 7,  # L5 trajectory gate
    "COVE_ENABLED": 2,  # post-build confirmation reads; first one in hand
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
    # Group by run_at and pick the most recent timestamp as "today"; count
    # backward from there.
    rows.sort(key=lambda r: r["run_at"])
    today_run = rows[-1]["run_at"]
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

    return {
        "L3_FIELDS": read_const(decay, "L3_FIELDS"),
        "L4_FIELDS": read_const(decay, "L4_FIELDS"),
        "L5_ENABLED": read_const(solar, "ENABLED"),
        "COVE_ENABLED": read_const(cove, "ENABLED"),
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
    p = prod.get("L5_ENABLED")
    if wants_bool is None:
        rows.append(("L5_ENABLED", p, None, "UNKNOWN", "verdict didn't classify"))
    else:
        status = "AGREE" if p == wants_bool else "DISAGREE"
        rows.append(("L5_ENABLED", p, wants_bool, status, ""))

    # Cove
    v = state.get("r5_cove_analysis", {}).get("verdict")
    wants_bool = claim_bool_ship(v)
    p = prod.get("COVE_ENABLED")
    if wants_bool is None:
        rows.append(("COVE_ENABLED", p, None, "UNKNOWN", "verdict didn't classify"))
    else:
        status = "AGREE" if p == wants_bool else "DISAGREE"
        rows.append(("COVE_ENABLED", p, wants_bool, status, ""))

    # Marine layer — stage1+stage2 don't print a clean VERDICT line yet.
    # Skip for today; surface as TODO.

    # ── render ──
    print("=" * 78)
    print("DIVERGENCE REPORT — production vs latest script verdict")
    print("=" * 78)
    print()
    print(f"{'KEY':<16} {'PRODUCTION':<20} {'SCRIPT WANTS':<20} {'STATUS':<14} STREAK")
    print("-" * 90)
    final_statuses = []
    for k, p, w, status, notes in rows:
        p_s = str(p) if p is not None else "—"
        w_s = str(w) if w is not None else "—"
        if len(p_s) > 19: p_s = p_s[:18] + "…"
        if len(w_s) > 19: w_s = w_s[:18] + "…"
        if status == "DISAGREE":
            streak, _oldest = _streak_for(k, w)
            count = streak + 1  # today's run itself counts as one read
            gate = GATES.get(k)
            if gate is not None and count >= gate:
                streak_s = f"GATE CLEARED ({count}/{gate})"
                status = "READY"
            elif gate is not None:
                streak_s = f"{count}/{gate} ({gate - count} to go)"
            else:
                streak_s = f"{count}/?"
        else:
            streak_s = "—"
        final_statuses.append(status)
        line = f"{k:<16} {p_s:<20} {w_s:<20} {status:<14} {streak_s}"
        if notes:
            line += f"   ({notes})"
        print(line)
    print()
    n_dis = sum(1 for s in final_statuses if s == "DISAGREE")
    n_ready = sum(1 for s in final_statuses if s == "READY")
    n_unk = sum(1 for s in final_statuses if s == "UNKNOWN")
    n_ok = sum(1 for s in final_statuses if s == "AGREE")
    print(f"Summary: {n_ready} gate-cleared, {n_dis} disagreement(s) below gate, "
          f"{n_unk} unknown, {n_ok} agreement(s).")


if __name__ == "__main__":
    main()
