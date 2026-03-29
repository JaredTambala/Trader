"""Direct-injection demo of an external Strategy implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

from trader.config import build_config, load_yaml_config
from trader.cycle import run_cycle
from trader.data import NoOpEventStore
from trader.market_data import StaticMarketDataSource, StockBarEvent
from trader.portfolio import Portfolio
from trader.risk import ConfigRiskManager, NoOpRiskManager, RiskManager, RiskPipeline
from trader.strategies.base import Strategy


class ExternalDemoStrategy(Strategy):
    """Minimal external strategy that always emits one buy order."""

    def __init__(self, symbol: str = "AAPL", qty: float = 1.0) -> None:
        self._symbol = symbol
        self._qty = qty

    @property
    def strategy_id(self) -> str:
        return "external_demo"

    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store,
        portfolio: Portfolio,
    ) -> Sequence[Mapping[str, object]]:
        return [
            {
                "symbol": self._symbol,
                "side": "buy",
                "qty": self._qty,
                "order_type": "market",
            }
        ]


def _build_demo_risk_manager(config) -> RiskManager:
    """Build a simple injected risk pipeline for the demo."""
    managers: list[RiskManager] = []
    if any(
        limit is not None
        for limit in (
            config.risk_max_orders_per_run,
            config.risk_max_gross_usd,
            config.risk_max_pos_usd_per_symbol,
        )
    ):
        managers.append(
            ConfigRiskManager(
                max_orders_per_run=config.risk_max_orders_per_run,
                max_gross_usd=config.risk_max_gross_usd,
                max_pos_usd_per_symbol=config.risk_max_pos_usd_per_symbol,
            )
        )
    if not managers:
        return NoOpRiskManager()
    return RiskPipeline(managers)


def main() -> None:
    now = datetime.now(timezone.utc)
    config_data = load_yaml_config("configs/external_strategy_demo.yaml")
    config = build_config(config_data)

    strategy = ExternalDemoStrategy(symbol="AAPL", qty=1.0)
    risk_manager = _build_demo_risk_manager(config)

    bar = StockBarEvent(
        symbol="AAPL",
        timeframe="1Min",
        ts=now,
        ingested_at=now,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
        trade_count=None,
        vwap=None,
        source="demo",
    )

    result = run_cycle(
        event_store=NoOpEventStore(),
        config=config,
        market_data_source=StaticMarketDataSource([bar]),
        ingest_market_data=False,
        decision_ts=now,
        portfolio=Portfolio.empty(cash_balance=1000.0),
        strategy=strategy,
        risk_manager=risk_manager,
    )
    print("Cycle result:", result)


if __name__ == "__main__":
    main()
