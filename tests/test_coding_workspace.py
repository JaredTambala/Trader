"""Focused safety and lifecycle contracts for the Coding Workspace service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trader_research.coding import (
    CodingWorkspacePolicy,
    CodingWorkspaceService,
    ContainerExecution,
)


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
    replayed = service.write_candidate_file(
        workspace_id,
        "implementation.py",
        "def build_strategy(**kwargs):\n    return kwargs\n",
        operation_id="write-step-1",
    )
    conflicted = service.write_candidate_file(
        workspace_id,
        "implementation.py",
        "raise RuntimeError('different write')\n",
        operation_id="write-step-1",
    )
    packaged = service.package_candidate(workspace_id)

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
    service = _service(tmp_path)

    searched = service.search_repository(query="public contract", roots=("src",))
    read = service.read_repository_file("src/interface.py")
    escaped = service.read_repository_file("../secret.txt")

    assert searched.ok is True
    assert searched.data["matches"][0]["relative_path"] == "src/interface.py"
    assert read.data["content"] == "# public contract\n"
    assert escaped.ok is False


def test_dependency_policy_never_installs_unapproved_packages(tmp_path: Path) -> None:
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


def test_cleanup_removes_only_exact_workspace(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = service.create_workspace(
        attempt_id="attempt-1", build_contract_id="contract-1"
    )
    second = service.create_workspace(
        attempt_id="attempt-2", build_contract_id="contract-1"
    )

    destroyed = service.destroy_workspace(first.data["workspace"]["workspace_id"])
    replayed = service.destroy_workspace(first.data["workspace"]["workspace_id"])
    resolved = service.get_workspace(first.data["workspace"]["workspace_id"])
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
        container_image="trader-agent-coding@sha256:demo",
        allowed_dependencies=("trader",),
    )
    return CodingWorkspaceService(policy, runner=runner)
