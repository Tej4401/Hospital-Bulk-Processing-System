"""CSV parsing and validation for bulk hospital uploads.

Expected format (header row required)::

    name,address,phone

``phone`` is optional (column may be omitted entirely, or left blank per
row). The number of data rows is capped by ``Config.MAX_CSV_HOSPITALS``.
"""
from __future__ import annotations

import csv
import io

from ..config import Config

REQUIRED_COLUMNS = ("name", "address")
OPTIONAL_COLUMNS = ("phone",)
ALLOWED_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS


class CSVValidationError(Exception):
    """Raised when an uploaded CSV is structurally invalid."""


def parse_csv(raw_bytes: bytes) -> list[dict[str, str | None]]:
    """Parse and validate CSV bytes into a list of normalised row dicts.

    Each returned row looks like::

        {"row": 1, "name": "...", "address": "...", "phone": "..." | None}

    ``row`` is the 1-based data-row index (the header is not counted).
    """
    if not raw_bytes:
        raise CSVValidationError("Uploaded file is empty.")

    try:
        text = raw_bytes.decode("utf-8-sig")  # tolerate a BOM
    except UnicodeDecodeError as exc:
        raise CSVValidationError(f"File is not valid UTF-8 text: {exc}") from exc

    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        raise CSVValidationError("CSV has no header row.")

    headers = [h.strip().lower() for h in reader.fieldnames if h is not None]
    _validate_headers(headers)

    rows: list[dict[str, str | None]] = []
    for line_no, raw_row in enumerate(reader, start=1):
        # Normalise keys to lowercase/trimmed to match validated headers.
        norm = {
            (k.strip().lower() if k else k): (v.strip() if isinstance(v, str) else v)
            for k, v in raw_row.items()
        }

        # Skip completely blank lines.
        if not any((norm.get(c) or "") for c in ALLOWED_COLUMNS):
            continue

        name = norm.get("name") or ""
        address = norm.get("address") or ""
        phone = norm.get("phone") or None

        if not name:
            raise CSVValidationError(f"Row {line_no}: 'name' is required.")
        if not address:
            raise CSVValidationError(f"Row {line_no}: 'address' is required.")

        rows.append(
            {
                "row": len(rows) + 1,
                "name": name,
                "address": address,
                "phone": phone,
            }
        )

        if len(rows) > Config.MAX_CSV_HOSPITALS:
            raise CSVValidationError(
                f"CSV exceeds the maximum of {Config.MAX_CSV_HOSPITALS} hospitals."
            )

    if not rows:
        raise CSVValidationError("CSV contains no data rows.")

    return rows


def _validate_headers(headers: list[str]) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        raise CSVValidationError(
            "Missing required column(s): "
            + ", ".join(missing)
            + f". Expected header: {','.join(ALLOWED_COLUMNS)}"
        )
    unknown = [h for h in headers if h not in ALLOWED_COLUMNS]
    if unknown:
        raise CSVValidationError(
            "Unexpected column(s): "
            + ", ".join(unknown)
            + f". Allowed columns: {','.join(ALLOWED_COLUMNS)}"
        )
