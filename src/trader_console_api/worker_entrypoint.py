"""Run the local Console backtest worker against explicitly installed storage."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from trader.config import build_config, load_yaml_config

from .backtest_executor import BacktestDefinitionExecutor
from .configuration import ConsoleApiSettings
from .repositories.backtest_executions import BacktestExecutionRepository
from .repositories.database import ConsoleDatabase, create_connection_pool
from .worker import BacktestExecutionWorker


def _positive_env(name: str, default: int, maximum: int) -> int:
    """Read one bounded positive integer from the worker environment."""
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1 or value > maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


async def _run(*, once: bool, worker_id: str, lease_seconds: int, poll_seconds: int) -> None:
    """Open one local pool and process commands until interrupted or drained."""
    settings = ConsoleApiSettings.from_environment()
    config_path = os.environ.get("TRADER_CONSOLE_BACKTEST_CONFIG_PATH") or os.environ.get(
        "BACKEND_CONFIG_PATH"
    )
    if not config_path:
        raise ValueError(
            "Set TRADER_CONSOLE_BACKTEST_CONFIG_PATH to a core Trader YAML config"
        )
    config = build_config(load_yaml_config(Path(config_path)))
    pool = create_connection_pool(settings)
    database = ConsoleDatabase(pool, settings)
    repository = BacktestExecutionRepository(database, settings.scope.scope_id)
    worker = BacktestExecutionWorker(
        repository,
        BacktestDefinitionExecutor.from_config(config),
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        max_attempts=_positive_env("TRADER_CONSOLE_WORKER_MAX_ATTEMPTS", 3, 20),
    )
    await pool.open(wait=True, timeout=settings.pool_open_timeout_seconds)
    try:
        while True:
            claimed = await worker.run_once()
            if once or not claimed:
                return
            await asyncio.sleep(poll_seconds)
    finally:
        await pool.close(timeout=settings.pool_close_timeout_seconds)


def main(arguments: list[str] | None = None) -> None:
    """Run one or continuously poll the local durable execution queue."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="claim at most one command")
    options = parser.parse_args(arguments)
    worker_id = os.environ.get("TRADER_CONSOLE_WORKER_ID", "local-worker").strip()
    if not worker_id:
        parser.error("TRADER_CONSOLE_WORKER_ID must not be blank")
    try:
        asyncio.run(
            _run(
                once=options.once,
                worker_id=worker_id,
                lease_seconds=_positive_env("TRADER_CONSOLE_WORKER_LEASE_SECONDS", 60, 86_400),
                poll_seconds=_positive_env("TRADER_CONSOLE_WORKER_POLL_SECONDS", 2, 300),
            )
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
