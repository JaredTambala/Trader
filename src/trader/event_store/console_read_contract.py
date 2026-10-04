"""Producer-owned PostgreSQL read contract for the Trader Console.

This module installs a metadata-versioned contract of stable ordinary views over
core runtime evidence. It is an operator/deployment surface: the trading runtime
and Console API must not run these migrations during normal startup.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from typing import Any, Final, Mapping, Sequence

try:
    import psycopg
    from psycopg import sql
except ImportError:  # pragma: no cover - psycopg is a core dependency in production
    psycopg = None
    sql = None


CONSOLE_READ_SCHEMA: Final = "console_read"
CONSOLE_READ_CONTRACT: Final = "trader_console"
CONSOLE_READ_CONTRACT_VERSION: Final = 9
CONSOLE_READ_MINIMUM_CONSUMER_VERSION: Final = 1

# These are the complete columns exposed by the current contract. Variable configuration,
# generic payload, prediction value, metrics payload, and decision-evidence fields
# remain private until a typed producer-owned projection is approved.
CONSOLE_READ_COLUMNS: Final[Mapping[str, tuple[str, ...]]] = {
    "sessions": (
        "session_id",
        "strategy_id",
        "started_at",
        "finished_at",
        "status",
        "error_message",
        "mode",
        "symbols",
        "timeframe",
        "start_ts",
        "end_ts",
    ),
    "runs": (
        "run_id",
        "run_type",
        "started_at",
        "finished_at",
        "status",
        "error_message",
        "mode",
        "symbols",
        "timeframe",
        "start_ts",
        "end_ts",
    ),
    "cycles": (
        "cycle_id",
        "run_id",
        "session_id",
        "strategy_id",
        "mode",
        "decision_ts",
        "started_at",
        "finished_at",
        "status",
        "error_message",
    ),
    "stock_bars": (
        "symbol",
        "timeframe",
        "ts",
        "ingested_at",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trade_count",
        "vwap",
        "source",
    ),
    "crypto_bars": (
        "symbol",
        "timeframe",
        "ts",
        "ingested_at",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trade_count",
        "vwap",
        "source",
    ),
    "signals": (
        "run_id",
        "session_id",
        "cycle_id",
        "symbol",
        "signal_name",
        "signal_value",
        "target_qty",
        "generated_at",
        "mapper_id",
    ),
    "indicators": (
        "run_id",
        "session_id",
        "cycle_id",
        "symbol",
        "indicator_name",
        "value",
        "bar_ts",
    ),
    "indicator_series": (
        "run_id",
        "session_id",
        "cycle_id",
        "symbol",
        "indicator_name",
        "series_id",
        "series_label",
        "pane",
        "scale_group",
        "unit",
        "series_kind",
        "value",
        "bar_ts",
        "signal_name",
        "signal_event_id",
        "strategy_id",
        "strategy_version",
        "variant_fingerprint",
        "data_scope_id",
        "parameters_fingerprint",
    ),
    "predictions": (
        "prediction_event_id",
        "run_id",
        "session_id",
        "cycle_id",
        "deployment_id",
        "deployment_validation_id",
        "model_version_id",
        "feature_set_id",
        "feature_batch_hash",
        "decision_ts",
        "symbol",
        "output_name",
        "semantics",
        "horizon",
        "latency_ms",
        "status",
        "error_message",
    ),
    "orders": (
        "order_event_id",
        "client_order_id",
        "run_id",
        "session_id",
        "cycle_id",
        "symbol",
        "side",
        "qty",
        "order_type",
        "status",
        "broker_order_id",
        "rejection_reason",
        "created_at",
    ),
    "fills": (
        "client_order_id",
        "run_id",
        "session_id",
        "cycle_id",
        "fill_ts",
        "fill_qty",
        "raw_fill_price",
        "slippage_amount",
        "fee_amount",
        "fill_price",
    ),
    "signal_lifecycle": (
        "signal_event_id",
        "run_id",
        "session_id",
        "cycle_id",
        "symbol",
        "signal_name",
        "signal_value",
        "target_qty",
        "generated_at",
        "mapper_id",
    ),
    "signal_markers": (
        "signal_event_id",
        "run_id",
        "session_id",
        "cycle_id",
        "symbol",
        "signal_name",
        "signal_value",
        "target_qty",
        "event_ts",
        "generated_at",
        "mapper_id",
    ),
    "order_lifecycle": (
        "order_event_id",
        "client_order_id",
        "signal_event_id",
        "run_id",
        "session_id",
        "cycle_id",
        "symbol",
        "side",
        "qty",
        "order_type",
        "status",
        "broker_order_id",
        "rejection_reason",
        "created_at",
    ),
    "fill_lifecycle": (
        "fill_event_id",
        "client_order_id",
        "run_id",
        "session_id",
        "cycle_id",
        "fill_ts",
        "fill_qty",
        "raw_fill_price",
        "slippage_amount",
        "fee_amount",
        "fill_price",
    ),
    "positions": (
        "asof_ts",
        "symbol",
        "qty",
        "avg_price",
        "cash_balance",
        "run_id",
        "session_id",
        "cycle_id",
    ),
    "backtest_runs": (
        "experiment_run_id",
        "experiment_id",
        "run_id",
        "session_id",
        "status",
        "mode",
        "created_at",
        "finished_at",
        "strategy_id",
        "strategy_name",
        "strategy_version",
        "symbols",
        "asset_class",
        "timeframe",
        "start_ts",
        "end_ts",
        "error_message",
        "artifact_dir",
    ),
    "backtest_performance": (
        "experiment_run_id",
        "experiment_id",
        "run_id",
        "observed_at",
        "total_runs",
        "failed_runs",
        "realized_pnl",
        "total_fees",
        "total_slippage",
        "strategy_start_equity",
        "strategy_end_equity",
        "strategy_total_return",
        "strategy_cagr",
        "strategy_volatility",
        "strategy_sharpe",
        "strategy_sortino",
        "strategy_max_drawdown",
        "strategy_max_drawdown_duration",
        "strategy_calmar",
        "strategy_ulcer_index",
        "strategy_avg_net_exposure",
        "strategy_avg_gross_exposure",
        "strategy_avg_invested_pct",
        "strategy_trade_count",
        "strategy_hit_rate",
        "strategy_profit_factor",
        "strategy_expectancy",
        "strategy_avg_win",
        "strategy_avg_loss",
        "strategy_turnover",
        "benchmark_start_equity",
        "benchmark_end_equity",
        "benchmark_total_return",
        "benchmark_cagr",
        "benchmark_volatility",
        "benchmark_sharpe",
        "benchmark_sortino",
        "benchmark_max_drawdown",
        "benchmark_max_drawdown_duration",
        "benchmark_calmar",
        "benchmark_ulcer_index",
        "tracking_error",
        "information_ratio",
        "alpha",
        "beta",
        "warnings_count",
    ),
    "backtest_exposure": (
        "experiment_run_id",
        "experiment_id",
        "run_id",
        "observed_at",
        "avg_net_exposure",
        "avg_gross_exposure",
        "avg_invested_pct",
        "final_net_notional",
        "final_gross_notional",
        "position_count",
        "long_positions",
        "short_positions",
    ),
    "backtest_equity_curve": (
        "experiment_run_id",
        "experiment_id",
        "run_id",
        "point_index",
        "ts",
        "strategy_equity",
        "benchmark_equity",
        "observed_at",
    ),
    "backtest_scope": (
        "experiment_run_id",
        "experiment_id",
        "run_id",
        "observed_at",
        "scope_fingerprint",
        "asset_class",
        "symbols",
        "timeframe",
        "replay_start",
        "replay_end",
        "data_scope_id",
        "benchmark_id",
        "benchmark_method",
        "benchmark_allocation",
        "initial_cash",
        "initial_position_count",
        "fill_model",
        "latency_ms",
        "fee_fixed_per_order",
        "fee_bps",
        "fee_minimum",
        "slippage_bps",
        "allow_latest_prior_bar",
        "allow_price_carry_forward",
        "variant_fingerprint",
        "variant_strategy_id",
        "variant_strategy_version",
        "variant_parameters_fingerprint",
    ),
    "backtest_comparison_runs": (
        "experiment_run_id",
        "experiment_id",
        "run_id",
        "status",
        "scope_fingerprint",
        "data_scope_id",
        "benchmark_id",
        "variant_fingerprint",
        "variant_strategy_id",
        "variant_strategy_version",
        "strategy_total_return",
        "benchmark_total_return",
        "strategy_max_drawdown",
        "benchmark_max_drawdown",
        "strategy_sharpe",
        "strategy_trade_count",
        "warnings_count",
        "observed_at",
    ),
    "backtest_comparison_curves": (
        "experiment_run_id",
        "experiment_id",
        "run_id",
        "scope_fingerprint",
        "variant_fingerprint",
        "variant_strategy_id",
        "variant_strategy_version",
        "point_index",
        "ts",
        "strategy_normalized",
        "benchmark_normalized",
        "strategy_drawdown",
        "benchmark_drawdown",
        "observed_at",
    ),
    "backtest_trades": (
        "experiment_run_id",
        "experiment_id",
        "run_id",
        "trade_index",
        "client_order_id",
        "cycle_id",
        "symbol",
        "side",
        "fill_ts",
        "fill_qty",
        "raw_fill_price",
        "fill_price",
        "fee_amount",
        "slippage_amount",
        "notional",
        "realized_pnl",
        "observed_at",
    ),
    "backtest_positions": (
        "experiment_run_id",
        "experiment_id",
        "run_id",
        "position_index",
        "symbol",
        "qty",
        "avg_price",
        "last_price",
        "last_ts",
        "market_value",
        "unrealized_pnl",
        "observed_at",
    ),
    "backtest_assumptions": (
        "experiment_run_id",
        "experiment_id",
        "run_id",
        "fill_model",
        "latency_ms",
        "fee_fixed_per_order",
        "fee_bps",
        "fee_minimum",
        "slippage_bps",
        "allow_latest_prior_bar",
        "allow_price_carry_forward",
        "observed_at",
    ),
    "backtest_warnings": (
        "experiment_run_id",
        "experiment_id",
        "run_id",
        "warning_index",
        "warning",
        "observed_at",
    ),
    "backtest_provenance": (
        "experiment_run_id",
        "experiment_id",
        "run_id",
        "provenance_key",
        "provenance_value",
        "observed_at",
    ),
    "backtest_evidence_coverage": (
        "experiment_run_id",
        "experiment_id",
        "run_id",
        "observed_at",
        "signal_events_status",
        "order_events_status",
        "fill_events_status",
        "position_snapshots_status",
        "risk_evidence_status",
    ),
    "risk_composition": (
        "run_id",
        "session_id",
        "catalogue_version",
        "composition_fingerprint",
        "manager_position",
        "manager_id",
        "manager_type",
        "manager_parameters",
    ),
    "risk_summary": (
        "run_id",
        "composition_fingerprint",
        "risk_evidence_status",
        "evaluated_count",
        "approved_count",
        "transformed_count",
        "rejected_count",
        "blocked_count",
    ),
    "risk_decisions": (
        "risk_decision_id",
        "composition_fingerprint",
        "run_id",
        "session_id",
        "cycle_id",
        "client_order_id",
        "decision_ts",
        "manager_id",
        "manager_type",
        "manager_position",
        "outcome",
        "reason_code",
        "before_qty",
        "after_qty",
        "before_order",
        "after_order",
    ),
}

CONSOLE_READ_SOURCES: Final[Mapping[str, str]] = {
    "sessions": "trading_sessions",
    "runs": "runs",
    "cycles": "run_events",
    "stock_bars": "stock_bar_events",
    "crypto_bars": "crypto_bar_events",
    "signals": "signal_events",
    "signal_lifecycle": "signal_events",
    "signal_markers": "signal_events",
    "indicators": "indicator_events",
    "predictions": "prediction_events",
    "orders": "order_events",
    "order_lifecycle": "order_events",
    "fills": "fill_events",
    "fill_lifecycle": "fill_events",
    "positions": "position_snapshots",
    "backtest_runs": "experiment_runs",
    "backtest_scope": "runs",
    "indicator_series": "indicator_events",
    "backtest_performance": "fill_events",
    "backtest_exposure": "position_snapshots",
    "backtest_equity_curve": "position_snapshots",
    "backtest_comparison_curves": "backtest_equity_curve",
    "backtest_comparison_runs": "backtest_performance",
    "backtest_trades": "fill_events",
    "backtest_positions": "position_snapshots",
    "backtest_assumptions": "runs",
    "backtest_warnings": "run_events",
    "backtest_provenance": "runs",
    "backtest_evidence_coverage": "runs",
    "risk_composition": "risk_compositions",
    "risk_summary": "runs",
    "risk_decisions": "risk_decisions",
}

_CONSOLE_READ_INSTALL_ORDER: Final[tuple[str, ...]] = (
    "sessions", "runs", "cycles", "stock_bars", "crypto_bars", "signals",
    "signal_lifecycle", "signal_markers", "indicators", "predictions", "orders",
    "order_lifecycle", "fills", "fill_lifecycle", "positions", "backtest_runs",
    "backtest_scope", "indicator_series", "backtest_assumptions", "backtest_evidence_coverage",
    "backtest_trades", "backtest_positions", "backtest_equity_curve", "backtest_performance",
    "backtest_exposure", "backtest_warnings", "backtest_provenance", "backtest_comparison_curves",
    "backtest_comparison_runs",
    "risk_composition", "risk_summary", "risk_decisions",
)
CONSOLE_READ_SOURCES = {
    name: CONSOLE_READ_SOURCES[name] for name in _CONSOLE_READ_INSTALL_ORDER
}

# Legacy backtest definitions below retain the snapshot projection for compatibility
# with the contract builder. Release 8 replaces each backtest relation with the
# direct SQL definitions appended below; external consumers still read ordinary
# columns and never need to interpret a metrics payload.
_BACKTEST_SNAPSHOT_CTE: Final[str] = """
WITH latest_snapshot AS (
    SELECT DISTINCT ON (run_id)
        run_id,
        ts,
        NULLIF(payload, '')::jsonb AS document
    FROM public.metrics_snapshots
    WHERE payload IS NOT NULL
    ORDER BY run_id, ts DESC NULLS LAST
)
"""

CONSOLE_READ_VIEW_SQL: Final[Mapping[str, str]] = {
    "indicator_series": """
CREATE OR REPLACE VIEW console_read.indicator_series
WITH (security_barrier=true, security_invoker=false) AS
SELECT
    event.run_id,
    event.session_id,
    event.cycle_id,
    event.symbol,
    event.indicator_name,
    COALESCE(NULLIF(document #>> '{metadata,series_id}', ''), event.indicator_name) AS series_id,
    COALESCE(NULLIF(document #>> '{metadata,series_label}', ''), event.indicator_name) AS series_label,
    COALESCE(NULLIF(document #>> '{metadata,display,pane}', ''), 'unknown') AS pane,
    COALESCE(NULLIF(document #>> '{metadata,display,scale_group}', ''), 'unknown') AS scale_group,
    COALESCE(NULLIF(document #>> '{metadata,display,unit}', ''), 'unknown') AS unit,
    COALESCE(NULLIF(document #>> '{metadata,display,series_kind}', ''), 'unknown') AS series_kind,
    event.value,
    event.bar_ts,
    document #>> '{metadata,signal_name}' AS signal_name,
    document #>> '{metadata,signal_event_id}' AS signal_event_id,
    runs.strategy_id,
    runs.strategy_version,
    scope.variant_fingerprint,
    scope.data_scope_id,
    scope.variant_parameters_fingerprint AS parameters_fingerprint
FROM (
    SELECT
        source.run_id,
        source.session_id,
        source.cycle_id,
        source.symbol,
        source.indicator_name,
        source.value,
        source.bar_ts,
        COALESCE(NULLIF(source.payload, ''), '{}')::jsonb AS document
    FROM public.indicator_events AS source
) AS event
LEFT JOIN console_read.backtest_runs AS runs ON runs.run_id = event.run_id
LEFT JOIN console_read.backtest_scope AS scope ON scope.run_id = event.run_id
""",
    "signal_markers": """
CREATE OR REPLACE VIEW console_read.signal_markers
WITH (security_barrier=true, security_invoker=false) AS
SELECT
    signal.signal_event_id,
    signal.run_id,
    signal.session_id,
    signal.cycle_id,
    signal.symbol,
    signal.signal_name,
    signal.signal_value,
    signal.target_qty,
    cycle.decision_ts AS event_ts,
    signal.generated_at,
    signal.mapper_id
FROM public.signal_events AS signal
LEFT JOIN console_read.cycles AS cycle ON cycle.cycle_id = signal.cycle_id
""",
    "backtest_evidence_coverage": """
CREATE OR REPLACE VIEW console_read.backtest_evidence_coverage
WITH (security_barrier=true, security_invoker=false) AS
"""
    + _BACKTEST_SNAPSHOT_CTE
    + """
SELECT
    er.experiment_run_id,
    er.experiment_id,
    er.run_id,
    snapshot.ts AS observed_at,
    COALESCE(snapshot.document #>> '{evidence_coverage,signal_events}', 'unknown') AS signal_events_status,
    COALESCE(snapshot.document #>> '{evidence_coverage,order_events}', 'unknown') AS order_events_status,
    COALESCE(snapshot.document #>> '{evidence_coverage,fill_events}', 'unknown') AS fill_events_status,
    COALESCE(snapshot.document #>> '{evidence_coverage,position_snapshots}', 'unknown') AS position_snapshots_status
FROM console_read.backtest_runs AS er
LEFT JOIN latest_snapshot AS snapshot ON snapshot.run_id = er.run_id
""",
    "backtest_scope": """
CREATE OR REPLACE VIEW console_read.backtest_scope
WITH (security_barrier=true, security_invoker=false) AS
"""
    + _BACKTEST_SNAPSHOT_CTE
    + """
SELECT
    er.experiment_run_id,
    er.experiment_id,
    er.run_id,
    snapshot.ts AS observed_at,
    snapshot.document #>> '{review_scope,scope_fingerprint}' AS scope_fingerprint,
    snapshot.document #>> '{review_scope,asset_class}' AS asset_class,
    CASE
        WHEN jsonb_typeof(snapshot.document #> '{review_scope,symbols}') = 'array'
        THEN ARRAY(SELECT jsonb_array_elements_text(snapshot.document #> '{review_scope,symbols}'))
        ELSE NULL::text[]
    END AS symbols,
    snapshot.document #>> '{review_scope,timeframe}' AS timeframe,
    NULLIF(snapshot.document #>> '{review_scope,replay_start}', '')::timestamptz AS replay_start,
    NULLIF(snapshot.document #>> '{review_scope,replay_end}', '')::timestamptz AS replay_end,
    snapshot.document #>> '{review_scope,data_scope_id}' AS data_scope_id,
    snapshot.document #>> '{review_scope,benchmark_id}' AS benchmark_id,
    snapshot.document #>> '{review_scope,benchmark_method}' AS benchmark_method,
    snapshot.document #>> '{review_scope,benchmark_allocation}' AS benchmark_allocation,
    NULLIF(snapshot.document #>> '{review_scope,initial_cash}', '')::double precision AS initial_cash,
    CASE
        WHEN jsonb_typeof(snapshot.document #> '{review_scope,initial_positions}') = 'array'
        THEN jsonb_array_length(snapshot.document #> '{review_scope,initial_positions}')
        ELSE NULL
    END AS initial_position_count,
    snapshot.document #>> '{review_scope,assumptions,fill_model}' AS fill_model,
    NULLIF(snapshot.document #>> '{review_scope,assumptions,latency_ms}', '')::double precision AS latency_ms,
    NULLIF(snapshot.document #>> '{review_scope,assumptions,fees,fixed_per_order}', '')::double precision AS fee_fixed_per_order,
    NULLIF(snapshot.document #>> '{review_scope,assumptions,fees,bps}', '')::double precision AS fee_bps,
    NULLIF(snapshot.document #>> '{review_scope,assumptions,fees,minimum_fee}', '')::double precision AS fee_minimum,
    NULLIF(snapshot.document #>> '{review_scope,assumptions,slippage,bps}', '')::double precision AS slippage_bps,
    NULLIF(snapshot.document #>> '{review_scope,assumptions,data,allow_latest_prior_bar}', '')::boolean AS allow_latest_prior_bar,
    NULLIF(snapshot.document #>> '{review_scope,assumptions,data,allow_price_carry_forward}', '')::boolean AS allow_price_carry_forward,
    snapshot.document #>> '{variant,variant_fingerprint}' AS variant_fingerprint,
    snapshot.document #>> '{variant,strategy_id}' AS variant_strategy_id,
    snapshot.document #>> '{variant,strategy_version}' AS variant_strategy_version,
    snapshot.document #>> '{variant,parameters_fingerprint}' AS variant_parameters_fingerprint
FROM latest_snapshot AS snapshot
JOIN console_read.backtest_runs AS er ON er.run_id = snapshot.run_id
""",
    "backtest_runs": """
CREATE OR REPLACE VIEW console_read.backtest_runs
WITH (security_barrier=true, security_invoker=false) AS
SELECT
    er.experiment_run_id,
    er.experiment_id,
    er.run_id,
    snapshot.session_id,
    er.status,
    runs.mode,
    er.created_at,
    er.finished_at,
    er.strategy_id,
    er.strategy_name,
    er.strategy_version,
    er.symbols,
    er.asset_class,
    er.timeframe,
    er.start_ts,
    er.end_ts,
    er.error_message,
    er.artifact_dir
FROM public.experiment_runs AS er
LEFT JOIN public.runs AS runs ON runs.run_id = er.run_id
LEFT JOIN LATERAL (
    SELECT metrics.session_id
    FROM public.metrics_snapshots AS metrics
    WHERE metrics.run_id = er.run_id
    ORDER BY metrics.ts DESC NULLS LAST
    LIMIT 1
) AS snapshot ON true
UNION ALL
SELECT
    'standalone:' || runs.run_id AS experiment_run_id,
    'standalone_backtests' AS experiment_id,
    runs.run_id,
    snapshot.session_id,
    runs.status,
    runs.mode,
    runs.started_at AS created_at,
    runs.finished_at,
    COALESCE(
        runs.config_snapshot #>> '{strategy,id}',
        runs.config_snapshot #>> '{payload,strategy,id}'
    ) AS strategy_id,
    COALESCE(
        runs.config_snapshot #>> '{strategy,id}',
        runs.config_snapshot #>> '{payload,strategy,id}'
    ) AS strategy_name,
    COALESCE(
        runs.config_snapshot #>> '{strategy,version}',
        runs.config_snapshot #>> '{payload,strategy,version}'
    ) AS strategy_version,
    runs.symbols,
    CASE
        WHEN runs.config_snapshot #>> '{payload,asset_class}' IS NOT NULL THEN runs.config_snapshot #>> '{payload,asset_class}'
        ELSE runs.config_snapshot #>> '{market_data,asset_class}'
    END AS asset_class,
    runs.timeframe,
    runs.start_ts,
    runs.end_ts,
    runs.error_message,
    NULL::text AS artifact_dir
FROM public.runs AS runs
LEFT JOIN LATERAL (
    SELECT metrics.session_id
    FROM public.metrics_snapshots AS metrics
    WHERE metrics.run_id = runs.run_id
    ORDER BY metrics.ts DESC NULLS LAST
    LIMIT 1
) AS snapshot ON true
WHERE runs.run_type = 'backtest'
  AND NOT EXISTS (
      SELECT 1 FROM public.experiment_runs AS grouped
      WHERE grouped.run_id = runs.run_id
  )
""",
    "backtest_performance": """
CREATE OR REPLACE VIEW console_read.backtest_performance
WITH (security_barrier=true, security_invoker=false) AS
"""
    + _BACKTEST_SNAPSHOT_CTE
    + """
SELECT
    er.experiment_run_id,
    er.experiment_id,
    er.run_id,
    snapshot.ts AS observed_at,
    NULLIF(snapshot.document->>'total_runs', '')::integer AS total_runs,
    NULLIF(snapshot.document->>'failed_runs', '')::integer AS failed_runs,
    NULLIF(snapshot.document->>'realized_pnl', '')::double precision AS realized_pnl,
    NULLIF(snapshot.document->>'total_fees', '')::double precision AS total_fees,
    NULLIF(snapshot.document->>'total_slippage', '')::double precision AS total_slippage,
    NULLIF(snapshot.document #>> '{strategy_performance,start_equity}', '')::double precision AS strategy_start_equity,
    NULLIF(snapshot.document #>> '{strategy_performance,end_equity}', '')::double precision AS strategy_end_equity,
    NULLIF(snapshot.document #>> '{strategy_performance,total_return}', '')::double precision AS strategy_total_return,
    NULLIF(snapshot.document #>> '{strategy_performance,cagr}', '')::double precision AS strategy_cagr,
    NULLIF(snapshot.document #>> '{strategy_performance,volatility}', '')::double precision AS strategy_volatility,
    NULLIF(snapshot.document #>> '{strategy_performance,sharpe}', '')::double precision AS strategy_sharpe,
    NULLIF(snapshot.document #>> '{strategy_performance,sortino}', '')::double precision AS strategy_sortino,
    NULLIF(snapshot.document #>> '{strategy_performance,max_drawdown}', '')::double precision AS strategy_max_drawdown,
    NULLIF(snapshot.document #>> '{strategy_performance,max_drawdown_duration}', '')::integer AS strategy_max_drawdown_duration,
    NULLIF(snapshot.document #>> '{strategy_performance,calmar}', '')::double precision AS strategy_calmar,
    NULLIF(snapshot.document #>> '{strategy_performance,ulcer_index}', '')::double precision AS strategy_ulcer_index,
    NULLIF(snapshot.document #>> '{strategy_performance,avg_net_exposure}', '')::double precision AS strategy_avg_net_exposure,
    NULLIF(snapshot.document #>> '{strategy_performance,avg_gross_exposure}', '')::double precision AS strategy_avg_gross_exposure,
    NULLIF(snapshot.document #>> '{strategy_performance,avg_invested_pct}', '')::double precision AS strategy_avg_invested_pct,
    NULLIF(snapshot.document #>> '{strategy_performance,trade_count}', '')::integer AS strategy_trade_count,
    NULLIF(snapshot.document #>> '{strategy_performance,hit_rate}', '')::double precision AS strategy_hit_rate,
    NULLIF(snapshot.document #>> '{strategy_performance,profit_factor}', '')::double precision AS strategy_profit_factor,
    NULLIF(snapshot.document #>> '{strategy_performance,expectancy}', '')::double precision AS strategy_expectancy,
    NULLIF(snapshot.document #>> '{strategy_performance,avg_win}', '')::double precision AS strategy_avg_win,
    NULLIF(snapshot.document #>> '{strategy_performance,avg_loss}', '')::double precision AS strategy_avg_loss,
    NULLIF(snapshot.document #>> '{strategy_performance,turnover}', '')::double precision AS strategy_turnover,
    NULLIF(snapshot.document #>> '{benchmark_performance,start_equity}', '')::double precision AS benchmark_start_equity,
    NULLIF(snapshot.document #>> '{benchmark_performance,end_equity}', '')::double precision AS benchmark_end_equity,
    NULLIF(snapshot.document #>> '{benchmark_performance,total_return}', '')::double precision AS benchmark_total_return,
    NULLIF(snapshot.document #>> '{benchmark_performance,cagr}', '')::double precision AS benchmark_cagr,
    NULLIF(snapshot.document #>> '{benchmark_performance,volatility}', '')::double precision AS benchmark_volatility,
    NULLIF(snapshot.document #>> '{benchmark_performance,sharpe}', '')::double precision AS benchmark_sharpe,
    NULLIF(snapshot.document #>> '{benchmark_performance,sortino}', '')::double precision AS benchmark_sortino,
    NULLIF(snapshot.document #>> '{benchmark_performance,max_drawdown}', '')::double precision AS benchmark_max_drawdown,
    NULLIF(snapshot.document #>> '{benchmark_performance,max_drawdown_duration}', '')::integer AS benchmark_max_drawdown_duration,
    NULLIF(snapshot.document #>> '{benchmark_performance,calmar}', '')::double precision AS benchmark_calmar,
    NULLIF(snapshot.document #>> '{benchmark_performance,ulcer_index}', '')::double precision AS benchmark_ulcer_index,
    NULLIF(snapshot.document->>'tracking_error', '')::double precision AS tracking_error,
    NULLIF(snapshot.document->>'information_ratio', '')::double precision AS information_ratio,
    NULLIF(snapshot.document->>'alpha', '')::double precision AS alpha,
    NULLIF(snapshot.document->>'beta', '')::double precision AS beta,
    COALESCE(jsonb_array_length(snapshot.document->'warnings'), 0) AS warnings_count
FROM console_read.backtest_runs AS er
JOIN latest_snapshot AS snapshot ON snapshot.run_id = er.run_id
WHERE snapshot.document ? 'strategy_performance'
""",
    "backtest_exposure": """
CREATE OR REPLACE VIEW console_read.backtest_exposure
WITH (security_barrier=true, security_invoker=false) AS
"""
    + _BACKTEST_SNAPSHOT_CTE
    + """
SELECT
    er.experiment_run_id,
    er.experiment_id,
    er.run_id,
    snapshot.ts AS observed_at,
    NULLIF(snapshot.document #>> '{strategy_performance,avg_net_exposure}', '')::double precision AS avg_net_exposure,
    NULLIF(snapshot.document #>> '{strategy_performance,avg_gross_exposure}', '')::double precision AS avg_gross_exposure,
    NULLIF(snapshot.document #>> '{strategy_performance,avg_invested_pct}', '')::double precision AS avg_invested_pct,
    NULLIF(snapshot.document->>'net_notional', '')::double precision AS final_net_notional,
    NULLIF(snapshot.document->>'gross_notional', '')::double precision AS final_gross_notional,
    NULLIF(snapshot.document->>'position_count', '')::integer AS position_count,
    NULLIF(snapshot.document->>'long_positions', '')::integer AS long_positions,
    NULLIF(snapshot.document->>'short_positions', '')::integer AS short_positions
FROM console_read.backtest_runs AS er
JOIN latest_snapshot AS snapshot ON snapshot.run_id = er.run_id
WHERE snapshot.document ? 'strategy_performance'
""",
    "backtest_equity_curve": """
CREATE OR REPLACE VIEW console_read.backtest_equity_curve
WITH (security_barrier=true, security_invoker=false) AS
"""
    + _BACKTEST_SNAPSHOT_CTE
    + """
, strategy_points AS (
    SELECT
        run_id,
        ts AS observed_at,
        ordinality - 1 AS point_index,
        NULLIF(point->>'ts', '')::timestamptz AS point_ts,
        NULLIF(point->>'equity', '')::double precision AS strategy_equity
    FROM latest_snapshot,
        jsonb_array_elements(latest_snapshot.document->'equity_curve') WITH ORDINALITY AS items(point, ordinality)
), benchmark_points AS (
    SELECT
        run_id,
        ordinality - 1 AS point_index,
        NULLIF(point->>'ts', '')::timestamptz AS point_ts,
        NULLIF(point->>'equity', '')::double precision AS benchmark_equity
    FROM latest_snapshot,
        jsonb_array_elements(latest_snapshot.document->'benchmark_curve') WITH ORDINALITY AS items(point, ordinality)
)
SELECT
    er.experiment_run_id,
    er.experiment_id,
    COALESCE(strategy_points.run_id, benchmark_points.run_id) AS run_id,
    COALESCE(strategy_points.point_index, benchmark_points.point_index) AS point_index,
    COALESCE(strategy_points.point_ts, benchmark_points.point_ts) AS ts,
    strategy_points.strategy_equity,
    benchmark_points.benchmark_equity,
    COALESCE(strategy_points.observed_at, latest_snapshot.ts) AS observed_at
FROM strategy_points
FULL OUTER JOIN benchmark_points
    ON benchmark_points.run_id = strategy_points.run_id
   AND benchmark_points.point_index = strategy_points.point_index
JOIN latest_snapshot
    ON latest_snapshot.run_id = COALESCE(strategy_points.run_id, benchmark_points.run_id)
JOIN console_read.backtest_runs AS er
    ON er.run_id = latest_snapshot.run_id
""",
    "backtest_comparison_curves": """
CREATE OR REPLACE VIEW console_read.backtest_comparison_curves
WITH (security_barrier=true, security_invoker=false) AS
WITH points AS (
    SELECT
        curves.experiment_run_id,
        curves.experiment_id,
        curves.run_id,
        scope.scope_fingerprint,
        scope.variant_fingerprint,
        scope.variant_strategy_id,
        scope.variant_strategy_version,
        curves.point_index,
        curves.ts,
        curves.strategy_equity,
        curves.benchmark_equity,
        curves.observed_at
    FROM console_read.backtest_equity_curve AS curves
    JOIN console_read.backtest_scope AS scope
      ON scope.run_id = curves.run_id
     AND scope.scope_fingerprint IS NOT NULL
), starts AS (
    SELECT
        points.*,
        FIRST_VALUE(strategy_equity) OVER (
            PARTITION BY run_id ORDER BY (strategy_equity IS NULL), point_index
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS strategy_start,
        FIRST_VALUE(benchmark_equity) OVER (
            PARTITION BY run_id ORDER BY (benchmark_equity IS NULL), point_index
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS benchmark_start,
        MAX(strategy_equity) OVER (
            PARTITION BY run_id ORDER BY point_index
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS strategy_peak,
        MAX(benchmark_equity) OVER (
            PARTITION BY run_id ORDER BY point_index
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS benchmark_peak
    FROM points
)
SELECT
    experiment_run_id,
    experiment_id,
    run_id,
    scope_fingerprint,
    variant_fingerprint,
    variant_strategy_id,
    variant_strategy_version,
    point_index,
    ts,
    strategy_equity / NULLIF(strategy_start, 0) AS strategy_normalized,
    benchmark_equity / NULLIF(benchmark_start, 0) AS benchmark_normalized,
    1 - strategy_equity / NULLIF(strategy_peak, 0) AS strategy_drawdown,
    1 - benchmark_equity / NULLIF(benchmark_peak, 0) AS benchmark_drawdown,
    observed_at
FROM starts
""",
    "backtest_comparison_runs": """
CREATE OR REPLACE VIEW console_read.backtest_comparison_runs
WITH (security_barrier=true, security_invoker=false) AS
SELECT
    scope.experiment_run_id,
    scope.experiment_id,
    scope.run_id,
    runs.status,
    scope.scope_fingerprint,
    scope.data_scope_id,
    scope.benchmark_id,
    scope.variant_fingerprint,
    scope.variant_strategy_id,
    scope.variant_strategy_version,
    performance.strategy_total_return,
    performance.benchmark_total_return,
    performance.strategy_max_drawdown,
    performance.benchmark_max_drawdown,
    performance.strategy_sharpe,
    performance.strategy_trade_count,
    performance.warnings_count,
    scope.observed_at
FROM console_read.backtest_scope AS scope
JOIN console_read.backtest_runs AS runs ON runs.run_id = scope.run_id
LEFT JOIN console_read.backtest_performance AS performance ON performance.run_id = scope.run_id
WHERE scope.scope_fingerprint IS NOT NULL
""",
    "backtest_trades": """
CREATE OR REPLACE VIEW console_read.backtest_trades
WITH (security_barrier=true, security_invoker=false) AS
"""
    + _BACKTEST_SNAPSHOT_CTE
    + """
SELECT
    er.experiment_run_id,
    er.experiment_id,
    er.run_id,
    items.ordinality - 1 AS trade_index,
    items.trade->>'client_order_id' AS client_order_id,
    items.trade->>'cycle_id' AS cycle_id,
    items.trade->>'symbol' AS symbol,
    items.trade->>'side' AS side,
    NULLIF(items.trade->>'fill_ts', '')::timestamptz AS fill_ts,
    NULLIF(items.trade->>'fill_qty', '')::double precision AS fill_qty,
    NULLIF(items.trade->>'raw_fill_price', '')::double precision AS raw_fill_price,
    NULLIF(items.trade->>'fill_price', '')::double precision AS fill_price,
    NULLIF(items.trade->>'fee_amount', '')::double precision AS fee_amount,
    NULLIF(items.trade->>'slippage_amount', '')::double precision AS slippage_amount,
    NULLIF(items.trade->>'notional', '')::double precision AS notional,
    NULLIF(items.trade->>'realized_pnl', '')::double precision AS realized_pnl,
    snapshot.ts AS observed_at
FROM latest_snapshot AS snapshot
CROSS JOIN LATERAL jsonb_array_elements(snapshot.document->'trades') WITH ORDINALITY AS items(trade, ordinality)
JOIN console_read.backtest_runs AS er ON er.run_id = snapshot.run_id
""",
    "backtest_positions": """
CREATE OR REPLACE VIEW console_read.backtest_positions
WITH (security_barrier=true, security_invoker=false) AS
"""
    + _BACKTEST_SNAPSHOT_CTE
    + """
SELECT
    er.experiment_run_id,
    er.experiment_id,
    er.run_id,
    items.ordinality - 1 AS position_index,
    items.position->>'symbol' AS symbol,
    NULLIF(items.position->>'qty', '')::double precision AS qty,
    NULLIF(items.position->>'avg_price', '')::double precision AS avg_price,
    NULLIF(items.position->>'last_price', '')::double precision AS last_price,
    NULLIF(items.position->>'last_ts', '')::timestamptz AS last_ts,
    NULLIF(items.position->>'market_value', '')::double precision AS market_value,
    NULLIF(items.position->>'unrealized_pnl', '')::double precision AS unrealized_pnl,
    snapshot.ts AS observed_at
FROM latest_snapshot AS snapshot
CROSS JOIN LATERAL jsonb_array_elements(snapshot.document->'positions') WITH ORDINALITY AS items(position, ordinality)
JOIN console_read.backtest_runs AS er ON er.run_id = snapshot.run_id
""",
    "backtest_assumptions": """
CREATE OR REPLACE VIEW console_read.backtest_assumptions
WITH (security_barrier=true, security_invoker=false) AS
"""
    + _BACKTEST_SNAPSHOT_CTE
    + """
SELECT
    er.experiment_run_id,
    er.experiment_id,
    er.run_id,
    snapshot.document #>> '{assumptions,fill_model}' AS fill_model,
    NULLIF(snapshot.document #>> '{assumptions,latency_ms}', '')::double precision AS latency_ms,
    NULLIF(snapshot.document #>> '{assumptions,fees,fixed_per_order}', '')::double precision AS fee_fixed_per_order,
    NULLIF(snapshot.document #>> '{assumptions,fees,bps}', '')::double precision AS fee_bps,
    NULLIF(snapshot.document #>> '{assumptions,fees,minimum_fee}', '')::double precision AS fee_minimum,
    NULLIF(snapshot.document #>> '{assumptions,slippage,bps}', '')::double precision AS slippage_bps,
    NULLIF(snapshot.document #>> '{assumptions,data,allow_latest_prior_bar}', '')::boolean AS allow_latest_prior_bar,
    NULLIF(snapshot.document #>> '{assumptions,data,allow_price_carry_forward}', '')::boolean AS allow_price_carry_forward,
    snapshot.ts AS observed_at
FROM latest_snapshot AS snapshot
JOIN console_read.backtest_runs AS er ON er.run_id = snapshot.run_id
WHERE snapshot.document ? 'assumptions'
""",
    "backtest_warnings": """
CREATE OR REPLACE VIEW console_read.backtest_warnings
WITH (security_barrier=true, security_invoker=false) AS
"""
    + _BACKTEST_SNAPSHOT_CTE
    + """
SELECT
    er.experiment_run_id,
    er.experiment_id,
    er.run_id,
    items.ordinality - 1 AS warning_index,
    items.warning,
    snapshot.ts AS observed_at
FROM latest_snapshot AS snapshot
CROSS JOIN LATERAL jsonb_array_elements_text(snapshot.document->'warnings') WITH ORDINALITY AS items(warning, ordinality)
JOIN console_read.backtest_runs AS er ON er.run_id = snapshot.run_id
""",
    "backtest_provenance": """
CREATE OR REPLACE VIEW console_read.backtest_provenance
WITH (security_barrier=true, security_invoker=false) AS
"""
    + _BACKTEST_SNAPSHOT_CTE
    + """
SELECT
    er.experiment_run_id,
    er.experiment_id,
    er.run_id,
    items.key AS provenance_key,
    items.value AS provenance_value,
    snapshot.ts AS observed_at
FROM latest_snapshot AS snapshot
CROSS JOIN LATERAL jsonb_each_text(
    CASE
        WHEN jsonb_typeof(snapshot.document->'provenance') = 'object'
        THEN snapshot.document->'provenance'
        ELSE '{}'::jsonb
    END
) AS items(key, value)
JOIN console_read.backtest_runs AS er ON er.run_id = snapshot.run_id
""",
}

# The Console read model is reconstructed from normalized runtime evidence. A
# metrics snapshot may still exist for other consumers, but it is not read by
# these views. The CTEs deliberately keep source identity and run scoping in
# every join so reused cycle IDs cannot cross-contaminate runs.
_BACKTEST_DIRECT_RUN_META_CTE: Final[str] = """
WITH run_meta AS (
    SELECT
        br.experiment_run_id,
        br.experiment_id,
        br.run_id,
        br.status,
        br.created_at,
        br.finished_at,
        br.strategy_id,
        br.strategy_name,
        br.strategy_version,
        br.symbols,
        COALESCE(
            br.asset_class,
            r.config_snapshot #>> '{backtest,asset_class}',
            r.config_snapshot #>> '{payload,backtest,asset_class}',
            r.config_snapshot #>> '{market_data,asset_class}',
            r.config_snapshot #>> '{payload,market_data,asset_class}'
        ) AS asset_class,
        COALESCE(
            br.timeframe,
            r.config_snapshot #>> '{backtest,timeframe}',
            r.config_snapshot #>> '{payload,backtest,timeframe}'
        ) AS timeframe,
        COALESCE(br.start_ts, r.start_ts) AS start_ts,
        COALESCE(br.end_ts, r.end_ts) AS end_ts,
        br.error_message,
        r.config_snapshot
    FROM console_read.backtest_runs AS br
    LEFT JOIN public.runs AS r ON r.run_id = br.run_id
), config AS (
    SELECT
        meta.*,
        COALESCE(meta.config_snapshot #> '{backtest}', meta.config_snapshot #> '{payload,backtest}', '{}'::jsonb) AS backtest_config,
        COALESCE(meta.config_snapshot #> '{logging,persist}', meta.config_snapshot #> '{payload,logging,persist}', '{}'::jsonb) AS persist_config,
        COALESCE(meta.config_snapshot #> '{market_data}', meta.config_snapshot #> '{payload,market_data}', '{}'::jsonb) AS market_data_config
    FROM run_meta AS meta
)
"""

_BACKTEST_DIRECT_EVIDENCE_CTE: Final[str] = _BACKTEST_DIRECT_RUN_META_CTE + """
, orders AS (
    SELECT DISTINCT ON (run_id, client_order_id)
        run_id, client_order_id, cycle_id, symbol, side, qty, status, created_at
    FROM public.order_events
    WHERE client_order_id IS NOT NULL
    ORDER BY run_id, client_order_id,
        CASE status WHEN 'filled' THEN 0 WHEN 'submitted' THEN 1 WHEN 'validated' THEN 2 ELSE 3 END,
        created_at DESC NULLS LAST, order_event_id DESC
), fills AS (
    SELECT
        fill.run_id,
        fill.client_order_id,
        COALESCE(fill.cycle_id, order_row.cycle_id) AS cycle_id,
        order_row.symbol AS symbol,
        order_row.side,
        fill.fill_ts,
        fill.fill_qty,
        fill.raw_fill_price,
        fill.fill_price,
        COALESCE(fill.fee_amount, 0.0) AS fee_amount,
        COALESCE(fill.slippage_amount, 0.0) AS slippage_amount
    FROM public.fill_events AS fill
    LEFT JOIN orders AS order_row
      ON order_row.run_id = fill.run_id
     AND order_row.client_order_id = fill.client_order_id
    WHERE fill.fill_qty IS NOT NULL AND fill.fill_price IS NOT NULL
), bars AS (
    SELECT
        meta.run_id, meta.asset_class, meta.timeframe,
        bar.symbol, bar.ts, bar.close
    FROM config AS meta
    CROSS JOIN LATERAL (
        SELECT source_bar.symbol, source_bar.ts, source_bar.close
        FROM public.stock_bar_events AS source_bar
        WHERE meta.asset_class = 'stock'
          AND source_bar.symbol = ANY(meta.symbols)
          AND source_bar.timeframe = meta.timeframe
          AND source_bar.ts >= meta.start_ts AND source_bar.ts <= meta.end_ts
          AND (meta.market_data_config->>'source' IS NULL OR source_bar.source = meta.market_data_config->>'source')
        OFFSET 0
    ) AS bar
    UNION ALL
    SELECT
        meta.run_id, meta.asset_class, meta.timeframe,
        bar.symbol, bar.ts, bar.close
    FROM config AS meta
    CROSS JOIN LATERAL (
        SELECT source_bar.symbol, source_bar.ts, source_bar.close
        FROM public.crypto_bar_events AS source_bar
        WHERE meta.asset_class = 'crypto'
          AND source_bar.symbol = ANY(meta.symbols)
          AND source_bar.timeframe = meta.timeframe
          AND source_bar.ts >= meta.start_ts AND source_bar.ts <= meta.end_ts
          AND (meta.market_data_config->>'source' IS NULL OR source_bar.source = meta.market_data_config->>'source')
        OFFSET 0
    ) AS bar
), initial_positions AS (
    SELECT snapshot.run_id, snapshot.asof_ts, snapshot.symbol, snapshot.qty
    FROM public.position_snapshots AS snapshot
    JOIN config AS meta ON meta.run_id = snapshot.run_id
    WHERE snapshot.cycle_id IS NULL AND snapshot.symbol IS NOT NULL AND snapshot.symbol <> ''
    UNION ALL
    SELECT meta.run_id, meta.start_ts, item->>'symbol',
           NULLIF(item->>'qty', '')::double precision
    FROM config AS meta
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(meta.backtest_config->'initial_positions') = 'array'
             THEN meta.backtest_config->'initial_positions' ELSE '[]'::jsonb END
    ) AS source(item)
    WHERE item->>'symbol' IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM public.position_snapshots AS snapshot
          WHERE snapshot.run_id = meta.run_id
            AND snapshot.cycle_id IS NULL
            AND snapshot.symbol = item->>'symbol'
      )
), timeline AS (
    SELECT
        bar.run_id, bar.ts, bar.symbol, bar.close,
        0.0::double precision AS qty_delta,
        0.0::double precision AS cash_delta,
        2 AS event_kind
    FROM bars AS bar
    UNION ALL
    SELECT
        initial.run_id, initial.asof_ts, initial.symbol, NULL::double precision,
        initial.qty, 0.0::double precision, 0
    FROM initial_positions AS initial
    UNION ALL
    SELECT
        fill.run_id, fill.fill_ts, fill.symbol, NULL::double precision,
        CASE WHEN fill.side = 'buy' THEN fill.fill_qty ELSE -fill.fill_qty END,
        CASE WHEN fill.side = 'buy'
             THEN -(fill.fill_qty * fill.fill_price) - fill.fee_amount
             ELSE (fill.fill_qty * fill.fill_price) - fill.fee_amount END,
        1
    FROM fills AS fill
    WHERE fill.symbol IS NOT NULL AND fill.side IN ('buy', 'sell')
), running_timeline AS (
    SELECT timeline.*,
        SUM(timeline.qty_delta) OVER (
            PARTITION BY timeline.run_id, timeline.symbol
            ORDER BY timeline.ts, timeline.event_kind
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_qty,
        SUM(timeline.cash_delta) OVER (
            PARTITION BY timeline.run_id
            ORDER BY timeline.ts, timeline.event_kind
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_cash_delta
    FROM timeline
), marked AS (
    SELECT
        timeline.run_id, timeline.ts, timeline.symbol, timeline.close,
        timeline.running_qty AS qty,
        COALESCE(meta.backtest_config->>'initial_cash', '0')::double precision
            + timeline.running_cash_delta AS cash_balance
    FROM running_timeline AS timeline
    JOIN config AS meta ON meta.run_id = timeline.run_id
    WHERE timeline.event_kind = 2
), curve_points AS (
    SELECT
        marked.run_id,
        marked.ts,
        SUM(marked.qty * marked.close) + MAX(marked.cash_balance) AS strategy_equity,
        SUM(marked.qty * marked.close) AS net_notional,
        SUM(ABS(marked.qty * marked.close)) AS gross_notional,
        MAX(marked.cash_balance) AS cash_balance
    FROM marked AS marked
    GROUP BY marked.run_id, marked.ts
), equity_points AS (
    SELECT
        curve.*,
        ROW_NUMBER() OVER (PARTITION BY curve.run_id ORDER BY curve.ts) - 1 AS point_index,
        FIRST_VALUE(curve.strategy_equity) OVER (
            PARTITION BY curve.run_id ORDER BY curve.ts
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS start_equity,
        LAG(curve.strategy_equity) OVER (PARTITION BY curve.run_id ORDER BY curve.ts) AS previous_equity,
        MAX(curve.strategy_equity) OVER (
            PARTITION BY curve.run_id ORDER BY curve.ts
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_peak
    FROM curve_points AS curve
)
"""

_CONSOLE_READ_DIRECT_VIEW_SQL: Mapping[str, str] = {
    "risk_composition": """
CREATE OR REPLACE VIEW console_read.risk_composition
WITH (security_barrier=true, security_invoker=false) AS
SELECT
    composition.run_id,
    composition.session_id,
    composition.catalogue_version,
    composition.composition_fingerprint,
    manager.ordinality - 1 AS manager_position,
    manager.value->>'manager_id' AS manager_id,
    manager.value->>'manager_type' AS manager_type,
    manager.value->'parameters' AS manager_parameters
FROM public.risk_compositions AS composition
CROSS JOIN LATERAL jsonb_array_elements(composition.managers) WITH ORDINALITY AS manager(value, ordinality)
""",
    "risk_summary": """
CREATE OR REPLACE VIEW console_read.risk_summary
WITH (security_barrier=true, security_invoker=false) AS
SELECT
    run.run_id,
    COALESCE(MAX(decision.composition_fingerprint), MAX(composition.composition_fingerprint)) AS composition_fingerprint,
    CASE WHEN COUNT(decision.risk_decision_id) > 0 OR COUNT(composition.risk_composition_record_id) > 0
         THEN 'recorded' ELSE 'unavailable' END AS risk_evidence_status,
    COUNT(decision.risk_decision_id)::integer AS evaluated_count,
    COUNT(decision.risk_decision_id) FILTER (WHERE decision.outcome = 'approved')::integer AS approved_count,
    COUNT(decision.risk_decision_id) FILTER (WHERE decision.outcome = 'transformed')::integer AS transformed_count,
    COUNT(decision.risk_decision_id) FILTER (WHERE decision.outcome = 'rejected')::integer AS rejected_count,
    COUNT(decision.risk_decision_id) FILTER (WHERE decision.outcome = 'rejected')::integer AS blocked_count
FROM public.runs AS run
LEFT JOIN public.risk_compositions AS composition ON composition.run_id = run.run_id
LEFT JOIN public.risk_decisions AS decision ON decision.run_id = run.run_id
WHERE run.run_type = 'backtest'
GROUP BY run.run_id
""",
    "risk_decisions": """
CREATE OR REPLACE VIEW console_read.risk_decisions
WITH (security_barrier=true, security_invoker=false) AS
SELECT
    risk_decision_id,
    composition_fingerprint,
    run_id,
    session_id,
    cycle_id,
    client_order_id,
    decision_ts,
    manager_id,
    manager_type,
    manager_position,
    outcome,
    reason_code,
    before_qty,
    after_qty,
    before_order,
    after_order
FROM public.risk_decisions
""",
    "backtest_runs": """
CREATE OR REPLACE VIEW console_read.backtest_runs
WITH (security_barrier=true, security_invoker=false) AS
SELECT
    er.experiment_run_id, er.experiment_id, er.run_id,
    er.run_id AS session_id, er.status, runs.mode,
    er.created_at, er.finished_at, er.strategy_id, er.strategy_name,
    er.strategy_version, er.symbols, er.asset_class, er.timeframe,
    er.start_ts, er.end_ts, er.error_message, er.artifact_dir
FROM public.experiment_runs AS er
LEFT JOIN public.runs AS runs ON runs.run_id = er.run_id
UNION ALL
SELECT
    'standalone:' || runs.run_id, 'standalone_backtests', runs.run_id,
    runs.run_id, runs.status, runs.mode, runs.started_at, runs.finished_at,
    COALESCE(runs.config_snapshot #>> '{strategy,id}', runs.config_snapshot #>> '{payload,strategy,id}'),
    COALESCE(runs.config_snapshot #>> '{strategy,id}', runs.config_snapshot #>> '{payload,strategy,id}'),
    COALESCE(runs.config_snapshot #>> '{strategy,version}', runs.config_snapshot #>> '{payload,strategy,version}'),
    runs.symbols,
    COALESCE(runs.config_snapshot #>> '{backtest,asset_class}', runs.config_snapshot #>> '{payload,backtest,asset_class}', runs.config_snapshot #>> '{market_data,asset_class}', runs.config_snapshot #>> '{payload,market_data,asset_class}'),
    COALESCE(runs.timeframe, runs.config_snapshot #>> '{backtest,timeframe}', runs.config_snapshot #>> '{payload,backtest,timeframe}'),
    runs.start_ts, runs.end_ts, runs.error_message, NULL::text
FROM public.runs AS runs
WHERE runs.run_type = 'backtest'
  AND NOT EXISTS (SELECT 1 FROM public.experiment_runs AS grouped WHERE grouped.run_id = runs.run_id)
""",
    "backtest_scope": """
CREATE OR REPLACE VIEW console_read.backtest_scope
WITH (security_barrier=true, security_invoker=false) AS
""" + _BACKTEST_DIRECT_RUN_META_CTE + """
SELECT
    run_meta.experiment_run_id, run_meta.experiment_id, run_meta.run_id,
    COALESCE(run_meta.finished_at, run_meta.created_at) AS observed_at,
    NULL::text AS scope_fingerprint, run_meta.asset_class, run_meta.symbols,
    run_meta.timeframe, run_meta.start_ts AS replay_start, run_meta.end_ts AS replay_end,
    NULL::text AS data_scope_id, NULL::text AS benchmark_id,
    NULL::text AS benchmark_method, NULL::text AS benchmark_allocation,
    NULLIF(config.backtest_config->>'initial_cash', '')::double precision AS initial_cash,
    CASE WHEN jsonb_typeof(config.backtest_config->'initial_positions') = 'array'
         THEN jsonb_array_length(config.backtest_config->'initial_positions') ELSE 0 END AS initial_position_count,
    config.backtest_config #>> '{assumptions,fill_model}' AS fill_model,
    NULLIF(config.backtest_config #>> '{assumptions,latency_ms}', '')::double precision AS latency_ms,
    NULLIF(config.backtest_config #>> '{assumptions,fees,fixed_per_order}', '')::double precision AS fee_fixed_per_order,
    NULLIF(config.backtest_config #>> '{assumptions,fees,bps}', '')::double precision AS fee_bps,
    NULLIF(config.backtest_config #>> '{assumptions,fees,minimum_fee}', '')::double precision AS fee_minimum,
    NULLIF(config.backtest_config #>> '{assumptions,slippage,bps}', '')::double precision AS slippage_bps,
    NULLIF(config.backtest_config #>> '{assumptions,data,allow_latest_prior_bar}', '')::boolean AS allow_latest_prior_bar,
    NULLIF(config.backtest_config #>> '{assumptions,data,allow_price_carry_forward}', '')::boolean AS allow_price_carry_forward,
    NULL::text AS variant_fingerprint, run_meta.strategy_id AS variant_strategy_id,
    run_meta.strategy_version AS variant_strategy_version, NULL::text AS variant_parameters_fingerprint
FROM run_meta
JOIN config ON config.run_id = run_meta.run_id
""",
    "backtest_trades": """
CREATE OR REPLACE VIEW console_read.backtest_trades
WITH (security_barrier=true, security_invoker=false) AS
""" + _BACKTEST_DIRECT_EVIDENCE_CTE + """
SELECT
    meta.experiment_run_id, meta.experiment_id, fill.run_id,
    ROW_NUMBER() OVER (PARTITION BY fill.run_id ORDER BY fill.fill_ts, fill.client_order_id) - 1 AS trade_index,
    fill.client_order_id, fill.cycle_id, fill.symbol, fill.side, fill.fill_ts,
    fill.fill_qty, fill.raw_fill_price, fill.fill_price, fill.fee_amount,
    fill.slippage_amount, ABS(fill.fill_qty * fill.fill_price) AS notional,
    NULL::double precision AS realized_pnl,
    COALESCE(meta.finished_at, meta.created_at) AS observed_at
FROM fills AS fill
JOIN run_meta AS meta ON meta.run_id = fill.run_id
""",
    "backtest_positions": """
CREATE OR REPLACE VIEW console_read.backtest_positions
WITH (security_barrier=true, security_invoker=false) AS
""" + _BACKTEST_DIRECT_RUN_META_CTE + """
, latest_positions AS (
    SELECT DISTINCT ON (snapshot.run_id, snapshot.symbol)
        snapshot.run_id, snapshot.symbol, snapshot.qty, snapshot.avg_price, snapshot.asof_ts
    FROM public.position_snapshots AS snapshot
    WHERE snapshot.symbol IS NOT NULL AND snapshot.symbol <> ''
    ORDER BY snapshot.run_id, snapshot.symbol, snapshot.asof_ts DESC, snapshot.cycle_id DESC NULLS LAST
)
SELECT
    meta.experiment_run_id, meta.experiment_id, position.run_id,
    ROW_NUMBER() OVER (PARTITION BY position.run_id ORDER BY position.symbol) - 1 AS position_index,
    position.symbol, position.qty, position.avg_price, price.close AS last_price,
    position.asof_ts AS last_ts, position.qty * price.close AS market_value,
    CASE WHEN position.avg_price IS NULL THEN NULL
         WHEN position.qty >= 0 THEN (price.close - position.avg_price) * position.qty
         ELSE (position.avg_price - price.close) * ABS(position.qty) END AS unrealized_pnl,
    COALESCE(meta.finished_at, meta.created_at) AS observed_at
FROM latest_positions AS position
JOIN run_meta AS meta ON meta.run_id = position.run_id
LEFT JOIN config ON config.run_id = position.run_id
LEFT JOIN LATERAL (
    SELECT bar.close, bar.ts
    FROM public.stock_bar_events AS bar
    WHERE config.asset_class = 'stock' AND bar.symbol = position.symbol
      AND bar.timeframe = config.timeframe AND bar.ts <= position.asof_ts
      AND (config.market_data_config->>'source' IS NULL OR bar.source = config.market_data_config->>'source')
    UNION ALL
    SELECT bar.close, bar.ts
    FROM public.crypto_bar_events AS bar
    WHERE config.asset_class = 'crypto' AND bar.symbol = position.symbol
      AND bar.timeframe = config.timeframe AND bar.ts <= position.asof_ts
      AND (config.market_data_config->>'source' IS NULL OR bar.source = config.market_data_config->>'source')
    ORDER BY ts DESC LIMIT 1
) AS price ON true
""",
    "backtest_equity_curve": """
CREATE OR REPLACE VIEW console_read.backtest_equity_curve
WITH (security_barrier=true, security_invoker=false) AS
""" + _BACKTEST_DIRECT_EVIDENCE_CTE + """
SELECT meta.experiment_run_id, meta.experiment_id, points.run_id, points.point_index,
       points.ts, points.strategy_equity, NULL::double precision AS benchmark_equity,
       COALESCE(meta.finished_at, meta.created_at) AS observed_at
FROM equity_points AS points
JOIN run_meta AS meta ON meta.run_id = points.run_id
""",
    "backtest_performance": """
CREATE OR REPLACE VIEW console_read.backtest_performance
WITH (security_barrier=true, security_invoker=false) AS
""" + _BACKTEST_DIRECT_EVIDENCE_CTE + """
, returns AS (
    SELECT points.*,
        CASE WHEN points.previous_equity = 0 THEN NULL
             ELSE points.strategy_equity / points.previous_equity - 1 END AS period_return,
        CASE WHEN points.running_peak = 0 THEN NULL
             ELSE 1 - points.strategy_equity / points.running_peak END AS drawdown
    FROM equity_points AS points
), aggregates AS (
    SELECT
        points.run_id, MIN(points.ts) AS first_ts, MAX(points.ts) AS last_ts,
        MAX(points.point_index) + 1 AS point_count,
        MAX(points.strategy_equity) FILTER (WHERE points.ts = aggregates_last.last_ts) AS end_equity,
        MAX(points.start_equity) AS start_equity,
        AVG(points.period_return) FILTER (WHERE points.period_return IS NOT NULL) AS average_return,
        STDDEV_POP(points.period_return) FILTER (WHERE points.period_return IS NOT NULL) AS return_stddev,
        STDDEV_POP(points.period_return) FILTER (WHERE points.period_return < 0) AS downside_stddev,
        MAX(points.drawdown) AS max_drawdown,
        SQRT(AVG(points.drawdown * points.drawdown) FILTER (WHERE points.drawdown IS NOT NULL)) AS ulcer_index,
        AVG(points.net_notional) AS avg_net_exposure,
        AVG(points.gross_notional) AS avg_gross_exposure,
        AVG(ABS(points.net_notional) / NULLIF(points.strategy_equity, 0)) AS avg_invested_pct
    FROM returns AS points
    JOIN (SELECT run_id, MAX(ts) AS last_ts FROM returns GROUP BY run_id) AS aggregates_last
      ON aggregates_last.run_id = points.run_id
    GROUP BY points.run_id, aggregates_last.last_ts
), fees AS (
    SELECT fill.run_id, SUM(fill.fee_amount) AS total_fees,
           SUM(fill.slippage_amount) AS total_slippage, COUNT(*) AS fill_count
    FROM fills AS fill GROUP BY fill.run_id
), period_factors AS (
    SELECT meta.run_id,
        CASE WHEN RIGHT(meta.timeframe, 3) = 'Min' THEN 365.0 * 24 * 60 / NULLIF(REGEXP_REPLACE(meta.timeframe, '[^0-9]', '', 'g')::double precision, 0)
             WHEN RIGHT(meta.timeframe, 4) = 'Hour' THEN 365.0 * 24 / NULLIF(REGEXP_REPLACE(meta.timeframe, '[^0-9]', '', 'g')::double precision, 0)
             WHEN RIGHT(meta.timeframe, 3) = 'Day' THEN 365.0 / NULLIF(REGEXP_REPLACE(meta.timeframe, '[^0-9]', '', 'g')::double precision, 0)
             ELSE 1.0 END AS periods_per_year
    FROM run_meta AS meta
)
SELECT
    meta.experiment_run_id, meta.experiment_id, aggregate.run_id,
    COALESCE(meta.finished_at, meta.created_at) AS observed_at,
    aggregate.point_count::integer AS total_runs, 0::integer AS failed_runs,
    NULL::double precision AS realized_pnl, fees.total_fees, fees.total_slippage,
    aggregate.start_equity AS strategy_start_equity, aggregate.end_equity AS strategy_end_equity,
    aggregate.end_equity / NULLIF(aggregate.start_equity, 0) - 1 AS strategy_total_return,
    CASE WHEN aggregate.start_equity > 0 AND aggregate.end_equity > 0 AND aggregate.point_count > 1
         THEN POWER(aggregate.end_equity / aggregate.start_equity, period.periods_per_year / (aggregate.point_count - 1)) - 1 END AS strategy_cagr,
    aggregate.return_stddev * SQRT(period.periods_per_year) AS strategy_volatility,
    aggregate.average_return / NULLIF(aggregate.return_stddev, 0) * SQRT(period.periods_per_year) AS strategy_sharpe,
    aggregate.average_return / NULLIF(aggregate.downside_stddev, 0) * SQRT(period.periods_per_year) AS strategy_sortino,
    aggregate.max_drawdown AS strategy_max_drawdown, NULL::integer AS strategy_max_drawdown_duration,
    NULL::double precision AS strategy_calmar, aggregate.ulcer_index AS strategy_ulcer_index,
    aggregate.avg_net_exposure AS strategy_avg_net_exposure,
    aggregate.avg_gross_exposure AS strategy_avg_gross_exposure,
    aggregate.avg_invested_pct AS strategy_avg_invested_pct,
    fees.fill_count::integer AS strategy_trade_count, NULL::double precision AS strategy_hit_rate,
    NULL::double precision AS strategy_profit_factor, NULL::double precision AS strategy_expectancy,
    NULL::double precision AS strategy_avg_win, NULL::double precision AS strategy_avg_loss,
    NULL::double precision AS strategy_turnover,
    NULL::double precision AS benchmark_start_equity, NULL::double precision AS benchmark_end_equity,
    NULL::double precision AS benchmark_total_return, NULL::double precision AS benchmark_cagr,
    NULL::double precision AS benchmark_volatility, NULL::double precision AS benchmark_sharpe,
    NULL::double precision AS benchmark_sortino, NULL::double precision AS benchmark_max_drawdown,
    NULL::integer AS benchmark_max_drawdown_duration, NULL::double precision AS benchmark_calmar,
    NULL::double precision AS benchmark_ulcer_index, NULL::double precision AS tracking_error,
    NULL::double precision AS information_ratio, NULL::double precision AS alpha,
    NULL::double precision AS beta, 0::integer AS warnings_count
FROM aggregates AS aggregate
JOIN run_meta AS meta ON meta.run_id = aggregate.run_id
JOIN period_factors AS period ON period.run_id = aggregate.run_id
LEFT JOIN fees ON fees.run_id = aggregate.run_id
""",
    "backtest_exposure": """
CREATE OR REPLACE VIEW console_read.backtest_exposure
WITH (security_barrier=true, security_invoker=false) AS
""" + _BACKTEST_DIRECT_EVIDENCE_CTE + """
 , equity_summary AS (
    SELECT points.run_id,
           AVG(points.net_notional) AS avg_net_exposure,
           AVG(points.gross_notional) AS avg_gross_exposure,
           AVG(ABS(points.net_notional) / NULLIF(points.strategy_equity, 0)) AS avg_invested_pct,
           (ARRAY_AGG(points.net_notional ORDER BY points.ts DESC))[1] AS final_net_notional,
           (ARRAY_AGG(points.gross_notional ORDER BY points.ts DESC))[1] AS final_gross_notional
    FROM equity_points AS points
    GROUP BY points.run_id
), latest_positions AS (
    SELECT DISTINCT ON (snapshot.run_id, snapshot.symbol)
           snapshot.run_id, snapshot.symbol, snapshot.qty
    FROM public.position_snapshots AS snapshot
    WHERE snapshot.symbol IS NOT NULL AND snapshot.symbol <> ''
    ORDER BY snapshot.run_id, snapshot.symbol, snapshot.asof_ts DESC, snapshot.cycle_id DESC NULLS LAST
), position_summary AS (
    SELECT positions.run_id,
           COUNT(*) FILTER (WHERE positions.qty IS NOT NULL AND positions.qty <> 0)::integer AS position_count,
           COUNT(*) FILTER (WHERE positions.qty > 0)::integer AS long_positions,
           COUNT(*) FILTER (WHERE positions.qty < 0)::integer AS short_positions
    FROM latest_positions AS positions
    GROUP BY positions.run_id
)
SELECT meta.experiment_run_id, meta.experiment_id, summary.run_id,
       COALESCE(meta.finished_at, meta.created_at) AS observed_at,
       summary.avg_net_exposure, summary.avg_gross_exposure, summary.avg_invested_pct,
       summary.final_net_notional, summary.final_gross_notional,
       COALESCE(positions.position_count, 0)::integer AS position_count,
       COALESCE(positions.long_positions, 0)::integer AS long_positions,
       COALESCE(positions.short_positions, 0)::integer AS short_positions
FROM equity_summary AS summary
JOIN run_meta AS meta ON meta.run_id = summary.run_id
LEFT JOIN position_summary AS positions ON positions.run_id = summary.run_id
""",
    "backtest_assumptions": """
CREATE OR REPLACE VIEW console_read.backtest_assumptions
WITH (security_barrier=true, security_invoker=false) AS
""" + _BACKTEST_DIRECT_RUN_META_CTE + """
SELECT meta.experiment_run_id, meta.experiment_id, meta.run_id,
       config.backtest_config #>> '{assumptions,fill_model}' AS fill_model,
       NULLIF(config.backtest_config #>> '{assumptions,latency_ms}', '')::double precision AS latency_ms,
       NULLIF(config.backtest_config #>> '{assumptions,fees,fixed_per_order}', '')::double precision AS fee_fixed_per_order,
       NULLIF(config.backtest_config #>> '{assumptions,fees,bps}', '')::double precision AS fee_bps,
       NULLIF(config.backtest_config #>> '{assumptions,fees,minimum_fee}', '')::double precision AS fee_minimum,
       NULLIF(config.backtest_config #>> '{assumptions,slippage,bps}', '')::double precision AS slippage_bps,
       NULLIF(config.backtest_config #>> '{assumptions,data,allow_latest_prior_bar}', '')::boolean AS allow_latest_prior_bar,
       NULLIF(config.backtest_config #>> '{assumptions,data,allow_price_carry_forward}', '')::boolean AS allow_price_carry_forward,
       COALESCE(meta.finished_at, meta.created_at) AS observed_at
FROM run_meta AS meta JOIN config ON config.run_id = meta.run_id
""",
    "backtest_evidence_coverage": """
CREATE OR REPLACE VIEW console_read.backtest_evidence_coverage
WITH (security_barrier=true, security_invoker=false) AS
""" + _BACKTEST_DIRECT_RUN_META_CTE + """
SELECT meta.experiment_run_id, meta.experiment_id, meta.run_id,
       COALESCE(meta.finished_at, meta.created_at) AS observed_at,
       CASE WHEN EXISTS (SELECT 1 FROM public.signal_events e WHERE e.run_id = meta.run_id) THEN 'recorded'
            WHEN COALESCE((config.persist_config->>'signals')::boolean, false) THEN 'not_recorded' ELSE 'not_applicable' END AS signal_events_status,
       CASE WHEN EXISTS (SELECT 1 FROM public.order_events e WHERE e.run_id = meta.run_id) THEN 'recorded'
            WHEN COALESCE((config.persist_config->>'orders')::boolean, false) THEN 'not_recorded' ELSE 'not_applicable' END AS order_events_status,
       CASE WHEN EXISTS (SELECT 1 FROM public.fill_events e WHERE e.run_id = meta.run_id) THEN 'recorded'
            WHEN COALESCE((config.persist_config->>'fills')::boolean, false) THEN 'not_recorded' ELSE 'not_applicable' END AS fill_events_status,
       CASE WHEN EXISTS (SELECT 1 FROM public.position_snapshots e WHERE e.run_id = meta.run_id) THEN 'recorded'
            WHEN COALESCE((config.persist_config->>'positions')::boolean, false) THEN 'not_recorded' ELSE 'not_applicable' END AS position_snapshots_status,
       CASE WHEN EXISTS (SELECT 1 FROM public.risk_compositions e WHERE e.run_id = meta.run_id)
                 OR EXISTS (SELECT 1 FROM public.risk_decisions e WHERE e.run_id = meta.run_id) THEN 'recorded'
            WHEN COALESCE((config.persist_config->>'orders')::boolean, false) THEN 'not_recorded' ELSE 'not_applicable' END AS risk_evidence_status
FROM run_meta AS meta JOIN config ON config.run_id = meta.run_id
""",
    "backtest_warnings": """
CREATE OR REPLACE VIEW console_read.backtest_warnings
WITH (security_barrier=true, security_invoker=false) AS
""" + _BACKTEST_DIRECT_RUN_META_CTE + """
SELECT meta.experiment_run_id, meta.experiment_id, meta.run_id,
       ROW_NUMBER() OVER (PARTITION BY meta.run_id ORDER BY warning.warning) - 1 AS warning_index,
       warning.warning, COALESCE(meta.finished_at, meta.created_at) AS observed_at
FROM run_meta AS meta
JOIN LATERAL (
    SELECT meta.error_message AS warning WHERE meta.error_message IS NOT NULL
    UNION ALL
    SELECT cycle.error_message FROM public.run_events AS cycle
    WHERE cycle.run_id = meta.run_id AND cycle.error_message IS NOT NULL
) AS warning ON true
""",
    "backtest_provenance": """
CREATE OR REPLACE VIEW console_read.backtest_provenance
WITH (security_barrier=true, security_invoker=false) AS
""" + _BACKTEST_DIRECT_RUN_META_CTE + """
SELECT meta.experiment_run_id, meta.experiment_id, meta.run_id,
       item.key AS provenance_key, item.value AS provenance_value,
       COALESCE(meta.finished_at, meta.created_at) AS observed_at
FROM run_meta AS meta
JOIN LATERAL jsonb_each_text(jsonb_build_object(
    'strategy_id', meta.strategy_id,
    'strategy_version', meta.strategy_version,
    'asset_class', meta.asset_class,
    'timeframe', meta.timeframe,
    'symbols', array_to_string(meta.symbols, ','),
    'start_ts', meta.start_ts,
    'end_ts', meta.end_ts
)) AS item(key, value) ON true
WHERE item.value IS NOT NULL
""",
}

CONSOLE_READ_VIEW_SQL = {
    **CONSOLE_READ_VIEW_SQL,
    **{
        name: definition.replace("security_barrier=true", "security_barrier=false")
        for name, definition in _CONSOLE_READ_DIRECT_VIEW_SQL.items()
    },
}
CONSOLE_READ_CONTRACT_COLUMNS: Final[tuple[str, ...]] = (
    "contract_name",
    "contract_version",
    "minimum_consumer_version",
    "installed_at",
)

CONSOLE_READ_VERSION_QUERY: Final = """
SELECT contract_version, minimum_consumer_version
FROM console_read.contract_versions
WHERE contract_name = %s
"""


@dataclass(frozen=True)
class ConsoleReadCompatibility:
    """Compatibility result for one Console consumer and installed contract."""

    compatible: bool
    installed_version: int | None
    minimum_consumer_version: int | None
    consumer_version: int
    reason: str | None


@dataclass(frozen=True)
class ConsoleReadInspection:
    """Catalog and compatibility result for the installed read contract."""

    compatibility: ConsoleReadCompatibility
    issues: tuple[str, ...]

    @property
    def ready(self) -> bool:
        """Return whether the installed read contract is usable by this consumer."""
        return self.compatibility.compatible and not self.issues


def assess_console_read_compatibility(
    *,
    installed_version: int | None,
    minimum_consumer_version: int | None,
    consumer_version: int = CONSOLE_READ_CONTRACT_VERSION,
) -> ConsoleReadCompatibility:
    """Assess an installed contract without querying or mutating PostgreSQL.

    A newer additive database contract may continue admitting an older consumer by
    retaining a sufficiently low ``minimum_consumer_version``. Missing, invalid,
    or older contracts fail closed.
    """
    if installed_version is None or minimum_consumer_version is None:
        reason = "console_read_contract_missing"
    elif min(installed_version, minimum_consumer_version, consumer_version) < 1 or minimum_consumer_version > installed_version:
        reason = "console_read_contract_invalid"
    elif consumer_version < minimum_consumer_version:
        reason = "console_consumer_too_old"
    elif consumer_version > installed_version:
        reason = "console_read_contract_too_old"
    else:
        reason = None
    return ConsoleReadCompatibility(
        compatible=reason is None,
        installed_version=installed_version,
        minimum_consumer_version=minimum_consumer_version,
        consumer_version=consumer_version,
        reason=reason,
    )


def install_console_read_contract(connection: Any) -> None:
    """Install the current read contract without provisioning database identity.

    Args:
        connection: Psycopg connection authenticated as the producer migration
            owner. It must own the runtime source tables.

    Raises:
        RuntimeError: If installation would downgrade a newer contract.
        Exception: If PostgreSQL rejects a migration statement.
    """
    _require_psycopg()

    with connection.transaction():
        connection.execute("CREATE SCHEMA IF NOT EXISTS console_read")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS console_read.contract_versions (
                contract_name TEXT PRIMARY KEY,
                contract_version INTEGER NOT NULL CHECK (contract_version > 0),
                minimum_consumer_version INTEGER NOT NULL
                    CHECK (minimum_consumer_version > 0),
                installed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CHECK (minimum_consumer_version <= contract_version)
            )
            """
        )
        existing_version = connection.execute(
            CONSOLE_READ_VERSION_QUERY, [CONSOLE_READ_CONTRACT]
        ).fetchone()
        if existing_version is not None and int(existing_version[0]) > CONSOLE_READ_CONTRACT_VERSION:
            raise RuntimeError(
                "Refusing to downgrade Console read contract from version "
                f"{existing_version[0]} to {CONSOLE_READ_CONTRACT_VERSION}."
            )
        for view_name, source_table in CONSOLE_READ_SOURCES.items():
            columns = CONSOLE_READ_COLUMNS[view_name]
            custom_definition = CONSOLE_READ_VIEW_SQL.get(view_name)
            if custom_definition is not None:
                connection.execute(custom_definition)
                continue
            connection.execute(
                sql.SQL(
                    "CREATE OR REPLACE VIEW console_read.{} "
                    "WITH (security_barrier=true, security_invoker=false) AS "
                    "SELECT {} FROM public.{}"
                ).format(
                    sql.Identifier(view_name),
                    sql.SQL(", ").join(sql.Identifier(column) for column in columns),
                    sql.Identifier(source_table),
                )
            )
        connection.execute(
            """
            INSERT INTO console_read.contract_versions (
                contract_name, contract_version, minimum_consumer_version, installed_at
            ) VALUES (%s, %s, %s, now())
            ON CONFLICT (contract_name) DO UPDATE SET
                contract_version = EXCLUDED.contract_version,
                minimum_consumer_version = EXCLUDED.minimum_consumer_version,
                installed_at = EXCLUDED.installed_at
            """,
            [
                CONSOLE_READ_CONTRACT,
                CONSOLE_READ_CONTRACT_VERSION,
                CONSOLE_READ_MINIMUM_CONSUMER_VERSION,
            ],
        )


def rollback_console_read_contract(connection: Any) -> None:
    """Remove the current contract after confirming no later one is installed."""
    relation = connection.execute(
        "SELECT to_regclass('console_read.contract_versions')"
    ).fetchone()
    if relation is None or relation[0] is None:
        raise RuntimeError("Console read contract is not installed.")
    row = connection.execute(
        CONSOLE_READ_VERSION_QUERY, [CONSOLE_READ_CONTRACT]
    ).fetchone()
    installed_version = int(row[0]) if row is not None else None
    if installed_version != CONSOLE_READ_CONTRACT_VERSION:
        raise RuntimeError(
            "Refusing Console read-contract rollback: expected installed version "
            f"{CONSOLE_READ_CONTRACT_VERSION}, found {installed_version!r}."
        )
    with connection.transaction():
        connection.execute("DROP SCHEMA console_read CASCADE")


def inspect_console_read_contract(
    connection: Any,
    *,
    consumer_version: int = CONSOLE_READ_CONTRACT_VERSION,
) -> ConsoleReadInspection:
    """Inspect only the installed relation shape and compatibility metadata.

    Authentication and authorization are deployment extension points rather
    than responsibilities of this database migration. The Console API owns its
    connection policy and read-only transaction boundary.
    """
    issues: list[str] = []
    catalog_rows = connection.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'console_read'
        ORDER BY table_name, ordinal_position
        """
    ).fetchall()
    observed_columns: dict[str, list[str]] = {}
    for table_name, column_name in catalog_rows:
        observed_columns.setdefault(str(table_name), []).append(str(column_name))
    expected_relations = {
        "contract_versions": CONSOLE_READ_CONTRACT_COLUMNS,
        **CONSOLE_READ_COLUMNS,
    }
    for relation_name, expected_columns in expected_relations.items():
        if tuple(observed_columns.get(relation_name, ())) != expected_columns:
            issues.append(f"console_read_catalog_mismatch:{relation_name}")

    contract_relation = connection.execute(
        "SELECT to_regclass('console_read.contract_versions')"
    ).fetchone()
    if (
        contract_relation is None
        or contract_relation[0] is None
        or tuple(observed_columns.get("contract_versions", ())) != CONSOLE_READ_CONTRACT_COLUMNS
    ):
        compatibility = assess_console_read_compatibility(
            installed_version=None,
            minimum_consumer_version=None,
            consumer_version=consumer_version,
        )
    else:
        version_row = connection.execute(
            CONSOLE_READ_VERSION_QUERY, [CONSOLE_READ_CONTRACT]
        ).fetchone()
        compatibility = assess_console_read_compatibility(
            installed_version=int(version_row[0]) if version_row else None,
            minimum_consumer_version=int(version_row[1]) if version_row else None,
            consumer_version=consumer_version,
        )
    return ConsoleReadInspection(
        compatibility=compatibility,
        issues=tuple(issues),
    )


def _require_psycopg() -> None:
    if psycopg is None or sql is None:  # pragma: no cover - import guard
        raise ImportError("psycopg is required to manage the Console read contract")


def _open_connection(environment_variable: str) -> Any:
    _require_psycopg()
    dsn = os.environ.get(environment_variable)
    if not dsn:
        raise RuntimeError(f"{environment_variable} must contain a PostgreSQL DSN.")
    return psycopg.connect(dsn)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install, verify, or roll back the Trader Console read contract."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("install")
    subparsers.add_parser("verify")
    from .console_contract_status import CONSUMERS

    status = subparsers.add_parser("status", help="Explain migration requirements without changing the database.")
    status.add_argument("--offline", action="store_true", help="Show release and consumer requirements without connecting.")
    status.add_argument("--consumer", choices=tuple(item.name for item in CONSUMERS))
    status.add_argument("--json", action="store_true", dest="json_output")
    rollback = subparsers.add_parser("rollback")
    rollback.add_argument(
        "--confirm-version",
        type=int,
        required=True,
        choices=(CONSOLE_READ_CONTRACT_VERSION,),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the explicit Console read-contract deployment command."""
    arguments = _parser().parse_args(argv)
    if arguments.command == "status":
        from .console_contract_status import run_status

        return run_status(offline=arguments.offline, consumer=arguments.consumer, json_output=arguments.json_output)
    if arguments.command == "verify":
        with _open_connection("TRADER_CONSOLE_DATABASE_URL") as connection:
            inspection = inspect_console_read_contract(connection)
        if inspection.ready:
            print(
                "Console read contract is ready at version "
                f"{inspection.compatibility.installed_version}."
            )
            return 0
        problems = [
            *inspection.issues,
            inspection.compatibility.reason,
        ]
        print("Console read contract is not ready: " + ", ".join(p for p in problems if p))
        return 1

    with _open_connection("TRADER_CONSOLE_MIGRATION_DSN") as connection:
        if arguments.command == "install":
            install_console_read_contract(connection)
            print(f"Installed Console read contract {CONSOLE_READ_CONTRACT_VERSION}.")
        else:
            rollback_console_read_contract(connection)
            print(
                "Rolled back Console read contract version "
                f"{arguments.confirm_version}."
            )
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
