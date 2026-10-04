"""Contracts for the Console resource persistence adapter.

Subject: SQL selection and boundary normalization for published Console views.
Level: In-process repository adapter.
Collaborators: Recording asynchronous transaction/connection; no PostgreSQL server.
Guarantees: Stable views are selected, parameters carry caller values, and sections are bounded.
Non-goals: Query planning, producer migrations, and frontend rendering.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import asyncio

from trader_console_api.repositories.resources import ConsoleResourceRepository


class _Cursor:
    def __init__(self, names: list[str], rows: list[tuple[Any, ...]]) -> None:
        self.description = [SimpleNamespace(name=name) for name in names]
        self._rows = rows

    async def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []

    async def execute(self, query: str, parameters: object | None = None) -> _Cursor:
        self.calls.append((query, parameters))
        if "stock_bars" in query and "count(*) OVER" in query:
            return _Cursor(
                ["symbol", "timeframe", "ts", "open", "high", "low", "close", "volume", "total_count"],
                [("AAPL", "1Min", datetime(2026, 1, 1, tzinfo=timezone.utc), 1, 2, 0.5, 1.5, 100, 1)],
            )
        if "backtest_runs" in query and "scope_fingerprint" not in query:
            return _Cursor(
                ["experiment_id", "run_count", "latest_created_at", "statuses", "total_count"],
                [("exp-1", 2, None, ["completed"], 1)],
            )
        if "backtest_runs" in query:
            return _Cursor(
                ["experiment_run_id", "experiment_id", "run_id", "status", "scope_fingerprint", "comparison_projection_available", "comparison_eligible", "comparison_exclusion_reason", "total_count"],
                [("er-1", "exp-1", "run-1", "completed", "scope-a", True, True, None, 1)],
            )
        return _Cursor([], [])


class _Database:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    @asynccontextmanager
    async def transaction(self) -> Any:
        yield self.connection


class _DetailConnection(_Connection):
    async def execute(self, query: str, parameters: object | None = None) -> _Cursor:
        self.calls.append((query, parameters))
        if "FROM console_read.backtest_runs" in query:
            return _Cursor(
                ["experiment_run_id", "experiment_id", "run_id", "status", "comparison_projection_available", "comparison_eligible", "comparison_exclusion_reason"],
                [("er-1", "exp-1", "run-1", "failed", False, False, "no_comparison_projection")],
            )
        return _Cursor(["run_id"], [])


class _RiskDecisionConnection(_Connection):
    """Connection double for bounded and filtered risk trace reads."""

    async def execute(self, query: str, parameters: object | None = None) -> _Cursor:
        self.calls.append((query, parameters))
        if "SELECT run_id FROM console_read.backtest_runs" in query:
            return _Cursor(["run_id"], [("run-1",)])
        if "FROM console_read.risk_decisions" in query:
            return _Cursor(
                [
                    "risk_decision_id", "composition_fingerprint", "run_id", "session_id",
                    "cycle_id", "client_order_id", "decision_ts", "manager_id", "manager_type",
                    "manager_position", "outcome", "reason_code", "before_qty", "after_qty",
                    "before_order", "after_order", "total_count",
                ],
                [(
                    "riskdec-1", "fingerprint", "run-1", "session-1", "cycle-1", "order-1",
                    datetime(2026, 1, 1, tzinfo=timezone.utc), "max_orders_per_run",
                    "trader_standard.risk.MaxOrdersPerRunRiskManager", 0, "rejected", "limit_exceeded",
                    0.2, None, {"qty": 0.2}, None, 1,
                )],
            )
        return _Cursor([], [])


class _MissingRiskRunConnection(_Connection):
    """Connection double where the risk trace target run is absent."""

    async def execute(self, query: str, parameters: object | None = None) -> _Cursor:
        self.calls.append((query, parameters))
        if "SELECT run_id FROM console_read.backtest_runs" in query:
            return _Cursor(["run_id"], [])
        return _Cursor([], [])


def test_bars_use_allowlisted_relation_and_parameterized_filters() -> None:
    """Select the server-owned stock view without interpolating request values."""
    connection = _Connection()
    repository = ConsoleResourceRepository(_Database(connection))  # type: ignore[arg-type]

    rows, total = asyncio.run(
        repository.list_bars(
            asset_class="stock",
            symbol="AAPL' OR 1=1 --",
            timeframe="1Min",
            source=None,
            start=None,
            end=None,
            limit=10,
            offset=0,
        )
    )

    query, parameters = connection.calls[0]
    assert "console_read.stock_bars" in query
    assert "AAPL' OR 1=1 --" not in query
    assert parameters == ["AAPL' OR 1=1 --", "1Min", 10, 0]
    assert rows[0]["symbol"] == "AAPL"
    assert total == 1


def test_experiment_discovery_stays_on_published_run_projection() -> None:
    """Derive groups from backtest runs rather than bypassing the Console contract."""
    connection = _Connection()
    repository = ConsoleResourceRepository(_Database(connection))  # type: ignore[arg-type]

    rows, total = asyncio.run(repository.list_experiments(limit=10, offset=0))

    query, _parameters = connection.calls[0]
    assert "console_read.backtest_runs" in query
    assert "public.experiments" not in query
    assert rows == [{"experiment_id": "exp-1", "run_count": 2, "latest_created_at": None, "statuses": ["completed"]}]
    assert total == 1


def test_backtest_coverage_uses_allowlisted_bar_relation_and_returns_one_row_per_symbol() -> None:
    """Read only aggregate coverage evidence without loading market bars."""
    connection = _Connection()
    repository = ConsoleResourceRepository(_Database(connection))  # type: ignore[arg-type]

    rows = asyncio.run(
        repository.backtest_coverage(
            asset_class="stock",
            symbols=("AAPL", "MSFT"),
            timeframe="1Min",
        )
    )

    assert len(rows) == 2
    assert all("console_read.stock_bars" in query for query, _parameters in connection.calls)
    assert all(
        parameters == [symbol, "1Min"]
        for (_query, parameters), symbol in zip(connection.calls, ("AAPL", "MSFT"), strict=True)
    )


def test_run_discovery_returns_comparison_eligibility_as_a_run_property() -> None:
    """Expose scope compatibility without creating a separate comparison resource."""
    connection = _Connection()
    repository = ConsoleResourceRepository(_Database(connection))  # type: ignore[arg-type]

    rows, _total = asyncio.run(
        repository.list_experiment_runs(
            experiment_id="exp-1",
            compatible_with_run_id="run-0",
            limit=10,
            offset=0,
        )
    )

    query, parameters = connection.calls[0]
    assert "console_read.backtest_scope" in query
    assert parameters == ["run-0", "run-0", "run-0", "exp-1", 10, 0]
    assert rows[0]["comparison_eligible"] is True


def test_run_detail_bounds_each_evidence_section_and_keeps_empty_sections() -> None:
    """Load a failed run without dropping it and bound every detail projection."""
    connection = _DetailConnection()
    repository = ConsoleResourceRepository(_Database(connection))  # type: ignore[arg-type]

    detail = asyncio.run(repository.get_run_detail(run_id="run-1", section_limit=2))

    assert detail is not None
    assert detail["run"]["status"] == "failed"
    assert detail["run"]["comparison_exclusion_reason"] == "no_comparison_projection"
    assert detail["comparison_curves"] == []
    section_calls = [
        (query, parameters)
        for query, parameters in connection.calls
        if "FROM console_read.backtest_runs" not in query
    ]
    assert section_calls
    bounded_sections = [
        parameters for query, parameters in section_calls if "LIMIT %s" in query
    ]
    assert bounded_sections
    assert all(parameters[-1] == 2 for parameters in bounded_sections)
    assert all("LIMIT" in query for query, _parameters in section_calls)


def test_risk_decision_trace_is_filterable_and_bounded() -> None:
    """Risk trace reads keep manager filters in parameters and preserve a page count."""
    connection = _RiskDecisionConnection()
    repository = ConsoleResourceRepository(_Database(connection))  # type: ignore[arg-type]

    result = asyncio.run(
        repository.list_risk_decisions(
            run_id="run-1",
            manager_id="max_orders_per_run",
            outcome="rejected",
            cycle_id="cycle-1",
            client_order_id="order-1",
            limit=25,
            offset=50,
        )
    )

    assert result is not None
    rows, total = result
    assert total == 1
    assert rows[0]["reason_code"] == "limit_exceeded"
    query, parameters = connection.calls[1]
    assert "ORDER BY decisions.decision_ts" in query
    assert parameters == ["run-1", "max_orders_per_run", "rejected", "cycle-1", "order-1", 25, 50]


def test_risk_decision_trace_returns_none_for_unknown_run() -> None:
    """An unknown run remains distinguishable from a published run with no decisions."""
    connection = _MissingRiskRunConnection()
    repository = ConsoleResourceRepository(_Database(connection))  # type: ignore[arg-type]

    result = asyncio.run(
        repository.list_risk_decisions(
            run_id="missing",
            manager_id=None,
            outcome=None,
            cycle_id=None,
            client_order_id=None,
            limit=25,
            offset=0,
        )
    )

    assert result is None
