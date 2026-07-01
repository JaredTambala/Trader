"""Strategy candidate schemas and maintained template catalog services.

The strategy catalog is deliberately declarative. It exposes the maintained
strategy families that later candidate-building tools may use, while avoiding
dynamic imports or arbitrary executable strategy code at discovery time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope


RESEARCH_LIST_STRATEGY_TEMPLATES = "research_list_strategy_templates"
METHOD_PACKAGE_MANIFEST = "method_package_manifest"
SUPPORTED_STRATEGY_FAMILIES = ("trend_following", "mean_reversion", "bollinger_band")


@dataclass(frozen=True)
class StrategyTemplateParameter:
    """JSON-safe parameter contract for a maintained strategy template.

    Attributes:
        name: Stable parameter name expected by the candidate builder.
        value_type: Human-readable JSON value type.
        description: Caller-facing explanation of how the parameter is used.
        required: Whether a candidate must provide the value explicitly.
        default: Optional default used by the maintained runtime builder.
        constraints: JSON-compatible validation hints for later candidate validation.
    """

    name: str
    value_type: str
    description: str
    required: bool = False
    default: Any | None = None
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate parameter identity and type labels before catalog publication."""
        if not self.name.strip():
            raise ValueError("strategy template parameter name is required")
        if not self.value_type.strip():
            raise ValueError("strategy template parameter value_type is required")
        if not self.description.strip():
            raise ValueError("strategy template parameter description is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the parameter contract into the catalog payload."""
        payload: dict[str, Any] = {
            "name": self.name,
            "value_type": self.value_type,
            "description": self.description,
            "required": self.required,
            "constraints": _jsonable(self.constraints),
        }
        if not self.required or self.default is not None:
            payload["default"] = _jsonable(self.default)
        return payload


@dataclass(frozen=True)
class StrategyTemplate:
    """Maintained strategy family metadata exposed to research supervisors.

    Attributes:
        template_family: Stable template identifier used by strategy candidates.
        display_name: Human-readable strategy family name.
        description: Brief explanation of the maintained strategy composition.
        runtime_builder_path: Import path string for the maintained runtime builder.
        runtime_strategy_id: Strategy identifier emitted by the runtime builder.
        parameters: Parameter contracts in deterministic output order.
        required_artifact_types: Artifact types expected before candidate creation.
        required_artifact_roles: Named signal/method package roles required by the family.
        entry_semantics: Declarative entry behavior for candidate manifests.
        exit_semantics: Declarative exit behavior for candidate manifests.
        sizing: Sizing assumptions exposed by the template.
        risk_assumptions: Risk and execution assumptions for v1 candidates.
        data_requirements: Declarative market-data requirements.
        constraints: Additional validation hints for later candidate tools.
    """

    template_family: str
    display_name: str
    description: str
    runtime_builder_path: str
    runtime_strategy_id: str
    parameters: tuple[StrategyTemplateParameter, ...]
    required_artifact_types: tuple[str, ...]
    required_artifact_roles: tuple[Mapping[str, Any], ...]
    entry_semantics: Mapping[str, Any]
    exit_semantics: Mapping[str, Any]
    sizing: Mapping[str, Any]
    risk_assumptions: Mapping[str, Any]
    data_requirements: Mapping[str, Any]
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate stable template identifiers and catalog parameter uniqueness."""
        if self.template_family not in SUPPORTED_STRATEGY_FAMILIES:
            raise ValueError(f"unsupported strategy template family: {self.template_family}")
        if not self.display_name.strip():
            raise ValueError("strategy template display_name is required")
        if not self.runtime_builder_path.strip():
            raise ValueError("strategy template runtime_builder_path is required")
        parameter_names = [parameter.name for parameter in self.parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError(f"duplicate parameter names for strategy template: {self.template_family}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize maintained template metadata for tool envelopes and docs."""
        return {
            "template_family": self.template_family,
            "display_name": self.display_name,
            "description": self.description,
            "runtime_builder_path": self.runtime_builder_path,
            "runtime_strategy_id": self.runtime_strategy_id,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "required_artifact_types": list(self.required_artifact_types),
            "required_artifact_roles": _jsonable(self.required_artifact_roles),
            "entry_semantics": _jsonable(self.entry_semantics),
            "exit_semantics": _jsonable(self.exit_semantics),
            "sizing": _jsonable(self.sizing),
            "risk_assumptions": _jsonable(self.risk_assumptions),
            "data_requirements": _jsonable(self.data_requirements),
            "constraints": _jsonable(self.constraints),
        }


def list_strategy_templates(*, families: Sequence[str] | None = None) -> ToolEnvelope:
    """Return maintained strategy templates in a standard research-tool envelope.

    Args:
        families: Optional strategy family filter. Family names are normalized by
            trimming whitespace, lowercasing, and converting hyphens to underscores.

    Returns:
        Read-only `ToolEnvelope` containing deterministic strategy template metadata.
        Unknown or empty requested families return a failed envelope.
    """
    try:
        requested_families = _normalize_requested_families(families)
        templates = [get_strategy_template(family) for family in requested_families]
    except ValueError as exc:
        return error_envelope(
            command=RESEARCH_LIST_STRATEGY_TEMPLATES,
            side_effect=SideEffect.READ_ONLY,
            code="unsupported_strategy_template",
            message=str(exc),
            data={"supported_strategy_families": list(SUPPORTED_STRATEGY_FAMILIES)},
        )

    return success_envelope(
        command=RESEARCH_LIST_STRATEGY_TEMPLATES,
        side_effect=SideEffect.READ_ONLY,
        data={
            "templates": [template.to_dict() for template in templates],
            "template_count": len(templates),
            "supported_strategy_families": list(SUPPORTED_STRATEGY_FAMILIES),
        },
    )


def get_strategy_template(family: str) -> StrategyTemplate:
    """Return one maintained strategy template by normalized family name.

    Args:
        family: Strategy family value supplied by a caller or suite config.

    Returns:
        Matching `StrategyTemplate`.

    Raises:
        ValueError: If the family is empty or unsupported.
    """
    normalized = normalize_strategy_family(family)
    return _TEMPLATE_BY_FAMILY[normalized]


def normalize_strategy_family(value: str) -> str:
    """Normalize and validate a maintained strategy family identifier.

    Args:
        value: Raw family text from a request or config file.

    Returns:
        Canonical family name.

    Raises:
        ValueError: If the normalized family is not cataloged.
    """
    family = str(value).strip().lower().replace("-", "_")
    if family not in SUPPORTED_STRATEGY_FAMILIES:
        raise ValueError(f"Unsupported strategy family: {value}")
    return family


def _normalize_requested_families(families: Sequence[str] | None) -> tuple[str, ...]:
    if families is None:
        return SUPPORTED_STRATEGY_FAMILIES
    normalized: list[str] = []
    for family in families:
        normalized_family = normalize_strategy_family(family)
        if normalized_family not in normalized:
            normalized.append(normalized_family)
    if not normalized:
        raise ValueError("At least one strategy family is required")
    return tuple(normalized)


def _shared_parameters() -> tuple[StrategyTemplateParameter, ...]:
    return (
        StrategyTemplateParameter(
            name="symbols",
            value_type="array[string]",
            description="Canonical symbol universe for the strategy candidate.",
            required=True,
            constraints={"min_items": 1, "max_items": 20},
        ),
        StrategyTemplateParameter(
            name="asset_class",
            value_type="string",
            description="Market-data asset class used to select the bar event table.",
            required=True,
            constraints={"allowed_values": ["stocks", "stock", "crypto", "cryptocurrency"]},
        ),
        StrategyTemplateParameter(
            name="timeframe",
            value_type="string",
            description="Bar timeframe consumed by the maintained runtime builder.",
            required=True,
            constraints={"examples": ["1Min", "5Min", "1Day"]},
        ),
        StrategyTemplateParameter(
            name="target_qty_when_long",
            value_type="number",
            description="Fixed quantity used when the long/flat template opens long exposure.",
            default=1.0,
            constraints={"minimum": 0.0},
        ),
    )


def _entry_semantics(*, signal_roles: Sequence[str], require_all: bool) -> dict[str, Any]:
    return {
        "position_model": "long_flat",
        "direction": "long_only",
        "order_type": "market",
        "signal_roles": list(signal_roles),
        "threshold": 0.0,
        "condition": "all_positive" if require_all else "any_positive",
    }


def _exit_semantics(*, signal_roles: Sequence[str], require_all: bool) -> dict[str, Any]:
    return {
        "position_model": "long_flat",
        "order_type": "market",
        "signal_roles": list(signal_roles),
        "threshold": 0.0,
        "condition": "all_negative" if require_all else "any_negative",
    }


def _required_artifact_roles(*roles: str) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        {
            "role": role,
            "artifact_type": METHOD_PACKAGE_MANIFEST,
            "runtime_contract": "trader.signals.Signal",
            "required": True,
        }
        for role in roles
    )


def _template_constraints() -> dict[str, Any]:
    return {
        "arbitrary_strategy_code_allowed": False,
        "shorting_allowed": False,
        "broker_mutation_allowed": False,
        "dynamic_stop_policy_configuration": False,
    }


def _sizing_contract() -> dict[str, Any]:
    return {
        "model": "fixed_quantity",
        "parameter": "target_qty_when_long",
        "default_target_qty_when_long": 1.0,
        "allows_short": False,
    }


def _risk_assumptions() -> dict[str, Any]:
    return {
        "position_direction": "long_only",
        "stop_policy": "not_exposed_in_v1_catalog",
        "order_type": "market",
        "portfolio_model": "single_target_quantity_per_symbol",
    }


def _data_requirements() -> dict[str, Any]:
    return {
        "market_data": "event_store_bars",
        "symbols_parameter": "symbols",
        "asset_class_parameter": "asset_class",
        "timeframe_parameter": "timeframe",
        "bar_order": "latest_first",
        "warmup": "max_signal_window",
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


TREND_FOLLOWING_TEMPLATE = StrategyTemplate(
    template_family="trend_following",
    display_name="Trend Following",
    description="Long/flat strategy that opens on EMA or MACD crossover strength and exits on bearish crossover state.",
    runtime_builder_path="trader_standard.strategies:build_trend_following_strategy",
    runtime_strategy_id="trend_following",
    parameters=_shared_parameters()
    + (
        StrategyTemplateParameter(
            name="ema_fast_period",
            value_type="integer",
            description="Fast EMA period for the crossover signal.",
            default=12,
            constraints={"minimum": 1},
        ),
        StrategyTemplateParameter(
            name="ema_slow_period",
            value_type="integer",
            description="Slow EMA period for the crossover signal.",
            default=26,
            constraints={"minimum": 2, "must_exceed": "ema_fast_period"},
        ),
        StrategyTemplateParameter(
            name="macd_fast_period",
            value_type="integer",
            description="Fast EMA period used inside MACD.",
            default=12,
            constraints={"minimum": 1},
        ),
        StrategyTemplateParameter(
            name="macd_slow_period",
            value_type="integer",
            description="Slow EMA period used inside MACD.",
            default=26,
            constraints={"minimum": 2, "must_exceed": "macd_fast_period"},
        ),
        StrategyTemplateParameter(
            name="macd_signal_period",
            value_type="integer",
            description="Signal-line EMA period used inside MACD.",
            default=9,
            constraints={"minimum": 1},
        ),
    ),
    required_artifact_types=(METHOD_PACKAGE_MANIFEST,),
    required_artifact_roles=_required_artifact_roles("ema_crossover_signal", "macd_crossover_signal"),
    entry_semantics=_entry_semantics(signal_roles=("ema_crossover_signal", "macd_crossover_signal"), require_all=False),
    exit_semantics=_exit_semantics(signal_roles=("ema_crossover_signal", "macd_crossover_signal"), require_all=False),
    sizing=_sizing_contract(),
    risk_assumptions=_risk_assumptions(),
    data_requirements=_data_requirements(),
    constraints=_template_constraints(),
)

MEAN_REVERSION_TEMPLATE = StrategyTemplate(
    template_family="mean_reversion",
    display_name="Mean Reversion",
    description="Long/flat strategy that enters on oversold RSI plus downside SMA stretch and exits on recovery.",
    runtime_builder_path="trader_standard.strategies:build_mean_reversion_strategy",
    runtime_strategy_id="mean_reversion",
    parameters=_shared_parameters()
    + (
        StrategyTemplateParameter(
            name="rsi_period",
            value_type="integer",
            description="RSI period used for entry and recovery signals.",
            default=14,
            constraints={"minimum": 1},
        ),
        StrategyTemplateParameter(
            name="oversold",
            value_type="number",
            description="RSI threshold below which the entry signal is considered oversold.",
            default=30.0,
            constraints={"minimum": 0.0, "maximum": 100.0},
        ),
        StrategyTemplateParameter(
            name="exit_rsi",
            value_type="number",
            description="RSI threshold used to identify recovery exits.",
            default=50.0,
            constraints={"minimum": 0.0, "maximum": 100.0},
        ),
        StrategyTemplateParameter(
            name="mean_period",
            value_type="integer",
            description="SMA period used for the downside stretch signal.",
            default=20,
            constraints={"minimum": 1},
        ),
        StrategyTemplateParameter(
            name="stretch_pct",
            value_type="number",
            description="Minimum percentage below the SMA required for stretch entry.",
            default=0.02,
            constraints={"minimum": 0.0},
        ),
    ),
    required_artifact_types=(METHOD_PACKAGE_MANIFEST,),
    required_artifact_roles=_required_artifact_roles(
        "rsi_threshold_signal",
        "rsi_recovery_signal",
        "sma_stretch_signal",
    ),
    entry_semantics=_entry_semantics(signal_roles=("rsi_threshold_signal", "sma_stretch_signal"), require_all=True),
    exit_semantics=_exit_semantics(signal_roles=("rsi_recovery_signal", "sma_stretch_signal"), require_all=False),
    sizing=_sizing_contract(),
    risk_assumptions=_risk_assumptions(),
    data_requirements=_data_requirements(),
    constraints=_template_constraints(),
)

BOLLINGER_BAND_TEMPLATE = StrategyTemplate(
    template_family="bollinger_band",
    display_name="Bollinger Band",
    description="Long/flat strategy that opens on lower-band re-entry and exits on middle-band reversion.",
    runtime_builder_path="trader_standard.strategies:build_bollinger_band_strategy",
    runtime_strategy_id="bollinger_band",
    parameters=_shared_parameters()
    + (
        StrategyTemplateParameter(
            name="period",
            value_type="integer",
            description="Rolling period used for Bollinger Bands.",
            default=20,
            constraints={"minimum": 1},
        ),
        StrategyTemplateParameter(
            name="stddev_multiplier",
            value_type="number",
            description="Standard-deviation multiplier applied to the rolling band width.",
            default=2.0,
            constraints={"minimum": 0.0},
        ),
    ),
    required_artifact_types=(METHOD_PACKAGE_MANIFEST,),
    required_artifact_roles=_required_artifact_roles("bollinger_band_signal"),
    entry_semantics=_entry_semantics(signal_roles=("bollinger_band_signal",), require_all=True),
    exit_semantics=_exit_semantics(signal_roles=("bollinger_band_signal",), require_all=True),
    sizing=_sizing_contract(),
    risk_assumptions=_risk_assumptions(),
    data_requirements=_data_requirements(),
    constraints=_template_constraints(),
)

STRATEGY_TEMPLATE_CATALOG = (
    TREND_FOLLOWING_TEMPLATE,
    MEAN_REVERSION_TEMPLATE,
    BOLLINGER_BAND_TEMPLATE,
)
_TEMPLATE_BY_FAMILY = {template.template_family: template for template in STRATEGY_TEMPLATE_CATALOG}

