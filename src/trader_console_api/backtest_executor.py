"""Concrete adapter from frozen Console definitions to ``BacktestRunner``.

This module is intentionally separate from API startup. A local worker
composition can inject a configured core ``Config`` here; the HTTP process does
not load runtime configuration, construct brokers, or execute producer code.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from trader.backtest import BacktestRunner, BacktestSpec
from trader.backtest.models import (
    BacktestAssumptions as CoreBacktestAssumptions,
    DataAssumptions,
    FeeAssumptions,
    SlippageAssumptions,
)
from trader.config import Config
from trader.portfolio import Position
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
            future = asyncio.run_coroutine_threadsafe(
                progress(processed, total, last_ts), loop
            )
            future.result()

        runner = BacktestRunner(
            config=self.config,
            spec=BacktestSpec(
                start=definition.start,
                end=definition.end,
                timeframe=definition.timeframe,
                max_runs=definition.resource_limits.max_cycles,
            ),
            strategy=strategy,
            risk_manager=risk_manager,
            symbols=definition.symbols,
            asset_class=definition.asset_class,
            initial_positions=positions,
            initial_cash=definition.initial_cash,
            assumptions=assumptions,
            run_id=run_id,
            config_snapshot={"console_definition": definition.model_dump(mode="json")},
        )
        result = await asyncio.to_thread(runner.run, progress_callback=emit_progress)
        status = "partial" if result.failed_runs else "completed"
        return ExecutionOutcome(
            status=status,
            processed_cycles=result.total_runs,
            total_cycles=result.total_runs,
            warnings=result.warnings,
        )


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


__all__ = ["BacktestDefinitionExecutor"]
