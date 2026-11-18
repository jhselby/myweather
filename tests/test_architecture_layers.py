"""
architecture.json "layers" must equal the code constants the debug page's layer sections render.
The sections read layers.* instead of hand-written prose, so this is what keeps them from drifting.

Run: python3 tests/test_architecture_layers.py   (or pytest)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
os.environ.setdefault("WU_API_KEY", "unset")

import architecture_state as A  # noqa: E402


def test_decay_fields_match_code():
    from weather_collector.processors import decay_apply as d
    L = A.layers()
    assert L["l3_fields"] == sorted(d.L3_FIELDS)
    assert L["l4_fields"] == sorted(d.L4_FIELDS)


def test_blend_fields_match_code():
    from weather_collector.processors import terminal_static_blend as b
    assert A.layers()["blend_fields"] == sorted(b.FIELD_APPLIED)


def test_lsr_matches_code():
    from weather_collector.processors import solar_correction as s
    L = A.layers()["lsr"]
    assert L["enabled"] == s.ENABLED
    assert L["skip_regimes"] == sorted(s.L5_SKIP_REGIMES)
    assert L["sun_up_wm2"] == s.SUN_UP_THRESHOLD


def test_lc_matches_code():
    from weather_collector.processors import cloud_saturation_correction as c
    L = A.layers()["lc"]
    assert L["enabled"] == c.ENABLED
    assert L["field_skip"] == sorted(c._FIELD_SKIP)
    assert set(L["cells"]) >= {"cm", "ch"}


if __name__ == "__main__":
    for n in sorted(dir()):
        if n.startswith("test_"):
            globals()[n]()
            print("PASS", n)
