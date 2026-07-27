"""Fixture runners for registered method implementation manifests."""

from __future__ import annotations

from trader_research.foundation import ApplicationResult, error_result, success_result
from trader_research.foundation.artifacts import ArtifactReference
from trader_research.methodology.implementation.io import write_json_artifact

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader.indicators import Indicator
from trader.signals import Signal

from trader_research.foundation.artifacts import ResearchArtifactStore, load_artifact_ref
from trader_research.foundation import stable_research_id
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    METHOD_IMPLEMENTATION_MANIFEST,
)
from trader_research.knowledge.approved_cards import ApprovedMethodCardReader
from trader_research.methodology.implementation.fixture_defaults import default_indicator_fixtures, default_signal_fixtures
from trader_research.methodology.implementation.fixture_helpers import run_indicator_fixture, run_signal_fixture
from trader_research.methodology.implementation.io import (
    load_manifest,
    local_mutating_error,
    save_manifest,
    validation_report_path,
)
from trader_research.methodology.implementation.manifest import (
    INDICATOR_RUNTIME_CONTRACT,
    MATH_RUN_INDICATOR_FIXTURES,
    MATH_RUN_SIGNAL_FIXTURES,
    SCHEMA_VERSION,
    SIGNAL_RUNTIME_CONTRACT,
    MethodImplementationManifest,
)
from trader_research.methodology.implementation.registration import _load_implementation_class, register_method_implementation


def run_indicator_fixtures(
    *,
    artifact_root: str | Path,
    implementation_id: str | None = None,
    implementation_manifest: Mapping[str, Any] | None = None,
    fixtures: Sequence[Mapping[str, Any]] | None = None,
    approved_card_reader: ApprovedMethodCardReader | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Validate an indicator implementation manifest against deterministic fixtures.

    The runner resolves a manifest from an ID or payload, revalidates registration
    before execution, enforces the indicator runtime contract, loads the class,
    applies default or caller-provided fixtures, and writes a validation report.
    Load, contract, or fixture mismatches are returned as local-mutating error
    results with artifact-ready diagnostics.
    """
    try:
        manifest = _resolve_manifest(
            artifact_root=artifact_root,
            implementation_id=implementation_id,
            implementation_manifest=implementation_manifest,
            artifact_store=artifact_store,
        )
    except (FileNotFoundError, ValueError) as exc:
        return local_mutating_error(MATH_RUN_INDICATOR_FIXTURES, "method_implementation_not_found", str(exc))

    register_check = _revalidate_manifest(
        command=MATH_RUN_INDICATOR_FIXTURES,
        artifact_root=artifact_root,
        manifest=manifest,
        approved_card_reader=approved_card_reader,
        artifact_store=artifact_store,
    )
    if not register_check.ok:
        return register_check

    manifest = MethodImplementationManifest.from_dict(register_check.data["method_implementation_manifest"])
    if manifest.runtime_contract != INDICATOR_RUNTIME_CONTRACT:
        return local_mutating_error(
            MATH_RUN_INDICATOR_FIXTURES,
            "invalid_runtime_contract",
            f"indicator fixtures require {INDICATOR_RUNTIME_CONTRACT}, got {manifest.runtime_contract}",
        )
    fixture_payloads = tuple(fixtures or default_indicator_fixtures(manifest.method_id))
    if not fixture_payloads:
        return local_mutating_error(MATH_RUN_INDICATOR_FIXTURES, "fixtures_required", f"no fixtures configured for {manifest.method_id}")

    try:
        implementation = _load_instance(manifest)
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        return local_mutating_error(MATH_RUN_INDICATOR_FIXTURES, "indicator_load_failed", str(exc))
    if not isinstance(implementation, Indicator):
        return local_mutating_error(MATH_RUN_INDICATOR_FIXTURES, "invalid_indicator_contract", "implementation is not an Indicator")

    results, warnings, blockers = _run_fixture_payloads(
        fixture_payloads,
        lambda fixture: run_indicator_fixture(implementation, fixture),
    )
    return _finish_validation(
        artifact_root=artifact_root,
        command=MATH_RUN_INDICATOR_FIXTURES,
        report_artifact_type="indicator_validation_report",
        report_data_key="indicator_validation_report",
        failure_code="indicator_fixture_validation_failed",
        failure_message="indicator fixture validation failed",
        validation_prefix="indicator_validation",
        manifest=manifest,
        results=results,
        warnings=warnings,
        blockers=blockers,
        artifact_store=artifact_store,
    )


def run_signal_fixtures(
    *,
    artifact_root: str | Path,
    implementation_id: str | None = None,
    implementation_manifest: Mapping[str, Any] | None = None,
    fixtures: Sequence[Mapping[str, Any]] | None = None,
    approved_card_reader: ApprovedMethodCardReader | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Validate a signal implementation manifest against deterministic fixtures.

    The runner follows the same manifest resolution and registration recheck as
    indicator validation, then enforces the signal runtime contract and executes
    signal fixtures with prefix/no-lookahead expectations. The final result
    records validation artifacts, warnings, and blockers for review.
    """
    try:
        manifest = _resolve_manifest(
            artifact_root=artifact_root,
            implementation_id=implementation_id,
            implementation_manifest=implementation_manifest,
            artifact_store=artifact_store,
        )
    except (FileNotFoundError, ValueError) as exc:
        return local_mutating_error(MATH_RUN_SIGNAL_FIXTURES, "method_implementation_not_found", str(exc))

    register_check = _revalidate_manifest(
        command=MATH_RUN_SIGNAL_FIXTURES,
        artifact_root=artifact_root,
        manifest=manifest,
        approved_card_reader=approved_card_reader,
        artifact_store=artifact_store,
    )
    if not register_check.ok:
        return register_check

    manifest = MethodImplementationManifest.from_dict(register_check.data["method_implementation_manifest"])
    if manifest.runtime_contract != SIGNAL_RUNTIME_CONTRACT:
        return local_mutating_error(
            MATH_RUN_SIGNAL_FIXTURES,
            "invalid_runtime_contract",
            f"signal fixtures require {SIGNAL_RUNTIME_CONTRACT}, got {manifest.runtime_contract}",
        )
    fixture_payloads = tuple(fixtures or default_signal_fixtures(manifest.method_id))
    if not fixture_payloads:
        return local_mutating_error(MATH_RUN_SIGNAL_FIXTURES, "fixtures_required", f"no signal fixtures configured for {manifest.method_id}")

    try:
        implementation = _load_instance(manifest)
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        return local_mutating_error(MATH_RUN_SIGNAL_FIXTURES, "signal_load_failed", str(exc))
    if not isinstance(implementation, Signal):
        return local_mutating_error(MATH_RUN_SIGNAL_FIXTURES, "invalid_signal_contract", "implementation is not a Signal")

    results, warnings, blockers = _run_fixture_payloads(
        fixture_payloads,
        lambda fixture: run_signal_fixture(implementation, fixture),
    )
    return _finish_validation(
        artifact_root=artifact_root,
        command=MATH_RUN_SIGNAL_FIXTURES,
        report_artifact_type="signal_implementation_validation_report",
        report_data_key="signal_implementation_validation_report",
        failure_code="signal_fixture_validation_failed",
        failure_message="signal fixture validation failed",
        validation_prefix="signal_validation",
        manifest=manifest,
        results=results,
        warnings=warnings,
        blockers=blockers,
        artifact_store=artifact_store,
    )


def _resolve_manifest(
    *,
    artifact_root: str | Path,
    implementation_id: str | None,
    implementation_manifest: Mapping[str, Any] | None,
    artifact_store: ResearchArtifactStore | None,
) -> MethodImplementationManifest:
    if implementation_manifest is not None:
        return MethodImplementationManifest.from_dict(implementation_manifest)
    if artifact_store is not None:
        return MethodImplementationManifest.from_dict(
            load_artifact_ref(artifact_store, METHOD_IMPLEMENTATION_MANIFEST, str(implementation_id or ""))
        )
    return load_manifest(artifact_root, str(implementation_id or ""))


def _revalidate_manifest(
    *,
    command: str,
    artifact_root: str | Path,
    manifest: MethodImplementationManifest,
    approved_card_reader: ApprovedMethodCardReader | None,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    register_check = register_method_implementation(
        artifact_root=artifact_root,
        method_id=manifest.method_id,
        method_card_ids=manifest.method_card_ids,
        method_contract=manifest.method_contract,
        entrypoint=manifest.entrypoint,
        source_path=manifest.source_path,
        class_name=manifest.class_name,
        constructor_kwargs=manifest.constructor_kwargs,
        implementation_kind=manifest.implementation_kind,
        dependency_allowlist=manifest.dependency_allowlist,
        expected_source_hash=manifest.source_hash,
        approved_card_reader=approved_card_reader,
        artifact_store=artifact_store,
    )
    if register_check.ok:
        return register_check
    return error_result(
        command=command,
        code="method_implementation_validation_failed",
        message="method implementation validation failed before fixtures",
        data=register_check.data,
    )


def _load_instance(manifest: MethodImplementationManifest) -> object:
    implementation_class = _load_implementation_class(
        entrypoint=manifest.entrypoint,
        source_path=Path(manifest.source_path) if manifest.implementation_kind == "generated" else None,
        class_name=manifest.class_name,
    )
    return implementation_class(**dict(manifest.constructor_kwargs))


def _run_fixture_payloads(
    fixtures: Sequence[Mapping[str, Any]],
    runner: Any,
) -> tuple[list[Mapping[str, Any]], list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    results = []
    for fixture in fixtures:
        result = runner(fixture)
        results.append(result)
        if result["status"] != "passed":
            blockers.append(f"fixture failed: {result['fixture_id']}")
        warnings.extend(str(warning) for warning in result.get("warnings", ()))
    return results, warnings, blockers


def _finish_validation(
    *,
    artifact_root: str | Path,
    command: str,
    report_artifact_type: str,
    report_data_key: str,
    failure_code: str,
    failure_message: str,
    validation_prefix: str,
    manifest: MethodImplementationManifest,
    results: list[Mapping[str, Any]],
    warnings: list[str],
    blockers: list[str],
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    status = "passed" if not blockers else "failed"
    validation_id = stable_research_id(
        validation_prefix,
        {
            "implementation_id": manifest.implementation_id,
            "source_hash": manifest.source_hash,
            "fixtures": [result["fixture_id"] for result in results],
            "status": status,
        },
    )
    report = {
        "artifact_type": report_artifact_type,
        "schema_version": SCHEMA_VERSION,
        "validation_id": validation_id,
        "implementation_id": manifest.implementation_id,
        "method_id": manifest.method_id,
        "entrypoint": manifest.entrypoint,
        "source_hash": manifest.source_hash,
        "status": status,
        "fixture_count": len(results),
        "fixture_results": results,
        "warnings": warnings,
        "blockers": blockers,
    }
    updated_manifest = replace(manifest, status="validated" if not blockers else "blocked")
    if artifact_store is not None:
        report_record = artifact_store.save_artifact(
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[report_artifact_type],
            producer_tool=command,
            artifact_type=report_artifact_type,
            artifact_id=validation_id,
            payload=report,
            status=status,
            source_hash=manifest.source_hash,
            metadata={"implementation_id": manifest.implementation_id, "method_id": manifest.method_id},
        )
        manifest_record = artifact_store.save_artifact(
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[METHOD_IMPLEMENTATION_MANIFEST],
            producer_tool=command,
            artifact_type=METHOD_IMPLEMENTATION_MANIFEST,
            artifact_id=updated_manifest.implementation_id,
            payload=updated_manifest.to_dict(),
            status=updated_manifest.status,
            source_hash=updated_manifest.source_hash,
            metadata={"method_id": updated_manifest.method_id, "runtime_contract": updated_manifest.runtime_contract},
        )
        manifest_ref = ArtifactReference(
            artifact_type=METHOD_IMPLEMENTATION_MANIFEST,
            uri=manifest_record.uri,
            metadata={"id": updated_manifest.implementation_id},
        ).to_dict()
        report_ref = ArtifactReference(
            artifact_type=report_artifact_type,
            uri=report_record.uri,
            metadata={"id": validation_id},
        ).to_dict()
    else:
        report_path = validation_report_path(artifact_root, validation_id)
        write_json_artifact(report, report_path)
        manifest_path = save_manifest(artifact_root, updated_manifest)
        manifest_ref = ArtifactReference(
            artifact_type=METHOD_IMPLEMENTATION_MANIFEST,
            path=manifest_path,
            metadata={"id": updated_manifest.implementation_id},
        ).to_dict()
        report_ref = ArtifactReference(
            artifact_type=report_artifact_type,
            path=report_path,
            metadata={"id": validation_id},
        ).to_dict()
    data = {
        "method_implementation_manifest": updated_manifest.to_dict(),
        report_data_key: report,
    }
    artifacts = {
        "method_implementation_manifest": manifest_ref,
        report_data_key: report_ref,
    }
    if blockers:
        return error_result(
            command=command,
            code=failure_code,
            message=failure_message,
            data=data,
        )
    return success_result(
        command=command,
        data=data,
        artifacts=artifacts,
        warnings=warnings,
    )
