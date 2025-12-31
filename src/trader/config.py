"""Configuration loader for the trading system."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    mode: str
    strategy_id: str
    db_path: str


def load_config() -> Config:
    """Load configuration from environment variables with safe defaults."""
    return Config(
        mode=os.getenv("MODE", "once"),
        strategy_id=os.getenv("STRATEGY_ID", "noop"),
        db_path=os.getenv("DB_PATH", "events.duckdb"),
    )
