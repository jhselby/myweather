"""Shared translators that turn a script's verdict into a production-claim.

A "claim" is what the script's evidence is asking production to look like —
mirrors the shape returned by divergence_report.probe_production(). Used by
both the divergence report (today's snapshot) and the history-aware streak
counter (consistency over N reads).
"""
import ast
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG_DIR = HERE.parent / "output" / "runlog"


def _claim_walkforward():
    """Extract L3/L4 sets from the most recent walkforward run's log."""
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


def _claim_bool_ship(verdict):
    if verdict is None:
        return None
    v = verdict.upper()
    if "HOLD" in v or "CLOSE" in v or "RETIRE" in v:
        return False
    if "SHIP" in v:
        return True
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
    v = state.get("l5_solar_analysis", {}).get("verdict")
    claims["LSR_ENABLED"] = _claim_bool_ship(v)
    v = state.get("r5_cove_analysis", {}).get("verdict")
    claims["LT_ENABLED"] = _claim_bool_ship(v)
    return claims


def claim_eq(a, b):
    """Equality that treats sets as unordered."""
    if isinstance(a, (set, list, tuple)) and isinstance(b, (set, list, tuple)):
        return set(a) == set(b)
    return a == b
