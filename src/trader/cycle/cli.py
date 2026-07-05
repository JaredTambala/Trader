"""Command-line boundary helpers for decision cycles."""

from __future__ import annotations

import logging

from ..config import Config
from .startup import _startup_config_log_values


logger = logging.getLogger(__name__)


def _log_startup_config(config: Config) -> None:
    """Log relevant configuration values for startup diagnostics."""
    masked = _startup_config_log_values(config)
    formatted = ", ".join(f"{key}={value}" for key, value in masked.items())
    logger.info("Startup config: %s", formatted)


def _configure_logging(level_name: str | None = None) -> None:
    """Configure logging from configuration defaults."""
    level_name = (level_name or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Logging configured level=%s", level_name)


def main() -> None:
    """Reject direct execution because cycles require injected dependencies."""
    raise SystemExit(
        "trader.cycle is a library module. "
        "Construct a Strategy and RiskManager in your own wrapper script and call run_cycle(...)."
    )


__all__ = ["main"]
