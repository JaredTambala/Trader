"""Console catalogue and preflight service contracts.

Subject: Typed profile discovery, normalization, fingerprinting, and read-only coverage preflight.
Level: Application-service unit tests.
Collaborators: Maintained catalogue and an in-memory coverage repository double.
Guarantees: Valid drafts normalize deterministically, coverage gaps are actionable, and invalid profiles never query data.
Non-goals: Console-owned definition persistence, command execution, worker leases, or PostgreSQL SQL syntax.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from trader_console_api.contracts import BacktestPreflightRequest
from trader_console_api.services.catalogue import PreflightService
from trader_standard.catalogue import maintained_catalogue


class _CoverageRepository:
    """In-memory coverage adapter for preflight service tests."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    async def backtest_coverage(self, **kwargs: object) -> list[dict[str, object]]:
        """Return configured coverage rows and record the bounded query."""
        self.calls.append(kwargs)
        return self.rows


def _request(**overrides: object) -> BacktestPreflightRequest:
    """Build one valid typed draft for service-level scenarios."""
    values: dict[str, object] = {
        "display_name": "Bollinger smoke",
        "strategy_profile_id": "bollinger_band",
        "strategy_parameters": {"period": 20, "stddev_multiplier": 2, "target_qty_when_long": 0.01},
        "risk_profile_id": "max_orders_per_run",
        "risk_parameters": {"limit": 10},
        "asset_class": "crypto",
        "symbols": (" btc/usd ",),
        "timeframe": "1m",
        "start": datetime(2026, 1, 2, tzinfo=UTC),
        "end": datetime(2026, 1, 2, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return BacktestPreflightRequest.model_validate(values)


def test_preflight_normalizes_valid_definition_and_returns_fingerprint() -> None:
    """Return canonical profile values and coverage evidence for an executable draft."""
    repository = _CoverageRepository(
        [{
            "symbol": "BTC/USD",
            "asset_class": "crypto",
            "timeframe": "1Min",
            "first_ts": datetime(2026, 1, 1, 23, 39, tzinfo=UTC),
            "last_ts": datetime(2026, 1, 2, 1, tzinfo=UTC),
            "bar_count": 82,
        }]
    )
    result = asyncio.run(PreflightService(repository, maintained_catalogue()).preflight(_request()))

    assert result.valid is True
    assert result.definition_fingerprint is not None
    assert result.normalized_definition is not None
    assert result.normalized_definition.symbols == ("BTC/USD",)
    assert result.normalized_definition.timeframe == "1Min"
    assert result.normalized_definition.strategy_parameters["period"] == 20
    assert result.coverage[0].warmup_bars == 21
    assert any(issue.code == "price_carry_forward_enabled" for issue in result.issues)
    assert repository.calls[0]["timeframe"] == "1Min"


def test_preflight_reports_coverage_and_parameter_failures_without_writes() -> None:
    """Keep data gaps and unsafe profile values explicit before queue or producer writes."""
    repository = _CoverageRepository(
        [{
            "symbol": "BTC/USD",
            "asset_class": "crypto",
            "timeframe": "1Min",
            "first_ts": datetime(2026, 1, 2, tzinfo=UTC),
            "last_ts": datetime(2026, 1, 2, 0, 30, tzinfo=UTC),
            "bar_count": 31,
        }]
    )
    result = asyncio.run(
        PreflightService(repository, maintained_catalogue()).preflight(
            _request(strategy_parameters={"period": 9999})
        )
    )

    assert result.valid is False
    assert {issue.code for issue in result.issues} == {"invalid_strategy_parameters"}
    assert repository.calls == []

    coverage_result = asyncio.run(
        PreflightService(repository, maintained_catalogue()).preflight(_request())
    )
    assert coverage_result.valid is False
    assert {issue.code for issue in coverage_result.issues} >= {
        "data_coverage_incomplete", "warmup_unavailable"
    }


def test_preflight_rejects_unknown_profile_before_coverage_lookup() -> None:
    """Reject arbitrary strategy identities without importing or querying their implementation."""
    repository = _CoverageRepository([])
    result = asyncio.run(
        PreflightService(repository, maintained_catalogue()).preflight(
            _request(strategy_profile_id="python:arbitrary.Class")
        )
    )

    assert result.valid is False
    assert any(issue.code == "unsupported_strategy_profile" for issue in result.issues)
    assert repository.calls == []
