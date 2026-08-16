"""Expose read-only experiment evidence to independent review services.

The reader loads canonical plans, runs, trials, and backtests through integrity-
checking query paths. It grants no persistence or experiment-execution authority
to Evaluation or Adversarial callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence, Any

from trader_research.foundation.artifacts import ResearchArtifactStore, load_artifact_ref
from trader_research.governance.artifacts import BACKTEST_RUN

from .optimization.ledger import (
    load_validated_parameter_optimization_plan,
    load_validated_parameter_optimization_run,
)


class ExperimentEvidenceReader(Protocol):
    """Read-only port for canonical evidence needed by Review services."""

    def load_backtest_run(self, reference: str) -> Mapping[str, Any]:
        """Load one canonical backtest run without exposing execution services."""

    def load_parameter_optimization_plan(
        self, reference: str
    ) -> Mapping[str, Any]:
        """Load and revalidate one immutable optimization plan."""

    def load_parameter_optimization_run(
        self, reference: str
    ) -> tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]:
        """Load and revalidate one run and its complete ordered trial ledger."""


@dataclass(frozen=True)
class StoreBackedExperimentEvidenceReader:
    """Research-artifact-store adapter for immutable experiment reads."""

    store: ResearchArtifactStore

    def load_backtest_run(self, reference: str) -> Mapping[str, Any]:
        """Load one canonical backtest run by ID or research URI."""
        payload = load_artifact_ref(self.store, BACKTEST_RUN, reference)
        if payload.get("artifact_type") != BACKTEST_RUN:
            raise ValueError("backtest evidence must be a backtest_run")
        if not str(payload.get("run_id") or ""):
            raise ValueError("backtest evidence is missing run_id")
        return payload

    def load_parameter_optimization_plan(
        self, reference: str
    ) -> Mapping[str, Any]:
        """Load a plan only after all sealed inputs revalidate."""
        plan, _, _ = load_validated_parameter_optimization_plan(self.store, reference)
        return plan

    def load_parameter_optimization_run(
        self, reference: str
    ) -> tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]:
        """Load a run only after plan, trials, selection, and lineage revalidate."""
        return load_validated_parameter_optimization_run(self.store, reference)


__all__ = ["ExperimentEvidenceReader", "StoreBackedExperimentEvidenceReader"]
