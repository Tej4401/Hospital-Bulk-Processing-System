"""Redis-backed persistence for batch state, rows and per-row results.

Redis layout (all keys carry a TTL of ``Config.BATCH_TTL_SECONDS``):

    batch:{id}:meta     HASH   scalar batch metadata / counters / status
    batch:{id}:rows     STRING JSON array of the parsed CSV rows (input)
    batch:{id}:results  HASH   field=row number, value=JSON per-row result
    batches             ZSET   all batch ids scored by creation time

This module is the single source of truth for batch state and is safe to
use from both the web process and the background worker.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from ..config import Config
from ..extensions import redis_conn


class BatchStatus:
    QUEUED = "queued"          # accepted, waiting for a worker
    PROCESSING = "processing"  # creating hospitals
    ACTIVATING = "activating"  # all created, calling activate
    COMPLETED = "completed"    # all created + batch activated
    PARTIALLY_FAILED = "partially_failed"  # some rows failed; not activated
    FAILED = "failed"          # nothing usable / activation failed

    TERMINAL = {COMPLETED, PARTIALLY_FAILED, FAILED}
    RESUMABLE = {PARTIALLY_FAILED, FAILED, PROCESSING, ACTIVATING, QUEUED}


class RowStatus:
    PENDING = "pending"
    CREATED = "created"
    CREATED_AND_ACTIVATED = "created_and_activated"
    FAILED = "failed"


def _meta_key(batch_id: str) -> str:
    return f"batch:{batch_id}:meta"


def _rows_key(batch_id: str) -> str:
    return f"batch:{batch_id}:rows"


def _results_key(batch_id: str) -> str:
    return f"batch:{batch_id}:results"


_INDEX_KEY = "batches"


@dataclass
class BatchView:
    """Read model assembled for status responses."""

    batch_id: str
    status: str
    total_hospitals: int
    processed_hospitals: int
    failed_hospitals: int
    batch_activated: bool
    created_at: str
    started_at: str | None
    finished_at: str | None
    processing_time_seconds: float | None
    error: str | None
    hospitals: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "status": self.status,
            "total_hospitals": self.total_hospitals,
            "processed_hospitals": self.processed_hospitals,
            "failed_hospitals": self.failed_hospitals,
            "processing_time_seconds": self.processing_time_seconds,
            "batch_activated": self.batch_activated,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "hospitals": self.hospitals,
        }


class BatchStore:
    """High-level CRUD operations over the Redis batch keys."""

    def __init__(self, conn=redis_conn):
        self.conn = conn
        self.ttl = Config.BATCH_TTL_SECONDS

    # -- Creation --------------------------------------------------------
    def create_batch(self, batch_id: str, rows: list[dict[str, Any]]) -> None:
        """Persist a freshly accepted batch and seed per-row results."""
        now = _utcnow()
        meta = {
            "batch_id": batch_id,
            "status": BatchStatus.QUEUED,
            "total_hospitals": len(rows),
            "processed_hospitals": 0,
            "failed_hospitals": 0,
            "batch_activated": 0,
            "created_at": now,
            "started_at": "",
            "finished_at": "",
            "processing_time_seconds": "",
            "error": "",
        }
        results = {}
        for row in rows:
            results[str(row["row"])] = json.dumps(
                {
                    "row": row["row"],
                    "name": row["name"],
                    "hospital_id": None,
                    "status": RowStatus.PENDING,
                    "error": None,
                }
            )

        pipe = self.conn.pipeline()
        pipe.hset(_meta_key(batch_id), mapping=meta)
        pipe.set(_rows_key(batch_id), json.dumps(rows))
        pipe.hset(_results_key(batch_id), mapping=results)
        pipe.zadd(_INDEX_KEY, {batch_id: time.time()})
        for key in (_meta_key(batch_id), _rows_key(batch_id), _results_key(batch_id)):
            pipe.expire(key, self.ttl)
        pipe.execute()

    # -- Existence / fetch ----------------------------------------------
    def exists(self, batch_id: str) -> bool:
        return bool(self.conn.exists(_meta_key(batch_id)))

    def get_rows(self, batch_id: str) -> list[dict[str, Any]]:
        raw = self.conn.get(_rows_key(batch_id))
        return json.loads(raw) if raw else []

    def get_meta(self, batch_id: str) -> dict[str, Any]:
        return self.conn.hgetall(_meta_key(batch_id))

    def get_results(self, batch_id: str) -> list[dict[str, Any]]:
        raw = self.conn.hgetall(_results_key(batch_id))
        results = [json.loads(v) for v in raw.values()]
        results.sort(key=lambda r: r["row"])
        return results

    def get_result(self, batch_id: str, row: int) -> dict[str, Any] | None:
        raw = self.conn.hget(_results_key(batch_id), str(row))
        return json.loads(raw) if raw else None

    # -- Mutations -------------------------------------------------------
    def set_status(self, batch_id: str, status: str, error: str | None = None) -> None:
        mapping: dict[str, Any] = {"status": status}
        if error is not None:
            mapping["error"] = error
        self.conn.hset(_meta_key(batch_id), mapping=mapping)

    def mark_started(self, batch_id: str) -> None:
        meta = self.get_meta(batch_id)
        mapping = {"status": BatchStatus.PROCESSING}
        # Only stamp started_at the first time processing begins.
        if not meta.get("started_at"):
            mapping["started_at"] = _utcnow()
        self.conn.hset(_meta_key(batch_id), mapping=mapping)

    def update_row_result(self, batch_id: str, row: int, **fields) -> None:
        current = self.get_result(batch_id, row) or {"row": row}
        current.update(fields)
        self.conn.hset(_results_key(batch_id), str(row), json.dumps(current))

    def recount(self, batch_id: str) -> tuple[int, int]:
        """Recompute processed/failed counters from per-row results."""
        results = self.get_results(batch_id)
        processed = sum(
            1
            for r in results
            if r["status"] in (RowStatus.CREATED, RowStatus.CREATED_AND_ACTIVATED)
        )
        failed = sum(1 for r in results if r["status"] == RowStatus.FAILED)
        self.conn.hset(
            _meta_key(batch_id),
            mapping={"processed_hospitals": processed, "failed_hospitals": failed},
        )
        return processed, failed

    def mark_activated(self, batch_id: str) -> None:
        self.conn.hset(_meta_key(batch_id), "batch_activated", 1)
        # Promote every successfully created row to activated.
        for r in self.get_results(batch_id):
            if r["status"] == RowStatus.CREATED:
                self.update_row_result(
                    batch_id, r["row"], status=RowStatus.CREATED_AND_ACTIVATED
                )

    def mark_finished(self, batch_id: str, status: str) -> None:
        meta = self.get_meta(batch_id)
        now = _utcnow()
        started = meta.get("started_at") or meta.get("created_at")
        elapsed = _elapsed_seconds(started, now)
        self.conn.hset(
            _meta_key(batch_id),
            mapping={
                "status": status,
                "finished_at": now,
                "processing_time_seconds": round(elapsed, 3),
            },
        )

    # -- Read model ------------------------------------------------------
    def view(self, batch_id: str) -> BatchView | None:
        meta = self.get_meta(batch_id)
        if not meta:
            return None
        results = self.get_results(batch_id)
        return BatchView(
            batch_id=meta["batch_id"],
            status=meta["status"],
            total_hospitals=int(meta.get("total_hospitals", 0)),
            processed_hospitals=int(meta.get("processed_hospitals", 0)),
            failed_hospitals=int(meta.get("failed_hospitals", 0)),
            batch_activated=meta.get("batch_activated") in ("1", 1, True),
            created_at=meta.get("created_at", ""),
            started_at=meta.get("started_at") or None,
            finished_at=meta.get("finished_at") or None,
            processing_time_seconds=(
                float(meta["processing_time_seconds"])
                if meta.get("processing_time_seconds")
                else None
            ),
            error=meta.get("error") or None,
            hospitals=[
                {
                    "row": r["row"],
                    "hospital_id": r.get("hospital_id"),
                    "name": r.get("name"),
                    "status": r["status"],
                    "error": r.get("error"),
                }
                for r in results
            ],
        )

    def list_batches(self, limit: int = 50) -> list[dict[str, Any]]:
        ids = self.conn.zrevrange(_INDEX_KEY, 0, max(0, limit - 1))
        out = []
        for bid in ids:
            meta = self.get_meta(bid)
            if not meta:
                continue
            out.append(
                {
                    "batch_id": meta["batch_id"],
                    "status": meta["status"],
                    "total_hospitals": int(meta.get("total_hospitals", 0)),
                    "processed_hospitals": int(meta.get("processed_hospitals", 0)),
                    "failed_hospitals": int(meta.get("failed_hospitals", 0)),
                    "created_at": meta.get("created_at", ""),
                }
            )
        return out


def _utcnow() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _elapsed_seconds(start_iso: str, end_iso: str) -> float:
    from datetime import datetime

    fmt = "%Y-%m-%dT%H:%M:%SZ"
    try:
        start = datetime.strptime(start_iso, fmt)
        end = datetime.strptime(end_iso, fmt)
        return (end - start).total_seconds()
    except (ValueError, TypeError):
        return 0.0
