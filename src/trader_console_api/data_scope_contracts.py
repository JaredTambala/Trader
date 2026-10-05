"""Typed contracts for exact, reusable market-data scopes."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DataScopeEvidenceStatus(StrEnum):
    """Current qualification state of the referenced Data evidence."""

    ACTIVE = "active"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class DataScopeSourcePolicy(BaseModel):
    """Provider and source policy frozen into a saved data scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=100)
    source: str | None = Field(default=None, max_length=100)
    allow_fallback: bool = False


class BacktestDataScopeHandoff(BaseModel):
    """Exact saved Data evidence handed into backtest authoring.

    The handoff repeats the immutable scope identity and evidence references so
    a preflight can detect a stale client or a changed selection.  The server
    resolves ``saved_scope_id`` and never widens the selection to a new
    catalogue or aggregate coverage query.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    saved_scope_id: UUID
    fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    asset_class: Literal["stock", "crypto"]
    symbols: tuple[str, ...] = Field(min_length=1, max_length=200)
    universe: str | None = Field(default=None, max_length=200)
    timeframe: str = Field(min_length=1, max_length=32)
    interval: str = Field(min_length=1, max_length=32)
    start: datetime
    end: datetime
    source_policy: DataScopeSourcePolicy
    manifest_artifact_id: str = Field(min_length=1, max_length=200)
    quality_artifact_id: str = Field(min_length=1, max_length=200)
    evidence_status: DataScopeEvidenceStatus
    evidence_reason: str | None = Field(default=None, max_length=500)

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Use the same canonical symbol representation as saved scopes."""
        normalized = tuple(sorted({str(symbol).strip().upper() for symbol in value if str(symbol).strip()}))
        if not normalized:
            raise ValueError("symbols must contain at least one non-empty symbol")
        return normalized

    @field_validator("start", "end")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        """Require timezone-aware timestamps and normalize them to UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scope timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_window_and_evidence(self) -> BacktestDataScopeHandoff:
        """Reject reversed windows and unexplained non-active evidence."""
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if self.evidence_status is not DataScopeEvidenceStatus.ACTIVE and not self.evidence_reason:
            raise ValueError("evidence_reason is required for stale or unavailable evidence")
        return self


class SavedDataScopeCreate(BaseModel):
    """Request to persist one exact Data evidence handoff."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=120)
    asset_class: Literal["stock", "crypto"]
    symbols: tuple[str, ...] = Field(min_length=1, max_length=200)
    universe: str | None = Field(default=None, max_length=200)
    timeframe: str = Field(min_length=1, max_length=32)
    interval: str = Field(min_length=1, max_length=32)
    start: datetime
    end: datetime
    source_policy: DataScopeSourcePolicy
    research_role: str = Field(min_length=1, max_length=100)
    manifest_artifact_id: str = Field(min_length=1, max_length=200)
    quality_artifact_id: str = Field(min_length=1, max_length=200)
    evidence_status: DataScopeEvidenceStatus = DataScopeEvidenceStatus.ACTIVE
    evidence_reason: str | None = Field(default=None, max_length=500)
    created_by: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Normalize symbols into one deterministic, duplicate-free tuple."""
        normalized = tuple(sorted({str(symbol).strip().upper() for symbol in value if str(symbol).strip()}))
        if not normalized:
            raise ValueError("symbols must contain at least one non-empty symbol")
        return normalized

    @field_validator("start", "end")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        """Normalize aware timestamps to UTC before hashing or persistence."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scope timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_window_and_evidence(self) -> SavedDataScopeCreate:
        """Reject reversed windows and incomplete evidence explanations."""
        if self.end < self.start:
            raise ValueError("end must not precede start")
        if self.evidence_status is not DataScopeEvidenceStatus.ACTIVE and not self.evidence_reason:
            raise ValueError("evidence_reason is required for stale or unavailable evidence")
        return self


class SavedDataScope(BaseModel):
    """Immutable scope identity plus revalidated evidence state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    saved_scope_id: UUID
    scope_id: str
    revision: Literal[1] = 1
    fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    name: str
    asset_class: Literal["stock", "crypto"]
    symbols: tuple[str, ...]
    universe: str | None = None
    timeframe: str
    interval: str
    start: datetime
    end: datetime
    source_policy: DataScopeSourcePolicy
    research_role: str
    manifest_artifact_id: str
    quality_artifact_id: str
    evidence_status: DataScopeEvidenceStatus
    evidence_reason: str | None = None
    created_by: str
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class SavedDataScopesResponse(BaseModel):
    """Bounded page of saved exact data scopes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[SavedDataScope, ...]
    page: "DataScopePageInfo"


class DataScopePageInfo(BaseModel):
    """Pagination evidence for saved scope collections."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)
    has_more: bool


SavedDataScopesResponse.model_rebuild()


__all__ = [
    "BacktestDataScopeHandoff",
    "DataScopeEvidenceStatus",
    "DataScopePageInfo",
    "DataScopeSourcePolicy",
    "SavedDataScope",
    "SavedDataScopeCreate",
    "SavedDataScopesResponse",
]
