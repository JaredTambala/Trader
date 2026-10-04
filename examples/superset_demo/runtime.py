"""Own the dedicated local Superset processes and credentials, never ambient PG targets."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

from psycopg.conninfo import make_conninfo
from dotenv import dotenv_values


DEMO_ROOT = Path(__file__).resolve().parent
DATABASE = "trader_superset_demo"
OWNER = "superset_demo_owner"
READER = "superset_demo_reader"
SECRET_NAMES = ("TRADER_PASSWORD", "READER_PASSWORD", "METADATA_PASSWORD", "ADMIN_PASSWORD", "SECRET_KEY")


def local_secrets(directory: Path) -> dict[str, str]:
    """Create once, then reuse private local credentials without displaying their values.

    The caller owns this state directory. Never regenerate a partial or malformed
    file: the retained Superset metadata depends on the same encryption key.
    """
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / "credentials.json"
    if not path.exists():
        values = {name: secrets.token_hex(32) for name in SECRET_NAMES}
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as target:
            json.dump(values, target, indent=2)
            target.write("\n")
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("Demo credentials must be a private regular file (mode 600)")
    values = json.loads(path.read_text())
    if not isinstance(values, dict) or set(values) != set(SECRET_NAMES) or any(
        not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in values.values()
    ):
        raise ValueError("Invalid demo credentials; preserve the existing file and volumes")
    return values


def _docker_config(directory: Path) -> Path:
    """Return a private client config that does not invoke Windows helpers in WSL.

    Docker Desktop's WSL integration can expose a Linux daemon while the global
    client config still names ``desktop.exe`` as its credential helper. BuildKit
    then fails before it can pull the public Superset image. The demo does not
    need registry credentials, so an empty, demo-owned config is the narrowest
    safe override and leaves the user's global Docker configuration untouched.
    """
    config_directory = directory / "docker-config"
    config_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    config_path = config_directory / "config.json"
    if not config_path.exists():
        descriptor = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as target:
            json.dump({}, target)
            target.write("\n")
    if config_path.is_symlink() or config_path.stat().st_mode & 0o077:
        raise ValueError("Demo Docker config must be a private regular file (mode 600)")
    return config_directory


@dataclass(frozen=True)
class DemoStack:
    """Fixed local application identity, with independently selectable local ports.

    Attributes:
        state_directory: Private credential storage, separate for each test project.
        project: Manual demo identity or a uniquely named test-owned Compose project.
        database_port: Loopback PostgreSQL port; no external DSN is accepted.
        ui_port: Loopback Superset HTTP port.
    """

    state_directory: Path = DEMO_ROOT / ".local"
    project: str = "trader-superset-demo"
    database_port: int = 25433
    ui_port: int = 8088
    mcp_port: int = 5008

    def __post_init__(self) -> None:
        for port in (self.database_port, self.ui_port, self.mcp_port):
            if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
                raise ValueError("Demo ports must be integers between 1024 and 65535")
        if len({self.database_port, self.ui_port, self.mcp_port}) != 3:
            raise ValueError("Database, UI and MCP ports must differ")
        if self.project != "trader-superset-demo" and not re.fullmatch(
            r"trader-superset-test-[a-f0-9]{12}", self.project
        ):
            raise ValueError("Refusing a Compose project outside this demo")

    def environment(self) -> dict[str, str]:
        """Supply explicit demo values, overriding ambient configuration."""
        values = local_secrets(self.state_directory)
        environment = {
            **os.environ,
            "DOCKER_CONFIG": str(_docker_config(self.state_directory)),
            **{f"SUPERSET_DEMO_{key}": value for key, value in values.items()},
            "SUPERSET_DEMO_DATABASE_PORT": str(self.database_port),
            "SUPERSET_DEMO_UI_PORT": str(self.ui_port),
            "SUPERSET_DEMO_MCP_PORT": str(self.mcp_port),
        }
        # The real-data view is opt-in through the repository's explicit local
        # runtime configuration. It is never inferred from ambient PG_* values.
        local_values = dotenv_values(DEMO_ROOT.parents[1] / ".env")
        if local_values.get("PG_PASSWORD"):
            environment.update({
                "SUPERSET_DEMO_REAL_TRADER_PASSWORD": local_values["PG_PASSWORD"],
                "SUPERSET_DEMO_REAL_TRADER_USER": local_values.get("PG_USER", "trader"),
                "SUPERSET_DEMO_REAL_TRADER_DATABASE": local_values.get("PG_DB", "trader"),
                "SUPERSET_DEMO_REAL_TRADER_PORT": local_values.get("PG_PORT", "5432"),
            })
        return environment

    def dsn(self, *, reader: bool = False) -> str:
        """Return only the fixed loopback Trader demo connection; never log it."""
        values = local_secrets(self.state_directory)
        return make_conninfo(
            host="127.0.0.1", port=self.database_port, dbname=DATABASE,
            user=READER if reader else OWNER,
            password=values["READER_PASSWORD" if reader else "TRADER_PASSWORD"],
            connect_timeout=3,
        )

    def compose(self, *arguments: str, timeout: int = 180) -> None:
        """Run a bounded command against only this project's explicit Compose file."""
        subprocess.run(
            ["docker", "compose", "--project-name", self.project,
             "--file", str(DEMO_ROOT / "compose.yml"), *arguments],
            env=self.environment(), check=True, timeout=timeout,
        )

    def up(self) -> None:
        """Install explicitly before starting the web process; preserve retained state."""
        from .database import bootstrap

        self.compose("up", "-d", "--wait", "trader", "metadata")
        bootstrap(self)
        self.compose("build", "web", "initialize", "seed", timeout=900)
        self.compose("run", "--rm", "initialize", timeout=300)
        self.compose("up", "-d", "--wait", "web", "mcp")
        self.compose("run", "--rm", "seed", timeout=300)

    def restart(self) -> None:
        """Restart the web process and wait for health without rerunning initialization."""
        self.compose("restart", "web")
        self.compose("up", "-d", "--wait", "web")

    def down(self, *, remove_test_volumes: bool = False) -> None:
        """Stop owned processes; only uniquely named test projects may delete volumes."""
        if remove_test_volumes and not self.project.startswith("trader-superset-test-"):
            raise ValueError("Manual demo volumes are retained; no reset command is provided")
        self.compose("down", *(('--volumes',) if remove_test_volumes else ()), timeout=60)
