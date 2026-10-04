"""Catalogue discovery and side-effect-free backtest preflight services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Mapping

from trader_standard.catalogue import (
    Catalogue,
    CatalogueValidationError,
    ProfileDefinition,
    canonicalize_datetime,
    fingerprint_definition,
    normalize_asset_class,
    normalize_symbols,
    normalize_timeframe,
    maintained_catalogue,
)

from ..contracts import (
    BacktestCatalogueResponse,
    BacktestCoverageCheck,
    BacktestDefinition,
    BacktestPreflightRequest,
    BacktestPreflightResponse,
    CatalogueParameter,
    CatalogueProfile,
    PreflightIssue,
)
from ..repositories.database import ConsoleDatabaseUnavailable
from ..repositories.resources import ConsoleResourceRepository


CatalogueDatabaseUnavailable = ConsoleDatabaseUnavailable


class CatalogueService:
    """Expose immutable allowlisted profile metadata."""

    def __init__(self, catalogue: Catalogue) -> None:
        """Bind a catalogue snapshot to the service."""
        self._catalogue = catalogue

    @classmethod
    def default(cls) -> "CatalogueService":
        """Build the current maintained catalogue snapshot."""
        return cls(maintained_catalogue())

    def describe(self) -> BacktestCatalogueResponse:
        """Return the typed strategy and risk profile catalogue."""
        return BacktestCatalogueResponse(
            catalogue_version=self._catalogue.version,
            strategy_profiles=tuple(_profile(item) for item in self._catalogue.strategies),
            risk_profiles=tuple(_profile(item) for item in self._catalogue.risks),
        )


class PreflightService:
    """Normalize and validate definitions before persistence or execution."""

    def __init__(self, repository: ConsoleResourceRepository, catalogue: Catalogue) -> None:
        """Bind read-only coverage access and an immutable catalogue snapshot."""
        self._repository = repository
        self._catalogue = catalogue

    @classmethod
    def default(cls, repository: ConsoleResourceRepository) -> "PreflightService":
        """Bind the current maintained catalogue to a resource repository."""
        return cls(repository, maintained_catalogue())

    async def preflight(self, request: BacktestPreflightRequest) -> BacktestPreflightResponse:
        """Return normalized definition, coverage, and field-level issues."""
        issues: list[PreflightIssue] = []
        normalized_symbols: tuple[str, ...] | None = None
        asset_class: str | None = None
        timeframe: str | None = None
        start: datetime | None = None
        end: datetime | None = None
        strategy: ProfileDefinition | None = None
        risk: ProfileDefinition | None = None
        strategy_parameters: dict[str, object] = {}
        risk_parameters: dict[str, object] = {}

        try:
            normalized_symbols = normalize_symbols(request.symbols)
        except CatalogueValidationError as exc:
            issues.append(_error("symbols", "invalid_symbols", str(exc)))
        try:
            asset_class = normalize_asset_class(request.asset_class)
        except CatalogueValidationError as exc:
            issues.append(_error("asset_class", "unsupported_asset_class", str(exc)))
        try:
            timeframe = normalize_timeframe(request.timeframe)
        except CatalogueValidationError as exc:
            issues.append(_error("timeframe", "unsupported_timeframe", str(exc)))
        try:
            start = canonicalize_datetime(request.start, field_name="start")
            end = canonicalize_datetime(request.end, field_name="end")
            if end <= start:
                issues.append(_error("end", "invalid_window", "end must be after start"))
            elif end - start > timedelta(days=365):
                issues.append(_error("end", "window_too_large", "Replay windows are limited to 365 days"))
        except CatalogueValidationError as exc:
            issues.append(_error("start", "invalid_timestamp", str(exc)))

        try:
            strategy = self._catalogue.get(
                "strategy", request.strategy_profile_id, request.strategy_catalogue_version
            )
        except CatalogueValidationError as exc:
            issues.append(_error("strategy_profile_id", "unsupported_strategy_profile", str(exc)))
        try:
            risk = self._catalogue.get(
                "risk", request.risk_profile_id, request.risk_catalogue_version
            )
        except CatalogueValidationError as exc:
            issues.append(_error("risk_profile_id", "unsupported_risk_profile", str(exc)))

        if strategy is not None:
            try:
                strategy_parameters = self._catalogue.normalize_parameters(
                    "strategy",
                    strategy.profile_id,
                    request.strategy_parameters,
                    version=strategy.version,
                )
            except CatalogueValidationError as exc:
                issues.append(_error("strategy_parameters", "invalid_strategy_parameters", str(exc)))
        if risk is not None:
            try:
                risk_parameters = self._catalogue.normalize_parameters(
                    "risk",
                    risk.profile_id,
                    request.risk_parameters,
                    version=risk.version,
                )
            except CatalogueValidationError as exc:
                issues.append(_error("risk_parameters", "invalid_risk_parameters", str(exc)))

        if asset_class is not None and strategy is not None and asset_class not in strategy.supported_asset_classes:
            issues.append(_error("asset_class", "strategy_asset_class_unsupported", f"{strategy.profile_id} does not support {asset_class}"))
        if timeframe is not None and strategy is not None and timeframe not in strategy.supported_timeframes:
            issues.append(_error("timeframe", "strategy_timeframe_unsupported", f"{strategy.profile_id} does not support {timeframe}"))
        if asset_class is not None and risk is not None and asset_class not in risk.supported_asset_classes:
            issues.append(_error("asset_class", "risk_asset_class_unsupported", f"{risk.profile_id} does not support {asset_class}"))
        if timeframe is not None and risk is not None and timeframe not in risk.supported_timeframes:
            issues.append(_error("timeframe", "risk_timeframe_unsupported", f"{risk.profile_id} does not support {timeframe}"))

        if normalized_symbols is not None:
            configured = set(normalized_symbols)
            for position in request.initial_positions:
                try:
                    position_symbol = normalize_symbols((position.symbol,))[0]
                except CatalogueValidationError as exc:
                    issues.append(_error("initial_positions", "invalid_initial_position_symbol", str(exc)))
                    continue
                if position_symbol not in configured:
                    issues.append(_error("initial_positions", "initial_position_outside_scope", f"{position_symbol} is not in symbols"))
                if not math.isfinite(position.qty):
                    issues.append(_error("initial_positions", "invalid_initial_position_qty", f"{position_symbol} qty must be finite"))

        lookback_bars = _lookback_bars(strategy, strategy_parameters)
        coverage: list[BacktestCoverageCheck] = []
        normalized_definition: BacktestDefinition | None = None
        if not any(issue.severity == "error" for issue in issues) and all(
            value is not None for value in (normalized_symbols, asset_class, timeframe, start, end, strategy, risk)
        ):
            assert normalized_symbols is not None
            assert asset_class is not None
            assert timeframe is not None
            assert start is not None
            assert end is not None
            assert strategy is not None
            assert risk is not None
            normalized_definition = BacktestDefinition(
                display_name=request.display_name.strip(),
                strategy_profile_id=strategy.profile_id,
                strategy_catalogue_version=strategy.version,
                strategy_parameters=strategy_parameters,
                risk_profile_id=risk.profile_id,
                risk_catalogue_version=risk.version,
                risk_parameters=risk_parameters,
                asset_class=asset_class,
                symbols=normalized_symbols,
                timeframe=timeframe,
                start=start,
                end=end,
                initial_cash=request.initial_cash,
                initial_positions=tuple(
                    position.model_copy(update={"symbol": normalize_symbols((position.symbol,))[0]})
                    for position in request.initial_positions
                ),
                assumptions=request.assumptions,
                benchmark_id=request.benchmark_id,
                resource_limits=request.resource_limits,
            )
            if request.assumptions.allow_price_carry_forward:
                issues.append(
                    _warning(
                        "assumptions.allow_price_carry_forward",
                        "price_carry_forward_enabled",
                        "Missing marks may use the latest prior bar during replay valuation",
                    )
                )
            estimated_cycles = _estimate_cycles(start, end, timeframe, len(normalized_symbols))
            if estimated_cycles > request.resource_limits.max_cycles:
                issues.append(_error("resource_limits.max_cycles", "cycle_budget_exceeded", f"Estimated cycles {estimated_cycles} exceed the configured limit"))
            estimated_bars = estimated_cycles + lookback_bars * len(normalized_symbols)
            if estimated_bars > request.resource_limits.max_bars:
                issues.append(_error("resource_limits.max_bars", "bar_budget_exceeded", f"Estimated bars {estimated_bars} exceed the configured limit"))
            coverage_rows = await self._repository.backtest_coverage(
                asset_class=asset_class,
                symbols=normalized_symbols,
                timeframe=timeframe,
            )
            required_start = start - _timeframe_delta(timeframe) * lookback_bars
            for row in coverage_rows:
                first_ts = _as_utc(row.get("first_ts"))
                last_ts = _as_utc(row.get("last_ts"))
                available = first_ts is not None and last_ts is not None and last_ts >= start
                warmup_satisfied = available and first_ts <= required_start
                coverage.append(
                    BacktestCoverageCheck(
                        symbol=str(row["symbol"]),
                        asset_class=asset_class,
                        timeframe=timeframe,
                        first_ts=first_ts,
                        last_ts=last_ts,
                        bar_count=int(row.get("bar_count", 0) or 0),
                        required_start=required_start,
                        requested_end=end,
                        warmup_bars=lookback_bars,
                        available=available,
                        warmup_satisfied=warmup_satisfied,
                    )
                )
                if not available:
                    issues.append(_error(f"coverage.{row['symbol']}", "data_coverage_missing", "No bars cover the requested replay window"))
                else:
                    if last_ts is not None and last_ts < end:
                        issues.append(_error(f"coverage.{row['symbol']}", "data_coverage_incomplete", "Bars do not reach the requested end"))
                    if not warmup_satisfied:
                        issues.append(_error(f"coverage.{row['symbol']}", "warmup_unavailable", f"At least {lookback_bars} warmup bars are required"))

            if not coverage:
                issues.append(_error("coverage", "data_coverage_missing", "No coverage rows were returned"))

        definition_fingerprint = (
            fingerprint_definition(normalized_definition.model_dump(mode="json"))
            if normalized_definition is not None
            else None
        )
        return BacktestPreflightResponse(
            valid=not any(issue.severity == "error" for issue in issues),
            catalogue_version=self._catalogue.version,
            definition_fingerprint=definition_fingerprint,
            normalized_definition=normalized_definition,
            coverage=tuple(coverage),
            issues=tuple(issues),
        )


def _profile(profile: ProfileDefinition) -> CatalogueProfile:
    return CatalogueProfile(
        kind=profile.kind,
        profile_id=profile.profile_id,
        version=profile.version,
        name=profile.name,
        description=profile.description,
        parameters=tuple(CatalogueParameter.model_validate(item.to_record()) for item in profile.parameters),
        supported_asset_classes=profile.supported_asset_classes,
        supported_timeframes=profile.supported_timeframes,
        lookback_bars=profile.lookback_bars,
        evidence_requirements=profile.evidence_requirements,
        manager_ids=profile.manager_ids,
        reason_codes=profile.reason_codes,
    )


def _error(path: str, code: str, message: str) -> PreflightIssue:
    return PreflightIssue(severity="error", code=code, path=path, message=message)


def _warning(path: str, code: str, message: str) -> PreflightIssue:
    return PreflightIssue(severity="warning", code=code, path=path, message=message)


def _lookback_bars(profile: ProfileDefinition | None, parameters: Mapping[str, object]) -> int:
    if profile is None:
        return 0
    if profile.profile_id == "bollinger_band":
        return int(parameters.get("period", profile.lookback_bars - 1)) + 1
    return profile.lookback_bars


def _timeframe_delta(timeframe: str) -> timedelta:
    return {"1Min": timedelta(minutes=1), "1Hour": timedelta(hours=1), "1Day": timedelta(days=1)}[timeframe]


def _estimate_cycles(start: datetime, end: datetime, timeframe: str, symbol_count: int) -> int:
    periods = math.ceil((end - start) / _timeframe_delta(timeframe))
    return max(1, periods) * symbol_count


def _as_utc(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


__all__ = ["CatalogueDatabaseUnavailable", "CatalogueService", "PreflightService"]
