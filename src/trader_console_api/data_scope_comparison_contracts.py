"""Read contracts for comparing saved market-data alternatives.

The comparison boundary deliberately keeps each saved scope and its producer
evidence separate.  It can explain why a pair is excluded, but it never
selects a preferred provider or combines bars from different scopes.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .contracts import MarketDataEvidenceResponse
from .data_scope_contracts import SavedDataScope

DataComparisonDimension = Literal["source", "window"]
DataComparisonState = Literal["ready", "partial", "unavailable"]


class DataScopeComparisonRequest(BaseModel):
    """Select two or more immutable scopes and allowed comparison dimensions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    saved_scope_ids: tuple[UUID, ...] = Field(min_length=2, max_length=8)
    comparison_dimensions: tuple[DataComparisonDimension, ...] = Field(
        default=("source", "window"), min_length=1, max_length=2
    )

    @field_validator("saved_scope_ids")
    @classmethod
    def require_unique_scopes(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        """Reject duplicate selections rather than implying a comparison."""
        if len(value) != len(set(value)):
            raise ValueError("saved_scope_ids must contain unique scopes")
        return value

    @field_validator("comparison_dimensions")
    @classmethod
    def require_unique_dimensions(
        cls, value: tuple[DataComparisonDimension, ...]
    ) -> tuple[DataComparisonDimension, ...]:
        """Reject duplicate dimension declarations."""
        if len(value) != len(set(value)):
            raise ValueError("comparison_dimensions must contain unique dimensions")
        return value


class DataScopeComparisonPair(BaseModel):
    """Pairwise compatibility and differences for two selected scopes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    left_scope_id: UUID
    right_scope_id: UUID
    eligible: bool
    equal_dimensions: tuple[str, ...]
    varied_dimensions: tuple[str, ...]
    exclusion_reasons: tuple[str, ...] = ()
    differences: dict[str, Any] = Field(default_factory=dict)


class DataScopeComparisonAlternative(BaseModel):
    """One selected scope with its independent evidence and pair exclusions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: SavedDataScope
    evidence: MarketDataEvidenceResponse
    eligible: bool
    exclusion_reasons: tuple[str, ...] = ()


class DataScopeComparisonResponse(BaseModel):
    """A reviewable comparison that never merges alternative evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: DataComparisonState
    comparison_dimensions: tuple[DataComparisonDimension, ...]
    alternatives: tuple[DataScopeComparisonAlternative, ...]
    pairs: tuple[DataScopeComparisonPair, ...]
    comparable_pair_count: int = Field(ge=0)
    excluded_pair_count: int = Field(ge=0)


__all__ = [
    "DataComparisonDimension",
    "DataComparisonState",
    "DataScopeComparisonAlternative",
    "DataScopeComparisonPair",
    "DataScopeComparisonRequest",
    "DataScopeComparisonResponse",
]
