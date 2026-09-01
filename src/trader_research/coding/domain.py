"""Typed contracts for isolated research coding workspaces.

The contracts normalize workspace policy and container execution results. They
contain no filesystem, process, container, network, or persistence side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


SUPPORTED_CODING_CHECKS = frozenset({"compile", "ruff", "pytest"})
SUPPORTED_CANDIDATE_SUFFIXES = frozenset({".py", ".json", ".toml", ".md"})


@dataclass(frozen=True)
class CodingWorkspacePolicy:
    """Validated policy for one Coding Workspace service.

    Attributes:
        workspace_root: Dedicated root containing disposable workspaces.
        repository_root: Pinned repository snapshot exposed read-only.
        repository_revision: Exact revision represented by the snapshot.
        container_image: Pinned container image used for checks.
        allowed_dependencies: Dependency names permitted by the build profile.
        max_file_bytes: Maximum bytes accepted for one candidate file.
        max_output_bytes: Maximum captured bytes from a check.
        max_workspace_bytes: Maximum total candidate bytes before packaging.
        default_timeout_seconds: Default bounded check timeout.
    """

    workspace_root: Path
    repository_root: Path
    repository_revision: str
    container_image: str
    allowed_dependencies: tuple[str, ...] = ()
    max_file_bytes: int = 512_000
    max_output_bytes: int = 64_000
    max_workspace_bytes: int = 2_000_000
    default_timeout_seconds: int = 60

    def __post_init__(self) -> None:
        """Normalize paths and reject unsafe or incomplete policy values."""
        workspace_root = Path(self.workspace_root).resolve()
        repository_root = Path(self.repository_root).resolve()
        if workspace_root in {Path("/").resolve(), Path.home().resolve()}:
            raise ValueError("workspace_root must be a dedicated bounded directory")
        if not repository_root.is_dir():
            raise ValueError("repository_root must be an existing directory")
        revision = str(self.repository_revision or "").strip()
        image = str(self.container_image or "").strip()
        if not revision:
            raise ValueError("repository_revision is required")
        if not image:
            raise ValueError("container_image is required")
        if self.max_file_bytes <= 0 or self.max_output_bytes <= 0:
            raise ValueError("file and output byte limits must be positive")
        if self.max_workspace_bytes < self.max_file_bytes:
            raise ValueError("max_workspace_bytes must be at least max_file_bytes")
        if self.default_timeout_seconds <= 0:
            raise ValueError("default_timeout_seconds must be positive")
        dependencies = tuple(
            dict.fromkeys(
                dependency
                for item in self.allowed_dependencies
                if (dependency := str(item or "").strip())
            )
        )
        object.__setattr__(self, "workspace_root", workspace_root)
        object.__setattr__(self, "repository_root", repository_root)
        object.__setattr__(self, "repository_revision", revision)
        object.__setattr__(self, "container_image", image)
        object.__setattr__(self, "allowed_dependencies", dependencies)

    def public_summary(self) -> dict[str, Any]:
        """Return non-secret policy metadata safe for model-facing tools."""
        return {
            "repository_revision": self.repository_revision,
            "container_image": self.container_image,
            "allowed_dependencies": list(self.allowed_dependencies),
            "supported_checks": sorted(SUPPORTED_CODING_CHECKS),
            "supported_candidate_suffixes": sorted(SUPPORTED_CANDIDATE_SUFFIXES),
            "max_file_bytes": self.max_file_bytes,
            "max_output_bytes": self.max_output_bytes,
            "max_workspace_bytes": self.max_workspace_bytes,
            "default_timeout_seconds": self.default_timeout_seconds,
            "network_enabled": False,
            "host_repository_writable": False,
        }


@dataclass(frozen=True)
class ContainerExecution:
    """Bounded result returned by an isolated container runner.

    Attributes:
        exit_code: Process exit status, or ``None`` when the runner timed out.
        stdout: Bounded standard output.
        stderr: Bounded standard error.
        timed_out: Whether the configured deadline stopped the check.
        metadata: Non-secret runner and resource metadata.
    """

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-native execution result."""
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "metadata": dict(self.metadata),
        }
