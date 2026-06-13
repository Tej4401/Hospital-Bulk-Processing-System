"""Bulk hospital endpoints: upload, status, resume and listing.

All heavy lifting is delegated to a background RQ worker; these handlers
only validate input, persist initial state, and enqueue/inspect jobs.
"""
from __future__ import annotations

import uuid

from flask import Response, stream_with_context
from flask_restx import Resource

from ..config import Config
from ..extensions import task_queue
from ..logging_config import get_logger
from ..services.batch_store import BatchStatus, BatchStore
from ..services.csv_parser import CSVValidationError, parse_csv
from ..services.events import event_stream
from .models import (
    api,
    batch_list_model,
    batch_status_model,
    error_model,
    upload_accepted_model,
    upload_parser,
)

logger = get_logger(__name__)
store = BatchStore()

_PROCESS_JOB = "app.services.processor.process_batch"


def _status_url(batch_id: str) -> str:
    return f"/hospitals/bulk/{batch_id}"


def _resume_url(batch_id: str) -> str:
    return f"/hospitals/bulk/{batch_id}/resume"


def _enqueue(batch_id: str) -> None:
    """Push the processing job onto the queue, keyed by batch id."""
    task_queue.enqueue(
        _PROCESS_JOB,
        batch_id,
        job_id=f"process:{batch_id}",
        job_timeout=Config.JOB_TIMEOUT,
        result_ttl=Config.BATCH_TTL_SECONDS,
        failure_ttl=Config.BATCH_TTL_SECONDS,
    )


@api.route("/bulk", endpoint="bulk_upload")
class BulkUpload(Resource):
    @api.doc("bulk_upload_hospitals")
    @api.expect(upload_parser)
    @api.response(202, "Accepted — processing started", upload_accepted_model)
    @api.response(400, "Invalid CSV / request", error_model)
    def post(self):
        """Upload a CSV to bulk-create hospitals (asynchronous).

        Returns ``202 Accepted`` with a ``batch_id``. Poll
        ``GET /hospitals/bulk/{batch_id}`` for progress.
        """
        args = upload_parser.parse_args()
        file_storage = args["file"]
        if file_storage is None or not file_storage.filename:
            api.abort(400, "No file provided under form field 'file'.")

        if not file_storage.filename.lower().endswith(".csv"):
            api.abort(400, "Uploaded file must have a .csv extension.")

        raw = file_storage.read()
        try:
            rows = parse_csv(raw)
        except CSVValidationError as exc:
            logger.warning("Rejected upload '%s': %s", file_storage.filename, exc)
            api.abort(400, str(exc))

        batch_id = str(uuid.uuid4())
        blog = get_logger(__name__, batch_id)
        store.create_batch(batch_id, rows)
        _enqueue(batch_id)
        blog.info(
            "Accepted upload '%s' with %d hospital(s); enqueued for processing",
            file_storage.filename,
            len(rows),
        )

        return {
            "batch_id": batch_id,
            "status": BatchStatus.QUEUED,
            "total_hospitals": len(rows),
            "message": "CSV accepted; processing started asynchronously.",
            "status_url": _status_url(batch_id),
            "resume_url": _resume_url(batch_id),
        }, 202


@api.route("/bulk/<string:batch_id>", endpoint="batch_status")
@api.param("batch_id", "The batch UUID returned from the upload call")
class BatchStatusResource(Resource):
    @api.doc("batch_status")
    @api.response(200, "Current batch status", batch_status_model)
    @api.response(404, "Batch not found", error_model)
    @api.marshal_with(batch_status_model)
    def get(self, batch_id):
        """Get processing status and per-row results for a batch."""
        view = store.view(batch_id)
        if view is None:
            api.abort(404, f"Batch '{batch_id}' not found.")
        return view.to_dict()


@api.route("/bulk/<string:batch_id>/resume", endpoint="batch_resume")
@api.param("batch_id", "The batch UUID returned from the upload call")
class BatchResumeResource(Resource):
    @api.doc("batch_resume")
    @api.response(202, "Resume accepted", upload_accepted_model)
    @api.response(404, "Batch not found", error_model)
    @api.response(409, "Batch already completed / cannot be resumed", error_model)
    def post(self, batch_id):
        """Resume an interrupted, failed or partially-failed batch.

        Idempotent: already-created hospitals are skipped and only
        pending/failed rows are retried before activation is re-attempted.
        """
        view = store.view(batch_id)
        if view is None:
            api.abort(404, f"Batch '{batch_id}' not found.")

        if view.status == BatchStatus.COMPLETED:
            api.abort(409, "Batch already completed; nothing to resume.")

        blog = get_logger(__name__, batch_id)
        store.set_status(batch_id, BatchStatus.QUEUED, error="")
        _enqueue(batch_id)
        blog.info("Resume requested; re-enqueued for processing")

        return {
            "batch_id": batch_id,
            "status": BatchStatus.QUEUED,
            "total_hospitals": view.total_hospitals,
            "message": "Batch re-enqueued; resuming pending/failed rows.",
            "status_url": _status_url(batch_id),
            "resume_url": _resume_url(batch_id),
        }, 202


@api.route("/bulk/<string:batch_id>/events", endpoint="batch_events")
@api.param("batch_id", "The batch UUID returned from the upload call")
class BatchEvents(Resource):
    @api.doc("batch_events")
    @api.produces(["text/event-stream"])
    @api.response(200, "SSE stream of real-time progress events")
    @api.response(404, "Batch not found", error_model)
    def get(self, batch_id):
        """Stream real-time progress as Server-Sent Events (SSE).

        Emits an initial ``snapshot`` event, then ``progress`` events as rows
        are created/activated, and a final ``done`` event. Each event's
        ``data`` is JSON: ``{"type": ..., "batch": {<status payload>}}``.

        Consume from anything, e.g. ``curl -N`` — no frontend required.
        """
        if not store.exists(batch_id):
            api.abort(404, f"Batch '{batch_id}' not found.")

        resp = Response(
            stream_with_context(event_stream(batch_id)),
            mimetype="text/event-stream",
        )
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["Connection"] = "keep-alive"
        # Disable proxy buffering (nginx honours this) so frames flush live.
        resp.headers["X-Accel-Buffering"] = "no"
        return resp


@api.route("/batches", endpoint="batch_list")
class BatchList(Resource):
    @api.doc("list_batches")
    @api.marshal_with(batch_list_model)
    def get(self):
        """List recent batches (most recent first)."""
        return {"batches": store.list_batches(limit=100)}
