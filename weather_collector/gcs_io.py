"""
Google Cloud Storage I/O primitives for the collector.

Loading is graceful — returns the `default` on a missing blob or any error,
logging the error at warning level. Uploading raises on failure so callers
can decide whether to abort.
"""
import gzip
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
        # Compact JSON + gzip — saves ~85% on the wire vs the old indented +
        # uncompressed format (weather_data.json: ~420KB → ~50KB). GCS serves
        # the bytes with Content-Encoding: gzip, browsers + iOS Safari + the
        # google-cloud-storage Python client all transparently decompress.
        payload_json = json.dumps(data, separators=(",", ":"))
        payload_gz = gzip.compress(payload_json.encode("utf-8"))
        blob.content_encoding = "gzip"
        blob.cache_control = "no-cache, max-age=0"
        blob.upload_from_string(payload_gz, content_type="application/json")
        logging.info(f"  ✓ Uploaded {label} to GCS ({len(payload_json):,}B → {len(payload_gz):,}B gzip)")
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
