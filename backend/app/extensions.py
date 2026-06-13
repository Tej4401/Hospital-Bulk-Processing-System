"""Shared infrastructure singletons: Redis connections and the RQ queue.

Two Redis clients are created intentionally:

* ``redis_conn`` decodes responses to ``str`` and is used for application
  state (batch metadata, rows, results).
* ``rq_redis_conn`` keeps raw bytes because RQ stores pickled job payloads
  and requires ``decode_responses=False``.
"""
import redis
from rq import Queue

from .config import Config

# Application data/state connection (strings in, strings out).
redis_conn = redis.Redis.from_url(Config.REDIS_URL, decode_responses=True)

# Dedicated connection for RQ (must NOT decode responses).
rq_redis_conn = redis.Redis.from_url(Config.REDIS_URL, decode_responses=False)

# The queue background jobs are pushed onto / consumed from.
task_queue = Queue(
    Config.RQ_QUEUE_NAME,
    connection=rq_redis_conn,
    default_timeout=Config.JOB_TIMEOUT,
)
