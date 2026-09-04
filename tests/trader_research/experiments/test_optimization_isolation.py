"""Contracts for optimisation objective and strategy isolation policy.

Subject: Closed observations, tunable paths, source safety, dependency authority, timeouts, and failures.
Level: Offline application and security contract.
Collaborators: In-memory artifacts, supplied Python source, and deterministic executor doubles.
Guarantees: Undeclared data and escape surfaces fail closed with bounded diagnostic evidence.
Non-goals: Trial selection quality, tracking projection, Postgres, Optuna, or live execution.
"""

from __future__ import annotations

import pytest

from tests.trader_research.experiments.optimization_fixtures import (
    FakeExecutor,
    HugeFailureExecutor,
    _base_validations,
    _manifest,
    _plan,
    _quality,
)
from trader_research.experiments import (
    OptimizationObservation,
    create_parameter_optimization_plan,
    register_optimization_objective,
    register_strategy_implementation,
    run_parameter_optimization,
    validate_optimization_objective,
    validate_strategy_implementation,
)
from trader_research.foundation.artifacts import InMemoryResearchArtifactStore


def test_closed_observation_and_plan_reject_undeclared_inputs() -> None:
    """Closed observations and plans reject undeclared fields and non-tunable paths."""
    with pytest.raises(ValueError, match="undeclared fields"):
        OptimizationObservation.from_mapping(
            {
                "schema_version": "1.0",
                "status": "passed",
                "metrics": {},
                "counts": {},
                "costs": {},
                "exposure": {},
                "risk": {},
                "quality": {},
                "constraints": {},
                "lineage": {},
                "raw_events": [],
            }
        )

    store = InMemoryResearchArtifactStore()
    base_validation_id, objective_validation_id = _base_validations(store)
    rejected = create_parameter_optimization_plan(
        base_backtest_specification_validation_ref=base_validation_id,
        holdout_dataset_manifest=_manifest(
            "holdout", "2025-02-01T00:00:00+00:00", "2025-02-28T00:00:00+00:00"
        ),
        holdout_data_quality_report=_quality(
            "2025-02-01T00:00:00+00:00", "2025-02-28T00:00:00+00:00"
        ),
        objective_validation_ref=objective_validation_id,
        search_space=[
            {"path": "/dataset/time_range/end", "type": "integer", "low": 1, "high": 2}
        ],
        artifact_store=store,
    )
    assert rejected.ok is False
    assert "not explicitly tunable" in rejected.errors[0]["message"]


def test_objective_validation_rejects_filesystem_and_indirect_builtin_access() -> None:
    """Objective validation blocks filesystem access, top-level execution, and non-finite results."""
    store = InMemoryResearchArtifactStore()
    unsafe = register_optimization_objective(
        name="unsafe",
        version="1",
        source_code="""
def objective(observation):
    opener = open
    return opener("/tmp/objective-output", "w")
""",
        factory_name="objective",
        artifact_store=store,
    )
    validation = validate_optimization_objective(
        implementation_version_id=unsafe.data["implementation_version"][
            "implementation_version_id"
        ],
        artifact_store=store,
    )
    assert validation.ok is False
    report = validation.data["implementation_validation_report"]
    assert any(
        "unsafe objective name is not allowed: open" in blocker
        for blocker in report["blockers"]
    )

    top_level = register_optimization_objective(
        name="top-level",
        version="1",
        source_code="value = 1\n\ndef objective(observation):\n    return value\n",
        factory_name="objective",
        artifact_store=store,
    )
    top_level_validation = validate_optimization_objective(
        implementation_version_id=top_level.data["implementation_version"][
            "implementation_version_id"
        ],
        artifact_store=store,
    )
    assert top_level_validation.ok is False
    assert "executable top-level statement" in top_level_validation.errors[0]["message"]

    non_finite = register_optimization_objective(
        name="non-finite",
        version="1",
        source_code="def objective(observation):\n    return float('nan')\n",
        factory_name="objective",
        artifact_store=store,
    )
    non_finite_validation = validate_optimization_objective(
        implementation_version_id=non_finite.data["implementation_version"][
            "implementation_version_id"
        ],
        artifact_store=store,
    )
    assert non_finite_validation.ok is False
    assert "finite numeric value" in non_finite_validation.errors[0]["message"]


@pytest.mark.parametrize(
    ("source_code", "blocker"),
    [
        (
            "import pathlib\n\ndef objective(observation):\n    return 1.0\n",
            "import is not allowed: pathlib",
        ),
        (
            "import socket\n\ndef objective(observation):\n    return 1.0\n",
            "import is not allowed: socket",
        ),
        (
            "import psycopg\n\ndef objective(observation):\n    return 1.0\n",
            "import is not allowed: psycopg",
        ),
        (
            "import subprocess\n\ndef objective(observation):\n    return 1.0\n",
            "import is not allowed: subprocess",
        ),
        (
            "import statistics\n\ndef objective(observation):\n"
            "    return statistics.sys.modules['os'].getcwd()\n",
            "import is not allowed: statistics",
        ),
        (
            "import typing\n\ndef objective(observation):\n"
            "    return typing.sys.modules['os'].getcwd()\n",
            "import is not allowed: typing",
        ),
        (
            "from trader_mcp import server\n\ndef objective(observation):\n    return 1.0\n",
            "import is not allowed: trader_mcp",
        ),
        (
            "def objective(observation):\n    return globals()\n",
            "unsafe name is not allowed: globals",
        ),
        (
            "def objective(observation):\n    return observation.__class__\n",
            "dunder attribute is not allowed: __class__",
        ),
    ],
)
def test_objective_validation_rejects_isolation_escape_surfaces(
    source_code: str,
    blocker: str,
) -> None:
    """Objective validation rejects imports, globals, and attributes that escape isolation."""
    store = InMemoryResearchArtifactStore()
    implementation = register_optimization_objective(
        name="unsafe-isolation-objective",
        version="1",
        source_code=source_code,
        factory_name="objective",
        dependencies=["psycopg", "requests"],
        artifact_store=store,
    )
    validation = validate_optimization_objective(
        implementation_version_id=implementation.data["implementation_version"][
            "implementation_version_id"
        ],
        artifact_store=store,
    )

    assert validation.ok is False
    assert blocker in validation.data["implementation_validation_report"]["blockers"]


@pytest.mark.parametrize(
    ("source_code", "blocker"),
    [
        (
            """
import psycopg
from trader.strategies import Strategy

class UnsafeStrategy(Strategy):
    @property
    def strategy_id(self):
        return "unsafe"

    def generate_orders(self, **kwargs):
        return ()

def build_strategy(**kwargs):
    return UnsafeStrategy()
""",
            "import is not allowed: psycopg",
        ),
        (
            """
from trader.strategies import Strategy

class UnsafeStrategy(Strategy):
    @property
    def strategy_id(self):
        return "unsafe"

    def generate_orders(self, *, event_store, **kwargs):
        event_store.connection().execute("DELETE FROM research_artifacts")
        return ()

def build_strategy(**kwargs):
    return UnsafeStrategy()
""",
            "unsafe attribute call is not allowed: connection",
        ),
        (
            """
from trader.broker import AlpacaPaperBroker
from trader.strategies import Strategy

class UnsafeStrategy(Strategy):
    @property
    def strategy_id(self):
        return "unsafe"

    def generate_orders(self, **kwargs):
        return ()

def build_strategy(**kwargs):
    return UnsafeStrategy()
""",
            "import is not allowed: trader.broker",
        ),
        (
            """
from trader import event_store
from trader.strategies import Strategy

class UnsafeStrategy(Strategy):
    @property
    def strategy_id(self):
        return "unsafe"

    def generate_orders(self, **kwargs):
        return ()

def build_strategy(**kwargs):
    return UnsafeStrategy()
""",
            "import is not allowed: trader.event_store",
        ),
        (
            """
import trader
from trader.strategies import Strategy

class UnsafeStrategy(Strategy):
    @property
    def strategy_id(self):
        return "unsafe"

    def generate_orders(self, **kwargs):
        return ()

def build_strategy(**kwargs):
    return UnsafeStrategy()
""",
            "broad import is not allowed: trader",
        ),
        (
            """
from trader.strategies import Strategy

class UnsafeStrategy(Strategy):
    @property
    def strategy_id(self):
        return self.__class__.__name__

    def generate_orders(self, **kwargs):
        return ()

def build_strategy(**kwargs):
    return UnsafeStrategy()
""",
            "dunder attribute is not allowed: __class__",
        ),
    ],
)
def test_strategy_dependencies_cannot_grant_database_or_broker_access(
    source_code: str,
    blocker: str,
) -> None:
    """Declared dependencies cannot grant strategy code database or broker authority."""
    store = InMemoryResearchArtifactStore()
    implementation = register_strategy_implementation(
        name="unsafe-strategy",
        version="1",
        source_code=source_code,
        factory_name="build_strategy",
        dependencies=["psycopg", "alpaca-py"],
        artifact_store=store,
    )
    validation = validate_strategy_implementation(
        implementation_version_id=implementation.data["implementation_version"][
            "implementation_version_id"
        ],
        artifact_store=store,
    )

    assert validation.ok is False
    assert blocker in validation.data["implementation_validation_report"]["blockers"]


def test_trial_timeout_requires_enforcement_and_oversized_failures_are_bounded() -> (
    None
):
    """Trial execution requires enforceable deadlines and truncates oversized failure evidence."""
    timeout_store = InMemoryResearchArtifactStore()
    timeout_plan = _plan(
        timeout_store,
        resource_limits={
            "max_trial_attempts": 1,
            "per_trial_timeout_seconds": 0.001,
        },
    )
    timed_out = run_parameter_optimization(
        optimization_plan_ref=timeout_plan["optimization_plan_id"],
        optimizer_profile="builtin_grid",
        trial_executor=FakeExecutor(),
        artifact_store=timeout_store,
    )
    assert timed_out.ok is False
    timeout_trials = timed_out.data["new_trials"]
    assert len(timeout_trials) == 2
    assert all(trial["status"] == "blocked" for trial in timeout_trials)
    assert all(
        trial["blockers"] == ["trial executor cannot enforce per_trial_timeout_seconds"]
        for trial in timeout_trials
    )

    failure_store = InMemoryResearchArtifactStore()
    failure_plan = _plan(failure_store)
    failed = run_parameter_optimization(
        optimization_plan_ref=failure_plan["optimization_plan_id"],
        optimizer_profile="builtin_grid",
        trial_executor=HugeFailureExecutor(),
        artifact_store=failure_store,
    )
    assert failed.ok is False
    for trial in failed.data["new_trials"]:
        blocker = trial["blockers"][0]
        assert len(blocker) == 2_000
        assert blocker.endswith("...[truncated]")
        assert trial["attempts"][0]["exception"] == blocker
