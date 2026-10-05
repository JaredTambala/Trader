"""Concrete adapter from frozen Console definitions to ``BacktestRunner``.

This module is intentionally separate from API startup. A local worker
composition can inject a configured core ``Config`` here; the HTTP process does
not load runtime configuration, construct brokers, or execute producer code.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from trader.backtest import BacktestResult, BacktestRunner, BacktestSpec
from trader.backtest.persistence import persist_backtest_result
from trader.backtest.models import (
    BacktestAssumptions as CoreBacktestAssumptions,
    DataAssumptions,
    FeeAssumptions,
    SlippageAssumptions,
)
from trader.config import Config
from trader.portfolio import Position
from trader.strategies import Strategy
from trader_standard.catalogue import Catalogue, maintained_catalogue

from .contracts import BacktestDefinition
from .worker import ExecutionOutcome, ProgressSink


@dataclass(frozen=True)
class BacktestDefinitionExecutor:
    """Resolve one immutable definition and run it through the core engine."""

    config: Config
    catalogue: Catalogue

    @classmethod
    def from_config(cls, config: Config) -> "BacktestDefinitionExecutor":
        """Bind the maintained catalogue to one worker-owned core config."""
        return cls(config=config, catalogue=maintained_catalogue())

    async def execute(
        self,
        definition: BacktestDefinition,
        *,
        run_id: str,
        progress: ProgressSink,
    ) -> ExecutionOutcome:
        """Execute the frozen definition in a worker thread with durable progress."""
        _require_allowlisted_lineage(definition)
        strategy = self.catalogue.build_strategy(
            definition.strategy_profile_id,
            version=definition.strategy_catalogue_version,
            parameters=definition.strategy_parameters,
            symbols=definition.symbols,
            asset_class=definition.asset_class,
            timeframe=definition.timeframe,
        )
        risk_manager = self.catalogue.build_risk_manager(
            definition.risk_profile_id,
            version=definition.risk_catalogue_version,
            parameters=definition.risk_parameters,
        )
        assumptions = _core_assumptions(definition)
        positions = tuple(
            Position(position.symbol, position.qty, position.avg_price)
            for position in definition.initial_positions
        )
        loop = asyncio.get_running_loop()

        def emit_progress(processed: int, total: int, last_ts: datetime | None) -> None:
            """Bridge the synchronous runner callback to the async worker sink."""
            async def notify() -> None:
                await progress(processed, total, last_ts)

            future: Future[None] = asyncio.run_coroutine_threadsafe(notify(), loop)
            future.result()

        runner = BacktestRunner(
            config=self.config,
            spec=BacktestSpec(
                start=definition.start,
                end=definition.end,
                timeframe=definition.timeframe,
                max_runs=definition.resource_limits.max_cycles,
            ),
            strategy=cast(Strategy, strategy),
            risk_manager=risk_manager,
            symbols=definition.symbols,
            asset_class=definition.asset_class,
            initial_positions=positions,
            initial_cash=definition.initial_cash,
            assumptions=assumptions,
            run_id=run_id,
            config_snapshot=_canonical_config_snapshot(definition, self.config),
        )
        result = await asyncio.to_thread(runner.run, progress_callback=emit_progress)
        _persist_result_for_durable_store(self.config, run_id=run_id, result=result)
        status: Literal["partial", "completed"] = (
            "partial" if result.failed_runs else "completed"
        )
        return ExecutionOutcome(
            status=status,
            processed_cycles=result.total_runs,
            total_cycles=result.total_runs,
            warnings=result.warnings,
        )


def _require_allowlisted_lineage(definition: BacktestDefinition) -> None:
    """Fail closed if a worker receives a definition outside preflight."""
    strategy_lineage = definition.strategy_implementation_lineage
    if (
        strategy_lineage.profile_id != definition.strategy_profile_id
        or strategy_lineage.implementation_kind != "strategy"
        or strategy_lineage.validation_report.status != "passed"
    ):
        raise ValueError("strategy implementation lineage is not an admitted allowlisted record")
    risk_lineage = definition.risk_implementation_lineage
    if (
        risk_lineage.profile_id != definition.risk_profile_id
        or risk_lineage.implementation_kind != "risk_manager"
        or risk_lineage.validation_report.status != "passed"
    ):
        raise ValueError("risk implementation lineage is not an admitted allowlisted record")


def _core_assumptions(definition: BacktestDefinition) -> CoreBacktestAssumptions:
    """Map the API's frozen assumptions contract to core value objects."""
    assumptions = definition.assumptions
    return CoreBacktestAssumptions(
        fill_model=assumptions.fill_model,
        latency_ms=float(assumptions.latency_ms),
        fees=FeeAssumptions(
            fixed_per_order=assumptions.fee_fixed_per_order,
            bps=assumptions.fee_bps,
            minimum_fee=assumptions.fee_minimum,
        ),
        slippage=SlippageAssumptions(bps=assumptions.slippage_bps),
        data=DataAssumptions(
            allow_latest_prior_bar=assumptions.allow_latest_prior_bar,
            allow_price_carry_forward=assumptions.allow_price_carry_forward,
        ),
    )


def _canonical_config_snapshot(definition: BacktestDefinition, config: Config) -> dict[str, object]:
    """Build the producer config shape consumed by runtime evidence views.

    Console definitions are immutable API contracts, while the core event
    store expects the same nested ``strategy``, ``market_data``, ``logging``
    and ``backtest`` paths used by normal runtime configuration.  Keeping this
    translation at the worker boundary gives standalone runs one canonical
    snapshot without asking the read contract to understand Console payloads.
    """
    scope = definition.data_scope.model_dump(mode="json")
    assumptions = definition.assumptions.model_dump(mode="json")
    initial_positions = [position.model_dump(mode="json") for position in definition.initial_positions]
    return {
        "strategy": {
            "id": definition.strategy_profile_id,
            "version": definition.strategy_catalogue_version,
            "parameters": definition.strategy_parameters,
        },
        "risk": {
            "id": definition.risk_profile_id,
            "version": definition.risk_catalogue_version,
            "parameters": definition.risk_parameters,
        },
        "market_data": {
            "asset_class": definition.asset_class,
            "symbols": list(definition.symbols),
            "timeframe": definition.timeframe,
            "source": definition.data_scope.source_policy.source
            or definition.data_scope.source_policy.provider,
            "provider": definition.data_scope.source_policy.provider,
            "source_policy": scope["source_policy"],
        },
        "logging": {
            "persist": {
                "signals": bool(getattr(config, "log_signal_events", True)),
                "indicators": bool(getattr(config, "log_indicator_events", True)),
                "orders": bool(getattr(config, "log_order_events", True)),
                "fills": bool(getattr(config, "log_fill_events", True)),
                "positions": bool(getattr(config, "log_position_snapshots", True)),
            }
        },
        "backtest": {
            "asset_class": definition.asset_class,
            "symbols": list(definition.symbols),
            "timeframe": definition.timeframe,
            "start": definition.start.isoformat(),
            "end": definition.end.isoformat(),
            "initial_cash": definition.initial_cash,
            "initial_positions": initial_positions,
            "assumptions": assumptions,
            "benchmark_id": definition.benchmark_id,
            "benchmark": {
                "id": definition.benchmark_id,
                "method": "buy_and_hold" if definition.benchmark_id == "buy_hold" else "none",
                "allocation": "equal_weight" if definition.benchmark_id == "buy_hold" else "none",
            },
            "data_scope": scope,
            "resource_limits": definition.resource_limits.model_dump(mode="json"),
        },
    }


def _persist_result_for_durable_store(
    config: object,
    *,
    run_id: str,
    result: BacktestResult,
) -> None:
    """Persist a typed result only when the worker uses PostgreSQL.

    Unit and adapter tests inject lightweight config/runner fakes.  Checking the
    explicit backend setting keeps those tests side-effect free while ensuring a
    real Console worker leaves one durable metrics snapshot after completion.
    """
    if str(getattr(config, "event_store", "")).strip().lower() != "postgres":
        return
    persist_backtest_result(run_id, result, cast(Config, config))


__all__ = ["BacktestDefinitionExecutor"]
