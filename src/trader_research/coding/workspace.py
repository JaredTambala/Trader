"""Deterministic isolated-workspace services for research code authoring.

Workspace file operations are path- and size-bounded. Candidate checks are
delegated to an injected container runner; this module never executes generated
source in the host interpreter or through an arbitrary shell.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Protocol

from trader_research.foundation import (
    ApplicationResult,
    error_result,
    stable_research_id,
    success_result,
)

from .domain import (
    SUPPORTED_CANDIDATE_SUFFIXES,
    SUPPORTED_CODING_CHECKS,
    CodingWorkspacePolicy,
    ContainerExecution,
)


CODING_CREATE_WORKSPACE = "coding_create_workspace"
CODING_GET_WORKSPACE = "coding_get_workspace"
CODING_SEARCH_REPOSITORY = "coding_search_repository"
CODING_READ_REPOSITORY_FILE = "coding_read_repository_file"
CODING_WRITE_CANDIDATE_FILE = "coding_write_candidate_file"
CODING_READ_CANDIDATE_FILE = "coding_read_candidate_file"
CODING_RESOLVE_DEPENDENCIES = "coding_resolve_dependencies"
CODING_RUN_CHECK = "coding_run_check"
CODING_PACKAGE_CANDIDATE = "coding_package_candidate"
CODING_DESTROY_WORKSPACE = "coding_destroy_workspace"

_MANIFEST_NAME = "workspace.json"
_CANDIDATE_DIRECTORY = "candidate"
_SEARCHABLE_REPOSITORY_SUFFIXES = frozenset({".py", ".md", ".toml", ".json", ".yaml", ".yml"})


class ContainerRunner(Protocol):
    """Execute one named check in an isolated candidate container."""

    def run(
        self,
        *,
        workspace_path: Path,
        check_name: str,
        timeout_seconds: int,
        max_output_bytes: int,
    ) -> ContainerExecution:
        """Run one allowlisted check without host execution authority."""


@dataclass(frozen=True)
class DockerContainerRunner:
    """Run allowlisted checks through a locked-down Docker-compatible CLI.

    Attributes:
        container_image: Pinned image containing Trader test dependencies.
        executable: Docker-compatible command name or absolute path.
        memory_limit: Container memory ceiling.
        cpu_limit: Container CPU ceiling.
        pids_limit: Container process-count ceiling.
    """

    container_image: str
    executable: str = "docker"
    memory_limit: str = "512m"
    cpu_limit: str = "1.0"
    pids_limit: int = 128

    def run(
        self,
        *,
        workspace_path: Path,
        check_name: str,
        timeout_seconds: int,
        max_output_bytes: int,
    ) -> ContainerExecution:
        """Run an allowlisted command in a networkless read-only container.

        Args:
            workspace_path: Exact workspace mounted read-only at `/workspace`.
            check_name: One supported check identity.
            timeout_seconds: Positive host-enforced deadline.
            max_output_bytes: Per-stream capture limit.

        Returns:
            Bounded exit, output, timeout, and isolation metadata.

        Raises:
            ValueError: If the requested check or timeout is invalid.
            RuntimeError: If the container executable is unavailable.
        """
        command = _container_check_command(check_name)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        executable = shutil.which(self.executable)
        if executable is None:
            raise RuntimeError(f"container executable is unavailable: {self.executable}")
        invocation = [
            executable,
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(self.pids_limit),
            "--memory",
            self.memory_limit,
            "--cpus",
            self.cpu_limit,
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--mount",
            f"type=bind,src={workspace_path},dst=/workspace,readonly",
            "--workdir",
            "/workspace/candidate",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONPYCACHEPREFIX=/tmp/pycache",
            self.container_image,
            *command,
        ]
        try:
            completed = subprocess.run(
                invocation,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return ContainerExecution(
                exit_code=None,
                stdout=_bounded_text(exc.stdout, max_output_bytes),
                stderr=_bounded_text(exc.stderr, max_output_bytes),
                timed_out=True,
                metadata=_runner_metadata(self, check_name),
            )
        return ContainerExecution(
            exit_code=completed.returncode,
            stdout=_bounded_text(completed.stdout, max_output_bytes),
            stderr=_bounded_text(completed.stderr, max_output_bytes),
            metadata=_runner_metadata(self, check_name),
        )


class CodingWorkspaceService:
    """Manage bounded candidate files and isolated deterministic checks.

    Attributes:
        policy: Validated repository, workspace, dependency, image, and resource
            policy.
        runner: Optional isolated check runner. Check requests fail closed when
            no runner is configured.
    """

    def __init__(
        self,
        policy: CodingWorkspacePolicy,
        *,
        runner: ContainerRunner | None = None,
    ) -> None:
        """Initialize the service without creating a workspace.

        Args:
            policy: Validated coding workspace policy.
            runner: Optional container runner for allowlisted checks.
        """
        self.policy = policy
        self.runner = runner

    def create_workspace(
        self,
        *,
        attempt_id: str,
        build_contract_id: str,
    ) -> ApplicationResult:
        """Create or idempotently reopen one candidate-attempt workspace.

        The workspace contains only a service-owned manifest and writable
        candidate directory. The product repository remains outside it and is
        exposed only through bounded read operations.

        Args:
            attempt_id: Immutable candidate-attempt identity.
            build_contract_id: Exact normalized build-contract identity.

        Returns:
            Public workspace identity and policy summary.
        """
        try:
            normalized_attempt = _required_identifier(attempt_id, "attempt_id")
            normalized_contract = _required_identifier(build_contract_id, "build_contract_id")
            workspace_id = stable_research_id(
                "coding_workspace",
                {
                    "attempt_id": normalized_attempt,
                    "build_contract_id": normalized_contract,
                    "repository_revision": self.policy.repository_revision,
                },
            )
            workspace_path = self._workspace_path(workspace_id)
            manifest = {
                "workspace_id": workspace_id,
                "attempt_id": normalized_attempt,
                "build_contract_id": normalized_contract,
                "repository_revision": self.policy.repository_revision,
                "status": "active",
            }
            if workspace_path.exists():
                existing = self._load_manifest(workspace_id)
                if existing != manifest:
                    raise ValueError("workspace identity resolves to conflicting manifest")
            else:
                (workspace_path / _CANDIDATE_DIRECTORY).mkdir(parents=True)
                self._write_manifest(workspace_path, manifest)
        except (OSError, ValueError) as exc:
            return error_result(
                command=CODING_CREATE_WORKSPACE,
                code="workspace_creation_failed",
                message=str(exc),
            )
        return success_result(
            command=CODING_CREATE_WORKSPACE,
            data={"workspace": {**manifest, "policy": self.policy.public_summary()}},
        )

    def get_workspace(self, workspace_id: str) -> ApplicationResult:
        """Return bounded status for one exact workspace identity."""
        try:
            manifest = self._load_manifest(workspace_id)
            files = self._candidate_files(workspace_id)
        except (OSError, ValueError) as exc:
            return error_result(
                command=CODING_GET_WORKSPACE,
                code="workspace_resolution_failed",
                message=str(exc),
            )
        return success_result(
            command=CODING_GET_WORKSPACE,
            data={
                "workspace": {
                    **manifest,
                    "candidate_files": files,
                    "policy": self.policy.public_summary(),
                }
            },
        )

    def search_repository(
        self,
        *,
        query: str,
        roots: Sequence[str] = ("src/trader", "src/trader_standard", "docs/python_code_quality.md"),
        limit: int = 20,
    ) -> ApplicationResult:
        """Search bounded text files in the pinned read-only repository.

        Args:
            query: Required case-insensitive literal query.
            roots: Approved repository-relative files or directories.
            limit: Maximum matching lines returned across all files.

        Returns:
            Repository revision plus bounded path, line, and excerpt matches.
        """
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return error_result(
                command=CODING_SEARCH_REPOSITORY,
                code="invalid_repository_query",
                message="query is required",
            )
        if not 1 <= int(limit) <= 100:
            return error_result(
                command=CODING_SEARCH_REPOSITORY,
                code="invalid_repository_query",
                message="limit must be between 1 and 100",
            )
        try:
            candidates = self._repository_files(roots)
            matches = _search_files(candidates, self.policy.repository_root, normalized_query, int(limit))
        except (OSError, ValueError, UnicodeError) as exc:
            return error_result(
                command=CODING_SEARCH_REPOSITORY,
                code="repository_search_failed",
                message=str(exc),
            )
        return success_result(
            command=CODING_SEARCH_REPOSITORY,
            data={
                "repository_revision": self.policy.repository_revision,
                "query": normalized_query,
                "match_count": len(matches),
                "matches": matches,
            },
        )

    def read_repository_file(
        self,
        relative_path: str,
        *,
        max_bytes: int = 64_000,
    ) -> ApplicationResult:
        """Read one approved text file from the pinned repository snapshot."""
        try:
            path = _safe_relative_file(
                self.policy.repository_root,
                relative_path,
                allowed_suffixes=_SEARCHABLE_REPOSITORY_SUFFIXES,
            )
            content = _read_bounded_text(path, max_bytes=max_bytes)
        except (OSError, ValueError, UnicodeError) as exc:
            return error_result(
                command=CODING_READ_REPOSITORY_FILE,
                code="repository_read_failed",
                message=str(exc),
            )
        return success_result(
            command=CODING_READ_REPOSITORY_FILE,
            data={
                "repository_revision": self.policy.repository_revision,
                "relative_path": path.relative_to(self.policy.repository_root).as_posix(),
                "content": content,
                "content_sha256": sha256(content.encode("utf-8")).hexdigest(),
            },
        )

    def write_candidate_file(
        self,
        workspace_id: str,
        relative_path: str,
        content: str,
    ) -> ApplicationResult:
        """Write one bounded candidate file inside an active workspace.

        Args:
            workspace_id: Exact active workspace identity.
            relative_path: Candidate-relative path with an allowed suffix.
            content: Complete replacement text for the file.

        Returns:
            Exact path-independent content hash and updated workspace byte use.
        """
        try:
            self._require_active_workspace(workspace_id)
            encoded = str(content).encode("utf-8")
            if len(encoded) > self.policy.max_file_bytes:
                raise ValueError("candidate file exceeds max_file_bytes")
            candidate_root = self._candidate_root(workspace_id)
            path = _safe_relative_target(
                candidate_root,
                relative_path,
                allowed_suffixes=SUPPORTED_CANDIDATE_SUFFIXES,
            )
            existing_size = path.stat().st_size if path.exists() else 0
            current_size = self._workspace_size(candidate_root)
            if current_size - existing_size + len(encoded) > self.policy.max_workspace_bytes:
                raise ValueError("candidate workspace exceeds max_workspace_bytes")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(content), encoding="utf-8")
        except (OSError, ValueError, UnicodeError) as exc:
            return error_result(
                command=CODING_WRITE_CANDIDATE_FILE,
                code="candidate_write_failed",
                message=str(exc),
            )
        return success_result(
            command=CODING_WRITE_CANDIDATE_FILE,
            data={
                "workspace_id": workspace_id,
                "relative_path": path.relative_to(candidate_root).as_posix(),
                "content_sha256": sha256(encoded).hexdigest(),
                "content_bytes": len(encoded),
                "workspace_bytes": self._workspace_size(candidate_root),
            },
        )

    def read_candidate_file(
        self,
        workspace_id: str,
        relative_path: str,
    ) -> ApplicationResult:
        """Read one bounded candidate file from an active workspace."""
        try:
            self._require_active_workspace(workspace_id)
            candidate_root = self._candidate_root(workspace_id)
            path = _safe_relative_file(
                candidate_root,
                relative_path,
                allowed_suffixes=SUPPORTED_CANDIDATE_SUFFIXES,
            )
            content = _read_bounded_text(path, max_bytes=self.policy.max_file_bytes)
        except (OSError, ValueError, UnicodeError) as exc:
            return error_result(
                command=CODING_READ_CANDIDATE_FILE,
                code="candidate_read_failed",
                message=str(exc),
            )
        return success_result(
            command=CODING_READ_CANDIDATE_FILE,
            data={
                "workspace_id": workspace_id,
                "relative_path": path.relative_to(candidate_root).as_posix(),
                "content": content,
                "content_sha256": sha256(content.encode("utf-8")).hexdigest(),
            },
        )

    def resolve_dependencies(
        self,
        workspace_id: str,
        dependencies: Sequence[str],
    ) -> ApplicationResult:
        """Validate dependency names against the pinned workspace policy.

        This operation does not install packages. The accepted container image
        must already contain every approved dependency at its pinned version.
        """
        try:
            self._require_active_workspace(workspace_id)
            requested = tuple(
                dict.fromkeys(
                    dependency
                    for item in dependencies
                    if (dependency := str(item or "").strip())
                )
            )
            denied = sorted(set(requested) - set(self.policy.allowed_dependencies))
            if denied:
                raise ValueError("dependencies are not allowed: " + ", ".join(denied))
        except (OSError, ValueError) as exc:
            return error_result(
                command=CODING_RESOLVE_DEPENDENCIES,
                code="dependency_policy_denied",
                message=str(exc),
            )
        return success_result(
            command=CODING_RESOLVE_DEPENDENCIES,
            data={
                "workspace_id": workspace_id,
                "dependencies": list(requested),
                "resolution": "preinstalled_in_pinned_container",
                "container_image": self.policy.container_image,
            },
        )

    def run_check(
        self,
        workspace_id: str,
        check_name: str,
        *,
        timeout_seconds: int | None = None,
    ) -> ApplicationResult:
        """Run one allowlisted check through the configured isolated runner."""
        try:
            self._require_active_workspace(workspace_id)
            normalized_check = str(check_name or "").strip()
            if normalized_check not in SUPPORTED_CODING_CHECKS:
                raise ValueError(f"unsupported coding check: {normalized_check}")
            if self.runner is None:
                raise RuntimeError("isolated container runner is not configured")
            timeout = timeout_seconds or self.policy.default_timeout_seconds
            execution = self.runner.run(
                workspace_path=self._workspace_path(workspace_id),
                check_name=normalized_check,
                timeout_seconds=int(timeout),
                max_output_bytes=self.policy.max_output_bytes,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return error_result(
                command=CODING_RUN_CHECK,
                code="coding_check_unavailable",
                message=str(exc),
            )
        payload = {
            "workspace_id": workspace_id,
            "check_name": normalized_check,
            "status": "passed" if execution.exit_code == 0 and not execution.timed_out else "failed",
            **execution.to_dict(),
        }
        if payload["status"] == "passed":
            return success_result(command=CODING_RUN_CHECK, data={"check": payload})
        return error_result(
            command=CODING_RUN_CHECK,
            code="coding_check_failed",
            message=("coding check timed out" if execution.timed_out else "coding check returned non-zero"),
            data={"check": payload},
        )

    def package_candidate(
        self,
        workspace_id: str,
        *,
        implementation_path: str = "implementation.py",
    ) -> ApplicationResult:
        """Build a content-addressed inert package from exact candidate files.

        Python syntax is parsed without importing or executing the candidate.
        The package remains transport evidence until ordinary implementation
        registration and independent admission persist canonical artifacts.
        """
        try:
            self._require_active_workspace(workspace_id)
            candidate_root = self._candidate_root(workspace_id)
            implementation_file = _safe_relative_file(
                candidate_root,
                implementation_path,
                allowed_suffixes=frozenset({".py"}),
            )
            source_code = _read_bounded_text(
                implementation_file,
                max_bytes=self.policy.max_file_bytes,
            )
            ast.parse(source_code, filename=implementation_path)
            files = []
            for path in sorted(item for item in candidate_root.rglob("*") if item.is_file()):
                relative_path = path.relative_to(candidate_root).as_posix()
                content = path.read_bytes()
                files.append(
                    {
                        "relative_path": relative_path,
                        "content_sha256": sha256(content).hexdigest(),
                        "content_bytes": len(content),
                    }
                )
            package_id = stable_research_id(
                "coding_candidate_package",
                {
                    "workspace_id": workspace_id,
                    "repository_revision": self.policy.repository_revision,
                    "implementation_path": implementation_path,
                    "files": files,
                },
            )
        except (OSError, SyntaxError, UnicodeError, ValueError) as exc:
            return error_result(
                command=CODING_PACKAGE_CANDIDATE,
                code="candidate_packaging_failed",
                message=str(exc),
            )
        return success_result(
            command=CODING_PACKAGE_CANDIDATE,
            data={
                "candidate_package": {
                    "package_id": package_id,
                    "workspace_id": workspace_id,
                    "repository_revision": self.policy.repository_revision,
                    "implementation_path": implementation_path,
                    "source_code": source_code,
                    "source_hash": sha256(source_code.encode("utf-8")).hexdigest(),
                    "files": files,
                    "status": "packaged_inert_candidate",
                }
            },
        )

    def destroy_workspace(self, workspace_id: str) -> ApplicationResult:
        """Permanently remove one exact disposable workspace after validation."""
        try:
            workspace_path = self._workspace_path(workspace_id)
            manifest = self._load_manifest(workspace_id)
            shutil.rmtree(workspace_path)
        except (OSError, ValueError) as exc:
            return error_result(
                command=CODING_DESTROY_WORKSPACE,
                code="workspace_cleanup_failed",
                message=str(exc),
            )
        return success_result(
            command=CODING_DESTROY_WORKSPACE,
            data={
                "workspace_id": manifest["workspace_id"],
                "status": "destroyed",
                "recoverable": False,
            },
        )

    def _workspace_path(self, workspace_id: str) -> Path:
        normalized = _required_identifier(workspace_id, "workspace_id")
        path = (self.policy.workspace_root / normalized).resolve()
        if path.parent != self.policy.workspace_root:
            raise ValueError("workspace_id escapes workspace_root")
        return path

    def _candidate_root(self, workspace_id: str) -> Path:
        return self._workspace_path(workspace_id) / _CANDIDATE_DIRECTORY

    def _load_manifest(self, workspace_id: str) -> dict[str, Any]:
        path = self._workspace_path(workspace_id) / _MANIFEST_NAME
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping) or payload.get("workspace_id") != workspace_id:
            raise ValueError("workspace manifest identity mismatch")
        return dict(payload)

    def _write_manifest(self, workspace_path: Path, manifest: Mapping[str, Any]) -> None:
        (workspace_path / _MANIFEST_NAME).write_text(
            json.dumps(dict(manifest), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _require_active_workspace(self, workspace_id: str) -> Mapping[str, Any]:
        manifest = self._load_manifest(workspace_id)
        if manifest.get("status") != "active":
            raise ValueError("workspace is not active")
        return manifest

    def _candidate_files(self, workspace_id: str) -> list[dict[str, Any]]:
        candidate_root = self._candidate_root(workspace_id)
        return [
            {
                "relative_path": path.relative_to(candidate_root).as_posix(),
                "content_bytes": path.stat().st_size,
            }
            for path in sorted(item for item in candidate_root.rglob("*") if item.is_file())
        ]

    def _repository_files(self, roots: Sequence[str]) -> tuple[Path, ...]:
        files: list[Path] = []
        for root in roots:
            path = _safe_relative_path(self.policy.repository_root, root)
            if path.is_file():
                if path.suffix in _SEARCHABLE_REPOSITORY_SUFFIXES:
                    files.append(path)
                continue
            if not path.is_dir():
                raise ValueError(f"repository search root does not exist: {root}")
            files.extend(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file() and candidate.suffix in _SEARCHABLE_REPOSITORY_SUFFIXES
            )
        return tuple(dict.fromkeys(sorted(files)))

    @staticmethod
    def _workspace_size(candidate_root: Path) -> int:
        return sum(path.stat().st_size for path in candidate_root.rglob("*") if path.is_file())


def _container_check_command(check_name: str) -> list[str]:
    commands = {
        "compile": ["python", "-m", "py_compile", "/workspace/candidate/implementation.py"],
        "ruff": ["ruff", "check", "/workspace/candidate"],
        "pytest": ["pytest", "-q", "/workspace/candidate"],
    }
    try:
        return commands[check_name]
    except KeyError as exc:
        raise ValueError(f"unsupported coding check: {check_name}") from exc


def _runner_metadata(runner: DockerContainerRunner, check_name: str) -> dict[str, Any]:
    return {
        "runner": "docker",
        "container_image": runner.container_image,
        "check_name": check_name,
        "network_enabled": False,
        "root_filesystem_read_only": True,
        "workspace_mount_read_only": True,
        "capabilities_dropped": True,
        "memory_limit": runner.memory_limit,
        "cpu_limit": runner.cpu_limit,
        "pids_limit": runner.pids_limit,
    }


def _bounded_text(value: object, max_bytes: int) -> str:
    if value is None:
        return ""
    encoded = str(value).encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return encoded.decode("utf-8", errors="replace")
    marker = b"\n...[output truncated]"
    return (encoded[: max_bytes - len(marker)] + marker).decode("utf-8", errors="replace")


def _required_identifier(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    if not all(character.isalnum() or character in {"-", "_"} for character in normalized):
        raise ValueError(f"{label} contains unsupported characters")
    return normalized


def _safe_relative_path(root: Path, relative_path: str) -> Path:
    value = str(relative_path or "").strip()
    if not value:
        raise ValueError("relative_path is required")
    candidate = (root / value).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("relative_path escapes its approved root")
    return candidate


def _safe_relative_file(
    root: Path,
    relative_path: str,
    *,
    allowed_suffixes: frozenset[str],
) -> Path:
    candidate = _safe_relative_path(root, relative_path)
    if not candidate.is_file():
        raise ValueError(f"file does not exist: {relative_path}")
    if candidate.suffix not in allowed_suffixes:
        raise ValueError(f"file suffix is not readable: {candidate.suffix}")
    return candidate


def _safe_relative_target(
    root: Path,
    relative_path: str,
    *,
    allowed_suffixes: frozenset[str],
) -> Path:
    candidate = _safe_relative_path(root, relative_path)
    if candidate.suffix not in allowed_suffixes:
        raise ValueError(f"candidate file suffix is not writable: {candidate.suffix}")
    return candidate


def _read_bounded_text(path: Path, *, max_bytes: int) -> str:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if path.stat().st_size > max_bytes:
        raise ValueError(f"file exceeds read limit of {max_bytes} bytes")
    return path.read_text(encoding="utf-8")


def _search_files(
    files: Sequence[Path],
    repository_root: Path,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    needle = query.casefold()
    matches: list[dict[str, Any]] = []
    for path in files:
        if path.stat().st_size > 512_000:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if needle not in line.casefold():
                continue
            matches.append(
                {
                    "relative_path": path.relative_to(repository_root).as_posix(),
                    "line": line_number,
                    "excerpt": line[:500],
                }
            )
            if len(matches) >= limit:
                return matches
    return matches
