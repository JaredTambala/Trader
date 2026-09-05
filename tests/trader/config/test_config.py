"""Define how strategy identity is normalized at the configuration boundary.

Subject: Relationship between configured strategy identifiers and implementation types.
Level: Deterministic configuration-boundary unit tests.
Collaborators: The real configuration parser with minimal in-memory mappings.
Guarantees: Missing types default predictably while explicit identifiers and types remain distinct.
Non-goals: YAML loading, environment overrides, strategy construction, or runtime execution.
"""

from __future__ import annotations

from trader.config import build_config


def test_build_config_uses_strategy_id_as_default_type() -> None:
    """Use the strategy identifier as its implementation type when type is omitted."""
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
    """Preserve independently configured strategy identity and implementation type values."""
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
