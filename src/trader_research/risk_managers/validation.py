"""Risk-manager candidate validation for supervisor-owned research tools."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader.portfolio import Position
from trader.risk import RiskContext, RiskManager

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
    QUANT_RESEARCH_SUPERVISOR_OWNER,
    RISK_MANAGER_CANDIDATE_VALIDATION_REPORT,
    RISK_MANAGER_IMPLEMENTATION,
    RiskManagerCandidateManifest,
    RiskManagerCandidateSourceRef,
    StrategyCandidateArtifactLink,
    stable_research_id,
)
from trader_research.knowledge.domain import RICH_METHOD_CARD_FORMAT
from trader_research.method_implementations.io import file_sha256

from .services import get_risk_manager_template, risk_manager_candidate_path


RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE = "research_validate_risk_manager_candidate"
RISK_MANAGER_VALIDATION_FIXTURE_ID = "risk_manager_candidate_smoke_v1"
FIXTURE_SYMBOLS = ("SYNTH_A", "SYNTH_B", "SYNTH_C")


@dataclass(frozen=True)
class _ResolvedRiskManagerCandidate:
    """Parsed risk-manager candidate and optional source path."""

    manifest: RiskManagerCandidateManifest
    path: Path | None


def validate_risk_manager_candidate(
    *,
    artifact_root: str | Path,
    candidate_id: str | None = None,
    path: str | Path | None = None,
    risk_manager_candidate_manifest: Mapping[str, Any] | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Validate one risk-manager candidate before stack composition.

    Args:
        artifact_root: Root directory for local research artifacts.
        candidate_id: Optional persisted risk-manager candidate ID.
        path: Optional path to a `risk_manager_candidate_manifest.json`.
        risk_manager_candidate_manifest: Optional inline candidate manifest.

    Returns:
        Local-mutating envelope with a persisted validation report. Resolved
        candidates that fail checks still write a failed report.
    """
    try:
        candidate = _resolve_candidate(
            artifact_root=artifact_root,
            candidate_id=candidate_id,
            path=path,
            risk_manager_candidate_manifest=risk_manager_candidate_manifest,
            artifact_store=artifact_store,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return error_envelope(
            command=RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="risk_manager_candidate_resolution_failed",
            message=str(exc),
        )

    report, report_path = _build_validation_report(
        artifact_root=artifact_root,
        candidate=candidate,
        artifact_store=artifact_store,
    )
    artifacts = {
        "risk_manager_candidate_validation_report": _validation_report_ref(report, report_path, artifact_store)
    }
    if report["status"] == "passed":
        return success_envelope(
            command=RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE,
            side_effect=SideEffect.LOCAL_MUTATING,
            data={"risk_manager_candidate_validation_report": report},
            artifacts=artifacts,
            warnings=tuple(str(item) for item in report["warnings"]),
        )
    return ToolEnvelope(
        ok=False,
        command=RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE,
        agent_owner=QUANT_RESEARCH_SUPERVISOR_OWNER,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"risk_manager_candidate_validation_report": report},
        artifacts=artifacts,
        warnings=tuple(str(item) for item in report["warnings"]),
        errors=(
            {
                "code": "risk_manager_candidate_validation_failed",
                "message": "Risk-manager candidate validation failed",
            },
        ),
    )


def risk_manager_candidate_validation_report_path(artifact_root: str | Path, validation_id: str) -> Path:
    """Return the deterministic path for one risk-manager validation report."""
    return Path(artifact_root) / "risk_managers" / "validation_reports" / f"{validation_id}.json"


def _resolve_candidate(
    *,
    artifact_root: str | Path,
    candidate_id: str | None,
    path: str | Path | None,
    risk_manager_candidate_manifest: Mapping[str, Any] | None,
    artifact_store: ResearchArtifactStore | None,
) -> _ResolvedRiskManagerCandidate:
    sources = [
        candidate_id is not None and str(candidate_id).strip() != "",
        path is not None and str(path).strip() != "",
        risk_manager_candidate_manifest is not None,
    ]
    if sum(1 for selected in sources if selected) != 1:
        raise ValueError("exactly one of candidate_id, path, or risk_manager_candidate_manifest is required")
    if risk_manager_candidate_manifest is not None:
        return _ResolvedRiskManagerCandidate(
            RiskManagerCandidateManifest.from_dict(risk_manager_candidate_manifest),
            None,
        )
    if candidate_id is not None and str(candidate_id).strip():
        if artifact_store is not None:
            return _ResolvedRiskManagerCandidate(
                RiskManagerCandidateManifest.from_dict(
                    load_artifact_ref(artifact_store, "risk_manager_candidate", str(candidate_id).strip())
                ),
                None,
            )
        candidate_path = risk_manager_candidate_path(artifact_root, str(candidate_id).strip())
        return _ResolvedRiskManagerCandidate(_candidate_from_path(candidate_path), candidate_path)
    candidate_path = Path(str(path))
    return _ResolvedRiskManagerCandidate(_candidate_from_path(candidate_path), candidate_path)


def _candidate_from_path(path: Path) -> RiskManagerCandidateManifest:
    if not path.exists():
        raise FileNotFoundError(f"risk-manager candidate manifest not found: {path}")
    return RiskManagerCandidateManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _build_validation_report(
    *,
    artifact_root: str | Path,
    candidate: _ResolvedRiskManagerCandidate,
    artifact_store: ResearchArtifactStore | None,
) -> tuple[dict[str, Any], Path | None]:
    manifest = candidate.manifest
    warnings = [issue.message for issue in manifest.warnings]
    blockers: list[str] = []
    checks: list[dict[str, Any]] = []
    fixture_summary: dict[str, Any] = {
        "fixture_id": RISK_MANAGER_VALIDATION_FIXTURE_ID,
        "status": "not_run",
        "orders_evaluated": 0,
    }
    template_family = manifest.template_family

    try:
        template = get_risk_manager_template(template_family)
    except ValueError as exc:
        _add_blocking_check(checks, blockers, "template_support", str(exc))
        template = None

    _record_check(checks, blockers, "manifest_integrity", _check_manifest_integrity(manifest))
    _record_check(checks, blockers, "method_package_refs", _check_method_package_refs(manifest.method_package_refs))
    _record_check(checks, blockers, "methodology_refs", _check_methodology_refs(manifest.methodology_refs))
    _record_check(checks, blockers, "execution_assumptions", _check_execution_assumptions(manifest))
    _record_check(
        checks,
        blockers,
        "risk_manager_source",
        _check_risk_manager_source(manifest.risk_manager_source, artifact_store),
    )
    _record_check(checks, blockers, "source_safety", _check_source_safety(manifest.risk_manager_source, artifact_store))
    if template is not None:
        _record_check(
            checks,
            blockers,
            "validation_requirements",
            _check_validation_requirements(manifest, template.validation_requirements),
        )
    if not blockers:
        risk_manager, source_blockers = _instantiate_risk_manager(manifest, artifact_store)
        _record_check(checks, blockers, "risk_manager_source_instantiation", source_blockers)
        if risk_manager is not None and not source_blockers:
            fixture_summary, fixture_blockers = _run_fixture_smoke(risk_manager, manifest)
            _record_check(checks, blockers, "fixture_smoke", fixture_blockers)

    status = "passed" if not blockers else "failed"
    validation_id = _validation_id(
        manifest=manifest,
        checks=checks,
        fixture_summary=fixture_summary,
        status=status,
    )
    source_ref = manifest.risk_manager_source
    report = {
        "artifact_type": RISK_MANAGER_CANDIDATE_VALIDATION_REPORT,
        "schema_version": SCHEMA_VERSION,
        "validation_id": validation_id,
        "candidate_id": manifest.candidate_id,
        "candidate_manifest_ref": _candidate_manifest_ref(candidate).to_dict(),
        "template_family": manifest.template_family,
        "status": status,
        "runtime_contract": source_ref.runtime_contract if source_ref is not None else "",
        "risk_manager_source_ref": source_ref.to_dict() if source_ref is not None else None,
        "checks": checks,
        "fixture_summary": fixture_summary,
        "policy_intent": dict(manifest.policy_intent),
        "telemetry_required": list(_sequence(manifest.execution_assumptions.get("telemetry_required"))),
        "warnings": warnings,
        "blockers": blockers,
    }
    if artifact_store is not None:
        artifact_store.save_artifact(
            artifact_type=RISK_MANAGER_CANDIDATE_VALIDATION_REPORT,
            artifact_id=validation_id,
            payload=report,
            status=status,
            source_hash=source_ref.source_hash if source_ref is not None else None,
            metadata={"candidate_id": manifest.candidate_id},
        )
        return report, None
    report_path = risk_manager_candidate_validation_report_path(artifact_root, validation_id)
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
            artifact_type=RISK_MANAGER_CANDIDATE_VALIDATION_REPORT,
            uri=f"research://postgres/{RISK_MANAGER_CANDIDATE_VALIDATION_REPORT}/{validation_id}",
            metadata=metadata,
        ).to_dict()
    return ArtifactReference(
        artifact_type=RISK_MANAGER_CANDIDATE_VALIDATION_REPORT,
        path=report_path,
        metadata=metadata,
    ).to_dict()


def _candidate_manifest_ref(candidate: _ResolvedRiskManagerCandidate) -> StrategyCandidateArtifactLink:
    manifest = candidate.manifest
    return StrategyCandidateArtifactLink(
        artifact_id=manifest.candidate_id,
        artifact_type=manifest.artifact_type,
        role="risk_manager_candidate",
        path=str(candidate.path) if candidate.path is not None else None,
        agent_owner=QUANT_RESEARCH_SUPERVISOR_OWNER,
        status=manifest.status,
        metadata={
            "template_family": manifest.template_family,
            "source_hash": manifest.risk_manager_source.source_hash if manifest.risk_manager_source else "",
        },
    )


def _check_manifest_integrity(manifest: RiskManagerCandidateManifest) -> list[str]:
    blockers: list[str] = []
    if manifest.blockers:
        blockers.extend(f"candidate manifest blocker: {blocker.message}" for blocker in manifest.blockers)
    if manifest.artifact_type != "risk_manager_candidate":
        blockers.append("candidate artifact_type must be risk_manager_candidate")
    if manifest.status not in {"candidate", "validated"}:
        blockers.append("candidate status must be candidate or validated")
    return blockers


def _check_method_package_refs(refs: Sequence[StrategyCandidateArtifactLink]) -> list[str]:
    blockers: list[str] = []
    seen_roles: set[str] = set()
    for ref in refs:
        if ref.role in seen_roles:
            blockers.append(f"duplicate method package role: {ref.role}")
        seen_roles.add(ref.role)
        if ref.artifact_type != METHOD_PACKAGE_MANIFEST:
            blockers.append(f"{ref.role} must reference artifact_type={METHOD_PACKAGE_MANIFEST}")
        if ref.status != "validated":
            blockers.append(f"{ref.role} package ref must have status=validated")
        if str(ref.metadata.get("source_hash") or "").strip() == "":
            blockers.append(f"{ref.role} package ref metadata.source_hash is required")
        validation_ref = _mapping(ref.metadata.get("validation_report_ref"))
        if validation_ref and str(validation_ref.get("status") or "") != "passed":
            blockers.append(f"{ref.role} package ref validation_report_ref.status must be passed")
    return blockers


def _check_methodology_refs(refs: Sequence[StrategyCandidateArtifactLink]) -> list[str]:
    blockers: list[str] = []
    seen_roles: set[str] = set()
    for ref in refs:
        if ref.role in seen_roles:
            blockers.append(f"duplicate methodology role: {ref.role}")
        seen_roles.add(ref.role)
        if ref.artifact_type != METHOD_CARD:
            blockers.append(f"{ref.role} methodology ref must reference artifact_type={METHOD_CARD}")
        if ref.status != "approved":
            blockers.append(f"{ref.role} methodology ref status must be approved")
        if str(ref.metadata.get("card_format") or "") != RICH_METHOD_CARD_FORMAT:
            blockers.append(f"{ref.role} methodology ref card_format must be rich_method_card")
        if str(ref.metadata.get("method_id") or "").strip() == "":
            blockers.append(f"{ref.role} methodology ref metadata.method_id is required")
    return blockers


def _check_execution_assumptions(manifest: RiskManagerCandidateManifest) -> list[str]:
    assumptions = manifest.execution_assumptions
    blockers: list[str] = []
    if assumptions.get("backtest_only") is not True:
        blockers.append("candidate execution_assumptions.backtest_only must remain true")
    for flag in ("broker_mutation_allowed", "live_trading_allowed", "raw_sql_allowed"):
        if _truthy(assumptions.get(flag)):
            blockers.append(f"candidate execution_assumptions.{flag} must remain false")
    return blockers


def _check_validation_requirements(
    manifest: RiskManagerCandidateManifest,
    template_requirements: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    requirements = manifest.validation_requirements
    if requirements.get("requires_risk_manager_candidate_validation") is not True:
        blockers.append("validation_requirements.requires_risk_manager_candidate_validation must be true")
    if requirements.get("requires_strategy_risk_stack_validation") is not True:
        blockers.append("validation_requirements.requires_strategy_risk_stack_validation must be true")
    expected_contract = str(template_requirements.get("required_runtime_contract") or "trader.risk.RiskManager")
    if str(requirements.get("required_runtime_contract") or "") != expected_contract:
        blockers.append(f"validation_requirements.required_runtime_contract must be {expected_contract}")
    return blockers


def _check_risk_manager_source(
    source_ref: RiskManagerCandidateSourceRef | None,
    artifact_store: ResearchArtifactStore | None,
) -> list[str]:
    if source_ref is None:
        return ["candidate risk_manager_source is required"]
    blockers: list[str] = []
    if source_ref.artifact_type != RISK_MANAGER_IMPLEMENTATION:
        blockers.append(f"risk_manager_source artifact_type must be {RISK_MANAGER_IMPLEMENTATION}")
    if source_ref.runtime_contract != "trader.risk.RiskManager":
        blockers.append("risk_manager_source runtime_contract must be trader.risk.RiskManager")
    if not source_ref.path and not source_ref.uri:
        blockers.append("risk_manager_source path or uri is required")
    if not source_ref.source_hash:
        blockers.append("risk_manager_source source_hash is required")
    if not source_ref.factory_name:
        blockers.append("risk_manager_source factory_name is required")
    if not source_ref.class_name:
        blockers.append("risk_manager_source class_name is required")
    if source_ref.uri:
        if artifact_store is None:
            blockers.append("risk_manager_source uri requires a configured research artifact store")
        else:
            try:
                payload = load_artifact_ref(artifact_store, RISK_MANAGER_IMPLEMENTATION, source_ref.uri)
                source_code = str(payload.get("source_code") or "")
                if not source_code:
                    blockers.append("risk_manager_source DB artifact source_code is required")
                elif source_ref.source_hash and source_text_hash(source_code) != source_ref.source_hash:
                    blockers.append("risk_manager_source source_hash does not match DB source artifact")
            except ResearchArtifactStoreError as exc:
                blockers.append(f"risk_manager_source DB artifact could not be loaded: {exc}")
    elif source_ref.path:
        source_path = Path(source_ref.path)
        if not source_path.exists():
            blockers.append(f"risk_manager_source file not found: {source_path}")
        elif source_ref.source_hash and file_sha256(source_path) != source_ref.source_hash:
            blockers.append("risk_manager_source source_hash does not match current source file")
    return blockers


def _check_source_safety(
    source_ref: RiskManagerCandidateSourceRef | None,
    artifact_store: ResearchArtifactStore | None,
) -> list[str]:
    if source_ref is None:
        return []
    if source_ref.uri:
        if artifact_store is None:
            return []
        try:
            source = str(load_artifact_ref(artifact_store, RISK_MANAGER_IMPLEMENTATION, source_ref.uri).get("source_code") or "")
        except ResearchArtifactStoreError:
            return []
    elif source_ref.path:
        source_path = Path(source_ref.path)
        if not source_path.exists():
            return []
        source = source_path.read_text(encoding="utf-8")
    else:
        return []
    forbidden_markers = (
        "alpaca",
        "broker.",
        "eval(",
        "exec(",
        "open(",
        "os.",
        "pathlib",
        "psycopg",
        "requests",
        "socket",
        "subprocess",
    )
    return [f"risk_manager_source contains forbidden marker: {marker}" for marker in forbidden_markers if marker in source]


def _instantiate_risk_manager(
    manifest: RiskManagerCandidateManifest,
    artifact_store: ResearchArtifactStore | None,
) -> tuple[RiskManager | None, list[str]]:
    source_ref = manifest.risk_manager_source
    if source_ref is None:
        return None, ["candidate risk_manager_source is required"]
    blockers: list[str] = []
    try:
        module = _load_risk_manager_source_module(source_ref, manifest.candidate_id, artifact_store)
        if not hasattr(module, source_ref.class_name):
            raise ValueError(f"risk-manager source class not found: {source_ref.class_name}")
        factory = getattr(module, source_ref.factory_name)
        risk_manager = factory()
    except Exception as exc:
        blockers.append(f"risk-manager source instantiation failed: {exc}")
        return None, blockers
    if not isinstance(risk_manager, RiskManager):
        blockers.append("risk-manager source factory did not return a trader.risk.RiskManager")
        return None, blockers
    return risk_manager, blockers


def _load_risk_manager_source_module(
    source_ref: RiskManagerCandidateSourceRef,
    candidate_id: str,
    artifact_store: ResearchArtifactStore | None,
) -> object:
    module_name = f"_trader_risk_manager_candidate_{_module_suffix(candidate_id)}"
    if source_ref.uri:
        if artifact_store is None:
            raise ValueError("risk-manager source uri requires a configured research artifact store")
        payload = load_artifact_ref(artifact_store, RISK_MANAGER_IMPLEMENTATION, source_ref.uri)
        source_code = str(payload.get("source_code") or "")
        if not source_code:
            raise ValueError("risk-manager source DB artifact source_code is required")
        return load_module_from_source(module_name, source_code, filename=source_ref.uri)
    if not source_ref.path:
        raise ValueError("risk-manager source path or uri is required")
    source_path = Path(source_ref.path)
    from importlib import util as importlib_util

    spec = importlib_util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load risk-manager source module: {source_path}")
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_fixture_smoke(
    risk_manager: RiskManager,
    manifest: RiskManagerCandidateManifest,
) -> tuple[dict[str, Any], list[str]]:
    orders = _fixture_orders()
    context = _fixture_context()
    try:
        approved, rejected = risk_manager.evaluate(orders, context)
    except Exception as exc:
        return _fixture_summary(status="failed", approved=(), rejected=(), manifest=manifest), [
            f"risk-manager fixture smoke check failed: {exc}"
        ]

    blockers: list[str] = []
    approved_list = list(approved)
    rejected_list = list(rejected)
    for index, order in enumerate([*approved_list, *rejected_list]):
        blockers.extend(_order_blockers(index, order))
    for index, order in enumerate(rejected_list):
        if str(order.get("rejection_reason") or "").strip() == "":
            blockers.append(f"fixture rejected order {index} missing rejection_reason")
    status = "passed" if not blockers else "failed"
    return _fixture_summary(status=status, approved=approved_list, rejected=rejected_list, manifest=manifest), blockers


def _fixture_orders() -> tuple[Mapping[str, object], ...]:
    return (
        {"symbol": "SYNTH_A", "side": "buy", "qty": 1.0, "order_type": "market", "price": 100.0},
        {"symbol": "SYNTH_B", "side": "buy", "qty": 2.0, "order_type": "market", "price": 110.0},
        {"symbol": "SYNTH_C", "side": "sell", "qty": 1.0, "order_type": "market", "price": 90.0},
    )


def _fixture_context() -> RiskContext:
    decision_ts = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    return RiskContext(
        positions={
            "SYNTH_A": Position(symbol="SYNTH_A", qty=0.0, avg_price=None),
            "SYNTH_B": Position(symbol="SYNTH_B", qty=1.0, avg_price=105.0),
            "SYNTH_C": Position(symbol="SYNTH_C", qty=1.0, avg_price=95.0),
        },
        open_orders=(),
        price_lookup={"SYNTH_A": 100.0, "SYNTH_B": 110.0, "SYNTH_C": 90.0},
        run_id="risk_manager_candidate_validation",
        cycle_id=RISK_MANAGER_VALIDATION_FIXTURE_ID,
        decision_ts=decision_ts,
    )


def _fixture_summary(
    *,
    status: str,
    approved: Sequence[Mapping[str, object]],
    rejected: Sequence[Mapping[str, object]],
    manifest: RiskManagerCandidateManifest,
) -> dict[str, Any]:
    return {
        "fixture_id": RISK_MANAGER_VALIDATION_FIXTURE_ID,
        "status": status,
        "symbols": list(FIXTURE_SYMBOLS),
        "orders_evaluated": len(approved) + len(rejected),
        "approved_orders": len(approved),
        "rejected_orders": len(rejected),
        "telemetry_required": list(_sequence(manifest.execution_assumptions.get("telemetry_required"))),
    }


def _order_blockers(index: int, order: Mapping[str, object]) -> list[str]:
    blockers: list[str] = []
    symbol = str(order.get("symbol") or "").strip().upper()
    side = str(order.get("side") or "").strip().lower()
    order_type = str(order.get("order_type") or "").strip().lower()
    qty = _numeric_value(order.get("qty"))
    if symbol not in FIXTURE_SYMBOLS:
        blockers.append(f"fixture order {index} has unknown symbol: {symbol}")
    if side not in {"buy", "sell"}:
        blockers.append(f"fixture order {index} side must be buy or sell")
    if order_type != "market":
        blockers.append(f"fixture order {index} order_type must be market")
    if qty is None or qty < 0.0:
        blockers.append(f"fixture order {index} qty must be non-negative numeric")
    return blockers


def _validation_id(
    *,
    manifest: RiskManagerCandidateManifest,
    checks: Sequence[Mapping[str, Any]],
    fixture_summary: Mapping[str, Any],
    status: str,
) -> str:
    return stable_research_id(
        "risk_manager_candidate_validation",
        {
            "candidate_id": manifest.candidate_id,
            "candidate_manifest": manifest.to_dict(),
            "checks": [{"name": check["name"], "status": check["status"]} for check in checks],
            "fixture_summary": fixture_summary,
            "status": status,
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


def _add_blocking_check(
    checks: list[dict[str, Any]],
    blockers: list[str],
    name: str,
    message: str,
) -> None:
    _record_check(checks, blockers, name, (message,))


def _module_suffix(candidate_id: str) -> str:
    suffix = "".join(character for character in candidate_id if character.isalnum())[-16:]
    return suffix or "generated"


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, MappingABC) else {}


def _sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, SequenceABC) and not isinstance(value, (str, bytes)) else ()


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in {float("inf"), float("-inf")} else None
