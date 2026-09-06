"""Normalized server-owned configuration for the Trader Console API."""

from __future__ import annotations

from collections.abc import Mapping
import os

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from .contracts import BrokerAccountBinding, ConsoleEnvironment, ConsoleScope


class ConsoleConfigurationError(RuntimeError):
    """Raised when required server configuration is absent."""


class ConsoleApiSettings(BaseModel):
    """Validated process settings for one isolated Console scope.

    Attributes:
        database_url: Local DSN baseline or value supplied by deployment
            composition. It is never part of a response model.
        scope: Safe server-owned scope description.
        pool_min_size: Connections opened when the pool starts.
        pool_max_size: Hard upper bound for pooled connections.
        pool_timeout_seconds: Maximum request wait for a connection.
        pool_open_timeout_seconds: Maximum initial pool-open wait.
        pool_close_timeout_seconds: Maximum graceful pool-close wait.
        statement_timeout_ms: PostgreSQL statement timeout applied locally to
            every repository transaction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    database_url: SecretStr
    scope: ConsoleScope
    pool_min_size: int = Field(default=1, ge=1, le=16)
    pool_max_size: int = Field(default=4, ge=1, le=32)
    pool_timeout_seconds: float = Field(default=3.0, gt=0, le=60)
    pool_open_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    pool_close_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    statement_timeout_ms: int = Field(default=2_000, ge=100, le=60_000)

    @model_validator(mode="after")
    def validate_pool_bounds(self) -> ConsoleApiSettings:
        """Reject a minimum pool size larger than its hard cap."""
        if self.pool_min_size > self.pool_max_size:
            raise ValueError("pool_min_size must not exceed pool_max_size")
        return self

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> ConsoleApiSettings:
        """Build settings from the local environment configuration baseline.

        Args:
            environment: Optional mapping used instead of ``os.environ``.

        Returns:
            Fully normalized immutable settings.

        Raises:
            ConsoleConfigurationError: If a required setting is missing.
            ValueError: If a supplied setting violates the typed contract.
        """
        values = os.environ if environment is None else environment
        database_url = _required(values, "TRADER_CONSOLE_DATABASE_URL")
        scope_id = _required(values, "TRADER_CONSOLE_SCOPE_ID")
        scope_environment = ConsoleEnvironment(
            _required(values, "TRADER_CONSOLE_SCOPE_ENVIRONMENT")
        )
        broker_binding = (
            BrokerAccountBinding.CONFIGURED
            if scope_environment is ConsoleEnvironment.PAPER
            else BrokerAccountBinding.NOT_APPLICABLE
        )
        scope = ConsoleScope(
            scope_id=scope_id,
            display_name=values.get("TRADER_CONSOLE_SCOPE_DISPLAY_NAME", scope_id),
            environment=scope_environment,
            broker_account_display_label=values.get(
                "TRADER_CONSOLE_BROKER_ACCOUNT_DISPLAY_LABEL"
            ),
            broker_account_binding=broker_binding,
            presentation_timezone=values.get(
                "TRADER_CONSOLE_PRESENTATION_TIMEZONE", "UTC"
            ),
        )
        return cls(
            database_url=SecretStr(database_url),
            scope=scope,
            pool_min_size=_integer(values, "TRADER_CONSOLE_POOL_MIN_SIZE", 1),
            pool_max_size=_integer(values, "TRADER_CONSOLE_POOL_MAX_SIZE", 4),
            pool_timeout_seconds=_number(
                values, "TRADER_CONSOLE_POOL_TIMEOUT_SECONDS", 3.0
            ),
            pool_open_timeout_seconds=_number(
                values, "TRADER_CONSOLE_POOL_OPEN_TIMEOUT_SECONDS", 10.0
            ),
            pool_close_timeout_seconds=_number(
                values, "TRADER_CONSOLE_POOL_CLOSE_TIMEOUT_SECONDS", 5.0
            ),
            statement_timeout_ms=_integer(
                values, "TRADER_CONSOLE_STATEMENT_TIMEOUT_MS", 2_000
            ),
        )


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ConsoleConfigurationError(f"{name} must be set for Console API startup")
    return value


def _integer(environment: Mapping[str, str], name: str, default: int) -> int:
    value = environment.get(name)
    try:
        return default if value is None else int(value)
    except ValueError as exc:
        raise ConsoleConfigurationError(f"{name} must be an integer") from exc


def _number(environment: Mapping[str, str], name: str, default: float) -> float:
    value = environment.get(name)
    try:
        return default if value is None else float(value)
    except ValueError as exc:
        raise ConsoleConfigurationError(f"{name} must be a number") from exc
