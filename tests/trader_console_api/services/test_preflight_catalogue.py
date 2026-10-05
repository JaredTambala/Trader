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
from uuid import uuid4

from trader_console_api.contracts import BacktestPreflightRequest
from trader_console_api.data_scope_contracts import BacktestDataScopeHandoff, DataScopeEvidenceStatus, DataScopeSourcePolicy, SavedDataScope
from trader_console_api.services.catalogue import PreflightService
from trader_standard.catalogue import maintained_catalogue
from tests.trader_console_api.support import implementation_lineage


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
        "strategy_implementation_lineage": implementation_lineage("bollinger_band"),
        "risk_profile_id": "max_orders_per_run",
        "risk_parameters": {"limit": 10},
        "risk_implementation_lineage": implementation_lineage(
            "max_orders_per_run", kind="risk", suffix="max-orders"
        ),
        "asset_class": "crypto",
        "symbols": (" btc/usd ",),
        "timeframe": "1m",
        "start": datetime(2026, 1, 2, tzinfo=UTC),
        "end": datetime(2026, 1, 2, 1, tzinfo=UTC),
        "data_scope": BacktestDataScopeHandoff(
            saved_scope_id=uuid4(), fingerprint="a" * 64, asset_class="crypto",
            symbols=("BTC/USD",), timeframe="1Min", interval="1Min",
            start=datetime(2026, 1, 2, tzinfo=UTC), end=datetime(2026, 1, 2, 1, tzinfo=UTC),
            source_policy=DataScopeSourcePolicy(provider="fixture", source="fixture"),
            manifest_artifact_id="manifest-1", quality_artifact_id="quality-1",
            evidence_status=DataScopeEvidenceStatus.ACTIVE,
        ),
    }
    values.update(overrides)
    return BacktestPreflightRequest.model_validate(values)


class _SavedScopeLookup:
    """Persisted scope fixture used to prove server-owned handoff resolution."""

    async def get(self, saved_scope_id):
        """Return the canonical crypto fixture regardless of request identity."""
        request = _request()
        return SavedDataScope(
            saved_scope_id=saved_scope_id,
            scope_id="console-local",
            fingerprint=request.data_scope.fingerprint,
            name="Fixture scope",
            asset_class="crypto",
            symbols=("BTC/USD",),
            universe=None,
            timeframe="1Min",
            interval="1Min",
            start=request.data_scope.start,
            end=request.data_scope.end,
            source_policy=request.data_scope.source_policy,
            research_role="backtest_authoring",
            manifest_artifact_id="manifest-1",
            quality_artifact_id="quality-1",
            evidence_status=DataScopeEvidenceStatus.ACTIVE,
            evidence_reason=None,
            created_by="fixture",
            idempotency_key="fixture",
            created_at=request.data_scope.start,
            updated_at=request.data_scope.start,
        )


def _service(repository: _CoverageRepository) -> PreflightService:
    """Compose preflight with the mandatory server-owned scope lookup."""
    return PreflightService(repository, maintained_catalogue(), _SavedScopeLookup())


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
    result = asyncio.run(_service(repository).preflight(_request()))

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
        _service(repository).preflight(
            _request(strategy_parameters={"period": 9999})
        )
    )

    assert result.valid is False
    assert {issue.code for issue in result.issues} == {"invalid_strategy_parameters"}
    assert repository.calls == []

    coverage_result = asyncio.run(
        _service(repository).preflight(_request())
    )
    assert coverage_result.valid is False
    assert {issue.code for issue in coverage_result.issues} >= {
        "data_coverage_incomplete", "warmup_unavailable"
    }


def test_preflight_rejects_unknown_profile_before_coverage_lookup() -> None:
    """Reject arbitrary strategy identities without importing or querying their implementation."""
    repository = _CoverageRepository([])
    result = asyncio.run(
        _service(repository).preflight(
            _request(strategy_profile_id="python:arbitrary.Class")
        )
    )

    assert result.valid is False
    assert any(issue.code == "unsupported_strategy_profile" for issue in result.issues)
    assert repository.calls == []


def test_preflight_requires_both_admitted_lineages() -> None:
    """A catalogue profile alone cannot become an executable Console definition."""
    repository = _CoverageRepository([])
    result = asyncio.run(
        _service(repository).preflight(
            _request(strategy_implementation_lineage=None, risk_implementation_lineage=None)
        )
    )

    assert result.valid is False
    assert {issue.code for issue in result.issues} >= {"implementation_lineage_missing"}
    assert repository.calls == []


def test_preflight_preserves_blocked_validation_report_as_actionable_issue() -> None:
    """Blocked admission evidence is surfaced before coverage access or persistence."""
    repository = _CoverageRepository([])
    result = asyncio.run(
        _service(repository).preflight(
            _request(
                strategy_implementation_lineage=implementation_lineage(
                    "bollinger_band", blockers=("fixture failed",), status="blocked"
                )
            )
        )
    )

    assert result.valid is False
    issue = next(issue for issue in result.issues if issue.code == "implementation_validation_blocked")
    assert "fixture failed" in issue.message
    assert repository.calls == []


def test_preflight_rejects_resolver_source_hash_drift() -> None:
    """A research resolver can fail closed when the admitted record has changed."""
    class _DriftResolver:
        def resolve(self, lineage, *, profile_id, expected_kind):
            return lineage.model_copy(update={"source_hash": "c" * 64})

    repository = _CoverageRepository([])
    result = asyncio.run(
        PreflightService(
            repository,
            maintained_catalogue(),
            lineage_resolver=_DriftResolver(),
            saved_scope_lookup=_SavedScopeLookup(),
        ).preflight(_request())
    )

    assert result.valid is False
    assert any(issue.code == "implementation_lineage_drifted" for issue in result.issues)
    assert repository.calls == []


def test_preflight_blocks_stale_scope_before_coverage_lookup() -> None:
    """Stale selected evidence is an actionable blocker and cannot be widened."""
    repository = _CoverageRepository([])
    request = _request(
        data_scope=_request().data_scope.model_copy(
            update={"evidence_status": DataScopeEvidenceStatus.STALE, "evidence_reason": "Quality report expired."}
        )
    )
    result = asyncio.run(_service(repository).preflight(request))

    assert result.valid is False
    assert any(issue.code == "data_scope_stale" for issue in result.issues)
    assert repository.calls == []


def test_preflight_rejects_client_scope_drift_against_persisted_evidence() -> None:
    """A changed manifest or scope fingerprint cannot be replaced by aggregate coverage."""
    request = _request()

    class _Lookup:
        async def get(self, _saved_scope_id):
            return SavedDataScope(
                saved_scope_id=request.data_scope.saved_scope_id,
                scope_id="console-local",
                fingerprint="b" * 64,
                name="Persisted scope",
                asset_class=request.data_scope.asset_class,
                symbols=request.data_scope.symbols,
                universe=request.data_scope.universe,
                timeframe=request.data_scope.timeframe,
                interval=request.data_scope.interval,
                start=request.data_scope.start,
                end=request.data_scope.end,
                source_policy=request.data_scope.source_policy,
                research_role="backtest_authoring",
                manifest_artifact_id="manifest-persisted",
                quality_artifact_id=request.data_scope.quality_artifact_id,
                evidence_status=DataScopeEvidenceStatus.ACTIVE,
                evidence_reason=None,
                created_by="fixture",
                idempotency_key="fixture",
                created_at=request.data_scope.start,
                updated_at=request.data_scope.start,
            )

    repository = _CoverageRepository([])
    result = asyncio.run(PreflightService(repository, maintained_catalogue(), saved_scope_lookup=_Lookup()).preflight(request))

    assert result.valid is False
    assert any(issue.code == "data_scope_mismatch" for issue in result.issues)
    assert repository.calls == []
