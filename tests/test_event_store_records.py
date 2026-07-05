"""Tests for event-store record normalization helpers."""

from datetime import datetime, timezone

from trader.event_store.records import (
    EXPERIMENT_RUN_FIELDS,
    experiment_run_row_to_record,
    json_payload_or_empty,
    json_payload_or_none,
    postgres_text_array_or_empty,
    postgres_text_array_or_none,
)


def test_json_payload_helpers_serialize_optional_payloads() -> None:
    """Ensure event-store JSON normalization handles absent and datetime values."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)

    assert json_payload_or_none(None) is None
    assert json_payload_or_none({"ts": timestamp}) == '{"ts": "2026-01-21 12:00:00+00:00"}'
    assert json_payload_or_empty(None) == "{}"
    assert json_payload_or_empty({"ts": timestamp}) == '{"ts": "2026-01-21 12:00:00+00:00"}'


def test_postgres_text_array_helpers_preserve_null_semantics() -> None:
    """Ensure optional and non-null text-array normalization remain distinct."""
    assert postgres_text_array_or_none(None) is None
    assert postgres_text_array_or_none(("AAPL", "MSFT")) == ["AAPL", "MSFT"]
    assert postgres_text_array_or_empty(None) == []
    assert postgres_text_array_or_empty(("sample",)) == ["sample"]


def test_experiment_run_row_mapping_uses_stable_field_order() -> None:
    """Ensure experiment-run query rows map into the public dictionary shape."""
    row = tuple(range(len(EXPERIMENT_RUN_FIELDS)))

    record = experiment_run_row_to_record(row)

    assert tuple(record) == EXPERIMENT_RUN_FIELDS
    assert record["experiment_run_id"] == 0
    assert record["error_message"] == len(EXPERIMENT_RUN_FIELDS) - 1
