"""Operator entrypoint for broker/local order recovery and local cleanup."""

from __future__ import annotations

import argparse
import logging
from pprint import pformat

from dotenv import load_dotenv

from trader.config import build_config, load_yaml_config, resolve_log_level
from trader.event_store import build_event_store
from trader.runtime.broker_factory import build_runtime_broker
from trader.runtime.orders import inspect_recovery_state, run_local_clean_start, run_startup_recovery


logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect and repair local order state.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("report", help="Report local-open and broker-open order state.")
    subparsers.add_parser("reconcile", help="Run resume-style bidirectional startup recovery.")
    subparsers.add_parser("clean-start", help="Close local open orders in the configured universe without touching broker state.")
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
    config = build_config(config_data)
    event_store = build_event_store(config)
    broker = None

    if args.command in {"report", "reconcile"}:
        broker = build_runtime_broker(config, event_store)

    if args.command == "report":
        assert broker is not None
        report = inspect_recovery_state(
            event_store=event_store,
            broker=broker,
            configured_symbols=config.market_data_symbols,
            configured_asset_class=config.market_data_asset_class,
        )
        logger.info("Local open orders=%s", report.local_open_before)
        logger.info("Broker open in scope=%s out_of_scope=%s", report.broker_open_in_scope, report.broker_open_out_of_scope)
        print("local_open:")
        print(pformat(report.local_open))
        print("broker_open_in_scope:")
        print(pformat(report.in_scope_broker_open))
        print("broker_open_out_of_scope:")
        print(pformat(report.out_of_scope_broker_open))
        return

    if args.command == "clean-start":
        report = run_local_clean_start(
            event_store=event_store,
            configured_symbols=config.market_data_symbols,
            configured_asset_class=config.market_data_asset_class,
            run_id=None,
        )
    else:
        assert broker is not None
        report = run_startup_recovery(
            event_store=event_store,
            broker=broker,
            configured_symbols=config.market_data_symbols,
            configured_asset_class=config.market_data_asset_class,
            mode="resume",
            run_id=None,
        )
    logger.info(
        "Order recovery command=%s local_open_before=%s local_closed_missing=%s local_updated_from_broker=%s adopted_broker_open=%s local_clean_start_closed=%s",
        args.command,
        report.local_open_before,
        report.local_closed_missing,
        report.local_updated_from_broker,
        report.adopted_broker_open,
        report.local_clean_start_closed,
    )
    print(pformat(report.actions))


if __name__ == "__main__":
    main()
