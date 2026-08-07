"""Output directory helper — env-var override for cloud runs.

Local runs (env var unset) resolve to `analysis/output/`, preserving prior
behavior. Cloud runs set MYWEATHER_OUTPUT_DIR=/tmp/output so writes hit
the tmpfs (Cloud Functions Gen2 has read-only /workspace, writable /tmp only).
"""
import os

_DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
OUTPUT_DIR = os.environ.get("MYWEATHER_OUTPUT_DIR") or _DEFAULT_DIR


def out(*parts):
    """Return output path under OUTPUT_DIR. Creates parent dirs on demand."""
    path = os.path.join(OUTPUT_DIR, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path
