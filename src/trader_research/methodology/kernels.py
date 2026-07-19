"""Template-restricted C++ kernel artifacts for Quantitative Methods."""

from __future__ import annotations

from trader_research.foundation import ApplicationResult, error_result, success_result
from trader_research.foundation.artifacts import ArtifactReference
from trader_research.methodology.implementation.io import write_json_artifact

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Mapping

from trader_research.foundation import stable_research_id
from trader_research.methodology.implementation.io import file_sha256, load_manifest
from trader_research.methodology.implementation.manifest import (
    INDICATOR_RUNTIME_CONTRACT,
    MethodImplementationManifest,
    mapping,
    parse_datetime,
)
from trader_research.methodology.registry import get_method


MATH_GENERATE_CPP_KERNEL = "math_generate_cpp_kernel"
MATH_COMPILE_KERNEL = "math_compile_kernel"
CXX_KERNEL_SCHEMA_VERSION = "1"
SUPPORTED_KERNEL_METHODS = frozenset({"sma"})
DEFAULT_COMPILER = "c++"
DEFAULT_COMPILE_FLAGS = ("-std=c++17", "-O2", "-fPIC", "-shared", "-Wall", "-Wextra", "-Werror")
ALLOWED_INCLUDES = frozenset({"cstddef"})
FORBIDDEN_SOURCE_PATTERNS = (
    r"\bstd::filesystem\b",
    r"\bstd::fstream\b",
    r"\bstd::ifstream\b",
    r"\bstd::ofstream\b",
    r"\bsystem\s*\(",
    r"\bpopen\s*\(",
    r"\bfork\s*\(",
    r"\bexec[a-z_]*\s*\(",
    r"\bsocket\s*\(",
    r"\bopen\s*\(",
    r"\bcurl_",
    r"\bpqxx\b",
    r"\bsqlite\b",
)


@dataclass(frozen=True)
class CxxKernelManifest:
    """Persisted manifest for one generated or compiled C++ kernel.

    Attributes:
        kernel_id: Stable ID derived from the Python reference and template.
        method_id: Maintained method contract ID.
        status: `generated`, `compiled`, or `compile_failed`.
        python_implementation_id: Validated Python reference implementation ID.
        python_source_hash: Source hash from the Python implementation manifest.
        method_card_ids: Approved method-card IDs inherited from the Python reference.
        method_contract: Method contract inherited from the Python reference.
        runtime_contract: Trader runtime contract for the Python reference.
        template: Template provenance, including ID, path, and hash.
        generated_source: Generated C++ source path and hash.
        build: Build command, compiler, binary, log, and status metadata.
        abi: ABI and binding metadata for later parity work.
        policies: Warmup, NaN, alignment, dtype, lookahead, and safety policy.
    """

    kernel_id: str
    method_id: str
    status: str
    python_implementation_id: str
    python_source_hash: str
    method_card_ids: tuple[str, ...]
    method_contract: Mapping[str, Any]
    runtime_contract: str
    template: Mapping[str, Any]
    generated_source: Mapping[str, Any]
    build: Mapping[str, Any]
    abi: Mapping[str, Any]
    policies: Mapping[str, Any]
    benchmark_summary: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = CXX_KERNEL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize kernel provenance, ABI, safety policy, and build metadata."""
        return {
            "artifact_type": "cxx_kernel_manifest",
            "schema_version": self.schema_version,
            "kernel_id": self.kernel_id,
            "method_id": self.method_id,
            "status": self.status,
            "python_implementation_id": self.python_implementation_id,
            "python_source_hash": self.python_source_hash,
            "method_card_ids": list(self.method_card_ids),
            "method_contract": dict(self.method_contract),
            "runtime_contract": self.runtime_contract,
            "template": dict(self.template),
            "generated_source": dict(self.generated_source),
            "build": dict(self.build),
            "abi": dict(self.abi),
            "policies": dict(self.policies),
            "benchmark_summary": dict(self.benchmark_summary),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CxxKernelManifest":
        """Parse a kernel manifest from JSON-compatible artifact payloads."""
        return cls(
            kernel_id=str(payload.get("kernel_id") or ""),
            method_id=str(payload.get("method_id") or ""),
            status=str(payload.get("status") or "generated"),
            python_implementation_id=str(payload.get("python_implementation_id") or ""),
            python_source_hash=str(payload.get("python_source_hash") or ""),
            method_card_ids=tuple(str(item) for item in _sequence(payload.get("method_card_ids"))),
            method_contract=mapping(payload.get("method_contract")),
            runtime_contract=str(payload.get("runtime_contract") or INDICATOR_RUNTIME_CONTRACT),
            template=mapping(payload.get("template")),
            generated_source=mapping(payload.get("generated_source")),
            build=mapping(payload.get("build")),
            abi=mapping(payload.get("abi")),
            policies=mapping(payload.get("policies")),
            benchmark_summary=mapping(payload.get("benchmark_summary")),
            warnings=tuple(str(item) for item in _sequence(payload.get("warnings"))),
            blockers=tuple(str(item) for item in _sequence(payload.get("blockers"))),
            created_at=parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or CXX_KERNEL_SCHEMA_VERSION),
        )


def generate_cpp_kernel(
    *,
    artifact_root: str | Path,
    implementation_id: str | None = None,
    implementation_manifest: Mapping[str, Any] | None = None,
    template_id: str | None = None,
) -> ApplicationResult:
    """Generate a template-owned C++ kernel source from a validated Python reference.

    The tool accepts either an implementation ID or manifest payload, verifies the
    Python reference has already passed fixture validation, restricts generation to
    supported indicator methods, renders the maintained template, scans the output
    for disallowed includes and calls, and writes a `cxx_kernel_manifest`.
    """
    try:
        python_manifest = _resolve_implementation_manifest(
            artifact_root=artifact_root,
            implementation_id=implementation_id,
            implementation_manifest=implementation_manifest,
        )
    except (FileNotFoundError, ValueError) as exc:
        return _local_error(MATH_GENERATE_CPP_KERNEL, "method_implementation_not_found", str(exc))

    blockers = _python_manifest_blockers(python_manifest)
    selected_template_id = str(template_id or f"{python_manifest.method_id}_scalar_series_v1")
    template = _template_for_method(python_manifest.method_id, selected_template_id)
    if template is None:
        blockers.append(f"unsupported C++ kernel method/template: {python_manifest.method_id}/{selected_template_id}")

    if blockers:
        return _blocked_generation(blockers)

    assert template is not None
    template_text = template.path.read_text(encoding="utf-8")
    generated_text = _render_template(template_text, python_manifest)
    safety_blockers = _source_safety_blockers(generated_text)
    if safety_blockers:
        return _blocked_generation(safety_blockers)

    kernel_id = stable_research_id(
        "cxx_kernel",
        {
            "implementation_id": python_manifest.implementation_id,
            "python_source_hash": python_manifest.source_hash,
            "template_id": template.template_id,
            "template_hash": template.template_hash,
            "method_contract": dict(python_manifest.method_contract),
        },
    )
    source_path = _generated_source_path(artifact_root, kernel_id)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(generated_text, encoding="utf-8")

    manifest = CxxKernelManifest(
        kernel_id=kernel_id,
        method_id=python_manifest.method_id,
        status="generated",
        python_implementation_id=python_manifest.implementation_id,
        python_source_hash=python_manifest.source_hash,
        method_card_ids=python_manifest.method_card_ids,
        method_contract=python_manifest.method_contract,
        runtime_contract=python_manifest.runtime_contract,
        template=template.to_payload(),
        generated_source={
            "path": str(source_path),
            "sha256": file_sha256(source_path),
            "language": "c++",
        },
        build={"status": "not_compiled"},
        abi=_abi_metadata(python_manifest.method_id),
        policies=_kernel_policies(python_manifest),
    )
    manifest_path = _save_kernel_manifest(artifact_root, manifest)
    return success_result(
        command=MATH_GENERATE_CPP_KERNEL,
        data={"cxx_kernel_manifest": manifest.to_dict()},
        artifacts={
            "cxx_kernel_manifest": ArtifactReference(
                artifact_type="cxx_kernel_manifest",
                path=manifest_path,
                metadata={"id": manifest.kernel_id},
            ).to_dict(),
            "cxx_source": ArtifactReference(
                artifact_type="cxx_source",
                path=source_path,
                metadata={"id": manifest.kernel_id, "sha256": manifest.generated_source["sha256"]},
            ).to_dict(),
        },
    )


def compile_cpp_kernel(
    *,
    artifact_root: str | Path,
    kernel_id: str | None = None,
    kernel_manifest: Mapping[str, Any] | None = None,
    compiler: str | None = None,
    timeout_seconds: float = 30.0,
) -> ApplicationResult:
    """Compile one generated C++ kernel in an isolated artifact build directory.

    Compilation uses a fixed safe flag set, verifies the generated source hash
    before invoking the compiler, captures stdout/stderr into a build log, and
    persists an updated kernel manifest with binary metadata or blockers.
    """
    try:
        manifest = _resolve_kernel_manifest(
            artifact_root=artifact_root,
            kernel_id=kernel_id,
            kernel_manifest=kernel_manifest,
        )
    except (FileNotFoundError, ValueError) as exc:
        return _local_error(MATH_COMPILE_KERNEL, "cxx_kernel_not_found", str(exc))

    source_path = Path(str(manifest.generated_source.get("path") or ""))
    blockers = _compile_preflight_blockers(manifest, source_path)
    resolved_compiler = _resolve_compiler(compiler or DEFAULT_COMPILER)
    if resolved_compiler is None:
        blockers.append(f"compiler not found: {compiler or DEFAULT_COMPILER}")
    if blockers:
        return _failed_compile_result(artifact_root, manifest, blockers=blockers)

    assert resolved_compiler is not None
    build_dir = _build_dir(artifact_root, manifest.kernel_id)
    build_dir.mkdir(parents=True, exist_ok=True)
    binary_path = build_dir / f"{manifest.kernel_id}.so"
    build_log_path = build_dir / "build.log"
    command = [resolved_compiler, *DEFAULT_COMPILE_FLAGS, str(source_path), "-o", str(binary_path)]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=build_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1.0, float(timeout_seconds)),
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        stdout = _subprocess_output_text(exc.stdout)
        stderr = _subprocess_output_text(exc.stderr)
        log_text = f"command timed out after {elapsed:.6f}s\n{stdout}\n{stderr}"
        build_log_path.write_text(log_text, encoding="utf-8")
        return _failed_compile_result(
            artifact_root,
            manifest,
            blockers=[f"compile timed out after {timeout_seconds} seconds"],
            build_log_path=build_log_path,
            command=command,
            compiler=resolved_compiler,
            elapsed_seconds=elapsed,
        )

    elapsed = time.perf_counter() - started
    build_log_path.write_text(
        "\n".join(
            (
                "$ " + " ".join(command),
                f"returncode={completed.returncode}",
                "stdout:",
                completed.stdout,
                "stderr:",
                completed.stderr,
            )
        ),
        encoding="utf-8",
    )
    if completed.returncode != 0:
        return _failed_compile_result(
            artifact_root,
            manifest,
            blockers=["compile failed"],
            build_log_path=build_log_path,
            command=command,
            compiler=resolved_compiler,
            elapsed_seconds=elapsed,
        )

    compiler_version = _compiler_version(resolved_compiler)
    updated = replace(
        manifest,
        status="compiled",
        build={
            "status": "compiled",
            "compiler": resolved_compiler,
            "compiler_version": compiler_version,
            "flags": list(DEFAULT_COMPILE_FLAGS),
            "command": command,
            "build_dir": str(build_dir),
            "binary_path": str(binary_path),
            "binary_sha256": file_sha256(binary_path),
            "binary_size_bytes": binary_path.stat().st_size,
            "build_log_path": str(build_log_path),
        },
        benchmark_summary={
            "compile_elapsed_seconds": elapsed,
            "smoke_check": "compile_only",
        },
        blockers=(),
    )
    manifest_path = _save_kernel_manifest(artifact_root, updated)
    return success_result(
        command=MATH_COMPILE_KERNEL,
        data={"cxx_kernel_manifest": updated.to_dict()},
        artifacts={
            "cxx_kernel_manifest": ArtifactReference(
                artifact_type="cxx_kernel_manifest",
                path=manifest_path,
                metadata={"id": updated.kernel_id},
            ).to_dict(),
            "cxx_binary": ArtifactReference(
                artifact_type="cxx_binary",
                path=binary_path,
                metadata={"id": updated.kernel_id, "sha256": updated.build["binary_sha256"]},
            ).to_dict(),
            "cxx_build_log": ArtifactReference(
                artifact_type="cxx_build_log",
                path=build_log_path,
                metadata={"id": updated.kernel_id},
            ).to_dict(),
        },
    )


@dataclass(frozen=True)
class _KernelTemplate:
    template_id: str
    method_id: str
    path: Path
    template_hash: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "method_id": self.method_id,
            "path": str(self.path),
            "sha256": self.template_hash,
        }


def _resolve_implementation_manifest(
    *,
    artifact_root: str | Path,
    implementation_id: str | None,
    implementation_manifest: Mapping[str, Any] | None,
) -> MethodImplementationManifest:
    if implementation_manifest is not None:
        return MethodImplementationManifest.from_dict(implementation_manifest)
    return load_manifest(artifact_root, str(implementation_id or ""))


def _python_manifest_blockers(manifest: MethodImplementationManifest) -> list[str]:
    blockers = []
    if manifest.status != "validated":
        blockers.append("validated Python implementation manifest is required")
    if manifest.runtime_contract != INDICATOR_RUNTIME_CONTRACT:
        blockers.append(f"C++ kernels require {INDICATOR_RUNTIME_CONTRACT}, got {manifest.runtime_contract}")
    if manifest.method_id not in SUPPORTED_KERNEL_METHODS:
        blockers.append(f"unsupported C++ kernel method: {manifest.method_id}")
    entry = get_method(manifest.method_id)
    requires_evidence = manifest.implementation_kind == "generated" or bool(entry and entry.requires_evidence)
    if requires_evidence and not manifest.method_card_ids:
        blockers.append("approved method-card refs are required")
    source_path = Path(manifest.source_path)
    if not source_path.exists():
        blockers.append(f"Python implementation source path does not exist: {source_path}")
    elif file_sha256(source_path) != manifest.source_hash:
        blockers.append("Python implementation source hash does not match manifest")
    return blockers


def _template_for_method(method_id: str, template_id: str) -> _KernelTemplate | None:
    if method_id != "sma" or template_id != "sma_scalar_series_v1":
        return None
    template_path = Path(__file__).resolve().parents[2] / "trader_standard" / "indicators" / "cpp" / "sma_kernel.cpp.template"
    if not template_path.exists():
        return None
    return _KernelTemplate(
        template_id=template_id,
        method_id=method_id,
        path=template_path,
        template_hash=file_sha256(template_path),
    )


def _render_template(template_text: str, manifest: MethodImplementationManifest) -> str:
    parameters = mapping(manifest.method_contract.get("parameters"))
    return (
        template_text.replace("{{METHOD_ID}}", manifest.method_id)
        .replace("{{PYTHON_IMPLEMENTATION_ID}}", manifest.implementation_id)
        .replace("{{PYTHON_SOURCE_HASH}}", manifest.source_hash)
        .replace("{{DEFAULT_PERIOD}}", str(int(parameters.get("period", manifest.constructor_kwargs.get("period", 0) or 0))))
    )


def _source_safety_blockers(source_text: str) -> list[str]:
    blockers = []
    includes = re.findall(r"^\s*#include\s*[<\"]([^>\"]+)[>\"]", source_text, flags=re.MULTILINE)
    for include in includes:
        if include not in ALLOWED_INCLUDES:
            blockers.append(f"disallowed include: {include}")
    for pattern in FORBIDDEN_SOURCE_PATTERNS:
        if re.search(pattern, source_text):
            blockers.append(f"forbidden C++ source pattern: {pattern}")
    return blockers


def _blocked_generation(blockers: list[str]) -> ApplicationResult:
    return error_result(
        command=MATH_GENERATE_CPP_KERNEL,
        code="cpp_kernel_generation_failed",
        message="C++ kernel generation failed",
        data={"blockers": list(dict.fromkeys(blockers))},
    )


def _kernel_policies(manifest: MethodImplementationManifest) -> Mapping[str, Any]:
    return {
        "warmup": manifest.method_contract.get("warmup_behavior") or manifest.method_contract.get("warmup") or "period - 1 observations",
        "nan_policy": manifest.method_contract.get("nan_policy") or "propagate",
        "alignment": "latest_first_input_latest_first_output",
        "dtype": "float64",
        "no_lookahead": bool(manifest.method_contract.get("no_lookahead", True)),
        "safety": {
            "template_restricted": True,
            "no_network": True,
            "no_filesystem_mutation": True,
            "no_sql": True,
            "no_broker_access": True,
            "no_process_execution": True,
        },
    }


def _abi_metadata(method_id: str) -> Mapping[str, Any]:
    if method_id == "sma":
        return {
            "abi": "extern_c",
            "function": "trader_sma_kernel_v1",
            "inputs": [
                {"name": "latest_first_closes", "type": "const double*", "order": "latest_first"},
                {"name": "count", "type": "size_t"},
                {"name": "period", "type": "int"},
                {"name": "latest_first_output", "type": "double*", "order": "latest_first"},
                {"name": "output_count", "type": "size_t"},
            ],
            "return": "non-negative output count or negative error code",
            "binding": "ctypes_ready",
        }
    return {}


def _resolve_kernel_manifest(
    *,
    artifact_root: str | Path,
    kernel_id: str | None,
    kernel_manifest: Mapping[str, Any] | None,
) -> CxxKernelManifest:
    if kernel_manifest is not None:
        return CxxKernelManifest.from_dict(kernel_manifest)
    if not kernel_id:
        raise ValueError("kernel_id is required")
    path = _kernel_manifest_path(artifact_root, kernel_id)
    if not path.exists():
        raise FileNotFoundError(f"unknown kernel_id: {kernel_id}")
    return CxxKernelManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _compile_preflight_blockers(manifest: CxxKernelManifest, source_path: Path) -> list[str]:
    blockers = []
    if manifest.status not in {"generated", "compile_failed", "compiled"}:
        blockers.append(f"kernel manifest status is not compilable: {manifest.status}")
    if not source_path.exists():
        blockers.append(f"generated source path does not exist: {source_path}")
        return blockers
    expected_hash = str(manifest.generated_source.get("sha256") or "")
    actual_hash = file_sha256(source_path)
    if expected_hash != actual_hash:
        blockers.append("generated source hash does not match manifest")
    blockers.extend(_source_safety_blockers(source_path.read_text(encoding="utf-8")))
    return blockers


def _resolve_compiler(compiler: str) -> str | None:
    compiler_path = Path(compiler)
    if compiler_path.is_absolute() or "/" in compiler:
        return str(compiler_path) if compiler_path.exists() else None
    return shutil.which(compiler)


def _subprocess_output_text(value: str | bytes | None) -> str:
    """Normalize timeout output emitted before text-mode decoding completed."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _compiler_version(compiler: str) -> str:
    try:
        completed = subprocess.run(
            [compiler, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return (completed.stdout or completed.stderr).splitlines()[0] if (completed.stdout or completed.stderr) else "unknown"


def _failed_compile_result(
    artifact_root: str | Path,
    manifest: CxxKernelManifest,
    *,
    blockers: list[str],
    build_log_path: Path | None = None,
    command: list[str] | None = None,
    compiler: str | None = None,
    elapsed_seconds: float | None = None,
) -> ApplicationResult:
    build = dict(manifest.build)
    build.update(
        {
            "status": "compile_failed",
            "compiler": compiler,
            "flags": list(DEFAULT_COMPILE_FLAGS),
            "command": command or [],
            "build_log_path": str(build_log_path) if build_log_path is not None else None,
        }
    )
    updated = replace(
        manifest,
        status="compile_failed",
        build=build,
        benchmark_summary={"compile_elapsed_seconds": elapsed_seconds} if elapsed_seconds is not None else {},
        blockers=tuple(list(dict.fromkeys(blockers))),
    )
    manifest_path = _save_kernel_manifest(artifact_root, updated)
    artifacts = {
        "cxx_kernel_manifest": ArtifactReference(
            artifact_type="cxx_kernel_manifest",
            path=manifest_path,
            metadata={"id": updated.kernel_id},
        ).to_dict()
    }
    if build_log_path is not None:
        artifacts["cxx_build_log"] = ArtifactReference(
            artifact_type="cxx_build_log",
            path=build_log_path,
            metadata={"id": updated.kernel_id},
        ).to_dict()
    return error_result(
        command=MATH_COMPILE_KERNEL,
        code="cpp_kernel_compile_failed",
        message="C++ kernel compile failed",
        data={
            "cxx_kernel_manifest": updated.to_dict(),
            "artifacts": artifacts,
            "blockers": updated.blockers,
        },
    )


def _local_error(command: str, code: str, message: str) -> ApplicationResult:
    return error_result(
        command=command,
        code=code,
        message=message,
    )


def _cpp_kernel_root(artifact_root: str | Path) -> Path:
    return Path(artifact_root) / "cpp_kernels"


def _generated_source_path(artifact_root: str | Path, kernel_id: str) -> Path:
    return _cpp_kernel_root(artifact_root) / "sources" / f"{kernel_id}.cpp"


def _kernel_manifest_path(artifact_root: str | Path, kernel_id: str) -> Path:
    return _cpp_kernel_root(artifact_root) / "manifests" / f"{kernel_id}.json"


def _build_dir(artifact_root: str | Path, kernel_id: str) -> Path:
    return _cpp_kernel_root(artifact_root) / "build" / kernel_id


def _save_kernel_manifest(artifact_root: str | Path, manifest: CxxKernelManifest) -> Path:
    return write_json_artifact(manifest.to_dict(), _kernel_manifest_path(artifact_root, manifest.kernel_id))


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)
