from __future__ import annotations

import json

from app.services.events import _sse, publish_event


def test_sse_frame_format() -> None:
    payload = {"type": "snapshot", "batch": {"batch_id": "batch-1"}}

    assert _sse(payload) == f"data: {json.dumps(payload)}\n\n"


def test_publish_event_calls_redis(monkeypatch) -> None:
    published: list[tuple[str, str]] = []

    class FakeRedis:
        def publish(self, channel: str, data: str) -> int:
            published.append((channel, data))
            return 1

    monkeypatch.setattr("app.services.events.redis_conn", FakeRedis())

    publish_event("batch-1", {"type": "progress"})

    assert published == [("batch:batch-1:events", json.dumps({"type": "progress"}))]
