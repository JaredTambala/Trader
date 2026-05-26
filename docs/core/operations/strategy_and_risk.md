# Strategy and Risk Component

The strategy and risk component turns market context into candidate orders and then decides which candidate orders are
allowed to reach the broker.

## Component responsibilities

- Keep strategy authoring as normal Python code.
- Keep indicator and signal authoring as normal Python code.
- Reuse strategy and risk objects across cycles.
- Compose indicators into signals, and signals into strategies.
- Generate candidate order intents from market data and portfolio context.
- Apply risk checks before any broker side effect.
- Persist accepted and rejected decision records.
- Keep strategy-specific configuration outside the core loader.
- Expose strategy metadata for research provenance when available.

## Backtest operation

Backtest wrappers construct strategy and risk objects directly:

```bash
uv run python examples/run_injected_backtest.py
uv run python examples/run_library_backtest.py
```

The maintained `trader_standard` package provides reusable indicators, signals, strategies, and risk managers. The
library wrappers show how to construct those objects from passive YAML values.
Standard strategies expose `StrategyInfo` metadata where practical. Custom strategies remain compatible without it;
the provenance helper falls back to `strategy.strategy_id`, class name, and provided parameter snapshots.

Indicator and signal ownership follows the same rule as strategy ownership: users can define their own Python classes
and inject composed strategy objects through a wrapper. The runtime does not discover custom indicators from YAML and
does not maintain a global indicator registry.

Backtest flow:

1. The wrapper builds indicators, signals, strategy, and risk manager.
2. `BacktestRunner` reuses those objects for every timestamp.
3. `run_cycle` supplies the in-memory market context.
4. Strategy evaluates its signals and emits candidate orders.
5. Risk filters candidate orders.
6. Rejected orders are persisted with rejection reasons.
7. Approved orders go to the deterministic internal broker.

This path keeps backtest and live strategy semantics close because both use `run_cycle`. A backtest can therefore show
which signals were generated, which risk checks rejected orders, and which approved orders would have reached the
execution layer under the configured assumptions.

## Live operation

Live wrappers construct strategy and risk objects before starting `TraderService`:

```bash
uv run python examples/run_injected_trader_service.py
uv run python examples/run_library_trader_service.py
```

Live flow:

1. `TraderService` keeps the injected strategy and risk objects for the service lifetime.
2. Every cycle receives broker-backed or locally loaded portfolio context.
3. Strategy evaluates its indicators/signals and emits candidate orders from fresh market context.
4. `RiskPipeline` evaluates orders with `RiskContext`.
5. Rejected orders are recorded locally and never reach the broker.
6. Approved orders are submitted through the broker component.

Risk context includes current positions, open orders, prices, run/cycle identity, decision timestamp, and halt state.
Rejected live orders are local facts: they are written to `order_events` and never submitted to the broker. This makes
the risk layer reviewable without requiring broker-side evidence for orders that were intentionally blocked.

## Configurability

Strategy metadata and passive parameters live in YAML:

```yaml
strategy:
  id: trend_following
  timeframe: 1Min
  trend_following:
    target_qty_when_long: 1.0
    ema_fast_period: 12
    ema_slow_period: 26
```

Standard-library indicators and signals are also configured indirectly by the wrapper. In the maintained
`trend_following` example, YAML values such as `ema_fast_period` and `ema_slow_period` are passive inputs to
`examples/strategy_library_support.py`, which constructs `EmaIndicator`, `MacdIndicator`, signal objects, and then a
`LongFlatSignalStrategy`.

Custom scalar indicators should implement `trader.indicators.Indicator`:

```python
from dataclasses import dataclass
from typing import Sequence

from trader.indicators import Indicator
from trader.signals import Bar


@dataclass(frozen=True)
class CloseRangeIndicator(Indicator):
    period: int

    @property
    def name(self) -> str:
        return "close_range"

    @property
    def window(self) -> int:
        return self.period

    def compute_series(self, bars: Sequence[Bar]) -> Sequence[float]:
        values: list[float] = []
        for idx in range(0, len(bars) - self.period + 1):
            window = bars[idx : idx + self.period]
            closes = [bar.close for bar in window]
            values.append(max(closes) - min(closes))
        return values
```

Richer indicators can also follow the same local pattern with `window` and `compute_series(...)` returning structured
values, as the standard MACD and Bollinger Band helpers do. `Indicator.compute(...)` returns an
`IndicatorObservation`, which carries a scalar `value` when possible plus a structured JSON payload for richer outputs.
That is the bridge for research code such as a PyTorch classifier: the model output can be recorded as its own
observable indicator fact, with model version, probabilities, features hash, or retraining metadata in the payload.

An indicator becomes actionable when a signal or strategy uses it. For the generic policy-driven strategy, wrap the
indicator in a `trader.signals.Signal` and pass that signal into `LongFlatSignalStrategy`. The signal's optional
`indicator_values(...)` method is what writes derived indicator telemetry into `indicator_events` when indicator
persistence is enabled. `indicator_events.value` stores the scalar path; `indicator_events.payload` stores structured
observations for audit, diagnostics, and future retraining workflows.

Risk parameters can also live in YAML:

```yaml
risk:
  max_orders_per_run: 10
  max_gross_usd: 250000
  max_pos_usd_per_symbol: 100000
  max_open_buy_orders_per_symbol: 1
  halted: false
```

The core runtime does not instantiate strategy, signal, or indicator classes from YAML. Wrapper code interprets these
sections and constructs objects. This keeps research code ownership explicit and avoids dynamic loading complexity in
the core engine. The research CLI intentionally supports only the maintained `trader_standard` path from YAML. Custom
indicator, signal, or strategy research should use an explicit wrapper so the source and construction logic stay
reviewable Python code.

Persistence flags:

```yaml
logging:
  persist:
    signals: true
    indicators: true
    orders: true
```

Even when signal or indicator persistence is disabled, order lifecycle and run/cycle records remain the core audit
surface for decisions that reached the order layer.

Strategy and risk objects are reused instead of rebuilt every cycle. Multiple risk managers can be composed through
`RiskPipeline`, and user-authored strategies can live outside the package. This is enough for local strategy research
and paper trading, but it is still an in-process execution model.

## Current limits

- Strategy execution is in-process.
- Indicator and signal execution is in-process and synchronous inside the strategy cycle.
- No distributed strategy evaluation.
- No centralized strategy parameter registry beyond local experiment metadata.
- No automatic promotion workflow from backtest to paper trading yet.
- Strategy-, signal-, and indicator-specific parameter schemas are still limited.
- No YAML/code loader exists for arbitrary custom indicators or signals.
- The runtime does not yet enforce data-quality gates before every strategy decision.
- The engine can make strategy decisions explainable, but it cannot make a weak strategy predictive.
