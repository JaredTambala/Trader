"""Configuration loading and normalization for the trading system."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from ..timeframes import normalize_timeframe


def _parse_symbols(raw: str) -> tuple[str, ...]:
    """Parse a comma-delimited symbol list into normalized tickers.

    Args:
        raw: Comma-separated string of symbols.

    Returns:
        Tuple of uppercased symbols with whitespace removed.

    Raises:
        None.
    """
    symbols = [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]
    return tuple(symbols)


def _parse_symbols_value(value: str | Sequence[object] | None) -> tuple[str, ...]:
    """Parse a symbol list from YAML values.

    Args:
        value: None, comma-delimited string, or list of symbols.

    Returns:
        Tuple of normalized symbols.
    """
    if value is None:
        return tuple()
    if isinstance(value, str):
        return _parse_symbols(value)
    if isinstance(value, (list, tuple)):
        symbols = [str(symbol).strip().upper() for symbol in value if str(symbol).strip()]
        return tuple(symbols)
    raise ValueError("market_data.symbols must be a string or list")


@dataclass(frozen=True)
class Config:
    """Typed configuration values for a trading cycle.

    Attributes:
        mode: Execution mode (once/loop/realtime).
        strategy_type: Strategy metadata/type label for logging and fallback metadata.
        strategy_id: Identifier for the active strategy version.
        strategy_timeframe: Timeframe used by strategy queries (e.g. 1Min).
        sma_short_window: Short SMA window size for crossover signals.
        sma_long_window: Long SMA window size for crossover signals.
        db_path: Optional path for local event store (unused for Postgres).
        event_store: Event store backend (postgres/noop).
        market_data_source: Source identifier for market data ingestion.
        market_data_asset_class: Asset class for market data (stocks/crypto).
        market_data_stock_feed: Alpaca stock data feed (iex/sip).
        market_data_symbols: Universe of symbols to fetch.
        market_data_max_age_seconds: Staleness cutoff before skipping trading.
        alpaca_api_key: Alpaca API key for data access.
        alpaca_secret_key: Alpaca secret key for data access.
        alpaca_data_base_url: Base URL for Alpaca data API.
        alpaca_base_url: Base URL for Alpaca trading API.
        pg_dsn: Optional Postgres DSN.
        pg_host: Postgres host.
        pg_port: Postgres port.
        pg_db: Postgres database name.
        pg_user: Postgres user.
        pg_password: Postgres password.
        log_signal_events: Whether to persist signal events.
        log_indicator_events: Whether to persist indicator events.
        log_order_events: Whether to persist order events.
        log_fill_events: Whether to persist fill events.
        log_position_snapshots: Whether to persist position snapshots.
        broker_type: Broker selection (noop/internal/alpaca).
        broker_time_in_force: Default time-in-force for broker orders.
        metrics_interval_seconds: Realtime metrics sampling interval (0 disables).
        metrics_window_seconds: Optional rolling window size for metrics.
        metrics_enable_snapshots: Whether to persist metrics snapshots.
        random_seed: Seed for random strategy (optional).
        random_order_qty: Default order size for random strategy.
        random_buy_probability: Probability of emitting a buy order.
        random_sell_probability: Probability of emitting a sell order.
        toggle_order_qty: Unit size for toggle strategy orders.
        trader_service_startup_recovery_mode: Startup recovery policy for live trading (resume/fail_closed).
        trader_service_portfolio_source: Source for live portfolio state (db/alpaca).
        trader_service_order_reconciliation_interval_seconds: Periodic open-order reconciliation interval; 0 disables.
    """
    mode: str
    strategy_type: str
    strategy_id: str
    strategy_timeframe: str
    sma_short_window: int
    sma_long_window: int
    db_path: str
    event_store: str
    market_data_source: str
    market_data_asset_class: str
    market_data_stock_feed: str
    market_data_symbols: tuple[str, ...]
    market_data_max_age_seconds: int
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_data_base_url: str
    alpaca_base_url: str
    pg_dsn: str
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str
    buffered_event_store: bool
    buffer_flush_interval_ms: int
    buffer_max_batch_size: int
    buffer_max_queue_size: int
    buffer_block_on_full: bool
    log_signal_events: bool
    log_indicator_events: bool
    log_order_events: bool
    log_fill_events: bool
    log_position_snapshots: bool
    broker_type: str
    internal_broker_reject_probability: float = 0.0
    internal_broker_fill_delay_ms_mean: float = 0.0
    internal_broker_fill_delay_ms_stddev: float = 0.0
    internal_broker_fill_qty_fraction_mean: float = 1.0
    internal_broker_fill_qty_fraction_stddev: float = 0.0
    internal_broker_rng_seed: int | None = None
    broker_time_in_force: str = "day"
    random_seed: int | None = None
    random_order_qty: float = 0.001
    random_buy_probability: float = 0.45
    random_sell_probability: float = 0.45
    toggle_order_qty: float = 1.0
    metrics_interval_seconds: int = 0
    metrics_window_seconds: int | None = None
    metrics_enable_snapshots: bool = False
    trader_service_startup_recovery_mode: str = "resume"
    trader_service_portfolio_source: str = ""
    trader_service_order_reconciliation_interval_seconds: int = 0


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load YAML configuration data from disk.

    Args:
        path: Relative or absolute path to the YAML configuration file.

    Returns:
        Parsed YAML mapping with environment variables expanded.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the YAML root is not a mapping.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, Mapping):
        raise ValueError("Config YAML must be a mapping at the root")
    expanded = _expand_env_values(data)
    return dict(expanded)


def build_config(data: Mapping[str, Any]) -> Config:
    """Normalize parsed YAML sections into the typed runtime config.

    The function applies defaults, expands nested config sections, coerces
    primitive values, normalizes timeframes and symbols, and derives defaults
    that depend on the broker type. Invalid scalar shapes fail here so runtime
    orchestration can rely on `Config` fields being typed.
    """
    runtime = _get_section(data, "runtime")
    strategy = _get_section(data, "strategy")
    market_data = _get_section(data, "market_data")
    broker = _get_section(data, "broker")
    database = _get_section(data, "database")
    alpaca = _get_section(data, "alpaca")
    pg = _get_section(database, "pg")

    window_value = strategy.get("sma_long_window", strategy.get("sma_window", 20))
    fallback_window = _as_int(window_value, 20)
    default_short = _as_int(strategy.get("sma_short_window"), max(1, fallback_window // 2))

    buffering = _get_section(database, "buffering")
    logging_cfg = _get_section(data, "logging")
    persist_cfg = _get_section(logging_cfg, "persist")
    metrics_cfg = _get_section(data, "metrics")
    trader_service_cfg = _get_section(data, "trader_service")
    internal_cfg = _get_section(broker, "internal")
    random_cfg = _get_section(strategy, "random")
    toggle_cfg = _get_section(strategy, "toggle")
    window_seconds_raw = metrics_cfg.get("window_seconds")
    window_seconds = None if window_seconds_raw in (None, "") else _as_int(window_seconds_raw, 0)
    strategy_type = str(strategy.get("type", strategy.get("id", "custom")))
    strategy_id = str(strategy.get("id", strategy_type))
    broker_type = str(broker.get("type", "noop"))
    default_portfolio_source = "alpaca" if broker_type.lower() == "alpaca" else "db"
    default_reconciliation_interval = 60 if broker_type.lower() == "alpaca" else 0

    return Config(
        mode=str(runtime.get("mode", "once")),
        strategy_type=strategy_type,
        strategy_id=strategy_id,
        strategy_timeframe=normalize_timeframe(str(strategy.get("timeframe", "1Min"))),
        sma_short_window=default_short,
        sma_long_window=fallback_window,
        db_path=str(database.get("db_path", "")),
        event_store=str(database.get("event_store", "postgres")),
        market_data_source=str(market_data.get("source", "alpaca")),
        market_data_asset_class=str(market_data.get("asset_class", "stocks")),
        market_data_stock_feed=str(market_data.get("stock_feed", "iex")),
        market_data_symbols=_parse_symbols_value(market_data.get("symbols")),
        market_data_max_age_seconds=_as_int(market_data.get("max_age_seconds"), 60),
        alpaca_api_key=str(alpaca.get("api_key", "")),
        alpaca_secret_key=str(alpaca.get("secret_key", "")),
        alpaca_data_base_url=str(alpaca.get("data_base_url", "https://data.alpaca.markets")),
        alpaca_base_url=str(alpaca.get("base_url", "https://paper-api.alpaca.markets")),
        pg_dsn=str(database.get("pg_dsn", pg.get("dsn", ""))),
        pg_host=str(database.get("pg_host", pg.get("host", ""))),
        pg_port=_as_int(database.get("pg_port", pg.get("port", 5432)), 5432),
        pg_db=str(database.get("pg_db", pg.get("db", ""))),
        pg_user=str(database.get("pg_user", pg.get("user", ""))),
        pg_password=str(database.get("pg_password", pg.get("password", ""))),
        buffered_event_store=_as_bool(buffering.get("enabled"), False),
        buffer_flush_interval_ms=_as_int(buffering.get("flush_interval_ms"), 250),
        buffer_max_batch_size=_as_int(buffering.get("max_batch_size"), 500),
        buffer_max_queue_size=_as_int(buffering.get("max_queue_size"), 10000),
        buffer_block_on_full=_as_bool(buffering.get("block_on_full"), True),
        log_signal_events=_as_bool(persist_cfg.get("signals"), True),
        log_indicator_events=_as_bool(persist_cfg.get("indicators"), True),
        log_order_events=_as_bool(persist_cfg.get("orders"), True),
        log_fill_events=_as_bool(persist_cfg.get("fills"), True),
        log_position_snapshots=_as_bool(persist_cfg.get("positions"), True),
        broker_type=broker_type,
        internal_broker_reject_probability=_as_float(internal_cfg.get("reject_probability"), 0.0),
        internal_broker_fill_delay_ms_mean=_as_float(internal_cfg.get("fill_delay_ms_mean"), 0.0),
        internal_broker_fill_delay_ms_stddev=_as_float(internal_cfg.get("fill_delay_ms_stddev"), 0.0),
        internal_broker_fill_qty_fraction_mean=_as_float(internal_cfg.get("fill_qty_fraction_mean"), 1.0),
        internal_broker_fill_qty_fraction_stddev=_as_float(internal_cfg.get("fill_qty_fraction_stddev"), 0.0),
        internal_broker_rng_seed=_as_optional_int(internal_cfg.get("rng_seed")),
        broker_time_in_force=str(broker.get("time_in_force", "day")),
        random_seed=_as_optional_int(random_cfg.get("seed")),
        random_order_qty=_as_float(random_cfg.get("order_qty"), 0.001),
        random_buy_probability=_as_float(random_cfg.get("buy_probability"), 0.45),
        random_sell_probability=_as_float(random_cfg.get("sell_probability"), 0.45),
        toggle_order_qty=_as_float(toggle_cfg.get("order_qty"), 1.0),
        metrics_interval_seconds=_as_int(metrics_cfg.get("interval_seconds"), 0),
        metrics_window_seconds=window_seconds,
        metrics_enable_snapshots=_as_bool(metrics_cfg.get("enable_snapshots"), False),
        trader_service_startup_recovery_mode=str(trader_service_cfg.get("startup_recovery_mode", "resume")),
        trader_service_portfolio_source=str(
            trader_service_cfg.get("portfolio_source", default_portfolio_source)
        ).strip().lower(),
        trader_service_order_reconciliation_interval_seconds=_as_int(
            trader_service_cfg.get("order_reconciliation_interval_seconds"),
            default_reconciliation_interval,
        ),
)


def resolve_log_level(data: Mapping[str, Any]) -> str:
    """Resolve the effective log level from config or environment.

    The explicit `logging.level` YAML value wins. When it is absent, `LOG_LEVEL`
    is used, falling back to `INFO`.
    """
    logging_cfg = _get_section(data, "logging")
    value = logging_cfg.get("level")
    if value:
        return str(value).upper()
    return os.getenv("LOG_LEVEL", "INFO").upper()


def _get_section(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Return a nested mapping section, treating missing/null as empty."""
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"Config section '{key}' must be a mapping")
    return value


def _expand_env_values(value: Any) -> Any:
    """Recursively expand environment variables in YAML string values."""
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, Mapping):
        return {key: _expand_env_values(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_expand_env_values(val) for val in value]
    return value


def _as_float(value: Any, default: float) -> float:
    """Coerce a config scalar to float while honoring an empty-value default."""
    if value in (None, ""):
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected float value, got {value!r}") from exc


def _as_optional_int(value: Any) -> int | None:
    """Coerce a config scalar to int, preserving missing/empty as `None`."""
    if value in (None, ""):
        return None
    return _as_int(value, 0)


def _as_int(value: Any, default: int) -> int:
    """Coerce a config scalar to integer with a default for missing values."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected integer value, got {value!r}") from exc


def _as_bool(value: Any, default: bool) -> bool:
    """Coerce common config boolean spellings into a real bool."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Expected boolean value, got {value!r}")
