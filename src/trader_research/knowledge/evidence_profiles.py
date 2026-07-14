"""Family-level evidence role profiles for open-world methodology extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


PROFILE_VERSION = "1"
"""Version for the maintained family evidence-role profile catalog."""

READINESS_LEVELS = ("descriptive", "implementation", "signal", "strategy_template", "risk_manager")
"""Supported methodology-readiness goals used by evidence assembly and validation."""


@dataclass(frozen=True)
class EvidenceRoleProfile:
    """One family-level evidence role used to assemble source-backed method packets."""

    role_id: str
    description: str
    search_terms: tuple[str, ...]
    field_paths: tuple[tuple[str, str, str], ...] = tuple()
    semantic_expectation: str | None = None


@dataclass(frozen=True)
class MethodologyFamilyEvidenceProfile:
    """Closed evidence-role contract for one methodology family.

    Profiles define what kinds of evidence should be searched and validated for a
    family. They deliberately do not enumerate known method targets; method names
    remain open-world values discovered from source/query evidence.
    """

    family: str
    version: str
    roles: tuple[EvidenceRoleProfile, ...]
    readiness_required_roles: Mapping[str, tuple[str, ...]]
    source_suitability: tuple[str, ...] = ("method_textbook", "primary_paper", "foundation_textbook")

    def role(self, role_id: str) -> EvidenceRoleProfile | None:
        """Return one role by ID, if present in this family profile."""
        for role in self.roles:
            if role.role_id == role_id:
                return role
        return None


def profile_for_family(family: str) -> MethodologyFamilyEvidenceProfile | None:
    """Return the maintained family profile for a normalized methodology family."""
    return FAMILY_EVIDENCE_PROFILES.get(normalize_family(family))


def required_roles_for_readiness(
    profile: MethodologyFamilyEvidenceProfile,
    readiness_goal: str,
) -> tuple[str, ...]:
    """Return required role IDs for a readiness goal, including descriptive base roles."""
    normalized_goal = normalize_readiness(readiness_goal)
    required: list[str] = []
    for level in READINESS_LEVELS:
        for role_id in profile.readiness_required_roles.get(level, ()):
            if role_id not in required:
                required.append(role_id)
        if level == normalized_goal:
            break
    return tuple(required)


def normalize_readiness(readiness_goal: str | None) -> str:
    """Normalize readiness labels while defaulting unknown values to descriptive."""
    normalized = str(readiness_goal or "descriptive").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in READINESS_LEVELS else "descriptive"


def normalize_family(family: str) -> str:
    """Normalize human-entered family labels into maintained family IDs."""
    text = str(family or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in FAMILY_ALIASES:
        return FAMILY_ALIASES[text]
    if "technical" in text or "indicator" in text or "oscillator" in text:
        return "technical_indicators"
    if "stat" in text or "arbitrage" in text or "pair" in text or "spread" in text:
        return "statistical_arbitrage"
    if "option" in text or "derivative" in text:
        return "options_derivatives"
    if "sentiment" in text or "alternative" in text:
        return "sentiment_alternative_data"
    if "portfolio" in text or "allocation" in text:
        return "portfolio_construction"
    if "risk" in text:
        return "risk_models"
    if "fundamental" in text or "valuation" in text:
        return "fundamental_valuation"
    if "execution" in text or "order" in text:
        return "execution_methods"
    return text


def family_role_ids(family: str) -> tuple[str, ...]:
    """Return role IDs for a family, or an empty tuple for unsupported families."""
    profile = profile_for_family(family)
    return tuple(role.role_id for role in profile.roles) if profile is not None else tuple()


FAMILY_ALIASES: Mapping[str, str] = {
    "indicator": "technical_indicators",
    "indicators": "technical_indicators",
    "technical_indicator": "technical_indicators",
    "statistical": "statistical_arbitrage",
    "statistical_arbitrage": "statistical_arbitrage",
    "options": "options_derivatives",
    "derivatives": "options_derivatives",
    "sentiment": "sentiment_alternative_data",
    "alternative_data": "sentiment_alternative_data",
    "portfolio": "portfolio_construction",
    "risk": "risk_models",
    "fundamental": "fundamental_valuation",
    "execution": "execution_methods",
}


FAMILY_EVIDENCE_PROFILES: Mapping[str, MethodologyFamilyEvidenceProfile] = {
    "technical_indicators": MethodologyFamilyEvidenceProfile(
        family="technical_indicators",
        version=PROFILE_VERSION,
        roles=(
            EvidenceRoleProfile(
                "definition",
                "Source names and describes the indicator or technical rule.",
                ("indicator", "oscillator", "rule", "method", "defined", "called"),
                (("core_fields", "identity", "description"),),
                "definition or local naming evidence",
            ),
            EvidenceRoleProfile(
                "input_data",
                "Source identifies the ordered input series or price fields.",
                ("price", "close", "high", "low", "volume", "return", "series", "input"),
                (
                    ("core_fields", "data_requirements", "required_inputs"),
                    ("extension_fields", "technical_indicators", "input_series"),
                ),
                "input series or data field evidence",
            ),
            EvidenceRoleProfile(
                "formula_algorithm",
                "Source provides formula, computation, or algorithm evidence.",
                ("formula", "compute", "calculate", "average", "ratio", "sum", "=", "moving"),
                (
                    ("core_fields", "method_specification", "algorithm_steps"),
                    ("core_fields", "method_specification", "equations"),
                    ("extension_fields", "technical_indicators", "indicator_formula"),
                ),
                "formula, algorithm, or calculation evidence",
            ),
            EvidenceRoleProfile(
                "parameters",
                "Source describes lookback, smoothing, warmup, or defaults.",
                ("period", "lookback", "window", "smoothing", "warmup", "default", "parameter"),
                (
                    ("core_fields", "method_specification", "parameters"),
                    ("extension_fields", "technical_indicators", "lookback_period"),
                    ("extension_fields", "technical_indicators", "smoothing_method"),
                    ("extension_fields", "technical_indicators", "warmup_period"),
                    ("extension_fields", "technical_indicators", "parameter_defaults"),
                ),
                "parameter or warmup evidence",
            ),
            EvidenceRoleProfile(
                "threshold_semantics",
                "Source defines thresholds or normalized decision regions.",
                ("threshold", "overbought", "oversold", "band", "upper", "lower", "cross", "signal"),
                (
                    ("core_fields", "signal_decision_logic", "thresholds"),
                    ("extension_fields", "technical_indicators", "overbought_threshold"),
                    ("extension_fields", "technical_indicators", "oversold_threshold"),
                    ("extension_fields", "technical_indicators", "normalization"),
                ),
                "threshold or normalization evidence",
            ),
            EvidenceRoleProfile(
                "signal_logic",
                "Source describes signal interpretation, entry, or exit behavior.",
                ("signal", "entry", "exit", "buy", "sell", "long", "short", "position", "cross"),
                (
                    ("core_fields", "signal_decision_logic", "signal_definition"),
                    ("core_fields", "signal_decision_logic", "entry_rules"),
                    ("core_fields", "signal_decision_logic", "exit_rules"),
                ),
                "signal, entry, or exit evidence",
            ),
            EvidenceRoleProfile(
                "limitations",
                "Source describes assumptions, limitations, or failure modes.",
                ("assumption", "limitation", "risk", "failure", "lag", "whipsaw", "noise", "regime"),
                (
                    ("core_fields", "risk_validation", "assumptions"),
                    ("core_fields", "risk_validation", "failure_modes"),
                    ("core_fields", "risk_validation", "known_limitations"),
                ),
                "assumption, limitation, or failure-mode evidence",
            ),
            EvidenceRoleProfile(
                "validation_requirements",
                "Source describes validation or implementation checks.",
                ("validate", "test", "backtest", "out-of-sample", "no-lookahead", "sensitivity"),
                (("core_fields", "risk_validation", "validation_tests"),),
                "validation or test evidence",
            ),
        ),
        readiness_required_roles={
            "descriptive": ("definition", "input_data"),
            "implementation": ("formula_algorithm",),
            "signal": ("signal_logic",),
            "strategy_template": ("signal_logic", "limitations"),
        },
    ),
    "statistical_arbitrage": MethodologyFamilyEvidenceProfile(
        family="statistical_arbitrage",
        version=PROFILE_VERSION,
        roles=(
            EvidenceRoleProfile(
                "definition",
                "Source names and describes the relative-value or arbitrage method.",
                ("statistical arbitrage", "pairs", "spread", "relative value", "mean reversion", "method"),
                (("core_fields", "identity", "description"),),
                "method definition evidence",
            ),
            EvidenceRoleProfile(
                "leg_universe",
                "Source identifies multiple legs, pairs, baskets, or assets.",
                ("pair", "pairs", "asset", "assets", "legs", "basket", "security", "securities"),
                (
                    ("core_fields", "data_requirements", "required_inputs"),
                    ("extension_fields", "statistical_arbitrage", "leg_universe"),
                ),
                "leg universe evidence",
            ),
            EvidenceRoleProfile(
                "spread_definition",
                "Source defines spread, linear combination, residual, or relative-value construction.",
                ("spread", "linear combination", "residual", "difference", "ratio", "portfolio"),
                (
                    ("core_fields", "method_specification", "algorithm_steps"),
                    ("extension_fields", "statistical_arbitrage", "spread_definition"),
                ),
                "spread construction evidence",
            ),
            EvidenceRoleProfile(
                "relationship_model",
                "Source describes relationship estimation, hedge ratio, regression, or correlation.",
                ("hedge ratio", "regression", "correlation", "beta", "coefficient", "estimate"),
                (
                    ("core_fields", "method_specification", "estimation_method"),
                    ("extension_fields", "statistical_arbitrage", "hedge_ratio_method"),
                ),
                "relationship model evidence",
            ),
            EvidenceRoleProfile(
                "stationarity_test",
                "Source describes stationarity, cointegration, residual tests, or mean-reversion diagnostics.",
                ("cointegration", "stationarity", "stationary", "unit root", "residual", "mean revert"),
                (
                    ("core_fields", "method_specification", "statistical_tests"),
                    ("extension_fields", "statistical_arbitrage", "cointegration_test"),
                    ("extension_fields", "statistical_arbitrage", "stationarity_test"),
                    ("extension_fields", "statistical_arbitrage", "mean_reversion_assumption"),
                ),
                "relationship test or stationarity evidence",
            ),
            EvidenceRoleProfile(
                "entry_logic",
                "Source describes entry conditions for spread or relative-value trades.",
                ("entry", "enter", "z-score", "threshold", "deviation", "long", "short", "signal"),
                (
                    ("core_fields", "signal_decision_logic", "entry_rules"),
                    ("extension_fields", "statistical_arbitrage", "entry_zscore"),
                ),
                "entry decision evidence",
            ),
            EvidenceRoleProfile(
                "exit_logic",
                "Source describes exit or mean-reversion close conditions.",
                ("exit", "close", "mean reverts", "mean revert", "reversion", "zero", "threshold"),
                (
                    ("core_fields", "signal_decision_logic", "exit_rules"),
                    ("extension_fields", "statistical_arbitrage", "exit_zscore"),
                ),
                "exit decision evidence",
            ),
            EvidenceRoleProfile(
                "risk_controls",
                "Source describes stop loss, liquidity, costs, or risk controls.",
                ("risk", "stop", "loss", "cost", "liquidity", "drawdown", "exposure", "constraint"),
                (
                    ("core_fields", "risk_validation", "risk_controls"),
                    ("extension_fields", "statistical_arbitrage", "stop_loss"),
                ),
                "risk-control evidence",
            ),
            EvidenceRoleProfile(
                "limitations",
                "Source describes structural breaks, instability, crowding, or failure modes.",
                ("structural break", "unstable", "breakdown", "crowding", "failure", "limitation", "assumption"),
                (
                    ("core_fields", "risk_validation", "failure_modes"),
                    ("core_fields", "risk_validation", "assumptions"),
                ),
                "failure-mode evidence",
            ),
            EvidenceRoleProfile(
                "validation_requirements",
                "Source describes out-of-sample, formation, trading-window, or diagnostic validation.",
                ("out-of-sample", "formation", "trading window", "backtest", "validate", "test", "diagnostic"),
                (
                    ("core_fields", "risk_validation", "validation_tests"),
                    ("extension_fields", "statistical_arbitrage", "formation_window"),
                    ("extension_fields", "statistical_arbitrage", "trading_window"),
                ),
                "validation requirement evidence",
            ),
        ),
        readiness_required_roles={
            "descriptive": ("definition", "leg_universe", "spread_definition"),
            "implementation": ("relationship_model", "stationarity_test"),
            "signal": ("entry_logic", "exit_logic"),
            "strategy_template": ("limitations",),
        },
    ),
    "options_derivatives": MethodologyFamilyEvidenceProfile(
        family="options_derivatives",
        version=PROFILE_VERSION,
        roles=(
            EvidenceRoleProfile("definition", "Source names and describes the options method.", ("option", "derivative", "strategy", "payoff", "position"), (("core_fields", "identity", "description"),)),
            EvidenceRoleProfile("instrument_structure", "Source identifies option instruments or legs.", ("call", "put", "leg", "strike", "expiry", "expiration", "contract"), (("extension_fields", "options_derivatives", "instrument_type"), ("extension_fields", "options_derivatives", "legs"))),
            EvidenceRoleProfile("payoff_risk", "Source describes payoff, Greeks, margin, or assignment risk.", ("payoff", "risk", "delta", "vega", "gamma", "margin", "assignment"), (("extension_fields", "options_derivatives", "payoff_profile"), ("extension_fields", "options_derivatives", "greeks"), ("core_fields", "risk_validation", "risk_controls"))),
            EvidenceRoleProfile("selection_rules", "Source describes strike, expiry, or volatility assumptions.", ("strike", "expiry", "expiration", "volatility", "selection", "maturity"), (("extension_fields", "options_derivatives", "strike_selection"), ("extension_fields", "options_derivatives", "expiry_selection"), ("extension_fields", "options_derivatives", "volatility_assumption"))),
            EvidenceRoleProfile("limitations", "Source describes assumptions, scenario behavior, or failure modes.", ("assumption", "scenario", "limitation", "risk", "loss", "failure"), (("core_fields", "risk_validation", "failure_modes"), ("extension_fields", "options_derivatives", "scenario_analysis"))),
        ),
        readiness_required_roles={
            "descriptive": ("definition", "instrument_structure"),
            "implementation": ("selection_rules",),
            "signal": ("payoff_risk",),
            "strategy_template": ("limitations",),
        },
    ),
    "sentiment_alternative_data": MethodologyFamilyEvidenceProfile(
        family="sentiment_alternative_data",
        version=PROFILE_VERSION,
        roles=(
            EvidenceRoleProfile("definition", "Source names and describes the alternative-data method.", ("sentiment", "alternative data", "news", "text", "signal"), (("core_fields", "identity", "description"),)),
            EvidenceRoleProfile("raw_source", "Source identifies raw text, news, social, or other alternative source.", ("news", "social", "text", "source", "raw", "feed"), (("extension_fields", "sentiment_alternative_data", "source_type"), ("extension_fields", "sentiment_alternative_data", "raw_signal"))),
            EvidenceRoleProfile("mapping", "Source maps entities, assets, or commodities.", ("entity", "asset", "commodity", "mapping", "issuer", "company"), (("extension_fields", "sentiment_alternative_data", "entity_mapping"), ("extension_fields", "sentiment_alternative_data", "commodity_mapping"))),
            EvidenceRoleProfile("scoring_aggregation", "Source describes scoring, preprocessing, or aggregation windows.", ("score", "scoring", "aggregate", "window", "preprocess", "filter"), (("extension_fields", "sentiment_alternative_data", "scoring_model"), ("extension_fields", "sentiment_alternative_data", "aggregation_window"), ("core_fields", "data_requirements", "preprocessing"))),
            EvidenceRoleProfile("bias_limitations", "Source describes lag, coverage, bias, or noise controls.", ("lag", "bias", "noise", "coverage", "limitation", "assumption"), (("extension_fields", "sentiment_alternative_data", "bias_controls"), ("extension_fields", "sentiment_alternative_data", "noise_filters"), ("core_fields", "risk_validation", "failure_modes"))),
        ),
        readiness_required_roles={
            "descriptive": ("definition", "raw_source"),
            "implementation": ("mapping", "scoring_aggregation"),
            "signal": ("scoring_aggregation",),
            "strategy_template": ("bias_limitations",),
        },
    ),
    "portfolio_construction": MethodologyFamilyEvidenceProfile(
        family="portfolio_construction",
        version=PROFILE_VERSION,
        roles=(
            EvidenceRoleProfile("definition", "Source names and describes the portfolio method.", ("portfolio", "allocation", "construction", "optimization"), (("core_fields", "identity", "description"),)),
            EvidenceRoleProfile("objective", "Source defines objective and optimization inputs.", ("objective", "optimization", "utility", "return", "risk", "input"), (("extension_fields", "portfolio_construction", "objective"), ("extension_fields", "portfolio_construction", "optimization_inputs"))),
            EvidenceRoleProfile("allocation_constraints", "Source describes allocation rules and constraints.", ("allocation", "weight", "constraint", "budget", "diversification"), (("extension_fields", "portfolio_construction", "allocation_method"), ("extension_fields", "portfolio_construction", "constraints"), ("extension_fields", "portfolio_construction", "risk_budget"))),
            EvidenceRoleProfile("rebalance_turnover", "Source describes rebalance or turnover controls.", ("rebalance", "turnover", "cadence", "frequency"), (("extension_fields", "portfolio_construction", "rebalance_cadence"), ("extension_fields", "portfolio_construction", "turnover_limit"))),
        ),
        readiness_required_roles={
            "descriptive": ("definition", "objective"),
            "implementation": ("allocation_constraints",),
            "strategy_template": ("rebalance_turnover",),
            "risk_manager": ("allocation_constraints",),
        },
    ),
    "risk_models": MethodologyFamilyEvidenceProfile(
        family="risk_models",
        version=PROFILE_VERSION,
        roles=(
            EvidenceRoleProfile("definition", "Source names and describes the risk model.", ("risk", "model", "measure", "var", "cvar", "drawdown"), (("core_fields", "identity", "description"), ("extension_fields", "risk_models", "risk_measure"))),
            EvidenceRoleProfile("data_estimator", "Source describes input data, correlation, covariance, or estimator.", ("data", "lookback", "correlation", "covariance", "estimator", "history"), (("extension_fields", "risk_models", "lookback_window"), ("extension_fields", "risk_models", "correlation_model"), ("extension_fields", "risk_models", "covariance_estimator"))),
            EvidenceRoleProfile("threshold_actions", "Source describes confidence, limits, thresholds, or breach actions.", ("confidence", "limit", "threshold", "breach", "action"), (("extension_fields", "risk_models", "confidence_level"), ("extension_fields", "risk_models", "limit_thresholds"), ("extension_fields", "risk_models", "breach_actions"))),
            EvidenceRoleProfile("validation_limitations", "Source describes stress scenarios or validation.", ("stress", "scenario", "validate", "test", "limitation", "assumption"), (("extension_fields", "risk_models", "stress_scenarios"), ("extension_fields", "risk_models", "model_validation"), ("core_fields", "risk_validation", "failure_modes"))),
        ),
        readiness_required_roles={
            "descriptive": ("definition", "data_estimator"),
            "implementation": ("threshold_actions",),
            "risk_manager": ("threshold_actions", "validation_limitations"),
        },
    ),
    "fundamental_valuation": MethodologyFamilyEvidenceProfile(
        family="fundamental_valuation",
        version=PROFILE_VERSION,
        roles=(
            EvidenceRoleProfile("definition", "Source names and describes the valuation method.", ("valuation", "fundamental", "model", "value"), (("core_fields", "identity", "description"), ("extension_fields", "fundamental_valuation", "valuation_model"))),
            EvidenceRoleProfile("inputs", "Source identifies statement, factor, or forecast inputs.", ("earnings", "cash flow", "balance sheet", "forecast", "factor", "input"), (("extension_fields", "fundamental_valuation", "financial_statement_inputs"), ("extension_fields", "fundamental_valuation", "factor_exposures"))),
            EvidenceRoleProfile("parameters", "Source describes horizon, discount rate, terminal value, or normalization.", ("horizon", "discount", "terminal", "normalization", "quality"), (("extension_fields", "fundamental_valuation", "forecast_horizon"), ("extension_fields", "fundamental_valuation", "discount_rate"), ("extension_fields", "fundamental_valuation", "terminal_value"), ("extension_fields", "fundamental_valuation", "normalization"))),
            EvidenceRoleProfile("revision_limitations", "Source describes revision triggers or limitations.", ("revision", "trigger", "limitation", "assumption", "risk"), (("extension_fields", "fundamental_valuation", "revision_triggers"), ("core_fields", "risk_validation", "failure_modes"))),
        ),
        readiness_required_roles={
            "descriptive": ("definition", "inputs"),
            "implementation": ("parameters",),
            "signal": ("revision_limitations",),
        },
    ),
    "execution_methods": MethodologyFamilyEvidenceProfile(
        family="execution_methods",
        version=PROFILE_VERSION,
        roles=(
            EvidenceRoleProfile("definition", "Source names and describes the execution method.", ("execution", "order", "algorithm", "twap", "vwap"), (("core_fields", "identity", "description"), ("extension_fields", "execution_methods", "execution_algorithm"))),
            EvidenceRoleProfile("scheduling_slicing", "Source describes order slicing, schedule, or participation.", ("slice", "schedule", "participation", "rate", "interval"), (("extension_fields", "execution_methods", "order_slicing"), ("extension_fields", "execution_methods", "schedule"), ("extension_fields", "execution_methods", "participation_rate"))),
            EvidenceRoleProfile("cost_fill_model", "Source describes slippage, impact, venue, or fill assumptions.", ("slippage", "impact", "venue", "fill", "latency"), (("extension_fields", "execution_methods", "slippage_model"), ("extension_fields", "execution_methods", "market_impact_model"), ("extension_fields", "execution_methods", "fill_assumptions"))),
        ),
        readiness_required_roles={
            "descriptive": ("definition", "scheduling_slicing"),
            "implementation": ("cost_fill_model",),
        },
    ),
}
