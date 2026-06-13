from __future__ import annotations

from app.services.batch_store import (
    BatchStatus,
    BatchStore,
    BatchView,
    RowStatus,
)


def sample_rows() -> list[dict[str, str | None]]:
    return [
        {"row": 1, "name": "Alpha Clinic", "address": "1 Main St", "phone": "111"},
        {"row": 2, "name": "Bravo Health", "address": "2 Oak St", "phone": None},
    ]


def test_batch_store_lifecycle(fake_redis) -> None:
    store = BatchStore(conn=fake_redis)
    rows = sample_rows()

    store.create_batch("batch-1", rows)

    assert store.exists("batch-1")
    assert store.get_rows("batch-1") == rows
    assert store.get_result("batch-1", 1)["status"] == RowStatus.PENDING

    view = store.view("batch-1")
    assert isinstance(view, BatchView)
    assert view.batch_id == "batch-1"
    assert view.status == BatchStatus.QUEUED
    assert view.total_hospitals == 2
    assert view.hospitals[0]["name"] == "Alpha Clinic"

    store.mark_started("batch-1")
    assert store.view("batch-1").status == BatchStatus.PROCESSING

    store.update_row_result(
        "batch-1",
        1,
        hospital_id="hospital-1",
        status=RowStatus.CREATED,
        error=None,
    )

    processed, failed = store.recount("batch-1")
    assert processed == 1
    assert failed == 0

    store.mark_activated("batch-1")
    activated_view = store.view("batch-1")
    assert activated_view.batch_activated is True
    assert activated_view.hospitals[0]["status"] == RowStatus.CREATED_AND_ACTIVATED

    store.mark_finished("batch-1", BatchStatus.COMPLETED)
    finished_view = store.view("batch-1")
    assert finished_view.status == BatchStatus.COMPLETED
    assert finished_view.processing_time_seconds is not None

    batches = store.list_batches(limit=10)
    assert batches and batches[0]["batch_id"] == "batch-1"
