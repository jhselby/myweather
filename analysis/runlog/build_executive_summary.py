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
# Scripts that emit action verbs (SHIP/PROMOTE/IMPLEMENT/"Move to Stage N"/
# "STAGE 1 HIT") for pipelines that are ALREADY LIVE. The verdict is a stability
# re-check, not a new action item. Relabels to STABLE before bucketing so the
# morning-digest reader doesn't propose already-done work.
#
# Six prior instances documented (feedback_stated_intent_vs_code_behavior +
# project_07_18_session): divergence-reporter regex (07-07), scorecard-Brier
# folding (07-07), wind-shift-rate ortho=0 (07-09 AM), C1f precip_fc live
# (07-09 PM), simulate_windows R6 (07-09 PM), h_l3_asymmetric_stage1 "Move
# to Stage 2 wiring" (07-23). Ideal fix is to add a STABLE self-check to the
# emitting script following h_precip_fc_orthogonality.py's pattern; this
# registry is the digest-side backstop that catches scripts not yet fixed.
KNOWN_LIVE_PIPELINES = {
    "h_l3_asymmetric_stage1": {
        "target": "L3 asymmetric fc-bin SKIP tables (wg, ws)",
        "since": "v0.6.366 (wg) / v0.6.370 (ws)",
        "date": "2026-07-20",
    },
    "h_c1h_orthogonality": {
        "target": "C1h trend-direction axis in confidence_layer.py "
                  "(_C1H_CELLS + _C1H_CO_AXIS_GATE)",
        "since": "v0.6.316",
        "date": "2026-07-10",
    },
    "h_cloud_disagreement_orthogonality": {
        "target": "C1d KBOS-vs-KBVY σ axis in confidence_layer.py "
                  "(c1d_curated.json loader)",
        "since": "Stage 3",
        "date": "2026-07-08",
    },
    "h_ch_persistence_blend": {
        "target": "ch persistence gate (chp) — L4-vs-persistence regime gate",
        "since": "v0.6.358",
        "date": "2026-07-19",
    },
    "h_ch_persistence_blend_stage2": {
        "target": "ch persistence gate (chp) Stage 2 curated skip table "
                  "(ch_persistence_gate_curated.json)",
        "since": "v0.6.358",
        "date": "2026-07-19",
    },
    "lc_fit": {
        "target": "Lc lead-decay correction (lc_correction_table.json). "
                  "Fitter re-emits SHIP cells each run; live table already reads them.",
        "since": "v0.6.354",
        "date": "2026-07-17",
    },
    # NOT registered (deliberate):
    #   walkforward_l3l4_validator — composite. L4 {ch,cc} half live but L3
    #     half proposes real drop of wg/ws. Registering would suppress the
    #     drop signal.
    #   cluster_spread_orthogonality / cluster_spread_smoketest — already
    #     emit their own STABLE self-check line.
    #   h_precip_fc_orthogonality — already emits its own STABLE self-check.
    #
    # Add entries as instances are caught. When adding, prefer to also add a
    # STABLE self-check to the script itself (see h_precip_fc_orthogonality.py).
}


def relabel_stable_recheck(script_name, verdict):
    """If script_name is a KNOWN_LIVE_PIPELINES entry and the verdict is
    action-verb-shaped, relabel to STABLE. Returns (new_verdict, was_relabeled).
    HOLD/MARGIN/KILL/WASH verdicts pass through unchanged — they're their own
    signals even for live pipelines.
    """
    if script_name not in KNOWN_LIVE_PIPELINES or verdict is None:
        return verdict, False
    v_upper = verdict.upper()
    action_verbs = ("SHIP", "PROMOTE", "IMPLEMENT",
                    "MOVE TO STAGE", "STAGE 1 HIT", "STAGE 2 HIT",
                    "STAGE 1 PROMOTE", "STAGE 2 PROMOTE")
    if not any(verb in v_upper for verb in action_verbs):
        return verdict, False
    entry = KNOWN_LIVE_PIPELINES[script_name]
    relabeled = (f"STABLE — {entry['target']} already live since "
                 f"{entry['since']} ({entry['date']}). Re-check pass. "
                 f"Original: {verdict}")
    return relabeled, True


# Cross-script contradictions on the same target. Same failure family as
# KNOWN_LIVE_PIPELINES (proposing action based on one script's verdict without
# checking whether other scripts on the same target disagree), just a different
# manifestation. Class case (2026-07-23): ch persistence gate — h_ch_persistence_blend
# says SHIP with 15-30% regime wins, h_persistence_skill says ch Prod −1.32 BEHIND.
# Both readings are real; they measure different windows (blend script uses fresh
# 30d; persistence_skill uses full pair log including pre-flip Lc-only rows). A
# morning read of only one produces a wrong action.
#
# Each entry lists the scripts that measure a live target + a resolution note
# explaining how to interpret disagreement. If bucket() gives different results
# across the listed scripts, digest emits a CROSS-SCRIPT CONTRADICTIONS section.
TARGET_SCRIPT_GROUPS = {
    "ch_persistence_gate": {
        "target_desc": "ch persistence gate (chp) — live layer since 07-19 v0.6.358",
        "scripts": [
            "h_ch_persistence_blend",
            "h_ch_persistence_blend_stage2",
            "h_persistence_skill",
        ],
        "resolution_note": (
            "h_persistence_skill scans full pair log (~30d, no date filter). "
            "chp shipped 07-19 → only ~4-14d of clean post-flip rows. "
            "h_ch_persistence_blend uses fresh windows. Expect blend script to "
            "lead persistence-skill until pair log ages out pre-flip. See "
            "[[project_chp_midlead_regression_watch]]."
        ),
    },
    # Add entries as instances are caught. Only add when both scripts really
    # measure the same target; don't over-register (a busy contradictions
    # section becomes noise).
}


def cross_script_contradictions(current):
    """Return a list of contradiction records for the digest output.

    A contradiction fires when the scripts in a TARGET_SCRIPT_GROUPS entry
    have MORE THAN ONE non-info bucket. Info/no_verdict buckets are skipped
    (a stability re-check or non-verdict script isn't a real disagreement).
    """
    out = []
    for target, group in TARGET_SCRIPT_GROUPS.items():
        rows = []
        buckets = set()
        for script in group["scripts"]:
            info = current.get(script)
            if not info:
                continue
            b = info.get("bucket")
            v = info.get("verdict")
            if b in (None, "no_verdict"):
                continue
            rows.append((script, b, v))
            if b != "info":
                buckets.add(b)
        if len(buckets) > 1:
            out.append({
                "target": target,
                "target_desc": group["target_desc"],
                "rows": rows,
                "resolution_note": group["resolution_note"],
            })
    return out


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

# Companion-tool pairs — two-step designs where Step 1 measures a signal
# (magnitude / stability / orthogonality) and Step 2 is the authoritative
# ship-decision cross-cut. When both ran in the same digest, the "New
# candidates" section emits the resolved combined verdict (Step 2 wins)
# instead of leaving Step 1 as a task for the reader. Added 2026-07-22
# (v0.6.373) after the r5_cove_analysis SHIP vs r5_audit HOLD re-triage:
# both ran in the same digest and the resolution was already in the file
# 200 lines later, but the exec summary listed Step 1 alone as "cross-cut
# required" as if the audit hadn't run.
#
# Format: step1_script -> step2_script. Both must be in `current` for the
# resolution to apply; otherwise Step 1 emits standalone as before.
COMPANION_PAIRS = {
    "r5_cove_analysis": "r5_audit",
    "h_dp_residual_persistence_stage1": "h_dp_residual_persistence_stage2",
    "h_wg_residual_persistence_stage1": "h_wg_residual_persistence_stage2",
}

# Post-ship 14-day watch. Any live-layer change is monitored for verdict
# flips during the 14 days after it ships. The ledger lives at
# analysis/output/runlog/shipped_ledger.jsonl — one JSON line per ship.
# Format: {"shipped_at": "YYYY-MM-DD", "script": "walkforward_l3l4_validator",
#          "change": "human-readable description of what shipped",
#          "verdict_at_ship": "the winning verdict text at ship time"}
# Watch window is computed as shipped_at + POST_SHIP_WATCH_DAYS.
POST_SHIP_WATCH_DAYS = 14
SHIPPED_LEDGER_PATH = HERE / "shipped_ledger.jsonl"

# Persistence-skill watch. h_persistence_skill.py emits per-field ADDS
# VALUE / MIXED / NO SKILL every digest run. Watch detects two conditions:
#   1. Regression: a field that was ADDS VALUE last run and isn't today.
#   2. At-risk: currently ADDS VALUE but skill_l4_mae_pooled below margin
#      (thin — could slip on the next run).
# Snapshot of last run's per-field verdicts lives at the path below;
# overwritten each digest.
PERSISTENCE_SKILL_JSON_PATH = HERE.parent / "output" / "h_persistence_skill.json"
PERSISTENCE_SKILL_SNAPSHOT_PATH = LOG_DIR / "persistence_skill_snapshot.json"
PERSISTENCE_SKILL_THIN_MARGIN = 0.20

# Anomaly detector — pair-log distribution-shift alert per field. Motivated
# by the 07-11 cm Stage 4 flip that would have been visible a week earlier
# if forecast-value distribution shift were tracked as its own signal.
ANOMALY_DETECTOR_JSON_PATH = HERE.parent / "output" / "anomaly_detector.json"

# Marine-layer stratum bias-collapse detector — companion to the global
# anomaly detector, targeting the ~3%-of-cc stratum where MLC lives.
MARINE_LAYER_ANOMALY_JSON_PATH = HERE.parent / "output" / "marine_layer_anomaly.json"

# Suppress-until registry — settled-known signals that should route to a
# "Suppressed (known)" section instead of the top-of-digest alert slot.
# See weather_collector/data/digest_suppress.json for entry format.
# Added 2026-07-22 (v0.6.373) after the MLC ★ COLLAPSE re-triage incident:
# the 07-16 diagnosis had already settled that the collapse was a real 06-30
# seasonal break, and the alert would continue firing daily until the
# anomaly detector's 21d baseline window rolls past 06-30 (~08-06).
SUPPRESS_REGISTRY_PATH = HERE.parent.parent / "weather_collector" / "data" / "digest_suppress.json"


def _load_suppress_registry():
    """Load the suppress-until registry as a list of entries with parsed dates.
    Filters out entries whose suppress_until date has passed."""
    if not SUPPRESS_REGISTRY_PATH.exists():
        return []
    try:
        doc = json.loads(SUPPRESS_REGISTRY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    import datetime
    today = datetime.date.today()
    active = []
    for entry in doc.get("suppressions") or []:
        end_str = entry.get("suppress_until") or ""
        try:
            end_date = datetime.date.fromisoformat(end_str)
        except ValueError:
            continue
        if today > end_date:
            continue
        active.append(entry)
    return active


def check_suppression(tool: str, signal: str | None = None, verdict: str | None = None):
    """Return the matching suppression entry or None.

    Match rules:
      - tool must equal entry.tool
      - if entry.signal is None → matches any signal for that tool
      - if entry.signal is a string → matches when signal == entry.signal OR
        when the verdict string contains entry.signal (case-insensitive).
    """
    for entry in _load_suppress_registry():
        if entry.get("tool") != tool:
            continue
        want_sig = entry.get("signal")
        if want_sig is None:
            return entry
        if signal is not None and signal == want_sig:
            return entry
        if verdict is not None and want_sig.upper() in verdict.upper():
            return entry
    return None


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
    # STABLE must be checked BEFORE SHIP/PROMOTE — the KNOWN_LIVE_PIPELINES
    # relabel prefixes with "STABLE — ..." but keeps "Original: <PROMOTE>" for
    # transparency, so a naive SHIP/PROMOTE check would still bucket as promote.
    if v.startswith("STABLE") or "STABLE —" in v[:20]:
        return "info"
    if "KILL" in v or "RETIRE" in v or "DRIFT" in v:
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


STALE_WINDOW_DAYS = 3  # any script whose max date literal is older than
                       # today − STALE_WINDOW_DAYS is a fossil-window suspect.
DATE_LITERAL_RE = re.compile(r'"(20\d\d)-(\d\d)-(\d\d)T?')


def stale_window_audit():
    """Scan analysis/*.py for hardcoded date literals in window constants.

    Return a list of warning lines for scripts whose max date literal is
    older than today − STALE_WINDOW_DAYS. This catches the fossil-window
    class of bug: hardcoded WIN_A_LO/HI/WIN_FULL_LO/HI constants that
    were set once and never refreshed, causing the daily digest to
    re-read the same fossilized verdict for weeks. See
    [[feedback_fossil_windows]] (07-19 h/l4 narrow-add incident:
    7/7 gate cleared on a window that ended 8 days behind today).
    """
    import datetime
    analysis_dir = HERE.parent  # analysis/
    today = datetime.date.today()
    threshold = today - datetime.timedelta(days=STALE_WINDOW_DAYS)

    stale = []
    for py in sorted(analysis_dir.glob("*.py")):
        try:
            src = py.read_text()
        except OSError:
            continue
        # Only care about assignments to WIN_* names — this scopes the
        # audit to window constants and avoids false positives on scripts
        # that print historical dates in log text.
        max_date = None
        for line in src.splitlines():
            s = line.strip()
            if not s.startswith("WIN_"):
                continue
            for m in DATE_LITERAL_RE.finditer(line):
                try:
                    d = datetime.date(int(m.group(1)), int(m.group(2)),
                                      int(m.group(3)))
                except ValueError:
                    continue
                if max_date is None or d > max_date:
                    max_date = d
        if max_date is not None and max_date < threshold:
            age = (today - max_date).days
            stale.append(f"  ⚠ {py.name}: max window date {max_date.isoformat()} "
                        f"({age}d behind today)")
    return stale


def anomaly_detector_summary():
    """Return list of alert lines from anomaly_detector.json, or None if absent."""
    if not ANOMALY_DETECTOR_JSON_PATH.exists():
        return None
    try:
        doc = json.loads(ANOMALY_DETECTOR_JSON_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    fields = doc.get("fields") or {}
    lines = []
    for f, d in sorted(fields.items()):
        v = d.get("verdict")
        if v not in ("ANOMALY", "WATCH"):
            continue
        mae_pct = d.get("mae_pct_change")
        sigmas = d.get("d_fc_mean_sigmas")
        bin_shift = d.get("max_bin_shift_pp")
        parts = []
        if mae_pct is not None:
            parts.append(f"ΔMAE {mae_pct:+.1f}%")
        if sigmas is not None:
            parts.append(f"Δfc_mean {sigmas:+.1f}σ")
        if bin_shift is not None:
            parts.append(f"bin shift {bin_shift:.1f}pp")
        mark = "★" if v == "ANOMALY" else "⚠"
        lines.append(f"  {mark} {f}: {v} — {', '.join(parts)}")
    return lines


def marine_layer_anomaly_summary():
    """Return (line, suppression_entry_or_None). `line` is the alert text or None
    if no alert. If a suppression matches, the alert routes to the Suppressed
    section instead of the top-of-digest slot."""
    if not MARINE_LAYER_ANOMALY_JSON_PATH.exists():
        return None, None
    try:
        doc = json.loads(MARINE_LAYER_ANOMALY_JSON_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None, None
    verdict = doc.get("verdict")
    if verdict not in ("COLLAPSE", "DECAY"):
        return None, None
    base = doc.get("in_bin_bias_baseline_mean")
    rec = doc.get("in_bin_bias_recent_mean")
    if base is None or rec is None:
        line = f"  ★ MLC in-bin bias: {verdict}"
    else:
        mark = "★" if verdict == "COLLAPSE" else "⚠"
        line = f"  {mark} MLC in-bin bias: {verdict} — baseline {base:+.2f} → recent {rec:+.2f} (Δ {rec - base:+.2f})"
    suppression = check_suppression("marine_layer_anomaly", signal=verdict, verdict=verdict)
    return line, suppression


def persistence_skill_watch():
    """Return (regression_lines, at_risk_lines, prod_delta_lines). Compares today's
    h_persistence_skill.json against last run's snapshot; overwrites the snapshot.

    Regression: field was ADDS VALUE last run, isn't today.
    At-risk: currently ADDS VALUE but pooled skill below PERSISTENCE_SKILL_THIN_MARGIN.
    Prod-delta: |skill_prod_mae_pooled - skill_l4_mae_pooled| >= 0.02 — specialists
      or L3 actually moving the number vs the L4-only reference.
    """
    if not PERSISTENCE_SKILL_JSON_PATH.exists():
        return None, None, None
    try:
        today = json.loads(PERSISTENCE_SKILL_JSON_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None, None, None
    fields_today = today.get("fields") or {}
    if not fields_today:
        return None, None, None

    prior_fields = {}
    if PERSISTENCE_SKILL_SNAPSHOT_PATH.exists():
        try:
            prior_fields = (json.loads(PERSISTENCE_SKILL_SNAPSHOT_PATH.read_text())
                            .get("fields") or {})
        except (json.JSONDecodeError, OSError):
            prior_fields = {}

    regression_lines = []
    at_risk_lines = []
    prod_delta_lines = []
    for f in sorted(fields_today.keys()):
        info = fields_today[f] or {}
        v_today = info.get("verdict")
        skill = info.get("skill_l4_mae_pooled")
        skill_prod = info.get("skill_prod_mae_pooled")
        v_prior = (prior_fields.get(f) or {}).get("verdict")
        skill_prior = (prior_fields.get(f) or {}).get("skill_l4_mae_pooled")
        if v_prior == "ADDS VALUE" and v_today != "ADDS VALUE":
            sk_txt = f"skill {skill:+.2f}" if skill is not None else "skill n/a"
            sk_prior_txt = f" (was {skill_prior:+.2f})" if skill_prior is not None else ""
            regression_lines.append(
                f"  ⚠ {f}: ADDS VALUE → {v_today} — {sk_txt}{sk_prior_txt}"
            )
        if v_today == "ADDS VALUE" and skill is not None and skill < PERSISTENCE_SKILL_THIN_MARGIN:
            at_risk_lines.append(
                f"  · {f}: ADDS VALUE but pooled skill {skill:+.2f} "
                f"(< {PERSISTENCE_SKILL_THIN_MARGIN:+.2f} margin — could slip)"
            )
        # Prod-vs-L4 delta: catches cases where L3 or specialists move the
        # persistence skill number materially. Positive delta = Production
        # helps vs L4 (specialists working). Negative = Production hurts vs L4
        # (L3/specialist damaging skill; wg L3 and ch L3 pattern).
        if (skill is not None and skill_prod is not None
                and abs(skill_prod - skill) >= 0.02):
            direction = "→" if skill_prod > skill else "↓"
            prod_delta_lines.append(
                f"  {direction} {f}: L4 {skill:+.2f} → Prod {skill_prod:+.2f} "
                f"(Δ {skill_prod - skill:+.2f})"
            )

    snapshot = {
        "recorded_at": today.get("generated_at"),
        "fields": {
            f: {
                "verdict": (info or {}).get("verdict"),
                "skill_l4_mae_pooled": (info or {}).get("skill_l4_mae_pooled"),
                "skill_prod_mae_pooled": (info or {}).get("skill_prod_mae_pooled"),
            }
            for f, info in fields_today.items()
        },
    }
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        PERSISTENCE_SKILL_SNAPSHOT_PATH.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True)
        )
    except OSError:
        pass
    return regression_lines, at_risk_lines, prod_delta_lines


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
    # Track what got auto-relabeled by KNOWN_LIVE_PIPELINES so the digest can
    # show it explicitly rather than silently suppressing.
    stable_recheck_relabels = []

    for name, status, secs in rows:
        log = LOG_DIR / f"{name}.log"
        verdict = extract_verdict(log)
        verdict, relabeled = relabel_stable_recheck(name, verdict)
        if relabeled:
            stable_recheck_relabels.append((name, verdict))
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

    stale_lines = stale_window_audit()
    if stale_lines:
        out.append("⚠ STALE ANALYSIS WINDOWS (fossil-window suspects):")
        out.extend(stale_lines)
        out.append(f"  → Windows are ≥{STALE_WINDOW_DAYS}d behind today. Any 7-day "
                   "streak or gate-cleared verdict on these scripts is likely a")
        out.append("    fossil (re-read of the same data). Slide the WIN_ constants "
                   "forward before trusting a ship signal. See feedback_fossil_windows.")
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
    # v0.6.364: iterate ALL ship-resolution scripts currently in promote
    # bucket, not just those that transitioned to promote today
    # (`promotes_new`). Previous behaviour missed sustained promotes — a
    # script that hit promote days ago and stayed there never re-entered
    # promotes_new, so it never surfaced in ship-eligible even after its
    # streak cleared. Uncovered while investigating v0.6.362 (C1h/C1d
    # narrow-promote GATE CLEARED but SHIP-ELIGIBLE said "none"; those
    # C1h/C1d specifically use the narrow-promote gate walker rather than
    # this SHIP-eligible walker, so this fix targets a related but distinct
    # class of the same problem — sustained promotes on ship-resolution
    # scripts).
    for name in sorted(all_promote_ship_res):
        verdict = current[name]["verdict"]
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
            companion = COMPANION_PAIRS.get(n)
            comp_info = current.get(companion) if companion else None
            if comp_info and comp_info.get("verdict"):
                # Companion (Step 2) ran and produced a verdict → resolve.
                # Step 2's bucket determines the resolution: promote/hold/kill.
                comp_verdict = comp_info["verdict"]
                comp_bucket = comp_info.get("bucket", "info")
                if comp_bucket == "promote":
                    tag = "RESOLVED SHIP"
                elif comp_bucket == "kill":
                    tag = "RESOLVED KILL"
                elif comp_bucket == "hold":
                    tag = "RESOLVED HOLD"
                else:
                    tag = "RESOLVED (see companion)"
                out.append(f"  • {n} — {tag} per {companion}")
                out.append(f"      step 1 said: {v}")
                out.append(f"      step 2 says: {comp_verdict}")
            else:
                out.append(f"  • {n} — {v}")
    else:
        out.append("  • none")
    out.append("")

    # STABLE re-check relabels — transparency for what KNOWN_LIVE_PIPELINES
    # auto-suppressed this run. Prevents silent suppression from hiding a
    # verdict that should be re-checked (e.g., if the target got unwired
    # without updating the registry).
    if stable_recheck_relabels:
        out.append("Auto-relabeled STABLE (KNOWN_LIVE_PIPELINES — target already live):")
        for n, v in stable_recheck_relabels:
            entry = KNOWN_LIVE_PIPELINES.get(n, {})
            out.append(f"  • {n} — {entry.get('target', '?')} "
                       f"(since {entry.get('since', '?')})")
        out.append("  → Verify these targets are actually still live if any "
                   "look stale. Registry lives in build_executive_summary.py.")
        out.append("")

    # Cross-script contradictions — same target, disagreeing verdicts. The
    # class case (2026-07-23) is chp: h_ch_persistence_blend SHIP vs
    # h_persistence_skill BEHIND. Both real, measuring different windows.
    # A morning read of only one produces a wrong action.
    contradictions = cross_script_contradictions(current)
    if contradictions:
        out.append("⚠ CROSS-SCRIPT CONTRADICTIONS (same target, disagreeing verdicts):")
        for c in contradictions:
            out.append(f"  • {c['target']} — {c['target_desc']}")
            for script, bucket_name, verdict in c["rows"]:
                short_v = verdict if len(verdict) <= 90 else verdict[:87] + "..."
                out.append(f"      {script} [{bucket_name}] → {short_v}")
            out.append(f"      Resolution: {c['resolution_note']}")
        out.append("  → Do NOT act on one script's verdict alone. Read the "
                   "resolution note before proposing action.")
        out.append("")

    # Post-ship 14-day watch: scan shipped_ledger for any active-watch ships,
    # flag any whose responsible script has flipped verdict since ship.
    post_ship_alerts = []
    suppressed_alerts = []
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
            # Suppression: ledger entry can carry `suppress_until` (YYYY-MM-DD)
            # and `suppress_reason`. Used when a verdict is known-contaminated
            # (e.g., a bug was fixed and the rolling window needs N days of
            # clean rows before the verdict is trustworthy again). Alerts in
            # this state route to a separate suppressed-alerts list instead
            # of the noisy top-of-digest slot.
            suppress_until_str = entry.get("suppress_until")
            if suppress_until_str:
                try:
                    suppress_until_date = _dt_date.fromisoformat(suppress_until_str)
                except ValueError:
                    suppress_until_date = None
                if suppress_until_date and today_date <= suppress_until_date:
                    suppressed_alerts.append({
                        "script": script,
                        "change": entry.get("change") or "(no change description)",
                        "suppress_until": suppress_until_str,
                        "suppress_reason": entry.get("suppress_reason") or "(no reason given)",
                    })
                    continue
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
    if suppressed_alerts:
        out.append("Suppressed (known contamination — do not act):")
        for a in suppressed_alerts:
            out.append(f"  · {a['script']} — {a['change']}")
            out.append(f"    suppress until {a['suppress_until']}: {a['suppress_reason']}")
        out.append("")

    # Persistence-skill watch: field-level regressions and at-risk fields.
    ps_regressions, ps_at_risk, ps_prod_delta = persistence_skill_watch()
    out.append("Persistence-skill watch (per-field verdict flips vs prior run):")
    if ps_regressions is None:
        out.append("  • no snapshot yet (h_persistence_skill.json missing or unparseable)")
    elif ps_regressions:
        for line in ps_regressions:
            out.append(line)
    else:
        out.append("  • no regressions")
    if ps_at_risk:
        out.append("  At-risk (currently ADDS VALUE, thin margin):")
        for line in ps_at_risk:
            out.append(line)
    if ps_prod_delta:
        out.append("  Production vs L4 delta (L3 + specialists visibly moving persistence skill):")
        for line in ps_prod_delta:
            out.append(line)
    out.append("")

    # Pair-log distribution-shift alerts.
    anomaly_lines = anomaly_detector_summary()
    out.append("Pair-log anomaly alerts (distribution shift vs baseline):")
    if anomaly_lines is None:
        out.append("  • detector not run yet (anomaly_detector.json missing)")
    elif anomaly_lines:
        for line in anomaly_lines:
            out.append(line)
    else:
        out.append("  • all fields CLEAN")
    ml_line, ml_suppression = marine_layer_anomaly_summary()
    ml_suppressed_line = None
    if ml_line:
        if ml_suppression:
            ml_suppressed_line = (ml_line, ml_suppression)
        else:
            out.append(ml_line)
    out.append("")

    # Suppressed alerts (settled-known signals per digest_suppress.json). Kept
    # visible but out of the top-of-digest slot so they don't retrigger triage.
    suppressed_signals = []
    if ml_suppressed_line:
        line, sup = ml_suppressed_line
        suppressed_signals.append({
            "line": line,
            "reason": sup.get("reason") or "(no reason)",
            "until": sup.get("suppress_until") or "(no date)",
            "memory": sup.get("memory_ref") or "",
        })
    if suppressed_signals:
        out.append("Suppressed (known — see memory; do not re-triage):")
        for s in suppressed_signals:
            out.append(s["line"] + f"    [suppressed → {s['until']}]")
            memref = f"  [[{s['memory']}]]" if s["memory"] else ""
            out.append(f"    reason: {s['reason']}{memref}")
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

    # Narrow-promote gates for the C1 marginal-axis Stage 3 tables. The gate
    # is "7 consecutive daily digest reads agreeing on the SHIP scope of the
    # curated table." Wired 2026-07-10 — same session that caught the L3/L4
    # streak-infra wedge; C1h/C1d gates had been aspirational text with no
    # counter behind them for weeks. today_claims is computed inline here
    # (the history-append block below also uses it — that block runs after
    # print so we compute claims eagerly to feed both consumers).
    from datetime import datetime as _dt_datetime, timezone as _dt_timezone
    sys.path.insert(0, str(HERE))
    from claims import compute_claims as _compute_claims
    _early_run_at = _dt_datetime.now(_dt_timezone.utc).strftime("%Y-%m-%dT%H:%M")
    _early_today_claims = _compute_claims(current)
    _NARROW_PROMOTE_GATES = {
        "C1H_SHIP_CELLS": ("C1h", 7),
        "C1D_SHIP_CELLS": ("C1d", 7),
        "PRE_FRONTAL_SHIP_CELLS": ("pre-frontal", 7),
        "H_L4_ADD_CANDIDATES": ("h/l4 narrow-add", 7),
    }
    # Jaccard threshold for cell-set match across consecutive daily reads.
    # v0.6.362: relaxed from exact-identity (== comparison) to Jaccard ≥ 0.8
    # to tolerate single-cell borderline drift. Three failures on 2026-07-19
    # traced to exact-match brittleness: h/l4 fossil catch (Jaccard = 0 →
    # correctly resets), pre-frontal same-day 5-cell shuffle with 2 cells
    # different (Jaccard = 0.43 → still resets with 0.8 gate — appropriate
    # because 40% turnover is real churn), hsf verdict flips (bucket-level,
    # different walker). Threshold picked at 0.8 so single-cell drift in a
    # 5-cell set (Jaccard = 4/6 ≈ 0.67) doesn't clear — one-cell tolerance is
    # 6/7 ≈ 0.86 in a 6-cell set, 5/6 ≈ 0.83 in a 5-cell set. Deliberately
    # tight; the goal is to catch fossils and true instability, not to paper
    # over half-cell churn.
    _JACCARD_MATCH_THRESHOLD = 0.8

    def _claim_match(prior_claim, today_claim, threshold=_JACCARD_MATCH_THRESHOLD):
        """Return True if prior_claim's SHIP-cell set matches today's under
        Jaccard similarity >= threshold. Cells are [field, band] pairs; we
        normalize to a set of tuples so order/serialization variance doesn't
        break the compare. Empty-vs-empty is a perfect match (1.0)."""
        sa = {tuple(x) for x in (prior_claim or [])}
        sb = {tuple(x) for x in (today_claim or [])}
        if not sa and not sb:
            return True
        union = sa | sb
        if not union:
            return False
        return (len(sa & sb) / len(union)) >= threshold
    _narrow_lines = []
    for key, (label, gate_n) in _NARROW_PROMOTE_GATES.items():
        today_claim = _early_today_claims.get(key)
        if today_claim is None:
            _narrow_lines.append(f"  • {label}: no claim today (curated table missing or empty)")
            continue
        streak = 0
        oldest = None
        if HISTORY_PATH.exists():
            needle = f'"_claim:{key}"'
            rows = []
            for line in HISTORY_PATH.read_text().splitlines():
                if needle not in line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            rows.sort(key=lambda r: r["run_at"])
            per_day = {}
            for r in rows:
                per_day[r["run_at"][:10]] = r
            rows = sorted(per_day.values(), key=lambda r: r["run_at"])
            today_str = _early_run_at[:10]
            for r in reversed([x for x in rows if x["run_at"][:10] != today_str]):
                c = r.get("claim")
                if _claim_match(c, today_claim):
                    streak += 1
                    oldest = r["run_at"]
                else:
                    break
        count = streak + 1
        if count >= gate_n:
            marker = f"✓ GATE CLEARED ({count}/{gate_n} days, oldest match {oldest})"
        else:
            marker = f"⏳ {count}/{gate_n} ({gate_n - count} to go)"
        _narrow_lines.append(f"  • {label}: {marker}  · {len(today_claim)} SHIP cells today")
    out.append("Narrow-promote gates (C1 marginal-axis Stage 3):")
    out.extend(_narrow_lines)
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
        #
        # Dormancy guard (2026-07-10): the L3/L4 streak sat wedged at 0 for a
        # week because compute_claims() returned {L3_FIELDS: None, L4_FIELDS:
        # None} on every digest run while the source script's verdict was
        # populated. Writing that null row RESETS the streak on the next
        # divergence read. So: if the source script's verdict is present but
        # the derived claim is None, skip the row and warn — the streak
        # walker will then find yesterday's row and hold, not reset.
        _claim_source = {
            "L3_FIELDS": "walkforward_l3l4_validator",
            "L4_FIELDS": "walkforward_l3l4_validator",
            # LSR_ENABLED comes from the live Fitter gate history cache
            # (.cache_l5_gate_history.json), not a script's verdict — no
            # source-script null-protect applies. Fixed 2026-07-20.
            "LSR_ENABLED": None,
            "LT_ENABLED": "r5_cove_analysis",
            "LC_ENABLED": "lc_fit",
            "C1H_SHIP_CELLS": "c1h_curate",
            "C1D_SHIP_CELLS": "c1d_curate",
            "PRE_FRONTAL_SHIP_CELLS": "h_pre_front_orthogonality",
            "H_L4_ADD_CANDIDATES": "h_full_regime_sweep",
        }
        for key, val in today_claims.items():
            if val is None:
                src = _claim_source.get(key)
                if src and current.get(src, {}).get("verdict"):
                    print(f"WARN: _claim:{key} came back None but {src} verdict "
                          f"is populated — skipping row to protect streak. "
                          f"Likely walkforward summary parse failure.",
                          file=sys.stderr)
                    continue
                # LSR_ENABLED-specific: null claim can also mean the gate
                # history cache is transiently missing (network failure on
                # yesterday's divergence_report fetch). Preserve streak by
                # skipping the row in that case; only write None when the
                # cache is present but yields a mixed / non-decisive history.
                if key == "LSR_ENABLED":
                    from claims import L5_GATE_HISTORY_CACHE
                    if not L5_GATE_HISTORY_CACHE.exists():
                        print("WARN: _claim:LSR_ENABLED came back None and "
                              "L5 gate history cache is missing — skipping "
                              "row to protect streak.", file=sys.stderr)
                        continue
            f.write(json.dumps({
                "run_at": run_at,
                "script": f"_claim:{key}",
                "claim": list(val) if isinstance(val, (set, frozenset)) else val,
            }) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
