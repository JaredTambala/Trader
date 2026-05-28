from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tests.support.duckdb_store import DuckDBEventStore
from trader.data import EventStore, NoOpEventStore
from trader.sample_data import load_sample_market_data_csv
from trader_research.data import (
    DataEnsureLoadedPolicy,
    DataEnsureLoadedRequest,
    DataInventoryRequest,
    data_ensure_loaded,
    get_data_inventory,
)


SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")


def _request(
    *,
    symbols: tuple[str, ...] = ("DEMO",),
    asset_class: str = "stocks",
    timeframe: str = "1Min",
    start: datetime = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
    end: datetime = datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
    mode: str = "existing",
    dry_run: bool = True,
) -> DataEnsureLoadedRequest:
    return DataEnsureLoadedRequest(
        symbols=symbols,
        asset_class=asset_class,
        timeframe=timeframe,
        start=start,
        end=end,
        mode=mode,
        dry_run=dry_run,
    )


def test_data_ensure_existing_succeeds_when_data_is_complete(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)

    envelope = data_ensure_loaded(store, _request(mode="existing"))
    result = envelope.to_dict()["data"]["load_result"]

    assert envelope.ok is True
    assert envelope.agent_owner == "Data Agent"
    assert envelope.side_effect.value == "local_mutating"
    assert result["mode"] == "existing"
    assert result["status"] == "already_loaded"
    assert result["rows_loaded"] == 0
    assert result["post_load_manifest"]["total_rows"] == 12


def test_data_ensure_existing_fails_when_data_is_incomplete(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))

    envelope = data_ensure_loaded(store, _request(mode="existing"))

    assert envelope.ok is False
    assert envelope.errors[0]["code"] == "data_missing"
    result = envelope.to_dict()["data"]["load_result"]
    assert result["status"] == "data_missing"
    assert result["post_load_manifest"]["total_rows"] == 0


def test_data_ensure_sample_refuses_when_loading_not_allowed(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))

    envelope = data_ensure_loaded(
        store,
        _request(mode="sample", dry_run=False),
        policy=DataEnsureLoadedPolicy(allow_data_loading=False),
    )

    assert envelope.ok is False
    assert envelope.errors[0]["code"] == "data_loading_not_allowed"


def test_data_ensure_sample_loads_checked_in_csv_when_allowed(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))

    envelope = data_ensure_loaded(
        store,
        _request(mode="sample", dry_run=False),
        policy=DataEnsureLoadedPolicy(allow_data_loading=True, sample_csv_path=SAMPLE_CSV),
    )
    result = envelope.to_dict()["data"]["load_result"]

    assert envelope.ok is True
    assert result["mode"] == "sample"
    assert result["status"] == "loaded"
    assert result["rows_loaded"] == 12
    assert result["pre_load_manifest"]["total_rows"] == 0
    assert result["post_load_manifest"]["total_rows"] == 12
    assert result["post_load_quality_report"]["complete"] is True


def test_data_ensure_backfill_dry_run_returns_bounded_plan_without_writes(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))

    envelope = data_ensure_loaded(store, _request(mode="backfill", dry_run=True))
    result = envelope.to_dict()["data"]["load_result"]
    inventory = get_data_inventory(
        store,
        DataInventoryRequest(
            symbols=("DEMO",),
            asset_class="stocks",
            timeframe="1Min",
            start=datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
        ),
    ).to_dict()["data"]["dataset_manifest"]

    assert envelope.ok is True
    assert result["mode"] == "backfill"
    assert result["status"] == "planned"
    assert result["rows_loaded"] == 0
    assert result["backfill_plan"]["network_calls"] == 0
    assert result["backfill_plan"]["writes"] == 0
    assert inventory["total_rows"] == 0


def test_data_ensure_backfill_non_dry_run_uses_injected_runner(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    calls: list[DataEnsureLoadedRequest] = []

    def _runner(request: DataEnsureLoadedRequest, event_store: EventStore) -> Mapping[str, Any]:
        calls.append(request)
        rows_loaded = load_sample_market_data_csv(event_store, SAMPLE_CSV)
        return {"rows_written": rows_loaded, "rows_loaded": rows_loaded, "source": "test_runner"}

    envelope = data_ensure_loaded(
        store,
        _request(mode="backfill", dry_run=False),
        policy=DataEnsureLoadedPolicy(allow_data_loading=True, backfill_runner=_runner),
    )
    result = envelope.to_dict()["data"]["load_result"]

    assert envelope.ok is True
    assert calls[0].symbols == ("DEMO",)
    assert result["mode"] == "backfill"
    assert result["status"] == "ran"
    assert result["rows_loaded"] == 12
    assert result["runner_result"]["source"] == "test_runner"
    assert result["pre_load_manifest"]["total_rows"] == 0
    assert result["post_load_manifest"]["total_rows"] == 12
    assert result["post_load_quality_report"]["complete"] is True


def test_data_ensure_backfill_non_dry_run_requires_runner_or_config_path(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))

    envelope = data_ensure_loaded(
        store,
        _request(mode="backfill", dry_run=False),
        policy=DataEnsureLoadedPolicy(allow_data_loading=True),
    )

    assert envelope.ok is False
    assert envelope.errors[0]["code"] == "backfill_runner_required"


def test_data_ensure_requires_queryable_connection() -> None:
    envelope = data_ensure_loaded(NoOpEventStore(), _request(mode="existing"))

    assert envelope.ok is False
    assert envelope.errors[0]["code"] == "event_store_connection_unavailable"
