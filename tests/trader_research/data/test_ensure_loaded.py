"""Unit contracts for bounded research-data readiness and loading.

Subject: Existing-data checks, sample loading, backfill planning, mutation journals, and recovery.
Level: In-process unit and local workflow contract.
Collaborators: Real Data services, shared DuckDB, sample CSV, injected runners, and in-memory artifacts.
Guarantees: Loading obeys policy, remains bounded and idempotent, and reconciles interrupted evidence writes.
Non-goals: Real providers, Postgres recovery, symbol discovery, orchestration routing, or data promotion.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tests.support.duckdb_store import DuckDBEventStore
from trader.event_store import EventStore, NoOpEventStore
from trader.market_data.sample import load_sample_market_data_csv
from trader_research.data import (
    DataEnsureLoadedPolicy,
    DataEnsureLoadedRequest,
    DataInventoryRequest,
    data_ensure_loaded,
    get_data_inventory,
)
from trader_research.foundation import InMemoryResearchArtifactStore
from trader_research.foundation.artifacts import (
    ResearchArtifactRecord,
    ResearchArtifactStoreError,
)
from trader_research.governance import DATA_LOAD_EVIDENCE


SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")


class _FailTerminalEvidenceOnceStore(InMemoryResearchArtifactStore):
    """Simulate a lost response after provider mutation has completed."""

    def __init__(self) -> None:
        super().__init__()
        self._fail_terminal_once = True

    def save_artifact(self, **kwargs: Any) -> ResearchArtifactRecord:
        """Fail the first terminal receipt write and retain prepared state."""
        if (
            kwargs.get("artifact_type") == DATA_LOAD_EVIDENCE
            and self._fail_terminal_once
        ):
            self._fail_terminal_once = False
            raise ResearchArtifactStoreError("simulated terminal write failure")
        return super().save_artifact(**kwargs)


def _request(
    *,
    symbols: tuple[str, ...] = ("DEMO",),
    asset_class: str = "stocks",
    timeframe: str = "1Min",
    start: datetime = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
    end: datetime = datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
    mode: str = "existing",
    dry_run: bool = True,
    acquisition_plan_id: str | None = None,
    operation_id: str | None = None,
    requested_by: str = "test-session",
    actor: str = "Data Research Agent",
) -> DataEnsureLoadedRequest:
    return DataEnsureLoadedRequest(
        symbols=symbols,
        asset_class=asset_class,
        timeframe=timeframe,
        start=start,
        end=end,
        mode=mode,
        dry_run=dry_run,
        acquisition_plan_id=acquisition_plan_id,
        operation_id=operation_id,
        requested_by=requested_by,
        actor=actor,
    )


def test_data_ensure_existing_succeeds_when_data_is_complete(tmp_path: Path) -> None:
    """Existing mode returns ready evidence without writing when the requested window is complete."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)

    envelope = data_ensure_loaded(store, _request(mode="existing"))
    result = envelope.to_dict()["data"]["load_result"]

    assert envelope.ok is True
    assert envelope.operation == "data_ensure_loaded"
    assert result["mode"] == "existing"
    assert result["status"] == "already_loaded"
    assert result["rows_loaded"] == 0
    assert result["post_load_manifest"]["total_rows"] == 12


def test_data_ensure_existing_fails_when_data_is_incomplete(tmp_path: Path) -> None:
    """Existing mode reports missing data explicitly when no requested bars are available."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))

    envelope = data_ensure_loaded(store, _request(mode="existing"))

    assert envelope.ok is False
    assert envelope.errors[0]["code"] == "data_missing"
    result = envelope.to_dict()["data"]["load_result"]
    assert result["status"] == "data_missing"
    assert result["post_load_manifest"]["total_rows"] == 0


def test_data_ensure_sample_refuses_when_loading_not_allowed(tmp_path: Path) -> None:
    """Sample loading fails closed when mutation policy does not authorize data writes."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))

    envelope = data_ensure_loaded(
        store,
        _request(
            mode="sample",
            dry_run=False,
            operation_id="sample-operation-1",
        ),
        policy=DataEnsureLoadedPolicy(allow_data_loading=False),
    )

    assert envelope.ok is False
    assert envelope.errors[0]["code"] == "data_loading_not_allowed"


def test_data_ensure_sample_loads_checked_in_csv_when_allowed(tmp_path: Path) -> None:
    """Authorized sample loading writes checked-in bars and returns post-load readiness evidence."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    journal = InMemoryResearchArtifactStore()

    envelope = data_ensure_loaded(
        store,
        _request(
            mode="sample",
            dry_run=False,
            operation_id="sample-operation-1",
        ),
        policy=DataEnsureLoadedPolicy(
            allow_data_loading=True, sample_csv_path=SAMPLE_CSV
        ),
        artifact_store=journal,
    )
    result = envelope.to_dict()["data"]["load_result"]

    assert envelope.ok is True
    assert result["mode"] == "sample"
    assert result["status"] == "loaded"
    assert result["rows_loaded"] == 12
    assert result["pre_load_manifest"]["total_rows"] == 0
    assert result["post_load_manifest"]["total_rows"] == 12
    assert result["post_load_quality_report"]["complete"] is True


def test_data_ensure_backfill_dry_run_returns_bounded_plan_without_writes(
    tmp_path: Path,
) -> None:
    """A backfill dry run describes bounded calls and writes without mutating inventory."""
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
    """An approved backfill invokes its injected runner once and replays terminal evidence idempotently."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    journal = InMemoryResearchArtifactStore()
    calls: list[DataEnsureLoadedRequest] = []

    def _runner(
        request: DataEnsureLoadedRequest, event_store: EventStore
    ) -> Mapping[str, Any]:
        calls.append(request)
        rows_loaded = load_sample_market_data_csv(event_store, SAMPLE_CSV)
        return {
            "rows_written": rows_loaded,
            "rows_loaded": rows_loaded,
            "source": "test_runner",
        }

    policy = DataEnsureLoadedPolicy(
        allow_data_loading=True,
        backfill_runner=_runner,
    )
    planned = data_ensure_loaded(
        store,
        _request(mode="backfill", dry_run=True),
        policy=policy,
    )
    plan_id = planned.data["load_result"]["backfill_plan"]["plan_id"]
    envelope = data_ensure_loaded(
        store,
        _request(
            mode="backfill",
            dry_run=False,
            acquisition_plan_id=plan_id,
            operation_id="backfill-operation-1",
        ),
        policy=policy,
        artifact_store=journal,
    )
    result = envelope.to_dict()["data"]["load_result"]

    replay = data_ensure_loaded(
        store,
        _request(
            mode="backfill",
            dry_run=False,
            acquisition_plan_id=plan_id,
            operation_id="backfill-operation-1",
        ),
        policy=policy,
        artifact_store=journal,
    )

    assert envelope.ok is True
    assert calls[0].symbols == ("DEMO",)
    assert result["mode"] == "backfill"
    assert result["status"] == "ran"
    assert result["rows_loaded"] == 12
    assert result["runner_result"]["source"] == "test_runner"
    assert result["pre_load_manifest"]["total_rows"] == 0
    assert result["post_load_manifest"]["total_rows"] == 12
    assert result["post_load_quality_report"]["complete"] is True
    assert replay.data["load_result"]["idempotent_replay"] is True
    assert len(calls) == 1


def test_data_load_recovers_prepared_operation_without_repeating_provider(
    tmp_path: Path,
) -> None:
    """Prepared loading evidence reconciles a lost terminal write without repeating provider mutation."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    journal = _FailTerminalEvidenceOnceStore()
    calls: list[DataEnsureLoadedRequest] = []

    def _runner(
        request: DataEnsureLoadedRequest,
        event_store: EventStore,
    ) -> Mapping[str, Any]:
        calls.append(request)
        rows_loaded = load_sample_market_data_csv(event_store, SAMPLE_CSV)
        return {"rows_loaded": rows_loaded}

    policy = DataEnsureLoadedPolicy(
        allow_data_loading=True,
        backfill_runner=_runner,
    )
    planned = data_ensure_loaded(
        store,
        _request(mode="backfill", dry_run=True),
        policy=policy,
    )
    plan_id = planned.data["load_result"]["backfill_plan"]["plan_id"]
    request = _request(
        mode="backfill",
        dry_run=False,
        acquisition_plan_id=plan_id,
        operation_id="interrupted-backfill-operation",
    )

    interrupted = data_ensure_loaded(
        store,
        request,
        policy=policy,
        artifact_store=journal,
    )
    recovered = data_ensure_loaded(
        store,
        request,
        policy=policy,
        artifact_store=journal,
    )

    assert interrupted.ok is False
    assert interrupted.errors[0]["code"] == "data_load_evidence_persistence_failed"
    assert recovered.ok is True
    assert recovered.data["load_result"]["status"] == "recovered_after_interruption"
    assert recovered.data["load_result"]["idempotent_replay"] is False
    assert len(calls) == 1


def test_data_ensure_backfill_non_dry_run_requires_runner_or_config_path(
    tmp_path: Path,
) -> None:
    """A mutating backfill requires an executable runner or explicit provider configuration path."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    journal = InMemoryResearchArtifactStore()

    policy = DataEnsureLoadedPolicy(allow_data_loading=True)
    planned = data_ensure_loaded(
        store,
        _request(mode="backfill", dry_run=True),
        policy=policy,
    )
    plan_id = planned.data["load_result"]["backfill_plan"]["plan_id"]
    envelope = data_ensure_loaded(
        store,
        _request(
            mode="backfill",
            dry_run=False,
            acquisition_plan_id=plan_id,
            operation_id="backfill-operation-1",
        ),
        policy=policy,
        artifact_store=journal,
    )

    assert envelope.ok is False
    assert envelope.errors[0]["code"] == "backfill_runner_required"


def test_data_ensure_requires_queryable_connection() -> None:
    """Readiness inspection returns a structured error when the event store cannot be queried."""
    envelope = data_ensure_loaded(NoOpEventStore(), _request(mode="existing"))

    assert envelope.ok is False
    assert envelope.errors[0]["code"] == "event_store_connection_unavailable"
