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
    promotes_new, kills_new, changed, failures = [], [], [], []

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

        if prior_b is None:
            # first time we've seen this script — only count it as "new" if it
            # actually produced a verdict
            if b == "promote":
                promotes_new.append((name, verdict))
            elif b == "kill":
                kills_new.append((name, verdict))
            continue

        if b != prior_b:
            changed.append((name, prior_v, verdict))
            if b == "promote" and prior_b != "promote":
                promotes_new.append((name, verdict))
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
    out.append("New promotions:")
    if promotes_new:
        for n, v in promotes_new:
            out.append(f"  • {n} — {v}")
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
