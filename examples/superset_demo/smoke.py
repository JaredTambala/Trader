"""Small HTTP smoke checks for the real local Superset instance."""

import json

import httpx
import psycopg
from psycopg import sql

from .runtime import DemoStack


BACKTEST_TABLES = (
    "backtest_runs",
    "backtest_performance",
    "backtest_exposure",
    "backtest_equity_curve",
    "backtest_trades",
    "backtest_positions",
    "backtest_assumptions",
    "backtest_warnings",
    "backtest_provenance",
    "signal_lifecycle",
    "order_lifecycle",
    "fill_lifecycle",
    "backtest_evidence_coverage",
    "backtest_scope",
    "backtest_comparison_runs",
    "backtest_comparison_curves",
)


def check_preview(stack: DemoStack) -> int:
    """Query the registered bars and return the dataset ID for persistence checks."""
    values = json.loads((stack.state_directory / "credentials.json").read_text())
    origin = f"http://127.0.0.1:{stack.ui_port}"
    with httpx.Client(base_url=origin, timeout=10) as client:
        health = client.get("/health")
        health.raise_for_status()
        login = client.post(
            "/api/v1/security/login",
            json={"username": "admin", "password": values["ADMIN_PASSWORD"], "provider": "db", "refresh": True},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        datasets = client.get(
            "/api/v1/dataset/",
            headers=headers,
            params={"q": "(page:0,page_size:100)"},
        )
        datasets.raise_for_status()
        matches = [
            row for row in datasets.json()["result"]
            if row.get("table_name") == "stock_bars" and row.get("schema") == "console_read"
        ]
        synthetic = [row for row in matches if row.get("database", {}).get("database_name") == "Trader synthetic demo"]
        real = [row for row in matches if row.get("database", {}).get("database_name") == "Trader local data"]
        if len(synthetic) != 1:
            raise RuntimeError("Expected one registered synthetic console_read.stock_bars dataset")
        if len(real) > 1:
            raise RuntimeError("Expected at most one registered real console_read.stock_bars dataset")
        matches = synthetic
        rows = _query_dataset(
            client,
            headers,
            matches[0]["id"],
            columns=["symbol", "timeframe", "ts", "open", "high", "low", "close", "volume"],
            orderby=[["ts", True]],
            row_limit=10,
        )
        if len(rows) != 3 or [row["symbol"] for row in rows] != ["DEMO"] * 3:
            raise RuntimeError("Superset bar preview did not return the expected three DEMO rows")
        for index, row in enumerate(rows):
            expected = ("1Min", 100 + index, 102 + index, 99 + index, 101 + index, 1000 + index * 100)
            observed = tuple(row[key] for key in ("timeframe", "open", "high", "low", "close", "volume"))
            if observed != expected:
                raise RuntimeError("Superset bar preview values differ from the synthetic fixture")
        charts = client.get("/api/v1/chart/", headers=headers, params={"page_size": 100})
        charts.raise_for_status()
        chart_names = {row["slice_name"] for row in charts.json()["result"]}
        expected_charts = {
            "Trader demo · MCP · close",
            "Trader demo · MCP · volume",
            "Trader demo · MCP · OHLCV rows",
        }
        if not expected_charts <= chart_names:
            raise RuntimeError("Superset observation charts were not registered")
        # The MCP seed owns chart query construction and has already validated
        # each generated asset through Superset's supported tool boundary. The
        # REST chart-data payload is version-specific and is not duplicated here.
        dashboards = client.get("/api/v1/dashboard/", headers=headers, params={"page_size": 100})
        dashboards.raise_for_status()
        if not any(row.get("dashboard_title") == "Trader demo · MCP · bars" for row in dashboards.json()["result"]):
            raise RuntimeError("Superset MCP demo dashboard was not registered")
        backtest_datasets = [
            row for row in datasets.json()["result"]
            if row.get("table_name") in set(BACKTEST_TABLES)
            and row.get("schema") == "console_read"
            and row.get("database", {}).get("database_name") == "Trader synthetic demo"
        ]
        expected_backtest_tables = {
            "backtest_runs", "backtest_performance", "backtest_exposure", "backtest_equity_curve",
            "backtest_trades", "backtest_positions", "backtest_assumptions", "backtest_warnings",
            "backtest_provenance", "signal_lifecycle", "order_lifecycle", "fill_lifecycle",
            "backtest_evidence_coverage", "backtest_scope",
            "backtest_comparison_runs", "backtest_comparison_curves",
        }
        if {row["table_name"] for row in backtest_datasets} != expected_backtest_tables:
            raise RuntimeError("Superset backtest projections were not all registered")
        backtest_dashboard = next(
            (
                row for row in dashboards.json()["result"]
                if row.get("dashboard_title") == "Trader backtest · MCP · single-run review"
            ),
            None,
        )
        if backtest_dashboard is None:
            raise RuntimeError("Superset backtest review dashboard was not registered")
        detail = client.get(f"/api/v1/dashboard/{backtest_dashboard['id']}", headers=headers)
        detail.raise_for_status()
        metadata = json.loads(detail.json()["result"].get("json_metadata") or "{}")
        filter_ids = {
            item.get("id") for item in metadata.get("native_filter_configuration", [])
        }
        if {"NATIVE_FILTER-TRADER-RUN", "NATIVE_FILTER-TRADER-TIME"} - filter_ids:
            raise RuntimeError("Superset backtest review filters were not configured")
        run_filter = next(
            item for item in metadata["native_filter_configuration"]
            if item.get("id") == "NATIVE_FILTER-TRADER-RUN"
        )
        run_dataset = next(row for row in backtest_datasets if row["table_name"] == "backtest_runs")
        if run_filter.get("targets") != [{"datasetUuid": run_dataset["uuid"], "column": {"name": "run_id"}}]:
            raise RuntimeError("Superset run filter must source values from backtest_runs")
        expected_review_charts = {
            "Trader backtest · MCP · signal lifecycle",
            "Trader backtest · MCP · order lifecycle",
            "Trader backtest · MCP · fill lifecycle",
            "Trader backtest · MCP · evidence coverage",
            "Trader backtest · MCP · comparison scope",
            "Trader backtest · MCP · comparison · cohort runs",
            "Trader backtest · MCP · comparison · normalized equity",
            "Trader backtest · MCP · comparison · drawdown",
        }
        if not expected_review_charts <= chart_names:
            raise RuntimeError("Superset lifecycle drill-down charts were not registered")
        comparison_dashboard = next(
            (
                row for row in dashboards.json()["result"]
                if row.get("dashboard_title") == "Trader backtest · MCP · comparison · review"
            ),
            None,
        )
        if comparison_dashboard is None:
            raise RuntimeError("Superset comparison dashboard was not registered")
        comparison_detail = client.get(f"/api/v1/dashboard/{comparison_dashboard['id']}", headers=headers)
        comparison_detail.raise_for_status()
        comparison_metadata = json.loads(comparison_detail.json()["result"].get("json_metadata") or "{}")
        if "NATIVE_FILTER-TRADER-SCOPE" not in {
            item.get("id") for item in comparison_metadata.get("native_filter_configuration", [])
        }:
            raise RuntimeError("Superset comparison scope filter was not configured")
        _check_backtest_projection_rows(client, headers, backtest_datasets, stack)
        if real:
            real_rows = _query_dataset(
                client,
                headers,
                real[0]["id"],
                columns=["symbol", "timeframe", "ts", "close"],
                orderby=[["ts", True]],
                row_limit=10,
            )
            if not real_rows or any(row["symbol"] == "DEMO" for row in real_rows):
                raise RuntimeError("Superset real-data preview did not return loaded Trader bars")
            if not any(row.get("dashboard_title") == "Trader real · MCP · bars" for row in dashboards.json()["result"]):
                raise RuntimeError("Superset MCP real-data dashboard was not registered")
    suffix = " and loaded Trader bars" if real else ""
    print(f"Superset preview passed: console_read.stock_bars returned three DEMO rows{suffix}.")
    return int(matches[0]["id"])


def _query_dataset(
    client: httpx.Client,
    headers: dict[str, str],
    dataset_id: int,
    *,
    columns: list[str],
    orderby: list[list[object]],
    row_limit: int,
) -> list[dict[str, object]]:
    """Query one registered dataset through Superset's chart-data API."""
    response = client.post(
        "/api/v1/chart/data",
        headers=headers,
        json={
            "datasource": {"id": dataset_id, "type": "table"},
            "queries": [{"columns": columns, "orderby": orderby, "row_limit": row_limit}],
            "result_format": "json", "result_type": "full", "force": True,
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("result") or not payload["result"][0].get("data"):
        return []
    return payload["result"][0]["data"]


def _check_backtest_projection_rows(
    client: httpx.Client,
    headers: dict[str, str],
    datasets: list[dict[str, object]],
    stack: DemoStack,
) -> None:
    """Reconcile each Superset backtest dataset's run identities to PostgreSQL."""
    by_name = {row["table_name"]: row["id"] for row in datasets}
    with psycopg.connect(stack.dsn(reader=True)) as connection:
        for table_name in BACKTEST_TABLES:
            expected = [
                str(row[0]) for row in connection.execute(
                    sql.SQL("SELECT run_id FROM console_read.{} ORDER BY run_id").format(
                        sql.Identifier(table_name)
                    )
                ).fetchall()
            ]
            observed = [
                str(row["run_id"]) for row in _query_dataset(
                    client,
                    headers,
                    by_name[table_name],
                    columns=["run_id"],
                    orderby=[["run_id", True]],
                    row_limit=10000,
                )
            ]
            expected.sort()
            observed.sort()
            if observed != expected:
                raise RuntimeError(
                    f"Superset dataset {table_name} differs from console_read: "
                    f"expected {len(expected)} rows, observed {len(observed)}"
                )
