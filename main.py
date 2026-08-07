# Lazy imports — Cloud Functions Gen2 imports main.py at container startup.
# If we imported both eagerly, the publisher container would pull in the
# collector's Gemini/PW/WU dependencies (which read secrets at import time)
# and crash before serving any request. Each function loads only its own
# chain the first time it's invoked.

def run(request):
    from weather_collector.collector import run as _run
    return _run(request)

def publish(request):
    from publisher.main import publish as _publish
    return _publish(request)
