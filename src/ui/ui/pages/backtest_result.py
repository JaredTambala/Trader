"""Result dashboard for completed UI backtests."""

from __future__ import annotations

import reflex as rx

from ..state import DataViewerState


def _metric_card(label: str, value: str) -> rx.Component:
    """Render a metric badge."""
    return rx.vstack(
        rx.text(label, class_name="metric-label"),
        rx.text(value, class_name="metric-value"),
        class_name="metric-card",
    )


def _positions_table(data: list[dict[str, object]]) -> rx.Component:
    """Render position table."""
    columns = [
        {"name": "Symbol", "id": "symbol"},
        {"name": "Qty", "id": "qty"},
        {"name": "Avg Price", "id": "avg_price"},
        {"name": "Market Value", "id": "market_value"},
        {"name": "Unrealized PnL", "id": "unrealized_pnl"},
    ]
    return rx.data_table(data=data, columns=columns, pagination=True, page_size=5, class_name="positions-table")


@rx.page(route="/backtest/result", title="Backtest Results")
def backtest_result_page() -> rx.Component:
    """Display aggregated metrics + equity curve for the last run."""
    return rx.cond(
        DataViewerState.backtest_has_result,
        _build_result_page(),
        rx.box(
            rx.text("No backtest result yet.", class_name="empty-state"),
            rx.link("Run a backtest", href="/backtest", class_name="primary-link"),
            class_name="empty-page",
        ),
    )


def _build_result_page() -> rx.Component:
    """Render the main content for a completed backtest."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text("Backtest Results", class_name="title"),
                    rx.text(f"Run ID: {DataViewerState.backtest_result_run_id}", class_name="subtitle"),
                    class_name="result-header",
                ),
                rx.link("Back to form", href="/backtest", class_name="secondary-link"),
                class_name="header-row",
            ),
            rx.text(DataViewerState.backtest_status_message, class_name="status-message"),
            rx.hstack(
                _metric_card("Return", DataViewerState.backtest_metric_total_return),
                _metric_card("Sharpe", DataViewerState.backtest_metric_sharpe),
                _metric_card("Max Drawdown", DataViewerState.backtest_metric_max_drawdown),
                class_name="metrics-row",
            ),
            rx.box(
                rx.plotly(
                    data=DataViewerState.backtest_equity_figure,
                    config={"displayModeBar": False},
                    class_name="chart-card",
                ),
                class_name="chart-wrapper",
            ),
            rx.vstack(
                rx.text("Final Positions", class_name="section-title"),
                _positions_table(DataViewerState.backtest_positions_table),
                spacing="2",
            ),
            spacing="4",
        ),
        class_name="app-shell result-page",
    )
