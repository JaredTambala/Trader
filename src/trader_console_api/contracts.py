"""Public value contracts for the Trader Console API."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConsoleEnvironment(StrEnum):
    """Execution environment represented by one isolated Console scope."""

    PAPER = "paper"
    BACKTEST = "backtest"
    SYNTHETIC_DEMO = "synthetic_demo"


class BrokerAccountBinding(StrEnum):
    """Evidence level for the scope's configured brokerage binding."""

    CONFIGURED = "configured"
    NOT_APPLICABLE = "not_applicable"


class TraderPrincipal(BaseModel):
    """Authenticated Trader-platform identity supplied by a future gateway.

    This is deliberately separate from brokerage-account identity and does not
    imply a Trader-owned user table.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    principal_id: str = Field(min_length=1, max_length=200)


class ConsoleScope(BaseModel):
    """Safe public description of one server-configured API scope.

    The database URL and brokerage provider reference are deliberately absent.
    One API process serves one scope backed by one isolated database.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    display_name: str = Field(min_length=1, max_length=200)
    environment: ConsoleEnvironment
    data_source_kind: Literal["postgresql"] = "postgresql"
    isolation_kind: Literal["isolated_database"] = "isolated_database"
    broker_account_display_label: str | None = Field(default=None, max_length=200)
    broker_account_binding: BrokerAccountBinding
    presentation_timezone: str = "UTC"

    @field_validator("presentation_timezone")
    @classmethod
    def validate_presentation_timezone(cls, value: str) -> str:
        """Require an IANA timezone without retaining a mutable timezone object."""
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("presentation_timezone must be an IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_broker_account_binding(self) -> ConsoleScope:
        """Keep paper brokerage bindings distinct from non-broker scopes."""
        if (
            self.environment is ConsoleEnvironment.PAPER
            and self.broker_account_binding is not BrokerAccountBinding.CONFIGURED
        ):
            raise ValueError("paper scopes require a configured broker-account binding")
        if (
            self.environment is not ConsoleEnvironment.PAPER
            and self.broker_account_binding is not BrokerAccountBinding.NOT_APPLICABLE
        ):
            raise ValueError(
                "backtest and synthetic-demo scopes do not have a broker-account binding"
            )
        return self


class LivenessResponse(BaseModel):
    """Process-liveness response that makes no database or trading claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["alive"] = "alive"
    service: Literal["trader-console-api"] = "trader-console-api"


class ReadinessResponse(BaseModel):
    """Database readiness without trading-health or IAM claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "unavailable"]
    scope_id: str
    contract_version: int | None = None
    issues: tuple[str, ...] = ()
