"""CLI operator surface for runtime status, halt control, and reconciliation."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
import logging
from pprint import pformat
from typing import Any, Mapping, NoReturn

from dotenv import load_dotenv

from trader.config import Config, build_config, load_yaml_config, resolve_log_level
from trader.event_store import EventStore, build_event_store
from trader.runtime.orders import run_startup_recovery
from trader.runtime.status import (
    get_halt_state,
    latest_open_orders,
    latest_portfolio_status,
    runtime_status,
    set_halt_state,
)
from trader.runtime.service import _build_runtime_broker


logger = logging.getLogger(__name__)


def main() -> None:
    """Run the operator CLI."""
    load_dotenv(".env")
    args = _parse_args()
    config_data = load_yaml_config(args.config)
    _configure_logging(resolve_log_level(config_data))
    config = build_config(config_data)
    event_store = build_event_store(config)
    try:
        exit_code = _run_command(args, config=config, event_store=event_store)
    finally:
        event_store.close()
    if exit_code:
        raise SystemExit(exit_code)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect and operate a live-paper trading runtime.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("status", "health", "positions", "open-orders", "reconcile"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    halt = subparsers.add_parser("halt")
    halt_subparsers = halt.add_subparsers(dest="halt_command", required=True)
    for command in ("status", "clear"):
        subparser = halt_subparsers.add_parser(command)
        subparser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    set_parser = halt_subparsers.add_parser("set")
    set_parser.add_argument("--reason", default="", help="Operator-supplied reason for the halt.")
    set_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args()


def _run_command(args: argparse.Namespace, *, config: Config, event_store: EventStore) -> int:
    if args.command == "status":
        payload = runtime_status(event_store, config)
        _emit(payload, json_output=args.json, title="runtime_status")
        return 0
    if args.command == "health":
        payload = runtime_status(event_store, config)
        _emit(payload["health"], json_output=args.json, title="health")
        return int(payload["health"]["exit_code"])
    if args.command == "positions":
        payload = latest_portfolio_status(event_store)
        _emit(payload, json_output=args.json, title="positions")
        return 0
    if args.command == "open-orders":
        payload = latest_open_orders(
            event_store,
            stale_after_seconds=config.market_data_max_age_seconds,
        )
        _emit(payload, json_output=args.json, title="open_orders")
        return 0
    if args.command == "halt":
        return _run_halt_command(args, event_store=event_store)
    if args.command == "reconcile":
        broker = _build_runtime_broker(config, event_store)
        report = run_startup_recovery(
            event_store=event_store,
            broker=broker,
            configured_symbols=config.market_data_symbols,
            configured_asset_class=config.market_data_asset_class,
            mode="resume",
            run_id=None,
        )
        payload = asdict(report)
        _emit(payload, json_output=args.json, title="reconcile")
        return 0
    _die(f"Unsupported command: {args.command}")


def _run_halt_command(args: argparse.Namespace, *, event_store: EventStore) -> int:
    if args.halt_command == "status":
        payload = get_halt_state(event_store)
    elif args.halt_command == "set":
        payload = set_halt_state(event_store, halted=True, reason=args.reason)
    elif args.halt_command == "clear":
        payload = set_halt_state(event_store, halted=False, reason="")
    else:
        _die(f"Unsupported halt command: {args.halt_command}")
    _emit(payload, json_output=args.json, title="halt")
    return 0


def _emit(payload: Mapping[str, Any], *, json_output: bool, title: str) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True, default=_json_default))
        return
    print(f"{title}:")
    print(pformat(dict(payload), sort_dicts=True))


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _configure_logging(level_name: str | None = None) -> None:
    level_name = (level_name or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Logging configured level=%s", level_name)


def _die(message: str) -> NoReturn:
    raise SystemExit(message)


if __name__ == "__main__":
    main()
