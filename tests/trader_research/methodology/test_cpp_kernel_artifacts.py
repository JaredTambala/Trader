"""Contracts for template-restricted C++ kernel generation and compilation.

Subject: Generating, validating, compiling, and diagnosing optional C++ method kernels.
Level: Local adapter and artifact contract.
Collaborators: Validated Python method manifests, temporary files, and the local C++ compiler.
Guarantees: Kernels preserve provenance, reject tampering, and retain actionable build evidence.
Non-goals: Authoring arbitrary C++, benchmarking speed, parity qualification, or strategy admission.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil

import pytest

from trader_research.methodology import (
    math_compile_kernel,
    math_generate_cpp_kernel,
    math_register_method_implementation,
    math_run_indicator_fixtures,
)


def test_generate_cpp_kernel_from_validated_sma_manifest(tmp_path: Path) -> None:
    """A validated SMA implementation deterministically generates a provenance-linked C++ source."""
    artifact_root = tmp_path / "artifacts"
    python_manifest = _validated_sma_manifest(artifact_root)

    result = math_generate_cpp_kernel(
        artifact_root=artifact_root,
        implementation_manifest=python_manifest,
    )

    assert result.ok is True, result.to_dict()
    manifest = result.data["cxx_kernel_manifest"]
    source_path = Path(manifest["generated_source"]["path"])

    assert manifest["artifact_type"] == "cxx_kernel_manifest"
    assert manifest["method_id"] == "sma"
    assert manifest["status"] == "generated"
    assert manifest["python_implementation_id"] == python_manifest["implementation_id"]
    assert manifest["python_source_hash"] == python_manifest["source_hash"]
    assert manifest["template"]["template_id"] == "sma_scalar_series_v1"
    assert manifest["generated_source"]["sha256"]
    assert manifest["abi"]["function"] == "trader_sma_kernel_v1"
    assert manifest["policies"]["safety"]["template_restricted"] is True
    assert source_path.exists()
    assert "trader_sma_kernel_v1" in source_path.read_text(encoding="utf-8")
    assert result.artifacts["cxx_kernel_manifest"]["path"]


def test_generate_cpp_kernel_requires_validated_indicator_manifest(
    tmp_path: Path,
) -> None:
    """Kernel generation rejects unvalidated, unsupported, or wrong-contract manifests without inventing provenance."""
    artifact_root = tmp_path / "artifacts"
    registered = _registered_sma_manifest(artifact_root)
    signal_like_manifest = {
        **_validated_sma_manifest(artifact_root),
        "runtime_contract": "trader.signals.Signal",
    }
    unsupported_manifest = {
        **_validated_sma_manifest(artifact_root),
        "method_id": "ema",
    }
    provenance_neutral_manifest = {
        **_validated_sma_manifest(artifact_root),
        "method_card_ids": [],
    }

    unvalidated = math_generate_cpp_kernel(
        artifact_root=artifact_root, implementation_manifest=registered
    )
    wrong_runtime = math_generate_cpp_kernel(
        artifact_root=artifact_root, implementation_manifest=signal_like_manifest
    )
    unsupported = math_generate_cpp_kernel(
        artifact_root=artifact_root, implementation_manifest=unsupported_manifest
    )
    provenance_neutral = math_generate_cpp_kernel(
        artifact_root=artifact_root,
        implementation_manifest=provenance_neutral_manifest,
    )

    assert unvalidated.ok is False
    assert (
        "validated Python implementation manifest is required"
        in unvalidated.data["blockers"]
    )
    assert wrong_runtime.ok is False
    assert (
        "C++ kernels require trader.indicators.Indicator, got trader.signals.Signal"
        in wrong_runtime.data["blockers"]
    )
    assert unsupported.ok is False
    assert "unsupported C++ kernel method: ema" in unsupported.data["blockers"]
    assert provenance_neutral.ok is True


def test_compile_cpp_kernel_success_when_compiler_available(tmp_path: Path) -> None:
    """The local compiler produces a content-addressed binary from validated generated source."""
    if shutil.which("c++") is None:
        pytest.skip("local C++ compiler not available")
    artifact_root = tmp_path / "artifacts"
    generated = math_generate_cpp_kernel(
        artifact_root=artifact_root,
        implementation_manifest=_validated_sma_manifest(artifact_root),
    )

    result = math_compile_kernel(
        artifact_root=artifact_root,
        kernel_manifest=generated.data["cxx_kernel_manifest"],
        compiler="c++",
    )

    assert result.ok is True, result.to_dict()
    manifest = result.data["cxx_kernel_manifest"]
    binary_path = Path(manifest["build"]["binary_path"])

    assert manifest["status"] == "compiled"
    assert manifest["build"]["status"] == "compiled"
    assert manifest["build"]["binary_sha256"]
    assert manifest["benchmark_summary"]["smoke_check"] == "compile_only"
    assert binary_path.exists()
    assert result.artifacts["cxx_binary"]["path"]


def test_compile_cpp_kernel_reports_missing_compiler_and_tampered_source(
    tmp_path: Path,
) -> None:
    """Compilation reports absent toolchains and refuses source whose hash has changed."""
    artifact_root = tmp_path / "artifacts"
    generated = math_generate_cpp_kernel(
        artifact_root=artifact_root,
        implementation_manifest=_validated_sma_manifest(artifact_root),
    )
    missing_compiler = math_compile_kernel(
        artifact_root=artifact_root,
        kernel_manifest=generated.data["cxx_kernel_manifest"],
        compiler="/missing/cxx",
    )
    source_path = Path(
        generated.data["cxx_kernel_manifest"]["generated_source"]["path"]
    )
    source_path.write_text(
        source_path.read_text(encoding="utf-8") + "\n#include <fstream>\n",
        encoding="utf-8",
    )
    tampered = math_compile_kernel(
        artifact_root=artifact_root,
        kernel_manifest=generated.data["cxx_kernel_manifest"],
        compiler="c++",
    )

    assert missing_compiler.ok is False
    assert "compiler not found: /missing/cxx" in missing_compiler.data["blockers"]
    assert missing_compiler.data["cxx_kernel_manifest"]["status"] == "compile_failed"
    assert tampered.ok is False
    assert "generated source hash does not match manifest" in tampered.data["blockers"]


def test_compile_cpp_kernel_persists_build_log_on_compiler_error(
    tmp_path: Path,
) -> None:
    """Compiler failures retain a readable build log as inspectable evidence."""
    if shutil.which("c++") is None:
        pytest.skip("local C++ compiler not available")
    artifact_root = tmp_path / "artifacts"
    generated = math_generate_cpp_kernel(
        artifact_root=artifact_root,
        implementation_manifest=_validated_sma_manifest(artifact_root),
    )
    manifest = generated.data["cxx_kernel_manifest"]
    source_path = Path(manifest["generated_source"]["path"])
    invalid_source = "int broken = ;\n"
    source_path.write_text(invalid_source, encoding="utf-8")
    manifest = {
        **manifest,
        "generated_source": {
            **manifest["generated_source"],
            "sha256": hashlib.sha256(invalid_source.encode("utf-8")).hexdigest(),
        },
    }

    result = math_compile_kernel(
        artifact_root=artifact_root,
        kernel_manifest=manifest,
        compiler="c++",
    )

    assert result.ok is False
    assert "compile failed" in result.data["blockers"]
    build_log_path = Path(result.data["artifacts"]["cxx_build_log"]["path"])
    assert build_log_path.exists()
    assert "returncode=" in build_log_path.read_text(encoding="utf-8")


def _registered_sma_manifest(artifact_root: Path) -> dict[str, object]:
    registered = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id="sma",
        method_card_ids=[],
        method_contract=_sma_contract(),
    )
    assert registered.ok is True, registered.to_dict()
    return dict(registered.data["method_implementation_manifest"])


def _validated_sma_manifest(artifact_root: Path) -> dict[str, object]:
    registered = _registered_sma_manifest(artifact_root)
    validated = math_run_indicator_fixtures(
        artifact_root=artifact_root,
        implementation_manifest=registered,
    )
    assert validated.ok is True, validated.to_dict()
    return dict(validated.data["method_implementation_manifest"])


def _sma_contract() -> dict[str, object]:
    return {
        "method_id": "sma",
        "parameters": {"period": 3},
        "no_lookahead": True,
    }
