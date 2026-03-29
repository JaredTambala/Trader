"""UI page for launching backtests."""

from __future__ import annotations

import reflex as rx

from ..state import DataViewerState


def _field(label: str, component: rx.Component) -> rx.Component:
    """Utility for form rows."""
    return rx.vstack(
        rx.text(label, class_name="field-label"),
        component,
        class_name="field",
    )


def _backtest_form() -> rx.Component:
    """Build the backtest form layout."""
    return rx.box(
        rx.vstack(
            rx.text("UI Backtest Runner", class_name="section-title"),
            rx.text(
                DataViewerState.backtest_status_message,
                class_name="status-message",
                font_size="sm",
            ),
            rx.cond(
                DataViewerState.backtest_run_id != "",
                rx.text(f"Run ID: {DataViewerState.backtest_run_id}", class_name="run-id"),
            ),
            rx.vstack(
                _field(
                    "Symbols (comma-separated)",
                    rx.input(
                        value=DataViewerState.backtest_symbols,
                        on_change=DataViewerState.set_backtest_symbols,
                        placeholder="e.g. AAPL, MSFT",
                        class_name="input",
                    ),
                ),
                _field(
                    "Asset class",
                    rx.select(
                        ["stocks", "crypto"],
                        value=DataViewerState.backtest_asset_class,
                        on_change=DataViewerState.set_backtest_asset_class,
                        class_name="input",
                    ),
                ),
                _field(
                    "Timeframe",
                    rx.input(
                        value=DataViewerState.backtest_timeframe,
                        on_change=DataViewerState.set_backtest_timeframe,
                        placeholder="1Min",
                        class_name="input",
                    ),
                ),
                _field(
                    "Start / End (UTC)",
                    rx.hstack(
                        rx.input(
                            value=DataViewerState.backtest_start,
                            on_change=DataViewerState.set_backtest_start,
                            type="datetime-local",
                            class_name="input",
                        ),
                        rx.input(
                            value=DataViewerState.backtest_end,
                            on_change=DataViewerState.set_backtest_end,
                            type="datetime-local",
                            class_name="input",
                        ),
                        class_name="range-inputs",
                    ),
                ),
                _field(
                    "Initial cash",
                    rx.input(
                        value=DataViewerState.backtest_initial_cash,
                        on_change=DataViewerState.set_backtest_initial_cash,
                        type="number",
                        class_name="input",
                    ),
                ),
                _field(
                    "Strategy JSON",
                    rx.text_area(
                        value=DataViewerState.backtest_strategy_params,
                        on_change=DataViewerState.set_backtest_strategy_params,
                        placeholder='{"signal": {"sma_short": 10, "sma_long": 20}}',
                        class_name="textarea",
                        min_rows=4,
                    ),
                ),
                rx.hstack(
                    rx.button(
                        "Start Backtest",
                        on_click=DataViewerState.start_backtest,
                        class_name="cta",
                    ),
                    rx.cond(
                        DataViewerState.backtest_polling_active,
                        rx.button(
                            "Refresh progress",
                            on_click=DataViewerState.poll_backtest_progress,
                            class_name="secondary-button",
                        ),
                    ),
                    rx.cond(
                        DataViewerState.backtest_run_id != "",
                        rx.button(
                            "Load results",
                            on_click=DataViewerState.fetch_backtest_result(DataViewerState.backtest_run_id),
                            class_name="secondary-button",
                        ),
                    ),
                    rx.cond(
                        DataViewerState.backtest_has_result,
                        rx.link("View results", href="/backtest/result", class_name="secondary-link"),
                    ),
                    rx.cond(
                        DataViewerState.backtest_progress != "",
                        rx.text(DataViewerState.backtest_progress, class_name="progress-label"),
                    ),
                    class_name="form-actions",
                ),
            ),
            class_name="backtest-form",
        ),
        class_name="card",
    )


@rx.page(route="/backtest", title="Backtest Runner")
def backtest() -> rx.Component:  # pragma: no cover - UI page
    """Backtest submission page."""
    return rx.box(_backtest_form(), class_name="app-shell")
