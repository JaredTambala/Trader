"""Stable producer-owned relation shapes consumed by Console resources."""

from __future__ import annotations

from typing import Final


# This is intentionally duplicated from the producer contract. The API declares
# what it consumes without importing the migration/installer code into startup.
RESOURCE_CONTRACT_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "stock_bars": (
        "symbol", "timeframe", "ts", "ingested_at", "open", "high", "low",
        "close", "volume", "trade_count", "vwap", "source",
    ),
    "crypto_bars": (
        "symbol", "timeframe", "ts", "ingested_at", "open", "high", "low",
        "close", "volume", "trade_count", "vwap", "source",
    ),
    "data_scope_evidence": (
        "manifest_artifact_id", "quality_artifact_id", "manifest_uri", "quality_uri",
        "evidence_status", "evidence_reason", "manifest_status", "quality_status",
        "manifest_schema_version", "quality_schema_version", "asset_class", "symbols",
        "timeframe", "interval", "bar_type", "requested_start", "requested_end",
        "provider", "source_policy", "manifest_created_at", "manifest_updated_at",
        "quality_created_at", "quality_updated_at", "manifest_source_hash",
        "quality_source_hash", "manifest_payload", "quality_payload", "coverage",
        "findings", "warnings", "provenance_refs",
    ),
    "backtest_runs": (
        "experiment_run_id", "experiment_id", "run_id", "session_id", "status",
        "mode", "created_at", "finished_at", "strategy_id", "strategy_name",
        "strategy_version", "symbols", "asset_class", "timeframe", "start_ts",
        "end_ts", "error_message", "artifact_dir",
    ),
    "backtest_performance": (
        "experiment_run_id", "experiment_id", "run_id", "observed_at",
        "total_runs", "failed_runs", "realized_pnl", "total_fees", "total_slippage",
        "strategy_start_equity", "strategy_end_equity", "strategy_total_return",
        "strategy_cagr", "strategy_volatility", "strategy_sharpe", "strategy_sortino",
        "strategy_max_drawdown", "strategy_max_drawdown_duration", "strategy_calmar",
        "strategy_ulcer_index", "strategy_avg_net_exposure", "strategy_avg_gross_exposure",
        "strategy_avg_invested_pct", "strategy_trade_count", "strategy_hit_rate",
        "strategy_profit_factor", "strategy_expectancy", "strategy_avg_win",
        "strategy_avg_loss", "strategy_turnover", "benchmark_start_equity",
        "benchmark_end_equity", "benchmark_total_return", "benchmark_cagr",
        "benchmark_volatility", "benchmark_sharpe", "benchmark_sortino",
        "benchmark_max_drawdown", "benchmark_max_drawdown_duration", "benchmark_calmar",
        "benchmark_ulcer_index", "tracking_error", "information_ratio", "alpha", "beta",
        "warnings_count",
    ),
    "backtest_exposure": (
        "experiment_run_id", "experiment_id", "run_id", "observed_at",
        "avg_net_exposure", "avg_gross_exposure", "avg_invested_pct",
        "final_net_notional", "final_gross_notional", "position_count", "long_positions",
        "short_positions",
    ),
    "backtest_equity_curve": (
        "experiment_run_id", "experiment_id", "run_id", "point_index", "ts",
        "strategy_equity", "benchmark_equity", "observed_at",
    ),
    "backtest_scope": (
        "experiment_run_id", "experiment_id", "run_id", "observed_at",
        "scope_fingerprint", "asset_class", "symbols", "timeframe", "replay_start",
        "replay_end", "data_scope_id", "data_scope_fingerprint", "saved_scope_id",
        "benchmark_id", "benchmark_method",
        "benchmark_allocation", "initial_cash", "initial_position_count", "fill_model",
        "latency_ms", "fee_fixed_per_order", "fee_bps", "fee_minimum", "slippage_bps",
        "allow_latest_prior_bar", "allow_price_carry_forward", "variant_fingerprint",
        "variant_strategy_id", "variant_strategy_version", "variant_parameters_fingerprint",
    ),
    "backtest_comparison_runs": (
        "experiment_run_id", "experiment_id", "run_id", "status", "scope_fingerprint",
        "data_scope_id", "benchmark_id", "variant_fingerprint", "variant_strategy_id",
        "variant_strategy_version", "strategy_total_return", "benchmark_total_return",
        "strategy_max_drawdown", "benchmark_max_drawdown", "strategy_sharpe",
        "strategy_trade_count", "warnings_count", "observed_at",
    ),
    "backtest_comparison_curves": (
        "experiment_run_id", "experiment_id", "run_id", "scope_fingerprint",
        "variant_fingerprint", "variant_strategy_id", "variant_strategy_version",
        "point_index", "ts", "strategy_normalized", "benchmark_normalized",
        "strategy_drawdown", "benchmark_drawdown", "observed_at",
    ),
    "backtest_trades": (
        "experiment_run_id", "experiment_id", "run_id", "trade_index", "client_order_id",
        "cycle_id", "symbol", "side", "fill_ts", "fill_qty", "raw_fill_price",
        "fill_price", "fee_amount", "slippage_amount", "notional", "realized_pnl",
        "observed_at",
    ),
    "backtest_positions": (
        "experiment_run_id", "experiment_id", "run_id", "position_index", "symbol",
        "qty", "avg_price", "last_price", "last_ts", "market_value", "unrealized_pnl",
        "observed_at",
    ),
    "backtest_assumptions": (
        "experiment_run_id", "experiment_id", "run_id", "fill_model", "latency_ms",
        "fee_fixed_per_order", "fee_bps", "fee_minimum", "slippage_bps",
        "allow_latest_prior_bar", "allow_price_carry_forward", "observed_at",
    ),
    "backtest_warnings": (
        "experiment_run_id", "experiment_id", "run_id", "warning_index", "warning",
        "observed_at",
    ),
    "backtest_provenance": (
        "experiment_run_id", "experiment_id", "run_id", "provenance_key",
        "provenance_value", "observed_at",
    ),
    "backtest_evidence_coverage": (
        "experiment_run_id", "experiment_id", "run_id", "observed_at",
        "signal_events_status", "order_events_status", "fill_events_status",
        "position_snapshots_status", "risk_evidence_status",
    ),
    "signal_lifecycle": (
        "signal_event_id", "run_id", "session_id", "cycle_id", "symbol", "signal_name",
        "signal_value", "target_qty", "generated_at", "mapper_id",
    ),
    "signal_markers": (
        "signal_event_id", "run_id", "session_id", "cycle_id", "symbol", "signal_name",
        "signal_value", "target_qty", "event_ts", "generated_at", "mapper_id",
    ),
    "indicator_series": (
        "run_id", "session_id", "cycle_id", "symbol", "indicator_name", "series_id",
        "series_label", "pane", "scale_group", "unit", "series_kind", "value", "bar_ts",
        "signal_name", "signal_event_id", "strategy_id", "strategy_version",
        "variant_fingerprint", "data_scope_id", "parameters_fingerprint",
    ),
    "risk_composition": (
        "run_id", "session_id", "catalogue_version", "composition_fingerprint",
        "manager_position", "manager_id", "manager_type", "manager_parameters",
    ),
    "risk_summary": (
        "run_id", "composition_fingerprint", "risk_evidence_status", "evaluated_count",
        "approved_count", "transformed_count", "rejected_count", "blocked_count",
    ),
    "risk_decisions": (
        "risk_decision_id", "composition_fingerprint", "run_id", "session_id", "cycle_id",
        "client_order_id", "decision_ts", "manager_id", "manager_type", "manager_position",
        "outcome", "reason_code", "before_qty", "after_qty", "before_order", "after_order",
    ),
    "order_lifecycle": (
        "order_event_id", "client_order_id", "signal_event_id", "run_id", "session_id",
        "cycle_id", "symbol", "side", "qty", "order_type", "status", "broker_order_id",
        "rejection_reason", "created_at",
    ),
    "fill_lifecycle": (
        "fill_event_id", "client_order_id", "run_id", "session_id", "cycle_id", "fill_ts",
        "fill_qty", "raw_fill_price", "slippage_amount", "fee_amount", "fill_price",
    ),
    "research_review_evidence": (
        "artifact_type", "artifact_id", "domain_owner", "producer_tool",
        "artifact_status", "schema_version", "source_hash", "created_at", "updated_at",
        "run_id", "claim_scope", "data_roles", "limitations", "blockers",
        "independent_confirmation", "origin_kind", "session_id", "session_digest",
        "graph_digest", "branch_id", "revision", "node_key",
    ),
}
