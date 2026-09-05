"""Cycle logging-filter and startup-diagnostic configuration contracts.

Subject: Event persistence allowlists and secret-safe startup configuration projections.
Level: Deterministic configuration-boundary unit contracts.
Collaborators: Real cycle filter/startup helpers and package-owned temporary configuration values.
Guarantees: Logging flags select event types and diagnostic values never expose raw credentials.
Non-goals: Logger output, event writes, environment parsing, or provider authentication.
"""

from __future__ import annotations

from dataclasses import replace

from tests.trader.cycle.factories import build_cycle_config as _base_config
from trader.cycle.filters import _allowed_cycle_event_types
from trader.cycle.startup import _mask_secret, _startup_config_log_values


def test_allowed_cycle_event_types_respects_logging_flags(tmp_path) -> None:
    """Retain mandatory lifecycle tables while filtering optional diagnostic event types."""
    config = _base_config(str(tmp_path / "events.duckdb"))

    assert _allowed_cycle_event_types(config) == {
        "runs",
        "run_events",
        "stock_bar_events",
        "crypto_bar_events",
        "config_kv",
        "signal_events",
        "indicator_events",
        "prediction_events",
        "order_events",
        "fill_events",
        "position_snapshots",
    }

    quiet = replace(
        config,
        log_signal_events=False,
        log_indicator_events=False,
        log_order_events=False,
        log_fill_events=False,
        log_position_snapshots=False,
    )

    assert _allowed_cycle_event_types(quiet) == {
        "runs",
        "run_events",
        "stock_bar_events",
        "crypto_bar_events",
        "config_kv",
        "prediction_events",
    }


def test_startup_config_log_values_mask_secrets(tmp_path) -> None:
    """Expose useful startup configuration while masking every credential-bearing value."""
    config = replace(
        _base_config(str(tmp_path / "events.duckdb")),
        alpaca_api_key="abcdefghijkl",
        alpaca_secret_key="short",
        pg_dsn="postgres://user:password@example/db",
        pg_password="",
    )

    values = _startup_config_log_values(config)

    assert _mask_secret(None) == "<unset>"
    assert _mask_secret("short") == "*****"
    assert _mask_secret("abcdefghijkl") == "abcd***ijkl"
    assert values["alpaca_api_key"] == "abcd***ijkl"
    assert values["alpaca_secret_key"] == "*****"
    assert values["pg_dsn"] == "post***e/db"
    assert values["pg_password"] == "<unset>"
    assert values["market_data_symbols"] == "AAPL"
