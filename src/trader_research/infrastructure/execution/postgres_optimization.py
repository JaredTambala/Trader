"""Run Postgres-backed optimization trials behind process deadlines.

The adapter reconstructs canonical backtest dependencies in a child process,
returns a bounded observation to the parent, and terminates work that exceeds
the declared limit. Child failures are translated into actionable trial errors
without fabricating canonical results.
"""

from __future__ import annotations

import multiprocessing
from multiprocessing.connection import Connection
from typing import Any, Mapping

from trader.config import Config
from trader.event_store import EventStore, PostgresEventStore
from trader_research.experiments import (
    BacktestOptimizationTrialExecutor,
    TrialExecution,
)
from trader_research.foundation import ResearchArtifactStore
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore


_TIMEOUT_BLOCKER = "trial execution exceeded per_trial_timeout_seconds"


class PostgresBacktestOptimizationTrialExecutor:
    """Run canonical backtest trials and terminate overdue work in a child process."""

    executor_kind = BacktestOptimizationTrialExecutor.executor_kind

    def __init__(
        self,
        *,
        event_store: EventStore,
        config: Config,
        artifact_store: ResearchArtifactStore,
    ) -> None:
        self._config = config
        self._event_store = event_store
        self._artifact_store = artifact_store
        self._delegate = BacktestOptimizationTrialExecutor(
            event_store=event_store,
            config=config,
            artifact_store=artifact_store,
        )
        if isinstance(artifact_store, PostgresResearchArtifactStore):
            _assert_store_matches_config(artifact_store, config)

    def execute(
        self,
        *,
        plan: Mapping[str, Any],
        parameters: Mapping[str, Any],
        trial_id: str,
        optimization_run_id: str,
    ) -> TrialExecution:
        """Execute one trial in process when no enforceable deadline is needed.

        The call delegates to the canonical backtest trial executor with the same
        sealed plan, parameters, and lineage IDs. It adds no timeout, process, or
        persistence behavior of its own.
        """
        return self._delegate.execute(
            plan=plan,
            parameters=parameters,
            trial_id=trial_id,
            optimization_run_id=optimization_run_id,
        )

    def execute_with_timeout(
        self,
        *,
        plan: Mapping[str, Any],
        parameters: Mapping[str, Any],
        trial_id: str,
        optimization_run_id: str,
        timeout_seconds: float,
    ) -> TrialExecution:
        """Run one trial in a spawned process and enforce its wall-clock deadline.

        Enforced deadlines require both Postgres event and artifact stores so the
        child can reconstruct dependencies after ``spawn``. The parent accepts one
        bounded ``TrialExecution`` from a pipe, terminates and then kills overdue
        work if necessary, and closes all process resources.

        Returns:
            The child result, or a blocked execution for unsupported stores,
            timeout, missing child output, or an invalid child response.
        """
        if not isinstance(self._event_store, PostgresEventStore) or not isinstance(
            self._artifact_store, PostgresResearchArtifactStore
        ):
            return TrialExecution(
                status="blocked",
                observation=None,
                blockers=(
                    "enforced trial deadlines require Postgres event and artifact stores",
                ),
            )
        context = multiprocessing.get_context("spawn")
        receive, send = context.Pipe(duplex=False)
        process = context.Process(
            target=_execute_trial_process,
            args=(
                send,
                self._config,
                dict(plan),
                dict(parameters),
                trial_id,
                optimization_run_id,
            ),
            name=f"optimization-trial-{trial_id[-12:]}",
        )
        try:
            process.start()
        except BaseException:
            receive.close()
            send.close()
            raise
        send.close()
        process.join(timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(5.0)
            if process.is_alive():
                process.kill()
                process.join(5.0)
            receive.close()
            process.close()
            return TrialExecution(
                status="blocked",
                observation=None,
                blockers=(_TIMEOUT_BLOCKER,),
            )
        exit_code = process.exitcode
        try:
            if not receive.poll():
                return TrialExecution(
                    status="blocked",
                    observation=None,
                    blockers=(
                        f"isolated trial process exited without a result (exit_code={exit_code})",
                    ),
                )
            result = receive.recv()
        finally:
            receive.close()
            process.close()
        if isinstance(result, TrialExecution):
            return result
        return TrialExecution(
            status="blocked",
            observation=None,
            blockers=(str(result),),
        )


def _execute_trial_process(
    connection: Connection,
    config: Config,
    plan: Mapping[str, Any],
    parameters: Mapping[str, Any],
    trial_id: str,
    optimization_run_id: str,
) -> None:
    """Recreate Postgres adapters after spawn and return one bounded result."""
    event_store: PostgresEventStore | None = None
    artifact_store: PostgresResearchArtifactStore | None = None
    try:
        kwargs = _connection_kwargs(config)
        event_store = PostgresEventStore(**kwargs)
        artifact_store = PostgresResearchArtifactStore(**kwargs)
        result = BacktestOptimizationTrialExecutor(
            event_store=event_store,
            config=config,
            artifact_store=artifact_store,
        ).execute(
            plan=plan,
            parameters=parameters,
            trial_id=trial_id,
            optimization_run_id=optimization_run_id,
        )
        connection.send(result)
    except BaseException as exc:
        connection.send(f"{type(exc).__name__}: {exc}")
    finally:
        connection.close()
        if artifact_store is not None:
            artifact_store.close()
        if event_store is not None:
            event_store.close()


def _connection_kwargs(config: Config) -> dict[str, Any]:
    if config.pg_dsn:
        return {"dsn": config.pg_dsn}
    return {
        "host": config.pg_host,
        "port": config.pg_port,
        "dbname": config.pg_db,
        "user": config.pg_user,
        "password": config.pg_password,
    }


def _assert_store_matches_config(
    artifact_store: PostgresResearchArtifactStore,
    config: Config,
) -> None:
    if config.pg_dsn:
        return
    info = artifact_store.connection().info
    expected = {
        "dbname": config.pg_db,
        "user": config.pg_user,
        "host": config.pg_host,
        "port": int(config.pg_port),
    }
    actual = {
        "dbname": info.dbname,
        "user": info.user,
        "host": info.host,
        "port": int(info.port),
    }
    if expected != actual:
        raise ValueError(
            "Postgres trial executor configuration must match the canonical artifact store"
        )
