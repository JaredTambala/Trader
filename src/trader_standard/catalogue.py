"""Allowlisted strategy and risk profiles for typed Console definitions.

The catalogue is deliberately explicit: resolving a profile selects one of the
maintained builders below and never imports a caller-provided module or callable.
Normalization is pure so the Console preflight boundary can validate and hash a
definition before it touches persistence or execution state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import re
from typing import Literal, Mapping, Sequence

from trader.risk import RiskManager

from .risk import (
    MaxOrdersPerRunRiskManager,
    MaxPositionUsdPerSymbolRiskManager,
    NoOpRiskManager,
)
from .strategies import NoOpStrategy, build_bollinger_band_strategy


ParameterType = Literal["integer", "number", "boolean", "string"]
ProfileKind = Literal["strategy", "risk"]


class CatalogueValidationError(ValueError):
    """Raised when a profile or typed parameter payload is not supported."""


@dataclass(frozen=True)
class ParameterDefinition:
    """One allowlisted typed parameter and its public bounds."""

    name: str
    value_type: ParameterType
    default: object | None = None
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    description: str | None = None

    def to_record(self) -> dict[str, object]:
        """Return the stable public parameter schema shape."""
        return {
            "name": self.name,
            "type": self.value_type,
            "default": self.default,
            "required": self.required,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "description": self.description,
        }


@dataclass(frozen=True)
class ProfileDefinition:
    """Allowlisted strategy or risk profile metadata and resolver identity."""

    kind: ProfileKind
    profile_id: str
    version: str
    name: str
    description: str
    parameters: tuple[ParameterDefinition, ...]
    supported_asset_classes: tuple[str, ...]
    supported_timeframes: tuple[str, ...]
    lookback_bars: int
    evidence_requirements: tuple[str, ...]
    manager_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def to_record(self) -> dict[str, object]:
        """Return a JSON-safe catalogue entry."""
        return {
            "kind": self.kind,
            "profile_id": self.profile_id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "parameters": [parameter.to_record() for parameter in self.parameters],
            "supported_asset_classes": list(self.supported_asset_classes),
            "supported_timeframes": list(self.supported_timeframes),
            "lookback_bars": self.lookback_bars,
            "evidence_requirements": list(self.evidence_requirements),
            "manager_ids": list(self.manager_ids),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class Catalogue:
    """Immutable collection of supported profiles and their catalogue version."""

    version: str
    strategies: tuple[ProfileDefinition, ...]
    risks: tuple[ProfileDefinition, ...]

    def all_profiles(self) -> tuple[ProfileDefinition, ...]:
        """Return strategy profiles followed by risk profiles in stable order."""
        return self.strategies + self.risks

    def get(self, kind: ProfileKind, profile_id: str, version: str | None = None) -> ProfileDefinition:
        """Resolve one exact profile identity or raise a validation error."""
        profiles = self.strategies if kind == "strategy" else self.risks
        profile = next((item for item in profiles if item.profile_id == profile_id), None)
        if profile is None:
            raise CatalogueValidationError(f"Unknown {kind} profile: {profile_id}")
        if version is not None and version != profile.version:
            raise CatalogueValidationError(
                f"Unsupported {kind} profile version for {profile_id}: {version}"
            )
        return profile

    def normalize_parameters(
        self,
        kind: ProfileKind,
        profile_id: str,
        parameters: Mapping[str, object] | None,
        *,
        version: str | None = None,
    ) -> dict[str, object]:
        """Validate and normalize typed profile parameters without side effects."""
        profile = self.get(kind, profile_id, version)
        supplied = dict(parameters or {})
        definitions = {parameter.name: parameter for parameter in profile.parameters}
        unknown = sorted(set(supplied) - set(definitions))
        if unknown:
            raise CatalogueValidationError(
                f"Unknown parameters for {kind}.{profile_id}: {', '.join(unknown)}"
            )
        normalized: dict[str, object] = {}
        for parameter in profile.parameters:
            if parameter.name not in supplied:
                if parameter.required and parameter.default is None:
                    raise CatalogueValidationError(
                        f"Missing required parameter: {kind}.{profile_id}.{parameter.name}"
                    )
                if parameter.default is not None:
                    normalized[parameter.name] = parameter.default
                continue
            normalized[parameter.name] = _normalize_parameter(parameter, supplied[parameter.name])
        return normalized

    def build_strategy(
        self,
        profile_id: str,
        *,
        version: str | None,
        parameters: Mapping[str, object] | None,
        symbols: Sequence[str],
        asset_class: str,
        timeframe: str,
    ) -> object:
        """Build a maintained strategy through an explicit profile allowlist."""
        normalized = self.normalize_parameters("strategy", profile_id, parameters, version=version)
        profile = self.get("strategy", profile_id, version)
        if asset_class not in profile.supported_asset_classes:
            raise CatalogueValidationError(f"Unsupported asset class for {profile_id}: {asset_class}")
        if timeframe not in profile.supported_timeframes:
            raise CatalogueValidationError(f"Unsupported timeframe for {profile_id}: {timeframe}")
        if profile_id == "noop":
            return NoOpStrategy()
        if profile_id == "bollinger_band":
            return build_bollinger_band_strategy(
                symbols=tuple(symbols),
                asset_class=asset_class,
                timeframe=timeframe,
                target_qty_when_long=float(normalized["target_qty_when_long"]),
                period=int(normalized["period"]),
                stddev_multiplier=float(normalized["stddev_multiplier"]),
            )
        raise CatalogueValidationError(f"No resolver registered for strategy profile: {profile_id}")

    def build_risk_manager(
        self,
        profile_id: str,
        *,
        version: str | None,
        parameters: Mapping[str, object] | None,
    ) -> RiskManager:
        """Build a maintained risk manager through an explicit profile allowlist."""
        normalized = self.normalize_parameters("risk", profile_id, parameters, version=version)
        if profile_id == "noop":
            return NoOpRiskManager()
        if profile_id == "max_orders_per_run":
            return MaxOrdersPerRunRiskManager(limit=int(normalized["limit"]))
        if profile_id == "max_position_usd_per_symbol":
            return MaxPositionUsdPerSymbolRiskManager(limit_usd=float(normalized["limit_usd"]))
        raise CatalogueValidationError(f"No resolver registered for risk profile: {profile_id}")


def maintained_catalogue() -> Catalogue:
    """Return the current immutable maintained profile catalogue."""
    return Catalogue(
        version="standard-1",
        strategies=(
            ProfileDefinition(
                kind="strategy",
                profile_id="noop",
                version="standard-1",
                name="No-op strategy",
                description="Emit no candidate orders while preserving replay evidence.",
                parameters=(),
                supported_asset_classes=("stock", "crypto"),
                supported_timeframes=("1Min", "1Hour", "1Day"),
                lookback_bars=0,
                evidence_requirements=("signals", "orders", "fills", "positions"),
            ),
            ProfileDefinition(
                kind="strategy",
                profile_id="bollinger_band",
                version="standard-1",
                name="Bollinger Band re-entry",
                description="Maintained long/flat Bollinger lower-band re-entry strategy.",
                parameters=(
                    ParameterDefinition(
                        "period", "integer", default=20, minimum=2, maximum=500,
                        description="Rolling Bollinger window in bars.",
                    ),
                    ParameterDefinition(
                        "stddev_multiplier", "number", default=2.0, minimum=0.1, maximum=10.0,
                        description="Bollinger standard-deviation multiplier.",
                    ),
                    ParameterDefinition(
                        "target_qty_when_long", "number", default=1.0, minimum=0.00000001, maximum=1_000_000.0,
                        description="Target quantity emitted for a long entry.",
                    ),
                ),
                supported_asset_classes=("stock", "crypto"),
                supported_timeframes=("1Min", "1Hour", "1Day"),
                lookback_bars=21,
                evidence_requirements=("signals", "indicators", "orders", "fills", "positions"),
            ),
        ),
        risks=(
            ProfileDefinition(
                kind="risk",
                profile_id="noop",
                version="standard-1",
                name="No-op risk",
                description="Approve every candidate order without changing it.",
                parameters=(),
                supported_asset_classes=("stock", "crypto"),
                supported_timeframes=("1Min", "1Hour", "1Day"),
                lookback_bars=0,
                evidence_requirements=("orders", "risk_composition", "risk_decisions"),
                manager_ids=("noop",),
                reason_codes=("approved",),
            ),
            ProfileDefinition(
                kind="risk",
                profile_id="max_orders_per_run",
                version="standard-1",
                name="Maximum orders per run",
                description="Block orders after a configured per-run order limit.",
                parameters=(
                    ParameterDefinition(
                        "limit", "integer", default=100, minimum=0, maximum=1_000_000,
                        description="Maximum number of candidate orders allowed per evaluation.",
                    ),
                ),
                supported_asset_classes=("stock", "crypto"),
                supported_timeframes=("1Min", "1Hour", "1Day"),
                lookback_bars=0,
                evidence_requirements=("orders", "risk_composition", "risk_decisions"),
                manager_ids=("max_orders_per_run",),
                reason_codes=("approved", "max_orders_per_run"),
            ),
            ProfileDefinition(
                kind="risk",
                profile_id="max_position_usd_per_symbol",
                version="standard-1",
                name="Maximum position value per symbol",
                description="Block orders that exceed a symbol-level USD position bound.",
                parameters=(
                    ParameterDefinition(
                        "limit_usd", "number", default=100_000.0, minimum=0.01, maximum=1_000_000_000.0,
                        description="Maximum absolute position value for one symbol.",
                    ),
                ),
                supported_asset_classes=("stock", "crypto"),
                supported_timeframes=("1Min", "1Hour", "1Day"),
                lookback_bars=0,
                evidence_requirements=("orders", "risk_composition", "risk_decisions"),
                manager_ids=("max_position_usd_per_symbol",),
                reason_codes=("approved", "max_pos_usd_per_symbol", "missing_price"),
            ),
        ),
    )


def normalize_symbols(symbols: Sequence[object]) -> tuple[str, ...]:
    """Normalize and validate a bounded symbol list for a definition."""
    normalized: list[str] = []
    for raw in symbols:
        symbol = str(raw).strip().upper()
        if not symbol or not re.fullmatch(r"[A-Z0-9][A-Z0-9._/-]{0,31}", symbol):
            raise CatalogueValidationError(f"Invalid symbol: {raw!r}")
        if symbol not in normalized:
            normalized.append(symbol)
    if not normalized:
        raise CatalogueValidationError("At least one symbol is required")
    if len(normalized) > 50:
        raise CatalogueValidationError("At most 50 symbols are supported")
    return tuple(normalized)


def normalize_asset_class(value: str) -> str:
    """Normalize common asset-class spellings to the Console contract."""
    normalized = value.strip().lower()
    aliases = {"stocks": "stock", "stock": "stock", "crypto": "crypto", "cryptocurrency": "crypto"}
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise CatalogueValidationError(f"Unsupported asset class: {value}") from exc


def normalize_timeframe(value: str) -> str:
    """Normalize supported timeframe aliases to persisted bar labels."""
    compact = re.sub(r"[ _-]", "", value.strip().lower())
    aliases = {
        "1m": "1Min", "1min": "1Min", "1minute": "1Min",
        "1h": "1Hour", "1hr": "1Hour", "1hour": "1Hour",
        "1d": "1Day", "1day": "1Day",
    }
    try:
        return aliases[compact]
    except KeyError as exc:
        raise CatalogueValidationError(f"Unsupported timeframe: {value}") from exc


def canonicalize_datetime(value: datetime, *, field_name: str) -> datetime:
    """Require a timezone-aware timestamp and normalize it to UTC."""
    from datetime import timezone

    if value.tzinfo is None or value.utcoffset() is None:
        raise CatalogueValidationError(f"{field_name} must include a timezone")
    return value.astimezone(timezone.utc)


def fingerprint_definition(value: Mapping[str, object]) -> str:
    """Return a deterministic SHA-256 fingerprint for normalized definition data."""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_parameter(definition: ParameterDefinition, value: object) -> object:
    if definition.value_type == "boolean":
        if not isinstance(value, bool):
            raise CatalogueValidationError(f"{definition.name} must be a boolean")
        normalized: object = value
    elif definition.value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise CatalogueValidationError(f"{definition.name} must be an integer")
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise CatalogueValidationError(f"{definition.name} must be an integer") from exc
        if isinstance(value, float) and not value.is_integer():
            raise CatalogueValidationError(f"{definition.name} must be an integer")
    elif definition.value_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise CatalogueValidationError(f"{definition.name} must be a number")
        try:
            normalized = float(value)
        except (TypeError, ValueError) as exc:
            raise CatalogueValidationError(f"{definition.name} must be a number") from exc
        if not math.isfinite(normalized):
            raise CatalogueValidationError(f"{definition.name} must be finite")
    else:
        if not isinstance(value, str):
            raise CatalogueValidationError(f"{definition.name} must be a string")
        normalized = value.strip()
        if not normalized:
            raise CatalogueValidationError(f"{definition.name} must not be blank")
    if isinstance(normalized, (int, float)):
        if definition.minimum is not None and normalized < definition.minimum:
            raise CatalogueValidationError(f"{definition.name} must be at least {definition.minimum}")
        if definition.maximum is not None and normalized > definition.maximum:
            raise CatalogueValidationError(f"{definition.name} must be at most {definition.maximum}")
    return normalized


__all__ = [
    "Catalogue",
    "CatalogueValidationError",
    "ParameterDefinition",
    "ProfileDefinition",
    "canonicalize_datetime",
    "fingerprint_definition",
    "maintained_catalogue",
    "normalize_asset_class",
    "normalize_symbols",
    "normalize_timeframe",
]
