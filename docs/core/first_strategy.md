# First Strategy Research Workflow

This tutorial runs a small repeatable research loop without the UI or a live broker. It uses the checked-in synthetic
`DEMO` data, a maintained `trader_standard` strategy, Postgres audit tables, and local JSON/CSV artifacts.

## Mental Model

The engine is split into operational components:

- Market data writes bars into Postgres.
- Indicator code computes derived values from bar windows.
- Indicator observations can be audited independently, including structured model outputs.
- Signal code converts indicators and bars into scalar decision values.
- Strategy code reads market context, evaluates signals, and emits candidate orders.
- Risk code approves or rejects those orders.
- The backtest broker simulates deterministic fills with configured cost assumptions.
- The portfolio applies fills to cash and positions.
- The event store persists runs, cycles, orders, fills, positions, metrics, experiments, and provenance.
- Result exports turn the run into files that can be compared or inspected by tools.

## 1. Start Postgres

```bash
docker compose -f docker-compose.postgres.yml up -d
```

Postgres is the runtime source of truth. DuckDB support remains for tests and local support utilities only.

## 2. Load Sample Data

```bash
uv run python examples/load_sample_market_data.py
```

The loader reads `examples/data/demo_stock_1min.csv` and writes idempotent `DEMO` stock bars with:

```text
symbol,asset_class,timeframe,ts,open,high,low,close,volume,trade_count,vwap,source
```

Running the loader multiple times should not duplicate bars because market-data tables are unique on
`(symbol, timeframe, ts, source)`.

## 3. Run One Canonical Research Backtest

Register and validate the strategy implementation, create and validate its immutable strategy and backtest
specifications, then call the backtest MCP tool. The run is stored in Postgres as canonical `backtest_run` evidence.
See [Research Agent Workflows](../research_agents/workflows.md) for the exact implementation-to-evidence graph.

## 4. Compare Results

Use the MCP comparison and optimization result tools over explicit `research://postgres/...` refs. Comparisons preserve
scope and assumption warnings; parameter searches preserve every trial and selected-specification lineage.

## 5. Try A Tiny Custom Wrapper

Custom indicators, signals, and strategies stay in explicit Python wrappers. That keeps code ownership clear and avoids
a general dynamic code loader.

```python
from pathlib import Path
from datetime import datetime
from typing import Mapping, Sequence

from trader.backtest import BacktestRunner
from trader.config import build_config, load_yaml_config
from trader.event_store import EventStore
from trader.indicators import Indicator
from trader.portfolio import Portfolio
from trader.risk import RiskPipeline
from trader.signals import Bar, Signal
from trader.strategies import Strategy
from trader_standard.bar_signals import fetch_recent_bars, table_for_asset_class


class OneBarMomentumIndicator(Indicator):
    @property
    def name(self) -> str:
        return "one_bar_momentum"

    @property
    def window(self) -> int:
        return 2

    def compute_series(self, bars: Sequence[Bar]) -> Sequence[float]:
        return [bars[0].close - bars[1].close]


class MomentumSignal(Signal):
    def __init__(self) -> None:
        self._indicator = OneBarMomentumIndicator()

    @property
    def name(self) -> str:
        return "momentum_positive"

    @property
    def window(self) -> int:
        return self._indicator.window

    def compute(self, bars: Sequence[Bar]) -> float:
        return 1.0 if self._indicator.compute_series(bars)[0] > 0 else 0.0


class BuyOneDemoStrategy(Strategy):
    def __init__(self) -> None:
        self._signal = MomentumSignal()

    @property
    def strategy_id(self) -> str:
        return "custom_buy_one_demo"

    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> Sequence[Mapping[str, object]]:
        if portfolio.positions.get("DEMO") is not None:
            return []
        bars = fetch_recent_bars(
            event_store,
            table=table_for_asset_class("stocks"),
            symbol="DEMO",
            timeframe="1Min",
            limit=self._signal.window,
            as_of_ts=decision_ts,
        )
        if len(bars) < self._signal.window or self._signal.compute(bars) <= 0:
            return []
        return [{"symbol": "DEMO", "side": "buy", "qty": 1.0, "order_type": "market"}]


config_data = load_yaml_config(Path("configs/reproducible_backtest.yaml"))
config = build_config(config_data)

runner = BacktestRunner(
    config=config,
    strategy=BuyOneDemoStrategy(),
    risk_manager=RiskPipeline([]),
    config_snapshot=config_data,
)
result = runner.run()
print(result.run_id, result.metrics.total_return)
```

Use this pattern for custom indicator, signal, or strategy experiments when the standard research CLI is too narrow.
The current research CLI does not instantiate arbitrary custom indicators from YAML; Python wrappers are the supported
extension path. When indicator persistence is enabled, scalar indicator observations are written to
`indicator_events.value` and structured observations are written to `indicator_events.payload`.

## Modeling Limits

- Backtests use bar data, not tick data or exchange order books.
- Slippage and fees are deterministic assumptions, not venue microstructure simulation.
- The benchmark is frictionless in this phase.
- Research runs do not call Alpaca and do not prove live fill quality.
- Data quality checks report gaps and coverage, but they do not yet enforce a hard gate before every experiment.
