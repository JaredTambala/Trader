"""Unit contracts for research dataset inventory manifests.

Subject: Multi-symbol coverage inventory, stable manifests, validation, and unavailable-store behavior.
Level: In-process unit contract.
Collaborators: Real Data inventory service with shared DuckDB or a no-op event store; no provider.
Guarantees: Inventory reports complete and missing coverage while rejecting invalid bounded requests.
Non-goals: Loading data, measuring temporal gaps, provider discovery, Postgres, or coordinator decisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.support.duckdb_store import DuckDBEventStore
from trader.event_store import NoOpEventStore
from trader.market_data.sample import load_sample_market_data_csv
from trader_research.data import DataInventoryRequest, get_data_inventory


SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")


def _request(
    *,
    symbols: tuple[str, ...] = ("DEMO",),
    asset_class: str = "stocks",
    timeframe: str = "1Min",
    start: datetime = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
    end: datetime = datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
    source: str | None = None,
) -> DataInventoryRequest:
    return DataInventoryRequest(
        symbols=symbols,
        asset_class=asset_class,
        timeframe=timeframe,
        start=start,
        end=end,
        source=source,
    )


def test_data_inventory_returns_dataset_manifest_for_sample_data(
    tmp_path: Path,
) -> None:
    """Complete sample bars produce a stable dataset manifest with per-symbol coverage details."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)
    request = _request(symbols=("DEMO",))

    first = get_data_inventory(store, request)
    second = get_data_inventory(store, request)

    assert first.ok is True
    assert first.operation == "data_get_inventory"
    assert first.warnings == ()
    manifest = first.to_dict()["data"]["dataset_manifest"]
    assert (
        manifest["dataset_id"]
        == second.to_dict()["data"]["dataset_manifest"]["dataset_id"]
    )
    assert manifest["asset_class"] == "stocks"
    assert manifest["symbols"] == ["DEMO"]
    assert manifest["timeframe"] == "1Min"
    assert manifest["source_filter"] is None
    assert "table" not in manifest
    assert manifest["total_rows"] == 12
    assert manifest["complete"] is True
    assert manifest["symbols_detail"] == [
        {
            "symbol": "DEMO",
            "row_count": 12,
            "first_ts": "2026-01-20T12:00:00+00:00",
            "last_ts": "2026-01-20T12:11:00+00:00",
            "sources": {"sample": 12},
        }
    ]


def test_data_inventory_warns_for_missing_symbol(tmp_path: Path) -> None:
    """A missing requested symbol remains a successful but explicitly incomplete inventory result."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)

    envelope = get_data_inventory(store, _request(symbols=("MISSING",)))
    manifest = envelope.to_dict()["data"]["dataset_manifest"]

    assert envelope.ok is True
    assert manifest["complete"] is False
    assert manifest["total_rows"] == 0
    assert manifest["symbols_detail"][0]["row_count"] == 0
    assert envelope.warnings == ("No bars found for MISSING.",)


@pytest.mark.parametrize(
    ("inventory_request", "code", "message"),
    [
        (_request(symbols=()), "validation_error", "at least one symbol"),
        (
            _request(symbols=tuple(f"SYM{index}" for index in range(21))),
            "validation_error",
            "at most 20 symbols",
        ),
        (
            _request(asset_class="forex"),
            "unsupported_instrument_type",
            "does not support instrument type forex",
        ),
        (_request(timeframe="bad"), "validation_error", "Invalid timeframe"),
        (
            _request(
                start=datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
                end=datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
            ),
            "validation_error",
            "end must be at or after start",
        ),
    ],
)
def test_data_inventory_validation_failures(
    inventory_request: DataInventoryRequest,
    code: str,
    message: str,
) -> None:
    """Invalid universes, instruments, timeframes, and windows yield specific validation evidence."""
    envelope = get_data_inventory(NoOpEventStore(), inventory_request)

    assert envelope.ok is False
    assert envelope.errors[0]["code"] == code
    assert message in str(envelope.errors[0]["message"])


def test_data_inventory_requires_queryable_connection() -> None:
    """Inventory reports a structured failure when its event store exposes no query connection."""
    envelope = get_data_inventory(NoOpEventStore(), _request())

    assert envelope.ok is False
    assert envelope.errors == (
        {
            "code": "event_store_connection_unavailable",
            "message": "Event store does not expose a queryable connection.",
        },
    )
