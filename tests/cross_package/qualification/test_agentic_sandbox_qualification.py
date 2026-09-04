"""Real OCI isolation qualification for agent-authored candidate checks.

Subject: Container isolation at the untrusted candidate-validation boundary.
Level: Cross-package controlled qualification.
Collaborators: Real Docker runtime and pinned image with temporary candidate workspaces.
Guarantees: Identity, filesystem, network, resource, cleanup, and no-host-fallback controls hold.
Non-goals: Candidate correctness, image construction, provider access, or production deployment.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import textwrap

import pytest

from tests.cross_package.qualification.support.postgres_verification import (
    AGENTIC_VERIFICATION_PROFILE,
    RETAIN_EVIDENCE_PHASE_ENV,
    VERIFICATION_PROFILE_ENV,
    load_qualification_profile,
    load_retained_evidence_phase,
)
from trader_research.coding.workspace import DockerContainerRunner


_PHASE = "AGENTIC_SANDBOX"
_IMAGE_ENV = "TRADER_MCP_CODING_CONTAINER_IMAGE"
_HOST_SECRET_ENV = "TRADER_SANDBOX_QUALIFICATION_SECRET"


def test_real_container_enforces_the_admitted_sandbox_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove identity, filesystem, network, resource, and secret isolation."""
    image = _require_sandbox_phase()
    secret = "must-not-cross-the-container-boundary"
    monkeypatch.setenv(_HOST_SECRET_ENV, secret)
    workspace = _workspace_with_test(
        tmp_path,
        """
        import os
        from pathlib import Path
        import socket


        def _cgroup_value(name: str) -> str:
            return (Path("/sys/fs/cgroup") / name).read_text(encoding="ascii").strip()


        def test_isolation_contract() -> None:
            assert os.getuid() != 0
            assert os.getgid() != 0
            status = Path("/proc/self/status").read_text(encoding="ascii")
            assert "NoNewPrivs:\\t1" in status
            assert "CapEff:\\t0000000000000000" in status
            assert os.environ.get("TRADER_SANDBOX_QUALIFICATION_SECRET") is None

            for target in (
                Path("/qualification-write-probe"),
                Path("/workspace/candidate/qualification-write-probe"),
            ):
                try:
                    target.write_text("not allowed", encoding="ascii")
                except OSError:
                    pass
                else:
                    raise AssertionError(f"writable protected path: {target}")

            temporary = Path("/tmp/qualification-write-probe")
            temporary.write_text("bounded", encoding="ascii")
            assert temporary.read_text(encoding="ascii") == "bounded"

            mounts = Path("/proc/mounts").read_text(encoding="ascii").splitlines()
            tmp_mount = next(line for line in mounts if line.split()[1] == "/tmp")
            tmp_options = set(tmp_mount.split()[3].split(","))
            assert {"rw", "noexec", "nosuid"}.issubset(tmp_options)

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
                connection.settimeout(0.25)
                try:
                    connection.connect(("1.1.1.1", 53))
                except OSError:
                    pass
                else:
                    raise AssertionError("sandbox acquired an external network path")

            assert int(_cgroup_value("pids.max")) <= 128
            assert int(_cgroup_value("memory.max")) <= 512 * 1024 * 1024
            quota, period = _cgroup_value("cpu.max").split()
            assert quota != "max"
            assert int(quota) <= int(period)
        """,
    )
    execution = DockerContainerRunner(image).run(
        workspace_path=workspace,
        check_name="pytest",
        timeout_seconds=15,
        max_output_bytes=16_000,
    )

    assert execution.exit_code == 0, (execution.stdout, execution.stderr)
    assert execution.timed_out is False
    assert execution.output_limit_exceeded is False
    assert execution.metadata["container_image"] == image
    assert execution.metadata["container_user"] == "65534:65534"


def test_real_container_is_removed_after_deadline_and_output_cutoff(
    tmp_path: Path,
) -> None:
    """Prove host-enforced limits leave no sandbox process behind."""
    image = _require_sandbox_phase()
    timeout_workspace = _workspace_with_test(
        tmp_path / "timeout",
        """
        import time


        def test_never_finishes() -> None:
            time.sleep(60)
        """,
    )
    runner = DockerContainerRunner(image)

    timed_out = runner.run(
        workspace_path=timeout_workspace,
        check_name="pytest",
        timeout_seconds=2,
        max_output_bytes=1_024,
    )
    assert timed_out.timed_out is True
    assert timed_out.output_limit_exceeded is False
    _assert_no_running_container_for_image(image)

    flood_workspace = _workspace_with_test(
        tmp_path / "output",
        """
        def test_floods_output() -> None:
            print("x" * 65536)
        """,
    )
    flooded = runner.run(
        workspace_path=flood_workspace,
        check_name="pytest",
        timeout_seconds=15,
        max_output_bytes=512,
    )
    assert flooded.timed_out is False
    assert flooded.output_limit_exceeded is True
    assert len(flooded.stdout.encode("utf-8")) <= 512
    assert len(flooded.stderr.encode("utf-8")) <= 512
    _assert_no_running_container_for_image(image)


def test_container_unavailability_never_falls_back_to_host_execution(
    tmp_path: Path,
) -> None:
    """Reject an unavailable OCI client without running candidate source."""
    image = _require_sandbox_phase()
    workspace = tmp_path / "unavailable"
    candidate = workspace / "candidate"
    candidate.mkdir(parents=True)
    sentinel = tmp_path / "host-execution-sentinel"
    (candidate / "implementation.py").write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('unsafe')\n",
        encoding="utf-8",
    )
    runner = DockerContainerRunner(
        image,
        executable="trader-deliberately-unavailable-container-client",
    )

    with pytest.raises(RuntimeError, match="container executable is unavailable"):
        runner.run(
            workspace_path=workspace,
            check_name="compile",
            timeout_seconds=5,
            max_output_bytes=1_024,
        )

    assert sentinel.exists() is False


def _require_sandbox_phase() -> str:
    """Return the pinned sandbox image or skip outside its controlled phase."""
    if load_qualification_profile().name != AGENTIC_VERIFICATION_PROFILE:
        pytest.skip(f"set {VERIFICATION_PROFILE_ENV}={AGENTIC_VERIFICATION_PROFILE}")
    if load_retained_evidence_phase() != _PHASE:
        pytest.skip(f"set {RETAIN_EVIDENCE_PHASE_ENV}={_PHASE}")
    image = str(os.environ.get(_IMAGE_ENV) or "").strip()
    if not image:
        raise RuntimeError(f"{_IMAGE_ENV} must identify the admitted sandbox image")
    return image


def _workspace_with_test(root: Path, source: str) -> Path:
    """Create the minimal read-only host workspace consumed by the runner."""
    candidate = root / "candidate"
    candidate.mkdir(parents=True)
    root.chmod(0o755)
    candidate.chmod(0o755)
    implementation = candidate / "implementation.py"
    test_file = candidate / "test_sandbox.py"
    implementation.write_text("PASS = True\n", encoding="utf-8")
    test_file.write_text(
        textwrap.dedent(source),
        encoding="utf-8",
    )
    implementation.chmod(0o444)
    test_file.chmod(0o444)
    return root


def _assert_no_running_container_for_image(image: str) -> None:
    """Prove no container for the exact admitted image remains running."""
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--quiet",
            "--filter",
            f"ancestor={image}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.stdout.strip() == ""
