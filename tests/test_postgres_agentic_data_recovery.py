"""Fresh-connection Postgres recovery for the agentic Data mutation journal."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from tests.support.duckdb_store import DuckDBEventStore
from trader.event_store import EventStore
from trader.market_data.sample import load_sample_market_data_csv
from trader_research.data import (
    DataEnsureLoadedPolicy,
    DataEnsureLoadedRequest,
    data_ensure_loaded,
)
from trader_research.foundation import ResearchArtifactStoreError
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore


_SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")


class _FailTerminalEvidenceOnceStore:
    """Delegate to Postgres while simulating one lost terminal write."""

    def __init__(self, delegate: PostgresResearchArtifactStore) -> None:
        """Retain the exact Postgres delegate and arm one terminal failure."""
        self._delegate = delegate
        self._fail_terminal_once = True

    def save_artifact(self, **kwargs: Any) -> Any:
        """Fail one terminal Data evidence write after prepared state persists."""
        if (
            kwargs.get("artifact_type") == "data_load_evidence"
            and self._fail_terminal_once
        ):
            self._fail_terminal_once = False
            raise ResearchArtifactStoreError("simulated lost terminal response")
        return self._delegate.save_artifact(**kwargs)

    def load_artifact_record(self, artifact_type: str, artifact_id: str) -> Any:
        """Load exact canonical state through the Postgres delegate."""
        return self._delegate.load_artifact_record(artifact_type, artifact_id)


@pytest.mark.postgres
def test_data_load_journal_recovers_through_fresh_postgres_connections(
    tmp_path: Path,
) -> None:
    """Accepted provider work is not repeated after a lost terminal response."""
    dsn = str(os.environ.get("TRADER_AGENTS_ARTIFACT_TEST_DSN") or "").strip()
    if not dsn:
        pytest.skip("TRADER_AGENTS_ARTIFACT_TEST_DSN is required")
    event_store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    provider_calls: list[str] = []

    def _runner(
        request: DataEnsureLoadedRequest,
        store: EventStore,
    ) -> Mapping[str, Any]:
        provider_calls.append(str(request.operation_id))
        rows = load_sample_market_data_csv(store, _SAMPLE_CSV)
        return {"rows_loaded": rows, "source": "postgres-recovery-fixture"}

    policy = DataEnsureLoadedPolicy(
        allow_data_loading=True,
        backfill_runner=_runner,
    )
    planning_request = _request()
    planned = data_ensure_loaded(event_store, planning_request, policy=policy)
    plan_id = planned.data["load_result"]["backfill_plan"]["plan_id"]
    operation_id = f"agent-data-load-{uuid4().hex}"
    request = _request(
        dry_run=False,
        acquisition_plan_id=plan_id,
        operation_id=operation_id,
    )

    first_store = PostgresResearchArtifactStore(dsn=dsn, ensure_schema=True)
    try:
        interrupted = data_ensure_loaded(
            event_store,
            request,
            policy=policy,
            artifact_store=_FailTerminalEvidenceOnceStore(first_store),
        )
    finally:
        first_store.close()

    second_store = PostgresResearchArtifactStore(dsn=dsn, ensure_schema=False)
    try:
        recovered = data_ensure_loaded(
            event_store,
            request,
            policy=policy,
            artifact_store=second_store,
        )
    finally:
        second_store.close()

    third_store = PostgresResearchArtifactStore(dsn=dsn, ensure_schema=False)
    try:
        replayed = data_ensure_loaded(
            event_store,
            request,
            policy=policy,
            artifact_store=third_store,
        )
    finally:
        third_store.close()
        event_store.close()

    assert interrupted.ok is False
    assert interrupted.errors[0]["code"] == "data_load_evidence_persistence_failed"
    assert recovered.ok is True
    assert recovered.data["load_result"]["status"] == ("recovered_after_interruption")
    assert recovered.data["load_result"]["idempotent_replay"] is False
    assert replayed.ok is True
    assert replayed.data["load_result"]["idempotent_replay"] is True
    assert provider_calls == [operation_id]


def _request(
    *,
    dry_run: bool = True,
    acquisition_plan_id: str | None = None,
    operation_id: str | None = None,
) -> DataEnsureLoadedRequest:
    """Build one exact bounded Data loading request."""
    return DataEnsureLoadedRequest(
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        start=datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
        end=datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
        mode="backfill",
        dry_run=dry_run,
        acquisition_plan_id=acquisition_plan_id,
        operation_id=operation_id,
        requested_by="agent-data-postgres-recovery",
        actor="Data Research Agent",
    )
