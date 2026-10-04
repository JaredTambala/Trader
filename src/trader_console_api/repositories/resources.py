"""Read repositories for the Console's published data resources."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
import json
from typing import Any, Literal

from .database import ConsoleDatabase

AssetClass = Literal["stock", "crypto"]

_DATASET_SQL = """
WITH datasets AS (
    SELECT 'stock'::text AS asset_class, symbol, timeframe, source,
           min(ts) AS first_ts, max(ts) AS last_ts, count(*)::integer AS bar_count
    FROM console_read.stock_bars
    GROUP BY symbol, timeframe, source
    UNION ALL
    SELECT 'crypto'::text AS asset_class, symbol, timeframe, source,
           min(ts) AS first_ts, max(ts) AS last_ts, count(*)::integer AS bar_count
    FROM console_read.crypto_bars
    GROUP BY symbol, timeframe, source
)
SELECT datasets.*, count(*) OVER()::integer AS total_count
FROM datasets
ORDER BY asset_class, symbol, timeframe, source NULLS LAST
LIMIT %s OFFSET %s
"""

_BARS_RELATIONS: dict[AssetClass, str] = {
    "stock": "console_read.stock_bars",
    "crypto": "console_read.crypto_bars",
}


async def _coverage_rows(connection: Any, *, asset_class: AssetClass, symbol: str, timeframe: str) -> dict[str, Any]:
    """Read one symbol/timeframe coverage aggregate from the stable bar view."""
    relation = _BARS_RELATIONS[asset_class]
    cursor = await connection.execute(
        "SELECT min(ts) AS first_ts, max(ts) AS last_ts, count(*)::integer AS bar_count "
        f"FROM {relation} WHERE symbol = %s AND timeframe = %s",
        [symbol, timeframe],
    )
    rows = await cursor.fetchall()
    values = rows[0] if rows else (None, None, 0)
    return {
        "symbol": symbol,
        "asset_class": asset_class,
        "timeframe": timeframe,
        "first_ts": values[0],
        "last_ts": values[1],
        "bar_count": int(values[2] or 0),
    }

_EXPERIMENTS_SQL = """
SELECT experiment_id, count(*)::integer AS run_count,
       max(created_at) AS latest_created_at,
       array_agg(DISTINCT status ORDER BY status) AS statuses,
       count(*) OVER()::integer AS total_count
FROM console_read.backtest_runs
GROUP BY experiment_id
ORDER BY max(created_at) DESC NULLS LAST, experiment_id
LIMIT %s OFFSET %s
"""

_RUNS_SQL = """
WITH target AS (
    SELECT scope.run_id AS target_run_id,
           scope.scope_fingerprint AS target_scope_fingerprint
    FROM console_read.backtest_scope AS scope
    WHERE scope.run_id = %s
    LIMIT 1
)
SELECT runs.*, scope.scope_fingerprint, scope.data_scope_id, scope.benchmark_id,
       scope.variant_fingerprint, scope.variant_strategy_id,
       scope.variant_strategy_version,
       (comparison.run_id IS NOT NULL) AS comparison_projection_available,
       CASE
           WHEN scope.scope_fingerprint IS NULL THEN false
           WHEN comparison.run_id IS NULL THEN false
           WHEN %s::text IS NULL THEN true
           WHEN target.target_run_id IS NULL THEN false
           WHEN scope.scope_fingerprint = target.target_scope_fingerprint THEN true
           ELSE false
       END AS comparison_eligible,
       CASE
           WHEN scope.scope_fingerprint IS NULL THEN 'missing_scope_fingerprint'
           WHEN comparison.run_id IS NULL THEN 'no_comparison_projection'
           WHEN %s::text IS NULL THEN NULL
           WHEN target.target_run_id IS NULL THEN 'target_run_not_found'
           WHEN target.target_run_id IS NOT NULL
                AND target.target_scope_fingerprint IS NULL
                THEN 'target_missing_scope_fingerprint'
           WHEN target.target_run_id IS NOT NULL
                AND scope.scope_fingerprint <> target.target_scope_fingerprint
                THEN 'scope_mismatch'
           ELSE NULL
       END AS comparison_exclusion_reason,
       count(*) OVER()::integer AS total_count
FROM console_read.backtest_runs AS runs
LEFT JOIN console_read.backtest_scope AS scope ON scope.run_id = runs.run_id
LEFT JOIN console_read.backtest_comparison_runs AS comparison ON comparison.run_id = runs.run_id
LEFT JOIN target ON true
WHERE runs.experiment_id = %s
ORDER BY runs.created_at DESC NULLS LAST, runs.run_id
LIMIT %s OFFSET %s
"""


def _row_dicts(cursor: Any, rows: Sequence[Sequence[Any]]) -> list[dict[str, Any]]:
    """Convert Psycopg rows to ordinary dictionaries at the adapter boundary."""
    names = []
    for column in cursor.description:
        name = getattr(column, "name", None)
        names.append(str(name if name is not None else column[0]))
    return [dict(zip(names, row, strict=True)) for row in rows]


def _total(rows: Sequence[dict[str, Any]]) -> int:
    """Read a window-count value without leaking SQL bookkeeping fields."""
    if not rows:
        return 0
    return int(rows[0].get("total_count", 0) or 0)


def _strip_total(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        row.pop("total_count", None)
    return rows


class ConsoleResourceRepository:
    """Query only stable, producer-owned ``console_read`` projections."""

    def __init__(self, database: ConsoleDatabase) -> None:
        """Bind resource queries to the API's transaction policy."""
        self._database = database

    async def list_market_datasets(self, *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """List available symbol/timeframe/source slices."""
        async with self._database.transaction() as connection:
            cursor = await connection.execute(_DATASET_SQL, [limit, offset])
            rows = _row_dicts(cursor, await cursor.fetchall())
        total = _total(rows)
        return _strip_total(rows), total

    async def get_market_data_evidence(
        self,
        *,
        asset_class: AssetClass,
        symbols: tuple[str, ...],
        timeframe: str,
        interval: str,
        bar_type: str,
        start: datetime,
        end: datetime,
        provider: str | None,
        source_policy: str | None,
    ) -> dict[str, Any] | None:
        """Resolve one exact Data manifest/quality pair from the producer projection.

        The API never reconstructs quality or joins raw artifact payloads. The
        producer-owned ``console_read.data_scope_evidence`` view resolves the
        canonical pair and preserves explicit unavailable/partial/stale states.
        """
        query = """
        SELECT *
        FROM console_read.data_scope_evidence
        WHERE asset_class = %s
          AND symbols = %s::jsonb
          AND timeframe = %s
          AND interval = %s
          AND bar_type = %s
          AND requested_start = %s
          AND requested_end = %s
          AND COALESCE(provider, '') = COALESCE(%s, '')
          AND COALESCE(source_policy, '') = COALESCE(%s, '')
        ORDER BY quality_updated_at DESC NULLS LAST, manifest_updated_at DESC NULLS LAST
        LIMIT 1
        """
        parameters = [
            asset_class,
            json.dumps(list(symbols), separators=(",", ":")),
            timeframe,
            interval,
            bar_type,
            start,
            end,
            provider,
            source_policy,
        ]
        async with self._database.transaction() as connection:
            cursor = await connection.execute(query, parameters)
            rows = _row_dicts(cursor, await cursor.fetchall())
        return rows[0] if rows else None

    async def list_bars(
        self,
        *,
        asset_class: AssetClass,
        symbol: str,
        timeframe: str,
        source: str | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """List bounded OHLCV observations with server-owned relation selection."""
        filters = ["symbol = %s", "timeframe = %s"]
        parameters: list[Any] = [symbol, timeframe]
        if source is not None:
            filters.append("source = %s")
            parameters.append(source)
        if start is not None:
            filters.append("ts >= %s")
            parameters.append(start)
        if end is not None:
            filters.append("ts <= %s")
            parameters.append(end)
        relation = _BARS_RELATIONS[asset_class]
        query = (
            "SELECT bars.*, count(*) OVER()::integer AS total_count "
            f"FROM {relation} AS bars WHERE {' AND '.join(filters)} "
            "ORDER BY ts ASC LIMIT %s OFFSET %s"
        )
        parameters.extend([limit, offset])
        async with self._database.transaction() as connection:
            cursor = await connection.execute(query, parameters)
            rows = _row_dicts(cursor, await cursor.fetchall())
        total = _total(rows)
        return _strip_total(rows), total

    async def backtest_coverage(
        self,
        *,
        asset_class: AssetClass,
        symbols: Sequence[str],
        timeframe: str,
    ) -> list[dict[str, Any]]:
        """Read bounded coverage aggregates for preflight without loading bars."""
        async with self._database.transaction() as connection:
            return [
                await _coverage_rows(
                    connection,
                    asset_class=asset_class,
                    symbol=symbol,
                    timeframe=timeframe,
                )
                for symbol in symbols
            ]

    async def list_experiments(self, *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """Discover experiment groups from published backtest-run membership."""
        async with self._database.transaction() as connection:
            cursor = await connection.execute(_EXPERIMENTS_SQL, [limit, offset])
            rows = _row_dicts(cursor, await cursor.fetchall())
        total = _total(rows)
        return _strip_total(rows), total

    async def list_experiment_runs(
        self,
        *,
        experiment_id: str,
        compatible_with_run_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """List runs and calculate comparison eligibility from scope fingerprints."""
        parameters: list[Any] = [
            compatible_with_run_id,
            compatible_with_run_id,
            compatible_with_run_id,
            experiment_id,
            limit,
            offset,
        ]
        async with self._database.transaction() as connection:
            cursor = await connection.execute(_RUNS_SQL, parameters)
            rows = _row_dicts(cursor, await cursor.fetchall())
        total = _total(rows)
        return _strip_total(rows), total

    async def list_risk_decisions(
        self,
        *,
        run_id: str,
        manager_id: str | None,
        outcome: str | None,
        cycle_id: str | None,
        client_order_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int] | None:
        """Return a bounded risk trace page, or ``None`` for an unknown run."""
        filters = ["decisions.run_id = %s"]
        parameters: list[Any] = [run_id]
        for column, value in (
            ("manager_id", manager_id),
            ("outcome", outcome),
            ("cycle_id", cycle_id),
            ("client_order_id", client_order_id),
        ):
            if value is not None:
                filters.append(f"decisions.{column} = %s")
                parameters.append(value)
        query = (
            "SELECT decisions.*, count(*) OVER()::integer AS total_count "
            "FROM console_read.risk_decisions AS decisions "
            f"WHERE {' AND '.join(filters)} "
            "ORDER BY decisions.decision_ts NULLS LAST, decisions.cycle_id, "
            "decisions.manager_position, decisions.risk_decision_id "
            "LIMIT %s OFFSET %s"
        )
        parameters.extend([limit, offset])
        async with self._database.transaction() as connection:
            cursor = await connection.execute(
                "SELECT run_id FROM console_read.backtest_runs WHERE run_id = %s LIMIT 1",
                [run_id],
            )
            if not await cursor.fetchall():
                return None
            cursor = await connection.execute(query, parameters)
            rows = _row_dicts(cursor, await cursor.fetchall())
        total = _total(rows)
        return _strip_total(rows), total

    async def get_run_detail(
        self,
        *,
        run_id: str,
        section_limit: int,
    ) -> dict[str, Any] | None:
        """Load one run and its bounded evidence sections in one transaction."""
        queries: dict[str, tuple[str, list[Any]]] = {
            "run": (
                "SELECT runs.*, scope.scope_fingerprint, scope.data_scope_id, "
                "scope.benchmark_id, scope.variant_fingerprint, "
                "scope.variant_strategy_id, scope.variant_strategy_version, "
                "(comparison.run_id IS NOT NULL) AS comparison_projection_available, "
                "(scope.scope_fingerprint IS NOT NULL AND comparison.run_id IS NOT NULL) AS comparison_eligible, "
                "CASE WHEN scope.scope_fingerprint IS NULL THEN "
                "'missing_scope_fingerprint' WHEN comparison.run_id IS NULL THEN "
                "'no_comparison_projection' ELSE NULL END AS comparison_exclusion_reason "
                "FROM console_read.backtest_runs AS runs "
                "LEFT JOIN console_read.backtest_scope AS scope ON scope.run_id = runs.run_id "
                "LEFT JOIN console_read.backtest_comparison_runs AS comparison ON comparison.run_id = runs.run_id "
                "WHERE runs.run_id = %s",
                [run_id],
            ),
            "performance": ("SELECT * FROM console_read.backtest_performance WHERE run_id = %s LIMIT 1", [run_id]),
            "comparison_summary": ("SELECT * FROM console_read.backtest_comparison_runs WHERE run_id = %s LIMIT 1", [run_id]),
            "exposure": ("SELECT * FROM console_read.backtest_exposure WHERE run_id = %s LIMIT 1", [run_id]),
            "scope": ("SELECT * FROM console_read.backtest_scope WHERE run_id = %s LIMIT 1", [run_id]),
            "assumptions": ("SELECT * FROM console_read.backtest_assumptions WHERE run_id = %s LIMIT 1", [run_id]),
            "evidence_coverage": ("SELECT * FROM console_read.backtest_evidence_coverage WHERE run_id = %s LIMIT 1", [run_id]),
            "equity_curve": ("SELECT * FROM console_read.backtest_equity_curve WHERE run_id = %s ORDER BY point_index LIMIT %s", [run_id, section_limit]),
            "comparison_curves": ("SELECT * FROM console_read.backtest_comparison_curves WHERE run_id = %s ORDER BY point_index LIMIT %s", [run_id, section_limit]),
            "trades": ("SELECT * FROM console_read.backtest_trades WHERE run_id = %s ORDER BY trade_index LIMIT %s", [run_id, section_limit]),
            "positions": ("SELECT * FROM console_read.backtest_positions WHERE run_id = %s ORDER BY position_index LIMIT %s", [run_id, section_limit]),
            "warnings": ("SELECT * FROM console_read.backtest_warnings WHERE run_id = %s ORDER BY warning_index LIMIT %s", [run_id, section_limit]),
            "provenance": ("SELECT * FROM console_read.backtest_provenance WHERE run_id = %s ORDER BY provenance_key LIMIT %s", [run_id, section_limit]),
            "indicator_series": ("SELECT * FROM console_read.indicator_series WHERE run_id = %s ORDER BY bar_ts, series_id LIMIT %s", [run_id, section_limit]),
            "signal_markers": ("SELECT * FROM console_read.signal_markers WHERE run_id = %s ORDER BY event_ts NULLS LAST, generated_at LIMIT %s", [run_id, section_limit]),
            "risk_composition": ("SELECT * FROM console_read.risk_composition WHERE run_id = %s ORDER BY manager_position LIMIT %s", [run_id, section_limit]),
            "risk_summary": ("SELECT * FROM console_read.risk_summary WHERE run_id = %s LIMIT 1", [run_id]),
            "risk_decisions": ("SELECT * FROM console_read.risk_decisions WHERE run_id = %s ORDER BY decision_ts, cycle_id, manager_position LIMIT %s", [run_id, section_limit]),
            "review_evidence": (
                "SELECT * FROM console_read.research_review_evidence "
                "WHERE run_id = %s ORDER BY artifact_type, artifact_id LIMIT %s",
                [run_id, section_limit],
            ),
            "signals": ("SELECT * FROM console_read.signal_lifecycle WHERE run_id = %s ORDER BY generated_at LIMIT %s", [run_id, section_limit]),
            "orders": ("SELECT * FROM console_read.order_lifecycle WHERE run_id = %s ORDER BY created_at LIMIT %s", [run_id, section_limit]),
            "fills": ("SELECT * FROM console_read.fill_lifecycle WHERE run_id = %s ORDER BY fill_ts LIMIT %s", [run_id, section_limit]),
        }
        async with self._database.transaction() as connection:
            results: dict[str, list[dict[str, Any]]] = {}
            for name, (query, parameters) in queries.items():
                cursor = await connection.execute(query, parameters)
                results[name] = _row_dicts(cursor, await cursor.fetchall())
        if not results["run"]:
            return None
        single_sections = {
            "run",
            "performance",
            "comparison_summary",
            "exposure",
            "scope",
            "assumptions",
            "evidence_coverage",
            "risk_summary",
        }
        return {
            name: (rows[0] if rows else None) if name in single_sections else rows
            for name, rows in results.items()
        }
