"""Describe maintained strategy and risk-manager implementation templates.

The catalog exposes stable template identifiers, source, parameters, and
capabilities without registering implementations or touching persistence.
Callers may use the metadata to create normal implementation-admission inputs.
"""

from __future__ import annotations

from trader_research.foundation import ApplicationResult, error_result, success_result

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence



RESEARCH_LIST_STRATEGY_TEMPLATES = "research_list_strategy_templates"
RESEARCH_LIST_RISK_MANAGER_TEMPLATES = "research_list_risk_manager_templates"
STRATEGY_RUNTIME_CONTRACT = "trader.strategies.Strategy"
RISK_MANAGER_RUNTIME_CONTRACT = "trader.risk.RiskManager"


@dataclass(frozen=True)
class ImplementationTemplateParameter:
    """One typed parameter accepted by a maintained implementation."""

    name: str
    value_type: str
    description: str
    required: bool = False
    default: Any | None = None
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible parameter metadata."""
        payload: dict[str, Any] = {
            "name": self.name,
            "value_type": self.value_type,
            "description": self.description,
            "required": self.required,
            "constraints": dict(self.constraints),
        }
        if not self.required or self.default is not None:
            payload["default"] = self.default
        return payload


@dataclass(frozen=True)
class MaintainedImplementationTemplate:
    """Provider-neutral metadata for one maintained runtime implementation."""

    template_id: str
    implementation_kind: str
    display_name: str
    description: str
    runtime_contract: str
    maintained_entrypoint: str
    parameters: tuple[ImplementationTemplateParameter, ...] = ()
    runtime_context: tuple[str, ...] = ()
    behavior: Mapping[str, Any] = field(default_factory=dict)
    portfolio_mode: str | None = None

    def __post_init__(self) -> None:
        if self.implementation_kind not in {"strategy", "risk_manager"}:
            raise ValueError("unsupported implementation template kind")
        if not self.template_id.strip() or not self.maintained_entrypoint.strip():
            raise ValueError("template identity and maintained entrypoint are required")
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate parameter names for {self.template_id}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize stable template metadata for the public catalog.

        The projection includes source, factory, parameter definitions,
        capabilities, runtime requirements, and resource bounds needed to submit
        normal implementation-registration inputs. It performs no registration.
        """
        payload: dict[str, Any] = {
            "template_id": self.template_id,
            "implementation_kind": self.implementation_kind,
            "display_name": self.display_name,
            "description": self.description,
            "runtime_contract": self.runtime_contract,
            "maintained_entrypoint": self.maintained_entrypoint,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "runtime_context": list(self.runtime_context),
            "behavior": dict(self.behavior),
        }
        if self.portfolio_mode is not None:
            payload["portfolio_mode"] = self.portfolio_mode
        return payload


def _parameter(
    name: str,
    value_type: str,
    description: str,
    default: Any,
    **constraints: Any,
) -> ImplementationTemplateParameter:
    return ImplementationTemplateParameter(
        name=name,
        value_type=value_type,
        description=description,
        default=default,
        constraints=constraints,
    )


_STRATEGY_CONTEXT = ("symbols", "asset_class", "timeframe")
_STRATEGY_TEMPLATES = (
    MaintainedImplementationTemplate(
        template_id="trend_following",
        implementation_kind="strategy",
        display_name="Trend Following",
        description="Long/flat EMA and MACD crossover strategy.",
        runtime_contract=STRATEGY_RUNTIME_CONTRACT,
        maintained_entrypoint=(
            "trader_standard.strategies:build_trend_following_strategy"
        ),
        runtime_context=_STRATEGY_CONTEXT,
        portfolio_mode="per_symbol_independent",
        behavior={"direction": "long_only", "rebalance": "every_bar"},
        parameters=(
            _parameter(
                "target_qty_when_long",
                "number",
                "Long target quantity.",
                1.0,
                minimum=0.0,
            ),
            _parameter("ema_fast_period", "integer", "Fast EMA period.", 12, minimum=1),
            _parameter("ema_slow_period", "integer", "Slow EMA period.", 26, minimum=2),
            _parameter(
                "macd_fast_period", "integer", "MACD fast EMA period.", 12, minimum=1
            ),
            _parameter(
                "macd_slow_period", "integer", "MACD slow EMA period.", 26, minimum=2
            ),
            _parameter(
                "macd_signal_period", "integer", "MACD signal period.", 9, minimum=1
            ),
        ),
    ),
    MaintainedImplementationTemplate(
        template_id="mean_reversion",
        implementation_kind="strategy",
        display_name="Mean Reversion",
        description="Long/flat RSI and SMA stretch strategy.",
        runtime_contract=STRATEGY_RUNTIME_CONTRACT,
        maintained_entrypoint="trader_standard.strategies:build_mean_reversion_strategy",
        runtime_context=_STRATEGY_CONTEXT,
        portfolio_mode="per_symbol_independent",
        behavior={"direction": "long_only", "rebalance": "every_bar"},
        parameters=(
            _parameter(
                "target_qty_when_long",
                "number",
                "Long target quantity.",
                1.0,
                minimum=0.0,
            ),
            _parameter("rsi_period", "integer", "RSI period.", 14, minimum=1),
            _parameter(
                "oversold",
                "number",
                "Oversold entry threshold.",
                30.0,
                minimum=0.0,
                maximum=100.0,
            ),
            _parameter(
                "exit_rsi",
                "number",
                "RSI recovery threshold.",
                50.0,
                minimum=0.0,
                maximum=100.0,
            ),
            _parameter("mean_period", "integer", "SMA period.", 20, minimum=1),
            _parameter(
                "stretch_pct", "number", "SMA stretch fraction.", 0.02, minimum=0.0
            ),
        ),
    ),
    MaintainedImplementationTemplate(
        template_id="bollinger_band",
        implementation_kind="strategy",
        display_name="Bollinger Band",
        description="Long/flat lower-band re-entry strategy.",
        runtime_contract=STRATEGY_RUNTIME_CONTRACT,
        maintained_entrypoint="trader_standard.strategies:build_bollinger_band_strategy",
        runtime_context=_STRATEGY_CONTEXT,
        portfolio_mode="per_symbol_independent",
        behavior={"direction": "long_only", "rebalance": "every_bar"},
        parameters=(
            _parameter(
                "target_qty_when_long",
                "number",
                "Long target quantity.",
                1.0,
                minimum=0.0,
            ),
            _parameter("period", "integer", "Rolling band period.", 20, minimum=1),
            _parameter(
                "stddev_multiplier",
                "number",
                "Band-width multiplier.",
                2.0,
                minimum=0.0,
            ),
        ),
    ),
    MaintainedImplementationTemplate(
        template_id="cross_sectional_momentum",
        implementation_kind="strategy",
        display_name="Cross-Sectional Momentum",
        description="Long-only ranking strategy over the supplied universe.",
        runtime_contract=STRATEGY_RUNTIME_CONTRACT,
        maintained_entrypoint=(
            "trader_standard.strategies:build_cross_sectional_momentum_strategy"
        ),
        runtime_context=_STRATEGY_CONTEXT,
        portfolio_mode="cross_sectional",
        behavior={"direction": "long_only", "ranking": "lookback_return"},
        parameters=(
            _parameter(
                "target_qty_when_long",
                "number",
                "Long target quantity.",
                1.0,
                minimum=0.0,
            ),
            _parameter(
                "lookback_period", "integer", "Return lookback period.", 20, minimum=1
            ),
            _parameter(
                "top_n", "integer", "Number of ranked symbols held.", 2, minimum=1
            ),
            _parameter(
                "rebalance_cadence",
                "string",
                "Rebalance cadence.",
                "every_bar",
                allowed_values=["every_bar", "daily"],
            ),
        ),
    ),
    MaintainedImplementationTemplate(
        template_id="pairs_mean_reversion",
        implementation_kind="strategy",
        display_name="Pairs Mean Reversion",
        description="Long/short spread z-score strategy over deterministic pairs.",
        runtime_contract=STRATEGY_RUNTIME_CONTRACT,
        maintained_entrypoint=(
            "trader_standard.strategies:build_pairs_mean_reversion_strategy"
        ),
        runtime_context=_STRATEGY_CONTEXT,
        portfolio_mode="pairs",
        behavior={"direction": "long_short", "pairing": "disjoint_sorted"},
        parameters=(
            _parameter(
                "target_qty_when_long",
                "number",
                "First-leg target quantity.",
                1.0,
                minimum=0.0,
            ),
            _parameter(
                "lookback_period", "integer", "Spread lookback period.", 60, minimum=2
            ),
            _parameter(
                "entry_zscore", "number", "Entry z-score magnitude.", 2.0, minimum=0.0
            ),
            _parameter(
                "exit_zscore", "number", "Exit z-score magnitude.", 0.5, minimum=0.0
            ),
            _parameter(
                "hedge_ratio",
                "number",
                "Second-leg hedge ratio.",
                1.0,
                minimum=0.000001,
            ),
            _parameter(
                "max_pairs", "integer", "Maximum active disjoint pairs.", 1, minimum=1
            ),
            _parameter(
                "pair_mode",
                "string",
                "Deterministic pairing mode.",
                "disjoint_sorted",
                allowed_values=["disjoint_sorted"],
            ),
        ),
    ),
)


def _risk_template(
    template_id: str,
    display_name: str,
    description: str,
    entrypoint: str,
    parameters: tuple[ImplementationTemplateParameter, ...] = (),
    *,
    required_context: tuple[str, ...] = (),
    rejection_reason: str,
) -> MaintainedImplementationTemplate:
    return MaintainedImplementationTemplate(
        template_id=template_id,
        implementation_kind="risk_manager",
        display_name=display_name,
        description=description,
        runtime_contract=RISK_MANAGER_RUNTIME_CONTRACT,
        maintained_entrypoint=entrypoint,
        parameters=parameters,
        runtime_context=required_context,
        behavior={"decision": "order_filter", "rejection_reason": rejection_reason},
    )


_RISK_MANAGER_TEMPLATES = (
    _risk_template(
        "halt",
        "Halt Guard",
        "Rejects all orders while the runtime halt flag is active.",
        "trader_standard.risk:HaltRiskManager",
        required_context=("halted",),
        rejection_reason="halted",
    ),
    _risk_template(
        "max_orders_per_run",
        "Maximum Orders Per Run",
        "Limits the number of orders approved in one evaluation.",
        "trader_standard.risk:MaxOrdersPerRunRiskManager",
        (
            ImplementationTemplateParameter(
                "limit",
                "integer",
                "Maximum approved orders.",
                True,
                constraints={"minimum": 0},
            ),
        ),
        rejection_reason="max_orders_per_run",
    ),
    _risk_template(
        "max_gross_exposure",
        "Maximum Gross Exposure",
        "Limits projected aggregate gross USD exposure.",
        "trader_standard.risk:MaxGrossExposureRiskManager",
        (
            ImplementationTemplateParameter(
                "limit_usd",
                "number",
                "Gross exposure cap in USD.",
                True,
                constraints={"minimum": 0.0},
            ),
        ),
        required_context=("positions", "price_lookup"),
        rejection_reason="max_gross_usd",
    ),
    _risk_template(
        "max_position_usd_per_symbol",
        "Maximum Position Per Symbol",
        "Limits projected absolute USD exposure for each symbol.",
        "trader_standard.risk:MaxPositionUsdPerSymbolRiskManager",
        (
            ImplementationTemplateParameter(
                "limit_usd",
                "number",
                "Per-symbol exposure cap in USD.",
                True,
                constraints={"minimum": 0.0},
            ),
        ),
        required_context=("positions", "price_lookup"),
        rejection_reason="max_pos_usd_per_symbol",
    ),
    _risk_template(
        "open_buy_order_limit",
        "Open Buy Order Limit",
        "Limits concurrent open buy orders per symbol.",
        "trader_standard.risk:OpenBuyOrderLimitRiskManager",
        (
            _parameter(
                "max_open_buy_orders_per_symbol",
                "integer",
                "Maximum open buys per symbol.",
                1,
                minimum=1,
            ),
        ),
        required_context=("open_orders",),
        rejection_reason="open_buy_order_exists",
    ),
)

SUPPORTED_STRATEGY_FAMILIES = tuple(item.template_id for item in _STRATEGY_TEMPLATES)
SUPPORTED_RISK_MANAGER_FAMILIES = tuple(
    item.template_id for item in _RISK_MANAGER_TEMPLATES
)


def list_strategy_templates(*, families: Sequence[str] | None = None) -> ApplicationResult:
    """List maintained strategy templates in catalog order.

    Optional family IDs are normalized and validated; unsupported requests return
    a structured failure rather than a partial list. No implementation is registered.
    """
    return _list_templates(
        command=RESEARCH_LIST_STRATEGY_TEMPLATES,
        requested=families,
        supported=SUPPORTED_STRATEGY_FAMILIES,
        catalog=_STRATEGY_TEMPLATES,
        data_key="supported_strategy_families",
        error_code="unsupported_strategy_template",
    )


def list_risk_manager_templates(
    *, families: Sequence[str] | None = None
) -> ApplicationResult:
    """List maintained risk-manager templates in catalog order.

    Optional family IDs are normalized and validated; unsupported requests return
    a structured failure rather than a partial list. No implementation is registered.
    """
    return _list_templates(
        command=RESEARCH_LIST_RISK_MANAGER_TEMPLATES,
        requested=families,
        supported=SUPPORTED_RISK_MANAGER_FAMILIES,
        catalog=_RISK_MANAGER_TEMPLATES,
        data_key="supported_risk_manager_families",
        error_code="unsupported_risk_manager_template",
    )


def normalize_strategy_family(value: str) -> str:
    """Normalize and validate one maintained strategy template identifier.

    Case and hyphens are canonicalized; unknown identifiers raise ``ValueError``
    instead of being treated as dynamic strategy families.
    """
    return _normalize_template_id(value, SUPPORTED_STRATEGY_FAMILIES)


def _normalize_template_id(value: str, supported: tuple[str, ...]) -> str:
    normalized = str(value).strip().lower().replace("-", "_")
    if normalized not in supported:
        raise ValueError(f"unsupported maintained implementation template: {value}")
    return normalized


def _list_templates(
    *,
    command: str,
    requested: Sequence[str] | None,
    supported: tuple[str, ...],
    catalog: tuple[MaintainedImplementationTemplate, ...],
    data_key: str,
    error_code: str,
) -> ApplicationResult:
    try:
        selected = (
            supported
            if requested is None
            else tuple(
                dict.fromkeys(
                    _normalize_template_id(item, supported) for item in requested
                )
            )
        )
        if not selected:
            raise ValueError(
                "at least one maintained implementation template is required"
            )
    except ValueError as exc:
        return error_result(
            command=command,
            code=error_code,
            message=str(exc),
            data={data_key: list(supported)},
        )
    by_id = {item.template_id: item for item in catalog}
    templates = [by_id[item] for item in selected]
    return success_result(
        command=command,
        data={
            "templates": [item.to_dict() for item in templates],
            "template_count": len(templates),
            data_key: list(supported),
        },
    )
