"""Main page for the market data viewer."""

from __future__ import annotations

import reflex as rx

from ..state import DataViewerState


def _filter_card() -> rx.Component:
    """Filter card."""
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
                        max_=50000,
                        class_name="input",
                    ),
                    class_name="field",
                ),
                class_name="filter-row",
            ),
            rx.hstack(
                rx.box(
                    rx.text("Time range", class_name="field-label"),
                    rx.vstack(
                        rx.hstack(
                            rx.text("Start", class_name="range-label"),
                            rx.input(
                                value=DataViewerState.start_date,
                                on_change=DataViewerState.set_start_date,
                                type="date",
                                class_name="input",
                            ),
                            rx.input(
                                value=DataViewerState.start_time,
                                on_change=DataViewerState.set_start_time,
                                type="time",
                                step="60",
                                class_name="input",
                            ),
                            class_name="range-inputs",
                        ),
                        rx.hstack(
                            rx.text("End", class_name="range-label"),
                            rx.input(
                                value=DataViewerState.end_date,
                                on_change=DataViewerState.set_end_date,
                                type="date",
                                class_name="input",
                            ),
                            rx.input(
                                value=DataViewerState.end_time,
                                on_change=DataViewerState.set_end_time,
                                type="time",
                                step="60",
                                class_name="input",
                            ),
                            class_name="range-inputs",
                        ),
                        class_name="range-stack",
                    ),
                    class_name="field range-field",
                ),
                class_name="filter-row range-row",
            ),
        ),
        class_name="card",
    )


def _view_toggle() -> rx.Component:
    """Handle view toggle."""
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
    """Handle axis toggle."""
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


def _drag_toggle() -> rx.Component:
    """Handle drag toggle."""
    return rx.hstack(
        rx.text("Drag mode", class_name="field-label"),
        rx.cond(
            DataViewerState.drag_mode == "zoom",
            rx.button(
                "Zoom",
                on_click=lambda: DataViewerState.set_drag_mode("zoom"),
                class_name="toggle active",
            ),
            rx.button(
                "Zoom",
                on_click=lambda: DataViewerState.set_drag_mode("zoom"),
                class_name="toggle",
            ),
        ),
        rx.cond(
            DataViewerState.drag_mode == "pan",
            rx.button(
                "Pan",
                on_click=lambda: DataViewerState.set_drag_mode("pan"),
                class_name="toggle active",
            ),
            rx.button(
                "Pan",
                on_click=lambda: DataViewerState.set_drag_mode("pan"),
                class_name="toggle",
            ),
        ),
        class_name="toggle-row axis-toggle",
    )


def _table_view() -> rx.Component:
    """Handle table view."""
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
    """Handle chart view."""
    return rx.box(
        rx.cond(
            DataViewerState.chart_data,
            rx.box(
                rx.plotly(
                    data=DataViewerState.candlestick_figure,
                    config={
                        "displayModeBar": False,
                        "responsive": False,
                        "scrollZoom": True,
                        "doubleClick": "reset",
                    },
                    class_name="plotly-chart",
                ),
                class_name="chart-scroll",
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
    """Handle index."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text("Market Data Viewer", class_name="title"),
                    rx.text(
                        "Browse market data bars by type, ticker, and timeframe.",
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
            rx.cond(
                DataViewerState.view_mode == "chart",
                rx.vstack(_axis_toggle(), _drag_toggle(), spacing="2"),
                rx.box(height="0px"),
            ),
            rx.cond(DataViewerState.view_mode == "table", _table_view(), _chart_view()),
            spacing="6",
        ),
        class_name="app-shell",
    )
