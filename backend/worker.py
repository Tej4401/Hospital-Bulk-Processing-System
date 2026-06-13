"""Background worker entrypoint.

Consumes jobs from the RQ queue and runs ``process_batch`` for each batch.
Run with: ``python worker.py`` (or via the docker-compose ``worker`` service).
"""
from rq import Worker

from app.config import Config
from app.extensions import rq_redis_conn
from app.logging_config import get_logger

logger = get_logger(__name__)


def main() -> None:
    logger.info(
        "Starting RQ worker on queue '%s' (downstream API: %s)",
        Config.RQ_QUEUE_NAME,
        Config.EXTERNAL_API_BASE_URL,
    )
    worker = Worker([Config.RQ_QUEUE_NAME], connection=rq_redis_conn)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
