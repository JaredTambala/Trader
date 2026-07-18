from __future__ import annotations

from collections.abc import Iterator

import pytest
import psycopg

from trader.event_store import PostgresEventStore
from trader_research.knowledge.postgres_store import PostgresKnowledgeStore
from trader_research.knowledge.store import KnowledgeVectorExtensionUnavailable
from trader_research.postgres_artifact_store import PostgresResearchArtifactStore
from tests.support.postgres_verification import (
    VerificationConfigurationError,
    assert_connection_targets_verification_database,
    assert_verification_database,
    load_test_settings,
    verification_mode_enabled,
)


def _postgres_settings_from_env() -> dict[str, object] | None:
    try:
        settings = load_test_settings()
    except VerificationConfigurationError as exc:
        if verification_mode_enabled():
            raise pytest.UsageError(str(exc)) from exc
        return None
    return settings.connect_kwargs() if settings is not None else None


def _truncate_runtime_tables(
    store: PostgresEventStore, settings: dict[str, object]
) -> None:
    connection = store.connection()
    assert_connection_targets_verification_database(connection, settings)
    connection.execute(
        """
        TRUNCATE TABLE
            metrics_snapshots,
            position_snapshots,
            fill_events,
            order_events,
            indicator_events,
            signal_events,
            stock_bar_events,
            crypto_bar_events,
            run_events,
            trading_sessions,
            runs,
            experiment_runs,
            experiments,
            config_kv
        """
    )


def _truncate_knowledge_tables(
    store: PostgresKnowledgeStore, settings: dict[str, object]
) -> None:
    connection = store.connection()
    assert_connection_targets_verification_database(connection, settings)
    connection.execute(
        """
        TRUNCATE TABLE
            knowledge_embeddings,
            knowledge_embedding_indexes,
            knowledge_ingestion_runs,
            knowledge_chunks,
            knowledge_sources,
            knowledge_method_cards,
            knowledge_method_card_sets,
            knowledge_method_contracts
        CASCADE
        """
    )


def _truncate_research_artifact_tables(
    store: PostgresResearchArtifactStore, settings: dict[str, object]
) -> None:
    connection = store.connection()
    assert_connection_targets_verification_database(connection, settings)
    connection.execute(
        """
        TRUNCATE TABLE
            research_parameter_optimization_robustness_reports,
            research_parameter_optimization_audit_plans,
            research_parameter_optimization_evaluations,
            research_experiment_tracking_projections,
            research_parameter_optimization_trials,
            research_parameter_optimization_runs,
            research_parameter_optimization_plans,
            research_backtest_runs,
            research_backtest_specification_validations,
            research_backtest_specifications,
            research_risk_stack_specification_validations,
            research_risk_stack_specifications,
            research_strategy_specification_validations,
            research_strategy_specifications,
            research_implementation_validations,
            research_implementation_versions,
            research_methodology_validations,
            research_methodology_evidence_packets,
            research_methodology_field_extractions,
            research_methodology_candidates,
            research_artifacts
        CASCADE
        """
    )


@pytest.fixture
def postgres_settings() -> dict[str, object]:
    settings = _postgres_settings_from_env()
    if settings is None:
        pytest.skip(
            "Postgres test env vars missing "
            "(PG_TEST_HOST/PG_TEST_PORT/PG_TEST_DB/PG_TEST_USER/PG_TEST_PASSWORD); "
            "legacy PG_HOST/PG_USER variables are never used by tests"
        )
    try:
        assert_verification_database(settings)
    except VerificationConfigurationError as exc:
        raise pytest.UsageError(str(exc)) from exc
    return settings


@pytest.fixture
def postgres_event_store(
    postgres_settings: dict[str, object],
) -> Iterator[PostgresEventStore]:
    store = PostgresEventStore(**postgres_settings)
    _truncate_runtime_tables(store, postgres_settings)
    try:
        yield store
    finally:
        _truncate_runtime_tables(store, postgres_settings)
        store.close()


@pytest.fixture
def postgres_listener_connection(postgres_settings: dict[str, object]) -> Iterator[psycopg.Connection]:
    connection = psycopg.connect(**postgres_settings)
    connection.autocommit = True
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def postgres_knowledge_store(
    postgres_settings: dict[str, object],
) -> Iterator[PostgresKnowledgeStore]:
    try:
        store = PostgresKnowledgeStore(**postgres_settings)
    except KnowledgeVectorExtensionUnavailable as exc:
        pytest.skip(str(exc))
    _truncate_knowledge_tables(store, postgres_settings)
    try:
        yield store
    finally:
        _truncate_knowledge_tables(store, postgres_settings)
        store.close()


@pytest.fixture
def postgres_research_artifact_store(
    postgres_settings: dict[str, object],
) -> Iterator[PostgresResearchArtifactStore]:
    store = PostgresResearchArtifactStore(**postgres_settings)
    _truncate_research_artifact_tables(store, postgres_settings)
    try:
        yield store
    finally:
        _truncate_research_artifact_tables(store, postgres_settings)
        store.close()
