"""Centralised logging configuration.

Provides a consistent, structured-ish log format used by both the web
process and the background worker. A ``batch_id`` field is injected via a
``logging.Filter`` so log lines can always be correlated to a batch even
when the caller does not pass one.
"""
import logging
import logging.handlers
import os
import sys

from .config import Config

_CONFIGURED = False

LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | "
    "batch=%(batch_id)s | %(message)s"
)


class _BatchIdFilter(logging.Filter):
    """Ensure every record has a ``batch_id`` attribute for the formatter."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if not hasattr(record, "batch_id"):
            record.batch_id = "-"
        return True


def setup_logging() -> None:
    """Configure root logging once for the current process."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, Config.LOG_LEVEL, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT)
    batch_filter = _BatchIdFilter()

    # Console handler (captured by Docker / journald).
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(batch_filter)
    root.addHandler(console)

    # Rotating file handler for persistent local logs.
    try:
        os.makedirs(Config.LOG_DIR, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(Config.LOG_DIR, "bulk_processor.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(batch_filter)
        root.addHandler(file_handler)
    except OSError:
        # If the log directory is not writable, carry on with console only.
        root.warning("Could not create file log handler; using console only")

    # Tame noisy third-party loggers.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str, batch_id: str | None = None) -> logging.LoggerAdapter:
    """Return a logger adapter that stamps ``batch_id`` onto every record."""
    setup_logging()
    return logging.LoggerAdapter(
        logging.getLogger(name), {"batch_id": batch_id or "-"}
    )
