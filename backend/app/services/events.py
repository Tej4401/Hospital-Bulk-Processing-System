"""Real-time batch progress events via Redis Pub/Sub + Server-Sent Events.

The background worker (a separate process) publishes progress events to a
per-batch Redis channel. The web process subscribes to that channel and
streams the events to any connected client as SSE (``text/event-stream``).

This decouples producers from consumers: the worker doesn't know or care
whether anyone is listening, and any number of clients (the React UI, a
``curl -N`` session, another service) can subscribe independently.
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterator

from ..extensions import redis_conn
from ..logging_config import get_logger
from .batch_store import BatchStatus, BatchStore

logger = get_logger(__name__)

# Seconds between SSE keep-alive comments when no events are flowing. Keeps
# intermediaries (proxies, load balancers) from closing an idle connection.
HEARTBEAT_SECONDS = 15
# How often we wake up to check for new messages / send heartbeats.
POLL_TIMEOUT_SECONDS = 1.0


def channel(batch_id: str) -> str:
    return f"batch:{batch_id}:events"


def publish_event(batch_id: str, event: dict[str, Any]) -> None:
    """Publish a progress event for a batch (best-effort; never raises)."""
    try:
        redis_conn.publish(channel(batch_id), json.dumps(event))
    except Exception as exc:  # noqa: BLE001 - publishing must not break work
        logger.warning("Failed to publish event for %s: %s", batch_id, exc)


def _sse(payload: dict[str, Any]) -> str:
    """Format a payload as a single SSE ``data:`` frame."""
    return f"data: {json.dumps(payload)}\n\n"


def event_stream(batch_id: str) -> Iterator[str]:
    """Yield SSE frames for a batch: an initial snapshot, then live updates.

    The stream ends after a terminal (``done``) event so clients (and the
    server) can cleanly close the connection rather than reconnecting.
    """
    store = BatchStore()
    pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
    # Subscribe BEFORE reading the snapshot to avoid missing events that fire
    # in between.
    pubsub.subscribe(channel(batch_id))
    log = get_logger(__name__, batch_id)
    log.info("SSE client subscribed")

    try:
        view = store.view(batch_id)
        if view is not None:
            snapshot = view.to_dict()
            yield _sse({"type": "snapshot", "batch": snapshot})
            # If the batch is already finished, emit done and stop.
            if snapshot["status"] in BatchStatus.TERMINAL:
                yield _sse({"type": "done", "batch": snapshot})
                return

        last_heartbeat = time.monotonic()
        while True:
            message = pubsub.get_message(timeout=POLL_TIMEOUT_SECONDS)
            if message and message.get("type") == "message":
                data = message["data"]  # already a JSON str (decode_responses)
                yield f"data: {data}\n\n"
                try:
                    if json.loads(data).get("type") == "done":
                        break
                except (ValueError, TypeError):
                    pass
                last_heartbeat = time.monotonic()
            elif time.monotonic() - last_heartbeat >= HEARTBEAT_SECONDS:
                yield ": heartbeat\n\n"
                last_heartbeat = time.monotonic()
    except GeneratorExit:
        # Client disconnected; fall through to cleanup.
        log.info("SSE client disconnected")
        raise
    finally:
        try:
            pubsub.close()
        except Exception:  # noqa: BLE001
            pass
