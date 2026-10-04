"""Register the demo's typed bar and backtest datasets in Superset metadata.

Run after the explicit upstream migration and role initialization commands. This
release-specific adapter imports Superset only inside its own container.
"""

import os
from typing import Final

from sqlalchemy.engine import URL
from superset import db, security_manager
from superset.app import create_app


BACKTEST_DATASETS: Final[tuple[tuple[str, str, str | None], ...]] = (
    ("backtest_runs", "Run overview: identity, scope, status and strategy metadata.", "created_at"),
    ("backtest_performance", "Strategy and benchmark performance summaries from the backtest result.", "observed_at"),
    ("backtest_exposure", "Final and aggregate exposure evidence from the backtest result.", "observed_at"),
    ("backtest_equity_curve", "Strategy and benchmark equity points from one backtest result.", "ts"),
    ("backtest_trades", "Executed backtest trade/fill evidence.", "fill_ts"),
    ("backtest_positions", "Final marked positions from the backtest result.", "last_ts"),
    ("backtest_assumptions", "Execution and missing-data assumptions recorded with the result.", "observed_at"),
    ("backtest_warnings", "Warnings emitted during the backtest replay.", "observed_at"),
    ("backtest_provenance", "Producer and source provenance attached to the result.", "observed_at"),
    ("signal_lifecycle", "Producer-recorded signal intent and causal identity.", "generated_at"),
    ("order_lifecycle", "Producer-recorded order lifecycle and signal linkage.", "created_at"),
    ("fill_lifecycle", "Producer-recorded simulated fills and execution identity.", "fill_ts"),
    ("backtest_evidence_coverage", "Recorded, unavailable or unknown evidence streams for each run.", "observed_at"),
    ("backtest_scope", "Typed comparison scope and explicit strategy variant metadata.", "observed_at"),
    ("backtest_comparison_runs", "Compatibility-gated cohort rows with normalized comparison metrics.", "observed_at"),
    ("backtest_comparison_curves", "Per-run normalized strategy and benchmark curves for compatible cohorts.", "ts"),
)


def main() -> None:
    """Idempotently create the local admin, reader connection and bar dataset."""
    with create_app().app_context():
        # Superset initializes its encrypted-field factory during create_app().
        # Importing models earlier fails before any dataset can be registered.
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.core import Database

        if not security_manager.find_user(username="admin"):
            admin = security_manager.add_user(
                username="admin",
                first_name="Local",
                last_name="Reviewer",
                email="admin@superset-demo.invalid",
                role=security_manager.find_role("Admin"),
                password=os.environ["SUPERSET_DEMO_ADMIN_PASSWORD"],
            )
            if not admin:
                raise RuntimeError("Superset demo administrator creation failed")
        database = db.session.query(Database).filter_by(
            database_name="Trader synthetic demo"
        ).one_or_none()
        if database is None:
            database = Database(database_name="Trader synthetic demo")
            db.session.add(database)
        database.set_sqlalchemy_uri(URL.create(
            "postgresql+psycopg2",
            username="superset_demo_reader",
            password=os.environ["SUPERSET_DEMO_READER_PASSWORD"],
            host="trader",
            database="trader_superset_demo",
        ).render_as_string(hide_password=False))
        database.expose_in_sqllab = True
        database.allow_dml = False
        database.allow_ctas = False
        database.allow_cvas = False
        database.allow_file_upload = False
        db.session.flush()
        _register_dataset(
            db,
            SqlaTable,
            database,
            "stock_bars",
            "Synthetic setup fixture: DEMO, 1Min, source superset-demo. Not market evidence.",
            "ts",
        )
        for table_name, description, time_column in BACKTEST_DATASETS:
            _register_dataset(db, SqlaTable, database, table_name, description, time_column)
        real_password = os.environ.get("SUPERSET_DEMO_REAL_TRADER_PASSWORD")
        if real_password:
            real_database = db.session.query(Database).filter_by(
                database_name="Trader local data"
            ).one_or_none()
            if real_database is None:
                real_database = Database(database_name="Trader local data")
                db.session.add(real_database)
            real_database.set_sqlalchemy_uri(URL.create(
                "postgresql+psycopg2",
                username=os.environ.get("SUPERSET_DEMO_REAL_TRADER_USER", "trader"),
                password=real_password,
                host="host.docker.internal",
                port=int(os.environ.get("SUPERSET_DEMO_REAL_TRADER_PORT", "5432")),
                database=os.environ.get("SUPERSET_DEMO_REAL_TRADER_DATABASE", "trader"),
            ).render_as_string(hide_password=False))
            real_database.expose_in_sqllab = True
            real_database.allow_dml = False
            real_database.allow_ctas = False
            real_database.allow_cvas = False
            db.session.flush()
            real_dataset = db.session.query(SqlaTable).filter_by(
                database_id=real_database.id, schema="console_read", table_name="stock_bars"
            ).one_or_none()
            if real_dataset is None:
                real_dataset = SqlaTable(
                    database=real_database, schema="console_read", table_name="stock_bars",
                    main_dttm_col="ts",
                    description="Real local Trader OHLCV data loaded from Alpaca through Trader MCP.",
                )
                db.session.add(real_dataset)
            real_dataset.fetch_metadata()
        db.session.commit()
        print("Superset demo initialized: synthetic and local Trader datasets registered; MCP creates charts and dashboards.")


def _register_dataset(
    session_db: object,
    table_model: type,
    database: object,
    table_name: str,
    description: str,
    time_column: str | None,
) -> None:
    """Create or refresh one physical Console dataset in Superset metadata."""
    dataset = session_db.session.query(table_model).filter_by(
        database_id=database.id, schema="console_read", table_name=table_name
    ).one_or_none()
    if dataset is None:
        dataset = table_model(
            database=database,
            schema="console_read",
            table_name=table_name,
            main_dttm_col=time_column,
            description=description,
        )
        session_db.session.add(dataset)
        session_db.session.flush()
    else:
        dataset.main_dttm_col = time_column
        dataset.description = description
    dataset.fetch_metadata()


if __name__ == "__main__":
    main()
