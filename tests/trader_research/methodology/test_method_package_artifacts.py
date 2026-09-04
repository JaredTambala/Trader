"""Contracts for packaging validated computational method artifacts.

Subject: Immutable packages joining exact implementations, validation reports, and optional kernels.
Level: In-process artifact contract.
Collaborators: Method registration, fixture validation, JSON method cards, and local artifact files.
Guarantees: Packages resolve exact evidence, remain idempotent, and exclude invalid optional kernels.
Non-goals: Strategy admission, experiment execution, kernel compilation, Postgres, or agent decisions.
"""

from __future__ import annotations

import json
from pathlib import Path

from trader_research.knowledge.approved_cards import StoreBackedApprovedMethodCardReader
from trader_research.knowledge.domain import EvidenceReference, MethodCard
from trader_research.knowledge.store import JsonKnowledgeStore
from trader_research.methodology import (
    math_package_method_artifact,
    math_register_method_implementation,
    math_run_indicator_fixtures,
    math_run_signal_fixtures,
)
from trader_research.methodology.packaging import MethodPackageManifest


def test_package_validated_indicator_method_artifact(tmp_path: Path) -> None:
    """A validated indicator produces an idempotent, fully linked method package."""
    artifact_root = tmp_path / "artifacts"
    manifest, report = _validated_sma(artifact_root)

    result = math_package_method_artifact(
        artifact_root=artifact_root,
        implementation_manifest=manifest,
        validation_report=report,
    )
    repeated = math_package_method_artifact(
        artifact_root=artifact_root,
        implementation_manifest=manifest,
        validation_report=report,
    )

    assert result.ok is True, result.to_dict()
    package = result.data["method_package_manifest"]
    package_path = Path(result.artifacts["method_package_manifest"]["path"])

    assert package["artifact_type"] == "method_package_manifest"
    assert package["status"] == "validated"
    assert package["method_id"] == "sma"
    assert package["runtime_contract"] == "trader.indicators.Indicator"
    assert package["implementation_id"] == manifest["implementation_id"]
    assert package["source_hash"] == manifest["source_hash"]
    assert package["validation_report_ref"]["validation_id"] == report["validation_id"]
    assert package["validation_summary"]["fixture_count"] == report["fixture_count"]
    assert package["method_card_ids"] == []
    assert package["cxx_kernel_refs"] == []
    assert package_path.exists()
    assert json.loads(package_path.read_text(encoding="utf-8")) == package
    assert MethodPackageManifest.from_dict(package).to_dict() == package
    assert (
        repeated.data["method_package_manifest"]["package_id"] == package["package_id"]
    )


def test_package_validated_signal_method_artifact(tmp_path: Path) -> None:
    """A validated signal package records its exact signal validation report."""
    artifact_root = tmp_path / "artifacts"
    manifest, report = _validated_signal(artifact_root)

    result = math_package_method_artifact(
        artifact_root=artifact_root,
        implementation_manifest=manifest,
        validation_report=report,
    )

    assert result.ok is True, result.to_dict()
    package = result.data["method_package_manifest"]
    assert package["method_id"] == "bollinger_bwma_action_signal"
    assert package["runtime_contract"] == "trader.signals.Signal"
    assert (
        package["validation_report_ref"]["artifact_type"]
        == "signal_implementation_validation_report"
    )


def test_package_resolves_persisted_implementation_and_report_ids(
    tmp_path: Path,
) -> None:
    """Packaging resolves canonical implementation and validation artifacts by stable identifiers."""
    artifact_root = tmp_path / "artifacts"
    manifest, report = _validated_sma(artifact_root)

    result = math_package_method_artifact(
        artifact_root=artifact_root,
        implementation_id=manifest["implementation_id"],
        validation_report_id=report["validation_id"],
    )

    assert result.ok is True, result.to_dict()
    package = result.data["method_package_manifest"]
    assert package["implementation_id"] == manifest["implementation_id"]
    assert package["validation_report_ref"]["path"].endswith(
        f"{report['validation_id']}.json"
    )


def test_package_rejects_invalid_python_gates(tmp_path: Path) -> None:
    """Packaging rejects unvalidated, unsupported, missing, drifted, or mismatched Python evidence."""
    artifact_root = tmp_path / "artifacts"
    registered = _registered_sma(artifact_root)
    validated_manifest, report = _validated_sma(artifact_root)

    cases = [
        (
            {**registered},
            report,
            "validated method implementation manifest is required",
        ),
        (
            {**validated_manifest, "runtime_contract": "custom.Runtime"},
            report,
            "unsupported runtime_contract: custom.Runtime",
        ),
        (
            {**validated_manifest, "source_path": str(tmp_path / "missing.py")},
            report,
            "source path does not exist",
        ),
        (
            {**validated_manifest, "source_hash": "bad"},
            report,
            "source hash does not match method implementation manifest",
        ),
        (
            validated_manifest,
            {**report, "status": "failed", "blockers": ["fixture failed"]},
            "passed validation report is required",
        ),
        (
            validated_manifest,
            {**report, "method_id": "ema"},
            "validation report method_id does not match method implementation manifest",
        ),
        (
            validated_manifest,
            {**report, "artifact_type": "signal_implementation_validation_report"},
            "validation report artifact_type must be indicator_validation_report",
        ),
    ]

    for manifest, validation_report, expected_blocker in cases:
        result = math_package_method_artifact(
            artifact_root=artifact_root,
            implementation_manifest=manifest,
            validation_report=validation_report,
        )
        assert result.ok is False
        assert any(expected_blocker in blocker for blocker in result.data["blockers"])


def test_package_rejects_missing_validation_report(tmp_path: Path) -> None:
    """Packaging fails closed when no validation report can be resolved."""
    artifact_root = tmp_path / "artifacts"
    manifest, _ = _validated_sma(artifact_root)

    result = math_package_method_artifact(
        artifact_root=artifact_root,
        implementation_manifest=manifest,
    )

    assert result.ok is False
    assert (
        "validation_report_id or validation_report is required"
        in result.data["blockers"]
    )


def test_package_handles_optional_cxx_metadata_as_non_gating(tmp_path: Path) -> None:
    """Optional compiled-kernel metadata is included only when its evidence is valid."""
    artifact_root = tmp_path / "artifacts"
    manifest, report = _validated_sma(artifact_root)
    valid_cxx = _compiled_cxx_manifest(manifest)
    generated_cxx = {
        **valid_cxx,
        "status": "generated",
        "build": {"status": "not_compiled"},
    }

    with_cxx = math_package_method_artifact(
        artifact_root=artifact_root,
        implementation_manifest=manifest,
        validation_report=report,
        cxx_kernel_manifest=valid_cxx,
    )
    invalid_cxx = math_package_method_artifact(
        artifact_root=artifact_root,
        implementation_manifest=manifest,
        validation_report=report,
        cxx_kernel_manifest=generated_cxx,
    )

    assert with_cxx.ok is True, with_cxx.to_dict()
    assert (
        with_cxx.data["method_package_manifest"]["cxx_kernel_refs"][0]["kernel_id"]
        == "cxx_kernel_test"
    )
    assert invalid_cxx.ok is True, invalid_cxx.to_dict()
    assert invalid_cxx.data["method_package_manifest"]["cxx_kernel_refs"] == []
    assert any(
        "optional C++ kernel excluded: status must be compiled" in warning
        for warning in invalid_cxx.warnings
    )


def _registered_sma(artifact_root: Path) -> dict[str, object]:
    registered = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id="sma",
        method_card_ids=[],
        method_contract=_contract("sma", {"period": 3}),
    )
    assert registered.ok is True, registered.to_dict()
    return dict(registered.data["method_implementation_manifest"])


def _validated_sma(artifact_root: Path) -> tuple[dict[str, object], dict[str, object]]:
    registered = _registered_sma(artifact_root)
    validated = math_run_indicator_fixtures(
        artifact_root=artifact_root,
        implementation_manifest=registered,
    )
    assert validated.ok is True, validated.to_dict()
    return (
        dict(validated.data["method_implementation_manifest"]),
        dict(validated.data["indicator_validation_report"]),
    )


def _validated_signal(
    artifact_root: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    method_card_id = "method_card_bollinger_bwma_action_signal_algorithmic_trading_v1"
    store = JsonKnowledgeStore(artifact_root)
    store.save_method_card(
        MethodCard(
            method_card_id=method_card_id,
            method_card_set_id="method_card_set_bollinger_bwma_action_signal_package_test",
            revision_number=1,
            method_id="bollinger_bwma_action_signal",
            title="Bollinger BWMA action signal",
            family="signal",
            status="approved",
            assumptions=("input bars are ordered latest first",),
            inputs=("latest-first OHLCV bar window",),
            outputs=("scalar action signal",),
            failure_modes=("insufficient warmup observations",),
            evidence_refs=(
                EvidenceReference(source_id="source_test", chunk_id="chunk_test"),
            ),
            source_methodology_candidate_id="methodology_candidate_bollinger_signal_test",
            validation_refs=(
                {
                    "artifact_type": "methodology_candidate_validation_report",
                    "artifact_id": "validation_bollinger_signal_test",
                },
            ),
            approved_by="test",
            approval_note="Approved for method package test.",
        )
    )
    reader = StoreBackedApprovedMethodCardReader(store)
    registered = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id="bollinger_bwma_action_signal",
        method_card_ids=[method_card_id],
        method_contract=_contract(
            "bollinger_bwma_action_signal",
            {"period": 20, "stddev_multiplier": 2.0},
            method_card_id,
        ),
        approved_card_reader=reader,
    )
    assert registered.ok is True, registered.to_dict()
    validated = math_run_signal_fixtures(
        artifact_root=artifact_root,
        implementation_manifest=registered.data["method_implementation_manifest"],
        approved_card_reader=reader,
    )
    assert validated.ok is True, validated.to_dict()
    return (
        dict(validated.data["method_implementation_manifest"]),
        dict(validated.data["signal_implementation_validation_report"]),
    )


def _contract(
    method_id: str,
    parameters: dict[str, object],
    method_card_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "method_id": method_id,
        "parameters": parameters,
        "no_lookahead": True,
    }
    if method_card_id is not None:
        payload["knowledge_evidence_refs"] = [{"method_card_id": method_card_id}]
    return payload


def _compiled_cxx_manifest(python_manifest: dict[str, object]) -> dict[str, object]:
    return {
        "artifact_type": "cxx_kernel_manifest",
        "kernel_id": "cxx_kernel_test",
        "method_id": python_manifest["method_id"],
        "status": "compiled",
        "python_implementation_id": python_manifest["implementation_id"],
        "python_source_hash": python_manifest["source_hash"],
        "method_card_ids": python_manifest["method_card_ids"],
        "method_contract": python_manifest["method_contract"],
        "runtime_contract": python_manifest["runtime_contract"],
        "template": {"template_id": "sma_scalar_series_v1"},
        "generated_source": {
            "path": "artifacts/research/cpp_kernels/sources/cxx_kernel_test.cpp",
            "sha256": "abc",
        },
        "build": {
            "status": "compiled",
            "binary_path": "artifacts/research/cpp_kernels/build/cxx_kernel_test.so",
        },
        "abi": {"function": "trader_sma_kernel_v1"},
        "policies": {},
        "benchmark_summary": {"smoke_check": "compile_only"},
        "warnings": [],
        "blockers": [],
    }
