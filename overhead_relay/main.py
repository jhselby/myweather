"""Overhead aircraft relay for the app's Airplanes card.

api.airplanes.live began refusing every client (403, "contact us") in Nov 2026, and the free
alternatives (adsb.lol, adsb.fi) send no CORS headers, so a browser cannot call them directly.
This function fetches adsb.lol server-side and returns the same JSON ({"ac": [...]}) with CORS on.

Fixed point and radius (no query parameters), so it cannot be used as an open proxy.
15 s in-memory cache plus Cache-Control, so a burst of viewers makes one upstream call.
"""
import json
import time
import urllib.request

import functions_framework

LAT, LON, RADIUS_NM = 42.4973, -70.8661, 200
UPSTREAM = f"https://api.adsb.lol/v2/point/{LAT}/{LON}/{RADIUS_NM}"
TTL_S = 15
_cache = {"t": 0.0, "body": None}
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET", "Cache-Control": f"public, max-age={TTL_S}"}


@functions_framework.http
def overhead(request):
    if request.method == "OPTIONS":
        return ("", 204, {**CORS, "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "3600"})
    now = time.time()
    if _cache["body"] is None or now - _cache["t"] > TTL_S:
        try:
            req = urllib.request.Request(UPSTREAM, headers={"User-Agent": "wymancove-weather-overhead/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read()
            json.loads(body)  # must parse before we cache it
            _cache["body"], _cache["t"] = body, now
        except Exception as e:  # serve the last good copy for up to 2 minutes, else say so
            if _cache["body"] is None or now - _cache["t"] > 120:
                return (json.dumps({"error": "upstream unavailable", "ac": []}), 502, {**CORS, "Content-Type": "application/json"})
    return (_cache["body"], 200, {**CORS, "Content-Type": "application/json"})
