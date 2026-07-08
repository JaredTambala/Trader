"""Strategy candidate validation for supervisor-owned research tools."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader.event_store import EventStore
from trader.portfolio import Portfolio
from trader.signals import Bar
from trader.strategies import Strategy

from trader_research.contracts import (
    ArtifactReference,
    SCHEMA_VERSION,
    SideEffect,
    ToolEnvelope,
    error_envelope,
    success_envelope,
    write_json_artifact,
)
from trader_research.artifact_store import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    load_artifact_ref,
    load_module_from_source,
    source_hash as source_text_hash,
)
from trader_research.domain import (
    METHOD_CARD,
    METHOD_PACKAGE_MANIFEST,
    STRATEGY_IMPLEMENTATION,
    STRATEGY_CANDIDATE_VALIDATION_REPORT,
    QUANT_RESEARCH_SUPERVISOR_OWNER,
    StrategyCandidateArtifactLink,
    StrategyCandidateManifest,
    StrategyCandidateSourceRef,
    stable_research_id,
)
from trader_research.knowledge.domain import RICH_METHOD_CARD_FORMAT
from trader_research.method_implementations.io import file_sha256
from trader_research.method_implementations.manifest import SIGNAL_RUNTIME_CONTRACT
from .services import get_strategy_template, strategy_candidate_path


RESEARCH_VALIDATE_STRATEGY_CANDIDATE = "research_validate_strategy_candidate"
STRATEGY_VALIDATION_FIXTURE_ID = "strategy_candidate_smoke_v1"
SYNTHETIC_BAR_COUNT = 160
FIXTURE_SYMBOL = "SYNTH"
FIXTURE_SYMBOLS = ("SYNTH_A", "SYNTH_B", "SYNTH_C")
FIXTURE_ASSET_CLASS = "stocks"
FIXTURE_TIMEFRAME = "1Min"


@dataclass(frozen=True)
class _ResolvedCandidate:
    """Parsed strategy candidate and optional source path."""

    manifest: StrategyCandidateManifest
    path: Path | None


class _FixtureEventStore(EventStore):
    """Small in-memory event store with enough read support for strategy smoke checks."""

    def __init__(self, bars_by_symbol: Mapping[str, Sequence[Bar]], timeframe: str) -> None:
        self._bars_by_symbol = {symbol.upper(): tuple(bars) for symbol, bars in bars_by_symbol.items()}
        self._timeframe = timeframe
        self.events: list[Mapping[str, object]] = []

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Record fixture telemetry emitted by maintained strategies."""
        self.events.append({"event_type": event_type, "payload": dict(payload)})

    def connection(self) -> "_FixtureConnection":
        """Return a DB-API-like connection facade used by bar query helpers."""
        return _FixtureConnection(self)

    def rows(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        as_of_ts: datetime | None,
    ) -> list[tuple[datetime, float, float, float, float, float, float | None, float | None]]:
        """Return latest-first OHLCV tuples for the requested fixture symbol."""
        if timeframe != self._timeframe:
            return []
        bars = self._bars_by_symbol.get(symbol.upper(), ())
        bounded = [bar for bar in bars if as_of_ts is None or bar.ts <= as_of_ts]
        return [
            (bar.ts, bar.open, bar.high, bar.low, bar.close, bar.volume, bar.vwap, bar.trade_count)
            for bar in bounded[:limit]
        ]


class _FixtureConnection:
    """Connection facade that creates fixture cursors."""

    def __init__(self, store: _FixtureEventStore) -> None:
        self._store = store

    def cursor(self) -> "_FixtureCursor":
        """Return a context-manager cursor facade."""
        return _FixtureCursor(self._store)


class _FixtureCursor:
    """Cursor facade for the query shape used by standard strategy bar helpers."""

    def __init__(self, store: _FixtureEventStore) -> None:
        self._store = store
        self._rows: list[tuple[datetime, float, float, float, float, float, float | None, float | None]] = []

    def __enter__(self) -> "_FixtureCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def execute(self, query: str, params: Sequence[object]) -> None:
        """Store deterministic rows for the latest executed fixture query."""
        del query
        if len(params) == 4:
            symbol, timeframe, as_of_ts, limit = params
            parsed_as_of = as_of_ts if isinstance(as_of_ts, datetime) else None
        else:
            symbol, timeframe, limit = params
            parsed_as_of = None
        self._rows = self._store.rows(
            symbol=str(symbol),
            timeframe=str(timeframe),
            limit=int(limit),
            as_of_ts=parsed_as_of,
        )

    def fetchall(self) -> list[tuple[datetime, float, float, float, float, float, float | None, float | None]]:
        """Return rows from the latest fixture query."""
        return list(self._rows)


def validate_strategy_candidate(
    *,
    artifact_root: str | Path,
    candidate_id: str | None = None,
    path: str | Path | None = None,
    strategy_candidate_manifest: Mapping[str, Any] | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Validate one strategy candidate before any backtest can consume it.

    Args:
        artifact_root: Root directory for local research artifacts.
        candidate_id: Optional persisted candidate ID.
        path: Optional direct path to a `strategy_candidate_manifest.json`.
        strategy_candidate_manifest: Optional inline candidate manifest payload.

    Returns:
        Local-mutating envelope with a persisted validation report. Resolved
        candidates that fail checks still write a failed report.
    """
    try:
        candidate = _resolve_candidate(
            artifact_root=artifact_root,
            candidate_id=candidate_id,
            path=path,
            strategy_candidate_manifest=strategy_candidate_manifest,
            artifact_store=artifact_store,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return error_envelope(
            command=RESEARCH_VALIDATE_STRATEGY_CANDIDATE,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="strategy_candidate_resolution_failed",
            message=str(exc),
        )

    report, report_path = _build_validation_report(
        artifact_root=artifact_root,
        candidate=candidate,
        artifact_store=artifact_store,
    )
    report_ref = _validation_report_ref(report, report_path, artifact_store)
    if report["status"] == "passed":
        return success_envelope(
            command=RESEARCH_VALIDATE_STRATEGY_CANDIDATE,
            side_effect=SideEffect.LOCAL_MUTATING,
            data={"strategy_candidate_validation_report": report},
            artifacts={"strategy_candidate_validation_report": report_ref},
            warnings=tuple(str(item) for item in report["warnings"]),
        )
    return ToolEnvelope(
        ok=False,
        command=RESEARCH_VALIDATE_STRATEGY_CANDIDATE,
        agent_owner=QUANT_RESEARCH_SUPERVISOR_OWNER,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"strategy_candidate_validation_report": report},
        artifacts={"strategy_candidate_validation_report": report_ref},
        warnings=tuple(str(item) for item in report["warnings"]),
        errors=(
            {
                "code": "strategy_candidate_validation_failed",
                "message": "Strategy candidate validation failed",
            },
        ),
    )


def strategy_candidate_validation_report_path(artifact_root: str | Path, validation_id: str) -> Path:
    """Return the deterministic path for a strategy candidate validation report."""
    return Path(artifact_root) / "strategy_candidates" / "validation_reports" / f"{validation_id}.json"


def _resolve_candidate(
    *,
    artifact_root: str | Path,
    candidate_id: str | None,
    path: str | Path | None,
    strategy_candidate_manifest: Mapping[str, Any] | None,
    artifact_store: ResearchArtifactStore | None,
) -> _ResolvedCandidate:
    sources = [
        candidate_id is not None and str(candidate_id).strip() != "",
        path is not None and str(path).strip() != "",
        strategy_candidate_manifest is not None,
    ]
    if sum(1 for selected in sources if selected) != 1:
        raise ValueError("exactly one of candidate_id, path, or strategy_candidate_manifest is required")
    if strategy_candidate_manifest is not None:
        return _ResolvedCandidate(StrategyCandidateManifest.from_dict(strategy_candidate_manifest), None)
    if candidate_id is not None and str(candidate_id).strip():
        if artifact_store is not None:
            return _ResolvedCandidate(
                StrategyCandidateManifest.from_dict(
                    load_artifact_ref(artifact_store, "strategy_candidate", str(candidate_id).strip())
                ),
                None,
            )
        candidate_path = strategy_candidate_path(artifact_root, str(candidate_id).strip())
        return _ResolvedCandidate(_candidate_from_path(candidate_path), candidate_path)
    candidate_path = Path(str(path))
    return _ResolvedCandidate(_candidate_from_path(candidate_path), candidate_path)


def _candidate_from_path(path: Path) -> StrategyCandidateManifest:
    if not path.exists():
        raise FileNotFoundError(f"strategy candidate manifest not found: {path}")
    return StrategyCandidateManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _build_validation_report(
    *,
    artifact_root: str | Path,
    candidate: _ResolvedCandidate,
    artifact_store: ResearchArtifactStore | None,
) -> tuple[dict[str, Any], Path | None]:
    manifest = candidate.manifest
    warnings = [issue.message for issue in manifest.warnings]
    blockers: list[str] = []
    checks: list[dict[str, Any]] = []
    fixture_summary: dict[str, Any] = {
        "fixture_id": STRATEGY_VALIDATION_FIXTURE_ID,
        "status": "not_run",
        "orders_emitted": 0,
    }
    strategy_info: dict[str, Any] = {}
    runtime_builder_path = ""
    runtime_strategy_id = ""

    try:
        template = get_strategy_template(manifest.template_family)
        runtime_builder_path = template.runtime_builder_path
        runtime_strategy_id = template.runtime_strategy_id
    except ValueError as exc:
        _add_blocking_check(checks, blockers, "template_support", str(exc))
        template = None

    _record_check(checks, blockers, "manifest_integrity", _check_manifest_integrity(manifest))
    if template is not None:
        _record_check(
            checks,
            blockers,
            "method_package_refs",
            _check_method_package_refs(manifest, template.required_artifact_roles),
        )
        _record_check(checks, blockers, "methodology_refs", _check_methodology_refs(manifest, template.template_family))
        _record_check(checks, blockers, "parameters", _check_parameters(manifest, template.parameters))
        _record_check(checks, blockers, "sizing", _check_sizing(manifest))
        _record_check(checks, blockers, "execution_assumptions", _check_execution_assumptions(manifest))
        _record_check(
            checks,
            blockers,
            "strategy_source",
            _check_strategy_source(manifest.strategy_source, template.runtime_builder_path, artifact_store),
        )
        if not blockers:
            strategy, source_blockers = _instantiate_strategy(manifest, artifact_store)
            _record_check(checks, blockers, "strategy_source_instantiation", source_blockers)
            if strategy is not None and not source_blockers:
                strategy_info = strategy.strategy_info.to_dict()
                fixture_summary, fixture_blockers = _run_fixture_smoke(strategy, manifest)
                _record_check(checks, blockers, "fixture_smoke", fixture_blockers)

    status = "passed" if not blockers else "failed"
    validation_id = _validation_id(
        manifest=manifest,
        runtime_builder_path=runtime_builder_path,
        runtime_strategy_id=runtime_strategy_id,
        strategy_info=strategy_info,
        checks=checks,
        fixture_summary=fixture_summary,
        status=status,
    )
    report = {
        "artifact_type": STRATEGY_CANDIDATE_VALIDATION_REPORT,
        "schema_version": SCHEMA_VERSION,
        "validation_id": validation_id,
        "candidate_id": manifest.candidate_id,
        "template_family": manifest.template_family,
        "status": status,
        "runtime_builder_path": runtime_builder_path,
        "runtime_strategy_id": runtime_strategy_id,
        "strategy_info": strategy_info,
        "checks": checks,
        "fixture_summary": fixture_summary,
        "warnings": warnings,
        "blockers": blockers,
    }
    if artifact_store is not None:
        artifact_store.save_artifact(
            artifact_type=STRATEGY_CANDIDATE_VALIDATION_REPORT,
            artifact_id=validation_id,
            payload=report,
            status=status,
            source_hash=strategy_info.get("source_hash"),
            metadata={"candidate_id": manifest.candidate_id},
        )
        return report, None
    report_path = strategy_candidate_validation_report_path(artifact_root, validation_id)
    write_json_artifact(report, report_path)
    return report, report_path


def _validation_report_ref(
    report: Mapping[str, Any],
    report_path: Path | None,
    artifact_store: ResearchArtifactStore | None,
) -> dict[str, Any]:
    validation_id = str(report["validation_id"])
    metadata = {"id": validation_id, "candidate_id": report["candidate_id"]}
    if artifact_store is not None:
        return ArtifactReference(
            artifact_type=STRATEGY_CANDIDATE_VALIDATION_REPORT,
            uri=f"research://postgres/{STRATEGY_CANDIDATE_VALIDATION_REPORT}/{validation_id}",
            metadata=metadata,
        ).to_dict()
    return ArtifactReference(
        artifact_type=STRATEGY_CANDIDATE_VALIDATION_REPORT,
        path=report_path,
        metadata=metadata,
    ).to_dict()


def _check_manifest_integrity(manifest: StrategyCandidateManifest) -> list[str]:
    blockers: list[str] = []
    if manifest.blockers:
        blockers.extend(f"candidate manifest blocker: {blocker.message}" for blocker in manifest.blockers)
    if manifest.artifact_type != "strategy_candidate":
        blockers.append("candidate artifact_type must be strategy_candidate")
    return blockers


def _check_strategy_source(
    source_ref: StrategyCandidateSourceRef | None,
    expected_builder_path: str,
    artifact_store: ResearchArtifactStore | None,
) -> list[str]:
    if source_ref is None:
        return ["candidate strategy_source is required"]
    blockers: list[str] = []
    if source_ref.artifact_type != STRATEGY_IMPLEMENTATION:
        blockers.append(f"strategy_source artifact_type must be {STRATEGY_IMPLEMENTATION}")
    if source_ref.runtime_contract != "trader.strategies.Strategy":
        blockers.append("strategy_source runtime_contract must be trader.strategies.Strategy")
    if not source_ref.path and not source_ref.uri:
        blockers.append("strategy_source path or uri is required")
    if not source_ref.source_hash:
        blockers.append("strategy_source source_hash is required")
    if not source_ref.factory_name:
        blockers.append("strategy_source factory_name is required")
    if not source_ref.class_name:
        blockers.append("strategy_source class_name is required")
    if str(source_ref.metadata.get("runtime_builder_path") or "") != expected_builder_path:
        blockers.append("strategy_source metadata.runtime_builder_path does not match template")
    if source_ref.uri:
        if artifact_store is None:
            blockers.append("strategy_source uri requires a configured research artifact store")
        else:
            try:
                payload = load_artifact_ref(artifact_store, STRATEGY_IMPLEMENTATION, source_ref.uri)
                source_code = str(payload.get("source_code") or "")
                if not source_code:
                    blockers.append("strategy_source DB artifact source_code is required")
                elif source_ref.source_hash and source_text_hash(source_code) != source_ref.source_hash:
                    blockers.append("strategy_source source_hash does not match DB source artifact")
            except ResearchArtifactStoreError as exc:
                blockers.append(f"strategy_source DB artifact could not be loaded: {exc}")
    elif source_ref.path:
        source_path = Path(source_ref.path)
        if not source_path.exists():
            blockers.append(f"strategy_source file not found: {source_path}")
        elif source_ref.source_hash and file_sha256(source_path) != source_ref.source_hash:
            blockers.append("strategy_source source_hash does not match current source file")
    return blockers


def _check_method_package_refs(
    manifest: StrategyCandidateManifest,
    required_artifact_roles: Sequence[Mapping[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    required_by_role = {str(item.get("role") or ""): item for item in required_artifact_roles}
    expected_roles = tuple(role for role in required_by_role if role)
    refs_by_role: dict[str, StrategyCandidateArtifactLink] = {}
    for ref in manifest.method_package_refs:
        if ref.role not in required_by_role:
            blockers.append(f"unknown method package role: {ref.role}")
            continue
        if ref.role in refs_by_role:
            blockers.append(f"duplicate method package role: {ref.role}")
            continue
        refs_by_role[ref.role] = ref
        blockers.extend(_method_package_ref_blockers(ref, required_by_role[ref.role]))
    for role in expected_roles:
        if role not in refs_by_role:
            blockers.append(f"missing required method package role: {role}")
    return blockers


def _check_methodology_refs(
    manifest: StrategyCandidateManifest,
    template_family: str,
) -> list[str]:
    blockers: list[str] = []
    refs = manifest.methodology_refs
    if template_family == "pairs_mean_reversion" and not refs:
        blockers.append("pairs_mean_reversion requires approved rich method-card methodology_refs")
    for ref in refs:
        if ref.artifact_type != METHOD_CARD:
            blockers.append(f"{ref.role} methodology ref must reference artifact_type={METHOD_CARD}")
        if ref.status != "approved":
            blockers.append(f"{ref.role} methodology ref status must be approved")
        if str(ref.metadata.get("card_format") or "") != RICH_METHOD_CARD_FORMAT:
            blockers.append(f"{ref.role} methodology ref card_format must be rich_method_card")
        if template_family == "pairs_mean_reversion" and str(ref.metadata.get("family") or "") != "statistical_arbitrage":
            blockers.append("pairs_mean_reversion methodology ref family must be statistical_arbitrage")
        if str(ref.metadata.get("method_id") or "").strip() == "":
            blockers.append(f"{ref.role} methodology ref metadata.method_id is required")
    return blockers


def _method_package_ref_blockers(
    ref: StrategyCandidateArtifactLink,
    required_role: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    expected_contract = str(required_role.get("runtime_contract") or "")
    if ref.artifact_type != METHOD_PACKAGE_MANIFEST:
        blockers.append(f"{ref.role} must reference artifact_type={METHOD_PACKAGE_MANIFEST}")
    if ref.status != "validated":
        blockers.append(f"{ref.role} package ref must have status=validated")
    if str(ref.metadata.get("runtime_contract") or "") != expected_contract:
        blockers.append(f"{ref.role} package ref runtime_contract must be {expected_contract}")
    if expected_contract != SIGNAL_RUNTIME_CONTRACT:
        blockers.append(f"{ref.role} requires unsupported v1 runtime_contract: {expected_contract}")
    if str(ref.metadata.get("method_id") or "").strip() == "":
        blockers.append(f"{ref.role} package ref metadata.method_id is required")
    if str(ref.metadata.get("source_hash") or "").strip() == "":
        blockers.append(f"{ref.role} package ref metadata.source_hash is required")
    package_id = str(ref.metadata.get("package_id") or ref.artifact_id).strip()
    if not package_id:
        blockers.append(f"{ref.role} package ref package_id is required")
    validation_ref = _mapping(ref.metadata.get("validation_report_ref"))
    if str(validation_ref.get("status") or "") != "passed":
        blockers.append(f"{ref.role} package ref validation_report_ref.status must be passed")
    return blockers


def _check_parameters(
    manifest: StrategyCandidateManifest,
    parameter_specs: Sequence[Any],
) -> list[str]:
    blockers: list[str] = []
    expected = {parameter.name: parameter for parameter in parameter_specs}
    for name in sorted(set(manifest.parameters).difference(expected)):
        blockers.append(f"unknown strategy template parameter: {name}")
    for parameter in parameter_specs:
        if parameter.required and parameter.name not in manifest.parameters:
            blockers.append(f"required strategy template parameter is missing: {parameter.name}")
        if parameter.name in manifest.parameters:
            blockers.extend(_parameter_value_blockers(parameter, manifest.parameters[parameter.name]))
    blockers.extend(_parameter_constraint_blockers(parameter_specs, manifest.parameters))
    return blockers


def _parameter_value_blockers(parameter: Any, value: Any) -> list[str]:
    field_name = f"parameters.{parameter.name}"
    if parameter.value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return [f"{field_name} must be an integer"]
        return []
    if parameter.value_type == "number":
        return [] if _numeric_value(value) is not None else [f"{field_name} must be numeric"]
    if parameter.value_type == "string":
        return [] if isinstance(value, str) and value.strip() else [f"{field_name} must be a non-empty string"]
    if parameter.value_type == "array[string]":
        if isinstance(value, SequenceABC) and not isinstance(value, (str, bytes)):
            values = [str(item).strip() for item in value if str(item).strip()]
            if values:
                return []
        return [f"{field_name} must be a non-empty string array"]
    return []


def _parameter_constraint_blockers(parameter_specs: Sequence[Any], parameters: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for parameter in parameter_specs:
        if parameter.name not in parameters:
            continue
        value = parameters[parameter.name]
        constraints = parameter.constraints
        if "allowed_values" in constraints and value not in constraints["allowed_values"]:
            blockers.append(f"{parameter.name} must be one of {constraints['allowed_values']}")
        if "min_items" in constraints and isinstance(value, SequenceABC) and not isinstance(value, (str, bytes)):
            if len(value) < int(constraints["min_items"]):
                blockers.append(f"{parameter.name} must contain at least {constraints['min_items']} items")
        if "max_items" in constraints and isinstance(value, SequenceABC) and not isinstance(value, (str, bytes)):
            if len(value) > int(constraints["max_items"]):
                blockers.append(f"{parameter.name} must contain at most {constraints['max_items']} items")
        numeric_value = _numeric_value(value)
        if "minimum" in constraints and numeric_value is not None and numeric_value < float(constraints["minimum"]):
            blockers.append(f"{parameter.name} must be >= {constraints['minimum']}")
        if "maximum" in constraints and numeric_value is not None and numeric_value > float(constraints["maximum"]):
            blockers.append(f"{parameter.name} must be <= {constraints['maximum']}")
        if "must_exceed" in constraints:
            other_name = str(constraints["must_exceed"])
            other_value = _numeric_value(parameters.get(other_name))
            if numeric_value is not None and other_value is not None and numeric_value <= other_value:
                blockers.append(f"{parameter.name} must exceed {other_name}")
    return blockers


def _check_sizing(manifest: StrategyCandidateManifest) -> list[str]:
    blockers: list[str] = []
    sizing = manifest.sizing
    if sizing.model != "fixed_quantity":
        blockers.append("candidate sizing.model must be fixed_quantity")
    if sizing.target_qty_when_long < 0.0:
        blockers.append("candidate target_qty_when_long must be non-negative")
    if sizing.max_position_qty is not None and sizing.target_qty_when_long > sizing.max_position_qty:
        blockers.append("candidate target_qty_when_long must not exceed max_position_qty")
    parameter_qty = _numeric_value(manifest.parameters.get("target_qty_when_long"))
    if parameter_qty is not None and parameter_qty != sizing.target_qty_when_long:
        blockers.append("target_qty_when_long cannot conflict between parameters and sizing")
    return blockers


def _check_execution_assumptions(manifest: StrategyCandidateManifest) -> list[str]:
    blockers: list[str] = []
    assumptions = manifest.execution_assumptions
    if assumptions.get("order_type") != "market":
        blockers.append("candidate execution_assumptions.order_type must be market")
    for flag in (
        "arbitrary_strategy_code_allowed",
        "broker_mutation_allowed",
        "dynamic_stop_policy_configuration",
        "live_trading_allowed",
    ):
        if _truthy(assumptions.get(flag)):
            blockers.append(f"candidate execution_assumptions.{flag} must remain false")
    return blockers


def _instantiate_strategy(
    manifest: StrategyCandidateManifest,
    artifact_store: ResearchArtifactStore | None,
) -> tuple[Strategy | None, list[str]]:
    blockers: list[str] = []
    source_ref = manifest.strategy_source
    if source_ref is None:
        return None, ["candidate strategy_source is required"]
    try:
        module = _load_strategy_source_module(source_ref, manifest.candidate_id, artifact_store)
        if not hasattr(module, source_ref.class_name):
            raise ValueError(f"strategy source class not found: {source_ref.class_name}")
        factory = getattr(module, source_ref.factory_name)
        strategy = factory(
            symbols=list(FIXTURE_SYMBOLS),
            asset_class=FIXTURE_ASSET_CLASS,
            timeframe=FIXTURE_TIMEFRAME,
        )
    except Exception as exc:
        blockers.append(f"strategy source instantiation failed: {exc}")
        return None, blockers
    if not isinstance(strategy, Strategy):
        blockers.append("strategy source factory did not return a trader.strategies.Strategy")
        return None, blockers
    return strategy, blockers


def _load_strategy_source_module(
    source_ref: StrategyCandidateSourceRef,
    candidate_id: str,
    artifact_store: ResearchArtifactStore | None,
) -> object:
    module_name = f"_trader_strategy_candidate_{_module_suffix(candidate_id)}"
    if source_ref.uri:
        if artifact_store is None:
            raise ValueError("strategy source uri requires a configured research artifact store")
        payload = load_artifact_ref(artifact_store, STRATEGY_IMPLEMENTATION, source_ref.uri)
        source_code = str(payload.get("source_code") or "")
        if not source_code:
            raise ValueError("strategy source DB artifact source_code is required")
        return load_module_from_source(module_name, source_code, filename=source_ref.uri)
    if not source_ref.path:
        raise ValueError("strategy source path or uri is required")
    source_path = Path(source_ref.path)
    from importlib import util as importlib_util

    spec = importlib_util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load strategy source module: {source_path}")
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module_suffix(candidate_id: str) -> str:
    suffix = "".join(character for character in candidate_id if character.isalnum())[-16:]
    return suffix or "generated"


def _run_fixture_smoke(
    strategy: Strategy,
    manifest: StrategyCandidateManifest,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    symbols = FIXTURE_SYMBOLS
    bars_by_symbol = {symbol: _synthetic_bars(symbol_index=index) for index, symbol in enumerate(symbols)}
    store = _FixtureEventStore(bars_by_symbol, FIXTURE_TIMEFRAME)
    decision_ts = max(bar.ts for bars in bars_by_symbol.values() for bar in bars)
    try:
        orders = list(
            strategy.generate_orders(
                run_id="strategy_candidate_validation",
                cycle_id=STRATEGY_VALIDATION_FIXTURE_ID,
                decision_ts=decision_ts,
                event_store=store,
                portfolio=Portfolio.empty(cash_balance=100_000.0),
            )
        )
    except Exception as exc:
        return _fixture_summary(status="failed", symbols=symbols, orders=(), store=store), [
            f"strategy fixture smoke check failed: {exc}"
        ]

    for index, order in enumerate(orders):
        blockers.extend(_order_blockers(index, order, symbols, manifest.sizing.max_position_qty))
    status = "passed" if not blockers else "failed"
    return _fixture_summary(status=status, symbols=symbols, orders=orders, store=store), blockers


def _fixture_summary(
    *,
    status: str,
    symbols: Sequence[str],
    orders: Sequence[Mapping[str, object]],
    store: _FixtureEventStore,
) -> dict[str, Any]:
    return {
        "fixture_id": STRATEGY_VALIDATION_FIXTURE_ID,
        "fixture_context": {
            "asset_class": FIXTURE_ASSET_CLASS,
            "symbols": list(symbols),
            "timeframe": FIXTURE_TIMEFRAME,
        },
        "status": status,
        "symbol_count": len(symbols),
        "symbols": list(symbols),
        "bar_count_per_symbol": SYNTHETIC_BAR_COUNT,
        "orders_emitted": len(orders),
        "signal_event_count": sum(1 for event in store.events if event.get("event_type") == "signal_events"),
    }


def _order_blockers(
    index: int,
    order: Mapping[str, object],
    symbols: Sequence[str],
    max_position_qty: float | None,
) -> list[str]:
    blockers: list[str] = []
    symbol = str(order.get("symbol") or "").strip().upper()
    side = str(order.get("side") or "").strip().lower()
    order_type = str(order.get("order_type") or "").strip().lower()
    qty = _numeric_value(order.get("qty"))
    if symbol not in symbols:
        blockers.append(f"fixture order {index} has unknown symbol: {symbol}")
    if side not in {"buy", "sell"}:
        blockers.append(f"fixture order {index} side must be buy or sell")
    if order_type != "market":
        blockers.append(f"fixture order {index} order_type must be market")
    if qty is None or qty < 0.0:
        blockers.append(f"fixture order {index} qty must be non-negative numeric")
    if max_position_qty is not None and qty is not None and qty > max_position_qty:
        blockers.append(f"fixture order {index} qty must not exceed max_position_qty")
    return blockers


def _synthetic_bars(*, symbol_index: int = 0) -> tuple[Bar, ...]:
    base_ts = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    ascending: list[Bar] = []
    drift = 0.03 + symbol_index * 0.02
    base_price = 95.0 + symbol_index * 5.0
    for index in range(SYNTHETIC_BAR_COUNT):
        close = base_price + index * drift + ((index % 7) - 3) * 0.02
        ts = base_ts + timedelta(minutes=index)
        ascending.append(
            Bar(
                ts=ts,
                open=close,
                high=close + 0.1,
                low=close - 0.1,
                close=close,
                volume=1000.0 + index,
                vwap=None,
                trade_count=None,
            )
        )
    return tuple(reversed(ascending))


def _validation_id(
    *,
    manifest: StrategyCandidateManifest,
    runtime_builder_path: str,
    runtime_strategy_id: str,
    strategy_info: Mapping[str, Any],
    checks: Sequence[Mapping[str, Any]],
    fixture_summary: Mapping[str, Any],
    status: str,
) -> str:
    return stable_research_id(
        "strategy_candidate_validation",
        {
            "candidate_id": manifest.candidate_id,
            "candidate_manifest": manifest.to_dict(),
            "checks": [{"name": check["name"], "status": check["status"]} for check in checks],
            "fixture_summary": fixture_summary,
            "runtime_builder_path": runtime_builder_path,
            "runtime_strategy_id": runtime_strategy_id,
            "status": status,
            "strategy_info": strategy_info,
        },
    )


def _record_check(
    checks: list[dict[str, Any]],
    blockers: list[str],
    name: str,
    check_blockers: Sequence[str],
) -> None:
    checks.append(
        {
            "name": name,
            "status": "passed" if not check_blockers else "failed",
            "messages": list(check_blockers),
        }
    )
    blockers.extend(check_blockers)


def _add_blocking_check(checks: list[dict[str, Any]], blockers: list[str], name: str, message: str) -> None:
    checks.append({"name": name, "status": "failed", "messages": [message]})
    blockers.append(message)


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, MappingABC):
        return value
    return {}


def _numeric_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
