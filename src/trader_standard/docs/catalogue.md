# Maintained Implementation Catalogue

## Indicators

- `SmaIndicator`, `EmaIndicator`: moving averages.
- `RsiIndicator`: relative-strength oscillator.
- `MacdIndicator`: MACD, signal, and histogram values.
- `BollingerBandsIndicator`: lower, middle, and upper bands.
- `HistoricalVolatilityIndicator`, `RollingVolatilityIndicator`: return-volatility estimates.
- `ZScoreIndicator`: rolling standardized value.

## Signals and generators

Maintained signals cover moving-average crossovers, RSI thresholds, MACD crossover, SMA stretch, Bollinger position,
and Bollinger-bandwidth/moving-average actions. `SimpleBarsSignalGenerator` reads bounded windows from an event store;
`InMemoryBarsSignalGenerator` supports deterministic in-memory composition.

## Strategies and policies

- `NoOpStrategy`: deliberately emits no orders.
- `RandomStrategy`: seeded probabilistic test behavior; not a research baseline.
- `ToggleUnitStrategy`: deterministic alternating exposure for runtime and accounting tests.
- `SimpleStrategy`: maps a primary scalar signal to fixed-quantity orders.
- `LongFlatSignalStrategy`: composes signals with entry, exit, and stop policies.
- `PairsMeanReversionStrategy`: universe-aware paired behavior.
- `PredictionDrivenStrategy`: maps typed model predictions through a strategy-owned mapper.
- `build_trend_following_strategy`, `build_mean_reversion_strategy`,
  `build_pairs_mean_reversion_strategy`, and `build_bollinger_band_strategy`: supported compositions.

Policies include threshold entry/exit, fixed stop loss, trailing stop, and composite stops.

## Risk managers

The maintained risk set includes no-op, halt, per-run order count, gross exposure, per-symbol position value, and open
buy-order limits. Compose them with core `RiskPipeline`; list order is preserved and should be intentional.

This catalogue describes availability, not suitability. Research selection still requires an explicit brief, data
scope, assumptions, prospective experiment, and independent review.
