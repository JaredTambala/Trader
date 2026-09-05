"""Postgres event-store schema definitions."""

from __future__ import annotations

from typing import Final


# Tables accepted by the generic append-only event insertion path.
POSTGRES_EVENT_TABLES: Final[frozenset[str]] = frozenset(
    {
        "runs",
        "trading_sessions",
        "run_events",
        "stock_bar_events",
        "crypto_bar_events",
        "signal_events",
        "indicator_events",
        "prediction_events",
        "order_events",
        "fill_events",
        "position_snapshots",
        "config_kv",
        "metrics_snapshots",
        "experiments",
        "experiment_runs",
    }
)

# Market-data event tables with idempotent bar insertion constraints.
BAR_EVENT_TABLES: Final[frozenset[str]] = frozenset({"stock_bar_events", "crypto_bar_events"})

# Idempotent schema creation and migration statements for the event store.
POSTGRES_SCHEMA_STATEMENTS: Final[tuple[str, ...]] = (
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                run_type TEXT,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                status TEXT,
                error_message TEXT,
                config_snapshot JSONB,
                mode TEXT,
                symbols TEXT[],
                timeframe TEXT,
                start_ts TIMESTAMPTZ,
                end_ts TIMESTAMPTZ
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trading_sessions (
                session_id TEXT PRIMARY KEY,
                strategy_id TEXT,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                status TEXT,
                error_message TEXT,
                config_snapshot JSONB,
                mode TEXT,
                symbols TEXT[],
                timeframe TEXT,
                start_ts TIMESTAMPTZ,
                end_ts TIMESTAMPTZ
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                name TEXT UNIQUE,
                description TEXT,
                tags TEXT[],
                created_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ,
                metadata JSONB
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS experiment_runs (
                experiment_run_id TEXT PRIMARY KEY,
                experiment_id TEXT,
                run_id TEXT,
                status TEXT,
                created_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                strategy_id TEXT,
                strategy_name TEXT,
                strategy_version TEXT,
                symbols TEXT[],
                asset_class TEXT,
                timeframe TEXT,
                start_ts TIMESTAMPTZ,
                end_ts TIMESTAMPTZ,
                parameters JSONB,
                assumptions JSONB,
                provenance JSONB,
                data_quality JSONB,
                result_summary JSONB,
                artifact_dir TEXT,
                error_message TEXT
            )
            """,
            """
            ALTER TABLE IF EXISTS run_events
            DROP CONSTRAINT IF EXISTS run_events_pkey
            """,
            """
            CREATE TABLE IF NOT EXISTS run_events (
                cycle_id TEXT PRIMARY KEY,
                run_id TEXT,
                session_id TEXT,
                strategy_id TEXT,
                mode TEXT,
                decision_ts TIMESTAMPTZ,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                status TEXT,
                error_message TEXT
            )
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS cycle_id TEXT
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS run_id TEXT
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS strategy_id TEXT
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS mode TEXT
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS decision_ts TIMESTAMPTZ
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS status TEXT
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS error_message TEXT
            """,
            """
            CREATE TABLE IF NOT EXISTS stock_bar_events (
                symbol TEXT,
                timeframe TEXT,
                ts TIMESTAMPTZ,
                ingested_at TIMESTAMPTZ,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                volume DOUBLE PRECISION,
                trade_count DOUBLE PRECISION,
                vwap DOUBLE PRECISION,
                source TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS crypto_bar_events (
                symbol TEXT,
                timeframe TEXT,
                ts TIMESTAMPTZ,
                ingested_at TIMESTAMPTZ,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                volume DOUBLE PRECISION,
                trade_count DOUBLE PRECISION,
                vwap DOUBLE PRECISION,
                source TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS signal_events (
                run_id TEXT,
                session_id TEXT,
                cycle_id TEXT,
                symbol TEXT,
                signal_name TEXT,
                signal_value DOUBLE PRECISION,
                target_qty DOUBLE PRECISION,
                generated_at TIMESTAMPTZ,
                prediction_event_refs TEXT,
                mapper_id TEXT,
                payload TEXT
            )
            """,
            "ALTER TABLE signal_events ADD COLUMN IF NOT EXISTS signal_name TEXT",
            "ALTER TABLE signal_events ADD COLUMN IF NOT EXISTS prediction_event_refs TEXT",
            "ALTER TABLE signal_events ADD COLUMN IF NOT EXISTS mapper_id TEXT",
            "ALTER TABLE signal_events ADD COLUMN IF NOT EXISTS payload TEXT",
            """
            CREATE TABLE IF NOT EXISTS indicator_events (
                run_id TEXT,
                session_id TEXT,
                cycle_id TEXT,
                symbol TEXT,
                indicator_name TEXT,
                value DOUBLE PRECISION,
                bar_ts TIMESTAMPTZ,
                payload TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS prediction_events (
                prediction_event_id TEXT PRIMARY KEY,
                run_id TEXT,
                session_id TEXT,
                cycle_id TEXT,
                deployment_id TEXT,
                deployment_validation_id TEXT,
                model_version_id TEXT,
                feature_set_id TEXT,
                feature_batch_hash TEXT,
                decision_ts TIMESTAMPTZ,
                symbol TEXT,
                output_name TEXT,
                semantics TEXT,
                horizon TEXT,
                value_payload TEXT,
                latency_ms DOUBLE PRECISION,
                status TEXT,
                error_message TEXT,
                payload TEXT
            )
            """,
            """
            ALTER TABLE signal_events
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            ALTER TABLE indicator_events
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            ALTER TABLE indicator_events
            ADD COLUMN IF NOT EXISTS payload TEXT
            """,
            """
            CREATE TABLE IF NOT EXISTS order_events (
                order_event_id TEXT PRIMARY KEY,
                client_order_id TEXT,
                run_id TEXT,
                session_id TEXT,
                cycle_id TEXT,
                symbol TEXT,
                side TEXT,
                qty DOUBLE PRECISION,
                order_type TEXT,
                status TEXT,
                broker_order_id TEXT,
                rejection_reason TEXT,
                decision_evidence TEXT,
                created_at TIMESTAMPTZ
            )
            """,
            """
            ALTER TABLE order_events
            ADD COLUMN IF NOT EXISTS rejection_reason TEXT
            """,
            """
            ALTER TABLE order_events
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            ALTER TABLE order_events
            ADD COLUMN IF NOT EXISTS decision_evidence TEXT
            """,
            """
            ALTER TABLE order_events
            DROP CONSTRAINT IF EXISTS order_events_pkey
            """,
            """
            ALTER TABLE order_events
            ADD COLUMN IF NOT EXISTS order_event_id TEXT
            """,
            """
            UPDATE order_events
            SET order_event_id = CONCAT('order_evt_', md5(random()::text || clock_timestamp()::text))
            WHERE order_event_id IS NULL
            """,
            """
            ALTER TABLE order_events
            ALTER COLUMN order_event_id SET NOT NULL
            """,
            """
            ALTER TABLE order_events
            ADD PRIMARY KEY (order_event_id)
            """,
            """
            CREATE TABLE IF NOT EXISTS fill_events (
                client_order_id TEXT,
                run_id TEXT,
                session_id TEXT,
                cycle_id TEXT,
                fill_ts TIMESTAMPTZ,
                fill_qty DOUBLE PRECISION,
                raw_fill_price DOUBLE PRECISION,
                slippage_amount DOUBLE PRECISION,
                fee_amount DOUBLE PRECISION,
                fill_price DOUBLE PRECISION
            )
            """,
            """
            ALTER TABLE fill_events
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            ALTER TABLE fill_events
            ADD COLUMN IF NOT EXISTS raw_fill_price DOUBLE PRECISION
            """,
            """
            ALTER TABLE fill_events
            ADD COLUMN IF NOT EXISTS slippage_amount DOUBLE PRECISION
            """,
            """
            ALTER TABLE fill_events
            ADD COLUMN IF NOT EXISTS fee_amount DOUBLE PRECISION
            """,
            """
            CREATE TABLE IF NOT EXISTS position_snapshots (
                asof_ts TIMESTAMPTZ,
                symbol TEXT,
                qty DOUBLE PRECISION,
                avg_price DOUBLE PRECISION,
                cash_balance DOUBLE PRECISION,
                run_id TEXT,
                session_id TEXT,
                cycle_id TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS config_kv (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """,
            """
            ALTER TABLE position_snapshots
            ADD COLUMN IF NOT EXISTS cash_balance DOUBLE PRECISION
            """,
            """
            ALTER TABLE position_snapshots
            ADD COLUMN IF NOT EXISTS run_id TEXT
            """,
            """
            ALTER TABLE position_snapshots
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            ALTER TABLE position_snapshots
            ADD COLUMN IF NOT EXISTS cycle_id TEXT
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS stock_bar_events_unique
            ON stock_bar_events(symbol, timeframe, ts, source)
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS crypto_bar_events_unique
            ON crypto_bar_events(symbol, timeframe, ts, source)
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS run_events_cycle_unique
            ON run_events(cycle_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS run_events_run_id_idx
            ON run_events(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS run_events_session_id_idx
            ON run_events(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS signal_events_run_id_idx
            ON signal_events(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS signal_events_session_id_idx
            ON signal_events(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS indicator_events_run_id_idx
            ON indicator_events(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS indicator_events_session_id_idx
            ON indicator_events(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS prediction_events_run_id_idx
            ON prediction_events(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS prediction_events_session_id_idx
            ON prediction_events(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS prediction_events_model_version_id_idx
            ON prediction_events(model_version_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS order_events_run_id_idx
            ON order_events(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS order_events_session_id_idx
            ON order_events(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS order_events_client_order_id_idx
            ON order_events(client_order_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS fill_events_run_id_idx
            ON fill_events(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS fill_events_session_id_idx
            ON fill_events(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS position_snapshots_run_id_idx
            ON position_snapshots(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS position_snapshots_session_id_idx
            ON position_snapshots(session_id)
            """,
            """
            CREATE TABLE IF NOT EXISTS metrics_snapshots (
                ts TIMESTAMPTZ,
                run_id TEXT,
                session_id TEXT,
                cycle_id TEXT,
                payload TEXT
            )
            """,
            """
            ALTER TABLE metrics_snapshots
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            CREATE INDEX IF NOT EXISTS metrics_snapshots_run_id_idx
            ON metrics_snapshots(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS metrics_snapshots_session_id_idx
            ON metrics_snapshots(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS experiment_runs_experiment_id_idx
            ON experiment_runs(experiment_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS experiment_runs_run_id_idx
            ON experiment_runs(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS experiment_runs_status_idx
            ON experiment_runs(status)
            """,
            """
            CREATE INDEX IF NOT EXISTS experiment_runs_created_at_idx
            ON experiment_runs(created_at)
            """,
)
