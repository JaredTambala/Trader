"""External entrypoint for market data backfills."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv

from trader.config import build_config, load_yaml_config, resolve_log_level
from trader.market_data.backfill import (
    BackfillSpec,
    MarketDataBackfillRunner,
    _parse_datetime,
    _parse_symbols_value,
    _parse_timeframe,
    _resolve_since,
    _resolve_window_from_config,
)
from trader_research.contracts import SideEffect, envelope_json, success_envelope


logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Alpaca market data bars.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    parser.add_argument("--json", action="store_true", help="Emit a stable tool JSON envelope.")
    parser.add_argument("--dry-run", action="store_true", help="Plan the backfill without fetching or writing bars.")
    parser.add_argument("--symbols", help="Comma-separated symbol override.")
    parser.add_argument("--asset-class", help="Asset-class override, e.g. stocks or crypto.")
    parser.add_argument("--timeframe", help="Timeframe override, e.g. 1Min.")
    parser.add_argument("--since", help="Relative window override, e.g. 30d.")
    parser.add_argument("--start", help="Explicit UTC start timestamp override.")
    parser.add_argument("--end", help="Explicit UTC end timestamp override.")
    parser.add_argument("--limit", type=int, help="Optional Alpaca bar limit override.")
    return parser.parse_args()


def _configure_logging(level_name: str | None = None) -> None:
    level_name = (level_name or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Logging configured level=%s", level_name)


def main() -> None:
    load_dotenv(".env")
    args = _parse_args()
    config_data = load_yaml_config(args.config)
    _configure_logging(resolve_log_level(config_data))
    result = run_backfill_command(config_data, args)
    if args.json:
        print(envelope_json(result))


def run_backfill_command(config_data: Mapping[str, Any], args: argparse.Namespace):
    """Run or plan a backfill from parsed CLI arguments."""
    config = build_config(config_data)

    backfill = config_data.get("backfill", {})
    if backfill is None:
        backfill = {}
    if not isinstance(backfill, Mapping):
        raise ValueError("backfill section must be a mapping")
    service_cfg = config_data.get("trader_service", {})
    if service_cfg is None:
        service_cfg = {}
    if not isinstance(service_cfg, Mapping):
        raise ValueError("trader_service section must be a mapping")

    now = datetime.now(timezone.utc)
    start, end = _resolve_window(backfill, args, now)
    timeframe_value = args.timeframe or backfill.get("timeframe", config.strategy_timeframe)
    limit_value = args.limit if args.limit is not None else backfill.get("limit")
    limit = int(limit_value) if limit_value is not None else None
    spec = BackfillSpec(
        start=start,
        end=end,
        timeframe=_parse_timeframe(str(timeframe_value)),
        limit=limit,
    )
    symbols = _parse_symbols_value(args.symbols if args.symbols else backfill.get("symbols"))
    asset_class = args.asset_class or backfill.get("asset_class")
    notify_channel = service_cfg.get("notify_channel")
    metadata = _backfill_metadata(
        symbols=symbols if symbols is not None else config.market_data_symbols,
        asset_class=str(asset_class or config.market_data_asset_class),
        timeframe=str(timeframe_value),
        start=start,
        end=end,
        since=None if args.start or args.end else str(args.since or backfill.get("since", "")) or None,
        limit=limit,
        notify_channel=str(notify_channel) if notify_channel else None,
        dry_run=bool(args.dry_run),
        rows_written=None,
    )
    if args.dry_run:
        return success_envelope(
            command="market_data_backfill",
            agent_owner="Data Agent",
            side_effect=SideEffect.READ_ONLY,
            data=metadata,
            warnings=(),
        )
    runner = MarketDataBackfillRunner(
        config,
        spec,
        symbols=symbols,
        asset_class=str(asset_class) if asset_class else None,
        notify_channel=str(notify_channel) if notify_channel else None,
    )
    rows_written = runner.run()
    metadata["rows_written"] = rows_written
    return success_envelope(
        command="market_data_backfill",
        agent_owner="Data Agent",
        side_effect=SideEffect.LOCAL_MUTATING,
        data=metadata,
        warnings=(),
    )


def _resolve_window(
    backfill: Mapping[str, object],
    args: argparse.Namespace,
    now: datetime,
) -> tuple[datetime, datetime]:
    if args.start or args.end:
        if not args.start:
            raise ValueError("--start is required when --end is provided")
        start = _parse_datetime(str(args.start))
        end = _parse_datetime(str(args.end)) if args.end else now
        return start, end
    if args.since:
        return _resolve_since(str(args.since), now)
    return _resolve_window_from_config(backfill, now)


def _backfill_metadata(
    *,
    symbols: Sequence[object],
    asset_class: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    since: str | None,
    limit: int | None,
    notify_channel: str | None,
    dry_run: bool,
    rows_written: int | None,
) -> dict[str, Any]:
    parsed_symbols = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    payload = {
        "symbols": parsed_symbols,
        "asset_class": asset_class.lower(),
        "timeframe": timeframe,
        "requested_window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "since": since,
        },
        "source": "alpaca",
        "limit": limit,
        "rows_written": rows_written,
        "rows_skipped": None,
        "notify_channel": notify_channel,
        "dry_run": dry_run,
    }
    dataset_payload = {
        "symbols": parsed_symbols,
        "asset_class": asset_class.lower(),
        "timeframe": timeframe,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "source": "alpaca",
    }
    digest = hashlib.sha256(
        json.dumps(dataset_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    payload["dataset_id"] = f"dataset_{digest}"
    return payload


if __name__ == "__main__":
    main()
