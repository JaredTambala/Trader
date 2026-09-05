# Configuration

Configuration crosses an untrusted text/environment boundary, so Trader parses and normalizes it before runtime
composition. `load_yaml_config` owns YAML loading and recursive environment expansion; `build_config` owns defaults,
coercion, symbol/timeframe normalization, and derived broker defaults.

## Sections

| Section | Controls |
| --- | --- |
| `runtime` | once, loop, or realtime execution mode |
| `strategy` | metadata, timeframe, and parameters consumed by wrappers |
| `market_data` | provider, asset class, feed, symbols, and staleness |
| `database` | Postgres connection, event-store selection, and buffering |
| `broker` | no-op, internal, or Alpaca adapter and execution options |
| `alpaca` | data/trading endpoint and credentials |
| `logging.persist` | optional high-volume event families |
| `metrics` | sample interval, window, and snapshot persistence |
| `trader_service` | recovery, portfolio truth, and reconciliation interval |

## Minimal normalized mapping

<!-- verified: doctest -->
```pycon
>>> from trader.config import build_config
>>> value = build_config({
...     "strategy": {"id": "demo", "timeframe": "1h"},
...     "market_data": {"symbols": "btc/usd, eth/usd", "asset_class": "crypto"},
... })
>>> value.strategy_timeframe
'1Hour'
>>> value.market_data_symbols
('BTC/USD', 'ETH/USD')
```

An empty mapping is valid and produces explicit defaults. That is useful for unit tests, but operators should provide
the database, universe, strategy, broker, and recovery choices rather than rely on implicit values.

## Environment and secrets

YAML may reference environment values; do not commit secrets. Paper-trading credentials belong only at the provider
adapter boundary. Research agents and their model context must never receive them. Postgres connection settings may be
provided as a DSN or component fields. See the root [environment guide](../../../docs/environment.md) for supported
variables and local Docker setup.

## Failure behavior

Wrong root/section shapes, invalid symbol shapes, and invalid scalar conversions fail during loading or normalization.
Runtime code may therefore assume the `Config` fields have stable Python types. Provider availability and credentials
are separate startup checks; syntactically valid configuration does not prove an external dependency is reachable.
