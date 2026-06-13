"""Application configuration loaded from environment variables.

All settings have sensible defaults so the service can boot locally without a
fully populated ``.env`` file. See ``.env.example`` for documentation.
"""
import os

from dotenv import load_dotenv

# Load a local .env if present (no-op in containers where env is injected).
load_dotenv()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Config:
    # --- Existing (downstream) Hospital Directory API -------------------
    # Base URL of the already-deployed hospital directory API that this
    # service orchestrates calls against.
    EXTERNAL_API_BASE_URL = os.getenv(
        "EXTERNAL_API_BASE_URL", "http://localhost:8000"
    ).rstrip("/")

    # --- Redis (data + state + queue) -----------------------------------
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    RQ_QUEUE_NAME = os.getenv("RQ_QUEUE_NAME", "bulk_hospitals")

    # --- Upload / processing constraints --------------------------------
    # Hard cap on the number of hospital rows accepted in a single CSV.
    MAX_CSV_HOSPITALS = _int_env("MAX_CSV_HOSPITALS", 20)
    # Reject obviously oversized uploads early (default 5 MB).
    MAX_CONTENT_LENGTH = _int_env("MAX_CONTENT_LENGTH", 5 * 1024 * 1024)

    # --- Outbound HTTP behaviour ----------------------------------------
    HTTP_TIMEOUT = _int_env("HTTP_TIMEOUT", 30)
    HTTP_MAX_RETRIES = _int_env("HTTP_MAX_RETRIES", 3)
    HTTP_BACKOFF_FACTOR = float(os.getenv("HTTP_BACKOFF_FACTOR", "0.5"))

    # --- Bookkeeping -----------------------------------------------------
    # How long (seconds) batch state is retained in Redis. Default 7 days.
    BATCH_TTL_SECONDS = _int_env("BATCH_TTL_SECONDS", 7 * 24 * 3600)
    # Job execution timeout for the RQ worker (seconds).
    JOB_TIMEOUT = _int_env("JOB_TIMEOUT", 1800)

    # --- Logging ---------------------------------------------------------
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_DIR = os.getenv("LOG_DIR", "logs")
