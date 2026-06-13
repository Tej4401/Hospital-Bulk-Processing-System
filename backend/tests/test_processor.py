from __future__ import annotations

from app.services.batch_store import BatchStore, BatchStatus, RowStatus
from app.services import processor as processor_module


class FakeHospitalClient:
    def __init__(self) -> None:
        self.activated_batches: list[str] = []

    def create_hospital(
        self,
        name: str,
        address: str,
        phone: str | None,
        batch_id: str,
    ) -> dict[str, str]:
        return {"id": f"hospital-{batch_id}-{name}"}

    def activate_batch(self, batch_id: str) -> None:
        self.activated_batches.append(batch_id)

    def get_batch(self, batch_id: str) -> list[dict[str, str]]:
        return []


def test_process_batch_completes_successfully(fake_redis, monkeypatch) -> None:
    store = BatchStore(conn=fake_redis)
    store.create_batch(
        "batch-success",
        [{"row": 1, "name": "Alpha Clinic", "address": "1 Main St", "phone": "111"}],
    )

    events: list[dict[str, object]] = []
    monkeypatch.setattr(processor_module, "BatchStore", lambda *args, **kwargs: store)
    monkeypatch.setattr(processor_module, "HospitalAPIClient", FakeHospitalClient)
    monkeypatch.setattr(processor_module, "publish_event", lambda batch_id, event: events.append(event))

    result = processor_module.process_batch("batch-success")

    assert result["status"] == BatchStatus.COMPLETED
    assert result["hospitals"][0]["status"] == RowStatus.CREATED_AND_ACTIVATED
    assert any(event["type"] == "done" for event in events)


def test_process_batch_records_failures(fake_redis, monkeypatch) -> None:
    class FailingClient(FakeHospitalClient):
        def create_hospital(
            self,
            name: str,
            address: str,
            phone: str | None,
            batch_id: str,
        ) -> dict[str, str]:
            raise processor_module.HospitalAPIError("create failed")

    store = BatchStore(conn=fake_redis)
    store.create_batch(
        "batch-failure",
        [{"row": 1, "name": "Beta Clinic", "address": "2 Oak St", "phone": None}],
    )

    events: list[dict[str, object]] = []
    monkeypatch.setattr(processor_module, "BatchStore", lambda *args, **kwargs: store)
    monkeypatch.setattr(processor_module, "HospitalAPIClient", FailingClient)
    monkeypatch.setattr(processor_module, "publish_event", lambda batch_id, event: events.append(event))

    result = processor_module.process_batch("batch-failure")

    assert result["status"] == BatchStatus.FAILED
    assert result["hospitals"][0]["status"] == RowStatus.FAILED
    assert any(event["type"] == "done" for event in events)
