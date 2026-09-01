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
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time
from typing import Any, Protocol

from trader_research.foundation import (
    ApplicationResult,
    error_result,
    json_payload_hash,
    stable_research_id,
    success_result,
)

from .domain import (
    SUPPORTED_CANDIDATE_SUFFIXES,
    SUPPORTED_CODING_CHECKS,
    CodingWorkspacePolicy,
    ContainerExecution,
    validate_pinned_container_image,
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
_OPERATION_DIRECTORY = ".operations"
_PACKAGE_DIRECTORY = ".packages"
_TOMBSTONE_DIRECTORY = ".destroyed"
_SEARCHABLE_REPOSITORY_SUFFIXES = frozenset(
    {".py", ".md", ".toml", ".json", ".yaml", ".yml"}
)


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
        container_user: Numeric unprivileged user and group inside the image.
        nofile_limit: Maximum open files inside the container.
    """

    container_image: str
    executable: str = "docker"
    memory_limit: str = "512m"
    cpu_limit: str = "1.0"
    pids_limit: int = 128
    container_user: str = "65534:65534"
    nofile_limit: int = 256

    def __post_init__(self) -> None:
        """Normalize immutable identity and reject invalid resource bounds."""
        object.__setattr__(
            self,
            "container_image",
            validate_pinned_container_image(self.container_image),
        )
        if not str(self.executable or "").strip():
            raise ValueError("container executable is required")
        if not str(self.memory_limit or "").strip():
            raise ValueError("container memory_limit is required")
        if not str(self.cpu_limit or "").strip():
            raise ValueError("container cpu_limit is required")
        if not 1 <= self.pids_limit <= 4096:
            raise ValueError("pids_limit must be between 1 and 4096")
        if not 16 <= self.nofile_limit <= 4096:
            raise ValueError("nofile_limit must be between 16 and 4096")
        if not _is_numeric_user(self.container_user):
            raise ValueError("container_user must be numeric uid:gid")

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
            raise RuntimeError(
                f"container executable is unavailable: {self.executable}"
            )
        invocation = [
            executable,
            "run",
            "--rm",
            "--network",
            "none",
            "--ipc",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            self.container_user,
            "--pids-limit",
            str(self.pids_limit),
            "--ulimit",
            f"nofile={self.nofile_limit}:{self.nofile_limit}",
            "--ulimit",
            f"nproc={self.pids_limit}:{self.pids_limit}",
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
            "--env",
            "HOME=/tmp",
            "--env",
            "TMPDIR=/tmp",
            self.container_image,
            *command,
        ]
        capture = _run_bounded_process(
            invocation,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )
        return ContainerExecution(
            exit_code=capture.exit_code,
            stdout=_bounded_text(
                capture.stdout,
                max_output_bytes,
                truncated="stdout" in capture.truncated_streams,
            ),
            stderr=_bounded_text(
                capture.stderr,
                max_output_bytes,
                truncated="stderr" in capture.truncated_streams,
            ),
            timed_out=capture.timed_out,
            output_limit_exceeded=capture.output_limit_exceeded,
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
            normalized_contract = _required_identifier(
                build_contract_id, "build_contract_id"
            )
            workspace_id = stable_research_id(
                "coding_workspace",
                {
                    "attempt_id": normalized_attempt,
                    "build_contract_id": normalized_contract,
                    "repository_revision": self.policy.repository_revision,
                },
            )
            workspace_path = self._workspace_path(workspace_id)
            if self._tombstone_path(workspace_id).exists():
                raise ValueError(
                    "candidate attempt was already destroyed and cannot be reopened"
                )
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
                    raise ValueError(
                        "workspace identity resolves to conflicting manifest"
                    )
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
            workspace_path = self._workspace_path(workspace_id)
            if workspace_path.exists():
                manifest = self._load_manifest(workspace_id)
                files = self._candidate_files(workspace_id)
            else:
                manifest = self._load_tombstone(workspace_id)
                files = []
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
        roots: Sequence[str] = (
            "src/trader",
            "src/trader_standard",
            "docs/python_code_quality.md",
        ),
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
            matches = _search_files(
                candidates, self.policy.repository_root, normalized_query, int(limit)
            )
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
                "relative_path": path.relative_to(
                    self.policy.repository_root
                ).as_posix(),
                "content": content,
                "content_sha256": sha256(content.encode("utf-8")).hexdigest(),
            },
        )

    def write_candidate_file(
        self,
        workspace_id: str,
        relative_path: str,
        content: str,
        *,
        operation_id: str | None = None,
    ) -> ApplicationResult:
        """Idempotently write one bounded file inside an active workspace.

        Args:
            workspace_id: Exact active workspace identity.
            relative_path: Candidate-relative path with an allowed suffix.
            content: Complete replacement text for the file.
            operation_id: Optional stable transition identity. Agent runtime
                supplies one so a lost response can be resolved without
                replaying or silently replacing an accepted write.

        Returns:
            Exact path-independent content hash and updated workspace byte use.
        """
        try:
            self._require_active_workspace(workspace_id)
            encoded = str(content).encode("utf-8")
            if len(encoded) > self.policy.max_file_bytes:
                raise ValueError("candidate file exceeds max_file_bytes")
            content_hash = sha256(encoded).hexdigest()
            candidate_root = self._candidate_root(workspace_id)
            path = _safe_relative_target(
                candidate_root,
                relative_path,
                allowed_suffixes=SUPPORTED_CANDIDATE_SUFFIXES,
            )
            normalized_path = path.relative_to(candidate_root).as_posix()
            resolved_operation_id = _required_identifier(
                operation_id
                or stable_research_id(
                    "coding_write_operation",
                    {
                        "workspace_id": workspace_id,
                        "relative_path": normalized_path,
                        "content_sha256": content_hash,
                    },
                ),
                "operation_id",
            )
            request_hash = json_payload_hash(
                {
                    "command": CODING_WRITE_CANDIDATE_FILE,
                    "workspace_id": workspace_id,
                    "relative_path": normalized_path,
                    "content_sha256": content_hash,
                }
            )
            prior = self._recover_write_operation(
                workspace_id=workspace_id,
                operation_id=resolved_operation_id,
                path=path,
                candidate_root=candidate_root,
            )
            if prior is not None:
                if prior["request_hash"] != request_hash:
                    return error_result(
                        command=CODING_WRITE_CANDIDATE_FILE,
                        code="coding_operation_conflict",
                        message=(
                            "operation_id already identifies a different "
                            "candidate write"
                        ),
                        data={"accepted_operation": prior},
                    )
                if prior["status"] == "accepted":
                    return success_result(
                        command=CODING_WRITE_CANDIDATE_FILE,
                        data={**dict(prior["result"]), "idempotent_replay": True},
                    )
            existing_size = path.stat().st_size if path.exists() else 0
            current_size = self._workspace_size(candidate_root)
            if (
                current_size - existing_size + len(encoded)
                > self.policy.max_workspace_bytes
            ):
                raise ValueError("candidate workspace exceeds max_workspace_bytes")
            path.parent.mkdir(parents=True, exist_ok=True)
            operation = {
                "operation_id": resolved_operation_id,
                "command": CODING_WRITE_CANDIDATE_FILE,
                "workspace_id": workspace_id,
                "request_hash": request_hash,
                "relative_path": normalized_path,
                "content_sha256": content_hash,
                "content_bytes": len(encoded),
                "status": "prepared",
            }
            self._write_json_atomic(
                self._operation_path(workspace_id, resolved_operation_id),
                operation,
            )
            self._write_bytes_atomic(
                path,
                encoded,
                operation_id=resolved_operation_id,
            )
            result = {
                "workspace_id": workspace_id,
                "relative_path": normalized_path,
                "content_sha256": content_hash,
                "content_bytes": len(encoded),
                "workspace_bytes": self._workspace_size(candidate_root),
                "operation_id": resolved_operation_id,
                "idempotent_replay": False,
            }
            self._write_json_atomic(
                self._operation_path(workspace_id, resolved_operation_id),
                {**operation, "status": "accepted", "result": result},
            )
        except (OSError, ValueError, UnicodeError) as exc:
            return error_result(
                command=CODING_WRITE_CANDIDATE_FILE,
                code="candidate_write_failed",
                message=str(exc),
            )
        return success_result(command=CODING_WRITE_CANDIDATE_FILE, data=result)

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
            "status": "passed"
            if execution.exit_code == 0 and not execution.timed_out
            else "failed",
            **execution.to_dict(),
        }
        if payload["status"] == "passed":
            return success_result(command=CODING_RUN_CHECK, data={"check": payload})
        return error_result(
            command=CODING_RUN_CHECK,
            code="coding_check_failed",
            message=(
                "coding check timed out"
                if execution.timed_out
                else "coding check exceeded its output limit"
                if execution.output_limit_exceeded
                else "coding check returned non-zero"
            ),
            data={"check": payload},
        )

    def package_candidate(
        self,
        workspace_id: str,
        *,
        implementation_path: str = "implementation.py",
    ) -> ApplicationResult:
        """Build and retain a content-addressed inert candidate package.

        Python syntax is parsed without importing or executing the candidate.
        Complete source is retained in a service-owned immutable package, not
        returned through the model-facing result. A later deterministic MCP
        adapter can resolve the package for ordinary implementation
        registration after the disposable workspace has been destroyed.

        Args:
            workspace_id: Exact active candidate workspace identity.
            implementation_path: Candidate-relative Python implementation.

        Returns:
            Public package identity, source hash, file manifest, and lineage.
        """
        try:
            workspace = dict(self._require_active_workspace(workspace_id))
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
            for path in sorted(
                item for item in candidate_root.rglob("*") if item.is_file()
            ):
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
            package = {
                "package_id": package_id,
                "workspace_id": workspace_id,
                "attempt_id": workspace["attempt_id"],
                "build_contract_id": workspace["build_contract_id"],
                "repository_revision": self.policy.repository_revision,
                "implementation_path": implementation_path,
                "source_code": source_code,
                "source_hash": sha256(source_code.encode("utf-8")).hexdigest(),
                "files": files,
                "status": "packaged_inert_candidate",
            }
            package_path = self._package_path(package_id)
            if package_path.exists():
                if self.resolve_candidate_package(package_id) != package:
                    raise ValueError(
                        "candidate package identity resolves to conflicting content"
                    )
            else:
                self._write_json_atomic(package_path, package)
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
                    key: value for key, value in package.items() if key != "source_code"
                }
            },
        )

    def resolve_candidate_package(self, package_id: str) -> dict[str, Any]:
        """Resolve one immutable package for trusted registration code.

        This method deliberately returns complete source and is therefore not
        registered as a model-facing MCP read tool. Callers must remain inside
        the deterministic coding-to-registration adapter.

        Args:
            package_id: Exact content-addressed package identity.

        Returns:
            Validated package payload including complete source text.

        Raises:
            OSError: If the retained package cannot be read.
            ValueError: If identity, source hash, or package structure is
                inconsistent.
        """
        normalized_id = _required_identifier(package_id, "package_id")
        payload = json.loads(
            self._package_path(normalized_id).read_text(encoding="utf-8")
        )
        if not isinstance(payload, Mapping):
            raise ValueError("candidate package must be an object")
        package = dict(payload)
        if package.get("package_id") != normalized_id:
            raise ValueError("candidate package identity mismatch")
        source_code = package.get("source_code")
        if not isinstance(source_code, str) or not source_code:
            raise ValueError("candidate package has no source code")
        if sha256(source_code.encode("utf-8")).hexdigest() != package.get(
            "source_hash"
        ):
            raise ValueError("candidate package source hash mismatch")
        files = package.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError("candidate package has no file manifest")
        expected_id = stable_research_id(
            "coding_candidate_package",
            {
                "workspace_id": package.get("workspace_id"),
                "repository_revision": package.get("repository_revision"),
                "implementation_path": package.get("implementation_path"),
                "files": files,
            },
        )
        if expected_id != normalized_id:
            raise ValueError("candidate package content does not match its identity")
        return package

    def destroy_workspace(self, workspace_id: str) -> ApplicationResult:
        """Idempotently remove one exact disposable workspace.

        A small source-free tombstone is written before deletion. Recovery can
        therefore finish cleanup after a crash or return the accepted result
        after a lost response without recreating or broadly deleting state.
        """
        try:
            workspace_path = self._workspace_path(workspace_id)
            tombstone_path = self._tombstone_path(workspace_id)
            idempotent_replay = tombstone_path.exists()
            if idempotent_replay:
                manifest = self._load_tombstone(workspace_id)
            else:
                manifest = {
                    **self._load_manifest(workspace_id),
                    "status": "destroying",
                    "recoverable": False,
                }
                self._write_json_atomic(tombstone_path, manifest)
            if workspace_path.exists():
                shutil.rmtree(workspace_path)
            manifest = {
                **manifest,
                "status": "destroyed",
                "recoverable": False,
            }
            self._write_json_atomic(tombstone_path, manifest)
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
                "idempotent_replay": idempotent_replay,
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
        if (
            not isinstance(payload, Mapping)
            or payload.get("workspace_id") != workspace_id
        ):
            raise ValueError("workspace manifest identity mismatch")
        return dict(payload)

    def _tombstone_path(self, workspace_id: str) -> Path:
        """Return the exact source-free cleanup receipt path for a workspace."""
        normalized = _required_identifier(workspace_id, "workspace_id")
        directory = (self.policy.workspace_root / _TOMBSTONE_DIRECTORY).resolve()
        if directory.parent != self.policy.workspace_root:
            raise ValueError("workspace tombstone directory escapes workspace_root")
        return directory / f"{normalized}.json"

    def _package_path(self, package_id: str) -> Path:
        """Return the exact service-owned immutable package path."""
        normalized = _required_identifier(package_id, "package_id")
        directory = (self.policy.workspace_root / _PACKAGE_DIRECTORY).resolve()
        if directory.parent != self.policy.workspace_root:
            raise ValueError("candidate package directory escapes workspace_root")
        return directory / f"{normalized}.json"

    def _load_tombstone(self, workspace_id: str) -> dict[str, Any]:
        """Load and validate one exact workspace cleanup receipt."""
        path = self._tombstone_path(workspace_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, Mapping)
            or payload.get("workspace_id") != workspace_id
        ):
            raise ValueError("workspace tombstone identity mismatch")
        if payload.get("status") not in {"destroying", "destroyed"}:
            raise ValueError("workspace tombstone status is invalid")
        return dict(payload)

    def _operation_path(self, workspace_id: str, operation_id: str) -> Path:
        """Return one exact service-owned operation receipt path."""
        normalized = _required_identifier(operation_id, "operation_id")
        directory = (
            self._workspace_path(workspace_id) / _OPERATION_DIRECTORY
        ).resolve()
        if directory.parent != self._workspace_path(workspace_id):
            raise ValueError("workspace operation directory escapes workspace")
        return directory / f"{normalized}.json"

    def _recover_write_operation(
        self,
        *,
        workspace_id: str,
        operation_id: str,
        path: Path,
        candidate_root: Path,
    ) -> dict[str, Any] | None:
        """Resolve an accepted or prepared write without reapplying content."""
        operation_path = self._operation_path(workspace_id, operation_id)
        if not operation_path.exists():
            return None
        payload = json.loads(operation_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("workspace operation receipt must be an object")
        operation = dict(payload)
        expected = {
            "operation_id": operation_id,
            "command": CODING_WRITE_CANDIDATE_FILE,
            "workspace_id": workspace_id,
        }
        if any(operation.get(key) != value for key, value in expected.items()):
            raise ValueError("workspace operation receipt identity mismatch")
        if operation.get("status") not in {"prepared", "accepted"}:
            raise ValueError("workspace operation receipt status is invalid")
        if operation["status"] == "accepted":
            if not isinstance(operation.get("result"), Mapping):
                raise ValueError("accepted workspace operation has no result")
            return operation
        expected_hash = str(operation.get("content_sha256") or "")
        if path.is_file() and sha256(path.read_bytes()).hexdigest() == expected_hash:
            result = {
                "workspace_id": workspace_id,
                "relative_path": str(operation.get("relative_path") or ""),
                "content_sha256": expected_hash,
                "content_bytes": int(operation.get("content_bytes") or 0),
                "workspace_bytes": self._workspace_size(candidate_root),
                "operation_id": operation_id,
                "idempotent_replay": True,
            }
            operation = {**operation, "status": "accepted", "result": result}
            self._write_json_atomic(operation_path, operation)
        return operation

    def _write_manifest(
        self, workspace_path: Path, manifest: Mapping[str, Any]
    ) -> None:
        self._write_json_atomic(workspace_path / _MANIFEST_NAME, manifest)

    @staticmethod
    def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
        """Replace one service-owned JSON record atomically on one filesystem."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(
            json.dumps(dict(payload), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(path)

    @staticmethod
    def _write_bytes_atomic(
        path: Path,
        content: bytes,
        *,
        operation_id: str,
    ) -> None:
        """Atomically replace one candidate file with complete bounded bytes."""
        temporary = path.with_name(f".{path.name}.{operation_id}.tmp")
        temporary.write_bytes(content)
        temporary.replace(path)

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
            for path in sorted(
                item for item in candidate_root.rglob("*") if item.is_file()
            )
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
                if candidate.is_file()
                and candidate.suffix in _SEARCHABLE_REPOSITORY_SUFFIXES
            )
        return tuple(dict.fromkeys(sorted(files)))

    @staticmethod
    def _workspace_size(candidate_root: Path) -> int:
        return sum(
            path.stat().st_size for path in candidate_root.rglob("*") if path.is_file()
        )


def _container_check_command(check_name: str) -> list[str]:
    commands = {
        "compile": [
            "python",
            "-m",
            "py_compile",
            "/workspace/candidate/implementation.py",
        ],
        "ruff": ["ruff", "check", "/workspace/candidate"],
        "pytest": ["pytest", "-q", "/workspace/candidate"],
    }
    try:
        return commands[check_name]
    except KeyError as exc:
        raise ValueError(f"unsupported coding check: {check_name}") from exc


@dataclass(frozen=True)
class _BoundedProcessCapture:
    """Bounded byte capture from one container-client process."""

    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    output_limit_exceeded: bool
    truncated_streams: frozenset[str]


def _run_bounded_process(
    invocation: Sequence[str],
    *,
    timeout_seconds: int,
    max_output_bytes: int,
) -> _BoundedProcessCapture:
    """Run a process while enforcing per-stream memory and time ceilings.

    The process is terminated as soon as either stream would exceed its byte
    ceiling. Unlike ``subprocess.run(capture_output=True)``, this function
    never accumulates unbounded child output before truncating it.

    Args:
        invocation: Exact argument-vector invocation without a shell.
        timeout_seconds: Positive wall-clock deadline.
        max_output_bytes: Positive byte ceiling for each output stream.

    Returns:
        Bounded process result and the stream identities that were truncated.

    Raises:
        ValueError: If a resource ceiling is not positive.
        OSError: If the process cannot be started or its pipes cannot be read.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if max_output_bytes <= 0:
        raise ValueError("max_output_bytes must be positive")
    process = subprocess.Popen(
        list(invocation),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        start_new_session=True,
    )
    if process.stdout is None or process.stderr is None:
        _terminate_process(process)
        raise RuntimeError("container process output pipes are unavailable")
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    truncated_streams: set[str] = set()
    timed_out = False
    deadline = time.monotonic() + timeout_seconds
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            events = selector.select(timeout=min(remaining, 0.1))
            for key, _ in events:
                chunk = os.read(key.fd, 8192)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                stream_name = str(key.data)
                buffer = buffers[stream_name]
                remaining_bytes = max_output_bytes - len(buffer)
                if len(chunk) > remaining_bytes:
                    buffer.extend(chunk[:remaining_bytes])
                    truncated_streams.add(stream_name)
                    break
                buffer.extend(chunk)
            if truncated_streams:
                break
    if timed_out or truncated_streams:
        _terminate_process(process)
    else:
        remaining = max(0.01, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process(process)
    for stream in (process.stdout, process.stderr):
        if not stream.closed:
            stream.close()
    return _BoundedProcessCapture(
        exit_code=None if timed_out else process.returncode,
        stdout=bytes(buffers["stdout"]),
        stderr=bytes(buffers["stderr"]),
        timed_out=timed_out,
        output_limit_exceeded=bool(truncated_streams),
        truncated_streams=frozenset(truncated_streams),
    )


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    """Terminate and reap one bounded container-client process."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def _runner_metadata(runner: DockerContainerRunner, check_name: str) -> dict[str, Any]:
    return {
        "runner": "docker",
        "container_image": runner.container_image,
        "check_name": check_name,
        "network_enabled": False,
        "root_filesystem_read_only": True,
        "workspace_mount_read_only": True,
        "capabilities_dropped": True,
        "no_new_privileges": True,
        "ipc_mode": "none",
        "container_user": runner.container_user,
        "output_limit_enforced_during_execution": True,
        "memory_limit": runner.memory_limit,
        "cpu_limit": runner.cpu_limit,
        "pids_limit": runner.pids_limit,
        "nofile_limit": runner.nofile_limit,
    }


def _bounded_text(
    value: object,
    max_bytes: int,
    *,
    truncated: bool = False,
) -> str:
    """Decode text within an exact byte ceiling and optional truncation mark."""
    if value is None:
        return ""
    encoded = (
        value
        if isinstance(value, bytes)
        else str(value).encode("utf-8", errors="replace")
    )
    if len(encoded) <= max_bytes and not truncated:
        return encoded.decode("utf-8", errors="replace")
    marker = b"\n...[output truncated]"
    if max_bytes <= len(marker):
        return marker[:max_bytes].decode("utf-8", errors="replace")
    return (encoded[: max_bytes - len(marker)] + marker).decode(
        "utf-8", errors="replace"
    )


def _is_numeric_user(value: str) -> bool:
    """Return whether a container identity is a numeric ``uid:gid`` pair."""
    parts = str(value or "").split(":")
    return len(parts) == 2 and all(part.isdigit() for part in parts)


def _required_identifier(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    if not all(
        character.isalnum() or character in {"-", "_"} for character in normalized
    ):
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
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
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
