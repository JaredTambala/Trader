"""Create the demo's charts and dashboard through Superset's MCP tools.

This is intentionally a small, idempotent client for the pinned Superset MCP
server. It owns only assets with the ``Trader demo · MCP`` prefix.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastmcp import Client
import httpx


PREFIX = "Trader demo · MCP"


def _data(result: Any) -> dict[str, Any]:
    """Normalize FastMCP results without depending on transport internals."""
    value = getattr(result, "data", None)
    if isinstance(value, dict):
        return value
    for item in getattr(result, "content", []):
        text = getattr(item, "text", None)
        if text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise RuntimeError(f"Superset MCP returned no structured data: {result!r}")


async def _call(client: Client, name: str, request: dict[str, Any]) -> dict[str, Any]:
    result = await client.call_tool(name, {"request": request})
    if getattr(result, "is_error", False):
        raise RuntimeError(f"Superset MCP {name} failed: {result}")
    value = _data(result)
    if value.get("success") is False or value.get("error"):
        raise RuntimeError(f"Superset MCP {name} failed: {value}")
    return value


async def _seed_dashboard(
    client: Client,
    *,
    dataset_id: int,
    prefix: str,
    dashboard_name: str,
    description: str,
) -> dict[str, Any]:
    """Create or update the compact OHLCV charts for one dataset."""
    charts = await _call(client, "list_charts", {"search": prefix, "page_size": 50})
    existing = {item.get("slice_name"): item for item in charts.get("charts", [])}
    definitions = (
        (f"{prefix} · close", {"chart_type": "xy", "x": {"name": "ts"}, "y": [{"name": "close", "aggregate": "AVG", "label": "Close"}], "kind": "line", "group_by": [{"name": "symbol"}]}),
        (f"{prefix} · volume", {"chart_type": "xy", "x": {"name": "ts"}, "y": [{"name": "volume", "aggregate": "SUM", "label": "Volume"}], "kind": "bar", "group_by": [{"name": "symbol"}]}),
        (f"{prefix} · OHLCV rows", {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in ("symbol", "timeframe", "open", "high", "low", "close", "volume", "source")], "row_limit": 1000}),
    )
    chart_ids: list[int] = []
    for name, config in definitions:
        if name in existing:
            chart_id = int(existing[name]["id"])
            await _call(client, "update_chart", {"identifier": chart_id, "config": config, "chart_name": name, "generate_preview": False})
        else:
            response = await _call(client, "generate_chart", {"dataset_id": dataset_id, "config": config, "chart_name": name, "save_chart": True, "generate_preview": False})
            chart_id = int((response.get("chart") or {})["id"])
        chart_ids.append(chart_id)
    dashboards = await _call(client, "list_dashboards", {"search": dashboard_name, "page_size": 50})
    matching = [item for item in dashboards.get("dashboards", []) if item.get("dashboard_title") == dashboard_name]
    if matching:
        dashboard = matching[0]
        url = dashboard.get("url") or f"/superset/dashboard/{dashboard['id']}/"
    else:
        response = await _call(client, "generate_dashboard", {"chart_ids": chart_ids, "dashboard_title": dashboard_name, "description": description, "published": True})
        dashboard = response.get("dashboard") or {}
        url = response.get("dashboard_url") or dashboard.get("url") or f"/superset/dashboard/{dashboard['id']}/"
    return {"dataset_id": dataset_id, "chart_ids": chart_ids, "dashboard_url": url}


async def _seed_backtest_review(client: Client, datasets: list[dict[str, Any]]) -> dict[str, Any]:
    """Create one single-run backtest review dashboard from producer projections."""
    by_table = {item.get("table_name"): item for item in datasets}
    required = (
        "backtest_runs", "backtest_performance", "backtest_exposure", "backtest_equity_curve",
        "backtest_trades", "backtest_positions", "backtest_assumptions", "backtest_warnings",
        "backtest_provenance", "signal_lifecycle", "order_lifecycle", "fill_lifecycle",
        "backtest_evidence_coverage", "backtest_scope",
    )
    missing = [table for table in required if table not in by_table]
    if missing:
        raise RuntimeError(f"Backtest datasets are not registered: {', '.join(missing)}")

    prefix = "Trader backtest · MCP"
    chart_specs = (
        (
            f"{prefix} · run overview",
            by_table["backtest_runs"],
            {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in (
                "experiment_run_id", "run_id", "status", "strategy_name", "strategy_version",
                "symbols", "asset_class", "timeframe", "start_ts", "end_ts", "error_message",
            )], "row_limit": 100},
        ),
        (
            f"{prefix} · performance summary",
            by_table["backtest_performance"],
            {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in (
                "experiment_run_id", "run_id", "strategy_total_return", "benchmark_total_return",
                "strategy_sharpe", "strategy_max_drawdown", "strategy_trade_count", "warnings_count",
            )], "row_limit": 100},
        ),
        (
            f"{prefix} · strategy vs benchmark equity",
            by_table["backtest_equity_curve"],
            {"chart_type": "xy", "x": {"name": "ts"}, "y": [
                {"name": "strategy_equity", "label": "Strategy equity"},
                {"name": "benchmark_equity", "label": "Benchmark equity"},
            ], "kind": "line", "group_by": [{"name": "run_id"}]},
        ),
        (
            f"{prefix} · exposure and positions",
            by_table["backtest_exposure"],
            {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in (
                "experiment_run_id", "run_id", "avg_net_exposure", "avg_gross_exposure",
                "avg_invested_pct", "final_net_notional", "final_gross_notional", "position_count",
                "long_positions", "short_positions",
            )], "row_limit": 100},
        ),
        (
            f"{prefix} · executed trades",
            by_table["backtest_trades"],
            {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in (
                "experiment_run_id", "run_id", "trade_index", "symbol", "side", "fill_ts",
                "fill_qty", "fill_price", "fee_amount", "slippage_amount", "realized_pnl",
            )], "row_limit": 1000},
        ),
        (
            f"{prefix} · assumptions and evidence",
            by_table["backtest_assumptions"],
            {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in (
                "experiment_run_id", "run_id", "fill_model", "latency_ms", "fee_bps", "slippage_bps",
                "allow_latest_prior_bar", "allow_price_carry_forward",
            )], "row_limit": 100},
        ),
        (
            f"{prefix} · warnings",
            by_table["backtest_warnings"],
            {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in (
                "experiment_run_id", "run_id", "warning_index", "warning", "observed_at",
            )], "row_limit": 500},
        ),
        (
            f"{prefix} · provenance",
            by_table["backtest_provenance"],
            {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in (
                "experiment_run_id", "run_id", "provenance_key", "provenance_value", "observed_at",
            )], "row_limit": 500},
        ),
        (
            f"{prefix} · signal lifecycle",
            by_table["signal_lifecycle"],
            {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in (
                "run_id", "signal_event_id", "session_id", "cycle_id", "symbol", "signal_name",
                "signal_value", "target_qty", "generated_at", "mapper_id",
            )], "row_limit": 1000},
        ),
        (
            f"{prefix} · order lifecycle",
            by_table["order_lifecycle"],
            {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in (
                "run_id", "order_event_id", "client_order_id", "signal_event_id", "session_id",
                "cycle_id", "symbol", "side", "qty", "order_type", "status", "broker_order_id",
                "rejection_reason", "created_at",
            )], "row_limit": 1000},
        ),
        (
            f"{prefix} · fill lifecycle",
            by_table["fill_lifecycle"],
            {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in (
                "run_id", "fill_event_id", "client_order_id", "session_id", "cycle_id", "fill_ts",
                "fill_qty", "raw_fill_price", "fill_price", "fee_amount", "slippage_amount",
            )], "row_limit": 1000},
        ),
        (
            f"{prefix} · evidence coverage",
            by_table["backtest_evidence_coverage"],
            {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in (
                "experiment_run_id", "run_id", "observed_at", "signal_events_status",
                "order_events_status", "fill_events_status", "position_snapshots_status",
            )], "row_limit": 100},
        ),
        (
            f"{prefix} · comparison scope",
            by_table["backtest_scope"],
            {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in (
                "experiment_run_id", "run_id", "scope_fingerprint", "data_scope_id", "asset_class",
                "symbols", "timeframe", "replay_start", "replay_end", "benchmark_id",
                "benchmark_method", "benchmark_allocation", "initial_cash", "initial_position_count",
                "fill_model", "latency_ms", "fee_bps", "slippage_bps", "variant_fingerprint",
                "variant_strategy_id", "variant_strategy_version", "variant_parameters_fingerprint",
            )], "row_limit": 100},
        ),
    )
    charts = await _call(client, "list_charts", {"search": prefix, "page_size": 100})
    existing = {item.get("slice_name"): item for item in charts.get("charts", [])}
    chart_ids: list[int] = []
    for name, dataset, config in chart_specs:
        if name in existing:
            chart_id = int(existing[name]["id"])
            await _call(client, "update_chart", {"identifier": chart_id, "config": config, "chart_name": name, "generate_preview": False})
        else:
            response = await _call(client, "generate_chart", {"dataset_id": int(dataset["id"]), "config": config, "chart_name": name, "save_chart": True, "generate_preview": False})
            chart_id = int((response.get("chart") or {})["id"])
        chart_ids.append(chart_id)
    dashboard_name = f"{prefix} · single-run review"
    dashboards = await _call(client, "list_dashboards", {"search": dashboard_name, "page_size": 50})
    matching = [item for item in dashboards.get("dashboards", []) if item.get("dashboard_title") == dashboard_name]
    if matching:
        dashboard = matching[0]
        dashboard_id = int(dashboard["id"])
        dashboard_url = dashboard.get("url")
    else:
        response = await _call(client, "generate_dashboard", {
            "chart_ids": chart_ids,
            "dashboard_title": dashboard_name,
            "description": "Single-run backtest review over Trader-produced projections. Select one run in Explore; strategy and benchmark remain separate.",
            "published": True,
        })
        dashboard = response.get("dashboard") or {}
        dashboard_id = int(dashboard["id"])
        dashboard_url = response.get("dashboard_url") or dashboard.get("url")
    _configure_backtest_filters(
        dashboard_id=dashboard_id,
        dataset_ids=[int(by_table["backtest_runs"]["id"])],
        chart_ids=chart_ids,
    )
    return {"dashboard_url": dashboard_url, "chart_ids": chart_ids, "datasets": list(required)}


async def _seed_backtest_comparison(client: Client, datasets: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a bounded cohort dashboard over producer-owned comparison views."""
    by_table = {item.get("table_name"): item for item in datasets}
    required = ("backtest_comparison_runs", "backtest_comparison_curves")
    missing = [table for table in required if table not in by_table]
    if missing:
        raise RuntimeError(f"Comparison datasets are not registered: {', '.join(missing)}")

    prefix = "Trader backtest · MCP · comparison"
    chart_specs = (
        (
            f"{prefix} · cohort runs",
            by_table["backtest_comparison_runs"],
            {"chart_type": "table", "query_mode": "raw", "columns": [{"name": name} for name in (
                "run_id", "status", "scope_fingerprint", "data_scope_id", "benchmark_id",
                "variant_fingerprint", "variant_strategy_id", "variant_strategy_version",
                "strategy_total_return", "benchmark_total_return", "strategy_max_drawdown",
                "benchmark_max_drawdown", "strategy_sharpe", "strategy_trade_count", "warnings_count",
            )], "row_limit": 100},
        ),
        (
            f"{prefix} · normalized equity",
            by_table["backtest_comparison_curves"],
            {"chart_type": "xy", "x": {"name": "ts"}, "y": [
                {"name": "strategy_normalized", "label": "Strategy"},
                {"name": "benchmark_normalized", "label": "Benchmark"},
            ], "kind": "line", "group_by": [{"name": "run_id"}]},
        ),
        (
            f"{prefix} · drawdown",
            by_table["backtest_comparison_curves"],
            {"chart_type": "xy", "x": {"name": "ts"}, "y": [
                {"name": "strategy_drawdown", "label": "Strategy drawdown"},
                {"name": "benchmark_drawdown", "label": "Benchmark drawdown"},
            ], "kind": "line", "group_by": [{"name": "run_id"}]},
        ),
    )
    charts = await _call(client, "list_charts", {"search": prefix, "page_size": 100})
    existing = {item.get("slice_name"): item for item in charts.get("charts", [])}
    chart_ids: list[int] = []
    for name, dataset, config in chart_specs:
        if name in existing:
            chart_id = int(existing[name]["id"])
            await _call(client, "update_chart", {"identifier": chart_id, "config": config, "chart_name": name, "generate_preview": False})
        else:
            response = await _call(client, "generate_chart", {"dataset_id": int(dataset["id"]), "config": config, "chart_name": name, "save_chart": True, "generate_preview": False})
            chart_id = int((response.get("chart") or {})["id"])
        chart_ids.append(chart_id)
    dashboard_name = f"{prefix} · review"
    dashboards = await _call(client, "list_dashboards", {"search": dashboard_name, "page_size": 50})
    matching = [item for item in dashboards.get("dashboards", []) if item.get("dashboard_title") == dashboard_name]
    if matching:
        dashboard = matching[0]
        dashboard_id = int(dashboard["id"])
        dashboard_url = dashboard.get("url")
    else:
        response = await _call(client, "generate_dashboard", {
            "chart_ids": chart_ids,
            "dashboard_title": dashboard_name,
            "description": "Compatibility-gated comparison of Trader backtest runs. Select one scope fingerprint; variants remain explicit.",
            "published": True,
        })
        dashboard = response.get("dashboard") or {}
        dashboard_id = int(dashboard["id"])
        dashboard_url = response.get("dashboard_url") or dashboard.get("url")
    _configure_backtest_filters(
        dashboard_id=dashboard_id,
        dataset_ids=[int(by_table["backtest_comparison_runs"]["id"])],
        chart_ids=chart_ids,
        scope_filter=True,
    )
    return {"dashboard_url": dashboard_url, "chart_ids": chart_ids, "datasets": list(required)}


def _configure_backtest_filters(
    *, dashboard_id: int, dataset_ids: list[int], chart_ids: list[int], scope_filter: bool = False
) -> None:
    """Install shared run and time filters through Superset's dashboard API.

    Superset MCP 6.1 can create charts and dashboards but does not expose native
    filter metadata in its dashboard tool schema. The MCP-created dashboard is
    therefore completed through the supported REST dashboard contract, keeping
    filter ownership in this idempotent seed rather than in manual UI edits.
    """
    origin = os.getenv("SUPERSET_DEMO_UI_URL", "http://web:8088")
    password = os.environ["SUPERSET_DEMO_ADMIN_PASSWORD"]
    with httpx.Client(base_url=origin, timeout=20) as api:
        login = api.post(
            "/api/v1/security/login",
            json={"username": "admin", "password": password, "provider": "db", "refresh": True},
        )
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        csrf = api.get("/api/v1/security/csrf_token/", headers=headers)
        csrf.raise_for_status()
        headers.update({"X-CSRFToken": csrf.json()["result"], "Referer": f"{origin}/"})

        dashboard_response = api.get(f"/api/v1/dashboard/{dashboard_id}", headers=headers)
        dashboard_response.raise_for_status()
        dashboard = dashboard_response.json()["result"]
        metadata = json.loads(dashboard.get("json_metadata") or "{}")
        datasets = []
        for dataset_id in dataset_ids:
            dataset_response = api.get(f"/api/v1/dataset/{dataset_id}", headers=headers)
            dataset_response.raise_for_status()
            datasets.append(dataset_response.json()["result"])
        targets = [
            {"datasetUuid": dataset["uuid"], "column": {"name": "run_id"}}
            for dataset in datasets
        ]
        owned_ids = {"NATIVE_FILTER-TRADER-RUN", "NATIVE_FILTER-TRADER-TIME", "NATIVE_FILTER-TRADER-SCOPE"}
        filters = [
            item for item in metadata.get("native_filter_configuration", [])
            if item.get("id") not in owned_ids
        ]
        scope = {"excluded": [], "rootPath": ["ROOT_ID"]}
        filters.extend([
            {
                "cascadeParentIds": [],
                "chartsInScope": chart_ids,
                "controlValues": {
                    "defaultToFirstItem": False,
                    "enableEmptyFilter": False,
                    "inverseSelection": False,
                    "multiSelect": True,
                    "searchAllOptions": False,
                },
                "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
                "description": "Select one Trader-produced run across the review tables.",
                "filterType": "filter_select",
                "id": "NATIVE_FILTER-TRADER-RUN",
                "name": "Backtest run",
                "scope": scope,
                "targets": targets,
                "type": "NATIVE_FILTER",
            },
            {
                "cascadeParentIds": [],
                "chartsInScope": chart_ids,
                "controlValues": {"enableEmptyFilter": True},
                "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
                "description": "Limit the review to an observation time range.",
                "filterType": "filter_time",
                "id": "NATIVE_FILTER-TRADER-TIME",
                "name": "Observation time",
                "scope": scope,
                "targets": [{}],
                "type": "NATIVE_FILTER",
            },
        ])
        if scope_filter:
            filters.append({
                "cascadeParentIds": [],
                "chartsInScope": chart_ids,
                "controlValues": {
                    "defaultToFirstItem": False,
                    "enableEmptyFilter": False,
                    "inverseSelection": False,
                    "multiSelect": False,
                    "searchAllOptions": False,
                },
                "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
                "description": "Select one producer-owned compatibility scope before comparing runs.",
                "filterType": "filter_select",
                "id": "NATIVE_FILTER-TRADER-SCOPE",
                "name": "Scope fingerprint",
                "scope": scope,
                "targets": [
                    {"datasetUuid": dataset["uuid"], "column": {"name": "scope_fingerprint"}}
                    for dataset in datasets
                ],
                "type": "NATIVE_FILTER",
            })
        metadata["native_filter_configuration"] = filters
        update = api.put(
            f"/api/v1/dashboard/{dashboard_id}",
            headers=headers,
            json={"json_metadata": json.dumps(metadata, separators=(",", ":"))},
        )
        update.raise_for_status()


async def seed() -> None:
    """Register synthetic and real local OHLCV dashboards through MCP."""
    endpoint = os.getenv("SUPERSET_DEMO_MCP_URL", "http://mcp:5008/mcp")
    async with Client(endpoint) as client:
        datasets = await _call(client, "list_datasets", {"search": "stock_bars", "page_size": 50})
        candidates = [item for item in datasets.get("datasets", []) if item.get("table_name") == "stock_bars"]
        if not candidates:
            raise RuntimeError("Expected at least one stock_bars dataset")
        summaries = []
        for item in candidates:
            database_name = item.get("database_name") or item.get("database", "")
            is_real = database_name == "Trader local data"
            prefix = "Trader real · MCP" if is_real else PREFIX
            summaries.append(await _seed_dashboard(
                client,
                dataset_id=int(item["id"]),
                prefix=prefix,
                dashboard_name=f"{prefix} · bars",
                description=("MCP-generated views of real local Trader OHLCV data loaded from Alpaca."
                             if is_real else "MCP-generated views of the synthetic DEMO OHLCV fixture; not market evidence."),
            ))
        backtest_datasets_response = await _call(
            client,
            "list_datasets",
            {"page_size": 100},
        )
        review_tables = {
            "backtest_runs", "backtest_performance", "backtest_exposure", "backtest_equity_curve",
            "backtest_trades", "backtest_positions", "backtest_assumptions", "backtest_warnings",
            "backtest_provenance", "signal_lifecycle", "order_lifecycle", "fill_lifecycle",
            "backtest_evidence_coverage", "backtest_scope",
            "backtest_comparison_runs", "backtest_comparison_curves",
        }
        backtest_datasets = [
            item for item in backtest_datasets_response.get("datasets", [])
            if item.get("database_name") == "Trader synthetic demo"
            and item.get("table_name") in review_tables
        ]
        summaries.append(await _seed_backtest_review(client, backtest_datasets))
        summaries.append(await _seed_backtest_comparison(client, backtest_datasets))
        print(json.dumps(summaries, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(seed())
