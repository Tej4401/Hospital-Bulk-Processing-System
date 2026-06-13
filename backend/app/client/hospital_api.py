"""HTTP client for the existing (downstream) Hospital Directory API.

Wraps the endpoints this service depends on with retry/backoff and clear
exception semantics so the processor can react sensibly to failures.
"""
from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import Config
from ..logging_config import get_logger

logger = get_logger(__name__)


class HospitalAPIError(Exception):
    """Raised when a downstream Hospital API call ultimately fails."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class HospitalAPIClient:
    """Thin, retrying wrapper around the downstream Hospital Directory API."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or Config.EXTERNAL_API_BASE_URL).rstrip("/")
        self.timeout = Config.HTTP_TIMEOUT
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=Config.HTTP_MAX_RETRIES,
            connect=Config.HTTP_MAX_RETRIES,
            read=Config.HTTP_MAX_RETRIES,
            backoff_factor=Config.HTTP_BACKOFF_FACTOR,
            # Only retry idempotent-ish transient failures. POST is included
            # because creates may legitimately need a retry on 5xx/timeout;
            # callers must tolerate the (small) risk of duplicates.
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST", "PATCH", "DELETE"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({"Content-Type": "application/json"})
        return session

    # -- Endpoints -------------------------------------------------------
    def create_hospital(
        self,
        name: str,
        address: str,
        phone: str | None,
        batch_id: str,
    ) -> dict[str, Any]:
        """POST /hospitals/ — create a single hospital tied to ``batch_id``."""
        payload = {
            "name": name,
            "address": address,
            "phone": phone,
            "creation_batch_id": batch_id,
        }
        url = f"{self.base_url}/hospitals/"
        resp = self._request("POST", url, json=payload)
        return resp.json()

    def activate_batch(self, batch_id: str) -> dict[str, Any]:
        """PATCH /hospitals/batch/{batch_id}/activate."""
        url = f"{self.base_url}/hospitals/batch/{batch_id}/activate"
        resp = self._request("PATCH", url)
        try:
            return resp.json()
        except ValueError:
            return {"status": "ok"}

    def get_batch(self, batch_id: str) -> list[dict[str, Any]]:
        """GET /hospitals/batch/{batch_id} — used for resume reconciliation."""
        url = f"{self.base_url}/hospitals/batch/{batch_id}"
        resp = self._request("GET", url)
        data = resp.json()
        # Tolerate either a bare list or an envelope like {"hospitals": [...]}.
        if isinstance(data, dict):
            return data.get("hospitals", [])
        return data

    def delete_batch(self, batch_id: str) -> None:
        """DELETE /hospitals/batch/{batch_id}."""
        url = f"{self.base_url}/hospitals/batch/{batch_id}"
        self._request("DELETE", url)

    # -- Internal --------------------------------------------------------
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        try:
            resp = self.session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            logger.error("HTTP %s %s failed: %s", method, url, exc)
            raise HospitalAPIError(f"Request to {url} failed: {exc}") from exc

        if resp.status_code >= 400:
            body = resp.text[:500]
            logger.error(
                "HTTP %s %s returned %s: %s", method, url, resp.status_code, body
            )
            raise HospitalAPIError(
                f"{method} {url} returned {resp.status_code}: {body}",
                status_code=resp.status_code,
            )

        logger.debug("HTTP %s %s -> %s", method, url, resp.status_code)
        return resp
