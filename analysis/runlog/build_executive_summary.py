#!/usr/bin/env python3
"""Build the executive-summary section of DIGEST.txt.

Inputs:
  - analysis/output/runlog/<script>.log  — per-script logs from run_digest.sh
  - analysis/output/runlog/run_status.tsv — name<TAB>status<TAB>secs per script
  - analysis/output/runlog/digest_state.json — prior-run verdicts (delta source)

Outputs:
  - prints the executive-summary block to stdout
  - rewrites digest_state.json with current verdicts

Verdict extraction: searches each log for the LAST line matching one of the
canonical verdict shapes, then buckets by keyword. Comparison against the
prior digest_state.json drives the "new" / "changed" sections.
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Tooling lives in analysis/runlog/; outputs live in analysis/output/runlog/.
LOG_DIR = HERE.parent / "output" / "runlog"
STATE_PATH = LOG_DIR / "digest_state.json"
HISTORY_PATH = LOG_DIR / "digest_history.jsonl"
STATUS_TSV = LOG_DIR / "run_status.tsv"

VERDICT_LINE_RE = re.compile(
    r"(VERDICT\s*[:\(]|^[ \t]*Verdict\s*:|^[ \t]*→[ \t]*[A-Z]|^[ \t]*RESULT\s*:)"
)

# Scripts that emit per-(field, regime, lead_band) or per-cell verdicts — the
# resolution required to ship a live-pipeline change without hiding regime-
# specific damage in an aggregate. Only "promote" verdicts from these scripts
# get surfaced as "New promotions." Everything else routes to "New candidates
# (aggregate-only — cross-cut required before shipping)" so morning-digest
# readers don't act on a single-number ship signal.
#
# This list is a WHITELIST — new scripts default to aggregate until proven
# otherwise. Codified 2026-07-03 after the h + L4 walkforward-vs-cross-cut
# incident: aggregate said +5.2% overall win; per-cell cross-cut said 21
# L4 LOSES / 4 WIN. See feedback_do_it_right.
SHIP_RESOLUTION_SCRIPTS = frozenset({
    "walkforward_l3l4_validator",
    "l3_regime_lead_analysis",
    "l4_regime_lead_analysis",
    "l5_solar_analysis",
    "c1_calibration_audit",
    "c1_stage4_audit",
    "production_whatif",
    # Orthogonality checks emit per-axis-pair verdicts — sufficient for the
    # promote/kill signals they're designed to give.
    "cluster_spread_orthogonality",
    "h_c1g_orthogonality",
    "h_cloud_disagreement_orthogonality",
    "h_hsf_orthogonality",
    "h_precip_fc_orthogonality",
    "h_pre_front_orthogonality",
    "h_wind_shift_rate_orthogonality",
})

# Live-layer change gate (codified 2026-07-03):
#   1. 7 consecutive daily digest reads all agreeing on the verdict.
#   2. At least 2 tools answering DIFFERENT questions agreeing (not just 2
#      tools reading the same data).
#   3. Per-cell resolution (SHIP_RESOLUTION_SCRIPTS whitelist above).
#   4. Post-deploy verification within 1 Fitter cycle (separate infra, TODO).
#   5. Post-ship 14-day watch for verdict flips (separate infra, TODO).
# This dict groups tools by the question they answer. A ship candidate needs
# promote-verdicts from AT LEAST 2 GROUPS.
TOOL_QUESTION_GROUPS = {
    "per_cell_aggregate": {
        "walkforward_l3l4_validator",       # per-(regime, lead_band), MAE
    },
    "regime_conditional": {
        "l3_regime_lead_analysis",
        "l4_regime_lead_analysis",
        "l5_solar_analysis",
    },
    "live_pipeline_replay": {
        "production_whatif",                # simulates the actual pipeline
    },
    "calibration_drift": {
        "c1_calibration_audit",
        "c1_stage4_audit",
    },
    "orthogonality": {
        "cluster_spread_orthogonality",
        "h_c1g_orthogonality",
        "h_cloud_disagreement_orthogonality",
        "h_hsf_orthogonality",
        "h_precip_fc_orthogonality",
        "h_pre_front_orthogonality",
        "h_wind_shift_rate_orthogonality",
    },
}
CONFIRMATION_STREAK_DAYS = 7

# Post-ship 14-day watch. Any live-layer change is monitored for verdict
# flips during the 14 days after it ships. The ledger lives at
# analysis/output/runlog/shipped_ledger.jsonl — one JSON line per ship.
# Format: {"shipped_at": "YYYY-MM-DD", "script": "walkforward_l3l4_validator",
#          "change": "human-readable description of what shipped",
#          "verdict_at_ship": "the winning verdict text at ship time"}
# Watch window is computed as shipped_at + POST_SHIP_WATCH_DAYS.
POST_SHIP_WATCH_DAYS = 14
SHIPPED_LEDGER_PATH = HERE / "shipped_ledger.jsonl"


def extract_verdict(log_path: Path) -> str | None:
    """Return a one-line verdict string or None."""
    try:
        text = log_path.read_text(errors="replace")
    except FileNotFoundError:
        return None
    matches = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if VERDICT_LINE_RE.search(line):
            stripped = line.strip()
            if len(stripped) > 140:
                stripped = stripped[:137] + "..."
            matches.append(stripped)
    if not matches:
        return None
    return matches[-1]


def bucket(verdict: str | None) -> str:
    """Classify a verdict line into a bucket."""
    if verdict is None:
        return "no_verdict"
    v = verdict.upper()
    if "KILL" in v or "RETIRE" in v:
        return "kill"
    if "SHIP" in v or "PROMOTE" in v or "IMPLEMENT" in v:
        return "promote"
    if "HOLD" in v or "CLOSE" in v or "WASH" in v or "MIXED" in v or "NOT READY" in v or "DEFER" in v:
        return "hold"
    return "info"


def load_prior_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def main():
    if not STATUS_TSV.exists():
        print("ERROR: run_status.tsv missing — run runner first.", file=sys.stderr)
        return 1

    rows = []
    for line in STATUS_TSV.read_text().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, status, secs = parts[0], parts[1], parts[2]
        rows.append((name, status, secs))

    n_total = len(rows)
    n_pass = sum(1 for _, s, _ in rows if s.startswith("OK"))
    n_fail = n_total - n_pass

    prior = load_prior_state()
    current = {}
    # "promotes_new" is only for scripts at ship resolution. Aggregate-only
    # scripts route to "candidates_new" so morning readers see the signal
    # without treating it as ship-ready.
    promotes_new, candidates_new, kills_new, changed, failures = [], [], [], [], []

    for name, status, secs in rows:
        log = LOG_DIR / f"{name}.log"
        verdict = extract_verdict(log)
        b = bucket(verdict)
        current[name] = {"verdict": verdict, "bucket": b}

        if not status.startswith("OK"):
            failures.append((name, status, verdict))
            continue

        prior_b = prior.get(name, {}).get("bucket")
        prior_v = prior.get(name, {}).get("verdict")
        ship_res = name in SHIP_RESOLUTION_SCRIPTS

        if prior_b is None:
            # first time we've seen this script — only count it as "new" if it
            # actually produced a verdict
            if b == "promote":
                (promotes_new if ship_res else candidates_new).append((name, verdict))
            elif b == "kill":
                kills_new.append((name, verdict))
            continue

        if b != prior_b:
            changed.append((name, prior_v, verdict))
            if b == "promote" and prior_b != "promote":
                (promotes_new if ship_res else candidates_new).append((name, verdict))
            if b == "kill" and prior_b != "kill":
                kills_new.append((name, verdict))

    out = []
    out.append("==================================================")
    out.append("EXECUTIVE SUMMARY")
    out.append("==================================================")
    out.append("")
    out.append(f"Scripts run: {n_total}")
    out.append(f"Pass: {n_pass}")
    out.append(f"Fail: {n_fail}")
    out.append("")
    # Compute confirmation streaks across HISTORY_PATH. For each ship-resolution
    # script currently in promote bucket, walk back through history to count
    # consecutive daily reads that were also in promote bucket. Ship-eligible
    # verdicts require CONFIRMATION_STREAK_DAYS AND multi-group agreement.
    from collections import defaultdict as _dd
    streaks = {}  # script_name -> consecutive promote days
    prior_by_script_day = _dd(dict)
    if HISTORY_PATH.exists():
        for row in HISTORY_PATH.read_text().splitlines():
            try:
                r = json.loads(row)
            except json.JSONDecodeError:
                continue
            if not r.get("script") or r["script"].startswith("_claim:"):
                continue
            day = (r.get("run_at") or "")[:10]  # YYYY-MM-DD
            if day:
                prior_by_script_day[r["script"]][day] = r.get("bucket")
    from datetime import date as _date, timedelta as _td
    today_d = _date.today()
    for name, info in current.items():
        if info["bucket"] != "promote":
            continue
        s = 1  # today counts
        d = today_d
        while True:
            d = d - _td(days=1)
            prev_bucket = prior_by_script_day.get(name, {}).get(d.isoformat())
            if prev_bucket == "promote":
                s += 1
                continue
            break
        streaks[name] = s

    # Split promotes_new into ship-eligible vs still-confirming.
    def _group_of(script_name):
        for g, members in TOOL_QUESTION_GROUPS.items():
            if script_name in members:
                return g
        return None
    all_promote_ship_res = [n for n in current
                            if current[n]["bucket"] == "promote" and n in SHIP_RESOLUTION_SCRIPTS]
    promoting_groups = {_group_of(n) for n in all_promote_ship_res if _group_of(n)}
    n_groups = len(promoting_groups)

    ship_eligible = []      # cleared 7 days + ≥2 groups agreeing
    still_confirming = []   # in promote bucket but streak < 7 OR only 1 group
    for name, verdict in promotes_new:
        streak = streaks.get(name, 1)
        if streak >= CONFIRMATION_STREAK_DAYS and n_groups >= 2:
            ship_eligible.append((name, verdict, streak))
        else:
            reason = []
            if streak < CONFIRMATION_STREAK_DAYS:
                reason.append(f"{streak}/{CONFIRMATION_STREAK_DAYS} days confirmed")
            if n_groups < 2:
                reason.append(f"only {n_groups} tool-group agreeing (need 2)")
            still_confirming.append((name, verdict, "; ".join(reason)))

    out.append("SHIP-ELIGIBLE (cleared 7-day + multi-tool gate):")
    if ship_eligible:
        for n, v, s in ship_eligible:
            out.append(f"  • {n} — {v}  [{s}/7 days confirmed]")
    else:
        out.append("  • none")
    out.append("")
    out.append("Still confirming (per-cell tool says promote but gate not cleared):")
    if still_confirming:
        for n, v, why in still_confirming:
            out.append(f"  • {n} — {v}  [{why}]")
    else:
        out.append("  • none")
    out.append("")
    out.append("New candidates (aggregate-only tools — cross-cut required before shipping):")
    if candidates_new:
        for n, v in candidates_new:
            out.append(f"  • {n} — {v}")
    else:
        out.append("  • none")
    out.append("")

    # Post-ship 14-day watch: scan shipped_ledger for any active-watch ships,
    # flag any whose responsible script has flipped verdict since ship.
    post_ship_alerts = []
    if SHIPPED_LEDGER_PATH.exists():
        from datetime import date as _dt_date, timedelta as _dt_td
        today_date = _dt_date.today()
        for line in SHIPPED_LEDGER_PATH.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            shipped_str = entry.get("shipped_at")
            script = entry.get("script")
            if not shipped_str or not script:
                continue
            try:
                shipped_date = _dt_date.fromisoformat(shipped_str)
            except ValueError:
                continue
            watch_until = shipped_date + _dt_td(days=POST_SHIP_WATCH_DAYS)
            if today_date > watch_until:
                continue  # watch window closed
            # Fetch current verdict.
            cur_info = current.get(script) or {}
            cur_bucket = cur_info.get("bucket")
            verdict_at_ship = entry.get("verdict_at_ship") or ""
            # Divergence if current bucket is no longer "promote" (assuming ship
            # was of a promote-verdict). Includes flip to kill or hold.
            if cur_bucket not in ("promote", None):
                days_since = (today_date - shipped_date).days
                post_ship_alerts.append({
                    "script": script,
                    "shipped_at": shipped_str,
                    "change": entry.get("change") or "(no change description)",
                    "verdict_at_ship": verdict_at_ship,
                    "current_verdict": cur_info.get("verdict") or "(no current verdict)",
                    "days_since": days_since,
                    "watch_remaining": (watch_until - today_date).days,
                })

    out.append("Post-ship 14-day watch alerts (verdict flipped after ship):")
    if post_ship_alerts:
        for a in post_ship_alerts:
            out.append(f"  ⚠  {a['script']} — {a['change']}")
            out.append(f"     shipped {a['shipped_at']} ({a['days_since']}d ago; {a['watch_remaining']}d watch remaining)")
            out.append(f"     verdict at ship:   {a['verdict_at_ship']}")
            out.append(f"     current verdict:   {a['current_verdict']}")
    else:
        out.append("  • none")
    out.append("")

    out.append("New kills:")
    if kills_new:
        for n, v in kills_new:
            out.append(f"  • {n} — {v}")
    else:
        out.append("  • none")
    out.append("")
    out.append("Changed verdicts:")
    if changed:
        for n, pv, nv in changed:
            pv_s = pv if pv else "(no prior verdict)"
            nv_s = nv if nv else "(no verdict)"
            out.append(f"  • {n}: {pv_s}  →  {nv_s}")
    else:
        out.append("  • none")
    out.append("")
    out.append("Needs attention:")
    if failures:
        for n, s, v in failures:
            out.append(f"  • {n} {s} — {v or '(no verdict captured)'}")
    else:
        out.append("  • none")
    out.append("")
    out.append("==================================================")
    out.append("")

    print("\n".join(out))

    STATE_PATH.write_text(json.dumps(current, indent=2, sort_keys=True))

    # Append per-script verdicts to the history log (one row per script per
    # run). Used by divergence_report.py to compute disagreement streaks.
    # We also stash one history row per *claim* (production-state derived
    # from today's verdicts) so streak counting can compare structured state,
    # not just truncated verdict text.
    from datetime import datetime, timezone
    sys.path.insert(0, str(HERE))
    from claims import compute_claims
    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    today_claims = compute_claims(current)
    with HISTORY_PATH.open("a") as f:
        for name, info in sorted(current.items()):
            f.write(json.dumps({
                "run_at": run_at,
                "script": name,
                "verdict": info["verdict"],
                "bucket": info["bucket"],
            }) + "\n")
        # Claim rows are stored under a "_claim:" prefix so streak walkers
        # can grep them efficiently.
        for key, val in today_claims.items():
            f.write(json.dumps({
                "run_at": run_at,
                "script": f"_claim:{key}",
                "claim": list(val) if isinstance(val, (set, frozenset)) else val,
            }) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
