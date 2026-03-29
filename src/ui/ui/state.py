"""Reflex state for the market data viewer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Sequence
import os
import time

import plotly.graph_objects as go
import psycopg
from psycopg import sql
import reflex as rx
import requests


@dataclass(frozen=True)
class BarRow:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None
    trade_count: float | None


class DataViewerState(rx.State):
    """UI state for filtering and viewing market data."""

    asset_type: str = "stock"
    axis_mode: str = "session"
    drag_mode: str = "zoom"
    symbol: str = ""
    timeframe: str = ""
    limit: int = 1000
    view_mode: str = "table"
    rows: list[dict[str, object]] = []
    chart_data: list[dict[str, object]] = []
    symbols: list[str] = []
    timeframes: list[str] = []
    start_date: str = ""
    start_time: str = ""
    end_date: str = ""
    end_time: str = ""
    error: str = ""
    backtest_symbols: str = ""
    backtest_timeframe: str = "1Min"
    backtest_asset_class: str = "stocks"
    backtest_start: str = ""
    backtest_end: str = ""
    backtest_initial_cash: str = "100000"
    backtest_strategy_params: str = "{}"
    backtest_status_message: str = "Backtest runner idle"
    backtest_progress: str = ""
    backtest_run_id: str = ""
    backtest_result: dict[str, object] | None = None
    backtest_polling_active: bool = False
    BACKEND_URL: str = os.environ.get("BACKEND_BASE_URL", "http://localhost:8000")

    def set_backtest_result(self, result: dict[str, object]) -> None:
        """Store the fetched backtest result payload."""
        self.backtest_result = result

    @rx.var
    def backtest_equity_figure(self) -> go.Figure:
        """Build a Plotly chart for the backtest and benchmark curves."""
        fig = go.Figure()
        result = self.backtest_result or {}
        equity_curve = result.get("equity_curve") or []
        benchmark_curve = result.get("benchmark_curve") or []
        if equity_curve:
            fig.add_trace(
                go.Scatter(
                    x=[point["ts"] for point in equity_curve],
                    y=[point["equity"] for point in equity_curve],
                    mode="lines",
                    name="Equity",
                    line=dict(color="#2f9e44"),
                )
            )
        if benchmark_curve:
            fig.add_trace(
                go.Scatter(
                    x=[point["ts"] for point in benchmark_curve],
                    y=[point["equity"] for point in benchmark_curve],
                    mode="lines",
                    name="Benchmark",
                    line=dict(color="#495057", dash="dash"),
                )
            )
        fig.update_layout(
            margin=dict(l=40, r=20, t=40, b=40),
            xaxis=dict(title="Time"),
            yaxis=dict(title="Equity"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            template="simple_white",
        )
        return fig

    @rx.var
    def backtest_has_result(self) -> bool:
        """Return True when a backtest result is available."""
        return self.backtest_result is not None

    @rx.var
    def backtest_result_run_id(self) -> str:
        """Return the run_id from the result (or the last submitted run_id)."""
        result = self.backtest_result or {}
        run_id = result.get("run_id") or self.backtest_run_id
        return str(run_id) if run_id is not None else ""

    @rx.var
    def backtest_metric_total_return(self) -> str:
        """Formatted total return for the latest backtest."""
        stats = (self.backtest_result or {}).get("strategy_performance") or {}
        return f"{stats.get('total_return', 0.0):.2%}"

    @rx.var
    def backtest_metric_sharpe(self) -> str:
        """Formatted Sharpe ratio for the latest backtest."""
        stats = (self.backtest_result or {}).get("strategy_performance") or {}
        return f"{stats.get('sharpe', 0.0):.2f}"

    @rx.var
    def backtest_metric_max_drawdown(self) -> str:
        """Formatted max drawdown for the latest backtest."""
        stats = (self.backtest_result or {}).get("strategy_performance") or {}
        return f"{stats.get('max_drawdown', 0.0):.2%}"

    @rx.var
    def backtest_positions_table(self) -> list[dict[str, object]]:
        """Prepare a formatted positions table for the backtest result."""
        positions = (self.backtest_result or {}).get("positions") or []
        rows: list[dict[str, object]] = []
        for pos in positions:
            rows.append(
                {
                    "symbol": pos.get("symbol"),
                    "qty": f"{pos.get('qty', 0):.4f}",
                    "avg_price": f"{pos.get('avg_price', 0.0):.2f}",
                    "market_value": f"{pos.get('market_value', 0.0):.2f}",
                    "unrealized_pnl": f"{pos.get('unrealized_pnl', 0.0):.2f}",
                }
            )
        return rows

    @rx.event
    def poll_backtest_progress(self) -> None:
        """Poll the backtest progress endpoint for the active run."""
        if not self.backtest_polling_active or not self.backtest_run_id:
            return
        run_id = self.backtest_run_id
        try:
            resp = requests.get(f"{self.BACKEND_URL}/backtest/progress", params={"run_id": run_id}, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            progress = data.get("progress") or {}
            percent = progress.get("percent", 0.0)
            self.backtest_progress = f"{percent:.1f}%"
            status = data.get("status", "unknown")
            self.backtest_status_message = f"Backtest {run_id} {status}"
            if status in {"completed", "failed"}:
                self.backtest_polling_active = False
                if status == "completed":
                    self.fetch_backtest_result(run_id)
                else:
                    error = data.get("error")
                    if error:
                        self.backtest_status_message = f"Backtest {run_id} failed: {error}"
        except Exception as exc:
            self.backtest_status_message = f"Progress poll failed: {exc}"
            self.backtest_polling_active = False

    @rx.event
    def fetch_backtest_result(self, run_id: str) -> None:
        """Fetch the completed backtest result and store it in state."""
        try:
            resp = requests.get(f"{self.BACKEND_URL}/backtest/result", params={"run_id": run_id}, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            result = data.get("result") or {}
            self.set_backtest_result(result)
            self.backtest_status_message = f"Backtest {run_id} completed"
        except Exception as exc:
            self.backtest_status_message = f"Result fetch failed: {exc}"

    def on_load(self) -> None:
        """Initial load for options and data."""
        if not self.axis_mode:
            self.axis_mode = self._default_axis_mode()
        self._load_options()
        self._refresh_data()

    @rx.var
    def candlestick_figure(self) -> go.Figure:
        """Build a Plotly candlestick figure from chart data."""
        if not self.chart_data:
            return go.Figure()
        rows = sorted(self.chart_data, key=lambda row: self._parse_ts(row["ts"]))
        chart_width = self._chart_width_px(len(rows))
        x_values, customdata = self._build_axis(rows)
        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=x_values,
                    open=[row["open"] for row in rows],
                    high=[row["high"] for row in rows],
                    low=[row["low"] for row in rows],
                    close=[row["close"] for row in rows],
                    customdata=customdata,
                    increasing_line_color="#2f9e44",
                    decreasing_line_color="#e03131",
                    hovertemplate=(
                        "Time: %{customdata[0]}<br>"
                        "Open: %{open}<br>"
                        "High: %{high}<br>"
                        "Low: %{low}<br>"
                        "Close: %{close}<br>"
                        "Volume: %{customdata[1]}<extra></extra>"
                    ),
                )
            ]
        )
        fig.update_layout(
            title=dict(
                text=self._chart_title(),
                x=0.02,
                y=0.98,
                xanchor="left",
                yanchor="top",
                font=dict(size=16, color="#1f1a17"),
            ),
            width=chart_width,
            height=1024,
            margin=dict(l=70, r=50, t=40, b=60),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_rangeslider_visible=False,
            dragmode=self.drag_mode,
            xaxis=dict(
                title=dict(text="Time", font=dict(size=14, color="#1f1a17")),
                showline=True,
                linecolor="#1f1a17",
                ticks="outside",
                tickfont=dict(size=12, color="#1f1a17"),
                gridcolor="rgba(31, 26, 23, 0.15)",
            ),
            yaxis=dict(
                title=dict(text="Price", font=dict(size=14, color="#1f1a17")),
                showline=True,
                linecolor="#1f1a17",
                ticks="outside",
                tickfont=dict(size=12, color="#1f1a17"),
                gridcolor="rgba(31, 26, 23, 0.15)",
                fixedrange=True,
            ),
            showlegend=False,
        )
        if self.axis_mode == "session":
            fig.update_xaxes(
                type="category",
                tickmode="auto",
                nticks=14,
                tickangle=-45,
            )
        else:
            fig.update_xaxes(
                type="date",
                tickmode="auto",
                nticks=14,
                tickformat=self._axis_tickformat(),
                tickangle=-45,
            )
        return fig

    def _chart_width_px(self, row_count: int) -> int:
        """Return the fixed chart width for reliable zoom selection."""
        base_width = 1280
        return base_width

    def _chart_title(self) -> str:
        """Handle chart title."""
        asset_label = "Stock" if self.asset_type == "stock" else "Crypto"
        symbol = self.symbol or "Unknown"
        timeframe = self.timeframe or "Unknown"
        start = self.start_date or "Any"
        end = self.end_date or "Any"
        return f"{asset_label} bars: {symbol} ({timeframe}) | {start} → {end}"

    def set_asset_type(self, value: str) -> None:
        """Set asset type and reload options."""
        self.asset_type = value
        self.axis_mode = self._default_axis_mode()
        self._load_options()
        self._refresh_data()

    def set_symbol(self, value: str) -> None:
        """Set symbol and refresh data."""
        self.symbol = value
        self._refresh_data()

    def set_timeframe(self, value: str) -> None:
        """Set timeframe and refresh data."""
        self.timeframe = value
        self._refresh_data()

    def set_limit(self, value: str) -> None:
        """Set row limit with safe parsing."""
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return
        self.limit = max(1, min(parsed, 50000))
        self._refresh_data()

    def set_view_mode(self, value: str) -> None:
        """Switch between table and chart views."""
        self.view_mode = value

    def set_axis_mode(self, value: str) -> None:
        """Switch between session and real-time axis modes."""
        self.axis_mode = value

    def set_drag_mode(self, value: str) -> None:
        """Switch between zoom and pan drag modes."""
        self.drag_mode = value

    def set_start_date(self, value: str) -> None:
        """Set the start date filter."""
        self.start_date = value
        self._refresh_data()

    def set_start_time(self, value: str) -> None:
        """Set the start time filter."""
        self.start_time = value
        self._refresh_data()

    def set_end_date(self, value: str) -> None:
        """Set the end date filter."""
        self.end_date = value
        self._refresh_data()

    def set_end_time(self, value: str) -> None:
        """Set the end time filter."""
        self.end_time = value
        self._refresh_data()

    def set_backtest_symbols(self, value: str) -> None:
        """Set the symbols string used by the backtest form."""
        self.backtest_symbols = value

    def set_backtest_timeframe(self, value: str) -> None:
        """Set the backtest timeframe."""
        self.backtest_timeframe = value

    def set_backtest_asset_class(self, value: str) -> None:
        """Set the backtest asset class."""
        self.backtest_asset_class = value

    def set_backtest_start(self, value: str) -> None:
        """Set the starting timestamp for backtests."""
        self.backtest_start = value

    def set_backtest_end(self, value: str) -> None:
        """Set the ending timestamp for backtests."""
        self.backtest_end = value

    def set_backtest_initial_cash(self, value: str) -> None:
        """Update the initial cash value for the backtest."""
        self.backtest_initial_cash = value

    def set_backtest_strategy_params(self, value: str) -> None:
        """Set the strategy parameter JSON for the backtest."""
        self.backtest_strategy_params = value

    @rx.event
    def start_backtest(self) -> None:
        """Record a UI-driven backtest submission."""
        self.backtest_status_message = "Submitting backtest..."
        self.backtest_progress = ""
        self.backtest_run_id = ""
        self.backtest_result = None
        yield
        symbols = [symbol.strip().upper() for symbol in self.backtest_symbols.split(",") if symbol.strip()]
        if not symbols:
            self.backtest_status_message = "Failed to start backtest: symbols required"
            yield
            return
        if not self.backtest_start or not self.backtest_end:
            self.backtest_status_message = "Failed to start backtest: start/end required"
            yield
            return
        try:
            initial_cash = float(self.backtest_initial_cash or 0.0)
        except ValueError:
            self.backtest_status_message = "Failed to start backtest: initial cash must be a number"
            yield
            return
        strategy_params: object | None
        if not self.backtest_strategy_params.strip():
            strategy_params = None
        else:
            try:
                strategy_params = json.loads(self.backtest_strategy_params)
            except json.JSONDecodeError as exc:
                self.backtest_status_message = f"Failed to start backtest: invalid strategy JSON ({exc})"
                yield
                return
        asset_class = self.backtest_asset_class or "stocks"
        asset_class = asset_class.strip().lower()
        if asset_class in {"stock", "stocks"}:
            asset_class = "stocks"
        elif asset_class in {"crypto", "cryptocurrency"}:
            asset_class = "crypto"
        payload = {
            "symbols": symbols,
            "timeframe": self.backtest_timeframe,
            "start": self.backtest_start,
            "end": self.backtest_end,
            "initial_cash": initial_cash,
            "strategy_params": strategy_params,
            "asset_class": asset_class,
        }
        try:
            response = requests.post(f"{self.BACKEND_URL}/backtest", json=payload, timeout=5)
            response.raise_for_status()
            run_id = response.json()["run_id"]
        except requests.HTTPError as exc:
            detail = ""
            try:
                detail = response.text
            except Exception:
                detail = ""
            suffix = f" ({detail})" if detail else ""
            self.backtest_status_message = f"Failed to start backtest: {exc}{suffix}"
            yield
            return
        except Exception as exc:
            self.backtest_status_message = f"Failed to start backtest: {exc}"
            yield
            return
        self.backtest_run_id = run_id
        self.backtest_progress = "0%"
        self.backtest_status_message = f"Backtest {run_id} queued"
        self.backtest_polling_active = True
        yield


    def _pg_connection(self) -> psycopg.Connection:
        """Handle pg connection."""
        dsn = os.getenv("UI_PG_DSN") or os.getenv("PG_DSN")
        if dsn:
            return psycopg.connect(dsn, autocommit=True)
        host = os.getenv("UI_PG_HOST") or os.getenv("PG_HOST")
        port = os.getenv("UI_PG_PORT") or os.getenv("PG_PORT") or "5432"
        dbname = os.getenv("UI_PG_DB") or os.getenv("PG_DB")
        user = os.getenv("UI_PG_USER") or os.getenv("PG_USER")
        password = os.getenv("UI_PG_PASSWORD") or os.getenv("PG_PASSWORD")
        if not (host and dbname and user and password):
            raise ValueError("Postgres env vars missing (PG_HOST/PG_DB/PG_USER/PG_PASSWORD)")
        return psycopg.connect(
            host=host,
            port=int(port),
            dbname=dbname,
            user=user,
            password=password,
            autocommit=True,
        )

    def _table_name(self) -> str:
        """Handle table name."""
        return "stock_bar_events" if self.asset_type == "stock" else "crypto_bar_events"

    def _load_options(self) -> None:
        """Load options."""
        self.error = ""
        try:
            table = self._table_name()
            with self._pg_connection() as conn, conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT DISTINCT symbol FROM {table} ORDER BY symbol").format(
                        table=sql.Identifier(table)
                    )
                )
                symbols = [row[0] for row in cursor.fetchall()]
                if self._has_timeframe_column_postgres(cursor, table):
                    cursor.execute(
                        sql.SQL(
                            """
                            SELECT DISTINCT COALESCE(timeframe, '1Min')
                            FROM {table}
                            ORDER BY 1
                            """
                        ).format(table=sql.Identifier(table))
                    )
                    timeframes = [row[0] for row in cursor.fetchall()]
                else:
                    timeframes = ["1Min"]
        except Exception as exc:
            self._reset_state(f"DB query failed: {exc}")
            return

        self.symbols = symbols
        self.timeframes = timeframes
        if self.symbol not in symbols:
            self.symbol = symbols[0] if symbols else ""
        if self.timeframe not in timeframes:
            self.timeframe = timeframes[0] if timeframes else ""

    def _refresh_data(self) -> None:
        """Handle refresh data."""
        if not self.symbol or not self.timeframe:
            self.rows = []
            self.chart_data = []
            return

        try:
            table = self._table_name()
            start_ts, end_ts = self._normalized_time_range()
            with self._pg_connection() as conn, conn.cursor() as cursor:
                where_clauses = ["symbol = %s", "COALESCE(timeframe, '1Min') = %s"]
                params: list[object] = [self.symbol, self.timeframe]
                if start_ts:
                    where_clauses.append("ts >= %s")
                    params.append(start_ts)
                if end_ts:
                    where_clauses.append("ts <= %s")
                    params.append(end_ts)
                where_sql = " AND ".join(where_clauses)
                if self._has_timeframe_column_postgres(cursor, table):
                    cursor.execute(
                        sql.SQL(
                            """
                            SELECT ts, open, high, low, close, volume, vwap, trade_count
                            FROM {table}
                            WHERE {where_sql}
                            ORDER BY ts DESC
                            LIMIT %s
                            """
                        ).format(
                            table=sql.Identifier(table),
                            where_sql=sql.SQL(where_sql),
                        ),
                        [*params, self.limit],
                    )
                else:
                    where_clauses = ["symbol = %s"]
                    params = [self.symbol]
                    if start_ts:
                        where_clauses.append("ts >= %s")
                        params.append(start_ts)
                    if end_ts:
                        where_clauses.append("ts <= %s")
                        params.append(end_ts)
                    where_sql = " AND ".join(where_clauses)
                    cursor.execute(
                        sql.SQL(
                            """
                            SELECT ts, open, high, low, close, volume, vwap, trade_count
                            FROM {table}
                            WHERE {where_sql}
                            ORDER BY ts DESC
                            LIMIT %s
                            """
                        ).format(
                            table=sql.Identifier(table),
                            where_sql=sql.SQL(where_sql),
                        ),
                        [*params, self.limit],
                    )
                rows = cursor.fetchall()
        except Exception as exc:
            self._reset_state(f"DB query failed: {exc}")
            return

        formatted = [self._format_row(row) for row in rows]
        self.rows = formatted
        self.chart_data = list(reversed(formatted))
        if self.rows:
            self.error = ""
        else:
            self.error = "No rows returned for the current filters."

    def _format_row(self, row: Sequence[object]) -> dict[str, object]:
        """Format row."""
        ts_value = row[0]
        if isinstance(ts_value, datetime):
            ts_value = ts_value.isoformat()
        return {
            "ts": ts_value,
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
            "volume": row[5],
            "vwap": row[6],
            "trade_count": row[7],
        }

    def _reset_state(self, message: str) -> None:
        """Handle reset state."""
        self.error = message
        self.rows = []
        self.chart_data = []
        self.symbols = []
        self.timeframes = []
        self.start_date = ""
        self.start_time = ""
        self.end_date = ""
        self.end_time = ""

    def _has_timeframe_column_postgres(self, cursor: psycopg.Cursor, table: str) -> bool:
        """Handle has timeframe column postgres."""
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'timeframe'
            """,
            [table],
        )
        return cursor.fetchone() is not None

    def _normalized_time_range(self) -> tuple[datetime | None, datetime | None]:
        """Handle normalized time range."""
        start = self._parse_input_datetime(self.start_date, self.start_time, is_end=False)
        end = self._parse_input_datetime(self.end_date, self.end_time, is_end=True)
        if start and end and start > end:
            start, end = end, start
        return start, end

    def _parse_input_datetime(
        self,
        date_value: str,
        time_value: str,
        *,
        is_end: bool,
    ) -> datetime | None:
        """Parse input datetime."""
        if not date_value:
            return None
        try:
            year_str, month_str, day_str = date_value.split("-")
            year, month, day = int(year_str), int(month_str), int(day_str)
        except ValueError:
            return None

        hour = 0
        minute = 0
        second = 0
        if time_value:
            parts = [int(part) for part in time_value.split(":") if part]
            if len(parts) >= 2:
                hour, minute = parts[0], parts[1]
            if len(parts) >= 3:
                second = parts[2]
        elif is_end:
            hour, minute, second = 23, 59, 59

        tz = ZoneInfo("America/New_York") if self.asset_type == "stock" else timezone.utc
        local_ts = datetime(year, month, day, hour, minute, second, tzinfo=tz)
        return local_ts.astimezone(timezone.utc)

    def _default_axis_mode(self) -> str:
        """Handle default axis mode."""
        return "session" if self.asset_type == "stock" else "real"

    def _build_axis(
        self,
        rows: list[dict[str, object]],
    ) -> tuple[list[object], list[list[object]]]:
        """Build axis."""
        row_count = len(rows)
        if self.axis_mode == "session":
            customdata = [[self._format_ts(self._parse_ts(row["ts"])), row["volume"]] for row in rows]
            x_values = [self._format_ts(self._parse_ts(row["ts"])) for row in rows]
            return x_values, customdata
        timestamps = [self._parse_ts(row["ts"]) for row in rows]
        customdata = [[self._format_ts(ts), row["volume"]] for ts, row in zip(timestamps, rows)]
        return timestamps, customdata

    def _parse_ts(self, value: object) -> datetime:
        """Parse ts."""
        if isinstance(value, datetime):
            ts = value
        else:
            ts = datetime.fromisoformat(str(value))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    def _format_ts(self, ts: datetime) -> str:
        """Format ts."""
        if self.asset_type == "stock":
            ts = ts.astimezone(ZoneInfo("America/New_York"))
        else:
            ts = ts.astimezone(timezone.utc)
        if self._is_daily_or_higher():
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m-%d %H:%M")

    def _is_daily_or_higher(self) -> bool:
        """Return whether daily or higher."""
        tf = self.timeframe.lower()
        if "day" in tf or "week" in tf or "month" in tf:
            return True
        if tf.endswith(("d", "w")):
            return True
        if tf.endswith("m") and not tf.endswith("min"):
            return True
        return False

    def _axis_tickformat(self) -> str:
        """Handle axis tickformat."""
        if self._is_daily_or_higher():
            return "%Y-%m-%d"
        return "%Y-%m-%d %H:%M"
