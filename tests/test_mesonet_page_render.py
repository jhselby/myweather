"""mesonet.html renders the numbers in mesonet.json, and its station counts add up.
Fixture-driven (no network); WebKit. Skipped if Playwright/WebKit is not installed."""
import json
import mimetypes
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parent.parent

MES = {
    "generated_at": "2026-11-25T22:00Z", "stations": [], "live": [], "own": None,
    "counts": {"tempest_ok": 18, "tempest_total": 18, "wu_ok": 34, "wu_live": 7, "wu_configured": 41,
               "wu_silent": 5, "wu_retired": 19, "homebuilt": 1, "wu_twins": 2},
    "water": {"rows": 343, "first": "2026-11-11T11:00",
              "last": {"ts": "2026-11-25T17:00", "gomofs_f": 51.6, "b44013_f": 52.2, "b44029_f": 51.4},
              "vs_44013": {"n": 342, "bias": 0.45, "mae": 0.62, "recent_bias": 0.26, "recent_n": 72, "first": "2026-11-11T11:00"},
              "vs_44029": {"n": 7, "bias": 0.2, "mae": 0.2, "recent_bias": 0.2, "recent_n": 7, "first": "2026-11-25T11:00"}},
}


@pytest.fixture(scope="module")
def page():
    with sync_api.sync_playwright() as p:
        try:
            b = p.webkit.launch()
        except Exception as e:
            pytest.skip(f"WebKit not installed: {e}")
        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        pg = ctx.new_page()

        def handler(route):
            u = route.request.url
            if "mesonet.json" in u:
                return route.fulfill(status=200, body=json.dumps(MES), content_type="application/json")
            if u.startswith("https://wymancove.com/"):
                f = ROOT / (u.split("://", 1)[1].split("/", 1)[1].split("?")[0] or "mesonet.html")
                if f.is_file():
                    return route.fulfill(status=200, body=f.read_bytes(),
                                         content_type=mimetypes.guess_type(str(f))[0] or "text/plain")
            return route.fulfill(status=404, body="")

        pg.route("**/*", handler)
        pg.goto("https://wymancove.com/mesonet.html")
        pg.wait_for_function("document.getElementById('water').innerText.includes('GoMOFS minus')", timeout=15000)
        yield pg
        b.close()


def test_water_numbers_match_the_data(page):
    t = page.locator("#water").inner_text()
    for needle in ("51.6°F", "52.2°F", "51.4°F", "342", "+0.45°F", "0.62°F", "+0.26°F", "+0.20°F"):
        assert needle in t, (needle, t)


def test_water_table_not_clipped_on_phone(page):
    # the panel must be able to scroll horizontally (class "scroll") rather than clip the last column
    assert "scroll" in page.locator("#water").locator("xpath=..").get_attribute("class")


def test_wu_counts_add_up_and_twins_are_explained(page):
    t = page.locator("#wu").inner_text()
    c = MES["counts"]
    assert c["wu_configured"] == c["wu_ok"] + c["wu_silent"] + c["wu_twins"]
    assert "34 working and counted" in t and "5 silent" in t and "2 not counted" in t, t


def test_snapshot_panels_say_how_old_they_are(page):
    # the WU and water panels are fed by mesonet.json (rebuilt at each build/digest, not live)
    assert "snapshot of 2026-11-25 22:00 UTC" in page.locator("#water").inner_text()
    assert "snapshot of 2026-11-25 22:00 UTC" in page.locator("#wu").inner_text()
