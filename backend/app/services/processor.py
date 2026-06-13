"""Core batch-processing workflow (executed by the background worker).

Workflow per the spec:

1. Load the accepted CSV rows for the batch.
2. (Resume only) Reconcile with the downstream API so rows already created
   in a previous, interrupted run are not created again.
3. Call ``POST /hospitals/`` for every pending row, tagging each with the
   batch id. Progress is persisted to Redis after every row so a crash can
   be resumed at any point.
4. If — and only if — every row was created successfully, call
   ``PATCH /hospitals/batch/{batch_id}/activate``.
5. Persist a final status (completed / partially_failed / failed).

The function is idempotent and safe to re-run: see ``resume_batch``.
"""
from __future__ import annotations

from ..client.hospital_api import HospitalAPIClient, HospitalAPIError
from ..logging_config import get_logger
from .batch_store import BatchStatus, BatchStore, RowStatus
from .events import publish_event

_DONE_ROW_STATES = (RowStatus.CREATED, RowStatus.CREATED_AND_ACTIVATED)


def _emit(store: BatchStore, batch_id: str, event_type: str) -> None:
    """Publish the current batch snapshot as a real-time progress event.

    ``event_type`` is ``progress`` for intermediate updates and ``done`` for
    the terminal state (which tells subscribers to close the stream).
    """
    view = store.view(batch_id)
    if view is not None:
        publish_event(batch_id, {"type": event_type, "batch": view.to_dict()})


def process_batch(batch_id: str) -> dict:
    """RQ entrypoint: create hospitals for a batch and activate it.

    Returns the final batch view as a dict (useful for the RQ job result).
    """
    log = get_logger(__name__, batch_id)
    store = BatchStore()

    if not store.exists(batch_id):
        log.error("process_batch called for unknown batch")
        return {"error": "unknown batch"}

    rows = store.get_rows(batch_id)
    log.info("Starting processing of %d row(s)", len(rows))
    store.mark_started(batch_id)
    _emit(store, batch_id, "progress")

    client = HospitalAPIClient()

    # On resume, reconcile already-created hospitals so we don't duplicate.
    _reconcile_existing(store, client, batch_id, rows, log)

    created_any_this_run = False
    for row in rows:
        existing = store.get_result(batch_id, row["row"])
        if existing and existing["status"] in _DONE_ROW_STATES:
            log.debug("Row %s already created; skipping", row["row"])
            continue

        try:
            hospital = client.create_hospital(
                name=row["name"],
                address=row["address"],
                phone=row.get("phone"),
                batch_id=batch_id,
            )
            store.update_row_result(
                batch_id,
                row["row"],
                hospital_id=hospital.get("id"),
                name=row["name"],
                status=RowStatus.CREATED,
                error=None,
            )
            created_any_this_run = True
            log.info(
                "Row %s created hospital id=%s (%s)",
                row["row"],
                hospital.get("id"),
                row["name"],
            )
        except HospitalAPIError as exc:
            store.update_row_result(
                batch_id,
                row["row"],
                name=row["name"],
                status=RowStatus.FAILED,
                error=str(exc),
            )
            log.error("Row %s failed to create: %s", row["row"], exc)
        finally:
            store.recount(batch_id)
            _emit(store, batch_id, "progress")

    processed, failed = store.recount(batch_id)
    total = len(rows)
    log.info("Creation phase done: processed=%d failed=%d total=%d", processed, failed, total)

    # Activation only happens when every row succeeded.
    if failed == 0 and processed == total and total > 0:
        store.set_status(batch_id, BatchStatus.ACTIVATING)
        _emit(store, batch_id, "progress")
        try:
            log.info("All hospitals created; activating batch")
            client.activate_batch(batch_id)
            store.mark_activated(batch_id)
            store.mark_finished(batch_id, BatchStatus.COMPLETED)
            log.info("Batch activated and completed")
        except HospitalAPIError as exc:
            store.set_status(batch_id, BatchStatus.FAILED, error=f"Activation failed: {exc}")
            store.mark_finished(batch_id, BatchStatus.FAILED)
            log.error("Activation failed: %s", exc)
    else:
        status = BatchStatus.PARTIALLY_FAILED if processed > 0 else BatchStatus.FAILED
        store.mark_finished(batch_id, status)
        if not created_any_this_run and processed == 0:
            log.warning("Batch finished with no successful rows (%s)", status)
        else:
            log.warning(
                "Batch finished without activation (%s); %d row(s) failed",
                status,
                failed,
            )

    # Terminal event tells SSE subscribers to close the stream.
    _emit(store, batch_id, "done")
    view = store.view(batch_id)
    return view.to_dict() if view else {"batch_id": batch_id}


def _reconcile_existing(store, client, batch_id, rows, log) -> None:
    """Best-effort: mark rows already present downstream as created.

    Primary resume safety comes from per-row Redis state. This adds a second
    layer for the rare case where a hospital was created downstream but the
    process crashed before recording it. Matching is by (name, address).
    """
    pending_rows = [
        r
        for r in rows
        if (store.get_result(batch_id, r["row"]) or {}).get("status")
        not in _DONE_ROW_STATES
    ]
    if not pending_rows:
        return

    try:
        existing = client.get_batch(batch_id)
    except HospitalAPIError as exc:
        log.warning("Could not fetch existing batch for reconciliation: %s", exc)
        return

    if not existing:
        return

    index: dict[tuple[str, str], dict] = {}
    for h in existing:
        key = (str(h.get("name", "")).strip(), str(h.get("address", "")).strip())
        index.setdefault(key, h)

    reconciled = 0
    for r in pending_rows:
        key = (r["name"].strip(), r["address"].strip())
        match = index.get(key)
        if match:
            store.update_row_result(
                batch_id,
                r["row"],
                hospital_id=match.get("id"),
                name=r["name"],
                status=(
                    RowStatus.CREATED_AND_ACTIVATED
                    if match.get("active")
                    else RowStatus.CREATED
                ),
                error=None,
            )
            reconciled += 1

    if reconciled:
        store.recount(batch_id)
        log.info("Reconciled %d already-created hospital(s) on resume", reconciled)


def resume_batch(batch_id: str) -> dict:
    """Resume an interrupted/failed batch by re-running ``process_batch``.

    ``process_batch`` is idempotent: completed rows are skipped, so calling
    it again only retries pending/failed rows and (re)attempts activation.
    """
    log = get_logger(__name__, batch_id)
    log.info("Resuming batch")
    return process_batch(batch_id)
