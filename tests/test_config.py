"""Tests for configuration defaults and normalization."""

from __future__ import annotations

from trader.config import build_config


def test_build_config_uses_strategy_id_as_default_type() -> None:
    config = build_config(
        {
            "strategy": {
                "id": "toggle",
            }
        }
    )

    assert config.strategy_type == "toggle"
    assert config.strategy_id == "toggle"


def test_build_config_prefers_explicit_strategy_id_and_type() -> None:
    config = build_config(
        {
            "strategy": {
                "type": "custom_toggle",
                "id": "toggle_v2",
            }
        }
    )

    assert config.strategy_type == "custom_toggle"
    assert config.strategy_id == "toggle_v2"
