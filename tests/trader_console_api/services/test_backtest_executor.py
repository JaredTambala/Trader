"""Concrete worker adapter contracts for the canonical backtest runner.

Subject: Frozen definition resolution, assumption mapping, run identity, and async progress bridging.
Level: Adapter unit tests.
Collaborators: Maintained catalogue and a fake BacktestRunner; no database or broker.
Guarantees: The adapter resolves allowlisted strategy/risk objects, preserves assumptions, and maps runner output without fake success.
Non-goals: Core replay behavior, PostgreSQL evidence persistence, and worker lease transitions.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from trader_console_api.backtest_executor import BacktestDefinitionExecutor, _core_assumptions
from trader_console_api.contracts import BacktestDefinition
from trader_console_api.data_scope_contracts import BacktestDataScopeHandoff, DataScopeEvidenceStatus, DataScopeSourcePolicy
from trader_standard.catalogue import maintained_catalogue
from tests.trader_console_api.support import implementation_lineage


def _definition() -> BacktestDefinition:
    """Build one frozen no-op definition with non-default assumptions."""
    return BacktestDefinition(
        display_name="Adapter smoke",
        strategy_profile_id="noop",
        strategy_catalogue_version="standard-1",
        strategy_implementation_lineage=implementation_lineage(),
        risk_profile_id="noop",
        risk_catalogue_version="standard-1",
        risk_implementation_lineage=implementation_lineage(kind="risk", suffix="risk"),
        asset_class="stock",
        symbols=("AAPL",),
        timeframe="1Min",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 1, 1, tzinfo=UTC),
        initial_cash=100_000,
        data_scope=BacktestDataScopeHandoff(
            saved_scope_id="00000000-0000-0000-0000-000000000001", fingerprint="a" * 64,
            asset_class="stock", symbols=("AAPL",), timeframe="1Min", interval="1Min",
            start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 1, 1, tzinfo=UTC),
            source_policy=DataScopeSourcePolicy(provider="fixture", source="fixture"),
            manifest_artifact_id="manifest-1", quality_artifact_id="quality-1",
            evidence_status=DataScopeEvidenceStatus.ACTIVE,
        ),
    )


def test_assumptions_map_to_core_value_objects() -> None:
    """Typed Console assumptions become the exact core fee, slippage and data objects."""
    assumptions = _core_assumptions(_definition())
    assert assumptions.fill_model == "full_fill"
    assert assumptions.fees.bps == 0.0
    assert assumptions.data.allow_price_carry_forward is True


def test_adapter_resolves_catalogue_and_bridges_runner_progress(monkeypatch) -> None:
    """The injected runner receives typed dependencies and its progress reaches the async sink."""
    calls: dict[str, object] = {}

    class _Runner:
        def __init__(self, **kwargs):
            calls.update(kwargs)

        def run(self, *, progress_callback):
            progress_callback(1, 2, datetime(2026, 1, 1, tzinfo=UTC))
            return SimpleNamespace(total_runs=2, failed_runs=0, warnings=("demo",))

    monkeypatch.setattr("trader_console_api.backtest_executor.BacktestRunner", _Runner)
    seen: list[tuple[int, int | None]] = []

    async def progress(processed, total, last_ts):
        seen.append((processed, total))

    executor = BacktestDefinitionExecutor(config=object(), catalogue=maintained_catalogue())  # type: ignore[arg-type]
    outcome = asyncio.run(executor.execute(_definition(), run_id="run-a", progress=progress))

    assert outcome.status == "completed"
    assert outcome.processed_cycles == 2
    assert outcome.warnings == ("demo",)
    assert seen == [(1, 2)]
    assert calls["run_id"] == "run-a"
    assert calls["strategy"].__class__.__name__ == "NoOpStrategy"
    assert calls["risk_manager"].__class__.__name__ == "NoOpRiskManager"
