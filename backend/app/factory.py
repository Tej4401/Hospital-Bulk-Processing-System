"""Flask application factory wiring up Flask-RESTX + Swagger UI."""
from __future__ import annotations

from flask import Flask, jsonify
from flask_restx import Api
from flask_cors import CORS

from .config import Config
from .extensions import redis_conn
from .logging_config import get_logger, setup_logging

logger = get_logger(__name__)


def create_app() -> Flask:
    setup_logging()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH
    app.config["RESTX_MASK_SWAGGER"] = False
    app.config["ERROR_404_HELP"] = False

    # Enable CORS for API endpoints. In development this allows the UI dev
    # server or other origins to talk to the API directly. In production you
    # should restrict `origins` appropriately (e.g. to your frontend host).
    CORS(app, resources={r"/*": {"origins": "*"}})

    api = Api(
        app,
        version="1.0",
        title="Bulk Hospital Processor",
        description=(
            "Asynchronous bulk hospital ingestion. Upload a CSV to create "
            "hospitals via the downstream Hospital Directory API under a "
            "single batch id, then auto-activate the batch. Supports status "
            "polling and resume."
        ),
        doc="/docs",
        prefix="",
    )

    # Import here to avoid circular imports at module load time.
    from .api.models import api as hospitals_ns
    from .api import bulk  # noqa: F401  (registers routes on the namespace)

    api.add_namespace(hospitals_ns)

    @app.route("/health")
    def health():
        """Liveness/readiness probe including Redis connectivity."""
        redis_ok = True
        try:
            redis_conn.ping()
        except Exception as exc:  # noqa: BLE001
            redis_ok = False
            logger.error("Redis health check failed: %s", exc)
        status = "ok" if redis_ok else "degraded"
        code = 200 if redis_ok else 503
        return jsonify({"status": status, "redis": redis_ok}), code

    @app.errorhandler(413)
    def too_large(_err):
        return jsonify({"message": "Uploaded file is too large."}), 413

    logger.info(
        "Application initialised (downstream API: %s)", Config.EXTERNAL_API_BASE_URL
    )
    return app
