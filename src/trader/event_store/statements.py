"""Postgres event-store lifecycle and experiment SQL statements."""

from __future__ import annotations

RUN_SESSION_START_SQL = """
            INSERT INTO runs (
                run_id,
                run_type,
                started_at,
                finished_at,
                status,
                error_message,
                config_snapshot,
                mode,
                symbols,
                timeframe,
                start_ts,
                end_ts
            )
            VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO NOTHING
            """

TRADING_SESSION_START_SQL = """
                INSERT INTO trading_sessions (
                    session_id,
                    strategy_id,
                    started_at,
                    finished_at,
                    status,
                    error_message,
                    config_snapshot,
                    mode,
                    symbols,
                    timeframe,
                    start_ts,
                    end_ts
                )
                VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (session_id) DO NOTHING
                """

RUN_SESSION_FINISH_SQL = """
            INSERT INTO runs (
                run_id,
                run_type,
                started_at,
                finished_at,
                status,
                error_message,
                config_snapshot,
                mode,
                symbols,
                timeframe,
                start_ts,
                end_ts
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                finished_at = excluded.finished_at,
                status = excluded.status,
                error_message = excluded.error_message
            """

TRADING_SESSION_FINISH_SQL = """
                INSERT INTO trading_sessions (
                    session_id,
                    strategy_id,
                    started_at,
                    finished_at,
                    status,
                    error_message,
                    config_snapshot,
                    mode,
                    symbols,
                    timeframe,
                    start_ts,
                    end_ts
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    finished_at = excluded.finished_at,
                    status = excluded.status,
                    error_message = excluded.error_message
                """

CYCLE_START_SQL = """
            INSERT INTO run_events (
                cycle_id,
                run_id,
                session_id,
                strategy_id,
                mode,
                decision_ts,
                started_at,
                finished_at,
                status,
                error_message
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, 'started', NULL)
            ON CONFLICT (cycle_id) DO NOTHING
            """

CYCLE_FINISH_SQL = """
            INSERT INTO run_events (
                cycle_id,
                run_id,
                session_id,
                strategy_id,
                mode,
                decision_ts,
                started_at,
                finished_at,
                status,
                error_message
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (cycle_id) DO UPDATE SET
                finished_at = excluded.finished_at,
                status = excluded.status,
                error_message = excluded.error_message
            """

UPSERT_EXPERIMENT_SQL = """
            INSERT INTO experiments (
                experiment_id,
                name,
                description,
                tags,
                created_at,
                updated_at,
                metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (experiment_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                tags = excluded.tags,
                updated_at = excluded.updated_at,
                metadata = excluded.metadata
            """

EXPERIMENT_RUN_START_SQL = """
            INSERT INTO experiment_runs (
                experiment_run_id,
                experiment_id,
                run_id,
                status,
                created_at,
                finished_at,
                strategy_id,
                strategy_name,
                strategy_version,
                symbols,
                asset_class,
                timeframe,
                start_ts,
                end_ts,
                parameters,
                assumptions,
                provenance,
                data_quality,
                result_summary,
                artifact_dir,
                error_message
            )
            VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, NULL)
            ON CONFLICT (experiment_run_id) DO UPDATE SET
                status = excluded.status,
                strategy_id = excluded.strategy_id,
                strategy_name = excluded.strategy_name,
                strategy_version = excluded.strategy_version,
                symbols = excluded.symbols,
                asset_class = excluded.asset_class,
                timeframe = excluded.timeframe,
                start_ts = excluded.start_ts,
                end_ts = excluded.end_ts,
                parameters = excluded.parameters,
                assumptions = excluded.assumptions,
                provenance = excluded.provenance,
                data_quality = excluded.data_quality,
                artifact_dir = excluded.artifact_dir,
                error_message = NULL
            """

EXPERIMENT_RUN_FINISH_SQL = """
            INSERT INTO experiment_runs (
                experiment_run_id,
                experiment_id,
                run_id,
                status,
                created_at,
                finished_at,
                provenance,
                data_quality,
                result_summary,
                artifact_dir,
                error_message
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (experiment_run_id) DO UPDATE SET
                status = excluded.status,
                finished_at = excluded.finished_at,
                provenance = COALESCE(excluded.provenance, experiment_runs.provenance),
                data_quality = COALESCE(excluded.data_quality, experiment_runs.data_quality),
                result_summary = excluded.result_summary,
                artifact_dir = COALESCE(excluded.artifact_dir, experiment_runs.artifact_dir),
                error_message = excluded.error_message
            """

LIST_EXPERIMENT_RUNS_SQL = """
            SELECT
                experiment_run_id,
                experiment_id,
                run_id,
                status,
                created_at,
                finished_at,
                strategy_id,
                strategy_name,
                strategy_version,
                symbols,
                asset_class,
                timeframe,
                start_ts,
                end_ts,
                parameters,
                assumptions,
                provenance,
                data_quality,
                result_summary,
                artifact_dir,
                error_message
            FROM experiment_runs
            WHERE experiment_id = %s
            ORDER BY created_at DESC, experiment_run_id DESC
        """


__all__ = [
    "CYCLE_FINISH_SQL",
    "CYCLE_START_SQL",
    "EXPERIMENT_RUN_FINISH_SQL",
    "EXPERIMENT_RUN_START_SQL",
    "LIST_EXPERIMENT_RUNS_SQL",
    "RUN_SESSION_FINISH_SQL",
    "RUN_SESSION_START_SQL",
    "TRADING_SESSION_FINISH_SQL",
    "TRADING_SESSION_START_SQL",
    "UPSERT_EXPERIMENT_SQL",
]
