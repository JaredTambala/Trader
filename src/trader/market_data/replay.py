"""Replay market data from the database to exercise realtime code paths."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Iterable, Mapping, Sequence

from dotenv import load_dotenv

from ..config import Config, build_config, load_yaml_config, resolve_log_level
from ..event_store import EventStore, build_event_store
from ..runtime.notifications import notify_market_data
from ..timeframes import normalize_timeframe


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplayConfig:
    """Query and pacing options for database-backed market-data replay.

    Attributes:
        asset_class: Stock or crypto event table family to replay.
        symbols: Symbol universe to query and notify.
        timeframe: Timeframe label matched against stored bars.
        start: Optional inclusive lower timestamp bound.
        end: Optional inclusive upper timestamp bound.
        cadence_seconds: Sleep interval between emitted notifications.
        notify_channel: Optional Postgres NOTIFY channel override.
        limit: Optional maximum number of stored bars to replay.
    """

    asset_class: str
    symbols: Sequence[str]
    timeframe: str
    start: datetime | None
    end: datetime | None
    cadence_seconds: float
    notify_channel: str | None
    limit: int | None


def _table_name(asset_class: str) -> str:
    """Resolve the event table name for the asset class."""
    asset_class = asset_class.lower()
    if asset_class in {"crypto", "cryptocurrency"}:
        return "crypto_bar_events"
    return "stock_bar_events"


def _fetch_bars(
    event_store: EventStore,
    config: ReplayConfig,
) -> Iterable[tuple[str, datetime]]:
    """Fetch bar timestamps for replay."""
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None or not hasattr(connection, "cursor"):
        raise RuntimeError("Replay requires a SQL-capable event store connection")

    table = _table_name(config.asset_class)
    symbols = [symbol.strip().upper() for symbol in config.symbols if symbol]
    if not symbols:
        return []

    placeholders = ", ".join(["%s"] * len(symbols))
    clauses = [
        f"symbol IN ({placeholders})",
        "COALESCE(timeframe, '1Min') = %s",
    ]
    params: list[object] = [*symbols, config.timeframe]
    if config.start is not None:
        clauses.append("ts >= %s")
        params.append(config.start)
    if config.end is not None:
        clauses.append("ts <= %s")
        params.append(config.end)

    where_clause = " AND ".join(clauses)
    limit_clause = "LIMIT %s" if config.limit else ""
    if config.limit:
        params.append(config.limit)

    query = f"""
        SELECT symbol, ts
        FROM {table}
        WHERE {where_clause}
        ORDER BY ts ASC, symbol ASC
        {limit_clause}
    """
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    return [(row[0], row[1]) for row in rows]


def replay_market_data(event_store: EventStore, config: ReplayConfig) -> int:
    """Replay stored bars by emitting realtime market-data notifications.

    The function does not rewrite bar events. It reads historical bar timestamps
    in chronological order, sends one notification payload per row, optionally
    sleeps between notifications, and returns the number of emitted messages.
    """
    rows = _fetch_bars(event_store, config)
    if not rows:
        logger.warning("No bars found for replay")
        return 0
    logger.info(
        "Replay start asset_class=%s symbols=%s timeframe=%s start=%s end=%s cadence_seconds=%s limit=%s",
        config.asset_class,
        ",".join(config.symbols),
        config.timeframe,
        config.start.isoformat() if config.start else "<none>",
        config.end.isoformat() if config.end else "<none>",
        config.cadence_seconds,
        config.limit,
    )
    sent = 0
    for symbol, ts in rows:
        payload = {
            "symbol": symbol,
            "timeframe": config.timeframe,
            "ts": _normalize_timestamp(ts).isoformat(),
            "asset_class": config.asset_class,
            "source": "replay",
        }
        notified = notify_market_data(event_store, payload, channel=config.notify_channel)
        sent += 1
        logger.info(
            "Replay notify sent=%s symbol=%s ts=%s",
            notified,
            symbol,
            _normalize_timestamp(ts).isoformat(),
        )
        if config.cadence_seconds > 0:
            time.sleep(config.cadence_seconds)
    logger.info("Replay complete count=%s", sent)
    return sent


def _normalize_timestamp(value: datetime) -> datetime:
    """Normalize timestamps to UTC-aware datetimes."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse ISO-8601 timestamps from config."""
    if not value:
        return None
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _parse_symbols(value: object | None) -> list[str]:
    """Parse symbol inputs into uppercase identifiers."""
    if value is None:
        return []
    if isinstance(value, str):
        return [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
    if isinstance(value, (list, tuple)):
        return [str(symbol).strip().upper() for symbol in value if str(symbol).strip()]
    raise ValueError("replay.symbols must be a string or list")


def _configure_logging(level_name: str | None = None) -> None:
    """Configure console logging for the market-data replay command."""
    level_name = (level_name or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Logging configured level=%s", level_name)


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for replay."""
    parser = argparse.ArgumentParser(description="Replay market data bars via NOTIFY.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    return parser.parse_args()


def _build_replay_config(config: Config, config_data: Mapping[str, object]) -> ReplayConfig:
    """Build the replay configuration from YAML data."""
    replay_cfg = config_data.get("replay", {})
    if replay_cfg is None:
        replay_cfg = {}
    if not isinstance(replay_cfg, Mapping):
        raise ValueError("replay section must be a mapping")

    symbols = _parse_symbols(replay_cfg.get("symbols") or config.market_data_symbols)
    asset_class = str(replay_cfg.get("asset_class") or config.market_data_asset_class)
    timeframe = normalize_timeframe(str(replay_cfg.get("timeframe") or config.strategy_timeframe))
    start = _parse_datetime(replay_cfg.get("start"))
    end = _parse_datetime(replay_cfg.get("end"))
    cadence_seconds = float(replay_cfg.get("cadence_seconds") or 0.0)
    notify_channel = replay_cfg.get("notify_channel")
    limit = replay_cfg.get("limit")
    limit_value = int(limit) if limit is not None else None
    return ReplayConfig(
        asset_class=asset_class,
        symbols=symbols,
        timeframe=timeframe,
        start=start,
        end=end,
        cadence_seconds=cadence_seconds,
        notify_channel=str(notify_channel) if notify_channel else None,
        limit=limit_value,
    )


def main() -> None:
    """Load config, build the event store, run replay, and close resources."""
    load_dotenv(".env")
    args = _parse_args()
    config_data = load_yaml_config(args.config)
    _configure_logging(resolve_log_level(config_data))
    config = build_config(config_data)
    replay_config = _build_replay_config(config, config_data)
    event_store = build_event_store(config)
    try:
        replay_market_data(event_store, replay_config)
    finally:
        event_store.close()


if __name__ == "__main__":
    main()
