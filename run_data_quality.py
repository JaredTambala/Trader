"""External entrypoint for data quality checks."""

from __future__ import annotations

import argparse
import logging

from dotenv import load_dotenv

from trader.config import load_yaml_config, resolve_log_level
from trader.data_quality import run_data_quality


logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check market data timestamp gaps.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
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
    run_data_quality(config_data)


if __name__ == "__main__":
    main()
