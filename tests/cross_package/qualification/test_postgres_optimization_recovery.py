"""Postgres restart, idempotent resume, and optimization fault qualification.

Subject: Recovery across trial persistence, retry, terminal blocking, and process deadlines.
Level: Cross-package controlled qualification.
Collaborators: Research optimization services, worker subprocesses, injected faults, and Postgres artifacts.
Guarantees: Accepted trials are not duplicated and terminal outcomes survive restart unambiguously.
Non-goals: Infrastructure failover, distributed scheduling, or production throughput guarantees.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

import pytest

from trader.event_store import PostgresEventStore
from trader_research.experiments import (
    BacktestOptimizationTrialExecutor,
    TrialExecution,
    get_parameter_optimization_results,
    run_parameter_optimization,
)
from trader_research.foundation.artifacts import (
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
)
from trader_research.governance.artifacts import (
    PARAMETER_OPTIMIZATION_RUN,
    PARAMETER_OPTIMIZATION_TRIAL,
)
from trader_research.infrastructure.execution import (
    PostgresBacktestOptimizationTrialExecutor,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.cross_package.qualification.support.optimization_qualification import prepare_optimization_qualification
from tests.cross_package.qualification.support.postgres_57n import reset_57n_product_state


class InjectedWriteFailureStore:
    """Delegate store that raises at one explicit canonical write boundary."""

    backend = "postgres"

    def __init__(
        self,
        delegate: ResearchArtifactStore,
        *,
        artifact_type: str,
        after_write: bool,
        occurrence: int = 1,
    ) -> None:
        self._delegate = delegate
        self._artifact_type = artifact_type
        self._after_write = after_write
        self._occurrence = occurrence
        self._matches = 0

    def runtime_summary(self) -> Mapping[str, Any]:
        return self._delegate.runtime_summary()

    def save_artifact(
        self,
        *,
        artifact_type: str,
        artifact_id: str,
        domain_owner: str,
        producer_tool: str,
        payload: Mapping[str, Any],
        requested_by: str | None = None,
        actor: str | None = None,
        status: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        source_hash: str | None = None,
    ) -> ResearchArtifactRecord:
        matches = artifact_type == self._artifact_type
        if matches:
            self._matches += 1
        should_fail = matches and self._matches == self._occurrence
        if should_fail and not self._after_write:
            raise ResearchArtifactStoreError(
                f"injected pre-write failure for {artifact_type}"
            )
        record = self._delegate.save_artifact(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            domain_owner=domain_owner,
            producer_tool=producer_tool,
            payload=payload,
            requested_by=requested_by,
            actor=actor,
            status=status,
            metadata=metadata,
            source_hash=source_hash,
        )
        if should_fail:
            raise ResearchArtifactStoreError(
                f"injected post-write failure for {artifact_type}"
            )
        return record

    def load_artifact(self, artifact_type: str, artifact_id: str) -> Mapping[str, Any]:
        return self._delegate.load_artifact(artifact_type, artifact_id)

    def load_artifact_record(
        self, artifact_type: str, artifact_id: str
    ) -> ResearchArtifactRecord:
        return self._delegate.load_artifact_record(artifact_type, artifact_id)

    def list_artifacts(
        self,
        *,
        artifact_type: str | None = None,
        artifact_ids: Sequence[str] | None = None,
    ) -> tuple[ResearchArtifactRecord, ...]:
        return self._delegate.list_artifacts(
            artifact_type=artifact_type,
            artifact_ids=artifact_ids,
        )

    def close(self) -> None:
        return None


class FailOnceExecutor:
    """Raise once per canonical trial before delegating to the real executor."""

    executor_kind = "backtest_specification"

    def __init__(self, delegate: BacktestOptimizationTrialExecutor) -> None:
        self._delegate = delegate
        self._calls: dict[str, int] = {}

    def execute(
        self,
        *,
        plan: Mapping[str, Any],
        parameters: Mapping[str, Any],
        trial_id: str,
        optimization_run_id: str,
    ) -> TrialExecution:
        self._calls[trial_id] = self._calls.get(trial_id, 0) + 1
        if self._calls[trial_id] == 1:
            raise RuntimeError("injected transient trial failure")
        return self._delegate.execute(
            plan=plan,
            parameters=parameters,
            trial_id=trial_id,
            optimization_run_id=optimization_run_id,
        )


class MissingMetricExecutor:
    """Return terminal blocked evidence without creating child artifacts."""

    executor_kind = "missing_metric_fixture"

    def execute(
        self,
        *,
        plan: Mapping[str, Any],
        parameters: Mapping[str, Any],
        trial_id: str,
        optimization_run_id: str,
    ) -> TrialExecution:
        del plan, parameters, trial_id, optimization_run_id
        return TrialExecution(
            status="blocked",
            observation=None,
            blockers=("required objective metric is unavailable",),
        )


@pytest.mark.postgres
def test_postgres_optimization_restart_resume_and_fault_recovery(
    postgres_event_store: PostgresEventStore,
    postgres_research_artifact_store: PostgresResearchArtifactStore,
    postgres_settings: dict[str, object],
) -> None:
    """Prove restart and injected persistence faults preserve one canonical outcome."""
    baseline_plan = prepare_optimization_qualification(
        event_store=postgres_event_store,
        artifact_store=postgres_research_artifact_store,
        postgres_settings=postgres_settings,
    )
    baseline_result = _run_direct(
        baseline_plan.optimization_plan_id,
        event_store=postgres_event_store,
        artifact_store=postgres_research_artifact_store,
        config=baseline_plan.config,
    )
    baseline_run = dict(baseline_result.data["parameter_optimization_run"])
    baseline_trials = _trials(
        postgres_research_artifact_store,
        str(baseline_run["optimization_run_id"]),
    )

    _reset_and_prepare(
        postgres_event_store,
        postgres_research_artifact_store,
        postgres_settings,
    )
    partial = _run_worker(baseline_plan.optimization_plan_id, max_new_trials=2)
    assert partial["ok"] is True
    assert partial["data"]["parameter_optimization_run"]["status"] == "partial"
    assert partial["data"]["parameter_optimization_run"]["trial_count"] == 2
    resumed = _run_worker(baseline_plan.optimization_plan_id)
    assert resumed["ok"] is True
    _assert_matches_baseline(
        postgres_research_artifact_store,
        baseline_run,
        baseline_trials,
    )

    prepared = _reset_and_prepare(
        postgres_event_store,
        postgres_research_artifact_store,
        postgres_settings,
    )
    orphan_failure = _run_direct(
        prepared.optimization_plan_id,
        event_store=postgres_event_store,
        artifact_store=InjectedWriteFailureStore(
            postgres_research_artifact_store,
            artifact_type=PARAMETER_OPTIMIZATION_TRIAL,
            after_write=False,
        ),
        executor_artifact_store=postgres_research_artifact_store,
        config=prepared.config,
    )
    assert orphan_failure.ok is False
    assert _trials(postgres_research_artifact_store, baseline_run["optimization_run_id"]) == []
    assert postgres_research_artifact_store.list_artifacts(
        artifact_type="backtest_run"
    )
    orphan_record = postgres_research_artifact_store.list_artifacts(
        artifact_type="backtest_run"
    )[0]
    assert _run_worker(prepared.optimization_plan_id)["ok"] is True
    recovered_record = postgres_research_artifact_store.load_artifact_record(
        "backtest_run", orphan_record.artifact_id
    )
    assert recovered_record.updated_at == orphan_record.updated_at
    assert recovered_record.payload == orphan_record.payload
    _assert_matches_baseline(
        postgres_research_artifact_store,
        baseline_run,
        baseline_trials,
    )

    prepared = _reset_and_prepare(
        postgres_event_store,
        postgres_research_artifact_store,
        postgres_settings,
    )
    post_trial_failure = _run_direct(
        prepared.optimization_plan_id,
        event_store=postgres_event_store,
        artifact_store=InjectedWriteFailureStore(
            postgres_research_artifact_store,
            artifact_type=PARAMETER_OPTIMIZATION_TRIAL,
            after_write=True,
        ),
        executor_artifact_store=postgres_research_artifact_store,
        config=prepared.config,
    )
    assert post_trial_failure.ok is False
    persisted = _trials(
        postgres_research_artifact_store,
        str(baseline_run["optimization_run_id"]),
    )
    assert len(persisted) == 1
    assert persisted[0]["sequence"] == 0
    assert _run_worker(prepared.optimization_plan_id)["ok"] is True
    _assert_matches_baseline(
        postgres_research_artifact_store,
        baseline_run,
        baseline_trials,
    )

    prepared = _reset_and_prepare(
        postgres_event_store,
        postgres_research_artifact_store,
        postgres_settings,
    )
    pre_selection_failure = _run_direct(
        prepared.optimization_plan_id,
        event_store=postgres_event_store,
        artifact_store=InjectedWriteFailureStore(
            postgres_research_artifact_store,
            artifact_type=PARAMETER_OPTIMIZATION_RUN,
            after_write=False,
        ),
        executor_artifact_store=postgres_research_artifact_store,
        config=prepared.config,
    )
    assert pre_selection_failure.ok is False
    assert len(
        _trials(
            postgres_research_artifact_store,
            str(baseline_run["optimization_run_id"]),
        )
    ) == 4
    assert not postgres_research_artifact_store.list_artifacts(
        artifact_type=PARAMETER_OPTIMIZATION_RUN
    )
    assert _run_worker(prepared.optimization_plan_id)["ok"] is True
    _assert_matches_baseline(
        postgres_research_artifact_store,
        baseline_run,
        baseline_trials,
    )


@pytest.mark.postgres
def test_postgres_optimization_retry_and_terminal_blocked_evidence(
    postgres_event_store: PostgresEventStore,
    postgres_research_artifact_store: PostgresResearchArtifactStore,
    postgres_settings: dict[str, object],
) -> None:
    """Prove retry histories and terminal blockers remain durable and inspectable."""
    prepared = prepare_optimization_qualification(
        event_store=postgres_event_store,
        artifact_store=postgres_research_artifact_store,
        postgres_settings=postgres_settings,
        max_trial_attempts=2,
    )
    executor = FailOnceExecutor(
        BacktestOptimizationTrialExecutor(
            event_store=postgres_event_store,
            config=prepared.config,
            artifact_store=postgres_research_artifact_store,
        )
    )
    retry_result = run_parameter_optimization(
        optimization_plan_ref=prepared.optimization_plan_id,
        optimizer_profile="builtin_grid",
        trial_executor=executor,
        artifact_store=postgres_research_artifact_store,
    )
    assert retry_result.ok is True
    retry_run = retry_result.data["parameter_optimization_run"]
    retry_trials = _trials(
        postgres_research_artifact_store,
        str(retry_run["optimization_run_id"]),
    )
    assert len(retry_trials) == 4
    for trial in retry_trials:
        assert [attempt["status"] for attempt in trial["attempts"]] == [
            "blocked",
            "passed",
        ]
        assert "injected transient trial failure" in trial["attempts"][0][
            "exception"
        ]

    prepared = _reset_and_prepare(
        postgres_event_store,
        postgres_research_artifact_store,
        postgres_settings,
    )
    blocked_result = run_parameter_optimization(
        optimization_plan_ref=prepared.optimization_plan_id,
        optimizer_profile="builtin_grid",
        trial_executor=MissingMetricExecutor(),
        artifact_store=postgres_research_artifact_store,
    )
    assert blocked_result.ok is False
    blocked_run = blocked_result.data["parameter_optimization_run"]
    assert blocked_run["status"] == "blocked"
    assert blocked_run["selected_trial_id"] is None
    loaded = get_parameter_optimization_results(
        optimization_run_ref=blocked_run["optimization_run_id"],
        artifact_store=postgres_research_artifact_store,
    )
    assert loaded.ok is True
    assert len(loaded.data["trials"]) == 4
    assert all(trial["status"] == "blocked" for trial in loaded.data["trials"])
    assert all(
        trial["blockers"] == ["required objective metric is unavailable"]
        for trial in loaded.data["trials"]
    )


@pytest.mark.postgres
def test_postgres_optimization_enforces_trial_process_deadlines(
    postgres_event_store: PostgresEventStore,
    postgres_research_artifact_store: PostgresResearchArtifactStore,
    postgres_settings: dict[str, object],
) -> None:
    """Prove subprocess deadlines become bounded terminal trial evidence."""
    completed = prepare_optimization_qualification(
        event_store=postgres_event_store,
        artifact_store=postgres_research_artifact_store,
        postgres_settings=postgres_settings,
        search_values=(2,),
        max_trials=1,
        per_trial_timeout_seconds=30.0,
    )
    completed_result = run_parameter_optimization(
        optimization_plan_ref=completed.optimization_plan_id,
        optimizer_profile="builtin_grid",
        trial_executor=PostgresBacktestOptimizationTrialExecutor(
            event_store=postgres_event_store,
            config=completed.config,
            artifact_store=postgres_research_artifact_store,
        ),
        artifact_store=postgres_research_artifact_store,
    )
    assert completed_result.ok is True
    assert completed_result.data["new_trials"][0]["status"] == "passed"

    timed = _reset_and_prepare(
        postgres_event_store,
        postgres_research_artifact_store,
        postgres_settings,
        search_values=(2,),
        max_trials=1,
        per_trial_timeout_seconds=0.001,
    )
    started_at = time.monotonic()
    timed_result = run_parameter_optimization(
        optimization_plan_ref=timed.optimization_plan_id,
        optimizer_profile="builtin_grid",
        trial_executor=PostgresBacktestOptimizationTrialExecutor(
            event_store=postgres_event_store,
            config=timed.config,
            artifact_store=postgres_research_artifact_store,
        ),
        artifact_store=postgres_research_artifact_store,
    )
    elapsed_seconds = time.monotonic() - started_at
    assert timed_result.ok is False
    assert elapsed_seconds < 15.0
    timed_trial = timed_result.data["new_trials"][0]
    assert timed_trial["status"] == "blocked"
    assert timed_trial["blockers"] == [
        "trial execution exceeded per_trial_timeout_seconds"
    ]
    assert timed_trial["attempts"][0]["status"] == "blocked"


def _run_direct(
    plan_ref: str,
    *,
    event_store: PostgresEventStore,
    artifact_store: ResearchArtifactStore,
    config: Any,
    executor_artifact_store: ResearchArtifactStore | None = None,
) -> Any:
    executor_store = executor_artifact_store or artifact_store
    return run_parameter_optimization(
        optimization_plan_ref=plan_ref,
        optimizer_profile="builtin_grid",
        trial_executor=BacktestOptimizationTrialExecutor(
            event_store=event_store,
            config=config,
            artifact_store=executor_store,
        ),
        artifact_store=artifact_store,
    )


def _run_worker(plan_ref: str, *, max_new_trials: int | None = None) -> Mapping[str, Any]:
    command = [
        sys.executable,
        "-m",
        "tests.cross_package.qualification.support.postgres_optimization_resume_worker",
        "--plan-ref",
        plan_ref,
    ]
    if max_new_trials is not None:
        command.extend(["--max-new-trials", str(max_new_trials)])
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    line = next(
        value
        for value in completed.stdout.splitlines()
        if value.startswith("OPTIMIZATION_RESULT=")
    )
    return json.loads(line.removeprefix("OPTIMIZATION_RESULT="))


def _reset_and_prepare(
    event_store: PostgresEventStore,
    artifact_store: PostgresResearchArtifactStore,
    postgres_settings: Mapping[str, object],
    **kwargs: Any,
) -> Any:
    reset_57n_product_state(event_store, artifact_store, postgres_settings)
    return prepare_optimization_qualification(
        event_store=event_store,
        artifact_store=artifact_store,
        postgres_settings=postgres_settings,
        **kwargs,
    )


def _trials(
    store: PostgresResearchArtifactStore,
    run_id: str,
) -> list[Mapping[str, Any]]:
    trials = [
        record.payload
        for record in store.list_artifacts(artifact_type=PARAMETER_OPTIMIZATION_TRIAL)
        if record.payload.get("optimization_run_id") == run_id
    ]
    return sorted(trials, key=lambda trial: int(trial["sequence"]))


def _assert_matches_baseline(
    store: PostgresResearchArtifactStore,
    baseline_run: Mapping[str, Any],
    baseline_trials: Sequence[Mapping[str, Any]],
) -> None:
    run_id = str(baseline_run["optimization_run_id"])
    assert store.load_artifact(PARAMETER_OPTIMIZATION_RUN, run_id) == baseline_run
    assert _trials(store, run_id) == list(baseline_trials)
    assert len({trial["trial_id"] for trial in baseline_trials}) == len(baseline_trials)
    assert [trial["sequence"] for trial in baseline_trials] == list(
        range(len(baseline_trials))
    )
