"""Contracts for server-owned Console scope and process configuration.

Subject: Normalization and disclosure boundaries for one configured Console scope.
Level: In-process unit contract.
Collaborators: Real Pydantic models and supplied environment mappings; no process environment or database.
Guarantees: Required identity, isolation, secret handling, and bounded pool settings fail closed.
Non-goals: Request authentication, database connectivity, gateway routing, and broker-account attestation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from trader_console_api import (
    BrokerAccountBinding,
    ConsoleApiSettings,
    ConsoleConfigurationError,
    ConsoleEnvironment,
    ConsoleScope,
)


def test_environment_settings_normalize_one_paper_scope_without_exposing_dsn() -> None:
    """Normalize server values while keeping connection secrets outside public scope data."""
    settings = ConsoleApiSettings.from_environment(
        {
            "TRADER_CONSOLE_DATABASE_URL": "postgresql://local:secret@db/trader",
            "TRADER_CONSOLE_SCOPE_ID": "paper-primary",
            "TRADER_CONSOLE_SCOPE_DISPLAY_NAME": "Primary paper account",
            "TRADER_CONSOLE_SCOPE_ENVIRONMENT": "paper",
            "TRADER_CONSOLE_BROKER_ACCOUNT_DISPLAY_LABEL": "Paper A",
            "TRADER_CONSOLE_PRESENTATION_TIMEZONE": "Europe/London",
            "TRADER_CONSOLE_POOL_MAX_SIZE": "6",
            "TRADER_CONSOLE_STATEMENT_TIMEOUT_MS": "1500",
        }
    )

    assert settings.scope.scope_id == "paper-primary"
    assert settings.scope.environment is ConsoleEnvironment.PAPER
    assert settings.scope.broker_account_binding is BrokerAccountBinding.CONFIGURED
    assert settings.pool_max_size == 6
    assert settings.statement_timeout_ms == 1_500
    assert "secret" not in repr(settings)
    assert "database_url" not in settings.scope.model_dump()


def test_environment_settings_require_database_and_scope_identity() -> None:
    """Fail startup configuration when server-owned database identity is absent."""
    with pytest.raises(
        ConsoleConfigurationError,
        match="TRADER_CONSOLE_DATABASE_URL",
    ):
        ConsoleApiSettings.from_environment(
            {
                "TRADER_CONSOLE_SCOPE_ID": "paper-primary",
                "TRADER_CONSOLE_SCOPE_ENVIRONMENT": "paper",
            }
        )


def test_non_paper_scope_rejects_a_broker_account_binding() -> None:
    """Prevent backtest evidence from claiming an external brokerage-account binding."""
    with pytest.raises(ValidationError, match="do not have a broker-account binding"):
        ConsoleScope(
            scope_id="backtest-local",
            display_name="Backtest",
            environment=ConsoleEnvironment.BACKTEST,
            broker_account_binding=BrokerAccountBinding.CONFIGURED,
        )


def test_scope_rejects_unknown_fields_and_invalid_timezone() -> None:
    """Keep client-like overrides and ambiguous presentation timezones outside the scope model."""
    with pytest.raises(ValidationError):
        ConsoleScope.model_validate(
            {
                "scope_id": "paper-primary",
                "display_name": "Paper",
                "environment": "paper",
                "broker_account_binding": "configured",
                "presentation_timezone": "London-ish",
                "database_url": "postgresql://must-not-be-here",
            }
        )


def test_settings_reject_unbounded_or_inverted_pool_configuration() -> None:
    """Reject pool settings that exceed the scaffold's explicit resource bounds."""
    with pytest.raises(ValidationError, match="pool_min_size"):
        ConsoleApiSettings.from_environment(
            {
                "TRADER_CONSOLE_DATABASE_URL": "postgresql://local/db",
                "TRADER_CONSOLE_SCOPE_ID": "demo",
                "TRADER_CONSOLE_SCOPE_ENVIRONMENT": "synthetic_demo",
                "TRADER_CONSOLE_POOL_MIN_SIZE": "5",
                "TRADER_CONSOLE_POOL_MAX_SIZE": "4",
            }
        )
