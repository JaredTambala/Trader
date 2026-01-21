"""Main page for the market data viewer."""

from __future__ import annotations

import reflex as rx

from ..state import DataViewerState


def _filter_card() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Filters", class_name="section-title"),
            rx.hstack(
                rx.box(
                    rx.text("Type", class_name="field-label"),
                    rx.select(
                        ["stock", "crypto"],
                        value=DataViewerState.asset_type,
                        on_change=DataViewerState.set_asset_type,
                        class_name="select",
                    ),
                    class_name="field",
                ),
                rx.box(
                    rx.text("Ticker", class_name="field-label"),
                    rx.select(
                        DataViewerState.symbols,
                        value=DataViewerState.symbol,
                        on_change=DataViewerState.set_symbol,
                        placeholder="Select symbol",
                        class_name="select",
                    ),
                    class_name="field",
                ),
                rx.box(
                    rx.text("Timeframe", class_name="field-label"),
                    rx.select(
                        DataViewerState.timeframes,
                        value=DataViewerState.timeframe,
                        on_change=DataViewerState.set_timeframe,
                        placeholder="Select timeframe",
                        class_name="select",
                    ),
                    class_name="field",
                ),
                rx.box(
                    rx.text("Limit", class_name="field-label"),
                    rx.input(
                        value=DataViewerState.limit,
                        on_change=DataViewerState.set_limit,
                        type="number",
                        min_=1,
                        max_=5000,
                        class_name="input",
                    ),
                    class_name="field",
                ),
                class_name="filter-row",
            ),
        ),
        class_name="card",
    )


def _view_toggle() -> rx.Component:
    return rx.hstack(
        rx.cond(
            DataViewerState.view_mode == "table",
            rx.button(
                "Table",
                on_click=lambda: DataViewerState.set_view_mode("table"),
                class_name="toggle active",
            ),
            rx.button(
                "Table",
                on_click=lambda: DataViewerState.set_view_mode("table"),
                class_name="toggle",
            ),
        ),
        rx.cond(
            DataViewerState.view_mode == "chart",
            rx.button(
                "Chart",
                on_click=lambda: DataViewerState.set_view_mode("chart"),
                class_name="toggle active",
            ),
            rx.button(
                "Chart",
                on_click=lambda: DataViewerState.set_view_mode("chart"),
                class_name="toggle",
            ),
        ),
        class_name="toggle-row",
    )


def _axis_toggle() -> rx.Component:
    return rx.hstack(
        rx.text("Axis mode", class_name="field-label"),
        rx.cond(
            DataViewerState.axis_mode == "session",
            rx.button(
                "Trading session",
                on_click=lambda: DataViewerState.set_axis_mode("session"),
                class_name="toggle active",
            ),
            rx.button(
                "Trading session",
                on_click=lambda: DataViewerState.set_axis_mode("session"),
                class_name="toggle",
            ),
        ),
        rx.cond(
            DataViewerState.axis_mode == "real",
            rx.button(
                "Real time",
                on_click=lambda: DataViewerState.set_axis_mode("real"),
                class_name="toggle active",
            ),
            rx.button(
                "Real time",
                on_click=lambda: DataViewerState.set_axis_mode("real"),
                class_name="toggle",
            ),
        ),
        class_name="toggle-row axis-toggle",
    )


def _table_view() -> rx.Component:
    columns = [
        {"name": "ts", "id": "ts"},
        {"name": "open", "id": "open"},
        {"name": "high", "id": "high"},
        {"name": "low", "id": "low"},
        {"name": "close", "id": "close"},
        {"name": "volume", "id": "volume"},
        {"name": "vwap", "id": "vwap"},
        {"name": "trade_count", "id": "trade_count"},
    ]
    return rx.data_table(
        data=DataViewerState.rows,
        columns=columns,
        pagination=True,
        page_size=25,
        class_name="table",
    )


def _chart_view() -> rx.Component:
    return rx.box(
        rx.cond(
            DataViewerState.chart_data,
            rx.plotly(
                data=DataViewerState.candlestick_figure,
                config={"displayModeBar": False},
                class_name="plotly-chart",
            ),
            rx.box(
                rx.text("No chart data available for the current filters."),
                class_name="empty-state",
            ),
        ),
        class_name="card chart-card",
    )


@rx.page(route="/", title="Trader Data Viewer", on_load=DataViewerState.on_load)
def index() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text("Market Data Viewer", class_name="title"),
                    rx.text(
                        "Browse DuckDB bars by type, ticker, and timeframe.",
                        class_name="subtitle",
                    ),
                    spacing="2",
                ),
                rx.badge("Stage 0", class_name="badge"),
                class_name="header",
            ),
            rx.cond(
                DataViewerState.error != "",
                rx.box(
                    rx.text(DataViewerState.error, class_name="error"),
                    class_name="card error-card",
                ),
                rx.box(height="0px"),
            ),
            _filter_card(),
            _view_toggle(),
            rx.cond(DataViewerState.view_mode == "chart", _axis_toggle(), rx.box(height="0px")),
            rx.cond(DataViewerState.view_mode == "table", _table_view(), _chart_view()),
            spacing="6",
        ),
        class_name="app-shell",
    )
