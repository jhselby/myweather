"""
Landing page (index.html) render tests, in WebKit (Safari's engine) at iPhone size.

Why: v0.7.155 shipped an alert banner that showed NWS `expires` (message lapse
time) as if it were the event end. A Wind Advisory starting Thursday noon read
"until Wednesday 4 PM". Only a rendered check against the source field catches
that class of error, so these tests render the real file with fixed fixtures and
assert on the displayed text.

No network and no server: every request is answered from the repo or from the
fixtures below. Skipped if Playwright/WebKit is not installed
(pip install playwright && python3 -m playwright install webkit).

Run: python3 -m pytest tests/test_landing_page_render.py -v
"""
import json
import mimetypes
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime.now(timezone.utc)


def iso(delta_hours):
    return (NOW + timedelta(hours=delta_hours)).isoformat()


def weather(alerts, station_temp=True, night=False):
    return {
        "generated_at": NOW.isoformat(),
        "current": {"temperature": 35, "weather_description": "Clear", "weather_code": 0, "weather_emoji": "\u2600\ufe0f", "wind_speed": 6,
                    "wind_direction": 0, "humidity": 63, "dew_point": 24},
        "daily": {"time": [datetime.now().strftime("%Y-%m-%d")], "temperature_max": [43],
                  "temperature_min": [28], "precipitation_probability_max": [0],
                  "precipitation_sum": [0.0], "sunrise": [iso(-15 if night else -3)], "sunset": [iso(-1 if night else 5)]},
        "briefing": {"headline": "Test headline", "subheadline": ""},
        "hyperlocal": {"station_temp": 38.7} if station_temp else {},
        "tempest": {"stations": []},
        "alerts": alerts,
    }


def alert(event="Wind Advisory", onset_h=-1, expires_h=2, ends_h=20, severity="Moderate",
          headline=None, description="", **extra):
    a = {"event": event, "severity": severity, "onset": iso(onset_h), "expires": iso(expires_h),
         "headline": headline if headline is not None else f"{event} issued by NWS",
         "description": description, "url": "https://forecast.weather.gov/x"}
    if ends_h is not None:
        a["ends"] = iso(ends_h)
    a.update(extra)
    return a


@pytest.fixture(scope="module")
def browser():
    with playwright_sync.sync_playwright() as p:
        try:
            b = p.webkit.launch()
        except Exception as e:  # browser binary missing
            pytest.skip(f"WebKit not installed: {e}")
        yield b
        b.close()


def open_page(browser, data, scheme="dark"):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme,
                              is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))

    def handler(route):
        u = route.request.url
        if u.startswith("https://data.wymancove.com/weather_data.json"):
            return route.fulfill(status=200, body=json.dumps(data), content_type="application/json")
        if u.startswith("https://data.wymancove.com/"):
            return route.fulfill(status=404, body="")
        rel = u.split("://", 1)[1].split("/", 1)[1].split("?")[0] or "index.html"
        f = ROOT / rel
        if f.is_file():
            return route.fulfill(status=200, body=f.read_bytes(),
                                 content_type=mimetypes.guess_type(str(f))[0] or "text/plain")
        return route.fulfill(status=404, body="")

    page.route("**/*", handler)
    page.goto("https://wymancove.com/?home")
    page.wait_for_selector("#now .temp", timeout=15000)
    return ctx, page


def banners(page):
    return [page.locator("#alerts a").nth(i).inner_text().replace("\n", " ")
            for i in range(page.locator("#alerts a").count())]


def test_no_alerts_hides_banner(browser):
    ctx, page = open_page(browser, weather([]))
    assert page.locator("#alerts").is_hidden()
    assert page.errors == []
    ctx.close()


def test_nws_test_message_is_filtered(browser):
    ctx, page = open_page(browser, weather([alert(description="THIS IS A TEST of the system")]))
    assert page.locator("#alerts").is_hidden()
    ctx.close()


def test_active_alert_shows_ends_not_expires(browser):
    # expires (2h) is the message lapse; ends (20h) is the event end. The banner must use ends.
    ctx, page = open_page(browser, weather([alert(onset_h=-1, expires_h=2, ends_h=20)]))
    (text,) = banners(page)
    end_expected = (NOW + timedelta(hours=20)).astimezone().strftime("%a")
    assert text.startswith("⚠️ Wind Advisory")
    assert "starts" not in text, text          # already in effect
    assert "until" in text and end_expected in text, text
    expires_clock = (NOW + timedelta(hours=2)).astimezone().strftime("%-I:%M %p")
    ends_clock = (NOW + timedelta(hours=20)).astimezone().strftime("%-I:%M %p")
    assert ends_clock in text and (expires_clock == ends_clock or expires_clock not in text), text
    ctx.close()


def test_future_alert_shows_start_and_end(browser):
    ctx, page = open_page(browser, weather([alert(onset_h=26, expires_h=3, ends_h=40)]))
    (text,) = banners(page)
    assert "starts" in text and "until" in text, text
    ctx.close()


def test_missing_ends_falls_back_to_headline_until(browser):
    h = "Wind Advisory issued November 25 at 1:22AM EST until November 27 at 7:00AM EST by NWS Boston/Norton MA"
    ctx, page = open_page(browser, weather([alert(ends_h=None, headline=h)]))
    (text,) = banners(page)
    assert "until November 27 at 7:00AM EST" in text, text
    ctx.close()


def test_never_shows_expires_when_no_end_is_known(browser):
    ctx, page = open_page(browser, weather([alert(ends_h=None, headline="No end phrase here")]))
    (text,) = banners(page)
    assert "until" not in text, text
    ctx.close()


def test_severe_alert_is_red_class(browser):
    ctx, page = open_page(browser, weather([alert(event="Tornado Warning", severity="Extreme")]))
    assert "severe" in page.locator("#alerts a").first.get_attribute("class")
    ctx.close()


def test_alert_text_is_not_interpreted_as_html(browser):
    ctx, page = open_page(browser, weather([alert(event="<img src=x onerror=window.__pwn=1>")]))
    assert page.evaluate("window.__pwn") is None
    assert page.locator("#alerts img").count() == 0
    ctx.close()


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_theme_is_behind_the_gear(browser, scheme):
    ctx, page = open_page(browser, weather([]), scheme)
    assert page.locator(".theme").is_hidden() and page.locator("#drawer").is_hidden()
    page.click("#settingsBtn")
    assert page.locator("#drawer").is_visible() and page.locator(".theme").is_visible()
    assert page.evaluate("document.activeElement.id") == "drawerClose"
    target = "light" if scheme == "dark" else "dark"
    page.click(f'.theme button[data-mode="{target}"]')
    assert page.evaluate("document.documentElement.dataset.theme") == target
    assert page.evaluate("localStorage.theme") == target
    page.keyboard.press("Escape")
    assert page.locator("#drawer").is_hidden()
    assert page.evaluate("document.activeElement.id") == "settingsBtn"
    assert page.errors == []
    ctx.close()


def test_headline_temperature_is_the_mesonet_value(browser):
    # current.temperature is 35 (served, model-blended); the Mesonet says 38.7 -> one number, 39.
    ctx, page = open_page(browser, weather([]))
    assert page.locator("#now .temp").inner_text() == "39\u00b0F"
    assert "Mesonet stations" in page.locator("#now .cond").inner_text()
    ctx.close()


def test_headline_falls_back_to_served_temperature_without_stations(browser):
    ctx, page = open_page(browser, weather([], station_temp=False))
    assert page.locator("#now .temp").inner_text() == "35\u00b0F"
    assert "Mesonet" not in page.locator("#now .cond").inner_text()
    ctx.close()


def test_clear_night_shows_a_moon_not_a_sun(browser):
    # 11-25: 5:47 PM, after sunset, the landing page showed a sun on a clear night.
    ctx, page = open_page(browser, weather([], night=True))
    assert page.locator("#now .emoji").inner_text() == "\U0001F319"
    ctx.close()


def test_clear_day_keeps_the_sun(browser):
    ctx, page = open_page(browser, weather([], night=False))
    assert page.locator("#now .emoji").inner_text() == "\u2600\ufe0f"
    ctx.close()
