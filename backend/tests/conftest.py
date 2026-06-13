from __future__ import annotations

from typing import Any

import pytest


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self.redis = redis

    def hset(self, key: str, *args: Any, mapping: dict[str, Any] | None = None, **kwargs: Any) -> None:
        return self.redis.hset(key, *args, mapping=mapping, **kwargs)

    def set(self, key: str, value: Any) -> None:
        return self.redis.set(key, value)

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        return self.redis.zadd(key, mapping)

    def expire(self, key: str, ttl: int) -> None:
        return self.redis.expire(key, ttl)

    def execute(self) -> list[Any]:
        return []


class FakeRedis:
    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._strings: dict[str, Any] = {}
        self._sorted_sets: dict[str, dict[str, float]] = {}

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)

    def hset(
        self,
        key: str,
        *args: Any,
        mapping: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if mapping is None:
            if args:
                field, value = args[:2]
                mapping = {str(field): value}
            elif "mapping" in kwargs:
                mapping = kwargs["mapping"]
            else:
                raise TypeError("Invalid arguments for hset")

        self._hashes.setdefault(key, {})
        for field, value in mapping.items():
            self._hashes[key][str(field)] = "" if value is None else str(value)

    def set(self, key: str, value: Any) -> None:
        self._strings[key] = value

    def get(self, key: str) -> Any:
        return self._strings.get(key)

    def exists(self, key: str) -> int:
        return int(
            key in self._hashes or key in self._strings or key in self._sorted_sets
        )

    def hgetall(self, key: str) -> dict[str, str]:
        return self._hashes.get(key, {}).copy()

    def hget(self, key: str, field: str) -> str | None:
        return self._hashes.get(key, {}).get(str(field))

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self._sorted_sets.setdefault(key, {})
        for member, score in mapping.items():
            self._sorted_sets[key][str(member)] = float(score)

    def zrevrange(self, key: str, start: int, end: int) -> list[str]:
        items = sorted(self._sorted_sets.get(key, {}).items(), key=lambda kv: -kv[1])
        if end < 0:
            end = len(items) + end
        return [member for member, _ in items][start : end + 1]

    def expire(self, key: str, ttl: int) -> None:
        pass


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()
