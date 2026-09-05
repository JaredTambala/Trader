"""Helpers for deterministic sample market-data loading."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from ..event_store import EventStore
from ..symbols import normalize_asset_class
from ..timeframes import normalize_timeframe

SAMPLE_BAR_COLUMNS = (
    "symbol",
    "asset_class",
    "timeframe",
    "ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "vwap",
    "source",
)


def load_sample_market_data_csv(event_store: EventStore, path: str | Path) -> int:
    """Load deterministic OHLCV rows from CSV into the configured event store."""
    csv_path = Path(path)
    row_count = 0
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(SAMPLE_BAR_COLUMNS):
            raise ValueError(
                f"Sample CSV columns must be {SAMPLE_BAR_COLUMNS}; got {tuple(reader.fieldnames or [])}"
            )
        for row in reader:
            asset_class = normalize_asset_class(str(row["asset_class"]).strip())
            event_type = "crypto_bar_events" if asset_class in {"crypto", "cryptocurrency"} else "stock_bar_events"
            timestamp = _parse_ts(row["ts"])
            event_store.record_event(
                event_type,
                {
                    "symbol": str(row["symbol"]).strip().upper(),
                    "timeframe": normalize_timeframe(str(row["timeframe"]).strip()),
                    "ts": timestamp,
                    "ingested_at": timestamp,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "trade_count": _optional_float(row["trade_count"]),
                    "vwap": _optional_float(row["vwap"]),
                    "source": str(row["source"]).strip(),
                },
            )
            row_count += 1
    return row_count


def _parse_ts(value: str) -> datetime:
    """Parse a CSV timestamp to UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _optional_float(value: str) -> float | None:
    """Parse optional numeric CSV cells."""
    text = value.strip()
    if not text:
        return None
    return float(text)
