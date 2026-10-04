"""Validated user-authored comparison definitions and current eligibility."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .contracts import PageInfo

RunId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
MetricKey = Literal[
    "strategy_total_return", "benchmark_total_return", "strategy_max_drawdown",
    "benchmark_max_drawdown", "strategy_sharpe", "strategy_trade_count", "warnings_count",
]
SeriesKey = Literal[
    "strategy_normalized", "benchmark_normalized", "strategy_drawdown", "benchmark_drawdown",
]


class ComparisonViewDefinition(BaseModel):
    """User intent only; unknown keys and duplicate selections are rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    run_ids: tuple[RunId, ...] = Field(default=(), max_length=20)
    reference_run_id: RunId | None = None
    metric_keys: tuple[MetricKey, ...] = Field(default=("strategy_total_return",), max_length=7)
    series_keys: tuple[SeriesKey, ...] = Field(default=("strategy_normalized",), max_length=4)

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        """Require unique keys and an explicit reference for nonempty selections."""
        for name in ("run_ids", "metric_keys", "series_keys"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must contain unique values")
        if self.run_ids:
            if self.reference_run_id not in self.run_ids:
                raise ValueError("reference_run_id must be one of run_ids")
        elif self.reference_run_id is not None:
            raise ValueError("empty selections require a null reference_run_id")
        if not self.metric_keys and not self.series_keys:
            raise ValueError("select at least one metric or series")
        return self


class ComparisonViewUpdate(ComparisonViewDefinition):
    """Complete replacement guarded against lost edits."""

    expected_revision: int = Field(ge=1, strict=True)


class SavedComparisonView(BaseModel):
    """Durable definition with server-owned identity and revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    view_id: UUID
    scope_id: str
    experiment_id: str
    definition_version: Literal[1] = 1
    definition: ComparisonViewDefinition
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class ComparisonRunEligibility(BaseModel):
    """Current eligibility of one selected ID; excluded IDs retain their reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    eligible: bool
    exclusion_reason: str | None = None
    scope_fingerprint: str | None = None


class ComparisonEvaluation(BaseModel):
    """Live admission result, independent of the saved definition's revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["empty", "unavailable", "one_run", "ready"]
    eligible_run_ids: tuple[str, ...]
    runs: tuple[ComparisonRunEligibility, ...]


class ComparisonViewDetail(BaseModel):
    """Saved intent and its freshly evaluated exclusions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    view: SavedComparisonView
    evaluation: ComparisonEvaluation


class ComparisonViewsResponse(BaseModel):
    """A bounded page of definitions without live evidence queries per item."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[SavedComparisonView, ...]
    page: PageInfo
