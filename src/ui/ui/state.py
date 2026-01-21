"""Reflex state for the market data viewer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os
from pathlib import Path
from typing import Sequence

import duckdb
import plotly.graph_objects as go
import reflex as rx


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
    symbol: str = ""
    timeframe: str = ""
    limit: int = 200
    view_mode: str = "table"
    rows: list[dict[str, object]] = []
    chart_data: list[dict[str, object]] = []
    symbols: list[str] = []
    timeframes: list[str] = []
    error: str = ""

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
        x_values, customdata, tickvals, ticktext = self._build_axis(rows)
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
            title=f"{self.symbol} {self.timeframe}",
            margin=dict(l=70, r=50, t=40, b=60),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_rangeslider_visible=False,
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
            ),
            showlegend=False,
        )
        if self.axis_mode == "session":
            fig.update_xaxes(
                type="category",
                tickmode="auto",
                tickangle=-45,
            )
        else:
            if tickvals:
                fig.update_xaxes(
                    type="date",
                    tickmode="array",
                    tickvals=tickvals,
                    ticktext=ticktext,
                    tickangle=-45,
                )
            else:
                fig.update_xaxes(
                    type="date",
                    tickmode="auto",
                    nticks=12,
                    tickformat=self._axis_tickformat(),
                    tickangle=-45,
                )
        return fig

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
        self.limit = max(1, min(parsed, 5000))
        self._refresh_data()

    def set_view_mode(self, value: str) -> None:
        """Switch between table and chart views."""
        self.view_mode = value

    def set_axis_mode(self, value: str) -> None:
        """Switch between session and real-time axis modes."""
        self.axis_mode = value

    def _db_path(self) -> str:
        configured = os.getenv("UI_DB_PATH") or os.getenv("DB_PATH")
        if configured:
            path = Path(configured)
            if path.is_absolute():
                return str(path)
            root = Path(__file__).resolve().parents[3]
            return str(root / path)
        root = Path(__file__).resolve().parents[3]
        return str(root / "events.duckdb")

    def _table_name(self) -> str:
        return "stock_bar_events" if self.asset_type == "stock" else "crypto_bar_events"

    def _load_options(self) -> None:
        self.error = ""
        db_path = self._db_path()
        if not os.path.exists(db_path):
            self._reset_state(f"DB not found at {db_path}")
            return

        try:
            conn = duckdb.connect(db_path, read_only=True)
            table = self._table_name()
            symbols = [
                row[0]
                for row in conn.execute(
                    f"SELECT DISTINCT symbol FROM {table} ORDER BY symbol"
                ).fetchall()
            ]
            if self._has_timeframe_column(conn, table):
                timeframes = [
                    row[0]
                    for row in conn.execute(
                        f"""
                        SELECT DISTINCT COALESCE(timeframe, '1Min')
                        FROM {table}
                        ORDER BY 1
                        """
                    ).fetchall()
                ]
            else:
                timeframes = ["1Min"]
            conn.close()
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
        if not self.symbol or not self.timeframe:
            self.rows = []
            self.chart_data = []
            return
        db_path = self._db_path()
        if not os.path.exists(db_path):
            self._reset_state(f"DB not found at {db_path}")
            return

        try:
            conn = duckdb.connect(db_path, read_only=True)
            table = self._table_name()
            if self._has_timeframe_column(conn, table):
                rows = conn.execute(
                    f"""
                    SELECT ts, open, high, low, close, volume, vwap, trade_count
                    FROM {table}
                    WHERE symbol = ? AND COALESCE(timeframe, '1Min') = ?
                    ORDER BY ts DESC
                    LIMIT ?
                    """,
                    [self.symbol, self.timeframe, self.limit],
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT ts, open, high, low, close, volume, vwap, trade_count
                    FROM {table}
                    WHERE symbol = ?
                    ORDER BY ts DESC
                    LIMIT ?
                    """,
                    [self.symbol, self.limit],
                ).fetchall()
            conn.close()
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
        self.error = message
        self.rows = []
        self.chart_data = []
        self.symbols = []
        self.timeframes = []

    def _has_timeframe_column(self, conn: duckdb.DuckDBPyConnection, table: str) -> bool:
        columns = [row[1] for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()]
        return "timeframe" in columns

    def _default_axis_mode(self) -> str:
        return "session" if self.asset_type == "stock" else "real"

    def _build_axis(
        self,
        rows: list[dict[str, object]],
    ) -> tuple[list[object], list[list[object]], list[object], list[str]]:
        if self.axis_mode == "session":
            customdata = [
                [self._format_ts(self._parse_ts(row["ts"])), row["volume"]]
                for row in rows
            ]
            x_values = [self._format_ts(self._parse_ts(row["ts"])) for row in rows]
            return x_values, customdata, [], []
        timestamps = [self._parse_ts(row["ts"]) for row in rows]
        customdata = [
            [self._format_ts(ts), row["volume"]] for ts, row in zip(timestamps, rows)
        ]
        tickvals: list[object] = []
        ticktext: list[str] = []
        if len(timestamps) <= 400:
            tickvals = timestamps
            ticktext = [self._format_ts(ts) for ts in timestamps]
        return timestamps, customdata, tickvals, ticktext

    def _parse_ts(self, value: object) -> datetime:
        if isinstance(value, datetime):
            ts = value
        else:
            ts = datetime.fromisoformat(str(value))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    def _format_ts(self, ts: datetime) -> str:
        if self.asset_type == "stock":
            ts = ts.astimezone(ZoneInfo("America/New_York"))
        else:
            ts = ts.astimezone(timezone.utc)
        if self._is_daily_or_higher():
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m-%d %H:%M")

    def _is_daily_or_higher(self) -> bool:
        tf = self.timeframe.lower()
        if "day" in tf or "week" in tf or "month" in tf:
            return True
        if tf.endswith(("d", "w")):
            return True
        if tf.endswith("m") and not tf.endswith("min"):
            return True
        return False

    def _axis_tickformat(self) -> str:
        if self._is_daily_or_higher():
            return "%Y-%m-%d"
        return "%Y-%m-%d %H:%M"
