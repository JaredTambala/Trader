"""Data quality checks for market data gaps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import logging
from typing import Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .config import build_config
from .data import EventStore, build_event_store
from .timeframes import normalize_timeframe, parse_timeframe


logger = logging.getLogger(__name__)

_MARKET_TZ = ZoneInfo("America/New_York")
_MARKET_OPEN = time(9, 30)
_MARKET_CLOSE = time(16, 0)


@dataclass(frozen=True)
class GapRecord:
    symbol: str
    prev_ts: datetime
    next_ts: datetime
    delta: timedelta
    expected: timedelta
    threshold: timedelta
    reason: str


@dataclass(frozen=True)
class DataQualitySummary:
    symbol: str
    total_bars: int
    missing_gaps: int
    expected_gaps: int
    max_gap: timedelta | None


@dataclass(frozen=True)
class SessionWindow:
    symbol: str
    timeframe: str
    start_time: time
    end_time: time
    timezone: ZoneInfo


def run_data_quality(config_data: Mapping[str, object]) -> None:
    """Run data quality checks using a parsed config mapping."""
    config = build_config(config_data)
    quality = _get_section(config_data, "data_quality")
    symbols = _parse_symbols(quality.get("symbols") or config.market_data_symbols)
    if not symbols:
        raise ValueError("data_quality.symbols is required")
    asset_class = str(quality.get("asset_class", config.market_data_asset_class)).lower()
    timeframe = normalize_timeframe(str(quality.get("timeframe", config.strategy_timeframe)))
    start = _parse_datetime(quality.get("start"))
    end = _parse_datetime(quality.get("end"))
    max_gap_logs = _as_int(quality.get("max_gap_logs"), 50)
    multipliers = _parse_gap_multipliers(quality.get("gap_multipliers"))
    sessions = _parse_sessions(quality.get("sessions"))

    event_store = build_event_store(config)
    try:
        for symbol in symbols:
            timestamps = _fetch_timestamps(
                event_store,
                asset_class,
                symbol,
                timeframe,
                start=start,
                end=end,
            )
            summary, gaps = _analyze_gaps(
                symbol=symbol,
                timestamps=timestamps,
                asset_class=asset_class,
                timeframe=timeframe,
                multipliers=multipliers,
                sessions=sessions,
            )
            _log_summary(summary)
            _log_gaps(gaps, max_gap_logs=max_gap_logs)
    finally:
        event_store.close()


def _fetch_timestamps(
    event_store: EventStore,
    asset_class: str,
    symbol: str,
    timeframe: str,
    *,
    start: datetime | None,
    end: datetime | None,
) -> list[datetime]:
    """Fetch timestamps."""
    table = "crypto_bar_events" if asset_class in {"crypto", "cryptocurrency"} else "stock_bar_events"
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None or not hasattr(connection, "cursor"):
        logger.warning("Data quality skipped; event store has no connection")
        return []

    placeholder = _param_placeholder(connection)
    filters = [f"symbol = {placeholder}", f"COALESCE(timeframe, '1Min') = {placeholder}"]
    params: list[object] = [symbol.upper(), timeframe]
    if start is not None:
        filters.append(f"ts >= {placeholder}")
        params.append(start)
    if end is not None:
        filters.append(f"ts <= {placeholder}")
        params.append(end)
    where_clause = " AND ".join(filters)
    query = f"""
        SELECT ts
        FROM {table}
        WHERE {where_clause}
        ORDER BY ts ASC
    """
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return [_normalize_timestamp(row[0]) for row in cursor.fetchall()]


def _analyze_gaps(
    *,
    symbol: str,
    timestamps: Sequence[datetime],
    asset_class: str,
    timeframe: str,
    multipliers: Mapping[str, float],
    sessions: Mapping[tuple[str, str], SessionWindow],
) -> tuple[DataQualitySummary, list[GapRecord]]:
    """Handle analyze gaps."""
    if len(timestamps) < 2:
        summary = DataQualitySummary(
            symbol=symbol,
            total_bars=len(timestamps),
            missing_gaps=0,
            expected_gaps=0,
            max_gap=None,
        )
        return summary, []

    expected_delta = _expected_delta(timeframe)
    unit = _timeframe_unit(timeframe)
    multiplier = multipliers.get(unit, 2.0)
    threshold = expected_delta * multiplier
    gaps: list[GapRecord] = []
    missing = 0
    expected = 0
    max_gap = None

    for prev_ts, next_ts in zip(timestamps, timestamps[1:]):
        delta = next_ts - prev_ts
        if max_gap is None or delta > max_gap:
            max_gap = delta
        if delta <= threshold:
            continue
        session = sessions.get((symbol.upper(), normalize_timeframe(timeframe)))
        reason = _gap_reason(prev_ts, next_ts, asset_class, timeframe, session=session)
        record = GapRecord(
            symbol=symbol,
            prev_ts=prev_ts,
            next_ts=next_ts,
            delta=delta,
            expected=expected_delta,
            threshold=threshold,
            reason=reason,
        )
        gaps.append(record)
        if reason == "expected_session_gap":
            expected += 1
        else:
            missing += 1

    summary = DataQualitySummary(
        symbol=symbol,
        total_bars=len(timestamps),
        missing_gaps=missing,
        expected_gaps=expected,
        max_gap=max_gap,
    )
    return summary, gaps


def _gap_reason(
    prev_ts: datetime,
    next_ts: datetime,
    asset_class: str,
    timeframe: str,
    *,
    session: SessionWindow | None,
) -> str:
    """Handle gap reason."""
    if asset_class not in {"stocks", "stock"}:
        if session and _is_expected_window_gap(prev_ts, next_ts, session):
            return "expected_session_gap"
        return "gap"
    unit = _timeframe_unit(timeframe)
    if unit in {"minute", "hour"}:
        if session and _is_expected_window_gap(prev_ts, next_ts, session):
            return "expected_session_gap"
        if unit == "minute" and prev_ts.date() != next_ts.date():
            return "expected_session_gap"
        if _is_expected_session_gap(prev_ts, next_ts):
            return "expected_session_gap"
    elif unit in {"day", "week", "month"}:
        if _is_expected_daily_gap(prev_ts, next_ts, timeframe):
            return "expected_session_gap"
    return "gap"


def _is_expected_session_gap(prev_ts: datetime, next_ts: datetime) -> bool:
    """Return whether expected session gap."""
    prev_local = prev_ts.astimezone(_MARKET_TZ)
    next_local = next_ts.astimezone(_MARKET_TZ)
    if prev_local.date() == next_local.date():
        return False
    trading_days = _count_trading_days(prev_local.date(), next_local.date())
    return trading_days <= 1


def _is_expected_window_gap(prev_ts: datetime, next_ts: datetime, session: SessionWindow) -> bool:
    """Return whether expected window gap."""
    prev_local = prev_ts.astimezone(session.timezone)
    next_local = next_ts.astimezone(session.timezone)
    if prev_local.date() == next_local.date():
        return False
    if prev_local.time() < session.end_time:
        return False
    if next_local.time() > session.start_time:
        return False
    return True


def _is_expected_daily_gap(prev_ts: datetime, next_ts: datetime, timeframe: str) -> bool:
    """Return whether expected daily gap."""
    prev_local = prev_ts.astimezone(_MARKET_TZ)
    next_local = next_ts.astimezone(_MARKET_TZ)
    trading_days = _count_trading_days(prev_local.date(), next_local.date())
    expected_days = _expected_trading_days(timeframe)
    return trading_days <= expected_days


def _expected_trading_days(timeframe: str) -> int:
    """Compute expected trading days."""
    tf = normalize_timeframe(timeframe)
    amount, unit = _parse_timeframe_parts(tf)
    if unit == "week":
        return amount * 5
    if unit == "month":
        return amount * 21
    return amount


def _count_trading_days(start_date: datetime.date, end_date: datetime.date) -> int:
    """Count trading days."""
    if end_date <= start_date:
        return 0
    day = start_date + timedelta(days=1)
    count = 0
    while day <= end_date:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def _expected_delta(timeframe: str) -> timedelta:
    """Compute expected delta."""
    tf = parse_timeframe(timeframe)
    if tf.unit.name == "Minute":
        return timedelta(minutes=tf.amount)
    if tf.unit.name == "Hour":
        return timedelta(hours=tf.amount)
    if tf.unit.name == "Day":
        return timedelta(days=tf.amount)
    if tf.unit.name == "Week":
        return timedelta(weeks=tf.amount)
    return timedelta(days=30 * tf.amount)


def _timeframe_unit(timeframe: str) -> str:
    """Handle timeframe unit."""
    tf = normalize_timeframe(timeframe)
    if tf.endswith("Min"):
        return "minute"
    if tf.endswith("Hour"):
        return "hour"
    if tf.endswith("Day"):
        return "day"
    if tf.endswith("Week"):
        return "week"
    if tf.endswith("Month"):
        return "month"
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _parse_timeframe_parts(timeframe: str) -> tuple[int, str]:
    """Parse timeframe parts."""
    tf = normalize_timeframe(timeframe)
    for unit in ("Min", "Hour", "Day", "Week", "Month"):
        if tf.endswith(unit):
            amount = int(tf[:-len(unit)])
            return amount, unit.lower()
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _parse_symbols(value: object) -> tuple[str, ...]:
    """Parse symbols."""
    if value is None:
        return tuple()
    if isinstance(value, str):
        symbols = [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
        return tuple(symbols)
    if isinstance(value, (list, tuple)):
        symbols = [str(symbol).strip().upper() for symbol in value if str(symbol).strip()]
        return tuple(symbols)
    raise ValueError("data_quality.symbols must be a string or list")


def _parse_datetime(value: object | None) -> datetime | None:
    """Parse datetime."""
    if value in {None, ""}:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _parse_gap_multipliers(value: object | None) -> dict[str, float]:
    """Parse gap multipliers."""
    defaults = {
        "minute": 2.0,
        "hour": 2.0,
        "day": 1.0,
        "week": 1.0,
        "month": 1.0,
    }
    if value is None:
        return defaults
    if not isinstance(value, Mapping):
        raise ValueError("data_quality.gap_multipliers must be a mapping")
    overrides: dict[str, float] = {}
    for key, raw in value.items():
        unit = str(key).lower()
        try:
            overrides[unit] = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid gap multiplier for {key}: {raw}") from exc
    defaults.update(overrides)
    return defaults


def _parse_sessions(value: object | None) -> dict[tuple[str, str], SessionWindow]:
    """Parse sessions."""
    if value is None:
        return {}
    if not isinstance(value, (list, tuple)):
        raise ValueError("data_quality.sessions must be a list")
    sessions: dict[tuple[str, str], SessionWindow] = {}
    for entry in value:
        if not isinstance(entry, Mapping):
            raise ValueError("data_quality.sessions entries must be mappings")
        symbol = str(entry.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("data_quality.sessions requires symbol")
        timeframe = normalize_timeframe(str(entry.get("timeframe", "")))
        start_raw = entry.get("start_time")
        end_raw = entry.get("end_time")
        if not start_raw or not end_raw:
            raise ValueError("data_quality.sessions requires start_time and end_time")
        tz_name = str(entry.get("timezone") or "America/New_York")
        timezone = ZoneInfo(tz_name)
        start_time = _parse_clock_time(str(start_raw))
        end_time = _parse_clock_time(str(end_raw))
        sessions[(symbol, timeframe)] = SessionWindow(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
        )
    return sessions


def _parse_clock_time(value: str) -> time:
    """Parse clock time."""
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time value: {value}")
    hour = int(parts[0])
    minute = int(parts[1])
    return time(hour=hour, minute=minute)


def _log_summary(summary: DataQualitySummary) -> None:
    """Log summary."""
    logger.info(
        "Data quality summary symbol=%s bars=%s missing_gaps=%s expected_gaps=%s max_gap=%s",
        summary.symbol,
        summary.total_bars,
        summary.missing_gaps,
        summary.expected_gaps,
        summary.max_gap,
    )


def _log_gaps(gaps: Iterable[GapRecord], *, max_gap_logs: int) -> None:
    """Log gaps."""
    gap_list = list(gaps)
    for idx, gap in enumerate(gap_list):
        if idx >= max_gap_logs:
            logger.warning("Additional gaps suppressed count=%s", len(gap_list) - max_gap_logs)
            break
        if gap.reason == "expected_session_gap":
            logger.info(
                "Expected session gap symbol=%s prev_ts=%s next_ts=%s delta=%s threshold=%s",
                gap.symbol,
                gap.prev_ts.isoformat(),
                gap.next_ts.isoformat(),
                gap.delta,
                gap.threshold,
            )
            continue
        logger.warning(
            "Missing gap symbol=%s prev_ts=%s next_ts=%s delta=%s threshold=%s",
            gap.symbol,
            gap.prev_ts.isoformat(),
            gap.next_ts.isoformat(),
            gap.delta,
            gap.threshold,
        )


def _param_placeholder(connection: object) -> str:
    """Return the SQL parameter placeholder for the active backend."""
    module = connection.__class__.__module__
    if module.startswith("duckdb"):
        return "?"
    return "%s"


def _as_int(value: object | None, default: int) -> int:
    """Coerce a value into an integer."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer value: {value}") from exc


def _get_section(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    """Return section."""
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"Config section '{key}' must be a mapping")
    return value


def _normalize_timestamp(value: datetime) -> datetime:
    """Normalize timestamp values to UTC-aware datetimes."""
    if value.tzinfo is None:
        return value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(ZoneInfo("UTC"))


if __name__ == "__main__":
    raise SystemExit(
        "trader.data_quality is a library module. "
        "Use run_data_quality.py (external entrypoint) to run checks."
    )
