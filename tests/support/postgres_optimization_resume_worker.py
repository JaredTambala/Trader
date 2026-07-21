"""Fresh-process worker for controlled optimization resume qualification."""

from __future__ import annotations

import argparse
import json

from trader.event_store import PostgresEventStore
from trader_research.experiments import (
    BacktestOptimizationTrialExecutor,
    run_parameter_optimization,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.support.postgres_verification import (
    assert_verification_database,
    load_test_settings,
)
from tests.support.realistic_optimization_fixture import build_backtest_config


def main() -> None:
    """Resume one canonical optimization plan in a newly constructed process."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-ref", required=True)
    parser.add_argument("--profile", default="builtin_grid")
    parser.add_argument("--max-new-trials", type=int)
    args = parser.parse_args()
    settings = load_test_settings(required=True)
    if settings is None:  # pragma: no cover - required=True fails first
        raise RuntimeError("PG_TEST settings are required")
    assert_verification_database(settings)
    connect_kwargs = settings.connect_kwargs()
    event_store = PostgresEventStore(**connect_kwargs)
    artifact_store = PostgresResearchArtifactStore(**connect_kwargs)
    try:
        result = run_parameter_optimization(
            optimization_plan_ref=args.plan_ref,
            optimizer_profile=args.profile,
            trial_executor=BacktestOptimizationTrialExecutor(
                event_store=event_store,
                config=build_backtest_config(connect_kwargs),
                artifact_store=artifact_store,
            ),
            artifact_store=artifact_store,
            max_new_trials=args.max_new_trials,
        )
        print(
            "OPTIMIZATION_RESULT="
            + json.dumps(
                {
                    "ok": result.ok,
                    "data": result.data,
                    "errors": list(result.errors),
                },
                sort_keys=True,
            )
        )
    finally:
        artifact_store.close()
        event_store.close()


if __name__ == "__main__":
    main()
