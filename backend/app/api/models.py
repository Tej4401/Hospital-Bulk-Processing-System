"""Flask-RESTX Swagger models (request parser + response schemas)."""
from flask_restx import Namespace, fields, reqparse
from werkzeug.datastructures import FileStorage

api = Namespace(
    "hospitals",
    description="Bulk hospital CSV ingestion, status and resume operations",
    path="/hospitals",
)

# --- Multipart upload parser -------------------------------------------
upload_parser = reqparse.RequestParser()
upload_parser.add_argument(
    "file",
    location="files",
    type=FileStorage,
    required=True,
    help="CSV file with header 'name,address,phone' (phone optional). "
    "Max rows configurable (default 20).",
)

# --- Response models ----------------------------------------------------
hospital_result_model = api.model(
    "HospitalResult",
    {
        "row": fields.Integer(description="1-based row number in the CSV"),
        "hospital_id": fields.Integer(
            description="ID assigned by the downstream API", allow_null=True
        ),
        "name": fields.String(description="Hospital name"),
        "status": fields.String(
            description="pending | created | created_and_activated | failed"
        ),
        "error": fields.String(description="Failure reason, if any", allow_null=True),
    },
)

batch_status_model = api.model(
    "BatchStatus",
    {
        "batch_id": fields.String(description="UUID identifying the batch"),
        "status": fields.String(
            description="queued | processing | activating | completed | "
            "partially_failed | failed"
        ),
        "total_hospitals": fields.Integer,
        "processed_hospitals": fields.Integer,
        "failed_hospitals": fields.Integer,
        "processing_time_seconds": fields.Float(allow_null=True),
        "batch_activated": fields.Boolean,
        "created_at": fields.String,
        "started_at": fields.String(allow_null=True),
        "finished_at": fields.String(allow_null=True),
        "error": fields.String(allow_null=True),
        "hospitals": fields.List(fields.Nested(hospital_result_model)),
    },
)

upload_accepted_model = api.model(
    "UploadAccepted",
    {
        "batch_id": fields.String(description="Use this id to poll status / resume"),
        "status": fields.String(example="queued"),
        "total_hospitals": fields.Integer,
        "message": fields.String,
        "status_url": fields.String,
        "resume_url": fields.String,
    },
)

batch_list_item = api.model(
    "BatchListItem",
    {
        "batch_id": fields.String,
        "status": fields.String,
        "total_hospitals": fields.Integer,
        "processed_hospitals": fields.Integer,
        "failed_hospitals": fields.Integer,
        "created_at": fields.String,
    },
)

batch_list_model = api.model(
    "BatchList",
    {"batches": fields.List(fields.Nested(batch_list_item))},
)

error_model = api.model(
    "Error",
    {"message": fields.String(description="Human-readable error message")},
)
