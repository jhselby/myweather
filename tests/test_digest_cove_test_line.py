"""The digest's one-line status for the pre-registered Cove-side test (plan 1.8)."""
import json
import os

os.environ.setdefault("GEMINI_API_KEY", "test")

from analysis.runlog.build_executive_summary import mesonet_cove_test_status  # noqa: E402


def write(tmp_path, refs, verdict=None):
    p = tmp_path / "q.json"
    p.write_text(json.dumps({"min_nights": 10, "references": refs, "verdict": verdict or {}}))
    return p


def ref(n):
    return {"nights": n, "eligible": n >= 10}


def test_waiting_shows_counts_and_no_verdict(tmp_path):
    (line,) = mesonet_cove_test_status(write(tmp_path, {"yard": ref(3), "driftwood": ref(3), "neptune": ref(17)}))
    assert "waiting" in line and "yard 3/10" in line and "driftwood 3/10" in line and "neptune 17/10" in line
    assert "qualifies" not in line


def test_ready_reports_the_verdict(tmp_path):
    v = {"t": {"qualifies": False}, "dp": {"qualifies": True}}
    (line,) = mesonet_cove_test_status(write(tmp_path, {"yard": ref(11), "driftwood": ref(12), "neptune": ref(20)}, v))
    assert "READY" in line and "t qualifies: False" in line and "dp qualifies: True" in line


def test_missing_file_is_called_out(tmp_path):
    (line,) = mesonet_cove_test_status(tmp_path / "nope.json")
    assert "no result file" in line
