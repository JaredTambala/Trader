"""Test-owned local Console processes; never use a developer's database or server."""

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import signal
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx

from examples.console_demo.runtime import bootstrap


REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_ROOT / "examples/console_demo/compose.yml"


def docker_command() -> str:
    """Resolve Docker for native hosts and WSL environments with Docker Desktop."""
    return shutil.which("docker.exe") or shutil.which("docker") or "docker"


@contextmanager
def compose_environment(port: int) -> Iterator[str | None]:
    """Expose Compose interpolation to Docker Desktop when WSL env forwarding is absent."""
    if not docker_command().lower().endswith(".exe"):
        yield None
        return

    shared_directory = Path("/mnt/c/Users/Public")
    directory = shared_directory if shared_directory.is_dir() else None
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="trader-console-", suffix=".env",
            dir=directory, delete=False
        ) as environment_file:
            environment_file.write(f"CONSOLE_DEMO_DATABASE_PORT={port}\n")
            temporary_path = environment_file.name
        path_for_docker = temporary_path
        if directory is not None:
            path_for_docker = subprocess.run(
                ["wslpath", "-w", temporary_path],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        yield path_for_docker
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)


def free_port() -> int:
    """Choose an unused loopback port for this test's processes."""
    # Avoid Docker Desktop's host-reserved dynamic port range, invisible to WSL sockets.
    for _ in range(100):
        with socket.socket() as listener:
            port = 20_000 + secrets.randbelow(10_000)
            try:
                listener.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No free Console test port found in 20000–29999")


@contextmanager
def database() -> Iterator[tuple[int, list[str], dict[str, str]]]:
    """Own a unique Compose project and remove only its temporary volume on exit."""
    port = free_port()
    environment = dict(os.environ, CONSOLE_DEMO_DATABASE_PORT=str(port))
    with compose_environment(port) as env_file:
        command = [docker_command(), "compose"]
        if env_file:
            command.extend(["--env-file", env_file])
        command.extend([
            "-f",
            str(COMPOSE_FILE),
            "-p",
            f"trader-console-test-{uuid4().hex[:12]}",
        ])
        try:
            subprocess.run(
                [*command, "up", "-d", "--wait"], env=environment, check=True, timeout=180
            )
            bootstrap(port)
            yield port, command, environment
        finally:
            subprocess.run(
                [*command, "down", "--volumes"], env=environment, check=True, timeout=60
            )


@contextmanager
def server(
    command: list[str],
    url: str,
    *,
    environment: dict[str, str] | None = None,
    cwd: Path = REPO_ROOT,
) -> Iterator[subprocess.Popen]:
    """Wait for one owned HTTP process and terminate it even when assertions fail."""
    with tempfile.TemporaryFile(mode="w+") as log:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 60
            ready = False
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    if httpx.get(url, timeout=1).status_code == 200:
                        ready = True
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.2)
            if not ready:
                log.seek(0)
                raise RuntimeError(
                    f"Console test process did not become ready: {log.read()}"
                )
            yield process
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)


def api_command(database_port: int, api_port: int) -> list[str]:
    """Start the real demo API as a separate process with explicit local ports."""
    return [
        sys.executable,
        "-m",
        "examples.console_demo",
        "api",
        "--database-port",
        str(database_port),
        "--api-port",
        str(api_port),
    ]
