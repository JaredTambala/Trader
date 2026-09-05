"""Safety and lifecycle contracts for isolated candidate coding workspaces.

Subject: Workspace creation, bounded repository access, candidate writes, checks, packaging, and cleanup.
Level: Offline application and local subprocess contract.
Collaborators: Real filesystem service, injected check runner, and a fake Docker-compatible executable.
Guarantees: Workspaces are idempotent, path-safe, resource-bounded, inspectable, and exactly destructible.
Non-goals: Real container execution, package installation, strategy admission, Postgres, or agent reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from trader_research.coding import (
    CodingWorkspacePolicy,
    CodingWorkspaceService,
    ContainerExecution,
    DockerContainerRunner,
)


_PINNED_IMAGE = f"trader-agent-coding@sha256:{'a' * 64}"


@dataclass
class _Runner:
    result: ContainerExecution

    def run(
        self,
        *,
        workspace_path: Path,
        check_name: str,
        timeout_seconds: int,
        max_output_bytes: int,
    ) -> ContainerExecution:
        assert workspace_path.is_dir()
        assert check_name in {"compile", "ruff", "pytest"}
        assert timeout_seconds > 0
        assert max_output_bytes > 0
        return self.result


def test_workspace_is_idempotent_and_packages_inert_source(tmp_path: Path) -> None:
    """Repeated workspace operations preserve identity and package only inert source evidence."""
    service = _service(tmp_path)

    first = service.create_workspace(
        attempt_id="attempt-1", build_contract_id="contract-1"
    )
    second = service.create_workspace(
        attempt_id="attempt-1", build_contract_id="contract-1"
    )
    workspace_id = first.data["workspace"]["workspace_id"]
    written = service.write_candidate_file(
        workspace_id,
        "implementation.py",
        "def build_strategy(**kwargs):\n    return kwargs\n",
        operation_id="write-step-1",
    )
    restarted_service = _service(tmp_path)
    replayed = restarted_service.write_candidate_file(
        workspace_id,
        "implementation.py",
        "def build_strategy(**kwargs):\n    return kwargs\n",
        operation_id="write-step-1",
    )
    conflicted = restarted_service.write_candidate_file(
        workspace_id,
        "implementation.py",
        "raise RuntimeError('different write')\n",
        operation_id="write-step-1",
    )
    packaged = restarted_service.package_candidate(workspace_id)

    assert first.ok is True
    assert second.data["workspace"]["workspace_id"] == workspace_id
    assert written.ok is True
    assert written.data["idempotent_replay"] is False
    assert replayed.ok is True
    assert replayed.data["idempotent_replay"] is True
    assert conflicted.ok is False
    assert conflicted.errors[0]["code"] == "coding_operation_conflict"
    assert packaged.ok is True
    package = packaged.data["candidate_package"]
    assert package["status"] == "packaged_inert_candidate"
    assert package["source_hash"] == written.data["content_sha256"]
    assert "source_code" not in package
    assert package["files"] == [
        {
            "relative_path": "implementation.py",
            "content_sha256": written.data["content_sha256"],
            "content_bytes": written.data["content_bytes"],
        }
    ]
    retained = service.resolve_candidate_package(package["package_id"])
    assert retained["source_code"] == (
        "def build_strategy(**kwargs):\n    return kwargs\n"
    )


def test_workspace_rejects_path_escape_and_unsupported_files(tmp_path: Path) -> None:
    """Candidate writes reject directory escapes and files outside the approved source policy."""
    service = _service(tmp_path)
    created = service.create_workspace(
        attempt_id="attempt-1", build_contract_id="contract-1"
    )
    workspace_id = created.data["workspace"]["workspace_id"]

    escaped = service.write_candidate_file(workspace_id, "../../outside.py", "pass\n")
    unsupported = service.write_candidate_file(workspace_id, "payload.sh", "exit 0\n")

    assert escaped.ok is False
    assert escaped.errors[0]["code"] == "candidate_write_failed"
    assert unsupported.ok is False
    assert not (tmp_path / "outside.py").exists()


def test_repository_reads_are_bounded_and_read_only(tmp_path: Path) -> None:
    """Repository search and reads remain inside approved roots without mutation authority."""
    service = _service(tmp_path)

    searched = service.search_repository(query="public contract", roots=("src",))
    read = service.read_repository_file("src/interface.py")
    escaped = service.read_repository_file("../secret.txt")

    assert searched.ok is True
    assert searched.data["matches"][0]["relative_path"] == "src/interface.py"
    assert read.data["content"] == "# public contract\n"
    assert escaped.ok is False


def test_dependency_policy_never_installs_unapproved_packages(tmp_path: Path) -> None:
    """Dependency resolution accepts preinstalled allowlisted packages and denies every other request."""
    service = _service(tmp_path)
    created = service.create_workspace(
        attempt_id="attempt-1", build_contract_id="contract-1"
    )
    workspace_id = created.data["workspace"]["workspace_id"]

    accepted = service.resolve_dependencies(workspace_id, ["trader"])
    denied = service.resolve_dependencies(workspace_id, ["requests"])

    assert accepted.ok is True
    assert accepted.data["resolution"] == "preinstalled_in_pinned_container"
    assert denied.ok is False
    assert denied.errors[0]["code"] == "dependency_policy_denied"


def test_checks_fail_closed_without_runner_and_preserve_bounded_evidence(
    tmp_path: Path,
) -> None:
    """Checks require an injected runner and retain bounded terminal evidence."""
    unavailable = _service(tmp_path)
    created = unavailable.create_workspace(
        attempt_id="attempt-1", build_contract_id="contract-1"
    )
    workspace_id = created.data["workspace"]["workspace_id"]
    unavailable.write_candidate_file(workspace_id, "implementation.py", "pass\n")

    blocked = unavailable.run_check(workspace_id, "compile")
    passing = _service(
        tmp_path,
        runner=_Runner(ContainerExecution(exit_code=0, stdout="ok", stderr="")),
    ).run_check(workspace_id, "compile")

    assert blocked.ok is False
    assert blocked.errors[0]["code"] == "coding_check_unavailable"
    assert passing.ok is True
    assert passing.data["check"]["status"] == "passed"


def test_workspace_policy_requires_content_pinned_container_image(
    tmp_path: Path,
) -> None:
    """Workspace policy rejects mutable tags, malformed digests, and incomplete image identities."""
    repository_root = tmp_path / "repository"
    repository_root.mkdir()

    for image in (
        "trader-agent-coding:latest",
        "trader-agent-coding@sha256:demo",
        "trader-agent-coding@sha256:" + "g" * 64,
    ):
        with pytest.raises(ValueError, match="pinned"):
            CodingWorkspacePolicy(
                workspace_root=tmp_path / "workspaces",
                repository_root=repository_root,
                repository_revision="revision-1",
                container_image=image,
            )


def test_container_runner_builds_locked_down_non_root_invocation(
    tmp_path: Path,
) -> None:
    """The Docker-compatible client receives every accepted isolation control as explicit arguments."""
    executable = _fake_container_executable(
        tmp_path,
        "import sys\nprint('\\n'.join(sys.argv[1:]))\n",
    )
    workspace = tmp_path / "workspace"
    (workspace / "candidate").mkdir(parents=True)
    runner = DockerContainerRunner(
        _PINNED_IMAGE,
        executable=str(executable),
    )

    execution = runner.run(
        workspace_path=workspace,
        check_name="compile",
        timeout_seconds=5,
        max_output_bytes=16_000,
    )

    arguments = execution.stdout.splitlines()
    assert execution.exit_code == 0
    assert execution.timed_out is False
    assert execution.output_limit_exceeded is False
    assert _argument_value(arguments, "--network") == "none"
    assert _argument_value(arguments, "--ipc") == "none"
    assert _argument_value(arguments, "--user") == "65534:65534"
    assert _argument_value(arguments, "--pids-limit") == "128"
    assert _argument_value(arguments, "--memory") == "512m"
    assert _argument_value(arguments, "--cpus") == "1.0"
    assert "--read-only" in arguments
    assert "ALL" in arguments
    assert "no-new-privileges" in arguments
    assert f"nofile={runner.nofile_limit}:{runner.nofile_limit}" in arguments
    assert f"nproc={runner.pids_limit}:{runner.pids_limit}" in arguments
    assert any(
        item.startswith("type=bind,") and item.endswith(",readonly")
        for item in arguments
    )
    assert _PINNED_IMAGE in arguments
    assert execution.metadata["output_limit_enforced_during_execution"] is True


def test_container_runner_terminates_on_output_limit(tmp_path: Path) -> None:
    """The host terminates noisy container clients while retaining bounded output evidence."""
    executable = _fake_container_executable(
        tmp_path,
        "import os\nos.write(1, b'x' * 4096)\nos.write(2, b'y' * 4096)\n",
    )
    workspace = tmp_path / "workspace"
    (workspace / "candidate").mkdir(parents=True)
    runner = DockerContainerRunner(
        _PINNED_IMAGE,
        executable=str(executable),
    )

    execution = runner.run(
        workspace_path=workspace,
        check_name="compile",
        timeout_seconds=5,
        max_output_bytes=128,
    )

    assert execution.timed_out is False
    assert execution.output_limit_exceeded is True
    assert len(execution.stdout.encode("utf-8")) <= 128
    assert len(execution.stderr.encode("utf-8")) <= 128
    assert (
        "output truncated" in execution.stdout or "output truncated" in execution.stderr
    )


def test_container_runner_terminates_on_deadline(tmp_path: Path) -> None:
    """The host-enforced deadline terminates execution and returns bounded timeout evidence."""
    executable = _fake_container_executable(
        tmp_path,
        "import time\nprint('started', flush=True)\ntime.sleep(5)\n",
    )
    workspace = tmp_path / "workspace"
    (workspace / "candidate").mkdir(parents=True)
    runner = DockerContainerRunner(
        _PINNED_IMAGE,
        executable=str(executable),
    )

    execution = runner.run(
        workspace_path=workspace,
        check_name="compile",
        timeout_seconds=1,
        max_output_bytes=128,
    )

    assert execution.exit_code is None
    assert execution.timed_out is True
    assert execution.output_limit_exceeded is False
    assert execution.stdout == "started\n"


def test_cleanup_removes_only_exact_workspace(tmp_path: Path) -> None:
    """Cleanup destroys only the requested workspace and replays idempotently after restart."""
    service = _service(tmp_path)
    first = service.create_workspace(
        attempt_id="attempt-1", build_contract_id="contract-1"
    )
    second = service.create_workspace(
        attempt_id="attempt-2", build_contract_id="contract-1"
    )

    destroyed = service.destroy_workspace(first.data["workspace"]["workspace_id"])
    restarted_service = _service(tmp_path)
    replayed = restarted_service.destroy_workspace(
        first.data["workspace"]["workspace_id"]
    )
    resolved = restarted_service.get_workspace(first.data["workspace"]["workspace_id"])
    still_present = service.get_workspace(second.data["workspace"]["workspace_id"])

    assert destroyed.ok is True
    assert destroyed.data["recoverable"] is False
    assert destroyed.data["idempotent_replay"] is False
    assert replayed.ok is True
    assert replayed.data["idempotent_replay"] is True
    assert resolved.ok is True
    assert resolved.data["workspace"]["status"] == "destroyed"
    assert resolved.data["workspace"]["candidate_files"] == []
    assert still_present.ok is True


def _service(
    tmp_path: Path,
    *,
    runner: _Runner | None = None,
) -> CodingWorkspaceService:
    repository_root = tmp_path / "repository"
    (repository_root / "src").mkdir(parents=True, exist_ok=True)
    (repository_root / "src" / "interface.py").write_text(
        "# public contract\n",
        encoding="utf-8",
    )
    policy = CodingWorkspacePolicy(
        workspace_root=tmp_path / "workspaces",
        repository_root=repository_root,
        repository_revision="revision-1",
        container_image=_PINNED_IMAGE,
        allowed_dependencies=("trader",),
    )
    return CodingWorkspaceService(policy, runner=runner)


def _fake_container_executable(tmp_path: Path, body: str) -> Path:
    """Create an executable test double for a Docker-compatible CLI."""
    executable = tmp_path / f"fake-container-{abs(hash(body))}"
    executable.write_text(f"#!/usr/bin/env python3\n{body}", encoding="utf-8")
    executable.chmod(0o755)
    return executable


def _argument_value(arguments: list[str], option: str) -> str:
    """Return the value immediately following one invocation option."""
    return arguments[arguments.index(option) + 1]
