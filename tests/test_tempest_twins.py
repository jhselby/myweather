"""WU stations that are the same device as a live Tempest station must never be
scored as independent validation stations (11-25: ColleeninMHD = KMAMARBL90,
Manton Rd = KMASWAMP37, readings match to 0.01 F)."""
import json
import os

os.environ.setdefault("GEMINI_API_KEY", "test")

from analysis import mesonet_vs_urma as mv  # noqa: E402
from weather_collector.processors.wu_archive import LIVE_STATIONS, TEMPEST_TWINS  # noqa: E402


def test_twins_are_declared():
    assert set(TEMPEST_TWINS) == {"KMAMARBL90", "KMASWAMP37"}


def test_twins_are_not_in_the_live_wu_set():
    assert not set(TEMPEST_TWINS) & set(LIVE_STATIONS)


def test_wu_series_drops_twins(monkeypatch):
    rows = [{"ep": 1795500000, "t": 40.0}]
    obs = {"KMAMARBL90": rows, "KMAMARBL63": rows}
    monkeypatch.setattr(mv, "_cat", lambda p: {"obs": obs})
    monkeypatch.setattr(mv, "snap", lambda ep: ep)
    ser = mv.wu_series(["2026-11-25"])
    assert "KMAMARBL63" in ser and "KMAMARBL90" not in ser


def test_page_count_excludes_twins():
    d = json.load(open(os.path.join(os.path.dirname(__file__), "..", "mesonet.json")))
    assert d["counts"]["wu_ok"] == sum(1 for s in d["stations"] if s["k"] in ("wu", "wu_live"))
