from __future__ import annotations

import pytest

from app.config import Config
from app.services.csv_parser import CSVValidationError, parse_csv


def test_parse_csv_returns_normalized_rows() -> None:
    rows = parse_csv(b"name,address,phone\nAcme Hospital,123 Main St,555-1234\n")

    assert rows == [
        {
            "row": 1,
            "name": "Acme Hospital",
            "address": "123 Main St",
            "phone": "555-1234",
        }
    ]


def test_parse_csv_tolerates_utf8_bom() -> None:
    rows = parse_csv("\ufeffname,address\nAcme Hospital,123 Main St\n".encode("utf-8"))

    assert rows[0]["name"] == "Acme Hospital"
    assert rows[0]["address"] == "123 Main St"


def test_parse_csv_rejects_empty_file() -> None:
    with pytest.raises(CSVValidationError, match="empty"):
        parse_csv(b"")


def test_parse_csv_requires_header_row() -> None:
    with pytest.raises(CSVValidationError, match="Missing required column"):
        parse_csv(b"\n\n")


def test_parse_csv_rejects_missing_required_column() -> None:
    with pytest.raises(CSVValidationError, match="Missing required column"):
        parse_csv(b"name,phone\nAcme Hospital,555-1234\n")


def test_parse_csv_rejects_unknown_column() -> None:
    with pytest.raises(CSVValidationError, match="Unexpected column"):
        parse_csv(b"name,address,extra\nAcme Hospital,123 Main St,foo\n")


def test_parse_csv_enforces_required_fields_on_each_row() -> None:
    with pytest.raises(CSVValidationError, match="Row 1: 'address' is required"):
        parse_csv(b"name,address\nAcme Hospital,\n")


def test_parse_csv_rejects_too_many_rows(monkeypatch) -> None:
    monkeypatch.setattr(Config, "MAX_CSV_HOSPITALS", 1)

    with pytest.raises(CSVValidationError, match="maximum"):
        parse_csv(b"name,address\nAcme Hospital,123 Main St\nBravo Clinic,456 Oak Ave\n")
