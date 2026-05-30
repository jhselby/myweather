"""
Google Cloud Storage I/O primitives for the collector.

Loading is graceful — returns the `default` on a missing blob or any error,
logging the error at warning level. Uploading raises on failure so callers
can decide whether to abort.
"""
import json
import logging

from .utils import redact_secrets


BUCKET = "myweather-data"


def get_client():
    """Lazy-init GCS client. The google.cloud import is deferred because
    it's a heavy dependency not needed at module load time."""
    from google.cloud import storage
    return storage.Client()


def upload_json(data, gcs_path, label):
    """Upload `data` as indented JSON to `gcs_path` with no-cache headers.

    Logs a sized success message at info level. Re-raises on failure so
    callers (e.g., the weather_data.json write) can fail the run.
    """
    try:
        client = get_client()
        blob = client.bucket(BUCKET).blob(gcs_path)
        payload = json.dumps(data, indent=2)
        blob.upload_from_string(payload, content_type="application/json")
        blob.cache_control = "no-cache, max-age=0"
        blob.patch()
        logging.info(f"  ✓ Uploaded {label} to GCS ({len(payload):,} bytes)")
    except Exception as e:
        logging.error(f"  ✗ Failed to upload {label} to GCS: {redact_secrets(e)}")
        raise


def load_json(gcs_path, default=None):
    """Load JSON from `gcs_path`. Returns `default` on missing blob or any error."""
    try:
        client = get_client()
        blob = client.bucket(BUCKET).blob(gcs_path)
        if blob.exists():
            return json.loads(blob.download_as_text())
    except Exception as e:
        logging.warning(f"  ⚠  Could not load {gcs_path} from GCS: {redact_secrets(e)}")
    return default
