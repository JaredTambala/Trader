"""Define typed methodology field groups used by method cards.

The models organize entry, exit, sizing, risk, data, and implementation details
without assuming every field can be extracted. Nullable values retain explicit
evidence status rather than being filled with generated defaults.
"""

from __future__ import annotations

from typing import Any, Mapping

from .common import (
    _mapping,
)
from .evidence import EvidenceBackedField

METHODOLOGY_CORE_FIELD_SCHEMA: Mapping[str, frozenset[str]] = {
    "identity": frozenset(
        {
            "method_name",
            "description",
            "aliases",
            "intended_use",
            "source_context",
            "limitations",
        }
    ),
    "scope": frozenset(
        {
            "asset_classes",
            "instruments",
            "markets",
            "timeframes",
            "horizon",
            "universe_definition",
            "market_regime",
            "geography",
        }
    ),
    "data_requirements": frozenset(
        {
            "required_inputs",
            "price_fields",
            "fundamental_fields",
            "alternative_data_fields",
            "option_chain_fields",
            "frequency",
            "lookback_window",
            "preprocessing",
            "data_quality_requirements",
        }
    ),
    "method_specification": frozenset(
        {
            "hypothesis",
            "algorithm_steps",
            "equations",
            "parameters",
            "estimation_method",
            "statistical_tests",
            "optimization_objective",
            "calibration",
        }
    ),
    "signal_decision_logic": frozenset(
        {
            "signal_definition",
            "entry_rules",
            "exit_rules",
            "thresholds",
            "ranking_rules",
            "position_direction",
            "rebalance_rules",
        }
    ),
    "portfolio_execution": frozenset(
        {
            "sizing",
            "portfolio_construction",
            "constraints",
            "rebalancing",
            "execution_timing",
            "order_types",
            "transaction_cost_assumptions",
            "liquidity_assumptions",
        }
    ),
    "risk_validation": frozenset(
        {
            "risk_controls",
            "validation_tests",
            "benchmarks",
            "performance_metrics",
            "stress_tests",
            "failure_modes",
            "assumptions",
            "known_limitations",
        }
    ),
    "implementation_notes": frozenset(
        {
            "implementation_steps",
            "libraries",
            "numerical_stability",
            "edge_cases",
            "runtime_requirements",
            "monitoring",
        }
    ),
}
"""Common nullable field groups shared by all methodology families."""


METHODOLOGY_EXTENSION_FIELD_SCHEMA: Mapping[str, frozenset[str]] = {
    "technical_indicators": frozenset(
        {
            "indicator_formula",
            "input_series",
            "lookback_period",
            "smoothing_method",
            "normalization",
            "overbought_threshold",
            "oversold_threshold",
            "warmup_period",
            "divergence_rules",
            "parameter_defaults",
        }
    ),
    "statistical_arbitrage": frozenset(
        {
            "spread_definition",
            "hedge_ratio_method",
            "cointegration_test",
            "stationarity_test",
            "entry_zscore",
            "exit_zscore",
            "stop_loss",
            "formation_window",
            "trading_window",
            "rebalance_frequency",
            "leg_universe",
            "mean_reversion_assumption",
        }
    ),
    "options_derivatives": frozenset(
        {
            "instrument_type",
            "payoff_profile",
            "legs",
            "strike_selection",
            "expiry_selection",
            "volatility_assumption",
            "greeks",
            "delta_hedging",
            "margin_assumptions",
            "exercise_style",
            "assignment_risk",
            "scenario_analysis",
        }
    ),
    "fundamental_valuation": frozenset(
        {
            "valuation_model",
            "financial_statement_inputs",
            "forecast_horizon",
            "discount_rate",
            "terminal_value",
            "factor_exposures",
            "quality_filters",
            "revision_triggers",
            "normalization",
        }
    ),
    "sentiment_alternative_data": frozenset(
        {
            "source_type",
            "raw_signal",
            "entity_mapping",
            "aggregation_window",
            "scoring_model",
            "lag_assumptions",
            "coverage_requirements",
            "bias_controls",
            "noise_filters",
            "commodity_mapping",
        }
    ),
    "portfolio_construction": frozenset(
        {
            "objective",
            "allocation_method",
            "constraints",
            "rebalance_cadence",
            "turnover_limit",
            "risk_budget",
            "diversification_rule",
            "optimization_inputs",
            "cash_handling",
        }
    ),
    "risk_models": frozenset(
        {
            "risk_measure",
            "confidence_level",
            "lookback_window",
            "correlation_model",
            "covariance_estimator",
            "stress_scenarios",
            "limit_thresholds",
            "breach_actions",
            "model_validation",
        }
    ),
    "execution_methods": frozenset(
        {
            "execution_algorithm",
            "order_slicing",
            "participation_rate",
            "schedule",
            "venue_selection",
            "slippage_model",
            "latency_assumptions",
            "market_impact_model",
            "fill_assumptions",
        }
    ),
}
"""Nullable domain extension blocks for specific methodology families."""


def _normalize_methodology_field_groups(
    groups: Mapping[str, Mapping[str, Any]],
    *,
    schema: Mapping[str, frozenset[str]],
    scope: str,
) -> dict[str, dict[str, EvidenceBackedField]]:
    normalized: dict[str, dict[str, EvidenceBackedField]] = {}
    for group_name, raw_fields in groups.items():
        group = str(group_name)
        if group not in schema:
            allowed = ", ".join(sorted(schema))
            raise ValueError(f"unsupported {scope} group: {group}; allowed values: {allowed}")
        fields = _mapping(raw_fields)
        normalized_fields: dict[str, EvidenceBackedField] = {}
        for field_name, raw_field in fields.items():
            name = str(field_name)
            if name not in schema[group]:
                allowed = ", ".join(sorted(schema[group]))
                raise ValueError(f"unsupported {scope} field for {group}: {name}; allowed values: {allowed}")
            normalized_fields[name] = _coerce_evidence_backed_field(raw_field)
        normalized[group] = normalized_fields
    return normalized


def _coerce_evidence_backed_field(value: Any) -> EvidenceBackedField:
    if isinstance(value, EvidenceBackedField):
        return value
    if isinstance(value, Mapping):
        return EvidenceBackedField.from_dict(value)
    return EvidenceBackedField(value=value)


def _serialize_methodology_field_groups(
    groups: Mapping[str, Mapping[str, EvidenceBackedField]],
) -> dict[str, dict[str, Any]]:
    return {
        group: {name: field.to_dict() for name, field in fields.items()}
        for group, fields in groups.items()
    }
